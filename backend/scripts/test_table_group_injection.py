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

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "test_fixtures" / "template2.docx"
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
    # This fixture defines borders once at the table level (<w:tblPr>
    # <w:tblBorders>), not per-cell (<w:tcBorders>) - confirmed directly
    # against the raw XML for every row in the table, including original,
    # never-inserted template rows. So per-cell <w:tcBorders> is never
    # present here even on rows that render with borders correctly - it is
    # not a valid signal of "did insert_row_after preserve this row's
    # formatting". What insert_row_after's own docstring actually guards
    # against is producing a bare cell with NO <w:tcPr> at all, which is
    # what plain `table.add_row()` would do instead - so that presence is
    # what's meaningful to check for this fixture.
    return all(cell._tc.find(qn("w:tcPr")) is not None for cell in row.cells)


def test_exact_fit():
    # Table 1.1's real fixture shape (test_fixtures/template2.docx, table 0),
    # confirmed directly against the raw XML: header(row0) + a blank divider
    # (row1, label="") + 5 Group-A placeholder rows (rows2-6) + the
    # "อาจารย์ประจำหลักสูตร" divider (row7) + 8 Group-B placeholder rows
    # (rows8-15) = 16 physical rows total. Injecting exactly 5 Group-A
    # records fills Group A's 5 placeholders with no overflow and leaves
    # Group B (0 records) untouched, so the table stays at its real 16 rows -
    # NOT 9 (an earlier, incorrect assumption about this fixture's row
    # count). Also: none of these placeholder cells carry literal ordinal
    # text ("1.", "2.", ...) - `layout.numbered` is correctly False for this
    # table, so the agent's value is written as-is, with no "N. " prefix
    # (unlike a table whose own template placeholders were numbered).
    document, table, headers, resolved = _fresh_table_1_1()
    rows = [_row([f"ตำแหน่ง{i}", f"ชื่อ{i}", "ปริญญาเอก", "สาขา"], group=GROUP_A) for i in range(1, 6)]
    section = TableSection(type="table", slot_id="table_ps_1_1", headers=headers, rows=rows)
    inject_table(resolved, section)
    assert len(table.rows) == 16, f"expected still 16 rows, got {len(table.rows)}"
    for i, ri in enumerate(range(2, 7)):
        texts = _row_texts(table, ri)
        assert texts[0] == f"ตำแหน่ง{i + 1}", texts
    print("test_exact_fit: PASS")


def test_partial_fill():
    # Same real 16-row shape as test_exact_fit. With only 3 of Group A's 5
    # placeholders filled, the remaining 2 stay exactly as they started:
    # genuinely blank (this fixture's placeholders carry no literal ordinal
    # text at all, unlike a numbered-list-style table).
    document, table, headers, resolved = _fresh_table_1_1()
    rows = [_row([f"ตำแหน่ง{i}", f"ชื่อ{i}", "ปริญญาเอก", "สาขา"], group=GROUP_A) for i in range(1, 4)]
    section = TableSection(type="table", slot_id="table_ps_1_1", headers=headers, rows=rows)
    inject_table(resolved, section)
    assert len(table.rows) == 16, f"expected still 16 rows, got {len(table.rows)}"
    assert _row_texts(table, 5) == ["", "", "", ""], "unfilled Group A placeholder row should stay blank"
    assert _row_texts(table, 6) == ["", "", "", ""], "unfilled Group A placeholder row should stay blank"
    print("test_partial_fill: PASS")


def test_overflow_inserts_inside_group():
    # 7 records into Group A's 5 real placeholders needs 2 overflow rows,
    # inserted inside Group A (before the Group B divider) - 16 + 2 = 18
    # total rows, not 11 (which assumed the fixture's real 16-row baseline
    # was 9 - see test_exact_fit).
    document, table, headers, resolved = _fresh_table_1_1()
    rows = [_row([f"ตำแหน่ง{i}", f"ชื่อ{i}", "ปริญญาเอก", "สาขา"], group=GROUP_A) for i in range(1, 8)]
    section = TableSection(type="table", slot_id="table_ps_1_1", headers=headers, rows=rows)
    inject_table(resolved, section)
    assert len(table.rows) == 18, f"expected 18 rows (16 + 2 overflow), got {len(table.rows)}"
    # the two new rows must land right after original group A (before the group B divider),
    # so the divider "อาจารย์ประจำหลักสูตร" must now be at index 9, not 7
    divider_texts = [t for t in (_row_texts(table, i) for i in range(len(table.rows))) if GROUP_B in t]
    assert divider_texts, "group B divider text not found anywhere in the table"
    divider_row_index = next(i for i in range(len(table.rows)) if GROUP_B in _row_texts(table, i))
    assert divider_row_index == 9, f"expected group B divider to have shifted to index 9, got {divider_row_index}"
    assert _row_texts(table, 7)[0] == "ตำแหน่ง6"
    assert _row_texts(table, 8)[0] == "ตำแหน่ง7"
    assert _has_borders(table.rows[7]) and _has_borders(table.rows[8]), "inserted rows must keep borders"
    print("test_overflow_inserts_inside_group: PASS")


def test_group_routing_regardless_of_order():
    # This table's placeholders carry no literal ordinal text (layout.numbered
    # is False - see test_exact_fit), so there is no cross-group numbering to
    # continue; each row's value is written as-is. What this test actually
    # verifies is routing: group A's record must land in group A's
    # placeholder rows (physical rows 2-6) and group B's record in group B's
    # placeholder rows (physical rows 8-15), regardless of the order the
    # agent submitted them in.
    document, table, headers, resolved = _fresh_table_1_1()
    rows = [
        _row(["B-ตำแหน่ง", "B-ชื่อ", "ปริญญาโท", "สาขา"], group=GROUP_B),
        _row(["A-ตำแหน่ง1", "A-ชื่อ1", "ปริญญาเอก", "สาขา"], group=GROUP_A),
    ]
    section = TableSection(type="table", slot_id="table_ps_1_1", headers=headers, rows=rows)
    inject_table(resolved, section)
    assert _row_texts(table, 2)[0] == "A-ตำแหน่ง1", "group A data must land in group A's placeholder rows"
    assert _row_texts(table, 8)[0] == "B-ตำแหน่ง", "group B data must land in group B's placeholder row"
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


def test_record_fewer_than_blocks_fills_in_order_leaves_extra_blank():
    # change.md "PS Table 1.2" - the exact real-world case: template has 14
    # record blocks (this fixture, matching the real Table 1.2 v2
    # structure) but the real MongoDB data behind this curriculum only has
    # 13 distinct instructors (5 programmeResponsible, all of whom are also
    # among 13 total programmeStaff - confirmed against aunqa_ps). This is
    # not a parser/agent bug - the template was authored with one more
    # block than this curriculum's real instructor count. Filling blocks in
    # template order and leaving the last (unused) block untouched is
    # deterministic and never guesses which person "block 14" belongs to,
    # since no person's data is ever written there at all.
    document, table, headers, resolved, num_records = _fresh_table_1_2()
    assert num_records == 14
    # capture block 14's original (untouched-by-injection) placeholder
    # content before injecting, since "untouched" means identical to the
    # template's own original text - not blanked out.
    original_block_14 = [_row_texts(table, i) for i in range(68, 73)]

    rows = []
    for r in range(1, 14):  # 13 real records, template has 14 blocks
        rows += _year_rows(f"คนที่ {r}", [2568, 2567, 2566, 2565, 2564])
    section = TableSection(type="table", slot_id="table_ps_1_2", headers=headers, rows=rows)
    inject_table(resolved, section)  # must NOT raise

    assert len(table.rows) == 73, f"no rows inserted/removed, got {len(table.rows)}"
    # blocks 1-13 (physical rows 3..67, 5 rows each) filled in template order
    for r in range(1, 14):
        block_start = 3 + (r - 1) * 5
        assert _row_texts(table, block_start)[0] == f"คนที่ {r}", f"block {r} identity mismatch"
    # block 14 (physical rows 68..72, the last 5 rows) must be byte-for-byte
    # unchanged from the template's own original placeholder content - never
    # fabricated, never shifted from another person's data
    new_block_14 = [_row_texts(table, i) for i in range(68, 73)]
    assert new_block_14 == original_block_14, (
        f"block 14 should stay exactly as the template had it, got {new_block_14} vs original {original_block_14}"
    )
    print("test_record_fewer_than_blocks_fills_in_order_leaves_extra_blank: PASS")


def test_record_more_than_blocks_raises():
    # The genuinely unsafe direction: the agent claims more distinct real
    # records exist than the template has physical blocks for. Satisfying
    # this would mean either dropping a real person's data or inventing a
    # block that doesn't exist - both are guesses, so this must still raise.
    document, table, headers, resolved, num_records = _fresh_table_1_2()
    rows = []
    for r in range(1, 16):  # 15 records, template only has 14 blocks
        rows += _year_rows(f"คนที่ {r}", [2568, 2567, 2566, 2565, 2564])
    section = TableSection(type="table", slot_id="table_ps_1_2", headers=headers, rows=rows)
    try:
        inject_table(resolved, section)
        raise AssertionError("expected InjectionError when agent has more records than template blocks")
    except InjectionError:
        print("test_record_more_than_blocks_raises: PASS")


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
        test_record_fewer_than_blocks_fills_in_order_leaves_extra_blank,
        test_record_more_than_blocks_raises,
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
