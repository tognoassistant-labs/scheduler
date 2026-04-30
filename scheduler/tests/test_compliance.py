"""Per-rule compliance tests (M4).

Strategy: solve a tiny dataset, then assert each implemented checker
produces sensible output (counts add up, pct in [0,100], samples bounded).
We don't assert specific violation counts — the solver's choices vary
across versions — but we DO assert structural invariants.
"""
from __future__ import annotations

from src.scheduler.models import Dataset, MasterAssignment, StudentAssignment
from src.scheduler.rules import RULE_REGISTRY
from src.scheduler.rules.compliance import (
    CHECKERS,
    SAMPLE_LIMIT,
    compute_compliance,
    serialize_samples,
    to_db_rows,
)


def test_all_checkers_have_registered_rules() -> None:
    for rule_id in CHECKERS:
        assert rule_id in RULE_REGISTRY, f"checker {rule_id} has no Rule"


def test_compute_compliance_basic_invariants(tiny_solved) -> None:
    ds, master, students, unmet = tiny_solved
    rows = compute_compliance(ds, master, students, unmet)
    assert rows, "expected at least one compliance row"
    seen_ids: set[str] = set()
    for r in rows:
        assert r.rule_id in CHECKERS
        assert r.rule_id not in seen_ids, f"duplicate row for {r.rule_id}"
        seen_ids.add(r.rule_id)
        assert r.satisfied >= 0 and r.violated >= 0
        assert 0.0 <= r.pct <= 100.0
        assert len(r.sample_violations) <= SAMPLE_LIMIT


def test_max_class_size_satisfied_on_clean_solve(tiny_solved) -> None:
    ds, master, students, unmet = tiny_solved
    rows = {r.rule_id: r for r in compute_compliance(ds, master, students, unmet)}
    r = rows["R_max_class_size"]
    # Solver guarantees no over-capacity sections — so violations must be 0.
    assert r.violated == 0
    assert r.pct == 100.0


def test_separations_satisfied_when_enforce_on(tiny_solved) -> None:
    ds, master, students, unmet = tiny_solved
    rows = {r.rule_id: r for r in compute_compliance(ds, master, students, unmet)}
    r = rows["R_enforce_separations"]
    # enforce_separations is True by default → solver must satisfy all of them.
    assert r.violated == 0


def test_serialize_samples_round_trip() -> None:
    import json
    samples = [{"a": 1, "b": [2, 3]}, {"x": "y"}]
    blob = serialize_samples(samples)
    restored = json.loads(blob.decode("utf-8"))
    assert restored == samples


def test_to_db_rows_shape() -> None:
    from src.scheduler.rules.registry import RuleCompliance
    rows = to_db_rows([
        RuleCompliance("R_x", 10, 0, 100.0, []),
        RuleCompliance("R_y", 8, 2, 80.0, [{"id": "z"}]),
    ])
    assert len(rows) == 2
    assert rows[0] == ("R_x", 10, 0, 100.0, None)
    assert rows[1][0] == "R_y"
    assert rows[1][4] is not None  # samples blob present


def test_zero_division_safe_with_no_separations() -> None:
    """A dataset with no separation pairs must still produce a row with pct=100."""
    from src.scheduler.rules.compliance import _check_separations
    from src.scheduler.models import BehaviorMatrix, SchoolConfig, default_rotation
    ds = Dataset(
        config=SchoolConfig(bell=default_rotation()),
        courses=[],
        teachers=[],
        rooms=[],
        sections=[],
        students=[],
        behavior=BehaviorMatrix(separations=[], groupings=[]),
    )
    r = _check_separations(ds, [], [], [])
    assert r.pct == 100.0
    assert r.violated == 0


def test_extended_checkers_present(tiny_solved) -> None:
    """The 13 implemented checkers must all run on a real solve."""
    ds, master, students, unmet = tiny_solved
    rows = compute_compliance(ds, master, students, unmet)
    rule_ids = {r.rule_id for r in rows}
    expected = {
        "R_max_class_size",
        "R_enforce_separations",
        "R_enforce_restricted_teachers",
        "R_max_section_spread_per_course",
        "R_max_consecutive_classes",
        "R_enforce_coplanning_groups",
        "R_w_first_choice_electives",
        "R_w_grouping_codes",
        "R_w_teacher_preferred_courses",
        "R_w_teacher_avoid_courses",
        "R_w_teacher_preferred_blocks",
        "R_w_teacher_avoid_blocks",
        "R_w_teacher_load_balance",
    }
    assert expected <= rule_ids, f"missing: {expected - rule_ids}"


def test_apply_custom_rules_forbid_pair() -> None:
    """A forbid_pair custom rule should append to behavior.separations."""
    from src.scheduler.models import (
        BehaviorMatrix,
        SchoolConfig,
        default_rotation,
    )
    from src.scheduler.rules.custom import (
        CustomRuleSpec,
        apply_custom_rules_to_dataset,
    )
    ds = Dataset(
        config=SchoolConfig(bell=default_rotation()),
        courses=[],
        teachers=[],
        rooms=[],
        sections=[],
        students=[],
        behavior=BehaviorMatrix(separations=[("A", "B")], groupings=[]),
    )
    specs = [
        CustomRuleSpec(
            id="user_no_pair_cd",
            kind="hard",
            label="Never C and D",
            solver_op="forbid_pair",
            params={"student_a": "C", "student_b": "D"},
        ),
        CustomRuleSpec(
            id="user_disabled",
            kind="hard",
            label="Disabled",
            solver_op="forbid_pair",
            params={"student_a": "E", "student_b": "F"},
            enabled=False,
        ),
    ]
    new_ds = apply_custom_rules_to_dataset(ds, specs)
    assert ("A", "B") in new_ds.behavior.separations
    assert ("C", "D") in new_ds.behavior.separations
    assert ("E", "F") not in new_ds.behavior.separations
    # Original ds not mutated
    assert ds.behavior.separations == [("A", "B")]


def test_apply_custom_rules_no_double_add() -> None:
    """Adding a pair that already exists must not duplicate it."""
    from src.scheduler.models import (
        BehaviorMatrix,
        SchoolConfig,
        default_rotation,
    )
    from src.scheduler.rules.custom import (
        CustomRuleSpec,
        apply_custom_rules_to_dataset,
    )
    ds = Dataset(
        config=SchoolConfig(bell=default_rotation()),
        courses=[],
        teachers=[],
        rooms=[],
        sections=[],
        students=[],
        behavior=BehaviorMatrix(separations=[("A", "B")], groupings=[]),
    )
    specs = [
        CustomRuleSpec(
            id="dup",
            kind="hard",
            label="dup",
            solver_op="forbid_pair",
            params={"student_a": "A", "student_b": "B"},
        ),
    ]
    new_ds = apply_custom_rules_to_dataset(ds, specs)
    assert new_ds.behavior.separations == [("A", "B")]


def test_apply_custom_rules_unknown_op_is_noop() -> None:
    from src.scheduler.models import (
        BehaviorMatrix,
        SchoolConfig,
        default_rotation,
    )
    from src.scheduler.rules.custom import (
        CustomRuleSpec,
        apply_custom_rules_to_dataset,
    )
    ds = Dataset(
        config=SchoolConfig(bell=default_rotation()),
        courses=[],
        teachers=[],
        rooms=[],
        sections=[],
        students=[],
        behavior=BehaviorMatrix(),
    )
    specs = [
        CustomRuleSpec(
            id="x",
            kind="hard",
            label="x",
            solver_op="not_implemented_yet",
            params={},
        ),
    ]
    new_ds = apply_custom_rules_to_dataset(ds, specs)
    assert new_ds is ds  # untouched
