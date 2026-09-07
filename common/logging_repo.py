from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from common.mongo import get_db

COLLECTION = "generation_criteria_log"
SLOT_MARKING_COLLECTION = "generation_slot_marking_log"


async def log_slot_marking(run_id: str, status: str, marked_slots: list[dict[str, Any]]) -> None:
    """addfeature.md: records the Slot Marking Agent's JSON result for this run."""
    db = get_db()
    await db[SLOT_MARKING_COLLECTION].insert_one(
        {
            "run_id": run_id,
            "status": status,
            "total_slots_marked": len(marked_slots),
            "marked_slots": marked_slots,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def log_criterion(run_id: str, criterion: str, status: str, citations: list[dict[str, Any]]) -> None:
    """mainpromt.md sec.44: after a criterion passes verification + injection,
    record its status and citation mapping so retrieved evidence can always
    be traced back through to what was actually written.
    """
    db = get_db()
    await db[COLLECTION].insert_one(
        {
            "run_id": run_id,
            "criterion": criterion,
            "status": status,
            "citations": citations,
            "created_at": datetime.now(timezone.utc),
        }
    )
