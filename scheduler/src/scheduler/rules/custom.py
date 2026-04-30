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


# ---------------------------------------------------------------------------
# Phase-2 DSL applier — translates solver_op values to direct mutations of
# the Dataset before solving. Each opcode reuses an existing solver-supported
# field (no solver changes needed for these ops).
#
# Supported opcodes:
#
#   forbid_pair      params: {student_a, student_b}
#                    → adds to behavior.separations (hard)
#
#   forbid_slot      params: {teacher_id, block} | {teacher_id, day}
#                    → appends to teacher.avoid_blocks (soft via
#                      R_w_teacher_avoid_blocks weight). For hard, set the
#                      weight high in the Rules tab.
#                    Note: course-level forbid_slot needs solver changes; not
#                    implemented in v1. Use teacher_id for now.
#
#   require_room     params: {course_id, room_id}
#                    → sets Section.locked_room_id for every section of
#                      course_id (hard via existing master solver constraint).
#
#   prefer_teacher   params: {student_id, course_id, teacher_id}
#                    → adds every OTHER teacher of course_id to
#                      student.restricted_teacher_ids. The existing
#                      R_enforce_restricted_teachers makes this hard.
#                    Use case: TA assignments — student must end up in a
#                    specific teacher's section.
#
#   cohort_together  params: {student_ids: [...], course_id?}
#                    → appends every pair from the list to behavior.groupings
#                      (soft via R_w_grouping_codes). course_id is informational.
#
# Unknown ops are silent no-ops (forward compat).
# ---------------------------------------------------------------------------


def _apply_forbid_pair(ds, params, state):
    a, b = params.get("student_a"), params.get("student_b")
    if not (a and b):
        return False
    seps = state["separations"]
    if (a, b) not in seps and (b, a) not in seps:
        seps.append((a, b))
        return True
    return False


def _apply_forbid_slot(ds, params, state):
    """Teacher-level only in v1: appends `block` to that teacher's avoid_blocks."""
    teacher_id = params.get("teacher_id")
    block = params.get("block")
    if not (teacher_id and block):
        return False
    teachers = state["teachers"]
    for i, t in enumerate(teachers):
        if t.teacher_id == str(teacher_id):
            new_avoids = list(t.avoid_blocks)
            if int(block) not in new_avoids:
                new_avoids.append(int(block))
                teachers[i] = t.model_copy(update={"avoid_blocks": new_avoids})
                return True
            return False
    return False


def _apply_require_room(ds, params, state):
    """Course-level: locks every section of course_id to room_id."""
    course_id = params.get("course_id")
    room_id = params.get("room_id")
    if not (course_id and room_id):
        return False
    course_id, room_id = str(course_id), str(room_id)
    sections = state["sections"]
    changed = False
    for i, s in enumerate(sections):
        if s.course_id == course_id and s.locked_room_id != room_id:
            sections[i] = s.model_copy(update={"locked_room_id": room_id})
            changed = True
    return changed


def _apply_require_room_type(ds, params, state):
    """Course-level: sets Course.required_room_type so the master solver
    only places sections of this course in rooms of the matching type.
    Use cases: química/biología → science_lab, banda → music, PE → gym."""
    course_id = params.get("course_id")
    room_type = params.get("room_type")
    if not (course_id and room_type):
        return False
    course_id = str(course_id)
    room_type = str(room_type).lower()
    if "courses" not in state:
        state["courses"] = list(ds.courses)
    courses = state["courses"]
    from ..models import RoomType
    try:
        rt = RoomType(room_type)
    except ValueError:
        return False  # unknown room_type — silent
    changed = False
    for i, c in enumerate(courses):
        if c.course_id == course_id and c.required_room_type != rt:
            courses[i] = c.model_copy(update={"required_room_type": rt})
            changed = True
    return changed


def _apply_prefer_teacher(ds, params, state):
    """Force student to the section of course_id taught by teacher_id, by
    adding every other teacher of that course to the student's
    restricted_teacher_ids. Hard via R_enforce_restricted_teachers."""
    student_id = params.get("student_id")
    course_id = params.get("course_id")
    teacher_id = params.get("teacher_id")
    if not (student_id and course_id and teacher_id):
        return False
    student_id, course_id, teacher_id = str(student_id), str(course_id), str(teacher_id)
    other_teachers = {
        s.teacher_id for s in ds.sections
        if s.course_id == course_id and s.teacher_id != teacher_id
    }
    if not other_teachers:
        return False
    students = state["students"]
    for i, st in enumerate(students):
        if st.student_id == student_id:
            new_restrictions = list(st.restricted_teacher_ids)
            added = [t for t in other_teachers if t not in new_restrictions]
            if added:
                new_restrictions.extend(added)
                students[i] = st.model_copy(update={"restricted_teacher_ids": new_restrictions})
                return True
            return False
    return False


def _apply_cohort_together(ds, params, state):
    """Pairwise: every pair in student_ids becomes a grouping (soft)."""
    student_ids = params.get("student_ids") or []
    if len(student_ids) < 2:
        return False
    student_ids = [str(s) for s in student_ids]
    groupings = state["groupings"]
    changed = False
    for i in range(len(student_ids)):
        for j in range(i + 1, len(student_ids)):
            pair = (student_ids[i], student_ids[j])
            reverse = (student_ids[j], student_ids[i])
            if pair not in groupings and reverse not in groupings:
                groupings.append(pair)
                changed = True
    return changed


_OP_TABLE = {
    "forbid_pair": _apply_forbid_pair,
    "forbid_slot": _apply_forbid_slot,
    "require_room": _apply_require_room,
    "require_room_type": _apply_require_room_type,
    "prefer_teacher": _apply_prefer_teacher,
    "cohort_together": _apply_cohort_together,
}


def apply_custom_rules_to_dataset(ds, specs: list[CustomRuleSpec]):
    """Mutate-then-return the Dataset with each enabled custom rule applied.

    State is collected in a mutable dict, then a single ds.model_copy commits
    everything at once. This makes ordering predictable and avoids creating
    N intermediate Datasets.

    Pydantic models are not mutated in place — we model_copy with updated lists.
    No-op for empty / all-disabled specs / unrecognized ops.
    """
    if not specs:
        return ds

    state = {
        "separations": list(ds.behavior.separations),
        "groupings": list(ds.behavior.groupings),
        "teachers": list(ds.teachers),
        "sections": list(ds.sections),
        "students": list(ds.students),
        "courses": list(ds.courses),
    }
    applied = 0
    for spec in specs:
        if not spec.enabled:
            continue
        fn = _OP_TABLE.get(spec.solver_op)
        if fn is None:
            continue  # forward compat — unknown opcode
        if fn(ds, spec.params, state):
            applied += 1
    if applied == 0:
        return ds
    new_behavior = ds.behavior.model_copy(update={
        "separations": state["separations"],
        "groupings": state["groupings"],
    })
    return ds.model_copy(update={
        "behavior": new_behavior,
        "teachers": state["teachers"],
        "sections": state["sections"],
        "students": state["students"],
        "courses": state["courses"],
    })


def supported_opcodes() -> list[str]:
    """For UI introspection / docs."""
    return sorted(_OP_TABLE.keys())
