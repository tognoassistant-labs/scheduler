"""Tests for the validation + readiness score logic."""
from __future__ import annotations

import pytest

from src.scheduler.models import Dataset
from src.scheduler.sample_data import make_grade_12_dataset
from src.scheduler.validate import Issue, validate_dataset


class TestReadiness:
    def test_clean_sample_is_100(self, sample_dataset: Dataset):
        rep = validate_dataset(sample_dataset)
        assert rep.score == 100
        assert rep.is_ready
        assert len(rep.errors) == 0
        assert len(rep.warnings) == 0

    def test_score_drops_with_errors(self, sample_dataset: Dataset):
        # Inject a section with bad teacher_id
        ds = sample_dataset.model_copy(deep=True)
        ds.sections[0].teacher_id = "T_DOES_NOT_EXIST"
        rep = validate_dataset(ds)
        assert not rep.is_ready
        assert rep.score < 100
        assert any(i.code == "SECTION_BAD_TEACHER" for i in rep.errors)

    def test_score_drops_with_warnings(self, sample_dataset: Dataset):
        # Inject a teacher with insufficient max_load
        ds = sample_dataset.model_copy(deep=True)
        ds.teachers[0].max_load = 1  # most teachers have ≥3 sections
        rep = validate_dataset(ds)
        assert any(i.code == "TEACHER_OVERLOAD" for i in rep.warnings)


class TestPrerequisiteValidation:
    def test_warns_when_prereq_not_in_requests(self, sample_dataset: Dataset):
        ds = sample_dataset.model_copy(deep=True)
        calc = next(c for c in ds.courses if c.course_id == "CALC")
        calc.prerequisite_course_ids = ["__FAKE_PREREQ__"]
        # Add the fake prereq as a course so PREREQ_BAD_COURSE doesn't fire
        from src.scheduler.models import Course
        ds.courses.append(Course(
            course_id="__FAKE_PREREQ__", name="Fake", department="d",
            qualified_teacher_ids=[ds.teachers[0].teacher_id],
        ))
        rep = validate_dataset(ds)
        # Every student who requested CALC but not __FAKE_PREREQ__ should warn
        warns = [i for i in rep.issues if i.code == "PREREQ_NOT_IN_REQUESTS"]
        assert len(warns) > 0

    def test_detects_prereq_cycle(self, sample_dataset: Dataset):
        ds = sample_dataset.model_copy(deep=True)
        a = next(c for c in ds.courses if c.course_id == "CALC")
        b = next(c for c in ds.courses if c.course_id == "STATS")
        a.prerequisite_course_ids = ["STATS"]
        b.prerequisite_course_ids = ["CALC"]
        rep = validate_dataset(ds)
        cycles = [i for i in rep.issues if i.code == "PREREQ_CYCLE"]
        assert len(cycles) >= 2  # both CALC and STATS reported in cycle

    def test_detects_bad_prereq_ref(self, sample_dataset: Dataset):
        ds = sample_dataset.model_copy(deep=True)
        calc = next(c for c in ds.courses if c.course_id == "CALC")
        calc.prerequisite_course_ids = ["NONEXISTENT_COURSE"]
        rep = validate_dataset(ds)
        bad = [i for i in rep.issues if i.code == "PREREQ_BAD_COURSE"]
        assert len(bad) == 1


class TestReferentialIntegrity:
    def test_section_bad_course(self, sample_dataset: Dataset):
        ds = sample_dataset.model_copy(deep=True)
        ds.sections[0].course_id = "FAKE"
        rep = validate_dataset(ds)
        assert any(i.code == "SECTION_BAD_COURSE" for i in rep.errors)

    def test_request_bad_course(self, sample_dataset: Dataset):
        ds = sample_dataset.model_copy(deep=True)
        ds.students[0].requested_courses[0].course_id = "FAKE"
        rep = validate_dataset(ds)
        assert any(i.code == "REQ_BAD_COURSE" for i in rep.errors)
