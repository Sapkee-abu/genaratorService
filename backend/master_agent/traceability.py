"""Traceability Matrix helpers (mainpromt.md sec.50-51).

NOT used by the Master any more: the generated SAR DOCX must contain SAR content only, so
`append_traceability_matrix` is no longer called during Export. Traceability lives in the system
instead - generation_criteria_log / slot_map / the Reference API and the Web Reference page. The
helpers are kept only as a library (and for scripts/test_traceability_no_heading1.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from docx.document import Document as DocumentObject
from docx.shared import Pt

from common.schemas import AgentResponse, NarrativeSection, TableSection


@dataclass
class TraceabilityRecord:
    criterion: str
    slot_id: str
    location: str  # "narrative" or "table row N"
    citation_id: str
    source_filename: str
    chunk_index: int
    text_span: str


def collect_records(criterion: str, response: AgentResponse) -> list[TraceabilityRecord]:
    records: list[TraceabilityRecord] = []
    citation_by_id = {c.citation_id: c for c in response.citations}

    for section in response.sections:
        if isinstance(section, NarrativeSection):
            for citation_id, citation in citation_by_id.items():
                if citation_id in section.content:
                    records.append(
                        TraceabilityRecord(
                            criterion=criterion,
                            slot_id=section.slot_id,
                            location="narrative",
                            citation_id=citation.citation_id,
                            source_filename=citation.source_filename,
                            chunk_index=citation.chunk_index,
                            text_span=citation.text_span,
                        )
                    )
        elif isinstance(section, TableSection):
            for row_index, row in enumerate(section.rows):
                for row_citation in row.citations:
                    records.append(
                        TraceabilityRecord(
                            criterion=criterion,
                            slot_id=section.slot_id,
                            location=f"table row {row_index + 1}",
                            citation_id="-",
                            source_filename=row_citation.source_filename,
                            chunk_index=row_citation.chunk_index,
                            text_span="",
                        )
                    )
    return records


def _add_section_heading(document: DocumentObject, text: str) -> None:
    """Adds a heading-like paragraph without assuming the template defines
    a "Heading 1" style - real templates may define none at all (confirmed:
    the real SAR Template's `document.styles` only has Normal/List
    Paragraph/Table Grid - no heading family whatsoever), which makes
    `document.add_heading(..., "Heading 1")` raise KeyError.

    Uses the template's own "Heading 1" style when it actually exists (so
    behavior for templates that do define one is unchanged), otherwise
    falls back to a plain paragraph with bold, enlarged run formatting -
    this never creates/clones a named style in the template's styles.xml,
    so it can't collide with or alter any existing style, section, table,
    or header the template already defines.
    """
    if "Heading 1" in {style.name for style in document.styles}:
        document.add_heading(text, level=1)
        return

    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(16)


def append_traceability_matrix(document: DocumentObject, records: list[TraceabilityRecord]) -> None:
    document.add_page_break()
    _add_section_heading(document, "Traceability Matrix")

    table = document.add_table(rows=1, cols=6)
    try:
        table.style = "Table Grid"
    except KeyError:
        pass  # template doesn't define this built-in style - fall back to the default table look
    headers = ["Criterion", "Slot ID", "Location", "Citation", "Source Filename", "Chunk Index"]
    for cell, header in zip(table.rows[0].cells, headers):
        cell.text = header

    for record in records:
        row = table.add_row()
        values = [
            record.criterion,
            record.slot_id,
            record.location,
            record.citation_id,
            record.source_filename,
            str(record.chunk_index),
        ]
        for cell, value in zip(row.cells, values):
            cell.text = value
