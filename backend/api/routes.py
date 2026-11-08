"""Web workspace API routes (preview/draft/history/reference/curriculum/
template) - kept separate from api_server.py's Generate/status/download
endpoints. Mounted into the same FastAPI `app` via an APIRouter
(api_server.py::app.include_router), not a second competing server.

Lifecycle: Generate -> Current Generated Artifact; PUT draft -> Current
Draft (edited DOCX, no Version); Download (api_server.py) -> Version
Snapshot in generated_documents; /api/history* read those snapshots only.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import docx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from api.draft_store import get_draft_html, get_draft_record, save_draft
from api.versioning import drafts_dir
from common.logging_repo import get_slot_map, list_version_docs
from common.mongo import get_latest_template_metadata
from document.docx_edit import UnsupportedEditError, apply_html_to_docx
from document.docx_to_html import document_to_html
from reference.traceability_api import (
    build_reference_tree,
    get_latest_version,
    get_run_id_for_version,
    get_version_entry,
    get_version_path,
)

router = APIRouter()


def _get_job_or_404(jobs: dict, job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job


def register_routes(app, jobs: dict) -> None:
    """`jobs` is api_server.py's existing in-memory `_jobs` dict - reused
    as-is (not a second job-tracking mechanism) so preview/draft can find
    a completed job's output_path.
    """

    @router.get("/api/curriculum")
    async def get_curriculum():
        """fix.md sec.4 - the single curriculum this system supports
        (change.md "single-curriculum system"). Real `curricula` fields
        only (curriculumName/_id) - no fabricated program/degree fields
        the real schema doesn't have (Dataschema.md sec.1)."""
        from common.mongo import get_db

        db = get_db()
        if await db["curricula"].count_documents({}) > 1:
            raise HTTPException(status_code=409, detail="Generator supports one curriculum; multiple curricula require explicit scoping before generation")
        doc = await db["curricula"].find_one({})
        if doc is None:
            raise HTTPException(status_code=404, detail="No curriculum found in curricula collection")
        return {
            "id": str(doc["_id"]),
            "code": doc.get("curriculumCode", ""),
            "name": doc.get("curriculumName", ""),
        }

    @router.get("/api/template/latest")
    async def get_latest_template():
        """fix.md sec.5 - reuses common.mongo.get_latest_template_metadata()
        unchanged (the exact `find_one({}, sort=[("version", -1)])` rule
        already used by the real generation pipeline) - not a second
        implementation, no caching, no hardcoded version."""
        metadata = await get_latest_template_metadata()
        if metadata is None:
            raise HTTPException(status_code=404, detail="No template document exists in template_ps yet")
        return {"version": metadata["version"], "fileName": metadata["filename"]}

    async def _render_html(path: Path, run_id: str | None, user_edits: list[dict] | None = None) -> str:
        """DOCX -> HTML with stable element ids; `data-slot-id`/
        `data-reference-id` are attached only where the run's slot_map/
        Reference items really exist (older runs simply have none)."""
        document = docx.Document(str(path))
        slot_map = await get_slot_map(run_id) if run_id else None
        reference_ids = None
        if slot_map:
            reference_ids = set((await build_reference_tree(run_id, user_edits))["items"].keys())
        return document_to_html(document, slot_map=slot_map, reference_ids=reference_ids)

    async def _render_original_html(job: dict, job_id: str) -> str:
        path = Path(job["output_path"])
        if not path.exists():
            raise HTTPException(status_code=404, detail="Output file no longer exists")
        return await _render_html(path, job_id)

    @router.get("/api/generate/{job_id}/preview")
    async def preview(job_id: str):
        job = _get_job_or_404(jobs, job_id)
        if job["status"] != "completed" or not job["output_path"]:
            raise HTTPException(status_code=404, detail="Document not ready for preview")

        draft_html = await get_draft_html(job_id)
        if draft_html is not None:
            return {"html": draft_html, "fromDraft": True}

        return {"html": await _render_original_html(job, job_id), "fromDraft": False}

    @router.put("/api/generate/{job_id}/draft")
    async def put_draft(job_id: str, body: dict):
        """Save = Current Draft only (never a Version). The saved HTML is
        applied onto a copy of the generated DOCX (document.docx_edit) so
        Download can serve an edited DOCX. If the edit can't be mapped back
        safely -> 422 and NOTHING is saved (the previous draft, if any,
        stays exactly as it was)."""
        job = _get_job_or_404(jobs, job_id)
        html = body.get("html")
        if not isinstance(html, str):
            raise HTTPException(status_code=422, detail="body.html (string) is required")
        if job["status"] != "completed" or not job["output_path"]:
            raise HTTPException(status_code=409, detail="Document not ready - generation has not completed")

        base_path = Path(job["output_path"])
        if not base_path.exists():
            raise HTTPException(status_code=404, detail="Output file no longer exists")

        # unique file per save: the previous draft DOCX stays valid until the
        # new record is committed, so a failure mid-save can't leave the
        # draft record pointing at a half-written/overwritten file
        new_docx = drafts_dir() / f"SAR_{job_id}.draft-{uuid.uuid4().hex[:8]}.docx"
        try:
            changes = apply_html_to_docx(base_path, html, new_docx)
        except UnsupportedEditError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "unsupported_edit",
                    "message": "การแก้ไขนี้แปลงกลับเป็น DOCX อย่างปลอดภัยไม่ได้ - draft ไม่ถูกบันทึก: "
                    + "; ".join(exc.problems),
                    "problems": exc.problems,
                },
            ) from exc

        try:
            previous = await get_draft_record(job_id)
            original_html = await _render_original_html(job, job_id) if previous is None else None
            canonical_html = await _render_html(new_docx, job_id)
            saved_at = await save_draft(
                job_id, canonical_html, str(new_docx), [c.to_dict() for c in changes], original_html=original_html
            )
        except Exception:
            new_docx.unlink(missing_ok=True)
            raise

        if previous and previous.get("docx_path") and previous["docx_path"] != str(new_docx):
            try:
                os.remove(previous["docx_path"])
            except OSError:
                pass
        return {"savedAt": saved_at}

    @router.get("/api/history/{version}/preview")
    async def preview_version(version: int):
        path_str = await get_version_path(version)
        if path_str is None:
            raise HTTPException(status_code=404, detail=f"Version {version} not found")
        path = Path(path_str)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Output file no longer exists for this version")
        entry = await get_version_entry(version)
        run_id = (entry.get("runId") if entry else None) or await get_run_id_for_version(version)
        return {"html": await _render_html(path, run_id, entry.get("userEdits") if entry else None)}

    @router.get("/api/history/{version}/download")
    async def download_version(version: int):
        path_str = await get_version_path(version)
        if path_str is None:
            raise HTTPException(status_code=404, detail=f"Version {version} not found")
        path = Path(path_str)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Output file no longer exists for this version")
        return FileResponse(
            path,
            filename=path.name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    @router.get("/api/history")
    async def get_history():
        """One entry per Version document (generated_documents: one document per Version), newest first.
        Same response shape the frontend already consumed."""
        docs = await list_version_docs()
        if not docs:
            return {"fileName": None, "versions": []}
        versions = [
            {"version": doc["version"], "timestamp": doc["timestamp"].isoformat(), "fileType": doc.get("fileType", "docx")}
            for doc in docs
        ]
        return {"fileName": docs[0].get("fileName"), "versions": versions}

    @router.get("/api/reference")
    async def get_reference(version: int | None = Query(default=None)):
        target_version = version if version is not None else await get_latest_version()
        if target_version is None:
            return {"criterion": "root", "nodes": []}

        run_id = await get_run_id_for_version(target_version)
        if run_id is None:
            raise HTTPException(status_code=404, detail=f"Version {target_version} not found")

        entry = await get_version_entry(target_version)
        result = await build_reference_tree(run_id, entry.get("userEdits") if entry else None)
        return result["tree"]

    @router.get("/api/reference/item/{item_id}")
    async def get_reference_item(item_id: str, version: int | None = Query(default=None)):
        target_version = version if version is not None else await get_latest_version()
        if target_version is None:
            raise HTTPException(status_code=404, detail="No generated document versions exist yet")

        run_id = await get_run_id_for_version(target_version)
        if run_id is None:
            raise HTTPException(status_code=404, detail=f"Version {target_version} not found")

        entry = await get_version_entry(target_version)
        result = await build_reference_tree(run_id, entry.get("userEdits") if entry else None)
        item = result["items"].get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"No reference item '{item_id}' for version {target_version}")
        return item

    app.include_router(router)
