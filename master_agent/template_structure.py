"""Serializes a docx Document into the two-array Document Structure JSON
addfeature.md's Slot Marking Agent expects: paragraphs indexed by p_index
(document.paragraphs order) and tables indexed by table_index
(document.tables order), each table cross-referencing the paragraph
immediately before it via preceding_p_index.

Pure read of the Document object already in memory - no temp files.
"""

from __future__ import annotations

from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph

from master_agent.docx_utils import (
    analyze_table_groups,
    find_header_row_index,
    group_into_records,
    iter_block_items,
    logical_columns,
    logical_header_texts,
)

MAX_PARAGRAPH_CHARS = 200


def _is_heading(paragraph: Paragraph) -> bool:
    try:
        return paragraph.style is not None and paragraph.style.name.lower().startswith("heading")
    except Exception:  # noqa: BLE001 - a malformed/missing style shouldn't crash structure extraction
        return False


def describe_document(document: DocumentObject) -> dict:
    paragraphs_out = []
    for p_index, paragraph in enumerate(document.paragraphs):
        text = paragraph.text.strip()
        paragraphs_out.append(
            {
                "p_index": p_index,
                "text": text[:MAX_PARAGRAPH_CHARS],
                "is_heading": _is_heading(paragraph),
                "is_empty": text == "",
            }
        )

    tables_out = []
    table_index = 0
    p_index_seen = -1  # index (into document.paragraphs) of the last paragraph encountered so far
    for item in iter_block_items(document):
        if isinstance(item, Paragraph):
            p_index_seen += 1
            continue

        table: Table = item
        # Logical (merge-deduplicated) columns - see docx_utils.logical_columns.
        # Real tables often horizontally-merge header cells; reading raw grid
        # cells here would show a merged header twice and mislead the Slot
        # Marking / Criteria Agents about how many columns of data exist.
        # find_header_row_index handles a decorative supra-header row sitting
        # above the real one (e.g. a "...(ย้อนหลัง 5 ปีการศึกษา)" banner row) -
        # without it, `headers`/`sample_row` here would describe the wrong
        # row entirely for such tables.
        header_index = find_header_row_index(table) if table.rows else 0
        headers = logical_header_texts(table.rows[header_index]) if table.rows else []
        if len(table.rows) > header_index + 1:
            sample_row_source = table.rows[header_index + 1]
            sample_columns = logical_columns(sample_row_source)
            sample_row = [sample_row_source.cells[start].text.strip() for start, _span in sample_columns]
        else:
            sample_row = []

        # Structural placeholder/group analysis (docx_utils.analyze_table_groups)
        # - purely mechanical (grid_span + a generic ordinal/checkbox regex),
        # not dependent on any criterion's wording. `fillable=False` means no
        # row's column layout matches the header's own - those tables aren't
        # safe to target for structured injection, so the Slot Marking
        # Agent's proposal for them gets dropped deterministically in
        # slot_marking_agent.apply_marks, regardless of what this
        # prompt-only description suggests. `rows_per_record` (>1 only when
        # every record agrees on the same row count) tells the Slot Marking
        # Agent when one record needs several physical rows instead of one -
        # e.g. one row per academic year for the same person.
        layout = analyze_table_groups(table)
        groups = [{"label": g.label, "placeholder_count": len(g.rows)} for g in layout.groups if g.rows]
        all_records = [r for g in layout.groups for r in group_into_records(g.rows)]
        record_sizes = {len(r.rows) for r in all_records}
        rows_per_record = record_sizes.pop() if len(record_sizes) == 1 and record_sizes != {1} else None

        tables_out.append(
            {
                "table_index": table_index,
                "preceding_p_index": p_index_seen,
                "headers": headers,
                "sample_row": sample_row,
                "groups": groups,
                "fillable": layout.has_placeholders,
                "rows_per_record": rows_per_record,
            }
        )
        table_index += 1

    return {"paragraphs": paragraphs_out, "tables": tables_out}
