"""Regression tests for change.md's PS Agent deterministic data-aggregation
fix (sec.35 TEST 1-14; TEST 15/16 already live in
test_table_group_injection.py's test_record_fewer_than_blocks_fills_in_
order_leaves_extra_blank / test_record_more_than_blocks_raises).

Pure unit tests - no MongoDB/Chroma/Gemini connection needed, per
change.md sec.35's mocked TEST 11-14.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from criterion_agents.ps_agent.degree_mapping import classify_degree_level, highest_level_among  # noqa: E402
from criterion_agents.ps_agent.field_resolution import resolve_field  # noqa: E402
from criterion_agents.ps_agent.person_aggregation import (  # noqa: E402
    aggregate_curriculum_people,
    table_1_1_members,
    checkbox_state,
)
from criterion_agents.ps_agent.work_aggregation import aggregate_work_counts, categorize_work_type  # noqa: E402
from criterion_agents.ps_agent.year_normalization import normalize_publication_year  # noqa: E402


def _person(pid, first, last, position="ผศ.", title="ดร."):
    return {"_id": pid, "firstName": first, "lastName": last, "academicPosition": position, "title": title,
            "source_filename": f"mongodb:persons:{pid}"}


def _appt(pid, role, status="active", curriculum="C1"):
    return {"personId": pid, "role": role, "status": status, "curriculumId": curriculum}


# ---------- TEST 1/2: role merging ----------

def test_1_multi_role_person_merged_into_one():
    appointments = [_appt("A", "programmeResponsible"), _appt("A", "programmeStaff")]
    persons = [_person("A", "สมชาย", "ใจดี")]
    people = aggregate_curriculum_people(appointments, persons, [], [])
    assert len(people) == 1, f"expected 1 merged person, got {len(people)}"
    assert set(people[0].roles) == {"programmeResponsible", "programmeStaff"}
    print("test_1_multi_role_person_merged_into_one: PASS")


def test_2_staff_only_person():
    appointments = [_appt("B", "programmeStaff")]
    persons = [_person("B", "สมหญิง", "ดีใจ")]
    people = aggregate_curriculum_people(appointments, persons, [], [])
    assert len(people) == 1
    assert people[0].roles == ["programmeStaff"]
    print("test_2_staff_only_person: PASS")


# ---------- TEST 3: Table 1.1 ordering ----------

def test_3_multi_role_first_ordering():
    appointments = [
        _appt("C", "programmeStaff"),
        _appt("D", "programmeStaff"),
        _appt("E", "programmeStaff"),
        _appt("A", "programmeResponsible"), _appt("A", "programmeStaff"),
        _appt("B", "programmeResponsible"), _appt("B", "programmeStaff"),
    ]
    persons = [_person(pid, pid, pid) for pid in ["A", "B", "C", "D", "E"]]
    people = aggregate_curriculum_people(appointments, persons, [], [])
    ids_in_order = [p.person_id for p in people]
    assert ids_in_order == ["A", "B", "C", "D", "E"], f"expected multi-role (A,B) before staff-only (C,D,E), got {ids_in_order}"
    assert not any("A" == pid for pid in ids_in_order[2:]), "must not split A into two rows"
    print("test_3_multi_role_first_ordering: PASS")


# ---------- TEST 4: Table 1.2 checkbox ----------

def test_4_checkbox_both_checked_for_multi_role():
    appointments = [_appt("A", "programmeResponsible"), _appt("A", "programmeStaff")]
    persons = [_person("A", "สมชาย", "ใจดี")]
    people = aggregate_curriculum_people(appointments, persons, [], [])
    state = checkbox_state(people[0])
    assert state == {"programmeResponsible": True, "programmeStaff": True}
    print("test_4_checkbox_both_checked_for_multi_role: PASS (responsible+staff)")


def test_4_checkbox_staff_only():
    appointments = [_appt("B", "programmeStaff")]
    persons = [_person("B", "สมหญิง", "ดีใจ")]
    people = aggregate_curriculum_people(appointments, persons, [], [])
    state = checkbox_state(people[0])
    assert state == {"programmeResponsible": False, "programmeStaff": True}
    print("test_4_checkbox_staff_only: PASS (staff only)")


def test_4_table_1_1_sections_come_from_roles():
    appointments = [_appt("A", "programmeResponsible"), _appt("A", "programmeStaff"), _appt("B", "programmeStaff")]
    persons = [_person("A", "x", "y"), _person("B", "x", "y")]
    people = aggregate_curriculum_people(appointments, persons, [], [])
    assert [p.person_id for p in table_1_1_members(people, "programmeResponsible")] == ["A"]
    assert [p.person_id for p in table_1_1_members(people, "programmeStaff")] == ["A", "B"]  # A holds both roles: in both sections, first in staff
    print("test_4_table_1_1_sections_come_from_roles: PASS")


# ---------- TEST 5/6: highest education level vs degree name ----------

def test_5_abbreviation_to_level():
    assert classify_degree_level("ปร.ด.") == "ปริญญาเอก"
    assert classify_degree_level("Ph.D.") == "ปริญญาเอก"
    assert classify_degree_level("วท.ม.") == "ปริญญาโท"
    assert classify_degree_level("วท.บ.") == "ปริญญาตรี"
    assert classify_degree_level("บธ.บ.") == "ปริญญาตรี"
    print("test_5_abbreviation_to_level: PASS")


def test_6_full_name_to_level_kept_separate_from_degree_name():
    level = classify_degree_level("ปรัชญาดุษฎีบัณฑิต")
    assert level == "ปริญญาเอก", f"expected ปริญญาเอก, got {level}"
    # highest_education_level must be the LEVEL, never the degree name itself
    assert level != "ปรัชญาดุษฎีบัณฑิต"
    assert classify_degree_level("วิทยาศาสตรมหาบัณฑิต") == "ปริญญาโท"
    assert classify_degree_level("วิทยาศาสตรบัณฑิต") == "ปริญญาตรี"
    print("test_6_full_name_to_level_kept_separate_from_degree_name: PASS")


def test_thai_abbreviation_missing_final_dot():
    # real aunqa_ps values found by the real-data audit ("วท.บ", "สท.บ" - no trailing dot)
    assert classify_degree_level("วท.บ") == "ปริญญาตรี"
    assert classify_degree_level("สท.บ") == "ปริญญาตรี"
    assert classify_degree_level("วท. ม") == "ปริญญาโท"
    assert classify_degree_level("ปร.ด") == "ปริญญาเอก"
    # ...but only that exact abbreviation shape: ordinary text ending in บ/ม/ด is NOT a degree
    assert classify_degree_level("ระบบ") is None
    assert classify_degree_level("การจัดการเทคโนโลยีสารสนเทศ ม") is None
    assert classify_degree_level("at") is None
    print("test_thai_abbreviation_missing_final_dot: PASS")


def test_highest_level_among_picks_max_not_first():
    # Bachelor's listed first, doctorate second - must still return เอก.
    level = highest_level_among(["วท.บ.", "ปร.ด.", "วท.ม."])
    assert level == "ปริญญาเอก", f"expected MAX(level)=ปริญญาเอก regardless of order, got {level}"
    print("test_highest_level_among_picks_max_not_first: PASS")


def test_unrecognized_degree_is_not_guessed():
    assert classify_degree_level("???") is None
    assert classify_degree_level("") is None
    assert classify_degree_level(None) is None
    print("test_unrecognized_degree_is_not_guessed: PASS")


# ---------- TEST 7: name duplication ----------

def test_7_display_name_no_title_duplication():
    appointments = [_appt("A", "programmeStaff")]
    persons = [{"_id": "A", "firstName": "X", "lastName": "Y", "academicPosition": "ผศ.", "title": "ดร.",
                "fullName": "ผศ. ดร. X Y", "source_filename": "mongodb:persons:A"}]
    people = aggregate_curriculum_people(appointments, persons, [], [])
    name = people[0].display_name
    assert name == "ดร.X Y", f"expected 'ดร.X Y', got {name!r}"
    assert "ผศ." not in name, f"academic position must not leak into the name field, got {name!r}"
    assert name.count("ดร.") == 1, f"title must not be duplicated, got {name!r}"
    print("test_7_display_name_no_title_duplication: PASS")


def test_7_display_name_no_title_when_absent():
    appointments = [_appt("C", "programmeStaff")]
    persons = [{"_id": "C", "firstName": "เจริญพร", "lastName": "บัวแย้ม", "academicPosition": "ผศ.", "title": "",
                "source_filename": "mongodb:persons:C"}]
    people = aggregate_curriculum_people(appointments, persons, [], [])
    assert people[0].display_name == "เจริญพร บัวแย้ม"
    print("test_7_display_name_no_title_when_absent: PASS")


# ---------- TEST 8: year normalization ----------

def test_8_year_normalization():
    assert normalize_publication_year(2022) == 2565
    assert normalize_publication_year(2565) == 2565
    assert normalize_publication_year(2023) == 2566
    assert normalize_publication_year(2566) == 2566
    print("test_8_year_normalization: PASS")


# ---------- TEST 9: academic/creative work count ----------

def test_9_academic_and_creative_counts():
    works = [
        {"workType": "Journal", "publicationYear": 2565},
        {"workType": "Conference", "publicationYear": 2565},
        {"workType": "Creative Work", "publicationYear": 2565},
    ]
    counts = aggregate_work_counts(works, [2565])
    assert counts[2565]["academic"] == 2, counts
    assert counts[2565]["creative"] == 1, counts
    print("test_9_academic_and_creative_counts: PASS")


def test_9_unsupported_work_type_not_guess_counted():
    works = [{"workType": "Patent", "publicationYear": 2565}]  # not in the recognized set
    counts = aggregate_work_counts(works, [2565])
    assert counts[2565] == {"academic": 0, "creative": 0}
    assert categorize_work_type("Patent") is None
    print("test_9_unsupported_work_type_not_guess_counted: PASS")


# ---------- TEST 10: graduationYear must never be used as publicationYear ----------

def test_10_graduation_year_never_used_as_publication_year():
    # A work record with only graduationYear (no publicationYear) must be
    # skipped, not silently counted using the wrong field.
    works = [{"workType": "Journal", "graduationYear": 2565}]
    counts = aggregate_work_counts(works, [2565])
    assert counts[2565] == {"academic": 0, "creative": 0}, "graduationYear must never substitute for publicationYear"
    print("test_10_graduation_year_never_used_as_publication_year: PASS")


# ---------- TEST 11-14: per-field Chroma/Mongo fallback ladder (mocked) ----------

def test_11_chroma_sufficient_takes_priority_over_mongo():
    def evidence_supports_field(hits, field):
        return True, {"value": "ปริญญาเอก", "source_reference": {"source_filename": "chroma:doc1", "chunk_index": 0}}

    def mongo_value_fn():
        return "ปริญญาโท", {"collection": "educations", "document_id": "x"}  # deliberately different, must NOT be used

    resolution = resolve_field("highest_education_level", [{"text": "..."}], evidence_supports_field, mongo_value_fn)
    assert resolution.source == "chroma"
    assert resolution.value == "ปริญญาเอก"
    print("test_11_chroma_sufficient_takes_priority_over_mongo: PASS")


def test_12_mongo_fallback_when_chroma_insufficient():
    def evidence_supports_field(hits, field):
        return False, None

    def mongo_value_fn():
        return "ปริญญาโท", {"collection": "educations", "document_id": "x"}

    resolution = resolve_field("highest_education_level", [{"text": "irrelevant chunk"}], evidence_supports_field, mongo_value_fn)
    assert resolution.source == "mongodb"
    assert resolution.value == "ปริญญาโท"
    print("test_12_mongo_fallback_when_chroma_insufficient: PASS")


def test_13_per_field_independent_fallback():
    # highest_education_level: chroma found; degree_name: chroma missing, mongo found
    def edu_level_evidence(hits, field):
        return True, {"value": "ปริญญาเอก", "source_reference": {"source_filename": "chroma:doc1", "chunk_index": 0}}

    def degree_name_evidence(hits, field):
        return False, None

    level_resolution = resolve_field("highest_education_level", [{}], edu_level_evidence, lambda: ("SHOULD_NOT_BE_USED", {}))
    degree_resolution = resolve_field("degree_name", [{}], degree_name_evidence, lambda: ("ปร.ด. วิทยาการคอมพิวเตอร์", {"collection": "educations", "document_id": "x"}))

    assert level_resolution.source == "chroma"
    assert degree_resolution.source == "mongodb"
    print("test_13_per_field_independent_fallback: PASS")


def test_14_chroma_chunks_without_relevant_evidence_not_considered_found():
    def evidence_supports_field(hits, field):
        # Genuine evaluation: chunks exist but mention nothing about this field.
        return False, None

    def mongo_value_fn():
        return "ปริญญาตรี", {"collection": "educations", "document_id": "y"}

    resolution = resolve_field(
        "highest_education_level",
        [{"text": "เอกสารนี้กล่าวถึงชื่อบุคคลเท่านั้น ไม่มีข้อมูลวุฒิการศึกษา"}],
        evidence_supports_field,
        mongo_value_fn,
    )
    assert resolution.source == "mongodb", "chunks present but irrelevant must NOT count as 'found'"
    print("test_14_chroma_chunks_without_relevant_evidence_not_considered_found: PASS")


def test_missing_when_no_tier_has_data():
    resolution = resolve_field("degree_name", [], lambda h, f: (False, None), lambda: None)
    assert resolution.source == "missing"
    assert resolution.value is None
    print("test_missing_when_no_tier_has_data: PASS")


def test_person_without_matching_persons_record_is_skipped_not_fabricated():
    appointments = [_appt("GHOST", "programmeStaff")]
    people = aggregate_curriculum_people(appointments, [], [], [])  # no persons records at all
    assert people == [], "a personId with no matching persons record must be skipped, never fabricated"
    print("test_person_without_matching_persons_record_is_skipped_not_fabricated: PASS")


def main() -> int:
    tests = [
        test_1_multi_role_person_merged_into_one,
        test_2_staff_only_person,
        test_3_multi_role_first_ordering,
        test_4_checkbox_both_checked_for_multi_role,
        test_4_checkbox_staff_only,
        test_4_table_1_1_sections_come_from_roles,
        test_5_abbreviation_to_level,
        test_6_full_name_to_level_kept_separate_from_degree_name,
        test_thai_abbreviation_missing_final_dot,
        test_highest_level_among_picks_max_not_first,
        test_unrecognized_degree_is_not_guessed,
        test_7_display_name_no_title_duplication,
        test_7_display_name_no_title_when_absent,
        test_8_year_normalization,
        test_9_academic_and_creative_counts,
        test_9_unsupported_work_type_not_guess_counted,
        test_10_graduation_year_never_used_as_publication_year,
        test_11_chroma_sufficient_takes_priority_over_mongo,
        test_12_mongo_fallback_when_chroma_insufficient,
        test_13_per_field_independent_fallback,
        test_14_chroma_chunks_without_relevant_evidence_not_considered_found,
        test_missing_when_no_tier_has_data,
        test_person_without_matching_persons_record_is_skipped_not_fabricated,
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
