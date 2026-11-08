"""DOCX -> HTML conversion for the Web Document Viewer/Editor (fix.md
sec.16). Read-only rendering: the generated DOCX on disk remains the
authoritative artifact - this only produces a structural HTML
representation (headings, paragraphs, tables, checkboxes, basic bold/
italic formatting) for the frontend to preview/edit, never plain extracted
text.

Reuses master_agent.docx_utils.iter_block_items/logical_columns (already
used by Template Structure/Injection) for body traversal and merged-column
handling - this module only adds NEW rendering logic on top, it doesn't
reimplement document traversal.

Stable element identity (fix.md sec.11): every rendered block carries
`data-block` (its index in the DOCX body, the order `iter_block_items`
yields), tables add `data-table-id`, rows `data-row` (physical row index) and
cells `data-col` (logical column index). These positional ids are what
`document.docx_edit` uses to map an edited element back to the exact DOCX
paragraph/cell. When a `slot_map` (master_agent.slot_map) is supplied, mapped
elements also carry `data-slot-id`/`data-section`, and - only where a real
Reference item exists (`reference_ids`) - `data-reference-id`. Nothing is
invented: no slot_map / no reference item -> no such attribute. No database
ids or secrets are ever emitted.
"""

from __future__ import annotations

import html as html_lib
import re

from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from master_agent.docx_utils import iter_block_items, row_logical_cells

_CHECKBOX_LINE_PATTERN = re.compile(r"^\s*\[\s*(✓?)\s*\]\s*(.*)$")


def _escape(text: str) -> str:
    return html_lib.escape(text)


def _is_heading(paragraph: Paragraph) -> bool:
    try:
        return paragraph.style is not None and paragraph.style.name.lower().startswith("heading")
    except Exception:  # noqa: BLE001 - a malformed/missing style must not break preview rendering
        return False


def _heading_level(paragraph: Paragraph) -> int:
    try:
        digits = "".join(ch for ch in paragraph.style.name if ch.isdigit())
        return min(max(int(digits), 1), 6) if digits else 1
    except Exception:  # noqa: BLE001
        return 1


def _is_list_item(paragraph: Paragraph) -> bool:
    """Real OOXML list detection, checking BOTH real conventions:
    1. A direct <w:numPr> (numbering reference) on the paragraph's own
       <w:pPr> - used when a paragraph is directly formatted as a list
       item regardless of its named style.
    2. The paragraph's STYLE name is specifically "List Bullet"/"List
       Number" (or a numbered variant, e.g. "List Bullet 2") - confirmed
       the more common real case for genuine lists: Word's own built-in
       list styles carry their <w:numPr> on the STYLE definition in
       styles.xml, not on each individual paragraph, so a direct-paragraph-
       only check misses them. Deliberately NOT matching the generic "List
       Paragraph" style name: confirmed against the real SAR template that
       it's also used for plain indented section labels with no actual
       list semantics (e.g. a single heading-like line before a table) -
       matching it would render those as a spurious one-item bullet list.
    Rendered uniformly as <ul><li> - resolving ordered-vs-unordered would
    need parsing numbering.xml's abstract format, which no real current
    SAR content exercises.
    """
    p_pr = paragraph._p.find(qn("w:pPr"))
    if p_pr is not None and p_pr.find(qn("w:numPr")) is not None:
        return True
    try:
        name = paragraph.style.name.lower() if paragraph.style is not None else ""
        return name.startswith("list bullet") or name.startswith("list number")
    except Exception:  # noqa: BLE001
        return False


def _render_line(text: str) -> str:
    """Renders one line of text - either a checkbox line ("[✓] label" /
    "[  ] label", the same convention docx_utils.extract_checkbox_options
    already recognizes) as a real HTML checkbox, or plain escaped text."""
    match = _CHECKBOX_LINE_PATTERN.match(text)
    if match:
        checked = bool(match.group(1))
        label = _escape(match.group(2))
        checked_attr = " checked" if checked else ""
        return f'<label class="doc-checkbox"><input type="checkbox"{checked_attr} disabled /> {label}</label>'
    return _escape(text)


def _render_runs(paragraph: Paragraph) -> str:
    parts = []
    for run in paragraph.runs:
        text = _escape(run.text)
        if not text:
            continue
        if run.bold:
            text = f"<strong>{text}</strong>"
        if run.italic:
            text = f"<em>{text}</em>"
        parts.append(text)
    return "".join(parts) if parts else _escape(paragraph.text)


def _attrs(**pairs: object) -> str:
    return "".join(f' {name.replace("_", "-")}="{_escape(str(value))}"' for name, value in pairs.items() if value is not None)


def _paragraph_slot_attrs(block: int, slot_map: dict | None, reference_ids: set[str] | None) -> str:
    info = (slot_map or {}).get("paragraphs", {}).get(str(block))
    if not info:
        return ""
    slot_id = info["slotId"]
    reference_id = slot_id if reference_ids is not None and slot_id in reference_ids else None
    return _attrs(data_slot_id=slot_id, data_section=info.get("criterion"), data_reference_id=reference_id)


def _paragraph_to_html(paragraph: Paragraph, block: int, slot_attrs: str) -> str:
    text = paragraph.text
    if not text.strip():
        return ""

    ids = f' data-block="{block}"{slot_attrs}'

    checkbox_match = _CHECKBOX_LINE_PATTERN.match(text)
    if checkbox_match:
        return f"<p{ids}>{_render_line(text)}</p>"

    if _is_heading(paragraph):
        level = _heading_level(paragraph)
        return f"<h{level}{ids}>{_render_runs(paragraph)}</h{level}>"

    return f"<p{ids}>{_render_runs(paragraph)}</p>"


def _cell_to_html(text: str) -> str:
    """A table cell's `.text` joins its own (possibly several) paragraphs
    with "\\n" (python-docx's own convention) - each line is rendered
    independently so a checkbox line inside a cell (e.g. Table 1.2's
    identity column, which carries a name line plus one or more checkbox
    lines) renders as a real checkbox, not literal "[✓]" text."""
    lines = text.split("\n")
    return "<br />".join(_render_line(line) for line in lines)


def _table_to_html(table: Table, block: int, slot_map: dict | None, reference_ids: set[str] | None) -> str:
    table_info = (slot_map or {}).get("tables", {}).get(str(block)) or {}
    slot_id = table_info.get("slotId")
    row_map: dict[str, int] = table_info.get("rows", {})

    rows = list(table.rows)
    row_cells = [row_logical_cells(row, table) for row in rows]

    # grid start of every raw cell, so a vertically-merged continuation can be
    # matched to its restart cell by grid column (not by raw index)
    grid_starts: list[list[int]] = []
    for cells in row_cells:
        starts, position = [], 0
        for rc in cells:
            starts.append(position)
            position += rc.grid_span
        grid_starts.append(starts)

    def continuation_at(row_index: int, grid_start: int) -> bool:
        if row_index >= len(rows):
            return False
        for rc, start in zip(row_cells[row_index], grid_starts[row_index]):
            if start == grid_start:
                return rc.vmerge == "continue"
        return False

    rows_html = []
    for row_index, cells in enumerate(row_cells):
        cell_tag = "th" if row_index == 0 else "td"
        agent_row = row_map.get(str(row_index))
        cells_html = []
        for rc, grid_start in zip(cells, grid_starts[row_index]):
            if rc.vmerge == "continue":
                continue  # covered by the restart cell's rowspan - not an independent editable cell
            span_attr = f' colspan="{rc.grid_span}"' if rc.grid_span > 1 else ""
            if rc.vmerge == "restart":
                rowspan = 1
                while continuation_at(row_index + rowspan, grid_start):
                    rowspan += 1
                if rowspan > 1:
                    span_attr += f' rowspan="{rowspan}"'

            slot_attrs = ""
            if slot_id is not None and agent_row is not None:
                reference_id = f"{slot_id}.row{agent_row}.col{rc.logical_col}"
                slot_attrs = _attrs(
                    data_slot_id=slot_id,
                    data_section=table_info.get("criterion"),
                    data_reference_id=reference_id if reference_ids is not None and reference_id in reference_ids else None,
                )
            cells_html.append(
                f'<{cell_tag} data-col="{rc.logical_col}"{span_attr}{slot_attrs}>{_cell_to_html(rc.cell.text)}</{cell_tag}>'
            )
        rows_html.append(f'<tr data-row="{row_index}">{"".join(cells_html)}</tr>')
    return f'<table data-block="{block}" data-table-id="table_{block}">{"".join(rows_html)}</table>'


def document_to_html(
    document: DocumentObject,
    slot_map: dict | None = None,
    reference_ids: set[str] | None = None,
) -> str:
    parts: list[str] = []
    pending_list_items: list[str] = []

    def flush_list() -> None:
        if pending_list_items:
            parts.append(f"<ul>{''.join(pending_list_items)}</ul>")
            pending_list_items.clear()

    for block, item in enumerate(iter_block_items(document)):
        if isinstance(item, Paragraph):
            if not item.text.strip():
                continue
            slot_attrs = _paragraph_slot_attrs(block, slot_map, reference_ids)
            if _is_list_item(item):
                pending_list_items.append(f'<li data-block="{block}"{slot_attrs}>{_render_runs(item)}</li>')
                continue
            flush_list()
            fragment = _paragraph_to_html(item, block, slot_attrs)
            if fragment:
                parts.append(fragment)
        else:
            flush_list()
            parts.append(_table_to_html(item, block, slot_map, reference_ids))

    flush_list()
    return "\n".join(parts)
