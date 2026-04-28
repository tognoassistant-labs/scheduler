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


def _build_section_number_map(ds: Dataset) -> dict[str, str]:
    """Map internal section_id (e.g. 'G0901.1', 'ADVHS01.16') to PS-compatible
    numeric Section_Number per the official import spec (2026-04-28):

      "Section Number must be a 'real number' with no alpha characters and
       no leading zeros. A section number must be unique per course, school
       and term."

    We assign sequential numbers per (course, term) starting at 101. The
    starting offset matches the example in the PS spec ("101"). Stable
    ordering: by appearance in ds.sections.
    """
    counter_per_course: dict[str, int] = {}
    section_num_by_id: dict[str, str] = {}
    for s in ds.sections:
        next_n = counter_per_course.get(s.course_id, 100) + 1
        counter_per_course[s.course_id] = next_n
        section_num_by_id[s.section_id] = str(next_n)
    return section_num_by_id


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

    # PS-compatible numeric Section_Number per the official import spec.
    # We keep the engine-internal id around in `Section_ID_Internal` for
    # cross-referencing back to engine logs / horario_estudiantes/.
    sect_num = _build_section_number_map(ds)

    # 1. ps_sections.csv — matches the official PS import spec (2026-04-28):
    #    SchoolID, Course Number, Section Number, TermID, Teacher Number, Room,
    #    Expression, Attendance_Type_Code, Att_Mode_Code, MaxEnrollment, GradebookType.
    # Extra cosmetic columns (CourseName, TeacherName, RoomName, Section_ID_Internal)
    # are kept BEFORE import for human review and must be deleted prior to upload —
    # the spec explicitly says "Course Name should be deleted prior to import".
    with (out_dir / "ps_sections.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            # Required-for-import columns first (keep contiguous so client can
            # delete the trailing review-only columns easily):
            "SchoolID", "Course Number", "Section Number", "TermID",
            "Teacher Number", "Room", "Expression",
            "Attendance_Type_Code", "Att_Mode_Code", "MaxEnrollment", "GradebookType",
            # Review-only columns (delete before import per PS spec):
            "Course Name", "Teacher Name", "Room Name", "Section_ID_Internal", "Slots",
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
                school_id,
                s.course_id,
                sect_num[s.section_id],            # numeric Section Number
                term_id,
                s.teacher_id,
                m.room_id,
                _expression(m.slots),
                "2",                                # Attendance_Type_Code: 2=each meeting separately
                "ATT_ModeMeeting",                  # Att_Mode_Code: literal per spec
                s.max_size,
                "2",                                # GradebookType: 2=PowerTeacher Pro
                # Review-only:
                c.name if c else "",
                t.name if t else "",
                r.name if r else "",
                s.section_id,                       # internal id for back-reference
                slots_str,
            ])

    # 2. ps_enrollments.csv — matches PS Enrollments import spec:
    #    Student_Number, Course_Number, Section_Number, Term_Number, SchoolID,
    #    + optional Dateenrolled / DateLeft (left blank = PS uses term defaults).
    # Section_ID_Internal is review-only — DELETE before import. It is here so
    # auditors can cross-reference against ps_sections / horario_estudiantes
    # using the engine slug (e.g. ADVHS01.16) before the numeric Section_Number
    # rewrite obscures it.
    with (out_dir / "ps_enrollments.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "Student_Number", "Course_Number", "Section_Number",
            "Dateenrolled", "DateLeft", "Term_Number", "SchoolID",
            "Section_ID_Internal",
        ])
        for sa in students:
            for sid in sa.section_ids:
                sect = sections_by_id.get(sid)
                if sect is None:
                    continue
                w.writerow([
                    sa.student_id,
                    sect.course_id,
                    sect_num[sid],
                    "",                              # Dateenrolled: blank → PS uses term start
                    "",                              # DateLeft: blank → PS uses term end
                    term_id,
                    school_id,
                    sid,                             # internal slug (delete before import)
                ])

    # 3. master_schedule.csv (engine-internal flattened view; not a PS import target)
    with (out_dir / "ps_master_schedule.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Day", "Block", "Period", "SectionNumber", "Section_ID_Internal",
                    "CourseID", "TeacherID", "RoomID"])
        for s in ds.sections:
            m = master_by_sect.get(s.section_id)
            if m is None:
                continue
            for (day, block) in m.slots:
                w.writerow([
                    day, block, _expression(m.slots),
                    sect_num[s.section_id], s.section_id,
                    s.course_id, s.teacher_id, m.room_id,
                ])

    # Field-mapping documentation
    (out_dir / "ps_field_mapping.md").write_text(
        """# PowerSchool Field Mapping

Generated CSVs target the Columbus PowerSchool instance per IT confirmations.

## ps_sections.csv → PS `Sections` import (Section Master Schedule)

Columns are emitted in import order; review-only columns are last so the
client can delete them in one block before uploading.

| CSV column | PS field | Required? | Format |
|---|---|---|---|
| SchoolID | School_Number | ✅ | Number — MS=12000, HS=13000 |
| Course Number | Course_Number | ✅ | Real PS course numbers (ingester preserves them) |
| Section Number | Section_Number | ✅ | **Numeric only**, no alpha, no leading zeros. Engine assigns sequentially per course starting at 101 (101, 102, 103…) |
| TermID | TermID | ✅ | 3600 = year-long, 3601 = S1, 3602 = S2 (Columbus 2026-2027, confirmed by client 2026-04-28) |
| Teacher Number | Teacher_Number | ✅ | Real PS teacher numbers |
| Room | Room | (recommended) | Real PS room numbers |
| Expression | Expression | ✅ | Period+Day. Format: `1(A)2(B)3(C)` per slot; `1(D-E)` for shared block |
| Attendance_Type_Code | Attendance_Type_Code | ✅ | `2` = each meeting tracked separately (multi-block sections) |
| Att_Mode_Code | Att_Mode_Code | ✅ | Literal `ATT_ModeMeeting` |
| MaxEnrollment | Max_Enrollment | (recommended) | From course or section override |
| GradebookType | GradebookType | ✅ | `2` = PowerTeacher Pro |
| **Course Name** | (delete before import) | review-only | For human review only |
| **Teacher Name** | (delete before import) | review-only | For human review only |
| **Room Name** | (delete before import) | review-only | For human review only |
| **Section_ID_Internal** | (delete before import) | review-only | Engine slug (e.g. `G0901.1`) — for back-reference to logs |
| **Slots** | (delete before import) | review-only | Day+block list e.g. `A1;D2;B4` |

## ps_enrollments.csv → PS Section Enrollments import

| CSV column | PS field | Required? | Format |
|---|---|---|---|
| Student_Number | Student_Number | ✅ | Real PS student numbers |
| Course_Number | Course_Number | ✅ | |
| Section_Number | Section_Number | ✅ | Matches numeric Section_Number in ps_sections.csv |
| Dateenrolled | Dateenrolled | (recommended) | Blank → PS uses term start |
| DateLeft | DateLeft | (recommended) | Blank → PS uses term end |
| Term_Number | Term_Number | ✅ | Same value as TermID in ps_sections.csv |
| SchoolID | SchoolID | ✅ | |

## ps_master_schedule.csv

Engine-internal flattened (day, block, section) view. **Not** a PS import
target — for inspection only. Includes both the new numeric Section_Number
and the engine-internal Section_ID_Internal for cross-referencing.

## Confirmed by client / IT

- 2026-04-26 (IT — Juan Pablo Vallejo, Luis Botero):
  - SchoolID: number, MS=12000 / HS=13000.
  - Period/Expression: `1(A)2(B)3(C)` per slot; `1(D-E)` for shared block.
  - IDs (course/teacher/student/room): real PS IDs preserved through ingest+export.
- 2026-04-28 (client via PS import spec sheet):
  - Section Number must be numeric (no alpha, no leading zeros).
  - Att_Mode_Code = `ATT_ModeMeeting`, Attendance_Type_Code = `2`, GradebookType = `2`.
  - TermID values: **3600** (year-long), **3601** (S1), **3602** (S2).
""")
