"""Offline test of the group-aware placeholder-fill algorithm
(docx_utils.analyze_table_groups + template_injector.inject_table) against
Table 1.1's real shape from tem/template2.docx - no Gemini/MCP round trip
needed, pure python-docx + our code, per changefeature.md sec.45's test list
(Test 1/2/3/6/7 there).

Uses the real template file directly (table_index=0 only) rather than a
hand-built fixture, since it's the authoritative shape this fix targets.
"""

import sys
from pathlib import Path

import docx
from docx.oxml.ns import qn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.schemas import RowCitation, TableRow, TableSection  # noqa: E402
from master_agent.docx_utils import (  # noqa: E402
    analyze_table_groups,
    extract_checkbox_options,
    find_header_row_index,
    group_into_records,
    logical_header_texts,
)
from master_agent.slot_marking_agent import ResolvedSlot  # noqa: E402
from master_agent.template_injector import InjectionError, inject_table  # noqa: E402

TEMPLATE_PATH = Path(r"D:\genarator\tem\template2.docx")
UNMARKED_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "test_fixtures" / "template_unmarked.docx"

GROUP_A = "อาจารย์ผู้รับผิดชอบหลักสูตร"
GROUP_B = "อาจารย์ประจำหลักสูตร"


def _fresh_table_1_1():
    document = docx.Document(str(TEMPLATE_PATH))
    table = document.tables[0]
    headers = logical_header_texts(table.rows[0])
    layout = analyze_table_groups(table)
    resolved = ResolvedSlot(
        criterion="PS",
        slot_id="table_ps_1_1",
        type="table",
        headers=headers,
        table=table,
        marker_paragraph=None,
        layout=layout,
    )
    return document, table, headers, resolved


def _fresh_table_1_2(with_checkbox=False):
    document = docx.Document(str(TEMPLATE_PATH))
    table = document.tables[1]
    header_row = table.rows[find_header_row_index(table)]
    headers = logical_header_texts(header_row)
    layout = analyze_table_groups(table)
    all_records = [r for g in layout.groups for r in group_into_records(g.rows)]
    rows_per_record = len(all_records[0].rows)
    checkbox_options = extract_checkbox_options(all_records[0].label) if with_checkbox else None
    resolved = ResolvedSlot(
        criterion="PS",
        slot_id="table_ps_1_2",
        type="table",
        headers=headers,
        table=table,
        marker_paragraph=None,
        layout=layout,
        rows_per_record=rows_per_record,
        checkbox_options=checkbox_options,
    )
    return document, table, headers, resolved, len(all_records)


def _row(values, group=None, citation_chunk=0, record_key=None):
    return TableRow(
        values=values,
        citations=[RowCitation(source_filename="x.pdf", chunk_index=citation_chunk)],
        group=group,
        record_key=record_key,
    )


def _row_texts(table, row_index):
    return [c.text.strip() for c in table.rows[row_index].cells]


def _has_borders(row):
    return all(cell._tc.find(qn("w:tcPr")) is not None and cell._tc.find(qn("w:tcPr")).find(qn("w:tcBorders")) is not None for cell in row.cells)


def test_exact_fit():
    document, table, headers, resolved = _fresh_table_1_1()
    rows = [_row([f"ตำแหน่ง{i}", f"ชื่อ{i}", "ปริญญาเอก", "สาขา"], group=GROUP_A) for i in range(1, 6)]
    section = TableSection(type="table", slot_id="table_ps_1_1", headers=headers, rows=rows)
    inject_table(resolved, section)
    assert len(table.rows) == 9, f"expected still 9 rows, got {len(table.rows)}"
    for i, ri in enumerate(range(2, 7)):
        texts = _row_texts(table, ri)
        assert texts[0] == f"{i + 1}. ตำแหน่ง{i + 1}", texts  # template's own ordinal ("1.") restored as a prefix
    print("test_exact_fit: PASS")


def test_partial_fill():
    document, table, headers, resolved = _fresh_table_1_1()
    rows = [_row([f"ตำแหน่ง{i}", f"ชื่อ{i}", "ปริญญาเอก", "สาขา"], group=GROUP_A) for i in range(1, 4)]
    section = TableSection(type="table", slot_id="table_ps_1_1", headers=headers, rows=rows)
    inject_table(resolved, section)
    assert len(table.rows) == 9
    assert _row_texts(table, 5)[0] == "4."  # row untouched, still placeholder "4."
    assert _row_texts(table, 6)[0] == "5."
    print("test_partial_fill: PASS")


def test_overflow_inserts_inside_group():
    document, table, headers, resolved = _fresh_table_1_1()
    rows = [_row([f"ตำแหน่ง{i}", f"ชื่อ{i}", "ปริญญาเอก", "สาขา"], group=GROUP_A) for i in range(1, 8)]
    section = TableSection(type="table", slot_id="table_ps_1_1", headers=headers, rows=rows)
    inject_table(resolved, section)
    assert len(table.rows) == 11, f"expected 11 rows (9 + 2 overflow), got {len(table.rows)}"
    # the two new rows must land right after original group A (before the group B divider),
    # so the divider "อาจารย์ประจำหลักสูตร" must now be at index 9, not 7
    divider_texts = [t for t in (_row_texts(table, i) for i in range(len(table.rows))) if GROUP_B in t]
    assert divider_texts, "group B divider text not found anywhere in the table"
    divider_row_index = next(i for i in range(len(table.rows)) if GROUP_B in _row_texts(table, i))
    assert divider_row_index == 9, f"expected group B divider to have shifted to index 9, got {divider_row_index}"
    assert _row_texts(table, 7)[0] == "6. ตำแหน่ง6"
    assert _row_texts(table, 8)[0] == "7. ตำแหน่ง7"
    assert _has_borders(table.rows[7]) and _has_borders(table.rows[8]), "inserted rows must keep borders"
    print("test_overflow_inserts_inside_group: PASS")


def test_group_routing_regardless_of_order():
    document, table, headers, resolved = _fresh_table_1_1()
    rows = [
        _row(["B-ตำแหน่ง", "B-ชื่อ", "ปริญญาโท", "สาขา"], group=GROUP_B),
        _row(["A-ตำแหน่ง1", "A-ชื่อ1", "ปริญญาเอก", "สาขา"], group=GROUP_A),
    ]
    section = TableSection(type="table", slot_id="table_ps_1_1", headers=headers, rows=rows)
    inject_table(resolved, section)
    # group A is processed before group B regardless of the agent's row order,
    # so numbering continues 1 (group A) then 2 (group B), not agent order.
    assert _row_texts(table, 2)[0] == "1. A-ตำแหน่ง1", "group A data must land in group A's placeholder rows"
    assert _row_texts(table, 8)[0] == "2. B-ตำแหน่ง", "group B data must land in group B's placeholder row"
    print("test_group_routing_regardless_of_order: PASS")


def test_column_mismatch_raises():
    document, table, headers, resolved = _fresh_table_1_1()
    rows = [_row(["only", "three", "values"], group=GROUP_A)]
    section = TableSection(type="table", slot_id="table_ps_1_1", headers=headers, rows=rows)
    try:
        inject_table(resolved, section)
        raise AssertionError("expected InjectionError for column-count mismatch")
    except InjectionError:
        print("test_column_mismatch_raises: PASS")


def test_unsupported_table_shape_rejected():
    # A genuinely unsupported table: the static PS pass/fail checklist in the
    # test fixture has no placeholder rows at all (every row already has
    # real, fixed checkbox text - "[✓] ผ่านเกณฑ์ PS" - not a bare "[ ]"), so
    # `has_placeholders` must stay False and injection must refuse to guess.
    # (Table 1.2 in the real template used to serve as this test's example,
    # but header-detection/record-grouping now correctly recognizes its
    # shape as supported - see test_table_1_2_is_recognized_as_supported.)
    document = docx.Document(str(UNMARKED_FIXTURE_PATH))
    table = document.tables[1]
    layout = analyze_table_groups(table)
    assert not layout.has_placeholders, "checklist table should have no placeholder rows"
    resolved = ResolvedSlot(
        criterion="PS", slot_id="table_checklist", type="table",
        headers=logical_header_texts(table.rows[0]), table=table, marker_paragraph=None, layout=layout,
    )
    section = TableSection(type="table", slot_id="table_checklist", headers=resolved.headers, rows=[])
    try:
        inject_table(resolved, section)
        raise AssertionError("expected InjectionError for unsupported table shape")
    except InjectionError:
        print("test_unsupported_table_shape_rejected: PASS")


def test_table_1_2_is_recognized_as_supported():
    document = docx.Document(str(TEMPLATE_PATH))
    table = document.tables[1]
    assert find_header_row_index(table) == 1, "real 5-column header is row 1, not row 0"

    layout = analyze_table_groups(table)
    assert layout.has_placeholders, "Table 1.2 should now be recognized as fillable"
    assert len(layout.header_columns) == 5

    all_records = [r for g in layout.groups for r in group_into_records(g.rows)]
    assert len(all_records) == 14, f"expected 14 instructor records, got {len(all_records)}"
    assert all(len(r.rows) == 5 for r in all_records), "every record should span exactly 5 rows"
    print("test_table_1_2_is_recognized_as_supported: PASS")


def _year_rows(person, years, group=GROUP_A):
    return [
        _row([person, "ปร.ด.", str(year), str(i + 1), "0"], group=group, record_key=person)
        for i, year in enumerate(years)
    ]


def test_record_exact_fit():
    document, table, headers, resolved, num_records = _fresh_table_1_2()
    rows = _year_rows("คนที่ 1", [2568, 2567, 2566, 2565, 2564])
    for r in range(2, num_records + 1):
        rows += _year_rows(f"คนที่ {r}", [2568, 2567, 2566, 2565, 2564])
    section = TableSection(type="table", slot_id="table_ps_1_2", headers=headers, rows=rows)
    inject_table(resolved, section)
    assert len(table.rows) == 73, f"expected still 73 rows, got {len(table.rows)}"
    first_block_texts = [_row_texts(table, i)[:3] for i in range(3, 8)]
    assert [t[0] for t in first_block_texts] == ["คนที่ 1"] * 5
    assert [t[2] for t in first_block_texts] == ["2568", "2567", "2566", "2565", "2564"]
    print("test_record_exact_fit: PASS")


def test_record_fewer_sub_rows_leaves_remainder_blank():
    # Columns 0-1 (identity: name+position, degree) turn out to be genuinely
    # vertically-merged (vMerge restart/continue) across each 5-row block in
    # the real template - confirmed directly against the raw XML (tc.vMerge
    # via each row's *own* <w:tc>, not the delegating high-level `.cells`
    # API, which transparently returns the restart row's cell for every
    # continuation row). So writing the identity columns on the block's
    # first physical row is expected to visually cover the whole merged
    # region - that's correct, desirable Word behavior, not a bug. What
    # must NOT leak is the *varying* per-row data (here: "พ.ศ." year, column
    # 2, which is NOT merged) - the remaining physical rows must stay blank
    # there rather than showing a leftover value from elsewhere.
    document, table, headers, resolved, num_records = _fresh_table_1_2()
    rows = _year_rows("คนที่ 1", [2568, 2567])  # only 2 of 5 years
    for r in range(2, num_records + 1):
        rows += _year_rows(f"คนที่ {r}", [2568, 2567, 2566, 2565, 2564])
    section = TableSection(type="table", slot_id="table_ps_1_2", headers=headers, rows=rows)
    inject_table(resolved, section)
    filled_years = [_row_texts(table, i)[2] for i in range(3, 5)]
    remainder_years = [_row_texts(table, i)[2] for i in range(5, 8)]
    assert filled_years == ["2568", "2567"]
    assert remainder_years == ["", "", ""], f"unfilled sub-rows' varying column should stay blank, got {remainder_years}"
    print("test_record_fewer_sub_rows_leaves_remainder_blank: PASS")


def test_record_overflow_inserts_inside_block():
    document, table, headers, resolved, num_records = _fresh_table_1_2()
    rows = _year_rows("คนที่ 1", [2569, 2568, 2567, 2566, 2565, 2564])  # 6 years, block only has 5 rows
    for r in range(2, num_records + 1):
        rows += _year_rows(f"คนที่ {r}", [2568, 2567, 2566, 2565, 2564])
    section = TableSection(type="table", slot_id="table_ps_1_2", headers=headers, rows=rows)
    inject_table(resolved, section)
    assert len(table.rows) == 74, f"expected 74 rows (73 + 1 overflow), got {len(table.rows)}"
    block_texts = [_row_texts(table, i)[:3] for i in range(3, 9)]
    assert [t[0] for t in block_texts] == ["คนที่ 1"] * 6
    assert [t[2] for t in block_texts] == ["2569", "2568", "2567", "2566", "2565", "2564"]
    # the next block (คนที่ 2) must now start one row later, at index 9
    assert _row_texts(table, 9)[0] == "คนที่ 2"
    print("test_record_overflow_inserts_inside_block: PASS")


def test_record_count_mismatch_raises():
    document, table, headers, resolved, num_records = _fresh_table_1_2()
    rows = _year_rows("คนที่ 1", [2568, 2567, 2566, 2565, 2564])  # only 1 record, template expects 14
    section = TableSection(type="table", slot_id="table_ps_1_2", headers=headers, rows=rows)
    try:
        inject_table(resolved, section)
        raise AssertionError("expected InjectionError for record-count mismatch")
    except InjectionError:
        print("test_record_count_mismatch_raises: PASS")


def test_record_checkbox_written():
    document, table, headers, resolved, num_records = _fresh_table_1_2(with_checkbox=True)
    assert resolved.checkbox_options == [GROUP_B, GROUP_A], resolved.checkbox_options

    rows = _year_rows("คนที่ 1", [2568, 2567, 2566, 2565, 2564], group=GROUP_A)
    for r in range(2, num_records + 1):
        rows += _year_rows(f"คนที่ {r}", [2568, 2567, 2566, 2565, 2564], group=GROUP_B)
    section = TableSection(type="table", slot_id="table_ps_1_2", headers=headers, rows=rows)
    inject_table(resolved, section)

    # Only the block's *first* physical row is what Word actually displays
    # for the vMerge-spanned identity column - the checkbox lines must live
    # there, marking GROUP_A's checkbox for คนที่ 1.
    cell_text = table.rows[3].cells[0].text
    lines = cell_text.split("\n")
    assert lines[0] == "คนที่ 1", lines
    assert f"[✓] {GROUP_A}" in lines, lines
    assert f"[ ] {GROUP_B}" in lines, lines

    # คนที่ 2 (GROUP_B) - block starts at physical row 8 (5 rows per block)
    cell_text_2 = table.rows[8].cells[0].text
    lines_2 = cell_text_2.split("\n")
    assert f"[✓] {GROUP_B}" in lines_2, lines_2
    assert f"[ ] {GROUP_A}" in lines_2, lines_2
    print("test_record_checkbox_written: PASS")


def main() -> int:
    tests = [
        test_exact_fit,
        test_partial_fill,
        test_overflow_inserts_inside_group,
        test_group_routing_regardless_of_order,
        test_column_mismatch_raises,
        test_unsupported_table_shape_rejected,
        test_table_1_2_is_recognized_as_supported,
        test_record_exact_fit,
        test_record_fewer_sub_rows_leaves_remainder_blank,
        test_record_overflow_inserts_inside_block,
        test_record_count_mismatch_raises,
        test_record_checkbox_written,
    ]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"{test.__name__}: FAIL - {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
