"""Read-only inspection of the REAL deployed MongoDB against the Final
9-collection schema (Dataschema.md) - change.md's "FIX MONGODB RETRIEVAL
MISMATCH" task, sec.15.

Connects with whatever MONGODB_URI/.env this repo is already configured
with and only ever calls list_collection_names()/count_documents({}) - never
inserts, updates, or deletes anything. Prints record counts for the 9 Final
collections plus the current-deployment-only `evidence_chunks`/
`evidence_documents` collections, so it's always clear whether the Final
Schema has real data yet or whether the MongoDB retrieval tier is correctly
reporting "missing" because there's genuinely nothing there.

Run: python scripts/inspect_mongo_schema.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.mongo import get_db  # noqa: E402

FINAL_SCHEMA_COLLECTIONS = [
    "curricula", "persons", "educations", "appointments", "academic_works",
    "documents", "ps_requirements", "data_usages", "generated_documents",
]
CURRENT_DEPLOYMENT_EXTRA_COLLECTIONS = ["evidence_chunks", "evidence_documents"]


async def main() -> None:
    db = get_db()
    try:
        names = set(await db.list_collection_names())
    except Exception as exc:  # noqa: BLE001
        print(f"MongoDB connection FAILED: {type(exc).__name__}: {exc}")
        return

    print("=== Final 9-collection schema (Dataschema.md) ===")
    any_final_data = False
    for name in FINAL_SCHEMA_COLLECTIONS:
        exists = name in names
        count = await db[name].count_documents({}) if exists else 0
        any_final_data = any_final_data or count > 0
        print(f"  {name:22s} exists={exists!s:5s} count={count}")

    print("\n=== Current-deployment-only collections (NOT part of the Final Schema) ===")
    for name in CURRENT_DEPLOYMENT_EXTRA_COLLECTIONS:
        exists = name in names
        count = await db[name].count_documents({}) if exists else 0
        print(f"  {name:22s} exists={exists!s:5s} count={count}")

    print(f"\n=== All collections actually in the database ===\n  {sorted(names)}")

    print()
    if any_final_data:
        print("RESULT: the Final Schema has real data - MongoDB retrieval can be proven against it.")
    else:
        print("RESULT: CURRENT DEPLOYMENT DATA DOES NOT MATCH FINAL SCHEMA "
              "(no Final-schema collection has any data yet). MongoDB retrieval "
              "will correctly report 'missing' for every request until this changes - "
              "that is expected, honest behavior, not a code bug.")


if __name__ == "__main__":
    asyncio.run(main())
