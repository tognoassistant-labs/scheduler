#!/usr/bin/env python3
"""Phased schedule build — Phase 1: G12 only.

This is the first phase of the school's preferred lex-min strategy
("primero los de 12, luego los de 11, luego los de 10 y por último los de 9"
— meeting 2026-04-30).

Approach:
  - Master solver decides where ALL 248 sections go (scheme + room).
    All sections will be opened by the school regardless of who fills them,
    so they all need a slot.
  - Student solver only assigns G12 students. G11/G10/G9 are filtered out
    of the Dataset for this phase.
  - Output goes to a SEPARATE bundle dir (HS_2026-2027_G12_only) so it
    doesn't overwrite the all-grades bundle.

Once we're happy with G12 outcomes, the next phase locks G12 assignments
and adds G11. Then G10, G9.

Run:
    .venv/bin/python build_g12_only.py
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from src.scheduler.ps_ingest_official import build_dataset_from_official_xlsx
from src.scheduler.master_solver import solve_master
from src.scheduler.student_solver import solve_students
from src.scheduler.io_csv import write_dataset
from src.scheduler.exporter import export_powerschool
from src.scheduler.reports import write_reports, compute_kpis


REPO = Path(__file__).resolve().parent
CANONICAL_XLSX = REPO.parent / "reference" / "schedule_master_data_hs.xlsx"
V4_DIR = REPO / "data" / "_client_bundle_v4"
G12_DIR = V4_DIR / "HS_2026-2027_G12_only"


def main() -> int:
    print("=== Build G12-only bundle (Phase 1) ===")
    print(f"Canonical xlsx: {CANONICAL_XLSX}")
    if not CANONICAL_XLSX.exists():
        print(f"ERROR: {CANONICAL_XLSX} not found")
        return 1

    t0 = time.time()
    ds = build_dataset_from_official_xlsx(CANONICAL_XLSX)
    print(f"\n  ingested (full HS): {len(ds.students)} students, {len(ds.sections)} sections, "
          f"{len(ds.teachers)} teachers, {len(ds.rooms)} rooms, {len(ds.courses)} courses")

    # ---- Filter to G12 only ----
    g12_students = [s for s in ds.students if s.grade == 12]
    other_grades = {s.grade for s in ds.students if s.grade != 12}
    print(f"  filtering to G12 only: {len(g12_students)} G12 students kept "
          f"({sum(1 for s in ds.students if s.grade != 12)} from grades {sorted(other_grades)} dropped)")

    # Replace ds.students in place. Master still sees all sections (they will
    # all be opened by the school). Behavior matrix entries that reference
    # non-G12 students simply won't trigger constraints.
    ds.students = g12_students

    # Filter behavior matrix: drop pairs where either student is not G12
    g12_ids = {s.student_id for s in g12_students}
    n_seps_before = len(ds.behavior.separations)
    n_grps_before = len(ds.behavior.groupings)
    ds.behavior.separations = [(a, b) for a, b in ds.behavior.separations if a in g12_ids and b in g12_ids]
    ds.behavior.groupings = [(a, b) for a, b in ds.behavior.groupings if a in g12_ids and b in g12_ids]
    print(f"  behavior matrix: separations {n_seps_before}→{len(ds.behavior.separations)}, "
          f"groupings {n_grps_before}→{len(ds.behavior.groupings)}")

    # Coplanning groups don't depend on students — keep as-is.
    print(f"  coplanning groups (unchanged): {len(ds.coplanning_groups)}")

    # Required courses count (just for context)
    n_required_g12 = sum(1 for s in g12_students for r in s.requested_courses if r.is_required and r.course_id != 'ADVHS01')
    n_elective_g12 = sum(1 for s in g12_students for r in s.requested_courses if not r.is_required)
    print(f"  G12 requests: {n_required_g12} required (excl Advisory) + {n_elective_g12} elective")

    print(f"\n=== Stage 1: master solve (all 248 sections) ===")
    t1 = time.time()
    master, _, m_status = solve_master(ds, time_limit_s=300.0)
    print(f"  status={m_status}, {len(master)} assignments, {time.time()-t1:.1f}s")
    if not master:
        print("ABORTING: master infeasible")
        return 2

    print(f"\n=== Stage 2: student solve (G12 only — {len(g12_students)} students) ===")
    t2 = time.time()
    student_assigns, unmet, _, s_status = solve_students(ds, master, time_limit_s=300.0, verbose=True)
    print(f"  status={s_status}, {len(student_assigns)} students placed, {len(unmet)} unmet, {time.time()-t2:.1f}s")

    print("\n=== Stage 3: KPI report ===")
    kpi = compute_kpis(ds, master, student_assigns, unmet)
    print(kpi.summary())

    # Build bundle dirs
    print("\n=== Stage 4: write bundle files ===")
    G12_DIR.mkdir(parents=True, exist_ok=True)
    write_dataset(ds, G12_DIR / "input_data")
    print(f"  input_data/ ✓")
    export_powerschool(ds, master, student_assigns, G12_DIR / "powerschool_upload")
    print(f"  powerschool_upload/ ✓")
    write_reports(ds, master, student_assigns, unmet, G12_DIR / "horario_estudiantes")
    print(f"  horario_estudiantes/ ✓")

    # Quick analysis
    print("\n=== G12-only analysis ===")
    from collections import Counter
    miss_dist = Counter()
    n_full = 0
    for sa in student_assigns:
        student = next((s for s in g12_students if s.student_id == sa.student_id), None)
        if student is None:
            continue
        sec_courses = set()
        for sid in sa.section_ids:
            sec = next((sec for sec in ds.sections if sec.section_id == sid), None)
            if sec:
                sec_courses.add(sec.course_id)
        requested = {r.course_id for r in student.requested_courses if r.course_id != 'ADVHS01'}
        n_missing = len(requested - sec_courses)
        miss_dist[n_missing] += 1
        if n_missing == 0:
            n_full += 1
    print(f"  Estudiantes G12 con TODOS sus cursos: {n_full}/{len(g12_students)} = {100*n_full/len(g12_students):.1f}%")
    for k in sorted(miss_dist):
        print(f"    {k} faltantes: {miss_dist[k]} estudiantes")

    print(f"\n=== DONE in {time.time()-t0:.1f}s ===")
    print(f"Bundle: {G12_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
