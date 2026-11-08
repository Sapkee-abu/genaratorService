"""Standalone test of the Slot Marking Agent against an unmarked template -
no Import Service / MCP round trip needed, just Gemini + the local fixture.
Verifies: the real data table gets marked, the static checklist table does
NOT, and the resolved slots point at the correct objects.
"""

import json
import sys
from pathlib import Path

import docx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master_agent.slot_marking_agent import apply_marks, run_slot_marking_agent  # noqa: E402
from master_agent.template_structure import describe_document  # noqa: E402

CRITERIA_META = json.loads(Path(__file__).resolve().parent.parent.joinpath("master_config.json").read_text(encoding="utf-8"))[
    "criteria"
]


def main() -> int:
    document = docx.Document(str(Path(__file__).resolve().parent.parent / "test_fixtures" / "template_unmarked.docx"))
    structure = describe_document(document)

    result = run_slot_marking_agent(structure, {"PS": CRITERIA_META["PS"]})
    print(f"Agent proposed {len(result.marked_slots)} slot(s):")
    for mark in result.marked_slots:
        print(
            f"  - {mark.criterion} / {mark.slot_id} ({mark.type}) "
            f"target={mark.target_type}:{mark.target_index} :: {mark.location_heading}"
        )

    resolved = apply_marks(document, structure, result.marked_slots)
    print(f"Resolved {len(resolved)}/{len(result.marked_slots)} slot(s)")
    for slot_id, r in resolved.items():
        print(f"  - {slot_id}: type={r.type} headers={r.headers}")

    checks = {
        "at least one narrative slot for PS": any(r.type == "narrative" and r.criterion == "PS" for r in resolved.values()),
        "at least one table slot for PS with instructor headers": any(
            r.type == "table" and r.headers == ["ลำดับ", "ชื่อ-สกุล", "คุณวุฒิ"] for r in resolved.values()
        ),
        "the static checklist table was NOT marked": not any(
            r.type == "table" and r.headers and "เกณฑ์การประเมิน" in r.headers[0] for r in resolved.values()
        ),
    }

    ok = True
    for description, passed in checks.items():
        print(f"  [{'OK' if passed else 'FAIL'}] {description}")
        ok = ok and passed

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
