"""ROLE audit for PS Table 1.1 / 1.2 checkboxes (fix.md Task 3 Part B / Part G-2). READ-ONLY against MongoDB.

Independent of the Generator (own rules, own code): the expected Table 1.1 is derived only from the real
`appointments` collection - current curriculum, status == "active", role in {programmeResponsible, programmeStaff}.
Nothing is read from `persons`, names, academic positions, the fetch order or a head-count.

Expected structure
  section "อาจารย์ผู้รับผิดชอบหลักสูตร" : everyone with an active programmeResponsible appointment
  section "อาจารย์ประจำหลักสูตร"         : everyone with an active programmeStaff appointment; the ones who ALSO hold
                                            programmeResponsible come first
  inside each block                       : the system's existing canonical order (personId ascending) - the appointments'
                                            orderNumber / orderDate / effectiveDate are identical for every appointment of
                                            the same appointment order, so they cannot rank people (reported below)
  numbering                               : 1., 2., ... restarting in each section
Table 1.2 checkboxes: [✓] for exactly the roles the person holds as ACTIVE appointments.

Usage: python scripts/audit_roles.py [--raw output/audit/raw_<run>.json]     (with --raw also verifies that DOCX)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import docx
from bson import ObjectId

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from master_agent.docx_utils import iter_block_items  # noqa: E402  (generic body traversal only)

RESPONSIBLE, STAFF = "programmeResponsible", "programmeStaff"
LABEL = {RESPONSIBLE: "อาจารย์ผู้รับผิดชอบหลักสูตร", STAFF: "อาจารย์ประจำหลักสูตร"}  # appointments.roleName values
FULL_TITLE = {"ศ.": "ศาสตราจารย์", "รศ.": "รองศาสตราจารย์", "ผศ.": "ผู้ช่วยศาสตราจารย์", "อ.": "อาจารย์"}  # independent copy


def _norm(text) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def display_name(p) -> str:
    """Table 1.1 name column (unchanged format): <ดร. only when title is ดร.><first> <last>."""
    bare = re.sub(r"^(?:\s*(?:ศ|รศ|ผศ|อ|ดร)\.)+\s*", "", f"{p.get('firstName')} {p.get('lastName')}").strip()
    return f"{'ดร.' if (p.get('title') or '').strip() == 'ดร.' else ''}{bare}"


async def load(db) -> dict:
    curriculum = await db["curricula"].find_one({}, {"_id": 1})
    persons = {p["_id"]: p async for p in db["persons"].find({})}
    all_appts = [a async for a in db["appointments"].find({})]
    current = [a for a in all_appts if a.get("status") == "active" and a.get("curriculumId") == curriculum["_id"]]
    roles: dict[ObjectId, set] = defaultdict(set)
    for a in current:
        roles[a["personId"]].add(a["role"])
    responsible = sorted((p for p, r in roles.items() if RESPONSIBLE in r), key=str)
    staff_all = [p for p, r in roles.items() if STAFF in r]
    staff = sorted((p for p in staff_all if p in set(responsible)), key=str) + sorted((p for p in staff_all if p not in set(responsible)), key=str)
    return {"curriculum_id": curriculum["_id"], "persons": persons, "all_appointments": all_appts, "current_appointments": current,
            "roles": roles, "sections": {RESPONSIBLE: responsible, STAFF: staff}}


def role_table(ctx: dict) -> list[dict]:
    """One row per person: the data the ordering is derived from + the resulting Table 1.1 position(s)."""
    rows = []
    for pid, roles in sorted(ctx["roles"].items(), key=lambda kv: str(kv[0])):
        appts = [a for a in ctx["all_appointments"] if a["personId"] == pid]
        positions = []
        for role in (RESPONSIBLE, STAFF):
            if pid in ctx["sections"][role]:
                positions.append(f"{LABEL[role]} #{ctx['sections'][role].index(pid) + 1}")
        rows.append({
            "person": ctx["persons"][pid].get("fullName"), "personId": str(pid),
            "programmeResponsible": RESPONSIBLE in roles, "programmeStaff": STAFF in roles,
            "appointments": [{"_id": str(a["_id"]), "role": a["role"], "roleName": a.get("roleName"), "status": a.get("status"),
                              "effectiveDate": a.get("effectiveDate"), "appointmentOrder": a.get("appointmentOrder"),
                              "timestamp": str(a.get("timestamp"))[:23]} for a in sorted(appts, key=lambda a: str(a["_id"]))],
            "final_table_1_1_positions": positions,
            "table_1_2_checkboxes": {LABEL[STAFF]: STAFF in roles, LABEL[RESPONSIBLE]: RESPONSIBLE in roles},
        })
    return rows


def ordering_evidence(ctx: dict) -> dict:
    cur = ctx["current_appointments"]
    return {
        "appointments_total": len(ctx["all_appointments"]), "appointments_used(active + current curriculum)": len(cur),
        "distinct_appointmentOrder": len({json.dumps(a.get("appointmentOrder"), sort_keys=True, default=str, ensure_ascii=False) for a in cur}),
        "distinct_effectiveDate": len({a.get("effectiveDate") for a in cur}),
        "conclusion": ("appointmentOrder and effectiveDate are identical for every appointment -> they cannot rank people; the order inside each "
                       "block is the system's existing canonical order (personId ascending)") if
                      len({json.dumps(a.get("appointmentOrder"), sort_keys=True, default=str) for a in cur}) == 1 and len({a.get("effectiveDate") for a in cur}) == 1
                      else "appointment fields differ - see the appointments above",
    }


def _unique_cells(row):
    seen, out = set(), []
    for c in row.cells:
        if id(c._tc) not in seen:
            seen.add(id(c._tc))
            out.append(c)
    return out


def verify_table_1_1(document, block: int, ctx: dict) -> tuple[list, dict]:
    """Table 1.1 in a generated DOCX == the structure derived from appointments (sections, members, order, numbering)."""
    findings: list[dict] = []
    table = next(t for i, t in enumerate(iter_block_items(document)) if i == block)
    persons = ctx["persons"]
    by_display = defaultdict(list)
    for pid, p in persons.items():
        by_display[display_name(p)].append(pid)

    sections: dict[str, list] = {}
    current = None
    for row in table.rows[1:]:
        cells = _unique_cells(row)
        if len(cells) == 1:  # divider row
            current = _norm(cells[0].text)
            sections[current] = []
            continue
        if not any(_norm(c.text) for c in cells) or current is None:
            continue
        sections[current].append([_norm(c.text) for c in cells[:4]])

    stats = {"sections": {k: len(v) for k, v in sections.items()}}
    for role in (RESPONSIBLE, STAFF):
        expected_ids = ctx["sections"][role]
        rows = sections.get(LABEL[role], [])
        if len(rows) != len(expected_ids):
            findings.append({"check": "table_1_1.section_size", "where": LABEL[role], "expected": len(expected_ids), "actual": len(rows)})
        for number, (cells, pid) in enumerate(zip(rows, expected_ids), start=1):
            p = persons[pid]
            pos, name = cells[0], cells[1]
            source_position = (p.get("academicPosition") or "").strip()
            expected_pos = f"{number}. {FULL_TITLE.get(source_position, source_position)}".rstrip()
            if name != display_name(p):
                findings.append({"check": "table_1_1.member_order", "where": f"{LABEL[role]} #{number}", "expected": display_name(p), "actual": name})
            if pos != expected_pos:
                findings.append({"check": "table_1_1.position_numbering", "where": f"{LABEL[role]} {name}", "expected": expected_pos, "actual": pos})
    return findings, stats


def verify_checkboxes(document, block: int, ctx: dict) -> tuple[list, dict]:
    """Table 1.2 identity-cell checkboxes == the person's ACTIVE appointment roles."""
    findings, checked = [], 0
    table = next(t for i, t in enumerate(iter_block_items(document)) if i == block)
    by_identity = {}
    for pid, p in ctx["persons"].items():
        doctor = "ดร." if (p.get("title") or "").strip() == "ดร." else ""
        bare = re.sub(r"^(?:\s*(?:ศ|รศ|ผศ|อ|ดร)\.)+\s*", "", f"{p.get('firstName')} {p.get('lastName')}").strip()
        by_identity[f"{(p.get('academicPosition') or '').strip()}{doctor}{bare}"] = pid
    seen = set()
    for row in table.rows[2:]:
        lines = [_norm(x) for x in row.cells[0].text.split("\n")]
        ident = re.sub(r"^\d+\.\s*", "", lines[0]) if lines else ""
        if ident not in by_identity or ident in seen:
            continue
        seen.add(ident)
        pid = by_identity[ident]
        roles = ctx["roles"].get(pid, set())
        for role in (STAFF, RESPONSIBLE):
            mark = next((l for l in lines[1:] if l.endswith(LABEL[role])), None)
            actual = None if mark is None else mark.startswith("[✓]")
            checked += 1
            if actual != (role in roles):
                findings.append({"check": "table_1_2.checkbox_from_appointments", "where": f"{ident} / {LABEL[role]}", "expected": role in roles, "actual": actual})
    return findings, {"checkboxes_checked": checked, "people": len(seen)}


def render(ctx: dict, rows: list[dict], evidence: dict) -> str:
    out = ["ROLE AUDIT (read-only) - source: appointments (current curriculum, status=active)", "=" * 78, json.dumps(evidence, ensure_ascii=False, indent=1)]
    out.append(f"\n{'person':32} {'responsible':>11} {'staff':>6}  final Table 1.1 position(s)  | checkboxes(1.2)")
    for r in rows:
        out.append(f"{r['person']:32} {str(r['programmeResponsible']):>11} {str(r['programmeStaff']):>6}  {'; '.join(r['final_table_1_1_positions'])}")
        for a in r["appointments"]:
            out.append(f"      appt {a['_id']} role={a['role']} status={a['status']} order={a['appointmentOrder']['orderNumber'] if a['appointmentOrder'] else None} ts={a['timestamp']}")
    for role in (RESPONSIBLE, STAFF):
        out.append(f"\nexpected {LABEL[role]}: {len(ctx['sections'][role])} people")
    return "\n".join(out)


if __name__ == "__main__":
    import asyncio

    from motor.motor_asyncio import AsyncIOMotorClient

    from common.config import Settings

    parser = argparse.ArgumentParser()
    parser.add_argument("--raw")
    args = parser.parse_args()
    st = Settings()

    async def _main():
        db = AsyncIOMotorClient(st.mongodb_uri)[st.mongodb_db_name]  # READ-ONLY
        ctx = await load(db)
        rows, evidence = role_table(ctx), ordering_evidence(ctx)
        print(render(ctx, rows, evidence))
        code = 0
        if args.raw:
            raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
            document = docx.Document(raw["docx_path"])
            blocks = {i["slotId"]: int(b) for b, i in raw["slot_map"]["tables"].items()}
            f1, s1 = verify_table_1_1(document, blocks["table_ps_1_1"], ctx)
            f2, s2 = verify_checkboxes(document, blocks["table_ps_1_2"], ctx)
            print("\nTable 1.1 sections in the DOCX:", s1["sections"], "| findings:", len(f1), "| Table 1.2 checkboxes checked:", s2["checkboxes_checked"], "findings:", len(f2))
            for f in f1 + f2:
                print("  FINDING", json.dumps(f, ensure_ascii=False))
            code = 1 if f1 or f2 else 0
        out = BACKEND / "output" / "audit"
        out.mkdir(parents=True, exist_ok=True)
        (out / "role_audit.json").write_text(json.dumps({"ordering_evidence": evidence, "people": rows}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        sys.exit(code)

    asyncio.run(_main())
