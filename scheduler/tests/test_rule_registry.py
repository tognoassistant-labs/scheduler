"""Registry contract tests (M2).

Critical invariants:
- Every registered rule's default matches the corresponding model.py default.
- Every rule has a stable R_* id.
- extract_values + apply_overrides round-trip cleanly.
- Unknown rule_ids are silently ignored (forward compat).
- Custom rule specs serialize/deserialize.
"""
from __future__ import annotations

import pytest

from src.scheduler.models import HardConstraints, SchoolConfig, SoftConstraintWeights, default_rotation
from src.scheduler.rules import (
    RULE_REGISTRY,
    Rule,
    apply_overrides,
    extract_values,
    list_rules,
)
from src.scheduler.rules.custom import CustomRuleSpec, deserialize_custom_rules, serialize_custom_rules


def test_registry_is_populated() -> None:
    assert len(RULE_REGISTRY) >= 15
    assert all(rid.startswith("R_") for rid in RULE_REGISTRY)


def test_kinds_split_correctly() -> None:
    hard_rules = list_rules(kind="hard")
    soft_rules = list_rules(kind="soft")
    assert hard_rules and soft_rules
    assert {r.kind for r in hard_rules} == {"hard"}
    assert {r.kind for r in soft_rules} == {"soft"}


def test_field_paths_are_valid() -> None:
    hard_fields = set(HardConstraints.model_fields.keys())
    soft_fields = set(SoftConstraintWeights.model_fields.keys())
    for r in RULE_REGISTRY.values():
        section, field = r.field_path.split(".", 1)
        if section == "hard":
            assert field in hard_fields, f"Rule {r.id}: hard.{field} not in HardConstraints"
        elif section == "soft":
            assert field in soft_fields, f"Rule {r.id}: soft.{field} not in SoftConstraintWeights"
        else:
            pytest.fail(f"Rule {r.id} has bad section {section!r}")


def test_defaults_match_model_defaults() -> None:
    """If model.py changes a default, this test fails until builtins.py is updated."""
    hc = HardConstraints()
    sw = SoftConstraintWeights()
    for r in RULE_REGISTRY.values():
        section, field = r.field_path.split(".", 1)
        target = hc if section == "hard" else sw
        actual = getattr(target, field)
        assert r.default == actual, f"Rule {r.id} default={r.default} but model default={actual}"


def test_int_rules_have_bounds() -> None:
    for r in RULE_REGISTRY.values():
        if r.value_type == "int":
            assert r.min_value is not None and r.max_value is not None
            assert r.min_value <= r.default <= r.max_value
        else:
            assert isinstance(r.default, bool)


def test_extract_values_returns_one_per_rule() -> None:
    cfg = SchoolConfig(bell=default_rotation())
    values = extract_values(cfg)
    assert set(values.keys()) == set(RULE_REGISTRY.keys())


def test_apply_overrides_updates_target_fields() -> None:
    hc = HardConstraints()
    sw = SoftConstraintWeights()
    new_hc, new_sw = apply_overrides(
        hc, sw,
        {
            "R_enforce_separations": False,
            "R_max_class_size": 30,
            "R_w_first_choice_electives": 50,
        },
    )
    assert new_hc.enforce_separations is False
    assert new_hc.max_class_size == 30
    assert new_sw.first_choice_electives == 50
    # Untouched fields preserved
    assert new_hc.enforce_restricted_teachers is True
    assert new_sw.balance_class_sizes == sw.balance_class_sizes


def test_apply_overrides_ignores_unknown_ids() -> None:
    hc = HardConstraints()
    sw = SoftConstraintWeights()
    new_hc, new_sw = apply_overrides(hc, sw, {"R_does_not_exist": 99})
    assert new_hc == hc
    assert new_sw == sw


def test_round_trip_extract_apply() -> None:
    cfg = SchoolConfig(
        bell=default_rotation(),
        hard=HardConstraints(enforce_separations=False, max_class_size=22),
        soft=SoftConstraintWeights(first_choice_electives=99),
    )
    values = extract_values(cfg)
    new_hc, new_sw = apply_overrides(HardConstraints(), SoftConstraintWeights(), values)
    assert new_hc == cfg.hard
    assert new_sw == cfg.soft


def test_custom_rule_serialization() -> None:
    specs = [
        CustomRuleSpec(
            id="user_no_friday_pe",
            kind="hard",
            label="No PE on Fridays",
            solver_op="forbid_slot",
            params={"course_id": "PE12", "day": "E"},
        ),
    ]
    blob = serialize_custom_rules(specs)
    restored = deserialize_custom_rules(blob)
    assert restored == specs


def test_deserialize_empty_blob() -> None:
    assert deserialize_custom_rules(None) == []
    assert deserialize_custom_rules(b"") == []
    assert deserialize_custom_rules(b'{"version":1,"rules":[]}') == []


def test_no_id_collision_with_builtins() -> None:
    """Custom rule ids must not collide with R_* builtin ids."""
    custom_id = "user_my_rule"
    assert custom_id not in RULE_REGISTRY
