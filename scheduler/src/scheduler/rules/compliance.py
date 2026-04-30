"""Per-rule post-solve compliance.

Each builtin rule that is meaningfully verifiable from `(Dataset, master,
students, unmet)` has a checker here. The output feeds the
`rule_compliance` table and the Compliance tab in the UI.

Design:
- One function per rule, named `_check_<rule_id>`. They return a
  RuleCompliance row and never raise.
- `compute_compliance` dispatches by rule_id and skips rules with no
  checker (kept N/A — visible in the UI as "no measurement available").
- For HARD rules we report (satisfied, violated). For SOFT rules we report
  achievement counts (e.g. rank-1 electives met / requested) — same shape
  so the UI can render uniformly.
- `sample_violations` is capped at SAMPLE_LIMIT to keep blob size bounded.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Callable

from ..models import (
    Course,
    Dataset,
    MasterAssignment,
    Section,
    StudentAssignment,
)
from .registry import RULE_REGISTRY, RuleCompliance

SAMPLE_LIMIT = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_ap_research(course: Course) -> bool:
    return "ap research" in course.name.lower() or course.course_id.upper().startswith("APR")


def _enrollment_by_section(students: list[StudentAssignment]) -> dict[str, int]:
    enr: dict[str, int] = defaultdict(int)
    for sa in students:
        for sid in sa.section_ids:
            enr[sid] += 1
    return enr


def _student_section_map(students: list[StudentAssignment]) -> dict[str, set[str]]:
    return {sa.student_id: set(sa.section_ids) for sa in students}


def _make(rule_id: str, satisfied: int, violated: int, samples: list[Any]) -> RuleCompliance:
    total = satisfied + violated
    pct = 100.0 if total == 0 else 100.0 * satisfied / total
    return RuleCompliance(
        rule_id=rule_id,
        satisfied=satisfied,
        violated=violated,
        pct=pct,
        sample_violations=samples[:SAMPLE_LIMIT],
    )


# ---------------------------------------------------------------------------
# HARD rules
# ---------------------------------------------------------------------------


def _check_max_class_size(
    ds: Dataset, master: list[MasterAssignment], students: list[StudentAssignment], unmet: list[tuple[str, str]]
) -> RuleCompliance:
    enr = _enrollment_by_section(students)
    courses_by_id = {c.course_id: c for c in ds.courses}
    cap = ds.config.hard.max_class_size
    ap_cap = ds.config.hard.ap_research_max_size
    sat = vio = 0
    samples: list[dict[str, Any]] = []
    for s in ds.sections:
        course = courses_by_id.get(s.course_id)
        section_cap = ap_cap if course and _is_ap_research(course) else cap
        # Honor section-level overrides too (some sections have larger max_size).
        section_cap = max(section_cap, s.max_size)
        size = enr.get(s.section_id, 0)
        if size <= section_cap:
            sat += 1
        else:
            vio += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append({
                    "section_id": s.section_id,
                    "course_id": s.course_id,
                    "enrollment": size,
                    "cap": section_cap,
                })
    return _make("R_max_class_size", sat, vio, samples)


def _check_separations(
    ds: Dataset, master: list[MasterAssignment], students: list[StudentAssignment], unmet: list[tuple[str, str]]
) -> RuleCompliance:
    student_sects = _student_section_map(students)
    sat = vio = 0
    samples: list[dict[str, Any]] = []
    for a, b in ds.behavior.separations:
        sa = student_sects.get(a, set())
        sb = student_sects.get(b, set())
        shared = sa & sb
        if not shared:
            sat += 1
        else:
            vio += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append({"student_a": a, "student_b": b, "shared_sections": sorted(shared)})
    return _make("R_enforce_separations", sat, vio, samples)


def _check_restricted_teachers(
    ds: Dataset, master: list[MasterAssignment], students: list[StudentAssignment], unmet: list[tuple[str, str]]
) -> RuleCompliance:
    sections_by_id = {s.section_id: s for s in ds.sections}
    students_by_id = {s.student_id: s for s in ds.students}
    sat = vio = 0
    samples: list[dict[str, Any]] = []
    for sa in students:
        student = students_by_id.get(sa.student_id)
        if student is None or not student.restricted_teacher_ids:
            continue
        restricted = set(student.restricted_teacher_ids)
        for sid in sa.section_ids:
            sect = sections_by_id.get(sid)
            if sect is None:
                continue
            if sect.teacher_id in restricted:
                vio += 1
                if len(samples) < SAMPLE_LIMIT:
                    samples.append({
                        "student_id": sa.student_id,
                        "section_id": sid,
                        "teacher_id": sect.teacher_id,
                    })
            else:
                sat += 1
    return _make("R_enforce_restricted_teachers", sat, vio, samples)


def _check_max_section_spread(
    ds: Dataset, master: list[MasterAssignment], students: list[StudentAssignment], unmet: list[tuple[str, str]]
) -> RuleCompliance:
    enr = _enrollment_by_section(students)
    sections_by_course: dict[str, list[Section]] = defaultdict(list)
    for s in ds.sections:
        sections_by_course[s.course_id].append(s)
    cap = ds.config.hard.max_section_spread_per_course
    min_sections = ds.config.hard.min_sections_for_balance
    sat = vio = 0
    samples: list[dict[str, Any]] = []
    for cid, sect_list in sections_by_course.items():
        if len(sect_list) < min_sections:
            continue
        sizes = [enr.get(s.section_id, 0) for s in sect_list]
        spread = max(sizes) - min(sizes)
        if spread <= cap:
            sat += 1
        else:
            vio += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append({
                    "course_id": cid,
                    "min": min(sizes),
                    "max": max(sizes),
                    "spread": spread,
                    "cap": cap,
                })
    return _make("R_max_section_spread_per_course", sat, vio, samples)


def _check_max_consecutive(
    ds: Dataset, master: list[MasterAssignment], students: list[StudentAssignment], unmet: list[tuple[str, str]]
) -> RuleCompliance:
    """Per-day per-teacher: count longest consecutive run of teaching blocks."""
    sections_by_id = {s.section_id: s for s in ds.sections}
    teacher_day_blocks: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for m in master:
        sect = sections_by_id.get(m.section_id)
        if sect is None:
            continue
        for day, block in m.slots:
            teacher_day_blocks[sect.teacher_id][day].add(block)

    sat = vio = 0
    samples: list[dict[str, Any]] = []
    for tid, day_map in teacher_day_blocks.items():
        for day, blocks in day_map.items():
            sorted_blocks = sorted(blocks)
            run = 1
            longest = 1
            for i in range(1, len(sorted_blocks)):
                if sorted_blocks[i] == sorted_blocks[i - 1] + 1:
                    run += 1
                    longest = max(longest, run)
                else:
                    run = 1
            cap_t = ds.teacher_by_id(tid).max_consecutive_classes if tid in {t.teacher_id for t in ds.teachers} else None
            cap = cap_t if cap_t is not None else ds.config.hard.max_consecutive_classes
            if longest <= cap:
                sat += 1
            else:
                vio += 1
                if len(samples) < SAMPLE_LIMIT:
                    samples.append({
                        "teacher_id": tid,
                        "day": day,
                        "longest_run": longest,
                        "cap": cap,
                    })
    return _make("R_max_consecutive_classes", sat, vio, samples)


def _check_coplanning(
    ds: Dataset, master: list[MasterAssignment], students: list[StudentAssignment], unmet: list[tuple[str, str]]
) -> RuleCompliance:
    if not ds.coplanning_groups:
        return _make("R_enforce_coplanning_groups", 0, 0, [])
    sections_by_id = {s.section_id: s for s in ds.sections}
    teacher_schemes: dict[str, set[Any]] = defaultdict(set)
    for m in master:
        sect = sections_by_id.get(m.section_id)
        if sect is None:
            continue
        teacher_schemes[sect.teacher_id].add(m.scheme)
    all_schemes = set(range(1, 9))
    sat = vio = 0
    samples: list[dict[str, Any]] = []
    for group in ds.coplanning_groups:
        free_per_member = []
        for tid in group:
            free_per_member.append(all_schemes - teacher_schemes.get(tid, set()))
        if not free_per_member:
            continue
        common_free = set.intersection(*free_per_member)
        if common_free:
            sat += 1
        else:
            vio += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append({"group": group})
    return _make("R_enforce_coplanning_groups", sat, vio, samples)


# ---------------------------------------------------------------------------
# SOFT achievement metrics — same shape, "satisfied" means request met
# ---------------------------------------------------------------------------


def _check_first_choice_electives(
    ds: Dataset, master: list[MasterAssignment], students: list[StudentAssignment], unmet: list[tuple[str, str]]
) -> RuleCompliance:
    sections_by_id = {s.section_id: s for s in ds.sections}
    granted_by_student: dict[str, set[str]] = {
        sa.student_id: {sections_by_id[sid].course_id for sid in sa.section_ids if sid in sections_by_id}
        for sa in students
    }
    sat = vio = 0
    samples: list[dict[str, Any]] = []
    for st in ds.students:
        granted = granted_by_student.get(st.student_id, set())
        for r in st.requested_courses:
            if r.is_required or r.rank != 1:
                continue
            if r.course_id in granted:
                sat += 1
            else:
                vio += 1
                if len(samples) < SAMPLE_LIMIT:
                    samples.append({"student_id": st.student_id, "course_id": r.course_id})
    return _make("R_w_first_choice_electives", sat, vio, samples)


def _check_grouping_codes(
    ds: Dataset, master: list[MasterAssignment], students: list[StudentAssignment], unmet: list[tuple[str, str]]
) -> RuleCompliance:
    student_sects = _student_section_map(students)
    sat = vio = 0
    samples: list[dict[str, Any]] = []
    for a, b in ds.behavior.groupings:
        sa = student_sects.get(a, set())
        sb = student_sects.get(b, set())
        if sa & sb:
            sat += 1
        else:
            vio += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append({"student_a": a, "student_b": b})
    return _make("R_w_grouping_codes", sat, vio, samples)


def _check_teacher_preferred_courses(
    ds: Dataset, master: list[MasterAssignment], students: list[StudentAssignment], unmet: list[tuple[str, str]]
) -> RuleCompliance:
    teachers_by_id = {t.teacher_id: t for t in ds.teachers}
    sat = vio = 0
    samples: list[dict[str, Any]] = []
    for s in ds.sections:
        teacher = teachers_by_id.get(s.teacher_id)
        if teacher is None or not teacher.preferred_course_ids:
            continue
        if s.course_id in teacher.preferred_course_ids:
            sat += 1
        elif s.course_id in (teacher.avoid_course_ids or []):
            vio += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append({
                    "teacher_id": teacher.teacher_id,
                    "course_id": s.course_id,
                    "section_id": s.section_id,
                    "kind": "avoid",
                })
        else:
            # Neutral assignment — count as not-preferred-but-not-avoided.
            vio += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append({
                    "teacher_id": teacher.teacher_id,
                    "course_id": s.course_id,
                    "section_id": s.section_id,
                    "kind": "neutral",
                })
    return _make("R_w_teacher_preferred_courses", sat, vio, samples)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


CheckFn = Callable[
    [Dataset, list[MasterAssignment], list[StudentAssignment], list[tuple[str, str]]],
    RuleCompliance,
]

CHECKERS: dict[str, CheckFn] = {
    "R_max_class_size": _check_max_class_size,
    "R_enforce_separations": _check_separations,
    "R_enforce_restricted_teachers": _check_restricted_teachers,
    "R_max_section_spread_per_course": _check_max_section_spread,
    "R_max_consecutive_classes": _check_max_consecutive,
    "R_enforce_coplanning_groups": _check_coplanning,
    "R_w_first_choice_electives": _check_first_choice_electives,
    "R_w_grouping_codes": _check_grouping_codes,
    "R_w_teacher_preferred_courses": _check_teacher_preferred_courses,
}


def compute_compliance(
    ds: Dataset,
    master: list[MasterAssignment],
    students: list[StudentAssignment],
    unmet: list[tuple[str, str]],
) -> list[RuleCompliance]:
    """Run all available checkers and return their results.

    Rules without a checker are skipped — their absence in the output
    means "not measured" rather than "satisfied", and the UI shows N/A.
    """
    out: list[RuleCompliance] = []
    for rule_id, fn in CHECKERS.items():
        if rule_id not in RULE_REGISTRY:
            continue
        try:
            out.append(fn(ds, master, students, unmet))
        except Exception as exc:  # checker bugs must not kill the run
            out.append(
                RuleCompliance(
                    rule_id=rule_id,
                    satisfied=0,
                    violated=0,
                    pct=0.0,
                    sample_violations=[{"_error": f"{type(exc).__name__}: {exc}"}],
                )
            )
    return out


def serialize_samples(samples: list[Any]) -> bytes:
    return json.dumps(samples, sort_keys=True, separators=(",", ":")).encode("utf-8")


def to_db_rows(
    compliances: list[RuleCompliance],
) -> list[tuple[str, int, int, float, bytes | None]]:
    """Transform RuleCompliance list into rows suitable for RunRepo.save_compliance."""
    rows: list[tuple[str, int, int, float, bytes | None]] = []
    for c in compliances:
        sample_blob = serialize_samples(c.sample_violations) if c.sample_violations else None
        rows.append((c.rule_id, c.satisfied, c.violated, c.pct, sample_blob))
    return rows
