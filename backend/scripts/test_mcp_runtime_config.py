"""Production MCP configuration regression test; makes no Gemini request."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from mcp import ClientSession
from mcp.client.stdio import stdio_client

from master_agent.master import mcp_server_parameters


async def main() -> None:
    params = mcp_server_parameters(BACKEND)
    required = {
        "MONGODB_URI", "MONGODB_DB_NAME", "CHROMA_HOST", "CHROMA_PORT",
        "CHROMA_COLLECTION", "TEMPLATE_SERVICE_URL", "GEMINI_API_KEY",
    }
    missing_parent = sorted(name for name in required if not os.environ.get(name))
    missing_child = sorted(name for name in required if not (params.env or {}).get(name))
    assert not missing_parent, f"Generator environment is missing: {missing_parent}"
    assert not missing_child, f"MCP environment is missing: {missing_child}"
    print("PASS MCP inherits required Generator environment (values hidden)")

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()

            async def call(name: str, arguments: dict | None = None):
                result = await session.call_tool(name, arguments or {})
                assert not result.isError, f"{name} failed: {result.content}"
                return [json.loads(block.text) for block in result.content if hasattr(block, "text")]

            template = (await call("get_sar_template"))[0]
            assert template.get("found") and template.get("content_base64"), "SAR template is unavailable"
            config = (await call("get_master_config"))[0]
            assert config.get("criterion_order"), "Master config has no criterion order"
            curricula = await call("query_structured_data", {"data_type": "curriculum", "limit": 1})
            assert curricula, "MCP cannot read the curriculum from MongoDB"
            evidence = await call("search_evidence", {"query": "หลักสูตร", "top_k": 1})
            assert evidence, "MCP cannot retrieve evidence from ChromaDB"

    print("PASS MCP reads Template, master config, MongoDB and ChromaDB without calling Gemini")


if __name__ == "__main__":
    asyncio.run(main())
