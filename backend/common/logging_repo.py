from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from common.mongo import get_db

COLLECTION = "generation_criteria_log"
SLOT_MARKING_COLLECTION = "generation_slot_marking_log"
MONITOR_LOG_COLLECTION = "generation_monitor_log"
GENERATED_DOCUMENTS_COLLECTION = "generated_documents"


async def log_slot_marking(run_id: str, status: str, marked_slots: list[dict[str, Any]]) -> None:
    """addfeature.md: records the Slot Marking Agent's JSON result for this run."""
    db = get_db()
    await db[SLOT_MARKING_COLLECTION].insert_one(
        {
            "run_id": run_id,
            "status": status,
            "total_slots_marked": len(marked_slots),
            "marked_slots": marked_slots,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def log_criterion(
    run_id: str,
    criterion: str,
    status: str,
    citations: list[dict[str, Any]],
    sections: list[dict[str, Any]] | None = None,
    trace: dict[str, Any] | None = None,
) -> None:
    """mainpromt.md sec.44: after a criterion passes verification + injection,
    record its status and citation mapping so retrieved evidence can always
    be traced back through to what was actually written.

    `sections` (fix.md sec.20 "Reference / Traceability API") is optional
    and purely additive - existing readers of this collection (none exist
    beyond this task's new reference API) are unaffected whether it's
    present or not. Holds the full AgentResponse.sections (narrative +
    table, with each table row's own citations) so the web Reference API
    can show per-field/per-row source detail, not just the top-level
    narrative citation list `citations` already carried.
    """
    db = get_db()
    document = {
        "run_id": run_id,
        "criterion": criterion,
        "status": status,
        "citations": citations,
        "created_at": datetime.now(timezone.utc),
    }
    if sections is not None:
        document["sections"] = sections
    if trace is not None:
        # additive audit record (fix.md "retrieval trace"): per attempt, what
        # was requested / which tier served it / verification verdict
        document["trace"] = trace
    await db[COLLECTION].insert_one(document)


async def log_monitor_event(
    event: str,
    curriculum_id: str | None,
    detail: str = "",
    run_id: str | None = None,
) -> None:
    """Monitor Integration log (change.md sec.37) - `event` is one of
    MONITOR_READINESS_REQUEST / MONITOR_READINESS_RESPONSE / MONITOR_READY /
    MONITOR_NOT_READY / MONITOR_UNAVAILABLE / MONITOR_INVALID_RESPONSE /
    GENERATION_STARTED_AFTER_READY / GENERATION_BLOCKED.

    Never pass a token/API key/password/secret in `detail` - this is a hard
    rule (change.md sec.37); callers must only pass human-readable status
    text, never raw headers or credentials.
    """
    db = get_db()
    await db[MONITOR_LOG_COLLECTION].insert_one(
        {
            "event": event,
            "curriculum_id": curriculum_id,
            "detail": detail,
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def log_slot_map(run_id: str, slot_map: dict[str, Any]) -> None:
    """fix.md sec.11 - additive `slot_map` field on this run's existing
    generation_slot_marking_log document (which block/row of the final DOCX
    holds which slot). Nothing already in that document is changed."""
    db = get_db()
    await db[SLOT_MARKING_COLLECTION].update_one({"run_id": run_id}, {"$set": {"slot_map": slot_map}})


async def get_slot_map(run_id: str) -> dict[str, Any] | None:
    db = get_db()
    record = await db[SLOT_MARKING_COLLECTION].find_one({"run_id": run_id}, {"_id": 0, "slot_map": 1})
    return record.get("slot_map") if record else None


class LegacyGeneratedDocumentsError(RuntimeError):
    """generated_documents still holds the OLD single-document / generatedFiles[] shape."""


VERSION_INDEX_NAME = "uq_generated_documents_curriculum_version"
_version_index_ready: set[str] = set()


async def ensure_version_index(db) -> None:
    """Non-destructive + idempotent: one Version document per (curriculumId, version). Partial on
    `version` existing so a not-yet-migrated legacy document (which has no `version`) can never
    collide with it. This is what makes a duplicate version number impossible even if two
    Downloads race."""
    key = f"{id(db)}"
    if key in _version_index_ready:
        return
    await db[GENERATED_DOCUMENTS_COLLECTION].create_index(
        [("curriculumId", 1), ("version", 1)],
        unique=True,
        name=VERSION_INDEX_NAME,
        partialFilterExpression={"version": {"$exists": True}},
    )
    _version_index_ready.add(key)


async def assert_migrated(db) -> None:
    """History / Preview / Download / Reference / Download-snapshot all read the per-Version shape. If
    the legacy array document is still there they would silently show an empty History, so refuse
    loudly instead. The migration is an explicit script (never run automatically at startup)."""
    legacy = await db[GENERATED_DOCUMENTS_COLLECTION].find_one({"generatedFiles": {"$exists": True}}, {"_id": 1})
    if legacy is not None:
        raise LegacyGeneratedDocumentsError(
            "generated_documents still contains the legacy array-based document (generatedFiles[]). "
            "Run the explicit migration first: python scripts/migrate_generated_documents.py"
        )


async def current_curriculum_id() -> ObjectId | None:
    """The single curriculum this system supports (same resolution as GET /api/curriculum)."""
    doc = await get_db()["curricula"].find_one({}, {"_id": 1})
    return doc["_id"] if doc else None


async def list_version_docs(curriculum_id: ObjectId | None = None) -> list[dict]:
    """Version documents of a curriculum, newest version first."""
    db = get_db()
    await assert_migrated(db)
    curriculum_id = curriculum_id or await current_curriculum_id()
    if curriculum_id is None:
        return []
    cursor = db[GENERATED_DOCUMENTS_COLLECTION].find({"curriculumId": curriculum_id, "version": {"$exists": True}}).sort("version", -1)
    return [doc async for doc in cursor]


async def get_version_doc(version: int, curriculum_id: ObjectId | None = None) -> dict | None:
    """The Version document for exactly (curriculumId, version) - never "the latest"."""
    db = get_db()
    await assert_migrated(db)
    curriculum_id = curriculum_id or await current_curriculum_id()
    if curriculum_id is None:
        return None
    return await db[GENERATED_DOCUMENTS_COLLECTION].find_one({"curriculumId": curriculum_id, "version": version})


async def save_version_snapshot(
    curriculum_id: str,
    file_name: str,
    file_type: str,
    path: str,
    run_id: str,
    user_edits: list[dict[str, Any]],
) -> int:
    """Creates ONE immutable Version Snapshot = ONE `generated_documents` document (fix.md Part C).
    Called ONLY by Download - never by Generate or Save.

    Shape: {_id, curriculumId, fileName, fileType, version, path, timestamp, runId, source:"download",
    userEdits}. Nothing ever updates or deletes an existing Version document - a Download only INSERTS.

    The next version is read from the database (max existing `version` for the curriculum + 1) - no
    in-memory counter - and the unique (curriculumId, version) index turns a racing duplicate into a
    DuplicateKeyError, on which the number is recomputed. Version 9 follows Version 8, never Version 1.
    """
    from pymongo.errors import DuplicateKeyError

    db = get_db()
    await ensure_version_index(db)
    await assert_migrated(db)
    curriculum_object_id = ObjectId(curriculum_id) if not isinstance(curriculum_id, ObjectId) else curriculum_id
    collection = db[GENERATED_DOCUMENTS_COLLECTION]

    for _attempt in range(10):
        last = await collection.find_one(
            {"curriculumId": curriculum_object_id, "version": {"$exists": True}}, sort=[("version", -1)], projection={"version": 1}
        )
        version = (last["version"] if last else 0) + 1
        try:
            await collection.insert_one(
                {
                    "curriculumId": curriculum_object_id,
                    "fileName": file_name,
                    "fileType": file_type,
                    "version": version,
                    "path": path,
                    "timestamp": datetime.now(timezone.utc),
                    "runId": run_id,
                    "source": "download",
                    "userEdits": user_edits,
                }
            )
            return version
        except DuplicateKeyError:
            continue  # another Download took this number first - recompute from the database
    raise RuntimeError("could not allocate a unique version number for generated_documents")
