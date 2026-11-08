"""P3 Agent (change.md sec.5).

Handles ONLY the P3 criterion. Owns its own Prompt
(prompt/system_prompt.txt) and Schema (schema/output_schema.json), separate
from every other Criterion Agent - see criterion_agents/_shared.py for the
mechanics this module renders its own content into.

prompt/system_prompt.txt is intentionally empty: master_config.json's
criteria.P3.guideline is still [] (no real AUN-QA P3 guideline
text has been supplied yet - master_config.json's own comment: "never
fabricate AUN-QA guideline text without a source"). This agent runs with
only the shared, criterion-agnostic instructions until that content is
provided; supplying it is a content decision outside this codebase's
authority (see the migration report's "DECISION REQUIRED" items for P3).
"""

from __future__ import annotations

from pathlib import Path

from common.schemas import AgentResponse, DataRequest, EvidenceChunkContext, TargetSlot
from criterion_agents import _shared
from criterion_agents._shared import AgentOutputError  # re-exported for master.py

CRITERION_CODE = "P3"

_EXTRA_RULES = (Path(__file__).parent / "prompt" / "system_prompt.txt").read_text(encoding="utf-8")


def build_data_request(meta: dict, target_slots: list[TargetSlot]) -> DataRequest:
    return _shared.default_build_data_request(CRITERION_CODE, meta)


def run(
    criterion_name: str,
    guideline: list[str],
    keywords: list[str],
    required_evidence: list[str],
    example_section: str,
    evidence_chunks: list[EvidenceChunkContext],
    target_slots: list[TargetSlot],
    current_academic_year: int | None = None,
    feedback: str | None = None,
) -> AgentResponse:
    return _shared.run_agent(
        CRITERION_CODE,
        criterion_name,
        guideline,
        keywords,
        required_evidence,
        example_section,
        evidence_chunks,
        target_slots,
        current_academic_year,
        feedback,
        extra_rules=_EXTRA_RULES,
    )
