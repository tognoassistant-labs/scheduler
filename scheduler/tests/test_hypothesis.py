"""Hypothesis property-based tests for solver invariants.

Strategy: generate small but valid Datasets via the seeded sample generator
and assert that solver outputs always satisfy the invariant checker.
This tests the pipeline holistically — any solver bug that produces a
schedule violating hard constraints will surface as a failed example.

Hypothesis is configured for short tests (max_examples=8) to keep CI fast.
Run more thoroughly with `pytest --hypothesis-seed=0` or by raising the
`max_examples` setting in `settings(profile="thorough")`.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from src.scheduler.exporter import export_powerschool
from src.scheduler.io_csv import read_dataset, write_dataset
from src.scheduler.master_solver import solve_master
from src.scheduler.sample_data import make_grade_12_dataset
from src.scheduler.student_solver import solve_students
from src.scheduler.validate import validate_dataset
from tests.check_invariants import check_invariants


# Profile: keep tests fast in CI; turn this up for nightly fuzzing.
settings.register_profile("ci", max_examples=8, deadline=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("ci")


# ============================================================================
# Property: CSV round-trip preserves the dataset structure
# ============================================================================

@given(seed=st.integers(min_value=1, max_value=2**31), n=st.integers(min_value=15, max_value=40))
def test_property_csv_roundtrip_preserves(seed: int, n: int, tmp_path_factory):
    """For any seeded sample dataset, write→read produces an equivalent dataset."""
    ds = make_grade_12_dataset(n_students=n, seed=seed)
    tmp = tmp_path_factory.mktemp(f"rt_{seed}")
    write_dataset(ds, tmp)
    ds2 = read_dataset(tmp)
    assert len(ds.students) == len(ds2.students)
    assert len(ds.sections) == len(ds2.sections)
    assert len(ds.courses) == len(ds2.courses)
    n_req_before = sum(len(s.requested_courses) for s in ds.students)
    n_req_after = sum(len(s.requested_courses) for s in ds2.students)
    assert n_req_before == n_req_after


# ============================================================================
# Property: any seeded sample validates clean (data quality invariant)
# ============================================================================

@given(seed=st.integers(min_value=1, max_value=2**31), n=st.integers(min_value=15, max_value=50))
def test_property_seeded_sample_validates(seed: int, n: int):
    ds = make_grade_12_dataset(n_students=n, seed=seed)
    rep = validate_dataset(ds)
    assert rep.is_ready, f"Seed {seed}, n={n}: errors={[i.code for i in rep.errors]}"


# ============================================================================
# Property: solver output passes the independent invariant checker
# ============================================================================

@given(seed=st.integers(min_value=1, max_value=2**31))
@settings(max_examples=3, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_solver_output_invariants(seed: int, tmp_path_factory):
    """When the solver succeeds, the output must pass the invariant checker.

    Some seeds at small N produce infeasible problems (singleton courses
    clustering into the same scheme). The property is conditional: if a
    solution exists, it must be valid. We don't require every input to be
    feasible.

    Budget: student_time=60s. Per Hector decision 2026-04-26 (Decisión 2),
    raised from 25s. NOTE: 60s and 120s both still fail at seed=1 (balance=4
    on GOV) — this is structural post-HC2b on this specific seed, not a
    pure time-budget issue. See QUESTIONS_FOR_HECTOR.md Decisión 2 for
    pending follow-up; for now this test still flags seed=1 as a Hypothesis
    falsifying example. Treat as a known edge case until follow-up.
    """
    ds = make_grade_12_dataset(n_students=100, seed=seed)
    master, _, m_status = solve_master(ds, time_limit_s=15)
    if not master:
        return  # Solver couldn't find a master schedule — skip
    students, unmet, _, s_status = solve_students(ds, master, time_limit_s=60, mode="single")
    if not students:
        return  # Couldn't fit students under hard balance — skip
    tmp = tmp_path_factory.mktemp(f"inv_{seed}")
    export_powerschool(ds, master, students, tmp)
    n_failures, msgs = check_invariants(tmp)
    assert n_failures == 0, f"Seed {seed}: {msgs}"


# ============================================================================
# Property: locked sections always honored
# ============================================================================

@given(
    seed=st.integers(min_value=1, max_value=2**31),
    locked_scheme=st.integers(min_value=1, max_value=8),
)
@settings(max_examples=3, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_locked_scheme_honored(seed: int, locked_scheme: int):
    ds = make_grade_12_dataset(n_students=100, seed=seed)
    target = next(s for s in ds.sections if not ds.course_by_id(s.course_id).is_advisory)
    target.locked_scheme = locked_scheme
    master, _, status = solve_master(ds, time_limit_s=15)
    if status not in ("OPTIMAL", "FEASIBLE"):
        return
    ass = next(m for m in master if m.section_id == target.section_id)
    assert ass.scheme == locked_scheme


# ============================================================================
# Property: capacity is always respected
# ============================================================================

@given(seed=st.integers(min_value=1, max_value=2**31))
@settings(max_examples=3, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_capacity_respected(seed: int):
    ds = make_grade_12_dataset(n_students=100, seed=seed)
    master, _, m_status = solve_master(ds, time_limit_s=15)
    if not master:
        return
    students, unmet, _, _ = solve_students(ds, master, time_limit_s=25, mode="single")
    if not students:
        return
    sec_max = {s.section_id: s.max_size for s in ds.sections}
    enrollment: dict[str, int] = defaultdict(int)
    for sa in students:
        for sid in sa.section_ids:
            enrollment[sid] += 1
    for sid, n in enrollment.items():
        assert n <= sec_max[sid], f"Section {sid} over capacity: {n}/{sec_max[sid]} (seed={seed})"


# ============================================================================
# Property: HC2b — every advisory section has a distinct room
# ============================================================================

@given(seed=st.integers(min_value=1, max_value=2**31))
@settings(max_examples=4, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_advisory_rooms_distinct(seed: int):
    """Advisory sections all meet at the same time slot (Day E, Block 3), so
    every advisory section must be in a different room. Caught by the
    standalone bundle verifier on 2026-04-26 — before HC2b, master was free
    to put every advisory section in one room because the academic HC2 only
    iterated schemes 1..8 and missed ADVISORY.

    This is the property formulation of the single-fixture regression test in
    `test_master_solver.py::test_no_advisory_room_double_booking`. Stronger
    coverage: any seed that produces a feasible master must satisfy this.
    """
    ds = make_grade_12_dataset(n_students=100, seed=seed)
    master, _, status = solve_master(ds, time_limit_s=15)
    if status not in ("OPTIMAL", "FEASIBLE"):
        return  # No solution to inspect — Hypothesis will keep searching
    advisory_assignments = [m for m in master if m.scheme == "ADVISORY"]
    rooms_used = [m.room_id for m in advisory_assignments]
    assert len(rooms_used) == len(set(rooms_used)), (
        f"Seed {seed}: advisory sections share rooms (HC2b violated). "
        f"Rooms: {rooms_used}"
    )
