# Unmet diagnosis

Total unmet (student, course) pairs: **116**.

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
| `grid_clash` | 114 | 98.3% |
| `separation` | 2 | 1.7% |

## Top 20 courses by unmet count

| Course | Total unmet | Dominant reason |
|---|---|---|
| `OC1305` (Painting I) | 16 | `grid_clash` (16) |
| `J0903` (FRC 9) | 8 | `grid_clash` (8) |
| `OH1501` (Journalism Higher Level) | 7 | `grid_clash` (7) |
| `OB1532` (AP Research) | 6 | `grid_clash` (6) |
| `C0904` (Band Level I) | 6 | `grid_clash` (4) |
| `G0901` (Español & Literatura 9) | 5 | `grid_clash` (5) |
| `I1204` (AP Calculus AB) | 4 | `grid_clash` (4) |
| `J1203` (Tech. and Innovation for Social Change) | 4 | `grid_clash` (4) |
| `OH1305` (Art of Fiction Intermediate Level) | 3 | `grid_clash` (3) |
| `H1001` (English 10) | 3 | `grid_clash` (3) |
| `I1214` (AP Seminar) | 3 | `grid_clash` (3) |
| `E1101` (Physical Education and Health 11) | 3 | `grid_clash` (3) |
| `OZ1313` (AP Computer Science A) | 3 | `grid_clash` (3) |
| `OC1306` (Sculpture I) | 2 | `grid_clash` (2) |
| `C0905` (Band Level II) | 2 | `grid_clash` (2) |
| `OC1314` (AP Drawing) | 2 | `grid_clash` (2) |
| `L1301` (AP Psychology) | 2 | `grid_clash` (2) |
| `L1303` (Pensar nuestro tiempo) | 2 | `grid_clash` (2) |
| `OZ1323` (AP Human Geography) | 2 | `grid_clash` (2) |
| `OI1303` (Financial Math) | 2 | `grid_clash` (2) |

## By grade

| Grade | `no_section` | `grid_clash` | `capacity` | `restriction` | `separation` | `unknown` |
|---|---|---|---|---|---|---|
| 9 | 0 | 34 | 0 | 0 | 2 | 0 |
| 10 | 0 | 18 | 0 | 0 | 0 | 0 |
| 11 | 0 | 29 | 0 | 0 | 0 | 0 |
| 12 | 0 | 33 | 0 | 0 | 0 | 0 |

## How to use this report

1. Filter `unmet_requests.csv` by `reason='grid_clash'` to find students who need a slot swap (most common case at Columbus).
2. `reason='capacity'` rows are candidates for section-expansion discussion with admin (school has frozen sections for 2026-2027).
3. `reason='separation'` rows can be reviewed against the counselor recommendations sheet — soft separations may be relaxed case-by-case.
4. `reason='restriction'` rows reflect explicit teacher-avoid rules; review the source data if the count is unexpectedly high.
5. `reason='no_section'` rows are pure data issues — the course was requested but never sectioned. Fix the input.
6. `reason='unknown'` rows should be empty in a healthy run. If present, investigate the dataset before re-running.

