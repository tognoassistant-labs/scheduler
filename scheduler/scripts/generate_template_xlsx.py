"""Genera plantillas xlsx vacías para que el coordinador entienda el schema
esperado por el motor.

Genera 2 plantillas:
  1. plantilla_legacy.xlsx — formato `1._STUDENTS_PER_COURSE_*.xlsx`
     (es lo que el uploader 'xlsx real de Columbus' espera)
  2. plantilla_v5.xlsx — formato consolidado `schedule_master_data_hs.xlsx`
     (todavía NO soportado en la UI directamente, pero útil como referencia)

Uso:
    .venv/bin/python scripts/generate_template_xlsx.py --out data/templates/

Las plantillas tienen:
  - Headers correctos en la primera fila
  - 1-3 filas de datos DUMMY (ej: 'STUDENT_001', '999.99') — no datos reales
  - Comentarios en celdas para explicar columnas críticas
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.comments import Comment


HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
DUMMY_FILL = PatternFill(start_color="FFF8DC", end_color="FFF8DC", fill_type="solid")


def _add_sheet(wb: Workbook, name: str, headers: list[str],
               example_rows: list[list], notes: dict[int, str] | None = None) -> None:
    """Helper para agregar una hoja con headers + ejemplos + comentarios."""
    ws = wb.create_sheet(name)
    # Header row
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col_idx, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if notes and col_idx in notes:
            c.comment = Comment(notes[col_idx], "Plantilla")
    # Example rows
    for row_idx, row in enumerate(example_rows, start=2):
        for col_idx, val in enumerate(row, start=1):
            cc = ws.cell(row=row_idx, column=col_idx, value=val)
            cc.fill = DUMMY_FILL
    # Auto-fit-ish — set width based on header length
    for col_idx, h in enumerate(headers, start=1):
        ws.column_dimensions[chr(64 + col_idx) if col_idx <= 26 else f"A{chr(64 + col_idx - 26)}"].width = max(15, len(h) + 2)


def generate_legacy_template(out_path: Path) -> None:
    """Plantilla en formato legacy (`1._STUDENTS_PER_COURSE_*.xlsx`)."""
    wb = Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Hoja 1: UPDATED MARCH 20 - COURSE_GRADE (la crítica)
    _add_sheet(
        wb,
        "UPDATED MARCH 20 - COURSE_GRADE",
        headers=["Student_Number", "Student_Name", "Grade", "Course_Number_1",
                 "Course_Number_2", "Course_Number_3", "Course_Number_4",
                 "Course_Number_5", "Course_Number_6", "Course_Number_7",
                 "Course_Number_8"],
        example_rows=[
            ["STD_DUMMY_001", "Apellido Apellido, Nombre Nombre", 12,
             "E1201", "I1208", "L1304", "G1202", "OZ1313", "OB1532",
             "OJ1306", "ADV.12"],
            ["STD_DUMMY_002", "Otro Otro, Persona Persona", 12,
             "E1201", "I1208", "OZ1313", "G1202", "ADV.12", "L1304",
             "OB1532", "OJ1306"],
        ],
        notes={
            1: "ID único del estudiante. Usar el Student_Number de PowerSchool.",
            2: "Formato: 'APELLIDOS, NOMBRES'. Acentos OK.",
            3: "Grado del año NUEVO (no el actual). Valores válidos: 9, 10, 11, 12.",
            4: "Course_Number_1..N son los cursos solicitados, EN ORDEN DE PREFERENCIA. "
               "Course_Number_1 es la primera opción.",
        },
    )

    # Hoja 2: LISTADO MAESTRO CURSOS Y SECCIO
    _add_sheet(
        wb,
        "LISTADO MAESTRO CURSOS Y SECCIO",
        headers=["Course_Number", "Course_Name", "Sections_To_Offer", "Max_Class_Size",
                 "Department", "Teacher_1", "Teacher_2", "Teacher_3", "Teacher_4"],
        example_rows=[
            ["E1201", "Physical Education and Health 12", 4, 25, "PE",
             "BETANCUR LOPEZ", "RAMIREZ GOMEZ", "", ""],
            ["I1208", "AP Calculus AB", 2, 25, "Math",
             "BERRIO GUZMAN", "", "", ""],
            ["OB1532", "AP Research", 1, 26, "AP_Capstone",
             "BUTTERWORTH EMILY", "", "", ""],
        ],
        notes={
            1: "Course_Number debe coincidir EXACTAMENTE con los del Student requests.",
            3: "Cuántas secciones se van a abrir de este curso.",
            4: "Capacidad máxima por sección. Default 25 (AP Research excepción 26).",
            6: "Apellido(s) y nombre del teacher principal. Hasta 4 teachers por curso.",
        },
    )

    # Hoja 3: CO PLANNING INFO (opcional pero recomendada)
    _add_sheet(
        wb,
        "CO PLANNING INFO",
        headers=["Group_Name", "Teacher_1", "Teacher_2", "Teacher_3", "Teacher_4",
                 "Teacher_5", "Notes"],
        example_rows=[
            ["Math_Coordination", "BERRIO GUZMAN", "GARCIA LOPEZ", "MARTINEZ SOLO",
             "", "", "Reunión semanal de coordinación matemáticas"],
            ["Science_Lab_Group", "BUTTERWORTH EMILY", "RAMIREZ GOMEZ", "", "", "",
             "Coordinación de uso de laboratorios"],
        ],
        notes={
            1: "Nombre arbitrario del grupo (libre).",
            2: "Lista de teachers que necesitan tiempo común libre. Hasta 5.",
        },
    )

    # Hoja 4: Teacher courses
    _add_sheet(
        wb,
        "Teacher courses",
        headers=["Teacher_Name", "Qualified_Courses", "Department", "Max_Load", "Notes"],
        example_rows=[
            ["BERRIO GUZMAN", "I1208;I1209;I1210", "Math", 5,
             "Calculus, Pre-Calc, Algebra II"],
            ["BETANCUR LOPEZ", "E1201;E1101;E1001;E0901", "PE", 5,
             "PE todos los grados"],
        ],
        notes={
            2: "Lista pipe-delimited (separada por ; o |) de Course_Numbers que el teacher puede dictar.",
            4: "Máximo de secciones que el teacher puede dictar por ciclo. Default 5.",
        },
    )

    # Crear hoja de README al inicio
    ws_readme = wb.create_sheet("README", 0)
    readme_lines = [
        ["PLANTILLA — formato legacy (1._STUDENTS_PER_COURSE_*.xlsx)"],
        [""],
        ["Esta plantilla es solo de referencia. La fila 2 de cada hoja muestra"],
        ["datos DUMMY de ejemplo (color crema). Reemplázalos por tus datos reales."],
        [""],
        ["Hojas en este archivo:"],
        ["  1. UPDATED MARCH 20 - COURSE_GRADE — solicitudes por estudiante (crítica)"],
        ["  2. LISTADO MAESTRO CURSOS Y SECCIO — secciones, teachers, salas"],
        ["  3. CO PLANNING INFO — grupos de teachers que comparten free time"],
        ["  4. Teacher courses — calificaciones por teacher"],
        [""],
        ["Hover sobre las celdas con triángulo rojo para ver explicaciones"],
        ["de cada columna."],
        [""],
        ["⚠️ El motor también espera otras hojas opcionales por departamento:"],
        ["    Math Final March 20, English Final March 20, Science Final March 20, etc."],
        ["Para producción del Colegio, la plantilla está incompleta — pídele a IT"],
        ["el archivo legacy completo del año pasado como base."],
        [""],
        ["Generado por scripts/generate_template_xlsx.py — v4.27.23"],
    ]
    for r, line in enumerate(readme_lines, start=1):
        ws_readme.cell(row=r, column=1, value=line[0])
    ws_readme.column_dimensions["A"].width = 80

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    print(f"✓ {out_path}")


def generate_v5_template(out_path: Path) -> None:
    """Plantilla en formato consolidado v5 (`schedule_master_data_hs.xlsx`)."""
    wb = Workbook()
    wb.remove(wb.active)

    # Sheet: courses
    _add_sheet(wb, "courses",
        headers=["DCID", "ID", "COURSE_NUMBER", "COURSE_NAME", "CREDIT_HOURS",
                 "SCHOOLID", "MAXCLASSSIZE", "REGCOURSEGROUP", "SECTIONSTOOFFER", "SCHED_FREQUENCY"],
        example_rows=[
            [1101, 1101, "E1201", "Physical Education and Health 12", 1.0,
             13000, 25, "PE", 4, 3],
            [1102, 1102, "I1208", "AP Calculus AB", 1.0, 13000, 25, "Math", 2, 3],
            [1103, 1103, "OB1532", "AP Research", 1.0, 13000, 26, "AP_Capstone", 1, 3],
        ],
        notes={3: "Course code único.", 7: "Capacidad máx (AP Research = 26)."},
    )

    # Sheet: rooms
    _add_sheet(wb, "rooms",
        headers=["DCID", "ID", "DESCRIPTION", "SCHOOLID", "ROOMNUMBER", "MAXIMUM"],
        example_rows=[
            [79, 79, "COLISEO", 13000, "COLISEO 1", 50],
            [1, 1, "901", 13000, "901", 25],
            [501, 501, "LAB CIENCIAS", 13000, "LAB_BIOLOGIA", 25],
        ],
    )

    # Sheet: teachers
    _add_sheet(wb, "teachers",
        headers=["TEACHER_NUMBER", "Last_Name", "First_Name", "DEPARTMENT", "STATUS"],
        example_rows=[
            ["T_001", "BERRIO GUZMAN", "Sandro", "Math", 1],
            ["T_002", "BETANCUR LOPEZ", "Anibal", "PE", 1],
        ],
    )

    # Sheet: teacher_assignments
    _add_sheet(wb, "teacher_assignments",
        headers=["TEACHER_NUMBER", "COURSE_NUMBER", "SECTIONS_COUNT", "PRIMARY"],
        example_rows=[
            ["T_001", "I1208", 2, 1],
            ["T_002", "E1201", 4, 1],
        ],
        notes={3: "Cuántas secciones de este curso dicta el teacher."},
    )

    # Sheet: student_requests
    _add_sheet(wb, "student_requests",
        headers=["COURSENUMBER", "COURSENAME", "STUDENT_NUMBER", "SCHOOLID",
                 "YEARID", "STUDENT_GRADE_LEVEL_NEXT_YEAR"],
        example_rows=[
            ["E1201", "Physical Education and Health 12", "STD_DUMMY_001",
             13000, 36, 12],
            ["I1208", "AP Calculus AB", "STD_DUMMY_001", 13000, 36, 12],
        ],
        notes={
            6: "Grado del año NUEVO. Valores: 9, 10, 11, 12.",
        },
    )

    # Sheet: required_courses
    _add_sheet(wb, "required_courses",
        headers=["GRADE", "COURSE_NUMBER", "COURSE_NAME", "Notes"],
        example_rows=[
            [12, "E1201", "Physical Education and Health 12", "PE obligatorio G12"],
            [12, "ADV.12", "Advisory 12", "Advisory obligatorio"],
        ],
    )

    # Sheet: course_relationships (simul groups, term pairs)
    _add_sheet(wb, "course_relationships",
        headers=["COURSE_NUMBER", "RELATIONSHIP_TYPE", "RELATED_COURSE", "GROUP_NAME"],
        example_rows=[
            ["G0902", "SIMULTANEOUS", "G1204", "SPANISH_FL"],
            ["I1213", "TERM_PAIR", "I1212", ""],
        ],
        notes={
            2: "SIMULTANEOUS = se dicta en la misma sección física (multi-nivel). "
               "TERM_PAIR = comparte slots pero diferente semestre.",
        },
    )

    # Sheet: behavior (separations + groupings)
    _add_sheet(wb, "conselours_recommendations",
        headers=["GRADE_LEVEL", "CODIGO", "NOMBRE ESTUDIANTE", "SEPARADO DE/COMPARTIR CLASES CON",
                 "CODIGO_2", "NOMBRE ESTUDIANTE_2"],
        example_rows=[
            [12, "STD_DUMMY_001", "Apellido, Nombre", "Separado de",
             "STD_DUMMY_002", "Otro, Persona"],
        ],
        notes={4: "Valores: 'Separado de' o 'Compartir clases con'."},
    )

    # Sheet: teacher_avoid (restricted teachers)
    _add_sheet(wb, "teacher_avoid",
        headers=["STUDENT_NUMBER", "STUDENT", "TEACHER_NAME"],
        example_rows=[
            ["STD_DUMMY_001", "Apellido, Nombre", "BERRIO GUZMAN, Sandro"],
        ],
        notes={3: "Teacher que NO debe dictar a este estudiante."},
    )

    # Sheet: teacher_assistants (TAs)
    _add_sheet(wb, "teacher_assistants",
        headers=["STUDENT_NUMBER", "GRADE_LEVEL", "STUDENT NAME", "COURSENAME",
                 "COURSENAME_TO_ASSIST", "PROFESOR", "CAMBIO EN POWERSCHEDULER"],
        example_rows=[
            ["STD_DUMMY_001", 12, "Apellido, Nombre", "Electives Alternative 1",
             "AP Drawing", "Vélez Cardona, Gloria", "ok"],
        ],
        notes={
            5: "Curso al que el estudiante asistirá como TA.",
            7: "Status: 'ok' / 'pendiente' / 'Sale de TA'.",
        },
    )

    # Sheet: co-planning
    _add_sheet(wb, "co-planning",
        headers=["GROUP_NAME", "TEACHER_1", "TEACHER_2", "TEACHER_3", "TEACHER_4", "TEACHER_5"],
        example_rows=[
            ["Math_Group", "T_001", "T_003", "T_005", "", ""],
        ],
    )

    # README
    ws_readme = wb.create_sheet("README", 0)
    readme = [
        ["PLANTILLA — formato consolidado v5 (schedule_master_data_hs.xlsx)"],
        [""],
        ["Esta plantilla es solo de referencia. Las filas con fondo crema son DUMMY."],
        ["Reemplázalas por datos reales del Colegio."],
        [""],
        ["⚠️ NOTA: el uploader 'xlsx real de Columbus' de la app NO soporta este"],
        ["formato directamente todavía. Para usarlo:"],
        ["  1. Llena este archivo con datos reales"],
        ["  2. Conviértelo a CSVs vía CLI:"],
        ["     python -m src.scheduler.cli import-ps --demand <este-archivo>.xlsx --out data/columbus_v5"],
        ["  3. En la app, escoge 'Carpeta canónica de CSVs' con ruta data/columbus_v5"],
        [""],
        ["Hojas (11):"],
        ["  - courses, rooms, teachers, teacher_assignments"],
        ["  - student_requests, required_courses, course_relationships"],
        ["  - conselours_recommendations, teacher_avoid"],
        ["  - co-planning, teacher_assistants"],
        [""],
        ["Generado por scripts/generate_template_xlsx.py — v4.27.23"],
    ]
    for r, line in enumerate(readme, start=1):
        ws_readme.cell(row=r, column=1, value=line[0])
    ws_readme.column_dimensions["A"].width = 80

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    print(f"✓ {out_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data/templates",
                   help="Directorio de salida")
    args = p.parse_args()
    out = Path(args.out)
    generate_legacy_template(out / "plantilla_legacy.xlsx")
    generate_v5_template(out / "plantilla_v5.xlsx")
    print(f"\n✅ Plantillas generadas en {out.resolve()}")


if __name__ == "__main__":
    main()
