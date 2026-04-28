"""Data validation + readiness score (v2 §8.3 / §15).

Returns a 0–100 score plus a structured list of issues. Hard issues block
solving; soft issues warn but allow solving.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .models import Dataset

Severity = Literal["error", "warning", "info"]


@dataclass
class Issue:
    severity: Severity
    code: str
    message: str
    entity_id: str | None = None


@dataclass
class ReadinessReport:
    score: int  # 0..100
    issues: list[Issue] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def summary(self) -> str:
        lines = [
            f"Readiness score: {self.score}/100",
            f"Errors:   {len(self.errors)}",
            f"Warnings: {len(self.warnings)}",
        ]
        for issue in self.issues:
            tag = issue.severity.upper()
            ent = f" [{issue.entity_id}]" if issue.entity_id else ""
            lines.append(f"  {tag} {issue.code}{ent}: {issue.message}")
        return "\n".join(lines)


def validate_dataset(ds: Dataset) -> ReadinessReport:
    issues: list[Issue] = []

    course_ids = {c.course_id for c in ds.courses}
    teacher_ids = {t.teacher_id for t in ds.teachers}
    room_ids = {r.room_id for r in ds.rooms}
    student_ids = {s.student_id for s in ds.students}

    # Referential integrity — sections
    for s in ds.sections:
        if s.course_id not in course_ids:
            issues.append(Issue("error", "SECTION_BAD_COURSE", f"Section {s.section_id} refers to unknown course {s.course_id}", s.section_id))
        if s.teacher_id not in teacher_ids:
            issues.append(Issue("error", "SECTION_BAD_TEACHER", f"Section {s.section_id} refers to unknown teacher {s.teacher_id}", s.section_id))

    # Referential integrity — course requests
    for st in ds.students:
        for r in st.requested_courses:
            if r.course_id not in course_ids:
                issues.append(Issue("error", "REQ_BAD_COURSE", f"Request by {st.student_id} for unknown course {r.course_id}", st.student_id))

    # Course coverage — every requested course needs at least one section
    requested = {r.course_id for st in ds.students for r in st.requested_courses}
    sectioned = {s.course_id for s in ds.sections}
    for cid in requested - sectioned:
        issues.append(Issue("error", "COURSE_NO_SECTION", f"Course {cid} requested but has no sections", cid))

    # Course-teacher qualification consistency
    for c in ds.courses:
        if c.is_advisory:
            continue
        if not c.qualified_teacher_ids:
            issues.append(Issue("error", "COURSE_NO_TEACHER", f"Course {c.course_id} has no qualified teachers", c.course_id))
        for tid in c.qualified_teacher_ids:
            if tid not in teacher_ids:
                issues.append(Issue("error", "COURSE_BAD_TEACHER", f"Course {c.course_id} lists unknown teacher {tid}", c.course_id))

    # Section teacher must be qualified
    courses_by_id = {c.course_id: c for c in ds.courses}
    for s in ds.sections:
        c = courses_by_id.get(s.course_id)
        if c is None or c.is_advisory:
            continue
        if s.teacher_id not in c.qualified_teacher_ids:
            issues.append(Issue("error", "SECTION_TEACHER_NOT_QUALIFIED", f"Teacher {s.teacher_id} not qualified for {c.course_id} (section {s.section_id})", s.section_id))

    # Room type availability — every required room_type must have at least one room
    needed_types = {c.required_room_type for c in ds.courses if not c.is_advisory}
    available_types = {r.room_type for r in ds.rooms}
    for rt in needed_types - available_types:
        issues.append(Issue("error", "NO_ROOM_OF_TYPE", f"No room of type {rt.value} but a course requires it", str(rt.value)))

    # Capacity sanity
    for r in ds.rooms:
        if r.capacity < 1:
            issues.append(Issue("error", "ROOM_BAD_CAPACITY", f"Room {r.room_id} has capacity {r.capacity}", r.room_id))

    # Demand vs supply per course
    demand: dict[str, int] = {}
    for st in ds.students:
        for r in st.requested_courses:
            if r.rank == 1:
                demand[r.course_id] = demand.get(r.course_id, 0) + 1
    for cid, d in demand.items():
        c = courses_by_id.get(cid)
        if c is None:
            continue
        sect_count = sum(1 for s in ds.sections if s.course_id == cid)
        capacity = sect_count * c.max_size
        if capacity < d:
            issues.append(Issue("warning", "CAPACITY_SHORTFALL", f"Course {cid}: demand={d}, capacity={capacity} ({sect_count} sections × {c.max_size})", cid))

    # Teacher load check — count academic sections only (advisory is a homeroom-style
    # assignment and conventionally not part of teaching load).
    by_teacher: dict[str, int] = {}
    for s in ds.sections:
        c = courses_by_id.get(s.course_id)
        if c and c.is_advisory:
            continue
        by_teacher[s.teacher_id] = by_teacher.get(s.teacher_id, 0) + 1
    for tid, n in by_teacher.items():
        t = next((tt for tt in ds.teachers if tt.teacher_id == tid), None)
        if t is None:
            continue
        if n > t.max_load:
            issues.append(Issue("warning", "TEACHER_OVERLOAD", f"Teacher {tid} has {n} academic sections, max_load={t.max_load}", tid))

    # Behavior matrix integrity
    for a, b in ds.behavior.separations + ds.behavior.groupings:
        if a not in student_ids:
            issues.append(Issue("warning", "BEHAVIOR_BAD_STUDENT", f"Behavior pair references unknown student {a}", a))
        if b not in student_ids:
            issues.append(Issue("warning", "BEHAVIOR_BAD_STUDENT", f"Behavior pair references unknown student {b}", b))

    # Prerequisite integrity (v2 §4.3) — referential + cycle detection.
    for c in ds.courses:
        for prereq_id in c.prerequisite_course_ids:
            if prereq_id not in course_ids:
                issues.append(Issue("error", "PREREQ_BAD_COURSE",
                                    f"Course {c.course_id} has prerequisite {prereq_id} which doesn't exist",
                                    c.course_id))
    # Cycle detection (DFS)
    prereqs_map = {c.course_id: set(c.prerequisite_course_ids) for c in ds.courses}
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {cid: WHITE for cid in prereqs_map}
    cycle_courses: set[str] = set()

    def visit(cid: str, stack: list[str]) -> None:
        if color[cid] == GRAY:
            cycle_courses.update(stack[stack.index(cid):] + [cid])
            return
        if color[cid] == BLACK:
            return
        color[cid] = GRAY
        for nxt in prereqs_map.get(cid, ()):
            if nxt in prereqs_map:
                visit(nxt, stack + [cid])
        color[cid] = BLACK

    for cid in prereqs_map:
        if color[cid] == WHITE:
            visit(cid, [])
    for cid in cycle_courses:
        issues.append(Issue("error", "PREREQ_CYCLE",
                            f"Course {cid} is part of a prerequisite cycle",
                            cid))

    # Per-student prereq warnings: if student requests a course but has no concurrent
    # nor prior request for the prereq. Without transcript history this is heuristic —
    # we treat "no other request for the prereq" as a yellow flag.
    for st in ds.students:
        requested_cids = {r.course_id for r in st.requested_courses}
        for r in st.requested_courses:
            c = courses_by_id.get(r.course_id)
            if c is None:
                continue
            for prereq in c.prerequisite_course_ids:
                if prereq not in requested_cids:
                    issues.append(Issue("warning", "PREREQ_NOT_IN_REQUESTS",
                                        f"Student {st.student_id} requests {r.course_id} but no request for prereq {prereq} (transcript not checked)",
                                        st.student_id))

    # Score: errors are heavy, warnings light
    n_err = sum(1 for i in issues if i.severity == "error")
    n_warn = sum(1 for i in issues if i.severity == "warning")
    score = max(0, 100 - n_err * 15 - n_warn * 3)
    return ReadinessReport(score=score, issues=issues)


if __name__ == "__main__":
    from .sample_data import make_grade_12_dataset
    ds = make_grade_12_dataset()
    rep = validate_dataset(ds)
    print(rep.summary())
