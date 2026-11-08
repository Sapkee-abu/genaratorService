"""Field-level User Edit traceability (fix.md sec.12/13/14/22).

Turns the list of elements a user changed (document.docx_edit.ElementChange,
computed against the generated DOCX) into the list frozen into a Version
Snapshot. Attribution comes ONLY from server-side data - the run's own
slot_map (which block/row holds which slot) and its Reference items
(generation_criteria_log) - never from client-supplied HTML attributes.

  * mapped to a real Reference item with a real source
      -> sourceType/sourceReference stay the ORIGINAL source (mongodb/chroma/
         document_ocr); originalValue + currentValue + userEdited=true.
         The source is never presented as having produced the edit.
  * anything else (no slot mapping, no Reference item, or the item has no
    real source) -> sourceType="user_edit", no sourceReference (nothing is
    invented).

Pure read/compute: never writes anywhere, never touches Source Data.
"""

from __future__ import annotations

from common.logging_repo import get_slot_map
from document.docx_edit import ElementChange
from reference.traceability_api import build_reference_tree

_REAL_SOURCES = {"mongodb", "chroma", "document_ocr"}


def _reference_item_id(change: ElementChange, slot_map: dict | None) -> tuple[str | None, str | None]:
    """(slot_id, reference_item_id) for a change, or (None, None) when the
    generated document has no known slot for that element."""
    if not slot_map:
        return None, None
    if change.kind == "paragraph":
        info = slot_map.get("paragraphs", {}).get(str(change.block))
        return (info["slotId"], info["slotId"]) if info else (None, None)
    info = slot_map.get("tables", {}).get(str(change.block))
    if not info:
        return None, None
    agent_row = info.get("rows", {}).get(str(change.row))
    if agent_row is None:
        return info["slotId"], None
    return info["slotId"], f"{info['slotId']}.row{agent_row}.col{change.col}"


async def build_user_edits(run_id: str, changes: list[ElementChange]) -> list[dict]:
    if not changes:
        return []

    slot_map = await get_slot_map(run_id)
    items = (await build_reference_tree(run_id))["items"]

    edits: list[dict] = []
    for change in changes:
        slot_id, reference_item_id = _reference_item_id(change, slot_map)
        item = items.get(reference_item_id) if reference_item_id else None

        edit = {
            "elementId": change.element_id,
            "slotId": slot_id,
            "referenceItemId": reference_item_id if item is not None else None,
            "originalValue": "\n".join(change.original_lines),
            "currentValue": "\n".join(change.current_lines),
            "userEdited": True,
        }
        if item is not None:
            edit["field"] = item["field"]
            if item.get("source") in _REAL_SOURCES:
                edit["sourceType"] = item["source"]
                edit["sourceReference"] = item.get("sourceReference") or {}
            else:
                edit["sourceType"] = "user_edit"
        else:
            edit["field"] = (
                f"Paragraph {change.block}"
                if change.kind == "paragraph"
                else f"Table {change.block} row {change.row} col {change.col}"
            )
            edit["sourceType"] = "user_edit"
        edits.append(edit)
    return edits
