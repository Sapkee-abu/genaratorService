"""Traceability Matrix (mainpromt.md sec.50-51): appended once, at Export,
after every criterion has been injected - lets a reader trace any narrative
statement or table row back to citation_id -> source_filename/chunk_index.
"""

from __future__ import annotations

from dataclasses import dataclass

from docx.document import Document as DocumentObject

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


def append_traceability_matrix(document: DocumentObject, records: list[TraceabilityRecord]) -> None:
    document.add_page_break()
    document.add_heading("Traceability Matrix", level=1)

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
