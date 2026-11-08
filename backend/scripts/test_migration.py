"""Tests for the generated_documents schema migration + the per-Version repository (fix.md Part C).

Everything runs in TEMPORARY databases `aunqa_ps_test_mig_<uuid>` (dropped at the end); the
production database is never opened. The legacy document is built in the REAL production shape
(8 generatedFiles elements: 7 legacy {path,timestamp} + 1 new-style with runId/source/userEdits) over
real files in a temp dir, so file-hash preservation is exercised for real.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / "scripts" / "migrate_generated_documents.py"
PROD_DB = None  # never touched
sys.path.insert(0, str(BACKEND))

from bson import ObjectId  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from common.config import Settings  # noqa: E402

passed = 0


def ok(name: str) -> None:
    global passed
    passed += 1
    print(f"TEST {name}: OK", flush=True)


def run_migration(db_name: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "MONGODB_DB_NAME": db_name, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=env, cwd=str(BACKEND), capture_output=True, text=True, timeout=120)


def run_snippet(db_name: str, code: str) -> str:
    """Runs python code in a fresh process bound to db_name (settings are read at import)."""
    env = {**os.environ, "MONGODB_DB_NAME": db_name, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run([sys.executable, "-c", code], env=env, cwd=str(BACKEND), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout.strip().splitlines()[-1]


async def main() -> None:
    uri = Settings().mongodb_uri
    client = AsyncIOMotorClient(uri)
    tmp = Path(tempfile.mkdtemp(prefix="migration_files_"))
    dbs = [f"aunqa_ps_test_mig_{uuid.uuid4().hex[:8]}" for _ in range(3)]
    try:
        curriculum = ObjectId()
        base = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)

        def legacy_doc():
            files = []
            for i in range(1, 9):
                p = tmp / f"SAR_v{i}.docx"
                p.write_bytes(f"content of version {i}".encode())
                entry = {"path": str(p), "timestamp": base + timedelta(minutes=i)}
                if i == 8:
                    entry.update(runId="run-8", source="download", userEdits=[{"elementId": "b7.r4.c2", "userEdited": True}])
                files.append(entry)
            return {"curriculumId": curriculum, "fileName": f"SAR_{curriculum}.docx", "fileType": "docx",
                    "generatedFiles": files, "timestamp": base + timedelta(minutes=8)}

        # ---------------- A: dry run, migrate, verify, idempotent ----------------
        a = dbs[0]
        legacy = legacy_doc()
        await client[a]["generated_documents"].insert_one(dict(legacy))
        hashes = {i: (tmp / f"SAR_v{i}.docx").read_bytes() for i in range(1, 9)}

        r = run_migration(a, "--dry-run")
        assert r.returncode == 0 and "dry run complete" in r.stdout, r.stdout + r.stderr
        assert await client[a]["generated_documents"].count_documents({}) == 1, "dry run wrote something"
        ok("1  --dry-run prints the plan and writes nothing")

        r = run_migration(a)
        assert r.returncode == 0, r.stdout + r.stderr
        docs = [d async for d in client[a]["generated_documents"].find({}).sort("version", 1)]
        assert [d["version"] for d in docs] == list(range(1, 9)) and all("generatedFiles" not in d for d in docs)
        assert await client[a]["generated_documents"].count_documents({"generatedFiles": {"$exists": True}}) == 0
        ok("2  migration -> exactly 8 Version documents (version 1..8), old array document removed")

        for i, d in enumerate(docs, 1):
            entry = legacy["generatedFiles"][i - 1]
            assert d["path"] == entry["path"] and d["timestamp"] == entry["timestamp"], (i, d)
            assert d["curriculumId"] == curriculum and d["fileName"] == legacy["fileName"] and d["fileType"] == "docx"
        assert docs[7]["runId"] == "run-8" and docs[7]["source"] == "download" and docs[7]["userEdits"][0]["elementId"] == "b7.r4.c2"
        assert all((tmp / f"SAR_v{i}.docx").read_bytes() == hashes[i] for i in range(1, 9))
        ok("3  every field preserved (path, timestamp, runId/source/userEdits of Version 8); Version 1 and 8 files byte-identical")

        backups = sorted((BACKEND / "output" / "backups").glob(f"generated_documents_legacy_{a}_*.json"))
        assert backups and "generatedFiles" in backups[-1].read_text(encoding="utf-8")
        ok("4  a JSON backup of the legacy document was written before anything else")

        before = [d async for d in client[a]["generated_documents"].find({}).sort("version", 1)]
        r = run_migration(a)
        after = [d async for d in client[a]["generated_documents"].find({}).sort("version", 1)]
        assert r.returncode == 0 and "already migrated" in r.stdout and before == after and len(after) == 8
        ok("5  running it twice is safe: 'already migrated', no duplicates, nothing modified")

        # ---------------- B: next version / History / immutability on the migrated data ----------------
        out = run_snippet(a, f"""
import asyncio
from bson import ObjectId
from common.logging_repo import save_version_snapshot, list_version_docs, get_version_doc
async def go():
    cid = ObjectId('{curriculum}')
    v9 = await save_version_snapshot(str(cid), 'SAR_x.docx', 'docx', 'p9.docx', 'run-9', [])
    v10 = await save_version_snapshot(str(cid), 'SAR_x.docx', 'docx', 'p10.docx', 'run-10', [])
    docs = await list_version_docs(cid)
    v8 = await get_version_doc(8, cid)
    v1 = await get_version_doc(1, cid)
    print(v9, v10, [d['version'] for d in docs], v8['runId'], v1['path'].endswith('SAR_v1.docx'))
asyncio.run(go())
""")
        assert out == "9 10 [10, 9, 8, 7, 6, 5, 4, 3, 2, 1] run-8 True", out
        v_before = {d["version"]: d for d in docs}
        now = {d["version"]: d async for d in client[a]["generated_documents"].find({})}
        assert all(now[v] == v_before[v] for v in range(1, 9)), "an older Version document was modified"
        assert await client[a]["generated_documents"].count_documents({}) == 10
        ok("6  next Download -> Version 9 (not 1), the one after -> Version 10; History order 10..1; Versions 1-8 unchanged")

        out = run_snippet(a, f"""
import asyncio
from bson import ObjectId
from common.logging_repo import get_version_doc
async def go():
    cid = ObjectId('{curriculum}')
    got = [ (await get_version_doc(v, cid))['path'] for v in (1, 5, 8)]
    print([p.rsplit('/',1)[-1] for p in got], (await get_version_doc(99, cid)))
asyncio.run(go())
""")
        assert out == "['SAR_v1.docx', 'SAR_v5.docx', 'SAR_v8.docx'] None", out
        ok("7  lookup by (curriculumId, version): Version N returns Version N (never the latest); unknown version -> None")

        # ---------------- C: duplicate version numbers are impossible ----------------
        out = run_snippet(a, f"""
import asyncio
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from common.mongo import get_db
async def go():
    coll = get_db()['generated_documents']
    try:
        await coll.insert_one({{'curriculumId': ObjectId('{curriculum}'), 'version': 3, 'path': 'dup'}})
        print('NO-ERROR')
    except DuplicateKeyError:
        print('DUPLICATE-REJECTED')
asyncio.run(go())
""")
        assert out == "DUPLICATE-REJECTED", out
        out = run_snippet(a, f"""
import asyncio
from bson import ObjectId
from common.logging_repo import save_version_snapshot
async def go():
    cid = str(ObjectId('{curriculum}'))
    vs = await asyncio.gather(*[save_version_snapshot(cid, 'f', 'docx', f'race{{i}}', 'r', []) for i in range(6)])
    print(sorted(vs))
asyncio.run(go())
""")
        assert out == "[11, 12, 13, 14, 15, 16]", out
        ok("8  unique (curriculumId, version) index rejects a duplicate; 6 concurrent Downloads get 6 distinct consecutive versions")

        # ---------------- D: refusal to overwrite a conflicting document ----------------
        b = dbs[1]
        await client[b]["generated_documents"].insert_one(dict(legacy_doc()))
        await client[b]["generated_documents"].insert_one({"curriculumId": curriculum, "version": 3, "path": "SOMETHING-ELSE.docx", "timestamp": base})
        r = run_migration(b)
        assert r.returncode == 1 and "ABORT" in r.stdout, r.stdout
        assert await client[b]["generated_documents"].count_documents({"generatedFiles": {"$exists": True}}) == 1
        assert (await client[b]["generated_documents"].find_one({"version": 3}))["path"] == "SOMETHING-ELSE.docx"
        ok("9  a conflicting existing Version 3 document -> ABORT (exit 1), legacy document kept, nothing overwritten")

        # ---------------- E: file changed during migration is detected; --keep-legacy keeps the old doc ----------------
        c = dbs[2]
        await client[c]["generated_documents"].insert_one(dict(legacy_doc()))
        r = run_migration(c, "--keep-legacy")
        assert r.returncode == 0 and await client[c]["generated_documents"].count_documents({"generatedFiles": {"$exists": True}}) == 1
        assert await client[c]["generated_documents"].count_documents({"version": {"$exists": True}}) == 8
        # while the legacy doc is still present the app refuses (503-worthy) instead of silently showing an empty History
        out = run_snippet(c, "import asyncio\nfrom common.logging_repo import list_version_docs, LegacyGeneratedDocumentsError\n"
                             "async def go():\n    try:\n        await list_version_docs()\n        print('NO-ERROR')\n    except LegacyGeneratedDocumentsError:\n        print('REFUSED')\nasyncio.run(go())")
        assert out == "REFUSED", out
        ok("10 --keep-legacy inserts+verifies but keeps the old document; the app refuses (LegacyGeneratedDocumentsError) until it is migrated")

        # nothing in this file ever touched the production database
        assert PROD_DB is None
        print(f"\nALL {passed} migration/version-repository checks passed (temp DBs only)")
    finally:
        for name in dbs:
            assert name.startswith("aunqa_ps_test_mig_")
            await client.drop_database(name)
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
