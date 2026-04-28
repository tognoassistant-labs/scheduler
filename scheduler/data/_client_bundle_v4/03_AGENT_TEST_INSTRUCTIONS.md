# Agent Test Instructions — Columbus Schedule Bundle

**Audience:** the Columbus-side AI agent that will run automated tests on this bundle before any data is imported to PowerSchool.

**Goal:** verify the schedule package is internally consistent, doesn't violate any hard scheduling rule, and matches the input data we received from Columbus, BEFORE any production import happens.

**Time budget:** ~30 seconds for the verifier. Plus optional sandbox import (manual, not scripted).

---

## What you have

This bundle contains:

```
columbus_2026-2027_bundle/
├── 00_LEEME_PRIMERO.md              ← Spanish overview (for humans)
├── 00_README_FIRST_en.md            ← English overview (for humans)
├── 01_PREGUNTAS_PARA_COLUMBUS.md    ← schedule-related questions for IT
├── 01_QUESTIONS_FOR_COLUMBUS_en.md
├── 02_KPI_REPORT.md                 ← KPIs achieved by the solver
├── 03_AGENT_TEST_INSTRUCTIONS.md    ← THIS FILE
├── verify_bundle.py                 ← standalone verifier (Python 3.8+ stdlib only)
│
├── HS_2026-2027_real/
│   ├── input_data/                  ← canonical input dataset (source of truth for cross-checks)
│   │   ├── students.csv
│   │   ├── teachers.csv
│   │   ├── rooms.csv
│   │   ├── courses.csv
│   │   ├── course_requests.csv
│   │   └── behavior.csv
│   ├── horario_estudiantes/
│   │   └── student_schedules_friendly.csv
│   ├── powerschool_upload/          ← solver output, ready to upload to PS
│   │   ├── ps_sections.csv
│   │   ├── ps_enrollments.csv
│   │   ├── ps_master_schedule.csv
│   │   └── ps_field_mapping.md
│   └── lms_upload/                  ← OneRoster v1.1 bundle for LMS
│       └── ... (7 CSVs)
│
└── MS_2026-2027_synthetic_PoC/
    └── ... (same structure, synthetic data)
```

## Step 1 — Run the standalone verifier (REQUIRED)

The verifier is a single Python file with **no external dependencies** (stdlib only). Run it from the bundle root:

```bash
python3 verify_bundle.py
```

Or pass an explicit path:

```bash
python3 verify_bundle.py /path/to/columbus_2026-2027_bundle/
```

**Exit codes:**
- `0` — all invariants passed
- `1` — at least one invariant failed (REPORT THIS UPSTREAM, do not import to PS)
- `2` — bundle structure invalid (missing files, malformed CSVs)

**What the verifier checks per school:**

| # | Invariant | Failure means |
|---|---|---|
| V1 | All expected files present | Bundle is incomplete; refuse to import |
| V2 | Each section has ≥1 master schedule row | Solver output is broken |
| V3 | No student has two sections at the same (day, block) | Hard scheduling rule violated |
| V4 | No teacher in two sections at the same scheme | Hard scheduling rule violated |
| V5 | No room hosting two sections at the same scheme | Hard scheduling rule violated |
| V6 | All sections within MaxEnrollment | Capacity violation |
| V7 | Section balance (max - min enrollment per course) ≤ 5 | KPI miss; v2 §10 target ≤3, accept up to 5 |
| V8 | Every output StudentID exists in input students.csv | Solver invented a student; refuse to import |
| V9 | Every output TeacherID / RoomID exists in input | Solver invented a teacher/room; refuse |
| V10 | Every required rank-1 request is fulfilled in enrollments | Required course missing; refuse to import |
| V11 | No student got a course they did not request | Solver invented an assignment; refuse |

**Expected result:** all checks PASS for `HS_2026-2027_real/`. For `MS_2026-2027_synthetic_PoC/`, V7 may report dev=4 (above target 3 but within accepted ≤5) — **this is documented and expected**, see `02_KPI_REPORT.md`.

## Step 2 — Report results upstream

Report a structured summary in this exact JSON format so a downstream agent can act on it programmatically:

```json
{
  "bundle_version": "v2",
  "verified_at": "2026-04-26T...",
  "verifier_exit_code": 0,
  "schools": [
    {
      "name": "HS_2026-2027_real",
      "all_passed": true,
      "failed_checks": []
    },
    {
      "name": "MS_2026-2027_synthetic_PoC",
      "all_passed": true,
      "failed_checks": []
    }
  ],
  "blocking_questions_unresolved": [
    "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"
  ],
  "recommendation": "Hold production import until questions A1-A9 are answered."
}
```

If any V1-V11 check fails, set `all_passed: false` for that school, populate `failed_checks` with the labels of failed checks, and recommend `"DO NOT IMPORT — verifier failed."` in `recommendation`.

## Step 3 — Sandbox import (manual, RECOMMENDED before production)

This step is **not automated** because it requires PowerSchool credentials. Perform it after V1-V11 pass:

1. Have Columbus IT connect a PowerSchool sandbox or test instance.
2. Import `HS_2026-2027_real/powerschool_upload/ps_sections.csv` into the sandbox's `Sections` module.
3. Import `HS_2026-2027_real/powerschool_upload/ps_enrollments.csv` into the sandbox's `CC` (course-section enrollments) module.
4. Verify in the PS UI:
   - The 234 sections appear linked to existing courses (not as orphans).
   - 3-5 randomly sampled students have the schedule shown in `horario_estudiantes/student_schedules_friendly.csv`.
   - The `Period` / `Expression` field renders correctly in the PS schedule report.
5. If any of these fail, this is likely a question A1-A7 issue (field-format mismatch). Refer to `01_QUESTIONS_FOR_COLUMBUS_en.md` and resolve the specific question before retrying.

## What the agent must NOT do

- **Do NOT import to production** without successfully completing Step 3 against a sandbox.
- **Do NOT modify the CSVs** in `powerschool_upload/` or `lms_upload/`. If a column needs adjustment (e.g., `SchoolID` should be the school number), document the required change in the report and let a human apply it — automated find-and-replace risks data corruption.
- **Do NOT run the solver again.** The bundle ships a finalized schedule. Re-solving would produce a different (multi-worker non-deterministic) schedule and invalidate any human review already done.
- **Do NOT delete or alter the `input_data/` directory.** It is the ground truth for cross-checks; without it, V8-V11 cannot run.

## Reading on errors

Common verifier failures and their causes:

- **V3 (time conflict) FAILS** → solver bug or master-schedule corruption. Stop, do not import, escalate to the schedule-engineering team.
- **V8/V9 (invented student/teacher/room) FAILS** → cross-check against input failed. Most likely the `input_data/` directory is incomplete or the wrong dataset; refuse to import until clarified.
- **V11 (invention) FAILS** → solver produced an assignment outside what was requested. Real bug; do not import.
- **V7 (balance) FAILS at >5** → unusual; expected dev ≤ 5 (hard cap). If observed value is between 4 and 5, is documented; if >5, indicates a solver-config drift.

## Where to find help

- **For schedule-engine questions:** see `02_KPI_REPORT.md` and `01_QUESTIONS_FOR_COLUMBUS_en.md`
- **For PowerSchool field mapping:** see `HS_2026-2027_real/powerschool_upload/ps_field_mapping.md`
- **For the canonical Dataset format spec:** see `input_data/` — every file's schema is in its first row (CSV headers); they map to Pydantic models in the source repo (not shipped in this bundle).
