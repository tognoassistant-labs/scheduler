# Production Gaps — Columbus Scheduling Engine

What the May 1 prototype does NOT yet do, and what it would take to close each gap. Maps to v2 requirements.

## 1. Real data integration

| Gap | Status | What's needed | Effort |
|---|---|---|---|
| ~~Real Columbus HS data ingestion~~ | ✅ DONE | `ps_ingest.py` reads `1._STUDENTS_PER_COURSE_*.xlsx` (course demand, teacher-course-room mapping, per-student requests) and `HS_Schedule_*.xlsx` (separations/groupings). 121 Grade-12 students, 93 sections, 100/100 readiness. Solves with 97.8% electives. | — |
| ~~Behavioral matrix in real format~~ | ✅ DONE | Parsed from `Student Groupings` sheet. ID column-mismatch between sheets handled (`STUDENT_ID` vs `ID` columns). | — |
| ~~OneRoster compatibility (v2 §7.2)~~ | ✅ DONE | `io_oneroster.py` writes v1.1-compliant bundle (`manifest`, `orgs`, `academicSessions`, `users`, `courses`, `classes`, `enrollments`). Reader is roster-only — `CourseRequest` ranks and `BehaviorMatrix` are not in the OneRoster schema, so they come back empty (use the reader to bootstrap a roster, then attach demand from another source). CLI: `solve --oneroster` adds `<out>/oneroster/` to the export. 12 tests in `tests/test_oneroster.py`. | — |
| PowerSchool API integration (v2 §7.3) | open | `ps_api_client.py` with REST/PSPP plugin support; replaces CSV step | 2–3 weeks |
| Real PS enrollment CSV ingest | partial | `ps_ingest.py:read_ps_enrollment_csv()` reads Spanish-headers PS export with BOM, returns flat rows. Not yet wired to Dataset assembly (would need to be combined with another data source for course demand). | 2–3 days |
| Other grades (HS 9-11) | ✅ DONE for HS | `ps_ingest.py` now accepts `grade=int | list[int]`; CLI `--grade` accepts `12`, `9,10,11,12`, or `all-hs` shorthand. Auto-relaxes `max_consecutive_classes` from 4 to 5 when any teacher carries ≥7 sections (real Columbus reality). MS still open — different rotation per v2 §4.2 (3-week cycle), different course catalog, no `Esquemas` tab in MS xlsx. | MS still ~2 weeks |

## 2. Solver quality

| Gap | Status | What's needed | Effort |
|---|---|---|---|
| ~~Section balance ≤3 student deviation~~ | ✅ DONE | Hard per-course spread cap (max−min ≤ 5) + soft minimization, single-pass weighted | — |
| Co-planning windows for teachers (v2 §6.2) | ⚠️ partial | Implemented in master_solver (weight=0 by default; can be enabled per school via `SoftConstraintWeights.co_planning`). When enabled at weight ≥1 it concentrates same-dept sections into fewer schemes, hurting first-choice electives by ~10-15pts. Tuning needed before defaulting on. | 3-5 days for tuning + per-dept config |
| OPTIMAL convergence within 5 minutes | open | Symmetry breaking on identical sections; warm-start from prior year | 1–2 weeks |
| ~~Teacher preferences honored (v2 §6.2)~~ | ✅ DONE | `Teacher.preferred_course_ids`, `avoid_course_ids`, `preferred_blocks`, `avoid_blocks` in `models.py`. Soft objectives in `master_solver.py` reward preferred matches and penalize avoided ones. Streamlit "🔒 Locks & Prefs" tab has an inline editor. CSV roundtrip. | — |
| ~~Singleton conflict avoidance (v2 §5.2)~~ | ✅ DONE (off by default) | Implemented as a soft objective in master_solver — minimize max-singletons-per-scheme. Default weight=0 because it competes with electives/balance; enable per-school via `SoftConstraintWeights.singleton_separation` if needed. | — |
| Multi-term scheduling (semester / quarter / year) | open | Section term support; per-term solves chained | 1–2 weeks |
| ~~Locked / pre-assigned sections~~ | ✅ DONE | `Section.locked_scheme` and `Section.locked_room_id` fields. Master solver enforces via equality constraints. Streamlit "🔒 Locks & Prefs" tab has an editable table. CSV roundtrip. v2 §13 (Human Approval) compliant. | — |
| Lex-min mode convergence on phase 2 (electives lock + grouping max) | partial | Phase 2 currently hits time limit at FEASIBLE; with warm-start it reaches OPTIMAL on small instances. Better hint propagation would help. | 2–3 days |

## 3. Hard constraints not yet modeled

| Constraint | Source | Effort |
|---|---|---|
| ~~Course prerequisites (v2 §4.3)~~ — DONE | `Course.prerequisite_course_ids` in `models.py`. `validate.py` does referential integrity, cycle detection (DFS), and per-student warning when a request lacks a prereq sibling request. Full enforcement requires transcript history (out of canonical Dataset scope). | — |
| Special-program restrictions (v2 §5.1) | Add program membership; filter sections accordingly | 3 days |
| Shared-staff availability (v2 §8.2) | Per-teacher availability calendar, not just max_load | 1 week |
| Shared rooms with usage windows (Spanish RFI) | Room availability windows by (day, block) | 3 days |

## 4. UI / UX

| Gap | What's needed | Effort |
|---|---|---|
| Admin dashboard (v2 §9 / English §9) | Next.js + Shadcn; schedule grid, section detail, override panel | 4–6 weeks |
| Manual override + lock | Per-section lock flag; resolve infeasibility hints | 2 weeks |
| ~~Scenario comparison (v2 §10)~~ — DONE | Implemented as `scenarios.py` + `cli.py scenarios` subcommand. Built-in presets cover baseline, cap_27, loose/tight balance, electives priority, lexmin. Custom scenarios via `ScenarioSpec(name, overrides)`. | — |
| Conflict review with one-click fixes | "Add a section" / "swap teacher" / "raise cap" actions | 3 weeks |
| Authentication + RBAC | Principal / counselor / dept chair / sysadmin roles | 1 week |
| Audit log | Immutable record of overrides and approvals | 1 week |

## 5. AI assistant layer (v2 §6.3 / §13)

| Gap | What's needed | Effort |
|---|---|---|
| NL Q&A over schedule | Anthropic Claude API + tool-use over solver outputs | 2 weeks |
| Why-was-X-assigned-Y explanation | Solver trace store + structured prompt rendering | 2 weeks |
| What-if scenario planning | Wrap solver as a tool the assistant can call | 2 weeks |
| PII redaction before LLM calls | FERPA + Habeas Data; strip names, emails, IDs before prompt | 1 week |

## 6. Operational

| Gap | What's needed | Effort |
|---|---|---|
| Postgres-backed persistence | Replace CSV-as-source with DB; CSV becomes import/export only | 1 week |
| Async solve queue (Celery) | Long solves run as background jobs with progress streaming | 1 week |
| Containerization (Docker) | Dockerfile + docker-compose for local dev | 2 days |
| Cloud deploy (one of AWS/Azure/GCP) | IaC + secrets management | 1–2 weeks |
| Observability | Solver runtime metrics, queue depth, error tracking | 3 days |
| Backup + disaster recovery | DB backups, point-in-time restore | 3 days |

## 7. Compliance

| Gap | What's needed | Effort |
|---|---|---|
| FERPA-aligned data handling | DPA, audit, access control, encryption in transit + at rest | 2 weeks |
| Colombian Habeas Data (Ley 1581) | Local-data-residency option; consent tracking | 1–2 weeks |
| Audit trail for student PII access | Track every read of student records | 3 days |

## 8. Testing & QA

| Gap | Status | What's needed | Effort |
|---|---|---|---|
| ~~Property-based tests for solver~~ | ✅ DONE | `tests/test_hypothesis.py` — 5 property tests covering CSV roundtrip, sample validation, solver output invariants, locks honored, capacity respected. Total 84 pytest tests across 9 files. Independent invariant checker at `tests/check_invariants.py` runs against PS exports. | — |
| ~~Scenario regression suite~~ | ✅ DONE | Golden-snapshot regression at `tests/golden/scenarios_default_tiny.json` (n=100 seed=7, default preset, 6 scenarios). `scenarios.to_snapshot_dict` + `scenarios.compare_to_golden` apply tolerances that catch real regressions while ignoring multi-worker CP-SAT noise. Test `test_golden_default_preset_tiny` is marked `slow` (~2.5 min) and deselected by default; opt in with `pytest -m slow`. Inline regenerate command in the test docstring. | — |
| End-to-end PS sandbox roundtrip test | open | Automated against a PS sandbox tenant — would require sandbox credentials and a test DB. | 1 week |
| ~~Load test at 520 HS students~~ | ✅ DONE | n=520 synthetic full-HS cohort (`make_full_hs_dataset` in `sample_data.py`) solves master OPTIMAL in 5.9s and students FEASIBLE within the 30-min budget, with 100% on every KPI (scheduled, required, first-choice electives, max-dev=3). Found and fixed two production blockers: (a) ortools 9.15.x is broken on Apple Silicon — pinned `ortools<9.13`; (b) master `min_distinct_schemes` constraint demanded >8 schemes for any course with >14 sections — capped at `len(SCHEMES)`. Student solve hit the time ceiling at FEASIBLE only because all soft objectives are already saturated; in practice it could stop at ~5 min. | — |

## 9. Multi-school expansion

| Gap | What's needed | Effort |
|---|---|---|
| Middle School support (v2 §4.2) | partial | Synthetic MS dataset working: `make_full_ms_dataset(n_per_grade=N)` in `sample_data.py` — same A-E rotation as HS (per v2 §4.2), three grade-specific course catalogs (6 cores per grade, no AP), 4-course MS elective pool for grades 7-8 only, grade-6 fully required (no electives). Solves end-to-end at n_per_grade≥200 (≥600 students). Smaller scales (n_per_grade<200) hit a cohort-required-clustering issue: when cohort-required courses have few sections, master can place them in the same scheme, leaving every cohort student unable to fit. A proper fix is a Hall-matching constraint in `master_solver` for cohort-required courses, but a first attempt broke HS tests; deferred. Real Columbus MS xlsx ingest is still open (different file structure, no `Esquemas` tab). | Real MS ingester ~1 week |
| Elementary School (v2 §4.2 — deferred) | Homeroom-based; 7 blocks; different hours K–5 | 3–4 weeks |
| Multi-campus (v2 English §16) | Cross-campus teacher sharing; campus-aware constraints | 2–3 weeks |

## Total to production-ready (HS + MS, no AI assistant)

Realistic bottom-up estimate: **14–18 weeks** with the team described in `scheduler_skills_log.md`. Adding the AI assistant adds another 6–8 weeks; adding ES adds 3–4 weeks; multi-campus adds 4 weeks. The May 1 demo is roughly **6–8% of the total work** — most of the iceberg is below the waterline (UI, integration, compliance, ops).
