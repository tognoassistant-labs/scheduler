# PowerSchool Field Mapping

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
