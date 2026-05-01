#!/usr/bin/env python3
"""Multi-seed harvest of phased solver. Runs N seeds, keeps the best.

Solver variance is ±15-20 students between FEASIBLE runs. With 5 seeds
we can typically harvest +5-15 additional students above any single run.

Output: scheduler/data/_client_bundle_v4/HS_2026-2027_phased_best/
"""
from __future__ import annotations

import csv
import shutil
import time
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
BEST_DIR = V4_DIR / "HS_2026-2027_phased_best"


def main(seeds=(42, 17, 1, 99, 1234)) -> int:
    print(f"=== Multi-seed phased harvest ({len(seeds)} seeds) ===")

    ds_template = build_dataset_from_official_xlsx(CANONICAL_XLSX)
    print(f"Dataset: {len(ds_template.students)} students")

    best_n_full = -1
    best_seed = None
    best_results = None
    for seed in seeds:
        print(f"\n--- Seed {seed} ---")
        ds = build_dataset_from_official_xlsx(CANONICAL_XLSX)  # fresh
        t0 = time.time()
        master, _, m_status = solve_master(ds, time_limit_s=120.0, random_seed=seed)
        if not master:
            print(f"  master failed (status={m_status}), skip")
            continue
        student_assigns, unmet, _, _ = solve_students_phased(
            ds, master, time_limit_s=480.0, verbose=False
        )
        # Count students with all courses (excl advisory)
        sections_by_id = {s.section_id: s for s in ds.sections}
        advisory_ids = {c.course_id for c in ds.courses if c.is_advisory}
        n_full = 0
        for sa in student_assigns:
            student = next((s for s in ds.students if s.student_id == sa.student_id), None)
            if not student:
                continue
            granted = {sections_by_id[sid].course_id for sid in sa.section_ids if sid in sections_by_id}
            requested_real = {r.course_id for r in student.requested_courses if r.course_id not in advisory_ids}
            if not (requested_real - granted):
                n_full += 1
        elapsed = time.time() - t0
        print(f"  full coverage: {n_full}/{len(ds.students)} = {100*n_full/len(ds.students):.1f}% ({elapsed:.0f}s)")
        if n_full > best_n_full:
            best_n_full = n_full
            best_seed = seed
            best_results = (ds, master, student_assigns, unmet)
            print(f"  *** new best: seed={seed} with {n_full} full ***")

    if best_results is None:
        print("\n!!! No successful seed !!!")
        return 1

    ds, master, student_assigns, unmet = best_results
    print(f"\n=== BEST: seed={best_seed}, {best_n_full} students full ===")

    # Write the winning bundle
    BEST_DIR.mkdir(parents=True, exist_ok=True)
    write_dataset(ds, BEST_DIR / "input_data")
    export_powerschool(ds, master, student_assigns, BEST_DIR / "powerschool_upload")
    write_reports(ds, master, student_assigns, unmet, BEST_DIR / "horario_estudiantes")

    kpi = compute_kpis(ds, master, student_assigns, unmet)
    print(kpi.summary())
    print(f"\nBundle: {BEST_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
