"""Tests for the real-data PowerSchool ingester.

Skipped if the real Columbus xlsx files aren't reachable on this machine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.scheduler.ps_ingest import (
    _id_str,
    build_dataset_from_columbus,
    read_columbus_course_demand,
    read_columbus_groupings,
    read_columbus_listado_maestro,
    read_columbus_student_requests,
    read_ps_enrollment_csv,
)
from src.scheduler.validate import validate_dataset


# Path setup — try the original Linux/Downloads location first, then the
# repo-mirrored `reference/` dir (used in handoff packages). Skip the marker
# only if neither is reachable.
_LINUX_DIR = Path("/home/hector/Downloads/2026-04-24 - Idea - motor de horarios/adjuntos")
_REPO_DIR = Path(__file__).resolve().parent.parent.parent / "reference"


def _find_first(*candidates: Path) -> Path | None:
    for p in candidates:
        if p.exists():
            return p
    return None


DEMAND_FILE = _find_first(
    _LINUX_DIR / "1._STUDENTS_PER_COURSE_2026-2027---c22bbfa2-7fc5-4d1e-bce4-4638e9c3a1fd.xlsx",
    _REPO_DIR / "rfi_1._STUDENTS_PER_COURSE_2026-2027.xlsx",
) or _LINUX_DIR / "missing.xlsx"

SCHEDULE_FILE = _find_first(
    _LINUX_DIR / "HS_Schedule_25-26---0a1ea20d-8b19-44ac-a39d-f7d0b50db399.xlsx",
    _REPO_DIR / "rfi_HS_Schedule_25-26.xlsx",
) or _LINUX_DIR / "missing.xlsx"

ENROLLMENT_CSV = _find_first(
    Path("/home/hector/Downloads/enrollments-export-69dedeb208e46.csv"),
    _REPO_DIR / "sample_real_enrollments.csv",
) or Path("/dev/null/missing.csv")

real_data = pytest.mark.skipif(
    not DEMAND_FILE.exists(),
    reason="Real Columbus data not available on this machine",
)


class TestIdNormalization:
    def test_int_string_unchanged(self):
        assert _id_str("28025") == "28025"

    def test_float_with_trailing_zero(self):
        assert _id_str(28025.0) == "28025"

    def test_empty(self):
        assert _id_str(None) == ""
        assert _id_str("") == ""

    def test_username_format(self):
        assert _id_str("arodriguez789*") == "arodriguez789*"


class TestPSEnrollmentCSV:
    @real_data
    def test_reads_real_csv(self):
        rows = read_ps_enrollment_csv(ENROLLMENT_CSV)
        assert len(rows) > 100  # 11k+ rows in real file
        # Check schema: every row has the canonical fields
        for r in rows[:10]:
            assert r.student_id
            assert r.course_id
            assert r.section_id


class TestParseGradeArg:
    def test_int_string(self):
        from src.scheduler.cli import _parse_grade_arg
        assert _parse_grade_arg("12") == 12

    def test_csv(self):
        from src.scheduler.cli import _parse_grade_arg
        assert _parse_grade_arg("9,10,11,12") == [9, 10, 11, 12]

    def test_csv_unsorted_dedup(self):
        from src.scheduler.cli import _parse_grade_arg
        assert _parse_grade_arg("12, 9, 11, 12") == [9, 11, 12]

    def test_all_hs_shorthand(self):
        from src.scheduler.cli import _parse_grade_arg
        assert _parse_grade_arg("all-hs") == [9, 10, 11, 12]
        assert _parse_grade_arg("hs") == [9, 10, 11, 12]
        assert _parse_grade_arg("ALL") == [9, 10, 11, 12]


class TestColumbusXlsxReaders:
    @real_data
    def test_course_demand_reads(self):
        demand = read_columbus_course_demand(DEMAND_FILE)
        assert len(demand) > 10
        assert all(d.course_name for d in demand)

    @real_data
    def test_listado_reads(self):
        rows = read_columbus_listado_maestro(DEMAND_FILE)
        assert len(rows) > 10
        assert all(r.course_name and r.teacher_name for r in rows)

    @real_data
    def test_student_requests_use_id_column(self):
        rows = read_columbus_student_requests(DEMAND_FILE)
        # IDs should be strings, normalized (no '.0' suffix)
        for r in rows[:10]:
            assert "." not in r.student_id, f"ID {r.student_id} has '.0' suffix"

    @real_data
    def test_groupings_match_request_ids(self):
        # The whole point of the ID-column fix: request student_ids should overlap
        # with grouping student_ids
        reqs = read_columbus_student_requests(DEMAND_FILE)
        grps = read_columbus_groupings(SCHEDULE_FILE)
        req_ids = {r.student_id for r in reqs}
        grp_ids = {g.student_a_id for g in grps} | {g.student_b_id for g in grps}
        # At least some overlap is expected
        overlap = req_ids & grp_ids
        assert len(overlap) > 0, "No overlap between request IDs and grouping IDs"


class TestEndToEndIngest:
    @real_data
    def test_grade_12_validates_clean(self):
        ds = build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=12)
        rep = validate_dataset(ds)
        assert rep.score == 100, f"Real Columbus Grade-12 doesn't validate clean: {rep.summary()}"

    @real_data
    def test_grade_12_has_groupings(self):
        ds = build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=12)
        # We expect SOME separations/groupings to match (at least 1)
        assert len(ds.behavior.separations) + len(ds.behavior.groupings) > 0


class TestMultiGradeIngest:
    @real_data
    def test_full_hs_validates_clean(self):
        ds = build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=[9, 10, 11, 12])
        rep = validate_dataset(ds)
        assert rep.score == 100, f"Real Columbus full-HS doesn't validate clean: {rep.summary()}"

    @real_data
    def test_full_hs_has_all_four_grades(self):
        ds = build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=[9, 10, 11, 12])
        grades_present = {s.grade for s in ds.students}
        assert grades_present == {9, 10, 11, 12}, f"missing grades: {grades_present}"

    @real_data
    def test_full_hs_student_count_matches_per_grade_sum(self):
        per_grade = {g: len(build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=g).students) for g in (9, 10, 11, 12)}
        full = build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=[9, 10, 11, 12])
        assert len(full.students) == sum(per_grade.values()), (
            f"full-HS student count {len(full.students)} != sum of per-grade {sum(per_grade.values())}"
        )

    @real_data
    def test_full_hs_courses_span_multiple_grades(self):
        ds = build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=[9, 10, 11, 12])
        # At least some courses should be requested by >1 grade
        cross_grade = [c for c in ds.courses if len(c.grade_eligibility) > 1]
        assert len(cross_grade) >= 5, f"expected ≥5 cross-grade courses, got {len(cross_grade)}"

    @real_data
    def test_full_hs_keeps_strict_max_consecutive_with_per_teacher_override(self, capsys):
        """Per client confirmation 2026-04-26, the global cap is 4. The 3
        teachers with ≥7 academic sections (pigeonhole-infeasible at strict 4)
        get a per-teacher override to 5 via `Teacher.max_consecutive_classes=5`.
        Updated 2026-04-28 from a global override after client reported other
        teachers with 5 consecutive blocks (Castañeda Día C).
        """
        ds = build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=[9, 10, 11, 12])
        assert ds.config.hard.max_consecutive_classes == 4
        captured = capsys.readouterr()
        assert "carry ≥7 academic sections" in captured.err
        assert "per-teacher max_consecutive_classes=5" in captured.err
        # Exactly 3 teachers should have the override applied
        overridden = [t for t in ds.teachers if t.max_consecutive_classes == 5]
        assert len(overridden) == 3, f"expected exactly 3 teacher overrides, got {len(overridden)}"
        # All other teachers should have None (use default 4)
        non_overridden = [t for t in ds.teachers if t.max_consecutive_classes is None]
        assert len(non_overridden) == len(ds.teachers) - 3

    @real_data
    def test_grade_12_only_keeps_default_max_consecutive(self):
        """Single Grade-12 keeps the default 4."""
        ds = build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=12)
        assert ds.config.hard.max_consecutive_classes == 4

    @real_data
    def test_full_hs_assigns_home_rooms_from_listado(self):
        """HC4 prep: every teacher with a single-room entry in LISTADO MAESTRO
        gets that room as their home_room_id. 41/43 real teachers have unique
        rooms; the rest land on the first observed room (deterministic)."""
        ds = build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=[9, 10, 11, 12])
        teachers_with_home = [t for t in ds.teachers if t.home_room_id is not None]
        # Most real teachers should have a home room set
        assert len(teachers_with_home) >= 0.8 * len(ds.teachers), (
            f"expected ≥80% of teachers to have home_room set, got "
            f"{len(teachers_with_home)}/{len(ds.teachers)}"
        )
        # Every home_room_id must be a real room in the dataset
        room_ids = {r.room_id for r in ds.rooms}
        for t in teachers_with_home:
            assert t.home_room_id in room_ids, (
                f"teacher {t.name} home_room_id={t.home_room_id} not in dataset rooms"
            )

    @real_data
    def test_back_compat_int_grade_arg(self):
        """Passing grade=12 (int) still works the same as before the multi-grade change."""
        ds = build_dataset_from_columbus(DEMAND_FILE, SCHEDULE_FILE, grade=12)
        assert all(s.grade == 12 for s in ds.students)
        assert ds.config.grade == 12
