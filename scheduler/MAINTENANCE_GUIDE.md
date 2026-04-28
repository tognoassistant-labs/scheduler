# Maintenance Guide — Columbus Scheduling Engine

**Audience:** Future agents (human or AI) modifying, extending, or debugging this codebase.
**Last updated:** 2026-04-25
**Authoritative spec:** `/home/hector/Documents/powerschool_requirements_v2.md`

This is a living document. Update it whenever you change the architecture, add a new module, or learn a new failure mode. Skills/role inventory lives in `/home/hector/Documents/scheduler_skills_log.md`; this guide is code-level.

---

## 1. Architecture in 30 seconds

```
CSV in → ingest → validate → master_solver → student_solver → reports + exporter → CSV out
                                ↑                  ↑
                           SchoolConfig       MasterAssignment[]
                          (from models)
```

Two-stage CP-SAT solve. **Never merge them** — staging is what makes the problem tractable and matches Columbus's existing operational process.

## 2. Module dependency graph

```
models.py         ← no deps (pure Pydantic)
sample_data.py    ← models
io_csv.py         ← models
validate.py       ← models
ps_ingest.py      ← models + openpyxl   (real Columbus xlsx → Dataset)
master_solver.py  ← models + ortools
student_solver.py ← models + ortools  (consumes MasterAssignment[] from master_solver)
reports.py        ← models
exporter.py       ← models
scenarios.py      ← models + master_solver + student_solver + reports
cli.py            ← all of the above (orchestrator, scriptable)
app.py            ← all of the above (Streamlit UI, interactive)
```

Rule: **never have a model file import a solver or IO file**. Models are the contract; everything else depends on them.

`scenarios.py` is the only module that re-uses both solvers; it deep-copies the dataset before applying overrides so each scenario is isolated.

## 3. Where to make common changes

### "Add a new hard constraint"

1. Add the parameter (if any) to `models.py:HardConstraints` or `SoftConstraintWeights`.
2. Implement the constraint in `master_solver.py` (if it's about scheduling) or `student_solver.py` (if it's about student assignments).
3. Add a check for it in `validate.py` so dirty data doesn't reach the solver.
4. Add an independent verification check in the manual invariant script (template at end of this doc).
5. Update the relevant section in `models.py:HardConstraints` docstring.

### "Add a new soft objective"

1. Add a weight to `models.py:SoftConstraintWeights`.
2. Build the objective expression in `student_solver.py` (or `master_solver.py`).
3. **Integrate carefully.** In `single` mode, add as `+ weight * obj_term` to the weighted sum. In `lexmin` mode, decide where it sits in the priority order and update the phase chain.
4. Test trade-offs: if the new term sucks budget from electives, you've over-weighted it.

### "Change the rotation grid"

`models.py:default_rotation()` defines the v2 §4.1 example grid. To use a different rotation, build a `BellSchedule(rotation=[RotationCell(...)...])` and pass it via `SchoolConfig.bell`. Validation in `master_solver` assumes 8 schemes + Advisory; if you change scheme count, also adjust the `SCHEMES = list(range(1, 9))` list in `master_solver.py`.

### "Add a new course/teacher/room field"

1. Add the field to the relevant Pydantic model in `models.py`.
2. Update `io_csv.py:write_dataset` (writer) and `read_dataset` (reader) to round-trip the field.
3. If the field affects solving, add a constraint or objective term.
4. Update the sample generator in `sample_data.py` to populate it.
5. Re-run the round-trip test (`generate-sample`, then `validate`).

### "Add a new KPI to reports"

1. Add the field to `reports.py:KPIReport` dataclass.
2. Compute it in `compute_kpis()`.
3. Render it in `KPIReport.summary()`.
4. Add a target check (target → bool) in `compute_kpis` and update `targets_met` dict.
5. If the KPI maps to a v2 §10 numbered target, cite the source in the docstring.

### "Add a new PowerSchool export field"

`exporter.py` writes three files. Map the new field to the appropriate one and update `ps_field_mapping.md`. Get sandbox confirmation before relying on field semantics.

### "Add a new scenario type"

1. Add a key handler in `scenarios.py:_apply_overrides` for the override.
2. Optionally add a `ScenarioSpec` instance to `PRESETS["default"]` if it's broadly useful.
3. Test by running `cli.py scenarios --preset default` and inspecting the comparison table.

The scenario engine deep-copies the base dataset before applying overrides, so each scenario is isolated. Don't mutate the base dataset directly.

### "Add a new tab to the Streamlit UI"

1. `app.py` is a single file — open it.
2. Add the tab to the `st.tabs([...])` list near the top of the main section.
3. Add a `with tab_<name>:` block at the end with your content. Gate it on `_has_dataset()` or `_has_solution()` if it depends on those.
4. Use `st.session_state` for any data that must survive reruns (Streamlit re-executes the whole script on every interaction). Don't call solvers without first checking the cache.
5. Run `.venv/bin/streamlit run app.py` to test. For automated checks: `from streamlit.testing.v1 import AppTest`.

### "Lock a section to a specific scheme/room"

Two ways:

1. **Per-section in the Dataset** — set `section.locked_scheme = 5` or `section.locked_room_id = "R001"` before calling `solve_master`. The locks are equality constraints — if conflicting (e.g. two sections locked to the same scheme + same teacher), the solver returns INFEASIBLE.

2. **Via the Streamlit UI** — open the "🔒 Locks & Prefs" tab → "Section locks" sub-tab → edit the table → click "Apply locks to dataset". Re-run Solve in tab 2.

Locks override room-type compatibility checks (you can lock a non-lab section to a lab room if you really want). Capacity is still enforced.

### "Set a teacher's preferences"

`Teacher.preferred_course_ids`, `avoid_course_ids`, `preferred_blocks` (1..5), `avoid_blocks`. Soft objectives in master_solver weighted by the corresponding `SoftConstraintWeights.teacher_*` fields. Defaults are 3, 5, 2, 3 — strong enough to honor preferences without dominating other objectives.

### "Add a new constraint slider to the Solve tab"

1. Add the field to `models.py:HardConstraints` or `SoftConstraintWeights`.
2. Wire the slider in `app.py` inside the `st.button("▶️ Solve")` block: `value = st.slider(...)`.
3. Apply to the dataset copy: `ds_run.config.hard.<field> = value` (the app already deep-copies `ds` before solving so the user can re-tune without re-loading).
4. Update the corresponding solver code in `master_solver.py` or `student_solver.py` to read the field.
5. Smoke-test with `.venv/bin/python -c "from streamlit.testing.v1 import AppTest; AppTest.from_file('app.py').run(timeout=60)"`.

### "Adapt the ingester to a different school's PS export"

The Columbus-specific ingester logic in `ps_ingest.py` makes a few assumptions:

- **Header map** (`PS_CSV_HEADER_MAP`) maps Spanish/Colombian column names → canonical fields. To handle a different school's PS, add their headers to the same map (or build a parallel map and pass it to `_build_header_index`).
- **xlsx sheet names** (`UPDATED MARCH 20 - COURSE_GRADE`, `LISTADO MAESTRO CURSOS Y SECCIO`, `Student Groupings`) are tolerantly matched (case-insensitive substring fallback). For another school, these likely need explicit overrides — refactor the readers to accept sheet-name params.
- **ID column** in the conditional sheets is `raw[2]` (the "ID" column), NOT `raw[1]` ("STUDENT_ID"). This matters for matching with the Groupings sheet.
- **"Optative" vs "Alternative"** semantics: Columbus marks "Electives Alternative N" as backup choices. Optatives are primary picks across departments (each is a rank-1 want, not an alternate of others). Don't reintroduce the "at most 1 elective total" constraint that was removed.
- **Course/teacher/room IDs** are slugged from names (`_slugify`). If a school uses real codes (e.g. PS Course Numbers), prefer those over slugs to keep IDs stable across years.

## 4. Solver tuning playbook

These are the levers in order of impact. **Always re-run the smoke test after tuning.**

| Lever | Where | When to touch |
|---|---|---|
| `HardConstraints.max_section_spread_per_course` | `models.py` | KPI says balance is too loose or solver is infeasible. K=4 is tight; K=6 is loose. K=5 is the current sweet spot for the v2 §10 ≤3 max-dev target. |
| `SoftConstraintWeights.first_choice_electives` | `models.py` | Elective rate too low. Bump from 20 → 30 if balance still OK. |
| `SoftConstraintWeights.balance_class_sizes` | `models.py` | Balance is right at the K cap (every course at max-min=K). Bump weight to 12-15 to push under the cap. |
| `--mode` flag (`single` vs `lexmin`) | CLI | `single` is default and faster. `lexmin` only if user demands strict lex-priority. |
| `--master-time` / `--student-time` | CLI | Solver hits FEASIBLE not OPTIMAL → bump time. Single rarely benefits past 240s; lexmin can use 360s+. |
| `solver.parameters.num_search_workers` | `master_solver.py`, `student_solver.py` | Always 4 unless the host has fewer cores. |
| `solver.parameters.random_seed` | `master_solver.py` | Set for reproducibility. CP-SAT multi-worker is not strictly deterministic, but seed reduces variance. |

## 5. Common failure modes

### "Solver returns INFEASIBLE"

1. First, confirm the data validates: `python cli.py validate --in <dir>`. If readiness < 100, fix that first.
2. Run with `--verbose` and inspect the solver log.
3. Bisect constraints: temporarily relax the most-recently-added hard constraint and retry. If feasible, the new constraint is the cause.
4. Common offenders: tight balance K, separation pairs that can't fit, capacity shortfalls hidden by elective alternates.

### "Solver returns UNKNOWN"

1. Time limit hit before any feasible solution found.
2. Bump `--student-time` to 300s+ as a first try.
3. If still UNKNOWN, the model is over-constrained. Same bisection as INFEASIBLE.
4. If only phase 2 of lex-min returns UNKNOWN, the snapshot fallback in `student_solver.py` keeps phase-1 values — verify by inspecting the output assignment count.

### "KPI says balance ≤3 but invariant check disagrees"

This was a real bug. The reports.py metric counted courses with ≥2 sections; the solver constraint applied only when `min_sections_for_balance ≥ 3`. **Always align the constraint set and the KPI set.** Both now use ≥2 (`min_sections_for_balance = 2`).

### "ImportError: attempted relative import"

You're running the flat handoff layout but hit a package-style import. Imports in the flat layout must be absolute (`from models import ...`). The packaged layout under `src/scheduler/` uses relative (`from .models import ...`). Don't mix.

### "After changing models.py, validate fails"

Pydantic v2 is strict. New required fields without defaults break loading old CSVs. Either: (a) add a default value, (b) update `io_csv.py` to default-fill the field on read, (c) re-generate sample data.

### "Lex-min phase 3 returns MODEL_INVALID"

You forgot to call `model.ClearHints()` between phases. The `_clear_objective` helper in `student_solver.py` already does both `ClearObjective` and `ClearHints` — use that helper, not the proto manipulation pattern.

## 6. Verification recipes

### pytest suite (every change)

```bash
.venv/bin/python -m pytest tests/                    # full suite, ~4 min
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_hypothesis.py  # fast subset, ~1 min
.venv/bin/python -m pytest tests/test_models.py -v   # unit tests for one module
```

84 tests across 9 files. The slow ones are the solver-driven tests in `test_master_solver.py`, `test_student_solver.py`, `test_reports_exporter.py`, `test_scenarios.py`, `test_hypothesis.py`. Skip Hypothesis tests with `--ignore=tests/test_hypothesis.py` for the fastest signal.

### Standalone invariant checker (post-solve)

```bash
.venv/bin/python tests/check_invariants.py data/exports/powerschool
```

Reads the exported PS CSVs and verifies the hard constraints + balance KPI independently of the solver. Use as the "did the solver actually do what it said it did" check.

### Quick smoke test (every change)

```bash
.venv/bin/python -m src.scheduler.cli generate-sample --out data/sample
.venv/bin/python -m src.scheduler.cli solve --in data/sample --out data/exports --master-time 30 --student-time 180
```

Expected: all KPI rows green, master OPTIMAL, student FEASIBLE/OPTIMAL, 130 students placed.

### Independent invariant check (every solver change)

```python
import csv
from collections import defaultdict
sections = list(csv.DictReader(open('data/exports/powerschool/ps_sections.csv')))
enrollments = list(csv.DictReader(open('data/exports/powerschool/ps_enrollments.csv')))

# Teacher double-bookings
ts_per_period = defaultdict(int)
for s in sections:
    if s['Period'] == 'ADV': continue
    ts_per_period[(s['TeacherID'], s['Period'])] += 1
assert all(c <= 1 for c in ts_per_period.values()), "teacher conflict"

# Room double-bookings
rs_per_period = defaultdict(int)
for s in sections:
    if s['Period'] == 'ADV': continue
    rs_per_period[(s['RoomID'], s['Period'])] += 1
assert all(c <= 1 for c in rs_per_period.values()), "room conflict"

# Student time conflicts
sect_to_slots = {s['SectionID']: s['Slots'].split(';') for s in sections}
stu_slot_count = defaultdict(lambda: defaultdict(int))
for e in enrollments:
    for slot in sect_to_slots.get(e['SectionID'], []):
        stu_slot_count[e['StudentID']][slot] += 1
assert all(c <= 1 for stu in stu_slot_count.values() for c in stu.values()), "student conflict"

# Per-course max-dev (v2 §10 ≤3)
sec_to_course = {s['SectionID']: s['CourseID'] for s in sections}
sec_enrollment = defaultdict(int)
for e in enrollments: sec_enrollment[e['SectionID']] += 1
by_course = defaultdict(list)
for sid, n in sec_enrollment.items():
    by_course[sec_to_course[sid]].append(n)
worst_dev = max(
    (max(abs(s - sum(sizes)/len(sizes)) for s in sizes)
     for sizes in by_course.values() if len(sizes) >= 2),
    default=0,
)
assert round(worst_dev) <= 3, f"balance violation: max-dev = {worst_dev}"
print("All invariants pass.")
```

Save as `tests/check_invariants.py` and run after any solver change.

### CSV round-trip test (every io_csv change)

```python
from src.scheduler.sample_data import make_grade_12_dataset
from src.scheduler.io_csv import write_dataset, read_dataset
from src.scheduler.validate import validate_dataset
from pathlib import Path
ds = make_grade_12_dataset()
write_dataset(ds, Path('/tmp/rt'))
ds2 = read_dataset(Path('/tmp/rt'))
assert len(ds.students) == len(ds2.students)
assert len(ds.sections) == len(ds2.sections)
assert validate_dataset(ds2).score == 100
```

## 7. Code conventions

- **Pydantic v2 models with explicit field types.** No Python dicts as data structures across module boundaries.
- **Constraint expressions read top-down in solver code.** Hard constraints first (commented `# HC: <name>`), soft objectives last (commented `# SOFT: <name>`).
- **One file per concern.** No mega-files. The largest module right now is `student_solver.py` at ~280 lines; if you're approaching 400, refactor.
- **Defaults belong in models.py.** Never hard-code constraint values inside solver functions. If you find yourself writing `25` in `student_solver.py`, that's a bug.
- **No emojis in code.** Markdown reports use ✅/❌; that's the only place.
- **Comments explain WHY, not WHAT.** The variable name `electives_obj` makes its purpose obvious; a comment "this is the electives objective" is noise.

## 8. Testing footguns specific to this codebase

- **Sample data uses random seed 42**. Don't rely on absolute KPI values being identical across versions of the sample generator — they shift when the generator logic changes (e.g., size sections from actual demand).
- **Solver multi-worker is non-strictly-deterministic** even with `random_seed=42`. KPI values can fluctuate by 1-2% between runs. Build assertions with tolerance (`elective_pct >= 80` not `== 81.5`).
- **Time limits are budgets, not guarantees.** A 60s budget might converge to OPTIMAL in 0.5s OR hit FEASIBLE at 60s. Don't assume convergence time.
- **`PYTHONDONTWRITEBYTECODE=1`** if you need a clean working tree for git diffs. The project doesn't ship pyc files.

## 9. Things that look like bugs but aren't

- **`ADV` (Advisory) sections all live in one room (R001)**. Not a bug — Advisory is fixed at one slot (Day E Block 3) but each section has its own teacher; rooms cycle (the solver picks one room and reuses it because no other Advisory section conflicts with it on the same teacher). If multiple Advisory sections need different rooms, add a constraint: `model.AddAllDifferent([advisory_room[s.section_id] for s in advisory_sections])`.
- **Student solve returns FEASIBLE not OPTIMAL** even with passing KPIs. The objective hasn't converged, but constraints hold. This is fine. Don't bump time budgets reflexively.
- **Sample dataset has 0 separation/grouping pairs satisfied** in some runs. The behavior matrix is randomly generated; some pairs may be unfittable given the schedule. This is expected.

## 10. Open invariants the codebase relies on

These are NOT enforced by Pydantic but ARE assumed by the solvers. If you violate them, you'll get cryptic infeasibility:

- Every course has at least one qualified teacher (or `is_advisory=True`).
- Every section's teacher is in `course.qualified_teacher_ids`.
- Every section's `max_size` is ≤ the smallest compatible room's capacity.
- Every requested course has at least one section.
- Behavior matrix references existing student IDs.
- `BellSchedule.rotation` covers all 25 (day × block) cells, with exactly one `ADVISORY` cell at `(advisory_day, advisory_block)`.

`validate.py` catches most of these but not all. If you add a new invariant, mirror it in `validate.py`.

## 11. What changed in each milestone (changelog)

| Date | Change | Files touched |
|---|---|---|
| 2026-04-25 | Initial Track A prototype: master + student solvers, sample data, CSV IO, validation, reports, PS exporter, CLI | All |
| 2026-04-25 (later) | Closed section-balance gap. Added hard `max_section_spread_per_course` cap (K=5) + soft balance term + `--mode lexmin` option. Default mode `single`. | `models.py`, `student_solver.py`, `master_solver.py`, `cli.py`, `README.md`, `PRODUCTION_GAPS.md` |
| 2026-04-25 (later) | Added co-planning windows (v2 §6.2) in master solver. Disabled by default (weight=0) because enabling it concentrates same-dept sections into fewer schemes, hurting electives by 10–15pts. Added hard min-schemes-per-course constraint (`ceil(n_sections/2)`) which actually IMPROVED elective rate even with co-planning at zero. | `master_solver.py`, `models.py` |
| 2026-04-25 (later) | Added scenario simulation (v2 §10): `scenarios.py` module with `ScenarioSpec` / `run_scenarios` / `format_comparison`. CLI subcommand `scenarios --preset default` runs 6 built-in scenarios and produces a markdown comparison table. | `scenarios.py` (new), `cli.py`, `MAINTENANCE_GUIDE.md`, `README.md`, `PRODUCTION_GAPS.md` |
| 2026-04-25 (later) | Real PowerSchool / Columbus xlsx ingester: `ps_ingest.py` reads `1._STUDENTS_PER_COURSE_*.xlsx` (course demand, LISTADO MAESTRO, per-student requests across departments) and optionally `HS_Schedule_*.xlsx` (Student Groupings). Handles UTF-8 BOM, Spanish headers, and ID-column mismatch between sheets (sheets use both `STUDENT_ID` (account ID) and `ID` (PS ID) — only `ID` matches groupings). CLI: `import-ps --demand <demand.xlsx> --schedule <schedule.xlsx> --grade 12`. Real Grade-12 cohort: 121 students, 93 sections, 100/100 readiness, 97.8% first-choice electives after solve. **Also fixed**: removed the spurious "at most 1 elective total" constraint in student_solver — students request multiple optatives across departments, not alternates of each other. | `ps_ingest.py` (new), `cli.py`, `student_solver.py`, `validate.py`, `models.py` |
| 2026-04-25 (later) | Streamlit web UI: `app.py` (single file, ~430 lines). 5 tabs (Setup → Solve → Browse → Scenarios → Export). Sidebar dataset picker (sample / canonical CSV / Columbus xlsx upload), interactive sliders for all soft+hard knobs, KPI cards with green/red indicators, schedule grid with enrollments, scenario comparison, one-click PS export downloads + zip bundle. Run with `.venv/bin/streamlit run app.py`. | `app.py` (new), `requirements.txt`, `README.md`, `MAINTENANCE_GUIDE.md` |
| 2026-04-25 (later) | Solver-quality pass: locked sections (Section.locked_scheme/locked_room_id, master_solver enforces, streamlit editable table), teacher preferences (preferred/avoid courses, preferred/avoid blocks, soft objectives, streamlit table), course prerequisites (Course.prerequisite_course_ids, validate.py with cycle detection + per-student warnings), singleton-conflict avoidance soft term (off by default to avoid competing with electives). Streamlit gets a new "🔒 Locks & Prefs" tab with two sub-tabs and `st.data_editor` editable tables. Synthetic and Columbus regression KPIs unchanged: 84.6% / 97.6% first-choice electives respectively. | `models.py`, `master_solver.py`, `validate.py`, `io_csv.py`, `app.py`, `PRODUCTION_GAPS.md`, `MAINTENANCE_GUIDE.md` |
| 2026-04-25 (later) | Test suite: 84 pytest tests across 9 files (`tests/`), plus 5 Hypothesis property tests, plus standalone `tests/check_invariants.py` script. **Bug found and fixed by Hypothesis**: `sample_data.py` was skipping section-creation for courses requested only at rank-2 (alternate); a student with PSYCH only as alt would trigger COURSE_NO_SECTION at validation. Fixed by ensuring every requested course gets ≥1 section. **Discovery**: synthetic generator at small N produces seed-sensitive solver feasibility — singleton courses can cluster into the same scheme. `tiny_dataset` fixture uses n=100, seed=7 for reliable feasibility. Test suite ~4 min full, ~1 min without Hypothesis. | `tests/*` (new), `pyproject.toml`, `requirements.txt` (pytest, hypothesis), `sample_data.py` (rank-2 fix), `README.md`, `MAINTENANCE_GUIDE.md`, `PRODUCTION_GAPS.md` |
| 2026-04-25 (later) | Full-HS load test (n=520) + two production bugs fixed. **(1) ortools 9.15.x is broken on Apple Silicon**: the wheel returns `MODEL_INVALID` on a trivial 2-variable model in single-worker mode and hangs the process indefinitely in the default multi-worker mode. Pinned `ortools>=9.10,<9.13` in `requirements.txt` (9.11.4210 confirmed working). **(2) Master `min_distinct_schemes` constraint was structurally infeasible at scale**: `ceil(n_sections/2)` demanded more than 8 distinct schemes for any course with >14 sections (ENG12, GOV at full HS). Capped at `len(SCHEMES)` in `master_solver.py:198`. After both fixes, n=520 synthetic load test: master OPTIMAL in 5.9s, students FEASIBLE in 1800s (hit time limit, but already at 100% on every KPI: scheduled, required, first-choice electives, 0 conflicts, max-dev=3). **(3)** Added `make_full_hs_dataset(n)` and `scale=` parameter to `make_grade_12_dataset` / `_make_teachers` / `_make_rooms` / `_assign_qualifications` so synthetic generator produces feasible large cohorts. Default scale=1 preserves all existing test fixtures and the 130-student demo. | `master_solver.py`, `sample_data.py`, `requirements.txt`, `MAINTENANCE_GUIDE.md`, `PRODUCTION_GAPS.md` |
| 2026-04-25 (later) | Golden-snapshot scenario regression. Added `to_snapshot_dict`, `compare_to_golden`, and tolerances (`_ELECTIVE_PCT_TOL=3.0`, `_PCT_DRIFT_TOL=0.5`, `_UNMET_TOL=3`, `OK_STATUSES=(OPTIMAL, FEASIBLE)`) to `scenarios.py`. Golden file lives at `tests/golden/scenarios_default_tiny.json` (n=100 seed=7, default preset, 6 scenarios). Test `test_golden_default_preset_tiny` is marked `slow` and deselected by default in `pyproject.toml` (`addopts: -m "not slow"`); opt in with `pytest -m slow`. Inline regenerate command in `REGENERATE_HINT` in `tests/test_scenarios.py`. **Why tolerances:** student solver uses `num_search_workers=4` and no `random_seed`, so multi-worker non-determinism produces ±1-2pt drift in elective rate and ±1 in balance dev between identical runs. | `scenarios.py`, `tests/test_scenarios.py`, `tests/golden/scenarios_default_tiny.json` (new), `pyproject.toml`, `PRODUCTION_GAPS.md` |
| 2026-04-25 (later) | OneRoster v1.1 compatibility (gap doc §7.2). New `io_oneroster.py` writes a 7-file CSV bundle (`manifest`, `orgs`, `academicSessions`, `users`, `courses`, `classes`, `enrollments`) compatible with Canvas / Schoology / Google Classroom imports. Roster-only reader recovers courses, teachers, students, sections, and rooms (synthesized from class `location`); explicitly does NOT recover `CourseRequest` ranks or `BehaviorMatrix` because OneRoster has no concept of either — bootstrap a Dataset from OneRoster, then attach demand and behavior from another source. CLI: `solve --oneroster` writes `<out>/oneroster/` alongside the PowerSchool exports. 12 tests in `tests/test_oneroster.py` (writer-shape, manifest, round-trip counts, advisory→homeroom mapping). Multi-term scheduling (gap item g) was DEFERRED in the same session — Columbus runs year-long today, so OneRoster interop ships first. | `io_oneroster.py` (new), `cli.py`, `tests/test_oneroster.py` (new), `PRODUCTION_GAPS.md`, `MAINTENANCE_GUIDE.md` |
| 2026-04-25 (later) | Full-HS multi-grade ingest. `build_dataset_from_columbus` now accepts `grade: int | list[int]` — pass `[9, 10, 11, 12]` for full-HS. CLI `--grade` parses `12`, `9,10,11,12`, or `all-hs` shorthand. Each Student keeps their actual grade; each Course's `grade_eligibility` is the set of requesting grades. **Auto-relax HC3:** when any teacher carries ≥7 sections (real Columbus reality), the ingester sets `max_consecutive_classes=5` instead of the default 4. Reason: with 5 blocks/day and 8 schemes, a teacher using 7 different schemes provably has ≥1 fully-busy day no matter how schemes are assigned, making master infeasible at the default. Real Columbus full-HS: 510 students (129+128+132+121), 71 courses (40 cross-grade), 234 sections, 43 teachers, 38 rooms, 51 separations, 42 groupings — all from the same xlsx files used for Grade-12 demo. New tests in `TestParseGradeArg` and `TestMultiGradeIngest`. Path detection updated so `@real_data` tests find files at either the original Linux path or the repo-mirrored `reference/` directory. | `ps_ingest.py`, `cli.py`, `tests/test_ps_ingest.py`, `PRODUCTION_GAPS.md`, `MAINTENANCE_GUIDE.md` |
| 2026-04-26 | **Advisory-room bug fix (HC2b) + bundle hardening pass.** The standalone `verify_bundle.py` exposed a master-solver bug: HC2 (no two sections in same scheme/room) iterated only schemes 1..8, so all advisory sections (which share scheme=ADVISORY) could collapse to one room — and did, in real Columbus full-HS where 21 advisory sections all landed in R931B. **Fix:** added `model.AddAllDifferent([advisory_room[s] for s in advisory_sections])` as HC2b in `master_solver.py:158`. **Side effect:** broke `tiny_dataset` (n=100, seed=7) which was on the edge of feasibility — HC2b shifted master to a different OPTIMAL that left students INFEASIBLE. **Mitigation:** bumped tiny fixture to n=120 (same seed) per `conftest.py`. **New pytest regressions:** `test_no_advisory_room_double_booking` in `test_master_solver`; `test_advisory_rooms_distinct_in_export`, `test_no_inventions_in_export`, `test_every_output_id_exists_in_input` in `test_reports_exporter`. **Bundle hardening:** v2 client bundle has standalone `verify_bundle.py` (Python stdlib only, 16 invariants), a `03_AGENT_TEST_INSTRUCTIONS.md` runbook for the Columbus-side AI agent, an `input_data/` ground-truth directory in each school, and a 02_KPI_REPORT comparing v1 vs v2. Re-solved HS (98.7% electives, dev=3) and synthetic MS (100% electives, dev=1) — all 6/6 KPIs hit. Lessons: (a) verifier-driven discovery — the test that caught this bug was independent of the solver; (b) edge-of-feasibility fixtures break on solver changes — bump fixture size or accept seed sensitivity. | `master_solver.py`, `conftest.py`, `tests/test_master_solver.py`, `tests/test_reports_exporter.py`, `tests/test_scenarios.py` (golden seed update), `tests/golden/scenarios_default_tiny.json` (regenerated), `data/_client_bundle_v2/` (new) |
| 2026-04-25 (later) | Synthetic Middle School support per v2 §4.2. New `make_full_ms_dataset(n_per_grade)` in `sample_data.py` plus three grade-specific course catalogs (`MS_CORE_GR6`, `MS_CORE_GR7`, `MS_CORE_GR8`) and a 4-course `MS_ELECTIVES` pool. Same A-E rotation as HS (v2 §4.2: "Similar A-E structure, 5 blocks per day"). Grade 6 takes a fully required schedule (6 cores, no electives); grades 7 and 8 take 6 cores + 1 elective + 1 alternate. Solves end-to-end at n_per_grade ≥ 200 (≥600 students total). **Limitation discovered:** at smaller scales (n_per_grade < 200), master can place cohort-required courses with few sections into the same scheme, causing student solver to return INFEASIBLE because every cohort student can't fit two of their required courses. A first attempt at a Hall-matching constraint in `master_solver` fixed MS but broke `tiny_dataset` and other HS tests; the constraint was reverted in the same session. Fix is feasible but needs broader testing — see `master_solver.py` history. The PoC at n_per_grade≥200 demonstrates the engine handles MS structurally; tighter cohort-feasibility is the open work for production MS. CLI: `from src.scheduler.sample_data import make_full_ms_dataset`. | `sample_data.py`, `cli.py`, `PRODUCTION_GAPS.md`, `MAINTENANCE_GUIDE.md` |
| 2026-04-28 | **HC4 home-room constraint + revert auto-relax of `max_consecutive_classes`.** Cliente validó bundle v2 con un agente y reportó que el motor asignaba MUCHOS salones distintos a un solo profesor (Hoyos Camilo: 5 secciones en 5 salones), violando la regla "salón es por profesor" del doc `rfi_Reglas_Horarios_HS_2026_04_22_*.md`. **Fix HC4 en `master_solver.py:73-85`:** cuando `Teacher.home_room_id` está set y no hay `Section.locked_room_id`, el dominio de `section_room` se restringe sólo al home_room. **`ps_ingest.py` lee la columna ROOM del LISTADO MAESTRO** y asigna `Teacher.home_room_id` con dos heurísticas: (1) skip placeholder teachers (nombre empieza con "New ") — ellos rotan; (2) skip multi-room teachers (Sindy Margarita aparece en R933 y R923 — left None). En real Columbus 39/43 profesores reciben home_room; los 4 floating son Sindy + 3 placeholders. **También revertido el auto-relax de `max_consecutive_classes=4→5`**: ahora imprime un WARNING explícito a stderr listando los profesores con ≥7 secciones académicas (Sofia Arcila, Gloria Vélez, Clara Martínez) + opciones de mitigación. Operador decide si pasar `HardConstraints(max_consecutive_classes=5)` explícito o coordinar con escuela. **Re-solve real Columbus HS post-HC4: 6/6 KPIs ✅**, 0 HC4 violations, master OPTIMAL en 1.2s. Trade-off: first-choice electives 98.7% → 92.7% (-6pt — costo del room pinning), unmet rank-1 38 → 214. Aceptable; sigue sobre target ≥80%. **Decisiones abiertas para Hector:** regenerar bundle v3 con HC4 + PS format fixes (decisión 11) y manejo de los 3 profesores con 7 sec (decisión 12). Cliente reportó también 2 falsas alarmas (Julián Zúñiga sin cursos + Tecnología falta) — ambas son mismatch de nombres / confusión de cursos, no bugs. | `master_solver.py`, `ps_ingest.py`, `tests/test_master_solver.py`, `tests/test_ps_ingest.py`, `data/columbus_full_hs_v4/` (new exports) |
