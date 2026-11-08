"""Web draft persistence (fix.md sec.15) - the Current Draft, completely
separate from `generated_documents` (Version Snapshots, created only by
Download) and from Source Data. Save here NEVER creates a version, NEVER
adds a generated_documents Version document, and NEVER touches persons/
educations/appointments/academic_works/documents.

One document per job in `generation_drafts`:
  html          current draft HTML (canonical re-render of the edited DOCX)
  docx_path     the edited DOCX artifact Download will snapshot
  changes       elements changed vs the generated DOCX (ElementChange dicts)
  original_html the generated document's HTML, captured once on first save
  updated_at
"""

from __future__ import annotations

from datetime import datetime, timezone

from common.mongo import get_db

DRAFTS_COLLECTION = "generation_drafts"


async def save_draft(
    job_id: str,
    html: str,
    docx_path: str,
    changes: list[dict],
    original_html: str | None = None,
) -> str:
    """`original_html` is captured once (first save, `$setOnInsert`) and never
    overwritten - the stable baseline of what generation produced."""
    db = get_db()
    now = datetime.now(timezone.utc)
    set_on_insert = {"job_id": job_id}
    if original_html is not None:
        set_on_insert["original_html"] = original_html
    await db[DRAFTS_COLLECTION].update_one(
        {"job_id": job_id},
        {
            "$set": {"html": html, "docx_path": docx_path, "changes": changes, "updated_at": now},
            "$setOnInsert": set_on_insert,
        },
        upsert=True,
    )
    return now.isoformat()


async def get_draft_html(job_id: str) -> str | None:
    db = get_db()
    record = await db[DRAFTS_COLLECTION].find_one({"job_id": job_id}, {"_id": 0, "html": 1})
    return record["html"] if record else None


async def get_draft_record(job_id: str) -> dict | None:
    db = get_db()
    return await db[DRAFTS_COLLECTION].find_one(
        {"job_id": job_id},
        {"_id": 0, "html": 1, "original_html": 1, "docx_path": 1, "changes": 1, "updated_at": 1},
    )
