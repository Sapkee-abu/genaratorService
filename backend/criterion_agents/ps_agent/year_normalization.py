"""Deterministic publication-year normalization (change.md sec.20).

Real `academic_works.publicationYear` values (confirmed against aunqa_ps)
are a genuine MIX of Gregorian (2022-2026) and Buddhist Era (2562, 2564-2569)
within the SAME collection - never assume every record uses one convention.
A threshold separates the two ranges cleanly for this real data: Buddhist
Era years for any date in the modern era are always >= 2400, Gregorian years
for the same era are always < 2400 - so this is a safe, deterministic
boundary, not a guess.
"""

from __future__ import annotations

BUDDHIST_ERA_OFFSET = 543
_ALREADY_BUDDHIST_ERA_THRESHOLD = 2400


def normalize_publication_year(year: int) -> int:
    year = int(year)
    if year >= _ALREADY_BUDDHIST_ERA_THRESHOLD:
        return year
    return year + BUDDHIST_ERA_OFFSET
