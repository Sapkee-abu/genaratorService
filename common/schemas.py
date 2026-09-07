from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SlotMark(BaseModel):
    """One slot the Slot Marking Agent decided to inject (addfeature.md)."""

    criterion: str
    slot_id: str
    type: Literal["narrative", "table"]
    target_type: Literal["paragraph", "table"]
    target_index: int  # p_index into document.paragraphs, or table_index into document.tables
    location_heading: str = ""
    table_headers: list[str] | None = None


class SlotMarkingResult(BaseModel):
    status: Literal["success"]
    marked_slots: list[SlotMark] = Field(default_factory=list)


class TargetSlot(BaseModel):
    slot_id: str
    type: Literal["narrative", "table"]
    criterion: str
    headers: list[str] | None = None  # table slots only
    groups: list[str] | None = None  # table slots only, when the table has >1 subheader-divided group
    rows_per_record: int | None = None  # table slots only, when >1 physical row makes up one logical record


class EvidenceChunkContext(BaseModel):
    chunk_id: str
    document_id: str | None = None
    chunk_index: int | None = None
    source_filename: str | None = None
    text: str


class GapAnalysis(BaseModel):
    status: Literal["complete", "missing", "not_applicable"]
    missing_fields: list[str] = Field(default_factory=list)


class CitationEntry(BaseModel):
    """Top-level citation (mainpromt.md sec.27/33): links a narrative's [N]
    marker, or a table row, back to the exact evidence span used."""

    citation_id: str
    text_span: str
    source_filename: str
    chunk_index: int

    @field_validator("citation_id")
    @classmethod
    def _citation_id_is_sequential_marker(cls, value: str) -> str:
        """citation_id must be a self-assigned sequential marker like "[1]",
        never a copy of chunk_id or any other identifier from the Evidence
        Chunks. Evidence chunks carry a `chunk_id` UUID (common.schemas.
        EvidenceChunkContext.chunk_id) purely for internal plumbing (e.g.
        master.py's retry exclusion list) - without this check, the LLM
        sometimes copies that UUID into citation_id instead of numbering its
        own citations, producing unreadable markers like
        "[3735e382-df65-44a5-9a23-021db45b6dbf]" in the final document.
        Raising here surfaces it as an AgentOutputError so master.py's
        retry loop asks the agent to fix it, instead of it silently making
        it into the generated SAR.
        """
        if not re.fullmatch(r"\[\d+\]", value):
            raise ValueError(
                f"citation_id '{value}' ต้องเป็นเลขอ้างอิงที่กำหนดเองแบบ [1], [2], [3] เท่านั้น "
                "ห้ามใช้ chunk_id หรือค่าอื่นจาก Evidence Chunks"
            )
        return value


class RowCitation(BaseModel):
    """Table-row citation (mainpromt.md sec.29): row-level only, no
    citation_id/text_span - just which evidence chunk backs this row."""

    source_filename: str
    chunk_index: int


class TableRow(BaseModel):
    values: list[str]
    citations: list[RowCitation] = Field(default_factory=list)
    group: str | None = None  # must match one of the TargetSlot's `groups`, when it has any
    record_key: str | None = None  # links sub-rows of one record, when the TargetSlot has `rows_per_record` > 1


class NarrativeSection(BaseModel):
    type: Literal["narrative"]
    slot_id: str
    content: str


class TableSection(BaseModel):
    type: Literal["table"]
    slot_id: str
    headers: list[str]
    rows: list[TableRow]


class AgentResponse(BaseModel):
    gap_analysis: GapAnalysis
    sections: list[NarrativeSection | TableSection]
    citations: list[CitationEntry] = Field(default_factory=list)
