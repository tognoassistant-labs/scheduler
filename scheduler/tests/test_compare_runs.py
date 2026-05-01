"""Tests for scripts/compare_runs.py — markdown report generator.

The script is run as a CLI normally; tests exercise its building blocks.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow tests to import from scripts/
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO / "scripts"))

from src.scheduler.models import (
    Dataset,
    HardConstraints,
    SoftConstraintWeights,
)
from src.scheduler.persistence import DB, InputBundleRepo, RuleConfigRepo, RunRepo


@pytest.fixture
def db_with_runs(tmp_path: Path, tiny_dataset: Dataset) -> DB:
    """Create a DB with 2 fake completed runs for testing the compare logic."""
    db = DB(tmp_path / "compare.sqlite")
    bundles = InputBundleRepo(db)
    rules = RuleConfigRepo(db)
    runs = RunRepo(db)

    bid = bundles.save("test-bundle", "sample", tiny_dataset)
    cid_a = rules.save("config_a", HardConstraints(), SoftConstraintWeights())
    cid_b = rules.save(
        "config_b",
        HardConstraints(),
        SoftConstraintWeights(first_choice_electives=50),
    )

    rid_a = runs.start("run_a", bid, cid_a)
    runs.save_result(rid_a, [], [], [])
    runs.save_kpis(rid_a, [
        ("first_choice_elective_pct", "global", "all", 70.0),
        ("required_fulfillment_pct", "global", "all", 99.5),
        ("section_balance_max_dev", "global", "all", 3),
        ("fully_scheduled_pct", "global", "all", 95.0),
    ])
    runs.save_compliance(rid_a, [
        ("R_max_class_size", 50, 0, 100.0, None),
        ("R_w_first_choice_electives", 100, 30, 70.0, None),
    ])
    runs.mark_complete(rid_a, master_seconds=2.0, student_seconds=10.0, objective=-100.0)

    rid_b = runs.start("run_b", bid, cid_b)
    runs.save_result(rid_b, [], [], [])
    runs.save_kpis(rid_b, [
        ("first_choice_elective_pct", "global", "all", 85.0),
        ("required_fulfillment_pct", "global", "all", 99.5),
        ("section_balance_max_dev", "global", "all", 3),
        ("fully_scheduled_pct", "global", "all", 98.0),
    ])
    runs.save_compliance(rid_b, [
        ("R_max_class_size", 50, 0, 100.0, None),
        ("R_w_first_choice_electives", 110, 20, 85.0, None),
    ])
    runs.mark_complete(rid_b, master_seconds=2.5, student_seconds=12.0, objective=-50.0)

    return db


def test_collect_returns_metadata_kpis_compliance(db_with_runs: DB) -> None:
    from compare_runs import collect
    data = collect(db_with_runs, [1, 2])
    assert set(data.keys()) == {1, 2}
    assert data[1]["meta"].label == "run_a"
    assert data[2]["meta"].label == "run_b"
    # KPIs round-tripped
    assert ("first_choice_elective_pct", "global", "all") in data[1]["kpis"]
    assert data[1]["kpis"][("first_choice_elective_pct", "global", "all")] == 70.0
    assert data[2]["kpis"][("first_choice_elective_pct", "global", "all")] == 85.0
    # Compliance round-tripped
    assert "R_max_class_size" in data[1]["compliance"]


def test_make_report_writes_markdown(db_with_runs: DB, tmp_path: Path) -> None:
    from compare_runs import collect, make_report
    data = collect(db_with_runs, [1, 2])
    out = tmp_path / "report.md"
    make_report(data, out)
    text = out.read_text()
    # Headers present
    assert "# Comparación de 2 corridas" in text
    assert "## Metadata" in text
    assert "## KPIs globales" in text
    assert "## Cumplimiento por regla" in text
    # Both runs referenced
    assert "#1" in text and "#2" in text
    # KPI deltas — first_choice 70→85 should show +15
    assert "+15" in text or "↑ +15" in text


def test_make_report_recommends_winner(db_with_runs: DB, tmp_path: Path) -> None:
    from compare_runs import collect, make_report
    data = collect(db_with_runs, [1, 2])
    out = tmp_path / "report.md"
    make_report(data, out)
    text = out.read_text()
    # Run #2 has fully_scheduled=98, required=99.5, electivas=85, balance=3 → all pass
    # Run #1 has fully_scheduled=95 → fails
    assert "Cumplen los 4 targets" in text
    assert "🏆" in text
    assert "#2" in text  # winner is run 2


def test_make_report_handles_empty_data(tmp_path: Path) -> None:
    from compare_runs import make_report
    out = tmp_path / "empty.md"
    make_report({}, out)
    text = out.read_text()
    assert "no runs to compare" in text
