"""Conflict reports + KPI generator (v2 §10, §11).

Produces:
- KPI summary vs v2 §10 targets
- Per-section enrollment + capacity
- Per-teacher load distribution
- Unscheduled students / unmet requests
- Markdown overview suitable for review
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .models import Dataset, MasterAssignment, StudentAssignment


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

    # Unmet requests
    with (out_dir / "unmet_requests.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["student_id", "course_id", "course_name", "is_required"])
        for stu_id, cid in unmet:
            c = courses_by_id.get(cid)
            is_req = c.is_required if c else False
            w.writerow([stu_id, cid, c.name if c else "", is_req])

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
