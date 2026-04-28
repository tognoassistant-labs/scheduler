"""Reproducible Grade-12 sample data generator.

Models a realistic Columbus HS Grade 12 cohort:
- 130 students
- ~25 teachers
- 18 courses (12 core/required + 6 electives + Advisory)
- 22 rooms (mix of standard, lab, art, music, gym)
- Behavior matrix with ~10 separations and 8 groupings
- Each student requests Advisory + 7 other courses (1 of which is an elective)
"""
from __future__ import annotations

import random
from typing import Sequence

from .models import (
    BehaviorMatrix,
    BellSchedule,
    Course,
    CourseRequest,
    Dataset,
    HardConstraints,
    Room,
    RoomType,
    SchoolConfig,
    Section,
    SoftConstraintWeights,
    Student,
    Teacher,
    default_rotation,
)


CORE_COURSES = [
    ("ENG12", "English 12", "english", "standard", False),
    ("CALC", "AP Calculus AB", "math", "standard", False),
    ("STATS", "AP Statistics", "math", "standard", False),
    ("BIO", "Biology", "science", "science_lab", True),
    ("CHEM", "Chemistry", "science", "science_lab", True),
    ("PHYS", "Physics", "science", "science_lab", True),
    ("HIST", "US History", "social_studies", "standard", False),
    ("GOV", "Government & Economics", "social_studies", "standard", False),
    ("SPAN", "Spanish IV", "world_lang", "standard", False),
    ("CS", "Computer Science", "tech", "computer_lab", False),
    ("PE", "Physical Education", "pe", "gym", False),
    ("ART", "Studio Art", "arts", "art", False),
]

ELECTIVES = [
    ("APRES", "AP Research", "interdisciplinary", "standard", False),  # max 26
    ("MUS", "Music Ensemble", "arts", "music", False),
    ("PSYCH", "Psychology", "social_studies", "standard", False),
    ("ECON", "Microeconomics", "social_studies", "standard", False),
    ("CRWR", "Creative Writing", "english", "standard", False),
    ("ROBO", "Robotics", "tech", "computer_lab", False),
]


def _make_teachers(rng: random.Random, scale: int = 1) -> list[Teacher]:
    departments = {
        "english": ["Allen", "Brooks", "Cole"],
        "math": ["Diaz", "Evans", "Foster"],
        "science": ["Garcia", "Hayes", "Iqbal", "Jones"],
        "social_studies": ["Kim", "Lopez", "Mehta"],
        "world_lang": ["Nguyen", "Ortiz"],
        "tech": ["Patel", "Quinn"],
        "pe": ["Reyes"],
        "arts": ["Singh", "Tan", "Umeh"],
        "interdisciplinary": ["Vargas"],
    }
    teachers: list[Teacher] = []
    tid = 100
    for dept, names in departments.items():
        for n in names:
            for k in range(scale):
                suffix = "" if k == 0 else f"_{k+1}"
                teachers.append(
                    Teacher(
                        teacher_id=f"T{tid}",
                        name=f"{n}{suffix}",
                        department=dept,
                        qualified_course_ids=[],
                        max_load=5,
                    )
                )
                tid += 1
    return teachers


def _assign_qualifications(courses: list[Course], teachers: list[Teacher], scale: int = 1) -> None:
    by_dept: dict[str, list[Teacher]] = {}
    for t in teachers:
        by_dept.setdefault(t.department, []).append(t)
    for c in courses:
        pool = by_dept.get(c.department, [])
        if not pool:
            continue
        n = min(len(pool), 3 * scale)
        chosen = pool[:n]
        c.qualified_teacher_ids = [t.teacher_id for t in chosen]
        for t in chosen:
            if c.course_id not in t.qualified_course_ids:
                t.qualified_course_ids.append(c.course_id)


def _make_courses() -> list[Course]:
    courses: list[Course] = []
    advisory = Course(
        course_id="ADV",
        name="Advisory",
        department="advisory",
        grade_eligibility=[12],
        is_required=True,
        meetings_per_week=1,
        max_size=25,
        is_advisory=True,
        qualified_teacher_ids=["__ANY__"],  # dummy; advisory uses any teacher
    )
    courses.append(advisory)
    for cid, name, dept, room_type, is_lab in CORE_COURSES:
        courses.append(
            Course(
                course_id=cid,
                name=name,
                department=dept,
                grade_eligibility=[12],
                is_required=cid in ("ENG12", "GOV"),
                meetings_per_week=3,
                max_size=25,
                required_room_type=RoomType(room_type),
                is_lab=is_lab,
                qualified_teacher_ids=[],
            )
        )
    for cid, name, dept, room_type, is_lab in ELECTIVES:
        courses.append(
            Course(
                course_id=cid,
                name=name,
                department=dept,
                grade_eligibility=[12],
                is_required=False,
                meetings_per_week=3,
                max_size=26 if cid == "APRES" else 25,
                required_room_type=RoomType(room_type),
                is_lab=is_lab,
                qualified_teacher_ids=[],
            )
        )
    return courses


def _make_rooms(scale: int = 1) -> list[Room]:
    rooms: list[Room] = []
    rid = 1
    for _ in range(14 * scale):
        rooms.append(Room(room_id=f"R{rid:03d}", name=f"Room {rid}", capacity=28, room_type=RoomType.STANDARD))
        rid += 1
    for _ in range(3 * scale):
        rooms.append(Room(room_id=f"R{rid:03d}", name=f"Lab {rid}", capacity=26, room_type=RoomType.SCIENCE_LAB))
        rid += 1
    for _ in range(2 * scale):
        rooms.append(Room(room_id=f"R{rid:03d}", name=f"Comp Lab {rid}", capacity=26, room_type=RoomType.COMPUTER_LAB))
        rid += 1
    for k in range(scale):
        suffix = "" if k == 0 else f" {k+1}"
        rooms.append(Room(room_id=f"R{rid:03d}", name=f"Art Studio{suffix}", capacity=25, room_type=RoomType.ART)); rid += 1
        rooms.append(Room(room_id=f"R{rid:03d}", name=f"Music Hall{suffix}", capacity=30, room_type=RoomType.MUSIC)); rid += 1
        rooms.append(Room(room_id=f"R{rid:03d}", name=f"Gymnasium{suffix}", capacity=40, room_type=RoomType.GYM)); rid += 1
    return rooms


def _make_sections(courses: list[Course], teachers: list[Teacher], students: list[Student], adv_teacher_count: int = 6) -> list[Section]:
    """Size sections based on actual rank-1 demand and round-robin teacher load.

    Note: every requested course (rank 1 OR rank 2) gets at least one section so
    students can fall back on their alternate elective. Without this, Hypothesis
    fuzzing surfaces seeds where a rank-2-only request points to a course with
    zero sections, which trips COURSE_NO_SECTION at validation time.
    """
    sections: list[Section] = []

    # Compute rank-1 demand (drives section count) and overall demand (drives ≥1 section)
    demand: dict[str, int] = {}
    requested_anywhere: set[str] = set()
    for s in students:
        for r in s.requested_courses:
            requested_anywhere.add(r.course_id)
            if r.rank == 1:
                demand[r.course_id] = demand.get(r.course_id, 0) + 1

    teacher_load: dict[str, int] = {t.teacher_id: 0 for t in teachers}
    teacher_max: dict[str, int] = {t.teacher_id: t.max_load for t in teachers}

    def pick_teacher(pool: list[str]) -> str | None:
        # Lightest-loaded qualified teacher with capacity remaining
        candidates = [tid for tid in pool if teacher_load[tid] < teacher_max[tid]]
        if not candidates:
            return None
        return min(candidates, key=lambda tid: teacher_load[tid])

    for c in courses:
        if c.is_advisory:
            adv_teachers = teachers[:adv_teacher_count]
            for i, t in enumerate(adv_teachers, 1):
                sections.append(
                    Section(section_id=f"{c.course_id}.{i}", course_id=c.course_id, teacher_id=t.teacher_id, max_size=c.max_size)
                )
                # Advisory does not count against academic max_load by convention
            continue

        d = demand.get(c.course_id, 0)
        if d == 0 and c.course_id not in requested_anywhere:
            continue  # truly no demand, skip
        # If only rank-2 demand exists, still create at least one section
        target = max(1, int(d * 1.10) + 1)
        n_sections = max(1, -(-target // c.max_size))
        pool = c.qualified_teacher_ids
        if not pool:
            continue
        for i in range(n_sections):
            tid = pick_teacher(pool)
            if tid is None:
                # Out of qualified teacher capacity — produce fewer sections
                break
            sections.append(
                Section(section_id=f"{c.course_id}.{i+1}", course_id=c.course_id, teacher_id=tid, max_size=c.max_size)
            )
            teacher_load[tid] += 1
    return sections


def _make_students(n: int, courses: list[Course], rng: random.Random) -> list[Student]:
    students: list[Student] = []
    elective_pool = [c.course_id for c in courses if not c.is_required and not c.is_advisory and c.course_id in {x[0] for x in ELECTIVES}]
    core_required = [c.course_id for c in courses if c.is_required and not c.is_advisory]
    core_optional = ["CALC", "STATS", "BIO", "CHEM", "PHYS", "HIST", "SPAN", "CS", "PE", "ART"]

    for i in range(n):
        sid = f"S{2026000 + i:07d}"
        requests: list[CourseRequest] = []
        # Advisory always required
        requests.append(CourseRequest(student_id=sid, course_id="ADV", is_required=True, rank=1))
        # Required cores
        for cid in core_required:
            requests.append(CourseRequest(student_id=sid, course_id=cid, is_required=True, rank=1))
        # Each student picks 5 core/optional + 1 elective + 1 alternate elective = 7 + advisory + required = 8 total
        chosen_core = rng.sample(core_optional, k=5)
        for cid in chosen_core:
            requests.append(CourseRequest(student_id=sid, course_id=cid, is_required=True, rank=1))
        e_first, e_alt = rng.sample(elective_pool, k=2)
        requests.append(CourseRequest(student_id=sid, course_id=e_first, is_required=False, rank=1))
        requests.append(CourseRequest(student_id=sid, course_id=e_alt, is_required=False, rank=2))

        students.append(
            Student(
                student_id=sid,
                name=f"Student_{i:03d}",
                grade=12,
                requested_courses=requests,
            )
        )
    return students


def _make_behavior(students: Sequence[Student], rng: random.Random) -> BehaviorMatrix:
    ids = [s.student_id for s in students]
    seps: set[tuple[str, str]] = set()
    while len(seps) < 10:
        a, b = rng.sample(ids, k=2)
        if a == b:
            continue
        seps.add(tuple(sorted((a, b))))
    grps: set[tuple[str, str]] = set()
    while len(grps) < 8:
        a, b = rng.sample(ids, k=2)
        if a == b or tuple(sorted((a, b))) in seps:
            continue
        grps.add(tuple(sorted((a, b))))
    return BehaviorMatrix(separations=list(seps), groupings=list(grps))


def make_grade_12_dataset(n_students: int = 130, seed: int = 42, scale: int = 1) -> Dataset:
    """Generate a Grade-12 synthetic cohort.

    `scale` multiplies the teacher and room pools (and per-course qualification
    breadth) so larger cohorts remain feasible. Default scale=1 reproduces the
    original 22-teacher / 22-room baseline used by tests and the 130-student demo.
    """
    rng = random.Random(seed)
    bell = default_rotation()
    courses = _make_courses()
    teachers = _make_teachers(rng, scale=scale)
    _assign_qualifications(courses, teachers, scale=scale)
    rooms = _make_rooms(scale=scale)
    students = _make_students(n_students, courses, rng)
    adv_count = max(6, -(-n_students // 25))
    sections = _make_sections(courses, teachers, students, adv_teacher_count=adv_count)
    behavior = _make_behavior(students, rng)
    config = SchoolConfig(
        bell=bell,
        hard=HardConstraints(),
        soft=SoftConstraintWeights(),
    )
    return Dataset(
        config=config,
        courses=courses,
        teachers=teachers,
        rooms=rooms,
        sections=sections,
        students=students,
        behavior=behavior,
    )


def make_full_hs_dataset(n_students: int = 520, seed: int = 42) -> Dataset:
    """Synthetic full-HS-scale cohort for load testing.

    Scales teacher and room pools proportionally to the cohort size relative to
    the 130-student baseline, with one extra step of headroom so per-course
    qualification breadth doesn't bottleneck section creation.
    """
    scale = max(1, -(-n_students // 130))
    return make_grade_12_dataset(n_students=n_students, seed=seed, scale=scale)


# ---------------------------------------------------------------------------
# Middle School synthetic data (v2 §4.2)
#
# v2 §4.2 says MS uses the same A-E (5-day × 5-block) structure as HS, with
# more fixed schedules, fewer electives, and a grade-6 vs grade-7/8 split.
# Grade 6 takes a fully required schedule (no electives). Grades 7-8 take a
# mostly-required schedule with one elective slot.

MS_CORE_GR6 = [
    ("ENG6",  "English 6",         "english",        "standard", False),
    ("MATH6", "Math 6",            "math",           "standard", False),
    ("SCI6",  "Science 6",         "science",        "science_lab", True),
    ("SS6",   "Social Studies 6",  "social_studies", "standard", False),
    ("SPAN6", "Spanish 6",         "world_lang",     "standard", False),
    ("PE6",   "PE 6",              "pe",             "gym", False),
]

MS_CORE_GR7 = [
    ("ENG7",  "English 7",         "english",        "standard", False),
    ("MATH7", "Pre-Algebra",       "math",           "standard", False),
    ("SCI7",  "Science 7",         "science",        "science_lab", True),
    ("SS7",   "Social Studies 7",  "social_studies", "standard", False),
    ("SPAN7", "Spanish 7",         "world_lang",     "standard", False),
    ("PE7",   "PE 7",              "pe",             "gym", False),
]

MS_CORE_GR8 = [
    ("ENG8",  "English 8",         "english",        "standard", False),
    ("MATH8", "Algebra I",         "math",           "standard", False),
    ("SCI8",  "Science 8 (Earth)", "science",        "science_lab", True),
    ("SS8",   "World History 8",   "social_studies", "standard", False),
    ("SPAN8", "Spanish 8",         "world_lang",     "standard", False),
    ("PE8",   "PE 8",              "pe",             "gym", False),
]

MS_ELECTIVES = [
    ("MUS_MS",   "Band / Choir",      "arts",           "music",        False),
    ("DRAMA_MS", "Drama",             "arts",           "art",          False),
    ("TECH_MS",  "Tech / Robotics",   "tech",           "computer_lab", False),
    ("ART_MS",   "Visual Art",        "arts",           "art",          False),
]


def _make_ms_teachers(rng: random.Random, scale: int = 1) -> list[Teacher]:
    """MS teacher pool. Departments mirror HS so qualification logic is shared."""
    departments = {
        "english":        ["MS_Allen", "MS_Brooks", "MS_Cole"],
        "math":           ["MS_Diaz",  "MS_Evans",  "MS_Foster"],
        "science":        ["MS_Garcia", "MS_Hayes", "MS_Iqbal"],
        "social_studies": ["MS_Kim",   "MS_Lopez",  "MS_Mehta"],
        "world_lang":     ["MS_Nguyen", "MS_Ortiz"],
        "tech":           ["MS_Patel"],
        "pe":             ["MS_Reyes", "MS_Stone"],
        "arts":           ["MS_Singh", "MS_Tan"],
    }
    teachers: list[Teacher] = []
    tid = 600
    for dept, names in departments.items():
        for n in names:
            for k in range(scale):
                suffix = "" if k == 0 else f"_{k+1}"
                teachers.append(Teacher(
                    teacher_id=f"T{tid}", name=f"{n}{suffix}", department=dept,
                    qualified_course_ids=[], max_load=5,
                ))
                tid += 1
    return teachers


def _make_ms_courses() -> list[Course]:
    courses: list[Course] = [Course(
        course_id="ADV_MS",
        name="MS Advisory",
        department="advisory",
        grade_eligibility=[6, 7, 8],
        is_required=True,
        meetings_per_week=1,
        max_size=22,
        is_advisory=True,
        qualified_teacher_ids=["__ANY__"],
    )]
    for catalog, grade in [(MS_CORE_GR6, 6), (MS_CORE_GR7, 7), (MS_CORE_GR8, 8)]:
        for cid, name, dept, room_type, is_lab in catalog:
            courses.append(Course(
                course_id=cid, name=name, department=dept,
                grade_eligibility=[grade], is_required=True,
                meetings_per_week=3, max_size=24,
                required_room_type=RoomType(room_type),
                is_lab=is_lab, qualified_teacher_ids=[],
            ))
    for cid, name, dept, room_type, is_lab in MS_ELECTIVES:
        courses.append(Course(
            course_id=cid, name=name, department=dept,
            grade_eligibility=[7, 8], is_required=False,
            meetings_per_week=3, max_size=24,
            required_room_type=RoomType(room_type),
            is_lab=is_lab, qualified_teacher_ids=[],
        ))
    return courses


def _make_ms_students(n_per_grade: int, courses: list[Course], rng: random.Random) -> list[Student]:
    students: list[Student] = []
    elective_pool = [c.course_id for c in courses if not c.is_required and not c.is_advisory]
    core_by_grade = {
        6: [cid for cid, *_ in MS_CORE_GR6],
        7: [cid for cid, *_ in MS_CORE_GR7],
        8: [cid for cid, *_ in MS_CORE_GR8],
    }
    sid_counter = 0
    for grade in (6, 7, 8):
        for i in range(n_per_grade):
            sid_counter += 1
            sid = f"M{2026000 + sid_counter:07d}"
            requests: list[CourseRequest] = [
                CourseRequest(student_id=sid, course_id="ADV_MS", is_required=True, rank=1),
            ]
            for cid in core_by_grade[grade]:
                requests.append(CourseRequest(student_id=sid, course_id=cid, is_required=True, rank=1))
            # Grades 7 and 8 pick one elective (rank 1) + one alternate (rank 2)
            if grade in (7, 8) and elective_pool:
                e_first, e_alt = rng.sample(elective_pool, k=2)
                requests.append(CourseRequest(student_id=sid, course_id=e_first, is_required=False, rank=1))
                requests.append(CourseRequest(student_id=sid, course_id=e_alt, is_required=False, rank=2))
            students.append(Student(student_id=sid, name=f"MS_Student_{sid_counter:04d}", grade=grade, requested_courses=requests))
    return students


def make_full_ms_dataset(n_per_grade: int = 100, seed: int = 42) -> Dataset:
    """Synthetic full-MS dataset (grades 6-8) per v2 §4.2.

    Generates `n_per_grade` students in each of grades 6, 7, 8. Grade 6 takes
    a fully fixed schedule (no electives). Grades 7-8 each take one elective
    plus one alternate from a 4-course MS elective pool.

    Reuses the same A-E (5-day × 5-block) rotation as HS — v2 §4.2 says MS
    "Similar A-E structure". The course catalog and request shape differ.
    """
    rng = random.Random(seed)
    bell = default_rotation()
    courses = _make_ms_courses()
    # Pick scale so the teacher / room pool can support 3 grades' worth of
    # required cores without hitting the qualification or capacity ceiling.
    n_total = n_per_grade * 3
    scale = max(1, -(-n_total // 130))
    teachers = _make_ms_teachers(rng, scale=scale)
    _assign_qualifications(courses, teachers, scale=scale)
    rooms = _make_rooms(scale=scale)
    students = _make_ms_students(n_per_grade, courses, rng)
    adv_count = max(6, -(-len(students) // 22))
    sections = _make_sections(courses, teachers, students, adv_teacher_count=adv_count)
    behavior = _make_behavior(students, rng)
    config = SchoolConfig(
        school="Columbus Middle School",
        grade=6,  # primary grade label; multi-grade datasets use min
        year="2026-2027",
        bell=bell,
        hard=HardConstraints(),
        soft=SoftConstraintWeights(),
    )
    return Dataset(
        config=config, courses=courses, teachers=teachers, rooms=rooms,
        sections=sections, students=students, behavior=behavior,
    )


if __name__ == "__main__":
    ds = make_grade_12_dataset()
    print(f"courses:  {len(ds.courses)}")
    print(f"teachers: {len(ds.teachers)}")
    print(f"rooms:    {len(ds.rooms)}")
    print(f"sections: {len(ds.sections)}")
    print(f"students: {len(ds.students)}")
    print(f"requests/student: {sum(len(s.requested_courses) for s in ds.students) / len(ds.students):.1f}")
    print(f"separations: {len(ds.behavior.separations)}")
    print(f"groupings:   {len(ds.behavior.groupings)}")
    by_course: dict[str, int] = {}
    for s in ds.sections:
        by_course[s.course_id] = by_course.get(s.course_id, 0) + 1
    print(f"sections by course: {sorted(by_course.items())}")
