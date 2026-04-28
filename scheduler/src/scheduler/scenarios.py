"""Scenario simulation (v2 §10).

A "scenario" is a Dataset modified by a small set of overrides. Run several
scenarios in one batch and produce a side-by-side KPI comparison.

Typical use:
    scenarios = [
        ScenarioSpec(name="baseline", overrides={}),
        ScenarioSpec(name="add_math_teacher", overrides={"add_teacher": ("math", "T999", "Substitute")}),
        ScenarioSpec(name="raise_cap", overrides={"max_class_size": 27}),
        ScenarioSpec(name="add_bio_section", overrides={"add_section": ("BIO", "T106")}),
    ]
    results = run_scenarios(base_dataset, scenarios)
    print(format_comparison(results))
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any

from .models import (
    Dataset,
    HardConstraints,
    Section,
    Teacher,
)
from .master_solver import solve_master
from .student_solver import solve_students
from .reports import KPIReport, compute_kpis


@dataclass
class ScenarioSpec:
    name: str
    overrides: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class ScenarioResult:
    name: str
    description: str
    overrides: dict[str, Any]
    kpi: KPIReport | None  # None if solve failed
    master_status: str
    student_status: str
    master_solve_seconds: float
    student_solve_seconds: float
    n_master_assignments: int
    n_students_placed: int
    n_unmet_rank1: int
    error: str | None = None


# Override appliers — each takes a Dataset and mutates it in place

def _apply_overrides(ds: Dataset, overrides: dict[str, Any]) -> None:
    """Mutate `ds` according to scenario overrides."""
    for key, value in overrides.items():
        if key == "max_class_size":
            ds.config.hard.max_class_size = value
            for s in ds.sections:
                if s.max_size == 25:  # only update default-sized sections
                    s.max_size = value

        elif key == "max_section_spread_per_course":
            ds.config.hard.max_section_spread_per_course = value

        elif key == "co_planning_weight":
            ds.config.soft.co_planning = value

        elif key == "first_choice_weight":
            ds.config.soft.first_choice_electives = value

        elif key == "balance_weight":
            ds.config.soft.balance_class_sizes = value

        elif key == "add_teacher":
            # value: (department, teacher_id, name)
            dept, tid, name = value
            ds.teachers.append(Teacher(
                teacher_id=tid, name=name, department=dept,
                qualified_course_ids=[], max_load=5,
            ))

        elif key == "add_section":
            # value: (course_id, teacher_id) — adds one new section to the course
            course_id, teacher_id = value
            existing = sum(1 for s in ds.sections if s.course_id == course_id)
            new_id = f"{course_id}.{existing+1}"
            course = next((c for c in ds.courses if c.course_id == course_id), None)
            if course is None:
                raise ValueError(f"Unknown course {course_id}")
            ds.sections.append(Section(
                section_id=new_id, course_id=course_id, teacher_id=teacher_id,
                max_size=course.max_size, grade_level=12,
            ))

        elif key == "remove_section":
            # value: section_id
            ds.sections = [s for s in ds.sections if s.section_id != value]

        elif key == "set_solver_mode":
            # value: "single" | "lexmin" — handled outside this fn (passed to solve_students)
            pass

        else:
            raise ValueError(f"Unknown override: {key}")


def run_scenario(
    base_dataset: Dataset,
    spec: ScenarioSpec,
    master_time: float = 30.0,
    student_time: float = 180.0,
) -> ScenarioResult:
    """Run a single scenario by deep-copying the dataset, applying overrides, solving."""
    ds = copy.deepcopy(base_dataset)
    try:
        _apply_overrides(ds, spec.overrides)
    except Exception as e:
        return ScenarioResult(
            name=spec.name, description=spec.description, overrides=spec.overrides,
            kpi=None, master_status="N/A", student_status="N/A",
            master_solve_seconds=0.0, student_solve_seconds=0.0,
            n_master_assignments=0, n_students_placed=0, n_unmet_rank1=0,
            error=f"override apply failed: {e}",
        )

    mode = spec.overrides.get("set_solver_mode", "single")

    t0 = time.time()
    master, _, m_status = solve_master(ds, time_limit_s=master_time)
    m_elapsed = time.time() - t0

    if not master:
        return ScenarioResult(
            name=spec.name, description=spec.description, overrides=spec.overrides,
            kpi=None, master_status=m_status, student_status="N/A",
            master_solve_seconds=m_elapsed, student_solve_seconds=0.0,
            n_master_assignments=0, n_students_placed=0, n_unmet_rank1=0,
            error="master solve failed",
        )

    t1 = time.time()
    students, unmet, _, s_status = solve_students(ds, master, time_limit_s=student_time, mode=mode)
    s_elapsed = time.time() - t1

    kpi = compute_kpis(ds, master, students, unmet) if students else None

    return ScenarioResult(
        name=spec.name, description=spec.description, overrides=spec.overrides,
        kpi=kpi, master_status=m_status, student_status=s_status,
        master_solve_seconds=m_elapsed, student_solve_seconds=s_elapsed,
        n_master_assignments=len(master), n_students_placed=len(students),
        n_unmet_rank1=len(unmet),
    )


def run_scenarios(
    base_dataset: Dataset,
    specs: list[ScenarioSpec],
    master_time: float = 30.0,
    student_time: float = 180.0,
    progress: bool = True,
) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    for i, spec in enumerate(specs, 1):
        if progress:
            print(f"[{i}/{len(specs)}] {spec.name}: {spec.description or '(no description)'}")
        r = run_scenario(base_dataset, spec, master_time, student_time)
        if progress:
            if r.error:
                print(f"  ERROR: {r.error}")
            elif r.kpi:
                print(f"  {r.master_status}/{r.student_status} | "
                      f"electives {r.kpi.first_choice_elective_pct:.1f}% | "
                      f"balance dev {r.kpi.section_balance_max_dev} | "
                      f"unmet {r.n_unmet_rank1} | "
                      f"{r.master_solve_seconds + r.student_solve_seconds:.1f}s")
            else:
                print(f"  {r.master_status}/{r.student_status} (no KPI computed)")
        results.append(r)
    return results


def format_comparison(results: list[ScenarioResult]) -> str:
    """Markdown side-by-side comparison of scenario KPIs."""
    if not results:
        return "(no scenarios)"

    header = "| Scenario | Description | Status | Fully Sched | Req Fulfill | First-Choice | Balance Dev | Unmet | Time (s) |"
    sep = "|" + "|".join(["---"] * 9) + "|"
    lines = [header, sep]

    for r in results:
        if r.error:
            lines.append(f"| {r.name} | {r.description} | ERROR | — | — | — | — | — | — |")
            continue
        if r.kpi is None:
            lines.append(f"| {r.name} | {r.description} | {r.master_status}/{r.student_status} | — | — | — | — | — | "
                         f"{r.master_solve_seconds + r.student_solve_seconds:.1f} |")
            continue
        kpi = r.kpi
        lines.append(
            f"| {r.name} | {r.description} | {r.master_status}/{r.student_status} | "
            f"{kpi.fully_scheduled_pct:.1f}% | {kpi.required_fulfillment_pct:.1f}% | "
            f"{kpi.first_choice_elective_pct:.1f}% | {kpi.section_balance_max_dev} | "
            f"{r.n_unmet_rank1} | {r.master_solve_seconds + r.student_solve_seconds:.1f} |"
        )
    return "\n".join(lines)


# Golden-snapshot regression -------------------------------------------------

# Tolerances for golden snapshot comparison. Multi-worker CP-SAT is not
# bit-deterministic across runs, so KPIs can drift by a small amount even on
# identical inputs. The tolerances catch real regressions while ignoring noise.
_ELECTIVE_PCT_TOL = 3.0    # rank-1 elective rate may drop by up to 3 points
_PCT_DRIFT_TOL = 0.5       # all-100% KPIs treated as exact (allow rounding)
_UNMET_TOL = 3             # rank-1 unmet may grow by up to 3 students
_BALANCE_DEV_TOL = 1       # max-dev may drift by ±1 due to multi-worker noise
_OK_STATUSES = ("OPTIMAL", "FEASIBLE")


def to_snapshot_dict(r: ScenarioResult) -> dict[str, Any]:
    """Reproducible snapshot of a scenario result for golden-file regression.

    Excludes solve times (variable across machines and runs).
    """
    snap: dict[str, Any] = {
        "name": r.name,
        "master_status": r.master_status,
        "student_status": r.student_status,
        "n_master_assignments": r.n_master_assignments,
        "n_students_placed": r.n_students_placed,
        "n_unmet_rank1": r.n_unmet_rank1,
        "error": r.error,
    }
    if r.kpi is None:
        snap["kpi"] = None
    else:
        snap["kpi"] = {
            "fully_scheduled_pct": r.kpi.fully_scheduled_pct,
            "required_fulfillment_pct": r.kpi.required_fulfillment_pct,
            "first_choice_elective_pct": r.kpi.first_choice_elective_pct,
            "section_balance_max_dev": r.kpi.section_balance_max_dev,
            "teacher_load_max_dev": r.kpi.teacher_load_max_dev,
            "unscheduled_students": r.kpi.unscheduled_students,
            "unmet_requests": r.kpi.unmet_requests,
        }
    return snap


def compare_to_golden(actual: dict[str, Any], golden: dict[str, Any]) -> list[str]:
    """Return list of regression violations (empty list = within tolerance)."""
    name = golden.get("name", "?")
    v: list[str] = []

    if (golden.get("error") or None) != (actual.get("error") or None):
        v.append(f"{name}: error changed: golden={golden.get('error')!r} actual={actual.get('error')!r}")

    if golden["master_status"] in _OK_STATUSES and actual["master_status"] not in _OK_STATUSES:
        v.append(f"{name}: master_status regressed: {golden['master_status']} -> {actual['master_status']}")
    if golden["student_status"] in _OK_STATUSES and actual["student_status"] not in _OK_STATUSES:
        v.append(f"{name}: student_status regressed: {golden['student_status']} -> {actual['student_status']}")

    if actual["n_master_assignments"] != golden["n_master_assignments"]:
        v.append(f"{name}: n_master_assignments: golden={golden['n_master_assignments']} actual={actual['n_master_assignments']}")
    if actual["n_students_placed"] != golden["n_students_placed"]:
        v.append(f"{name}: n_students_placed: golden={golden['n_students_placed']} actual={actual['n_students_placed']}")

    if actual["n_unmet_rank1"] > golden["n_unmet_rank1"] + _UNMET_TOL:
        v.append(f"{name}: n_unmet_rank1 regressed: golden={golden['n_unmet_rank1']} actual={actual['n_unmet_rank1']} (tol +{_UNMET_TOL})")

    gk, ak = golden.get("kpi"), actual.get("kpi")
    if gk and ak:
        if ak["first_choice_elective_pct"] < gk["first_choice_elective_pct"] - _ELECTIVE_PCT_TOL:
            v.append(f"{name}: first_choice_elective_pct regressed: golden={gk['first_choice_elective_pct']:.1f}% actual={ak['first_choice_elective_pct']:.1f}% (tol -{_ELECTIVE_PCT_TOL})")
        if ak["section_balance_max_dev"] > gk["section_balance_max_dev"] + _BALANCE_DEV_TOL:
            v.append(f"{name}: section_balance_max_dev regressed: golden={gk['section_balance_max_dev']} actual={ak['section_balance_max_dev']} (tol +{_BALANCE_DEV_TOL})")
        for fld in ("fully_scheduled_pct", "required_fulfillment_pct"):
            if abs(ak[fld] - gk[fld]) > _PCT_DRIFT_TOL:
                v.append(f"{name}: {fld} drifted: golden={gk[fld]:.1f}% actual={ak[fld]:.1f}% (tol +/-{_PCT_DRIFT_TOL})")
    elif (gk is None) != (ak is None):
        v.append(f"{name}: kpi presence changed: golden_has_kpi={gk is not None} actual_has_kpi={ak is not None}")

    return v


# Built-in scenario presets ---------------------------------------------------

PRESETS: dict[str, list[ScenarioSpec]] = {
    "default": [
        ScenarioSpec(name="baseline", description="As-is dataset"),
        ScenarioSpec(name="cap_27", description="Raise max class size to 27",
                     overrides={"max_class_size": 27}),
        ScenarioSpec(name="loose_balance", description="Allow per-course spread up to 8",
                     overrides={"max_section_spread_per_course": 8}),
        ScenarioSpec(name="tight_balance", description="Force per-course spread to 3",
                     overrides={"max_section_spread_per_course": 3}),
        ScenarioSpec(name="electives_priority", description="Heavily favor first-choice electives",
                     overrides={"first_choice_weight": 40, "balance_weight": 4}),
        ScenarioSpec(name="lexmin_mode", description="Use lex-min solver mode",
                     overrides={"set_solver_mode": "lexmin"}),
    ],
}
