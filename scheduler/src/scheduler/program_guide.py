"""Program Guide loader & classifier (v4.28.18+).

Lee el YAML `data/program_guide_2026-2027.yaml` que codifica el PDF
oficial del Colegio (HS Program Guide), y expone helpers para:

  - classify_course(grade, course_id) → 'required' | 'optative' | 'elective' | 'unknown'
  - is_required_for_student(grade, course_id) → bool (True si required O optative)
  - validate_student_coverage(student, requested_course_ids) → list[CoverageIssue]

Filosofía:
  - Required del PDF = todos los estudiantes lo toman
  - Optative del PDF = obligatorio pero hay opciones por área; cada
    estudiante toma UN curso por área. Para el motor, ese UN curso
    SE TRATA COMO REQUIRED (porque para ese estudiante específico es
    obligatorio).
  - Elective del PDF = opcional, máximo 1 por estudiante.

Ver `MANUAL_REGLAS.md` sección XX para más detalle.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal


DEFAULT_GUIDE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "program_guide_2026-2027.yaml"


@dataclass(frozen=True)
class GradeProgram:
    """Estructura del programa para un grado específico."""
    grade: int
    required: list[str]
    optative_areas: dict[str, list[str]]  # area_name → [course_ids]
    electives: list[str]


@dataclass(frozen=True)
class CoverageIssue:
    """Un problema de cobertura detectado al validar requests vs program guide."""
    student_id: str
    grade: int
    severity: Literal["error", "warning"]
    code: str  # e.g., "missing_required", "missing_optative_area", "extra_electives"
    message: str


class ProgramGuide:
    """Encapsula el program guide del Colegio."""

    def __init__(self, programs: dict[int, GradeProgram]):
        self._programs = programs

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> "ProgramGuide":
        """Carga el guide desde YAML. Si path es None, usa el default."""
        # Use simple regex-based loader to avoid PyYAML dependency
        # (pure Python, since the YAML structure is restricted)
        path = path or DEFAULT_GUIDE_PATH
        if not path.exists():
            raise FileNotFoundError(f"Program guide YAML no encontrado: {path}")
        return cls._parse_yaml(path.read_text(encoding="utf-8"))

    @classmethod
    def _parse_yaml(cls, content: str) -> "ProgramGuide":
        """Parser tolerante de YAML.

        Acepta solo el subset estructural que usamos:
          - Top-level: integer keys (9, 10, 11, 12)
          - Each grade has: required (list), optative_areas (mapping of area→list),
            electives (list).
          - List items son strings (codes).
          - Comments con '#' se ignoran.
        """
        try:
            import yaml as _yaml
            data = _yaml.safe_load(content)
        except ImportError:
            # Fallback minimal parser if PyYAML not available
            data = _minimal_yaml_parse(content)

        programs: dict[int, GradeProgram] = {}
        for grade_key, grade_data in (data or {}).items():
            try:
                grade = int(grade_key)
            except (TypeError, ValueError):
                continue
            if not isinstance(grade_data, dict):
                continue
            required = [str(c).strip() for c in (grade_data.get("required") or [])]
            optative_areas: dict[str, list[str]] = {}
            for area_name, area_courses in (grade_data.get("optative_areas") or {}).items():
                optative_areas[str(area_name)] = [str(c).strip() for c in (area_courses or [])]
            electives = [str(c).strip() for c in (grade_data.get("electives") or [])]
            programs[grade] = GradeProgram(
                grade=grade,
                required=required,
                optative_areas=optative_areas,
                electives=electives,
            )
        return cls(programs)

    def grades(self) -> list[int]:
        return sorted(self._programs.keys())

    def get(self, grade: int) -> GradeProgram | None:
        return self._programs.get(grade)

    def classify_course(
        self, grade: int, course_id: str
    ) -> Literal["required", "optative", "elective", "unknown"]:
        """Devuelve la categoría del curso para el grado dado."""
        program = self._programs.get(grade)
        if program is None:
            return "unknown"
        if course_id in program.required:
            return "required"
        for area_courses in program.optative_areas.values():
            if course_id in area_courses:
                return "optative"
        if course_id in program.electives:
            return "elective"
        return "unknown"

    def is_required_for_student(self, grade: int, course_id: str) -> bool:
        """True si el curso es required o optative — ambos son obligatorios
        para el estudiante específico que los pidió."""
        cat = self.classify_course(grade, course_id)
        return cat in ("required", "optative")

    def find_optative_area(self, grade: int, course_id: str) -> str | None:
        """Si el curso es optative, devuelve el nombre del área. Sino None."""
        program = self._programs.get(grade)
        if program is None:
            return None
        for area_name, area_courses in program.optative_areas.items():
            if course_id in area_courses:
                return area_name
        return None

    def validate_student_coverage(
        self,
        student_id: str,
        grade: int,
        requested_course_ids: Iterable[str],
    ) -> list[CoverageIssue]:
        """Valida que el estudiante haya pedido:
          - Todos los Required del grado
          - Al menos UN curso por cada área Optative del grado
          - Máximo UN curso de Electives

        Devuelve lista de issues. Vacía si todo OK.
        """
        program = self._programs.get(grade)
        if program is None:
            return [CoverageIssue(
                student_id=student_id,
                grade=grade,
                severity="warning",
                code="grade_not_in_guide",
                message=f"Grado {grade} no está en el program guide",
            )]

        requested = set(requested_course_ids)
        issues: list[CoverageIssue] = []

        # Required: cada uno debe estar
        for course_id in program.required:
            if course_id not in requested:
                issues.append(CoverageIssue(
                    student_id=student_id,
                    grade=grade,
                    severity="error",
                    code="missing_required",
                    message=f"Falta curso REQUIRED `{course_id}` (todos los G{grade} lo deben tomar)",
                ))

        # Optative areas: al menos 1 curso de cada área
        for area_name, area_courses in program.optative_areas.items():
            if not any(c in requested for c in area_courses):
                issues.append(CoverageIssue(
                    student_id=student_id,
                    grade=grade,
                    severity="error",
                    code="missing_optative_area",
                    message=f"No pidió ningún curso del área OPTATIVE `{area_name}` "
                            f"(opciones: {', '.join(area_courses[:3])}…)",
                ))

        # Electives: máximo 1.
        # Heurística: un curso cuenta como ELECTIVE si está en program.electives
        # PERO NO está en ningún optative_area (para evitar falsos positivos
        # cuando un curso aparece en ambas listas del PDF).
        all_optative_codes: set[str] = set()
        for area_courses in program.optative_areas.values():
            all_optative_codes.update(area_courses)
        electives_picked = [
            c for c in requested
            if c in program.electives and c not in all_optative_codes
        ]
        if len(electives_picked) > 1:
            issues.append(CoverageIssue(
                student_id=student_id,
                grade=grade,
                severity="warning",
                code="multiple_electives",
                message=f"Pidió {len(electives_picked)} electives ({', '.join(electives_picked[:3])}); "
                        f"el PDF dice 'máximo UNO'",
            ))

        return issues


def _minimal_yaml_parse(content: str) -> dict:
    """Parser mínimo de YAML para nuestro subset (no requiere PyYAML).

    Soporta:
      - top-level integer keys (9: ...)
      - nested keys (required:, optative_areas:, electives:)
      - lists (- ITEM)
      - comments (# ...)
    No soporta: anchors, flows, multi-line strings, etc.
    """
    result: dict = {}
    lines = content.split("\n")
    grade_key: int | None = None
    section_key: str | None = None  # required / optative_areas / electives
    area_key: str | None = None      # nombre del área dentro de optative_areas

    for raw in lines:
        # Strip comments
        if "#" in raw:
            raw = raw.split("#", 1)[0]
        line = raw.rstrip()
        if not line.strip():
            continue
        # Indent level (multiplo de 2 spaces)
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)

        # Top-level integer key (grade)
        if indent == 0 and stripped.endswith(":"):
            try:
                grade_key = int(stripped[:-1])
                result[grade_key] = {"required": [], "optative_areas": {}, "electives": []}
                section_key = None
                area_key = None
                continue
            except ValueError:
                pass

        # Section under grade
        if indent == 2 and stripped.endswith(":") and grade_key is not None:
            section_key = stripped[:-1].strip()
            area_key = None
            if section_key == "optative_areas":
                result[grade_key]["optative_areas"] = {}
            elif section_key in ("required", "electives"):
                result[grade_key][section_key] = []
            continue

        # Empty list (e.g., `electives: []`)
        if indent == 2 and ":" in stripped and stripped.endswith("[]"):
            section_key = stripped.split(":", 1)[0].strip()
            result[grade_key][section_key] = []
            continue

        # Area within optative_areas
        if indent == 4 and stripped.endswith(":") and section_key == "optative_areas" and grade_key is not None:
            area_key = stripped[:-1].strip()
            result[grade_key]["optative_areas"][area_key] = []
            continue

        # List item
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if grade_key is not None:
                if section_key == "required":
                    result[grade_key]["required"].append(item)
                elif section_key == "electives":
                    result[grade_key]["electives"].append(item)
                elif section_key == "optative_areas" and area_key is not None:
                    result[grade_key]["optative_areas"][area_key].append(item)

    return result
