# Questions for Columbus — required to upload this schedule

This document collects the questions that **directly block importing the attached schedule** into your PowerSchool instance and the LMS. All are about the format of the schedule data or the scheduling rules we applied. Out-of-scope future deliverables, governance and strategic decisions are handled separately.

> _Versión en español: ver `01_PREGUNTAS_PARA_COLUMBUS.md` (same numbering)._

---

## A. Data format in the bundle (affects PowerSchool import)

Without these answers, the CSVs in `HS_2026-2027_real/powerschool_upload/` can be uploaded but may fail the import or create badly-linked sections in your PowerSchool instance.

| # | Question | Why it matters | Where it shows up in the bundle |
|---|---|---|---|
| A1 | Should the `SchoolID` column contain Columbus's PowerSchool **school number**, or the school name? Today the bundle ships with `"Columbus High School"`. | PS typically expects an integer (e.g. `1234`). The name may cause import failure. | `ps_sections.csv` column `SchoolID` |
| A2 | Should the `Period` column be formatted as `P01..P08` + `ADV` (what we generate), or day-block tokens like `A1,D2,B4` (what we have in `Slots`)? | PS instances vary in how they represent the `Expression`. | `ps_sections.csv` columns `Period` and `Slots` |
| A3 | What real `TermID` does PS expect for the 2026-2027 year in your instance? Today we ship the string `"2026-2027"`. | PS usually links sections to a Term object with a specific ID (e.g., `2700`). | `ps_sections.csv` and `ps_enrollments.csv`, column `TermID` |
| A4 | Do the `CourseID`s we generate (`ALGEBRA_I_9`, `AP_CALCULUS_`, `ESPAÑOL_LITE`, etc.) **match** Columbus's existing PS `Course_Number` values, or do they need mapping? | If they don't match, sections won't link to existing courses and will appear as orphans. | `ps_sections.csv` and `courses.csv` column `CourseID` |
| A5 | Do the `TeacherID`s (`T_RODRIGUEZ_`, `T_ARCILA_FER`, etc.) match `Teacher_Number` in PS, or do they need mapping to real IDs? | Same problem: if not matched, teachers will appear as new instead of existing. | `ps_sections.csv` column `TeacherID` |
| A6 | Are the `StudentID`s we use (`28026`, `100052`, etc., taken from the `ID` column in the xlsx) the real `Student_Number` in PS, or do they need mapping? | Without a match, enrollments don't link to existing student records. | `ps_enrollments.csv` column `StudentID` |
| A7 | Do the `RoomID`s (`R901_0`, `R922_0`, etc.) match the room IDs in PS, or are they internal labels only? | If they don't match, rooms appear as new. | `ps_sections.csv` column `RoomID` |
| A8 | Is there a **PowerSchool sandbox / test instance** we can dry-run against before importing to production? | Sandbox-first is the standard practice and avoids breaking real data. | — (external decision) |
| A9 | Who is the contact at Columbus IT who can provide sandbox credentials/URL? | Without this contact, A8 doesn't move. | — (external decision) |

## B. Columbus's actual rules that we applied to the solver

These are the rules the engine used to produce the attached schedule. If any doesn't match Columbus's reality, we need to re-run the solver with the corrected rule.

| # | Question | How it was handled in this schedule |
|---|---|---|
| B1 | What is the **authoritative list of required courses per grade**? Today we use a heuristic: course name contains "Required" or ends in the grade number. | `Course.is_required` in the model. |
| B2 | Is the **behavioral matrix** (separations / groupings) we read from the `Student Groupings` tab complete, or are there rules documented elsewhere? | 51 separations + 42 groupings read from xlsx, all respected in the schedule. |
| B3 | Should the **consecutive-class cap for teachers** be 4 or 5? We auto-relax to 5 when any teacher has ≥7 sections (real Columbus case). | At 4, the schedule was infeasible: 3 teachers with 7 sections + 5 blocks/day = one day always full. 5 makes it feasible. |
| B4 | Is Advisory **always** locked at E3, for all grades? | Yes, assumed in this schedule (matches Columbus's current 2025-26 schedule). |
| B5 | Is the section-balance target **≤3 students** absolute or aspirational? If aspirational, which KPI is OK to sacrifice to reach 3? | Today we land at balance=4 with 97.5% first-choice electives. To reach 3 there is a documented trade-off in `02_KPI_REPORT.md`. |
| B6 | Are the `CourseRequest` ranks correct (rank 1 = first choice, rank 2 = alternate)? We detected that "Optatives" were misinterpreted earlier — confirm final xlsx reading. | xlsx read with the convention: rank=1 unless marked as "Electives Alternative N", rank=2 if so. |

## C. Verifications we recommend BEFORE importing to production

These are concrete tasks the Columbus team should do in sandbox before touching production:

1. **Import `ps_sections.csv` to sandbox** and confirm the 234 sections appear linked to the correct courses.
2. **Import `ps_enrollments.csv` to sandbox** and verify ~3-5 randomly sampled students have the correct schedule.
3. **Validate the `Period`/`Expression` format** by generating a schedule report in sandbox and comparing with the format expected by the instance.
4. **Verify room codes exist** in sandbox before importing.
5. **Run a demo with 1-2 coordinators** reviewing `HS_2026-2027_real/horario_estudiantes/student_schedules_friendly.csv` to catch discrepancies before a parent/student does.

---

**Convention:** when a question is answered, mark `✅` in the table with the date. Unmarked questions remain blockers for the import.
