"""Conflict reports + KPI generator (v2 §10, §11).

Produces:
- KPI summary vs v2 §10 targets
- Per-section enrollment + capacity
- Per-teacher load distribution
- Unscheduled students / unmet requests
- Per-unmet diagnosis (Principle 5 — generate infeasibility reports)
- Markdown overview suitable for review
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .models import Dataset, MasterAssignment, StudentAssignment


# Diagnosis reason vocabulary. Single source of truth for the labels used in
# `unmet_requests.csv`'s `reason` column and `unmet_diagnosis.md`. Order is
# the priority used when multiple constraints block a student — picks the
# most actionable blocker first, since that's what the operator would relax.
DIAGNOSIS_REASONS: tuple[str, ...] = (
    "no_section",      # the course has zero sections in the dataset
    "grid_clash",      # every section's slots clash with the student's other assignments
    "capacity",        # every section is at max_size
    "restriction",     # every section's teacher is on the student's restricted list
    "separation",      # every section is blocked by a separation pair already enrolled there
    "unknown",         # solver anomaly — no constraint visibly blocks the student
)


def diagnose_unmet(
    ds: Dataset,
    master: list[MasterAssignment],
    students: list[StudentAssignment],
    unmet: list[tuple[str, str]],
) -> dict[tuple[str, str], str]:
    """Classify each unmet (student, course) into a `DIAGNOSIS_REASONS` value.

    The diagnosis answers: *which constraint, if relaxed, would have let this
    student into this course?* The output drives `unmet_requests.csv:reason`
    and `unmet_diagnosis.md` so coord. académica can triage the ~105 unmet
    students for manual placement post-import.

    Heuristic (Principle 5: report what the solver concluded, do not re-solve):
    1. If the course has zero sections → `no_section`.
    2. Per section, list every visible blocker for this student:
       - teacher in `restricted_teacher_ids` → `restriction`
       - section at max_size → `capacity`
       - any of the section's slots already taken by the student's other
         assignments → `grid_clash`
       - a separation partner of this student already enrolled → `separation`
    3. If every section is blocked by the SAME constraint → that's the diagnosis.
    4. Otherwise pick the constraint that, in priority order, blocks the
       largest number of sections. Priority follows `DIAGNOSIS_REASONS`: grid
       (the dominant case per the lessons doc) before capacity, then
       restriction, then separation.
    5. If a section has zero blockers but the student is still unmet → `unknown`
       (the solver should have placed the student there; data anomaly).
    """
    sections_by_course: dict[str, list] = defaultdict(list)
    for s in ds.sections:
        sections_by_course[s.course_id].append(s)

    master_by_sect = {m.section_id: m for m in master}

    enrollment: Counter[str] = Counter()
    students_by_section: dict[str, set[str]] = defaultdict(set)
    student_slots: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for sa in students:
        for sid in sa.section_ids:
            enrollment[sid] += 1
            students_by_section[sid].add(sa.student_id)
            m = master_by_sect.get(sid)
            if m:
                for slot in m.slots:
                    student_slots[sa.student_id].add(tuple(slot))

    sep_partners: dict[str, set[str]] = defaultdict(set)
    for a, b in ds.behavior.separations:
        sep_partners[a].add(b)
        sep_partners[b].add(a)

    student_by_id = {st.student_id: st for st in ds.students}

    # Priority order: grid_clash before capacity (lessons doc says grid is
    # dominant), then restriction (reflects student-specific data), then
    # separation (softest — currently enforced as soft anyway).
    priority = ("grid_clash", "capacity", "restriction", "separation")

    diagnoses: dict[tuple[str, str], str] = {}
    for stu_id, course_id in unmet:
        sects = sections_by_course.get(course_id, [])
        if not sects:
            diagnoses[(stu_id, course_id)] = "no_section"
            continue
        st = student_by_id.get(stu_id)
        if st is None:
            diagnoses[(stu_id, course_id)] = "unknown"
            continue

        slots_taken = student_slots.get(stu_id, set())
        partners = sep_partners.get(stu_id, set())

        per_section: list[set[str]] = []
        for sec in sects:
            blockers: set[str] = set()
            if sec.teacher_id in st.restricted_teacher_ids:
                blockers.add("restriction")
            if enrollment[sec.section_id] >= sec.max_size:
                blockers.add("capacity")
            m = master_by_sect.get(sec.section_id)
            if m and any(tuple(slot) in slots_taken for slot in m.slots):
                blockers.add("grid_clash")
            if partners and partners.intersection(students_by_section.get(sec.section_id, set())):
                blockers.add("separation")
            per_section.append(blockers)

        # If any section has zero visible blockers, the solver should have
        # placed the student there — flag as anomaly.
        if any(not b for b in per_section):
            diagnoses[(stu_id, course_id)] = "unknown"
            continue

        # Pick the diagnosis: priority-ordered single blocker that explains
        # the most sections.
        section_count = len(per_section)
        per_blocker_count = Counter(b for blist in per_section for b in blist)
        # Common blocker = present in EVERY section's blocker set.
        common = {b for b, c in per_blocker_count.items() if c == section_count}
        chosen = next((p for p in priority if p in common), None)
        if chosen is None:
            # No single blocker explains all sections; report the priority
            # blocker with the highest section coverage.
            chosen = next((p for p in priority if p in per_blocker_count), None)
        diagnoses[(stu_id, course_id)] = chosen or "unknown"

    return diagnoses


def write_unmet_diagnosis(
    ds: Dataset,
    unmet: list[tuple[str, str]],
    diagnoses: dict[tuple[str, str], str],
    out_path: Path,
) -> Path:
    """Markdown summary of unmet diagnoses for school review."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    courses_by_id = {c.course_id: c for c in ds.courses}
    students_by_id = {st.student_id: st for st in ds.students}

    by_reason = Counter(diagnoses.values())
    by_course_reason: dict[str, Counter] = defaultdict(Counter)
    by_grade_reason: dict[int, Counter] = defaultdict(Counter)
    for (sid, cid), reason in diagnoses.items():
        by_course_reason[cid][reason] += 1
        st = students_by_id.get(sid)
        if st is not None:
            by_grade_reason[st.grade][reason] += 1

    lines: list[str] = [
        "# Unmet diagnosis",
        "",
        f"Total unmet (student, course) pairs: **{len(unmet)}**.",
        "",
        "Each unmet has been classified into one of:",
        "",
        "- `no_section` — the course has zero sections in the dataset (data issue).",
        "- `grid_clash` — every section's slots clash with the student's other "
        "assignments (the dominant case for Columbus per the lessons doc — "
        "**grid-bound, not capacity-bound**).",
        "- `capacity` — every section is at `max_size`. Opening a section would help.",
        "- `restriction` — every section's teacher is on the student's "
        "`restricted_teacher_ids` list.",
        "- `separation` — every section is blocked by a separation pair already enrolled.",
        "- `unknown` — solver anomaly: no visible constraint blocks the student. "
        "Investigate the data.",
        "",
        "## Distribution by reason",
        "",
        "| Reason | Count | % |",
        "|---|---|---|",
    ]
    total = max(1, len(unmet))
    for reason in DIAGNOSIS_REASONS:
        n = by_reason.get(reason, 0)
        if n == 0:
            continue
        lines.append(f"| `{reason}` | {n} | {100.0 * n / total:.1f}% |")

    lines += ["", "## Top 20 courses by unmet count", "",
              "| Course | Total unmet | Dominant reason |",
              "|---|---|---|"]
    courses_ranked = sorted(
        by_course_reason.items(),
        key=lambda kv: -sum(kv[1].values()),
    )[:20]
    for cid, cr in courses_ranked:
        c = courses_by_id.get(cid)
        cname = c.name if c else "?"
        total_c = sum(cr.values())
        dominant = max(cr.items(), key=lambda x: x[1])[0]
        lines.append(f"| `{cid}` ({cname}) | {total_c} | `{dominant}` ({cr[dominant]}) |")

    lines += ["", "## By grade", "",
              "| Grade | " + " | ".join(f"`{r}`" for r in DIAGNOSIS_REASONS) + " |",
              "|---|" + "|".join(["---"] * len(DIAGNOSIS_REASONS)) + "|"]
    for grade in sorted(by_grade_reason):
        cr = by_grade_reason[grade]
        cells = " | ".join(str(cr.get(r, 0)) for r in DIAGNOSIS_REASONS)
        lines.append(f"| {grade} | {cells} |")

    lines += [
        "",
        "## How to use this report",
        "",
        "1. Filter `unmet_requests.csv` by `reason='grid_clash'` to find students "
        "who need a slot swap (most common case at Columbus).",
        "2. `reason='capacity'` rows are candidates for section-expansion "
        "discussion with admin (school has frozen sections for 2026-2027).",
        "3. `reason='separation'` rows can be reviewed against the counselor "
        "recommendations sheet — soft separations may be relaxed case-by-case.",
        "4. `reason='restriction'` rows reflect explicit teacher-avoid rules; "
        "review the source data if the count is unexpectedly high.",
        "5. `reason='no_section'` rows are pure data issues — the course was "
        "requested but never sectioned. Fix the input.",
        "6. `reason='unknown'` rows should be empty in a healthy run. If "
        "present, investigate the dataset before re-running.",
        "",
    ]

    out_path.write_text("\n".join(lines) + "\n")
    return out_path


@dataclass
class KPIReport:
    fully_scheduled_pct: float
    required_fulfillment_pct: float
    first_choice_elective_pct: float
    section_balance_max_dev: int
    teacher_load_max_dev: int
    unscheduled_students: int
    unmet_requests: int
    targets_met: dict[str, bool]

    def summary(self) -> str:
        lines = [
            "## KPI vs v2 §10 targets",
            "",
            f"| Metric | Value | Target | Met |",
            f"|---|---|---|---|",
            f"| Fully scheduled students | {self.fully_scheduled_pct:.1f}% | ≥98% | {'✅' if self.targets_met['fully_scheduled'] else '❌'} |",
            f"| Required course fulfillment | {self.required_fulfillment_pct:.1f}% | ≥98% | {'✅' if self.targets_met['required'] else '❌'} |",
            f"| First-choice electives | {self.first_choice_elective_pct:.1f}% | ≥80% | {'✅' if self.targets_met['first_choice'] else '❌'} |",
            f"| Section balance (max dev from mean) | {self.section_balance_max_dev} students | ≤3 | {'✅' if self.targets_met['balance'] else '❌'} |",
            f"| Unscheduled (missing required) | {self.unscheduled_students} | 0 | {'✅' if self.unscheduled_students == 0 else '❌'} |",
            f"| Time conflicts | 0 | 0 | ✅ (enforced by solver) |",
        ]
        return "\n".join(lines)


def compute_kpis(
    ds: Dataset,
    master: list[MasterAssignment],
    students: list[StudentAssignment],
    unmet: list[tuple[str, str]],
) -> KPIReport:
    sections_by_id = {s.section_id: s for s in ds.sections}
    courses_by_id = {c.course_id: c for c in ds.courses}

    student_assigns = {sa.student_id: sa for sa in students}

    # Required fulfillment + first-choice electives
    required_total = 0
    required_met = 0
    elective_rank1_total = 0
    elective_rank1_met = 0
    fully_scheduled = 0

    for st in ds.students:
        granted = student_assigns.get(st.student_id, StudentAssignment(student_id=st.student_id, section_ids=[]))
        granted_courses = {sections_by_id[sid].course_id for sid in granted.section_ids}
        rank1_required = [r for r in st.requested_courses if r.is_required]
        rank1_elective = [r for r in st.requested_courses if r.rank == 1 and not r.is_required]

        for r in rank1_required:
            required_total += 1
            if r.course_id in granted_courses:
                required_met += 1
        for r in rank1_elective:
            elective_rank1_total += 1
            if r.course_id in granted_courses:
                elective_rank1_met += 1

        # Fully scheduled = received all required + Advisory
        if all(r.course_id in granted_courses for r in rank1_required):
            fully_scheduled += 1

    fully_pct = 100.0 * fully_scheduled / max(1, len(ds.students))
    req_pct = 100.0 * required_met / max(1, required_total)
    elec_pct = 100.0 * elective_rank1_met / max(1, elective_rank1_total)

    # Section balance: max deviation from mean within course
    sections_by_course: dict[str, list[str]] = defaultdict(list)
    for s in ds.sections:
        sections_by_course[s.course_id].append(s.section_id)
    enrollment: dict[str, int] = defaultdict(int)
    for sa in students:
        for sid in sa.section_ids:
            enrollment[sid] += 1

    max_dev = 0
    for cid, sect_list in sections_by_course.items():
        if len(sect_list) < 2:
            continue
        sizes = [enrollment[sid] for sid in sect_list]
        mean = sum(sizes) / len(sizes)
        dev = max(abs(s - mean) for s in sizes)
        max_dev = max(max_dev, int(round(dev)))

    # Teacher load deviation
    teacher_loads: dict[str, int] = defaultdict(int)
    for s in ds.sections:
        teacher_loads[s.teacher_id] += 1
    if teacher_loads:
        loads = list(teacher_loads.values())
        mean_load = sum(loads) / len(loads)
        teacher_dev = int(round(max(abs(l - mean_load) for l in loads)))
    else:
        teacher_dev = 0

    targets = {
        "fully_scheduled": fully_pct >= 98.0,
        "required": req_pct >= 98.0,
        "first_choice": elec_pct >= 80.0,
        "balance": max_dev <= 3,
        "conflicts": (len(unmet) / max(1, len(ds.students))) < 0.05,
    }

    return KPIReport(
        fully_scheduled_pct=fully_pct,
        required_fulfillment_pct=req_pct,
        first_choice_elective_pct=elec_pct,
        section_balance_max_dev=max_dev,
        teacher_load_max_dev=teacher_dev,
        unscheduled_students=len(ds.students) - fully_scheduled,
        unmet_requests=len(unmet),
        targets_met=targets,
    )


def write_reports(
    ds: Dataset,
    master: list[MasterAssignment],
    students: list[StudentAssignment],
    unmet: list[tuple[str, str]],
    out_dir: Path,
    unmet_reasons: dict[tuple[str, str], str] | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    sections_by_id = {s.section_id: s for s in ds.sections}
    courses_by_id = {c.course_id: c for c in ds.courses}
    teachers_by_id = {t.teacher_id: t for t in ds.teachers}
    rooms_by_id = {r.room_id: r for r in ds.rooms}

    enrollment: dict[str, int] = defaultdict(int)
    for sa in students:
        for sid in sa.section_ids:
            enrollment[sid] += 1

    # Per-section CSV
    with (out_dir / "sections_with_enrollment.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section_id", "course_id", "course_name", "teacher_id", "teacher_name",
                    "scheme", "room_id", "room_name", "enrolled", "max_size", "utilization_pct", "slots"])
        master_by_sect = {m.section_id: m for m in master}
        for s in ds.sections:
            m = master_by_sect.get(s.section_id)
            if m is None:
                continue
            t = teachers_by_id.get(s.teacher_id)
            r = rooms_by_id.get(m.room_id)
            c = courses_by_id.get(s.course_id)
            enrolled = enrollment.get(s.section_id, 0)
            util = 100.0 * enrolled / max(1, s.max_size)
            slots_str = ";".join(f"{d}{b}" for d, b in m.slots)
            w.writerow([
                s.section_id, s.course_id, c.name if c else "", s.teacher_id,
                t.name if t else "", m.scheme, m.room_id, r.name if r else "",
                enrolled, s.max_size, f"{util:.1f}", slots_str
            ])

    # Per-student CSV — n_courses excludes Advisory; n_requested counts only the
    # student's REAL course requests (not the synthetic Advisory we add to all).
    # `missing_courses` lists requested course_ids that weren't assigned, so the
    # school can validate row-by-row that every student got every request.
    advisory_course_ids = {c.course_id for c in ds.courses if c.is_advisory}
    with (out_dir / "student_schedules.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "student_id", "name", "grade",
            "n_requested", "n_assigned", "n_missing",
            "section_ids", "course_ids", "missing_courses",
        ])
        student_assigns = {sa.student_id: sa for sa in students}
        for st in ds.students:
            sa = student_assigns.get(st.student_id, StudentAssignment(student_id=st.student_id, section_ids=[]))
            cids = [sections_by_id[sid].course_id for sid in sa.section_ids if sid in sections_by_id]
            assigned_real = [cid for cid in cids if cid not in advisory_course_ids]
            requested_real = [r.course_id for r in st.requested_courses if r.course_id not in advisory_course_ids]
            missing = sorted(set(requested_real) - set(assigned_real))
            w.writerow([
                st.student_id, st.name, st.grade,
                len(set(requested_real)), len(set(assigned_real)), len(missing),
                "|".join(sa.section_ids), "|".join(cids), "|".join(missing),
            ])

    # Unmet requests — Principle 5: every row carries a `reason` so coord.
    # académica can triage. If no diagnosis was supplied (legacy callers),
    # compute one inline so behavior remains useful.
    if unmet_reasons is None:
        unmet_reasons = diagnose_unmet(ds, master, students, unmet)
    with (out_dir / "unmet_requests.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["student_id", "course_id", "course_name", "is_required", "reason"])
        for stu_id, cid in unmet:
            c = courses_by_id.get(cid)
            is_req = c.is_required if c else False
            reason = unmet_reasons.get((stu_id, cid), "unknown")
            w.writerow([stu_id, cid, c.name if c else "", is_req, reason])

    # Teacher load summary
    teacher_loads: dict[str, list[str]] = defaultdict(list)
    for s in ds.sections:
        teacher_loads[s.teacher_id].append(s.section_id)
    with (out_dir / "teacher_loads.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["teacher_id", "name", "department", "n_sections", "max_load", "section_ids"])
        for t in ds.teachers:
            sids = teacher_loads.get(t.teacher_id, [])
            w.writerow([t.teacher_id, t.name, t.department, len(sids), t.max_load, "|".join(sids)])

    # Markdown KPI summary
    kpi = compute_kpis(ds, master, students, unmet)
    md_lines = [
        f"# Schedule Report — {ds.config.school}, Grade {ds.config.grade}, {ds.config.year}",
        "",
        kpi.summary(),
        "",
        "## Capacity overview",
        "",
        "| Course | Sections | Enrolled / Capacity | Avg / Section |",
        "|---|---|---|---|",
    ]
    sections_by_course: dict[str, list[str]] = defaultdict(list)
    for s in ds.sections:
        sections_by_course[s.course_id].append(s.section_id)
    for cid in sorted(sections_by_course):
        sect_list = sections_by_course[cid]
        c = courses_by_id.get(cid)
        cap = sum(sections_by_id[sid].max_size for sid in sect_list)
        enr = sum(enrollment.get(sid, 0) for sid in sect_list)
        avg = enr / len(sect_list) if sect_list else 0
        md_lines.append(f"| {cid} ({c.name if c else ''}) | {len(sect_list)} | {enr}/{cap} | {avg:.1f} |")

    md_lines += [
        "",
        "## Top unmet rank-1 requests",
        "",
    ]
    by_course = Counter(c for _, c in unmet)
    for cid, n in by_course.most_common(10):
        c = courses_by_id.get(cid)
        md_lines.append(f"- **{cid}** ({c.name if c else ''}): {n} students did not get their first choice")

    md_lines += [
        "",
        "## Teacher load",
        "",
        "| Teacher | Department | Sections | Max load |",
        "|---|---|---|---|",
    ]
    for t in ds.teachers:
        n = len(teacher_loads.get(t.teacher_id, []))
        md_lines.append(f"| {t.name} ({t.teacher_id}) | {t.department} | {n} | {t.max_load} |")

    md_path = out_dir / "schedule_report.md"
    md_path.write_text("\n".join(md_lines) + "\n")
    return md_path
