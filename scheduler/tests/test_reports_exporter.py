"""Tests for reports + exporter modules."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.scheduler.exporter import export_powerschool
from src.scheduler.reports import compute_kpis, write_reports


class TestKPIs:
    def test_kpi_structure(self, tiny_solved):
        ds, master, students, unmet = tiny_solved
        kpi = compute_kpis(ds, master, students, unmet)
        assert 0 <= kpi.fully_scheduled_pct <= 100
        assert 0 <= kpi.required_fulfillment_pct <= 100
        assert 0 <= kpi.first_choice_elective_pct <= 100
        assert kpi.section_balance_max_dev >= 0
        assert isinstance(kpi.targets_met, dict)

    def test_required_fulfillment_100_on_clean_solve(self, tiny_solved):
        ds, master, students, unmet = tiny_solved
        kpi = compute_kpis(ds, master, students, unmet)
        # Solver enforces required = exactly 1; should always be 100%
        assert kpi.required_fulfillment_pct == 100.0

    def test_summary_renders(self, tiny_solved):
        ds, master, students, unmet = tiny_solved
        kpi = compute_kpis(ds, master, students, unmet)
        text = kpi.summary()
        assert "v2 §10" in text
        assert "Fully scheduled" in text


class TestReports:
    def test_write_reports_creates_files(self, tiny_solved, tmp_path: Path):
        ds, master, students, unmet = tiny_solved
        write_reports(ds, master, students, unmet, tmp_path)
        for fname in ("schedule_report.md", "sections_with_enrollment.csv",
                      "student_schedules.csv", "teacher_loads.csv", "unmet_requests.csv"):
            assert (tmp_path / fname).exists(), f"Missing {fname}"


class TestPowerSchoolExporter:
    def test_export_creates_files(self, tiny_solved, tmp_path: Path):
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        for fname in ("ps_sections.csv", "ps_enrollments.csv",
                      "ps_master_schedule.csv", "ps_field_mapping.md"):
            assert (tmp_path / fname).exists()

    def test_ps_sections_columns(self, tiny_solved, tmp_path: Path):
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        with (tmp_path / "ps_sections.csv").open() as f:
            r = csv.DictReader(f)
            header = r.fieldnames
            for col in ("SchoolID", "CourseID", "SectionID", "TeacherID", "RoomID", "Period", "Slots"):
                assert col in header, f"Missing PS column {col}"

    def test_advisory_period_code(self, tiny_solved, tmp_path: Path):
        """Per 2026-04-26 client confirmation, Period uses Columbus PS Expression
        format: `<block>(<day>)`. Advisory meets at Day E Block 3 → "3(E)"."""
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        with (tmp_path / "ps_sections.csv").open() as f:
            for row in csv.DictReader(f):
                if row["CourseID"] == "ADV":
                    assert row["Period"] == "3(E)", (
                        f"advisory Period should be '3(E)', got {row['Period']!r}"
                    )
                    assert row["Slots"] == "E3"

    def test_invariants_pass_on_export(self, tiny_solved, tmp_path: Path):
        from tests.check_invariants import check_invariants
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        n_failures, msgs = check_invariants(tmp_path)
        assert n_failures == 0, f"Invariants failed: {msgs}"

    def test_advisory_rooms_distinct_in_export(self, tiny_solved, tmp_path: Path):
        """Regression test for the 2026-04-26 advisory-room collapse bug:
        every advisory section was assigned the same room because HC2
        in master_solver only iterated schemes 1..8, missing ADVISORY.
        After HC2b, all advisory sections must have distinct rooms.
        """
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        adv_rooms: list[str] = []
        with (tmp_path / "ps_sections.csv").open() as f:
            for row in csv.DictReader(f):
                if row["CourseID"] == "ADV":
                    adv_rooms.append(row["RoomID"])
        assert len(adv_rooms) == len(set(adv_rooms)), (
            f"advisory sections share rooms in export: {adv_rooms}"
        )

    def test_no_inventions_in_export(self, tiny_solved, tmp_path: Path):
        """Every (StudentID, CourseID) in ps_enrollments must correspond to
        a course the student actually requested (rank 1 or rank 2). Catches
        export-time data corruption where a student gets enrolled in
        something they didn't ask for.
        """
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        student_requests: dict[str, set[str]] = {
            stu.student_id: {r.course_id for r in stu.requested_courses}
            for stu in ds.students
        }
        with (tmp_path / "ps_enrollments.csv").open() as f:
            for row in csv.DictReader(f):
                sid, cid = row["StudentID"], row["CourseID"]
                assert cid in student_requests.get(sid, set()), (
                    f"student {sid} got course {cid} without requesting it"
                )

    def test_every_output_id_exists_in_input(self, tiny_solved, tmp_path: Path):
        """Cross-check: every StudentID, TeacherID, RoomID in the export
        must exist in the input dataset. Catches export-time ID corruption.
        """
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        input_students = {s.student_id for s in ds.students}
        input_teachers = {t.teacher_id for t in ds.teachers}
        input_rooms = {r.room_id for r in ds.rooms}
        with (tmp_path / "ps_sections.csv").open() as f:
            for row in csv.DictReader(f):
                assert row["TeacherID"] in input_teachers, f"output teacher {row['TeacherID']} not in input"
                assert row["RoomID"] in input_rooms, f"output room {row['RoomID']} not in input"
        with (tmp_path / "ps_enrollments.csv").open() as f:
            for row in csv.DictReader(f):
                assert row["StudentID"] in input_students, f"output student {row['StudentID']} not in input"
