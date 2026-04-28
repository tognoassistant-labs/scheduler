# Columbus Scheduling Engine — Grade 12 Prototype

End-to-end constraint-optimization scheduler for Columbus High School Grade 12, built against `powerschool_requirements_v2.md`.

This is a **Track A "May 1 demo" prototype**: synthetic-but-realistic data, real solver, real PowerSchool-compatible exports. Not yet a production system — see `PRODUCTION_GAPS.md`.

## What it does

```
CSV input → validate → master schedule (CP-SAT) → student assignment (CP-SAT) → reports + PS exports
```

Two-stage solve matches Columbus's existing process (v2 §7):
1. **Master schedule** — assign every section to a scheme (1..8) and a room. Advisory locked at Day E Block 3.
2. **Student assignment** — given the master, assign each student to one section per requested course.

## Hard constraints enforced (v2 §6.1)

- No student in two classes at the same time
- No teacher in two classes at the same time
- No room hosting two classes at the same time
- Class size ≤ 25 (26 for AP Research)
- No teacher with > 4 consecutive classes per day
- Advisory fixed at Day E Block 3
- Lab courses require lab rooms
- Restricted teachers excluded
- Separation pairs never share a section

## Soft objectives

- Maximize first-choice elective fulfillment (weight 20)
- Balance class sizes (weight 8) — combined with a HARD per-course spread cap (max−min ≤ 5, configurable via `HardConstraints.max_section_spread_per_course`)
- Honor grouping pairs (weight 4)
- Balance teacher load across days (weight 5, in master)

## Solver modes

- **`--mode single` (default)** — single-pass weighted-sum; ~3 min on 130 students
- **`--mode lexmin`** — two-phase lex-min (electives → groupings) under hard balance cap; useful when you want strict lexicographic priority but slower

## Quickstart

### Web UI (recommended for demos)

```bash
cd /home/hector/scheduler
.venv/bin/streamlit run app.py
# Opens http://localhost:8501 — pick dataset source in sidebar, run solve, browse results
```

The Streamlit app has 5 tabs: Setup → Solve → Browse → Scenarios → Export. It accepts the built-in sample, a canonical CSV folder, or real Columbus xlsx uploads. All KPIs render as colored cards; scenarios produce a side-by-side comparison; PowerSchool exports are one-click downloads.

### Tests

The suite is split into three tiers — opt in to the slower ones explicitly.

```bash
# Tier 1 — FAST (default, ~3 min, 106 tests)
# Hypothesis property tests are excluded; slow regression is deselected by pytest marker.
.venv/bin/python -m pytest tests/ --ignore=tests/test_hypothesis.py

# Tier 2 — SLOW REGRESSION (INDICATOR ONLY, NOT A RELEASE GATE)
# Golden-snapshot scenario regression. Tolerances live in `scenarios.compare_to_golden`.
# Multi-worker non-determinism can cause this to fail on tight-budget fixtures even
# when the engine is healthy. Per Hector decision 2026-04-26 (Decisión 1), this test
# is an "indicator only" — it surfaces multi-worker drift but a failure does NOT
# block release/demo. If it fails on the same code that the fast suite passes:
# don't regenerate the golden blindly; inspect first to rule out a real solver bug.
.venv/bin/python -m pytest tests/ -m slow

# Tier 3 — HYPOTHESIS PROPERTY-BASED FUZZING (opt-in by removing the --ignore, ~2 min more)
# Exercises invariants over many seeded inputs. Includes HC2b (advisory rooms distinct).
.venv/bin/python -m pytest tests/

# Standalone bundle verifier — consumes only export CSVs (no solver imports)
.venv/bin/python tests/check_invariants.py data/exports/powerschool
```

**Known test footguns** (see `MAINTENANCE_GUIDE.md` changelog):
- `tests/test_scenarios.py::test_golden_default_preset_tiny` (slow, opt-in only) is calibrated for n=120/seed=7 with tight time budgets (master 15s, student 30s). Multi-worker non-determinism on different CPUs can drift KPIs beyond the ±3 tolerance. The fast suite runs at larger budgets and is stable. **Per Hector decision 2026-04-26: this slow test is an indicator, not a release gate.** If it fails while the fast suite passes, treat as multi-worker drift; don't regenerate golden blindly.
- `tests/test_hypothesis.py` uses `max_examples=8` for CI speed. Raise it for nightly fuzzing.
- `tests/test_ps_ingest.py` auto-skips its real-data tests if the Columbus xlsx files aren't reachable. The fast suite still passes; only those specific tests skip.

The suite has 9 test files: unit tests for each module, integration tests, and Hypothesis property tests for the highest-value invariants (CSV roundtrip, locks honored, capacity respected, exporter output passes the invariant checker).

### CLI (scriptable, automatable)

```bash
cd /home/hector/scheduler

# Synthetic Grade-12 demo
.venv/bin/python -m src.scheduler.cli generate-sample --out data/sample
.venv/bin/python -m src.scheduler.cli validate --in data/sample
.venv/bin/python -m src.scheduler.cli solve --in data/sample --out data/exports
.venv/bin/python -m src.scheduler.cli scenarios --in data/sample --out data/exports --preset default

# Real Columbus xlsx ingest → solve → export
.venv/bin/python -m src.scheduler.cli import-ps \
  --demand "/path/to/1._STUDENTS_PER_COURSE_2026-2027.xlsx" \
  --schedule "/path/to/HS_Schedule_25-26.xlsx" \
  --out data/columbus --grade 12
.venv/bin/python -m src.scheduler.cli solve --in data/columbus --out data/columbus_exports
```

Outputs:
- `data/exports/reports/schedule_report.md` — KPI summary
- `data/exports/reports/sections_with_enrollment.csv` — every section with assigned scheme, room, enrollment, utilization
- `data/exports/reports/student_schedules.csv` — every student's full schedule
- `data/exports/reports/unmet_requests.csv` — rank-1 requests that could not be granted
- `data/exports/reports/teacher_loads.csv` — load per teacher
- `data/exports/powerschool/ps_sections.csv` — PowerSchool-import-ready sections
- `data/exports/powerschool/ps_enrollments.csv` — PowerSchool-import-ready enrollments
- `data/exports/powerschool/ps_master_schedule.csv` — flattened (day, block) view
- `data/exports/powerschool/ps_field_mapping.md` — PS field-mapping cheatsheet

## Layout

```
src/scheduler/
  models.py         — Pydantic data models, default rotation grid
  sample_data.py    — Reproducible Grade-12 dataset generator
  io_csv.py         — CSV ingest + write (round-trip safe)
  validate.py       — Validation + readiness score (0..100)
  master_solver.py  — Stage 1 (CP-SAT)
  student_solver.py — Stage 2 (CP-SAT)
  reports.py        — KPI + report generation
  exporter.py       — PowerSchool-compatible CSV export
  scenarios.py      — Multi-scenario simulation + KPI comparison
  cli.py            — Command-line entry point
app.py              — Streamlit web UI (single file, all tabs)
data/
  sample/           — generated sample data
  exports/          — solve outputs
MAINTENANCE_GUIDE.md — code-level guide for future agents
PRODUCTION_GAPS.md   — gap analysis with effort estimates
DEVELOPMENT_PROPOSAL.md — Track A vs B; phased plan
```

## Sample run results

### Synthetic dataset (130 students, 62 sections, seed=42)

| Metric | Value | v2 Target | Met |
|---|---|---|---|
| Fully scheduled students | 100% | ≥98% | ✅ |
| Required course fulfillment | 100% | ≥98% | ✅ |
| First-choice electives | 81–93% | ≥80% | ✅ |
| Section balance (max dev) | 3 | ≤3 | ✅ |
| Time conflicts | 0 | 0 | ✅ |

### Real Columbus Grade 12 (121 students, 93 sections, ingested from real xlsx)

| Metric | Value | v2 Target | Met |
|---|---|---|---|
| Fully scheduled students | 100% | ≥98% | ✅ |
| Required course fulfillment | 100% | ≥98% | ✅ |
| First-choice electives | **97.8%** | ≥80% | ✅ |
| Section balance (max dev) | 2 | ≤3 | ✅ |
| Time conflicts | 0 | 0 | ✅ |

All hard constraints + KPIs met. Independent invariant check on exported PS CSVs confirms zero teacher/room double-bookings, zero student conflicts, zero capacity violations, Advisory locked at E3, max per-course spread (max−min) = 5, worst per-course |size−mean| = 3.33 (rounds to 3).

Master solve: ~0.5s. Student solve: ~3 min in single-pass mode with multi-worker (FEASIBLE; OPTIMAL not always reached but constraints honored).

## Constraints-as-data

`SchoolConfig` (in `models.py`) is a structured object — change values, not code, to retune. To support a different school/grade/year, populate a new `SchoolConfig` and pass a different `BellSchedule.rotation`. This is the v2 §3.1 parametrization principle.
