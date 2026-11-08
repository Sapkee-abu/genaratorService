"""Table 1.2 "วุฒิการศึกษา (ทุกระดับ)" display + duplicate-rule tests (deterministic; no DB, no LLM).

  format     "1. <degree> <field>", one per line, NO year, meaningful parentheses kept, plain numbering, no backslash
  duplicates merged only when they are the SAME PERSON's same logical education (degree+field+year+institution name);
             abbreviated-vs-full / faculty suffix / OCR letter variants are NOT merged; different persons never compared
  traceability every underlying record stays cited, incl. the ones merged into a shown line
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import docx  # noqa: E402

from common.schemas import RowCitation, TableRow, TableSection, TargetSlot  # noqa: E402
from criterion_agents.ps_agent.agent import _build_table_1_2, _education_source_citations  # noqa: E402
from criterion_agents.ps_agent.education_display import education_cell_text, education_items, strip_year_parentheses  # noqa: E402
from criterion_agents.ps_agent.person_aggregation import aggregate_curriculum_people  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "test_fixtures" / "template2.docx"


def rec(_id, degree, field, year, inst="มหาวิทยาลัยวลัยลักษณ์", pid="P"):
    return {"_id": _id, "personId": pid, "degree": degree, "field": field, "graduationYear": year, "institution": inst,
            "source_filename": f"mongodb:educations:{_id}"}


def test_format_no_year_parentheses_kept_plain_numbering():
    # distinct education (different institutions), so nothing is merged: the format itself is what is checked
    recs = [rec("a1", "ปร.ด.", "วิทยาศาสตร์เชิงคำนวณ", 2562, "มหาวิทยาลัย ก"),
            rec("b1", "ปร.ด.", "ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)", 2562, "มหาวิทยาลัย ข"),
            rec("a2", "วท.บ.", "วิทยาศาสตร์เชิงคำนวณ", 2557, "มหาวิทยาลัย ก"),
            rec("b2", "วท.บ.", "วิทยาศาสตรบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)", 2557, "มหาวิทยาลัย ข")]
    text = education_cell_text(education_items(recs))
    assert text.split("\n") == [
        "1. ปร.ด. วิทยาศาสตร์เชิงคำนวณ",
        "2. ปร.ด. ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)",
        "3. วท.บ. วิทยาศาสตร์เชิงคำนวณ",
        "4. วท.บ. วิทยาศาสตรบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)",
    ], text  # degree + field exactly as stored, parentheses of the field kept, no year, plain numbering
    assert "2562" not in text and "2557" not in text and "\\" not in text
    print("test_format_no_year_parentheses_kept_plain_numbering: PASS")


def test_only_year_parentheses_are_removed():
    assert strip_year_parentheses("ปร.ด. X (2562)") == "ปร.ด. X"
    assert strip_year_parentheses("ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)") == "ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)"
    assert strip_year_parentheses("Networks (13) (2024)") == "Networks (13)"
    assert strip_year_parentheses("X (Journal 2562)") == "X (Journal 2562)"  # not purely a year -> kept
    # a year that happens to be inside the source field is removed too, but the record's own year is never displayed
    items = education_items([rec("x", "ปร.ด.", "วิทยาการคอมพิวเตอร์ (2562)", 2562)])
    assert education_cell_text(items) == "1. ปร.ด. วิทยาการคอมพิวเตอร์"
    print("test_only_year_parentheses_are_removed: PASS")


def test_confirmed_duplicates_are_merged_but_keep_every_record():
    # same person, degree, field, year; institution differs only by the country suffix -> ONE logical education
    a = rec("a", "Ph.D.", "Informatics", 2555, "King’s College London/ United Kingdom")
    b = rec("b", "Ph.D.", "Informatics", 2555, "King’s College London/ UK")
    # same person/degree/year/institution; field differs only by a space
    c = rec("c", "วท.ม.", "การจัดการคอมพิวเตอร์และ วิศวกรรม", 2536, "มหาวิทยาลัยอัสสัมชัญ")
    d = rec("d", "วท.ม.", "การจัดการคอมพิวเตอร์และวิศวกรรม", 2536, "มหาวิทยาลัยอัสสัมชัญ")
    items = education_items([b, a, d, c])
    assert [len(i.records) for i in items] == [2, 2] and len(items) == 2
    assert items[0].text == "Ph.D. Informatics" and items[1].text == "วท.ม. การจัดการคอมพิวเตอร์และ วิศวกรรม"  # earliest _id's text is shown
    assert [r["_id"] for r in items[0].records] == ["a", "b"] and [r["_id"] for r in items[1].records] == ["c", "d"]
    print("test_confirmed_duplicates_are_merged_but_keep_every_record: PASS")


def test_written_out_representation_of_the_same_education_is_merged_and_both_records_kept():
    # the real พีรวิชญ์ case: same person, degree abbreviation, year and institution; the second record's field is
    # "<full degree name> (<the first record's field>)"
    recs = [rec("f8e6", "ปร.ด.", "วิทยาศาสตร์เชิงคํานวณ", 2562), rec("f8e7", "วท.บ.", "วิทยาศาสตร์เชิงคํานวณ", 2557),
            rec("daea9", "ปร.ด.", "ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงคํานวณ)", 2562), rec("daeaa", "วท.บ.", "วิทยาศาสตรบัณฑิต (วิทยาศาสตร์เชิงคํานวณ)", 2557)]
    items = education_items(recs)
    assert education_cell_text(items) == "1. ปร.ด. วิทยาศาสตร์เชิงคํานวณ\n2. วท.บ. วิทยาศาสตร์เชิงคํานวณ"
    assert [[r["_id"] for r in i.records] for i in items] == [["f8e6", "daea9"], ["f8e7", "daeaa"]]  # shown record first, both kept
    # OCR-tolerant on the parenthesized major (sara-am / nikhahit / stray space): still the same education
    assert len(education_items([rec("a", "ปร.ด.", "วิทยาศาสตร์เชิงคำนวณ", 2565), rec("b", "ปร.ด.", "ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงค านวณ)", 2565)])) == 1
    # the plain representation is the one shown, whichever was imported first
    swapped = education_items([rec("a", "ปร.ด.", "ปรัชญาดุษฎีบัณฑิต (สาขา X)", 2562), rec("b", "ปร.ด.", "สาขา X", 2562)])
    assert education_cell_text(swapped) == "1. ปร.ด. สาขา X" and [r["_id"] for r in swapped[0].records] == ["b", "a"]
    print("test_written_out_representation_of_the_same_education_is_merged_and_both_records_kept: PASS")


def test_distinct_or_unproven_records_are_never_merged():
    # a written-out name whose LEVEL does not match the degree, or whose parenthesized text is another field: distinct
    assert len(education_items([rec("1", "ปร.ด.", "วิทยาศาสตร์เชิงคำนวณ", 2562), rec("2", "ปร.ด.", "วิทยาศาสตรมหาบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)", 2562)])) == 2
    assert len(education_items([rec("1", "ปร.ด.", "วิทยาศาสตร์เชิงคำนวณ", 2562), rec("2", "ปร.ด.", "ปรัชญาดุษฎีบัณฑิต (คอมพิวเตอร์)", 2562)])) == 2
    assert len(education_items([rec("1", "วท.บ.", "เคมีวิศวกรรม", 2530), rec("2", "วท.บ.", "เคมีวิศวกรรม คณะวิทยาศาสตร์", 2530)])) == 2  # faculty suffix: not proven
    assert len(education_items([rec("1", "วท.บ.", "วิทยาการคอมพิวเตอร์", 2541), rec("2", "วบ.บ.", "วิทยาการคอมพิวเตอร์", 2541)])) == 2  # one-letter degree variant
    assert len(education_items([rec("1", "วท.บ.", "วิทยาการคอมพิวเตอร์", 2541), rec("2", "วท.บ.", "วิทยาการคอมพิวเตอร์", 2545)])) == 2  # different year
    assert len(education_items([rec("1", "วท.บ.", "X", 2541, "ม.เชียงใหม่"), rec("2", "วท.บ.", "X", 2541, "ม.สงขลา")])) == 2  # different institution
    assert len(education_items([rec("1", "ปร.ด.", "F", 2562), rec("2", "ปร.ด.", "ปรัชญาดุษฎีบัณฑิต (F)", 2560)])) == 2  # written-out form but another year
    print("test_distinct_or_unproven_records_are_never_merged: PASS")


def test_noise_is_not_displayed_and_order_is_deterministic():
    noise = [rec("n1", "at", "https", 2560), rec("n2", "heuristic approach. Journal of Sensor and Actuator", "Networks, 13(5), 59. https", 2567)]
    good = [rec("g1", "วท.บ.", "ก", 2540), rec("g2", "ปร.ด.", "ข", 2555), rec("g3", "วท.ม.", "ค", 2548)]
    assert education_cell_text(education_items(noise + good)) == "1. ปร.ด. ข\n2. วท.ม. ค\n3. วท.บ. ก"  # year desc, year not shown
    assert education_cell_text(education_items(list(reversed(good + noise)))) == education_cell_text(education_items(good + noise))
    assert education_items(noise) == []
    print("test_noise_is_not_displayed_and_order_is_deterministic: PASS")


def test_different_persons_are_never_merged_and_citations_stay_complete():
    def person(pid, first, edu_ids):
        return {"_id": pid, "firstName": first, "lastName": "ทดสอบ", "academicPosition": "ผศ.", "title": "", "source_filename": f"mongodb:persons:{pid}"}, \
               [rec(i, "ปร.ด.", "วิทยาศาสตร์เชิงคำนวณ", 2562, pid=pid) for i in edu_ids]

    pa, ea = person("A", "เอ", ["a1"])
    pb, eb = person("B", "บี", ["b1", "b2"])  # B holds a genuine duplicate pair, A holds the same text - must stay separate
    appts = [{"personId": "A", "role": "programmeStaff", "status": "active"}, {"personId": "B", "role": "programmeStaff", "status": "active"}]
    people = {p.person_id: p for p in aggregate_curriculum_people(appts, [pa, pb], ea + eb, [])}
    assert education_cell_text(education_items(people["A"].educations)) == "1. ปร.ด. วิทยาศาสตร์เชิงคำนวณ"
    assert education_cell_text(education_items(people["B"].educations)) == "1. ปร.ด. วิทยาศาสตร์เชิงคำนวณ"  # b1+b2 merged inside B only
    # the SAME written-out pair split across two different persons is never merged (each person keeps their own record)
    pc, ec = person("C", "ซี", ["c1"])
    pd, ed = person("D", "ดี", ["d1"])
    ed = [dict(ed[0], field="ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)")]
    two = {p.person_id: p for p in aggregate_curriculum_people(
        [{"personId": "C", "role": "programmeStaff", "status": "active"}, {"personId": "D", "role": "programmeStaff", "status": "active"}], [pc, pd], ec + ed, [])}
    assert len(education_items(two["C"].educations)) == 1 and len(education_items(two["D"].educations)) == 1
    assert [c.source_filename for c in _education_source_citations(people["A"])] == ["mongodb:educations:a1"]
    assert [c.source_filename for c in _education_source_citations(people["B"])] == ["mongodb:educations:b1", "mongodb:educations:b2"]
    print("test_different_persons_are_never_merged_and_citations_stay_complete: PASS")


def test_table_1_2_row_carries_the_new_education_and_all_sources():
    person = {"_id": "P", "firstName": "พีรวิชญ์", "lastName": "เควด", "academicPosition": "รศ.", "title": "ดร.", "source_filename": "mongodb:persons:P"}
    edus = [rec("e1", "ปร.ด.", "X", 2562, pid="P"), rec("e2", "ปร.ด.", "X", 2562, pid="P"), rec("e3", "วท.บ.", "Y", 2557, pid="P")]
    people = aggregate_curriculum_people([{"personId": "P", "role": "programmeStaff", "status": "active"}], [person], edus, [])
    rows = _build_table_1_2(TargetSlot(slot_id="t", type="table", criterion="PS", headers=list("abcde"), rows_per_record=5), people).rows
    assert rows[0].values[1] == "1. ปร.ด. X\n2. วท.บ. Y", rows[0].values[1]
    assert [c.source_filename for c in rows[0].column_citations["1"]] == ["mongodb:educations:e1", "mongodb:educations:e2", "mongodb:educations:e3"]
    # yearly columns untouched by the education change
    assert [r.values[2] for r in rows] == ["2569", "2568", "2567", "2566", "2565"] and all(r.values[3] == "0" and r.values[4] == "0" for r in rows)
    print("test_table_1_2_row_carries_the_new_education_and_all_sources: PASS")


def test_multiline_cell_survives_injection_html_and_edit_roundtrip():
    from document.docx_edit import compute_changes
    from document.docx_to_html import document_to_html
    from master_agent.docx_utils import analyze_table_groups, find_header_row_index, group_into_records, logical_header_texts
    from master_agent.slot_marking_agent import ResolvedSlot
    from master_agent.template_injector import inject_table

    document = docx.Document(str(TEMPLATE))
    table = document.tables[1]
    layout = analyze_table_groups(table)
    records = [r for g in layout.groups for r in group_into_records(g.rows)]
    resolved = ResolvedSlot(criterion="PS", slot_id="t", type="table", headers=logical_header_texts(table.rows[find_header_row_index(table)]),
                            table=table, marker_paragraph=None, layout=layout, rows_per_record=len(records[0].rows))
    cite = [RowCitation(source_filename="x", chunk_index=0)]
    edu = "1. ปร.ด. X\n2. ปรัชญา (Y)\n3. วท.บ. Z"
    rows = [TableRow(values=["1. รศ.ดร.ก ข", edu, str(y), "0", "0"], citations=cite, record_key="k") for y in (2569, 2568, 2567, 2566, 2565)]
    inject_table(resolved, TableSection(type="table", slot_id="t", headers=resolved.headers, rows=rows))
    cell_text = records[0].rows[0].cells[1].text
    assert cell_text.split("\n") == edu.split("\n"), repr(cell_text)  # one paragraph, real line breaks, no "\\" anywhere
    html = document_to_html(document)
    assert "1. ปร.ด. X<br />2. ปรัชญา (Y)<br />3. วท.บ. Z" in html and "\\" not in html
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "g.docx"
        document.save(str(p))
        assert compute_changes(p, html) == []  # the preview HTML maps back to the DOCX with zero differences
    print("test_multiline_cell_survives_injection_html_and_edit_roundtrip: PASS")


def test_reference_lists_every_source_record_of_a_multi_record_cell():
    from reference.traceability_api import _table_leaves

    def row(cites):
        return {"values": ["1. x", "1. a\n2. b", "2569", "0", "0"], "citations": [], "column_citations": cites}

    c = lambda i: {"source_filename": f"mongodb:educations:{i}", "chunk_index": 0}
    section = {"slot_id": "t", "headers": ["h0", "h1", "h2", "h3", "h4"],
               "rows": [row({"0": [], "1": [c("e1"), c("e2"), c("e3")], "2": [], "3": [c("w1")], "4": []})]}
    leaves = {l["id"]: l for l in _table_leaves(section)}
    edu = leaves["t.row0.col1"]
    assert [r["recordId"] for r in edu["sourceReferences"]] == ["e1", "e2", "e3"] and all(r["collection"] == "educations" for r in edu["sourceReferences"])
    assert edu["sourceReference"]["recordId"] == "e1" and edu["source"] == "mongodb"  # the existing single reference is unchanged
    assert "sourceReferences" not in leaves["t.row0.col3"]  # exactly one record -> nothing new is added
    assert leaves["t.row0.col2"]["source"] == "missing" and "sourceReferences" not in leaves["t.row0.col2"]  # no source -> none invented
    print("test_reference_lists_every_source_record_of_a_multi_record_cell: PASS")


if __name__ == "__main__":
    tests = [test_reference_lists_every_source_record_of_a_multi_record_cell, test_format_no_year_parentheses_kept_plain_numbering, test_only_year_parentheses_are_removed,
             test_confirmed_duplicates_are_merged_but_keep_every_record, test_written_out_representation_of_the_same_education_is_merged_and_both_records_kept, test_distinct_or_unproven_records_are_never_merged,
             test_noise_is_not_displayed_and_order_is_deterministic, test_different_persons_are_never_merged_and_citations_stay_complete,
             test_table_1_2_row_carries_the_new_education_and_all_sources, test_multiline_cell_survives_injection_html_and_edit_roundtrip]
    for t in tests:
        t()
    print(f"\n{len(tests)}/{len(tests)} passed")
