"""Tests for the student-assignment solver."""
from __future__ import annotations

from collections import defaultdict

import pytest

from src.scheduler.master_solver import solve_master
from src.scheduler.models import Dataset
from src.scheduler.student_solver import solve_students


class TestBasicSolve:
    def test_all_students_assigned(self, tiny_solved):
        ds, master, students, unmet = tiny_solved
        assert len(students) == len(ds.students)

    def test_no_student_time_conflicts(self, tiny_solved):
        ds, master, students, unmet = tiny_solved
        slots_per_section: dict[str, list] = {m.section_id: m.slots for m in master}
        for sa in students:
            slots_taken: list = []
            for sid in sa.section_ids:
                slots_taken.extend(slots_per_section.get(sid, []))
            assert len(slots_taken) == len(set(slots_taken)), \
                f"Student {sa.student_id} has time conflicts: {slots_taken}"

    def test_capacity_respected(self, tiny_solved):
        ds, master, students, unmet = tiny_solved
        sec_max = {s.section_id: s.max_size for s in ds.sections}
        enrollment: dict[str, int] = defaultdict(int)
        for sa in students:
            for sid in sa.section_ids:
                enrollment[sid] += 1
        for sid, n in enrollment.items():
            assert n <= sec_max[sid], f"Section {sid} over capacity: {n}/{sec_max[sid]}"


class TestSeparations:
    def test_separation_pairs_never_share_section(self, tiny_solved):
        ds, master, students, unmet = tiny_solved
        student_sections: dict[str, set] = {sa.student_id: set(sa.section_ids) for sa in students}
        for a, b in ds.behavior.separations:
            sa = student_sections.get(a, set())
            sb = student_sections.get(b, set())
            assert not (sa & sb), \
                f"Separation pair {a}/{b} share sections: {sa & sb}"


class TestRequirements:
    def test_required_courses_mostly_granted(self, tiny_solved):
        """v4 student_solver uses soft slack on required courses (heavily
        penalized) so over-constrained synthetic students can leave a small
        number unmet rather than INFEASIBLE. We require ≥95% fulfillment on
        the tiny fixture: tight enough to catch hard regressions (which drop
        far below), loose enough to absorb seed-sensitive partial coverage
        in the synthetic generator."""
        ds, master, students, unmet = tiny_solved
        sec_to_course = {s.section_id: s.course_id for s in ds.sections}
        student_assigns = {sa.student_id: sa for sa in students}
        total_required = 0
        unmet_required = 0
        for stu in ds.students:
            sa = student_assigns.get(stu.student_id)
            assert sa is not None
            granted_courses = {sec_to_course[sid] for sid in sa.section_ids if sid in sec_to_course}
            for r in stu.requested_courses:
                if r.is_required:
                    total_required += 1
                    if r.course_id not in granted_courses:
                        unmet_required += 1
        if total_required:
            fulfillment = 1 - unmet_required / total_required
            assert fulfillment >= 0.95, (
                f"required fulfillment {fulfillment:.3f} below 95% "
                f"({unmet_required}/{total_required} unmet)"
            )


class TestBalance:
    def test_section_spread_within_hard_cap(self, tiny_solved):
        ds, master, students, unmet = tiny_solved
        sections_by_course: dict[str, list[str]] = defaultdict(list)
        for s in ds.sections:
            sections_by_course[s.course_id].append(s.section_id)
        enrollment: dict[str, int] = defaultdict(int)
        for sa in students:
            for sid in sa.section_ids:
                enrollment[sid] += 1
        cap = ds.config.hard.max_section_spread_per_course
        for cid, sids in sections_by_course.items():
            if len(sids) < ds.config.hard.min_sections_for_balance:
                continue
            sizes = [enrollment[sid] for sid in sids]
            spread = max(sizes) - min(sizes)
            assert spread <= cap, \
                f"Course {cid} spread {spread} exceeds hard cap {cap} (sizes: {sizes})"


class TestModes:
    def test_lexmin_mode_runs(self, tiny_dataset: Dataset):
        master, _, _ = solve_master(tiny_dataset, time_limit_s=10)
        students, unmet, _, status = solve_students(
            tiny_dataset, master, time_limit_s=30, mode="lexmin"
        )
        assert status in ("OPTIMAL", "FEASIBLE")
        # Soft slack (v4) lets lexmin leave a small number of over-constrained
        # students partially placed; require ≥99% of students to receive
        # at least one section. Hard regressions would drop well below.
        assert len(students) >= 0.99 * len(tiny_dataset.students), (
            f"lexmin placed {len(students)}/{len(tiny_dataset.students)} students"
        )

    def test_single_mode_runs(self, tiny_dataset: Dataset):
        master, _, _ = solve_master(tiny_dataset, time_limit_s=10)
        students, unmet, _, status = solve_students(
            tiny_dataset, master, time_limit_s=20, mode="single"
        )
        assert status in ("OPTIMAL", "FEASIBLE")
