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
from collections import defaultdict
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


def _build_section_number_map(ds: Dataset) -> dict[tuple[str, str], str]:
    """Map (section_id, course_id) → PS-compatible numeric Section_Number per the
    official import spec (2026-04-28):

      "Section Number must be a 'real number' with no alpha characters and
       no leading zeros. A section number must be unique per course, school
       and term."

    For Simultaneous multi-level sections (Section.linked_course_ids non-empty),
    each linked course gets its OWN Section_Number — they may collide numerically
    across courses (course A section 101 and course B section 101 are distinct
    PS rows because Section_Number is unique per course, not globally).

    Counters per course start at 101 to match the PS spec example. Stable
    ordering: by appearance in ds.sections.
    """
    counter_per_course: dict[str, int] = {}
    section_num: dict[tuple[str, str], str] = {}
    for s in ds.sections:
        for cid in [s.course_id] + list(s.linked_course_ids):
            next_n = counter_per_course.get(cid, 100) + 1
            counter_per_course[cid] = next_n
            section_num[(s.section_id, cid)] = str(next_n)
    return section_num


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
            slots_str = ";".join(f"{d}{b}" for d, b in m.slots)
            # v4.2 — Term sections (Section.term_id set) override the school's
            # default TermID (3600) with their own (3601=S1, 3602=S2).
            section_term_id = s.term_id if s.term_id else term_id
            # v4.2 — Simultaneous: emit ONE row per covered course (primary +
            # each linked course). All rows share Teacher/Room/Expression so
            # PS sees them as physically the same class with multiple course
            # codes attached.
            covered_courses = [s.course_id] + list(s.linked_course_ids)
            for cid in covered_courses:
                c = courses_by_id.get(cid)
                w.writerow([
                    school_id,
                    cid,
                    sect_num[(s.section_id, cid)],     # numeric per-course Section Number
                    section_term_id,
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
    # Section_ID_Internal is review-only — DELETE before import.
    #
    # v4.2 — Each enrollment is emitted using the student's REQUESTED course
    # number, not the section's primary course_id. This is essential for
    # combined multi-level sections (e.g. a Spanish FL section covers G0902 +
    # G1204 + G1205 + G1206; a 9th-grader requesting G0902 must enroll under
    # course G0902, while a 12th-grader requesting G1206 enrolls under G1206
    # — even though both are in the same physical section).
    request_by_student: dict[str, set[str]] = defaultdict(set)
    for st in ds.students:
        for r in st.requested_courses:
            request_by_student[st.student_id].add(r.course_id)
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
                # Determine which course this enrollment fulfills for this student.
                covered = [sect.course_id] + list(sect.linked_course_ids)
                requested = request_by_student.get(sa.student_id, set())
                # Pick the requested course this section covers (first match).
                fulfilled_cid = next((cid for cid in covered if cid in requested), sect.course_id)
                section_term_id = sect.term_id if sect.term_id else term_id
                w.writerow([
                    sa.student_id,
                    fulfilled_cid,
                    sect_num[(sid, fulfilled_cid)],
                    "",                              # Dateenrolled: blank → PS uses term start
                    "",                              # DateLeft: blank → PS uses term end
                    section_term_id,
                    school_id,
                    sid,                             # internal slug (delete before import)
                ])

    # 3. master_schedule.csv (engine-internal flattened view; not a PS import target)
    with (out_dir / "ps_master_schedule.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Day", "Block", "Period", "SectionNumber", "Section_ID_Internal",
                    "CourseID", "LinkedCourseIDs", "TeacherID", "RoomID", "TermID"])
        for s in ds.sections:
            m = master_by_sect.get(s.section_id)
            if m is None:
                continue
            section_term_id = s.term_id if s.term_id else term_id
            for (day, block) in m.slots:
                w.writerow([
                    day, block, _expression(m.slots),
                    sect_num[(s.section_id, s.course_id)], s.section_id,
                    s.course_id, "|".join(s.linked_course_ids),
                    s.teacher_id, m.room_id, section_term_id,
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
