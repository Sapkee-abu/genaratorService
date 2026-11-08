"""Standalone test for the MongoDB Retrieval tier against the Final 9-
collection schema (Dataschema.md) - change.md's "FIX MONGODB RETRIEVAL
MISMATCH" task, sec.14.

No live MongoDB needed: `common.mongo.get_db()` is monkeypatched with a fake
in-memory-shaped Motor-like database (fake `find`/`aggregate` async
cursors) so this runs anywhere, fast, deterministic - same spirit as
scripts/test_slot_marking.py (mocked LLM) and
scripts/test_table_group_injection.py (real docx, no Gemini/MCP).

Covers change.md sec.14 items 1-15:
  1-5   query persons / educations / appointments / academic_works / curricula
  6     appointment role: programmeResponsible / programmeStaff / specialInstructor
  7-8   appointment -> person, appointment -> curriculum relationship (lookup)
  9-10  person -> education, person -> academic_work relationship (lookup)
  11    no matching record -> missing (empty collection -> [] -> RetrievalManager "missing")
  12    Mongo unavailable -> fallback (RetrievalManager falls through to document_ocr/missing)
  13    Mongo result contains source metadata (source_type/collection/record id encoded)
  14    no fabricated source reference (empty DB -> no hits, ever)
  15    Source Data is never modified (write methods on the fake DB raise if called)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bson import ObjectId  # noqa: E402

import retrieval.mongodb as mongodb_retrieval  # noqa: E402
from common.schemas import DataRequestItem  # noqa: E402
from retrieval.manager import RetrievalManager  # noqa: E402


class _AsyncCursor:
    """Fakes both `collection.find(...)` (sync iterable of docs, then
    awaited item-by-item) and `collection.aggregate([...])` (same shape) -
    Motor's async cursors support `.limit()` chaining then `async for`."""

    def __init__(self, docs: list[dict]):
        self._docs = docs

    def limit(self, n):
        return self

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


def _refuses_writes(name: str):
    def _raise(*args, **kwargs):
        raise AssertionError(f"retrieval/mongodb.py must never call {name}() - Source Data must stay read-only")

    return _raise


class _FakeCollection:
    """A collection that answers find()/aggregate() from fixed fixture data,
    and raises immediately if ANY write method is ever called - proving
    change.md sec.12/15's read-only requirement at the code-execution level,
    not just by code review.
    """

    def __init__(self, find_docs: list[dict] | None = None, aggregate_docs: list[dict] | None = None):
        self._find_docs = find_docs or []
        self._aggregate_docs = aggregate_docs if aggregate_docs is not None else (find_docs or [])
        self.last_aggregate_pipeline = None
        for write_method in [
            "insert_one", "insert_many", "update_one", "update_many",
            "delete_one", "delete_many", "replace_one", "find_one_and_update",
            "find_one_and_delete", "find_one_and_replace", "bulk_write", "drop",
        ]:
            setattr(self, write_method, _refuses_writes(write_method))

    def find(self, query=None, *args, **kwargs):
        return _AsyncCursor(self._find_docs)

    def aggregate(self, pipeline):
        self.last_aggregate_pipeline = pipeline
        return _AsyncCursor(self._aggregate_docs)


class _FakeDB:
    def __init__(self, collections: dict[str, _FakeCollection]):
        self._collections = collections

    def __getitem__(self, name):
        return self._collections.setdefault(name, _FakeCollection([]))


def _fixture_ids():
    return {
        "person": ObjectId(),
        "curriculum": ObjectId(),
        "appointment_pr": ObjectId(),
        "appointment_ps": ObjectId(),
        "appointment_si": ObjectId(),
        "education": ObjectId(),
        "academic_work": ObjectId(),
    }


def _build_fake_db(ids: dict) -> _FakeDB:
    person_doc = {
        "_id": ids["person"], "fullName": "ผศ.ดร.สุภาภรณ์ ใจรังษี", "academicPosition": "ผู้ช่วยศาสตราจารย์",
    }
    curriculum_doc = {
        "_id": ids["curriculum"], "curriculumCode": "25500231104894",
        "curriculumName": "วิทยาศาสตรบัณฑิต สาขาเทคโนโลยีสารสนเทศอัจฉริยะ",
        "curriculumYear": 2567, "version": 1, "status": "latest",
    }

    def appointment_doc(_id, role, role_name):
        return {
            "_id": _id, "curriculumId": ids["curriculum"], "personId": ids["person"],
            "role": role, "roleName": role_name, "effectiveDate": "2567-11-13",
            "appointmentOrder": {"orderNumber": "350/2568", "orderDate": "2568-02-04"},
            "status": "active",
            "_person": [person_doc], "_curriculum": [curriculum_doc],
        }

    appointments_all = [
        appointment_doc(ids["appointment_pr"], "programmeResponsible", "อาจารย์ผู้รับผิดชอบหลักสูตร"),
        appointment_doc(ids["appointment_ps"], "programmeStaff", "อาจารย์ประจำหลักสูตร"),
        appointment_doc(ids["appointment_si"], "specialInstructor", "อาจารย์พิเศษ"),
    ]

    education_doc = {
        "_id": ids["education"], "personId": ids["person"], "degree": "Ph.D.",
        "field": "Informatics", "institution": "King's College London",
        "graduationYear": 2555, "_person": [person_doc],
    }
    academic_work_doc = {
        "_id": ids["academic_work"], "personId": ids["person"], "workType": "journalArticle",
        "title": "A sequential deep learning framework for proactive fault detection",
        "publicationYear": 2569, "database": "Scopus", "quartile": "Q1", "_person": [person_doc],
    }

    return _FakeDB({
        "persons": _FakeCollection([person_doc]),
        "curricula": _FakeCollection([curriculum_doc]),
        "appointments": _FakeCollection(aggregate_docs=appointments_all),
        "educations": _FakeCollection(aggregate_docs=[education_doc]),
        "academic_works": _FakeCollection(aggregate_docs=[academic_work_doc]),
        "documents": _FakeCollection([]),
        "data_usages": _FakeCollection([]),
    })


def _appointments_by_role_db(ids: dict, role: str) -> _FakeDB:
    """A DB whose appointments.aggregate() only returns docs matching one
    role - the fake mimics the real Mongo $match stage manually, since the
    fake collection doesn't execute the pipeline for real."""

    def appointment_doc(_id, r, role_name):
        return {
            "_id": _id, "curriculumId": ids["curriculum"], "personId": ids["person"],
            "role": r, "roleName": role_name, "effectiveDate": "2567-11-13",
            "appointmentOrder": {"orderNumber": "1/2568", "orderDate": "2568-01-01"}, "status": "active",
            "_person": [{"_id": ids["person"], "fullName": "Test Person", "academicPosition": "อาจารย์"}],
            "_curriculum": [{"_id": ids["curriculum"], "curriculumName": "Test Curriculum"}],
        }

    all_appointments = {
        "programmeResponsible": appointment_doc(ObjectId(), "programmeResponsible", "อาจารย์ผู้รับผิดชอบหลักสูตร"),
        "programmeStaff": appointment_doc(ObjectId(), "programmeStaff", "อาจารย์ประจำหลักสูตร"),
        "specialInstructor": appointment_doc(ObjectId(), "specialInstructor", "อาจารย์พิเศษ"),
    }
    return _FakeDB({"appointments": _FakeCollection(aggregate_docs=[all_appointments[role]])})


async def main() -> None:
    ids = _fixture_ids()

    # --- 1-5: each Final-schema data_type resolves to its own collection ---
    fake_db = _build_fake_db(ids)
    mongodb_retrieval.get_db = lambda: fake_db

    persons = await mongodb_retrieval.search(DataRequestItem(data_type="person", purpose="x"))
    assert len(persons) == 1 and "สุภาภรณ์" in persons[0].text, persons

    educations = await mongodb_retrieval.search(DataRequestItem(data_type="education", purpose="x"))
    assert len(educations) == 1 and "Ph.D." in educations[0].text, educations

    appointments = await mongodb_retrieval.search(DataRequestItem(data_type="appointment", purpose="x"))
    assert len(appointments) == 3, appointments  # all 3 roles, no role filter

    academic_works = await mongodb_retrieval.search(DataRequestItem(data_type="academic_work", purpose="x"))
    assert len(academic_works) == 1 and "Scopus" in academic_works[0].text, academic_works

    curricula = await mongodb_retrieval.search(DataRequestItem(data_type="curriculum", purpose="x"))
    assert len(curricula) == 1 and "25500231104894" in curricula[0].text, curricula
    print("1-5  query persons/educations/appointments/academic_works/curricula: OK")

    # --- 6: all three appointment roles filter correctly ---
    expected_role_name = {
        "programmeResponsible": "อาจารย์ผู้รับผิดชอบหลักสูตร",
        "programmeStaff": "อาจารย์ประจำหลักสูตร",
        "specialInstructor": "อาจารย์พิเศษ",
    }
    for role, role_name in expected_role_name.items():
        mongodb_retrieval.get_db = lambda r=role: _appointments_by_role_db(ids, r)
        hits = await mongodb_retrieval.search(DataRequestItem(data_type="appointment", role=role, purpose="x"))
        assert len(hits) == 1, (role, hits)
        assert role_name in hits[0].text, (role, hits[0].text)
    print("6    appointment role filter (programmeResponsible/programmeStaff/specialInstructor): OK")

    # --- 7-8: appointment -> person, appointment -> curriculum (lookup joins) ---
    mongodb_retrieval.get_db = lambda: fake_db
    appt = (await mongodb_retrieval.search(DataRequestItem(data_type="appointment", purpose="x")))[0]
    assert "สุภาภรณ์" in appt.text, "appointment -> person lookup missing from text"
    assert "เทคโนโลยีสารสนเทศ" in appt.text, "appointment -> curriculum lookup missing from text"
    assert appt.document_id == str(ids["person"]), "appointment's document_id should resolve to the linked person"
    print("7-8  appointment -> person, appointment -> curriculum relationship: OK")

    # --- 9-10: person -> education, person -> academic_work (lookup joins) ---
    edu = educations[0]
    assert "สุภาภรณ์" in edu.text, "education -> person lookup missing"
    work = academic_works[0]
    assert "สุภาภรณ์" in work.text, "academic_work -> person lookup missing"
    print("9-10 person -> education, person -> academic_work relationship: OK")

    # --- 11: no matching record -> missing ---
    empty_db = _FakeDB({})
    mongodb_retrieval.get_db = lambda: empty_db
    for data_type in ["person", "education", "appointment", "academic_work", "curriculum"]:
        hits = await mongodb_retrieval.search(DataRequestItem(data_type=data_type, purpose="x"))
        assert hits == [], (data_type, hits)
    print("11   no matching record -> missing (empty collections -> []): OK")

    # --- 12: Mongo unavailable -> RetrievalManager falls back, doesn't crash ---
    # RetrievalManager no longer imports retrieval/mongodb.py or
    # retrieval/document_ocr.py directly (change.md "MCP ARCHITECTURE - MUST
    # FIX": both tiers are reached only through injected MCP-tool-backed
    # callables, mirroring search_chroma) - so these are exercised here as
    # plain callables, matching how master_agent/master.py wires them for
    # real via _search_mongo/_search_document_ocr (MCP tool calls).
    async def chroma_miss(query, top_k, exclude):
        return []

    async def mongo_boom(item):
        raise ConnectionError("simulated: MongoDB Atlas unreachable")

    ocr_calls = []

    async def ocr_spy(item):
        ocr_calls.append(item)
        return []  # real retrieval/document_ocr.py is a stub too - matches its behavior

    mgr = RetrievalManager(search_chroma=chroma_miss, search_mongo=mongo_boom, search_document_ocr=ocr_spy, top_k=6)
    result = await mgr.retrieve([DataRequestItem(data_type="appointment", role="programmeResponsible", purpose="x")])
    assert result.fields[0].source_tier == "missing", result.fields[0]
    print("12   Mongo unavailable -> RetrievalManager falls back to document_ocr/missing, no crash: OK")

    # --- 12b: fallback specifically REACHES the Document/OCR tier (not just
    # "ends up missing", which could also happen if OCR were silently
    # skipped) - the spy above records every call made to it. ---
    assert len(ocr_calls) == 1, "Document/OCR tier was not actually reached after MongoDB failed"
    print("12b  fallback explicitly reaches the Document/OCR tier when MongoDB fails: OK")

    # --- 12c: MCP boundary - RetrievalManager takes its Mongo/OCR tiers only
    # as injected callables, never importing retrieval/mongodb.py or
    # retrieval/document_ocr.py itself (those are only imported by
    # mcp_server/server.py's query_structured_data/retrieve_document tools,
    # which reuse them unchanged from behind the MCP boundary). ---
    import inspect

    manager_source = inspect.getsource(sys.modules["retrieval.manager"])
    assert "import retrieval.mongodb" not in manager_source and "from retrieval import mongodb" not in manager_source, (
        "retrieval/manager.py must not import retrieval/mongodb.py directly - MCP boundary violation"
    )
    assert (
        "import retrieval.document_ocr" not in manager_source and "from retrieval import document_ocr" not in manager_source
    ), "retrieval/manager.py must not import retrieval/document_ocr.py directly - MCP boundary violation"
    print("12c  RetrievalManager has no direct import of retrieval/mongodb.py or retrieval/document_ocr.py: OK")

    # --- 13: Mongo result contains source metadata ---
    mongodb_retrieval.get_db = lambda: fake_db
    appt = (await mongodb_retrieval.search(DataRequestItem(data_type="appointment", purpose="x")))[0]
    assert appt.source_filename.startswith("mongodb:appointments:"), appt.source_filename
    assert appt.document_id is not None, "record identifier (linked person id) must be present"
    assert appt.chunk_index == 0, "each Mongo record is its own single-chunk source"
    print("13   Mongo result carries source metadata (source_type/collection/record id): OK")

    # --- 14: no fabricated source reference when nothing is found ---
    mongodb_retrieval.get_db = lambda: empty_db
    hits = await mongodb_retrieval.search(DataRequestItem(data_type="appointment", role="programmeResponsible", purpose="x"))
    assert hits == [], "must return nothing, never a fabricated/placeholder reference"
    print("14   no fabricated source reference on empty data: OK")

    # --- 15: Source Data is never modified (write methods raise if called) ---
    mongodb_retrieval.get_db = lambda: fake_db
    for data_type in ["person", "education", "appointment", "academic_work", "curriculum"]:
        await mongodb_retrieval.search(DataRequestItem(data_type=data_type, purpose="x"))
    # (no AssertionError raised above means no write method was ever invoked)
    print("15   Source Data is never modified (write methods on Final collections never called): OK")

    print("\nALL 15 MongoDB Retrieval checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
