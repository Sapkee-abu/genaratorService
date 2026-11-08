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


class DataRequestItem(BaseModel):
    """One thing a Criterion Agent needs (change.md sec.7). `data_type` is a
    free-form label the Agent chooses - not a Python enum, since a generic
    "evidence" request (still used by every non-PS agent, resolved only via
    ChromaDB/Document-OCR) coexists with the Final-Schema-aware types
    retrieval/mongodb.py knows how to map deterministically: "curriculum",
    "person", "education", "appointment", "academic_work", "document",
    "data_usage" (Dataschema.md's 9 collections, minus `ps_requirements` and
    `generated_documents` - see retrieval/mongodb.py's module docstring for
    why). `role` is set only when `data_type="appointment"` and the Agent is
    asking specifically about one of the three appointment roles
    (programmeResponsible / programmeStaff / specialInstructor) - role lives
    on `appointments.role`, never on `persons` (Dataschema.md sec.2)."""

    data_type: str
    purpose: str
    role: str | None = None


class DataRequest(BaseModel):
    """A Criterion Agent's own Data Requirement (change.md sec.7) - built by
    the Agent itself from its Prompt/Logic/Template Structure, never by
    Master or the Retrieval Manager (change.md: "The Retrieval Manager does
    NOT decide what the Criterion requires. The Master does NOT decide what
    the Criterion requires.")."""

    criterion: str
    requests: list[DataRequestItem] = Field(default_factory=list)


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
    column_citations: dict[str, list[RowCitation]] | None = None
    """Optional per-column provenance (key = logical column index as a string).
    Set only by agents that build a row deterministically from known sources
    (PS): lets the Reference API attribute each cell to the record that really
    produced it instead of pointing every column at the row's first citation.
    `citations` (the row-level list Verification checks) stays the union, so
    nothing about Verification/Injection changes. A column absent from this
    dict (or with an empty list) has NO source - never guessed."""
    checked_options: list[str] | None = None
    """change.md sec.13: a multi-role record's checkbox must show every
    matching option checked at once (e.g. Responsible + Staff -> both
    checked), not just one - `group` alone can only ever mark a single
    option. When set, template_injector.py's checkbox-writing uses this
    list instead of the single-`group` match; when None (the common,
    single-category case), existing group-based behavior is unchanged."""


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
