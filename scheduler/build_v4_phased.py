#!/usr/bin/env python3
"""Phased build — strict lex G12 → G11 → G10 → G9.

Uses `solve_students_phased` (in student_solver.py) which solves each
grade in priority order, locking enrollments before moving to the next.
This implements the school's "primero los de 12..." rule with TRUE lex
priority instead of weighted approximation.

Output: scheduler/data/_client_bundle_v4/HS_2026-2027_phased/
(separate from the all-at-once bundle so we can compare).

Run:
    .venv/bin/python build_v4_phased.py
"""
from __future__ import annotations

import os
import time
from collections import Counter
from pathlib import Path

from src.scheduler.ps_ingest_official import build_dataset_from_official_xlsx
from src.scheduler.master_solver import solve_master
from src.scheduler.student_solver import solve_students_phased
from src.scheduler.io_csv import write_dataset
from src.scheduler.exporter import export_powerschool
from src.scheduler.reports import write_reports, compute_kpis


REPO = Path(__file__).resolve().parent
CANONICAL_XLSX = REPO.parent / "reference" / "schedule_master_data_hs.xlsx"
V4_DIR = REPO / "data" / "_client_bundle_v4"
PHASED_DIR = V4_DIR / "HS_2026-2027_phased"


def main() -> int:
    print("=== Build PHASED bundle (lex G12 → G11 → G10 → G9) ===")
    print(f"Canonical xlsx: {CANONICAL_XLSX}")
    if not CANONICAL_XLSX.exists():
        print(f"ERROR: {CANONICAL_XLSX} not found")
        return 1

    t0 = time.time()
    ds = build_dataset_from_official_xlsx(CANONICAL_XLSX)
    print(f"\n  ingested: {len(ds.students)} students, {len(ds.sections)} sections, "
          f"{len(ds.teachers)} teachers, {len(ds.rooms)} rooms, {len(ds.courses)} courses")

    print(f"\n=== Stage 1: master solve (all 248 sections) ===")
    t1 = time.time()
    master, _, m_status = solve_master(ds, time_limit_s=300.0)
    print(f"  status={m_status}, {len(master)} assignments, {time.time()-t1:.1f}s")
    if not master:
        print("ABORTING: master infeasible")
        return 2

    print(f"\n=== Stage 2: phased student solve (G12 → G11 → G10 → G9) ===")
    t2 = time.time()
    student_assigns, unmet, _, s_status = solve_students_phased(
        ds, master, time_limit_s=600.0, verbose=True
    )
    print(f"\n  PHASED total: {len(student_assigns)} students placed, {len(unmet)} unmet, {time.time()-t2:.1f}s")

    # Per-grade breakdown
    grade_by_stu = {s.student_id: s.grade for s in ds.students}
    print(f"\n=== Per-grade post-phased coverage ===")
    by_grade = Counter()
    by_grade_full = Counter()
    sections_by_id = {s.section_id: s for s in ds.sections}
    advisory_ids = {c.course_id for c in ds.courses if c.is_advisory}
    for sa in student_assigns:
        grade = grade_by_stu.get(sa.student_id)
        if grade is None:
            continue
        by_grade[grade] += 1
        student = next((s for s in ds.students if s.student_id == sa.student_id), None)
        if student is None:
            continue
        granted_courses = {sections_by_id[sid].course_id for sid in sa.section_ids if sid in sections_by_id}
        requested_real = {r.course_id for r in student.requested_courses if r.course_id not in advisory_ids}
        granted_real = granted_courses - advisory_ids
        if not (requested_real - granted_real):
            by_grade_full[grade] += 1

    print(f"  {'Grade':5s} {'placed':>6s} {'full':>5s} {'full%':>6s}")
    for g in [12, 11, 10, 9]:
        n_g = sum(1 for s in ds.students if s.grade == g)
        n_full = by_grade_full.get(g, 0)
        pct = 100 * n_full / max(1, n_g)
        print(f'  {g:>3d}    {by_grade.get(g, 0):>6d} {n_full:>5d} {pct:>5.1f}%')

    print("\n=== Stage 3: KPI report ===")
    kpi = compute_kpis(ds, master, student_assigns, unmet)
    print(kpi.summary())

    # Build bundle dirs
    print("\n=== Stage 4: write bundle files ===")
    PHASED_DIR.mkdir(parents=True, exist_ok=True)
    write_dataset(ds, PHASED_DIR / "input_data")
    print(f"  input_data/ ✓")
    export_powerschool(ds, master, student_assigns, PHASED_DIR / "powerschool_upload")
    print(f"  powerschool_upload/ ✓")
    write_reports(ds, master, student_assigns, unmet, PHASED_DIR / "horario_estudiantes")
    print(f"  horario_estudiantes/ ✓")

    print(f"\n=== DONE in {time.time()-t0:.1f}s ===")
    print(f"Bundle: {PHASED_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
