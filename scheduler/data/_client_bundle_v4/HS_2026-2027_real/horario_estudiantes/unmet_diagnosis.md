# Unmet diagnosis

Total unmet (student, course) pairs: **203**.

Each unmet has been classified into one of:

- `no_section` — the course has zero sections in the dataset (data issue).
- `grid_clash` — every section's slots clash with the student's other assignments (the dominant case for Columbus per the lessons doc — **grid-bound, not capacity-bound**).
- `capacity` — every section is at `max_size`. Opening a section would help.
- `restriction` — every section's teacher is on the student's `restricted_teacher_ids` list.
- `separation` — every section is blocked by a separation pair already enrolled.
- `unknown` — solver anomaly: no visible constraint blocks the student. Investigate the data.

## Distribution by reason

| Reason | Count | % |
|---|---|---|
| `grid_clash` | 198 | 97.5% |
| `separation` | 3 | 1.5% |
| `unknown` | 2 | 1.0% |

## Top 20 courses by unmet count

| Course | Total unmet | Dominant reason |
|---|---|---|
| `OC1305` (Painting I) | 18 | `grid_clash` (18) |
| `I1204` (AP Calculus AB) | 12 | `grid_clash` (12) |
| `J0903` (FRC 9) | 11 | `grid_clash` (10) |
| `I0903` (Algebra I 9) | 9 | `grid_clash` (6) |
| `L1302` (Introduction to Law) | 9 | `grid_clash` (8) |
| `OH1305` (Art of Fiction Intermediate Level) | 8 | `grid_clash` (8) |
| `L1303` (Pensar nuestro tiempo) | 7 | `grid_clash` (7) |
| `C0905` (Band Level II) | 7 | `grid_clash` (7) |
| `VHS0052` (Spanish Film, Art, and Literature) | 7 | `grid_clash` (7) |
| `I1211` (AP Precalculus) | 7 | `grid_clash` (7) |
| `L1301` (AP Psychology) | 6 | `grid_clash` (6) |
| `OA1322` (AP Physics 2) | 6 | `grid_clash` (6) |
| `C0904` (Band Level I) | 6 | `grid_clash` (6) |
| `H1201B` (AP English Literature and Composition) | 6 | `grid_clash` (6) |
| `OC1307` (Drawing I) | 5 | `grid_clash` (5) |
| `B1006` (Cultural Studies) | 5 | `grid_clash` (5) |
| `OC1306` (Sculpture I) | 5 | `grid_clash` (5) |
| `H1001` (English 10) | 5 | `grid_clash` (5) |
| `OI1303` (Financial Math) | 5 | `grid_clash` (5) |
| `L1304` (Life Purpose) | 4 | `grid_clash` (4) |

## By grade

| Grade | `no_section` | `grid_clash` | `capacity` | `restriction` | `separation` | `unknown` |
|---|---|---|---|---|---|---|
| 9 | 0 | 36 | 0 | 0 | 3 | 1 |
| 10 | 0 | 37 | 0 | 0 | 0 | 0 |
| 11 | 0 | 73 | 0 | 0 | 0 | 1 |
| 12 | 0 | 52 | 0 | 0 | 0 | 0 |

## How to use this report

1. Filter `unmet_requests.csv` by `reason='grid_clash'` to find students who need a slot swap (most common case at Columbus).
2. `reason='capacity'` rows are candidates for section-expansion discussion with admin (school has frozen sections for 2026-2027).
3. `reason='separation'` rows can be reviewed against the counselor recommendations sheet — soft separations may be relaxed case-by-case.
4. `reason='restriction'` rows reflect explicit teacher-avoid rules; review the source data if the count is unexpectedly high.
5. `reason='no_section'` rows are pure data issues — the course was requested but never sectioned. Fix the input.
6. `reason='unknown'` rows should be empty in a healthy run. If present, investigate the dataset before re-running.

