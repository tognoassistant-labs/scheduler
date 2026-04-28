"""PowerSchool-compatible CSV exporter (v2 §9).

Produces three CSV files matching common PowerSchool import templates:
1. sections.csv — section roster (course, teacher, room, period info)
2. enrollments.csv — student → section associations
3. master_schedule.csv — flattened (day, block, section, room, teacher) view

Field mapping is documented inline. Per 2026-04-26 client confirmation
from Columbus IT:
- SchoolID is a number (MS=12000, HS=13000), set via SchoolConfig.school_id
- TermID is the PS term number (3600 for 2026-2027), via SchoolConfig.term_id
- Period (Expression) format is `<block>(<day>)` per slot, concatenated; e.g.
  a section at A1, D2, B4 → "1(A)2(D)4(B)"; a section meeting block 1 on
  days D and E → "1(D-E)".
"""
from __future__ import annotations

import csv
from pathlib import Path

from .models import Dataset, MasterAssignment, SchoolConfig, StudentAssignment


def _resolve_school_id(cfg: SchoolConfig) -> str:
    """PS School_Number — prefer cfg.school_id; fall back to school name string."""
    if cfg.school_id is not None and str(cfg.school_id).strip() != "":
        return str(cfg.school_id)
    return cfg.school


def _resolve_term_id(cfg: SchoolConfig) -> str:
    """PS TermID — prefer cfg.term_id; fall back to year string."""
    if cfg.term_id is not None and str(cfg.term_id).strip() != "":
        return str(cfg.term_id)
    return cfg.year


def _expression(slots: list[tuple[str, int]]) -> str:
    """Format a list of (day, block) slots as PS Expression.

    Examples:
      [("A", 1), ("D", 2), ("B", 4)]  -> "1(A)2(D)4(B)"
      [("E", 3)]                       -> "3(E)"               (advisory)
      [("D", 1), ("E", 1)]             -> "1(D-E)"             (shared block)

    Days within a block are sorted alphabetically and joined with '-'.
    Blocks are output in ascending order.
    """
    by_block: dict[int, list[str]] = {}
    for day, block in slots:
        by_block.setdefault(block, []).append(day)
    parts: list[str] = []
    for block in sorted(by_block):
        days = sorted(by_block[block])
        if len(days) == 1:
            parts.append(f"{block}({days[0]})")
        else:
            parts.append(f"{block}({'-'.join(days)})")
    return "".join(parts)


def export_powerschool(
    ds: Dataset,
    master: list[MasterAssignment],
    students: list[StudentAssignment],
    out_dir: Path,
) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sections_by_id = {s.section_id: s for s in ds.sections}
    courses_by_id = {c.course_id: c for c in ds.courses}
    teachers_by_id = {t.teacher_id: t for t in ds.teachers}
    rooms_by_id = {r.room_id: r for r in ds.rooms}
    master_by_sect = {m.section_id: m for m in master}

    school_id = _resolve_school_id(ds.config)
    term_id = _resolve_term_id(ds.config)

    # 1. sections.csv
    # PS-typical columns: SchoolID, CourseID, SectionID, TeacherID, RoomID, Period, TermID
    with (out_dir / "ps_sections.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "SchoolID", "CourseID", "CourseName", "SectionID", "TeacherID",
            "TeacherName", "RoomID", "RoomName", "Period", "Slots", "TermID", "MaxEnrollment"
        ])
        for s in ds.sections:
            m = master_by_sect.get(s.section_id)
            if m is None:
                continue
            t = teachers_by_id.get(s.teacher_id)
            r = rooms_by_id.get(m.room_id)
            c = courses_by_id.get(s.course_id)
            slots_str = ";".join(f"{d}{b}" for d, b in m.slots)
            w.writerow([
                school_id, s.course_id, c.name if c else "", s.section_id,
                s.teacher_id, t.name if t else "", m.room_id, r.name if r else "",
                _expression(m.slots), slots_str, term_id, s.max_size,
            ])

    # 2. enrollments.csv
    # PS-typical columns: SchoolID, StudentID, SectionID, EnrollmentDate, TermID
    with (out_dir / "ps_enrollments.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["SchoolID", "StudentID", "SectionID", "CourseID", "TermID"])
        for sa in students:
            for sid in sa.section_ids:
                sect = sections_by_id.get(sid)
                if sect is None:
                    continue
                w.writerow([school_id, sa.student_id, sid, sect.course_id, term_id])

    # 3. master_schedule.csv
    with (out_dir / "ps_master_schedule.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Day", "Block", "Period", "SectionID", "CourseID", "TeacherID", "RoomID"])
        for s in ds.sections:
            m = master_by_sect.get(s.section_id)
            if m is None:
                continue
            for (day, block) in m.slots:
                w.writerow([day, block, _expression(m.slots), s.section_id, s.course_id, s.teacher_id, m.room_id])

    # Field-mapping documentation
    (out_dir / "ps_field_mapping.md").write_text(
        """# PowerSchool Field Mapping

Generated CSVs target the Columbus PowerSchool instance per IT confirmation
on 2026-04-26.

## ps_sections.csv → PS `Sections` import
| Engine column | PS field | Format / Source |
|---|---|---|
| SchoolID | School_Number | Number — MS=12000, HS=13000 (set via SchoolConfig.school_id) |
| CourseID | Course_Number | Real PS course IDs preserved through ingester |
| SectionID | Section_Number | Engine uses dotted form (e.g. ENG12.1) — confirm acceptable in PS |
| TeacherID | Teacher_Number | Real PS teacher IDs preserved through ingester |
| RoomID | Room | Real PS room IDs preserved through ingester |
| Period | Expression | Format: `<block>(<day>)` per slot, concatenated. E.g. "1(A)2(D)4(B)" or "1(D-E)" for shared block. Advisory at E3 → "3(E)". |
| Slots | (legacy `<day><block>;...` view) | Engine produces e.g. "A1;D2;B4" — kept for inspection / debugging |
| TermID | TermID | 3600 for 2026-2027 (set via SchoolConfig.term_id) |
| MaxEnrollment | Max_Enrollment | Direct |

## ps_enrollments.csv → PS `CC` (course-section enrollments)
| Engine column | PS field |
|---|---|
| SchoolID | SchoolID (number, see above) |
| StudentID | StudentID (real PS student IDs) |
| SectionID | SectionID |
| CourseID | Course_Number |
| TermID | TermID (3600) |

## ps_master_schedule.csv
A flattened view for quick visual inspection or for SIS systems that
prefer day-block × section rows. Not directly imported by PS but useful
for leadership review and downstream reporting. Period column uses the
new Expression format.

## Confirmed by Columbus IT (2026-04-26)
- A1 SchoolID: number, MS=12000 / HS=13000.
- A2 Period/Expression: `1(A)2(B)3(C)` per slot; `1(D-E)` for shared block.
- A3 TermID: 3600.
- A4-A7 IDs (course/teacher/student/room): the IDs delivered in the input
  data are the real PS IDs; the engine preserves them through ingest+export.
- A8 Sandbox: available.
- A9 IT contacts: Juan Pablo Vallejo and Luis Botero.
""")
