"""Deterministic academic-work aggregation (change.md sec.17/18/19/21/22).

Real `academic_works.workType` values (confirmed against aunqa_ps) are
"Journal" and "Conference" only - both are peer-reviewed/scholarly output
("ผลงานวิชาการ"/academic), distinct from "งานสร้างสรรค์" (creative work: art,
design, patents - a different output type entirely). "Creative Work" is
also recognized (matching the real Table 1.2 column's own label,
"งานสร้างสรรค์") even though no current real record uses it yet - this is a
forward-compatible category the template itself already anticipates, not a
guess. Any workType outside this known set is marked unsupported rather
than guessed into a category.
"""

from __future__ import annotations

from criterion_agents.ps_agent.year_normalization import normalize_publication_year

WORK_TYPE_CATEGORY: dict[str, str] = {
    "Journal": "academic",
    "Conference": "academic",
    "Creative Work": "creative",
}


def categorize_work_type(work_type: str | None) -> str | None:
    if work_type is None:
        return None
    return WORK_TYPE_CATEGORY.get(work_type)


def aggregate_work_counts(works: list[dict], year_range: list[int]) -> dict[int, dict[str, int]]:
    """`works` - dicts with at least "workType"/"publicationYear" (change.md
    sec.18 - personId/workType/publicationYear are the aggregation keys;
    educations.graduationYear must never be used here). Returns
    {year: {"academic": int, "creative": int}} for exactly `year_range` -
    works outside that range are not counted (change.md sec.19's
    deterministic 5-year window), works with an unrecognized workType are
    skipped, never guess-counted (change.md sec.21).
    """
    counts: dict[int, dict[str, int]] = {year: {"academic": 0, "creative": 0} for year in year_range}
    for work in works:
        category = categorize_work_type(work.get("workType"))
        if category is None:
            continue
        raw_year = work.get("publicationYear")
        if raw_year is None:
            continue
        year = normalize_publication_year(raw_year)
        if year not in counts:
            continue
        counts[year][category] += 1
    return counts
