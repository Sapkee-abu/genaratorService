"""Slot map (fix.md sec.11/12): which body block / table row of the FINAL
generated DOCX holds which slot / agent row. Built once at export, from the
same in-memory ResolvedSlot/Placement objects injection already used, so it
records what actually happened - never a re-scan/guess of the saved file.

Keyed by document body block index (the order `iter_block_items` yields,
which `document.docx_to_html` also uses), so the HTML renderer can attach
`data-slot-id` / `data-reference-id` to exactly the right element without
the DOCX itself needing any embedded marker.
"""

from __future__ import annotations

from docx.document import Document as DocumentObject

from master_agent.docx_utils import iter_block_items
from master_agent.slot_marking_agent import ResolvedSlot
from master_agent.template_injector import Placement

SLOT_MAP_VERSION = 1


def build_slot_map(
    document: DocumentObject,
    resolved_slots: dict[str, ResolvedSlot],
    injected_slot_ids: set[str],
    placements: list[Placement],
) -> dict:
    block_index_of: dict[int, int] = {}
    for index, item in enumerate(iter_block_items(document)):
        element = item._p if hasattr(item, "_p") else item._tbl
        block_index_of[id(element)] = index

    paragraphs: dict[str, dict] = {}
    tables: dict[str, dict] = {}

    for slot_id in injected_slot_ids:
        resolved = resolved_slots.get(slot_id)
        if resolved is None:
            continue
        if resolved.type == "narrative" and resolved.paragraph is not None:
            block = block_index_of.get(id(resolved.paragraph._p))
            if block is not None:
                paragraphs[str(block)] = {"slotId": slot_id, "criterion": resolved.criterion}
        elif resolved.type == "table" and resolved.table is not None:
            block = block_index_of.get(id(resolved.table._tbl))
            if block is None:
                continue
            tr_list = list(resolved.table._tbl.tr_lst)
            rows: dict[str, int] = {}
            for placement in placements:
                if placement.slot_id != slot_id:
                    continue
                rows[str(tr_list.index(placement.tr))] = placement.row_index
            tables[str(block)] = {"slotId": slot_id, "criterion": resolved.criterion, "rows": rows}

    return {"version": SLOT_MAP_VERSION, "paragraphs": paragraphs, "tables": tables}
