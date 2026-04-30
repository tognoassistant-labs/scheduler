"""Rule registry primitives.

A `Rule` is a metadata-rich descriptor of either:
  - a `HardConstraints` field (kind="hard")    — toggle or numeric cap
  - a `SoftConstraintWeights` field (kind="soft") — weight slider

The registry is a single dict keyed by stable rule IDs (R_*) so configs
can reference them durably even if labels change.

`apply_to_solver` / `check` slots are reserved for Phase 2 custom rules
and the M4 compliance computation. Builtins leave them None — the solver
already reads `dataset.config.hard/soft` directly, and compliance lives
in `compliance.py` which dispatches on `rule_id`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from ..models import (
    Dataset,
    HardConstraints,
    MasterAssignment,
    SchoolConfig,
    SoftConstraintWeights,
    StudentAssignment,
)

RuleKind = Literal["hard", "soft"]
ValueType = Literal["bool", "int"]


@dataclass(frozen=True)
class RuleCompliance:
    """Result of a per-rule post-solve check (populated in M4)."""

    rule_id: str
    satisfied: int
    violated: int
    pct: float
    sample_violations: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class Rule:
    """A schedule rule the user can toggle/tune from the UI.

    Attributes:
        id              Stable identifier (R_*). Persisted in rule_config.
        kind            "hard" → toggle/cap; "soft" → weight slider.
        label           Short human label (Spanish OK).
        description     One-line tooltip.
        field_path      Dotted path inside SchoolConfig: "hard.<x>" or "soft.<x>".
                        Used by extract_values / apply_overrides.
        value_type      "bool" or "int" — drives the UI widget.
        default         Default value (matches the field default in models.py).
        min_value/max_value
                        Numeric bounds for sliders (None for booleans).
        category        Free-form grouping label for UI sectioning.
        apply_to_solver Phase-2 hook for custom rules to add CP-SAT constraints.
                        Builtins leave this None — solver reads config directly.
        check           Phase-2 hook for compliance. Builtins leave this None;
                        M4 dispatches on rule_id via compliance.py.
        param_schema    JSON-schema for custom rule parameters (Phase 2).
    """

    id: str
    kind: RuleKind
    label: str
    description: str
    field_path: str
    value_type: ValueType
    default: bool | int
    min_value: int | None = None
    max_value: int | None = None
    category: str = "general"
    apply_to_solver: Callable[..., None] | None = None
    check: Callable[
        [Dataset, list[MasterAssignment], list[StudentAssignment], list[tuple[str, str]]],
        RuleCompliance,
    ] | None = None
    param_schema: dict[str, Any] | None = None


RULE_REGISTRY: dict[str, Rule] = {}


def rule(r: Rule) -> Rule:
    """Register a rule. Last write wins — useful for tests overriding builtins."""
    RULE_REGISTRY[r.id] = r
    return r


def list_rules(kind: RuleKind | None = None) -> list[Rule]:
    items = list(RULE_REGISTRY.values())
    if kind is not None:
        items = [r for r in items if r.kind == kind]
    items.sort(key=lambda r: (r.category, r.kind, r.id))
    return items


def _split_path(path: str) -> tuple[str, str]:
    parts = path.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"field_path {path!r} must be 'hard.<x>' or 'soft.<x>'")
    return parts[0], parts[1]


def extract_values(config: SchoolConfig) -> dict[str, bool | int]:
    """Snapshot of every registered rule's current value, keyed by rule_id.

    Useful for UI initialization — render the registry into widgets,
    pre-fill with these values.
    """
    values: dict[str, bool | int] = {}
    for r in RULE_REGISTRY.values():
        section, field_name = _split_path(r.field_path)
        target = config.hard if section == "hard" else config.soft
        values[r.id] = getattr(target, field_name)
    return values


def apply_overrides(
    hard: HardConstraints,
    soft: SoftConstraintWeights,
    overrides: dict[str, bool | int],
) -> tuple[HardConstraints, SoftConstraintWeights]:
    """Return (hard, soft) with the supplied per-rule values applied.

    Unknown rule_ids are ignored (forward compat — older runs may reference
    rules removed from the registry; we don't crash on them).

    Pydantic models are immutable-by-convention → model_copy(update=...).
    """
    hard_updates: dict[str, Any] = {}
    soft_updates: dict[str, Any] = {}
    for rule_id, value in overrides.items():
        r = RULE_REGISTRY.get(rule_id)
        if r is None:
            continue
        section, field_name = _split_path(r.field_path)
        if section == "hard":
            hard_updates[field_name] = value
        else:
            soft_updates[field_name] = value
    new_hard = hard.model_copy(update=hard_updates) if hard_updates else hard
    new_soft = soft.model_copy(update=soft_updates) if soft_updates else soft
    return new_hard, new_soft
