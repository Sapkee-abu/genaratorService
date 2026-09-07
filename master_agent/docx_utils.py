from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field

from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell, _Row
from docx.text.paragraph import Paragraph

PLACEHOLDER_PATTERN = re.compile(r"^(\d+\.?|\[\s*\]|☐)$")
NUMERIC_ORDINAL_PATTERN = re.compile(r"^\d+\.?$")


def iter_block_items(parent):
    """Yields each Paragraph and Table in `parent` (a Document) in the order
    they appear in the document body. python-docx has no built-in unified
    iterator for this - `document.paragraphs` and `document.tables` are
    separate, order-losing lists - so template_structure.py (which needs to
    know which paragraph immediately precedes a given table) needs this.
    """
    if isinstance(parent, DocumentObject):
        parent_element = parent.element.body
    else:
        raise ValueError("iter_block_items only supports a Document root")

    for child in parent_element.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    """Replaces a paragraph's text while preserving the formatting of its
    first run (font, size, bold, etc.) - mainpromt.md sec.43 requires keeping
    the template's existing formatting during injection.
    """
    if not paragraph.runs:
        paragraph.add_run(text)
        return

    first_run = paragraph.runs[0]
    first_run.text = text
    for run in paragraph.runs[1:]:
        run.text = ""


def clear_paragraph(paragraph: Paragraph) -> None:
    for run in paragraph.runs:
        run.text = ""


def set_cell_lines(cell: _Cell, lines: list[str]) -> None:
    """Like `set_paragraph_text`, but writes several lines into a cell as
    separate paragraphs - needed when one cell must show more than one line
    (e.g. a person's name followed by checkbox-style category options, all
    inside one physical cell - see `_inject_table_records` in
    template_injector.py). Reuses existing paragraphs where possible
    (cloning the last one's own formatting for any extra lines needed,
    the same idiom `insert_row_after` uses for rows) rather than collapsing
    everything onto one line or losing per-paragraph formatting.
    """
    paragraphs = list(cell.paragraphs)
    if not paragraphs:
        paragraphs = [cell.add_paragraph()]
    while len(paragraphs) < len(lines):
        template_p = paragraphs[-1]._p
        new_p = deepcopy(template_p)
        template_p.addnext(new_p)
        paragraphs = list(cell.paragraphs)
    for paragraph, line in zip(paragraphs, lines):
        set_paragraph_text(paragraph, line)
    for extra_paragraph in paragraphs[len(lines) :]:
        clear_paragraph(extra_paragraph)


def set_cell_text(cell: _Cell, text: str) -> None:
    """Like `set_paragraph_text`, but for a table cell: writes into the first
    paragraph's first run, preserving that run's formatting (font, size,
    bold, etc.) instead of `cell.text = value`, which replaces every
    paragraph in the cell with a single default-formatted one - a real
    formatting-loss bug once cells carry template-defined fonts/alignment.
    """
    set_cell_lines(cell, [text])


CHECKBOX_OPTION_PATTERN = re.compile(r"^\[[ ✓]?\]\s*(.+)$")


def extract_checkbox_options(label: str) -> list[str]:
    """Parses a placeholder label's lines for checkbox options (e.g.
    "14.\n[ ] อาจารย์ประจำหลักสูตร\n[ ] อาจารย์ผู้รับผิดชอบหลักสูตร") and returns the
    option text after each checkbox glyph, in the order they appear -
    ["อาจารย์ประจำหลักสูตร", "อาจารย์ผู้รับผิดชอบหลักสูตร"] for that example. Purely a
    regex over whatever lines the label actually has - not tied to any
    specific category names - so it applies to any table using this
    checkbox-option convention, not just one criterion's. Returns `[]` when
    the label has no checkbox lines at all.
    """
    options = []
    for line in label.splitlines():
        match = CHECKBOX_OPTION_PATTERN.match(line.strip())
        if match:
            options.append(match.group(1).strip())
    return options


def logical_columns(row: _Row) -> list[tuple[int, int]]:
    """Real Word tables routinely horizontally-merge header cells (e.g. one
    "ตำแหน่งทางวิชาการ" header spanning what's really 2 grid columns).
    python-docx's `row.cells` returns one _Cell per *grid* column, and every
    grid position inside a merge returns the *same* cell object with the
    same text - so reading headers as `[c.text for c in row.cells]` sees
    that merged header twice, out of step with how many columns of actual
    data the table has. This walks the raw grid cells once and returns
    `(start_grid_index, span)` per real (deduplicated) column, using
    `_Cell.grid_span` to skip over merge continuations. General-purpose -
    not specific to any one table shape, since real SAR tables vary a lot.
    """
    cells = row.cells
    columns = []
    i = 0
    n = len(cells)
    while i < n:
        span = cells[i].grid_span
        columns.append((i, span))
        i += span
    return columns


def logical_header_texts(row: _Row) -> list[str]:
    """Header text per logical (merge-deduplicated) column - see `logical_columns`."""
    cells = row.cells
    return [cells[start].text.strip() for start, _span in logical_columns(row)]


def _row_first_line(row: _Row) -> str:
    """The first logical column's text, first line only - a placeholder
    label can be multi-line (e.g. "14.\n[ ] อาจารย์ประจำหลักสูตร\n[ ] ..."), and
    only the leading ordinal/checkbox token on line 1 is what
    `PLACEHOLDER_PATTERN` needs to match; the rest is real label content
    that a plain single-line placeholder ("14.") never had to begin with.
    """
    columns = logical_columns(row)
    if not columns:
        return ""
    start, _span = columns[0]
    text = row.cells[start].text.strip()
    return text.splitlines()[0].strip() if text else ""


def _is_divider_shaped(row: _Row) -> bool:
    """A row that's a single cell spanning the whole grid width - e.g. a
    subheader/section-divider row. Self-contained (only looks at the row's
    own merges), unlike the header-pattern comparison in
    `analyze_table_groups`, so it can be used *before* a header is known -
    see `find_header_row_index`.
    """
    return len(logical_columns(row)) == 1


def _is_placeholder_shaped(row: _Row) -> bool:
    """A row whose first logical column is a bare ordinal/checkbox token
    (first line only, see `_row_first_line`) and every other logical column
    is blank - i.e. an empty slot waiting to be filled in, regardless of
    that table's actual header shape. Self-contained like
    `_is_divider_shaped`, for the same reason.
    """
    columns = logical_columns(row)
    if not columns:
        return False
    texts = [row.cells[start].text.strip() for start, _span in columns]
    if not all(t == "" for t in texts[1:]):
        return False
    return bool(PLACEHOLDER_PATTERN.match(_row_first_line(row)))


def find_header_row_index(table: Table) -> int:
    """Finds the real header row even when it isn't `table.rows[0]` - some
    templates put a decorative supra-header above the row that actually
    names each column (e.g. Table 1.2's real template: row 0 is a merged
    "...(ย้อนหลัง 5 ปีการศึกษา)" banner spanning 3 columns, row 1 has the
    actual 5 column labels). Walks from the top and keeps advancing the
    header candidate until hitting the first row that's clearly *not* a
    header - a divider or a placeholder - at which point the previous
    candidate is the real header. Returns 0 (today's assumption) whenever
    the very first row already looks like body content, so single-row-header
    tables (Table 1.1) are unaffected.
    """
    header_index = 0
    for i, row in enumerate(table.rows):
        if _is_divider_shaped(row) or _is_placeholder_shaped(row):
            break
        header_index = i
    return header_index


def insert_row_after(table: Table, after_row: _Row) -> _Row:
    """Inserts a new row immediately after `after_row` (not at the table's
    tail, unlike `table.add_row()`) by deep-copying `after_row`'s own <w:tr>
    XML and placing the copy right next to it - the same `addnext` idiom
    `slot_marking_agent._insert_paragraph_after` already uses for paragraphs.

    Cloning a real row (instead of `table.add_row()`, which creates bare
    cells with no <w:tcPr> at all - no borders, no merges) means the new row
    already has the exact same borders/shading/gridSpan/fonts as the row it
    was cloned from, for free. All that's left is clearing the cloned text.
    """
    new_tr = deepcopy(after_row._tr)
    after_row._tr.addnext(new_tr)
    new_row = _Row(new_tr, table)
    for cell in new_row.cells:
        set_cell_text(cell, "")
    return new_row


def set_row_values(row: _Row, columns: list[tuple[int, int]], values: list[str]) -> None:
    """Writes `values` (one per logical column, per `logical_columns`) into
    `row`'s grid cells. `row` must already have the correct merge shape
    (grid_span pattern) for the header's columns - true both for an existing
    template placeholder row and for a row produced by `insert_row_after`
    (cloned from one) - so no `.merge()` calls are needed here at all.
    """
    for (start, _span), value in zip(columns, values):
        set_cell_text(row.cells[start], value)


@dataclass
class TableGroup:
    """One group of placeholder rows within a table, delimited by a
    subheader/divider row (mainpromt.md/changefeature.md: e.g. a table
    listing 'อาจารย์ผู้รับผิดชอบหลักสูตร' rows separately from 'อาจารย์ประจำหลักสูตร'
    rows). `label=""` is the implicit group covering any placeholder rows
    that appear before the table's first divider - so a table with no
    dividers at all still gets exactly one group, and single-group tables
    work identically to grouped ones.
    """

    label: str
    rows: list[_Row] = field(default_factory=list)


@dataclass
class TableLayout:
    header_columns: list[tuple[int, int]]
    groups: list[TableGroup]
    numbered: bool = False  # True if the template's own placeholder rows used a bare ordinal ("1.", "2.", ...)

    @property
    def has_placeholders(self) -> bool:
        return any(g.rows for g in self.groups)


def analyze_table_groups(table: Table) -> TableLayout:
    """Classifies every row after the header as either a group divider (its
    logical column-span pattern differs from the header's - e.g. a single
    cell spanning the whole row) or a same-shaped row, and among those,
    whether it's an empty placeholder waiting to be filled (first logical
    column matches `PLACEHOLDER_PATTERN`, the rest blank) or already has
    real content (left untouched either way).

    Purely structural (grid_span + a generic ordinal/checkbox regex) - not
    tied to any specific table's headers or language, so it applies to any
    similarly-shaped table, not just one criterion's.
    """
    if not table.rows:
        return TableLayout(header_columns=[], groups=[TableGroup(label="")])

    header_index = find_header_row_index(table)
    header_columns = logical_columns(table.rows[header_index])
    header_pattern = [span for _, span in header_columns]

    groups: list[TableGroup] = [TableGroup(label="")]
    numbered = False
    for row in table.rows[header_index + 1 :]:
        row_columns = logical_columns(row)
        row_pattern = [span for _, span in row_columns]

        if row_pattern != header_pattern:
            texts = [row.cells[start].text.strip() for start, _span in row_columns]
            label = next((t for t in texts if t), "")
            groups.append(TableGroup(label=label))
            continue

        texts = [row.cells[start].text.strip() for start, _span in row_columns]
        first, rest = _row_first_line(row), texts[1:]
        if PLACEHOLDER_PATTERN.match(first) and all(t == "" for t in rest):
            # Store the actual _Row object, not its position: inserting new
            # rows into an earlier group (see template_injector.inject_table)
            # shifts every later row's positional index in the table, but a
            # captured _Row still points at its own <w:tr> element regardless.
            groups[-1].rows.append(row)
            if NUMERIC_ORDINAL_PATTERN.match(first):
                # The template's own placeholder was a bare running number
                # ("1.", "2.", ...), not a checkbox - that number gets
                # replaced by real data during injection, so
                # template_injector.inject_table restores an equivalent
                # continuous count (spanning every group, matching how the
                # template's own placeholders numbered "1."-"5." then kept
                # counting "6." into the next group) rather than silently
                # dropping it.
                numbered = True

    return TableLayout(header_columns=header_columns, groups=groups, numbered=numbered)


@dataclass
class TableRecord:
    """One "record" within a `TableGroup` - one or more consecutive physical
    rows sharing the same raw placeholder label (see `group_into_records`).
    For most tables a record is a single row (Table 1.1: each instructor's
    placeholder ordinal, "1.", "2.", ... is unique, so every record is a
    singleton). Some tables need several physical rows per logical record
    instead - e.g. Table 1.2's real template, where one instructor occupies
    5 consecutive rows (one per academic year) that all repeat the exact
    same ordinal+checkbox label in their first column until filled in.
    """

    label: str
    rows: list[_Row] = field(default_factory=list)


def group_into_records(rows: list[_Row]) -> list[TableRecord]:
    """Clusters *consecutive* rows (in table order - callers pass a
    `TableGroup.rows` list, itself built by walking the table top-to-bottom,
    so list order already matches table order) that share identical raw
    first-cell text into one `TableRecord` each.

    Purely a grouping of what `analyze_table_groups` already found - no new
    structural analysis, no assumption about how many rows make up a record
    (that block size falls out naturally from however many consecutive rows
    actually repeat the same label in the real template).
    """
    records: list[TableRecord] = []
    for row in rows:
        label = row.cells[logical_columns(row)[0][0]].text.strip() if row.cells else ""
        if records and records[-1].label == label:
            records[-1].rows.append(row)
        else:
            records.append(TableRecord(label=label, rows=[row]))
    return records


def force_field_update(document: DocumentObject) -> None:
    """Sets <w:updateFields w:val="true"/> in the document's settings.xml so
    Word (and most compliant renderers) recompute every field - PAGE,
    NUMPAGES, TOC, DATE, etc. - when the file is opened, instead of showing
    whatever value happened to be cached in the template at the time it was
    last saved in Word.

    Needed because python-docx (and this pipeline generally) never
    recalculates field results itself - a template's footer PAGE field, for
    instance, keeps showing the exact page number that was true when the
    template was last edited (e.g. "8" on every single page) unless
    something tells Word to redo that math on open. This is a document-wide
    setting, not tied to any specific field/template, so it fixes every
    cached field the template may contain, not just page numbers.
    """
    settings = document.settings.element
    existing = settings.find(qn("w:updateFields"))
    if existing is not None:
        existing.set(qn("w:val"), "true")
        return
    update_fields = settings.makeelement(qn("w:updateFields"), {qn("w:val"): "true"})
    settings.insert(0, update_fields)
