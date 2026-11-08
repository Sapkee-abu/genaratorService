"""Document/OCR fallback tier for the Retrieval Manager (change.md sec.8,
tier 3 - the last resort before a field is reported missing).

A real OCR pipeline (scanning uploaded PDFs/images page-by-page) is
out of scope for this change (DO NOT TOUCH per the locked migration scope).
This module is the real integration point for one: `search()` is the exact
function retrieval/manager.py calls after both ChromaDB and MongoDB come
back empty for a field. Wiring up a real OCR service later only means
implementing the body of this function - no change needed anywhere else in
the Retrieval Manager, Master, or any Criterion Agent.
"""

from __future__ import annotations

from common.schemas import DataRequestItem, EvidenceChunkContext


async def search(item: DataRequestItem) -> list[EvidenceChunkContext]:
    # No OCR pipeline is wired up yet - always "not found", never fabricated.
    return []
