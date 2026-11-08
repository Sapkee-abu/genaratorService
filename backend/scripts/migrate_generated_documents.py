"""EXPLICIT one-time migration: generated_documents  array-of-Versions  ->  one document per Version.

    OLD  one document {curriculumId, fileName, fileType, generatedFiles: [v1, v2, ..., vN], timestamp}
    NEW  N documents  {curriculumId, fileName, fileType, version: k, path, timestamp, + every field the
                       old generatedFiles[k-1] element had (runId, source, userEdits, ...), migratedFrom}

Never run by the application (no startup hook). Run it yourself:

    python scripts/migrate_generated_documents.py --dry-run     # show the plan, write nothing
    python scripts/migrate_generated_documents.py               # migrate, verify, then remove the old document

Safety rules it enforces:
  * a JSON backup of every legacy document is written BEFORE anything else (output/backups/);
  * new Version documents are only INSERTED (upsert with $setOnInsert on (curriculumId, version)) - an
    existing document is never modified; a same-version document with different content aborts the run;
  * it then verifies: all N versions exist, each equals its old generatedFiles element field by field,
    Version 1 and Version N keep the same path and (if the file exists) the same content hash;
  * ONLY after that verification passes is the old array-based document deleted (skip with --keep-legacy);
  * idempotent: nothing legacy left -> "already migrated", no duplicates are created on a second run;
  * the target database is the one in MONGODB_DB_NAME / .env and is printed first.
Exit code 0 = migrated (or already migrated), 1 = aborted/verification failed (legacy document kept).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from common.config import get_settings  # noqa: E402
from common.logging_repo import GENERATED_DOCUMENTS_COLLECTION, ensure_version_index  # noqa: E402
from common.mongo import get_db  # noqa: E402


def file_hash(path: str) -> str | None:
    p = Path(path)
    if not p.is_absolute():
        p = BACKEND / p
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def build_version_doc(legacy: dict, entry: dict, version: int) -> dict:
    doc = {
        "curriculumId": legacy["curriculumId"],
        "fileName": legacy["fileName"],
        "fileType": legacy.get("fileType", "docx"),
        "version": version,
        **{k: v for k, v in entry.items()},  # path, timestamp and ALL other Version-specific metadata, unchanged
        "migratedFrom": legacy["_id"],
    }
    if "path" not in doc or "timestamp" not in doc:
        raise ValueError(f"legacy generatedFiles[{version - 1}] has no path/timestamp - refusing to guess")
    return doc


def same_content(existing: dict, wanted: dict) -> bool:
    return all(existing.get(k) == v for k, v in wanted.items())


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the plan and verify readability, write nothing")
    parser.add_argument("--keep-legacy", action="store_true", help="insert + verify but do NOT delete the old array document")
    parser.add_argument("--backup-dir", default=str(BACKEND / "output" / "backups"))
    args = parser.parse_args()

    settings = get_settings()
    db = get_db()
    coll = db[GENERATED_DOCUMENTS_COLLECTION]
    print(f"[migrate] database: {settings.mongodb_db_name}  collection: {GENERATED_DOCUMENTS_COLLECTION}"
          f"{'  (DRY RUN - nothing is written)' if args.dry_run else ''}")

    legacy_docs = [d async for d in coll.find({"generatedFiles": {"$exists": True}})]
    if not legacy_docs:
        n = await coll.count_documents({"version": {"$exists": True}})
        print(f"[migrate] no legacy array-based document found - already migrated ({n} Version documents). Nothing to do.")
        return 0

    # ---------- plan ----------
    plans = []
    for legacy in legacy_docs:
        entries = legacy["generatedFiles"]
        wanted = [build_version_doc(legacy, e, i) for i, e in enumerate(entries, start=1)]
        plans.append((legacy, wanted))
        print(f"[migrate] legacy _id={legacy['_id']} curriculumId={legacy['curriculumId']} -> {len(wanted)} Version documents "
              f"(versions 1..{len(wanted)})")

    # ---------- refuse anything that could overwrite ----------
    for legacy, wanted in plans:
        for w in wanted:
            existing = await coll.find_one({"curriculumId": w["curriculumId"], "version": w["version"]})
            if existing is not None and not same_content(existing, w):
                print(f"[migrate] ABORT: a Version {w['version']} document already exists with DIFFERENT content "
                      f"(_id={existing['_id']}). Refusing to overwrite. Legacy document kept.")
                return 1

    hashes_before = {(str(l["_id"]), w["version"]): file_hash(w["path"]) for l, ws in plans for w in ws}
    if args.dry_run:
        for legacy, wanted in plans:
            for w in wanted:
                print(f"   v{w['version']:<3} path={w['path']}  file={'present' if hashes_before[(str(legacy['_id']), w['version'])] else 'MISSING'}")
        print("[migrate] dry run complete.")
        return 0

    # ---------- backup first ----------
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"generated_documents_legacy_{settings.mongodb_db_name}_{stamp}.json"
    backup.write_text(json_util.dumps(legacy_docs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[migrate] backup of the legacy document(s) written: {backup}")

    # ---------- insert (never modify an existing document) ----------
    await ensure_version_index(db)
    inserted = existed = 0
    for legacy, wanted in plans:
        for w in wanted:
            res = await coll.update_one({"curriculumId": w["curriculumId"], "version": w["version"]}, {"$setOnInsert": w}, upsert=True)
            if res.upserted_id is not None:
                inserted += 1
            else:
                existed += 1
    print(f"[migrate] Version documents inserted: {inserted}; already present (left untouched): {existed}")

    # ---------- verify ----------
    problems: list[str] = []
    for legacy, wanted in plans:
        docs = {d["version"]: d async for d in coll.find({"curriculumId": legacy["curriculumId"], "version": {"$exists": True}})}
        n = len(wanted)
        if sorted(docs) != list(range(1, n + 1)):
            problems.append(f"versions present {sorted(docs)} != 1..{n}")
        for w in wanted:
            got = docs.get(w["version"])
            if got is None or not same_content(got, w):
                problems.append(f"Version {w['version']} does not equal its legacy generatedFiles element")
            if hashes_before[(str(legacy["_id"]), w["version"])] != file_hash(w["path"]):
                problems.append(f"Version {w['version']} file content changed")
        first, last = wanted[0], wanted[-1]
        print(f"[migrate] verified: {n} Version documents; Version 1 path={first['path']} unchanged; "
              f"Version {n} path={last['path']} unchanged")
    if problems:
        print("[migrate] VERIFICATION FAILED - legacy document NOT deleted:")
        for p in problems:
            print("   -", p)
        return 1

    # ---------- only now remove the old document ----------
    if args.keep_legacy:
        print("[migrate] --keep-legacy: old array-based document left in place (the app will keep refusing until it is removed).")
        return 0
    for legacy, _ in plans:
        res = await coll.delete_one({"_id": legacy["_id"], "generatedFiles": {"$exists": True}})
        print(f"[migrate] removed old array-based document {legacy['_id']}: {res.deleted_count == 1}")
    remaining = await coll.count_documents({"generatedFiles": {"$exists": True}})
    total = await coll.count_documents({"version": {"$exists": True}})
    print(f"[migrate] DONE. legacy documents left: {remaining}; Version documents: {total}")
    return 0 if remaining == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
