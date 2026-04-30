"""Solve orchestrator with optional persistence.

The single seam between (UI / CLI) and the solver pipeline. Both `app.py`
and `cli.py` go through here so that persistence semantics — bundle save,
rule_config save, run lifecycle, KPI denormalization — live in exactly one
place.

A run that hits a SQLite-backed `DB` becomes browseable, comparable, and
re-exportable from history. A run with `db=None` keeps the legacy
in-memory behavior.

Per-rule compliance is computed in M4. M1 only persists the global KPIs
already produced by `reports.compute_kpis`, so the run row is fully
populated and `run_kpi` (scope='global') is queryable from day one.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Literal

from .master_solver import solve_master
from .models import (
    Dataset,
    HardConstraints,
    ScheduleResult,
    SoftConstraintWeights,
)
from .persistence import DB, InputBundleRepo, RuleConfigRepo, RunRepo
from .reports import KPIReport, compute_kpis
from .rules.compliance import compute_compliance, to_db_rows
from .student_solver import solve_students

APP_VERSION = "v4.27-dev"


@dataclass
class RunOutcome:
    """Everything a caller needs after a solve, persisted or not."""

    result: ScheduleResult
    kpi: KPIReport
    master_status: str
    student_status: str
    run_id: int | None  # None when db is None
    bundle_id: int | None
    rule_config_id: int | None


def _git_sha() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or None
    except Exception:
        return None


def _global_kpi_rows(kpi: KPIReport) -> list[tuple[str, str, str, float]]:
    """Flatten KPIReport into (metric, scope, key, value) rows for run_kpi."""
    rows: list[tuple[str, str, str, float]] = [
        ("fully_scheduled_pct", "global", "all", float(kpi.fully_scheduled_pct)),
        ("required_fulfillment_pct", "global", "all", float(kpi.required_fulfillment_pct)),
        ("first_choice_elective_pct", "global", "all", float(kpi.first_choice_elective_pct)),
        ("section_balance_max_dev", "global", "all", float(kpi.section_balance_max_dev)),
        ("teacher_load_max_dev", "global", "all", float(kpi.teacher_load_max_dev)),
        ("unscheduled_students", "global", "all", float(kpi.unscheduled_students)),
        ("unmet_requests", "global", "all", float(kpi.unmet_requests)),
    ]
    for target, met in kpi.targets_met.items():
        rows.append(("target_met", "global", target, 1.0 if met else 0.0))
    return rows


def solve_and_persist(
    dataset: Dataset,
    *,
    db: DB | None = None,
    bundle_id: int | None = None,
    rule_config_id: int | None = None,
    run_label: str = "",
    bundle_label: str = "ad-hoc",
    bundle_source_kind: str = "csv",
    rule_config_label: str = "default",
    master_time: float = 60.0,
    student_time: float = 240.0,
    mode: Literal["single", "lexmin"] = "single",
    verbose: bool = False,
) -> RunOutcome:
    """Run master + student solver, optionally persisting everything to SQLite.

    When `db` is provided:
      - If `bundle_id` is None, the dataset is saved as a new bundle.
      - If `rule_config_id` is None, `dataset.config.hard/soft` are saved as
        a new rule_config.
      - A run row is started, results + global KPIs are persisted, and the
        run is marked completed/failed/infeasible.
    """
    bundle_repo = InputBundleRepo(db) if db else None
    rule_repo = RuleConfigRepo(db) if db else None
    run_repo = RunRepo(db) if db else None

    if db and bundle_repo and bundle_id is None:
        bundle_id = bundle_repo.save(bundle_label, bundle_source_kind, dataset)

    if db and rule_repo and rule_config_id is None:
        rule_config_id = rule_repo.save(
            rule_config_label,
            dataset.config.hard,
            dataset.config.soft,
        )

    run_id: int | None = None
    if db and run_repo and bundle_id is not None and rule_config_id is not None:
        run_id = run_repo.start(
            run_label or f"run-{bundle_id}",
            bundle_id,
            rule_config_id,
            git_sha=_git_sha(),
            app_version=APP_VERSION,
        )

    try:
        master, master_solver, m_status = solve_master(
            dataset, time_limit_s=master_time, verbose=verbose
        )
        master_seconds = float(master_solver.WallTime() if master else 0.0)

        if not master:
            if run_id is not None and run_repo is not None:
                run_repo.mark_failed(
                    run_id,
                    f"master infeasible: status={m_status}",
                    status="infeasible",
                )
            empty_result = ScheduleResult(
                master=[],
                students=[],
                unscheduled_requests=[],
                objective_value=0.0,
                solve_seconds=master_seconds,
            )
            empty_kpi = compute_kpis(dataset, [], [], [])
            return RunOutcome(
                result=empty_result,
                kpi=empty_kpi,
                master_status=m_status,
                student_status="not_run",
                run_id=run_id,
                bundle_id=bundle_id,
                rule_config_id=rule_config_id,
            )

        students, unmet, student_solver_obj, s_status = solve_students(
            dataset, master, time_limit_s=student_time, mode=mode, verbose=verbose
        )
        student_seconds = float(student_solver_obj.WallTime() if students else 0.0)

        try:
            objective = float(master_solver.ObjectiveValue())
        except Exception:
            objective = 0.0

        result = ScheduleResult(
            master=master,
            students=students,
            unscheduled_requests=unmet,
            objective_value=objective,
            solve_seconds=master_seconds + student_seconds,
        )
        kpi = compute_kpis(dataset, master, students, unmet)

        if run_id is not None and run_repo is not None:
            run_repo.save_result(run_id, master, students, unmet)
            run_repo.save_kpis(run_id, _global_kpi_rows(kpi))
            compliances = compute_compliance(dataset, master, students, unmet)
            if compliances:
                run_repo.save_compliance(run_id, to_db_rows(compliances))
            run_repo.mark_complete(
                run_id,
                master_seconds=master_seconds,
                student_seconds=student_seconds,
                objective=objective,
            )

        return RunOutcome(
            result=result,
            kpi=kpi,
            master_status=m_status,
            student_status=s_status,
            run_id=run_id,
            bundle_id=bundle_id,
            rule_config_id=rule_config_id,
        )
    except Exception as exc:
        if run_id is not None and run_repo is not None:
            run_repo.mark_failed(run_id, f"{type(exc).__name__}: {exc}")
        raise


def solve_from_db(
    db: DB,
    bundle_id: int,
    rule_config_id: int,
    *,
    run_label: str = "",
    master_time: float = 60.0,
    student_time: float = 240.0,
    mode: Literal["single", "lexmin"] = "single",
    verbose: bool = False,
) -> RunOutcome:
    """Convenience: load bundle + rule_config from DB, apply config to dataset, run.

    The rule_config's hard/soft override whatever is in the bundle's
    saved `dataset.config` — this is the whole point of having separate
    bundle and rule_config tables.
    """
    bundle_repo = InputBundleRepo(db)
    rule_repo = RuleConfigRepo(db)
    _, dataset = bundle_repo.get(bundle_id)
    _, hard, soft, _ = rule_repo.get(rule_config_id)
    dataset = _apply_rule_config(dataset, hard, soft)
    return solve_and_persist(
        dataset,
        db=db,
        bundle_id=bundle_id,
        rule_config_id=rule_config_id,
        run_label=run_label,
        master_time=master_time,
        student_time=student_time,
        mode=mode,
        verbose=verbose,
    )


def _apply_rule_config(
    dataset: Dataset, hard: HardConstraints, soft: SoftConstraintWeights
) -> Dataset:
    """Return a Dataset whose config carries the supplied hard/soft.

    Pydantic models are immutable-by-convention — we model_copy with the
    config replaced rather than mutating in place.
    """
    new_config = dataset.config.model_copy(update={"hard": hard, "soft": soft})
    return dataset.model_copy(update={"config": new_config})
