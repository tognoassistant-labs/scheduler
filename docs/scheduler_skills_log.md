# Skills Log — Scheduler Solution

Living document. Each row = one capability needed to deliver the Columbus scheduling engine. Used later as input for defining agent profiles for the next scheduler project.

Columns:
- **Skill** — the capability
- **Why needed (this project)** — concrete reason it shows up in Columbus work
- **Depth** — Core (must have full ownership) / Strong (must execute well) / Working (must collaborate competently)
- **Reusable as agent profile?** — Y/N + suggested profile name if Y

---

## A. Optimization & math

| Skill | Why needed | Depth | Agent profile? |
|---|---|---|---|
| Constraint Programming (CP-SAT) with Google OR-Tools | The core scheduling engine; two-stage solve (master then student assignment) | Core | Y — `optimization-engineer` |
| Mathematical modeling of school scheduling | Turn 8 schemes × 5 days × 5 blocks × teacher/room/student constraints into solvable variables | Core | Y — `scheduling-modeler` |
| Symmetry breaking, warm-starting, time-budgeted solves | 520 students × 8 courses won't solve naively; needs solver craft | Strong | Y — folded into `optimization-engineer` |
| Soft-constraint weighting / multi-objective tuning | Balance class size, electives, co-planning preferences | Strong | Y — folded into `optimization-engineer` |

## B. Data & validation

| Skill | Why needed | Depth | Agent profile? |
|---|---|---|---|
| Schema design (Postgres relational + typed JSON for constraint config) | Constraints-as-data store, parameterizable per school/grade/year | Core | Y — `data-modeler` |
| CSV ingest + cleaning (Pandas / Apache POI for Excel) | PowerSchool exports, behavioral matrix, course demand files | Core | Y — `data-engineer` |
| Data validation framework + readiness score | Hard prerequisite before any solve runs | Core | Y — `data-validator` |
| ID reconciliation across messy real-world inputs | enrollment CSVs already mix `2_11104`, `1_10656`, `arodriguez789*` formats | Strong | Y — folded into `data-engineer` |

## C. Backend engineering

| Skill | Why needed | Depth | Agent profile? |
|---|---|---|---|
| Python + FastAPI **or** Java + Spring Boot | Service layer wrapping solver and exposing APIs | Core | Y — `backend-engineer` |
| Background job / queue (Celery, or Spring async) | Solves take minutes; must run async with progress | Strong | Y — folded into `backend-engineer` |
| REST API design with role-based auth | Admin/counselor/dept-chair separation | Strong | Y — folded into `backend-engineer` |

## D. Integrations

| Skill | Why needed | Depth | Agent profile? |
|---|---|---|---|
| PowerSchool CSV mapping (sections, enrollments, master) | Phase 1 PS export | Core | Y — `powerschool-integration` |
| PowerSchool API (REST/PSPP plugins) | Phase 2 push-back without manual import | Strong | Y — folded into `powerschool-integration` |
| OneRoster (CSV/REST) | Forward-compat for SIS portability | Working | Y — folded into `powerschool-integration` |

## E. Frontend / UX

| Skill | Why needed | Depth | Agent profile? |
|---|---|---|---|
| Next.js + React + Shadcn/Tailwind | Admin dashboard, conflict review, manual override | Core | Y — `admin-ui-engineer` |
| Schedule grid visualization patterns | Render 5×5×8 schemes legibly; lock/override cells | Strong | Y — folded into `admin-ui-engineer` |
| Scenario diff / compare UI | "Add one Algebra section" what-if analysis | Strong | Y — folded into `admin-ui-engineer` |

## F. AI assistant layer

| Skill | Why needed | Depth | Agent profile? |
|---|---|---|---|
| Anthropic Claude API (tool use, structured outputs) | NL queries; explanation rendering | Core | Y — `ai-assistant-engineer` |
| Prompt caching strategy | Schedule + traces are large + reused | Strong | Y — folded into `ai-assistant-engineer` |
| Retrieval over solver traces (not over PII) | Grounded explanations, no hallucination on assignments | Core | Y — `explainability-engineer` |
| PII redaction before LLM calls | FERPA + Colombian Habeas Data (Ley 1581) | Core | Y — folded into `security-compliance` |

## G. Security & compliance

| Skill | Why needed | Depth | Agent profile? |
|---|---|---|---|
| RBAC / authn-authz design | Principal vs counselor vs dept chair vs sysadmin | Strong | Y — `security-compliance` |
| FERPA-aligned data handling | English RFP requires it | Strong | Y — folded into `security-compliance` |
| Colombian Habeas Data (Ley 1581) | Local compliance for Columbus | Strong | Y — folded into `security-compliance` |
| Audit logging | Every override/approval traceable | Working | Y — folded into `security-compliance` |

## H. QA & testing

| Skill | Why needed | Depth | Agent profile? |
|---|---|---|---|
| Property-based / fixture-driven testing for solvers | Generate adversarial inputs to validate constraint handling | Strong | Y — `solver-qa` |
| Scenario regression suite | Lock golden schedules; detect regressions on rule changes | Strong | Y — folded into `solver-qa` |
| End-to-end PS roundtrip test in sandbox | Validate exports without polluting prod | Core | Y — folded into `solver-qa` |

## I. DevOps / delivery

| Skill | Why needed | Depth | Agent profile? |
|---|---|---|---|
| Docker + cloud deploy (one of AWS/Azure/GCP) | Solver container, web container, db | Working | Y — `devops` |
| Observability (logs, solver runtimes, queue depth) | Solves can hang; need visibility | Working | Y — folded into `devops` |

## J. Domain & process

| Skill | Why needed | Depth | Agent profile? |
|---|---|---|---|
| K–12 master scheduling expertise | Translate Columbus rules to formal constraints | Core | Y — `school-scheduling-sme` |
| PowerSchool administration | Field semantics, term setup, year rollover | Strong | Y — folded into `powerschool-integration` |
| Stakeholder facilitation (principal/coordinator workshops) | Hard vs soft constraint elicitation is a workshop, not a doc | Strong | N (human role) |
| Technical writing for non-technical reviewers | Schedule explanation reports, admin training material | Working | Y — `tech-writer` |

---

## Suggested agent team for the next scheduler project (consolidated)

Minimum viable team of 6–8 specialized agents:

1. **`scheduling-modeler`** — owns the formal constraint model; speaks OR-Tools natively; takes business rules and returns a CP-SAT model with proofs of equivalence.
2. **`optimization-engineer`** — owns solver performance; symmetry breaking, warm starts, multi-objective tuning, time budgets.
3. **`data-engineer`** — owns ingest, schema, validation, readiness score; reconciles dirty real-world IDs.
4. **`powerschool-integration`** — owns CSV mapping and API client; runs sandbox roundtrip tests.
5. **`backend-engineer`** — owns service layer, async jobs, RBAC.
6. **`admin-ui-engineer`** — owns dashboard, override UX, scenario compare.
7. **`ai-assistant-engineer`** — owns NL Q&A and trace-grounded explanations; never the optimizer.
8. **`solver-qa`** — owns fixtures, scenario regression, sandbox PS validation.
9. *(optional)* **`security-compliance`** — FERPA/Habeas Data, RBAC, audit, PII redaction; can be folded into backend if budget tight.
10. *(optional)* **`school-scheduling-sme`** — domain agent that vets constraints in plain English before they hit the modeler.

### Specialized profiles inferred during execution

These emerged from real implementation work and are documented in the Updates log below. Use to spin out specialists when the MVP team hits the corresponding bottleneck.

| Profile | Why it splits out | Folds into |
|---|---|---|
| `solver-objective-tuner` | Empirical multi-objective weight tuning is a distinct skill from formal modeling | `optimization-engineer` |
| `prototype-driver` | Runs end-to-end smoke tests after every change; catches integration regressions in seconds | Cross-cutting; can be a hook in any agent |
| `streamlit-prototype-engineer` | Demo/internal-tool UIs only; not production. Knows `st.session_state`, `AppTest`, deprecation cycles | Distinct from `admin-ui-engineer` |
| `human-in-the-loop-ux-designer` | Owns lock/override/approval workflows where human authority overrides the model | Distinct from `admin-ui-engineer` |
| `real-data-shape-archaeologist` | Schema discovery on unfamiliar real-school exports (xlsx, dirty CSV); finds join keys, ID-format quirks, orphan records | Distinct from `data-engineer` |
| `solver-qa-engineer` | Property-based fuzzing + independent invariant checkers + scenario regression for CP-SAT specifically | Replaces generic `solver-qa` |
| `environment-resilience-engineer` | Diagnoses package/wheel/runtime incompatibilities (e.g., ortools 9.15 broken on Apple Silicon) | Cross-cutting; can fold into `devops` |
| `regression-test-curator` | Owns what to snapshot, what to tolerate, what to opt-out by default. Multi-worker non-determinism makes exact-match brittle | Folds into `solver-qa-engineer` |
| `interop-format-engineer` | OneRoster, PowerSchool CSV, etc. — knows what each format does and DOESN'T carry; documents non-round-trip fields | Folds into `powerschool-integration` |
| `cohort-feasibility-engineer` | Hall-matching constraint class for "every student in cohort C takes this same K courses" — discovery, not just tuning | Distinct from `optimization-engineer` |
| `client-deliverable-packager` | Bundles solver outputs into client-uploadable packages with bilingual docs, sandbox-first deployment instructions, explicit unknowns | Folds into `tech-writer` + `powerschool-integration` |
| `independent-verifier` | Verification that consumes only the exports, never the solver. Random-sample audits, cross-check input vs output, replay constraints from CSVs | Distinct from `solver-qa-engineer` (different code path) |

### Anti-patterns observed

- **Silent meta-documentation drift.** During multi-hour autonomous sessions, living docs (`MAINTENANCE_GUIDE.md`, `PRODUCTION_GAPS.md`, this file) drift out of date until explicitly raised. Future agent systems need an end-of-session prompt that demands a docs-updated check before "done".
- **Untested constraint additions.** A new solver constraint that fixes the most-recent failing fixture must be regression-tested against every existing fixture before shipping. Cohort Hall-matching attempted, broke HS, reverted — the cost was contained only because the fast suite caught it within minutes.
- **CPU-time blindness.** A process at 6s CPU after 3 hours wall is *wedged*, not *slow*. Future tooling should surface this distinction by default.

---

## Updates log

- **2026-04-25** — initial skills inventory after reading `powerschool_requirements_v2.md`.
- **2026-04-25 (after Track A prototype)** — confirmed via working build at `/home/hector/scheduler`:
  - `scheduling-modeler` and `optimization-engineer` are the **dominant** skills. The model design (variables, hard vs soft, multi-objective shaping) and the solver tuning (scheme balance, weight ratios) are the bottleneck for solution quality. Underweighting either yields broken or unbalanced schedules.
  - **Solution-quality discovery**: section-balance objective formulated as `(max - min)` per course works; `max` alone collapses balance. Lex-min ordering would be the next step.
  - **Trade-off discovery**: balance vs first-choice electives is real and quantifiable. Weight tuning (balance=2, first-choice=20) hit 93% first-choice with acceptable balance; reverse weights hit 80% first-choice with no balance gain.
  - `data-engineer` skill = sizing sections from **actual** demand (post-student-generation) is non-negotiable; estimating from heuristics produced bogus capacity warnings.
  - `data-validator` skill saved time — readiness score caught teacher-overload and capacity-shortfall before the solver wasted minutes trying.
  - `powerschool-integration` is genuinely a separate skill, not just CSV writing — field mapping (Period, TermID, Expression) needs PS-specific knowledge to avoid sandbox-import surprises.
  - **New skill not in original list**: **`solver-objective-tuner`** — composing soft-constraint weights so they don't dominate each other. This is empirical tuning, not just modeling. Could be folded into `optimization-engineer` or split out as its own profile for next project.
  - **Reusable artifact**: the `Dataset → Pydantic` round-trip pattern is the right interface boundary. Every other skill (validation, solver, exporter) consumes `Dataset`. Future agent team should agree on this contract before parallel work.

- **Suggested new agent profile to add** (based on what hurt during the build):
  - **`prototype-driver`** — runs end-to-end smoke tests against synthetic data after every major change. Catches integration regressions (e.g., the CSV round-trip) within seconds. Prevents the "ship 5 modules, integrate at the end, debug for a week" failure mode.

- **2026-04-25 (after solver hardening pass — closed the section-balance gap)**:
  - **Lex-min ≠ silver bullet.** Three-phase lex-min (electives → balance → groupings) with balance as a soft objective in phase 2 burned the entire solver budget without converging. Balance-as-soft is too combinatorially expensive on 130×62 problems. The shipped pattern that actually works: **hard balance cap + soft balance term + single-pass weighted-sum**. Cap (max−min ≤ 5) prevents catastrophic outliers; the soft term tightens within the cap; single-pass weighted is fast and predictable.
  - **Tuning K for hard balance is a UX decision.** K=4 made phase 1 elective optimization infeasible. K=8 met no balance KPI. K=5 ↔ max-dev ≤ 3 after rounding hit all KPIs. Future agent profile (`solver-objective-tuner`) needs to know that translating "v2 §10 target ≤3 max-dev" to "K hard cap" requires understanding the rounding boundary and the spread-vs-dev relationship (max-dev = max(max-mean, mean-min), bounded by max-min/2 for symmetric distributions but can equal max-min for skewed ones).
  - **Master solver multi-worker beats single-worker even with fixed seed.** Single-worker deterministic produced schedules that left no feasible room for tight balance constraints. 4-worker with `random_seed=42` gives reproducibility (within OR-Tools' guarantees) AND better-quality master schedules.
  - **Min-section threshold matters for balance.** Initially gated balance to courses with ≥3 sections, which let 2-section electives produce huge spreads (16/6 splits). Aligning min_sects with the report metric (≥2) closed this hole. Lesson: **the constraint set and the KPI set must agree on which entities they apply to** — easy to miss, hard to debug.
  - **Solver `ClearObjective()` + `ClearHints()` is mandatory between lex-min phases.** Using only `ClearObjective` left stale hints that made phase 3 return MODEL_INVALID. Add `prototype-driver` instinct: re-run the smoke test after every solver-state-mutation change.

- **Lessons codified into reusable agent guidance (for next scheduler project)**:
  1. Default to **single-pass weighted with hard caps**, not lex-min. Lex-min is a fallback for cases where the user demands strict priority.
  2. Always keep an **independent invariant checker** in the loop. Run it on the exported CSVs (not the solver's internal vars). Several "passing" runs had hidden violations only the independent checker caught.
  3. **Reproducibility ≠ determinism.** Use `random_seed` and accept that multi-worker is non-strictly-deterministic. Don't sacrifice solution quality for byte-identical reproducibility.
  4. **The report metric and the solver constraint must measure the same thing.** Hidden mismatch (min_sects=3 vs ≥2) wastes hours debugging "why the constraint isn't holding."

- **2026-04-25 (after co-planning + scenario simulation passes)**:
  - **Soft objectives can break the master/student composition.** Adding co-planning to master with weight=3 made the master locally-better (more dept overlap) but globally-worse (student INFEASIBLE). Lesson: when a soft objective in stage 1 changes the *shape* of the solution (not just the cost), it can poison stage 2. Default new soft objectives to weight=0 and force users to opt in after measuring.
  - **A hard constraint can rescue a problematic soft objective.** Adding "min schemes per course = ceil(n_sections/2)" to master did two things: (1) made co-planning safe to enable, (2) improved electives even with co-planning OFF (from 81.5% → 86.2%). Lesson: hard structural invariants reveal hidden assumptions in your model.
  - **Scenario simulation is cheap when you have isolation.** Deep-copying the dataset takes ms; the value is in seeing trade-offs as a table not a debate. The 6-scenario preset took ~9 minutes total but produced a side-by-side that's worth a 30-minute meeting.
  - **New skill confirmed real**: `solver-objective-tuner` (proposed earlier as folded into `optimization-engineer`) deserves its own profile. Tuning weights for multi-objective is empirical, requires deep knowledge of CP-SAT internals (search heuristics, branching, restart behavior), and is distinct from formal modeling.

- **For future agents maintaining this codebase, key references**:
  - `/home/hector/scheduler/MAINTENANCE_GUIDE.md` — code-level "how to make changes" guide. Read first if you need to add a constraint, change a KPI, or debug an infeasibility.
  - `/home/hector/scheduler/PRODUCTION_GAPS.md` — what's done, what's not, with effort estimates. Use to plan iterative work.
  - `/home/hector/scheduler/DEVELOPMENT_PROPOSAL.md` — phased plan for Track B production.
  - This file (`scheduler_skills_log.md`) — skills/agent-profile inventory, kept up-to-date with each milestone.

- **2026-04-25 (after real Columbus xlsx ingester pass — Phase 1 unlocked)**:
  - **The "ID" column is not the "STUDENT_ID" column.** Columbus's `Math_Conditional` sheet has both `STUDENT_ID` (account ID, e.g., 4413) and `ID` (PS ID, e.g., 30004). Only `ID` matches the `Student Groupings` sheet. **Lesson: in real-school data, identify the "join key" column explicitly before assuming it's the leftmost ID column.** Took 30 min to debug an empty behavior matrix.
  - **"Optative" ≠ "Alternative".** Columbus marks primary cross-department electives as "Optatives" (the student WANTS each one) and only marks fallback courses as "Electives Alternative N". The naive synthetic-data assumption ("students request 1 first-choice + 1 alt") collapsed real-data first-choice rate from 97.8% to 14.3% via a single `at most 1 elective total` constraint. **Lesson: domain semantics matter more than syntactic similarity.** When the model says "elective", check whether the school means "one optional course" or "one of several optional courses I want."
  - **Real schools' max_load varies.** Columbus has teachers with 6 sections; default `max_load=5` is wrong for them. Auto-adjusting `max_load = max(default, observed)` from `LISTADO MAESTRO` keeps validation clean without manual config per teacher.
  - **Drop "orphan" courses silently.** Columbus had a "Teacher Aide" course with 1 student request but no entry in `LISTADO MAESTRO` (no teacher/room assignment). The ingester now drops such courses from the dataset rather than creating downstream solver infeasibilities. Real-data noise should be filtered, not propagated.
  - **Advisory ≠ teaching load.** Real schools don't count Advisory against academic teaching load. Validation now excludes advisory sections from the `max_load` check.
  - **Schema discovery is half the work.** Inspecting the actual xlsx files (sheet names, column layouts, ID formats, encoding) took ~15 minutes of focused reading before any code was written. **Lesson: always do a schema-discovery pass first — it changes assumptions about field types, header normalization, sheet selection, and join keys. Skipping this step on real data wastes more time than it saves.**

- **New skill profile to consider for next project (concrete, not generic)**:
  - **`real-data-shape-archaeologist`** — opens unfamiliar real-school exports (xlsx, CSV, sometimes PDF), maps their schemas to canonical models, and identifies join keys, encoding quirks, ID-format mismatches, and orphan records. This work is distinct from `data-engineer` (which assumes a known schema) and from `data-validator` (which assumes the data has been mapped).

- **2026-04-25 (after Streamlit UI pass)**:
  - **The "admin-ui-engineer" profile splits into two**: a **demo-UI** profile (Streamlit/Gradio prototypes — what we just shipped, fast to build, fine for stakeholder demos) and a **production-UI** profile (Next.js + Shadcn + RBAC + auth — what Phase 3 of Track B requires). Streamlit is great for "show the schedule engine working" but does not satisfy v2 §9's RBAC, audit-log, or scenario-history requirements. Don't conflate them when staffing.
  - **Single-file Streamlit > multi-page Streamlit for prototypes ≤ ~500 lines.** Multi-page (`pages/` directory) adds boilerplate without reducing complexity until you have actual page-specific persistence concerns.
  - **`st.session_state` is the cache layer.** Don't call solvers (or any expensive function) without first checking session_state. Every interaction triggers a full script rerun.
  - **`AppTest.from_file()` is great for CI.** It executes the app code path without a browser and catches syntax errors, import failures, runtime exceptions, and even API deprecations. Use it as the smoke test for every UI change.
  - **Streamlit deprecation cycles are aggressive.** `use_container_width=True` was deprecated mid-2025 and removed late 2025. Always check streamlit's `st.warning` messages on first boot — they're not silent. Pin streamlit version in production.
  - **The UI doesn't add solver capability — it adds reachability.** Same KPIs, same solver, same exports. The value is that a coordinator can run the solve themselves, change a slider, and see the impact, without learning the CLI. For Track B, this is the entry point that gets the school's coordinator engaged with the engine.

- **New skill profile inferred from this pass**:
  - **`streamlit-prototype-engineer`** — fast Streamlit/Gradio prototypes that wrap an existing engine. Distinct from production frontend work. Useful for: stakeholder demos, internal tools, feasibility studies, MVP UIs. Skills: `st.session_state`, deprecation tracking, `AppTest`, mixing `st.dataframe`/`st.markdown`/CSS-in-markdown for KPI cards. Should NOT be staffed for production-grade UI (auth, RBAC, audit, RBE).

- **2026-04-25 (after solver-quality pass — locks + prefs + prereqs + singletons)**:
  - **A "soft objective" can have hard side-effects on the solution shape.** Adding singleton-separation as a soft term (weight 4) at default visibly hurt synthetic KPIs (78.5% electives vs 84.6% baseline). Lesson: each new soft term must be benchmarked against ALL the existing KPIs, not just the one it targets. Default new soft terms to weight=0 unless they prove additive.
  - **Locks must broaden the variable domain, not contradict it.** A locked room outside a section's normal compatibility set was first INFEASIBLE because `section_room` had a domain that excluded the locked room. Fix: include the locked room in the section's `course_rooms` list when constructing variables. Operator override > type compatibility.
  - **Cycle detection in prereq graphs is a 5-line DFS, not a library call.** Worth doing at validation time — an undetected prereq cycle would produce an unsolvable dataset.
  - **`st.data_editor` is the right tool for "edit-then-apply" workflows.** It makes the lock/preference editing experience natural without paginated CRUD or modal forms. Always pair with an "Apply" button — don't auto-mutate session state on every cell change (causes excessive reruns).
  - **Prerequisite enforcement requires transcript history**, which is out of the canonical Dataset scope. The validation only WARNS at the request level. Full enforcement is Phase 0 work (real PS data ingest of completed courses) — flagged as `PREREQ_NOT_IN_REQUESTS` warning, not error.

- **New skill profile inferred**: `human-in-the-loop-ux-designer` — owns the lock/override/approval flows that v2 §13 demands. Distinct from `admin-ui-engineer` because the focus is on workflows where the human's authority OVERRIDES the model (locks, manual assignments, signed approvals), not on display/browsing. Critical for school operations because schedules always have political/contextual constraints the solver can't see.

- **2026-04-25 (after test suite + Hypothesis pass)**:
  - **Hypothesis caught a real bug Day 1.** `sample_data.py` was skipping sections for courses requested only at rank-2. A student picking PSYCH only as alt would fail validation. Took 5 seconds for Hypothesis to find a failing example (seed=15, n=15). Lesson: **property-based fuzzing pays for itself the moment the suite runs**. Don't wait until "we have time" to add it.
  - **Conditional properties beat strong properties.** Initial property "every seeded sample produces a feasible solve" was too strong — singleton clustering at small N makes some seeds infeasible. Right pattern: "if a solution exists, it must satisfy invariants." Skip examples where the precondition fails (`if not master: return`). Hypothesis will still find shrinking counterexamples for legitimate bugs.
  - **An independent invariant checker is worth more than 100 unit tests.** `tests/check_invariants.py` reads the EXPORTED CSVs (not the solver's internal vars) and verifies the hard constraints + balance KPI. It catches discrepancies between what the solver thinks it produced and what's actually in the output. This is where solver bugs would manifest first.
  - **Solver fixtures should be the smallest reliably-feasible size, not the smallest possible size.** Initial tiny fixture at n=30 was infeasible at hard balance K=5. Bumped to n=100, seed=7. Lesson: when fixtures fail, don't loosen constraints — pick a more representative fixture size.
  - **84 tests in 4 minutes is the right CI shape.** Fast subset (~1 min) without Hypothesis catches obvious regressions. Full suite (~4 min) catches edge cases. Anything slower would discourage pre-commit running.

- **New skill profile inferred**: `solver-qa-engineer` — owns property-based fuzzing of CP-SAT solvers, independent invariant checkers, scenario regression suites. Distinct from generic QA because: (1) requires understanding solver semantics (OPTIMAL vs FEASIBLE vs INFEASIBLE vs UNKNOWN), (2) needs intuition for which properties to fuzz (capacity, conflicts, locks) vs which not (specific KPI values, which are stochastic), (3) builds the independent invariant checker that catches discrepancies between solver claims and exported reality.

- **2026-04-25 (later — full-HS load test + golden snapshot + OneRoster pass)**:
  - **Package-version compatibility is a Day-0 risk, not a deployment risk.** ortools 9.15.x ships a broken Apple Silicon wheel: returns `MODEL_INVALID` on a trivial 2-variable LP in single-worker mode and hangs forever in default multi-worker mode. **Cost a 4-hour debug session** of "tests are slow" before realising the solver was wedged. Pinned `ortools>=9.10,<9.13` (9.11.4210 confirmed working on Python 3.12). Lesson: when a CI/test run is unusually slow, **check CPU time vs wall time** — a process at 6s CPU after 3 hours wall is wedged, not slow.
  - **Trivial CP-SAT smoke test belongs in the test suite.** Cost of a 2-variable solve check: 5 ms. Cost of a missing one: 4 hours. Future scheduler projects should include a "is the solver itself functional" check before trying full-scale solves.
  - **Master constraints can be structurally infeasible at scale even when locally sound.** `min_distinct_schemes = ceil(n_sections/2)` worked fine for ≤14-section courses but demanded >8 schemes for any course with >14 sections — physically impossible since only 8 schemes exist. Capped at `len(SCHEMES)`. Lesson: any constraint of the form "at least N of X" must be bounded by `min(N, |X|)`.
  - **Multi-worker non-determinism + identical inputs ≠ identical outputs.** Student solver uses `num_search_workers=4` and no `random_seed`, so KPIs drift ±2pt between runs. Golden-snapshot regression must use **tolerances** (`first_choice_elective_pct ≥ golden − 3`, `section_balance_max_dev ≤ golden`, etc.), not exact equality. Encoded the tolerances in `scenarios.compare_to_golden` so the policy is in code, not in test reviewers' heads.
  - **Slow tests belong in a separate marker.** The golden regression takes ~2.5 min; if it ran by default the fast suite would balloon from 2 min to 4.5 min and pre-commit running would suffer. `pytest -m "not slow"` (the new default) keeps the fast loop tight; `pytest -m slow` opts in.
  - **Synthetic data must scale with the cohort or it lies.** Original `make_grade_12_dataset(n=130)` clipped at 22 teachers / 22 rooms regardless of n. At n=520, the same fixed pool produced datasets that were infeasible by construction — not a solver problem, a data problem. Added `scale=` parameter to `_make_teachers`/`_make_rooms`/`_assign_qualifications` plus `make_full_hs_dataset(n)` that auto-picks scale. Lesson: synthetic-data generators that "scale" must scale every dimension that real-world growth would scale, not just the headline number.
  - **OneRoster v1.1 round-trip has structural limits worth documenting.** OneRoster has no concept of `CourseRequest` ranks or `BehaviorMatrix` — a roster bundle can describe the *result* of scheduling (classes, enrollments) but not the *demand* that drove scheduling. The reader returns a roster-only Dataset with `requested_courses=[]` for every student. Lesson: when wrapping a more-permissive external format, document explicitly which fields **don't round-trip** — silent omission is a future-debugging trap.

- **New skill profiles inferred from this pass**:
  - **`environment-resilience-engineer`** — diagnoses package/runtime incompatibilities fast: pins versions, isolates wheels, builds smoke tests for native deps. Distinct from `data-engineer` because the work is below application code, in the OS/runtime/wheel layer.
  - **`regression-test-curator`** — owns the discipline of **what to snapshot, what to tolerate, and what to opt-out by default**. Combines knowing the difference between "noise" and "regression" with knowing how to mark slow tests so a fast feedback loop survives. Folds into `solver-qa-engineer` for small teams.
  - **`interop-format-engineer`** — owns OneRoster, PowerSchool CSV, and similar mappings. Knows what each format DOES and DOESN'T carry, documents non-round-trip fields, writes both writer + roster-only reader (asymmetric is the norm). Folds into `powerschool-integration` for small teams.

- **2026-04-26 (autonomous overnight: full real-HS + synthetic MS pass)**:
  - **Real-school cohorts force a constraint that synthetic doesn't.** With three real Columbus teachers carrying 7 academic sections each, the default `max_consecutive_classes=4` is provably infeasible: with 5 blocks/day and 8 schemes, a teacher using 7 distinct schemes occupies one of the 5 days fully (pigeonhole). Auto-relaxing to 5 when any teacher's load ≥ 7 keeps default tight for synthetic data while accommodating real loads. Lesson: **structural-feasibility math is worth doing before "tuning" a constraint** — sometimes the constraint is *impossible*, not just "tight".
  - **Backward-compat pluralization works.** Changing `grade: int = 12` to `grade: int | list[int] = 12` in `build_dataset_from_columbus`, plus an internal `grades = [grade] if isinstance(grade, int) else list(grade)` line, kept every existing caller working while enabling multi-grade. CLI accepts `12`, `9,10,11,12`, and `all-hs`. Lesson: when extending a parameter from singular to plural, accept both at the API boundary and normalize internally — DO NOT introduce a parallel `grades` parameter.
  - **Cohort feasibility is its own constraint class — and it's tricky.** Attempted a Hall-matching constraint in `master_solver`: for each grade cohort, force a 1-to-1 matching of cohort-required courses → distinct schemes. Mathematically correct, fixed synthetic MS at small scales. **But broke `tiny_dataset` and other HS tests** — the constraint interacts in non-obvious ways with multi-worker non-determinism and per-scheme balance. **Reverted in the same session.** Documented the attempt in a memory file so future agents don't reattempt without broader testing. Lesson: **any solver constraint that "fixes one fixture" must be regression-tested against ALL existing fixtures before shipping**. The cohort issue is real but needs a more careful encoding (probably a per-pair "schemes-must-not-be-identical-singletons" instead of full Hall's).
  - **Synthetic-MS works at scale, fails at toy size.** `make_full_ms_dataset(n_per_grade=200)` solves end-to-end with all KPIs hit; same code at `n_per_grade<200` returns `INFEASIBLE` from student solver because too few sections per cohort-required course mean master can cluster two of them in the same scheme. The PoC ships with the documented scale floor. Lesson: synthetic data fixtures should explicitly state their working range; "works at any N" is rarely true.
  - **Path detection for test fixtures is cheap insurance.** Existing `test_ps_ingest.py` skipped its real-data tests because the path was hardcoded to a Linux Downloads dir. Added a `_find_first(...)` that tries multiple locations (Linux original + `reference/` mirror) — now the same tests run on both the original dev machine and any handoff package. Lesson: `@pytest.mark.skipif(not file.exists(), ...)` should always check more than one plausible location.

- **New skill profile inferred**: **`cohort-feasibility-engineer`** — owns the matching/Hall's-condition class of constraints that emerge specifically when "every student in cohort C must take this same set of K courses." Distinct from `optimization-engineer` because the work is in *constraint discovery* (figuring out which constraint class is missing) rather than tuning. Distinct from `scheduling-modeler` because it requires recognizing the constraint pattern from the symptom (master OPTIMAL, student INFEASIBLE in 0.0s) rather than from the spec.

- **Anti-pattern documented**: **silent meta-documentation drift.** During an autonomous overnight session that produced ~2000 lines of code and 3 new milestones, this skills log was not updated until the user asked. Future agent systems should have an end-of-session hook that explicitly prompts: "did you update the living docs?" — `MAINTENANCE_GUIDE.md`, `PRODUCTION_GAPS.md`, and `scheduler_skills_log.md` were all out of date until the user raised it. **The cost of silence here is that the next agent or human walks in without the lessons.**

- **2026-04-26 (after client deliverable packaging + verification pass)**:
  - **Bilingual deliverables for Latin-American clients are not optional.** Columbus IT receives Spanish-first; the README in the upload bundle ships Spanish primary (`README.md`) and English secondary (`README_en.md`). Lesson: when packaging for a non-English-primary client, the language of the deliverable is part of the deliverable, not a translation chore at the end.
  - **Verification independent of the solver is what earns trust.** When the user asked "how do I know you're not hallucinating," the answer wasn't "I ran tests" but rather four independent cross-checks executed live: (1) row counts in PS exports match solver-claimed counts, (2) 100% of student names in the output appear in the input xlsx (no inventions), (3) random-sample audit shows requested rank-1 courses === assigned courses with no extras, (4) time-conflict check by reading the CSVs without the solver. Lesson: the existence of `tests/check_invariants.py` (an *independent* invariant checker that consumes only the exports) proved decisive — it ran in <2 seconds and produced exactly the failure I had reported (section balance 4 vs target 3) and nothing else. **An independent verifier is the difference between "trust me" and "check yourself".**
  - **The existing solver uses heuristics for "required" classification that don't match real Columbus.** `is_required_flag = "required" in name_lower or any(name_lower.endswith(str(g)) for g in grades)` flags "English 9" as required for grade 9 — works most of the time, but masks the deeper question of WHO actually requires this course (every grade-9 student? the school? prerequisite-driven?). Lesson: real-school flags should come from a **per-school config table**, not a name-substring heuristic. Filed for a future profile pass.

- **New skill profiles inferred from packaging + verification**:
  - **`client-deliverable-packager`** — bundles solver outputs into client-uploadable formats with bilingual documentation, deployment instructions, and explicit unknowns ("verify SchoolID is number not name", "test in sandbox first"). Distinct from `powerschool-integration` because the focus is on *the package*, not the format. Folds into `tech-writer` + `powerschool-integration` for small teams.
  - **`independent-verifier`** — operates without trusting the producer. Runs cross-checks between input and output (do all output names appear in input?), random-sample audits (3 students chosen by seed, check their pedidos vs asignaciones), and constraint replays (re-derive time conflicts from CSVs without invoking the solver). Distinct from `solver-qa-engineer` because the verifier never imports the solver code — it only consumes artifacts. Critical for client-facing deliverables.

- **2026-04-26 (after bundle-hardening pass post-handoff)**:
  - **The independent verifier earned its keep on day 2.** `verify_bundle.py` (a script that consumes only the export CSVs and re-derives invariants from scratch — no solver imports) caught a master-solver bug that **all 102 fast pytest tests missed**: 21 advisory sections collapsed into one room because HC2 only iterated academic schemes 1..8, not ADVISORY. The pytest tests for room conflicts explicitly skipped advisory (`if m.scheme != "ADVISORY"`) — leaving the bug invisible to the solver-level test layer. Lesson: **independent verifiers find bugs the solver-level tests can't, because they consume artifacts not internal state and re-derive invariants from a different angle.** This pattern earned its place in `solver-qa-engineer` / `independent-verifier` profiles (already in skills log).
  - **Solver bug fixes shift the OPTIMAL solution and can break edge-of-feasibility fixtures.** Adding HC2b (AllDifferent on advisory rooms) was a strict subset of the previous feasible space — but on `tiny_dataset` (n=100 seed=7, designed to be the smallest reliably-feasible fixture) it shifted master to a different OPTIMAL that happened to leave students INFEASIBLE. Mitigation: bump fixture to n=120. Lesson: **fixtures designed at the edge of feasibility are fragile to legitimate solver improvements; size them with margin.** The handoff doc had warned about this; HC2b just made the warning concrete.
  - **Client bundles for handoff to a downstream agent need an explicit JSON report contract.** The Columbus-side agent runs `verify_bundle.py`, gets a structured report, and can act on it programmatically. The `03_AGENT_TEST_INSTRUCTIONS.md` documents the expected output JSON format so the recipient agent doesn't have to reverse-engineer "did this pass". Lesson: when the deliverable is consumed by an agent, design the test contract as if it were an API.
  - **Schedule-only bundles must NOT contain governance/AI/strategic questions.** The first pass of `01_PREGUNTAS_PARA_COLUMBUS.md` mixed schedule-import questions (PS field formats) with governance questions (RBAC, Habeas Data, AI assistant). Hector flagged this as scope creep into the client deliverable. Moved governance/scope questions to `docs/internal_pending_decisions.md` (NOT in the bundle). Lesson: **client bundles for school IT teams are NOT project-management questionnaires; they answer "how do I import this and what should I verify".** Strategic questions belong in internal docs only.

- **New skill profile observation**: the **`independent-verifier`** profile (already inferred) is now load-bearing. Without it, the advisory-room bug would have shipped to Columbus and been caught only when a coordinator looked at the schedule visually. The verifier ran in <2 seconds and gave a precise, reproducible failure signature.

- **2026-04-26 (continuation session — hardening pass while waiting on Columbus agent)**:
  - **Slow-regression test golden snapshots are CPU-affinity-sensitive even when the solver code is unchanged.** Verified by hash that `master_solver.py`, `student_solver.py`, `scenarios.py`, `sample_data.py` had `mtime == golden_capture_time`. Pure tolerance/calibration drift: two consecutive runs of the slow test on the same machine showed different KPI shapes — second run had two scenarios flip FEASIBLE→INFEASIBLE entirely (`cap_27`, `tight_balance`). The fast suite (larger budgets) was rock-solid 106/106 across both runs. **Lesson: tight-budget tolerance bands need CPU-load awareness, not just ortools-version awareness.** Currently `compare_to_golden` encodes a fixed ±3pt tolerance; on a contention-heavy host it's not enough. Next iteration could either (a) widen the band to ±5pt, (b) re-run the failing scenarios up to 3× before declaring failure, or (c) move the slow test out of "regression" framing into "noise indicator" framing. Left this as a `QUESTIONS_FOR_HECTOR` item — it's a calibration policy decision, not an engineering one.
  - **Edge-of-feasibility fixtures + tightened constraints = Hypothesis catches drift the next day.** The pre-existing `test_property_solver_output_invariants` started failing on seed=1, n=100 with balance=4 (target ≤3). NOT my new HC2b test — a pre-existing Hypothesis property. Source: HC2b (added yesterday) shifted the master OPTIMAL solution shape, and at this specific seed the new shape produces a feasible-but-borderline student solve. Standalone re-runs of the same test pass (different Hypothesis random search trajectory). This isn't a "broken" failure — it's a "Hypothesis is doing its job" failure, surfacing that the property "balance ≤ 3 always" was overly strong post-HC2b. Possible fix: weaken the property to "balance ≤ 3 in single-pass with student_time ≥ 60s" (current test uses 25s).
  - **CLI surface should match what's reachable from Python.** Added `generate-sample-ms` subcommand because `make_full_ms_dataset` was only reachable via Python import — operationally awkward when the test/demo path is CLI-first. Pattern: every public-facing data generator should have a CLI entry point AND must surface its working-scale floor in the CLI help text and stderr output (see the n_per_grade<200 warning).
  - **README test-tier documentation is critical for cold starts.** Future agents arriving without context need to know: fast suite passes by default, slow regression is opt-in, Hypothesis is opt-in. Without explicit docs, a new agent runs `pytest tests/` (full default), gets surprised by Hypothesis flakiness, and either masks tests or wastes hours on what turns out to be calibration drift.
  - **Property tests are a force multiplier when added on top of fixture-only regression.** Added the property formulation of HC2b ("for any feasible dataset, all advisory sections have distinct rooms") — total addition: 22 lines of test code. The fixture test was a single-point check; the property test scans the seed space. This is the right shape for any solver constraint that must hold universally.
  - **WHAT_TO_REPORT_BACK.md is the right pattern for autonomous agent work.** When the user asks "what did you do while I was away," a contract-driven reporting format (4 mandatory files: SESSION_LOG, CHANGES_TO_CODE, COLUMBUS_AGENT_REPORT, QUESTIONS_FOR_HECTOR) means the agent doesn't reinvent the report format and the user knows exactly what to scan. Pattern proven again here.

- **2026-04-26 (continuation, Phase 2 — after Columbus client responses)**:
  - **Domain terminology overlap is real and shows up in unexpected places.** I numbered open questions `Q1-Q9`. Hector flagged that "Q" in this domain means *Quarter* (Q1-Q4 = 4 quarters at Columbus, 2 quarters = 1 semester). My label collided with an authoritative term in the school calendar vocabulary. **Lesson: when picking issue/question prefixes, scan the domain glossary first — Q, P (period), S (section/semester), G (grade), T (term) are all overloaded in school scheduling.** Renamed to `Decisión 1-9` in this codebase. The client bundle uses `A1-A9` and `B1-B6` (round letters) which are safer in this domain.
  - **A "tunable" parameter can stop being tunable when paired with a structural fix.** Decisión 2 was supposed to be a calibration tweak: bump `student_time` from 25s to 60s in a Hypothesis property test that started failing post-HC2b. Result: 60s failed at seed=1 with the SAME `balance=4 on GOV` as 25s did. Bumped to 120s — same failure. Diagnosis: post-HC2b shifted master OPTIMAL into a region where seed=1 + n=100 is structurally stuck at balance=4 regardless of time budget. **Lesson: when a property starts failing after a "strict subset" solver fix (HC2b is a hard constraint *adding* to the feasible space restriction), don't assume the property still holds — sometimes the previous space allowed for a balance=3 solution that no longer exists.** Property may need to weaken; not every failure is a calibration issue. The "tightening fix can break a property" interaction is a CP-SAT / property-test specific failure mode worth codifying.
  - **TermID granularity is its own modeling decision and it matters at the export boundary.** v2 §10 and the v2 PowerSchool requirements treat "TermID" as if it's a single value per dataset. But Columbus has Q1-Q4 quarters at-the-year + 2 semesters + 1 year-long. A single `TermID=3600` in the export would mean "all sections in this term" — incorrect for a mix of year-long, semester, and quarter courses. **Lesson: term granularity needs a per-`Course.term` mapping table, not a single config field.** Currently the model has `Course.term: Term enum` but the exporter ignores it. Filed as Decisión 10 — pending Hector's confirmation with client.
  - **"Indicator only, not gate" is a useful CI/test policy when multi-worker non-determinism is in play.** Hector resolved Decisión 1 as "accept the slow regression test as an indicator, don't gate releases on it." Pattern: tests that depend on multi-worker convergence within tight time budgets ARE worth keeping (they catch real solver regressions when they happen) but should not block release because their false-positive rate exceeds their signal. **Codify: pyproject.toml `-m "not slow"` default + README note "indicator only, not gate".** Useful template for future projects with non-deterministic solvers.
  - **Phase-2 PS-format bug fixes were higher-value-than-expected.** SchoolID, Period/Expression, TermID — three small format corrections from the client response replaced demonstrably-wrong defaults with confirmed real values. Total code change: ~80 lines + 30 lines tests. None of these required solver changes. The bundle (`v2`) was deliberately NOT regenerated — that's the explicit "Hector decision" gate (regenerating changes the SHA Columbus is testing). **Lesson: code change ≠ deliverable change; keep them as separate decision points especially when the deliverable is being tested by a downstream agent.**

- **New skill profile observation (refinement of `interop-format-engineer`)**:
  - The `interop-format-engineer` profile must include knowledge of **TermID granularity semantics** in PowerSchool and similar SIS systems. A "term" in PS can mean year, semester, quarter, or arbitrary date range — and PS expects different IDs per granularity. The exporter must read `Course.term` and pick the right TermID per section. Not just "stuff a single TermID in the column."

- **2026-04-28 (after cliente feedback round + HC4 implementation)**:
  - **El cliente NO valida con un agente neutral; valida con su propio agente que tiene una aplicación de validación.** Cuando ese agente reporta problemas, hay que filtrarlos: algunos son bugs reales del solver, otros son mismatch de formato/nombre, otros son confusiones del operador. En esta ronda 2 de 4 reportes resultaron ser falsas alarmas (Julián tenía cursos pero bajo formato `Zuniga, Julian`; Tecnología existía pero la dictaba otro profesor). **Lección:** no arrancar a refactorear código a la primera mención del cliente; verificar primero contra los exports reales con `grep -i`.
  - **Documentos de "reglas" del cliente son specs de constraints encubiertos.** El doc `rfi_Reglas_Horarios_HS_*.md` (notas de Gemini de la reunión 2026-04-22) contenía reglas que no estaban en v2 spec ni en el handoff: "salón es por profesor", "pares/tríos para coplanificación", "dos cursos diferentes que se dictan al mismo tiempo en el mismo salón porque son del mismo área". Cada bullet de ese tipo de doc es un constraint potencial. **Lección:** las notas de reuniones del cliente son spec input — leerlas antes de programar nuevas restricciones.
  - **HC4 (home-room) fue trivial de encodear cuando lo entendí.** Restringir el dominio de `section_room[s]` a `[home_room_idx]` cuando el teacher tiene `home_room_id` set. 8 líneas. Lo difícil NO fue la encoding sino las heurísticas de cuándo aplicarlo: (a) skip "New X Teacher" placeholders (rotan); (b) skip multi-room teachers legítimos (Sindy aparece en 2 salones por enseñar 2 cursos distintos); (c) shared rooms son OK si combined sections ≤ schemes (HC2 ya cubre). **Lección:** las constraints "obvias" del dominio educativo tienen excepciones que no están en el doc; descubrirlas viendo la data real, no asumiendo.
  - **Auto-relax silencioso es deuda técnica.** El previo auto-relax de `max_consecutive_classes=4→5` enmascaraba un conflicto que el cliente quería ver. Reemplazado por WARNING-to-stderr explícito que nombra a los teachers offending y lista opciones de mitigación. Mejor: falla loud, dile a quien decide. **Lección:** un auto-relax silencioso para "destrabar" el solver es engañoso; mejor preservar la default y delegar la decisión.
  - **El trade-off de HC4 es medible y aceptable.** Pinnear 39/43 profesores a 1 salón cada uno bajó electives 98.7% → 92.7% (-6pt) y subió unmet rank-1 de 38 a 214. Pero todos los 6 KPIs siguen sobre target. **Lección:** restricciones nuevas casi siempre tienen un costo en KPIs blandos; medirlo y reportarlo, no esconderlo.
  - **Verifier independiente NO captura mismatches de cosmetic naming.** El cliente reportó "Julián Zúñiga sin cursos" pero realmente Julián tiene cursos — solo está bajo otro formato de nombre. Si el verifier hubiera chequeado "every output teacher_name appears recognizable in input data" habría flagged. **Lección:** agregar al verifier un check de cross-format-consistency en nombres antes de que el cliente confunda.

- **New skill profile observation**: el `cohort-feasibility-engineer` tiene un primo necesario: **`domain-rule-archaeologist`** — el agente que lee notas de meeting con cliente y extrae las constraints implícitas. En esta sesión el doc de Gemini contenía 7+ reglas no formalizadas en specs previos. Sin alguien que las extraiga, HC4 no se habría descubierto.

- **Lessons codified into reusable agent guidance (cumulative through 2026-04-26)**:
  5. **Smoke-test the runtime before the model.** A 2-variable LP solve check catches broken wheels; skipping it cost 4 hours.
  6. **All "at least N" constraints must be bounded by `min(N, |X|)`.** Otherwise they become structurally infeasible at scale.
  7. **Tolerances live in code, not in reviewers' heads.** Multi-worker CP-SAT is non-bit-deterministic; encode the acceptable drift in `compare_to_golden` so the regression policy is reviewable.
  8. **Pluralize parameters at the boundary, normalize inside.** Don't introduce parallel singular+plural params.
  9. **A solver constraint that fixes one fixture must regress-test against ALL fixtures.** The cohort matching attempt fixed MS, broke HS, was reverted. Lesson preserved.
  10. **Independent verifiers consume artifacts, never the solver.** They are the difference between "I claim it works" and "you can check".
  11. **Update living docs as part of every milestone, not at the end.** Cost of skipping: the next agent walks in without your lessons. Real failure mode observed in this session.
  12. **Synthetic data fixtures must declare their working scale range.** "Works at any N" is rarely true. Document the floor.
  13. **Independent verifiers belong in client bundles when handoff is to a downstream agent.** The verifier consumes only artifacts, runs in seconds, and gives the receiving agent a structured report contract. Without it, the receiving agent has to trust the producer.
  14. **Edge-of-feasibility fixtures break on legitimate solver improvements.** Size test fixtures with margin so a 1-bit constraint addition doesn't push them over the edge. If they were chosen to be "the smallest possible," they will fail when constraints tighten.
  15. **Client deliverables ≠ internal project tracking.** Governance, AI features, multi-tenant scope, RBAC, and other strategic questions don't belong in the client schedule package. Keep schedule import + scheduling rules + verification steps; move everything else to internal docs.
