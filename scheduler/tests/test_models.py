"""Tests for the Pydantic data models."""
from __future__ import annotations

import pytest

from src.scheduler.models import (
    BellSchedule,
    Course,
    HardConstraints,
    Room,
    RoomType,
    Section,
    SoftConstraintWeights,
    Teacher,
    default_rotation,
)


class TestBellSchedule:
    def test_default_rotation_has_25_cells(self):
        bell = default_rotation()
        assert len(bell.rotation) == 25

    def test_advisory_at_e3(self):
        bell = default_rotation()
        assert bell.scheme_at("E", 3) == "ADVISORY"

    def test_each_scheme_has_exactly_3_slots(self):
        bell = default_rotation()
        for k in range(1, 9):
            slots = bell.slots_for_scheme(k)
            assert len(slots) == 3, f"Scheme {k} has {len(slots)} slots, expected 3"

    def test_no_scheme_overlap(self):
        bell = default_rotation()
        seen: set[tuple[str, int]] = set()
        for cell in bell.rotation:
            key = (cell.day, cell.block)
            assert key not in seen, f"Duplicate cell {key}"
            seen.add(key)


class TestSection:
    def test_locked_scheme_default_none(self):
        s = Section(section_id="X.1", course_id="X", teacher_id="T1")
        assert s.locked_scheme is None
        assert s.locked_room_id is None

    def test_locked_scheme_int(self):
        s = Section(section_id="X.1", course_id="X", teacher_id="T1", locked_scheme=5)
        assert s.locked_scheme == 5

    def test_locked_scheme_advisory(self):
        s = Section(section_id="X.1", course_id="X", teacher_id="T1", locked_scheme="ADVISORY")
        assert s.locked_scheme == "ADVISORY"


class TestTeacher:
    def test_preferences_default_empty(self):
        t = Teacher(teacher_id="T1", name="X", department="d")
        assert t.preferred_course_ids == []
        assert t.avoid_course_ids == []
        assert t.preferred_blocks == []
        assert t.avoid_blocks == []

    def test_preferences_settable(self):
        t = Teacher(
            teacher_id="T1", name="X", department="d",
            preferred_course_ids=["MATH"], preferred_blocks=[1, 2],
        )
        assert t.preferred_course_ids == ["MATH"]
        assert t.preferred_blocks == [1, 2]


class TestCourse:
    def test_prerequisites_default_empty(self):
        c = Course(course_id="X", name="X", department="d")
        assert c.prerequisite_course_ids == []

    def test_prerequisites_settable(self):
        c = Course(course_id="CALC", name="Calculus", department="math",
                   prerequisite_course_ids=["ALG2"])
        assert c.prerequisite_course_ids == ["ALG2"]


class TestHardConstraints:
    def test_defaults(self):
        h = HardConstraints()
        assert h.max_class_size == 25
        assert h.ap_research_max_size == 26
        assert h.max_consecutive_classes == 4
        assert h.advisory_day == "E"
        assert h.advisory_block == 3
        assert h.max_section_spread_per_course == 5


class TestSoftConstraintWeights:
    def test_co_planning_off_by_default(self):
        s = SoftConstraintWeights()
        assert s.co_planning == 0  # documented: off by default

    def test_singleton_separation_off_by_default(self):
        s = SoftConstraintWeights()
        assert s.singleton_separation == 0


class TestRoom:
    def test_default_room_type(self):
        r = Room(room_id="R1", name="Room 1")
        assert r.room_type == RoomType.STANDARD


class TestRoomType:
    def test_enum_values(self):
        assert RoomType.STANDARD.value == "standard"
        assert RoomType.SCIENCE_LAB.value == "science_lab"
