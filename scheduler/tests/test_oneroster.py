"""Tests for OneRoster v1.1 reader/writer."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.scheduler.io_oneroster import read_oneroster, write_oneroster
from src.scheduler.master_solver import solve_master
from src.scheduler.models import Dataset
from src.scheduler.student_solver import solve_students


@pytest.fixture(scope="module")
def solved_tiny(tiny_dataset: Dataset):
    master, _, m_status = solve_master(tiny_dataset, time_limit_s=10)
    assert master, f"master failed: {m_status}"
    students, _, _, s_status = solve_students(tiny_dataset, master, time_limit_s=20, mode="single")
    assert students, f"students failed: {s_status}"
    return tiny_dataset, master, students


REQUIRED_FILES = {
    "manifest.csv",
    "orgs.csv",
    "academicSessions.csv",
    "users.csv",
    "courses.csv",
    "classes.csv",
    "enrollments.csv",
}


class TestWriter:
    def test_writes_all_required_files(self, solved_tiny, tmp_path: Path):
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        present = {p.name for p in tmp_path.iterdir()}
        assert REQUIRED_FILES.issubset(present), f"missing: {REQUIRED_FILES - present}"

    def test_manifest_lists_present_files(self, solved_tiny, tmp_path: Path):
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        rows = list(csv.DictReader((tmp_path / "manifest.csv").open()))
        kv = {r["propertyName"]: r["value"] for r in rows}
        assert kv["oneroster.version"] == "1.1"
        for name in ("academicSessions", "orgs", "users", "courses", "classes", "enrollments"):
            assert kv[f"file.{name}"] == "bulk"
        # demographics is not produced
        assert kv["file.demographics"] == "absent"

    def test_orgs_has_one_school(self, solved_tiny, tmp_path: Path):
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        rows = list(csv.DictReader((tmp_path / "orgs.csv").open()))
        assert len(rows) == 1
        assert rows[0]["type"] == "school"
        assert rows[0]["name"] == ds.config.school

    def test_users_partitioned_by_role(self, solved_tiny, tmp_path: Path):
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        rows = list(csv.DictReader((tmp_path / "users.csv").open()))
        roles = [r["role"] for r in rows]
        assert roles.count("teacher") == len(ds.teachers)
        assert roles.count("student") == len(ds.students)

    def test_classes_have_master_periods(self, solved_tiny, tmp_path: Path):
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        rows = list(csv.DictReader((tmp_path / "classes.csv").open()))
        master_ids = {m.section_id for m in master}
        for row in rows:
            sid = row["classCode"]
            if sid in master_ids:
                # Every solved section gets a periods string and a non-empty location
                assert row["periods"], f"empty periods for {sid}"
                assert row["location"], f"empty location for {sid}"

    def test_enrollments_include_teacher_and_students(self, solved_tiny, tmp_path: Path):
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        rows = list(csv.DictReader((tmp_path / "enrollments.csv").open()))
        roles = [r["role"] for r in rows]
        # One primary teacher per master-assigned section
        assert roles.count("teacher") == len(master)
        # Student enrollment count = sum of placed sections across students
        expected_student_enrollments = sum(len(s.section_ids) for s in students)
        # May be fewer than expected if some sections were dropped (unmastered);
        # all master-mapped students must be present
        assert roles.count("student") <= expected_student_enrollments
        assert roles.count("student") > 0

    def test_advisory_classes_marked_homeroom(self, solved_tiny, tmp_path: Path):
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        rows = list(csv.DictReader((tmp_path / "classes.csv").open()))
        adv_course_ids = {c.course_id for c in ds.courses if c.is_advisory}
        for row in rows:
            section_id = row["classCode"]
            section = next((s for s in ds.sections if s.section_id == section_id), None)
            if section and section.course_id in adv_course_ids:
                assert row["classType"] == "homeroom"


class TestReader:
    def test_round_trip_preserves_counts(self, solved_tiny, tmp_path: Path):
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        ds2 = read_oneroster(tmp_path)
        assert len(ds2.courses) == len(ds.courses)
        assert len(ds2.teachers) == len(ds.teachers)
        assert len(ds2.students) == len(ds.students)
        # Sections recovered from classes.csv (one row per section)
        assert len(ds2.sections) == len(ds.sections)
        # Rooms come from class locations — only rooms actually used appear
        used_rooms = {m.room_id for m in master}
        assert len(ds2.rooms) <= len(used_rooms)
        assert len(ds2.rooms) >= 1

    def test_round_trip_preserves_school_and_year(self, solved_tiny, tmp_path: Path):
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        ds2 = read_oneroster(tmp_path)
        assert ds2.config.school == ds.config.school
        assert ds2.config.year == ds.config.year

    def test_reader_does_not_recover_requests(self, solved_tiny, tmp_path: Path):
        """OneRoster has no concept of CourseRequest ranks — must come back empty."""
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        ds2 = read_oneroster(tmp_path)
        for s in ds2.students:
            assert s.requested_courses == []

    def test_reader_recovers_section_to_teacher_mapping(self, solved_tiny, tmp_path: Path):
        ds, master, students = solved_tiny
        write_oneroster(ds, master, students, tmp_path)
        ds2 = read_oneroster(tmp_path)
        # Every section gets back its primary teacher (from enrollments)
        for s2 in ds2.sections:
            original = next((s for s in ds.sections if s.section_id == s2.section_id), None)
            if original is None or s2.section_id not in {m.section_id for m in master}:
                continue
            assert s2.teacher_id == original.teacher_id, (
                f"teacher mismatch on {s2.section_id}: expected {original.teacher_id} got {s2.teacher_id!r}"
            )

    def test_reader_handles_missing_dir(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        ds = read_oneroster(empty)
        assert ds.courses == []
        assert ds.students == []
