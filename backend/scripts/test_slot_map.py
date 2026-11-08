"""Offline test of the REAL injection -> slot_map -> HTML id chain (fix.md
sec.11/12) using tests/fixtures' real template2.docx tables - no Gemini/MCP/
Mongo. Proves that build_slot_map() (fed by template_injector's Placement
collection) records where each agent row REALLY landed, so that
data-reference-id="<slot>.row<i>.col<j>" in the preview HTML sits on the cell
that actually holds agent row i / column j - the exact id the Reference tree
uses. (test_lifecycle.py seeds its slot_map by hand; this test covers the
production code that builds it.)
"""

import sys
from pathlib import Path

import docx
import lxml.html

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.schemas import NarrativeSection, RowCitation, TableRow, TableSection  # noqa: E402
from document.docx_edit import apply_html_to_docx  # noqa: E402
from document.docx_to_html import document_to_html  # noqa: E402
from master_agent.docx_utils import (  # noqa: E402
    analyze_table_groups,
    extract_checkbox_options,
    find_header_row_index,
    group_into_records,
    logical_header_texts,
)
from master_agent.slot_map import build_slot_map  # noqa: E402
from master_agent.slot_marking_agent import ResolvedSlot  # noqa: E402
from master_agent.template_injector import Placement, inject_section  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "test_fixtures" / "template2.docx"
GROUP_A, GROUP_B = "อาจารย์ผู้รับผิดชอบหลักสูตร", "อาจารย์ประจำหลักสูตร"


def _row(values, group=None, record_key=None, checked=None):
    return TableRow(
        values=values,
        citations=[RowCitation(source_filename="mongodb:education:x", chunk_index=0)],
        group=group,
        record_key=record_key,
        checked_options=checked,
    )


def _cells_by_reference(html: str) -> dict[str, list[str]]:
    root = lxml.html.fromstring(f"<div>{html}</div>")
    found = {}
    for cell in root.iter("td", "th"):
        rid = cell.get("data-reference-id")
        if rid:
            assert rid not in found, f"duplicate data-reference-id {rid}"
            lines = [t.strip() for t in cell.itertext() if t.strip()]
            found[rid] = lines
    return found


def test_single_row_table_ids_match_real_cells():
    document = docx.Document(str(TEMPLATE))
    table = document.tables[0]
    resolved = ResolvedSlot(
        criterion="PS", slot_id="table_ps_1_1", type="table",
        headers=logical_header_texts(table.rows[0]), table=table, marker_paragraph=None,
        layout=analyze_table_groups(table),
    )
    # deliberately out of template order: group routing places row 1 before row 0
    rows = [
        _row(["ผศ.", "ดร.ข", "ปริญญาเอก", "ปร.ด. ก"], group=GROUP_B),
        _row(["รศ.", "ดร.ก", "ปริญญาโท", "วท.ม. ข"], group=GROUP_A),
        _row(["อ.", "ดร.ค", "ปริญญาตรี", "วท.บ. ค"], group=GROUP_A),
    ]
    placements: list[Placement] = []
    inject_section({"table_ps_1_1": resolved}, TableSection(type="table", slot_id="table_ps_1_1", headers=resolved.headers, rows=rows), placements)
    assert len(placements) == 3

    slot_map = build_slot_map(document, {"table_ps_1_1": resolved}, {"table_ps_1_1"}, placements)
    (block, info), = slot_map["tables"].items()
    assert info["slotId"] == "table_ps_1_1" and sorted(info["rows"].values()) == [0, 1, 2]

    ref_ids = {f"table_ps_1_1.row{i}.col{j}" for i in range(3) for j in range(4)}
    html = document_to_html(document, slot_map=slot_map, reference_ids=ref_ids)
    cells = _cells_by_reference(html)
    assert len(cells) == 12, len(cells)
    for i, row in enumerate(rows):
        for j, value in enumerate(row.values):
            got = " ".join(cells[f"table_ps_1_1.row{i}.col{j}"])
            assert got.endswith(value), (i, j, got, value)  # (ordinal prefix, if any, precedes the value)
    # ids are only attached where a Reference item exists
    assert 'data-reference-id="table_ps_1_1.row0.col0"' in html
    assert "data-reference-id" not in document_to_html(document, slot_map=slot_map, reference_ids=set())
    print("test_single_row_table_ids_match_real_cells: PASS")


def test_record_table_ids_match_real_cells():
    document = docx.Document(str(TEMPLATE))
    table = document.tables[1]
    header_row = table.rows[find_header_row_index(table)]
    layout = analyze_table_groups(table)
    records = [r for g in layout.groups for r in group_into_records(g.rows)]
    options = extract_checkbox_options(records[0].label)
    resolved = ResolvedSlot(
        criterion="PS", slot_id="table_ps_1_2", type="table",
        headers=logical_header_texts(header_row), table=table, marker_paragraph=None,
        layout=layout, rows_per_record=len(records[0].rows), checkbox_options=options,
    )
    n_cols = len(resolved.headers)
    rows = []
    for key, name in (("p1", "รศ.ดร.ก"), ("p2", "ผศ.ดร.ข")):
        for year in (2564, 2565):
            rows.append(_row([name, "ปริญญาเอก", str(year), "3", "1"], record_key=key, group=options[0]))
    placements: list[Placement] = []
    inject_section({"table_ps_1_2": resolved}, TableSection(type="table", slot_id="table_ps_1_2", headers=resolved.headers, rows=rows), placements)
    assert len(placements) == 4

    slot_map = build_slot_map(document, {"table_ps_1_2": resolved}, {"table_ps_1_2"}, placements)
    ref_ids = {f"table_ps_1_2.row{i}.col{j}" for i in range(4) for j in range(n_cols)}
    cells = _cells_by_reference(document_to_html(document, slot_map=slot_map, reference_ids=ref_ids))
    # columns 0-1 (identity / education) are vertically merged across a record's block in the real
    # template: only the block's FIRST sub-row owns a rendered cell (rowspan); later sub-rows have none
    for i, row in enumerate(rows):
        first_sub_row = i % 2 == 0
        for j in range(n_cols):
            rid = f"table_ps_1_2.row{i}.col{j}"
            if j >= 2:
                assert cells[rid] == [row.values[j]], (rid, cells.get(rid))
            elif first_sub_row:
                assert cells[rid][0] == row.values[j], (rid, cells.get(rid))
            else:
                assert rid not in cells, f"{rid} attached to a non-existent (vMerge-continued) cell"
    print("test_record_table_ids_match_real_cells: PASS")


def test_narrative_and_edit_round_trip():
    document = docx.Document(str(TEMPLATE))
    paragraph = next(p for p in document.paragraphs if not p.text.strip())
    resolved = ResolvedSlot(criterion="PS", slot_id="intro_ps", type="narrative", paragraph=paragraph)
    inject_section({"intro_ps": resolved}, NarrativeSection(type="narrative", slot_id="intro_ps", content="ข้อความเดิม [1]"), [])
    slot_map = build_slot_map(document, {"intro_ps": resolved}, {"intro_ps"}, [])
    (block, info), = slot_map["paragraphs"].items()
    assert info["slotId"] == "intro_ps"
    html = document_to_html(document, slot_map=slot_map, reference_ids={"intro_ps"})
    assert f'<p data-block="{block}" data-slot-id="intro_ps" data-section="PS" data-reference-id="intro_ps">ข้อความเดิม [1]</p>' in html

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base.docx"
        document.save(str(base))
        edited = html.replace("ข้อความเดิม [1]", "ข้อความใหม่ [1]")
        changes = apply_html_to_docx(base, edited, Path(tmp) / "out.docx")
        assert [c.element_id for c in changes] == [f"b{block}"]
        assert any(p.text == "ข้อความใหม่ [1]" for p in docx.Document(str(Path(tmp) / "out.docx")).paragraphs)
    print("test_narrative_and_edit_round_trip: PASS")


if __name__ == "__main__":
    test_single_row_table_ids_match_real_cells()
    test_record_table_ids_match_real_cells()
    test_narrative_and_edit_round_trip()
    print("\n3/3 passed")
