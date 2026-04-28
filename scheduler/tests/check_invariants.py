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


def check_invariants(ps_dir: Path) -> tuple[int, list[str]]:
    """Return (failure_count, messages)."""
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

    # Helper: detect advisory sections by CourseID rather than Period (the
    # Period value is now `3(E)` per Columbus PS Expression format, not "ADV").
    def _is_advisory(row: dict) -> bool:
        return row.get("CourseID") == "ADV"

    # 1. Teacher double-bookings (HC1) — uses (TeacherID, Slots) since the
    # Period (Expression) for two academic sections at different schemes can
    # collide if they happen to share one (day, block) cell. Slots is the
    # ground-truth multi-cell representation.
    ts_per_slot: dict[tuple[str, str], int] = defaultdict(int)
    for s in sections:
        if _is_advisory(s):
            continue
        for slot in s["Slots"].split(";"):
            slot = slot.strip()
            if slot:
                ts_per_slot[(s["TeacherID"], slot)] += 1
    teacher_violations = sum(1 for c in ts_per_slot.values() if c > 1)
    if teacher_violations:
        failures.append(f"HC1: {teacher_violations} teacher double-booking(s)")

    # 2. Room double-bookings (HC2) — academic sections only (advisory rooms
    # checked separately below). Same Slots-based ground truth.
    rs_per_slot: dict[tuple[str, str], int] = defaultdict(int)
    for s in sections:
        if _is_advisory(s):
            continue
        for slot in s["Slots"].split(";"):
            slot = slot.strip()
            if slot:
                rs_per_slot[(s["RoomID"], slot)] += 1
    room_violations = sum(1 for c in rs_per_slot.values() if c > 1)
    if room_violations:
        failures.append(f"HC2: {room_violations} room double-booking(s)")

    # 2b. HC2b: Advisory sections (all at E3) must each be in a distinct room.
    advisory_rooms = [s["RoomID"] for s in sections if _is_advisory(s)]
    if len(advisory_rooms) != len(set(advisory_rooms)):
        n_dup = len(advisory_rooms) - len(set(advisory_rooms))
        failures.append(f"HC2b: {n_dup} advisory section(s) share rooms (all advisories meet at E3)")

    # 3. Student time conflicts
    sect_to_slots = {s["SectionID"]: s["Slots"].split(";") for s in sections}
    stu_slot_count: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in enrollments:
        for slot in sect_to_slots.get(e["SectionID"], []):
            if slot:
                stu_slot_count[e["StudentID"]][slot] += 1
    student_violations = sum(
        1 for slots in stu_slot_count.values() for c in slots.values() if c > 1
    )
    if student_violations:
        failures.append(f"HC3: {student_violations} student time conflict(s)")

    # 4. Capacity
    sec_to_course = {s["SectionID"]: s["CourseID"] for s in sections}
    sec_max_size = {s["SectionID"]: int(s.get("MaxEnrollment", 25) or 25) for s in sections}
    size_count: dict[str, int] = defaultdict(int)
    for e in enrollments:
        size_count[e["SectionID"]] += 1
    cap_violations = []
    for sid, n in size_count.items():
        cap = sec_max_size.get(sid, 25)
        # AP Research is allowed 26
        if sec_to_course.get(sid) == "APRES":
            cap = max(cap, 26)
        if n > cap:
            cap_violations.append(f"{sid}: {n}/{cap}")
    if cap_violations:
        failures.append(f"HC4: {len(cap_violations)} capacity violation(s) — {', '.join(cap_violations[:3])}")

    # 5. Advisory at E3
    adv_violations = sum(1 for s in sections if s["CourseID"] == "ADV" and s["Slots"] != "E3")
    if adv_violations:
        failures.append(f"HC5: {adv_violations} advisory section(s) not at E3")

    # 6. Per-course balance (v2 §10): max-dev from mean ≤ 3
    by_course: dict[str, list[int]] = defaultdict(list)
    for sid, n in size_count.items():
        by_course[sec_to_course[sid]].append(n)
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
    if round(worst_dev) > 3:
        failures.append(f"KPI: section balance {round(worst_dev)} > 3 (worst course: {worst_course})")

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
