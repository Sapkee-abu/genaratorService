"""GLOBAL education audit for PS Table 1.2 "วุฒิการศึกษา (ทุกระดับ)" (fix.md Task 2, parts 2 / 10).

READ-ONLY against MongoDB. Written independently of the Generator's display code (its own
normalization, its own classification) so a bug there cannot hide itself.

Level A  every pair of records inside ONE person
Level B  identical / similar education across DIFFERENT persons (never merged - only reported)

Every suspicious match is classified (fix.md Task 3 A1):
  A  DISTINCT EDUCATION                               different degree / field / year / institution -> both kept
  B  SAME EDUCATION, DIFFERENT REPRESENTATION         same degree abbreviation, year and institution, and one record's
                                                       field is the other's written out as "<full degree name> (<field>)"
                                                       with a degree-name level equal to the degree's level -> shown once,
                                                       BOTH records stay as sources
  C  CONFIRMED SOURCE DUPLICATE                       same degree, field, year and institution NAME after normalization
                                                       (NFKC, no whitespace/dots, case-folded; institution compared before
                                                       any "/" country suffix) -> shown once, both records stay as sources
  D  INSUFFICIENT EVIDENCE                            same year + institution + degree LEVEL but the fields do not prove it
                                                       is one education (faculty suffix, one-letter degree variant) ->
                                                       NOT merged, both shown
  N  NOISE                                            degree is not a degree (OCR junk): not education, not displayed
  E  GENERATOR DUPLICATE                              (only with --raw) the DOCX shows a line more often than the
                                                       source records justify
Records of different persons are never compared for merging (Level B only reports them).

Decisions never use string similarity alone: personId, record _id, degree, field, year and institution are all
compared, and a different _id / identical text alone decides nothing.

Usage
  python scripts/audit_education.py                          global source audit + display decision (no DOCX)
  python scripts/audit_education.py --raw output/audit/raw_<run>.json   ... plus verification of a generated DOCX,
                                                                        its agent result, slot_map and Reference sources
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import docx
from bson import ObjectId

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from master_agent.docx_utils import iter_block_items  # noqa: E402  (generic body traversal only)


# ----------------------------- independent rules -----------------------------
def key(text) -> str:
    return re.sub(r"[\s.]+", "", unicodedata.normalize("NFKC", text or "")).casefold()


def inst_name(text) -> str:
    return key((text or "").split("/")[0])


def level(degree: str) -> str | None:
    """Own, simple degree-level rule: only short abbreviation-shaped tokens count."""
    tok = re.sub(r"[\s.]", "", degree or "")
    if not tok or len(tok) > 9:
        return None
    up = tok.upper()
    if up.startswith(("PHD", "EDD", "DBA")) or tok.endswith("ด"):
        return "doctoral"
    if up.startswith("M") or tok.endswith("ม"):
        return "master"
    if up.startswith("B") or tok.endswith("บ"):
        return "bachelor"
    return None


def year(rec) -> int:
    try:
        return int(rec.get("graduationYear"))
    except (TypeError, ValueError):
        return 0


def person_label(p) -> str:
    return p.get("fullName") or f"{p.get('firstName')} {p.get('lastName')}"


def describe(rec, persons) -> dict:
    return {"recordId": str(rec["_id"]), "personId": str(rec["personId"]), "person": person_label(persons[rec["personId"]]),
            "degree": rec.get("degree"), "field": rec.get("field"), "graduationYear": rec.get("graduationYear"),
            "institution": rec.get("institution"), "importedAt": str(rec.get("timestamp"))[:19]}


def ocr_key(text) -> str:
    """key() that also ignores the sara-am / nikhahit glyph (PDF/OCR splits or drops it: คำ / คํา / ค า are one word)."""
    return key(unicodedata.normalize("NFKC", text or "").replace("\u0e4d", "").replace("\u0e33", ""))


def degree_name_level(text: str) -> str | None:
    """Level of a written-out Thai degree NAME (ends with ดุษฎีบัณฑิต / มหาบัณฑิต / บัณฑิต)."""
    t = (text or "").strip()
    if re.search(r"ดุษฎีบัณฑิต\s*$", t):
        return "doctoral"
    if re.search(r"มหาบัณฑิต\s*$", t):
        return "master"
    if re.search(r"บัณฑิต\s*$", t):
        return "bachelor"
    return None


def fullname_and_field(rec) -> tuple[str, str] | None:
    m = re.match(r"^\s*([^()]+?)\s*\(\s*(.+?)\s*\)\s*$", str(rec.get("field") or ""))
    return (m.group(1), m.group(2)) if m and degree_name_level(m.group(1)) else None


def written_out_form_of(plain, full) -> bool:
    parsed = fullname_and_field(full)
    return bool(parsed) and degree_name_level(parsed[0]) == level(full.get("degree")) and ocr_key(parsed[1]) == ocr_key(plain.get("field"))


def common_basis(a, b) -> bool:
    """Same degree abbreviation, same graduation year, compatible institution."""
    ia, ib = inst_name(a.get("institution")), inst_name(b.get("institution"))
    return key(a.get("degree")) == key(b.get("degree")) and year(a) == year(b) and (ia == ib or not ia or not ib)


def same_logical(a, b) -> bool:
    return common_basis(a, b) and (key(a.get("field")) == key(b.get("field")) or written_out_form_of(a, b) or written_out_form_of(b, a))


def classify_pair(a, b) -> str:
    if common_basis(a, b) and key(a.get("field")) == key(b.get("field")):
        return "C"
    if common_basis(a, b) and (written_out_form_of(a, b) or written_out_form_of(b, a)):
        return "B"
    ia, ib = inst_name(a.get("institution")), inst_name(b.get("institution"))
    if year(a) == year(b) and (ia == ib or not ia or not ib) and level(a.get("degree")) and level(a.get("degree")) == level(b.get("degree")):
        return "D"
    return "A"


def display_items(records: list[dict]) -> list[dict]:
    """The rule the Generator must follow (spec'd in the docstring above), implemented here from scratch."""
    shown = [r for r in records if level(r.get("degree"))]
    shown.sort(key=lambda r: (-year(r), str(r["_id"])))
    groups: list[list[dict]] = []
    for r in shown:
        for g in groups:
            if any(same_logical(m, r) for m in g):
                g.append(r)
                break
        else:
            groups.append([r])
    items: list[dict] = []
    for g in groups:
        pick = min(g, key=lambda r: (1 if fullname_and_field(r) else 0, str(r["_id"])))  # plain representation first, else earliest
        items.append({"text": f"{(pick.get('degree') or '').strip()} {(pick.get('field') or '').strip()}".strip(),
                      "records": [pick] + [r for r in g if r is not pick]})
    return items


# ----------------------------- global source audit -----------------------------
async def source_audit(db) -> dict:
    persons = {p["_id"]: p async for p in db["persons"].find({})}
    edus = [e async for e in db["educations"].find({})]
    appointed = list(dict.fromkeys([a["personId"] async for a in db["appointments"].find({}, {"personId": 1})]))
    by_person: dict[ObjectId, list] = defaultdict(list)
    for e in edus:
        by_person[e["personId"]].append(e)

    relevant = [e for pid in appointed for e in by_person[pid]]
    report: dict = {
        "scope": {"education_records_in_collection": len(edus), "persons_in_collection": len(persons),
                  "people_in_table_1_2": len(appointed), "education_records_of_those_people": len(relevant),
                  "fields_present_on_records": sorted({k for e in edus for k in e})},
        "levelA_within_person": {"B_representation_duplicates": [], "C_confirmed_source_duplicates": [], "D_uncertain": [],
                                 "N_noise_records": [], "A_distinct_pairs_checked": 0},
        "levelB_cross_person": [], "display_decisions": [],
    }

    for pid in appointed:
        recs = sorted(by_person[pid], key=lambda r: str(r["_id"]))
        for r in recs:
            if not level(r.get("degree")):
                report["levelA_within_person"]["N_noise_records"].append(
                    {**describe(r, persons), "decision": "NOT EDUCATION (degree field is OCR/parse junk) - not displayed; source untouched"})
        good = [r for r in recs if level(r.get("degree"))]
        for a, b in combinations(good, 2):
            cat = classify_pair(a, b)
            if cat == "A":
                report["levelA_within_person"]["A_distinct_pairs_checked"] += 1
                continue
            entry = {"person": person_label(persons[pid]), "personId": str(pid), "records": [describe(a, persons), describe(b, persons)]}
            if cat == "C":
                diffs = [f for f in ("degree", "field", "institution") if a.get(f) != b.get(f)]
                entry.update(category="C - CONFIRMED SOURCE DUPLICATE", verdict="SAME EDUCATION", differing_raw_text_fields=diffs,
                             reason="same personId, degree, field, graduation year and institution name after normalization "
                                    "(raw text differs only in: " + (", ".join(diffs) or "nothing") + "); imported "
                                    f"{str(a.get('timestamp'))[:16]} and {str(b.get('timestamp'))[:16]}",
                             decision="SHOWN ONCE; Reference lists BOTH record ids; nothing deleted")
                report["levelA_within_person"]["C_confirmed_source_duplicates"].append(entry)
            elif cat == "B":
                plain, full = (a, b) if fullname_and_field(b) else (b, a)
                fn, major = fullname_and_field(full)
                entry.update(category="B - SAME EDUCATION, DIFFERENT REPRESENTATION", verdict="SAME EDUCATION",
                             reason=f"same personId, same degree abbreviation {a.get('degree')!r}, same graduation year {a.get('graduationYear')}, "
                                    f"same institution; record {full['_id']}'s field is the written-out form {fn!r} + ({major!r}) whose degree-name "
                                    f"level ({degree_name_level(fn)}) equals the degree's level, and the parenthesized major equals record "
                                    f"{plain['_id']}'s field (OCR-tolerant compare: {plain.get('field')!r})",
                             decision=f"SHOWN ONCE using record {plain['_id']}; Reference lists BOTH record ids; nothing deleted")
                report["levelA_within_person"]["B_representation_duplicates"].append(entry)
            else:
                entry.update(category="D - INSUFFICIENT EVIDENCE", verdict="UNKNOWN",
                             reason="same person, same year, same institution, same degree level, but the fields do not prove one education "
                                    "(different degree text or extra words in the field)",
                             decision="NOT MERGED - both shown")
                report["levelA_within_person"]["D_uncertain"].append(entry)
        items = display_items(recs)
        report["display_decisions"].append({
            "person": person_label(persons[pid]), "personId": str(pid), "records_in_mongo": len(recs),
            "displayed_lines": [f"{i}. {it['text']}" for i, it in enumerate(items, 1)],
            "records_behind_each_line": [[str(r["_id"]) for r in it["records"]] for it in items],
            "not_displayed_noise": [str(r["_id"]) for r in recs if not level(r.get("degree"))],
        })

    # Level B: same education text held by DIFFERENT persons - reported, never merged
    groups: dict[tuple, list] = defaultdict(list)
    for pid in appointed:
        for r in by_person[pid]:
            if level(r.get("degree")):
                groups[(key(r.get("degree")), key(r.get("field")))].append(r)
    for (_dk, _fk), recs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        owners = {r["personId"] for r in recs}
        if len(owners) < 2:
            continue
        same_year = defaultdict(set)
        for r in recs:
            same_year[year(r)].add(r["personId"])
        report["levelB_cross_person"].append({
            "education": f"{recs[0].get('degree')} {recs[0].get('field')}", "persons": len(owners),
            "identical_text_and_year_across_persons": {str(y): len(p) for y, p in same_year.items() if len(p) > 1},
            "records": [describe(r, persons) for r in sorted(recs, key=lambda r: (str(r["personId"]), str(r["_id"])))],
            "category": "B - DIFFERENT PERSONS, SAME EDUCATION TEXT", "decision": "LEGITIMATE DIFFERENT PEOPLE - never merged, all kept"})

    affected = {g["personId"] for k in ("B_representation_duplicates", "C_confirmed_source_duplicates", "D_uncertain") for g in report["levelA_within_person"][k]}
    report["summary"] = {
        "education_records_of_table_1_2_people": len(relevant), "people": len(appointed),
        "B_same_education_different_representation": len(report["levelA_within_person"]["B_representation_duplicates"]),
        "C_confirmed_source_duplicates": len(report["levelA_within_person"]["C_confirmed_source_duplicates"]),
        "D_uncertain": len(report["levelA_within_person"]["D_uncertain"]),
        "A_distinct_pairs": report["levelA_within_person"]["A_distinct_pairs_checked"],
        "affected_people": len(affected),
        "noise_records": len(report["levelA_within_person"]["N_noise_records"]),
        "cross_person_groups": len(report["levelB_cross_person"]),
        "cross_person_records_involved": sum(len(g["records"]) for g in report["levelB_cross_person"]),
    }
    report["_persons"] = persons
    report["_by_person"] = by_person
    report["_appointed"] = appointed
    return report


# ----------------------------- generated DOCX verification -----------------------------
def _unique_cells(row):
    seen, out = set(), []
    for c in row.cells:
        if id(c._tc) not in seen:
            seen.add(id(c._tc))
            out.append(c)
    return out


async def verify_docx(db, report: dict, docx_path, slot_map, criteria_logs) -> dict:
    """Mongo -> Retrieval -> Aggregation -> Agent result -> DOCX -> Reference, for every person's education cell."""
    from criterion_agents.ps_agent.person_aggregation import aggregate_curriculum_people  # Generator aggregation stage (traced)
    from reference.traceability_api import _table_leaves  # the Reference builder under test
    from retrieval.mongodb import fetch_curriculum_people_raw  # Generator retrieval stage (traced)

    persons, appointed = report["_persons"], report["_appointed"]
    # run the Generator's OWN retrieval function against the database handle we were given (the process default DB may be
    # a temporary one, e.g. in real_generate.py / browser_e2e.py - the Master's MCP server reads the real source DB)
    import retrieval.mongodb as retrieval_mongodb

    original_get_db = retrieval_mongodb.get_db
    retrieval_mongodb.get_db = lambda: db
    try:
        raw = await fetch_curriculum_people_raw()
    finally:
        retrieval_mongodb.get_db = original_get_db
    aggregated = {p.person_id: p for p in aggregate_curriculum_people(raw["appointments"], raw["persons"], raw["educations"], raw["academic_works"])}

    document = docx.Document(str(docx_path))
    sections = {s["slot_id"]: s for c in criteria_logs for s in c.get("sections", [])}
    section = sections["table_ps_1_2"]
    block = next(int(b) for b, i in slot_map["tables"].items() if i["slotId"] == "table_ps_1_2")
    rows_map = {int(r): k for r, k in slot_map["tables"][str(block)]["rows"].items()}
    table = next(t for i, t in enumerate(iter_block_items(document)) if i == block)
    leaves = {leaf["id"]: leaf for leaf in _table_leaves(section)}
    docx_text = "\n".join([p.text for p in document.paragraphs] + [c.text for t in document.tables for r in t.rows for c in r.cells])

    results, findings = [], []
    seen_person: set[str] = set()
    for phys in sorted(rows_map):
        agent_idx = rows_map[phys]
        agent = section["rows"][agent_idx]
        pid = agent["record_key"]
        if pid in seen_person:
            continue
        seen_person.add(pid)
        oid = ObjectId(pid)
        recs = sorted(report["_by_person"][oid], key=lambda r: str(r["_id"]))
        items = display_items(recs)
        expected = [f"{i}. {it['text']}" for i, it in enumerate(items, 1)]
        expected_ids = [str(r["_id"]) for it in items for r in it["records"]]
        cell_lines = [ln.strip() for ln in _unique_cells(table.rows[phys])[1].text.split("\n") if ln.strip()]
        agent_lines = [ln.strip() for ln in agent["values"][1].split("\n") if ln.strip()]
        cited = [c["source_filename"].split(":", 2)[2] for c in (agent.get("column_citations") or {}).get("1", []) if c["source_filename"].startswith("mongodb:educations:")]
        leaf = leaves[f"table_ps_1_2.row{agent_idx}.col1"]
        leaf_ids = [r.get("recordId") for r in (leaf.get("sourceReferences") or [leaf["sourceReference"]])]
        # ownership: every cited id must exist AND belong to this person (no cross-person leakage, no fabricated id)
        owners = {}
        for rid in cited:
            doc = await db["educations"].find_one({"_id": ObjectId(rid)}, {"personId": 1})
            owners[rid] = str(doc["personId"]) if doc else None
        aggregated_n = len(aggregated[pid].educations) if pid in aggregated else None
        checks = {
            "docx_lines_equal_expected": cell_lines == expected,
            "agent_lines_equal_docx": agent_lines == cell_lines,
            "no_year_in_lines": not any(re.search(r"\(\s*\d{4}\s*\)|(?<!\d)(?:19|20|25|26)\d{2}(?!\d)", ln) for ln in cell_lines),
            "plain_sequential_numbering": [ln.split(". ", 1)[0] for ln in cell_lines] == [str(i) for i in range(1, len(cell_lines) + 1)] and not any("\\" in ln for ln in cell_lines),
            "no_generator_duplicate": len(cell_lines) == len(set(cell_lines)) or len(cell_lines) <= len(expected),
            "reference_records_exact": cited == expected_ids and leaf_ids == expected_ids,
            "reference_records_exist_and_owned_by_this_person": all(o == pid for o in owners.values()) and len(owners) == len(cited),
            "aggregation_kept_every_mongo_record": aggregated_n == len(recs),
        }
        row = {"person": person_label(persons[oid]), "personId": pid, "mongo_records": len(recs), "aggregated_records": aggregated_n,
               "displayed_items": len(items), "docx_lines": cell_lines, "expected_lines": expected, "reference_record_ids": cited,
               "checks": checks, "result": "PASS" if all(checks.values()) else "FAIL"}
        results.append(row)
        if row["result"] != "PASS":
            findings.append(row)

    # Source vs Generator duplicate trace for every confirmed/possible duplicate group
    traces = []
    for group in (report["levelA_within_person"]["B_representation_duplicates"] + report["levelA_within_person"]["C_confirmed_source_duplicates"]
                  + report["levelA_within_person"]["D_uncertain"]):
        pid = group["personId"]
        mine = next(r for r in results if r["personId"] == pid)
        ids = [r["recordId"] for r in group["records"]]
        texts = [f"{r['degree']} {r['field']}".strip() for r in group["records"]]
        occurrences = [sum(1 for ln in mine["docx_lines"] if ln.split(". ", 1)[1] == t) for t in texts]
        merged_once = group["category"][0] in "BC"
        traces.append({"person": group["person"], "category": group["category"], "recordIds": ids,
                       "stage_mongo_records": len(ids), "stage_aggregation_records_for_person": mine["aggregated_records"],
                       "stage_docx_lines_for_person": len(mine["docx_lines"]), "docx_occurrences_of_each_text": occurrences,
                       "where_duplication_occurs": (
                           "SOURCE (MongoDB holds both records; DOCX shows the logical education once)" if group["category"][0] in "BC"
                           else "UNPROVEN (two source records, both displayed)")})
    return {"people": results, "failures": findings, "duplicate_traces": traces,
            "docx_has_traceability_matrix": "Traceability Matrix" in docx_text,
            "docx_table_count": len(document.tables),
            "docx_has_backslash_numbering": bool(re.search(r"\d\\\.", docx_text))}


# ----------------------------- rendering / CLI -----------------------------
def render(report: dict, verification: dict | None) -> str:
    out = ["GLOBAL EDUCATION AUDIT (read-only)", "=" * 60]
    sc = report["scope"]
    out += [f"education records inspected (collection): {sc['education_records_in_collection']}  | persons in collection: {sc['persons_in_collection']}",
            f"people in Table 1.2: {sc['people_in_table_1_2']}  | their education records: {sc['education_records_of_those_people']}",
            f"fields on every record: {', '.join(sc['fields_present_on_records'])}", ""]
    out.append("LEVEL A - within one person")
    for sect, title in (("B_representation_duplicates", "B  SAME EDUCATION, DIFFERENT REPRESENTATION (shown once)"),
                        ("C_confirmed_source_duplicates", "C  CONFIRMED SOURCE DUPLICATES (shown once)"),
                        ("D_uncertain", "D  INSUFFICIENT EVIDENCE (kept, both shown)")):
        out.append(f"  {title}: {len(report['levelA_within_person'][sect])}")
        for g in report["levelA_within_person"][sect]:
            out.append(f"    {g['person']}  personId={g['personId']}")
            for r in g["records"]:
                out.append(f"      id={r['recordId']} | {r['degree']} | {r['field']} | {r['graduationYear']} | {r['institution']} | imported {r['importedAt']}")
            out.append(f"      verdict: {g['verdict']}\n      reason: {g['reason']}\n      decision: {g['decision']}")
    out.append(f"  N  NOISE records (not education): {len(report['levelA_within_person']['N_noise_records'])}")
    for r in report["levelA_within_person"]["N_noise_records"]:
        out.append(f"    id={r['recordId']} {r['person']} degree={r['degree']!r} field={r['field']!r} year={r['graduationYear']}")
    out.append(f"  A  distinct pairs checked: {report['levelA_within_person']['A_distinct_pairs_checked']}")
    out.append(f"\nLEVEL B - across different persons: {len(report['levelB_cross_person'])} groups (all LEGITIMATE DIFFERENT PEOPLE, never merged)")
    for g in report["levelB_cross_person"]:
        out.append(f"    {g['education']}  x{g['persons']} persons; same text AND same year across persons: {g['identical_text_and_year_across_persons'] or 'none'}")
    out.append("\nDISPLAY DECISION per person")
    for d in report["display_decisions"]:
        out.append(f"  {d['person']} ({d['records_in_mongo']} records)")
        for line, ids in zip(d["displayed_lines"], d["records_behind_each_line"]):
            out.append(f"     {line}    <- {', '.join(ids)}")
        if d["not_displayed_noise"]:
            out.append(f"     (not displayed, noise: {', '.join(d['not_displayed_noise'])})")
    if verification:
        out.append("\nGENERATED DOCX VERIFICATION")
        for r in verification["people"]:
            out.append(f"  [{r['result']}] {r['person']}: mongo={r['mongo_records']} aggregated={r['aggregated_records']} shown={r['displayed_items']}")
        for t in verification["duplicate_traces"]:
            out.append(f"  trace {t['person']} {t['category']}: mongo={t['stage_mongo_records']} aggregation={t['stage_aggregation_records_for_person']} "
                       f"docx-lines={t['stage_docx_lines_for_person']} -> {t['where_duplication_occurs']}")
    return "\n".join(out)


def public(report: dict) -> dict:
    return {k: v for k, v in report.items() if not k.startswith("_")}


async def run_all(db, raw: dict | None = None) -> tuple[dict, dict | None]:
    report = await source_audit(db)
    verification = None
    if raw:
        verification = await verify_docx(db, report, raw["docx_path"], raw["slot_map"], raw["criteria_logs"])
    return report, verification


if __name__ == "__main__":
    import asyncio

    from motor.motor_asyncio import AsyncIOMotorClient

    from common.config import Settings

    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", help="raw_<run>.json written by scripts/real_generate.py (adds the DOCX verification)")
    args = parser.parse_args()
    st = Settings()

    async def _main():
        client = AsyncIOMotorClient(st.mongodb_uri)  # READ-ONLY: find / find_one only
        raw = json.loads(Path(args.raw).read_text(encoding="utf-8")) if args.raw else None
        report, verification = await run_all(client[st.mongodb_db_name], raw)
        print(render(report, verification))
        out_dir = BACKEND / "output" / "audit"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (out_dir / f"education_audit_{stamp}.json").write_text(json.dumps({"source": public(report), "docx_verification": verification}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (out_dir / f"education_audit_{stamp}.txt").write_text(render(report, verification), encoding="utf-8")
        sys.exit(1 if verification and verification["failures"] else 0)

    asyncio.run(_main())
