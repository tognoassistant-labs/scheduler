"""Genera reportes individuales por estudiante en lenguaje humano.

Para cada estudiante de un run, produce un párrafo natural en español
explicando qué horario recibió y qué cosas pidió que NO pudo recibir
(con razón humana).

Útil para:
- Compartir con padres de familia que pidan claridad
- Comunicación de consejería al estudiante
- Auditoría humana ("¿por qué Pedro no recibió Ciencias?")

Genera 1 archivo por estudiante en out_dir/<student_id>.md
+ un INDEX.md con la lista.

Uso:
    .venv/bin/python scripts/generate_student_reports.py \\
        --db data/columbus.sqlite \\
        --run 5 \\
        --out reports/students/
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.scheduler.persistence import open_db, RunRepo, InputBundleRepo
from src.scheduler.persistence.serialize import (
    master_from_blob,
    students_from_blob,
    unmet_from_blob,
)


def generate_per_student_reports(db, run_id: int, out_dir: Path,
                                  limit: int | None = None) -> None:
    runs = RunRepo(db)
    bundles = InputBundleRepo(db)
    meta = runs.get(run_id)
    bmeta, ds = bundles.get(meta.bundle_id)

    master_blob, students_blob, unmet_blob = runs.get_result_blobs(run_id)
    master = master_from_blob(master_blob)
    student_assigns = students_from_blob(students_blob)
    unmet = unmet_from_blob(unmet_blob)

    # Lookups
    sections_by_id = {s.section_id: s for s in ds.sections}
    courses_by_id = {c.course_id: c for c in ds.courses}
    teachers_by_id = {t.teacher_id: t for t in ds.teachers}
    rooms_by_id = {r.room_id: r for r in ds.rooms}
    master_by_sect = {m.section_id: m for m in master}
    students_by_id = {st.student_id: st for st in ds.students}

    # Unmet por estudiante (rank-1 sin cumplir)
    unmet_by_student: dict[str, list[str]] = defaultdict(list)
    for sid, cid in unmet:
        unmet_by_student[sid].append(cid)

    out_dir.mkdir(parents=True, exist_ok=True)
    index_lines = [f"# Reportes por estudiante — corrida #{run_id} ({meta.label})"]
    index_lines.append("")
    index_lines.append(f"Total estudiantes: {len(student_assigns)}")
    if limit:
        index_lines.append(f"Limitando a {limit} reportes (use --limit 0 para todos).")
    index_lines.append("")
    index_lines.append("| Estudiante | Grado | Cursos asignados | Faltantes | Reporte |")
    index_lines.append("|---|---|---|---|---|")

    sample_assigns = student_assigns[:limit] if limit else student_assigns

    for sa in sample_assigns:
        st_obj = students_by_id.get(sa.student_id)
        if st_obj is None:
            continue

        # Construir lista de cursos asignados
        assigned_courses = []
        for sid in sa.section_ids:
            sec = sections_by_id.get(sid)
            if sec is None:
                continue
            c = courses_by_id.get(sec.course_id)
            t = teachers_by_id.get(sec.teacher_id)
            m = master_by_sect.get(sid)
            r = rooms_by_id.get(m.room_id) if m else None
            slots_str = ", ".join(f"{d}{b}" for d, b in m.slots) if m else ""
            assigned_courses.append({
                "course_id": sec.course_id,
                "course_name": c.name if c else sec.course_id,
                "teacher": t.name if t else sec.teacher_id,
                "room": r.name if r else (m.room_id if m else ""),
                "slots": slots_str,
                "section_id": sec.section_id,
            })

        missing = unmet_by_student.get(sa.student_id, [])
        n_assigned = len(assigned_courses)
        n_requested = len(st_obj.requested_courses)
        n_missing = len(missing)

        # Construir el reporte por estudiante
        lines = []
        lines.append(f"# Horario de {st_obj.name}")
        lines.append("")
        lines.append(f"**Estudiante:** {st_obj.name}  ")
        lines.append(f"**Código:** {st_obj.student_id}  ")
        lines.append(f"**Grado:** {st_obj.grade}  ")
        lines.append(f"**Año académico:** 2026-2027 — corrida #{run_id}")
        lines.append("")

        # Resumen humano
        if n_missing == 0:
            summary = (
                f"✅ **Recibió todos los cursos solicitados** ({n_assigned} cursos). "
                f"Su horario está completo."
            )
        else:
            faltantes_str = ", ".join(missing[:3])
            if len(missing) > 3:
                faltantes_str += f" + {len(missing) - 3} más"
            summary = (
                f"⚠️ **Recibió {n_assigned} de {n_requested} cursos solicitados** "
                f"({n_missing} pendiente{'s' if n_missing > 1 else ''}: {faltantes_str}). "
                f"La causa más común es que la electiva en primera opción ya estaba "
                f"a tope; el estudiante puede pedirle al consejero que valide si la "
                f"alternativa es aceptable o si vale la pena escalar."
            )
        lines.append(summary)
        lines.append("")

        # Tabla de cursos asignados
        lines.append("## Cursos asignados")
        lines.append("")
        if assigned_courses:
            lines.append("| Curso | Sección | Profesor | Sala | Horario |")
            lines.append("|---|---|---|---|---|")
            for c in assigned_courses:
                lines.append(
                    f"| {c['course_name']} | {c['section_id']} | "
                    f"{c['teacher']} | {c['room']} | {c['slots']} |"
                )
        else:
            lines.append("(sin cursos asignados)")
        lines.append("")

        # Cursos no asignados
        if missing:
            lines.append("## Cursos pendientes")
            lines.append("")
            lines.append(
                "Los siguientes cursos fueron solicitados en primera opción pero "
                "no se pudieron asignar:"
            )
            lines.append("")
            for cid in missing:
                cobj = courses_by_id.get(cid)
                lines.append(f"- **{cobj.name if cobj else cid}** (`{cid}`)")
            lines.append("")
            lines.append(
                "**Razón típica:** todas las secciones de ese curso están a "
                "capacidad (25 estudiantes por sección, 26 para AP Research). "
                "El motor priorizó cursos requeridos por encima de electivas en "
                "primera opción."
            )
            lines.append("")
            lines.append(
                "**Qué hacer:**\n"
                "1. Si la materia es realmente obligatoria → escalar a coordinación "
                "académica para revisar capacidad.\n"
                "2. Si es electiva → revisar las opciones rank-2 y rank-3 del "
                "estudiante para ver qué alternativa recibió."
            )
            lines.append("")

        # Footer
        lines.append("---")
        lines.append(
            f"_Generado automáticamente desde corrida #{run_id} ({meta.created_at[:10]}). "
            f"Para cambios al horario, contactar a coordinación académica._"
        )

        out_file = out_dir / f"{st_obj.student_id}.md"
        out_file.write_text("\n".join(lines), encoding="utf-8")

        # Index entry
        status = "✅" if n_missing == 0 else f"⚠️ {n_missing} faltante{'s' if n_missing > 1 else ''}"
        missing_list = ", ".join(missing[:2]) + (f"..." if len(missing) > 2 else "")
        index_lines.append(
            f"| {st_obj.name} | {st_obj.grade} | {n_assigned} | "
            f"{missing_list or '-'} | [{out_file.name}]({out_file.name}) |"
        )

    (out_dir / "INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")
    print(f"✓ Generados {len(sample_assigns)} reportes en {out_dir}")
    print(f"  índice: {out_dir / 'INDEX.md'}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--run", type=int, required=True)
    p.add_argument("--out", default="reports/students")
    p.add_argument("--limit", type=int, default=0,
                   help="Solo generar N primeros reportes (0 = todos).")
    args = p.parse_args()

    db = open_db(args.db)
    out = Path(args.out)
    limit = args.limit if args.limit > 0 else None
    generate_per_student_reports(db, args.run, out, limit=limit)


if __name__ == "__main__":
    main()
