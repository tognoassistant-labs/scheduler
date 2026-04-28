"""Tests for the master schedule solver — feasibility + locks + invariants."""
from __future__ import annotations

from collections import Counter

import pytest

from src.scheduler.master_solver import solve_master
from src.scheduler.models import Dataset


class TestBasicSolve:
    def test_tiny_solves_optimal_or_feasible(self, tiny_dataset: Dataset):
        master, _, status = solve_master(tiny_dataset, time_limit_s=10)
        assert status in ("OPTIMAL", "FEASIBLE")
        assert len(master) == len(tiny_dataset.sections)

    def test_advisory_at_e3(self, tiny_dataset: Dataset):
        master, _, _ = solve_master(tiny_dataset, time_limit_s=10)
        adv_assignments = [m for m in master
                            if any(s.section_id == m.section_id and s.course_id == "ADV"
                                   for s in tiny_dataset.sections)]
        for a in adv_assignments:
            assert a.scheme == "ADVISORY"
            assert a.slots == [("E", 3)]

    def test_no_teacher_double_booking(self, tiny_dataset: Dataset):
        master, _, _ = solve_master(tiny_dataset, time_limit_s=10)
        # Group by teacher + scheme; should never exceed 1 (excluding advisory)
        sect_to_teacher = {s.section_id: s.teacher_id for s in tiny_dataset.sections}
        academic = [m for m in master if m.scheme != "ADVISORY"]
        per_teacher_scheme: dict[tuple[str, int], int] = Counter()
        for m in academic:
            tid = sect_to_teacher[m.section_id]
            per_teacher_scheme[(tid, m.scheme)] += 1
        violations = [k for k, v in per_teacher_scheme.items() if v > 1]
        assert violations == [], f"Teacher double-bookings: {violations}"

    def test_no_room_double_booking(self, tiny_dataset: Dataset):
        master, _, _ = solve_master(tiny_dataset, time_limit_s=10)
        academic = [m for m in master if m.scheme != "ADVISORY"]
        per_room_scheme: dict[tuple[str, int], int] = Counter()
        for m in academic:
            per_room_scheme[(m.room_id, m.scheme)] += 1
        violations = [k for k, v in per_room_scheme.items() if v > 1]
        assert violations == []

    def test_no_advisory_room_double_booking(self, tiny_dataset: Dataset):
        """All advisory sections meet at E3 simultaneously, so each must have a
        distinct room. Caught by the standalone bundle verifier on 2026-04-26 —
        before HC2b, master was free to put every advisory section in one room.
        """
        master, _, _ = solve_master(tiny_dataset, time_limit_s=10)
        advisory = [m for m in master if m.scheme == "ADVISORY"]
        rooms_used = [m.room_id for m in advisory]
        assert len(rooms_used) == len(set(rooms_used)), (
            f"advisory sections share rooms: {Counter(rooms_used).most_common(3)}"
        )


class TestHomeRoom:
    """HC4 — when a teacher has home_room_id set, all of their academic sections
    must use that room. Per the Reglas Horarios HS doc 2026-04-22 ("salón es por
    profesor"). The client flagged this as the most important fix on 2026-04-28
    after observing teachers with sections spread across 5 different rooms.
    """

    def test_home_room_pins_academic_sections(self, tiny_dataset: Dataset):
        ds = tiny_dataset.model_copy(deep=True)
        # Pick a teacher that owns at least 1 academic section
        adv_course_ids = {c.course_id for c in ds.courses if c.is_advisory}
        teacher = next(
            t for t in ds.teachers
            if any(s.teacher_id == t.teacher_id and s.course_id not in adv_course_ids for s in ds.sections)
        )
        # Pick a compatible room (any standard works for synthetic Grade-12 cores)
        target_room = next(
            r for r in ds.rooms
            if r.capacity >= 25 and r.room_type.value == "standard"
        )
        teacher.home_room_id = target_room.room_id

        master, _, status = solve_master(ds, time_limit_s=15)
        assert status in ("OPTIMAL", "FEASIBLE")
        # Every academic section taught by this teacher must be in the home room
        academic_assignments = [m for m in master if m.scheme != "ADVISORY"]
        sect_to_teacher = {s.section_id: s.teacher_id for s in ds.sections}
        for m in academic_assignments:
            if sect_to_teacher.get(m.section_id) == teacher.teacher_id:
                assert m.room_id == target_room.room_id, (
                    f"section {m.section_id} (teacher={teacher.teacher_id}) "
                    f"got room {m.room_id} but home_room={target_room.room_id}"
                )

    def test_home_room_unset_keeps_default_behavior(self, tiny_dataset: Dataset):
        """Sections of teachers WITHOUT home_room_id retain the original
        type-compatibility-based room domain (no HC4 pin)."""
        ds = tiny_dataset.model_copy(deep=True)
        # Make sure all teachers have home_room_id=None for this test
        for t in ds.teachers:
            t.home_room_id = None
        master, _, status = solve_master(ds, time_limit_s=10)
        assert status in ("OPTIMAL", "FEASIBLE")
        # Different sections of the same teacher CAN go to different rooms
        # (we don't enforce that inversely here — just confirm the solve works)
        assert len(master) > 0


class TestLocks:
    def test_locked_scheme_honored(self, tiny_dataset: Dataset):
        ds = tiny_dataset.model_copy(deep=True)
        target = next(s for s in ds.sections if not ds.course_by_id(s.course_id).is_advisory)
        target.locked_scheme = 6
        master, _, status = solve_master(ds, time_limit_s=10)
        assert status in ("OPTIMAL", "FEASIBLE")
        ass = next(m for m in master if m.section_id == target.section_id)
        assert ass.scheme == 6

    def test_locked_room_honored(self, tiny_dataset: Dataset):
        ds = tiny_dataset.model_copy(deep=True)
        target = next(s for s in ds.sections if not ds.course_by_id(s.course_id).is_advisory)
        target_room = next(r for r in ds.rooms if r.capacity >= target.max_size)
        target.locked_room_id = target_room.room_id
        master, _, status = solve_master(ds, time_limit_s=10)
        assert status in ("OPTIMAL", "FEASIBLE")
        ass = next(m for m in master if m.section_id == target.section_id)
        assert ass.room_id == target_room.room_id

    def test_locked_invalid_scheme_raises(self, tiny_dataset: Dataset):
        ds = tiny_dataset.model_copy(deep=True)
        target = next(s for s in ds.sections if not ds.course_by_id(s.course_id).is_advisory)
        target.locked_scheme = 99  # outside 1..8
        with pytest.raises(ValueError, match="invalid scheme"):
            solve_master(ds, time_limit_s=5)


class TestSchemeBalance:
    def test_no_scheme_drastically_overloaded(self, tiny_dataset: Dataset):
        """Each scheme should hold roughly avg ± 1-2 sections (hard constraint)."""
        master, _, _ = solve_master(tiny_dataset, time_limit_s=10)
        academic = [m for m in master if m.scheme != "ADVISORY"]
        n_academic = len(academic)
        scheme_counts = Counter(m.scheme for m in academic)
        avg = n_academic // 8
        for scheme, count in scheme_counts.items():
            assert count >= max(1, avg - 1), f"Scheme {scheme} underloaded ({count} sections)"
            assert count <= avg + 2, f"Scheme {scheme} overloaded ({count} sections)"
