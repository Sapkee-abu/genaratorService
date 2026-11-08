"""MCP Server for the AUN-QA Generator Service.

Hands the Master Agent (the MCP client, see ../master_agent/master.py) the
SAR Template, the Master Config JSON (criterion order + per-criterion
name/evidence_top_k - no keywords or guideline), plus
current-year evidence/structured-data retrieval. No Example is served: the
Generator no longer uses a previous-year Example.

SAR Template metadata is read from `template_ps` (common/mongo.py::
get_latest_template_metadata()) - the latest `version` is served - and the
file itself is downloaded from the Template Service HTTP API
(common/template_client.py), since the real file lives on a different
machine's filesystem than this Generator Service instance can read.
Evidence search queries the same ChromaDB collection (`document_chunks`)
the Import Service populates during embedding, using BGE-M3 query
embeddings (common/bge_embedding.py) to match how those chunks were
embedded.
"""

from __future__ import annotations

import base64

from mcp.server.fastmcp import FastMCP

from common import bge_embedding
from common import chroma as chroma_module
from common import mongo
from common import template_client
from common.master_config import read_master_config
from common.schemas import DataRequestItem
from retrieval import document_ocr as document_ocr_module
from retrieval import mongodb as mongodb_module

mcp = FastMCP("aunqa-generator")


@mcp.tool()
async def get_sar_template() -> dict:
    """Returns the latest-version SAR Template (.docx) as base64 content
    (change.md "SAR TEMPLATE" / "Template Version ล่าสุด"). Metadata comes
    from `template_ps`; the file bytes are downloaded from the Template
    Service HTTP API (change.md Blocker 2) - never a silent fallback to a
    stale/local file when either step fails.
    """
    metadata = await mongo.get_latest_template_metadata()
    if metadata is None:
        return {"found": False, "error": "No template document exists in template_ps yet"}

    try:
        content = await template_client.download_template(metadata["version"])
    except template_client.TemplateDownloadError as exc:
        return {"found": False, "error": str(exc)}

    return {
        "found": True,
        "filename": metadata["filename"],
        "file_format": metadata["file_format"],
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


@mcp.tool()
def get_master_config() -> dict:
    """Returns the Master Config JSON (criterion order, current academic year, per-criterion name/evidence_top_k)."""
    return read_master_config()


@mcp.tool()
def search_evidence(query: str, top_k: int = 6, exclude_chunk_ids: list[str] | None = None) -> list[dict]:
    """Semantic search over current-year evidence chunks (ChromaDB).

    Args:
        query: text describing what evidence is needed (from the Agent's Data Request).
        top_k: how many chunks to return.
        exclude_chunk_ids: chunk_ids to skip - used when the Master Agent asks
            for *additional* evidence during verification-gate remediation.
    """
    query_embedding = bge_embedding.embed_query(query)
    return chroma_module.search(query_embedding, top_k=top_k, exclude_chunk_ids=exclude_chunk_ids)


@mcp.tool()
async def query_structured_data(data_type: str, role: str | None = None, limit: int = 50) -> list[dict]:
    """MongoDB tier of Retrieval (change.md "MCP ARCHITECTURE - MUST FIX"):
    the ONLY path the Retrieval Manager's MongoDB fallback uses to reach
    MongoDB - Master/Retrieval Manager never query MongoDB directly, only
    through this MCP tool, same boundary `search_evidence` already enforces
    for ChromaDB.

    Deterministic Data Request -> Final MongoDB Schema mapping (Dataschema.md)
    lives in retrieval/mongodb.py, reused here unchanged - this tool is only
    the MCP boundary around it, not a second implementation.

    Args:
        data_type: "curriculum" | "person" | "education" | "appointment" |
            "academic_work" | "document" | "data_usage" - any other value
            (e.g. the generic "evidence" non-PS agents still send) returns [].
        role: only meaningful when data_type="appointment" - one of
            "programmeResponsible" / "programmeStaff" / "specialInstructor".
        limit: max records to return.
    """
    item = DataRequestItem(data_type=data_type, role=role, purpose="")
    hits = await mongodb_module.search(item, limit=limit)
    return [hit.model_dump() for hit in hits]


@mcp.tool()
async def get_curriculum_people_raw(limit: int = 500) -> dict:
    """Structured (non-prose) MongoDB fetch for PS Agent's canonical person
    aggregation (change.md sec.32) - same MCP boundary as
    query_structured_data, but returns the real structured
    appointments/persons/educations/academic_works fields directly instead
    of prose EvidenceChunkContext blobs, since Table 1.1/1.2 values must be
    computed by deterministic Python, not re-parsed out of prose by an LLM
    (change.md sec.26/38). Reuses retrieval/mongodb.py's
    fetch_curriculum_people_raw() unchanged - this tool is only the MCP
    boundary around it, not a second implementation.
    """
    return await mongodb_module.fetch_curriculum_people_raw(limit=limit)


@mcp.tool()
async def retrieve_document(data_type: str, limit: int = 50) -> list[dict]:
    """Document/OCR tier of Retrieval (change.md "MCP ARCHITECTURE - MUST
    FIX") - the MCP boundary around retrieval/document_ocr.py, same pattern
    as query_structured_data. Currently a stub (no real OCR pipeline wired
    in - out of scope): always returns [], never a fabricated hit. Wiring a
    real OCR service in later only means implementing
    retrieval/document_ocr.py's body - this tool and its callers don't
    change.
    """
    item = DataRequestItem(data_type=data_type, purpose="")
    hits = await document_ocr_module.search(item)
    return [hit.model_dump() for hit in hits[:limit]]


if __name__ == "__main__":
    mcp.run()
