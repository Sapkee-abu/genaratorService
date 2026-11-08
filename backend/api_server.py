"""HTTP API wrapping the Generator Service's CLI (master_agent.master.run)
so the Import Service frontend's "Generate SAR" button has something to
call. This is intentionally a separate process/file from both the CLI
entrypoint and the MCP server - nothing else in the Generator Service
depends on it.

To disable the web-triggered generation feature entirely: just don't run
this process. Nothing elsewhere references api_server.py, so the CLI
(`python -m master_agent.master`) and everything it depends on keeps working
exactly as before with this file untouched or even deleted.

Run: uvicorn api_server:app --port 8010
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api.routes import register_routes
from common.config import get_settings
from common.logging_repo import LegacyGeneratedDocumentsError, log_monitor_event
from common.mongo import get_db
from master_agent.master import run as run_master
from monitor.client import MonitorClient
from monitor.schemas import MonitorReadinessStatus
from api.versioning import create_download_snapshot

settings = get_settings()
_monitor_client = MonitorClient()
_log = logging.getLogger(__name__)

# Monitor readiness status -> the MONITOR_* log event name (change.md sec.37).
_MONITOR_LOG_EVENT_BY_STATUS = {
    MonitorReadinessStatus.NOT_READY: "MONITOR_NOT_READY",
    MonitorReadinessStatus.MONITOR_UNAVAILABLE: "MONITOR_UNAVAILABLE",
    MonitorReadinessStatus.INVALID_RESPONSE: "MONITOR_INVALID_RESPONSE",
}


class GenerateRequest(BaseModel):
    """`curriculum_id` is optional at the FastAPI/parsing layer only so a
    request with no body doesn't 422 before reaching our own, more
    descriptive "blocked" response - it is still required in practice to
    check Monitor readiness (see start_generate()).
    """

    curriculum_id: str | None = None

app = FastAPI(title="AUN-QA Generator Service API")


@app.exception_handler(LegacyGeneratedDocumentsError)
async def _legacy_generated_documents(_request, exc: LegacyGeneratedDocumentsError):
    """The database still has the old array-based generated_documents document: say so, don't show an empty History."""
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=503, content={"detail": {"status": "migration_required", "message": str(exc)}})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # the browser can only read X-Document-Version (the backend-assigned
    # Version Snapshot number) from a cross-origin download if it's exposed
    expose_headers=["X-Document-Version"],
)

# In-memory job tracking: fine for a single-user local tool with one
# generation run at a time (guarded by _active_job_id below). Not durable
# across an api_server.py restart - Mongo (generation_criteria_log /
# generation_slot_marking_log) is the durable record of what happened.
_jobs: dict[str, dict] = {}
_active_job_id: str | None = None

# fix.md sec.13 - new Web workspace endpoints (preview/draft/history/
# reference), mounted alongside the 3 existing endpoints above/below,
# which stay exactly as they were.
register_routes(app, _jobs)


@app.on_event("startup")
async def restore_portal_jobs():
    if settings.monitor_contract != "aunqa-portal":
        return
    async for record in get_db()["portal_generation_jobs"].find({}):
        job_id = record.pop("_id")
        if record.get("status") == "running":
            record.update(status="failed", error="Generation interrupted by service restart; please retry")
            await get_db()["portal_generation_jobs"].replace_one({"_id": job_id}, {"_id": job_id, **record})
        _jobs[job_id] = record


async def persist_portal_job(job_id):
    if settings.monitor_contract == "aunqa-portal":
        await get_db()["portal_generation_jobs"].replace_one(
            {"_id": job_id}, {"_id": job_id, **_jobs[job_id]}, upsert=True)


def _new_job(mode: str) -> str:
    """Registers a generation job and marks it active. Shared by the production route
    (after its Monitor gate) and the development route (fix.md: single Generator core -
    only the entry gate differs). `mode` is recorded so a job's origin is always visible."""
    global _active_job_id
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "output_path": None, "error": None, "mode": mode}
    _active_job_id = job_id
    return job_id


def _start_job(job_id: str) -> None:
    asyncio.create_task(_execute(job_id))  # -> the real master_agent.master.run(run_id=job_id)


def _root_exception(exc: BaseException) -> BaseException:
    """Return the useful cause hidden by anyio/MCP TaskGroup wrappers."""
    current = exc
    seen: set[int] = set()
    while id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, BaseExceptionGroup) and current.exceptions:
            current = current.exceptions[0]
            continue
        last_attempt = getattr(current, "last_attempt", None)
        nested = last_attempt.exception() if last_attempt is not None else None
        if isinstance(nested, BaseException):
            current = nested
            continue
        if isinstance(current.__cause__, BaseException):
            current = current.__cause__
            continue
        break
    return current


async def _execute(job_id: str) -> None:
    global _active_job_id
    try:
        output_path = await run_master(run_id=job_id)
        if settings.monitor_contract == "aunqa-portal":
            logs = await get_db()["generation_criteria_log"].find({"run_id": job_id}).to_list(None)
            failures = [r for r in logs if r.get("status", "").startswith("failed")]
            if failures or not any(r.get("status") == "completed" for r in logs):
                raise RuntimeError("Document generation did not complete verified sections; inspect generation logs")
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["output_path"] = str(output_path)
    except Exception as exc:  # noqa: BLE001
        real = _root_exception(exc)
        _log.exception("Generation job failed job_id=%s root=%s: %s", job_id, type(real).__name__, real)
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = f"{type(real).__name__}: {real}"
    finally:
        _active_job_id = None
        await persist_portal_job(job_id)


@app.get("/api/health")
async def health():
    await get_db().command("ping")
    return {"status": "ok", "generationConfigured": bool(settings.gemini_api_key.strip()),
            "verificationEnabled": True, "developmentMode": settings.generator_dev_mode}


@app.post("/api/generate")
async def start_generate(body: GenerateRequest | None = None):
    """Generator Gate (change.md "Fix and align Generator Service with the
    real Monitor Readiness Contract"): GET /monitor/{curriculumId}/readiness
    -> MonitorClient -> generatedReady == true? -> existing Generate flow,
    unchanged from this point on. Any other status (NOT_READY /
    MONITOR_UNAVAILABLE / INVALID_RESPONSE) stops here - Master, Criterion
    Agents, Retrieval Manager and MCP are never called. Generator never
    computes readiness itself (no PS/threshold/role/guideline checks, no
    ps_requirements query) - it only relays the one boolean Monitor returned.

    This gate only ever runs in response to a real User POST /api/generate
    call - Monitor reporting generatedReady=true never by itself triggers
    generation (no poller/webhook calls run_master anywhere in this
    codebase); the User must still click Generate.

    Real Monitor Service is PLUG/WAIT: with MONITOR_SERVICE_URL unset, every
    call here correctly reports MONITOR_UNAVAILABLE and stops - this is the
    honest state, not a bypass.
    """
    global _active_job_id
    if not settings.gemini_api_key.strip():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured; generation is unavailable")
    if _active_job_id is not None:
        raise HTTPException(status_code=409, detail="A generation run is already in progress")

    curriculum_id = body.curriculum_id if body else None
    if not curriculum_id:
        await log_monitor_event("GENERATION_BLOCKED", None, detail="curriculum_id missing from /api/generate request")
        raise HTTPException(
            status_code=400,
            detail={
                "status": "blocked",
                "reason": "MISSING_CURRICULUM_ID",
                "message": "curriculum_id is required to check Monitor readiness before generating",
            },
        )

    await log_monitor_event("MONITOR_READINESS_REQUEST", curriculum_id)
    readiness = await _monitor_client.check_readiness(curriculum_id)
    await log_monitor_event(
        "MONITOR_READINESS_RESPONSE", curriculum_id, detail=f"status={readiness.status.value} {readiness.detail}"
    )

    if readiness.status != MonitorReadinessStatus.READY:
        await log_monitor_event(_MONITOR_LOG_EVENT_BY_STATUS[readiness.status], curriculum_id, detail=readiness.detail)
        await log_monitor_event("GENERATION_BLOCKED", curriculum_id, detail=readiness.status.value)
        raise HTTPException(
            status_code=412,
            detail={
                "status": "blocked",
                "reason": readiness.status.value,
                "message": readiness.detail or "Monitor did not report generatedReady=true",
            },
        )

    await log_monitor_event("MONITOR_READY", curriculum_id, detail=readiness.detail)

    # ---------- existing Generate flow, unchanged from here down ----------
    # Readiness awaits may interleave concurrent requests. Recheck immediately before reserving the job.
    if _active_job_id is not None:
        raise HTTPException(status_code=409, detail="A generation run is already in progress")
    job_id = _new_job("production")
    try:
        await persist_portal_job(job_id)
        await log_monitor_event("GENERATION_STARTED_AFTER_READY", curriculum_id, run_id=job_id)
    except Exception:
        _jobs[job_id].update(status="failed", error="Unable to persist generation job")
        _active_job_id = None
        raise HTTPException(status_code=503, detail="Unable to persist generation job") from None
    _start_job(job_id)
    return {"job_id": job_id, "status": "running"}


if settings.generator_dev_mode:
    if settings.monitor_service_url:
        raise RuntimeError(
            "GENERATOR_DEV_MODE=true must not be combined with a configured MONITOR_SERVICE_URL: "
            "the development route bypasses the Monitor gate and must never run next to a live one"
        )

    @app.post("/api/dev/generate")
    async def dev_generate():
        """DEVELOPMENT/TEST ONLY - same Generator core as POST /api/generate (_new_job ->
        _start_job -> _execute -> master_agent.master.run: real Master, Criterion Agents,
        Retrieval Manager, MCP, ChromaDB, MongoDB, Verification, Reference Mapping, Template
        Injection), but without the Monitor READY gate. Not registered unless
        GENERATOR_DEV_MODE=true. Status/preview/draft/download/history/reference are the
        ordinary shared routes, so the whole Web lifecycle is identical to production."""
        if _active_job_id is not None:
            raise HTTPException(status_code=409, detail="A generation run is already in progress")
        job_id = _new_job("development")
        print(f"[DEV] /api/dev/generate: Monitor gate bypassed (GENERATOR_DEV_MODE) - real Master starting, job={job_id}", flush=True)
        _start_job(job_id)
        return {"job_id": job_id, "status": "running", "mode": "development"}


@app.get("/api/generate/{job_id}/status")
async def get_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")

    db = get_db()
    slot_marking = await db["generation_slot_marking_log"].find_one({"run_id": job_id}, {"_id": 0})
    criteria_cursor = db["generation_criteria_log"].find({"run_id": job_id}, {"_id": 0}).sort("created_at", 1)
    criteria_progress = [c async for c in criteria_cursor]

    return {
        "job_id": job_id,
        "status": job["status"],
        "error": job["error"],
        "mode": job.get("mode", "production"),
        "slot_marking": slot_marking,
        "criteria_progress": criteria_progress,
    }


@app.get("/api/generate/{job_id}/download")
async def download(job_id: str):
    """Download = Version Snapshot (fix.md sec.6). Resolves the current
    document state (latest saved Current Draft's edited DOCX, else the
    Current Generated Artifact), freezes it as a NEW immutable snapshot in
    generated_documents, and returns that snapshot with the backend-assigned
    version in `X-Document-Version`. Each explicit Download creates exactly
    one new Version."""
    job = _jobs.get(job_id)
    if job is None or job["status"] != "completed":
        raise HTTPException(status_code=404, detail="Result not available")

    snapshot_path, version = await create_download_snapshot(job_id, job)
    return FileResponse(
        snapshot_path,
        filename=f"SAR_v{version}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"X-Document-Version": str(version)},
    )
