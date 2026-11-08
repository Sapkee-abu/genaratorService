"""Canonical person aggregation (change.md sec.11/12/14/32/33) - the ONE
deterministic Python function both Table 1.1 and Table 1.2 use to decide
which people exist, what roles each has, and in what order they appear.
Pure/DB-independent: takes plain dicts (as
retrieval.mongodb.fetch_curriculum_people_raw returns), so it's unit
testable without a real MongoDB connection.

person aggregation, role merging, sorting are explicitly forbidden from
being an LLM's job (change.md sec.26/38) - this module is the deterministic
replacement.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AggregatedPerson:
    person_id: str
    first_name: str
    last_name: str
    academic_position: str
    title: str
    source_filename: str
    roles: list[str] = field(default_factory=list)
    educations: list[dict] = field(default_factory=list)
    academic_works: list[dict] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """change.md sec.7: firstName + lastName, with "ดร." prefixed only
        when present - never fullName (which already bakes in
        academicPosition, causing the observed "ผศ. ผศ. ดร. X Y"
        duplication when something else adds academicPosition again)."""
        prefix = "ดร." if self.title.strip() == "ดร." else ""
        return f"{prefix}{self.first_name} {self.last_name}".strip()


ROLE_RESPONSIBLE = "programmeResponsible"
ROLE_STAFF = "programmeStaff"


def is_current_appointment(appointment: dict, curriculum_id: str | None = None) -> bool:
    """An appointment counts toward a person's CURRENT role only if its `status` is "active" and (when the
    current curriculum is known) it belongs to that curriculum. Inactive/ended appointments - and appointments
    of another curriculum - never decide a role, a checkbox or a Table 1.1 group."""
    if appointment.get("status") != "active":
        return False
    return curriculum_id is None or str(appointment.get("curriculumId")) == str(curriculum_id)


def aggregate_curriculum_people(
    appointments: list[dict],
    persons: list[dict],
    educations: list[dict],
    academic_works: list[dict],
    curriculum_id: str | None = None,
) -> list[AggregatedPerson]:
    """change.md sec.32's aggregate_curriculum_people(): group appointments
    by personId (merging roles - sec.11), attach each person's own record,
    education records, and work records, then sort deterministically
    (sec.33: multi-role first, personId ascending as the fully reproducible
    tiebreaker - never relies on incidental DB read order).

    A personId with appointments but no matching `persons` record is
    skipped, not fabricated (change.md sec.34 - never invent a person).
    """
    appointments = [a for a in appointments if is_current_appointment(a, curriculum_id)]
    persons_by_id = {p["_id"]: p for p in persons}
    educations_by_person: dict[str, list[dict]] = {}
    for edu in educations:
        educations_by_person.setdefault(edu.get("personId"), []).append(edu)
    works_by_person: dict[str, list[dict]] = {}
    for work in academic_works:
        works_by_person.setdefault(work.get("personId"), []).append(work)

    order: list[str] = []
    roles_by_person: dict[str, list[str]] = {}
    for appt in appointments:
        pid = appt.get("personId")
        if pid is None:
            continue
        if pid not in roles_by_person:
            roles_by_person[pid] = []
            order.append(pid)
        role = appt.get("role")
        if role and role not in roles_by_person[pid]:
            roles_by_person[pid].append(role)

    people: list[AggregatedPerson] = []
    for pid in order:
        person = persons_by_id.get(pid)
        if person is None:
            continue
        people.append(
            AggregatedPerson(
                person_id=pid,
                first_name=person.get("firstName", ""),
                last_name=person.get("lastName", ""),
                academic_position=person.get("academicPosition", ""),
                title=person.get("title", ""),
                source_filename=person["source_filename"],
                roles=roles_by_person[pid],
                educations=educations_by_person.get(pid, []),
                academic_works=works_by_person.get(pid, []),
            )
        )

    people.sort(key=lambda p: (-len(p.roles), p.person_id))
    return people


def checkbox_state(person: AggregatedPerson) -> dict[str, bool]:
    """change.md sec.13: checkbox reflects the full merged role set, never
    a single appointment record in isolation."""
    return {
        "programmeResponsible": "programmeResponsible" in person.roles,
        "programmeStaff": "programmeStaff" in person.roles,
    }


def table_1_1_members(people: list[AggregatedPerson], role: str) -> list[AggregatedPerson]:
    """The people listed in ONE Table 1.1 section, derived only from their ACTIVE appointment roles (`person.roles`,
    built from `appointments.role`) - never from the person record, the name, the academic position, the position in
    the fetched list or any hardcoded head-count / list of names.

      role = programmeResponsible -> everyone holding that role
      role = programmeStaff       -> everyone holding that role, and the ones who ALSO hold programmeResponsible
                                     come first (a person with both roles appears in both sections)

    Inside each of those two blocks the order is the system's existing canonical order (personId ascending): the
    appointments' own orderNumber / orderDate / effectiveDate are free text shared by every row of the same
    appointment order, so they cannot rank people (see the README)."""
    members = [p for p in people if role in p.roles]
    members.sort(key=lambda p: (0 if ROLE_RESPONSIBLE in p.roles else 1, p.person_id))
    return members


def numbering(people: list[AggregatedPerson]) -> dict[str, int]:
    """change.md sec.27: deterministic 1-based numbering in canonical order,
    keyed by person_id - only used when a template slot actually has a
    numbering column/placeholder (the real Table 1.1/1.2 currently don't -
    layout.numbered is False - so this is unused today but available for a
    template that does)."""
    return {person.person_id: index + 1 for index, person in enumerate(people)}
