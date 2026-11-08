# tools mcp server จะมาเรียก mongodb.py จากไฟล์นี้ เพื่อเข้า mongodb ของจริง

"""MongoDB fallback tier for the Retrieval Manager (change.md sec.8, tier 2:
ChromaDB -> MongoDB -> Document/OCR).

Queries the FINAL 9-collection schema (Dataschema.md) - `curricula`,
`persons`, `educations`, `appointments`, `academic_works`, `documents`,
`data_usages` - never the current deployment's `evidence_chunks` /
`evidence_documents` collections. Those two are real, but they are NOT part
of the Final Schema (Dataschema.md), and there is no deterministic,
non-fabricated way to turn a CV text chunk into a structured `persons` /
`appointments` record - doing so would be exactly the "guessed mapping" /
"fabricated structured record" the migration rules forbid. So: if the Final
collections have no data (as of this writing, none of the 9 exist yet in the
real deployment - confirmed by a live, read-only inspection), every query
below correctly returns nothing. This is honest behavior, not a bug: it will
start returning real matches automatically the moment the Final collections
are populated (by a separate, out-of-scope import/migration effort), with no
code change needed here.

`ps_requirements` (guideline/config - completeness is MONITOR's job, not
Generator's) and `generated_documents` (version persistence, not source
evidence) are deliberately NOT queryable as evidence data_types here - see
Dataschema.md sec.7/9 and change.md sec.6.
"""

from __future__ import annotations

from common.mongo import get_db
from common.schemas import DataRequestItem, EvidenceChunkContext


def mongodb_source_filename(collection: str, record_id) -> str:
    """Each Mongo record acts as its own single-chunk 'source file' for
    citation purposes (chunk_index is always 0 below) - unique per record,
    so (source_filename, chunk_index) pairs never collide across different
    records the way a flat per-collection counter would. Encodes source_type
    ("mongodb"), collection, and record identifier in one string - the
    "source metadata" change.md sec.11 requires - without needing a new
    field on the shared EvidenceChunkContext schema (out of scope: that
    schema is also consumed by Verification/Traceability/Injection, which
    this task must not touch).
    """
    return f"mongodb:{collection}:{record_id}"


def _person_text(person: dict | None) -> str:
    if not person:
        return "(ไม่พบข้อมูลบุคคลที่เชื่อมโยง - personId ไม่ตรงกับ persons collection ใดเลย)"
    return f"{person.get('fullName', '')} (ตำแหน่งทางวิชาการ: {person.get('academicPosition', '')})"


async def _query_appointments(role: str | None, limit: int) -> list[EvidenceChunkContext]:
    """appointments -> persons (personId) + curricula (curriculumId), per
    Dataschema.md sec.4/"Relationship". Role lives ONLY on appointments,
    never on persons (Dataschema.md sec.2's own note) - so a role-specific
    request (programmeResponsible / programmeStaff / specialInstructor)
    filters appointments.role, never persons.role (that field doesn't
    exist).
    """
    db = get_db()
    pipeline: list[dict] = []
    if role:
        pipeline.append({"$match": {"role": role}})
    pipeline += [
        {"$lookup": {"from": "persons", "localField": "personId", "foreignField": "_id", "as": "_person"}},
        {"$lookup": {"from": "curricula", "localField": "curriculumId", "foreignField": "_id", "as": "_curriculum"}},
        {"$limit": limit},
    ]
    hits: list[EvidenceChunkContext] = []
    async for doc in db["appointments"].aggregate(pipeline):
        person = (doc.get("_person") or [None])[0]
        curriculum = (doc.get("_curriculum") or [None])[0]
        order = doc.get("appointmentOrder") or {}
        text = (
            f"บทบาท: {doc.get('roleName', doc.get('role', ''))} | "
            f"บุคคล: {_person_text(person)} | "
            f"หลักสูตร: {curriculum.get('curriculumName', '') if curriculum else '(ไม่พบ curriculum ที่เชื่อมโยง)'} | "
            f"วันที่มีผล: {doc.get('effectiveDate', '')} | "
            f"คำสั่งแต่งตั้ง: {order.get('orderNumber', '')} ลงวันที่ {order.get('orderDate', '')} | "
            f"สถานะ: {doc.get('status', '')}"
        )
        hits.append(
            EvidenceChunkContext(
                chunk_id=mongodb_source_filename("appointments", doc["_id"]),
                document_id=str(person["_id"]) if person else None,
                chunk_index=0,
                source_filename=mongodb_source_filename("appointments", doc["_id"]),
                text=text,
            )
        )
    return hits


async def _query_educations(limit: int) -> list[EvidenceChunkContext]:
    """educations -> persons (personId), per Dataschema.md sec.3."""
    db = get_db()
    pipeline = [
        {"$lookup": {"from": "persons", "localField": "personId", "foreignField": "_id", "as": "_person"}},
        {"$limit": limit},
    ]
    hits: list[EvidenceChunkContext] = []
    async for doc in db["educations"].aggregate(pipeline):
        person = (doc.get("_person") or [None])[0]
        text = (
            f"บุคคล: {_person_text(person)} | "
            f"วุฒิ: {doc.get('degree', '')} สาขา {doc.get('field', '')} | "
            f"สถาบัน: {doc.get('institution', '')} | ปีที่จบ: {doc.get('graduationYear', '')}"
        )
        hits.append(
            EvidenceChunkContext(
                chunk_id=mongodb_source_filename("educations", doc["_id"]),
                document_id=str(person["_id"]) if person else None,
                chunk_index=0,
                source_filename=mongodb_source_filename("educations", doc["_id"]),
                text=text,
            )
        )
    return hits


async def _query_academic_works(limit: int) -> list[EvidenceChunkContext]:
    """academic_works -> persons (personId), per Dataschema.md sec.5."""
    db = get_db()
    pipeline = [
        {"$lookup": {"from": "persons", "localField": "personId", "foreignField": "_id", "as": "_person"}},
        {"$limit": limit},
    ]
    hits: list[EvidenceChunkContext] = []
    async for doc in db["academic_works"].aggregate(pipeline):
        person = (doc.get("_person") or [None])[0]
        text = (
            f"บุคคล: {_person_text(person)} | ประเภทผลงาน: {doc.get('workType', '')} | "
            f"ชื่อผลงาน: {doc.get('title', '')} | ปีที่ตีพิมพ์: {doc.get('publicationYear', '')} | "
            f"ฐานข้อมูล: {doc.get('database', '')} {doc.get('quartile', '')}"
        )
        hits.append(
            EvidenceChunkContext(
                chunk_id=mongodb_source_filename("academic_works", doc["_id"]),
                document_id=str(person["_id"]) if person else None,
                chunk_index=0,
                source_filename=mongodb_source_filename("academic_works", doc["_id"]),
                text=text,
            )
        )
    return hits


async def _query_plain(collection: str, text_fields: list[str], limit: int) -> list[EvidenceChunkContext]:
    """Collections queried with no join: curricula, documents, data_usages -
    `text_fields` picks which top-level fields go into the readable text."""
    db = get_db()
    hits: list[EvidenceChunkContext] = []
    async for doc in db[collection].find({}).limit(limit):
        text = " | ".join(f"{f}: {doc.get(f, '')}" for f in text_fields)
        hits.append(
            EvidenceChunkContext(
                chunk_id=mongodb_source_filename(collection, doc["_id"]),
                document_id=str(doc["_id"]),
                chunk_index=0,
                source_filename=mongodb_source_filename(collection, doc["_id"]),
                text=text,
            )
        )
    return hits


async def _query_persons(limit: int) -> list[EvidenceChunkContext]:
    db = get_db()
    hits: list[EvidenceChunkContext] = []
    async for doc in db["persons"].find({}).limit(limit):
        text = f"{doc.get('fullName', '')} | ตำแหน่งทางวิชาการ: {doc.get('academicPosition', '')}"
        hits.append(
            EvidenceChunkContext(
                chunk_id=mongodb_source_filename("persons", doc["_id"]),
                document_id=str(doc["_id"]),
                chunk_index=0,
                source_filename=mongodb_source_filename("persons", doc["_id"]),
                text=text,
            )
        )
    return hits


async def search(item: DataRequestItem, limit: int = 50) -> list[EvidenceChunkContext]:
    """Deterministic Data Request -> Final Schema collection mapping
    (change.md sec.7). No LLM involved in choosing a collection, no Agent
    writes a Mongo query directly - `item.data_type` (+ `item.role` for
    appointments) is the only input; everything else is fixed Python.

    `data_type` values recognized here mirror Dataschema.md's 9 collections,
    minus `ps_requirements` and `generated_documents` (change.md sec.6 -
    deliberately not queryable as evidence). A `data_type` outside this set
    (e.g. the generic "evidence" every non-PS agent still sends today, or
    any typo) returns [] immediately - same "not found here, try the next
    tier" behavior as a real query that matched nothing, never an error.
    """
    if item.data_type == "appointment":
        return await _query_appointments(item.role, limit)
    if item.data_type == "education":
        return await _query_educations(limit)
    if item.data_type == "academic_work":
        return await _query_academic_works(limit)
    if item.data_type == "person":
        return await _query_persons(limit)
    if item.data_type == "curriculum":
        return await _query_plain(
            "curricula", ["curriculumCode", "curriculumName", "curriculumYear", "version", "status"], limit
        )
    if item.data_type == "document":
        return await _query_plain("documents", ["documentType", "fileType", "fileName", "status"], limit)
    if item.data_type == "data_usage":
        return await _query_plain("data_usages", ["dataType", "psCodes", "roles", "templateFields"], limit)

    return []


async def fetch_curriculum_people_raw(limit: int = 500) -> dict:
    """Structured (non-prose) fetch for the canonical person aggregation
    (change.md sec.32 - "aggregate_curriculum_people()"). `search()` above
    returns prose-blob EvidenceChunkContext objects - the right shape for
    Chroma-style Evidence a Criteria Agent's LLM reasons over, but Table
    1.1/1.2's person/role/degree/work-count VALUES must be computed by
    deterministic Python, never re-parsed out of prose by an LLM (change.md
    sec.26/38). This returns the real structured fields directly instead.

    Every record's own Mongo `_id` is stringified and doubles as its
    `source_filename` key via `mongodb_source_filename()` - the SAME
    convention `search()`'s Mongo-tier EvidenceChunkContext hits already use
    for the same record, so a citation built from this structured data
    exists in Verification's evidence_chunks lookup as long as the matching
    prose-tier hit for that exact record was also retrieved this run (see
    mcp_server.server.get_curriculum_people_raw).
    """
    db = get_db()

    def _clean(doc: dict, collection: str) -> dict:
        out = {k: v for k, v in doc.items() if k != "_id"}
        out["_id"] = str(doc["_id"])
        out["source_filename"] = mongodb_source_filename(collection, doc["_id"])
        for id_field in ("personId", "curriculumId"):
            if id_field in out and out[id_field] is not None:
                out[id_field] = str(out[id_field])
        return out

    appointments = [_clean(d, "appointments") async for d in db["appointments"].find({}).limit(limit)]
    persons = [_clean(d, "persons") async for d in db["persons"].find({}).limit(limit)]
    educations = [_clean(d, "educations") async for d in db["educations"].find({}).limit(limit)]
    academic_works = [_clean(d, "academic_works") async for d in db["academic_works"].find({}).limit(limit)]

    return {
        "appointments": appointments,
        "persons": persons,
        "educations": educations,
        "academic_works": academic_works,
    }
