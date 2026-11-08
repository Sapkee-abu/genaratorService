"""Independent data-correctness audit of a REAL generated SAR (fix.md Phase B).

Answers "where does the value in this DOCX cell come from?" by recomputing
what each PS cell SHOULD contain straight from the RAW source collections
(persons / appointments / educations / academic_works) with its own,
deliberately simple rules - it does NOT call the Generator's aggregation/
mapping code (person_aggregation, degree_mapping, work_aggregation), so a bug
there cannot hide itself. Production DB access is READ-ONLY (find_one/find).

Checks (each finding is {"check", "where", "expected", "actual"}):
  table_1_1   position / name / highest level / degree text / group divider
  table_1_2   identity checkboxes / education list / per-year academic+creative counts
  narrative   every order number ("NNN/YYYY") in the text exists in appointments
  slot_map    each data-reference-id cell holds the agent value the slot_map says it does
  reference   every cited Mongo record / document actually exists, and the per-column
              source collection is the expected one
Anything that can't be verified independently is reported as "review", never PASS.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

import docx
import lxml.html
from bson import ObjectId

from document.docx_to_html import document_to_html
from master_agent.docx_utils import iter_block_items  # generic body traversal only
from reference.traceability_api import _table_leaves  # the Reference builder under test

ROLE_LABEL = {"programmeResponsible": "อาจารย์ผู้รับผิดชอบหลักสูตร", "programmeStaff": "อาจารย์ประจำหลักสูตร"}
YEARS = [2569, 2568, 2567, 2566, 2565]  # most-recent-first, as generated


# ----------------------------- independent rules -----------------------------
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _level(degree: str) -> str | None:
    """Own, simple classification: only short abbreviation-shaped tokens count,
    so OCR garbage stored in `degree` (long sentences, URLs) is ignored."""
    tok = re.sub(r"[\s.]", "", degree or "")
    if not tok or len(tok) > 9:
        return None
    up = tok.upper()
    if up.startswith(("PHD", "EDD", "DBA")) or tok.endswith("ด"):
        return "ปริญญาเอก"
    if up.startswith("M") or tok.endswith("ม"):
        return "ปริญญาโท"
    if up.startswith("B") or tok.endswith("บ"):
        return "ปริญญาตรี"
    return None


_RANK = {"ปริญญาเอก": 0, "ปริญญาโท": 1, "ปริญญาตรี": 2}


def _year_be(y) -> int | None:
    try:
        y = int(y)
    except (TypeError, ValueError):
        return None
    return y + 543 if y < 2400 else y


async def load_source(db) -> dict:
    persons = {p["_id"]: p async for p in db["persons"].find({})}
    edus: dict[str, list] = defaultdict(list)
    async for e in db["educations"].find({}):
        edus[str(e["personId"])].append(e)
    works: dict[str, list] = defaultdict(list)
    async for w in db["academic_works"].find({}):
        works[str(w["personId"])].append(w)
    roles: dict[str, set] = defaultdict(set)
    orders: set[str] = set()
    curriculum = await db["curricula"].find_one({}, {"_id": 1})
    async for a in db["appointments"].find({}):
        if a.get("status") != "active" or a.get("curriculumId") != (curriculum or {}).get("_id"):
            continue  # only ACTIVE appointments of the current curriculum decide a role
        roles[str(a["personId"])].add(a["role"])
        num = (a.get("appointmentOrder") or {}).get("orderNumber")
        if num:
            orders.add(str(num))
    import audit_roles

    return {"persons": persons, "edus": edus, "works": works, "roles": roles, "orders": orders, "_role_ctx": await audit_roles.load(db)}


FULL_TITLE = {"ศ.": "ศาสตราจารย์", "รศ.": "รองศาสตราจารย์", "ผศ.": "ผู้ช่วยศาสตราจารย์", "อ.": "อาจารย์"}  # independent copy


def _identity_no_number(p) -> str:
    """Table 1.2 identity text without the number: <position abbr><ดร. if title is ดร.><name>."""
    bare = re.sub(r"^(?:\s*(?:ศ|รศ|ผศ|อ|ดร)\.)+\s*", "", f"{p.get('firstName')} {p.get('lastName')}").strip()
    return f"{(p.get('academicPosition') or '').strip()}{'ดร.' if (p.get('title') or '').strip() == 'ดร.' else ''}{bare}"


def _display(p) -> str:
    return _norm(f"{p.get('title') or ''}{p.get('firstName') or ''} {p.get('lastName') or ''}")


# ----------------------------- table helpers -----------------------------
def _table_for_block(document, block: int):
    for index, item in enumerate(iter_block_items(document)):
        if index == block:
            return item
    return None


def _unique_cells(row):
    seen, out = set(), []
    for c in row.cells:
        if id(c._tc) not in seen:
            seen.add(id(c._tc))
            out.append(c)
    return out


# ----------------------------- audits -----------------------------
def audit_table_1_1(document, block, src, db=None) -> tuple[list, dict]:
    """Table 1.1: sections, members, order and numbering derived from the ACTIVE appointments (audit_roles), plus the
    unchanged per-person columns (name / highest level / degree text) checked against raw Mongo."""
    import audit_roles

    ctx = src["_role_ctx"]
    findings, stats = audit_roles.verify_table_1_1(document, block, ctx)
    table = _table_for_block(document, block)
    persons = ctx["persons"]
    by_name = defaultdict(list)
    for pid, p in persons.items():
        by_name[audit_roles.display_name(p)].append(pid)
    rows = 0
    for row in table.rows[1:]:
        cells = _unique_cells(row)
        if len(cells) == 1 or not any(_norm(c.text) for c in cells):
            continue
        rows += 1
        _pos, name, level, degree = (_norm(c.text) for c in cells[:4])
        candidates = by_name.get(name, [])
        if len(candidates) != 1:
            findings.append({"check": "table_1_1.person_exists_once", "where": name, "expected": "exactly one persons record", "actual": len(candidates)})
            continue
        pid = str(candidates[0])
        recognized = [e for e in src["edus"].get(pid, []) if _level(e.get("degree", ""))]
        best = min(recognized, key=lambda e: _RANK[_level(e["degree"])]) if recognized else None
        exp_level = _level(best["degree"]) if best else ""
        if level != exp_level:
            findings.append({"check": "table_1_1.highest_level", "where": name, "expected": exp_level, "actual": level})
        exp_degree = _norm(f"{best.get('degree', '')} {best.get('field', '')}") if best else ""
        if degree != exp_degree:
            findings.append({"check": "table_1_1.degree_text", "where": name, "expected": exp_degree, "actual": degree})
    stats = {**stats, "rows": rows, "distinct_people": len({str(p) for r in ("programmeResponsible", "programmeStaff") for p in ctx["sections"][r]}),
             "people_with_active_roles": len(ctx["roles"])}
    return findings, stats


def audit_table_1_2(document, block, src) -> tuple[list, dict]:
    findings, stats = [], {"records": 0}
    table = _table_for_block(document, block)
    by_name = {_identity_no_number(p): p for p in src["persons"].values()}
    records: dict[str, list] = {}
    order: list[str] = []
    for row in table.rows[2:]:
        # first physical cell (vMerge restart holds the record identity; continuation cells resolve to it)
        ident_full = row.cells[0].text.split("\n")[0].strip()
        ident = re.sub(r"^\d+\.\s*", "", ident_full)
        if not ident or len(_unique_cells(row)) < 5 and ident not in by_name:
            continue
        records.setdefault(ident, [])
        records[ident].append(row)
        if ident not in order:
            order.append(ident)
            expected_number = len(order)
            if ident_full != f"{expected_number}. {ident}":
                findings.append({"check": "table_1_2.numbering", "where": ident_full, "expected": f"{expected_number}. {ident}", "actual": ident_full})
    for name in order:
        person = by_name.get(_norm(name))
        if person is None:
            findings.append({"check": "table_1_2.person_exists", "where": name, "expected": "persons record", "actual": None})
            continue
        stats["records"] += 1
        pid = str(person["_id"])
        rows = records[name]
        first = rows[0]
        # checkboxes
        lines = [_norm(l) for l in first.cells[0].text.split("\n")[1:]]
        for role, label in ROLE_LABEL.items():
            expected = role in src["roles"].get(pid, set())
            mark = next((l for l in lines if l.endswith(label)), None)
            actual = None if mark is None else mark.startswith("[✓]")
            if actual is None or actual != expected:
                findings.append({"check": "table_1_2.checkbox", "where": f"{name} / {label}", "expected": expected, "actual": actual})
        # education list: the new format "N. <degree> <field>" (no year), computed by audit_education's independent rule
        from audit_education import display_items

        expected_lines = [f"{i}. {it['text']}" for i, it in enumerate(display_items(src["edus"].get(pid, [])), 1)]
        actual_lines = [ln.strip() for ln in first.cells[1].text.split("\n") if ln.strip()]
        if expected_lines != actual_lines:
            findings.append({"check": "table_1_2.education_list", "where": name, "expected": expected_lines, "actual": actual_lines})
        # per-year counts
        for year, row in zip(YEARS, rows):
            exp_acad = exp_creat = 0
            for w in src["works"].get(pid, []):
                if _year_be(w.get("publicationYear")) != year:
                    continue
                if w.get("workType") in ("Journal", "Conference"):
                    exp_acad += 1
                elif w.get("workType") == "Creative Work":
                    exp_creat += 1
            cells = [_norm(c.text) for c in _unique_cells(row)]
            got = (cells[-3], cells[-2], cells[-1])
            if got != (str(year), str(exp_acad), str(exp_creat)):
                findings.append({"check": "table_1_2.year_counts", "where": f"{name} / {year}",
                                 "expected": [str(year), str(exp_acad), str(exp_creat)], "actual": list(got)})
    return findings, stats


def audit_narratives(document, src) -> tuple[list, dict]:
    findings, checked = [], 0
    for p in document.paragraphs:
        for num in re.findall(r"\b\d{1,4}/\d{4}\b", p.text):
            checked += 1
            if num not in src["orders"]:
                findings.append({"check": "narrative.order_number", "where": p.text[:60], "expected": sorted(src["orders"]), "actual": num})
    return findings, {"order_numbers_checked": checked}


def audit_slot_map(document, slot_map, sections_by_slot) -> tuple[list, dict]:
    """Agent slot -> DOCX block/row/col -> the value physically in that cell."""
    findings, checked = [], 0
    ref_ids = {f"{slot}.row{i}.col{j}" for slot, sec in sections_by_slot.items() if sec["type"] == "table"
               for i, _ in enumerate(sec["rows"]) for j, _ in enumerate(sec["headers"])}
    root = lxml.html.fromstring("<div>" + document_to_html(document, slot_map=slot_map, reference_ids=ref_ids) + "</div>")
    cells = {c.get("data-reference-id"): [t.strip() for t in c.itertext() if t.strip()] for c in root.iter("td", "th") if c.get("data-reference-id")}
    for slot, sec in sections_by_slot.items():
        if sec["type"] != "table":
            continue
        for i, row in enumerate(sec["rows"]):
            for j, value in enumerate(row["values"]):
                rid = f"{slot}.row{i}.col{j}"
                if rid not in cells:
                    continue  # vMerge-continued cell: only the block's first sub-row owns a rendered cell
                checked += 1
                text = " ".join(cells[rid])
                first_line = cells[rid][0] if cells[rid] else ""
                if not (_norm(text).endswith(_norm(value)) or _norm(first_line).endswith(_norm(value))):
                    findings.append({"check": "slot_map.cell_value", "where": rid, "expected": value, "actual": text})
    for slot, sec in sections_by_slot.items():
        if sec["type"] == "narrative":
            hit = any(p["slotId"] == slot for p in slot_map.get("paragraphs", {}).values())
            if not hit:
                findings.append({"check": "slot_map.narrative_mapped", "where": slot, "expected": "in slot_map.paragraphs", "actual": None})
    return findings, {"cells_checked": checked, "cells_with_reference_id": len(cells)}


async def audit_references(db, sections_by_slot) -> tuple[list, dict]:
    findings = []
    distribution: Counter = Counter()
    exists_checked = 0
    for slot, sec in sections_by_slot.items():
        if sec["type"] != "table":
            continue
        for leaf in _table_leaves(sec):
            col = int(leaf["id"].rsplit(".col", 1)[1])
            ref = leaf["sourceReference"]
            distribution[(slot, col, leaf["source"], ref.get("collection") or ("documents" if ref.get("documentId") else None))] += 1
            if leaf["source"] == "mongodb":
                exists_checked += 1
                try:
                    found = await db[ref["collection"]].find_one({"_id": ObjectId(ref["recordId"])}, {"_id": 1})
                except Exception:  # noqa: BLE001
                    found = None
                if found is None:
                    findings.append({"check": "reference.mongo_record_exists", "where": leaf["id"], "expected": f"{ref}", "actual": None})
            elif leaf["source"] == "chroma":
                exists_checked += 1
                try:
                    found = await db["documents"].find_one({"_id": ObjectId(ref["documentId"])}, {"_id": 1})
                except Exception:  # noqa: BLE001
                    found = None
                if found is None:
                    findings.append({"check": "reference.chroma_document_exists", "where": leaf["id"], "expected": f"documents._id={ref['documentId']}", "actual": None})
    # expected source collection per PS column (independent expectation)
    expect = {("table_ps_1_1", 0): {"persons"}, ("table_ps_1_1", 1): {"persons"}, ("table_ps_1_1", 2): {"educations", "documents"},
              ("table_ps_1_1", 3): {"educations"}, ("table_ps_1_2", 0): {"persons"}, ("table_ps_1_2", 1): {"educations"},
              ("table_ps_1_2", 3): {"academic_works"}, ("table_ps_1_2", 4): {"academic_works"}}
    for (slot, col, source, collection), n in distribution.items():
        allowed = expect.get((slot, col))
        if allowed is not None and source != "missing" and collection not in allowed:
            findings.append({"check": "reference.column_source", "where": f"{slot}.col{col}", "expected": sorted(allowed),
                             "actual": f"{source}:{collection} x{n}"})
    summary = {f"{s}.col{c} -> {src}:{coll}": n for (s, c, src, coll), n in sorted(distribution.items(), key=str)}
    return findings, {"source_records_verified": exists_checked, "column_source_distribution": summary}


async def run_audit(prod_db, docx_path, slot_map, criteria_logs) -> dict:
    document = docx.Document(str(docx_path))
    src = await load_source(prod_db)
    sections_by_slot = {s["slot_id"]: s for c in criteria_logs for s in c.get("sections", [])}
    blocks = {info["slotId"]: int(b) for b, info in (slot_map or {}).get("tables", {}).items()}
    report, findings = {}, []
    if "table_ps_1_1" in blocks:
        f, st = audit_table_1_1(document, blocks["table_ps_1_1"], src)
        report["table_1_1"] = st
        findings += f
    if "table_ps_1_2" in blocks:
        import audit_roles

        f, st = audit_roles.verify_checkboxes(document, blocks["table_ps_1_2"], src["_role_ctx"])
        report["table_1_2_checkboxes"] = st
        findings += f
        f, st = audit_table_1_2(document, blocks["table_ps_1_2"], src)
        report["table_1_2"] = st
        findings += f
    f, st = audit_narratives(document, src)
    report["narrative"] = st
    findings += f
    f, st = audit_slot_map(document, slot_map or {}, sections_by_slot)
    report["slot_map"] = st
    findings += f
    f, st = await audit_references(prod_db, sections_by_slot)
    report["reference"] = st
    findings += f
    report["findings"] = findings
    report["fail_count"] = sum(1 for x in findings if x.get("severity") != "review")
    report["review_count"] = sum(1 for x in findings if x.get("severity") == "review")
    return report


if __name__ == "__main__":
    # Re-run the audit from a dump written by real_generate.py (no re-generation needed):
    #   python scripts/_real_generate_audit.py output/audit/raw_<run_id>.json
    import asyncio
    import json
    import sys
    from pathlib import Path

    BACKEND = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(BACKEND))
    from motor.motor_asyncio import AsyncIOMotorClient

    from common.config import Settings

    raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    st = Settings()

    async def _main():
        client = AsyncIOMotorClient(st.mongodb_uri)
        result = await run_audit(client[st.mongodb_db_name], raw["docx_path"], raw["slot_map"], raw["criteria_logs"])  # READ-ONLY
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    asyncio.run(_main())
