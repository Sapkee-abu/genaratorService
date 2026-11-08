"""Table 1.2 "วุฒิการศึกษา (ทุกระดับ)" - what is shown, and how duplicate SOURCE records are shown (deterministic, no LLM).

PRESENTATION ONLY: reads the person's own education records and produces display items; nothing is
written anywhere, no record is ever deleted or moved to another person.

Display of one item : "<degree> <field>"   (both exactly as stored - no expansion, no year, no institution)
Numbering           : "1. ...", "2. ..."  plain text (added by the caller); never a backslash
Year                : never displayed. It stays in the source record and in the Reference; it is used here only to
                      decide whether two records are the same education.
Order               : graduation year, most recent first, then record _id (deterministic). Records without a
                      recognizable degree (OCR noise such as "at" / "heuristic approach. ...") are not education
                      and are not shown - unchanged rule from degree_mapping.classify_degree_level.

Merge rule (within ONE person only - records of different persons are never compared). Two records are ONE
logical education when they have the same degree abbreviation, the same graduation year, compatible institutions
(the institution NAME before any "/" country suffix is equal, or one side is empty) AND either

  (1) the same field after Unicode NFKC normalization and removing whitespace/dots   (an exact source duplicate), or
  (2) one record's field is the OTHER's field written out as "<full degree name> (<field>)": the part before the
      parentheses is a Thai degree NAME whose level (ดุษฎีบัณฑิต / มหาบัณฑิต / บัณฑิต) equals the degree's level, and the
      parenthesized text is the other record's field (OCR-tolerant: whitespace and the sara-am/nikhahit glyph are
      ignored). That is the same education stored in two representations, e.g.
          ปร.ด. | วิทยาศาสตร์เชิงคำนวณ                          + ปร.ด. | ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)
          วท.บ. | วิทยาศาสตร์เชิงคำนวณ                          + วท.บ. | วิทยาศาสตรบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)

The shown text is the plain (non "full-name") record's, else the lowest _id; EVERY underlying record stays the
item's source, so Reference still points to all of them. Anything not proven by those fields - a faculty suffix,
a one-letter degree variant ("วท.บ." vs "วบ.บ."), a different year or institution - is NOT merged: both are shown.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from criterion_agents.ps_agent.degree_mapping import classify_degree_level

# only parentheses that contain nothing but a 4-digit (Buddhist or Gregorian) year, e.g. "(2562)"
_YEAR_PARENTHESES = re.compile(r"\(\s*(?:1[89]|2[0-6])\d{2}\s*\)")


def strip_year_parentheses(text: str) -> str:
    """Removes "(2562)"-style year parentheses. Meaningful parentheses such as
    "ปรัชญาดุษฎีบัณฑิต (วิทยาศาสตร์เชิงคำนวณ)" are kept."""
    return re.sub(r"\s{2,}", " ", _YEAR_PARENTHESES.sub("", text or "")).strip()


def _key(text: str | None) -> str:
    """Comparison key only (never displayed): NFKC, no whitespace, no dots, case-folded."""
    return re.sub(r"[\s.]+", "", unicodedata.normalize("NFKC", text or "")).casefold()


def _institution_name(text: str | None) -> str:
    return _key((text or "").split("/")[0])


def _year(record: dict) -> int:
    try:
        return int(record.get("graduationYear"))
    except (TypeError, ValueError):
        return 0


# "<full degree name> (<field>)" - the field column holding the written-out degree name plus the field in parentheses
_FULLNAME_AND_FIELD = re.compile(r"^\s*([^()]+?)\s*\(\s*(.+?)\s*\)\s*$")


def _ocr_key(text: str | None) -> str:
    """Like _key, additionally ignoring the sara-am / nikhahit glyph, which PDF/OCR extraction splits off or drops
    ("คำนวณ" / "คํานวณ" / "ค านวณ" are the same word). Comparison key only - never displayed."""
    return _key(unicodedata.normalize("NFKC", text or "").replace("\u0e4d", "").replace("\u0e33", ""))


def _fullname_and_field(record: dict) -> tuple[str, str] | None:
    """(full degree name, field) when this record's field is written as "<full degree name> (<field>)"."""
    match = _FULLNAME_AND_FIELD.match(str(record.get("field") or ""))
    if match is None or classify_degree_level(match.group(1)) is None:
        return None
    return match.group(1), match.group(2)


def _is_written_out_form_of(plain: dict, written_out: dict) -> bool:
    parsed = _fullname_and_field(written_out)
    return (
        parsed is not None
        and classify_degree_level(parsed[0]) == classify_degree_level(written_out.get("degree"))
        and _ocr_key(parsed[1]) == _ocr_key(plain.get("field"))
    )


def _same_logical_education(a: dict, b: dict) -> bool:
    ia, ib = _institution_name(a.get("institution")), _institution_name(b.get("institution"))
    if not (_key(a.get("degree")) == _key(b.get("degree")) and _year(a) == _year(b) and (ia == ib or not ia or not ib)):
        return False
    return _key(a.get("field")) == _key(b.get("field")) or _is_written_out_form_of(a, b) or _is_written_out_form_of(b, a)


@dataclass
class EducationItem:
    text: str  # "<degree> <field>", no year
    records: list[dict] = field(default_factory=list)  # every underlying source record (first = the one displayed)


def education_items(educations: list[dict]) -> list[EducationItem]:
    """The retained education items of ONE person, in display order."""
    recognized = [e for e in educations if classify_degree_level(e.get("degree")) is not None]
    ordered = sorted(recognized, key=lambda e: (-_year(e), str(e.get("_id", ""))))
    groups: list[list[dict]] = []
    for record in ordered:
        for group in groups:
            if any(_same_logical_education(member, record) for member in group):
                group.append(record)
                break
        else:
            groups.append([record])

    items: list[EducationItem] = []
    for group in groups:
        # shown text: the plain representation if there is one, else the earliest record
        shown = min(group, key=lambda r: (1 if _fullname_and_field(r) else 0, str(r.get("_id", ""))))
        degree = strip_year_parentheses(str(shown.get("degree", "")).strip())
        major = strip_year_parentheses(str(shown.get("field", "")).strip())
        records = [shown] + [r for r in group if r is not shown]  # the shown record first, the rest in display order
        items.append(EducationItem(text=f"{degree} {major}".strip(), records=records))
    return items


def education_cell_text(items: list[EducationItem]) -> str:
    """"1. ปร.ด. ...\\n2. ..." - plain numbering, one item per line."""
    return "\n".join(f"{number}. {item.text}" for number, item in enumerate(items, start=1))
