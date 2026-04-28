# PowerSchool Field Mapping

Generated CSVs are baseline templates. Adjust column names per the
school's PS instance using PS Data Dictionary if needed.

## ps_sections.csv → PS `Sections` import
| Engine column | PS field | Notes |
|---|---|---|
| SchoolID | School_Number | Hard-coded to school name; replace with school number |
| CourseID | Course_Number | Direct |
| SectionID | Section_Number | Engine uses dotted form (e.g. ENG12.1) |
| TeacherID | Teacher_Number | Direct |
| RoomID | Room | Direct |
| Period | Expression | Engine produces P01..P08 + ADV |
| Slots | (split into M/T/W/Th/F flags) | Engine produces e.g. "A1;D2;B4" |
| TermID | TermID | School year as a string here |
| MaxEnrollment | Max_Enrollment | Direct |

## ps_enrollments.csv → PS `CC` (course-section enrollments)
| Engine column | PS field |
|---|---|
| SchoolID | SchoolID |
| StudentID | StudentID |
| SectionID | SectionID |
| CourseID | Course_Number |
| TermID | TermID |

## ps_master_schedule.csv
A flattened view for quick visual inspection or for SIS systems that
prefer day-block × section rows. Not directly imported by PS but useful
for leadership review and downstream reporting.

## Open items for sandbox testing
- Confirm Period code format expected by Columbus PS instance
- Confirm whether `Expression` should be the period code or a
  comma-separated list of (day, block) tokens
- Map TermID to actual PS term IDs (year ≠ term)
