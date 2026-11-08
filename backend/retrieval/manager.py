"""Retrieval Manager (change.md sec.8): resolves a Criterion Agent's Data
Request into Retrieved Data, one requested item at a time, trying
ChromaDB -> MongoDB -> Document/OCR in that order and stopping at the first
tier that returns something - never deciding *what* is needed (that's the
Agent's job, see common.schemas.DataRequest) and never fabricating a hit
when every tier comes back empty.

MCP ARCHITECTURE BOUNDARY (change.md "MCP ARCHITECTURE - MUST FIX"): this
class never touches ChromaDB, MongoDB, or a filesystem/OCR pipeline
directly - all three tiers are reached exclusively through MCP tools
(mcp_server/server.py: search_evidence / query_structured_data /
retrieve_document) over the MCP session master.py already has open. The
three `search_*` callables below are the only way in - RetrievalManager
doesn't open its own MCP connection or import retrieval/mongodb.py or
retrieval/document_ocr.py itself; those modules' actual query logic is
reused unchanged, just called from behind the MCP tool boundary
(mcp_server/server.py) instead of from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable

from common.schemas import DataRequestItem, EvidenceChunkContext

# (query, top_k, exclude_chunk_ids) -> list of raw hit dicts, same shape
# common/chroma.py:search already returns (chunk_id/text/document_id/
# chunk_index/source_filename/...).
ChromaSearchFn = Callable[[str, int, list[str]], Awaitable[list[dict]]]

# (DataRequestItem) -> list of raw hit dicts, same shape EvidenceChunkContext
# expects (chunk_id/document_id/chunk_index/source_filename/text) - the MCP
# tool already returns them via EvidenceChunkContext.model_dump().
MongoSearchFn = Callable[[DataRequestItem], Awaitable[list[dict]]]
DocumentOcrSearchFn = Callable[[DataRequestItem], Awaitable[list[dict]]]

SourceTier = str  # "chromadb" | "mongodb" | "document_ocr" | "missing"


@dataclass
class RetrievedField:
    data_type: str
    purpose: str
    source_tier: SourceTier
    chunks: list[EvidenceChunkContext] = field(default_factory=list)
    role: str | None = None
    tiers_tried: list[str] = field(default_factory=list)  # in order, e.g. ["chromadb", "mongodb"]

    def trace(self) -> dict:
        """Audit record for this requested item (fix.md "retrieval trace"):
        what was requested, which tiers were tried in order, which tier
        finally served it, and exactly which real chunks (source id +
        chunk index) came back. Purely descriptive - never invents a
        reference: an item that resolved nowhere is `missing: True` with no
        sources."""
        seen: set[tuple] = set()
        sources = []
        for chunk in self.chunks:
            key = (chunk.source_filename, chunk.chunk_index)
            if key not in seen:
                seen.add(key)
                sources.append({"source": chunk.source_filename, "chunkIndex": chunk.chunk_index})
        return {
            "requested": {"dataType": self.data_type, "role": self.role, "purpose": self.purpose},
            "tiersTried": list(self.tiers_tried),
            "resolvedTier": self.source_tier,
            "fallbackUsed": len(self.tiers_tried) > 1,
            "missing": self.source_tier == "missing",
            "chunkCount": len(self.chunks),
            "sources": sources[:25],
            "sourcesTruncated": len(sources) > 25,
        }


@dataclass
class RetrievedData:
    fields: list[RetrievedField] = field(default_factory=list)

    @property
    def all_chunks(self) -> list[EvidenceChunkContext]:
        """Deduplicated union of every field's chunks, in the order they were
        resolved - what a Criterion Agent's prompt actually gets fed as
        Evidence (see criterion_agents/_shared.py)."""
        seen: set[str] = set()
        out: list[EvidenceChunkContext] = []
        for retrieved_field in self.fields:
            for chunk in retrieved_field.chunks:
                if chunk.chunk_id not in seen:
                    seen.add(chunk.chunk_id)
                    out.append(chunk)
        return out

    @property
    def missing_data_types(self) -> list[str]:
        return [f.data_type for f in self.fields if f.source_tier == "missing"]


class RetrievalManager:
    def __init__(
        self,
        search_chroma: ChromaSearchFn,
        search_mongo: MongoSearchFn,
        search_document_ocr: DocumentOcrSearchFn,
        top_k: int = 6,
    ):
        self._search_chroma = search_chroma
        self._search_mongo = search_mongo
        self._search_document_ocr = search_document_ocr
        self._top_k = top_k



    # รับ data request มาจาก  master ส่งเข้ามา
    async def retrieve(
        self,
        requests: list[DataRequestItem],
        exclude_chunk_ids: list[str] | None = None,
    ) -> RetrievedData:
        exclude = exclude_chunk_ids or []
        fields: list[RetrievedField] = []
        for item in requests:
            fields.append(await self._retrieve_one(item, exclude))
        return RetrievedData(fields=fields)

    async def _retrieve_one(self, item: DataRequestItem, exclude: list[str]) -> RetrievedField:
        query = item.purpose if not item.role else f"{item.purpose} {item.role}"
        tried: list[str] = ["chromadb"]

        try:
            chroma_hits = await self._search_chroma(query, self._top_k, exclude)
        except Exception as exc:  # noqa: BLE001
            # A tier being unreachable (e.g. no ChromaDB server running) must
            # fall through to the next tier, not crash the whole retrieval -
            # change.md sec.8's fallback chain ("if still unavailable ->
            # missing") only works if a hard error from one tier is treated
            # the same as "this tier had nothing", same as an empty hit list.
            print(f"RetrievalManager: chromadb tier raised {type(exc).__name__}: {exc} - falling back")
            chroma_hits = []



            # Retrieval Manager ไม่ได้ไปแตะ MongoDB หรือ ChromaDB เอง มันมีหน้าที่หลักคือ:ตัดสินใจว่าจะลองค้นจากแหล่งไหนก่อน
            # มันจะหาจาก chroma ก่อน -> mongo db -> raw data โดยเอาข้อมูลมา และฟังชั้นจาก master มาที่มี mcp client
        if chroma_hits:
            return RetrievedField(
                data_type=item.data_type,
                purpose=item.purpose,
                source_tier="chromadb",
                chunks=[EvidenceChunkContext(**hit) for hit in chroma_hits],
                role=item.role,
                tiers_tried=tried,
            )

        tried.append("mongodb")
        try:                        
                                    # เป็นตัว ฟังขั้นของ master ส่งมาที่มี mcp client 
            mongo_hits_raw = await self._search_mongo(item)
        except Exception as exc:  # noqa: BLE001
            print(f"RetrievalManager: mongodb tier raised {type(exc).__name__}: {exc} - falling back")
            mongo_hits_raw = []
        if mongo_hits_raw:
            return RetrievedField(
                data_type=item.data_type,
                purpose=item.purpose,
                source_tier="mongodb",
                chunks=[EvidenceChunkContext(**hit) for hit in mongo_hits_raw],
                role=item.role,
                tiers_tried=tried,
            )

        tried.append("document_ocr")
        try:
            ocr_hits_raw = await self._search_document_ocr(item)
        except Exception as exc:  # noqa: BLE001
            print(f"RetrievalManager: document_ocr tier raised {type(exc).__name__}: {exc} - falling back")
            ocr_hits_raw = []
        if ocr_hits_raw:
            return RetrievedField(
                data_type=item.data_type,
                purpose=item.purpose,
                source_tier="document_ocr",
                chunks=[EvidenceChunkContext(**hit) for hit in ocr_hits_raw],
                role=item.role,
                tiers_tried=tried,
            )

        return RetrievedField(
            data_type=item.data_type, purpose=item.purpose, source_tier="missing", role=item.role, tiers_tried=tried
        )
