"""MCP Server for the AUN-QA Generator Service.

Hands the Master Agent (the MCP client, see ../master_agent/master.py) the
inputs mainpromt.md's Initialization step requires - SAR Template, Example,
Master Config JSON (which now carries each criterion's Guideline directly,
per changefeature.md - no separate Guideline file/tool) - plus current-year
evidence search.

Template / Example are read from the same MongoDB + GridFS the Import
Service writes to (`templates` / `examples` collections, `reference_files`
GridFS bucket) - the most recently uploaded file of each type is served.
Evidence search queries the same ChromaDB collection the Import Service
populates during embedding.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from common import chroma as chroma_module
from common import gemini
from common import mongo
from common.config import get_settings

mcp = FastMCP("aunqa-generator")


async def _reference_file_payload(reference_type: str) -> dict:
    file = await mongo.get_latest_reference_file(reference_type)
    if file is None:
        return {"found": False, "error": f"No {reference_type} file has been uploaded to the Import Service yet"}
    return {
        "found": True,
        "filename": file["filename"],
        "file_format": file["file_format"],
        "content_base64": base64.b64encode(file["content"]).decode("ascii"),
    }


@mcp.tool()
async def get_sar_template() -> dict:
    """Returns the most recently uploaded SAR Template (.docx) as base64 content."""
    return await _reference_file_payload("template")


@mcp.tool()
async def get_example() -> dict:
    """Returns the most recently uploaded previous-year Example (.pdf/.docx) as base64 content."""
    return await _reference_file_payload("example")


@mcp.tool()
def get_master_config() -> dict:
    """Returns the Master Config JSON (criterion order, per-criterion guideline, keywords, required evidence)."""
    settings = get_settings()
    path = Path(settings.master_config_path)
    return json.loads(path.read_text(encoding="utf-8"))


@mcp.tool()
def search_evidence(query: str, top_k: int = 6, exclude_chunk_ids: list[str] | None = None) -> list[dict]:
    """Semantic search over current-year evidence chunks (ChromaDB).

    Args:
        query: text describing what evidence is needed (e.g. criterion keywords).
        top_k: how many chunks to return.
        exclude_chunk_ids: chunk_ids to skip - used when the Master Agent asks
            for *additional* evidence during verification-gate remediation.
    """
    query_embedding = gemini.embed_query(query)
    return chroma_module.search(query_embedding, top_k=top_k, exclude_chunk_ids=exclude_chunk_ids)


if __name__ == "__main__":
    mcp.run()
