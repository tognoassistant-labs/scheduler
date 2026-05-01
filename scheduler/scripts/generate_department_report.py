"""Reporte por departamento — markdown agrupando estadísticas por área.

Útil para:
- Reuniones de jefes de departamento
- Detectar departamentos sobrecargados
- Validar balance de profesores por área

Uso:
    .venv/bin/python scripts/generate_department_report.py \\
        --db data/columbus.sqlite \\
        --run 5 \\
        --out REPORTE_DEPARTAMENTOS_run_5.md
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
)


def generate_report(db, run_id: int, out_path: Path) -> None:
    runs = RunRepo(db)
    bundles = InputBundleRepo(db)

    meta = runs.get(run_id)
    bmeta, ds = bundles.get(meta.bundle_id)
    master_blob, students_blob, _ = runs.get_result_blobs(run_id)
    master = master_from_blob(master_blob)
    students = students_from_blob(students_blob)

    # Agrupar por departamento
    sections_by_dept: dict[str, list] = defaultdict(list)
    courses_by_id = {c.course_id: c for c in ds.courses}
    for s in ds.sections:
        c = courses_by_id.get(s.course_id)
        dept = c.department if c else "(sin dept)"
        sections_by_dept[dept].append(s)

    # Teachers por dept
    teachers_by_dept: dict[str, set] = defaultdict(set)
    for s in ds.sections:
        c = courses_by_id.get(s.course_id)
        if c and s.teacher_id:
            teachers_by_dept[c.department].add(s.teacher_id)

    # Enrollment por sección
    enrollment: dict[str, int] = defaultdict(int)
    for sa in students:
        for sid in sa.section_ids:
            enrollment[sid] += 1

    lines = []
    lines.append(f"# Reporte por departamento — corrida #{run_id}")
    lines.append("")
    lines.append(f"**Dataset:** {bmeta.label} ({len(ds.students)} estudiantes · "
                 f"{len(ds.sections)} secciones · {len(ds.courses)} cursos)")
    lines.append(f"**Fecha:** {meta.created_at[:10]}")
    if meta.tags:
        lines.append(f"**Etiquetas:** `{meta.tags}`")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Resumen por departamento")
    lines.append("")
    lines.append("| Departamento | # Cursos | # Secciones | # Teachers | Total inscritos | Promedio/sección |")
    lines.append("|---|---|---|---|---|---|")

    sorted_depts = sorted(sections_by_dept.keys(),
                          key=lambda d: -len(sections_by_dept[d]))

    for dept in sorted_depts:
        sects = sections_by_dept[dept]
        teachers = teachers_by_dept.get(dept, set())
        total_enrolled = sum(enrollment.get(s.section_id, 0) for s in sects)
        unique_courses = {s.course_id for s in sects}
        avg = total_enrolled / len(sects) if sects else 0
        lines.append(
            f"| {dept} | {len(unique_courses)} | {len(sects)} | "
            f"{len(teachers)} | {total_enrolled} | {avg:.1f} |"
        )
    lines.append("")

    # Detalle por departamento
    lines.append("## Detalle por departamento")
    lines.append("")

    for dept in sorted_depts:
        lines.append(f"### {dept}")
        lines.append("")
        sects = sections_by_dept[dept]
        teachers = teachers_by_dept.get(dept, set())

        # Cursos del departamento
        courses_in_dept = sorted({s.course_id for s in sects})
        lines.append(f"**Cursos ({len(courses_in_dept)}):**")
        for cid in courses_in_dept:
            c = courses_by_id.get(cid)
            n_sects = sum(1 for s in sects if s.course_id == cid)
            total_in_course = sum(enrollment.get(s.section_id, 0) for s in sects if s.course_id == cid)
            lines.append(f"- **{c.name if c else cid}** (`{cid}`) — "
                         f"{n_sects} sección{'es' if n_sects > 1 else ''}, "
                         f"{total_in_course} inscritos")
        lines.append("")

        # Carga de teachers
        teacher_load: dict[str, int] = defaultdict(int)
        teacher_enrolled: dict[str, int] = defaultdict(int)
        for s in sects:
            teacher_load[s.teacher_id] += 1
            teacher_enrolled[s.teacher_id] += enrollment.get(s.section_id, 0)

        lines.append(f"**Carga de teachers ({len(teachers)}):**")
        teacher_lookup = {t.teacher_id: t.name for t in ds.teachers}
        sorted_teachers = sorted(teachers, key=lambda tid: -teacher_load[tid])
        lines.append("")
        lines.append("| Teacher | Secciones | Estudiantes | Promedio/sección |")
        lines.append("|---|---|---|---|")
        for tid in sorted_teachers:
            tname = teacher_lookup.get(tid, tid)
            n_sec = teacher_load[tid]
            n_st = teacher_enrolled[tid]
            avg = n_st / n_sec if n_sec > 0 else 0
            lines.append(f"| {tname} | {n_sec} | {n_st} | {avg:.1f} |")
        lines.append("")

        lines.append("---")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ Reporte → {out_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--run", type=int, required=True)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    db = open_db(args.db)
    out = Path(args.out) if args.out else Path(f"REPORTE_DEPARTAMENTOS_run_{args.run}.md")
    generate_report(db, args.run, out)


if __name__ == "__main__":
    main()
