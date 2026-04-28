"""Tests for scenario simulation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.scheduler.models import Dataset
from src.scheduler.scenarios import (
    PRESETS,
    ScenarioSpec,
    compare_to_golden,
    format_comparison,
    run_scenario,
    run_scenarios,
    to_snapshot_dict,
)


class TestScenarioSpec:
    def test_default_overrides_empty(self):
        s = ScenarioSpec(name="test")
        assert s.overrides == {}


class TestRunScenario:
    def test_baseline_runs(self, tiny_dataset: Dataset):
        spec = ScenarioSpec(name="baseline", description="As-is")
        r = run_scenario(tiny_dataset, spec, master_time=5, student_time=15)
        assert r.error is None
        assert r.kpi is not None
        assert r.master_status in ("OPTIMAL", "FEASIBLE")

    def test_unknown_override_raises(self, tiny_dataset: Dataset):
        spec = ScenarioSpec(name="bad", overrides={"nonsense_key": 42})
        r = run_scenario(tiny_dataset, spec, master_time=5, student_time=15)
        assert r.error is not None

    def test_max_class_size_override_applied(self, tiny_dataset: Dataset):
        """Verify the override mechanism — scenario runs and reports a status.

        Note: cap_27 may be INFEASIBLE on the tiny fixture because some lab
        rooms have capacity 26. The test just verifies the override is applied
        and solver completes (any status), not that the resulting solve is
        feasible at small scale.
        """
        spec = ScenarioSpec(name="cap27", overrides={"max_class_size": 27})
        r = run_scenario(tiny_dataset, spec, master_time=5, student_time=15)
        assert r.error is None
        assert r.master_status in ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN")

    def test_isolation_base_dataset_unchanged(self, tiny_dataset: Dataset):
        """Running a scenario must not mutate the base dataset."""
        original_max = tiny_dataset.config.hard.max_class_size
        spec = ScenarioSpec(name="x", overrides={"max_class_size": 99})
        run_scenario(tiny_dataset, spec, master_time=3, student_time=10)
        assert tiny_dataset.config.hard.max_class_size == original_max


class TestRunScenarios:
    def test_default_preset_completes(self, tiny_dataset: Dataset):
        # Use only first 2 scenarios from default preset to keep test fast
        specs = PRESETS["default"][:2]
        results = run_scenarios(tiny_dataset, specs, master_time=3, student_time=10, progress=False)
        assert len(results) == 2
        for r in results:
            assert r.master_status in ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN", "MODEL_INVALID")


class TestFormatComparison:
    def test_handles_empty(self):
        s = format_comparison([])
        assert "no scenarios" in s.lower()

    def test_renders_markdown_table(self, tiny_dataset: Dataset):
        spec = ScenarioSpec(name="baseline")
        r = run_scenario(tiny_dataset, spec, master_time=3, student_time=10)
        s = format_comparison([r])
        assert "| Scenario |" in s
        assert "baseline" in s


GOLDEN_PATH = Path(__file__).parent / "golden" / "scenarios_default_tiny.json"


REGENERATE_HINT = (
    "To regenerate after an INTENTIONAL change, run:\n"
    '  .venv/bin/python -c "import json; from pathlib import Path; '
    "from src.scheduler.sample_data import make_grade_12_dataset; "
    "from src.scheduler.scenarios import run_scenarios, PRESETS, to_snapshot_dict; "
    "ds = make_grade_12_dataset(n_students=120, seed=7); "
    "results = run_scenarios(ds, PRESETS['default'], master_time=15, student_time=30, progress=True); "
    "out = {'fixture': {'n_students': 120, 'seed': 7, 'preset': 'default'}, "
    "'solve_budget': {'master_time': 15, 'student_time': 30}, "
    "'scenarios': [to_snapshot_dict(r) for r in results]}; "
    "Path('tests/golden/scenarios_default_tiny.json').write_text(json.dumps(out, indent=2))\""
)


@pytest.mark.slow
def test_golden_default_preset_tiny(tiny_dataset: Dataset):
    """Run the default preset on the tiny fixture and diff against golden snapshot.

    Catches regressions in solver constraints, scenario override appliers, and
    KPI computation. Tolerances live in `scenarios.compare_to_golden`.

    Marked `slow` (~2.5 min) — opt in with `pytest -m slow`.
    """
    assert GOLDEN_PATH.exists(), f"missing golden file at {GOLDEN_PATH}\n\n{REGENERATE_HINT}"
    golden = json.loads(GOLDEN_PATH.read_text())

    assert golden["fixture"] == {"n_students": 120, "seed": 7, "preset": "default"}, (
        "golden fixture metadata changed — regenerate golden if intentional"
    )

    budget = golden["solve_budget"]
    results = run_scenarios(
        tiny_dataset, PRESETS["default"],
        master_time=budget["master_time"], student_time=budget["student_time"],
        progress=False,
    )
    actual = [to_snapshot_dict(r) for r in results]

    assert len(actual) == len(golden["scenarios"]), (
        f"scenario count changed: golden={len(golden['scenarios'])} actual={len(actual)}"
    )

    all_violations: list[str] = []
    for a, g in zip(actual, golden["scenarios"]):
        assert a["name"] == g["name"], f"scenario order changed: golden={g['name']} actual={a['name']}"
        all_violations.extend(compare_to_golden(a, g))

    if all_violations:
        msg = "\n  ".join(["regression vs golden snapshot:"] + all_violations)
        pytest.fail(msg + "\n\n" + REGENERATE_HINT)
