"""Canonical data models for the Columbus scheduling engine.

Models reflect powerschool_requirements_v2.md §4–6:
- 5 days A–E, 5 blocks/day, 8 rotating schemes
- Each student takes 8 courses, each course meets 3x/week
- Advisory fixed at Day E, Block 3
- Max class size 25 (26 for AP Research)
- No teacher >4 consecutive classes
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Day = Literal["A", "B", "C", "D", "E"]
DAYS: tuple[Day, ...] = ("A", "B", "C", "D", "E")
BLOCKS: tuple[int, ...] = (1, 2, 3, 4, 5)
ADVISORY_DAY: Day = "E"
ADVISORY_BLOCK: int = 3


class RoomType(str, Enum):
    STANDARD = "standard"
    SCIENCE_LAB = "science_lab"
    COMPUTER_LAB = "computer_lab"
    ART = "art"
    MUSIC = "music"
    GYM = "gym"
    SPECIAL_ED = "special_ed"


class Term(str, Enum):
    YEAR = "year"
    SEMESTER = "semester"
    QUARTER = "quarter"


class Course(BaseModel):
    course_id: str
    name: str
    department: str
    grade_eligibility: list[int] = Field(default_factory=list)
    is_required: bool = False
    credits: float = 1.0
    meetings_per_week: int = 3
    max_size: int = 25
    min_size: int = 5
    required_room_type: RoomType = RoomType.STANDARD
    qualified_teacher_ids: list[str] = Field(default_factory=list)
    is_lab: bool = False
    is_advisory: bool = False
    term: Term = Term.YEAR
    # Course prerequisites (v2 §4.3): list of course IDs that must be completed
    # (or concurrently scheduled — depending on policy) before this one.
    # Validation only warns since transcript history isn't part of the canonical Dataset.
    prerequisite_course_ids: list[str] = Field(default_factory=list)
    # Course relationships from `course_relationships.csv` (client spec 2026-04-28):
    #
    # `simul_group`: identifier shared by courses that must be dictated simultaneously
    #   in the same physical section (multi-level class). Example: G0902 + G1204 +
    #   G1205 + G1206 (Spanish 9/10/11/12 Foreign Language) all share simul_group="SPANISH_FL".
    #   When a teacher has assignments to multiple courses with the same simul_group,
    #   the ingester merges them into ONE Section with `linked_course_ids` populated.
    #
    # `term_pair`: course_id of the term-paired counterpart. Example: I1213 (Micro)
    #   has term_pair="I1212" (Macro). They share slots but in different semesters.
    #   The ingester emits sections with `Section.term_id` set to "3601" (S1) or
    #   "3602" (S2). Year-long courses keep term_id=None and use SchoolConfig.term_id (3600).
    simul_group: str | None = None
    term_pair: str | None = None


class Teacher(BaseModel):
    teacher_id: str
    name: str
    department: str
    qualified_course_ids: list[str] = Field(default_factory=list)
    max_load: int = 5  # sections per cycle
    min_prep_periods: int = 1
    home_room_id: str | None = None
    # Per-teacher override of HardConstraints.max_consecutive_classes. None = use
    # the school-wide default. Use this for the rare case of a teacher whose
    # academic load is structurally infeasible at the global cap (e.g. 7+
    # sections in a 5×8 rotation requires max_consec ≥ 5 by pigeonhole).
    max_consecutive_classes: int | None = None
    # Preferences (v2 §6.2 — soft objectives in master solver)
    preferred_course_ids: list[str] = Field(default_factory=list)
    avoid_course_ids: list[str] = Field(default_factory=list)
    # Block preferences: 1 = first block of day, 5 = last. Empty = no preference.
    preferred_blocks: list[int] = Field(default_factory=list)
    avoid_blocks: list[int] = Field(default_factory=list)


class Room(BaseModel):
    room_id: str
    name: str
    capacity: int = 25
    room_type: RoomType = RoomType.STANDARD
    department: str | None = None


class Section(BaseModel):
    """A specific offering of a course (e.g., ALG2.1, ALG2.2)."""
    section_id: str
    course_id: str
    teacher_id: str
    room_id: str | None = None  # may be assigned by master solver
    max_size: int = 25
    grade_level: int = 12
    # Locks (v2 §13 human approval): if set, master solver must respect.
    locked_scheme: int | Literal["ADVISORY"] | None = None
    locked_room_id: str | None = None
    # v4.2 — course relationships:
    #
    # `linked_course_ids`: additional courses also covered by this physical
    #   section (Simultaneous relationship). Example: a Spanish multi-level
    #   section with course_id="G0902" might have linked_course_ids=["G1204",
    #   "G1205", "G1206"]. A student requesting any of those courses can be
    #   assigned to this section (subject to grade eligibility).
    # `term_id`: explicit term override for Term-paired sections.
    #   None  = year-long, use SchoolConfig.term_id (3600).
    #   "3601" = S1, "3602" = S2 (Columbus 2026-2027 mapping).
    #   Same-slot sections in different term_ids do NOT conflict.
    linked_course_ids: list[str] = Field(default_factory=list)
    term_id: str | None = None

    @model_validator(mode="after")
    def _normalize(self) -> "Section":
        return self


class CourseRequest(BaseModel):
    student_id: str
    course_id: str
    is_required: bool = True
    rank: int = 1  # 1=first choice, 2=alternate


class Student(BaseModel):
    student_id: str
    name: str
    grade: int
    counselor_id: str | None = None
    requested_courses: list[CourseRequest] = Field(default_factory=list)
    restricted_teacher_ids: list[str] = Field(default_factory=list)


class BehaviorMatrix(BaseModel):
    """Separation and grouping codes from §5.2.

    separations: pairs of student IDs that MUST NOT share a section.
    groupings: pairs of student IDs that SHOULD share a section.
    """
    separations: list[tuple[str, str]] = Field(default_factory=list)
    groupings: list[tuple[str, str]] = Field(default_factory=list)


class RotationCell(BaseModel):
    """Maps (Day, Block) → scheme number 1..8 or 'ADVISORY'."""
    day: Day
    block: int
    scheme: int | Literal["ADVISORY"]


class BellSchedule(BaseModel):
    """The 5×5 rotation grid from v2 §4.1."""
    rotation: list[RotationCell]

    def scheme_at(self, day: Day, block: int) -> int | Literal["ADVISORY"]:
        for cell in self.rotation:
            if cell.day == day and cell.block == block:
                return cell.scheme
        raise KeyError(f"No rotation cell for ({day}, {block})")

    def slots_for_scheme(self, scheme: int) -> list[tuple[Day, int]]:
        return [(c.day, c.block) for c in self.rotation if c.scheme == scheme]


def default_rotation() -> BellSchedule:
    """The example rotation from v2 §4.1 — Day E Block 3 = Advisory."""
    grid: list[list[int | str]] = [
        # Block 1
        [1, 6, 3, 8, 5],
        # Block 2
        [2, 7, 4, 1, 6],
        # Block 3
        [3, 8, 5, 2, "ADVISORY"],
        # Block 4
        [4, 1, 6, 3, 7],
        # Block 5
        [5, 2, 7, 4, 8],
    ]
    cells: list[RotationCell] = []
    for b_idx, row in enumerate(grid):
        block = b_idx + 1
        for d_idx, scheme in enumerate(row):
            day = DAYS[d_idx]
            cells.append(RotationCell(day=day, block=block, scheme=scheme))
    return BellSchedule(rotation=cells)


class HardConstraints(BaseModel):
    """v2 §6.1."""
    max_class_size: int = 25
    ap_research_max_size: int = 26
    max_consecutive_classes: int = 4
    advisory_day: Day = ADVISORY_DAY
    advisory_block: int = ADVISORY_BLOCK
    # When True, separations are HARD: paired students NEVER share a section.
    # When False, soft penalty via `separation_violation` weight.
    # v4.17: re-enabled HARD as part of A+B+C combo — school accepted ≥90%
    # required-fulfillment target, so we now spend the budget on guaranteeing
    # 100% of counselor "Separado de" pairs are respected. Estimated cost
    # ~94 cupos; estimated landing ~91-92% required fulfillment.
    enforce_separations: bool = True
    enforce_restricted_teachers: bool = True
    # Balance: max enrollment minus min enrollment within sections of the same course.
    # School decision 2026-04-29 (audio noche): "ideal 4, aceptamos 5".
    # v4.16: subimos a la meta ideal del Colegio (≤4) porque al aceptar 90%
    # de cobertura tenemos presupuesto para endurecer balance. Combinado con
    # coplanning HARD (recomendación A+C). Estimado: ~66 cupos extra,
    # required fulfillment ~93% (sigue sobre 90%).
    max_section_spread_per_course: int = 4
    # Coplanning: when True, every group in Dataset.coplanning_groups must
    # share at least one scheme where all members are simultaneously free.
    # v4.16 (2026-04-29): turned ON per recommendation A+C — el Colegio
    # acepta 90% cobertura a cambio de respetar balance ≤4 + coplanning
    # de los 18 grupos definidos en la pestaña 'co-planning'.
    enforce_coplanning_groups: bool = True
    min_sections_for_balance: int = 2


class SoftConstraintWeights(BaseModel):
    """v2 §6.2 — multi-objective weights for single-pass mode.

    Co-planning is implemented in master_solver but disabled by default
    (weight=0) because it can concentrate same-dept sections into fewer
    schemes, which hurts first-choice electives and per-course balance.
    Enable selectively per-school by setting `co_planning > 0` in config.
    """
    balance_class_sizes: int = 8
    first_choice_electives: int = 20
    co_planning: int = 0
    grouping_codes: int = 4
    teacher_load_balance: int = 5
    # Teacher preferences (v2 §6.2)
    teacher_preferred_courses: int = 3
    teacher_avoid_courses: int = 5
    teacher_preferred_blocks: int = 2
    teacher_avoid_blocks: int = 3
    # Singleton-conflict avoidance (v2 §5.2). Off by default — concentrating
    # singletons into different schemes is helpful but can compete with other
    # objectives. Enable per school if needed.
    singleton_separation: int = 0
    # Separation-pair penalty (active when HardConstraints.enforce_separations
    # is False). 1000 ranks a violated separation between groupings (~4) and
    # required-course coverage (~10000+ via grade weights), so the solver
    # respects most separations but breaks them when needed for coverage.
    separation_violation: int = 1000


class SchoolConfig(BaseModel):
    """Top-level config bound to a (school, grade, year) context — v2 §3."""
    school: str = "Columbus High School"
    school_id: int | str | None = None
    """PowerSchool School_Number. If None, exporter falls back to `school` string.
    Columbus values per 2026-04-26 client confirmation: MS=12000, HS=13000."""
    grade: int = 12
    year: str = "2026-2027"
    term_id: str | int | None = None
    """PowerSchool TermID. If None, exporter falls back to `year` string.
    Columbus value per 2026-04-26 client confirmation: 3600 (for 2026-2027)."""
    bell: BellSchedule
    hard: HardConstraints = Field(default_factory=HardConstraints)
    soft: SoftConstraintWeights = Field(default_factory=SoftConstraintWeights)


class Dataset(BaseModel):
    """A complete bundle the solver consumes."""
    config: SchoolConfig
    courses: list[Course]
    teachers: list[Teacher]
    rooms: list[Room]
    sections: list[Section]
    students: list[Student]
    behavior: BehaviorMatrix = Field(default_factory=BehaviorMatrix)
    coplanning_groups: list[list[str]] = Field(default_factory=list)

    def course_by_id(self, cid: str) -> Course:
        for c in self.courses:
            if c.course_id == cid:
                return c
        raise KeyError(cid)

    def teacher_by_id(self, tid: str) -> Teacher:
        for t in self.teachers:
            if t.teacher_id == tid:
                return t
        raise KeyError(tid)

    def room_by_id(self, rid: str) -> Room:
        for r in self.rooms:
            if r.room_id == rid:
                return r
        raise KeyError(rid)


# Solver outputs


class MasterAssignment(BaseModel):
    """Where and when a section meets."""
    section_id: str
    scheme: int | Literal["ADVISORY"]
    room_id: str
    # Concrete (day, block) slots derived from scheme via BellSchedule
    slots: list[tuple[Day, int]]


class StudentAssignment(BaseModel):
    student_id: str
    section_ids: list[str]


class ScheduleResult(BaseModel):
    master: list[MasterAssignment]
    students: list[StudentAssignment]
    unscheduled_students: list[str] = Field(default_factory=list)
    unscheduled_requests: list[tuple[str, str]] = Field(default_factory=list)
    objective_value: float = 0.0
    solve_seconds: float = 0.0
