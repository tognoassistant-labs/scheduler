"""Custom rules — Phase 2 placeholder.

When a user defines a rule from the UI (Phase 2), it is persisted into
`rule_config.registry_overrides_json` as a CustomRuleSpec. At load time,
`load_custom_rules(blob)` parses the spec, builds a `Rule` per entry, and
registers it temporarily on top of the builtins registry.

M6 wires the placeholder UI tab. The DSL evaluator + apply_to_solver hook
are deferred — Phase 2 ships independently when the school requests
custom-rule authoring.

The on-disk format is intentionally minimal so M6 can land without the
final DSL. Phase 2 is free to evolve `params` without migrations as long
as `id`, `kind`, `label`, `field_path` (or `solver_op`) remain stable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CustomRuleSpec:
    """User-authored rule metadata, persisted in rule_config.

    Fields:
        id          Stable user-chosen ID (must NOT collide with R_* builtins).
        kind        "hard" | "soft".
        label       UI display name.
        description One-line tooltip.
        solver_op   Phase-2 DSL opcode: "forbid_pair", "prefer_slot", etc.
        params      Opaque JSON object consumed by the DSL evaluator.
        enabled     User toggle.
    """

    id: str
    kind: str
    label: str
    description: str = ""
    solver_op: str = "noop"
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "description": self.description,
            "solver_op": self.solver_op,
            "params": self.params,
            "enabled": self.enabled,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "CustomRuleSpec":
        return cls(
            id=data["id"],
            kind=data["kind"],
            label=data["label"],
            description=data.get("description", ""),
            solver_op=data.get("solver_op", "noop"),
            params=data.get("params", {}),
            enabled=data.get("enabled", True),
        )


def serialize_custom_rules(specs: list[CustomRuleSpec]) -> bytes:
    payload = {"version": 1, "rules": [s.to_json() for s in specs]}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def deserialize_custom_rules(blob: bytes | str | None) -> list[CustomRuleSpec]:
    if blob is None:
        return []
    if isinstance(blob, bytes):
        blob = blob.decode("utf-8")
    if not blob.strip():
        return []
    payload = json.loads(blob)
    return [CustomRuleSpec.from_json(item) for item in payload.get("rules", [])]
