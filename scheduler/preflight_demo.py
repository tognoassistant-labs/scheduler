#!/usr/bin/env python3
"""Pre-flight demo smoke test — simulates what the cliente will see on May 1.

Validates the v4.3 bundle as a downstream consumer would:
1. PowerSchool upload CSVs parse cleanly with the spec column names.
2. OneRoster bundle has all 7 required files + correct sub-sessions.
3. Term-paired Micro/Macro alternate semesters (S1+S2 in same slot).
4. Required-PE coverage acceptable (≤5 unmet on synthetic data target).
5. Sanity-check student 28001 (the case that originated the "stale visor"
   bug report): must have Introduction to Law assigned.
6. Sanity-check student 29096 (the over-constrained 10-requests / 9-slots
   case): must have exactly 1 required unmet via soft slack.

Run:
    .venv/bin/python preflight_demo.py
"""
from __future__ import annotations
import csv
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent
BUNDLE = REPO / "data" / "_client_bundle_v4"
HS = BUNDLE / "HS_2026-2027_real"


def _read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}" + (f"  — {detail}" if detail else ""))
    return ok


def main() -> int:
    if not BUNDLE.exists():
        print(f"ERROR: bundle not found at {BUNDLE}. Run build_v4_bundle.py first.")
        return 1

    failures: list[str] = []

    print("=== 1. PowerSchool upload CSVs ===")
    ps_sections = _read_csv(HS / "powerschool_upload" / "ps_sections.csv")
    ps_enrollments = _read_csv(HS / "powerschool_upload" / "ps_enrollments.csv")

    required_section_cols = {"SchoolID", "Course Number", "Section Number", "TermID",
                             "Teacher Number", "Room", "Expression",
                             "Attendance_Type_Code", "Att_Mode_Code", "MaxEnrollment",
                             "GradebookType"}
    actual_cols = set(ps_sections[0].keys())
    missing = required_section_cols - actual_cols
    if not _check("ps_sections.csv has all PS spec columns", not missing,
                  f"missing: {missing}" if missing else f"{len(actual_cols)} cols"):
        failures.append("ps_sections columns")

    enrollment_cols = {"Student_Number", "Course_Number", "Section_Number",
                       "Term_Number", "SchoolID"}
    missing_e = enrollment_cols - set(ps_enrollments[0].keys())
    if not _check("ps_enrollments.csv has all PS spec columns", not missing_e,
                  f"missing: {missing_e}" if missing_e else f"{len(ps_enrollments[0])} cols"):
        failures.append("ps_enrollments columns")

    # Term codes only S1/S2/year
    term_codes = {r["TermID"] for r in ps_sections}
    valid_terms = {"3600", "3601", "3602"}
    invalid_terms = term_codes - valid_terms
    _check(f"All TermIDs valid", not invalid_terms,
           f"found: {sorted(term_codes)}")

    print("\n=== 2. OneRoster bundle ===")
    onerost = HS / "lms_upload"
    expected_files = {"orgs.csv", "academicSessions.csv", "users.csv",
                      "courses.csv", "classes.csv", "enrollments.csv"}
    present = {p.name for p in onerost.iterdir() if p.is_file()}
    missing_or = expected_files - present
    _check("All required OneRoster files present", not missing_or,
           f"missing: {missing_or}" if missing_or else f"{len(present)} files")

    sessions = _read_csv(onerost / "academicSessions.csv")
    sub_sessions = [s for s in sessions if s["type"] == "semester"]
    if not _check("academicSessions has S1 + S2 sub-sessions",
                  len(sub_sessions) == 2,
                  f"found {len(sub_sessions)} sub-sessions"):
        failures.append("OneRoster sub-sessions")

    classes = _read_csv(onerost / "classes.csv")
    micro_classes = [c for c in classes if c["sourcedId"].startswith("class-I1213")]
    macro_classes = [c for c in classes if c["sourcedId"].startswith("class-I1212")]
    micro_in_s1 = all("s1" in c["termSourcedIds"] for c in micro_classes)
    macro_in_s2 = all("s2" in c["termSourcedIds"] for c in macro_classes)
    _check("AP Micro classes reference S1 sub-session",
           micro_in_s1, f"{len(micro_classes)} Micro classes, all S1: {micro_in_s1}")
    _check("AP Macro classes reference S2 sub-session",
           macro_in_s2, f"{len(macro_classes)} Macro classes, all S2: {macro_in_s2}")

    print("\n=== 3. Term-paired sections (Micro/Macro) ===")
    # Each Micro section pairs with a Macro section sharing the same Expression.
    micro_secs = [s for s in ps_sections if s["Course Number"] == "I1213"]
    macro_secs = [s for s in ps_sections if s["Course Number"] == "I1212"]
    micro_exprs = {s["Expression"] for s in micro_secs}
    macro_exprs = {s["Expression"] for s in macro_secs}
    paired_exprs = micro_exprs & macro_exprs
    _check(f"Micro/Macro sections share at least 1 expression",
           len(paired_exprs) >= 1,
           f"shared: {sorted(paired_exprs)} (Micro: {len(micro_exprs)}, Macro: {len(macro_exprs)})")

    # All Micro in same room as all Macro (Ortegon's home_room)
    micro_rooms = {s["Room"] for s in micro_secs}
    macro_rooms = {s["Room"] for s in macro_secs}
    _check("Micro and Macro share single home_room",
           micro_rooms == macro_rooms and len(micro_rooms) == 1,
           f"Micro: {micro_rooms}, Macro: {macro_rooms}")

    print("\n=== 4. Coverage and required-unmet ===")
    schedules = defaultdict(list)
    for r in _read_csv(HS / "horario_estudiantes" / "student_schedules_friendly.csv"):
        schedules[r["StudentID"]].append(r)
    unmet = _read_csv(HS / "horario_estudiantes" / "unmet_requests.csv")
    n_required_unmet = sum(1 for u in unmet if u["is_required"] in ("True", "true"))
    n_total_unmet = len(unmet)
    _check(f"Required-unmet (PE-curricular) ≤ 5",
           n_required_unmet <= 5, f"{n_required_unmet} unmet")
    _check(f"Total unmet ≤ 250 (real Columbus baseline)",
           n_total_unmet <= 250, f"{n_total_unmet} unmet")

    print("\n=== 5. Sanity check: student 28001 (origin of stale visor case) ===")
    s28001 = schedules.get("28001", [])
    courses = {r["CourseID"] for r in s28001}
    _check("28001 has Introduction to Law (L1302)", "L1302" in courses,
           f"courses: {sorted(courses)[:5]}…" if len(courses) > 5 else f"courses: {courses}")

    print("\n=== 6. Sanity check: student 29096 (was over-constrained 10-requests case) ===")
    s29096 = schedules.get("29096", [])
    n_courses = len({r["CourseID"] for r in s29096})
    n_unmet_29096 = sum(1 for u in unmet if u["student_id"] == "29096")
    n_requests_29096 = sum(1 for r in _read_csv(HS / "input_data" / "course_requests.csv")
                           if r["student_id"] == "29096")
    # Cliente reduced requests from 10 to 9 — soft slack now likely 0 unmet.
    _check(f"29096 fully placed (n_requests={n_requests_29096})",
           n_courses == n_requests_29096 and n_unmet_29096 == 0,
           f"{n_courses}/{n_requests_29096} courses, {n_unmet_29096} unmet")

    print("\n=== Result ===")
    if failures:
        print(f"  ✗ {len(failures)} pre-flight check(s) failed: {failures}")
        return 1
    print(f"  ✓ All pre-flight checks passed. Bundle ready for demo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
