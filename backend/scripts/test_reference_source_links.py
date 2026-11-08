"""Read-only smoke test for Reference -> imported original document links."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from common.mongo import get_db  # noqa: E402
from reference.traceability_api import _attach_original_documents  # noqa: E402


async def main() -> None:
    db = get_db()
    record = None
    collection = None
    for name in ("academic_works", "educations", "appointments", "persons", "curricula"):
        record = await db[name].find_one({"sources.0": {"$exists": True}})
        if record:
            collection = name
            break

    document = await db["documents"].find_one({})
    assert record is not None and collection is not None, "no Mongo record with source provenance"
    assert document is not None, "no imported source document"

    items = {
        "mongo": {
            "sourceReference": {
                "collection": collection,
                "recordId": str(record["_id"]),
            }
        },
        "chroma": {
            "sourceReference": {
                "documentId": str(document["_id"]),
            }
        },
    }
    await _attach_original_documents(items)

    mongo_docs = items["mongo"]["sourceReference"].get("originalDocuments")
    chroma_docs = items["chroma"]["sourceReference"].get("originalDocuments")
    assert mongo_docs and mongo_docs[0]["documentId"], items["mongo"]
    assert chroma_docs and chroma_docs[0]["documentId"] == str(document["_id"]), items["chroma"]
    assert chroma_docs[0]["fileName"] == document["fileName"], items["chroma"]
    print(f"PASS Mongo ({collection}) and Chroma references resolve to original documents")


if __name__ == "__main__":
    asyncio.run(main())
