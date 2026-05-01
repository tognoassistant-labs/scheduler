#!/usr/bin/env python3
"""SOLUTION A: Apply admin proposal in code, then run phased.

Implements the 6 actions from `06_PROPUESTA_ADMIN_G12.md`:
1. Open 2nd section of OB1532 AP Research (Butterworth) in scheme 6 slots
2. Move H1201B AP English Lit to scheme 6 slots
3. Open 2nd section of OH1501 Journalism Higher Level
4. Move one OI1305 Calculus section
5. Move one OI1303 Financial Math section
6. Open 2nd section of OA1322 AP Physics 2

The "moves" are implemented as `Section.locked_scheme` so the master
solver is forced to put those sections in the chosen scheme. The "opens"
add new Section objects to the dataset (with the existing teacher who
has capacity).

Output: scheduler/data/_client_bundle_v4/HS_2026-2027_admin_applied/
"""
from __future__ import annotations

import time
from pathlib import Path

from src.scheduler.ps_ingest_official import build_dataset_from_official_xlsx
from src.scheduler.master_solver import solve_master
from src.scheduler.student_solver import solve_students_phased
from src.scheduler.io_csv import write_dataset
from src.scheduler.exporter import export_powerschool
from src.scheduler.reports import write_reports, compute_kpis
from src.scheduler.models import Section


REPO = Path(__file__).resolve().parent
CANONICAL_XLSX = REPO.parent / "reference" / "schedule_master_data_hs.xlsx"
V4_DIR = REPO / "data" / "_client_bundle_v4"
ADMIN_DIR = V4_DIR / "HS_2026-2027_admin_applied"


# Scheme 6 in the default rotation falls at: B1, C4, E2 (per models.default_rotation)
TARGET_SCHEME = 6


def apply_admin_proposal(ds) -> None:
    """Mutate the Dataset to reflect the 6 admin actions."""
    sections_by_id = {s.section_id: s for s in ds.sections}

    # ---- 1. AP Research (OB1532) — open 2nd section + move existing to scheme 6 ----
    ob1532_existing = sections_by_id.get("OB1532.1")
    if ob1532_existing:
        # Move existing to scheme 6
        ob1532_existing.locked_scheme = TARGET_SCHEME
        # Add 2nd section with same teacher (Butterworth, only has 1 sec — has capacity)
        new_sec = Section(
            section_id="OB1532.2",
            course_id="OB1532",
            teacher_id=ob1532_existing.teacher_id,
            max_size=ob1532_existing.max_size,
            grade_level=12,
            # Don't lock — let master pick best slot for this 2nd one
        )
        ds.sections.append(new_sec)
        print(f"  ✓ AP Research: locked .1 to scheme {TARGET_SCHEME}, added .2 (same teacher)")

    # ---- 2. AP English Lit (H1201B) — move to scheme 6 ----
    h1201b = sections_by_id.get("H1201B.1")
    if h1201b:
        h1201b.locked_scheme = TARGET_SCHEME
        print(f"  ✓ AP English Lit: locked H1201B.1 to scheme {TARGET_SCHEME}")

    # ---- 3. Journalism Higher (OH1501) — open 3rd section in scheme 6 ----
    oh1501_existing = sections_by_id.get("OH1501.1")
    if oh1501_existing:
        new_sec = Section(
            section_id="OH1501.3",
            course_id="OH1501",
            teacher_id=oh1501_existing.teacher_id,
            max_size=oh1501_existing.max_size,
            grade_level=12,
            locked_scheme=TARGET_SCHEME,
        )
        ds.sections.append(new_sec)
        print(f"  ✓ Journalism Higher: added OH1501.3 in scheme {TARGET_SCHEME} (same teacher)")

    # ---- 4. Calculus (OI1305) — move first section to scheme 6 ----
    oi1305 = sections_by_id.get("OI1305.1")
    if oi1305:
        oi1305.locked_scheme = TARGET_SCHEME
        print(f"  ✓ Calculus: locked OI1305.1 to scheme {TARGET_SCHEME}")

    # ---- 5. Financial Math (OI1303) — move first to scheme 6 ----
    oi1303 = sections_by_id.get("OI1303.1")
    if oi1303:
        oi1303.locked_scheme = TARGET_SCHEME
        print(f"  ✓ Financial Math: locked OI1303.1 to scheme {TARGET_SCHEME}")

    # ---- 6. AP Physics 2 (OA1322) — open 3rd section in scheme 6 ----
    oa1322 = sections_by_id.get("OA1322.1")
    if oa1322:
        new_sec = Section(
            section_id="OA1322.3",
            course_id="OA1322",
            teacher_id=oa1322.teacher_id,
            max_size=oa1322.max_size,
            grade_level=12,
            locked_scheme=TARGET_SCHEME,
        )
        ds.sections.append(new_sec)
        print(f"  ✓ AP Physics 2: added OA1322.3 in scheme {TARGET_SCHEME} (same teacher)")


def main() -> int:
    print("=== SOLUTION A: Admin Proposal Applied (phased) ===")
    print(f"Canonical xlsx: {CANONICAL_XLSX}")

    t0 = time.time()
    ds = build_dataset_from_official_xlsx(CANONICAL_XLSX)
    print(f"\n  ingested: {len(ds.students)} students, {len(ds.sections)} sections")

    print(f"\n=== Applying 6 admin actions (sections moved/added) ===")
    apply_admin_proposal(ds)
    print(f"  After overrides: {len(ds.sections)} sections (was 248)")

    print(f"\n=== Stage 1: master solve ===")
    t1 = time.time()
    master, _, m_status = solve_master(ds, time_limit_s=300.0)
    print(f"  status={m_status}, {len(master)} assignments, {time.time()-t1:.1f}s")
    if not master:
        print("ABORTING: master infeasible — admin proposal may conflict with HC4 (home_room) or HC1 (consec)")
        return 2

    print(f"\n=== Stage 2: phased student solve (G12 → G9) ===")
    t2 = time.time()
    student_assigns, unmet, _, s_status = solve_students_phased(
        ds, master, time_limit_s=600.0, verbose=True
    )
    print(f"\n  PHASED: {len(student_assigns)} students placed, {len(unmet)} unmet, {time.time()-t2:.1f}s")

    # Per-grade
    from collections import Counter
    sections_by_id = {s.section_id: s for s in ds.sections}
    advisory_ids = {c.course_id for c in ds.courses if c.is_advisory}
    by_grade_full = Counter()
    grade_total = Counter(s.grade for s in ds.students)
    for sa in student_assigns:
        student = next((s for s in ds.students if s.student_id == sa.student_id), None)
        if not student:
            continue
        granted = {sections_by_id[sid].course_id for sid in sa.section_ids if sid in sections_by_id}
        requested_real = {r.course_id for r in student.requested_courses if r.course_id not in advisory_ids}
        if not (requested_real - granted):
            by_grade_full[student.grade] += 1

    print(f"\n=== Per-grade full coverage ===")
    print(f"  {'Gr':3s} {'tot':>4s} {'full':>5s} {'full%':>6s}")
    n_full_total = 0
    for g in [12, 11, 10, 9]:
        n_full = by_grade_full.get(g, 0)
        tot = grade_total[g]
        pct = 100*n_full/max(1,tot)
        print(f"  {g:>3d}  {tot:>4d}  {n_full:>5d}  {pct:>5.1f}%")
        n_full_total += n_full
    pct_total = 100*n_full_total/max(1,sum(grade_total.values()))
    print(f"  TOTAL: {n_full_total}/{sum(grade_total.values())} = {pct_total:.1f}%")

    print("\n=== Stage 3: KPI report ===")
    kpi = compute_kpis(ds, master, student_assigns, unmet)
    print(kpi.summary())

    # Write bundle
    print("\n=== Stage 4: write bundle files ===")
    ADMIN_DIR.mkdir(parents=True, exist_ok=True)
    write_dataset(ds, ADMIN_DIR / "input_data")
    export_powerschool(ds, master, student_assigns, ADMIN_DIR / "powerschool_upload")
    write_reports(ds, master, student_assigns, unmet, ADMIN_DIR / "horario_estudiantes")

    print(f"\n=== DONE in {time.time()-t0:.1f}s ===")
    print(f"Bundle: {ADMIN_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
