"""Download = Version Snapshot (fix.md sec.1/6/19).

The single place a Version is created. Resolves the current document state
(latest saved Current Draft's edited DOCX if one exists, otherwise the
Current Generated Artifact), freezes a copy of it as an immutable snapshot
file, freezes the field-level User Edit list, and appends ONE element to
a new generated_documents document (one per Version) (common.logging_repo.save_version_
snapshot). The backend alone assigns the version number.

Every call creates a NEW snapshot (an explicit Download is an explicit
"take a Version" action - fix.md sec.6). The snapshot file is a copy with a
unique name, so it can never be overwritten by a later Generate/Save/
Download and older versions' files are never touched.
"""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from api.draft_store import get_draft_record
from common.config import get_settings
from common.logging_repo import save_version_snapshot
from common.mongo import get_db
from document.docx_edit import ElementChange
from reference.user_edits import build_user_edits


def versions_dir() -> Path:
    return Path(get_settings().output_dir) / "versions"


def drafts_dir() -> Path:
    return Path(get_settings().output_dir) / "drafts"


async def create_download_snapshot(job_id: str, job: dict) -> tuple[Path, int]:
    generated_path = Path(job["output_path"])
    if not generated_path.exists():
        raise HTTPException(status_code=404, detail="Output file no longer exists")

    source_path = generated_path
    changes: list[ElementChange] = []
    draft = await get_draft_record(job_id)
    if draft and draft.get("docx_path"):
        draft_path = Path(draft["docx_path"])
        if not draft_path.exists():
            raise HTTPException(status_code=409, detail="Saved draft document is missing - save the draft again")
        source_path = draft_path
        changes = [ElementChange.from_dict(c) for c in draft.get("changes", [])]

    db = get_db()
    curriculum = await db["curricula"].find_one({}, {"_id": 1})
    if curriculum is None:
        raise HTTPException(status_code=404, detail="No curriculum found in curricula collection")
    curriculum_id = str(curriculum["_id"])

    user_edits = await build_user_edits(job_id, changes)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    snapshot_path = versions_dir() / f"SAR_{job_id}_{stamp}_{uuid.uuid4().hex[:8]}.docx"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, snapshot_path)

    try:
        version = await save_version_snapshot(
            curriculum_id=curriculum_id,
            file_name=f"SAR_{curriculum_id}.docx",
            file_type="docx",
            path=str(snapshot_path),
            run_id=job_id,
            user_edits=user_edits,
        )
    except Exception:
        snapshot_path.unlink(missing_ok=True)
        raise
    return snapshot_path, version
