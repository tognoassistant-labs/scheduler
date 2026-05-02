"""Tests for ProgramGuide loader & classifier (v4.28.18)."""
from __future__ import annotations

import pytest

from src.scheduler.program_guide import ProgramGuide


@pytest.fixture
def guide() -> ProgramGuide:
    """Carga el YAML real del repo."""
    return ProgramGuide.from_yaml()


def test_yaml_loads_all_4_grades(guide: ProgramGuide) -> None:
    assert guide.grades() == [9, 10, 11, 12]


def test_classify_required_courses(guide: ProgramGuide) -> None:
    # G9 required del PDF
    assert guide.classify_course(9, "A0901") == "required"  # Biology 9
    assert guide.classify_course(9, "H0904") == "required"  # English 9
    assert guide.classify_course(9, "E0901") == "required"  # PE 9
    assert guide.classify_course(9, "B0901") == "required"  # Social Studies 9


def test_classify_optatives(guide: ProgramGuide) -> None:
    # G9 Math optatives — PDF dice "Algebra I or Geometry"
    assert guide.classify_course(9, "I0903") == "optative"
    assert guide.classify_course(9, "I1003") == "optative"
    # G9 Spanish: PDF lista "Lit o FL". El YAML lo refleja como optative.
    # is_required_for_student devuelve True (es obligatorio para el estudiante).
    assert guide.classify_course(9, "G0901") == "optative"
    assert guide.is_required_for_student(9, "G0901") is True
    assert guide.classify_course(9, "G0902") == "optative"
    # G10 Math optatives
    assert guide.classify_course(10, "I1003") == "optative"  # Geometry
    assert guide.classify_course(10, "I1211") == "optative"  # AP Precalc


def test_classify_unknown_course(guide: ProgramGuide) -> None:
    assert guide.classify_course(9, "FAKE_CODE") == "unknown"
    assert guide.classify_course(99, "A0901") == "unknown"  # bad grade


def test_is_required_for_student(guide: ProgramGuide) -> None:
    # required → True
    assert guide.is_required_for_student(9, "A0901") is True
    # optative → True (es obligatorio para ese estudiante)
    assert guide.is_required_for_student(9, "I0903") is True
    # elective → False
    cat = guide.classify_course(10, "OZ1207")  # Anatomy (elective in G10)
    assert cat == "elective"
    assert guide.is_required_for_student(10, "OZ1207") is False


def test_find_optative_area(guide: ProgramGuide) -> None:
    assert guide.find_optative_area(9, "I0903") == "Math"
    assert guide.find_optative_area(9, "OC1305") == "Art"
    assert guide.find_optative_area(9, "A0901") is None  # required, no area


def test_validate_coverage_complete_student(guide: ProgramGuide) -> None:
    """Estudiante de G9 que pidió todo lo necesario — sin issues."""
    requested = [
        "A0901",  # Biology 9 (req)
        "H0904",  # English 9 (req)
        "B0901",  # Social Studies 9 (req)
        "E0901",  # PE 9 (req)
        "G0901",  # Spanish Lit 9 (optative-Spanish)
        "I0903",  # Algebra I (optative-Math)
        "J0901",  # Technology 9 (optative-Tech)
        "OC1305", # Painting I (optative-Art)
    ]
    issues = guide.validate_student_coverage("S1", 9, requested)
    # Filtro warnings que no son errores reales de cobertura
    real_issues = [i for i in issues if i.severity == "error"]
    assert real_issues == [], f"Esperaba sin errors pero llegaron: {real_issues}"


def test_validate_coverage_missing_optative_area(guide: ProgramGuide) -> None:
    """Estudiante de G9 que NO pidió Tech — debe detectar missing_optative_area."""
    requested = [
        "A0901", "H0904", "B0901", "E0901",  # required
        "G0901", "I0903",  # spanish + math
        # falta tech y art
    ]
    issues = guide.validate_student_coverage("S2", 9, requested)
    codes = [i.code for i in issues]
    assert "missing_optative_area" in codes
    # Debe haber al menos 2 (Tech, Art)
    assert sum(1 for c in codes if c == "missing_optative_area") >= 2


def test_validate_coverage_missing_required(guide: ProgramGuide) -> None:
    """Estudiante de G9 que NO pidió Biology — error."""
    requested = ["H0904", "B0901", "E0901", "G0901", "I0903", "J0901", "OC1305"]
    issues = guide.validate_student_coverage("S3", 9, requested)
    codes = [i.code for i in issues]
    assert "missing_required" in codes


def test_validate_unknown_grade(guide: ProgramGuide) -> None:
    issues = guide.validate_student_coverage("S4", 99, [])
    assert len(issues) == 1
    assert issues[0].code == "grade_not_in_guide"
