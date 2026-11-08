"""Per-field Chroma -> MongoDB -> Document/OCR fallback (change.md sec.3/4/
28), for semantic fields where the retrieved evidence must be evaluated for
whether it actually SUPPORTS the requested field - not just "Chroma
returned something" (change.md sec.4's explicit anti-pattern).

Deliberately generic/mock-testable: `evidence_supports_field` and the
mongo/document_ocr value functions are injected callables, so the ladder
mechanism itself can be unit tested (change.md sec.35 TEST 11-14) without a
real Chroma/MongoDB connection - the real evaluator used against actual
retrieved evidence lives in criterion_agents/ps_agent/education_evidence.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

FieldValue = str | int | None


@dataclass
class FieldResolution:
    field: str
    value: FieldValue
    source: str  # "chroma" | "mongodb" | "document_ocr" | "missing"
    source_reference: dict


def resolve_field(
    field_name: str,
    chroma_evidence: list[dict],
    evidence_supports_field: Callable[[list[dict], str], tuple[bool, dict | None]],
    mongo_value_fn: Callable[[], tuple[FieldValue, dict] | None],
    document_ocr_value_fn: Callable[[], tuple[FieldValue, dict] | None] | None = None,
) -> FieldResolution:
    """change.md sec.28's pseudo-logic, literally: Chroma is tried first,
    but only ACCEPTED as the source when `evidence_supports_field` says the
    retrieved evidence genuinely supports this specific field (never just
    "Chroma returned N chunks"). Falls through to Mongo, then Document/OCR,
    then "missing" - the same tier never gets used twice, and a tier that
    can't help this field never blocks the next one.
    """
    sufficient, extracted = evidence_supports_field(chroma_evidence, field_name)
    if sufficient and extracted is not None:
        return FieldResolution(
            field=field_name, value=extracted["value"], source="chroma", source_reference=extracted["source_reference"]
        )

    mongo_result = mongo_value_fn()
    if mongo_result is not None:
        value, reference = mongo_result
        return FieldResolution(field=field_name, value=value, source="mongodb", source_reference=reference)

    if document_ocr_value_fn is not None:
        ocr_result = document_ocr_value_fn()
        if ocr_result is not None:
            value, reference = ocr_result
            return FieldResolution(field=field_name, value=value, source="document_ocr", source_reference=reference)

    return FieldResolution(field=field_name, value=None, source="missing", source_reference={})
