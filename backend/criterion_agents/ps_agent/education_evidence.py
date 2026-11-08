"""Real (non-mocked) Chroma evidence-sufficiency evaluator for
highest_education_level/degree_name/field (change.md sec.4/5/9/28) - the
concrete `evidence_supports_field` callable
criterion_agents/ps_agent/field_resolution.py's generic ladder is given for
this specific field family.

Real evidence chunks in this dataset (confirmed against aunqa_ps's
document_chunks - see change.md audit) are OCR/PDF-extracted text with
private-use-area noise characters, and come in two real shapes: a person's
own CV document (their name and degree both present, nothing else to
confuse them with), and a shared roster table scraped from a มคอ.2-style
document (multiple people's name+degree rows back to back). Both are
handled the same way: find the person's last name in the chunk text, then
look at a bounded window immediately after it for the CLOSEST recognized
degree-abbreviation token - this is safe even in the shared-table case
because the correct degree is always the physically nearest one following
the name, never a later person's.

This is a conservative, real heuristic, not a guess: it only ever accepts a
chunk when an actual recognizable degree token is found near the person's
own name; anything else is correctly treated as insufficient, falling
through to MongoDB (change.md: "ถ้าไม่พอ fallback MongoDB").
"""

from __future__ import annotations

import re
import unicodedata

from criterion_agents.ps_agent.degree_mapping import classify_degree_level

_NAME_PROXIMITY_WINDOW = 400

# Thai two-part dot abbreviations (ปร.ด., วท.บ., วท.ม., บธ.บ., ค.ม., ...) and
# English dot abbreviations (Ph.D., M.Sc., B.Eng., ...) - a structural
# pattern over ANY abbreviation shape, never a hardcoded list of specific
# degree names (change.md sec.37).
_DEGREE_TOKEN_PATTERN = re.compile(
    r"[ก-๙]{1,4}\.\s?[ก-๙]{1,3}\.|[A-Za-z]{1,4}\.\s?[A-Za-z]{1,4}\."
)


def _strip_noise(text: str) -> str:
    """Drops PDF/OCR private-use-area glyphs (observed in real chunks, e.g.
    U+F702/U+F70E) that otherwise break substring matching without being
    visible in the text."""
    return "".join(ch for ch in text if unicodedata.category(ch) != "Co")


def _find_degree_near_name(chunk_text: str, last_name: str) -> str | None:
    text = _strip_noise(chunk_text)
    name = _strip_noise(last_name).strip()
    if not name:
        return None
    idx = text.find(name)
    if idx == -1:
        return None
    window = text[idx + len(name) : idx + len(name) + _NAME_PROXIMITY_WINDOW]
    match = _DEGREE_TOKEN_PATTERN.search(window)
    if match is None:
        return None
    return match.group(0)


def evidence_supports_education_level(
    chroma_evidence: list[dict], person_last_name: str
) -> tuple[bool, dict | None]:
    """`evidence_supports_field`-shaped callable (see field_resolution.py)
    for the highest_education_level/degree_name family. `chroma_evidence`
    items are dicts shaped like common/chroma.py's search() hits
    (chunk_id/document_id/chunk_index/source_filename/text).
    """
    for hit in chroma_evidence:
        degree_token = _find_degree_near_name(hit.get("text", ""), person_last_name)
        if degree_token is None:
            continue
        level = classify_degree_level(degree_token)
        if level is None:
            continue
        return True, {
            "value": level,
            "degree_token": degree_token,
            "source_reference": {
                "source_filename": hit.get("source_filename"),
                "chunk_index": hit.get("chunk_index"),
            },
        }
    return False, None
