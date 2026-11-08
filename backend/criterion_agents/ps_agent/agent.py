"""PS Agent - Programme Specification (change.md sec.5).

Handles ONLY the PS criterion. Owns its own Prompt (prompt/system_prompt.txt)
and Schema (schema/output_schema.json).

Data Requirement: PS's real target slots (table_ps_1_1 - instructor list:
ตำแหน่งทางวิชาการ/ชื่อ-นามสกุล/วุฒิการศึกษาสูงสุด/ชื่อปริญญา; table_ps_1_2 -
อาจารย์+ผลงานวิชาการ history) need exactly what the Final Schema's
`appointments`/`persons`/`educations`/`academic_works` collections hold
(Dataschema.md) - so PS, unlike the other five agents, builds a real
per-data-type Data Request instead of the generic keyword-joined default
(see _shared.default_build_data_request). Requests all three appointment
roles explicitly, plus every person's education and academic work history
via retrieval/mongodb.py's deterministic Data-Request-to-collection mapping.

Table 1.1/1.2 VALUES (person identity, role merging, education level,
degree/field, year normalization, academic-work counts, checkbox, ordering)
are computed by deterministic Python (this module,
criterion_agents/ps_agent/person_aggregation.py,
criterion_agents/ps_agent/degree_mapping.py,
criterion_agents/ps_agent/work_aggregation.py,
criterion_agents/ps_agent/field_resolution.py,
criterion_agents/ps_agent/education_evidence.py), never by the LLM
(change.md sec.26/38 - "DO NOT LET LLM DO DETERMINISTIC DATA AGGREGATION").
The LLM is only asked to produce PS's narrative slots (e.g. intro_ps,
eval_p_ps) - see run() below.

`purpose` in build_data_request is a fixed, human-readable label, not the
Slot Marking Agent's own slot_id - that id is an LLM's own choice,
regenerated (and worded differently) on every run, so it isn't a stable key
to hang a data requirement on.
"""

from __future__ import annotations

from pathlib import Path

from common.schemas import (
    AgentResponse,
    DataRequest,
    DataRequestItem,
    EvidenceChunkContext,
    GapAnalysis,
    RowCitation,
    TableRow,
    TableSection,
    TargetSlot,
)
from criterion_agents import _shared
from criterion_agents._shared import AgentOutputError  # re-exported for master.py
from criterion_agents.ps_agent.academic_position import full_academic_position, position_and_name
from criterion_agents.ps_agent.degree_mapping import classify_degree_level
from criterion_agents.ps_agent.education_display import education_cell_text, education_items
from criterion_agents.ps_agent.education_evidence import evidence_supports_education_level
from criterion_agents.ps_agent.field_resolution import resolve_field
from criterion_agents.ps_agent.person_aggregation import (
    ROLE_RESPONSIBLE,
    ROLE_STAFF,
    AggregatedPerson,
    checkbox_state,
    table_1_1_members,
)
from criterion_agents.ps_agent.work_aggregation import aggregate_work_counts, categorize_work_type
from criterion_agents.ps_agent.year_normalization import normalize_publication_year

CRITERION_CODE = "PS"

_EXTRA_RULES = (Path(__file__).parent / "prompt" / "system_prompt.txt").read_text(encoding="utf-8")

FIVE_YEAR_RANGE = [2565, 2566, 2567, 2568, 2569]

# change.md sec.13: checkbox option labels, matching the real
# `appointments.roleName` values confirmed against aunqa_ps
# (programmeResponsible -> "อาจารย์ผู้รับผิดชอบหลักสูตร", programmeStaff ->
# "อาจารย์ประจำหลักสูตร") - not a guess, the system's own real role-label
# convention. specialInstructor's label is not confirmed against real data
# (zero real specialInstructor appointments exist in aunqa_ps at the time
# of writing) - best-effort per the same naming convention, flagged here so
# it's not silently assumed correct.
ROLE_CODE_TO_LABEL = {
    "programmeResponsible": "อาจารย์ผู้รับผิดชอบหลักสูตร",
    "programmeStaff": "อาจารย์ประจำหลักสูตร",
    "specialInstructor": "อาจารย์พิเศษ",  # best-effort, unconfirmed against real data
}


def build_data_request(meta: dict, target_slots: list[TargetSlot]) -> DataRequest:
    return DataRequest(
        criterion=CRITERION_CODE,
        requests=[
            DataRequestItem(data_type="appointment", role="programmeResponsible", purpose="PS instructor list"),
            DataRequestItem(data_type="appointment", role="programmeStaff", purpose="PS instructor list"),
            DataRequestItem(data_type="appointment", role="specialInstructor", purpose="PS instructor list"),
            DataRequestItem(data_type="education", purpose="PS instructor qualifications"),
            DataRequestItem(data_type="academic_work", purpose="PS academic work history"),
        ],
    )


def _mongo_person_source(person: AggregatedPerson) -> tuple[str, dict]:
    return person.academic_position, {"collection": "persons", "document_id": person.person_id}


def _resolve_highest_education_level(
    person: AggregatedPerson, chroma_hits: list[dict]
) -> tuple[str | None, RowCitation | None]:
    """change.md sec.4/9/28: Chroma first (with a real evidence-sufficiency
    check - see education_evidence.py), MongoDB fallback (deterministic MAX
    over the person's own real education records - never just "the first
    education record found")."""

    def _mongo_value() -> tuple[str, dict] | None:
        levels = [classify_degree_level(edu.get("degree")) for edu in person.educations]
        levels = [lvl for lvl in levels if lvl is not None]
        if not levels:
            return None
        rank = {"ปริญญาเอก": 0, "ปริญญาโท": 1, "ปริญญาตรี": 2}
        best = min(levels, key=lambda lvl: rank[lvl])
        # cite whichever real education record produced the winning level
        for edu in person.educations:
            if classify_degree_level(edu.get("degree")) == best:
                return best, {"source_filename": edu["source_filename"], "chunk_index": 0}
        return None

    resolution = resolve_field(
        field_name="highest_education_level",
        chroma_evidence=chroma_hits,
        evidence_supports_field=lambda hits, _field: evidence_supports_education_level(hits, person.last_name),
        mongo_value_fn=_mongo_value,
    )
    if resolution.value is None:
        return None, None
    ref = resolution.source_reference
    citation = None
    if ref.get("source_filename") is not None:
        citation = RowCitation(source_filename=ref["source_filename"], chunk_index=ref.get("chunk_index", 0))
    return str(resolution.value), citation


def _degree_name_field(person: AggregatedPerson) -> tuple[str, RowCitation | None]:
    """"ชื่อปริญญา (สาขาวิชา)" - real stored degree abbreviation + field for the
    person's highest-level education record (change.md sec.10). Kept in its
    real, stored abbreviated form rather than expanded to a full Thai name:
    expanding "ปร.ด." -> "ปรัชญาดุษฎีบัณฑิต" would need either an unbounded
    hardcoded abbreviation->full-name table (change.md sec.37 forbids
    hardcoding วุฒิ) or scraping a full name out of fragmented OCR text next
    to the abbreviation (real, but unreliable to do safely per-person) -
    both risk showing a name the source doesn't literally, safely support.
    """
    if not person.educations:
        return "", None
    ranked = sorted(
        person.educations,
        key=lambda edu: {"ปริญญาเอก": 0, "ปริญญาโท": 1, "ปริญญาตรี": 2}.get(classify_degree_level(edu.get("degree")), 9),
    )
    top = ranked[0]
    text = f"{top.get('degree', '')} {top.get('field', '')}".strip()
    citation = RowCitation(source_filename=top["source_filename"], chunk_index=0)
    return text, citation


def _education_all_levels_text(person: AggregatedPerson) -> str:
    """"วุฒิการศึกษา (ทุกระดับ)" (Table 1.2): the person's own real education records, one numbered line per
    retained item - "<degree> <field>" exactly as stored, NO year - see education_display.py for the
    order, the noise filter and the (within-one-person only) duplicate rule."""
    return education_cell_text(education_items(person.educations))


def _education_source_citations(person: AggregatedPerson) -> list[RowCitation]:
    """Every source record behind the displayed education lines (a merged duplicate keeps ALL of its
    records), so the Reference cell can point at each original MongoDB education record."""
    return [
        RowCitation(source_filename=record["source_filename"], chunk_index=0)
        for item in education_items(person.educations)
        for record in item.records
    ]


def _build_table_1_1(slot: TargetSlot, people: list[AggregatedPerson], education_chroma_hits: dict[str, list[dict]]) -> TableSection:
    """Table 1.1 has two sections; each lists the people holding that ACTIVE appointment role (see
    person_aggregation.table_1_1_members): "อาจารย์ผู้รับผิดชอบหลักสูตร" = programmeResponsible,
    "อาจารย์ประจำหลักสูตร" = programmeStaff with the people who are also programmeResponsible first. A person with
    both roles therefore appears in both sections. Numbering restarts at 1 in each section."""
    rows: list[TableRow] = []
    for role in (ROLE_RESPONSIBLE, ROLE_STAFF):
        group_label = ROLE_CODE_TO_LABEL[role]
        for number, person in enumerate(table_1_1_members(people, role), start=1):
            level, level_citation = _resolve_highest_education_level(person, education_chroma_hits.get(person.person_id, []))
            degree_field_text, degree_citation = _degree_name_field(person)
            person_citation = RowCitation(source_filename=person.source_filename, chunk_index=0)

            citations = [person_citation]
            if level_citation is not None:
                citations.append(level_citation)
            if degree_citation is not None:
                citations.append(degree_citation)

            rows.append(
                TableRow(
                    # col 0: "N. <full academic title>" (number within its section + explicit abbreviation->full-title
                    # map; unknown source values are shown as-is). Name/education/degree columns are unchanged.
                    values=[
                        f"{number}. {full_academic_position(person.academic_position)}".rstrip(),
                        person.display_name,
                        level or "",
                        degree_field_text,
                    ],
                    citations=citations,
                    group=group_label,
                    # per-cell provenance: position/name <- persons; level <- whichever tier resolve_field accepted
                    # (Chroma evidence or Mongo educations); degree name+field <- the highest-level educations record
                    column_citations={
                        "0": [person_citation],
                        "1": [person_citation],
                        "2": [level_citation] if level_citation is not None else [],
                        "3": [degree_citation] if degree_citation is not None else [],
                    },
                )
            )
    return TableSection(type="table", slot_id=slot.slot_id, headers=slot.headers or [], rows=rows)


def _build_table_1_2(slot: TargetSlot, people: list[AggregatedPerson]) -> TableSection:
    rows: list[TableRow] = []
    for record_number, person in enumerate(people, start=1):  # record order == the order Injection fills the blocks
        identity_text = f"{record_number}. " + position_and_name(
            person.academic_position, person.title, person.first_name, person.last_name
        )
        education_text = _education_all_levels_text(person)
        counts = aggregate_work_counts(person.academic_works, FIVE_YEAR_RANGE)
        checkbox = checkbox_state(person)
        checked_options = [
            ROLE_CODE_TO_LABEL[role_code] for role_code, checked in checkbox.items() if checked and role_code in ROLE_CODE_TO_LABEL
        ]
        person_citation = RowCitation(source_filename=person.source_filename, chunk_index=0)
        work_citations_by_year: dict[int, list[RowCitation]] = {year: [] for year in FIVE_YEAR_RANGE}
        # same per-year works split by the SAME category rule aggregate_work_counts uses,
        # so the "งานวิชาการ"/"งานสร้างสรรค์" cells cite exactly the works they count
        category_citations_by_year: dict[int, dict[str, list[RowCitation]]] = {
            year: {"academic": [], "creative": []} for year in FIVE_YEAR_RANGE
        }
        for work in person.academic_works:
            raw_year = work.get("publicationYear")
            if raw_year is None:
                continue
            year = normalize_publication_year(raw_year)
            if year in work_citations_by_year:
                work_citation = RowCitation(source_filename=work["source_filename"], chunk_index=0)
                work_citations_by_year[year].append(work_citation)
                category = categorize_work_type(work.get("workType"))
                if category is not None:
                    category_citations_by_year[year][category].append(work_citation)
        recognized_education_citations = _education_source_citations(person)

        # most-recent-year-first, matching the real evidence documents' own
        # stated convention (change.md sec.19 gives the set of years; order
        # isn't specified there, but the source CVs read "เรียงลำดับจากปีล่าสุด").
        for year in sorted(FIVE_YEAR_RANGE, reverse=True):
            year_counts = counts[year]
            citations = [person_citation] + work_citations_by_year[year]
            rows.append(
                TableRow(
                    values=[
                        identity_text,
                        education_text,
                        str(year),
                        str(year_counts["academic"]),
                        str(year_counts["creative"]),
                    ],
                    citations=citations,
                    group=None,
                    record_key=person.person_id,
                    checked_options=checked_options,
                    column_citations={
                        "0": [person_citation],
                        "1": recognized_education_citations,
                        "2": [],  # the fixed 5-year window is a constant, not sourced data
                        "3": category_citations_by_year[year]["academic"],
                        "4": category_citations_by_year[year]["creative"],
                    },
                )
            )
    return TableSection(type="table", slot_id=slot.slot_id, headers=slot.headers or [], rows=rows)


def _build_deterministic_tables(table_slots: list[TargetSlot], structured_context: dict) -> list[TableSection]:
    people: list[AggregatedPerson] = structured_context["people"]
    education_chroma_hits: dict[str, list[dict]] = structured_context.get("education_chroma_hits", {})

    sections: list[TableSection] = []
    for slot in table_slots:
        if slot.rows_per_record and slot.rows_per_record > 1:
            sections.append(_build_table_1_2(slot, people))
        else:
            sections.append(_build_table_1_1(slot, people, education_chroma_hits))
    return sections


def run(
    criterion_name: str,
    guideline: list[str],
    keywords: list[str],
    required_evidence: list[str],
    example_section: str,
    evidence_chunks: list[EvidenceChunkContext],
    target_slots: list[TargetSlot],
    current_academic_year: int | None = None,
    feedback: str | None = None,
    structured_context: dict | None = None,
) -> AgentResponse:
    if structured_context is None:
        # Backward-compatible fallback for callers that don't provide
        # structured Mongo data (e.g. older/offline tests) - the real
        # pipeline (master_agent/master.py) always provides it now.
        return _shared.run_agent(
            CRITERION_CODE,
            criterion_name,
            guideline,
            keywords,
            required_evidence,
            example_section,
            evidence_chunks,
            target_slots,
            current_academic_year,
            feedback,
            extra_rules=_EXTRA_RULES,
        )

    table_slots = [s for s in target_slots if s.type == "table"]
    narrative_slots = [s for s in target_slots if s.type == "narrative"]

    table_sections = _build_deterministic_tables(table_slots, structured_context)

    if narrative_slots:
        narrative_response = _shared.run_agent(
            CRITERION_CODE,
            criterion_name,
            guideline,
            keywords,
            required_evidence,
            example_section,
            evidence_chunks,
            narrative_slots,
            current_academic_year,
            feedback,
            extra_rules=_EXTRA_RULES,
        )
    else:
        narrative_response = AgentResponse(gap_analysis=GapAnalysis(status="complete", missing_fields=[]), sections=[], citations=[])

    return AgentResponse(
        gap_analysis=narrative_response.gap_analysis,
        sections=list(narrative_response.sections) + table_sections,
        citations=narrative_response.citations,
    )
