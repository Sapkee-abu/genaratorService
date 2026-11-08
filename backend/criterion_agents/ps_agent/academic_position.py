"""Academic-position / name presentation for PS Table 1.1 and 1.2 (deterministic, no LLM).

PRESENTATION ONLY: these helpers build display strings from `persons.academicPosition`,
`persons.title` and the person's name. Nothing here reads or writes anywhere else; the
numbering ("1.", "2.", ...) is display order and is never stored back to MongoDB.
"""

from __future__ import annotations

import re

# Explicit abbreviation -> full title map. Only these well-known Thai academic ranks;
# anything else is shown exactly as it is in the source (never guessed / invented).
FULL_ACADEMIC_TITLE: dict[str, str] = {
    "ศ.": "ศาสตราจารย์",
    "รศ.": "รองศาสตราจารย์",
    "ผศ.": "ผู้ช่วยศาสตราจารย์",
    "อ.": "อาจารย์",
}

# Leading titles that may already be embedded in a source name (and must not be duplicated).
_KNOWN_LEADING_TITLES = ("ศ.", "รศ.", "ผศ.", "อ.", "ดร.", "Dr.", "Asst.Prof.", "Assoc.Prof.", "Prof.")
# The trailing dot is REQUIRED: without it "อ" / "ศ" would eat the first letter of real names such as
# "อรุณ" or "ศิริรัตน์".
_LEADING_TITLE = re.compile(r"^\s*(?:" + "|".join(re.escape(t) for t in _KNOWN_LEADING_TITLES) + r")\s*", re.IGNORECASE)


def _position_key(position: str | None) -> str:
    """Source abbreviation normalized for lookup only ("รศ", "รศ ." -> "รศ.")."""
    key = re.sub(r"\s+", "", position or "")
    return key if key.endswith(".") or not key else key + "."


def full_academic_position(position: str | None) -> str:
    """"รศ." -> "รองศาสตราจารย์". Unknown/blank source values are returned as they are."""
    text = (position or "").strip()
    return FULL_ACADEMIC_TITLE.get(_position_key(text), text)


def strip_leading_titles(name: str) -> str:
    """Removes titles/ranks already written at the start of a name ("ผศ. ดร. X Y" -> "X Y")."""
    previous = None
    while previous != name:
        previous = name
        name = _LEADING_TITLE.sub("", name, count=1)
    return name.strip()


def position_and_name(position: str | None, title: str | None, first_name: str, last_name: str) -> str:
    """Table 1.2 identity text (without the number): "<position abbr><title><first> <last>",
    e.g. "รศ.ดร.พีรวิชญ์ เควด". The position is the ABBREVIATION from the source
    ("รศ."), the title is the source `title` only when it is "ดร."; ranks/titles already
    present at the start of the source name are removed first so nothing is duplicated
    (never "รศ.ดร.ดร.พีรวิชญ์")."""
    bare_name = strip_leading_titles(f"{first_name} {last_name}".strip())
    position_text = (position or "").strip()
    doctor = "ดร." if (title or "").strip() == "ดร." else ""
    return f"{position_text}{doctor}{bare_name}".strip()
