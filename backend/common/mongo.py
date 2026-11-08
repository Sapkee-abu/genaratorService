from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket

from common.config import get_settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None
_gridfs_bucket: AsyncIOMotorGridFSBucket | None = None

REFERENCE_COLLECTIONS = {
    "example": "examples",
    "guideline": "guidelines",
}

# The real deployment doesn't use the `templates` + `reference_files` GridFS
# mechanism `get_latest_reference_file` still serves "example"/"guideline"
# from - SAR Templates live in `template_ps` instead, with real documents
# shaped {version, fileName, fileType, originalFile: {storage: "local",
# path: ...}, timestamp} (confirmed live against aunqa_ps; not part of
# Dataschema.md's original 9-collection Final Schema, same as
# generation_criteria_log/generation_slot_marking_log - change.md "SAR
# TEMPLATE: Template มีอยู่ใน MongoDB แล้ว").
TEMPLATE_COLLECTION = "template_ps"


def get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.mongodb_uri)
        _db = _client[settings.mongodb_db_name]
    return _db


def get_gridfs_bucket() -> AsyncIOMotorGridFSBucket:
    global _gridfs_bucket
    if _gridfs_bucket is None:
        _gridfs_bucket = AsyncIOMotorGridFSBucket(get_db(), bucket_name="reference_files")
    return _gridfs_bucket


async def get_latest_reference_file(reference_type: str) -> dict | None:
    """Fetches the metadata + raw bytes of the most recently uploaded file of
    this reference_type, matching the Import Service's `examples` /
    `guidelines` collections + `reference_files` GridFS bucket. NOT used for
    "template" any more - see `get_latest_template_metadata()` below.
    """
    from bson import ObjectId

    collection_name = REFERENCE_COLLECTIONS[reference_type]
    db = get_db()
    metadata = await db[collection_name].find_one({}, sort=[("created_at", -1)])
    if metadata is None:
        return None

    bucket = get_gridfs_bucket()
    stream = await bucket.open_download_stream(ObjectId(metadata["grid_file_id"]))
    content = await stream.read()

    return {
        "filename": metadata["filename"],
        "file_format": metadata["file_format"],
        "content": content,
    }


async def get_latest_template_metadata() -> dict | None:
    """Fetches the metadata (no file content) of the most recent SAR
    Template from `template_ps` (change.md "SAR TEMPLATE" / "Generator
    ต้องใช้ Template Version ล่าสุด") - `version` is the explicit,
    unambiguous "latest" signal (sorted descending), not just insertion
    order or timestamp.

    The file itself is no longer read from local disk here: real
    `originalFile.path` values point to a file on a different machine's
    filesystem than this Generator Service instance can read (change.md
    Blocker 2) - fetching the actual bytes is now
    common/template_client.py::download_template(version)'s job, via the
    Template Service HTTP API.

    Returns None only when `template_ps` has no document at all.
    """
    db = get_db()
    metadata = await db[TEMPLATE_COLLECTION].find_one({}, sort=[("version", -1)])
    if metadata is None:
        return None

    return {
        "version": metadata.get("version"),
        "filename": metadata.get("fileName"),
        "file_format": metadata.get("fileType"),
    }
