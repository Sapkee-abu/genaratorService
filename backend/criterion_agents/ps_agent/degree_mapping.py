"""Deterministic degree-abbreviation -> education-level classification
(change.md sec.5/9/26 - "highest_education_level ไม่ใช่ degree name...
ห้ามให้ LLM เดา/ขยาย abbreviation").

Real `educations.degree` values (confirmed against aunqa_ps) are ALREADY
abbreviations, not full names - e.g. "ปร.ด.", "วท.บ.", "วท.ม.", "บธ.บ.",
"Ph.D." - never "ปรัชญาดุษฎีบัณฑิต". Thai academic-degree abbreviations are
structurally suffixed by level (...ด. = doctoral, ...ม. = master's,
...บ. = bachelor's - a real, general convention, not specific to any one
degree name), so classification is a structural pattern match, never a
hardcoded list of specific degree names.
"""

from __future__ import annotations

import re

HIGHEST_EDUCATION_LEVELS = ("ปริญญาเอก", "ปริญญาโท", "ปริญญาตรี")
_LEVEL_RANK = {level: rank for rank, level in enumerate(HIGHEST_EDUCATION_LEVELS)}  # 0 = highest

_ENGLISH_DOCTORAL = re.compile(r"ph\.?\s*d\.?|ed\.?\s*d\.?|doctor", re.IGNORECASE)
_ENGLISH_MASTER = re.compile(r"^m\.|master", re.IGNORECASE)
_ENGLISH_BACHELOR = re.compile(r"^b\.|bachelor", re.IGNORECASE)

# A Thai dotted abbreviation whose FINAL dot was simply omitted in the source
# (real aunqa_ps educations contain "วท.บ", "สท.บ" - confirmed by the real-data
# audit, which found the highest-level column blank for such a person). Only
# this exact abbreviation SHAPE (internal dot, 1-3 Thai letters after it, no
# other text) is normalized, so ordinary words/field names that merely end in
# ด/ม/บ are never misread as a degree.
_THAI_ABBREVIATION_MISSING_FINAL_DOT = re.compile(r"^[ก-๙]{1,4}\.\s?[ก-๙]{1,3}$")

_THAI_DOCTORAL_SUFFIX = re.compile(r"ด\.\s*$")
_THAI_MASTER_SUFFIX = re.compile(r"ม\.\s*$")
_THAI_BACHELOR_SUFFIX = re.compile(r"บ\.\s*$")

# Full (non-abbreviated) Thai degree names always end in one of these three
# suffixes - a real, general naming convention ("ดุษฎีบัณฑิต"=Doctor,
# "มหาบัณฑิต"=Master, "บัณฑิต"=Bachelor), not a hardcoded list of specific
# degree names. Order matters: the more specific suffixes must be checked
# before the generic "บัณฑิต" ending, which they both also end with.
_THAI_DOCTORAL_FULLNAME_SUFFIX = re.compile(r"ดุษฎีบัณฑิต\s*$")
_THAI_MASTER_FULLNAME_SUFFIX = re.compile(r"มหาบัณฑิต\s*$")
_THAI_BACHELOR_FULLNAME_SUFFIX = re.compile(r"บัณฑิต\s*$")


def classify_degree_level(degree_text: str | None) -> str | None:
    """Returns one of HIGHEST_EDUCATION_LEVELS, or None when the text doesn't
    match a recognized pattern (never guessed - caller must treat None as
    "unsupported/missing", not silently drop the person). Accepts either a
    real stored abbreviation ("ปร.ด.", "Ph.D.") or a full Thai degree name
    ("ปรัชญาดุษฎีบัณฑิต") - both are structural suffix patterns, not specific
    hardcoded degree names."""
    text = (degree_text or "").strip()
    if not text:
        return None
    if _THAI_ABBREVIATION_MISSING_FINAL_DOT.match(text):
        text += "."

    if _ENGLISH_DOCTORAL.search(text):
        return "ปริญญาเอก"
    if _ENGLISH_MASTER.search(text):
        return "ปริญญาโท"
    if _ENGLISH_BACHELOR.search(text):
        return "ปริญญาตรี"

    if _THAI_DOCTORAL_SUFFIX.search(text):
        return "ปริญญาเอก"
    if _THAI_MASTER_SUFFIX.search(text):
        return "ปริญญาโท"
    if _THAI_BACHELOR_SUFFIX.search(text):
        return "ปริญญาตรี"

    if _THAI_DOCTORAL_FULLNAME_SUFFIX.search(text):
        return "ปริญญาเอก"
    if _THAI_MASTER_FULLNAME_SUFFIX.search(text):
        return "ปริญญาโท"
    if _THAI_BACHELOR_FULLNAME_SUFFIX.search(text):
        return "ปริญญาตรี"

    return None


def highest_level_among(degree_abbreviations: list[str]) -> str | None:
    """Deterministic MAX over a person's full degree list (change.md sec.9 -
    "highest_education_level") - never an LLM guess, never just "the first
    education record found"."""
    levels = [classify_degree_level(d) for d in degree_abbreviations]
    levels = [lvl for lvl in levels if lvl is not None]
    if not levels:
        return None
    return min(levels, key=lambda lvl: _LEVEL_RANK[lvl])
