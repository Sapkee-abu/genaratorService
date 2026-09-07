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
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from common.config import get_settings
from common.mongo import get_db
from master_agent.master import run as run_master

settings = get_settings()

app = FastAPI(title="AUN-QA Generator Service API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job tracking: fine for a single-user local tool with one
# generation run at a time (guarded by _active_job_id below). Not durable
# across an api_server.py restart - Mongo (generation_criteria_log /
# generation_slot_marking_log) is the durable record of what happened.
_jobs: dict[str, dict] = {}
_active_job_id: str | None = None


async def _execute(job_id: str) -> None:
    global _active_job_id
    try:
        output_path = await run_master(run_id=job_id)
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["output_path"] = str(output_path)
    except Exception as exc:  # noqa: BLE001
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(exc)
    finally:
        _active_job_id = None


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/generate")
async def start_generate():
    global _active_job_id
    if _active_job_id is not None:
        raise HTTPException(status_code=409, detail="A generation run is already in progress")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "output_path": None, "error": None}
    _active_job_id = job_id
    asyncio.create_task(_execute(job_id))
    return {"job_id": job_id, "status": "running"}


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
        "slot_marking": slot_marking,
        "criteria_progress": criteria_progress,
    }


@app.get("/api/generate/{job_id}/download")
async def download(job_id: str):
    job = _jobs.get(job_id)
    if job is None or job["status"] != "completed":
        raise HTTPException(status_code=404, detail="Result not available")
    path = Path(job["output_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file no longer exists")
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
