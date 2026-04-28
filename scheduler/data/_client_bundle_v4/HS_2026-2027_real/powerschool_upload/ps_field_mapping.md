# PowerSchool Field Mapping

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
