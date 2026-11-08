"""Example extraction (mainpromt.md sec.7): Master itself extracts full text
+ tables from the Example file, kept as plain text in memory.

Guideline no longer goes through this module - per changefeature.md, each
criterion's guideline is written directly in master_config.json, not sliced
out of an uploaded file.
"""

from __future__ import annotations

import io
from collections import OrderedDict

import docx
import fitz  # pymupdf

from common.schemas import EvidenceChunkContext


def extract_text(content: bytes, file_format: str) -> str:
    file_format = file_format.lower()
    if file_format == "pdf":
        parts = []
        with fitz.open(stream=content, filetype="pdf") as pdf:
            for page in pdf:
                parts.append(page.get_text())
        return "\n".join(parts)
    if file_format == "docx":
        document = docx.Document(io.BytesIO(content))
        parts = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        return "\n".join(parts)
    raise ValueError(f"Unsupported example format: {file_format}")


def group_evidence_by_source(chunks: list[EvidenceChunkContext]) -> tuple[str, int]:
    """Groups retrieved Evidence Chunks by `source_filename` into one clearly
    delimited block per file, instead of handing the Criteria Agent one flat
    list of ~100 chunks pre-ranked by semantic similarity.

    Why: with a large criterion (e.g. PS, evidence_top_k=100 across 14
    instructor CVs), a flat relevance-ranked list scatters one file's chunks
    all over the context (rank 4, 21, 43, ... for the same person) - a
    known LLM failure mode ("lost in the middle") where the model drops a
    few records when synthesizing a long list from a long, unstructured
    context. Grouping by source file first, each internally ordered by its
    own `chunk_index` (reading order within that document, not relevance
    rank), gives the model one clean, complete block per candidate record
    and an explicit "SOURCE i / N" count so it has something concrete to
    check its own output against - see criteria_agent.py's completeness rule.

    Returns (formatted_text, source_count). Chunks with no `source_filename`
    are grouped under a single fallback label rather than dropped.
    """
    if not chunks:
        return "(ไม่มี Evidence Chunk ที่เกี่ยวข้อง)", 0

    grouped: "OrderedDict[str, list[EvidenceChunkContext]]" = OrderedDict()
    for chunk in chunks:
        key = chunk.source_filename or "(ไม่ทราบชื่อไฟล์)"
        grouped.setdefault(key, []).append(chunk)

    source_count = len(grouped)
    blocks = [f"[EVIDENCE_SOURCES] (ตรวจพบไฟล์หลักฐานทั้งหมด {source_count} ไฟล์)"]
    for i, (source_filename, source_chunks) in enumerate(grouped.items(), start=1):
        blocks.append(f"\n=== SOURCE {i} / {source_count}: {source_filename} ===")
        for chunk in sorted(source_chunks, key=lambda c: c.chunk_index if c.chunk_index is not None else 0):
            blocks.append(f"[Chunk {chunk.chunk_index}] {chunk.text}")

    return "\n".join(blocks), source_count
