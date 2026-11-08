"""Regression test for change.md "Traceability - Heading 1": the real SAR
Template defines no heading-family style at all (confirmed against the real
downloaded template - `document.styles` only has Normal/Default Paragraph
Font/Normal Table/No List/List Paragraph/Table Grid), so the old
`document.add_heading(..., "Heading 1")` raised
`KeyError: "no style with name 'Heading 1'"` before ever reaching
document.save().

Uses the same real-template-shaped fixture (test_fixtures/template2.docx)
the table-injection tests use, which mirrors the real template exactly:
no Heading 1, has Table Grid, has existing tables/paragraphs/formatting.
"""

import sys
from pathlib import Path

import docx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.schemas import (  # noqa: E402
    AgentResponse,
    CitationEntry,
    GapAnalysis,
    NarrativeSection,
    RowCitation,
    TableRow,
    TableSection,
)
from master_agent.traceability import append_traceability_matrix, collect_records  # noqa: E402

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "test_fixtures" / "template2.docx"


def _sample_response() -> AgentResponse:
    return AgentResponse(
        gap_analysis=GapAnalysis(status="complete", missing_fields=[]),
        sections=[
            NarrativeSection(type="narrative", slot_id="intro_ps", content="เนื้อหาอ้างอิง [1] ตัวอย่าง"),
            TableSection(
                type="table",
                slot_id="table_ps_1_1",
                headers=["a", "b"],
                rows=[TableRow(values=["x", "y"], citations=[RowCitation(source_filename="doc.pdf", chunk_index=2)])],
            ),
        ],
        citations=[CitationEntry(citation_id="[1]", source_filename="doc.pdf", chunk_index=1, text_span="เนื้อหาอ้างอิง")],
    )


def test_real_template_has_no_heading1_style():
    document = docx.Document(str(TEMPLATE_PATH))
    style_names = {s.name for s in document.styles}
    assert "Heading 1" not in style_names, f"fixture no longer matches real template: {style_names}"
    print("test_real_template_has_no_heading1_style: PASS")


def test_append_traceability_matrix_does_not_crash():
    document = docx.Document(str(TEMPLATE_PATH))
    original_table_count = len(document.tables)
    original_style_names = {s.name for s in document.styles}

    records = collect_records("PS", _sample_response())
    assert len(records) == 2, f"expected 2 traceability records (1 narrative + 1 table row), got {len(records)}"

    append_traceability_matrix(document, records)  # must NOT raise KeyError

    # Traceability Matrix must actually be produced - a heading-like
    # paragraph plus a table with the real records, not silently skipped.
    heading_paragraphs = [p for p in document.paragraphs if p.text.strip() == "Traceability Matrix"]
    assert len(heading_paragraphs) == 1, "Traceability Matrix heading paragraph not found"
    heading_run = heading_paragraphs[0].runs[0]
    assert heading_run.bold, "fallback heading should be bold since no Heading 1 style exists to carry that"

    assert len(document.tables) == original_table_count + 1, "exactly one new table (the matrix) should be added"
    matrix_table = document.tables[-1]
    assert [c.text for c in matrix_table.rows[0].cells] == [
        "Criterion", "Slot ID", "Location", "Citation", "Source Filename", "Chunk Index",
    ]
    assert len(matrix_table.rows) == 1 + len(records), "one header row + one row per traceability record"

    # Must not have created/cloned a "Heading 1" style into the template -
    # the fallback is direct run formatting only, not a new named style.
    new_style_names = {s.name for s in document.styles}
    assert new_style_names == original_style_names, (
        f"append_traceability_matrix must not add/remove styles: {original_style_names} -> {new_style_names}"
    )
    print("test_append_traceability_matrix_does_not_crash: PASS")


def test_existing_template_tables_untouched():
    document = docx.Document(str(TEMPLATE_PATH))
    original_tables_content = [[c.text for row in t.rows for c in row.cells] for t in document.tables]

    records = collect_records("PS", _sample_response())
    append_traceability_matrix(document, records)

    for i, original in enumerate(original_tables_content):
        current = [c.text for row in document.tables[i].rows for c in row.cells]
        assert current == original, f"table {i} content changed by append_traceability_matrix"
    print("test_existing_template_tables_untouched: PASS")


def main() -> int:
    tests = [
        test_real_template_has_no_heading1_style,
        test_append_traceability_matrix_does_not_crash,
        test_existing_template_tables_untouched,
    ]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"{test.__name__}: FAIL - {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
