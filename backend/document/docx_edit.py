"""HTML -> DOCX edit application (fix.md sec.9/10/16).

The generated DOCX stays the structural base - this module never rebuilds a
document from HTML. It:
  1. renders the base DOCX to HTML with `document_to_html` (the BASELINE),
  2. parses both the baseline and the user's saved HTML into the same
     id-keyed model (`data-block` / `data-row` / `data-col`, see
     document.docx_to_html),
  3. finds the elements whose text really changed, and
  4. writes ONLY those elements back into a copy of the base DOCX, reusing
     the exact primitives Template Injection uses (`set_paragraph_text`,
     `set_cell_lines`), so template layout/tables/merged cells/styles are
     untouched everywhere else.

Comparing baseline-render vs edited-HTML (instead of DOCX text vs HTML
text) means an untouched element can never look "edited" merely because of
how the renderer or the browser normalizes it.

Anything that cannot be mapped back safely (a block/row/cell added, removed
or duplicated - e.g. Enter in a paragraph, deleting a table row) raises
`UnsupportedEditError` naming the offending element; a broken DOCX is never
silently produced. Client-supplied `data-slot-id`/`data-reference-id` are
ignored here on purpose - attribution comes from the server's own slot_map.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import docx
import lxml.html

from document.docx_to_html import document_to_html
from master_agent.docx_utils import iter_block_items, row_logical_cells, set_cell_lines, set_paragraph_text

_WS = re.compile(r"\s+")


class UnsupportedEditError(Exception):
    """`problems` is a list of human-readable strings, one per offending element."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class ElementChange:
    """One element whose text differs from the generated document.
    kind = "paragraph" (block only) or "cell" (block + row + col)."""

    kind: str
    block: int
    row: int | None
    col: int | None
    original_lines: list[str]
    current_lines: list[str]

    @property
    def element_id(self) -> str:
        if self.kind == "cell":
            return f"b{self.block}.r{self.row}.c{self.col}"
        return f"b{self.block}"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "block": self.block,
            "row": self.row,
            "col": self.col,
            "originalLines": self.original_lines,
            "currentLines": self.current_lines,
        }

    @staticmethod
    def from_dict(data: dict) -> "ElementChange":
        return ElementChange(
            kind=data["kind"],
            block=data["block"],
            row=data.get("row"),
            col=data.get("col"),
            original_lines=list(data["originalLines"]),
            current_lines=list(data["currentLines"]),
        )


@dataclass
class _Model:
    # block index -> lines, for paragraph-like blocks (p / h1-6 / li)
    paragraphs: dict[int, list[str]] = field(default_factory=dict)
    # block index -> {(row, col): lines}
    tables: dict[int, dict[tuple[int, int], list[str]]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def _norm_line(text: str) -> str:
    return _WS.sub(" ", text.replace("\xa0", " ")).strip()


def _trim(lines: list[str]) -> list[str]:
    lines = [_norm_line(line) for line in lines]
    while lines and lines[-1] == "":
        lines.pop()
    return lines or [""]


_BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}


def _element_lines(element) -> list[str]:
    """Visible text of an element as a list of lines: <br>, and any nested
    block element (browsers wrap Enter-created lines in <div>/<p>), start a
    new line; a doc-checkbox <label> becomes "[✓] text" / "[ ] text"."""
    lines: list[str] = [""]

    def add(text: str | None) -> None:
        if text:
            lines[-1] += text

    def walk(node) -> None:
        add(node.text)
        for child in node:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag == "br":
                lines.append("")
            elif tag == "label" and "doc-checkbox" in (child.get("class") or ""):
                checkbox = child.find(".//input")
                checked = checkbox is not None and checkbox.get("checked") is not None
                label_text = "".join(child.itertext())
                if lines[-1].strip():
                    lines.append("")
                lines[-1] = f"[{'✓' if checked else ' '}] {_norm_line(label_text)}"
            elif tag in _BLOCK_TAGS:
                if lines[-1].strip():
                    lines.append("")
                walk(child)
                if lines[-1].strip():
                    lines.append("")
            else:
                walk(child)
            add(child.tail)

    walk(element)
    return _trim(lines)


def _int_attr(element, name: str) -> int | None:
    value = element.get(name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _is_blank(element) -> bool:
    return not "".join(element.itertext()).strip() and element.find(".//input") is None


def _parse_html(html: str) -> _Model:
    model = _Model()
    root = lxml.html.fromstring(f"<div>{html}</div>")

    def paragraph_like(element, label: str) -> None:
        block = _int_attr(element, "data-block")
        if block is None:
            if not _is_blank(element):
                model.problems.append(f"{label}: content was added outside any existing document block")
            return
        if block in model.paragraphs or block in model.tables:
            if not _is_blank(element):
                model.problems.append(
                    f"block {block}: split/duplicated (e.g. pressing Enter inside a paragraph) - "
                    "adding new paragraphs is not supported"
                )
            return
        model.paragraphs[block] = _element_lines(element)

    for child in root:
        tag = child.tag if isinstance(child.tag, str) else ""
        if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6"}:
            paragraph_like(child, f"<{tag}>")
        elif tag in {"ul", "ol"}:
            for item in child:
                if item.tag == "li":
                    paragraph_like(item, "<li>")
                elif not _is_blank(item):
                    model.problems.append("list contains unsupported content")
        elif tag == "table":
            block = _int_attr(child, "data-block")
            if block is None or block in model.tables or block in model.paragraphs:
                model.problems.append("table: unknown or duplicated table (adding tables is not supported)")
                continue
            cells: dict[tuple[int, int], list[str]] = {}
            for row in child.iter("tr"):
                row_index = _int_attr(row, "data-row")
                if row_index is None:
                    model.problems.append(f"table {block}: a row was added (adding rows is not supported)")
                    continue
                for cell in row:
                    if cell.tag not in {"td", "th"}:
                        continue
                    col = _int_attr(cell, "data-col")
                    if col is None or (row_index, col) in cells:
                        model.problems.append(f"table {block} row {row_index}: a cell was added or duplicated")
                        continue
                    cells[(row_index, col)] = _element_lines(cell)
            model.tables[block] = cells
        elif not _is_blank(child):
            model.problems.append(f"<{tag or 'text'}>: unsupported top-level content")
    # stray text directly under the wrapper
    if (root.text or "").strip():
        model.problems.append("free text was typed outside any document block")
    return model


def _diff(baseline: _Model, edited: _Model) -> list[ElementChange]:
    problems = list(edited.problems)

    for block in baseline.paragraphs.keys() - edited.paragraphs.keys():
        problems.append(f"block {block}: paragraph was deleted (deleting content blocks is not supported)")
    for block in baseline.tables.keys() - edited.tables.keys():
        problems.append(f"table {block}: table was deleted")
    for block in edited.paragraphs.keys() - baseline.paragraphs.keys():
        problems.append(f"block {block}: unknown paragraph id")
    for block in edited.tables.keys() - baseline.tables.keys():
        problems.append(f"table {block}: unknown table id")

    changes: list[ElementChange] = []
    for block in sorted(baseline.paragraphs.keys() & edited.paragraphs.keys()):
        if baseline.paragraphs[block] != edited.paragraphs[block]:
            changes.append(
                ElementChange("paragraph", block, None, None, baseline.paragraphs[block], edited.paragraphs[block])
            )
    for block in sorted(baseline.tables.keys() & edited.tables.keys()):
        base_cells, edit_cells = baseline.tables[block], edited.tables[block]
        for key in sorted(base_cells.keys() - edit_cells.keys()):
            problems.append(f"table {block} row {key[0]} col {key[1]}: cell/row was deleted")
        for key in sorted(edit_cells.keys() - base_cells.keys()):
            problems.append(f"table {block} row {key[0]} col {key[1]}: unknown cell (adding rows/cells is not supported)")
        for key in sorted(base_cells.keys() & edit_cells.keys()):
            if base_cells[key] != edit_cells[key]:
                changes.append(ElementChange("cell", block, key[0], key[1], base_cells[key], edit_cells[key]))

    if problems:
        raise UnsupportedEditError(problems)
    return changes


def compute_changes(base_docx_path: str | Path, html: str) -> list[ElementChange]:
    document = docx.Document(str(base_docx_path))
    baseline = _parse_html(document_to_html(document))
    return _diff(baseline, _parse_html(html))


def apply_html_to_docx(base_docx_path: str | Path, html: str, out_path: str | Path) -> list[ElementChange]:
    """Writes `out_path` = base DOCX + only the elements the user changed.
    Returns the changes (empty list -> `out_path` is an unchanged copy).
    Raises UnsupportedEditError (and writes nothing) if the edit cannot be
    mapped back safely."""
    document = docx.Document(str(base_docx_path))
    baseline = _parse_html(document_to_html(document))
    changes = _diff(baseline, _parse_html(html))

    blocks = list(iter_block_items(document))
    for change in changes:
        item = blocks[change.block]
        if change.kind == "paragraph":
            set_paragraph_text(item, "\n".join(change.current_lines))
            continue
        table = item
        row = table.rows[change.row]
        cell = next(rc.cell for rc in row_logical_cells(row, table) if rc.logical_col == change.col)
        set_cell_lines(cell, list(change.current_lines))

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(out))
    return changes
