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


def test_full_coverage_19_of_19(tiny_solved) -> None:
    """Every registered rule must have a working checker (19/19 coverage)."""
    from src.scheduler.rules import RULE_REGISTRY
    ds, master, students, unmet = tiny_solved
    rows = compute_compliance(ds, master, students, unmet)
    rule_ids = {r.rule_id for r in rows}
    missing = set(RULE_REGISTRY.keys()) - rule_ids
    assert not missing, f"Rules without compliance: {missing}"
    # And no row references a non-registered rule
    extra = rule_ids - set(RULE_REGISTRY.keys())
    assert not extra, f"Compliance rows for unregistered rules: {extra}"


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


def test_apply_forbid_slot_extends_teacher_avoid_blocks() -> None:
    from src.scheduler.rules.custom import CustomRuleSpec, apply_custom_rules_to_dataset
    from src.scheduler.sample_data import make_grade_12_dataset
    ds = make_grade_12_dataset(n_students=30, seed=7)
    target = ds.teachers[0].teacher_id
    specs = [
        CustomRuleSpec(
            id="user_avoid_b1",
            kind="hard",
            label="No teacher T1 in block 1",
            solver_op="forbid_slot",
            params={"teacher_id": target, "block": 1},
        ),
    ]
    new_ds = apply_custom_rules_to_dataset(ds, specs)
    new_t = next(t for t in new_ds.teachers if t.teacher_id == target)
    old_t = next(t for t in ds.teachers if t.teacher_id == target)
    assert 1 in new_t.avoid_blocks
    assert 1 not in old_t.avoid_blocks


def test_apply_require_room_locks_all_sections_of_course() -> None:
    from src.scheduler.rules.custom import CustomRuleSpec, apply_custom_rules_to_dataset
    from src.scheduler.sample_data import make_grade_12_dataset
    ds = make_grade_12_dataset(n_students=30, seed=7)
    course_id = ds.sections[0].course_id
    room_id = ds.rooms[0].room_id
    specs = [
        CustomRuleSpec(
            id="r",
            kind="hard",
            label="Lock to one room",
            solver_op="require_room",
            params={"course_id": course_id, "room_id": room_id},
        ),
    ]
    new_ds = apply_custom_rules_to_dataset(ds, specs)
    affected = [s for s in new_ds.sections if s.course_id == course_id]
    assert affected, "test setup: course must have sections"
    assert all(s.locked_room_id == room_id for s in affected)


def test_apply_prefer_teacher_restricts_others() -> None:
    """Prefer_teacher should add every OTHER teacher of the course to the
    student's restricted list."""
    from src.scheduler.rules.custom import CustomRuleSpec, apply_custom_rules_to_dataset
    from src.scheduler.sample_data import make_grade_12_dataset
    ds = make_grade_12_dataset(n_students=30, seed=7)
    # Pick a course with ≥ 2 teachers
    from collections import defaultdict
    by_course = defaultdict(set)
    for s in ds.sections:
        by_course[s.course_id].add(s.teacher_id)
    multi_teacher = next((c for c, ts in by_course.items() if len(ts) >= 2), None)
    if multi_teacher is None:
        return  # tiny dataset doesn't have one — skip
    teachers_of_course = list(by_course[multi_teacher])
    preferred = teachers_of_course[0]
    student_id = ds.students[0].student_id

    specs = [
        CustomRuleSpec(
            id="p",
            kind="hard",
            label="Prefer T1",
            solver_op="prefer_teacher",
            params={
                "student_id": student_id,
                "course_id": multi_teacher,
                "teacher_id": preferred,
            },
        ),
    ]
    new_ds = apply_custom_rules_to_dataset(ds, specs)
    new_st = next(s for s in new_ds.students if s.student_id == student_id)
    for other in teachers_of_course[1:]:
        assert other in new_st.restricted_teacher_ids
    assert preferred not in new_st.restricted_teacher_ids


def test_apply_cohort_together_creates_pairwise_groupings() -> None:
    from src.scheduler.models import BehaviorMatrix, SchoolConfig, default_rotation
    from src.scheduler.rules.custom import CustomRuleSpec, apply_custom_rules_to_dataset
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
            id="cohort1",
            kind="soft",
            label="A,B,C juntos",
            solver_op="cohort_together",
            params={"student_ids": ["A", "B", "C"]},
        ),
    ]
    new_ds = apply_custom_rules_to_dataset(ds, specs)
    pairs = set(new_ds.behavior.groupings)
    assert ("A", "B") in pairs
    assert ("A", "C") in pairs
    assert ("B", "C") in pairs


def test_apply_combined_rules_in_one_call() -> None:
    """All ops in one apply_custom_rules call should land independently."""
    from src.scheduler.rules.custom import CustomRuleSpec, apply_custom_rules_to_dataset
    from src.scheduler.sample_data import make_grade_12_dataset
    ds = make_grade_12_dataset(n_students=30, seed=7)
    teacher = ds.teachers[0].teacher_id
    course = ds.sections[0].course_id
    room = ds.rooms[0].room_id
    student = ds.students[0].student_id
    student_b = ds.students[1].student_id
    specs = [
        CustomRuleSpec(id="a", kind="hard", label="a", solver_op="forbid_pair",
                       params={"student_a": student, "student_b": student_b}),
        CustomRuleSpec(id="b", kind="hard", label="b", solver_op="forbid_slot",
                       params={"teacher_id": teacher, "block": 4}),
        CustomRuleSpec(id="c", kind="hard", label="c", solver_op="require_room",
                       params={"course_id": course, "room_id": room}),
    ]
    new_ds = apply_custom_rules_to_dataset(ds, specs)
    # forbid_pair landed
    assert (student, student_b) in new_ds.behavior.separations or \
           (student_b, student) in new_ds.behavior.separations
    # forbid_slot landed
    new_t = next(t for t in new_ds.teachers if t.teacher_id == teacher)
    assert 4 in new_t.avoid_blocks
    # require_room landed
    affected = [s for s in new_ds.sections if s.course_id == course]
    assert all(s.locked_room_id == room for s in affected)


def test_supported_opcodes_lists_all_implemented() -> None:
    from src.scheduler.rules.custom import supported_opcodes
    ops = supported_opcodes()
    assert "forbid_pair" in ops
    assert "forbid_slot" in ops
    assert "require_room" in ops
    assert "require_room_type" in ops
    assert "prefer_teacher" in ops
    assert "cohort_together" in ops


def test_apply_require_room_type_sets_course_required_type() -> None:
    """require_room_type sets Course.required_room_type so the master solver
    constrains room placement by the existing room_type matching."""
    from src.scheduler.models import RoomType
    from src.scheduler.rules.custom import CustomRuleSpec, apply_custom_rules_to_dataset
    from src.scheduler.sample_data import make_grade_12_dataset
    ds = make_grade_12_dataset(n_students=30, seed=7)
    target = ds.courses[0].course_id
    specs = [
        CustomRuleSpec(
            id="rrt",
            kind="hard",
            label="Course X requires science_lab",
            solver_op="require_room_type",
            params={"course_id": target, "room_type": "science_lab"},
        ),
    ]
    new_ds = apply_custom_rules_to_dataset(ds, specs)
    new_course = next(c for c in new_ds.courses if c.course_id == target)
    assert new_course.required_room_type == RoomType.SCIENCE_LAB


def test_apply_require_room_type_unknown_type_is_noop() -> None:
    from src.scheduler.rules.custom import CustomRuleSpec, apply_custom_rules_to_dataset
    from src.scheduler.sample_data import make_grade_12_dataset
    ds = make_grade_12_dataset(n_students=30, seed=7)
    target = ds.courses[0].course_id
    specs = [
        CustomRuleSpec(
            id="bad",
            kind="hard",
            label="bad type",
            solver_op="require_room_type",
            params={"course_id": target, "room_type": "definitely_not_a_type"},
        ),
    ]
    new_ds = apply_custom_rules_to_dataset(ds, specs)
    # Unknown room_type → returns same instance (no changes applied).
    assert new_ds is ds
