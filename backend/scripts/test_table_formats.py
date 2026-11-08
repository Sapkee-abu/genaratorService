"""PS Table 1.1 / 1.2 column-0 formatting tests (presentation only; no DB, no LLM).

Table 1.1  "N. <full academic title>"       e.g. "1. รองศาสตราจารย์"  (N = display order, continuous across groups)
Table 1.2  "N. <position abbr><title><name>" e.g. "1. รศ.ดร.พีรวิชญ์ เควด"  (N = record order)
The name / education / degree / field / count / year columns are NOT touched by this change.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.schemas import TargetSlot  # noqa: E402
from criterion_agents.ps_agent.academic_position import (  # noqa: E402
    full_academic_position,
    position_and_name,
    strip_leading_titles,
)
from criterion_agents.ps_agent.agent import _build_table_1_1, _build_table_1_2  # noqa: E402
from criterion_agents.ps_agent.person_aggregation import aggregate_curriculum_people  # noqa: E402

GROUP_A, GROUP_B = "อาจารย์ผู้รับผิดชอบหลักสูตร", "อาจารย์ประจำหลักสูตร"


def _people(spec):
    """spec: [(id, position, title, first, last, roles)] -> AggregatedPerson list (through the real aggregation)."""
    persons = [{"_id": i, "firstName": f, "lastName": l, "academicPosition": pos, "title": t, "source_filename": f"mongodb:persons:{i}"}
               for i, pos, t, f, l, _ in spec]
    appts = [{"personId": i, "role": r, "status": "active"} for i, *_rest, roles in spec for r in roles]
    edus = [{"personId": i, "degree": "ปร.ด.", "field": "F", "graduationYear": 2560, "source_filename": f"mongodb:educations:{i}"} for i, *_ in spec]
    return aggregate_curriculum_people(appts, persons, edus, [])


def test_full_title_mapping_is_explicit_and_never_invents():
    assert full_academic_position("รศ.") == "รองศาสตราจารย์"
    assert full_academic_position("ผศ.") == "ผู้ช่วยศาสตราจารย์"
    assert full_academic_position("อ.") == "อาจารย์" and full_academic_position("ศ.") == "ศาสตราจารย์"
    assert full_academic_position("รศ") == "รองศาสตราจารย์"  # source missing its dot
    assert full_academic_position("") == ""  # blank stays blank
    assert full_academic_position("ศ.ดร.") == "ศ.ดร."  # unknown value: shown as in the source, not guessed
    print("test_full_title_mapping_is_explicit_and_never_invents: PASS")


def test_no_duplicate_titles_and_names_starting_with_title_letters_survive():
    assert position_and_name("รศ.", "ดร.", "พีรวิชญ์", "เควด") == "รศ.ดร.พีรวิชญ์ เควด"
    assert position_and_name("ผศ.", "ดร.", "ดร.สุภาภรณ์", "ใจรังษี") == "ผศ.ดร.สุภาภรณ์ ใจรังษี"  # name already has ดร.
    assert position_and_name("ผศ.", "", "ผศ.กาญจนา", "หฤหรรษพงศ์") == "ผศ.กาญจนา หฤหรรษพงศ์"  # name already has the rank
    assert position_and_name("รศ.", "ดร.", "ผศ. ดร. X", "Y") == "รศ.ดร.X Y"
    assert position_and_name("", "", "เจริญพร", "บัวแย้ม") == "เจริญพร บัวแย้ม"
    # real names that merely START with a title letter are never mangled
    assert position_and_name("ผศ.", "ดร.", "ศิริรัตน์", "สมเชื้อ") == "ผศ.ดร.ศิริรัตน์ สมเชื้อ"
    assert position_and_name("อ.", "", "อรุณ", "ใจดี") == "อ.อรุณ ใจดี"
    assert strip_leading_titles("ดร.ดร.ดร.X Y") == "X Y"
    print("test_no_duplicate_titles_and_names_starting_with_title_letters_survive: PASS")


def test_table_1_1_numbering_restarts_in_each_section():
    # canonical person order (personId asc): p1 staff-only, p2 dual, p3 dual, p4 staff-only
    people = _people([
        ("p1", "ผศ.", "ดร.", "สอง", "หนึ่ง", ["programmeStaff"]),
        ("p2", "รศ.", "ดร.", "เอ", "หนึ่ง", ["programmeResponsible", "programmeStaff"]),
        ("p3", "ผศ.", "ดร.", "เอ", "สอง", ["programmeResponsible", "programmeStaff"]),
        ("p4", "อ.", "", "สี่", "สี่", ["programmeStaff"]),
    ])
    slot = TargetSlot(slot_id="table_ps_1_1", type="table", criterion="PS",
                      headers=["ตำแหน่งทางวิชาการ", "ชื่อ-นามสกุล", "วุฒิการศึกษาสูงสุด", "ชื่อปริญญา (สาขาวิชา)"], groups=[GROUP_A, GROUP_B])
    rows = _build_table_1_1(slot, people, {}).rows
    listing = [(r.group, r.values[0], r.values[1]) for r in rows]
    assert listing == [
        (GROUP_A, "1. รองศาสตราจารย์", "ดร.เอ หนึ่ง"),
        (GROUP_A, "2. ผู้ช่วยศาสตราจารย์", "ดร.เอ สอง"),
        (GROUP_B, "1. รองศาสตราจารย์", "ดร.เอ หนึ่ง"),       # dual-role people first in the staff section ...
        (GROUP_B, "2. ผู้ช่วยศาสตราจารย์", "ดร.เอ สอง"),
        (GROUP_B, "3. ผู้ช่วยศาสตราจารย์", "ดร.สอง หนึ่ง"),   # ... then the staff-only ones
        (GROUP_B, "4. อาจารย์", "สี่ สี่"),
    ], listing
    # nothing else in a row changed: name / level / degree columns and the citations keep their old meaning
    first = rows[0]
    assert first.values[2] == "ปริญญาเอก" and first.values[3] == "ปร.ด. F" and first.column_citations["0"][0].source_filename == "mongodb:persons:p2"
    print("test_table_1_1_numbering_restarts_in_each_section: PASS")


def test_table_1_2_numbering_and_identity_text():
    people = _people([
        ("p1", "รศ.", "ดร.", "พีรวิชญ์", "เควด", ["programmeResponsible", "programmeStaff"]),
        ("p2", "ผศ.", "ดร.", "สุภาภรณ์", "ใจรังษี", ["programmeResponsible", "programmeStaff"]),
        ("p3", "ผศ.", "", "กาญจนา", "หฤหรรษพงศ์", ["programmeStaff"]),
    ])
    slot = TargetSlot(slot_id="table_ps_1_2", type="table", criterion="PS", headers=["a", "b", "c", "d", "e"], rows_per_record=5)
    rows = _build_table_1_2(slot, people).rows
    assert len(rows) == 15
    firsts = [rows[i * 5].values[0] for i in range(3)]
    assert firsts == ["1. รศ.ดร.พีรวิชญ์ เควด", "2. ผศ.ดร.สุภาภรณ์ ใจรังษี", "3. ผศ.กาญจนา หฤหรรษพงศ์"], firsts
    assert all(r.values[0] == firsts[i // 5] for i, r in enumerate(rows))  # the 5 year-rows of a person share the identity text
    # yearly values untouched by the format change: [education, year, academic, creative] keep their positions/meaning
    assert [r.values[2] for r in rows[:5]] == ["2569", "2568", "2567", "2566", "2565"]
    assert all(r.values[3] == "0" and r.values[4] == "0" for r in rows)
    assert rows[0].column_citations["0"][0].source_filename == "mongodb:persons:p1"
    print("test_table_1_2_numbering_and_identity_text: PASS")


def test_injector_does_not_double_number():
    import docx
    from common.schemas import RowCitation, TableRow, TableSection
    from master_agent.docx_utils import analyze_table_groups, logical_header_texts
    from master_agent.slot_marking_agent import ResolvedSlot
    from master_agent.template_injector import inject_table

    document = docx.Document(str(Path(__file__).resolve().parent.parent / "test_fixtures" / "template2.docx"))
    table = document.tables[0]
    # this template variant has blank placeholders; give them the numbered form ("1.", "2.", ...) some templates use
    from master_agent.docx_utils import set_cell_text

    ordinal = 1
    for row in table.rows[2:]:
        cells = row.cells
        if cells[0].text.strip() == "" and len({id(c._tc) for c in cells}) == 4:
            set_cell_text(cells[0], f"{ordinal}.")
            ordinal += 1
    layout = analyze_table_groups(table)
    assert layout.numbered, "numbered placeholders expected after seeding them"
    resolved = ResolvedSlot(criterion="PS", slot_id="t", type="table", headers=logical_header_texts(table.rows[0]), table=table,
                            marker_paragraph=None, layout=layout)
    cite = [RowCitation(source_filename="x", chunk_index=0)]
    rows = [TableRow(values=["1. รองศาสตราจารย์", "ดร.เอ บี", "ปริญญาเอก", "ปร.ด. F"], citations=cite, group=GROUP_A)]
    inject_table(resolved, TableSection(type="table", slot_id="t", headers=resolved.headers, rows=rows))
    first_data_row = next(r for r in table.rows if "รองศาสตราจารย์" in r.cells[0].text)
    assert first_data_row.cells[0].text.strip() == "1. รองศาสตราจารย์", first_data_row.cells[0].text  # not "1. 1. รองศาสตราจารย์"
    print("test_injector_does_not_double_number: PASS")


if __name__ == "__main__":
    tests = [test_full_title_mapping_is_explicit_and_never_invents, test_no_duplicate_titles_and_names_starting_with_title_letters_survive,
             test_table_1_1_numbering_restarts_in_each_section, test_table_1_2_numbering_and_identity_text,
             test_injector_does_not_double_number]
    for t in tests:
        t()
    print(f"\n{len(tests)}/{len(tests)} passed")
