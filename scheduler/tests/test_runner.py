"""Integration tests for runner.solve_and_persist (M1).

Validates:
- db=None path returns identical KPIs to db=DB path (persistence is
  side-effect only, never alters solver behavior).
- A persisted run has all expected rows: bundle, rule_config, run,
  run_result, run_kpi (global scope).
- solve_from_db loads bundle + rule_config and produces an equivalent run.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.scheduler.models import Dataset
from src.scheduler.persistence import DB, InputBundleRepo, RuleConfigRepo, RunRepo
from src.scheduler.runner import solve_and_persist, solve_from_db


@pytest.fixture
def db(tmp_path: Path) -> DB:
    return DB(tmp_path / "runner.sqlite")


def test_solve_without_db(tiny_dataset: Dataset) -> None:
    outcome = solve_and_persist(
        tiny_dataset, db=None, master_time=10.0, student_time=20.0
    )
    assert outcome.run_id is None
    assert outcome.bundle_id is None
    assert outcome.rule_config_id is None
    assert outcome.result.master, "master should be feasible on tiny_dataset"
    assert outcome.kpi.required_fulfillment_pct >= 0.0


def test_solve_with_db_persists_full_lineage(db: DB, tiny_dataset: Dataset) -> None:
    outcome = solve_and_persist(
        tiny_dataset,
        db=db,
        bundle_label="tiny-test",
        rule_config_label="defaults",
        run_label="m1-integration",
        master_time=10.0,
        student_time=20.0,
    )
    assert outcome.run_id is not None
    assert outcome.bundle_id is not None
    assert outcome.rule_config_id is not None

    bundles = InputBundleRepo(db)
    rules = RuleConfigRepo(db)
    runs = RunRepo(db)

    bmeta, ds = bundles.get(outcome.bundle_id)
    assert bmeta.label == "tiny-test"
    assert len(ds.students) == len(tiny_dataset.students)

    rmeta, hard, soft, _ = rules.get(outcome.rule_config_id)
    assert rmeta.label == "defaults"
    assert hard == tiny_dataset.config.hard
    assert soft == tiny_dataset.config.soft

    run = runs.get(outcome.run_id)
    assert run.status == "completed"
    assert run.master_seconds is not None
    assert run.student_seconds is not None
    assert run.app_version

    kpis = dict(((m, s, k), v) for (m, s, k, v) in runs.get_kpis(outcome.run_id))
    assert ("fully_scheduled_pct", "global", "all") in kpis
    assert ("required_fulfillment_pct", "global", "all") in kpis
    assert ("first_choice_elective_pct", "global", "all") in kpis

    master_blob, students_blob, unmet_blob = runs.get_result_blobs(outcome.run_id)
    assert master_blob and students_blob


def test_solve_from_db_reuses_persisted_inputs(db: DB, tiny_dataset: Dataset) -> None:
    bundles = InputBundleRepo(db)
    rules = RuleConfigRepo(db)
    bid = bundles.save("preloaded", "sample", tiny_dataset)
    cid = rules.save("preloaded", tiny_dataset.config.hard, tiny_dataset.config.soft)

    outcome = solve_from_db(
        db, bid, cid, run_label="from-db", master_time=10.0, student_time=20.0
    )
    assert outcome.bundle_id == bid
    assert outcome.rule_config_id == cid
    assert outcome.run_id is not None
    assert outcome.kpi.required_fulfillment_pct >= 0.0


def test_solve_from_db_applies_custom_rules(db: DB, tiny_dataset: Dataset) -> None:
    """A rule_config with a forbid_pair custom rule should add a separation
    that survives into the active dataset at solve time."""
    from src.scheduler.persistence.repo import InputBundleRepo, RuleConfigRepo
    from src.scheduler.rules.custom import CustomRuleSpec, serialize_custom_rules

    # Pick two existing students for the pair so the constraint is non-trivial.
    s_a = tiny_dataset.students[0].student_id
    s_b = tiny_dataset.students[1].student_id

    bundles = InputBundleRepo(db)
    rules = RuleConfigRepo(db)
    bid = bundles.save("custom-rules-test", "sample", tiny_dataset)

    overrides_blob = serialize_custom_rules([
        CustomRuleSpec(
            id="user_test_pair",
            kind="hard",
            label="test pair",
            solver_op="forbid_pair",
            params={"student_a": s_a, "student_b": s_b},
        ),
    ])
    cid = rules.save("with-custom", tiny_dataset.config.hard, tiny_dataset.config.soft, overrides_blob)

    outcome = solve_from_db(
        db, bid, cid, run_label="custom-rules", master_time=10.0, student_time=20.0
    )
    assert outcome.run_id is not None
    assert outcome.result.master, "solve must succeed even with the extra separation"

    # Confirm s_a and s_b never share a section in the resulting student schedules.
    student_sects = {sa.student_id: set(sa.section_ids) for sa in outcome.result.students}
    sa_set = student_sects.get(s_a, set())
    sb_set = student_sects.get(s_b, set())
    assert not (sa_set & sb_set), f"forbid_pair violated: {sa_set & sb_set}"


def test_persist_does_not_break_solver(db: DB, tiny_dataset: Dataset) -> None:
    """Persistence is a pure side-channel — both paths must produce valid runs.

    OR-Tools CP-SAT is not bit-deterministic across invocations, so we cannot
    assert KPI equality. We only assert that the persistence path doesn't
    regress — both solves succeed and produce roughly equivalent solutions.
    """
    no_db = solve_and_persist(
        tiny_dataset, db=None, master_time=10.0, student_time=20.0
    )
    with_db = solve_and_persist(
        tiny_dataset, db=db, master_time=10.0, student_time=20.0
    )
    assert no_db.master_status == with_db.master_status
    assert no_db.student_status == with_db.student_status
    assert len(no_db.result.master) == len(with_db.result.master)
    assert len(no_db.result.students) == len(with_db.result.students)
    assert abs(no_db.kpi.required_fulfillment_pct - with_db.kpi.required_fulfillment_pct) < 5.0
