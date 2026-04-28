# Changes to code — 2026-04-26 continuation session (TWO PHASES)

## Phase 1 — Hardening before Columbus response

Small additive hardening (1 Hypothesis property test, 1 CLI subcommand, README docs).

## Phase 2 — Bug fixes after Columbus client response

PowerSchool field-format corrections (SchoolID number, Period/Expression format, TermID 3600) per Columbus IT confirmation 2026-04-26. Models extended with `school_id` and `term_id` fields (optional). Tests + invariant checker updated for new Period format. Zero changes to solver constraint logic. Bundle NOT regenerated.

## Files modified — Phase 1 (hardening, before client response)

| File | Lines changed (approx) | Change |
|---|---|---|
| `scheduler/tests/test_hypothesis.py` | +28 lines | New property test `test_property_advisory_rooms_distinct` for HC2b — strengthens the single-fixture regression test in `test_master_solver.py`. |
| `scheduler/src/scheduler/cli.py` | +35 lines | New subcommand `generate-sample-ms` mirroring `generate-sample` but using `make_full_ms_dataset`. Surfaces the n_per_grade<200 working-scale floor in stderr. Updated the module docstring's subcommand list. |
| `scheduler/README.md` | +18 lines (Tests section restructured) | Replaced the small "Tests" snippet with a 3-tier explanation (fast / slow / Hypothesis) and a "Known test footguns" subsection covering golden snapshot drift, Hypothesis max_examples, and ps_ingest auto-skip behavior. |
| `docs/scheduler_skills_log.md` | +12 lines | New 2026-04-26 (continuation session) "Updates log" entry: 6 lessons learned (slow-test calibration sensitivity, CLI/Python parity, README test-tier docs, property-test force multiplier, etc.). |

## Files modified — Phase 2 (Columbus PS-format bug fixes)

| File | Lines changed (approx) | Change |
|---|---|---|
| `scheduler/src/scheduler/models.py` | +6 lines | Added `SchoolConfig.school_id: int \| str \| None = None` and `SchoolConfig.term_id: str \| int \| None = None` with docstrings citing the 2026-04-26 client confirmation values. Optional/backward-compat: if None, exporter falls back to existing `school` / `year` strings. |
| `scheduler/src/scheduler/exporter.py` | ~80 lines (rewrites) | (1) Replaced `_period_code(scheme)` (returned `P01..P08, ADV`) with `_expression(slots)` returning the Columbus-confirmed `<block>(<day>)` format (e.g. `1(A)2(D)4(B)`, `1(D-E)` for shared block, `3(E)` for advisory). (2) Added `_resolve_school_id(cfg)` and `_resolve_term_id(cfg)` helpers. (3) `ps_sections.csv`, `ps_enrollments.csv`, `ps_master_schedule.csv` now write the resolved values. (4) Field-mapping doc rewritten with the confirmed Columbus values and citation of the 2026-04-26 IT response. |
| `scheduler/src/scheduler/ps_ingest.py` | +12 lines | When constructing `SchoolConfig`: detects MS vs HS by ingested grades (6/7/8 → MS, 9-12 → HS); sets `school_id=12000` (MS) or `13000` (HS); sets `term_id="3600"` when `year` contains "2026-2027"; sets `school` name accordingly. |
| `scheduler/tests/test_reports_exporter.py` | 1 line + 2 lines doc | `test_advisory_period_code` now asserts `Period == "3(E)"` (was `"ADV"`); added a docstring citing the client confirmation. |
| `scheduler/tests/check_invariants.py` | ~30 lines refactor | (1) `_is_advisory(row)` helper — detects advisory by `CourseID == "ADV"` instead of by `Period == "ADV"`. (2) HC1 (teacher) and HC2 (room) now iterate over `Slots` cells (the `D1;B3;E5` ground-truth representation) instead of the `Period` string — robust to the format change AND more correct (Slots is the multi-cell list; Period is a stringified projection). (3) Added explicit HC2b advisory-rooms-distinct check (was previously implied via the academic checks but is now directly stated). |
| `docs/internal_pending_decisions.md` | +35 lines | New section: "Columbus client responses received 2026-04-26 (Hector forwarded)" with three tables (A1-A7 PS format, A8-A9 test env, B1-B6 academic validation) capturing every answer + action taken or open question reference. |

## Files NOT modified (across both phases)

- `scheduler/src/scheduler/master_solver.py` — solver constraint logic unchanged
- `scheduler/src/scheduler/student_solver.py` — solver logic unchanged
- `scheduler/src/scheduler/scenarios.py` — golden snapshot logic unchanged
- `scheduler/src/scheduler/sample_data.py` — generator unchanged
- `scheduler/tests/golden/scenarios_default_tiny.json` — **deliberately not regenerated** despite slow-test failure (would mask the drift; see `QUESTIONS_FOR_HECTOR.md`)
- `bundle_for_columbus/columbus_2026-2027_bundle_v2.zip` — sha256 confirmed unchanged. Bundle has the OLD Period/SchoolID/TermID formats; **regeneration deferred per decisión 9**.
- `scheduler/MAINTENANCE_GUIDE.md` — no recipes changed (solver behavior unchanged); Phase 2 changes are exporter-only
- `scheduler/PRODUCTION_GAPS.md` — no gaps newly closed or opened

**Specifically NOT changed in Phase 2 (waiting on Hector):**
- `master_solver.py` — `max_consecutive_classes` auto-relax logic (decisión 5: client says 4, code relaxes to 5 because of structural pigeonhole)
- `default_rotation()` / `BellSchedule` — Advisory still hardcoded at E3 for both HS and MS (decisión 6: MS shouldn't have fixed Advisory)
- `ps_ingest.py` `is_alternative` detection — still flags "Electives Alternative N" as rank-2 (decisión 8: 2026-2027 should ignore)

## Test results after changes (re-run after Phase 2 edits)

### Fast suite (default — `pytest tests/ --ignore=tests/test_hypothesis.py`)
**106 passed, 1 deselected in 3:48** after Phase 2 changes. No regression from any of the additions. Stable across multiple runs in this session.

### Slow regression suite (`pytest -m slow`)
**1 failed in 2:29** — golden snapshot drift, NOT a solver regression. Two failure pattern shapes observed across two re-runs:
- Run A: `electives_priority` -4.2pt, `lexmin_mode` -3.3pt (tolerance ±3.0pt) plus 4 unmet-rank-1 increases
- Run B: `cap_27` flipped FEASIBLE→INFEASIBLE, `tight_balance` flipped FEASIBLE→INFEASIBLE, plus the Run A drift

Source: same machine, same code, same dependencies. Diagnosed as multi-worker non-determinism amplified by tight time budgets (master_time=15s, student_time=30s). The fast suite uses larger budgets and is stable. Calibration policy decision left for Hector — see `QUESTIONS_FOR_HECTOR.md` item decisión 1.

### Hypothesis property tests (`pytest tests/test_hypothesis.py`)
**4 passed, 1 failed (in batch run); all 5 pass when run individually.**
- The new `test_property_advisory_rooms_distinct` (my addition): **passed**
- The pre-existing `test_property_solver_output_invariants`: failed at seed=1 with `balance=4 > 3` (worst course: GOV) when run as part of the batch, passed when run alone. Edge-case post-HC2b. See `QUESTIONS_FOR_HECTOR.md` item decisión 2.

### Streamlit app (`AppTest`)
**6 tabs render, 0 exceptions, 0 errors.** Click on "Generate sample" works → 4 metrics shown. Demo path is functional.

### Standalone bundle verifier
Not re-run because the bundle was not modified and the sha256 confirms integrity. The Columbus-side agent will run it.

## Confirmation that solver was not modified

Hashes of `master_solver.py` and `student_solver.py` after Phase 2 changes:
```bash
$ sha256sum src/scheduler/master_solver.py src/scheduler/student_solver.py
9a99c878e3689bbc53e683ee59793e299aaeca5f17560fe4e0380c04ba18f5c2  src/scheduler/master_solver.py
2d4e10d2d34abb7768e8b16ec9661e40863ee016866e548a8af960f90b06690e  src/scheduler/student_solver.py
```

Same hashes as at handoff time. Solver constraint logic NOT modified.

`models.py` and `exporter.py` ARE modified (Phase 2). The changes are additive (new optional fields with backward-compat fallbacks) and format-only (Period string format). They do not affect what the solver computes — only how the result is written to PowerSchool CSVs.

Per WHAT_TO_REPORT_BACK contract: I did NOT re-run `verify_bundle.py` because (a) the bundle was not regenerated and (b) the verifier itself doesn't check PS field formats — it checks invariants on the CSVs. The bundle still passes its own verifier. The new Period format is what would NOT pass a real PowerSchool sandbox import — which is exactly the change decisión 9 (regenerate v3) addresses.
