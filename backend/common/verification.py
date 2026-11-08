"""Three verification gates (mainpromt.md sec.34-38) run on a Criteria
Agent's JSON output before it's allowed anywhere near Template Injection.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer, util

from common.config import get_settings
from common.schemas import AgentResponse, EvidenceChunkContext, NarrativeSection, TableSection

_st_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _st_model
    if _st_model is None:
        settings = get_settings()
        # Explicit CPU device: sentence-transformers otherwise auto-selects
        # CUDA when a GPU is present, but this machine's GPU (compute
        # capability 5.0) is older than what the installed PyTorch CUDA
        # build supports (>=7.5), which fails at encode() time - an
        # environment issue, not a change to Gate 2's logic/threshold.
        _st_model = SentenceTransformer(settings.sentence_transformer_model, device="cpu")
    return _st_model


@dataclass
class VerificationResult:
    passed: bool
    issues: list[str] = field(default_factory=list)

    def feedback_text(self) -> str:
        return "กรุณาแก้ไขปัญหาต่อไปนี้แล้วส่งผลลัพธ์ใหม่:\n" + "\n".join(f"- {issue}" for issue in self.issues)


def _chunk_lookup(evidence_chunks: list[EvidenceChunkContext]) -> dict[tuple[str, int], str]:
    return {(c.source_filename, c.chunk_index): c.text for c in evidence_chunks if c.source_filename is not None}


def _gate1_spelling_number(response: AgentResponse, chunk_lookup: dict[tuple[str, int], str]) -> list[str]:
    """rapidfuzz: every citation's text_span must fuzzy-match the evidence
    chunk it claims to come from, so a wrong name/number/date doesn't slip
    through as a "citation" pointing at text that doesn't actually say that.

    Also checks (narrative and table alike, per changefeature.md sec.20) that
    every citation's source_filename/chunk_index actually exists among the
    Evidence Chunks given to the agent - a citation pointing at a chunk that
    was never provided is as good as a fabricated one, even before we get to
    comparing the text itself. Table row citations have no text_span (see
    RowCitation), so only the existence check applies to them.
    """
    settings = get_settings()
    issues = []
    for citation in response.citations:
        key = (citation.source_filename, citation.chunk_index)
        chunk_text = chunk_lookup.get(key)
        if chunk_text is None:
            issues.append(
                f"Citation {citation.citation_id} อ้างอิง {citation.source_filename} "
                f"chunk {citation.chunk_index} ซึ่งไม่อยู่ใน Evidence Chunks ที่ให้ไป (ห้ามอ้างอิงนอกเหนือ Evidence)"
            )
            continue
        score = fuzz.partial_ratio(citation.text_span, chunk_text)
        if score < settings.rapidfuzz_threshold:
            issues.append(
                f"Citation {citation.citation_id}: text_span ไม่ตรงกับเนื้อหาจริงใน "
                f"{citation.source_filename} chunk {citation.chunk_index} (fuzzy match {score:.0f} "
                f"< threshold {settings.rapidfuzz_threshold}) - ตรวจสอบตัวสะกด/ตัวเลข/ชื่อ"
            )

    for section in response.sections:
        if not isinstance(section, TableSection):
            continue
        for row_index, row in enumerate(section.rows):
            for row_citation in row.citations:
                key = (row_citation.source_filename, row_citation.chunk_index)
                if key not in chunk_lookup:
                    issues.append(
                        f"Table slot {section.slot_id} row {row_index + 1}: citation อ้างอิง "
                        f"{row_citation.source_filename} chunk {row_citation.chunk_index} ซึ่งไม่อยู่ใน "
                        f"Evidence Chunks ที่ให้ไป"
                    )

    return issues


def _gate2_semantic_similarity(response: AgentResponse, chunk_lookup: dict[tuple[str, int], str]) -> list[str]:
    """sentence-transformers: generated content must be semantically close to
    the evidence it's citing - anti-hallucination check independent of exact
    wording (Gate 1 already covers exact spans)."""
    settings = get_settings()
    model = _get_model()
    issues = []

    for section in response.sections:
        if isinstance(section, NarrativeSection):
            cited = [
                chunk_lookup[(c.source_filename, c.chunk_index)]
                for c in response.citations
                if (c.source_filename, c.chunk_index) in chunk_lookup and c.citation_id in section.content
            ]
            if not cited:
                continue  # Gate 3 already flags missing citations
            similarity = _max_similarity(model, section.content, cited)
            if similarity < settings.semantic_similarity_threshold:
                issues.append(
                    f"Narrative slot {section.slot_id}: semantic similarity กับ Evidence ต่ำเกินไป "
                    f"({similarity:.2f} < {settings.semantic_similarity_threshold}) - เนื้อหาอาจไม่ตรงกับหลักฐาน"
                )
        elif isinstance(section, TableSection):
            for row_index, row in enumerate(section.rows):
                cited = [
                    chunk_lookup[(c.source_filename, c.chunk_index)]
                    for c in row.citations
                    if (c.source_filename, c.chunk_index) in chunk_lookup
                ]
                if not cited:
                    continue
                row_text = " ".join(row.values)
                similarity = _max_similarity(model, row_text, cited)
                if similarity < settings.semantic_similarity_threshold:
                    issues.append(
                        f"Table slot {section.slot_id} row {row_index + 1}: semantic similarity "
                        f"กับ Evidence ต่ำเกินไป ({similarity:.2f} < {settings.semantic_similarity_threshold})"
                    )
    return issues


def _max_similarity(model: SentenceTransformer, text: str, candidates: list[str]) -> float:
    text_emb = model.encode(text, convert_to_tensor=True)
    candidate_embs = model.encode(candidates, convert_to_tensor=True)
    scores = util.cos_sim(text_emb, candidate_embs)
    return float(scores.max())


def _gate3_completeness(response: AgentResponse) -> list[str]:
    issues = []
    if response.gap_analysis.status == "missing":
        fields = ", ".join(response.gap_analysis.missing_fields) or "(ไม่ระบุ)"
        issues.append(f"gap_analysis.status = missing (missing_fields: {fields}) - Evidence ไม่เพียงพอ")

    citation_ids = {c.citation_id for c in response.citations}

    for section in response.sections:
        if isinstance(section, NarrativeSection):
            has_marker = any(cid in section.content for cid in citation_ids)
            if not has_marker:
                issues.append(f"Narrative slot {section.slot_id}: ไม่มี Citation Number ([n]) ในเนื้อหา")
        elif isinstance(section, TableSection):
            for row_index, row in enumerate(section.rows):
                if not row.citations:
                    issues.append(f"Table slot {section.slot_id} row {row_index + 1}: ไม่มี Citation")

    return issues


def verify(response: AgentResponse, evidence_chunks: list[EvidenceChunkContext]) -> VerificationResult:
    chunk_lookup = _chunk_lookup(evidence_chunks)
    issues = []
    issues += _gate1_spelling_number(response, chunk_lookup)
    issues += _gate2_semantic_similarity(response, chunk_lookup)
    issues += _gate3_completeness(response)
    return VerificationResult(passed=not issues, issues=issues)
