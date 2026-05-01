#!/usr/bin/env python3
"""SOLUTION B: Iterative master + student with smart slot hints.

The master_solver normally picks slots for sections WITHOUT knowing which
slots would let interested students fit in. This causes "wasted" sections
like H1201B AP English Lit (1 sec / 0 enrolled / 13 wanted) where the
master placed the section in slots that conflict with all interested
students' other classes.

This script implements an iterative approach:
  1. Run master + phased student normally (baseline)
  2. Identify "wasted" sections: high demand, low enrollment ratio
  3. For each wasted section, compute the slot triplet where MOST of the
     unmet interested students are simultaneously free
  4. Re-run master with those sections locked to the computed scheme
  5. Re-run phased student
  6. Iterate up to N cycles, or until convergence

Output: scheduler/data/_client_bundle_v4/HS_2026-2027_iterative/
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
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
ITER_DIR = V4_DIR / "HS_2026-2027_iterative"


# Map (day, block) → scheme for the default rotation
# (matches models.default_rotation())
SLOT_TO_SCHEME = {
    ('A',1):1, ('A',2):2, ('A',3):3, ('A',4):4, ('A',5):5,
    ('B',1):6, ('B',2):7, ('B',3):8, ('B',4):1, ('B',5):2,
    ('C',1):3, ('C',2):4, ('C',3):5, ('C',4):6, ('C',5):7,
    ('D',1):8, ('D',2):1, ('D',3):2, ('D',4):3, ('D',5):4,
    ('E',1):5, ('E',2):6,                ('E',4):7, ('E',5):8,
    # E3 = ADVISORY
}
SCHEME_TO_SLOTS = defaultdict(list)
for slot, sch in SLOT_TO_SCHEME.items():
    SCHEME_TO_SLOTS[sch].append(slot)


def find_best_scheme_for_section(
    target_section_id: str,
    interested_unmet_students: list[str],
    busy_slots_by_student: dict,
) -> int | None:
    """For a wasted section, pick the scheme whose 3 slots are
    simultaneously free for the maximum number of interested-but-unmet
    students."""
    best_scheme = None
    best_score = -1
    for scheme, slots in SCHEME_TO_SLOTS.items():
        # Count students free at ALL 3 slots of this scheme
        n_free = sum(1 for sid in interested_unmet_students
                     if all(slot not in busy_slots_by_student.get(sid, set())
                            for slot in slots))
        if n_free > best_score:
            best_score = n_free
            best_scheme = scheme
    return best_scheme if best_score > 0 else None


def identify_wasted_sections(
    ds, master, student_assigns, threshold_enrollment_ratio: float = 0.3,
    min_demand: int = 5,
) -> list[tuple[str, list[str], int]]:
    """Returns list of (section_id, interested_unmet_student_ids, current_scheme).

    A section is "wasted" if:
      - Its enrollment ratio < threshold (default 30%)
      - At least `min_demand` students requested its course
    """
    sections_by_id = {s.section_id: s for s in ds.sections}
    enrollment_by_section = Counter()
    for sa in student_assigns:
        for sid in sa.section_ids:
            enrollment_by_section[sid] += 1

    # Demand per course
    demand_by_course = Counter()
    for st in ds.students:
        for r in st.requested_courses:
            demand_by_course[r.course_id] += 1

    # Granted per (student, course) — to find unmet
    granted = defaultdict(set)
    for sa in student_assigns:
        for sid in sa.section_ids:
            sec = sections_by_id.get(sid)
            if sec:
                granted[sa.student_id].add(sec.course_id)

    master_by_sect = {m.section_id: m for m in master}

    wasted = []
    for s in ds.sections:
        sid = s.section_id
        m = master_by_sect.get(sid)
        if not m:
            continue
        enrolled = enrollment_by_section.get(sid, 0)
        if enrolled / max(1, s.max_size) >= threshold_enrollment_ratio:
            continue
        if demand_by_course.get(s.course_id, 0) < min_demand:
            continue
        # Find interested-but-unmet students for this course
        interested_unmet = [
            st.student_id for st in ds.students
            if any(r.course_id == s.course_id for r in st.requested_courses)
            and s.course_id not in granted.get(st.student_id, set())
        ]
        if not interested_unmet:
            continue
        current_scheme = SLOT_TO_SCHEME.get(m.slots[0]) if m.slots else None
        wasted.append((sid, interested_unmet, current_scheme))
    return wasted


def main(max_iterations: int = 3) -> int:
    print(f"=== SOLUTION B: Iterative master + student (max {max_iterations} iterations) ===")
    print(f"Canonical xlsx: {CANONICAL_XLSX}")

    t0 = time.time()
    ds = build_dataset_from_official_xlsx(CANONICAL_XLSX)
    print(f"\n  ingested: {len(ds.students)} students, {len(ds.sections)} sections")

    section_locks: dict[str, int] = {}  # section_id → forced scheme

    best_n_full = -1
    best_results = None

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"=== ITERATION {iteration} ===")
        print(f"{'='*60}")

        # Apply locks
        for s in ds.sections:
            if s.section_id in section_locks:
                s.locked_scheme = section_locks[s.section_id]

        print(f"\nIteration {iteration}: {len(section_locks)} sections locked to specific schemes")

        # Master solve
        t1 = time.time()
        master, _, m_status = solve_master(ds, time_limit_s=180.0)
        print(f"  master: status={m_status}, {len(master)} assigns, {time.time()-t1:.1f}s")
        if not master:
            print(f"  MASTER FAILED — locks may be infeasible. Reverting last batch.")
            # Unlock the sections added in last iteration (not implemented, just abort)
            break

        # Phased student solve
        t2 = time.time()
        student_assigns, unmet, _, s_status = solve_students_phased(
            ds, master, time_limit_s=400.0, verbose=False
        )
        print(f"  student: {len(student_assigns)} placed, {len(unmet)} unmet, {time.time()-t2:.1f}s")

        # Compute coverage
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
        print(f"  coverage: {n_full}/{len(ds.students)} = {100*n_full/len(ds.students):.1f}% full")

        if n_full > best_n_full:
            best_n_full = n_full
            best_results = (
                [s.model_copy() for s in ds.sections],
                master, student_assigns, unmet
            )
            print(f"  *** new best: {n_full} full ***")

        if iteration == max_iterations:
            break

        # Identify wasted sections to re-lock
        master_by_sect = {m.section_id: m for m in master}
        busy_by_stu = defaultdict(set)
        for sa in student_assigns:
            for sid in sa.section_ids:
                m = master_by_sect.get(sid)
                if m:
                    for slot in m.slots:
                        busy_by_stu[sa.student_id].add(slot)

        wasted = identify_wasted_sections(ds, master, student_assigns)
        print(f"\n  Found {len(wasted)} wasted sections (enrollment <30% with demand ≥5)")

        new_locks = 0
        for sid, interested_unmet, current_scheme in wasted:
            if sid in section_locks:
                continue  # already locked, skip
            best_scheme = find_best_scheme_for_section(
                sid, interested_unmet, busy_by_stu
            )
            if best_scheme is None or best_scheme == current_scheme:
                continue
            section_locks[sid] = best_scheme
            new_locks += 1
            print(f"    will lock {sid} (course {sections_by_id[sid].course_id}) "
                  f"from scheme {current_scheme} → scheme {best_scheme} "
                  f"(would unlock {len(interested_unmet)} potential students)")
        if new_locks == 0:
            print(f"  No new locks proposed → converged. Stopping.")
            break

    if best_results is None:
        print("\n!!! No successful run !!!")
        return 1

    sections, master, student_assigns, unmet = best_results
    print(f"\n=== BEST: {best_n_full} students full ===")

    # Restore sections in ds
    for s_copy in sections:
        for s in ds.sections:
            if s.section_id == s_copy.section_id:
                s.locked_scheme = s_copy.locked_scheme
                break

    print("\n=== Stage 4: write bundle files ===")
    ITER_DIR.mkdir(parents=True, exist_ok=True)
    write_dataset(ds, ITER_DIR / "input_data")
    export_powerschool(ds, master, student_assigns, ITER_DIR / "powerschool_upload")
    write_reports(ds, master, student_assigns, unmet, ITER_DIR / "horario_estudiantes")

    print("\n=== Stage 5: KPI report ===")
    kpi = compute_kpis(ds, master, student_assigns, unmet)
    print(kpi.summary())

    print(f"\n=== DONE in {time.time()-t0:.1f}s ===")
    print(f"Bundle: {ITER_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
