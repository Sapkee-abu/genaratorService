"""DEVELOPMENT / TEST ONLY - real Browser E2E (fix.md Phase C).

  Chrome (headless, driven over CDP)  ->  the REAL frontend (Vite dev server,
  VITE_USE_MOCK_API=false - no mock adapters)  ->  the REAL backend
  (`api_server.app`, unmodified, served by uvicorn in this process)  ->  the
  REAL Master Agent / Criterion Agents / Retrieval / MCP / Chroma / Mongo /
  Gemini / Verification / Injection.

Monitor: NOT touched. The backend is started with GENERATOR_DEV_MODE=true, so it serves the
REAL backend route `POST /api/dev/generate` (same Generator core as `POST /api/generate`,
no Monitor READY gate) - defined in api_server.py, NOT in this harness. The frontend is
built with VITE_USE_MOCK_API=false + VITE_DEV_GENERATE=true, so the Generate button itself
posts to /api/dev/generate: nothing is intercepted, rewritten or faked by the harness.
The production `POST /api/generate` keeps its Monitor Gate (MONITOR_SERVICE_URL unset) and
is checked separately from the browser: it must answer 412.

Isolation: the backend writes ONLY to a temporary DB `aunqa_ps_test_<uuid>`
(source collections + template_ps are COPIED from production, read-only) and a
temporary OUTPUT_DIR; production source/template collections are fingerprinted
before/after and the temp DB is dropped at the end (no scratch DB left).

Usage: cd backend && python scripts/browser_e2e.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from common.config import Settings  # noqa: E402

PROD_DB = Settings().mongodb_db_name
TEST_DB = f"aunqa_ps_test_{uuid.uuid4().hex[:8]}"
OUTPUT_DIR = tempfile.mkdtemp(prefix="browser_e2e_out_")
DOWNLOAD_DIR = tempfile.mkdtemp(prefix="browser_e2e_dl_")
os.environ.update(MONGODB_DB_NAME=TEST_DB, OUTPUT_DIR=OUTPUT_DIR, TEST_MODE_FORCE_CONTENT="false", CORS_ORIGINS="http://localhost:5173", GENERATOR_DEV_MODE="true")

import docx  # noqa: E402
import uvicorn  # noqa: E402
import websockets  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

import api_server  # noqa: E402  (the production app, unmodified)
from common.config import get_settings  # noqa: E402
from document.docx_edit import compute_changes  # noqa: E402
from audit_table_1_2 import audit as audit_table_1_2  # noqa: E402  (scripts/ is on sys.path when run as a script)
import _real_generate_audit as rga  # noqa: E402
import audit_education as edu  # noqa: E402
import audit_roles  # noqa: E402

API_PORT, WEB_PORT, CDP_PORT = 8011, 5173, 9333
API = f"http://localhost:{API_PORT}"
WEB = f"http://localhost:{WEB_PORT}"
SOURCE = ["curricula", "persons", "educations", "appointments", "academic_works", "documents", "ps_requirements", "data_usages"]
COPIED = SOURCE + ["template_ps", "generated_documents"]  # generated_documents = the real, migrated Version 1-8 documents (copy)
NAME, ORIGINAL, EDIT_A, EDIT_B = "กาญจนา หฤหรรษพงศ์", "ปริญญาโท", "ปริญญาเอก", "ปริญญาเอก (แก้ครั้งที่ 2)"
NOTE_SUFFIX = " [แก้ไขทดสอบ]"

evidence: dict = {}
checks: list[tuple[str, bool, str]] = []
SHOTS = BACKEND / "output" / "audit" / "screens"


def check(name: str, cond: bool, detail: str = "") -> None:
    checks.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""), flush=True)


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


async def fingerprint(db) -> dict:
    out = {}
    for name in COPIED:
        h, n = hashlib.sha256(), 0
        async for doc in db[name].find({}).sort("_id", 1):
            h.update(json.dumps(doc, default=str, sort_keys=True).encode())
            n += 1
        out[name] = (n, h.hexdigest())
    return out


class CDP:
    def __init__(self, ws):
        self.ws, self.n, self.pending, self.handlers, self.responses = ws, 0, {}, {}, []

    async def start(self):
        self.task = asyncio.create_task(self._reader())

    async def _reader(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if "id" in msg:
                    fut = self.pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        fut.set_result(msg)
                else:
                    for h in self.handlers.get(msg["method"], []):
                        asyncio.create_task(h(msg["params"]))
        except websockets.ConnectionClosed:
            pass  # Chrome is terminated at the end of the run

    async def call(self, method, **params):
        self.n += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[self.n] = fut
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        msg = await asyncio.wait_for(fut, 60)
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        return msg["result"]

    def on(self, method, handler):
        self.handlers.setdefault(method, []).append(handler)

    async def js(self, expression: str):
        r = await self.call("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS error: {r['exceptionDetails'].get('exception', {}).get('description', r['exceptionDetails'])}")
        return r["result"].get("value")

    async def wait(self, expression: str, timeout: float = 30, what: str = ""):
        end = time.time() + timeout
        last = None
        while time.time() < end:
            try:
                last = await self.js(expression)
                if last:
                    return last
            except RuntimeError as exc:
                last = str(exc)
            await asyncio.sleep(0.4)
        raise TimeoutError(f"timeout waiting for {what or expression} (last={last!r})")

    async def click_button(self, label: str):
        ok = await self.js(
            "(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===%s&&!b.disabled);if(!b)return false;b.click();return true})()"
            % json.dumps(label)
        )
        assert ok, f"button {label!r} not found/enabled"

    async def shot(self, name: str):
        SHOTS.mkdir(parents=True, exist_ok=True)
        r = await self.call("Page.captureScreenshot", format="png")
        import base64

        (SHOTS / f"{name}.png").write_bytes(base64.b64decode(r["data"]))


def docx_cell(path, block_table_idx: int, row: int, col: int) -> str:
    return docx.Document(str(path)).tables[block_table_idx].rows[row].cells[col].text


def all_text(path) -> str:
    d = docx.Document(str(path))
    return "\n".join([p.text for p in d.paragraphs] + [c.text for t in d.tables for r in t.rows for c in r.cells])


async def type_into(cdp: CDP, select_js: str, text: str):
    """Real typing: select the target text in the contentEditable, then CDP Input.insertText
    (fires the browser's own beforeinput/input events -> React onInput)."""
    await cdp.js(select_js)
    await cdp.call("Input.insertText", text=text)


async def main() -> int:
    settings = get_settings()
    assert settings.mongodb_db_name == TEST_DB != PROD_DB and not settings.monitor_service_url
    for port in (API_PORT, WEB_PORT, CDP_PORT):
        assert port_free(port), f"port {port} is busy"

    client = AsyncIOMotorClient(settings.mongodb_uri)
    prod, test = client[PROD_DB], client[TEST_DB]
    procs: list[subprocess.Popen] = []
    server = None
    chrome_dir = tempfile.mkdtemp(prefix="browser_e2e_chrome_")
    started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        before = await fingerprint(prod)
        prod_gd_before = await prod["generated_documents"].count_documents({})
        assert await prod["generated_documents"].count_documents({"generatedFiles": {"$exists": True}}) == 0, "run scripts/migrate_generated_documents.py first"
        # ---- temp DB: copy source + template (READ prod, WRITE temp only) ----
        for name in COPIED:
            docs = [d async for d in prod[name].find({})]
            if docs:
                await test[name].insert_many(docs)
        print(f"[e2e] temp db {TEST_DB} seeded from {PROD_DB} (read-only copy of {len(COPIED)} collections)", flush=True)

        # ---- backend: the real app (api_server.py) - includes the real /api/dev/generate because GENERATOR_DEV_MODE=true ----
        app = api_server.app
        assert any(getattr(r, "path", "") == "/api/dev/generate" for r in app.routes), "backend does not serve /api/dev/generate"

        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=API_PORT, log_level="info"))
        server_task = asyncio.create_task(server.serve())
        for _ in range(60):
            if server.started:
                break
            await asyncio.sleep(0.25)
        assert server.started, "backend did not start"

        # ---- frontend: real adapters ----
        vite_env = {**os.environ, "VITE_API_BASE_URL": API, "VITE_USE_MOCK_API": "false", "VITE_DEV_GENERATE": "true"}
        procs.append(subprocess.Popen(["npm", "run", "dev", "--", "--port", str(WEB_PORT), "--strictPort", "--host", "localhost"],
                                      cwd=FRONTEND, env=vite_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        for _ in range(120):
            try:
                urllib.request.urlopen(WEB, timeout=1)
                break
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            raise RuntimeError("frontend dev server did not start")

        # ---- browser ----
        procs.append(subprocess.Popen(
            ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", f"--remote-debugging-port={CDP_PORT}",
             f"--user-data-dir={chrome_dir}", "--window-size=1500,1100", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=1))
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.5)
        else:
            raise RuntimeError("chrome did not start")
        ws = await websockets.connect(page["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024, ping_interval=None, ping_timeout=None)  # the in-process Master blocks the loop for seconds at a time
        cdp = CDP(ws)
        await cdp.start()
        await cdp.call("Page.enable")
        await cdp.call("Runtime.enable")
        await cdp.call("Network.enable")
        await cdp.call("Page.setDownloadBehavior", behavior="allow", downloadPath=DOWNLOAD_DIR)

        api_calls: list[dict] = []
        methods: dict[str, str] = {}

        async def on_request(p):
            methods[p["requestId"]] = p["request"]["method"]

        async def on_response(p):
            u = p["response"]["url"]
            if "/api/" in u:
                h = {k.lower(): v for k, v in p["response"].get("headers", {}).items()}
                api_calls.append({"url": u.replace(API, ""), "method": methods.get(p["requestId"]), "status": p["response"]["status"],
                                  "expose": h.get("access-control-expose-headers"), "x-document-version": h.get("x-document-version")})

        cdp.on("Network.requestWillBeSent", on_request)
        cdp.on("Network.responseReceived", on_response)

        # ============ 1. Generate page loads REAL curriculum/template ============
        await cdp.call("Page.navigate", url=f"{WEB}/generate")
        await cdp.wait("document.querySelector('.generate-form__value')&&[...document.querySelectorAll('.generate-form__value')].every(e=>e.textContent.trim()!=='—')", 30, "curriculum+template")
        vals = await cdp.js("[...document.querySelectorAll('.generate-form__value')].map(e=>e.textContent.trim())")
        cur = await test["curricula"].find_one({})
        check("real adapters: Generate form shows the REAL curriculum + latest template", vals[0] == cur["curriculumName"] and "v2" in vals[1], str(vals))
        await cdp.shot("01_generate_form")

        # ============ 2. Mock disabled + explicit dev mode (evidence from the served frontend + UI) ============
        cfg = await cdp.js(f"fetch('{WEB}/src/services/config.ts').then(r=>r.text())")
        env_block = "".join(re.findall(r'VITE_[A-Z_]+"?\s*:\s*"[^"]*"', cfg))
        check("frontend running with VITE_USE_MOCK_API=false (mock adapters not selected) and VITE_DEV_GENERATE=true",
              re.search(r'VITE_USE_MOCK_API"?\s*:\s*"false"', cfg) and re.search(r'VITE_DEV_GENERATE"?\s*:\s*"true"', cfg), env_block)
        mode_text = await cdp.js("document.querySelector('.generate-form__mode')?.textContent||''")
        check("UI states the mode: Development/Test real Generator via /api/dev/generate (not MOCK)", "/api/dev/generate" in mode_text and "MOCK" not in mode_text, mode_text)

        # ============ 3. Production Monitor gate, from the browser: POST /api/generate must be 412 ============
        prod_resp = await cdp.js(f"fetch('{API}/api/generate', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{curriculum_id: {json.dumps(str(cur['_id']))}}})}}).then(async r=>[r.status, await r.json()])")
        check("Production POST /api/generate (browser fetch) -> 412, Monitor gate intact (MONITOR_SERVICE_URL unset)",
              prod_resp[0] == 412 and prod_resp[1]["detail"]["reason"] == "MONITOR_UNAVAILABLE" and not settings.monitor_service_url, json.dumps(prod_resp, ensure_ascii=False)[:200])
        check("the blocked production request created no job (Generator core not reached)", not api_server._jobs)

        # ============ 3b. Part I: History of the migrated Versions 1..8 (real docs, read via the real UI) ============
        vcount = lambda: test["generated_documents"].count_documents({"version": {"$exists": True}})
        base_versions = await vcount()
        seeded = {d["version"]: d async for d in test["generated_documents"].find({"version": {"$exists": True}})}
        seeded_hash = {v: hashlib.sha256(Path(seeded[v]["path"]).read_bytes()).hexdigest() for v in (1, 8)}
        check("temp DB holds the 8 migrated Version documents (one document per Version, no array)",
              sorted(seeded) == list(range(1, 9)) and not await test["generated_documents"].count_documents({"generatedFiles": {"$exists": True}}), str(sorted(seeded)))
        await cdp.js("[...document.querySelectorAll('a')].find(a=>a.textContent.trim()==='History').click()")
        await cdp.wait("document.querySelectorAll('.history-item').length===8", 20, "history of 8 versions")
        shown = await cdp.js("[...document.querySelectorAll('.history-item__version')].map(e=>e.textContent.trim())")
        check("Web History shows Version 8 ... Version 1", shown == [f"Version {n}" for n in range(8, 0, -1)], str(shown))
        for n in (1, 8):
            await cdp.js(f"[...document.querySelectorAll('.history-item')].find(i=>i.querySelector('.history-item__version').textContent.trim()==='Version {n}').querySelector('button').click()")
            await cdp.wait(f"document.body.innerText.includes('Preview — Version {n}')", 20, f"preview v{n}")
            html_n = await cdp.js("document.querySelector('.history-page__preview .document-viewer').innerHTML")
            check(f"Open Version {n} from History: readable preview (tables rendered, no error)", html_n.count("<table") >= 4 and "history-page__error" not in await cdp.js("document.body.innerHTML"), f"{len(html_n)} chars")
        await cdp.js("[...document.querySelectorAll('a')].find(a=>a.textContent.trim()==='Generate').click()")
        await cdp.wait("(()=>{const b=document.querySelector('.generate-form__button');return !!b&&!b.disabled})()", 30, "generate page ready (curriculum loaded)")

        # ============ 4. REAL Generate: the user's click -> /api/dev/generate -> real Master ============
        mcp_seen = {"seen": False}

        async def probe_mcp():
            while True:
                out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
                if "mcp_server.server" in out:
                    mcp_seen["seen"] = True
                await asyncio.sleep(0.7)

        probe = asyncio.create_task(probe_mcp())
        calls_before_click = len(api_calls)
        await cdp.click_button("Generate")
        await cdp.wait("document.body.innerText.includes('Generating...')", 20, "loading state")
        await cdp.wait("document.querySelectorAll('.generate-progress__item').length>0", 15, "progress steps")
        steps = await cdp.js("[...document.querySelectorAll('.generate-progress__item')].length")
        check("loading state shown while the real Master runs", steps > 0, f"{steps} progress steps")
        await cdp.shot("03_generating")
        caused = [c for c in api_calls[calls_before_click:] if c["url"].endswith(("/api/generate", "/api/dev/generate")) and c["method"] == "POST"]
        check("the browser's Generate click sent POST /api/dev/generate (200) and did NOT call the production POST /api/generate",
              [(c["url"], c["status"]) for c in caused] == [("/api/dev/generate", 200)], json.dumps([(c["method"], c["url"], c["status"]) for c in caused]))
        t0 = time.time()
        await cdp.wait("!!document.querySelector('.document-toolbar')", 1500, "generated document workspace")
        gen_seconds = round(time.time() - t0, 1)
        probe.cancel()
        job_id = next(iter(api_server._jobs))
        job = api_server._jobs[job_id]
        check("job was created by the development route (mode=development)", job.get("mode") == "development")
        check("real Master finished; job completed with a DOCX artifact", job["status"] == "completed" and Path(job["output_path"]).exists(), f"{gen_seconds}s")
        gen_docx = Path(job["output_path"])
        check(f"Generate created NO Version (still {base_versions} Version documents)", await vcount() == base_versions)
        await cdp.shot("04_preview")

        # ---- preview HTML == generated DOCX ----
        viewer_html = await cdp.js("document.querySelector('.document-viewer').innerHTML")
        diffs = compute_changes(gen_docx, viewer_html)
        check("HTML preview in the browser matches the generated DOCX (0 differing elements)", diffs == [], f"{len(diffs)} diffs")
        slot_log = await test["generation_slot_marking_log"].find_one({"run_id": job_id})
        slot_map = slot_log["slot_map"]
        check("real Master persisted a slot_map (tables + narratives)", bool(slot_map["tables"]) and bool(slot_map["paragraphs"]))
        # ---- proof the click reached the REAL backend execution path (not just that the UI rendered) ----
        crit_logs_all = [c async for c in test["generation_criteria_log"].find({"run_id": job_id}, {"_id": 0})]
        crit_by = {c["criterion"]: c for c in crit_logs_all}
        ps_log = crit_by["PS"]
        attempts = ps_log["trace"]["attempts"]
        first_retrieval = attempts[0]["retrieval"]
        check("Master Agent executed: Slot Marking Agent (Gemini) marked slots + PS/P1/P2/P3/P4/P8 logged (PS completed, others SKIPPED)",
              slot_log["status"] == "success" and len(slot_log["marked_slots"]) >= 4 and ps_log["status"] == "completed"
              and {k: v["status"] for k, v in crit_by.items() if k != "PS"} == {k: "skipped_no_slots" for k in ("P1", "P2", "P3", "P4", "P8")},
              f"{len(slot_log['marked_slots'])} slots; " + ", ".join(f"{k}={v['status']}" for k, v in crit_by.items()))
        check("Retrieval Manager executed via the Chroma tier: PS data requests each tried 'chromadb' first and returned real chunks",
              all(f["tiersTried"][0] == "chromadb" for f in first_retrieval) and any(f["resolvedTier"] == "chromadb" and f["chunkCount"] > 0 for f in first_retrieval),
              f"{len(first_retrieval)} requests, chunks={[f['chunkCount'] for f in first_retrieval]}")
        ctx = ps_log["trace"]["psStructuredContext"]
        check("MongoDB accessed (via MCP get_curriculum_people_raw / query_structured_data): 13 people + Mongo citation chunks",
              ctx["people"] == 13 and ctx["mongoCitationChunks"] > 0, json.dumps(ctx)[:160])
        check("Verification executed on every attempt; the injected result is the attempt that PASSED",
              all("verification" in a for a in attempts) and attempts[-1]["verification"]["passed"] is True and all(not a["verification"]["passed"] for a in attempts[:-1]),
              "verdicts=" + str([a["verification"]["passed"] for a in attempts]))
        import chromadb

        col = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port).get_collection(settings.chroma_collection)  # READ-ONLY
        sample = [x for f in first_retrieval if f["resolvedTier"] == "chromadb" for x in f["sources"]][:6]
        found = [bool(col.get(where={"$and": [{"documentId": x["source"]}, {"chunkIndex": x["chunkIndex"]}]}, include=[])["ids"]) for x in sample]
        check("the chunks the Retrieval Manager returned really exist in the live ChromaDB (independent read-only lookup)", sample and all(found), f"{sum(found)}/{len(found)}")
        check("MCP server process observed running during generation (the only path to Chroma/Mongo)", mcp_seen["seen"])
        ps_out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
        check("real_generate.py was NOT called: not imported in the backend process, no such process, not referenced by the web path",
              "real_generate" not in sys.modules and "real_generate" not in ps_out and "real_generate" not in (BACKEND / "api_server.py").read_text(encoding="utf-8"))
        toolbar_name = await cdp.js("document.querySelector('.document-toolbar__filename').textContent.trim()")
        check("document shown is the job's own real artifact (SAR_<job uuid>.docx), not mock data (mock names are fixed)", toolbar_name == f"SAR_{job_id}.docx", toolbar_name)
        tbl_block = next(int(b) for b, i in slot_map["tables"].items() if i["slotId"] == "table_ps_1_1")
        has_ids = await cdp.js(f"!!document.querySelector('table[data-block=\"{tbl_block}\"] td[data-slot-id=\"table_ps_1_1\"][data-reference-id]')")
        check("preview HTML carries data-slot-id + data-reference-id on mapped cells", has_ids)

        # ---- Table 1.2 in the BROWSER == DOCX == live Mongo (65 rows) ----
        crit_logs = [c async for c in test["generation_criteria_log"].find({"run_id": job_id}, {"_id": 0})]
        t12 = await audit_table_1_2(prod, gen_docx, slot_map, crit_logs)  # READ-ONLY prod queries
        check("Table 1.2 audit on the generated DOCX: 65/65 rows == live Mongo (year + academic + creative + cited sources)",
              t12["totals"]["PASS"] == 65 and t12["totals"]["FAIL"] == 0 and t12["totals"]["complete_13x5"], json.dumps(t12["totals"]))
        blk12 = next(int(b) for b, i in slot_map["tables"].items() if i["slotId"] == "table_ps_1_2")
        dom12 = await cdp.js(f"""(()=>{{const t=document.querySelector('.document-viewer table[data-block="{blk12}"]');const o={{}};
            for(const tr of t.querySelectorAll('tr[data-row]')){{const g=c=>{{const e=tr.querySelector('[data-col="'+c+'"]');return e?e.textContent.trim():null}};
              o[tr.dataset.row]=[g(2),g(3),g(4)]}}return o}})()""")
        dom_bad = [r for r in t12["rows"] if dom12.get(str(r["physicalRow"])) != [r["docx"]["year"], r["docx"]["academic"], r["docx"]["creative"]]
                   or [str(r["year"]), str(r["mongo"]["academic"]), str(r["mongo"]["creative"])] != dom12.get(str(r["physicalRow"]))]
        check("Table 1.2 as rendered in the browser preview == DOCX == Mongo (65 rows x year/academic/creative)", not dom_bad and len(t12["rows"]) == 65,
              f"{len(dom_bad)} differing rows")
        verified = sorted(BACKEND.glob("output/audit/table_1_2_audit_realgen-*.json"), key=lambda p: p.stat().st_mtime)
        if verified:
            prev = {(r["personId"], r["year"]): (r["docx"]["academic"], r["docx"]["creative"]) for r in json.loads(verified[-1].read_text(encoding="utf-8"))["rows"]}
            now = {(r["personId"], r["year"]): (r["docx"]["academic"], r["docx"]["creative"]) for r in t12["rows"]}
            check("Table 1.2 from this browser-triggered generation == the previously VERIFIED 65-cell result", prev == now and len(now) == 65, verified[-1].name)
        evidence["table_1_2_totals"] = t12["totals"]

        # ---- Part H: the new first-column formats, checked against RAW Mongo by independent rules AND as rendered in the browser ----
        src_data = await rga.load_source(prod)
        f11, st11 = rga.audit_table_1_1(docx.Document(str(gen_docx)), tbl_block, src_data)
        role_ctx = src_data["_role_ctx"]
        n_resp, n_staff = len(role_ctx["sections"][audit_roles.RESPONSIBLE]), len(role_ctx["sections"][audit_roles.STAFF])
        check(f"Table 1.1 vs the REAL appointments (active, current curriculum): {n_resp} responsible, {n_staff} staff; the dual-role people come first in the "
              "staff section; numbering restarts per section; names/education/degree unchanged",
              not f11 and st11["rows"] == n_resp + n_staff and n_resp > 0 and n_staff >= n_resp,
              json.dumps(f11[:2], ensure_ascii=False) if f11 else f"{st11['rows']} rows, sections {st11['sections']}, 0 findings")
        dom11 = await cdp.js(f"""(()=>{{const t=document.querySelector('.document-viewer table[data-block="{tbl_block}"]');const out=[];let sec=null;
            for(const tr of t.querySelectorAll('tr[data-row]')){{const c=[...tr.querySelectorAll('td')];if(!c.length)continue;
              if(c.length===1&&c[0].hasAttribute('colspan')){{sec=c[0].textContent.trim();continue}}
              if(sec)out.push([sec,c[0].textContent.trim(),c[1].textContent.trim()])}}return out}})()""")
        expected_dom = [(audit_roles.LABEL[role], f"{n}. ", audit_roles.display_name(role_ctx["persons"][pid]))
                        for role in (audit_roles.RESPONSIBLE, audit_roles.STAFF) for n, pid in enumerate(role_ctx["sections"][role], 1)]
        check("Table 1.1 as shown in the browser: every section lists the people of that real role in order, numbered 1..n per section, FULL academic titles",
              [(g, n.split(" ")[0] + " ", nm) for g, n, nm in dom11] == expected_dom
              and all(n.split(". ", 1)[1] in ("รองศาสตราจารย์", "ผู้ช่วยศาสตราจารย์", "อาจารย์", "ศาสตราจารย์") for _, n, _nm in dom11),
              str([(g[-8:], n) for g, n, _ in dom11[:3]]) + " ... " + str([(g[-8:], n) for g, n, _ in dom11[n_resp:n_resp + 2]]))
        cb_findings, cb_stats = audit_roles.verify_checkboxes(docx.Document(str(gen_docx)), blk12, role_ctx)
        check("Table 1.2 role checkboxes == the person's ACTIVE appointment roles (all people, both boxes)", not cb_findings and cb_stats["people"] == len(role_ctx["roles"]),
              json.dumps(cb_stats))
        col0_12 = await cdp.js(f"""(()=>{{const t=document.querySelector('.document-viewer table[data-block="{blk12}"]');
            return [...t.querySelectorAll('tr[data-row] td[data-col="0"][rowspan]')].map(e=>e.innerText.split('\\n')[0].trim()).filter(x=>x!=='')}})()""")  # the template has 14 record blocks; the unused 14th block stays blank
        dup = re.compile(r"(ดร\.\s*){2}|(ศ|รศ|ผศ|อ)\.\s*(ศ|รศ|ผศ|อ)\.")
        check("Table 1.2 in the browser: numbering 1..13, '<position abbr><ดร.><name>' per person, no duplicated title, matches the independent audit",
              len(col0_12) == 13 and [int(x.split(".")[0]) for x in col0_12] == list(range(1, 14)) and not any(dup.search(x) for x in col0_12)
              and t12["totals"]["numbering_1_to_n"] and [r["person"] for r in t12["rows"][::5]] == col0_12, str(col0_12[:3]))
        check("Table 1.2 yearly values unchanged by the format change (65/65 == live Mongo; identical to the previously verified numbers)",
              t12["totals"]["PASS"] == 65 and (not verified or prev == now))

        # ---- Task 2: education (all levels) + global duplicate audit + no Traceability Matrix ----
        edu_report, edu_ver = await edu.run_all(prod, {"docx_path": str(gen_docx), "slot_map": slot_map, "criteria_logs": crit_logs})
        summ = edu_report["summary"]
        check("Global education audit vs real MongoDB: 54 records / 17 persons inspected, 13 people in Table 1.2 (41 records); Level A + Level B run",
              edu_report["scope"]["education_records_in_collection"] == 54 and edu_report["scope"]["people_in_table_1_2"] == 13
              and edu_report["scope"]["education_records_of_those_people"] == 41, json.dumps(edu_report["scope"], ensure_ascii=False)[:200])
        check("Within-person audit classified: confirmed source duplicates, semantic variants (kept), noise (not education); cross-person groups all kept",
              summ["B_same_education_different_representation"] == 3 and summ["C_confirmed_source_duplicates"] == 2 and summ["D_uncertain"] == 2
              and summ["noise_records"] == 3 and all(g["decision"].startswith("LEGITIMATE DIFFERENT PEOPLE") for g in edu_report["levelB_cross_person"]), json.dumps(summ))
        check("Table 1.2 education in the generated DOCX == the Mongo-derived expectation for all 13 people (no year, plain 1./2./3., no backslash, "
              "every cited record exists and belongs to that person, aggregation kept every record)",
              len(edu_ver["people"]) == 13 and not edu_ver["failures"] and not edu_ver["docx_has_backslash_numbering"],
              json.dumps([(r["person"], r["result"]) for r in edu_ver["failures"]], ensure_ascii=False) or "13/13")
        check("Source-vs-Generator duplicate trace: every duplicate-looking group is SOURCE (MongoDB holds both) or SEMANTIC - no GENERATOR duplicate (E)",
              all(t["where_duplication_occurs"].startswith(("SOURCE", "UNPROVEN")) for t in edu_ver["duplicate_traces"]) and len(edu_ver["duplicate_traces"]) == 7
              and all(len(set(t["docx_occurrences_of_each_text"])) >= 1 and max(t["docx_occurrences_of_each_text"]) <= 1 for t in edu_ver["duplicate_traces"]),
              str([(t["person"][-14:], t["category"][:1], t["stage_mongo_records"], t["stage_docx_lines_for_person"]) for t in edu_ver["duplicate_traces"]]))
        edu_dom = await cdp.js(f"""(()=>{{const t=document.querySelector('.document-viewer table[data-block="{blk12}"]');
            return [...t.querySelectorAll('tr[data-row] td[data-col="1"][rowspan]')].map(e=>e.innerText.split('\\n').map(x=>x.trim()).filter(x=>x!=='')).filter(a=>a.length>0)}})()""")
        check("Table 1.2 education as shown in the browser preview == expected lines per person (13 cells, no year, numbered 1..n)",
              edu_dom == [r["expected_lines"] for r in edu_ver["people"]] and not any(re.search(r"\(\s*\d{4}\s*\)|\\", ln) for cell in edu_dom for ln in cell), str(edu_dom[1]))
        preview_text = await cdp.js("document.querySelector('.document-viewer').innerText")
        check("NO Traceability Matrix in the generated DOCX (tables == the template's 4) and none in the browser preview",
              not edu_ver["docx_has_traceability_matrix"] and edu_ver["docx_table_count"] == 4 and "Traceability Matrix" not in preview_text,
              f"{edu_ver['docx_table_count']} tables")
        evidence["education_audit_summary"] = summ
        evidence["education_people"] = [{"person": r["person"], "lines": r["docx_lines"], "records": r["reference_record_ids"]} for r in edu_ver["people"]]
        evidence["table_formats"] = {"table_1_1_dom": dom11, "table_1_2_col0": col0_12}
        evidence["role_audit"] = audit_roles.role_table(role_ctx)

        # locate the target cell in the DOM (row where col1 == NAME, col2 == ORIGINAL)
        loc = await cdp.js(f"""(()=>{{const t=document.querySelector('table[data-block="{tbl_block}"]');
            for(const tr of t.querySelectorAll('tr')){{const n=tr.querySelector('td[data-col="1"]');
              if(n&&n.textContent.trim()==={json.dumps(NAME)}){{const c=tr.querySelector('td[data-col="2"]');
                return {{row:+tr.dataset.row, text:c.textContent.trim()}}}}}}return null}})()""")
        assert loc and loc["text"] == ORIGINAL, loc
        row = loc["row"]
        agent_row = slot_map["tables"][str(tbl_block)]["rows"][str(row)]
        leaf_id = f"table_ps_1_1.row{agent_row}.col2"
        docx_table_idx = 0  # table_ps_1_1 is the first table of the SAR template
        assert docx_cell(gen_docx, docx_table_idx, row, 2) == ORIGINAL

        sel_cell = lambda r: f"""(()=>{{const ed=document.querySelector('.document-editor');ed.focus();
            const td=ed.querySelector('table[data-block="{tbl_block}"] tr[data-row="{r}"] td[data-col="2"]');
            const rg=document.createRange();rg.selectNodeContents(td);const s=getSelection();s.removeAllRanges();s.addRange(rg);return td.textContent}})()"""

        # ============ 4. Edit A -> Save (no Version) ============
        await cdp.click_button("Edit")
        await cdp.wait("!!document.querySelector('.document-editor')", 10, "editor")
        await type_into(cdp, sel_cell(row), EDIT_A)
        await cdp.wait("document.body.innerText.includes('Unsaved changes')", 10, "unsaved indicator")
        await cdp.click_button("Save")
        await cdp.wait("document.body.innerText.includes('✓ Saved')", 30, "saved")
        await cdp.shot("05_saved_edit_a")
        draft = await test["generation_drafts"].find_one({"job_id": job_id})
        check("Save: Current Draft stored; HTML changed", draft is not None and EDIT_A in draft["html"] and ORIGINAL not in draft["html"].split(f'data-row="{row}"')[1].split("</tr>")[0])
        check("Save: draft DOCX contains the edit; generated DOCX untouched", docx_cell(draft["docx_path"], 0, row, 2) == EDIT_A and docx_cell(gen_docx, 0, row, 2) == ORIGINAL)
        check("Save created NO Version", await vcount() == base_versions)
        prev = await cdp.js(f"fetch('{API}/api/generate/{job_id}/preview').then(r=>r.json())")
        check("Preview endpoint now returns the Current Draft", prev["fromDraft"] is True and EDIT_A in prev["html"])

        # ============ 5. Download #1 (UI) -> Version 9 (next after the migrated 8) ============
        n_files = len(os.listdir(DOWNLOAD_DIR))
        await cdp.click_button("Download")
        await cdp.wait("document.body.innerText.includes('Downloaded as Version')", 30, "download notice")
        notice1 = await cdp.js("document.querySelector('.document-workspace__notice').innerText")
        dl1 = next(c for c in reversed(api_calls) if c["url"].endswith(f"/api/generate/{job_id}/download"))
        vA, vB, vC = base_versions + 1, base_versions + 2, base_versions + 3
        check(f"browser read X-Document-Version (UI shows the backend-assigned Version {vA})", f"Version {vA}." in notice1, notice1)
        check("CORS: response exposes X-Document-Version to the browser origin", dl1["expose"] is not None and "x-document-version" in dl1["expose"].lower(), str(dl1["expose"]))
        for _ in range(50):
            if len(os.listdir(DOWNLOAD_DIR)) > n_files and not any(f.endswith(".crdownload") for f in os.listdir(DOWNLOAD_DIR)):
                break
            await asyncio.sleep(0.3)
        f1 = sorted(Path(DOWNLOAD_DIR).glob("*.docx"), key=lambda p: p.stat().st_mtime)[-1]
        check("file downloaded BY THE BROWSER is the draft DOCX (contains the edit)", docx_cell(f1, 0, row, 2) == EDIT_A, f1.name)
        doc_a = await test["generated_documents"].find_one({"version": vA})
        check(f"Download created exactly 1 new document: generated_documents {base_versions} -> {base_versions + 1}, new document has version {vA}",
              await vcount() == base_versions + 1 and doc_a and doc_a["source"] == "download" and doc_a["curriculumId"] == seeded[8]["curriculumId"]
              and "generatedFiles" not in doc_a, f"version={doc_a and doc_a['version']}")
        check("Version 8 (migrated) unchanged after the Download", {k: v for k, v in (await test["generated_documents"].find_one({"version": 8})).items()} == seeded[8])
        v1_path = doc_a["path"]
        v1_hash = hashlib.sha256(Path(v1_path).read_bytes()).hexdigest()
        doc_a_before = dict(doc_a)

        # ============ 6. Edit B (mapped cell + an UNMAPPED template paragraph) -> Save -> Download #2 ============
        await cdp.click_button("Edit")
        await cdp.wait("!!document.querySelector('.document-editor')", 10, "editor")
        await type_into(cdp, sel_cell(row), EDIT_B)
        note_sel = f"""(()=>{{const ed=document.querySelector('.document-editor');ed.focus();
            const p=[...ed.querySelectorAll('p')].find(p=>p.textContent.startsWith('หมายเหตุ หลักสูตรที่มีวิชาเอก'));
            const rg=document.createRange();rg.selectNodeContents(p);rg.collapse(false);const s=getSelection();s.removeAllRanges();s.addRange(rg);return p.dataset.block}})()"""
        await type_into(cdp, note_sel, NOTE_SUFFIX)
        await cdp.click_button("Save")
        await cdp.wait("document.body.innerText.includes('✓ Saved')", 30, "saved 2")
        check("Save #2 still no new Version", await vcount() == base_versions + 1)
        n_files = len(os.listdir(DOWNLOAD_DIR))
        await cdp.click_button("Download")
        await cdp.wait(f"document.body.innerText.includes('Downloaded as Version {vB}')", 30, "download 2")
        for _ in range(50):
            if len(os.listdir(DOWNLOAD_DIR)) > n_files and not any(f.endswith(".crdownload") for f in os.listdir(DOWNLOAD_DIR)):
                break
            await asyncio.sleep(0.3)
        f2 = sorted(Path(DOWNLOAD_DIR).glob("*.docx"), key=lambda p: p.stat().st_mtime)[-1]
        check(f"Download #2 -> Version {vB} (10); browser file has Edit B + the note edit", docx_cell(f2, 0, row, 2) == EDIT_B and NOTE_SUFFIX.strip() in all_text(f2))
        # in-page Download #3 with no changes: header read directly by page JS
        hdr = await cdp.js(f"fetch('{API}/api/generate/{job_id}/download').then(r=>r.headers.get('X-Document-Version'))")
        check("page JS reads response.headers.get('X-Document-Version') (Download without changes -> next Version)", hdr == str(vC), str(hdr))

        all_docs = {d["version"]: d async for d in test["generated_documents"].find({"version": {"$exists": True}})}
        check(f"History data = Version {vC} ... 1: exactly {vC} documents, new ones Download-created, no array-based document",
              sorted(all_docs) == list(range(1, vC + 1)) and all(all_docs[v]["source"] == "download" for v in (vA, vB, vC))
              and not await test["generated_documents"].count_documents({"generatedFiles": {"$exists": True}}))
        check(f"Version {vA} unchanged after Version {vB}/{vC}: document identical, file byte-identical, has Edit A and NOT Edit B / note",
              {k: v for k, v in all_docs[vA].items()} == doc_a_before and hashlib.sha256(Path(v1_path).read_bytes()).hexdigest() == v1_hash
              and docx_cell(v1_path, 0, row, 2) == EDIT_A and NOTE_SUFFIX.strip() not in all_text(v1_path))
        check("Migrated Version 1 and Version 8 unchanged after all three Downloads (documents and files)",
              all({k: v for k, v in all_docs[v].items()} == seeded[v] and hashlib.sha256(Path(seeded[v]["path"]).read_bytes()).hexdigest() == seeded_hash[v] for v in (1, 8)))

        # ============ 7. History page + Reference (UI) ============
        await cdp.js("[...document.querySelectorAll('a')].find(a=>a.textContent.trim()==='History').click()")
        await cdp.wait(f"document.body.innerText.includes('Version {vC}')", 20, "history list")
        versions_shown = await cdp.js("[...document.querySelectorAll('.history-item__version')].map(e=>e.textContent.trim())")
        check(f"Web History lists Version {vC} ... Version 1 (backend-numbered)", versions_shown == [f"Version {n}" for n in range(vC, 0, -1)], str(versions_shown))
        await cdp.js(f"[...document.querySelectorAll('.history-item')].find(i=>i.querySelector('.history-item__version').textContent.trim()==='Version {vA}').querySelector('button').click()")  # Preview vA
        await cdp.wait(f"document.body.innerText.includes('Preview — Version {vA}')", 20, f"preview v{vA}")
        v1_preview = await cdp.js("document.querySelector('.history-page__preview .document-viewer').innerHTML")
        check(f"History Preview of Version {vA} shows Edit A (not Edit B)", EDIT_A in v1_preview and EDIT_B not in v1_preview)
        await cdp.shot("06_history_preview_v1")

        async def open_reference(version: int):
            await cdp.js(f"[...document.querySelectorAll('.history-item')].find(i=>i.querySelector('.history-item__version').textContent.trim()==='Version {version}').querySelector('a').click()")
            await cdp.wait(f"document.body.innerText.includes('Reference — Version {version}')&&!!document.querySelector('[role=treeitem]')", 20, "reference page")

        async def click_tree(label_contains: str):
            await cdp.wait(f"[...document.querySelectorAll('[role=treeitem]')].some(e=>e.textContent.includes({json.dumps(label_contains)}))", 10, label_contains)
            await cdp.js(f"[...document.querySelectorAll('[role=treeitem]')].find(e=>e.textContent.includes({json.dumps(label_contains)})).click()")

        # A tree item's own label, WITHOUT the toggle glyph (▶/▼) and the "N rows" badge the UI adds around it.
        OWN = ("const own=e=>[...e.childNodes].filter(n=>!(n.nodeType===1&&(n.classList.contains('reference-tree-node__toggle')"
               "||n.classList.contains('reference-tree-node__count')))).map(n=>n.textContent).join('').trim();"
               "const items=()=>[...document.querySelectorAll('[role=treeitem]')];")

        async def click_exact(label: str):
            """Toggle/select the tree item whose own label is exactly `label`."""
            await cdp.wait(f"(()=>{{{OWN} return items().some(e=>own(e)==={json.dumps(label)})}})()", 10, label)
            await cdp.js(f"(()=>{{{OWN} items().find(e=>own(e)==={json.dumps(label)}).click()}})()")

        async def open_exact(label: str):
            """Expand (never collapse) the item with this exact label."""
            await cdp.wait(f"(()=>{{{OWN} return items().some(e=>own(e)==={json.dumps(label)})}})()", 10, label)
            await cdp.js(f"(()=>{{{OWN} const e=items().find(e=>own(e)==={json.dumps(label)});if(e.getAttribute('aria-expanded')!=='true')e.click()}})()")

        async def table_dom(slot: str) -> dict:
            """DOM view of a node: its badge text + each direct child's label / open state / own children labels."""
            return await cdp.js(f"""(()=>{{{OWN}
              const head=items().find(e=>own(e)==={json.dumps(slot)});const li=head.parentElement;const ul=li.querySelector(':scope > ul');const rows=[];
              if(ul)for(const c of ul.children){{const t=c.querySelector(':scope > [role=treeitem]');const sub=c.querySelector(':scope > ul');
                rows.push({{label:own(t), open:t.getAttribute('aria-expanded'), fields:sub?[...sub.children].map(x=>own(x.querySelector(':scope > [role=treeitem]'))):[]}})}}
              const badge=head.querySelector('.reference-tree-node__count');
              return {{head:own(head), badge:badge?badge.textContent.trim():null, rows}}}})()""")

        def expected_rows(api_tree: dict, slot: str) -> dict:
            """Row index -> field labels (row suffix stripped), taken from the UNCHANGED API tree."""
            ps = next(n for n in api_tree["nodes"] if n["id"] == "ps")
            node = next(c for c in ps["children"] if c["id"] == slot)
            rows: dict[int, list] = {}
            for leaf in node["children"]:
                m = re.search(r"\.row(\d+)\.col\d+$", leaf["id"])
                rows.setdefault(int(m.group(1)), []).append(re.sub(r"\s*\(row \d+\)\s*$", "", leaf["label"]))
            return rows

        async def check_row_grouping(version: int, slot: str, pick_row: int):
            api_tree = await cdp.js(f"fetch('{API}/api/reference?version={version}').then(r=>r.json())")
            exp = expected_rows(api_tree, slot)
            n_rows = len(exp)
            n_leaves = sum(len(v) for v in exp.values())
            await open_exact(slot)
            d = await table_dom(slot)
            check(f"Reference UI {slot}: Table -> Row groups ('Row 1..Row {n_rows}'), no field listed directly under the table, row count shown ({n_rows} rows)",
                  [r["label"] for r in d["rows"]] == [f"Row {i + 1}" for i in range(n_rows)] and all(r["fields"] == [] and r["open"] == "false" for r in d["rows"])
                  and d["badge"] == f"{n_rows} rows", f"{d['head']} [{d['badge']}] / first rows {[r['label'] for r in d['rows'][:3]]}")
            # accordion: open one row -> only its fields; open a second; close the first
            await open_exact(f"Row {pick_row + 1}")
            d1_ = await table_dom(slot)
            shown = {r["label"]: r["fields"] for r in d1_["rows"] if r["fields"]}
            check(f"Reference UI {slot}: opening Row {pick_row + 1} shows only that row's fields (others stay collapsed)",
                  list(shown) == [f"Row {pick_row + 1}"] and shown[f"Row {pick_row + 1}"] == exp[pick_row], str(shown)[:200])
            other = 0 if pick_row != 0 else 1
            await open_exact(f"Row {other + 1}")
            await click_exact(f"Row {pick_row + 1}")  # collapse the first again
            d2_ = await table_dom(slot)
            shown2 = {r["label"]: r["fields"] for r in d2_["rows"] if r["fields"]}
            check(f"Reference UI {slot}: Row {other + 1} opens independently; closing Row {pick_row + 1} leaves only Row {other + 1} open",
                  list(shown2) == [f"Row {other + 1}"] and shown2[f"Row {other + 1}"] == exp[other], str(shown2)[:200])
            # every row expanded: no field lost, none moved to another row, original order kept
            for i in range(n_rows):
                await open_exact(f"Row {i + 1}")
            d3_ = await table_dom(slot)
            got = {int(r["label"].split()[1]) - 1: r["fields"] for r in d3_["rows"]}
            check(f"Reference UI {slot}: all {n_rows} rows x fields present, each field under its own row ({n_leaves} fields == API)",
                  got == exp and sum(len(v) for v in got.values()) == n_leaves and all("(row" not in f for v in got.values() for f in v), f"{n_leaves} fields")
            for i in range(n_rows):  # leave the tree tidy: collapse all rows, then the table
                await click_exact(f"Row {i + 1}")
            await cdp.js(f"(()=>{{{OWN} const e=items().find(e=>own(e)==={json.dumps(slot)});if(e.getAttribute('aria-expanded')==='true')e.click()}})()")

        async def details() -> str:
            await asyncio.sleep(0.8)
            return (await cdp.js("document.querySelector('.reference-details').innerText")).lower()

        await open_reference(vA)
        await check_row_grouping(vA, "table_ps_1_1", agent_row)   # Table 1.1: 13 rows
        await check_row_grouping(vA, "table_ps_1_2", 1)           # Table 1.2: 65 rows
        # education leaf of a person whose lines merge duplicate source records: Reference must list ALL original Mongo records
        target = next(r for r in edu_ver["people"] if r["person"].endswith("สุภาภรณ์ ใจรังษี") or "สุภาภรณ์" in r["person"])
        first_row_of_person = next(x for x in t12["rows"] if x["personId"] == target["personId"])
        edu_leaf = f"table_ps_1_2.row{first_row_of_person['agentRow']}.col1"
        api_edu = await cdp.js(f"fetch('{API}/api/reference/item/{edu_leaf}?version={vA}').then(r=>r.json())")
        api_ids = [r["recordId"] for r in (api_edu.get("sourceReferences") or [api_edu["sourceReference"]])]
        check("Reference API (education cell): sourceReferences == every original MongoDB education record behind the lines (incl. the merged duplicate)",
              api_ids == target["reference_record_ids"] and len(api_ids) == 4 and all(r["collection"] == "educations" for r in api_edu["sourceReferences"]), str(api_ids))
        # every person whose lines merge a written-out representation (category B): fewer lines than records, ALL records referenced
        for g in edu_report["levelA_within_person"]["B_representation_duplicates"]:
            person_row = next(r for r in edu_ver["people"] if r["personId"] == g["personId"])
            first_row = next(x for x in t12["rows"] if x["personId"] == g["personId"])
            item = await cdp.js(f"fetch('{API}/api/reference/item/table_ps_1_2.row{first_row['agentRow']}.col1?version={vA}').then(r=>r.json())")
            ids = [r["recordId"] for r in (item.get("sourceReferences") or [item["sourceReference"]])]
            pair = [r["recordId"] for r in g["records"]]
            check(f"Merged representation ({g['person'][-12:]}, {g['records'][0]['degree']}): shown once (fewer lines than records) and Reference lists BOTH source records {pair[0][-6:]} + {pair[1][-6:]}",
                  all(p in ids for p in pair) and len(person_row["docx_lines"]) < person_row["mongo_records"], f"{len(person_row['docx_lines'])} lines / {len(ids)} record refs")
        await open_exact("table_ps_1_2")
        await open_exact(f"Row {first_row_of_person['agentRow'] + 1}")
        await cdp.js(f"(()=>{{{OWN} const e=items().find(e=>own(e).replace(/\\s+/g,' ')==='วุฒิการศึกษา (ทุกระดับ)');e.click()}})()")
        edu_details = await details()
        check("Web Reference (browser): the education field shows 'Source records (4)' = collection educations + each original record id",
              "source records (4)" in edu_details and all(rid in edu_details for rid in target["reference_record_ids"]) and "educations" in edu_details, edu_details.replace("\n", " | ")[:260])
        await cdp.shot("09_reference_education_records")
        # non-row items keep their original display: PS's own children are the narrative slots + the two table nodes, no Row group among them
        ps_dom = await table_dom("PS")
        ps_children = [r["label"] for r in ps_dom["rows"]]
        check("Reference UI: non-row items (narrative slots such as intro_ps) still listed as before; Row groups exist only inside tables",
              "intro_ps" in ps_children and any(c.startswith("desc_ps") or c.startswith("eval_") for c in ps_children) and not any(c.startswith("Row ") for c in ps_children)
              and "table_ps_1_1" in ps_children and "table_ps_1_2" in ps_children, str(ps_children))
        await open_exact("table_ps_1_1")
        await open_exact(f"Row {agent_row + 1}")
        await click_exact("วุฒิการศึกษาสูงสุด")
        d1 = await details()
        print("   v1 reference details:", d1.replace("\n", " | "))
        check(f"Reference Version {vA} (browser): original source kept (MongoDB/Chroma) + Original vs User Edit",
              ORIGINAL in d1 and EDIT_A in d1 and "user edit" in d1 and "original source" in d1 and ("mongodb" in d1 or "chromadb" in d1), d1.replace("\n", " | ")[:220])
        await cdp.shot("07_reference_v1")
        api_item_v1 = await cdp.js(f"fetch('{API}/api/reference/item/{leaf_id}?version={vA}').then(r=>r.json())")
        check(f"Reference Version {vA} API: sourceType/sourceReference original + originalValue/currentValue/userEdited",
              api_item_v1["originalValue"] == ORIGINAL and api_item_v1["currentValue"] == EDIT_A and api_item_v1["userEdited"] is True
              and api_item_v1["sourceType"] in ("mongodb", "chroma") and bool(api_item_v1.get("sourceReference")), json.dumps(api_item_v1, ensure_ascii=False)[:300])

        await cdp.js("[...document.querySelectorAll('a')].find(a=>a.textContent.trim()==='History').click()")
        await cdp.wait("!!document.querySelector('.history-item')", 20, "history")
        await open_reference(vB)
        await open_exact("table_ps_1_1")
        await open_exact(f"Row {agent_row + 1}")
        await click_exact("วุฒิการศึกษาสูงสุด")
        d2 = await details()
        check(f"Reference Version {vB} (browser): shows Edit B; version-specific", EDIT_B in d2 and "user edit" in d2, d2.replace("\n", " | ")[:200])
        # root-level nodes are already expanded by the UI - only toggle if the leaf isn't visible yet
        if not await cdp.js("[...document.querySelectorAll('[role=treeitem]')].some(e=>e.textContent.includes('Paragraph'))"):
            await click_tree("User Edits (unattributed)")
        await cdp.wait("[...document.querySelectorAll('[role=treeitem]')].some(e=>e.textContent.includes('Paragraph'))", 10, "unattributed leaf")
        await cdp.js("[...document.querySelectorAll('[role=treeitem]')].find(e=>e.textContent.includes('Paragraph')).click()")
        d3 = await details()
        print("   v2 unattributed details:", d3.replace("\n", " | "))
        check(f"Reference Version {vB}: unmapped edit -> User Edit badge, NO source reference fabricated",
              "user edit" in d3 and "generated value" in d3 and not any(k in d3 for k in ("collection", "person id", "record id", "document", "chunk", "mongodb", "chromadb")), d3.replace("\n", " | ")[:220])
        await cdp.shot("08_reference_v2_unattributed")
        api_v1_again = await cdp.js(f"fetch('{API}/api/reference/item/{leaf_id}?version={vA}').then(r=>r.json())")
        check(f"Reference Version {vA} unchanged after Versions {vB}/{vC} exist", api_v1_again == api_item_v1)

        # ============ 8. Source integrity ============
        after = await fingerprint(prod)
        check("Production source + template collections identical before/after (count + hash)", before == after)
        check("Production generated_documents untouched (still the 8 migrated documents)", await prod["generated_documents"].count_documents({}) == prod_gd_before == 8)
        evidence.update(api_calls=[c for c in api_calls if c["url"].startswith("/api/")][:60], generate_seconds=gen_seconds, job_id=job_id,
                        leaf_id=leaf_id, chrome_downloads=sorted(os.listdir(DOWNLOAD_DIR)))
    except Exception as exc:  # noqa: BLE001
        check("harness ran to completion", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except Exception:  # noqa: BLE001
                p.kill()
        subprocess.run(["pkill", "-f", f"vite.*--port {WEB_PORT}"], check=False)
        if server is not None:
            server.should_exit = True
            await asyncio.sleep(1.0)
        assert TEST_DB.startswith("aunqa_ps_test_") and TEST_DB != PROD_DB
        await client.drop_database(TEST_DB)
        dropped = TEST_DB not in await client.list_database_names()
        check("temp DB dropped (no scratch DB left)", dropped)
        client.close()
        for d in (OUTPUT_DIR, DOWNLOAD_DIR, chrome_dir):
            shutil.rmtree(d, ignore_errors=True)

    failed = [c for c in checks if not c[1]]
    report = {"started": started, "checks": [{"name": n, "pass": ok_, "detail": d} for n, ok_, d in checks], "evidence": evidence, "failed": len(failed)}
    out = BACKEND / "output" / "audit" / f"browser_e2e_{started}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[e2e] {len(checks) - len(failed)}/{len(checks)} checks passed; report: {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
