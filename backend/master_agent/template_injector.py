"""Template Injection (mainpromt.md sec.39-43): writes a verified
AgentResponse's sections into the SAR Template Document object kept in
memory, preserving existing structure/style/font.

Targets are resolved ResolvedSlot objects from the Slot Marking Agent
(master_agent/slot_marking_agent.py) - direct paragraph/table references
captured when slots were marked, not a text re-scan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from common.schemas import NarrativeSection, TableRow, TableSection
from master_agent.docx_utils import (
    NUMERIC_ORDINAL_PATTERN,
    TableLayout,
    clear_paragraph,
    group_into_records,
    insert_row_after,
    set_cell_lines,
    set_paragraph_text,
    set_row_values,
)
from master_agent.slot_marking_agent import ResolvedSlot


class InjectionError(Exception):
    pass


@dataclass
class Placement:
    """Where one agent table row (index into `section.rows`) actually landed:
    the physical <w:tr> element. Collected only so master.py can persist a
    slot_map (fix.md sec.11: stable HTML identity) - injection behavior is
    identical whether or not a collector list is passed."""

    slot_id: str
    row_index: int
    tr: object


def inject_narrative(resolved: ResolvedSlot, section: NarrativeSection) -> None:
    if resolved.paragraph is None:
        raise InjectionError(f"Narrative slot '{section.slot_id}' has no resolved paragraph")
    set_paragraph_text(resolved.paragraph, section.content)


def _bucket_rows_by_group(
    slot_id: str, rows: list[TableRow], group_labels: list[str]
) -> dict[str, list[TableRow]]:
    """Sorts the agent's rows into the template's real groups (in template
    order, not agent order) so each group's placeholder queue only ever
    receives the rows meant for it - matching changefeature.md's
    group-aware filling requirement. A row naming an unknown group (typo,
    or the agent inventing one) falls back to the first group rather than
    raising - a bad label shouldn't discard an entire criterion's data, but
    it's logged so it's visible.
    """
    buckets: dict[str, list[TableRow]] = {label: [] for label in group_labels}
    for row in rows:
        label = row.group if row.group in buckets else group_labels[0]
        if row.group is not None and row.group not in buckets:
            print(f"table slot '{slot_id}': row.group={row.group!r} not in {group_labels} - using {label!r}")
        buckets[label].append(row)
    return buckets


def inject_table(resolved: ResolvedSlot, section: TableSection, placements: list[Placement] | None = None) -> None:
    if resolved.table is None or resolved.layout is None:
        raise InjectionError(f"Table slot '{section.slot_id}' has no resolved table")

    template_headers = resolved.headers or []
    if template_headers != section.headers:
        raise InjectionError(
            f"Table slot '{section.slot_id}': agent headers {section.headers} don't match "
            f"template headers {template_headers} - refusing to inject mismatched columns"
        )

    layout = resolved.layout
    if not layout.has_placeholders:
        raise InjectionError(
            f"Table slot '{section.slot_id}': template table has no placeholder rows to fill - "
            "this table shape isn't supported for structured injection"
        )

    for row in section.rows:
        if len(row.values) != len(layout.header_columns):
            raise InjectionError(
                f"Table slot '{section.slot_id}': row has {len(row.values)} values but "
                f"template has {len(layout.header_columns)} columns"
            )

    if resolved.rows_per_record and resolved.rows_per_record > 1:
        _inject_table_records(resolved, section, layout, placements)
    else:
        _inject_table_rows(resolved, section, layout, placements)

    if resolved.marker_paragraph is not None:
        clear_paragraph(resolved.marker_paragraph)


def _inject_table_records(
    resolved: ResolvedSlot, section: TableSection, layout: TableLayout, placements: list[Placement] | None = None
) -> None:
    """Fills a multi-row-per-record table (e.g. one instructor = 5 physical
    rows, one per academic year) - see docx_utils.group_into_records.

    The agent's flat `section.rows` are clustered by `record_key` (order of
    first appearance = record order), then each cluster is mapped onto one
    template `TableRecord` block in template order. Reuses the exact same
    per-row primitives (`set_row_values`, `insert_row_after`) as the
    single-row-per-record path - only the *mapping* from agent rows to
    template rows differs.
    """
    table = resolved.table
    all_records = [r for g in layout.groups for r in group_into_records(g.rows)]

    order: list[str] = []
    by_key: dict[str, list[TableRow]] = {}
    row_index_of: dict[int, int] = {}  # id(row) -> index in section.rows, for Placement
    for i, row in enumerate(section.rows):
        key = row.record_key or f"__no_record_key_{i}__"
        if key not in by_key:
            by_key[key] = []
            order.append(key)
        by_key[key].append(row)
        row_index_of[id(row)] = i

    if len(order) > len(all_records):
        # More real records than the template has physical blocks for -
        # genuinely unsafe: satisfying this would mean either dropping a
        # real person's data or inventing a block that doesn't exist in
        # this table, both of which are guesses (change.md "PS Table 1.2":
        # "ห้ามสร้างข้อมูล record ที่ 14 ขึ้นเอง").
        raise InjectionError(
            f"Table slot '{section.slot_id}': agent produced {len(order)} distinct record_key(s) but "
            f"the template only has {len(all_records)} record block(s) - refusing to guess where the "
            f"overflow goes"
        )

    if len(order) < len(all_records):
        # Fewer real records than the template has blocks for is safe: the
        # template's blocks are structurally identical/interchangeable
        # placeholders (verified against the real Table 1.2 - all 14 blocks
        # share the same blank label/shape/vMerge pattern), so filling the
        # first len(order) blocks in template order and leaving the rest
        # untouched is the same deterministic, order-preserving mapping
        # already used when counts match - not a guess about which block
        # is "the extra one" (change.md: "ห้ามสมมติว่า block ที่ 14 คือ
        # record ใด" - this never claims any specific block is a specific
        # person, it just doesn't write to blocks past the real data).
        print(
            f"table slot '{section.slot_id}': agent produced {len(order)} record(s) but template has "
            f"{len(all_records)} block(s) - filling the first {len(order)} block(s) in template order, "
            f"leaving {len(all_records) - len(order)} block(s) blank (not guessed, not fabricated)"
        )

    identity_col_start = layout.header_columns[0][0] if layout.header_columns else None

    for record, key in zip(all_records, order):
        sub_rows = by_key[key]
        block_rows = record.rows
        last_row = block_rows[-1]
        for i, row in enumerate(sub_rows):
            if i < len(block_rows):
                target_row = block_rows[i]
            else:
                # More sub-rows than the block has physical rows (e.g. more
                # years of history than the template pre-allocated for) -
                # insert extra rows inside the block, same mechanism as
                # cross-group overflow in `_inject_table_rows`.
                last_row = insert_row_after(table, last_row)
                target_row = last_row
            set_row_values(target_row, layout.header_columns, row.values)
            if placements is not None:
                placements.append(Placement(section.slot_id, row_index_of[id(row)], target_row._tr))
        # Fewer sub-rows than the block's physical row count (e.g. a newer
        # instructor with less than the full N years of history) - the
        # remaining physical rows are simply left untouched/blank, matching
        # the "empty is not always an error" principle used elsewhere.

        if resolved.checkbox_options and sub_rows and identity_col_start is not None:
            # The identity column turns out to be genuinely vertically
            # merged (vMerge restart/continue) across the whole block in the
            # real template - Word only displays the block's *first*
            # physical row's cell content for that merged span, so the
            # category checkbox has to live there too, as extra lines under
            # the name/position - matching how the template's own unfilled
            # placeholder combined an ordinal with checkbox lines in that
            # same cell (see docx_utils.extract_checkbox_options).
            identity_value = sub_rows[0].values[0]  # first *logical* column - values is indexed by logical position
            # change.md sec.13: a multi-role record (e.g. Responsible + Staff)
            # must show every matching option checked at once - `group`
            # alone can only ever match one option, so `checked_options`
            # (a list) takes priority when the agent provides it; falls back
            # to the original single-`group` match otherwise (Table 1.1-style
            # slots / older callers are unaffected).
            checked_options = sub_rows[0].checked_options
            if checked_options is None:
                record_group = sub_rows[0].group
                checked_options = [record_group] if record_group is not None else []
            lines = [identity_value] + [
                f"[{'✓' if option in checked_options else ' '}] {option}" for option in resolved.checkbox_options
            ]
            set_cell_lines(block_rows[0].cells[identity_col_start], lines)


def _inject_table_rows(
    resolved: ResolvedSlot, section: TableSection, layout: TableLayout, placements: list[Placement] | None = None
) -> None:
    """One row per record (the common case - e.g. Table 1.1's instructor
    list) - group-aware placeholder fill with overflow, see inject_table's
    module docstring for the overall approach.
    """
    groups_with_placeholders = [g for g in layout.groups if g.rows]
    group_labels = [g.label for g in groups_with_placeholders]
    buckets = _bucket_rows_by_group(section.slot_id, section.rows, group_labels)
    row_index_of = {id(row): i for i, row in enumerate(section.rows)}

    table = resolved.table
    ordinal = 1  # continuous across every group, matching how the template's own
    # placeholder rows numbered "1."-"5." then kept counting "6." into the next
    # group, rather than restarting per group - only used when layout.numbered.
    for group in groups_with_placeholders:
        data_rows = buckets[group.label]
        placeholder_rows = group.rows
        last_row = placeholder_rows[-1]

        for i, row in enumerate(data_rows):
            if i < len(placeholder_rows):
                target_row = placeholder_rows[i]
            else:
                # Placeholders exhausted for this group: insert right after
                # the last row *written so far in this group*, so overflow
                # rows land inside the group, never past the next group's
                # subheader - matches changefeature.md sec.14/41.
                last_row = insert_row_after(table, last_row)
                target_row = last_row
            values = list(row.values)
            if layout.numbered and values:
                first = values[0].strip()
                # If the agent's own value for this column is itself just a
                # bare number (or blank) - e.g. a table whose first column is
                # a real, dedicated "ลำดับ"/"No." sequence-number header, which
                # the agent correctly filled with its own count - Python's
                # row order is the authoritative sequence, so it *replaces*
                # that value rather than doubling up into "1. 1". Otherwise
                # (the agent's value is real data, e.g. an academic position,
                # because the template's numbering was only ever an artifact
                # of the placeholder token, not a real column) it's
                # *prepended*, restoring the count the template's own
                # placeholder ("1.", "2.", ...) used to show before injection
                # overwrote it with that real data.
                if first == "" or NUMERIC_ORDINAL_PATTERN.match(first):
                    values[0] = f"{ordinal}."
                elif re.match(r"^\d+\.\s", first):
                    pass  # the Agent already numbered this value ("1. รองศาสตราจารย์") - never number twice
                else:
                    values[0] = f"{ordinal}. {first}"
                ordinal += 1
            set_row_values(target_row, layout.header_columns, values)
            if placements is not None:
                placements.append(Placement(section.slot_id, row_index_of[id(row)], target_row._tr))


def inject_section(
    resolved_slots: dict[str, ResolvedSlot],
    section: NarrativeSection | TableSection,
    placements: list[Placement] | None = None,
) -> None:
    resolved = resolved_slots.get(section.slot_id)
    if resolved is None:
        raise InjectionError(f"Slot '{section.slot_id}' was not produced by the Slot Marking Agent")

    if isinstance(section, NarrativeSection):
        inject_narrative(resolved, section)
    else:
        inject_table(resolved, section, placements)
