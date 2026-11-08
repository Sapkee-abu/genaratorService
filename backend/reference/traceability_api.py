"""Reference / Traceability API data (fix.md sec.20/21) - read-only queries
over generation_criteria_log (extended with `sections`, see
common/logging_repo.py::log_criterion) and generated_documents. Builds the
PS/P1../Table 1.1/Table 1.2/Narrative -> field/value/source tree the
frontend's ReferenceTree/ReferenceItem types expect.

Version-aware (fix.md sec.21): a Version Snapshot (created only by Download,
common.logging_repo.save_version_snapshot; ONE generated_documents document per Version) stores
its own `runId` and a frozen `userEdits` list, so Reference for version N is always
  criteria-log(runId) + userEdits(N)
and can never be changed by a later edit/version. Pre-lifecycle-change entries
have neither field (migrated as-is): their run_id is recovered from the file name
`SAR_{run_id}.docx` exactly as before, and they simply have no user edits.
"""

from __future__ import annotations

import re
from pathlib import Path

from bson import ObjectId
from bson.errors import InvalidId

from common.logging_repo import get_version_doc, list_version_docs
from common.mongo import get_db

_RUN_ID_PATTERN = re.compile(r"^SAR_(.+)\.docx$")


def _extract_run_id(path: str) -> str | None:
    match = _RUN_ID_PATTERN.match(Path(path).name)
    return match.group(1) if match else None


async def get_version_entry(version: int) -> dict | None:
    """The Version document for exactly (curriculumId, version) - one generated_documents document per
    Version. Returned in the same field names callers already used (`path`, `timestamp`, `runId`,
    `userEdits`), plus `version`."""
    return await get_version_doc(version)


def _entry_run_id(entry: dict) -> str | None:
    return entry.get("runId") or _extract_run_id(entry["path"])


async def get_run_id_for_version(version: int) -> str | None:
    entry = await get_version_entry(version)
    return _entry_run_id(entry) if entry else None


async def get_version_path(version: int) -> str | None:
    """The stored `path` for a specific version (History Preview/Download -
    each Version document keeps its own real file path, never
    reconstructed or guessed)."""
    entry = await get_version_entry(version)
    return entry["path"] if entry else None


async def get_latest_version() -> int | None:
    docs = await list_version_docs()
    return docs[0]["version"] if docs else None


def _source_from_filename(source_filename: str | None) -> tuple[str, dict]:
    """The real citation convention (retrieval/mongodb.py, common/chroma.py):
    Mongo-sourced citations use "mongodb:<collection>:<id>"; Chroma-sourced
    citations use the raw Chroma document_id with no prefix. Document/OCR
    is a stub today (never produces real citations) - not fabricated here.
    """
    if not source_filename:
        return "missing", {}
    if source_filename.startswith("mongodb:"):
        _, collection, record_id = (source_filename.split(":", 2) + ["", ""])[:3]
        ref = {"collection": collection, "recordId": record_id}
        if collection == "persons":
            ref["personId"] = record_id  # only a persons record id IS a personId
        return "mongodb", ref
    return "chroma", {"documentId": source_filename}


def _object_id(value: object) -> ObjectId | None:
    try:
        return value if isinstance(value, ObjectId) else ObjectId(str(value))
    except (InvalidId, TypeError):
        return None


async def _attach_original_documents(all_items: dict[str, dict]) -> None:
    """Resolve Chroma/Mongo references to verified imported source files."""
    refs: list[dict] = []
    for item in all_items.values():
        primary = item.get("sourceReference")
        if isinstance(primary, dict):
            refs.append(primary)
        refs.extend(ref for ref in item.get("sourceReferences", []) if isinstance(ref, dict))

    db = get_db()
    mongo_records: dict[tuple[str, str], dict] = {}
    records_by_collection: dict[str, dict[str, ObjectId]] = {}
    for ref in refs:
        collection, record_id = ref.get("collection"), ref.get("recordId")
        object_id = _object_id(record_id)
        if isinstance(collection, str) and collection and object_id is not None:
            records_by_collection.setdefault(collection, {})[str(object_id)] = object_id

    for collection, object_ids in records_by_collection.items():
        cursor = db[collection].find(
            {"_id": {"$in": list(object_ids.values())}},
            {"sources": 1},
        )
        async for record in cursor:
            mongo_records[(collection, str(record["_id"]))] = record

    candidates: dict[int, list[tuple[str, list[int]]]] = {}
    document_ids: dict[str, ObjectId] = {}
    for ref in refs:
        resolved: list[tuple[str, list[int]]] = []
        direct_id = _object_id(ref.get("documentId"))
        if direct_id is not None:
            resolved.append((str(direct_id), []))
            document_ids[str(direct_id)] = direct_id
        else:
            key = (str(ref.get("collection") or ""), str(ref.get("recordId") or ""))
            record = mongo_records.get(key)
            for source in record.get("sources", []) if record else []:
                source_id = _object_id(source.get("documentId")) if isinstance(source, dict) else None
                if source_id is None:
                    continue
                source_id_text = str(source_id)
                pages = source.get("pageNumbers")
                resolved.append((source_id_text, pages if isinstance(pages, list) else []))
                document_ids[source_id_text] = source_id
        candidates[id(ref)] = resolved

    documents: dict[str, dict] = {}
    if document_ids:
        cursor = db["documents"].find(
            {"_id": {"$in": list(document_ids.values())}},
            {"fileName": 1},
        )
        async for document in cursor:
            documents[str(document["_id"])] = document

    for ref in refs:
        originals = []
        seen = set()
        for document_id, pages in candidates.get(id(ref), []):
            document = documents.get(document_id)
            if document is None or document_id in seen:
                continue
            seen.add(document_id)
            original = {
                "documentId": document_id,
                "fileName": document.get("fileName") or document_id,
            }
            if pages:
                original["pageNumbers"] = pages
            originals.append(original)
        if originals:
            ref["originalDocuments"] = originals


def _narrative_leaf(section: dict, citations_by_id: dict[str, dict]) -> dict:
    content = section.get("content", "")
    cited_ids = [cid for cid in citations_by_id if cid in content]
    citation = citations_by_id.get(cited_ids[0]) if cited_ids else None
    source, ref = _source_from_filename(citation.get("source_filename") if citation else None)
    if citation:
        ref["chunkIndex"] = citation.get("chunk_index")
    return {
        "id": f"{section['slot_id']}",
        "field": section["slot_id"],
        "value": content,
        "source": source,
        "sourceType": source,
        "sourceReference": ref,
    }


def _table_leaves(section: dict) -> list[dict]:
    """One leaf per (row, column). A row that carries `column_citations`
    (PS, built deterministically) attributes each cell to the record that
    really produced it - a column with no citation has NO source
    ("missing"), it is never assigned the row's first citation. Rows without
    `column_citations` (LLM-built tables) keep the original behavior: the
    row's first citation stands for every column."""
    headers = section.get("headers", [])
    leaves = []
    for row_index, row in enumerate(section.get("rows", [])):
        values = row.get("values", [])
        row_citations = row.get("citations", [])
        column_citations = row.get("column_citations")
        for col_index, header in enumerate(headers):
            if column_citations is not None:
                cell_citations = column_citations.get(str(col_index)) or []
            else:
                cell_citations = row_citations[:1]
            primary = cell_citations[0] if cell_citations else None
            source, ref = _source_from_filename(primary.get("source_filename") if primary else None)
            if primary:
                ref["chunkIndex"] = primary.get("chunk_index")
            # a cell built from SEVERAL source records (e.g. the education list of Table 1.2): list every one of them,
            # in display order (`sourceReference` above stays the first, unchanged). Additive - only when there is more than one.
            extra_refs = []
            if len(cell_citations) > 1:
                for citation in cell_citations:
                    _src, one_ref = _source_from_filename(citation.get("source_filename"))
                    one_ref["chunkIndex"] = citation.get("chunk_index")
                    extra_refs.append(one_ref)
            value = values[col_index] if col_index < len(values) else ""
            leaves.append(
                {
                    "id": f"{section['slot_id']}.row{row_index}.col{col_index}",
                    "field": f"{header} (row {row_index + 1})",
                    "value": value,
                    "source": source,
                    "sourceType": source,
                    "sourceReference": ref,
                    **({"sourceReferences": extra_refs} if extra_refs else {}),
                }
            )
    return leaves


async def build_reference_tree(run_id: str, user_edits: list[dict] | None = None) -> dict:
    db = get_db()
    cursor = db["generation_criteria_log"].find({"run_id": run_id}, {"_id": 0}).sort("created_at", 1)
    records = [doc async for doc in cursor]

    nodes = []
    all_items: dict[str, dict] = {}

    for record in records:
        criterion = record["criterion"]
        sections = record.get("sections")
        if not sections:
            nodes.append({"id": criterion.lower(), "label": criterion, "children": []})
            continue

        citations_by_id = {c["citation_id"]: c for c in record.get("citations", [])}
        children = []
        for section in sections:
            if section["type"] == "narrative":
                leaf = _narrative_leaf(section, citations_by_id)
                all_items[leaf["id"]] = leaf
                children.append({"id": leaf["id"], "label": section["slot_id"], "referenceItemId": leaf["id"]})
            else:
                table_leaves = _table_leaves(section)
                table_children = []
                for leaf in table_leaves:
                    all_items[leaf["id"]] = leaf
                    table_children.append({"id": leaf["id"], "label": leaf["field"], "referenceItemId": leaf["id"]})
                children.append({"id": section["slot_id"], "label": section["slot_id"], "children": table_children})

        nodes.append({"id": criterion.lower(), "label": criterion, "children": children})

    _apply_user_edits(nodes, all_items, user_edits or [])
    await _attach_original_documents(all_items)
    return {"tree": {"criterion": "root", "nodes": nodes}, "items": all_items}


def _apply_user_edits(nodes: list[dict], all_items: dict[str, dict], user_edits: list[dict]) -> None:
    """Overlays a Version's frozen User Edits (fix.md sec.12/13/21).

    - Edit on a field with a real Reference item: the item keeps its ORIGINAL
      source (sourceType/sourceReference - MongoDB/Chroma still backs the
      original value, never the edit) and gains originalValue/currentValue/
      userEdited=true; `value` shows the current value.
    - Edit with no real source mapping: sourceType="user_edit", NO
      sourceReference (nothing fabricated), listed under an "unattributed"
      node.
    """
    unattributed: list[dict] = []
    for edit in user_edits:
        item = all_items.get(edit.get("referenceItemId") or "")
        if item is not None:
            item["value"] = edit["currentValue"]
            item["originalValue"] = edit["originalValue"]
            item["currentValue"] = edit["currentValue"]
            item["userEdited"] = True
            item["source"] = item["sourceType"] = edit["sourceType"]
            if edit["sourceType"] == "user_edit":
                item.pop("sourceReference", None)
            continue
        leaf_id = f"user_edit.{edit['elementId']}"
        all_items[leaf_id] = {
            "id": leaf_id,
            "field": edit["field"],
            "value": edit["currentValue"],
            "originalValue": edit["originalValue"],
            "currentValue": edit["currentValue"],
            "source": "user_edit",
            "sourceType": "user_edit",
            "userEdited": True,
        }
        unattributed.append({"id": leaf_id, "label": edit["field"], "referenceItemId": leaf_id})
    if unattributed:
        nodes.append({"id": "user_edits", "label": "User Edits (unattributed)", "children": unattributed})
