"""Table 1.2 year + per-year work-count tests (deterministic - no LLM, no DOCX).

Part 1 - pure unit tests of the Generator's own aggregation with hand-built
records (year mapping, zero / non-zero counts, duplicates, person mapping,
unsupported work types, out-of-window years).

Part 2 - LIVE cross-check against the REAL MongoDB (READ-ONLY): for all 13
appointed persons x the 5 fixed years = 65 cells, the Generator's aggregation
(retrieval.mongodb.fetch_curriculum_people_raw -> aggregate_curriculum_people ->
aggregate_work_counts) must equal an INDEPENDENT live query written here:
    academic_works.count_documents({personId, publicationYear: {$in: [Y, Y-543]}, workType: ...})
Expected values are never edited to make this pass - a mismatch is a real bug.

The end-to-end DOCX-level 65-cell audit (Mongo -> agent -> slot_map -> DOCX ->
cited sources) is scripts/audit_table_1_2.py, run by scripts/real_generate.py.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import ObjectId  # noqa: E402

from common.mongo import get_db  # noqa: E402
from criterion_agents.ps_agent.agent import FIVE_YEAR_RANGE  # noqa: E402
from criterion_agents.ps_agent.person_aggregation import aggregate_curriculum_people  # noqa: E402
from criterion_agents.ps_agent.work_aggregation import aggregate_work_counts  # noqa: E402
from criterion_agents.ps_agent.year_normalization import normalize_publication_year  # noqa: E402
from retrieval.mongodb import fetch_curriculum_people_raw  # noqa: E402

passed = 0


def ok(name: str) -> None:
    global passed
    passed += 1
    print(f"TEST {name}: OK", flush=True)


def W(year, work_type="Journal", person="A"):
    return {"personId": person, "publicationYear": year, "workType": work_type}


def unit_tests() -> None:
    # 1. year mapping: Gregorian -> BE exactly once, BE untouched
    assert FIVE_YEAR_RANGE == [2565, 2566, 2567, 2568, 2569]  # change.md sec.19 (user-specified, static)
    assert [normalize_publication_year(y) for y in (2022, 2023, 2024, 2025, 2026)] == [2565, 2566, 2567, 2568, 2569]
    assert [normalize_publication_year(y) for y in (2565, 2566, 2567, 2568, 2569)] == [2565, 2566, 2567, 2568, 2569]
    assert normalize_publication_year(2399) == 2942 and normalize_publication_year(2400) == 2400  # documented threshold
    ok("1  year mapping: 2022-2026 -> 2565-2569 (+543 once); 2565-2569 unchanged (never +543 twice)")

    # 2/3/4. counts per year: zero and non-zero, mixed Gregorian+BE in the same year add up
    counts = aggregate_work_counts([W(2565), W(2565), W(2022), W(2567, "Conference"), W(2569)], FIVE_YEAR_RANGE)
    assert counts[2565] == {"academic": 3, "creative": 0}, counts  # 2 BE + 1 Gregorian(2022)
    assert counts[2566] == {"academic": 0, "creative": 0}, counts  # zero stays zero
    assert counts[2567] == {"academic": 1, "creative": 0} and counts[2569]["academic"] == 1
    ok("2  count per year (mixed BE + Gregorian in one year summed) / 3 zero count / 4 non-zero count")

    # 5. no de-duplication: two identical source records are two works (Generator shows the Source as-is)
    assert aggregate_work_counts([W(2566), W(2566)], FIVE_YEAR_RANGE)[2566]["academic"] == 2
    ok("5  duplicate handling: identical records are NOT silently merged (Generator displays Source)")

    # 6. out-of-window years and unsupported workType are not counted (never guessed into a category)
    counts = aggregate_work_counts([W(2564), W(2562), W(2570), W(2566, "Poster"), W(2566, None), W(2566, "Creative Work")], FIVE_YEAR_RANGE)
    assert sum(c["academic"] for c in counts.values()) == 0 and counts[2566]["creative"] == 1
    ok("6  years outside 2565-2569 and unsupported workType are not counted; 'Creative Work' -> creative")

    # 7. person mapping is by personId, never by name
    raw_persons = [
        {"_id": "P1", "firstName": "สมชาย", "lastName": "ใจดี", "academicPosition": "ผศ.", "title": "", "source_filename": "mongodb:persons:P1"},
        {"_id": "P2", "firstName": "สมชาย", "lastName": "ใจดี", "academicPosition": "รศ.", "title": "", "source_filename": "mongodb:persons:P2"},  # same NAME
    ]
    appts = [{"personId": "P1", "role": "programmeStaff", "status": "active"}, {"personId": "P2", "role": "programmeStaff", "status": "active"}]
    works = [{**W(2566, person="P1"), "source_filename": "w1"}, {**W(2566, person="P2"), "source_filename": "w2"},
             {**W(2567, person="P2"), "source_filename": "w3"}, {**W(2566, person="P3-not-appointed"), "source_filename": "w4"}]
    people = {p.person_id: p for p in aggregate_curriculum_people(appts, raw_persons, [], works)}
    assert len(people) == 2
    assert [w["source_filename"] for w in people["P1"].academic_works] == ["w1"]
    assert sorted(w["source_filename"] for w in people["P2"].academic_works) == ["w2", "w3"]
    ok("7  person mapping by personId: same-name persons keep their own works; non-appointed person's works never attach")


async def live_65_cells() -> None:
    db = get_db()  # READ-ONLY: find / count_documents only
    raw = await fetch_curriculum_people_raw()
    people = aggregate_curriculum_people(raw["appointments"], raw["persons"], raw["educations"], raw["academic_works"])
    assert len(people) == 13, f"expected 13 appointed people, got {len(people)}"

    cells = mismatches = 0
    zero_cells = nonzero_cells = 0
    for person in people:
        gen = aggregate_work_counts(person.academic_works, FIVE_YEAR_RANGE)
        oid = ObjectId(person.person_id)
        for year in FIVE_YEAR_RANGE:
            base = {"personId": oid, "publicationYear": {"$in": [year, year - 543]}}
            m_acad = await db["academic_works"].count_documents({**base, "workType": {"$in": ["Journal", "Conference"]}})
            m_creat = await db["academic_works"].count_documents({**base, "workType": "Creative Work"})
            cells += 1
            if (gen[year]["academic"], gen[year]["creative"]) != (m_acad, m_creat):
                mismatches += 1
                print(f"   MISMATCH {person.display_name} {year}: generator={gen[year]} mongo=({m_acad},{m_creat})")
            zero_cells += (m_acad == 0)
            nonzero_cells += (m_acad > 0)
    assert cells == 65, cells
    assert mismatches == 0, f"{mismatches}/65 cells differ from live MongoDB"
    assert zero_cells > 0 and nonzero_cells > 0  # both cases really exercised by the real data
    ok(f"8  LIVE 13 persons x 5 years = {cells} cells equal independent MongoDB queries ({nonzero_cells} non-zero, {zero_cells} zero academic cells)")

    total = sum(aggregate_work_counts(p.academic_works, FIVE_YEAR_RANGE)[y]["academic"] for p in people for y in FIVE_YEAR_RANGE)
    in_window = 0
    async for w in db["academic_works"].find({"personId": {"$in": [ObjectId(p.person_id) for p in people]}}, {"publicationYear": 1}):
        y = w["publicationYear"]
        in_window += (y in FIVE_YEAR_RANGE) or (y + 543 in FIVE_YEAR_RANGE)
    assert total == in_window, (total, in_window)
    ok(f"9  cross-total: table sum ({total}) == appointed persons' works whose year falls in 2565-2569 ({in_window})")


if __name__ == "__main__":
    unit_tests()
    asyncio.run(live_65_cells())
    print(f"\nALL {passed} Table 1.2 count checks passed (live part is READ-ONLY)")
