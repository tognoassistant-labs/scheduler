"""Standalone invariant checker for solved schedules.

Verifies the hard constraints + v2 §10 KPI targets directly from the
exported PowerSchool CSVs — independently of the solver. Use this as
post-solve verification: if it passes, the schedule is correct
regardless of what the solver said.

Usage:
    python tests/check_invariants.py path/to/exports/powerschool

Returns 0 if all invariants hold, 1 otherwise. Suitable for CI.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


def _get(row: dict, *keys: str, default: str = "") -> str:
    """Read first present column among `keys` (handles old/new PS column names)."""
    for k in keys:
        v = row.get(k)
        if v is not None and v != "":
            return v
    return default


def _effective_terms(term_id: str) -> tuple[str, ...]:
    """Year-long blocks both S1+S2; S1 (3601) blocks S1; S2 (3602) blocks S2."""
    if term_id == "3601":
        return ("S1",)
    if term_id == "3602":
        return ("S2",)
    return ("S1", "S2")


def check_invariants(ps_dir: Path, balance_threshold: int = 3) -> tuple[int, list[str]]:
    """Return (failure_count, messages).

    `balance_threshold` is the per-course max-dev-from-mean cap (KPI v2 §10).
    Real Columbus at full HS hits dev=4 on courses with high demand; pass 4
    here to make the CLI noisy-but-not-failing on real data, or keep the
    default 3 to enforce the KPI target.
    """
    ps_dir = Path(ps_dir)
    sections_path = ps_dir / "ps_sections.csv"
    enrollments_path = ps_dir / "ps_enrollments.csv"
    if not sections_path.exists():
        return 1, [f"Missing {sections_path}"]
    if not enrollments_path.exists():
        return 1, [f"Missing {enrollments_path}"]

    sections = list(csv.DictReader(sections_path.open()))
    enrollments = list(csv.DictReader(enrollments_path.open()))

    failures: list[str] = []

    # Helper: advisory sections start their course code with "ADV" (real
    # Columbus uses "ADVHS01"; synthetic uses "ADV"). PS spec column name is
    # "Course Number"; older bundles used "CourseID".
    def _course_of(row: dict) -> str:
        return _get(row, "Course Number", "CourseID")

    def _is_advisory(row: dict) -> bool:
        return _course_of(row).upper().startswith("ADV")

    def _section_internal_id(row: dict) -> str:
        return _get(row, "Section_ID_Internal", "SectionID")

    # 1. Teacher double-bookings (HC1) — term-aware: a teacher can teach S1 and
    # S2 sections in the same slot since they alternate semesters. Multi-level
    # Simultaneous sections emit multiple Course Number rows for the same
    # physical section; dedupe by Section_ID_Internal before counting.
    seen_for_hc1: set[str] = set()
    ts_per_slot: dict[tuple[str, str, str], int] = defaultdict(int)
    for s in sections:
        if _is_advisory(s):
            continue
        sid = _section_internal_id(s)
        if sid in seen_for_hc1:
            continue
        seen_for_hc1.add(sid)
        teacher = _get(s, "Teacher Number", "TeacherID")
        term = _get(s, "TermID")
        for slot in s["Slots"].split(";"):
            slot = slot.strip()
            if not slot:
                continue
            for et in _effective_terms(term):
                ts_per_slot[(teacher, slot, et)] += 1
    teacher_violations = sum(1 for c in ts_per_slot.values() if c > 1)
    if teacher_violations:
        failures.append(f"HC1: {teacher_violations} teacher double-booking(s)")

    # 2. Room double-bookings (HC2) — term-aware idem. Multi-level Simultaneous
    # sections share Section_ID_Internal across rows; dedupe before counting.
    seen_physical: set[str] = set()
    rs_per_slot: dict[tuple[str, str, str], int] = defaultdict(int)
    for s in sections:
        if _is_advisory(s):
            continue
        sid = _section_internal_id(s)
        if sid in seen_physical:
            continue
        seen_physical.add(sid)
        room = _get(s, "Room", "RoomID")
        term = _get(s, "TermID")
        for slot in s["Slots"].split(";"):
            slot = slot.strip()
            if not slot:
                continue
            for et in _effective_terms(term):
                rs_per_slot[(room, slot, et)] += 1
    room_violations = sum(1 for c in rs_per_slot.values() if c > 1)
    if room_violations:
        failures.append(f"HC2: {room_violations} room double-booking(s)")

    # 2b. HC2b: Advisory sections (all at E3) must each be in a distinct room.
    advisory_rooms = [_get(s, "Room", "RoomID") for s in sections if _is_advisory(s)]
    if len(advisory_rooms) != len(set(advisory_rooms)):
        n_dup = len(advisory_rooms) - len(set(advisory_rooms))
        failures.append(f"HC2b: {n_dup} advisory section(s) share rooms (all advisories meet at E3)")

    # 3. Student time conflicts — term-aware. PS column is "Student_Number".
    sect_to_slots = {_section_internal_id(s): s["Slots"].split(";") for s in sections}
    sect_to_term = {_section_internal_id(s): _get(s, "TermID") for s in sections}
    stu_slot_count: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    for e in enrollments:
        sid = _get(e, "Section_ID_Internal", "SectionID")
        student = _get(e, "Student_Number", "StudentID")
        for slot in sect_to_slots.get(sid, []):
            if not slot:
                continue
            for et in _effective_terms(sect_to_term.get(sid, "")):
                stu_slot_count[student][(slot, et)] += 1
    student_violations = sum(
        1 for slots in stu_slot_count.values() for c in slots.values() if c > 1
    )
    if student_violations:
        failures.append(f"HC3: {student_violations} student time conflict(s)")

    # 4. Capacity — count enrollments per physical section. Multi-level
    # Simultaneous sections are counted via Section_ID_Internal so the merged
    # roster shows up under the single physical section.
    sec_to_course = {_section_internal_id(s): _course_of(s) for s in sections}
    sec_max_size = {
        _section_internal_id(s): int(s.get("MaxEnrollment") or 25)
        for s in sections
    }
    size_count: dict[str, int] = defaultdict(int)
    for e in enrollments:
        size_count[_get(e, "Section_ID_Internal", "SectionID")] += 1
    cap_violations = []
    for sid, n in size_count.items():
        cap = sec_max_size.get(sid, 25)
        # AP Research allows 26 (Columbus AP Research is OB1532; synthetic uses APRES).
        if sec_to_course.get(sid) in ("APRES", "OB1532"):
            cap = max(cap, 26)
        if n > cap:
            cap_violations.append(f"{sid}: {n}/{cap}")
    if cap_violations:
        failures.append(f"HC4: {len(cap_violations)} capacity violation(s) — {', '.join(cap_violations[:3])}")

    # 5. Advisory at E3
    adv_violations = sum(
        1 for s in sections if _is_advisory(s) and s["Slots"] != "E3"
    )
    if adv_violations:
        failures.append(f"HC5: {adv_violations} advisory section(s) not at E3")

    # 6. Per-course balance (v2 §10): max-dev from mean ≤ 3
    by_course: dict[str, list[int]] = defaultdict(list)
    for sid, n in size_count.items():
        by_course[sec_to_course.get(sid, "")].append(n)
    worst_dev = 0.0
    worst_course = ""
    for cid, sizes in by_course.items():
        if len(sizes) < 2:
            continue
        mean = sum(sizes) / len(sizes)
        dev = max(abs(s - mean) for s in sizes)
        if dev > worst_dev:
            worst_dev = dev
            worst_course = cid
    if round(worst_dev) > balance_threshold:
        failures.append(
            f"KPI: section balance {round(worst_dev)} > {balance_threshold} (worst course: {worst_course})"
        )

    return len(failures), failures


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    ps_dir = Path(args[0])
    n, failures = check_invariants(ps_dir)
    if n == 0:
        print(f"✓ All invariants pass for {ps_dir}")
        return 0
    print(f"✗ {n} invariant(s) failed for {ps_dir}:")
    for f in failures:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
