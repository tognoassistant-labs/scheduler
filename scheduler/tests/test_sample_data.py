"""Tests for the sample data generator."""
from __future__ import annotations

import pytest

from src.scheduler.sample_data import make_grade_12_dataset


class TestSampleData:
    def test_seeded_deterministic(self):
        ds1 = make_grade_12_dataset(n_students=20, seed=1)
        ds2 = make_grade_12_dataset(n_students=20, seed=1)
        assert [s.student_id for s in ds1.students] == [s.student_id for s in ds2.students]

    def test_different_seeds_differ(self):
        ds1 = make_grade_12_dataset(n_students=20, seed=1)
        ds2 = make_grade_12_dataset(n_students=20, seed=2)
        # Same student count but request mix likely differs
        req1 = sorted([(r.student_id, r.course_id) for s in ds1.students for r in s.requested_courses])
        req2 = sorted([(r.student_id, r.course_id) for s in ds2.students for r in s.requested_courses])
        assert req1 != req2

    def test_minimum_size(self):
        ds = make_grade_12_dataset(n_students=10, seed=1)
        assert len(ds.students) == 10
        assert len(ds.sections) >= 1

    def test_advisory_present(self):
        ds = make_grade_12_dataset(n_students=20, seed=1)
        assert any(c.is_advisory for c in ds.courses)
        assert any(s.course_id == "ADV" for s in ds.sections)

    def test_apres_capacity_26(self):
        ds = make_grade_12_dataset(n_students=20, seed=1)
        apres = next((c for c in ds.courses if c.course_id == "APRES"), None)
        if apres:
            assert apres.max_size == 26

    def test_validates_clean(self):
        from src.scheduler.validate import validate_dataset
        ds = make_grade_12_dataset(n_students=30, seed=3)
        rep = validate_dataset(ds)
        assert rep.score == 100, f"Score: {rep.score}, issues: {[i.code for i in rep.issues]}"
