"""Table 1.1 sections + Table 1.2 checkboxes come from the REAL appointments (deterministic; no DB, no LLM).

  5  programmeResponsible is derived from appointments (nothing from names / positions / fetch order)
  6  a person holding both roles is placed first in the programmeStaff section (and stays in the responsible one)
  7  nothing hardcodes "5" (or any head-count / list of names): the numbers follow the data
  8  the Table 1.2 role checkboxes come from appointments
  9  an inactive appointment (or one of another curriculum) does not determine the current role
  + live: the REAL MongoDB gives 5 responsible / 13 staff with the 5 dual-role people first (read-only)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.schemas import TargetSlot  # noqa: E402
from criterion_agents.ps_agent.agent import ROLE_CODE_TO_LABEL, _build_table_1_1, _build_table_1_2  # noqa: E402
from criterion_agents.ps_agent.person_aggregation import (  # noqa: E402
    ROLE_RESPONSIBLE,
    ROLE_STAFF,
    aggregate_curriculum_people,
    checkbox_state,
    table_1_1_members,
)

GA, GB = ROLE_CODE_TO_LABEL[ROLE_RESPONSIBLE], ROLE_CODE_TO_LABEL[ROLE_STAFF]
H11 = ["ตำแหน่งทางวิชาการ", "ชื่อ-นามสกุล", "วุฒิการศึกษาสูงสุด", "ชื่อปริญญา (สาขาวิชา)"]
CUR = "CUR1"


def person(pid, first="ก", position="ผศ."):
    return {"_id": pid, "firstName": first, "lastName": pid, "academicPosition": position, "title": "ดร.", "source_filename": f"mongodb:persons:{pid}"}


def appt(pid, role, status="active", curriculum=CUR):
    return {"personId": pid, "role": role, "status": status, "curriculumId": curriculum}


def sections(people):
    return {role: [p.person_id for p in table_1_1_members(people, role)] for role in (ROLE_RESPONSIBLE, ROLE_STAFF)}


def scenario(n_responsible, n_staff_only, ids_first=True):
    """n_responsible people hold BOTH roles, n_staff_only hold staff only. Ids are chosen so that the fetch order
    and the alphabetical order of the ids disagree with the role structure."""
    dual = [f"D{i:02d}" for i in range(n_responsible)]
    only = [f"A{i:02d}" for i in range(n_staff_only)]  # sort BEFORE the dual ids by id and appear FIRST in the fetch order
    appts = [appt(i, ROLE_STAFF) for i in only] + [a for i in dual for a in (appt(i, ROLE_RESPONSIBLE), appt(i, ROLE_STAFF))]
    return dual, only, aggregate_curriculum_people(appts, [person(i) for i in dual + only], [], [], curriculum_id=CUR)


def test_5_and_6_responsible_derived_from_appointments_dual_role_first_in_staff():
    dual, only, people = scenario(3, 4)
    s = sections(people)
    assert s[ROLE_RESPONSIBLE] == dual, s                       # exactly the people holding programmeResponsible
    assert s[ROLE_STAFF] == dual + only, s                      # dual-role first, then the staff-only ones
    assert not set(only) & set(s[ROLE_RESPONSIBLE])
    print("test_5_and_6_responsible_derived_from_appointments_dual_role_first_in_staff: PASS")


def test_7_no_hardcoded_count_or_names():
    for n_resp, n_only in [(0, 3), (1, 0), (2, 7), (4, 9), (5, 8), (6, 1)]:
        dual, only, people = scenario(n_resp, n_only)
        s = sections(people)
        assert s[ROLE_RESPONSIBLE] == dual and s[ROLE_STAFF] == dual + only, (n_resp, n_only)
        slot = TargetSlot(slot_id="table_ps_1_1", type="table", criterion="PS", headers=H11, groups=[GA, GB])
        rows = _build_table_1_1(slot, people, {}).rows
        assert [r.group for r in rows].count(GA) == n_resp and [r.group for r in rows].count(GB) == n_resp + n_only
        staff_numbers = [int(r.values[0].split(".")[0]) for r in rows if r.group == GB]
        assert staff_numbers == list(range(1, n_resp + n_only + 1))  # numbering restarts per section and follows the real count
    # a responsible-only person (no staff appointment) is listed in the responsible section only
    people = aggregate_curriculum_people([appt("R", ROLE_RESPONSIBLE), appt("S", ROLE_STAFF)], [person("R"), person("S")], [], [], curriculum_id=CUR)
    assert sections(people) == {ROLE_RESPONSIBLE: ["R"], ROLE_STAFF: ["S"]}
    import inspect

    from criterion_agents.ps_agent import agent, person_aggregation
    src = inspect.getsource(agent._build_table_1_1) + inspect.getsource(person_aggregation.table_1_1_members)
    assert not any(tok in src for tok in (" 5", "[:5]", "range(5)", "== 5", "พีรวิชญ์", "สุภาภรณ์", "กาญจนา"))
    print("test_7_no_hardcoded_count_or_names: PASS")


def test_8_role_checkbox_comes_from_appointments():
    people = {p.person_id: p for p in aggregate_curriculum_people(
        [appt("B", ROLE_RESPONSIBLE), appt("B", ROLE_STAFF), appt("S", ROLE_STAFF), appt("R", ROLE_RESPONSIBLE)],
        [person("B"), person("S"), person("R")], [], [], curriculum_id=CUR)}
    assert checkbox_state(people["B"]) == {ROLE_RESPONSIBLE: True, ROLE_STAFF: True}
    assert checkbox_state(people["S"]) == {ROLE_RESPONSIBLE: False, ROLE_STAFF: True}
    assert checkbox_state(people["R"]) == {ROLE_RESPONSIBLE: True, ROLE_STAFF: False}
    # and the rendered Table 1.2 row carries exactly those checked options (position/name never decide it)
    slot = TargetSlot(slot_id="t", type="table", criterion="PS", headers=list("abcde"), rows_per_record=5)
    rows = _build_table_1_2(slot, list(people.values())).rows
    checked = {r.record_key: r.checked_options for r in rows}
    assert checked["B"] == [GA, GB] or sorted(checked["B"]) == sorted([GA, GB])
    assert checked["S"] == [GB] and checked["R"] == [GA]
    print("test_8_role_checkbox_comes_from_appointments: PASS")


def test_9_inactive_or_other_curriculum_appointments_do_not_decide_the_role():
    appts = [appt("P", ROLE_STAFF), appt("P", ROLE_RESPONSIBLE, status="inactive"),       # responsible role ended
             appt("Q", ROLE_STAFF, status="ended"),                                       # nothing current at all
             appt("O", ROLE_STAFF, curriculum="OTHER"), appt("O", ROLE_RESPONSIBLE, curriculum="OTHER"),  # another curriculum
             appt("N", ROLE_STAFF), {"personId": "N", "role": ROLE_RESPONSIBLE}]          # a record with no status is not "active"
    people = {p.person_id: p for p in aggregate_curriculum_people(appts, [person(i) for i in "PQON"], [], [], curriculum_id=CUR)}
    assert set(people) == {"P", "N"}, set(people)  # Q and O have no current appointment -> not listed at all
    assert people["P"].roles == [ROLE_STAFF] and people["N"].roles == [ROLE_STAFF]
    assert checkbox_state(people["P"]) == {ROLE_RESPONSIBLE: False, ROLE_STAFF: True}
    assert sections(list(people.values())) == {ROLE_RESPONSIBLE: [], ROLE_STAFF: ["N", "P"]}
    # same data without the curriculum filter still ignores the inactive/ended/status-less records
    loose = {p.person_id: p for p in aggregate_curriculum_people(appts, [person(i) for i in "PQON"], [], [])}
    assert set(loose) == {"P", "O", "N"} and loose["P"].roles == [ROLE_STAFF]
    print("test_9_inactive_or_other_curriculum_appointments_do_not_decide_the_role: PASS")


async def live_real_mongo() -> None:
    from common.mongo import get_db
    from retrieval.mongodb import fetch_curriculum_people_raw

    db = get_db()  # READ-ONLY
    raw = await fetch_curriculum_people_raw()
    cur = str((await db["curricula"].find_one({}, {"_id": 1}))["_id"])
    people = aggregate_curriculum_people(raw["appointments"], raw["persons"], raw["educations"], raw["academic_works"], curriculum_id=cur)
    truth_resp = {str(a["personId"]) async for a in db["appointments"].find({"role": ROLE_RESPONSIBLE, "status": "active"})}
    truth_staff = {str(a["personId"]) async for a in db["appointments"].find({"role": ROLE_STAFF, "status": "active"})}
    s = sections(people)
    assert set(s[ROLE_RESPONSIBLE]) == truth_resp and set(s[ROLE_STAFF]) == truth_staff
    dual = truth_resp & truth_staff
    assert set(s[ROLE_STAFF][: len(dual)]) == dual and not set(s[ROLE_STAFF][len(dual):]) & truth_resp  # dual-role people first, then the rest
    print(f"live: responsible={len(s[ROLE_RESPONSIBLE])} staff={len(s[ROLE_STAFF])} (dual-role first: {len(dual)}) - all derived from the real appointments")
    print("test_live_real_mongo_roles: PASS")


if __name__ == "__main__":
    for t in (test_5_and_6_responsible_derived_from_appointments_dual_role_first_in_staff, test_7_no_hardcoded_count_or_names,
              test_8_role_checkbox_comes_from_appointments, test_9_inactive_or_other_curriculum_appointments_do_not_decide_the_role):
        t()
    asyncio.run(live_real_mongo())
    print("\n5/5 passed (live part is READ-ONLY)")
