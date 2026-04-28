"""OneRoster v1.1 CSV bundle reader/writer (v1 spec §7.2).

OneRoster (IMS Global) is a CSV interchange format for sharing roster data
between an SIS (PowerSchool, Infinite Campus, etc.) and learning platforms
(Canvas, Schoology, Google Classroom). The spec is at:
https://www.imsglobal.org/spec/oneroster/v1p1/

Files written by `write_oneroster`:
  manifest.csv          — bundle metadata
  orgs.csv              — the school (single row)
  academicSessions.csv  — the school year (single row)
  users.csv             — teachers + students
  courses.csv           — Dataset.courses
  classes.csv           — Dataset.sections with master scheme + room
  enrollments.csv       — student→class + teacher→class

Files NOT written (optional in v1.1, not in spec §7.2):
  demographics.csv, lineItems.csv, results.csv, categories.csv,
  classResources.csv, courseResources.csv

The reader (`read_oneroster`) reconstructs a roster-only Dataset:
courses, teachers, rooms (synthesized from class `location`), sections,
students. It does NOT recover CourseRequest ranks or BehaviorMatrix
because OneRoster does not carry those concepts. Use the reader to bootstrap
a Dataset, then attach demand and behavior from another source.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    BehaviorMatrix,
    Course,
    Dataset,
    HardConstraints,
    MasterAssignment,
    Room,
    RoomType,
    SchoolConfig,
    Section,
    SoftConstraintWeights,
    Student,
    StudentAssignment,
    Teacher,
    default_rotation,
)


# ---------------------------------------------------------------------------
# helpers

_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def _slug(s: str) -> str:
    return _SLUG_RE.sub("-", s.strip()).strip("-").lower() or "x"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _school_sid(school: str) -> str:
    return f"school-{_slug(school)}"


def _term_sid(year: str) -> str:
    return f"term-{_slug(year)}"


def _course_sid(course_id: str) -> str:
    return f"course-{course_id}"


def _class_sid(section_id: str) -> str:
    return f"class-{section_id}"


def _student_sid(student_id: str) -> str:
    return f"student-{student_id}"


def _teacher_sid(teacher_id: str) -> str:
    return f"teacher-{teacher_id}"


def _enrollment_sid(role: str, user_id: str, section_id: str) -> str:
    return f"enr-{role[0]}-{user_id}-{section_id}"


def _split_name(full: str) -> tuple[str, str]:
    """OneRoster wants givenName + familyName separately."""
    full = (full or "").strip()
    if not full:
        return ("", "")
    parts = full.split()
    if len(parts) == 1:
        return (parts[0], "")
    return (" ".join(parts[:-1]), parts[-1])


def _period_code(scheme: object) -> str:
    if scheme == "ADVISORY":
        return "ADV"
    return f"P{scheme:02d}"


def _slot_codes(master: MasterAssignment) -> str:
    """Compact period descriptor: scheme code + day-block list.

    Example: "P03 | Mon-1,Wed-3,Fri-5". Importers can split on '|' if needed.
    """
    sched = ",".join(f"{d}-{b}" for d, b in master.slots)
    return f"{_period_code(master.scheme)} | {sched}"


def _year_dates(year: str) -> tuple[str, str]:
    """Best-effort start/end dates for a string like '2026-2027'.

    Defaults to Aug 1 / May 31 of the parsed years; importers that care about
    exact term dates should pass `school_year_start`/`school_year_end` to
    `write_oneroster`.
    """
    m = re.match(r"^(\d{4})\s*[-/]\s*(\d{2,4})$", year.strip()) if year else None
    if m:
        y1 = int(m.group(1))
        y2_raw = m.group(2)
        y2 = int(y2_raw) if len(y2_raw) == 4 else 2000 + int(y2_raw)
    else:
        y1 = datetime.now(timezone.utc).year
        y2 = y1 + 1
    return f"{y1}-08-01", f"{y2}-05-31"


# ---------------------------------------------------------------------------
# writer


def write_oneroster(
    ds: Dataset,
    master: list[MasterAssignment],
    students: list[StudentAssignment],
    out_dir: Path,
    school_year_start: str | None = None,
    school_year_end: str | None = None,
) -> None:
    """Write a OneRoster v1.1 CSV bundle to `out_dir`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    now = _now_iso()
    school = ds.config.school
    year = ds.config.year
    grade = ds.config.grade

    school_sid = _school_sid(school)
    term_sid = _term_sid(year)
    start, end = _year_dates(year)
    if school_year_start:
        start = school_year_start
    if school_year_end:
        end = school_year_end

    courses_by_id = {c.course_id: c for c in ds.courses}
    rooms_by_id = {r.room_id: r for r in ds.rooms}
    teachers_by_id = {t.teacher_id: t for t in ds.teachers}
    sections_by_id = {s.section_id: s for s in ds.sections}
    master_by_section = {m.section_id: m for m in master}

    # 1. orgs.csv — the school
    with (out_dir / "orgs.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sourcedId", "status", "dateLastModified", "name", "type", "identifier", "parentSourcedId"])
        w.writerow([school_sid, "active", now, school, "school", school_sid, ""])

    # 2. academicSessions.csv — the school year
    with (out_dir / "academicSessions.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sourcedId", "status", "dateLastModified", "title", "type", "startDate", "endDate", "parentSourcedId", "schoolYear"])
        w.writerow([term_sid, "active", now, year, "schoolYear", start, end, "", year.split("-")[0] if "-" in year else year])

    # 3. users.csv — teachers + students
    with (out_dir / "users.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "sourcedId", "status", "dateLastModified", "enabledUser", "orgSourcedIds",
            "role", "username", "userIds", "givenName", "familyName", "middleName",
            "identifier", "email", "sms", "phone", "agentSourcedIds", "grades", "password",
        ])
        for t in ds.teachers:
            given, family = _split_name(t.name)
            w.writerow([
                _teacher_sid(t.teacher_id), "active", now, "true", school_sid,
                "teacher", t.teacher_id, "", given, family, "",
                t.teacher_id, "", "", "", "", "", "",
            ])
        for s in ds.students:
            given, family = _split_name(s.name)
            w.writerow([
                _student_sid(s.student_id), "active", now, "true", school_sid,
                "student", s.student_id, "", given, family, "",
                s.student_id, "", "", "", "", str(s.grade), "",
            ])

    # 4. courses.csv
    school_year_only = year.split("-")[0] if "-" in year else year
    with (out_dir / "courses.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "sourcedId", "status", "dateLastModified", "schoolYearSourcedId",
            "title", "courseCode", "grades", "orgSourcedId", "subjects", "subjectCodes",
        ])
        for c in ds.courses:
            grades_field = ",".join(str(g) for g in c.grade_eligibility) if c.grade_eligibility else str(grade)
            w.writerow([
                _course_sid(c.course_id), "active", now, term_sid,
                c.name, c.course_id, grades_field, school_sid, c.department, c.department,
            ])

    # 5. classes.csv — sections with master placement
    with (out_dir / "classes.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "sourcedId", "status", "dateLastModified", "title", "grades",
            "courseSourcedId", "classCode", "classType", "location", "schoolSourcedId",
            "termSourcedIds", "subjects", "subjectCodes", "periods",
        ])
        for s in ds.sections:
            c = courses_by_id.get(s.course_id)
            m = master_by_section.get(s.section_id)
            location = ""
            periods = ""
            if m is not None:
                room = rooms_by_id.get(m.room_id)
                location = room.name if room else m.room_id
                periods = _slot_codes(m)
            grades_field = str(c.grade_eligibility[0]) if (c and c.grade_eligibility) else str(grade)
            class_type = "homeroom" if (c and c.is_advisory) else "scheduled"
            w.writerow([
                _class_sid(s.section_id), "active", now, c.name if c else s.course_id,
                grades_field, _course_sid(s.course_id), s.section_id, class_type,
                location, school_sid, term_sid,
                c.department if c else "", c.department if c else "", periods,
            ])

    # 6. enrollments.csv — student + teacher class associations
    with (out_dir / "enrollments.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "sourcedId", "status", "dateLastModified", "classSourcedId",
            "schoolSourcedId", "userSourcedId", "role", "primary", "beginDate", "endDate",
        ])
        # Primary teacher per section
        for s in ds.sections:
            if s.section_id not in master_by_section:
                continue
            t = teachers_by_id.get(s.teacher_id)
            if t is None:
                continue
            w.writerow([
                _enrollment_sid("teacher", s.teacher_id, s.section_id), "active", now,
                _class_sid(s.section_id), school_sid, _teacher_sid(s.teacher_id),
                "teacher", "true", start, end,
            ])
        # Students per their assigned sections
        for sa in students:
            for sid in sa.section_ids:
                if sid not in sections_by_id or sid not in master_by_section:
                    continue
                w.writerow([
                    _enrollment_sid("student", sa.student_id, sid), "active", now,
                    _class_sid(sid), school_sid, _student_sid(sa.student_id),
                    "student", "false", start, end,
                ])

    # 7. manifest.csv — must list which files are present
    present = ["academicSessions", "orgs", "users", "courses", "classes", "enrollments"]
    absent = ["demographics", "lineItems", "results", "categories", "classResources", "courseResources"]
    with (out_dir / "manifest.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["propertyName", "value"])
        w.writerow(["manifest.version", "1.0"])
        w.writerow(["oneroster.version", "1.1"])
        for name in present:
            w.writerow([f"file.{name}", "bulk"])
        for name in absent:
            w.writerow([f"file.{name}", "absent"])
        w.writerow(["source.systemName", "Columbus scheduling engine"])
        w.writerow(["source.systemCode", "scheduler-py"])


# ---------------------------------------------------------------------------
# reader (roster-only)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


_TEACHER_PREFIX = "teacher-"
_STUDENT_PREFIX = "student-"
_COURSE_PREFIX = "course-"
_CLASS_PREFIX = "class-"


def _strip_prefix(s: str, p: str) -> str:
    return s[len(p):] if s.startswith(p) else s


def read_oneroster(in_dir: Path) -> Dataset:
    """Read a OneRoster v1.1 CSV bundle into a roster-only Dataset.

    Limitations:
      - CourseRequest ranks are NOT recovered (OneRoster has no concept of
        per-student course preferences); `Student.requested_courses` is empty.
      - BehaviorMatrix (separations / groupings) is NOT recovered.
      - Rooms are synthesized from class `location` strings (capacity defaults
        to 25, room_type defaults to STANDARD). Real ingest from a OneRoster
        bundle should be followed by a manual room-attribute pass.
    """
    in_dir = Path(in_dir)

    orgs = _read_csv(in_dir / "orgs.csv")
    sessions = _read_csv(in_dir / "academicSessions.csv")
    users = _read_csv(in_dir / "users.csv")
    courses_rows = _read_csv(in_dir / "courses.csv")
    classes_rows = _read_csv(in_dir / "classes.csv")
    enrollments = _read_csv(in_dir / "enrollments.csv")

    # School + year
    school_name = orgs[0]["name"] if orgs else "Unknown School"
    year = sessions[0]["title"] if sessions else "unknown-year"

    # Teachers + students
    teachers: list[Teacher] = []
    students_out: list[Student] = []
    for u in users:
        sid = u["sourcedId"]
        role = (u.get("role") or "").strip().lower()
        name = " ".join(p for p in (u.get("givenName"), u.get("middleName"), u.get("familyName")) if p)
        identifier = (u.get("identifier") or u.get("username") or _strip_prefix(sid, _TEACHER_PREFIX if role == "teacher" else _STUDENT_PREFIX)).strip()
        if role == "teacher":
            teachers.append(Teacher(
                teacher_id=identifier, name=name or identifier, department="",
                qualified_course_ids=[], max_load=5,
            ))
        elif role == "student":
            grade_str = (u.get("grades") or "").split(",")[0].strip()
            try:
                grade = int(grade_str)
            except ValueError:
                grade = 12
            students_out.append(Student(
                student_id=identifier, name=name or identifier, grade=grade,
                requested_courses=[],
            ))

    # Courses
    courses: list[Course] = []
    for c in courses_rows:
        course_id = (c.get("courseCode") or _strip_prefix(c["sourcedId"], _COURSE_PREFIX)).strip()
        name = c.get("title") or course_id
        dept = (c.get("subjects") or c.get("subjectCodes") or "").split(",")[0].strip() or "general"
        grades_field = (c.get("grades") or "").strip()
        try:
            grade_eligibility = [int(x.strip()) for x in grades_field.split(",") if x.strip()]
        except ValueError:
            grade_eligibility = [12]
        courses.append(Course(
            course_id=course_id, name=name, department=dept,
            grade_eligibility=grade_eligibility or [12], is_required=False,
            meetings_per_week=3, max_size=25, qualified_teacher_ids=[],
        ))

    # Rooms — synthesized from unique class locations
    rooms_by_name: dict[str, Room] = {}
    for c in classes_rows:
        loc = (c.get("location") or "").strip()
        if not loc or loc in rooms_by_name:
            continue
        rid = f"R{len(rooms_by_name)+1:03d}"
        rooms_by_name[loc] = Room(room_id=rid, name=loc, capacity=25, room_type=RoomType.STANDARD)
    rooms = list(rooms_by_name.values())

    # Build a map: classSourcedId → primary teacher (via enrollments)
    primary_teacher_by_class: dict[str, str] = {}
    for e in enrollments:
        if (e.get("role") or "").lower() == "teacher" and (e.get("primary") or "").lower() == "true":
            class_sid = e["classSourcedId"]
            tid_raw = e["userSourcedId"]
            tid = _strip_prefix(tid_raw, _TEACHER_PREFIX)
            primary_teacher_by_class.setdefault(class_sid, tid)

    # Sections
    sections: list[Section] = []
    for c in classes_rows:
        sid = (c.get("classCode") or _strip_prefix(c["sourcedId"], _CLASS_PREFIX)).strip()
        course_id = _strip_prefix(c.get("courseSourcedId") or "", _COURSE_PREFIX)
        loc = (c.get("location") or "").strip()
        room = rooms_by_name.get(loc) if loc else None
        teacher_id = primary_teacher_by_class.get(c["sourcedId"], "")
        sections.append(Section(
            section_id=sid, course_id=course_id, teacher_id=teacher_id,
            max_size=25, locked_room_id=(room.room_id if room else None),
        ))

    return Dataset(
        config=SchoolConfig(
            school=school_name, year=year, bell=default_rotation(),
            hard=HardConstraints(), soft=SoftConstraintWeights(),
        ),
        courses=courses, teachers=teachers, rooms=rooms, sections=sections,
        students=students_out, behavior=BehaviorMatrix(),
    )
