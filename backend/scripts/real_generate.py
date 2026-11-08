"""DEVELOPMENT / TEST ONLY - Real Generator entry point (fix.md Phase A/B).

Calls the REAL Master Agent (`master_agent.master.run`) - real Gemini, real
Criterion Agents, real Retrieval Manager over the real MCP server, real
ChromaDB, real MongoDB, real Template Service/template, real Verification,
real Template Injection. Nothing is mocked or stubbed.

This is NOT a production entry point and does not touch it: the production
`POST /api/generate` (api_server.py) keeps its Monitor Gate untouched and still
answers 412 until a real Monitor is configured. This script neither calls,
patches, nor imports that route, and never sets MONITOR_SERVICE_URL.

Isolation
  * Everything the Master WRITES (generation_criteria_log, generation_slot_
    marking_log, ...) goes to a TEMPORARY database `aunqa_ps_test_<uuid>`
    (MONGODB_DB_NAME is overridden for this process only) and a temporary
    OUTPUT_DIR. The temp DB is dropped at the end.
  * The production DB is opened read-only: source collections + template_ps
    are fingerprinted (count + content hash) before and after, and the run is
    reported FAIL if anything changed. Nothing is ever written to it.
  * TEST_MODE_FORCE_CONTENT is forced to "false" for this process (the .env
    value `true` nudges agents to write content even without evidence, which
    would defeat a data-correctness audit). .env itself is not modified.

Usage:  cd backend && python scripts/real_generate.py [--report-dir DIR]
Exit code 0 only if generation finished, source data is unchanged and the DOCX
audit found no FAIL.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # master_config.json / .env are relative to backend/

# ---- pin settings BEFORE anything imports common.config ----
from common.config import Settings  # noqa: E402

PROD_DB = Settings().mongodb_db_name
TEST_DB = f"aunqa_ps_test_{uuid.uuid4().hex[:8]}"
OUTPUT_DIR = tempfile.mkdtemp(prefix="real_generate_out_")
os.environ["MONGODB_DB_NAME"] = TEST_DB
os.environ["OUTPUT_DIR"] = OUTPUT_DIR
os.environ["TEST_MODE_FORCE_CONTENT"] = "false"

import docx  # noqa: E402
from lxml import etree  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from common.config import get_settings  # noqa: E402

SOURCE_COLLECTIONS = [
    "curricula", "persons", "educations", "appointments", "academic_works",
    "documents", "ps_requirements", "data_usages",
]
FINGERPRINTED = SOURCE_COLLECTIONS + ["template_ps"]
STATUS_MAP = {"completed": "PASS", "skipped_no_slots": "SKIPPED", "failed_verification": "FAIL", "failed_injection": "FAIL"}


async def fingerprint(db) -> dict:
    out = {}
    for name in FINGERPRINTED:
        h, n = hashlib.sha256(), 0
        async for doc in db[name].find({}).sort("_id", 1):
            h.update(json.dumps(doc, default=str, sort_keys=True).encode())
            n += 1
        out[name] = {"count": n, "sha256": h.hexdigest()}
    return out


class _Tee(io.TextIOBase):
    """Copies everything the real Master prints (attempt / verification / retrieval
    lines) into the report while still showing it live."""

    def __init__(self, real):
        self.real, self.lines, self._buf = real, [], ""

    def write(self, text):
        self.real.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.lines.append(line)
        return len(text)

    def flush(self):
        self.real.flush()


def docx_facts(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.testzip() is None, "zip CRC error"
        for name in z.namelist():
            if name.endswith((".xml", ".rels")):
                etree.fromstring(z.read(name))  # raises if not well-formed
        xml = z.read("word/document.xml").decode("utf-8")
    d = docx.Document(io.BytesIO(data))
    return {
        "tables": len(d.tables),
        "rows": [len(t.rows) for t in d.tables],
        "gridSpan": len(re.findall(r"<w:gridSpan", xml)),
        "vMerge": len(re.findall(r"<w:vMerge", xml)),
        "paragraphs": len(d.paragraphs),
        "styles": sorted({p.style.name for p in d.paragraphs}),
        "all_text_hits": [t for t in ("Traceability Matrix",) if t in "\n".join(p.text for p in d.paragraphs)],
        "markers": re.findall(r"\{\{[^}]*\}\}", "\n".join(p.text for p in d.paragraphs)
                              + "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)),
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", default=str(BACKEND / "output" / "audit"))
    args = parser.parse_args()

    settings = get_settings()
    assert settings.mongodb_db_name == TEST_DB and TEST_DB != PROD_DB and TEST_DB.startswith("aunqa_ps_test_")
    assert not settings.monitor_service_url, "MONITOR_SERVICE_URL must stay unset - this script never uses Monitor"

    client = AsyncIOMotorClient(settings.mongodb_uri)
    prod, test = client[PROD_DB], client[TEST_DB]
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"realgen-{uuid.uuid4().hex[:8]}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    problems: list[str] = []
    report: dict = {"run_id": run_id, "temp_db": TEST_DB, "prod_db": PROD_DB, "started": stamp}

    try:
        before = await fingerprint(prod)
        report["prod_fingerprint_before"] = before
        print(f"[real_generate] run_id={run_id} temp_db={TEST_DB} (prod {PROD_DB} read-only)", flush=True)

        # ---------------- REAL MASTER ----------------
        from master_agent.master import run as run_master  # the real Master Agent

        t0 = time.time()
        tee = _Tee(sys.stdout)
        try:
            with contextlib.redirect_stdout(tee):
                output_path = await run_master(run_id=run_id)
            report["generate"] = {"status": "PASS", "seconds": round(time.time() - t0, 1), "output": str(output_path)}
        except Exception as exc:  # noqa: BLE001
            report["generate"] = {"status": "FAIL", "seconds": round(time.time() - t0, 1), "error": f"{type(exc).__name__}: {exc}"}
            problems.append(f"Master run failed: {exc}")
            output_path = None
        report["master_events"] = [l for l in tee.lines if l.startswith("[") or "Slot Marking" in l or "table slot" in l or "injection" in l]

        # ---------------- AUDIT (temp DB only) ----------------
        slot_log = await test["generation_slot_marking_log"].find_one({"run_id": run_id}, {"_id": 0})
        crit_logs = [c async for c in test["generation_criteria_log"].find({"run_id": run_id}, {"_id": 0}).sort("created_at", 1)]
        report["slot_marking_log"] = {"status": (slot_log or {}).get("status"), "marked_slots": (slot_log or {}).get("marked_slots"),
                                      "has_slot_map": bool((slot_log or {}).get("slot_map")),
                                      "slot_map": (slot_log or {}).get("slot_map")}
        report["criteria"] = {}
        for c in crit_logs:
            report["criteria"][c["criterion"]] = {
                "log_status": c["status"], "audit_status": STATUS_MAP.get(c["status"], "FAIL"),
                "sections": [{"type": s["type"], "slot_id": s["slot_id"]} for s in c.get("sections", [])],
                "citations": len(c.get("citations", [])),
                "sections_full": c.get("sections", []),
                "trace": c.get("trace"),
            }
            if STATUS_MAP.get(c["status"], "FAIL") == "FAIL":
                problems.append(f"criterion {c['criterion']}: {c['status']}")

        if output_path is not None and Path(output_path).exists():
            data = Path(output_path).read_bytes()
            facts = docx_facts(data)
            report["docx"] = facts
            if facts["markers"]:
                problems.append(f"template markers left in DOCX: {facts['markers']}")

            # structure vs the REAL template the Master used (read-only download)
            from common.mongo import get_latest_template_metadata
            from common.template_client import download_template

            meta = await prod["template_ps"].find_one({}, sort=[("version", -1)])
            tpl = docx_facts(await download_template(meta["version"]))
            report["template"] = {"version": meta["version"], **{k: tpl[k] for k in ("tables", "rows", "gridSpan", "vMerge")}}
            # the DOCX has exactly the template's tables (NO appended Traceability Matrix); rows may only GROW (overflow rows), never shrink
            if facts["tables"] != tpl["tables"]:
                problems.append(f"tables {facts['tables']} != template {tpl['tables']} (a Traceability Matrix must not be appended)")
            if any("Traceability" in t for t in facts.get("all_text_hits", [])):
                problems.append("a Traceability Matrix text is present in the DOCX")
            for i, (a, b) in enumerate(zip(facts["rows"], tpl["rows"])):
                if a < b:
                    problems.append(f"table {i}: rows shrank {b} -> {a}")
            if facts["gridSpan"] < tpl["gridSpan"] or facts["vMerge"] < tpl["vMerge"]:
                problems.append("gridSpan/vMerge count decreased vs template")
            keep = report_dir / f"SAR_{run_id}.docx"
            shutil.copyfile(output_path, keep)
            report["docx_kept_at"] = str(keep)

            # raw dump FIRST (the temp DB is dropped at the end): lets the audit be re-run/iterated
            # offline with `python scripts/_real_generate_audit.py <raw json>` without re-generating
            raw_path = report_dir / f"raw_{run_id}.json"
            raw_path.write_text(json.dumps(
                {"run_id": run_id, "docx_path": str(keep), "slot_map": (slot_log or {}).get("slot_map"), "criteria_logs": crit_logs,
                 "master_events": report["master_events"]}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            report["raw_dump"] = str(raw_path)

            # ---- Phase B: independent data-correctness audit (prod DB read-only) ----
            import traceback

            from _real_generate_audit import run_audit

            try:
                report["data_audit"] = await run_audit(prod, keep, (slot_log or {}).get("slot_map"), crit_logs)
                if report["data_audit"]["fail_count"]:
                    problems.append(f"data audit: {report['data_audit']['fail_count']} finding(s)")
            except Exception as exc:  # noqa: BLE001 - an audit crash must be visible, never a silent pass
                report["data_audit"] = {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-800:]}
                problems.append(f"data audit crashed: {exc}")

            # ---- global education audit + verification of THIS generated DOCX (Mongo -> retrieval -> aggregation -> agent -> DOCX -> Reference) ----
            from audit_education import public as edu_public
            from audit_education import render as edu_render
            from audit_education import run_all as edu_run_all

            try:
                edu_report, edu_verification = await edu_run_all(prod, {"docx_path": str(keep), "slot_map": (slot_log or {}).get("slot_map"), "criteria_logs": crit_logs})
                report["education_audit"] = {"source": edu_public(edu_report), "docx_verification": edu_verification}
                (report_dir / f"education_audit_{run_id}.txt").write_text(edu_render(edu_report, edu_verification), encoding="utf-8")
                if edu_verification["failures"]:
                    problems.append(f"education audit: {len(edu_verification['failures'])} person(s) differ")
                if edu_verification["docx_has_traceability_matrix"] or edu_verification["docx_has_backslash_numbering"]:
                    problems.append("DOCX contains a Traceability Matrix or backslash numbering")
            except Exception as exc:  # noqa: BLE001
                report["education_audit"] = {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-800:]}
                problems.append(f"education audit crashed: {exc}")

            # ---- Table 1.2 full audit: 13 persons x 5 years vs LIVE Mongo queries -> agent -> slot_map -> DOCX -> cited sources ----
            from audit_table_1_2 import audit as audit_table_1_2
            from audit_table_1_2 import render as render_table_1_2

            try:
                t12 = await audit_table_1_2(prod, keep, (slot_log or {}).get("slot_map"), crit_logs)
                report["table_1_2_audit"] = {"totals": t12["totals"], "observations": t12["observations"], "rows": t12["rows"]}
                (report_dir / f"table_1_2_audit_{run_id}.txt").write_text(render_table_1_2(t12), encoding="utf-8")
                if t12["totals"]["FAIL"] or not t12["totals"]["complete_13x5"]:
                    problems.append(f"table 1.2 audit: {t12['totals']['FAIL']} FAIL / complete={t12['totals']['complete_13x5']}")
            except Exception as exc:  # noqa: BLE001
                report["table_1_2_audit"] = {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-800:]}
                problems.append(f"table 1.2 audit crashed: {exc}")

        report["source_integrity"] = None
    finally:
        after = await fingerprint(prod)
        report["prod_fingerprint_after"] = after
        report["source_integrity"] = "PASS" if after == report["prod_fingerprint_before"] else "FAIL"
        if report["source_integrity"] == "FAIL":
            problems.append("PRODUCTION source/template collections changed!")
        assert TEST_DB.startswith("aunqa_ps_test_") and TEST_DB != PROD_DB
        await client.drop_database(TEST_DB)
        report["temp_db_dropped"] = TEST_DB not in await client.list_database_names()
        client.close()
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)

    report["problems"] = problems
    out = report_dir / f"real_generate_{run_id}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[real_generate] report: {out}")
    print(json.dumps({k: report.get(k) for k in ("generate", "source_integrity", "temp_db_dropped", "problems")}, ensure_ascii=False, indent=2, default=str))
    for code, info in report.get("criteria", {}).items():
        print(f"  {code}: {info['audit_status']} ({info['log_status']}) sections={[s['slot_id'] for s in info['sections']]}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
