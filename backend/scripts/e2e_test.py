"""End-to-end test for the Generator Service.

Uploads synthetic Template/Example/Evidence fixtures to a running Import
Service (must be up on IMPORT_BASE_URL, with its ChromaDB server also
running), waits for evidence processing, runs the Master Agent, checks the
output .docx contains the expected injected content (and NOT the Example's
deliberately-wrong fact, to catch example-contamination), then removes the
fixtures it uploaded.

No Guideline file is uploaded here: per changefeature.md, the Generator reads
each criterion's guideline straight from master_config.json, not from an
uploaded Guideline file (Import Service's own Guideline upload feature still
exists for its own purposes, the Generator just doesn't consume it anymore).

Usage:
    python scripts/e2e_test.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import docx
import requests

IMPORT_BASE_URL = "http://127.0.0.1:8000"
FIXTURES = Path(__file__).resolve().parent.parent / "test_fixtures"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master_agent.master import run as run_master  # noqa: E402


def upload_reference(reference_type: str, path: Path) -> str:
    with path.open("rb") as fh:
        response = requests.post(f"{IMPORT_BASE_URL}/api/references/{reference_type}/upload", files={"file": (path.name, fh)})
    response.raise_for_status()
    return response.json()["file_id"]


def upload_evidence(path: Path) -> str:
    with path.open("rb") as fh:
        response = requests.post(f"{IMPORT_BASE_URL}/api/evidence/upload", files={"files": (path.name, fh)})
    response.raise_for_status()
    return response.json()["created"][0]["document_id"]


def wait_for_evidence(document_id: str, timeout: int = 120) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        doc = requests.get(f"{IMPORT_BASE_URL}/api/evidence/{document_id}").json()
        if doc["status"] in ("completed", "failed"):
            return doc
        time.sleep(2)
    raise TimeoutError("evidence did not finish processing in time")


def main() -> int:
    print("Uploading fixtures to Import Service...")
    template_id = upload_reference("template", FIXTURES / "template_unmarked.docx")
    example_id = upload_reference("example", FIXTURES / "example_style.docx")
    evidence_id = upload_evidence(FIXTURES / "evidence_instructors.docx")

    try:
        evidence_doc = wait_for_evidence(evidence_id)
        if evidence_doc["status"] != "completed":
            print("FAIL: evidence processing did not complete:", evidence_doc.get("error"))
            return 1
        print("Evidence processed. Running Master Agent...")

        output_path = asyncio.run(run_master())
        print("Generated:", output_path)

        document = docx.Document(str(output_path))
        all_text = "\n".join(p.text for p in document.paragraphs)
        table_cells = [cell.text for table in document.tables for row in table.rows for cell in row.cells]

        checks = {
            "narrative injected with real fact (5 instructors)": "5" in all_text and "อาจารย์ผู้รับผิดชอบหลักสูตร" in all_text,
            "citation marker present": "[1]" in all_text,
            "example's fake number (99) did NOT leak in": "99" not in all_text,
            "real instructor name made it into the table": any("สมชาย" in c for c in table_cells),
            "NO traceability matrix in the DOCX (SAR content only)": "Traceability Matrix" not in all_text,
        }

        ok = True
        for description, passed in checks.items():
            print(f"  [{'OK' if passed else 'FAIL'}] {description}")
            ok = ok and passed

        return 0 if ok else 1
    finally:
        print("Cleaning up fixtures...")
        requests.delete(f"{IMPORT_BASE_URL}/api/references/template/{template_id}")
        requests.delete(f"{IMPORT_BASE_URL}/api/references/example/{example_id}")
        requests.delete(f"{IMPORT_BASE_URL}/api/evidence/{evidence_id}")


if __name__ == "__main__":
    sys.exit(main())
