"""Document lifecycle tests (fix.md sec.29):

    Generate -> Current Generated Artifact      (NO Version)
    Save     -> Current Draft (edited DOCX)     (NO Version)
    Download -> immutable Version Snapshot      (generated_documents -> History)

Runs the real FastAPI app (api_server.app) in-process through httpx's ASGI
transport, against a TEMPORARY MongoDB database `aunqa_ps_test_<uuid>` (created
here, dropped at the end) and a temporary OUTPUT_DIR. The production database
(`aunqa_ps`) is opened READ-ONLY and only to prove Test 9 (Source Data is
never modified) - nothing is ever written to it. The script refuses to run
if the configured DB name isn't the temporary one.

Generate is exercised through the real `POST /api/generate` route with
`MonitorClient.check_readiness` patched to READY *in this test process only*
(same technique test_generator_gate.py uses) and `run_master` replaced by a
stand-in that copies a real generated SAR DOCX into OUTPUT_DIR - the real
Master needs Gemini/Chroma/Template Service, which are out of scope here. The
production Monitor Gate code is not modified by any of this.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# ---- settings must be pinned BEFORE anything imports common.config ----
from common.config import Settings  # noqa: E402

PROD_DB = Settings().mongodb_db_name  # read the real name once, before overriding
TEST_DB = f"aunqa_ps_test_{uuid.uuid4().hex[:8]}"
OUTPUT_DIR = tempfile.mkdtemp(prefix="lifecycle_out_")
os.environ["MONGODB_DB_NAME"] = TEST_DB
os.environ["OUTPUT_DIR"] = OUTPUT_DIR

import docx  # noqa: E402
import httpx  # noqa: E402
from bson import ObjectId  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

import api_server  # noqa: E402
from common.config import get_settings  # noqa: E402
from common.mongo import get_db  # noqa: E402
from document.docx_edit import apply_html_to_docx  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from monitor.schemas import MonitorReadinessResult, MonitorReadinessStatus  # noqa: E402

SOURCE_COLLECTIONS = [
    "curricula", "persons", "educations", "appointments", "academic_works",
    "documents", "ps_requirements", "data_usages",
]
BASE_DOCX = BACKEND / "output" / "SAR_28abcfd2-75eb-4701-8ea9-44423d728125.docx"  # real generated SAR (has "ปริญญาโท")
ORIGINAL, EDIT_A, EDIT_B = "ปริญญาโท", "ปริญญาเอก", "ปริญญาเอก (ทดสอบ B)"
TABLE_BLOCK, EDIT_ROW, EDIT_COL = 7, 4, 2  # the "วุฒิการศึกษาสูงสุด" cell holding ORIGINAL in BASE_DOCX

passed = 0


def ok(name: str) -> None:
    global passed
    passed += 1
    print(f"TEST {name}: OK")


def docx_text(path) -> str:
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for r in t.rows:
            parts.extend(c.text for c in r.cells)
    return "\n".join(parts)


def cell_text(path, block_table_index: int, row: int, col: int) -> str:
    return docx.Document(str(path)).tables[block_table_index].rows[row].cells[col].text


def structure_signature(path) -> dict:
    """Template-structure fingerprint: tables/rows/cells, gridSpan + vMerge
    sequence, paragraph styles - everything an edit must NOT disturb."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    d = docx.Document(str(path))
    return {
        "tables": len(d.tables),
        "rows": [len(t.rows) for t in d.tables],
        "gridSpan": len(re.findall(r"<w:gridSpan", xml)),
        "vMerge": len(re.findall(r"<w:vMerge", xml)),
        "tbl_borders": len(re.findall(r"<w:tblBorders", xml)),
        "paragraphs": len(d.paragraphs),
        "styles": [p.style.name for p in d.paragraphs],
    }


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


async def source_digest(prod_db) -> dict:
    """Read-only fingerprint (count + content hash) of every Source Data collection."""
    result = {}
    for name in SOURCE_COLLECTIONS:
        h = hashlib.sha256()
        count = 0
        async for doc in prod_db[name].find({}).sort("_id", 1):
            h.update(json.dumps(doc, default=str, sort_keys=True).encode())
            count += 1
        result[name] = (count, h.hexdigest())
    return result


async def prod_history_digest(prod_db) -> tuple:
    """READ-ONLY fingerprint of the production Version History (every element's content + order)."""
    docs = [d async for d in prod_db["generated_documents"].find({}).sort("_id", 1)]
    return (len(docs), hashlib.sha256(json.dumps(docs, default=str, sort_keys=True).encode()).hexdigest())


def edited_table_html(html: str, old: str, new: str) -> str:
    """Change ONE cell's text in the HTML, addressed by its stable ids."""
    pattern = re.compile(
        rf'(<table data-block="{TABLE_BLOCK}".*?<tr data-row="{EDIT_ROW}">.*?<td data-col="{EDIT_COL}"[^>]*>){re.escape(old)}(</td>)',
        re.S,
    )
    result, n = pattern.subn(rf"\g<1>{new}\g<2>", html, count=1)
    assert n == 1, "could not locate the target cell in preview HTML"
    return result


def _ready():
    return MonitorReadinessResult(status=MonitorReadinessStatus.READY, detail="test patch")


async def main() -> None:
    settings = get_settings()
    assert settings.mongodb_db_name == TEST_DB and TEST_DB != PROD_DB and TEST_DB.startswith("aunqa_ps_test_"), (
        f"refusing to run: app is not pointed at a temporary test DB ({settings.mongodb_db_name})"
    )
    assert settings.output_dir == OUTPUT_DIR
    assert BASE_DOCX.exists(), f"fixture DOCX missing: {BASE_DOCX}"

    client_raw = AsyncIOMotorClient(settings.mongodb_uri)
    prod_db = client_raw[PROD_DB]  # READ-ONLY use only (find/count) - no writes anywhere below
    db = get_db()  # the temporary DB
    digest_before = await source_digest(prod_db)
    prod_history_before = await prod_history_digest(prod_db)

    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=api_server.app), base_url="http://test")

    try:
        # ---------------- seed the TEMP db ----------------
        curriculum_id = ObjectId()
        await db["curricula"].insert_one({"_id": curriculum_id, "curriculumName": "TEST curriculum"})
        legacy_docx = Path(OUTPUT_DIR) / "SAR_legacy-run-0001.docx"  # pre-lifecycle-change style entry
        shutil.copyfile(BASE_DOCX, legacy_docx)
        # a pre-existing Version in the CURRENT per-Version shape (what the migration produces from a legacy element:
        # no runId/source/userEdits) - proves old Versions stay readable and are never rewritten
        legacy_doc = {"curriculumId": curriculum_id, "fileName": f"SAR_{curriculum_id}.docx", "fileType": "docx", "version": 1,
                      "path": str(legacy_docx), "timestamp": __import__("datetime").datetime(2026, 1, 1)}
        await db["generated_documents"].insert_one(dict(legacy_doc))
        # a real education id (READ-ONLY lookup) so the seeded citation points at a real record
        education = await prod_db["educations"].find_one({}, {"_id": 1})
        education_id = str(education["_id"]) if education else "no-education-in-prod"

        # fake Master: Generate produces a Current Generated Artifact only
        async def fake_run_master(run_id=None):
            out = Path(get_settings().output_dir) / f"SAR_{run_id}.docx"
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BASE_DOCX, out)
            return out

        api_server.run_master = fake_run_master
        api_server._monitor_client.check_readiness = lambda cid: _async(_ready())

        async def versions() -> int:
            return await db["generated_documents"].count_documents({"version": {"$exists": True}})

        async def generate() -> str:
            resp = await api_server.start_generate(api_server.GenerateRequest(curriculum_id=str(curriculum_id)))
            job_id = resp["job_id"]
            for _ in range(200):
                if api_server._jobs[job_id]["status"] != "running":
                    break
                await asyncio.sleep(0.02)
            assert api_server._jobs[job_id]["status"] == "completed", api_server._jobs[job_id]
            return job_id

        async def seed_reference(job_id: str) -> None:
            """slot_map + criteria log for `job_id`, derived from the REAL cells of BASE_DOCX table block 7."""
            d = docx.Document(str(BASE_DOCX))
            table = d.tables[0]
            rows_map, agent_rows = {}, []
            for r_index, row in enumerate(table.rows):
                cells = [c.text for c in row.cells]
                if r_index >= 2 and len(set(map(id, row.cells))) == 4 and cells[1].strip():
                    rows_map[str(r_index)] = len(agent_rows)
                    agent_rows.append({
                        "values": cells,
                        "citations": [{"source_filename": f"mongodb:education:{education_id}", "chunk_index": 0}],
                    })
            await db["generation_slot_marking_log"].insert_one(
                {"run_id": job_id, "status": "success", "marked_slots": [],
                 "slot_map": {"version": 1, "paragraphs": {},
                              "tables": {str(TABLE_BLOCK): {"slotId": "table_ps_1_1", "criterion": "PS", "rows": rows_map}}}}
            )
            await db["generation_criteria_log"].insert_one(
                {"run_id": job_id, "criterion": "PS", "status": "completed", "citations": [],
                 "sections": [{"type": "table", "slot_id": "table_ps_1_1",
                               "headers": ["ตำแหน่งทางวิชาการ", "ชื่อ-นามสกุล", "วุฒิการศึกษาสูงสุด", "ชื่อปริญญา (สาขาวิชา)"],
                               "rows": agent_rows}]}
            )

        async def preview(job_id):
            r = await http.get(f"/api/generate/{job_id}/preview")
            assert r.status_code == 200, r.text
            return r.json()

        async def save(job_id, html):
            return await http.put(f"/api/generate/{job_id}/draft", json={"html": html})

        async def download(job_id):
            r = await http.get(f"/api/generate/{job_id}/download")
            assert r.status_code == 200, r.text
            return r

        def as_file(resp, name) -> Path:
            p = Path(OUTPUT_DIR) / name
            p.write_bytes(resp.content)
            return p

        N = await versions()
        assert N == 1  # the seeded legacy entry: proves "N" is non-zero, like production's 7

        # ================= TEST 1 + 3: Generate (x3) creates NO version =================
        job1 = await generate()
        assert await versions() == N, "Generate created a Version"
        ok("1  Generate does NOT create a generated_documents Version")
        job2, job3 = await generate(), await generate()
        assert await versions() == N, "multiple Generates created Versions"
        assert len({job1, job2, job3}) == 3
        ok("3  Generate x3 without Download -> versions unchanged")

        master_src = inspect.getsource(sys.modules["master_agent.master"]) if "master_agent.master" in sys.modules else \
            (BACKEND / "master_agent" / "master.py").read_text(encoding="utf-8")
        assert "save_version_snapshot(" not in master_src and "save_generated_document(" not in master_src
        ok("1b master.py no longer writes to generated_documents (static check)")

        await seed_reference(job1)

        # ================= preview: original HTML carries stable ids =================
        p0 = await preview(job1)
        assert p0["fromDraft"] is False and ORIGINAL in p0["html"]
        assert f'data-block="{TABLE_BLOCK}"' in p0["html"] and 'data-slot-id="table_ps_1_1"' in p0["html"]
        assert 'data-reference-id="table_ps_1_1.row2.col2"' in p0["html"], "mapped cell lacks data-reference-id"
        data_attrs = " ".join(re.findall(r'data-[a-z-]+="[^"]*"', p0["html"]))
        assert "mongodb" not in data_attrs and education_id not in data_attrs, "source internals leaked into data-* attributes"
        ok("16a Preview (no draft) = original generated HTML with stable ids/data-slot-id/data-reference-id")

        # ================= TEST 15: Download w/o draft uses the ORIGINAL artifact =================
        r_plain = await download(job2)  # job2: no draft, no slot map
        f_plain = as_file(r_plain, "dl_plain.docx")
        assert r_plain.headers["x-document-version"] == "2"
        assert await versions() == N + 1
        assert cell_text(f_plain, 0, EDIT_ROW, EDIT_COL) == ORIGINAL
        ok("2/15 Download creates exactly ONE Version (N -> N+1), no draft -> original artifact, header X-Document-Version=2")

        # ================= TEST 13: Download again w/o changes = another snapshot =================
        r_again = await download(job2)
        assert r_again.headers["x-document-version"] == "3" and await versions() == N + 2
        ok("13 Second Download without changes creates another immutable Version (documented behavior)")
        n_after_downloads = await versions()

        # ================= TEST 4: Save creates no Version =================
        html_a = edited_table_html(p0["html"], ORIGINAL, EDIT_A)
        rs = await save(job1, html_a)
        assert rs.status_code == 200, rs.text
        assert await versions() == n_after_downloads, "Save created a Version"
        ok("4  Save does NOT create a Version")

        p1 = await preview(job1)
        assert p1["fromDraft"] is True and EDIT_A in p1["html"] and 'data-block=' in p1["html"]
        assert ORIGINAL not in p1["html"].split(f'<tr data-row="{EDIT_ROW}">')[1].split("</tr>")[0]
        ok("17 Preview after Save returns the Current Draft HTML (survives refresh)")

        # ================= TEST 5 + 6: Download after Save -> Version whose DOCX has the edit =================
        r_v = await download(job1)
        v1 = int(r_v.headers["x-document-version"])
        assert v1 == n_after_downloads + 1 and await versions() == n_after_downloads + 1
        f_v1 = as_file(r_v, "dl_v1.docx")
        assert cell_text(f_v1, 0, EDIT_ROW, EDIT_COL) == EDIT_A, "downloaded DOCX lacks the saved edit"
        assert ORIGINAL not in cell_text(f_v1, 0, EDIT_ROW, EDIT_COL)
        assert EDIT_A in docx_text(f_v1)
        ok("5  Generate -> Edit -> Save -> Download creates a Version (+1)")
        ok(f'6  Downloaded DOCX (opened & inspected) contains "{EDIT_A}" in the edited cell, not "{ORIGINAL}"')

        # browser-facing: a cross-origin fetch can only read X-Document-Version if CORS exposes it
        cors = await http.get("/api/history", headers={"Origin": settings.cors_origin_list[0]})
        assert "x-document-version" in cors.headers["access-control-expose-headers"].lower(), cors.headers
        ok("26 CORS exposes X-Document-Version to the browser (real bug found in inspection)")

        # package integrity of the downloaded DOCX (zip CRCs + every XML part well-formed)
        from lxml import etree

        with zipfile.ZipFile(f_v1) as z:
            assert z.testzip() is None
            for name in z.namelist():
                if name.endswith((".xml", ".rels")):
                    etree.fromstring(z.read(name))
        ok("6b Downloaded DOCX package is intact (zip CRC ok, all XML parts well-formed, reopens in python-docx)")

        base_sig, v1_sig = structure_signature(BASE_DOCX), structure_signature(f_v1)
        assert base_sig == v1_sig, f"template structure changed:\n{base_sig}\n{v1_sig}"
        assert base_sig["vMerge"] > 0 and base_sig["gridSpan"] > 0
        ok(f"10a Edited DOCX preserves template structure (tables/rows/gridSpan={base_sig['gridSpan']}/vMerge={base_sig['vMerge']}/styles)")

        # untouched cells identical
        b, e = docx.Document(str(BASE_DOCX)), docx.Document(str(f_v1))
        diffs = [(ti, ri, ci) for ti, (tb, te) in enumerate(zip(b.tables, e.tables))
                 for ri, (rb, re_) in enumerate(zip(tb.rows, te.rows))
                 for ci, (cb, ce) in enumerate(zip(rb.cells, re_.cells)) if cb.text != ce.text]
        assert set(diffs) == {(0, EDIT_ROW, EDIT_COL)}, diffs
        ok("10b Only the edited cell differs from the generated DOCX")

        snapshot_v1_hash = sha256(f_v1)
        v1_file_on_server = (await db["generated_documents"].find_one({"version": v1}))["path"]
        assert sha256(v1_file_on_server) == snapshot_v1_hash

        # ================= TEST 10: field-level reference (Version 1) =================
        item_url = f"/api/reference/item/table_ps_1_1.row2.col2?version={v1}"
        item_v1 = (await http.get(item_url)).json()
        assert item_v1["originalValue"] == ORIGINAL and item_v1["currentValue"] == EDIT_A and item_v1["userEdited"] is True, item_v1
        assert item_v1["value"] == EDIT_A
        assert item_v1["sourceType"] == item_v1["source"] == "mongodb", "original source must stay MongoDB"
        assert item_v1["sourceReference"]["collection"] == "education" and item_v1["sourceReference"]["recordId"] == education_id
        assert "personId" not in item_v1["sourceReference"], "an education record id must not be labelled personId"
        assert "user_edit" not in json.dumps(item_v1["sourceType"])
        ok("10  Reference: originalValue/currentValue/userEdited=true AND the real MongoDB source reference retained")

        # an unedited field of the same version is untouched
        other = (await http.get(f"/api/reference/item/table_ps_1_1.row2.col1?version={v1}")).json()
        assert "userEdited" not in other and other["source"] == "mongodb"
        ok("10c Unedited fields carry no userEdited flag")
        ref_tree_v1 = (await http.get(f"/api/reference?version={v1}")).json()
        hist_prev_v1 = (await http.get(f"/api/history/{v1}/preview")).json()["html"]
        assert EDIT_A in hist_prev_v1

        # ================= TEST 7: Edit B -> Save -> Download = Version v1+1; Version 1 immutable =================
        html_b = edited_table_html((await preview(job1))["html"], EDIT_A, EDIT_B)
        assert (await save(job1, html_b)).status_code == 200
        assert await versions() == v1, "second Save created a Version"
        r_v2 = await download(job1)
        v2 = int(r_v2.headers["x-document-version"])
        assert v2 == v1 + 1
        f_v2 = as_file(r_v2, "dl_v2.docx")
        assert cell_text(f_v2, 0, EDIT_ROW, EDIT_COL) == EDIT_B
        assert cell_text(f_v1, 0, EDIT_ROW, EDIT_COL) == EDIT_A and EDIT_B not in docx_text(f_v1)
        assert sha256(v1_file_on_server) == snapshot_v1_hash, "Version 1 file changed after Version 2"
        via_history = await http.get(f"/api/history/{v1}/download")
        assert sha256(as_file(via_history, "hist_v1.docx")) == snapshot_v1_hash
        assert EDIT_B not in docx_text(as_file(via_history, "hist_v1b.docx"))
        assert EDIT_B in docx_text(as_file(await http.get(f"/api/history/{v2}/download"), "hist_v2.docx"))
        ok("7  Version 1 contains Edit A and NOT Edit B (byte-identical after Version 2); Version 2 contains Edit B")

        hist = (await http.get("/api/history")).json()
        assert [v["version"] for v in hist["versions"]] == list(range(v2, 0, -1))
        ok("20 History = legacy entry + Download-created snapshots only (Generate/Save added none)")

        # ================= TEST 8: Reference v1 unchanged after v2 =================
        assert (await http.get(item_url)).json() == item_v1
        assert (await http.get(f"/api/reference?version={v1}")).json() == ref_tree_v1
        assert (await http.get(f"/api/history/{v1}/preview")).json()["html"] == hist_prev_v1
        item_v2 = (await http.get(f"/api/reference/item/table_ps_1_1.row2.col2?version={v2}")).json()
        assert item_v2["originalValue"] == ORIGINAL and item_v2["currentValue"] == EDIT_B and item_v2["userEdited"] is True
        assert item_v2["sourceType"] == "mongodb"
        ok("8  Reference Version 1 unchanged after Version 2 (v1: ->Edit A, v2: ->Edit B, original always the generated value)")
        ok("21 Reference is version-aware (each snapshot has its own frozen userEdits)")

        # ================= TEST 17 (legacy): pre-existing version untouched & readable =================
        doc_now = await db["generated_documents"].find_one({"version": 1})
        assert {k: v for k, v in doc_now.items() if k != "_id"} == legacy_doc, "legacy Version document was rewritten"
        assert await db["generated_documents"].count_documents({"generatedFiles": {"$exists": True}}) == 0, "array shape reappeared"
        assert (await http.get("/api/history/1/preview")).status_code == 200
        assert (await http.get("/api/history/1/download")).status_code == 200
        ok("24 Pre-existing (legacy-shaped) version is untouched and still previewable/downloadable")

        # ================= TEST 11: unmapped edit -> user_edit, nothing fabricated =================
        job_u = await generate()  # NO slot_map / criteria log seeded for this run
        pu = await preview(job_u)
        assert "data-slot-id" not in pu["html"] and "data-reference-id" not in pu["html"], "ids invented without a slot map"
        html_u = edited_table_html(pu["html"], ORIGINAL, EDIT_A)
        assert (await save(job_u, html_u)).status_code == 200
        r_u = await download(job_u)
        vu = int(r_u.headers["x-document-version"])
        assert cell_text(as_file(r_u, "dl_u.docx"), 0, EDIT_ROW, EDIT_COL) == EDIT_A
        tree_u = (await http.get(f"/api/reference?version={vu}")).json()
        node = next(n for n in tree_u["nodes"] if n["id"] == "user_edits")
        leaf_id = node["children"][0]["referenceItemId"]
        item_u = (await http.get(f"/api/reference/item/{leaf_id}?version={vu}")).json()
        assert item_u["sourceType"] == item_u["source"] == "user_edit" and item_u["userEdited"] is True
        assert item_u["originalValue"] == ORIGINAL and item_u["currentValue"] == EDIT_A
        assert "sourceReference" not in item_u, f"fabricated source reference: {item_u}"
        assert "mongodb" not in json.dumps(item_u) and "chroma" not in json.dumps(item_u)
        ok("11 Unmapped edit -> sourceType=user_edit, userEdited=true, no MongoDB/Chroma reference fabricated")

        # ================= unsupported edit -> 422, draft unchanged, no Version =================
        before_rec = await db["generation_drafts"].find_one({"job_id": job1}, {"_id": 0})
        n_before = await versions()
        cur_html = (await preview(job1))["html"]
        for label, bad in [
            ("split paragraph (Enter)", cur_html.replace('<p data-block="1">', '<p data-block="1">x</p><p data-block="1">y', 1)),
            ("deleted row", re.sub(r'<tr data-row="3">.*?</tr>', "", cur_html, count=1, flags=re.S)),
            ("new table row", cur_html.replace('<tr data-row="3">', '<tr><td>new</td></tr><tr data-row="3">', 1)),
        ]:
            resp = await save(job1, bad)
            assert resp.status_code == 422, (label, resp.status_code)
            body = resp.json()["detail"]
            assert body["status"] == "unsupported_edit" and body["problems"], body
        after_rec = await db["generation_drafts"].find_one({"job_id": job1}, {"_id": 0})
        assert before_rec == after_rec, "a rejected save changed the stored draft"
        assert (await preview(job1))["html"] == cur_html and await versions() == n_before
        assert sha256(Path(after_rec["docx_path"])) == sha256(f_v2)
        ok("14 Unsupported edit -> 422, previous draft (record + DOCX) unchanged, no Version")

        # ================= HTML -> DOCX unit round trips (checkbox, list-free, Table 1.2 vMerge) =================
        base_html = docx_to_html_of(BASE_DOCX)
        assert 'rowspan=' in base_html and "doc-checkbox" in base_html
        toggled = base_html.replace('<input type="checkbox" disabled />', '<input type="checkbox" checked disabled />', 1)
        out = Path(OUTPUT_DIR) / "checkbox.docx"
        changes = apply_html_to_docx(BASE_DOCX, toggled, out)
        assert len(changes) == 1 and changes[0].current_lines[1].startswith("[✓]"), [c.to_dict() for c in changes]
        assert structure_signature(out) == base_sig
        noop = apply_html_to_docx(BASE_DOCX, base_html, Path(OUTPUT_DIR) / "noop.docx")
        assert noop == []
        ok("15b Checkbox toggle round-trips ([ ] -> [✓]); untouched merged/vMerge tables & no-op HTML -> zero changes")

        # ================= TEST 9: Source Data never modified =================
        digest_after = await source_digest(prod_db)
        assert digest_before == digest_after, "PRODUCTION source data changed!"
        for name in SOURCE_COLLECTIONS:
            if name != "curricula":
                assert await db[name].count_documents({}) == 0, f"app wrote to source collection {name} in test DB"
        # production history must be exactly what it was when THIS test started (someone may legitimately have
        # created Versions there before - e.g. a real Download from the review UI - so no absolute assumption)
        assert await prod_history_digest(prod_db) == prod_history_before, "this test changed PRODUCTION generated_documents!"
        ok("9  User Edit does not modify Source Data (8 source collections identical before/after; prod read-only)")

        # ================= TEST 12: Monitor gate intact =================
        api_server._jobs.clear()
        api_server._active_job_id = None
        n_gate = await versions()
        for status, detail in [(MonitorReadinessStatus.NOT_READY, ""), (MonitorReadinessStatus.MONITOR_UNAVAILABLE, "down"),
                               (MonitorReadinessStatus.INVALID_RESPONSE, "bad")]:
            api_server._monitor_client.check_readiness = (
                lambda cid, s=status, d=detail: _async(MonitorReadinessResult(status=s, detail=d))
            )
            try:
                await api_server.start_generate(api_server.GenerateRequest(curriculum_id="cur-x"))
                raise AssertionError(f"gate let {status} through")
            except HTTPException as exc:
                assert exc.status_code == 412 and exc.detail["reason"] == status.value
            assert not api_server._jobs and await versions() == n_gate
        ok("12 Monitor gate intact: false / unavailable / invalid -> Generate rejected (412), never silently READY")

        print(f"\nALL {passed} lifecycle checks passed (temp DB {TEST_DB}, prod DB {PROD_DB} read-only)")
    finally:
        await http.aclose()
        assert TEST_DB.startswith("aunqa_ps_test_") and TEST_DB != PROD_DB
        await client_raw.drop_database(TEST_DB)  # only ever our own scratch DB
        client_raw.close()
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)


async def _async(value):
    return value


def docx_to_html_of(path) -> str:
    from document.docx_to_html import document_to_html

    return document_to_html(docx.Document(str(path)))


if __name__ == "__main__":
    asyncio.run(main())
