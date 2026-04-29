#!/usr/bin/env python3
"""Build the v4 client bundle from canonical PowerSchool xlsx.

Run:
    .venv/bin/python build_v4_bundle.py
"""
from __future__ import annotations

import csv
import hashlib
import shutil
import time
from pathlib import Path

from src.scheduler.ps_ingest_official import build_dataset_from_official_xlsx
from src.scheduler.master_solver import solve_master
from src.scheduler.student_solver import solve_students
from src.scheduler.io_csv import write_dataset
from src.scheduler.exporter import export_powerschool
from src.scheduler.io_oneroster import write_oneroster
from src.scheduler.reports import write_reports, compute_kpis


REPO = Path(__file__).resolve().parent
CANONICAL_XLSX = REPO.parent / "reference" / "columbus_official_2026-2027.xlsx"
V3_DIR = REPO / "data" / "_client_bundle_v3"
V4_DIR = REPO / "data" / "_client_bundle_v4"
HS_DIR = V4_DIR / "HS_2026-2027_real"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_student_schedules_friendly(ds, master, student_assigns, out_path: Path) -> None:
    """One row per (student, section) with human-friendly columns."""
    sections_by_id = {s.section_id: s for s in ds.sections}
    courses_by_id = {c.course_id: c for c in ds.courses}
    teachers_by_id = {t.teacher_id: t for t in ds.teachers}
    rooms_by_id = {r.room_id: r for r in ds.rooms}
    master_by_sect = {m.section_id: m for m in master}
    students_by_id = {st.student_id: st for st in ds.students}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["StudentID", "StudentName", "Grade", "CourseID", "CourseName",
                    "SectionID", "Period", "Slots", "TeacherID", "TeacherName",
                    "RoomID", "RoomName"])
        for sa in student_assigns:
            st = students_by_id.get(sa.student_id)
            if st is None:
                continue
            for sid in sa.section_ids:
                s = sections_by_id.get(sid)
                if s is None:
                    continue
                m = master_by_sect.get(sid)
                c = courses_by_id.get(s.course_id)
                t = teachers_by_id.get(s.teacher_id)
                r = rooms_by_id.get(m.room_id) if m else None
                slots_str = ";".join(f"{d}{b}" for d, b in m.slots) if m else ""
                period_str = m.scheme if m else ""
                w.writerow([
                    st.student_id, st.name, st.grade,
                    s.course_id, c.name if c else "",
                    s.section_id, period_str, slots_str,
                    s.teacher_id, t.name if t else "",
                    m.room_id if m else "", r.name if r else "",
                ])


def main() -> int:
    print(f"=== Build v4 bundle ===")
    print(f"Canonical xlsx: {CANONICAL_XLSX}")
    if not CANONICAL_XLSX.exists():
        print(f"ERROR: {CANONICAL_XLSX} not found")
        return 1

    t0 = time.time()
    ds = build_dataset_from_official_xlsx(CANONICAL_XLSX)
    print(f"  ingested: {len(ds.students)} students, {len(ds.sections)} sections, "
          f"{len(ds.teachers)} teachers, {len(ds.rooms)} rooms, {len(ds.courses)} courses")

    print("\n=== Stage 1: master solve ===")
    t1 = time.time()
    master, _, m_status = solve_master(ds, time_limit_s=300.0)
    print(f"  status={m_status}, {len(master)} assignments, {time.time()-t1:.1f}s")
    if not master:
        print("ABORTING: master infeasible")
        return 2

    print("\n=== Stage 2: student solve ===")
    t2 = time.time()
    student_assigns, unmet, _, s_status = solve_students(ds, master, time_limit_s=300.0, verbose=True)
    print(f"  status={s_status}, {len(student_assigns)} students placed, {len(unmet)} unmet, {time.time()-t2:.1f}s")

    print("\n=== Stage 3: KPI report ===")
    kpi = compute_kpis(ds, master, student_assigns, unmet)
    print(kpi.summary())

    # Build bundle dirs
    print("\n=== Stage 4: write bundle files ===")
    HS_DIR.mkdir(parents=True, exist_ok=True)
    write_dataset(ds, HS_DIR / "input_data")
    print(f"  input_data/ ✓")
    export_powerschool(ds, master, student_assigns, HS_DIR / "powerschool_upload")
    print(f"  powerschool_upload/ ✓")
    write_oneroster(ds, master, student_assigns, HS_DIR / "lms_upload")
    print(f"  lms_upload/ ✓")
    write_reports(ds, master, student_assigns, unmet, HS_DIR / "horario_estudiantes")
    _write_student_schedules_friendly(ds, master, student_assigns, HS_DIR / "horario_estudiantes" / "student_schedules_friendly.csv")
    print(f"  horario_estudiantes/ ✓")

    # Copy unchanged docs from v3 (they remain valid, will be edited later)
    print("\n=== Stage 5: copy + update docs ===")
    for doc in ("00_LEEME_PRIMERO.md", "00_README_FIRST_en.md",
                "01_PREGUNTAS_PARA_COLUMBUS.md", "01_QUESTIONS_FOR_COLUMBUS_en.md",
                "03_AGENT_TEST_INSTRUCTIONS.md", "verify_bundle.py"):
        src = V3_DIR / doc
        dst = V4_DIR / doc
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  {doc} (copied from v3)")

    # Copy MS synthetic PoC unchanged
    ms_src = V3_DIR / "MS_2026-2027_synthetic_PoC"
    ms_dst = V4_DIR / "MS_2026-2027_synthetic_PoC"
    if ms_src.exists() and not ms_dst.exists():
        shutil.copytree(ms_src, ms_dst)
        print(f"  MS_2026-2027_synthetic_PoC/ (copied from v3)")

    # Write fresh KPI report
    kpi_path = V4_DIR / "02_KPI_REPORT.md"
    elapsed_total = time.time() - t0
    total_rank1 = sum(1 for s in ds.students for r in s.requested_courses if r.rank == 1)
    cov_pct = 100.0 * (total_rank1 - len(unmet)) / max(1, total_rank1)
    kpi_path.write_text(f"""# Reporte de KPIs — Bundle v4

**Fecha:** 2026-04-28
**Datos:** PowerSchool canónicos (`columbus_official_2026-2027.xlsx`)
**Tiempo total de solve:** {elapsed_total:.1f}s

## Datos de entrada

| | |
|---|---|
| Estudiantes | {len(ds.students)} |
| Secciones | {len(ds.sections)} |
| Profesores | {len(ds.teachers)} |
| Salones | {len(ds.rooms)} |
| Cursos | {len(ds.courses)} |
| Requests rank-1 | {sum(1 for s in ds.students for r in s.requested_courses if r.rank == 1)} |

## Resultados del solve

| | |
|---|---|
| Master status | `{m_status}` |
| Master assignments | {len(master)} |
| Student status | `{s_status}` |
| Estudiantes asignados | {len(student_assigns)}/{len(ds.students)} |
| Requests no satisfechos | {len(unmet)} |
| **Cobertura** | **{cov_pct:.1f}%** |

## KPI breakdown

```
{kpi.summary()}
```

## Cambios v4 vs v3

- **Ingester canónico** (`ps_ingest_official.py`) reemplaza al heurístico. Lee 5 hojas del xlsx canónico de PS con IDs reales.
- **Fix:** advisory sections deduplicadas (PS canónico ya las trae).
- **Fix:** cursos semestrales (S1/S2) omitidos para evitar double-count en Ortegon.
- **Soft penalty** en student_solver para required courses — antes era hard `==1`, ahora con slack penalizado. Permite cobertura parcial cuando el grid no alcanza (estudiante 29096: 10 requests vs 9 slots).

## Problemas de datos del cliente

Ver `PROBLEMAS_DATOS_CLIENTE.md` en la raíz del repo. ~3 días perdidos en limpieza.

## Decisiones del cliente pendientes

1. **Cursos semestrales** (Ortegon): ¿OK omitir para demo, modelar properly post-MVP?
2. **Estudiantes sobreasignados** (29096 con 10 requests): ¿soft penalty es aceptable o hay que reducir requests en origen?
""")
    print(f"  02_KPI_REPORT.md ✓")

    # SHA256 manifest
    print("\n=== Stage 6: SHA256 manifest ===")
    manifest_path = V4_DIR / "MANIFEST_SHA256.txt"
    files = sorted(p for p in V4_DIR.rglob("*") if p.is_file() and p.name != "MANIFEST_SHA256.txt")
    with manifest_path.open("w") as f:
        for p in files:
            rel = p.relative_to(V4_DIR)
            f.write(f"{_sha256(p)}  {rel}\n")
    print(f"  MANIFEST_SHA256.txt ({len(files)} files)")

    print(f"\n=== DONE in {time.time()-t0:.1f}s ===")
    print(f"Bundle: {V4_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
