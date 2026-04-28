"""CSV ingest and export for the scheduling engine.

Format aligned to v2 §7 / §9 — minimum-viable CSVs that can round-trip
data into and out of the engine. PowerSchool-specific export lives in
exporter.py.
"""
from __future__ import annotations

import csv
from pathlib import Path

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


def _bool(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def _list(v: str) -> list[str]:
    return [p.strip() for p in v.split("|") if p.strip()]


def write_dataset(ds: Dataset, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    with (out_dir / "courses.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "course_id", "name", "department", "is_required", "credits",
            "meetings_per_week", "max_size", "min_size", "required_room_type",
            "qualified_teacher_ids", "is_lab", "is_advisory", "term",
            "prerequisite_course_ids",
        ])
        for c in ds.courses:
            w.writerow([
                c.course_id, c.name, c.department, c.is_required, c.credits,
                c.meetings_per_week, c.max_size, c.min_size, c.required_room_type.value,
                "|".join(c.qualified_teacher_ids), c.is_lab, c.is_advisory, c.term.value,
                "|".join(c.prerequisite_course_ids),
            ])

    with (out_dir / "teachers.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["teacher_id", "name", "department", "qualified_course_ids", "max_load",
                    "min_prep_periods", "preferred_course_ids", "avoid_course_ids",
                    "preferred_blocks", "avoid_blocks"])
        for t in ds.teachers:
            w.writerow([t.teacher_id, t.name, t.department, "|".join(t.qualified_course_ids),
                        t.max_load, t.min_prep_periods,
                        "|".join(t.preferred_course_ids),
                        "|".join(t.avoid_course_ids),
                        "|".join(str(b) for b in t.preferred_blocks),
                        "|".join(str(b) for b in t.avoid_blocks)])

    with (out_dir / "rooms.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["room_id", "name", "capacity", "room_type", "department"])
        for r in ds.rooms:
            w.writerow([r.room_id, r.name, r.capacity, r.room_type.value, r.department or ""])

    with (out_dir / "sections.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section_id", "course_id", "teacher_id", "room_id", "max_size", "grade_level",
                    "locked_scheme", "locked_room_id"])
        for s in ds.sections:
            w.writerow([s.section_id, s.course_id, s.teacher_id, s.room_id or "",
                        s.max_size, s.grade_level,
                        "" if s.locked_scheme is None else str(s.locked_scheme),
                        s.locked_room_id or ""])

    with (out_dir / "students.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["student_id", "name", "grade", "counselor_id", "restricted_teacher_ids"])
        for s in ds.students:
            w.writerow([s.student_id, s.name, s.grade, s.counselor_id or "", "|".join(s.restricted_teacher_ids)])

    with (out_dir / "course_requests.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["student_id", "course_id", "is_required", "rank"])
        for s in ds.students:
            for r in s.requested_courses:
                w.writerow([r.student_id, r.course_id, r.is_required, r.rank])

    with (out_dir / "behavior.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "student_a", "student_b"])
        for a, b in ds.behavior.separations:
            w.writerow(["separation", a, b])
        for a, b in ds.behavior.groupings:
            w.writerow(["grouping", a, b])

    with (out_dir / "rotation.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["day", "block", "scheme"])
        for cell in ds.config.bell.rotation:
            w.writerow([cell.day, cell.block, cell.scheme])


def read_dataset(in_dir: Path, school: str = "Columbus High School", grade: int = 12, year: str = "2026-2027") -> Dataset:
    in_dir = Path(in_dir)

    courses: list[Course] = []
    with (in_dir / "courses.csv").open() as f:
        for row in csv.DictReader(f):
            courses.append(Course(
                course_id=row["course_id"],
                name=row["name"],
                department=row["department"],
                is_required=_bool(row["is_required"]),
                credits=float(row["credits"]),
                meetings_per_week=int(row["meetings_per_week"]),
                max_size=int(row["max_size"]),
                min_size=int(row["min_size"]),
                required_room_type=RoomType(row["required_room_type"]),
                qualified_teacher_ids=_list(row["qualified_teacher_ids"]),
                is_lab=_bool(row["is_lab"]),
                is_advisory=_bool(row["is_advisory"]),
                prerequisite_course_ids=_list(row.get("prerequisite_course_ids", "")),
            ))

    teachers: list[Teacher] = []
    with (in_dir / "teachers.csv").open() as f:
        for row in csv.DictReader(f):
            def _int_list(s: str) -> list[int]:
                return [int(p) for p in s.split("|") if p.strip().isdigit()] if s else []
            teachers.append(Teacher(
                teacher_id=row["teacher_id"],
                name=row["name"],
                department=row["department"],
                qualified_course_ids=_list(row["qualified_course_ids"]),
                max_load=int(row["max_load"]),
                min_prep_periods=int(row["min_prep_periods"]),
                preferred_course_ids=_list(row.get("preferred_course_ids", "")),
                avoid_course_ids=_list(row.get("avoid_course_ids", "")),
                preferred_blocks=_int_list(row.get("preferred_blocks", "")),
                avoid_blocks=_int_list(row.get("avoid_blocks", "")),
            ))

    rooms: list[Room] = []
    with (in_dir / "rooms.csv").open() as f:
        for row in csv.DictReader(f):
            rooms.append(Room(
                room_id=row["room_id"],
                name=row["name"],
                capacity=int(row["capacity"]),
                room_type=RoomType(row["room_type"]),
                department=row["department"] or None,
            ))

    sections: list[Section] = []
    with (in_dir / "sections.csv").open() as f:
        for row in csv.DictReader(f):
            ls = row.get("locked_scheme", "")
            locked_scheme: int | str | None
            if not ls:
                locked_scheme = None
            elif ls == "ADVISORY":
                locked_scheme = "ADVISORY"
            else:
                try:
                    locked_scheme = int(ls)
                except ValueError:
                    locked_scheme = None
            sections.append(Section(
                section_id=row["section_id"],
                course_id=row["course_id"],
                teacher_id=row["teacher_id"],
                room_id=row["room_id"] or None,
                max_size=int(row["max_size"]),
                grade_level=int(row["grade_level"]),
                locked_scheme=locked_scheme,
                locked_room_id=row.get("locked_room_id") or None,
            ))

    students_raw: dict[str, Student] = {}
    with (in_dir / "students.csv").open() as f:
        for row in csv.DictReader(f):
            students_raw[row["student_id"]] = Student(
                student_id=row["student_id"],
                name=row["name"],
                grade=int(row["grade"]),
                counselor_id=row["counselor_id"] or None,
                restricted_teacher_ids=_list(row["restricted_teacher_ids"]),
                requested_courses=[],
            )

    with (in_dir / "course_requests.csv").open() as f:
        for row in csv.DictReader(f):
            sid = row["student_id"]
            if sid not in students_raw:
                continue
            students_raw[sid].requested_courses.append(CourseRequest(
                student_id=sid,
                course_id=row["course_id"],
                is_required=_bool(row["is_required"]),
                rank=int(row["rank"]),
            ))

    seps: list[tuple[str, str]] = []
    grps: list[tuple[str, str]] = []
    behavior_path = in_dir / "behavior.csv"
    if behavior_path.exists():
        with behavior_path.open() as f:
            for row in csv.DictReader(f):
                pair = (row["student_a"], row["student_b"])
                if row["kind"] == "separation":
                    seps.append(pair)
                elif row["kind"] == "grouping":
                    grps.append(pair)

    rotation_path = in_dir / "rotation.csv"
    bell: BellSchedule
    if rotation_path.exists():
        from .models import RotationCell
        cells: list[RotationCell] = []
        with rotation_path.open() as f:
            for row in csv.DictReader(f):
                scheme_val: int | str = row["scheme"]
                if scheme_val != "ADVISORY":
                    scheme_val = int(scheme_val)
                cells.append(RotationCell(day=row["day"], block=int(row["block"]), scheme=scheme_val))
        bell = BellSchedule(rotation=cells)
    else:
        bell = default_rotation()

    config = SchoolConfig(
        school=school, grade=grade, year=year,
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
        students=list(students_raw.values()),
        behavior=BehaviorMatrix(separations=seps, groupings=grps),
    )
