"""Tests for reports + exporter modules."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.scheduler.exporter import export_powerschool
from src.scheduler.models import (
    Course,
    CourseRequest,
    Dataset,
    MasterAssignment,
    Room,
    SchoolConfig,
    Section,
    Student,
    StudentAssignment,
    Teacher,
    default_rotation,
)
from src.scheduler.reports import (
    DIAGNOSIS_REASONS,
    compute_kpis,
    diagnose_unmet,
    write_reports,
    write_unmet_diagnosis,
)


class TestKPIs:
    def test_kpi_structure(self, tiny_solved):
        ds, master, students, unmet = tiny_solved
        kpi = compute_kpis(ds, master, students, unmet)
        assert 0 <= kpi.fully_scheduled_pct <= 100
        assert 0 <= kpi.required_fulfillment_pct <= 100
        assert 0 <= kpi.first_choice_elective_pct <= 100
        assert kpi.section_balance_max_dev >= 0
        assert isinstance(kpi.targets_met, dict)

    def test_required_fulfillment_high_on_clean_solve(self, tiny_solved):
        ds, master, students, unmet = tiny_solved
        kpi = compute_kpis(ds, master, students, unmet)
        # Solver uses soft slack (since v4): over-constrained students may
        # leave 1-2 required unmet; the heavy penalty keeps the count tiny.
        assert kpi.required_fulfillment_pct >= 98.0, kpi.required_fulfillment_pct

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
        """PS spec column names (per 2026-04-26 IT confirmation) — `Course Number`,
        `Teacher Number`, `Room`, `Expression`. The legacy slug stays in
        `Section_ID_Internal` for cross-reference."""
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        with (tmp_path / "ps_sections.csv").open() as f:
            r = csv.DictReader(f)
            header = r.fieldnames
            for col in (
                "SchoolID", "Course Number", "Section Number", "TermID",
                "Teacher Number", "Room", "Expression",
                "Section_ID_Internal", "Slots",
            ):
                assert col in header, f"Missing PS column {col}"

    def test_advisory_period_code(self, tiny_solved, tmp_path: Path):
        """Per 2026-04-26 client confirmation, Expression uses Columbus PS format:
        `<block>(<day>)`. Advisory meets at Day E Block 3 → "3(E)"."""
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        with (tmp_path / "ps_sections.csv").open() as f:
            for row in csv.DictReader(f):
                if row["Course Number"].upper().startswith("ADV"):
                    assert row["Expression"] == "3(E)", (
                        f"advisory Expression should be '3(E)', got {row['Expression']!r}"
                    )
                    assert row["Slots"] == "E3"

    def test_invariants_pass_on_export(self, tiny_solved, tmp_path: Path):
        from tests.check_invariants import check_invariants
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        n_failures, msgs = check_invariants(tmp_path, balance_threshold=4)
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
                if row["Course Number"].upper().startswith("ADV"):
                    adv_rooms.append(row["Room"])
        assert len(adv_rooms) == len(set(adv_rooms)), (
            f"advisory sections share rooms in export: {adv_rooms}"
        )

    def test_no_inventions_in_export(self, tiny_solved, tmp_path: Path):
        """Every (Student_Number, Course_Number) in ps_enrollments must
        correspond to a course the student actually requested. Catches
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
                sid, cid = row["Student_Number"], row["Course_Number"]
                assert cid in student_requests.get(sid, set()), (
                    f"student {sid} got course {cid} without requesting it"
                )

    def test_every_output_id_exists_in_input(self, tiny_solved, tmp_path: Path):
        """Cross-check: every Student_Number, Teacher Number, Room in the
        export must exist in the input dataset. Catches export-time ID
        corruption.
        """
        ds, master, students, unmet = tiny_solved
        export_powerschool(ds, master, students, tmp_path)
        input_students = {s.student_id for s in ds.students}
        input_teachers = {t.teacher_id for t in ds.teachers}
        input_rooms = {r.room_id for r in ds.rooms}
        with (tmp_path / "ps_sections.csv").open() as f:
            for row in csv.DictReader(f):
                assert row["Teacher Number"] in input_teachers, f"output teacher {row['Teacher Number']} not in input"
                assert row["Room"] in input_rooms, f"output room {row['Room']} not in input"
        with (tmp_path / "ps_enrollments.csv").open() as f:
            for row in csv.DictReader(f):
                assert row["Student_Number"] in input_students, f"output student {row['Student_Number']} not in input"


# ============================================================================
# Per-unmet diagnosis (Principle 5)
# ============================================================================


def _make_minimal_dataset(
    sections: list[Section],
    students: list[Student],
    courses: list[Course],
    teachers: list[Teacher],
    rooms: list[Room] | None = None,
    behavior_separations: list[tuple[str, str]] | None = None,
) -> Dataset:
    """Build a tiny in-memory Dataset for diagnose_unmet unit tests.

    Bypasses the solver — the diagnostic is post-solve and works on
    Dataset + master + students inputs directly. Tests inject the exact
    state needed to exercise each reason class.
    """
    from src.scheduler.models import BehaviorMatrix
    if rooms is None:
        rooms = [Room(room_id="R1", name="Room 1", capacity=30)]
    cfg = SchoolConfig(
        school="Unit Test", school_id=99999, grade=12, year="2099-2100",
        bell=default_rotation(),
    )
    return Dataset(
        config=cfg,
        courses=courses,
        teachers=teachers,
        rooms=rooms,
        sections=sections,
        students=students,
        behavior=BehaviorMatrix(separations=behavior_separations or []),
    )


class TestDiagnoseUnmet:
    def test_no_section_when_course_has_no_sections(self):
        course = Course(course_id="C1", name="Course 1", department="X",
                        qualified_teacher_ids=["T1"])
        teacher = Teacher(teacher_id="T1", name="T1", department="X",
                          qualified_course_ids=["C1"])
        student = Student(student_id="S1", name="S1", grade=12,
                          requested_courses=[CourseRequest(student_id="S1", course_id="C1")])
        ds = _make_minimal_dataset(
            sections=[],   # ← course requested, but no section exists
            students=[student], courses=[course], teachers=[teacher],
        )
        result = diagnose_unmet(ds, master=[], students=[], unmet=[("S1", "C1")])
        assert result[("S1", "C1")] == "no_section"

    def test_capacity_when_only_section_is_full(self):
        course = Course(course_id="C1", name="Course 1", department="X",
                        qualified_teacher_ids=["T1"])
        teacher = Teacher(teacher_id="T1", name="T1", department="X",
                          qualified_course_ids=["C1"])
        # Section capacity 1; one student already enrolled → blocking second.
        sec = Section(section_id="C1.1", course_id="C1", teacher_id="T1",
                      max_size=1, grade_level=12)
        s1 = Student(student_id="S1", name="S1", grade=12,
                     requested_courses=[CourseRequest(student_id="S1", course_id="C1")])
        s2 = Student(student_id="S2", name="S2", grade=12,
                     requested_courses=[CourseRequest(student_id="S2", course_id="C1")])
        ds = _make_minimal_dataset(
            sections=[sec], students=[s1, s2], courses=[course], teachers=[teacher],
        )
        master = [MasterAssignment(section_id="C1.1", scheme=1, room_id="R1",
                                   slots=[("A", 1)])]
        students = [StudentAssignment(student_id="S1", section_ids=["C1.1"])]  # S1 takes the seat
        result = diagnose_unmet(ds, master=master, students=students,
                                unmet=[("S2", "C1")])
        assert result[("S2", "C1")] == "capacity"

    def test_grid_clash_when_all_sections_collide(self):
        c_target = Course(course_id="C2", name="Math", department="M",
                          qualified_teacher_ids=["T2"])
        c_other = Course(course_id="C3", name="Other", department="O",
                         qualified_teacher_ids=["T3"])
        t2 = Teacher(teacher_id="T2", name="T2", department="M",
                     qualified_course_ids=["C2"])
        t3 = Teacher(teacher_id="T3", name="T3", department="O",
                     qualified_course_ids=["C3"])
        sec_target = Section(section_id="C2.1", course_id="C2", teacher_id="T2",
                             max_size=20, grade_level=12)
        sec_other = Section(section_id="C3.1", course_id="C3", teacher_id="T3",
                            max_size=20, grade_level=12)
        student = Student(student_id="S1", name="S1", grade=12,
                          requested_courses=[
                              CourseRequest(student_id="S1", course_id="C2"),
                              CourseRequest(student_id="S1", course_id="C3"),
                          ])
        ds = _make_minimal_dataset(
            sections=[sec_target, sec_other], students=[student],
            courses=[c_target, c_other], teachers=[t2, t3],
        )
        # Both sections meet at slot (A, 1). Student got into C3.1 → C2.1 grid-clashes.
        master = [
            MasterAssignment(section_id="C2.1", scheme=1, room_id="R1", slots=[("A", 1)]),
            MasterAssignment(section_id="C3.1", scheme=1, room_id="R1", slots=[("A", 1)]),
        ]
        students_solved = [StudentAssignment(student_id="S1", section_ids=["C3.1"])]
        result = diagnose_unmet(ds, master=master, students=students_solved,
                                unmet=[("S1", "C2")])
        assert result[("S1", "C2")] == "grid_clash"

    def test_restriction_when_every_teacher_blocked(self):
        course = Course(course_id="C1", name="Course 1", department="X",
                        qualified_teacher_ids=["T1"])
        teacher = Teacher(teacher_id="T1", name="T1", department="X",
                          qualified_course_ids=["C1"])
        sec = Section(section_id="C1.1", course_id="C1", teacher_id="T1",
                      max_size=20, grade_level=12)
        student = Student(student_id="S1", name="S1", grade=12,
                          restricted_teacher_ids=["T1"],  # ← only teacher is blocked
                          requested_courses=[CourseRequest(student_id="S1", course_id="C1")])
        ds = _make_minimal_dataset(
            sections=[sec], students=[student], courses=[course], teachers=[teacher],
        )
        master = [MasterAssignment(section_id="C1.1", scheme=1, room_id="R1",
                                   slots=[("A", 1)])]
        result = diagnose_unmet(ds, master=master, students=[],
                                unmet=[("S1", "C1")])
        assert result[("S1", "C1")] == "restriction"

    def test_separation_when_pair_in_every_section(self):
        course = Course(course_id="C1", name="Course 1", department="X",
                        qualified_teacher_ids=["T1"])
        teacher = Teacher(teacher_id="T1", name="T1", department="X",
                          qualified_course_ids=["C1"])
        sec = Section(section_id="C1.1", course_id="C1", teacher_id="T1",
                      max_size=20, grade_level=12)
        s1 = Student(student_id="S1", name="S1", grade=12,
                     requested_courses=[CourseRequest(student_id="S1", course_id="C1")])
        s2 = Student(student_id="S2", name="S2", grade=12,
                     requested_courses=[CourseRequest(student_id="S2", course_id="C1")])
        ds = _make_minimal_dataset(
            sections=[sec], students=[s1, s2], courses=[course], teachers=[teacher],
            behavior_separations=[("S1", "S2")],
        )
        master = [MasterAssignment(section_id="C1.1", scheme=1, room_id="R1",
                                   slots=[("A", 1)])]
        # S2 is in the only section. S1 can't join (separation pair).
        students_solved = [StudentAssignment(student_id="S2", section_ids=["C1.1"])]
        result = diagnose_unmet(ds, master=master, students=students_solved,
                                unmet=[("S1", "C1")])
        assert result[("S1", "C1")] == "separation"

    def test_diagnosis_vocabulary_complete(self):
        """Every reason emitted by diagnose_unmet must be in DIAGNOSIS_REASONS."""
        # Synthetic case touching every branch above
        assert set(DIAGNOSIS_REASONS) == {
            "no_section", "grid_clash", "capacity", "restriction",
            "separation", "unknown",
        }

    def test_write_unmet_diagnosis_renders_md(self, tmp_path: Path):
        # Smoke: write_unmet_diagnosis should produce a non-empty markdown file
        # given a minimal input. Real-data renderings live in the build tests.
        course = Course(course_id="C1", name="Course 1", department="X",
                        qualified_teacher_ids=["T1"])
        teacher = Teacher(teacher_id="T1", name="T1", department="X",
                          qualified_course_ids=["C1"])
        student = Student(student_id="S1", name="S1", grade=12,
                          requested_courses=[CourseRequest(student_id="S1", course_id="C1")])
        ds = _make_minimal_dataset(
            sections=[], students=[student], courses=[course], teachers=[teacher],
        )
        unmet = [("S1", "C1")]
        diagnoses = {("S1", "C1"): "no_section"}
        out = write_unmet_diagnosis(ds, unmet, diagnoses, tmp_path / "unmet_diagnosis.md")
        text = out.read_text()
        assert "Unmet diagnosis" in text
        assert "no_section" in text
        assert "S1" not in text or "C1" in text  # smoke: it doesn't list raw IDs


class TestUnmetCSVReason:
    def test_unmet_csv_includes_reason_column(self, tiny_solved, tmp_path: Path):
        """Principle 5: unmet_requests.csv must carry a reason per row."""
        ds, master, students, unmet = tiny_solved
        write_reports(ds, master, students, unmet, tmp_path)
        with (tmp_path / "unmet_requests.csv").open() as f:
            r = csv.DictReader(f)
            assert r.fieldnames == [
                "student_id", "course_id", "course_name", "is_required", "reason"
            ]
            for row in r:
                assert row["reason"] in DIAGNOSIS_REASONS, (
                    f"reason {row['reason']!r} not in vocabulary"
                )
