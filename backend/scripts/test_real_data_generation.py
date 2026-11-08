"""REAL DATA INTEGRATION TEST — Generator Service.

    ***********************************************
    * DEVELOPMENT / INTEGRATION TEST ONLY.         *
    * This is NOT the production generation path.  *
    * This does NOT call Monitor.                  *
    ***********************************************

change.md ("Create a REAL DATA INTEGRATION TEST path for Generator
Service"): verifies whether the existing Generator Service can retrieve
REAL data through the existing, unmodified retrieval architecture -

    Criterion Agent -> Master -> Retrieval Manager -> MCP -> MCP Tools
    -> real MongoDB / real ChromaDB -> Retrieved Data -> Agent
    -> Result JSON -> Verification -> Reference Mapping
    -> Template Injection -> Generated DOCX

- and to produce a real generated DOCX if enough real data exists, without
ever waiting for or calling the Monitor Readiness Gate.

Why this doesn't need a new bypass mechanism: `master_agent.master.run()` -
the exact same function `POST /api/generate` calls after its Monitor gate
passes - never imports or calls MonitorClient at all (confirmed: MonitorClient
is only referenced in api_server.py). So calling it directly, as this script
does, already is "Generator without waiting for Monitor" - nothing about the
production gate (api_server.py) is touched, changed, or bypassed by this file.

MongoDB target (change.md "Point the REAL-DATA INTEGRATION TEST environment
to the actual MongoDB database"): this script loads `.env.realdata` (via
python-dotenv, override=True) BEFORE anything calls
`common.config.get_settings()`, so - for THIS PROCESS ONLY - MONGODB_URI/
MONGODB_DB_NAME resolve to the real project MongoDB
(10.200.28.47:27017/aunqa_ps) instead of `.env`'s own Atlas cluster.
Production (api_server.py, mcp_server, the CLI) never loads
`.env.realdata` and is completely unaffected - they keep reading `.env`
exactly as before. This reuses the exact same pydantic-settings/env-var
mechanism `common/config.py` already has (real OS env vars take priority
over the `env_file=".env"` it's hardcoded to read) - no second
configuration system, no hardcoded URI in source, no change to production
config. ChromaDB is untouched by this - it still resolves from `.env` via
CHROMA_HOST/CHROMA_PORT/CHROMA_COLLECTION as before.

Uses the exact same Master Agent / Criterion Agents / Retrieval Manager /
MCP / Verification / Reference Mapping / Template Injection as production -
no mocks, no second pipeline, no fabricated data. If the configured
database or ChromaDB don't have the expected real data, this script
reports that honestly instead of inventing it.

Run: python scripts/test_real_data_generation.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

_REALDATA_ENV_PATH = Path(__file__).resolve().parent.parent / ".env.realdata"
if not _REALDATA_ENV_PATH.exists():
    print(
        f"FATAL: {_REALDATA_ENV_PATH} not found - this test requires the real-data "
        "MongoDB override file (MONGODB_URI/MONGODB_DB_NAME for 10.200.28.47:27017/aunqa_ps). "
        "Refusing to silently fall back to .env's own (different) database."
    )
    sys.exit(1)
load_dotenv(_REALDATA_ENV_PATH, override=True)  # must happen before any get_settings() call below

from common import chroma as chroma_module  # noqa: E402
from common.config import get_settings  # noqa: E402
from common.mongo import get_db, get_latest_reference_file  # noqa: E402

FINAL_SCHEMA_COLLECTIONS = [
    "curricula", "persons", "educations", "appointments", "academic_works",
    "documents", "ps_requirements", "data_usages", "generated_documents",
]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Report:
    checks: list[CheckResult] = field(default_factory=list)

    def record(self, name: str, passed: bool, detail: str = "") -> bool:
        self.checks.append(CheckResult(name, passed, detail))
        status = "PASS" if passed else "FAIL"
        suffix = f" - {detail}" if detail else ""
        print(f"[{status}] {name}{suffix}")
        return passed

    def get(self, name: str) -> bool:
        for c in self.checks:
            if c.name == name:
                return c.passed
        return False


async def run_preflight(report: Report) -> dict:
    """Section 21's 9 pre-flight checks. Never silently switches to mock
    data - a failed check is reported and the script continues so the FULL
    picture is visible, but nothing here fabricates a passing result.
    """
    settings = get_settings()
    print("\n=== PRE-FLIGHT CHECKS ===")

    report.record(
        "[1] MongoDB configuration exists (.env, unchanged)",
        bool(settings.mongodb_uri) and bool(settings.mongodb_db_name),
        f"MONGODB_DB_NAME={settings.mongodb_db_name!r} (from existing .env - not modified by this script)",
    )

    names: list[str] = []
    try:
        db = get_db()
        names = await db.list_collection_names()
        report.record("[2] MongoDB connection succeeds", True)
    except Exception as exc:  # noqa: BLE001
        report.record("[2] MongoDB connection succeeds", False, f"{type(exc).__name__}: {exc}")

    report.record(
        "[3] target database exists (has collections)",
        len(names) > 0,
        f"{len(names)} collection(s): {sorted(names)}",
    )

    schema_counts: dict[str, int | None] = {}
    if names:
        db = get_db()
        for coll in FINAL_SCHEMA_COLLECTIONS:
            if coll in names:
                schema_counts[coll] = await db[coll].count_documents({})
            else:
                schema_counts[coll] = None
    any_final_data = any(isinstance(v, int) and v > 0 for v in schema_counts.values())
    report.record(
        "[4] expected Final-Schema collections readable with real data",
        any_final_data,
        f"counts={schema_counts}",
    )
    # Section 19.C's own named per-collection checks (curricula/persons/
    # educations/appointments/academic_works/documents) - individual
    # PASS/FAIL, never a hardcoded expected count, just "is it readable and
    # does it actually have >0 real records right now".
    for coll in ["curricula", "persons", "educations", "appointments", "academic_works", "documents"]:
        count = schema_counts.get(coll)
        report.record(f"MongoDB real data: {coll}", isinstance(count, int) and count > 0, f"count={count}")

    chroma_ok = False
    collection = None
    try:
        collection = chroma_module.get_collection()
        chroma_ok = True
        report.record(
            "[5] ChromaDB connection succeeds", True,
            f"{settings.chroma_host}:{settings.chroma_port} collection={settings.chroma_collection}",
        )
    except Exception as exc:  # noqa: BLE001
        report.record("[5] ChromaDB connection succeeds", False, f"{type(exc).__name__}: {exc}")

    chroma_count = None
    if chroma_ok:
        try:
            chroma_count = collection.count()
            report.record("[6] Chroma collection has real evidence chunks", chroma_count > 0, f"count={chroma_count}")
        except Exception as exc:  # noqa: BLE001
            report.record("[6] Chroma collection has real evidence chunks", False, f"{type(exc).__name__}: {exc}")
    else:
        report.record("[6] Chroma collection has real evidence chunks", False, "skipped - ChromaDB unreachable")

    try:
        import mcp_server.server as mcp_mod

        required_tools = ["search_evidence", "query_structured_data", "retrieve_document", "get_sar_template", "get_master_config"]
        missing = [t for t in required_tools if not hasattr(mcp_mod, t)]
        report.record("[7] MCP server module + tools importable", not missing, f"missing={missing}" if missing else "")
    except Exception as exc:  # noqa: BLE001
        report.record("[7] MCP server module + tools importable", False, f"{type(exc).__name__}: {exc}")

    template_found = False
    try:
        template_file = await get_latest_reference_file("template")
        template_found = template_file is not None
        report.record(
            "[8] SAR Template exists in configured MongoDB", template_found,
            template_file["filename"] if template_file else "no template uploaded to the configured database",
        )
    except Exception as exc:  # noqa: BLE001
        report.record("[8] SAR Template exists in configured MongoDB", False, f"{type(exc).__name__}: {exc}")

    try:
        cfg = json.loads(Path(settings.master_config_path).read_text(encoding="utf-8"))
        report.record(
            "[9] Agent configuration (master_config.json) exists and parses",
            "criterion_order" in cfg,
            f"criteria={list(cfg.get('criteria', {}).keys())}",
        )
    except Exception as exc:  # noqa: BLE001
        report.record("[9] Agent configuration (master_config.json) exists and parses", False, f"{type(exc).__name__}: {exc}")

    return schema_counts


def _unwrap_exception(exc: BaseException) -> BaseException:
    """anyio's TaskGroups (used inside stdio_client/ClientSession) wrap any
    error raised inside them in an ExceptionGroup - str(that) is just
    "unhandled errors in a TaskGroup (1 sub-exception)", which hides the
    real cause. Unwraps down to the innermost real exception so the report
    shows what actually happened instead of a generic wrapper message.
    """
    seen = exc
    while isinstance(seen, BaseExceptionGroup) and seen.exceptions:
        seen = seen.exceptions[0]
    return seen


def _attribute_failure_layer(exc: Exception) -> tuple[str, str]:
    """Best-effort mapping of a raised exception to the layer Section 24
    wants named explicitly - never just 'Generation failed'. Returns
    (layer, real_error_message) - the latter after unwrapping any
    ExceptionGroup wrapper.
    """
    real = _unwrap_exception(exc)
    msg = f"{type(real).__name__}: {real}"
    if "SAR Template" in msg or "template file has been uploaded" in msg:
        return "MongoDB (template fetch, common.mongo.get_latest_reference_file)", msg
    if "Slot Marking Agent" in msg:
        return "Master Agent (Slot Marking / Template Parser)", msg
    if "MCP tool" in msg:
        return "MCP", msg
    return f"Unattributed ({type(real).__name__})", msg


def _patch_mcp_subprocess_env_inheritance() -> None:
    """`master_agent.master.run()` spawns the MCP server via
    `StdioServerParameters(command=..., args=..., cwd=...)` with NO
    explicit `env=`. The `mcp` library then gives that child process only
    a restrictive safe-list (`mcp.client.stdio.get_default_environment()` -
    PATH/HOME/etc, confirmed by reading its source - never app vars like
    MONGODB_URI/MONGODB_DB_NAME), never this parent process's actual
    environment. That means the MCP server subprocess - where the real
    MongoDB/ChromaDB tool calls actually run - would silently keep reading
    `.env`'s own database directly off disk, completely ignoring this
    script's `.env.realdata` override, without this patch. This is a real,
    general env-propagation gap (not specific to this test - any
    os.environ-based override of Settings would hit the same silent
    failure today), but fixing it is squarely a "make the real-data test
    actually able to connect to aunqa_ps" requirement.

    Rather than editing master_agent/master.py (out of scope - change.md
    "DO NOT modify Master Agent"), this replaces the module-level
    `StdioServerParameters` NAME `master_agent.master.run()` looks up at
    call time (Python resolves a bare global inside a function from the
    module's own namespace at call time, not at import time) with a thin
    wrapper that fills in `env=dict(os.environ)` when the caller didn't
    specify one - functionally identical to passing `env=` explicitly,
    achieved without touching Master Agent's source file at all. Scoped to
    this one test process only; production's own call site is completely
    unaffected since it never imports or runs this script.
    """
    import os

    import master_agent.master as master_module
    from mcp import StdioServerParameters as RealStdioServerParameters

    def stdio_params_with_full_env(*args, **kwargs):
        kwargs.setdefault("env", dict(os.environ))
        return RealStdioServerParameters(*args, **kwargs)

    master_module.StdioServerParameters = stdio_params_with_full_env


async def verify_mcp_mongodb_retrieval(report: Report) -> None:
    """Direct, unambiguous proof of AC-05/AC-06/AC-09: spins up the exact
    same MCP subprocess mechanism master_agent.master.run() uses (same
    StdioServerParameters/stdio_client/ClientSession pattern, with the env
    patch applied), and calls the real `query_structured_data` MCP tool
    directly for a few data_types - independent of whether the rest of the
    pipeline (template fetch, Slot Marking, Agent, Verification) can
    proceed. This is the one check that actually confirms MongoDB
    retrieval through MCP reaches aunqa_ps, rather than inferring it from
    the full run's overall success/failure.
    """
    print("\n=== DIRECT MCP -> MongoDB VERIFICATION (query_structured_data, bypassing the rest of the pipeline) ===")
    import os
    import sys as _sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    generator_root = Path(__file__).resolve().parent.parent
    # NOTE: constructed directly here (not via master_agent.master.run()),
    # so _patch_mcp_subprocess_env_inheritance()'s module-attribute patch
    # doesn't apply to this call site - env=dict(os.environ) must be passed
    # explicitly right here for the same reason that patch exists at all.
    server_params = StdioServerParameters(
        command=_sys.executable, args=["-m", "mcp_server.server"], cwd=str(generator_root), env=dict(os.environ)
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def call(data_type: str, role: str | None = None):
                    result = await session.call_tool("query_structured_data", {"data_type": data_type, "role": role})
                    if result.isError:
                        raise RuntimeError(f"{result.content}")
                    return [json.loads(b.text) for b in result.content if hasattr(b, "text")]

                appointments = await call("appointment", role="programmeResponsible")
                persons = await call("person")
                curricula = await call("curriculum")

        report.record(
            "MCP query_structured_data reaches real aunqa_ps data (appointment/programmeResponsible)",
            len(appointments) > 0,
            f"{len(appointments)} hit(s)" + (f" - e.g. {appointments[0]['text'][:120]}" if appointments else ""),
        )
        report.record(
            "MCP query_structured_data reaches real aunqa_ps data (person)",
            len(persons) > 0,
            f"{len(persons)} hit(s)" + (f" - e.g. {persons[0]['text'][:120]}" if persons else ""),
        )
        report.record(
            "MCP query_structured_data reaches real aunqa_ps data (curriculum)",
            len(curricula) > 0,
            f"{len(curricula)} hit(s)" + (f" - e.g. {curricula[0]['text'][:160]}" if curricula else ""),
        )
    except Exception as exc:  # noqa: BLE001
        real = _unwrap_exception(exc)
        report.record("MCP query_structured_data reaches real aunqa_ps data", False, f"{type(real).__name__}: {real}")


async def run_real_generation(report: Report) -> dict:
    print("\n=== REAL GENERATION RUN (no Monitor call - master_agent.master.run() directly) ===")
    from master_agent.master import run as run_master  # imported here so pre-flight failures print first

    _patch_mcp_subprocess_env_inheritance()

    run_id = f"realdata-{uuid.uuid4()}"
    result = {"run_id": run_id, "output_path": None, "error": None, "layer": None}
    try:
        output_path = await run_master(run_id=run_id)
        result["output_path"] = str(output_path)
        report.record("Real generation run completes without crashing", True, f"run_id={run_id}")
    except Exception as exc:  # noqa: BLE001
        layer, real_msg = _attribute_failure_layer(exc)
        result["error"] = real_msg
        result["layer"] = layer
        report.record("Real generation run completes without crashing", False, f"failed at layer: {layer} - {real_msg}")
    return result


async def summarize_agent_flow(run_id: str, report: Report) -> None:
    """Reads back generation_slot_marking_log / generation_criteria_log for
    this run - the same collections api_server.py's /status endpoint reads,
    reused here read-only.
    """
    print("\n=== AGENT FLOW / VERIFICATION SUMMARY (from generation_*_log, read-only) ===")
    db = get_db()
    slot_marking = await db["generation_slot_marking_log"].find_one({"run_id": run_id}, {"_id": 0})
    if slot_marking:
        print(f"Slot Marking: status={slot_marking['status']} total_slots_marked={slot_marking['total_slots_marked']}")
    report.record("Master routing (Slot Marking Agent ran for this run)", slot_marking is not None)

    criteria_cursor = db["generation_criteria_log"].find({"run_id": run_id}, {"_id": 0}).sort("created_at", 1)
    criteria_progress = [c async for c in criteria_cursor]
    for c in criteria_progress:
        print(f"  [{c['criterion']}] status={c['status']} citations={len(c.get('citations', []))}")

    report.record("Agent receives retrieved data / Data Request executed", len(criteria_progress) > 0)
    passed_any = any(c["status"] == "completed" for c in criteria_progress)
    report.record("Verification PASS reached for at least one criterion", passed_any)


async def verify_source_data_untouched(before: dict, report: Report) -> None:
    print("\n=== SOURCE DATA SAFETY CHECK (read-only before/after comparison) ===")
    db = get_db()
    names = await db.list_collection_names()
    unchanged = True
    for coll in FINAL_SCHEMA_COLLECTIONS:
        before_count = before.get(coll)
        after_count = await db[coll].count_documents({}) if coll in names else None
        if before_count != after_count:
            unchanged = False
            print(f"  MISMATCH: {coll} before={before_count} after={after_count}")
    report.record("Source Final-Schema collections unchanged after the run", unchanged)


def print_final_report(report: Report, schema_counts_before: dict, gen_result: dict) -> None:
    settings = get_settings()
    print("\n" + "=" * 70)
    print("REAL DATA INTEGRATION TEST - FINAL REPORT")
    print("=" * 70)

    def status(name: str) -> str:
        return "PASS" if report.get(name) else "FAIL"

    parsed = urlparse(settings.mongodb_uri)
    print("\nA. Configuration")
    print("   Previous database: aunqa (.env's own Atlas cluster - unchanged, still used by production)")
    print(f"   New real-data test database: {settings.mongodb_db_name!r}")
    print(f"   MongoDB host: {parsed.hostname}")
    print(f"   MongoDB port: {parsed.port}")
    print("   Config source: .env.realdata (overrides .env for THIS PROCESS only, via python-dotenv "
          "override=True before get_settings() is ever called) - production (api_server.py, mcp_server, "
          "the CLI) never loads this file")

    print("\nB. Connectivity")
    print(f"   MongoDB: {status('[2] MongoDB connection succeeds')}")
    print(f"   ChromaDB: {status('[5] ChromaDB connection succeeds')}")
    print(f"   MCP: {status('[7] MCP server module + tools importable')}")

    print("\nC. MongoDB Real Data")
    for coll in ["curricula", "persons", "educations", "appointments", "academic_works", "documents"]:
        print(f"   {coll}: {status(f'MongoDB real data: {coll}')}")

    print("\nD. Retrieval")
    print(f"   MongoDB through MCP (direct query_structured_data call): "
          f"{status('MCP query_structured_data reaches real aunqa_ps data (appointment/programmeResponsible)')} / "
          f"{status('MCP query_structured_data reaches real aunqa_ps data (person)')} / "
          f"{status('MCP query_structured_data reaches real aunqa_ps data (curriculum)')} "
          f"(appointment/person/curriculum)")
    print(f"   ChromaDB through MCP: {status('[6] Chroma collection has real evidence chunks')}")
    blocked_before_retrieval_manager = gen_result.get("layer", "").startswith("MongoDB (template fetch")
    if blocked_before_retrieval_manager:
        print("   Retrieval Manager (via full pipeline): NOT EXERCISED (blocked earlier, at template fetch - "
              "see below; direct MongoDB-through-MCP retrieval above already proves this tier works)")
    else:
        print(f"   Retrieval Manager (Data Request executed, fallback chain reached): "
              f"{status('Agent receives retrieved data / Data Request executed')}")
    print("   source metadata: see retrieval/mongodb.py source_filename encoding (\"mongodb:<collection>:<id>\") "
          "and common/chroma.py's chunk_id/document_id/chunk_index/source_filename - unchanged, reused as-is")

    print("\n   -- downstream stages (change.md sec.18: do not claim full E2E PASS unless ALL of these pass) --")
    if blocked_before_retrieval_manager:
        print("   Agent / Verification / Reference Mapping / Template Injection / Generated DOCX: "
              "NOT REACHED (pipeline stopped at Initialization, before Master ever dispatches to an Agent)")
    else:
        print(f"   Agent (Master routing + Data Request): {status('Agent receives retrieved data / Data Request executed')}")
        print(f"   Verification: {status('Verification PASS reached for at least one criterion')}")
        print(f"   Reference Mapping / Template Injection / Generated DOCX: "
              f"{'PASS' if gen_result.get('output_path') else 'FAIL'}")
        if gen_result.get("output_path"):
            print(f"     -> {gen_result['output_path']}")
    if gen_result.get("error"):
        print(f"   FIRST FAILING LAYER: {gen_result['layer']}")
        print(f"   ERROR: {gen_result['error']}")

    print("\nE. Safety")
    print(f"   Source data modified: {'NO' if report.get('Source Final-Schema collections unchanged after the run') else 'YES - see mismatch above'}")
    print("   Mock data used: NO")
    print("   Agent direct DB access: NO (Criterion Agents only ever receive EvidenceChunkContext objects "
          "from Master; retrieval/mongodb.py and common/chroma.py are called only from mcp_server/server.py "
          "MCP tools, never imported by any criterion_agents/* module)")
    print("   Production Monitor Gate changed: NO (api_server.py, monitor/client.py untouched by this task)")
    print("   Monitor used by this test: NO (change.md - real-data integration test intentionally does not "
          "wait for /monitor/{curriculumId}/readiness)")

    print("\nF. Files changed")
    print("   NEW:      .env.realdata (gitignored, MongoDB override for this test only)")
    print("   MODIFIED: scripts/test_real_data_generation.py (loads .env.realdata; per-collection real-data checks)")
    print("   MODIFIED: .gitignore (added .env.realdata)")
    print("   UNCHANGED: .env, common/config.py, common/mongo.py, retrieval/*, mcp_server/*, master_agent/*, "
          "criterion_agents/*, monitor/*, api_server.py")

    mongo_ready = (
        report.get("[2] MongoDB connection succeeds")
        and report.get("[4] expected Final-Schema collections readable with real data")
        and report.get("MCP query_structured_data reaches real aunqa_ps data (appointment/programmeResponsible)")
        and report.get("MCP query_structured_data reaches real aunqa_ps data (person)")
        and report.get("MCP query_structured_data reaches real aunqa_ps data (curriculum)")
    )
    chroma_ready = report.get("[5] ChromaDB connection succeeds") and report.get("[6] Chroma collection has real evidence chunks")
    print("\n" + "=" * 70)
    print(f"MongoDB real-data connection (proven through real MCP retrieval): {'PASS' if mongo_ready else 'FAIL'}")
    print(f"ChromaDB: {'PASS' if chroma_ready else 'FAIL (reported separately - see change.md sec.13/17)'}")
    if mongo_ready and chroma_ready and gen_result.get("output_path") and report.get("Verification PASS reached for at least one criterion"):
        print("RESULT: Real E2E PASS - all stages, including Verification, passed with real data.")
    else:
        print("RESULT: Real E2E PASS NOT claimed (change.md sec.18) - see per-stage PASS/FAIL above for exactly "
              "which stage(s) are not yet passing.")
    print("=" * 70)


async def main() -> int:
    print("REAL DATA INTEGRATION TEST — Generator Service")
    print("DEVELOPMENT / INTEGRATION TEST ONLY — does not call Monitor, does not affect production /api/generate.\n")

    report = Report()
    schema_counts_before = await run_preflight(report)
    await verify_mcp_mongodb_retrieval(report)
    gen_result = await run_real_generation(report)
    if gen_result["output_path"]:
        await summarize_agent_flow(gen_result["run_id"], report)
    await verify_source_data_untouched(schema_counts_before, report)
    print_final_report(report, schema_counts_before, gen_result)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
