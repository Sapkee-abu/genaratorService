from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket

from common.config import get_settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None
_gridfs_bucket: AsyncIOMotorGridFSBucket | None = None

REFERENCE_COLLECTIONS = {
    "template": "templates",
    "example": "examples",
    "guideline": "guidelines",
}


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
    this reference_type, matching the Import Service's `templates` /
    `examples` / `guidelines` collections + `reference_files` GridFS bucket.
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
