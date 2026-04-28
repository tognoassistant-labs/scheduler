"""Tests for CSV ingest/write — round-trip safety."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.scheduler.io_csv import read_dataset, write_dataset
from src.scheduler.models import Dataset
from src.scheduler.sample_data import make_grade_12_dataset
from src.scheduler.validate import validate_dataset


def _normalize_for_compare(ds: Dataset) -> dict:
    """Extract comparable structure from a Dataset (orderless where appropriate)."""
    return {
        "courses": sorted([c.course_id for c in ds.courses]),
        "teachers": sorted([t.teacher_id for t in ds.teachers]),
        "rooms": sorted([r.room_id for r in ds.rooms]),
        "sections": sorted([(s.section_id, s.course_id, s.teacher_id) for s in ds.sections]),
        "students": sorted([s.student_id for s in ds.students]),
        "n_requests": sum(len(s.requested_courses) for s in ds.students),
        "n_separations": len(ds.behavior.separations),
        "n_groupings": len(ds.behavior.groupings),
    }


class TestRoundTrip:
    def test_basic_roundtrip(self, tmp_path: Path):
        ds = make_grade_12_dataset(n_students=20, seed=1)
        write_dataset(ds, tmp_path)
        ds2 = read_dataset(tmp_path)
        assert _normalize_for_compare(ds) == _normalize_for_compare(ds2)

    def test_roundtrip_validates_clean(self, tmp_path: Path):
        ds = make_grade_12_dataset(n_students=20, seed=1)
        write_dataset(ds, tmp_path)
        ds2 = read_dataset(tmp_path)
        rep = validate_dataset(ds2)
        assert rep.score == 100
        assert len(rep.errors) == 0

    def test_locked_section_roundtrip(self, tmp_path: Path):
        ds = make_grade_12_dataset(n_students=20, seed=1)
        ds.sections[0].locked_scheme = 5
        ds.sections[1].locked_room_id = ds.rooms[0].room_id
        write_dataset(ds, tmp_path)
        ds2 = read_dataset(tmp_path)
        s0 = next(s for s in ds2.sections if s.section_id == ds.sections[0].section_id)
        s1 = next(s for s in ds2.sections if s.section_id == ds.sections[1].section_id)
        assert s0.locked_scheme == 5
        assert s1.locked_room_id == ds.rooms[0].room_id

    def test_teacher_preferences_roundtrip(self, tmp_path: Path):
        ds = make_grade_12_dataset(n_students=20, seed=1)
        t = ds.teachers[0]
        t.preferred_course_ids = ["ENG12"]
        t.avoid_course_ids = ["GOV"]
        t.preferred_blocks = [1, 2]
        t.avoid_blocks = [5]
        write_dataset(ds, tmp_path)
        ds2 = read_dataset(tmp_path)
        t2 = next(tt for tt in ds2.teachers if tt.teacher_id == t.teacher_id)
        assert t2.preferred_course_ids == ["ENG12"]
        assert t2.avoid_course_ids == ["GOV"]
        assert t2.preferred_blocks == [1, 2]
        assert t2.avoid_blocks == [5]

    def test_course_prerequisites_roundtrip(self, tmp_path: Path):
        ds = make_grade_12_dataset(n_students=20, seed=1)
        calc = next(c for c in ds.courses if c.course_id == "CALC")
        calc.prerequisite_course_ids = ["STATS"]
        write_dataset(ds, tmp_path)
        ds2 = read_dataset(tmp_path)
        calc2 = next(c for c in ds2.courses if c.course_id == "CALC")
        assert calc2.prerequisite_course_ids == ["STATS"]

    def test_request_count_preserved(self, tmp_path: Path):
        ds = make_grade_12_dataset(n_students=30, seed=2)
        n_requests_before = sum(len(s.requested_courses) for s in ds.students)
        write_dataset(ds, tmp_path)
        ds2 = read_dataset(tmp_path)
        n_requests_after = sum(len(s.requested_courses) for s in ds2.students)
        assert n_requests_before == n_requests_after
