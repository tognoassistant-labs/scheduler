"""Rule registry — exposes HardConstraints fields and SoftConstraintWeights
as first-class, introspectable rules so the UI can render toggles + sliders
generically and the M4 compliance layer can iterate the same registry to
compute per-rule satisfaction.

Phase 1 (M2): every existing constraint/weight is registered as a builtin
Rule. Adding a new builtin = adding one entry in `builtins.py`.

Phase 2 (M6+): custom rules persist their parameters in
`rule_config.registry_overrides_json` and live in `custom.py`.
"""
from .registry import (
    RULE_REGISTRY,
    Rule,
    RuleCompliance,
    apply_overrides,
    extract_values,
    list_rules,
    rule,
)
from . import builtins  # noqa: F401 — register-on-import

__all__ = [
    "RULE_REGISTRY",
    "Rule",
    "RuleCompliance",
    "list_rules",
    "rule",
    "apply_overrides",
    "extract_values",
]
