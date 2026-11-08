"""FULL audit of Table 1.2 "ปี พ.ศ." + "จำนวนผลงานรายปี" against the REAL MongoDB
(13 appointed persons x 5 years = 65 rows, 3 numbers each = 195 values).

Chain verified for every row:
    Mongo (live query, READ-ONLY)  ->  agent result (generation_criteria_log.sections)
      ->  slot_map (physical DOCX row)  ->  the cell physically in the DOCX
      ->  Reference / column_citations (source records behind the count)

Independence: the expected numbers are obtained by running a REAL MongoDB
query per (person, year) written here from scratch:
    academic_works.find({personId: <ObjectId>, publicationYear: {$in: [Y, Y-543]}})
(Y = Buddhist-Era year; Y-543 = the same year in the Gregorian convention that
some source records use). It does NOT import the Generator's year
normalization, person aggregation or work aggregation - so a bug there cannot
hide itself. Person identity comes from the agent row's record_key (personId),
and is cross-checked against the name printed in the DOCX.

Usage:  python scripts/audit_table_1_2.py output/audit/raw_<run_id>.json
        (raw dump written by scripts/real_generate.py; the DB is only READ)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import docx
from bson import ObjectId

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from master_agent.docx_utils import iter_block_items  # noqa: E402  (generic body traversal only)

YEARS = [2565, 2566, 2567, 2568, 2569]  # change.md sec.19: user-specified fixed range
SUPPORTED_ACADEMIC = ["Journal", "Conference"]
SUPPORTED_CREATIVE = ["Creative Work"]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _bare_name(person) -> str:
    """Independent rule (NOT the Generator's): first + last name with any leading rank/title already written in it removed
    (the dot is required, so names such as "ศิริรัตน์"/"อรุณ" are safe)."""
    return re.sub(r"^(?:\s*(?:ศ|รศ|ผศ|อ|ดร)\.)+\s*", "", f"{person.get('firstName')} {person.get('lastName')}").strip()


def expected_identity(person) -> str:
    """Table 1.2 identity WITHOUT the number: <position abbreviation from source><ดร. if title is ดร.><name>."""
    doctor = "ดร." if (person.get("title") or "").strip() == "ดร." else ""
    return f"{(person.get('academicPosition') or '').strip()}{doctor}{_bare_name(person)}"


def _unique_cells(row):
    seen, out = set(), []
    for c in row.cells:
        if id(c._tc) not in seen:
            seen.add(id(c._tc))
            out.append(c)
    return out


async def audit(db, docx_path, slot_map, criteria_logs) -> dict:
    document = docx.Document(str(docx_path))
    sections = {s["slot_id"]: s for c in criteria_logs for s in c.get("sections", [])}
    section = sections["table_ps_1_2"]
    block = next(int(b) for b, i in slot_map["tables"].items() if i["slotId"] == "table_ps_1_2")
    rows_map = {int(r): k for r, k in slot_map["tables"][str(block)]["rows"].items()}  # physical row -> agent row idx
    table = next(t for i, t in enumerate(iter_block_items(document)) if i == block)

    persons = {p["_id"]: p async for p in db["persons"].find({})}
    name_counts = Counter(_norm(expected_identity(p)) for p in persons.values())

    rows_out, findings = [], []
    record_number: dict[str, int] = {}  # personId -> 1-based record order, by first appearance top to bottom
    for phys_row in sorted(rows_map):
        agent_idx = rows_map[phys_row]
        agent = section["rows"][agent_idx]
        pid = agent["record_key"]
        person = persons.get(ObjectId(pid))
        docx_row = table.rows[phys_row]
        docx_name = _norm(docx_row.cells[0].text.split("\n")[0])
        k = record_number.setdefault(pid, len(record_number) + 1)
        cells = [_norm(c.text) for c in _unique_cells(docx_row)]
        docx_year, docx_acad, docx_creat = cells[-3], cells[-2], cells[-1]
        a_year, a_acad, a_creat = agent["values"][2], agent["values"][3], agent["values"][4]
        Y = int(a_year)
        oid = ObjectId(pid)

        # ---- REAL Mongo queries (independent formulation) ----
        year_filter = {"$in": [Y, Y - 543]}
        base = {"personId": oid, "publicationYear": year_filter}
        matching = [w async for w in db["academic_works"].find(base, {"publicationYear": 1, "workType": 1, "title": 1})]
        m_acad = await db["academic_works"].count_documents({**base, "workType": {"$in": SUPPORTED_ACADEMIC}})
        m_creat = await db["academic_works"].count_documents({**base, "workType": {"$in": SUPPORTED_CREATIVE}})
        unsupported = len(matching) - m_acad - m_creat
        acad_ids = sorted(str(w["_id"]) for w in matching if w["workType"] in SUPPORTED_ACADEMIC)
        creat_ids = sorted(str(w["_id"]) for w in matching if w["workType"] in SUPPORTED_CREATIVE)

        # ---- name <-> personId consistency + the new display format "N. <position><title><name>" ----
        expected_name = None
        if person is not None:
            expected_name = f"{k}. {_norm(expected_identity(person))}"
        name_ok = person is not None and docx_name == expected_name and name_counts[_norm(expected_identity(person))] == 1

        # ---- cited sources (column_citations) vs the Mongo records ----
        def cited(col):
            return sorted(c["source_filename"].split(":", 2)[2] for c in (agent.get("column_citations") or {}).get(str(col), [])
                          if c["source_filename"].startswith("mongodb:academic_works:"))

        cite_acad, cite_creat = cited(3), cited(4)
        year_cites = (agent.get("column_citations") or {}).get("2", None)

        year_ok = docx_year == a_year == str(Y)
        count_ok = (str(m_acad), str(m_creat)) == (a_acad, a_creat) == (docx_acad, docx_creat)
        source_ok = cite_acad == acad_ids and cite_creat == creat_ids
        static_year_ok = year_cites == []  # a fixed window is not sourced data: no citation may be attached
        ok = year_ok and count_ok and source_ok and static_year_ok and name_ok and unsupported == 0

        person_total = await db["academic_works"].count_documents({"personId": oid})
        hist = Counter()
        async for w in db["academic_works"].find({"personId": oid}, {"publicationYear": 1}):
            hist[w["publicationYear"]] += 1

        why_zero = None
        if m_acad == 0 or m_creat == 0:
            why_zero = (f"academic_works.find({{personId: ObjectId('{pid}'), publicationYear: {{$in: [{Y}, {Y - 543}]}}}}) -> "
                        f"{len(matching)} record(s) [academic={m_acad}, creative={m_creat}, unsupported-type={unsupported}]; "
                        f"person has {person_total} work(s) in total, raw publicationYear histogram={dict(sorted(hist.items()))}")
        row = {
            "person": docx_name, "expectedIdentity": expected_name, "recordNumber": k, "personId": pid, "year": Y, "physicalRow": phys_row, "agentRow": agent_idx,
            "mongo": {"academic": m_acad, "creative": m_creat, "matchingRecords": len(matching),
                      "rawYearsMatched": sorted({w["publicationYear"] for w in matching}), "unsupportedTypeRecords": unsupported},
            "agent": {"year": a_year, "academic": a_acad, "creative": a_creat},
            "docx": {"year": docx_year, "academic": docx_acad, "creative": docx_creat},
            "citations": {"academic_cited": len(cite_acad), "creative_cited": len(cite_creat), "year_cited": year_cites},
            "checks": {"year": year_ok, "count": count_ok, "source_records_exact": source_ok, "year_has_no_source": static_year_ok, "person_mapping": name_ok},
            "result": "PASS" if ok else "FAIL",
        }
        if why_zero:
            row["zero_explanation"] = why_zero
        rows_out.append(row)
        if not ok:
            findings.append(row)

    # ---- completeness: 13 appointed persons x 5 years, each exactly once, order most-recent-first ----
    appt_persons = {str(a["personId"]) async for a in db["appointments"].find({}, {"personId": 1})}
    got = defaultdict(list)
    for r in rows_out:
        got[r["personId"]].append(r["year"])
    complete = set(got) == appt_persons and all(sorted(y) == YEARS and y == sorted(y, reverse=True) for y in got.values())

    # ---- duplicates / data-quality observations (reported, never altered) ----
    works = [w async for w in db["academic_works"].find({})]
    exact = Counter((str(w["personId"]), _norm(w["title"]).lower(), w["publicationYear"]) for w in works)
    same_title = defaultdict(list)
    for w in works:
        same_title[(str(w["personId"]), _norm(w["title"]).lower())].append(w["publicationYear"])
    appointed_oids = {ObjectId(p) for p in appt_persons}
    outside_window = sum(1 for w in works if w["personId"] in appointed_oids and (w["publicationYear"] + (543 if w["publicationYear"] < 2400 else 0)) not in YEARS)
    observations = {
        "academic_works_total": len(works),
        "works_of_appointed_persons": sum(1 for w in works if w["personId"] in appointed_oids),
        "works_of_appointed_persons_outside_2565_2569_not_counted": outside_window,
        "works_of_non_appointed_persons_excluded": sum(1 for w in works if w["personId"] not in appointed_oids),
        "exact_duplicate_records": [k for k, c in exact.items() if c > 1],
        "same_person_same_title_different_years": {f"{k[0]}|{k[1][:40]}": v for k, v in same_title.items() if len(v) > 1},
        "publicationYear_raw_values": dict(sorted(Counter(w["publicationYear"] for w in works).items())),
        "gregorian_records_converted_to_BE": sum(1 for w in works if w["publicationYear"] < 2400),
        "workType_values": dict(Counter(w["workType"] for w in works)),
    }
    totals = {"rows": len(rows_out), "PASS": sum(1 for r in rows_out if r["result"] == "PASS"), "FAIL": len(findings),
              "persons": len(got), "complete_13x5": complete,
              "numbering_1_to_n": sorted(record_number.values()) == list(range(1, len(record_number) + 1)),
              "values_checked": len(rows_out) * 3}
    return {"totals": totals, "rows": rows_out, "findings": findings, "observations": observations}


def render(result: dict) -> str:
    lines = ["Person | Year | Mongo(acad/creat) | Agent | DOCX | cited src | Result"]
    for r in result["rows"]:
        lines.append(f"{r['person']:<28} | {r['year']} | {r['mongo']['academic']}/{r['mongo']['creative']} (raw {r['mongo']['rawYearsMatched']}) | "
                     f"{r['agent']['academic']}/{r['agent']['creative']} | {r['docx']['academic']}/{r['docx']['creative']} | "
                     f"{r['citations']['academic_cited']}/{r['citations']['creative_cited']} | {r['result']}")
    return "\n".join(lines)


if __name__ == "__main__":
    import asyncio

    from motor.motor_asyncio import AsyncIOMotorClient

    from common.config import Settings

    raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    st = Settings()

    async def _main():
        client = AsyncIOMotorClient(st.mongodb_uri)  # READ-ONLY use: find / count_documents only
        result = await audit(client[st.mongodb_db_name], raw["docx_path"], raw["slot_map"], raw["criteria_logs"])
        print(render(result))
        print(json.dumps({"totals": result["totals"], "observations": result["observations"]}, ensure_ascii=False, indent=2, default=str))
        out = Path(sys.argv[1]).with_name(Path(sys.argv[1]).stem.replace("raw_", "table_1_2_audit_") + ".json")
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print("saved:", out)
        sys.exit(1 if result["totals"]["FAIL"] or not result["totals"]["complete_13x5"] else 0)

    asyncio.run(_main())
