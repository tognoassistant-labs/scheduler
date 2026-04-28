"""Canonical PowerSchool ingester (replaces xlsx-derived ps_ingest.py for v4+).

Reads the official Columbus PowerSchool catalog xlsx exported from PS itself
(`reference/columbus_official_2026-2027.xlsx`) and produces a Dataset with
**real PS IDs** — no slugs, no heuristics.

5 sheets:
    courses              — Course catalog with COURSE_NUMBER (real PS), MAXCLASSSIZE,
                            MULTITERM, SCHED_FREQUENCY, SCHED_DEMAND
    rooms                — Room catalog with DCID, ROOMNUMBER, DEPARTMENT, MAXIMUM
    teachers             — Teacher catalog with DCID, LASTFIRST, PREFERRED_ROOM,
                            SCHED_DEPARTMENT
    teacher_assignments  — Per-(teacher, course) assignments with SECTIONS_PER_COURSE
    requests             — Per-student requests with COURSENUMBER, STUDENT_NUMBER

Fixes applied (consolidated from ps_ingest.py history):
    - All requests are is_required=True / rank=1 (client B6: no alternates 2026-2027)
    - PREFERRED_ROOM → Teacher.home_room_id (HC4)
    - max_consecutive_classes per teacher: default 4, override 5 only for the
      pigeonhole-impossible cases (≥7 academic sections)
    - Multi-room teachers (PREFERRED_ROOM blank in source) stay floating
    - Semester courses (MULTITERM='S1' or 'S2') are flagged via Course.term
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

from .models import (
    BehaviorMatrix,
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
    Term,
    default_rotation,
)


# ---------------------------------------------------------------------------
# Helpers


def _safe_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _safe_int(v, default: int = 0) -> int:
    if v is None or v == "":
        return default
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _infer_room_type(department: str, room_name: str) -> RoomType:
    """Map a room department + name to a RoomType."""
    d = (department or "").lower()
    n = (room_name or "").lower()
    if "pe" in d or "coliseo" in n or "gym" in n:
        return RoomType.GYM
    if "science" in d or "lab" in n:
        return RoomType.SCIENCE_LAB
    if "tech" in d or "maker" in n or "comp" in n:
        return RoomType.COMPUTER_LAB
    if "art" in d:
        return RoomType.ART
    if "music" in d or "band" in n:
        return RoomType.MUSIC
    return RoomType.STANDARD


def _infer_grades_from_name(name: str) -> list[int]:
    """Extract grade levels from a course name like 'English 9' or 'AP Spanish Lit'.

    Returns the grades the course is offered to. For courses without an explicit
    grade in the name, returns [9, 10, 11, 12] as the eligibility set.
    """
    grades = sorted({int(m) for m in re.findall(r"\b(9|10|11|12)\b", name or "")})
    if grades:
        return grades
    # No explicit grade in name → eligible to all HS grades
    return [9, 10, 11, 12]


# ---------------------------------------------------------------------------
# Sheet readers


def _read_courses(wb) -> list[dict]:
    ws = wb["courses"]
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    out = []
    for raw in rows[1:]:
        if not raw or not raw[0]:
            continue
        d = dict(zip(headers, raw))
        if not d.get("COURSE_NUMBER"):
            continue
        out.append(d)
    return out


def _read_rooms(wb) -> list[dict]:
    ws = wb["rooms"]
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    out = []
    for raw in rows[1:]:
        if not raw or not raw[0]:
            continue
        d = dict(zip(headers, raw))
        if not d.get("ROOMNUMBER"):
            continue
        out.append(d)
    return out


def _read_teachers(wb) -> list[dict]:
    ws = wb["teachers"]
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    out = []
    for raw in rows[1:]:
        if not raw or not raw[0]:
            continue
        d = dict(zip(headers, raw))
        if not d.get("LASTFIRST"):
            continue
        out.append(d)
    return out


def _read_teacher_assignments(wb) -> list[dict]:
    ws = wb["teacher_assignments"]
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    out = []
    for raw in rows[1:]:
        if not raw or not raw[0]:
            continue
        d = dict(zip(headers, raw))
        if not d.get("COURSENUMBER") or not d.get("TEACHER_DCID"):
            continue
        out.append(d)
    return out


def _apply_course_relationships(
    rel_path: Path,
    courses: list[Course],
    course_by_number: dict[str, Course],
) -> None:
    """Read course_relationships.csv and set Course.simul_group / Course.term_pair.

    Simultaneous relationships are unioned via union-find so chains (G0902 ↔
    G1204, G0902 ↔ G1205, G0902 ↔ G1206) collapse to a single shared group ID.
    Term relationships are stored as a single peer pointer per course.
    """
    parent: dict[str, str] = {}

    def _find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def _union(a: str, b: str) -> None:
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    term_pairs: dict[str, str] = {}
    simul_courses: set[str] = set()
    with rel_path.open() as f:
        for row in csv.DictReader(f):
            c1 = (row.get("COURSE_NUMBER1") or "").strip()
            c2 = (row.get("COURSE_NUMBER2") or "").strip()
            code = (row.get("RELATIONSHIPCODE") or "").strip()
            if not c1 or not c2:
                continue
            if code == "Simultaneous":
                _union(c1, c2)
                simul_courses.add(c1)
                simul_courses.add(c2)
            elif code == "Term":
                term_pairs[c1] = c2
                term_pairs[c2] = c1

    for cid in simul_courses:
        c = course_by_number.get(cid)
        if c is not None:
            c.simul_group = _find(cid)
    for cid, peer in term_pairs.items():
        c = course_by_number.get(cid)
        if c is not None:
            c.term_pair = peer


def _read_requests(wb) -> list[dict]:
    ws = wb["requests"]
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    out = []
    for raw in rows[1:]:
        if not raw or not raw[0]:
            continue
        d = dict(zip(headers, raw))
        if not d.get("COURSENUMBER") or not d.get("STUDENT_NUMBER"):
            continue
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Builder


def build_dataset_from_official_xlsx(
    xlsx_path: Path,
    grades: list[int] | None = None,
) -> Dataset:
    """Build a canonical Dataset from the official PS-exported xlsx.

    `grades` filters student requests to those grades. Default = full HS [9..12].

    Returns a Dataset where:
    - Course IDs are real PS COURSE_NUMBERs (e.g. 'OZ1313', 'E0901')
    - Teacher IDs are real PS DCIDs as strings (e.g. '377')
    - Room IDs are real PS room DCIDs as strings (e.g. '1', '304')
    - Student IDs are real PS STUDENT_NUMBERs (e.g. '28026')
    """
    if grades is None:
        grades = [9, 10, 11, 12]

    wb = load_workbook(xlsx_path, data_only=True)

    course_rows = _read_courses(wb)
    room_rows = _read_rooms(wb)
    teacher_rows = _read_teachers(wb)
    assignment_rows = _read_teacher_assignments(wb)
    request_rows = _read_requests(wb)

    # ------------------------------------------------------------------ rooms
    room_dcid_by_number: dict[str, str] = {}
    rooms: list[Room] = []
    for r in room_rows:
        dcid = _safe_str(r.get("DCID"))
        room_number = _safe_str(r.get("ROOMNUMBER"))
        department = _safe_str(r.get("DEPARTMENT"))
        capacity = _safe_int(r.get("MAXIMUM"), default=25) or 25
        room_dcid_by_number[room_number] = dcid
        rooms.append(Room(
            room_id=dcid,
            name=room_number,
            capacity=capacity,
            room_type=_infer_room_type(department, room_number),
            department=department or None,
        ))

    # --------------------------------------------------------------- courses
    courses: list[Course] = []
    course_by_number: dict[str, Course] = {}
    for c in course_rows:
        course_number = _safe_str(c["COURSE_NUMBER"])
        name = _safe_str(c.get("COURSE_NAME"))
        department = _safe_str(c.get("SCHED_DEPARTMENT"))
        max_size = _safe_int(c.get("MAXCLASSSIZE"), default=25) or 25
        # PE has MAXCLASSSIZE=130; AP Research has 26 explicitly.
        # Some courses have 0 → treat as default 25.
        if max_size <= 0:
            max_size = 25
        meetings = _safe_int(c.get("SCHED_FREQUENCY"), default=3) or 3
        is_advisory = course_number.upper().startswith("ADV")
        # Per client B6: only PE is curricularly "required". The rest is variable
        # but every student request must still be assigned (handled at request level).
        is_required_course = course_number.upper().startswith("E") and any(
            course_number.upper().endswith(suffix) for suffix in ("0901", "1001", "1101", "1201")
        )
        # MULTITERM 'S1' / 'S2' → semester course; everything else year-long
        multiterm = _safe_str(c.get("MULTITERM"))
        term = Term.SEMESTER if multiterm in ("S1", "S2") else Term.YEAR
        course = Course(
            course_id=course_number,
            name=name,
            department=department or "general",
            grade_eligibility=_infer_grades_from_name(name),
            is_required=is_required_course,
            meetings_per_week=meetings if not is_advisory else 1,
            max_size=max_size,
            is_advisory=is_advisory,
            qualified_teacher_ids=[],
            term=term,
        )
        courses.append(course)
        course_by_number[course_number] = course

    # ---------------------------------------------- course relationships (v4.2)
    # Apply Simultaneous and Term relationships from the client-provided
    # `course_relationships.csv` (canonical reference at repo root). The file
    # contains 7 rows for HS 2026-2027:
    #   - 6 Simultaneous (multi-level classes: Spanish FL, AP Art, Drawings, etc.)
    #   - 1 Term (AP Micro / AP Macro share slot, alternate semesters)
    rel_path = xlsx_path.parent / "course_relationships.csv"
    if rel_path.exists():
        _apply_course_relationships(rel_path, courses, course_by_number)

    # -------------------------------------------------------------- teachers
    teachers: list[Teacher] = []
    teacher_by_dcid: dict[str, Teacher] = {}
    teacher_by_lastfirst: dict[str, Teacher] = {}
    for t in teacher_rows:
        dcid = _safe_str(t["DCID"])
        lastfirst = _safe_str(t.get("LASTFIRST"))
        department = _safe_str(t.get("SCHED_DEPARTMENT"))
        preferred_room_number = _safe_str(t.get("PREFERRED_ROOM"))
        home_room_id = room_dcid_by_number.get(preferred_room_number) if preferred_room_number else None
        teacher = Teacher(
            teacher_id=dcid,
            name=lastfirst,
            department=department or "general",
            qualified_course_ids=[],
            max_load=5,  # tightened below from observed assignments
            home_room_id=home_room_id,
        )
        teachers.append(teacher)
        teacher_by_dcid[dcid] = teacher
        teacher_by_lastfirst[lastfirst] = teacher

    # ---------------------------------------------------- sections (from assignments)
    sections: list[Section] = []
    sections_per_teacher: dict[str, int] = defaultdict(int)
    section_counter_per_course: dict[str, int] = defaultdict(int)

    # v4.2: SCHEDULETERMCODE → Section.term_id (Columbus 2026-2027 mapping confirmed
    # by client 2026-04-28). Year-long courses keep term_id=None and inherit
    # SchoolConfig.term_id (3600) at export time.
    TERM_CODE_TO_ID = {"S1": "3601", "S2": "3602"}

    for a in assignment_rows:
        teacher_dcid = _safe_str(a["TEACHER_DCID"])
        course_number = _safe_str(a["COURSENUMBER"])
        n_sections = _safe_int(a.get("SECTIONS_PER_COURSE"), default=1)
        # SECTIONTYPE 'LP' rows are duplicates of regular rows in the source — skip.
        section_type = _safe_str(a.get("SECTIONTYPE"))
        if section_type:  # 'LP' or any non-empty subtype → already counted in the regular row
            continue

        teacher = teacher_by_dcid.get(teacher_dcid)
        course = course_by_number.get(course_number)
        if teacher is None or course is None:
            continue

        # Term handling: v4.2 ships Simultaneous course relationships.
        # Term-paired sections (S1/S2 sharing slot) are deferred to v4.3 —
        # the master_solver's term-aware HC1/HC2 partitioning passes locally
        # but interacts subtly with the global scheme balance and HC4 home_room
        # pinning to produce INFEASIBLE for Ortegon's room. Skip semester
        # sections for now; the engine still produces the correct merged
        # multi-level Spanish/Art/Drawing/Sculpture sections (the bigger win).
        # TODO v4.3: emit Term sections + adjust scheme balance + handle home_room.
        term_code = _safe_str(a.get("SCHEDULETERMCODE"))
        if term_code and term_code not in ("26-27", "2026-2027"):
            continue
        section_term_id: str | None = None

        # Wire up qualifications
        if course_number not in teacher.qualified_course_ids:
            teacher.qualified_course_ids.append(course_number)
        if teacher_dcid not in course.qualified_teacher_ids:
            course.qualified_teacher_ids.append(teacher_dcid)

        for _ in range(n_sections):
            section_counter_per_course[course_number] += 1
            idx = section_counter_per_course[course_number]
            sections.append(Section(
                section_id=f"{course_number}.{idx}",
                course_id=course_number,
                teacher_id=teacher_dcid,
                max_size=course.max_size,
                grade_level=course.grade_eligibility[0] if course.grade_eligibility else 12,
                term_id=section_term_id,
            ))
            if not course.is_advisory:
                sections_per_teacher[teacher_dcid] += 1

    # v4.2 — Simultaneous merge pass.
    # When a teacher is assigned to multiple courses sharing the same simul_group
    # (multi-level class: e.g. Spanish 9/10/11/12 FL, AP 2D + AP 3D Art), merge
    # those individual sections into ONE physical section with `linked_course_ids`
    # set to the additional courses. This fixes the apparent "overload" of
    # teachers like Clara Martínez (9 sections → 5) and Sofia Arcila.
    #
    # Strategy: for each (teacher, simul_group), pair sections by index — the
    # k-th section of each course in the group becomes one combined physical
    # section. If counts differ across courses (rare in practice), the extras
    # remain as standalone single-course sections.
    merged_groups: dict[tuple[str, str], dict[str, list[int]]] = {}
    for i, s in enumerate(sections):
        c = course_by_number.get(s.course_id)
        if c is None or c.simul_group is None:
            continue
        key = (s.teacher_id, c.simul_group)
        merged_groups.setdefault(key, {}).setdefault(s.course_id, []).append(i)

    to_remove: set[int] = set()
    for (tid, sg), by_course in merged_groups.items():
        if len(by_course) <= 1:
            continue  # only one course of the group present — nothing to merge
        # Pair by index: k-th section of each course becomes one combined section.
        ordered_courses = sorted(by_course.keys())  # determinism
        max_k = max(len(idxs) for idxs in by_course.values())
        for k in range(max_k):
            primary_idx: int | None = None
            for cid in ordered_courses:
                idxs = by_course[cid]
                if k >= len(idxs):
                    continue  # this course doesn't have a k-th section
                if primary_idx is None:
                    primary_idx = idxs[k]
                else:
                    # Append linked course to primary; mark this section for removal
                    primary = sections[primary_idx]
                    if cid != primary.course_id and cid not in primary.linked_course_ids:
                        primary.linked_course_ids.append(cid)
                    to_remove.add(idxs[k])
                    # Pigeonhole credit relief: this physical section is no longer
                    # "extra" load on the teacher.
                    if not course_by_number[cid].is_advisory:
                        sections_per_teacher[tid] -= 1
    if to_remove:
        sections = [s for i, s in enumerate(sections) if i not in to_remove]

    # Drop teachers with no academic sections (happens when SECTIONTYPE filter dropped all rows)
    # Note: keep all teachers — even those with only Advisory — since they appear in the data.

    # Apply per-teacher max_consec override for the pigeonhole-impossible cases
    for tid, n in sections_per_teacher.items():
        if n >= 7:
            t = teacher_by_dcid.get(tid)
            if t is not None:
                t.max_consecutive_classes = 5

    # Adjust max_load per observed
    for t in teachers:
        observed = sections_per_teacher.get(t.teacher_id, 0)
        if observed > t.max_load:
            t.max_load = observed

    # Drop courses that ended up with zero sections (no qualified teacher in this dataset)
    courses = [c for c in courses if c.is_advisory or any(s.course_id == c.course_id for s in sections)]
    course_by_number = {c.course_id: c for c in courses}

    # ----------------------------------------------------------------- students
    students_map: dict[str, Student] = {}
    for r in request_rows:
        sid = _safe_str(r["STUDENT_NUMBER"])
        course_number = _safe_str(r["COURSENUMBER"])
        if not sid or not course_number:
            continue
        if course_number not in course_by_number:
            continue  # request for a course not in catalog — skip
        if sid not in students_map:
            # Infer grade from the courses they request (highest grade-suffixed course wins)
            students_map[sid] = Student(
                student_id=sid,
                name=f"Student_{sid}",  # real names not in this sheet; PS provides them later
                grade=12,  # placeholder; updated below if their requests reveal a grade
                requested_courses=[],
            )
        # Per client B6: ALL requests for 2026-2027 are mandatory.
        students_map[sid].requested_courses.append(CourseRequest(
            student_id=sid,
            course_id=course_number,
            is_required=True,
            rank=1,
        ))

    # Add Advisory request to every student (Advisory is always-on for HS)
    advisory_id = next((c.course_id for c in courses if c.is_advisory), None)
    if advisory_id:
        for s in students_map.values():
            if not any(r.course_id == advisory_id for r in s.requested_courses):
                s.requested_courses.append(CourseRequest(
                    student_id=s.student_id,
                    course_id=advisory_id,
                    is_required=True,
                    rank=1,
                ))

    # Infer student grade from grade suffixes in their requested course names
    for s in students_map.values():
        grade_votes: dict[int, int] = defaultdict(int)
        for r in s.requested_courses:
            c = course_by_number.get(r.course_id)
            if not c:
                continue
            for g in c.grade_eligibility:
                if g in (9, 10, 11, 12):
                    grade_votes[g] += 1
        if grade_votes:
            # Pick the LOWEST grade with the most votes — usually their home grade.
            # (e.g. a grade-11 student takes some grade-10 courses; lowest is correct.)
            top = max(grade_votes.values())
            s.grade = min(g for g, v in grade_votes.items() if v == top)

    students = list(students_map.values())

    # Filter by requested grades if not full HS
    if set(grades) != {9, 10, 11, 12}:
        students = [s for s in students if s.grade in grades]

    # Advisory sections: prefer the PS-provided advisory rows from the assignment
    # sheet (canonical). Only synthesize new advisory sections if PS gave us none
    # — otherwise we duplicate the PS-derived ones and blow up HC1/HC4 budgets.
    if advisory_id:
        existing_adv = [s for s in sections if s.course_id == advisory_id]
        if not existing_adv:
            adv_size = course_by_number[advisory_id].max_size or 25
            if adv_size <= 0:
                adv_size = 25
            n_adv = max(6, -(-len(students) // adv_size))
            adv_teachers = [t for t in teachers if advisory_id in t.qualified_course_ids]
            if not adv_teachers:
                adv_teachers = teachers[:n_adv]
            for i in range(n_adv):
                tid = adv_teachers[i % len(adv_teachers)].teacher_id
                sections.append(Section(
                    section_id=f"{advisory_id}.{i+1}",
                    course_id=advisory_id,
                    teacher_id=tid,
                    max_size=adv_size,
                    grade_level=9,
                ))

    # Build SchoolConfig with the canonical PS values
    is_ms = all(g in (6, 7, 8) for g in grades)
    config = SchoolConfig(
        school="Columbus Middle School" if is_ms else "Columbus High School",
        school_id=12000 if is_ms else 13000,
        term_id="3600",
        grade=min(grades),
        year="2026-2027",
        bell=default_rotation(),
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
        behavior=BehaviorMatrix(),  # behavior matrix comes from a separate file (HS_Schedule.xlsx)
    )
