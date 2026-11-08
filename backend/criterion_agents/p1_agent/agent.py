"""P1 Agent (change.md sec.5).

Handles ONLY the P1 criterion. Owns its own Prompt
(prompt/system_prompt.txt) and Schema (schema/output_schema.json), separate
from every other Criterion Agent - see criterion_agents/_shared.py for the
mechanics this module renders its own content into.

prompt/system_prompt.txt is intentionally empty: no criterion-specific rules
have been supplied yet, so this agent runs with only the shared,
criterion-agnostic instructions. Not implemented yet (criteria are built
one at a time, PS first): its own Data Requirement - derived from its
Target Slots per SRS FR-010 - still has to be written in
build_data_request(), which requests nothing until then.
"""

from __future__ import annotations

from pathlib import Path

from common.schemas import AgentResponse, DataRequest, EvidenceChunkContext, TargetSlot
from criterion_agents import _shared
from criterion_agents._shared import AgentOutputError  # re-exported for master.py

CRITERION_CODE = "P1"

_EXTRA_RULES = (Path(__file__).parent / "prompt" / "system_prompt.txt").read_text(encoding="utf-8")


def build_data_request(target_slots: list[TargetSlot]) -> DataRequest:
    return _shared.default_build_data_request(CRITERION_CODE)


def run(
    criterion_name: str,
    evidence_chunks: list[EvidenceChunkContext],
    target_slots: list[TargetSlot],
    current_academic_year: int | None = None,
    feedback: str | None = None,
) -> AgentResponse:
    return _shared.run_agent(
        CRITERION_CODE,
        criterion_name,
        evidence_chunks,
        target_slots,
        current_academic_year,
        feedback,
        extra_rules=_EXTRA_RULES,
    )
