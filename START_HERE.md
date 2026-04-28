# START HERE — Columbus Scheduling Engine

**Repo:** https://github.com/tognoassistant-labs/scheduler
**Last updated:** 2026-04-28
**Status:** May 1 MVP demo target in **3 days**. **Bundle v3 delivered** (HC4 home-room fix + PowerSchool format fixes confirmed by Columbus IT 2026-04-26). v2 retained for comparison. Cliente confirmó: "estuvo muy acertado, lo más importante era lo de los salones" — fix aplicado en v3.

> **De ahora en adelante**, todo el desarrollo se versiona en este repo. Workflow:
> 1. Clone → cambios → tests → commit → push → PR (si quieres) → merge.
> 2. Bundles van en `bundle_for_columbus/` con SHA256 actualizado en `SHA256SUM.txt`.
> 3. Notas de sesión en `agent_returns_here/` cuando un agente termina su trabajo.
> 4. NO commitear `.venv/` ni `__pycache__/` (ya están en `.gitignore`).
> 5. Tests must pass: `pytest tests/ --ignore=tests/test_hypothesis.py` → 109 expected.

---

## ⚠️ READ THIS FIRST — CRITICAL ENVIRONMENT FOOTGUNS

**These will burn hours if you skip them. They are the difference between a 30-second smoke test and a 4-hour debug session.**

### 1. Use Python 3.12 explicitly. NOT 3.13, NOT 3.14.

```bash
# CORRECT — explicit version
python3.12 -m venv .venv

# WRONG — may pick whatever the system default is, including 3.14
python3 -m venv .venv      # ← bug-prone on systems where /usr/bin/python3 is newer
python -m venv .venv       # ← same problem
```

**Why:** ortools < 9.13 doesn't ship wheels for Python 3.13+ as of this session. With Python 3.14 the install will either silently pull a too-new ortools (which is broken — see #2) or fail to install ortools at all. Confirmed working: **Python 3.12.3 + ortools 9.12.4544**.

If `python3.12` isn't on the target machine: `apt install python3.12 python3.12-venv` (Linux), `brew install python@3.12` (macOS), or use pyenv. Do NOT proceed with 3.13+.

### 2. ortools is pinned `>=9.10,<9.13`. Keep the pin. DO NOT RELAX IT.

```toml
# requirements.txt (already in the project — verify it's intact)
ortools>=9.10,<9.13
```

**Why:** ortools 9.15.x is BROKEN on Apple Silicon. It returns `MODEL_INVALID` instantly on a 2-variable LP in single-worker mode AND hangs forever in multi-worker mode (default). A previous session lost ~4 hours debugging "tests are slow" before realizing the solver was wedged at 0% CPU. **Confirmed working in the pinned range:** 9.11.4210 (previous session) and 9.12.4544 (this session).

If you upgrade the pin: run a 2-variable LP smoke test FIRST, before any other work:

```bash
.venv/bin/python -c "
from ortools.sat.python import cp_model
m = cp_model.CpModel()
x = m.NewIntVar(0, 10, 'x'); y = m.NewIntVar(0, 10, 'y')
m.Add(x + y == 5); m.Maximize(x)
s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = 5
status = s.Solve(m)
print(f'CP-SAT smoke: status={s.StatusName(status)} x={s.Value(x)} y={s.Value(y)}')
"
# Expected output: CP-SAT smoke: status=OPTIMAL x=5 y=0
# If this hangs >5 seconds or returns MODEL_INVALID → ortools wheel is broken on this machine.
```

### 3. CPU time vs wall time — wedged ≠ slow

If a test or process is at 0% CPU after several minutes of wall-clock time, **it is wedged, not slow**. Don't wait — kill it and investigate.

```bash
ps -o pid,etime,time,%cpu,stat,cmd -p <PID>
# etime = wall-clock elapsed
# time  = CPU time consumed
# If time is ~0:00 while etime is 10+ minutes → wedged.
```

Most common cause: ortools wheel mismatch (point #2). Second most common: a CP-SAT model with a typo creating an infinite-domain variable.

### 4. Other gotchas

- **`pyproject.toml` has `-m "not slow"` in addopts.** That means `pytest tests/` skips the slow regression test by default. Per Hector decision 2026-04-26 (Decisión 1), the slow test is "indicator only, not gate" — its failure does NOT block release.
- **Hypothesis tests (`tests/test_hypothesis.py`) run with `pytest tests/` UNLESS you `--ignore=tests/test_hypothesis.py`.** They take ~3 min total. The fast suite (everything except Hypothesis) takes ~3.5 min on its own.
- **macOS dot-files (`._*`)** sometimes leak into rsync'd handoffs. Already cleaned in this folder; if you see them after copying elsewhere, `find . -name "._*" -delete`.

---

## Read this first, in order

1. **This file** — current state, environment footguns, and immediate next steps
2. **`previous_session_outputs/SESSION_LOG.md`** — what the previous session did (it ran twice on this same machine: morning hardening pass + afternoon Phase 2 PS-format fixes after client response)
3. **`previous_session_outputs/QUESTIONS_FOR_HECTOR.md`** — 10 open decisions (1 resolved, 1 partial, 8 open), with my recommendations for each
4. **`previous_session_outputs/CHANGES_TO_CODE.md`** — every code change made in the previous session, with test-result diff
5. **`previous_session_outputs/COLUMBUS_AGENT_REPORT.md`** — what Columbus IT confirmed (A1-A9, B1-B6) on 2026-04-26
6. **`docs/scheduler_skills_log.md`** — living skills/lessons doc; **update this with each milestone you complete**
7. **`scheduler/MAINTENANCE_GUIDE.md`** — code-level "how to make changes" guide. Read before touching solver code.
8. **`scheduler/PRODUCTION_GAPS.md`** — what's done, what's open, with effort estimates.
9. **`docs/internal_pending_decisions.md`** — strategic / governance / scope questions NOT in the client bundle. Includes the audit trail of Columbus answers.
10. **`bundle_for_columbus/columbus_2026-2027_bundle_v2.zip`** — the v2 deliverable. **DO NOT TOUCH** without explicit approval from Hector. Hash: `5a2932b8a9b7f0371b488c012296073549b000976d93ade08b4c65432ab46a89` (verify with `bundle_for_columbus/SHA256SUM.txt`).

---

## Folder layout

```
handoff_2026-04-26_continuation/
├── START_HERE.md                     ← you are here
├── WHAT_TO_REPORT_BACK.md            ← what to deliver to Hector when he returns
│
├── scheduler/                        ← THE PROJECT (source + tests + data)
│   ├── src/scheduler/                ← Python package (13 modules)
│   ├── tests/                        ← 106 fast + 1 slow + 5 Hypothesis property
│   ├── data/sample/                  ← canonical synthetic Grade-12 fixture
│   ├── README.md                     ← quickstart + tests guide (Tier 1/2/3)
│   ├── MAINTENANCE_GUIDE.md          ← changelog + recipes + footguns
│   ├── PRODUCTION_GAPS.md            ← gap inventory with effort estimates
│   ├── DEVELOPMENT_PROPOSAL.md       ← Track B 14-18 week plan
│   ├── app.py                        ← Streamlit demo UI
│   ├── pyproject.toml                ← pytest config (markers, addopts)
│   └── requirements.txt              ← pinned deps; KEEP `ortools>=9.10,<9.13`
│
├── reference/                        ← real Columbus data (rfi_ prefix)
│
├── docs/                             ← project-level docs
│   ├── powerschool_requirements_v2.md       ← THE spec
│   ├── powerschool_requirements_v1_LEGACY.md
│   ├── scheduler_skills_log.md              ← living skills inventory (UPDATE THIS!)
│   └── internal_pending_decisions.md        ← audit trail of Columbus answers
│
├── bundle_for_columbus/              ← what the user delivers to Columbus
│   ├── columbus_2026-2027_bundle_v2.zip  (intact, hash verified)
│   └── SHA256SUM.txt
│
├── previous_session_outputs/         ← what the previous Claude session left
│   ├── SESSION_LOG.md                ← chronological log (2 phases, ~5h total)
│   ├── CHANGES_TO_CODE.md            ← all source edits with test results
│   ├── COLUMBUS_AGENT_REPORT.md      ← what client confirmed
│   └── QUESTIONS_FOR_HECTOR.md       ← 10 decisiones, status per decisión
│
└── agent_returns_here/               ← when you finish work, drop your outputs here
                                          (currently empty — placeholder for you)
```

---

## State of play (end of session 2026-04-26 PM)

### What's done

- **HS real Columbus data (510 students, grades 9-12)** — solves end-to-end, **6/6 KPIs hit**.
- **MS synthetic PoC (600 students, grades 6-8)** — solves end-to-end, **6/6 KPIs hit**.
- **OneRoster v1.1 export** — included in v2 bundle.
- **Standalone verifier** (`verify_bundle.py`) — Python stdlib only, 16 invariants. Used by Columbus-side agent.
- **Tests:** 106 fast + 1 slow + 5 Hypothesis property tests.
- **HC2b advisory-rooms-distinct fix** — caught by the standalone verifier.
- **Phase 2 PS-format bug fixes (this session):**
  - `SchoolConfig.school_id` (12000 MS / 13000 HS) and `term_id` (3600 for 2026-2027) added
  - Period/Expression format changed from `P01..P08, ADV` → `1(A)2(D)4(B)` and `1(D-E)` per Columbus IT confirmation
  - Tests + invariant checker updated; **fast suite remains 106/106**
- **Hypothesis property test for HC2b** added (`test_property_advisory_rooms_distinct`).
- **CLI subcommand `generate-sample-ms`** added.
- **README test tier documentation** (fast / slow / Hypothesis) added.

### What's pending

#### Open decisiones (8 of 10 unresolved)

| # | Decisión | Status |
|---|---|---|
| 1 | Slow regression test as indicator/gate | ✅ RESUELTA — indicator only, not gate (README updated) |
| 2 | Hypothesis test budget for `test_property_solver_output_invariants` | ⚠️ PARTIAL — bumped to 60s but seed=1 still fails (structural post-HC2b, not budget). 3 follow-up options listed. |
| 3 | ortools pin granularity (range vs exact) | OPEN — recommendation: leave range until May 1 |
| 4 | Channel for Columbus agent's verifier JSON report | OPEN — recommendation: agree on `agent_returns_here/columbus_response_<date>.json` |
| 5 | `max_consecutive=4` (client) vs auto-relax to 5 (code, structural) | OPEN — recommendation: keep auto-relax, document exception clearly to coord. académica |
| 6 | MS without fixed Advisory at E3 | OPEN — recommendation: defer to Track B Phase 5 (MS expansion) |
| 7 | "Section balance ≤3" semantic (per-course size vs teacher-load) | OPEN — recommendation: ask client to clarify before changing anything |
| 8 | "No alternates for 2026-2027" — CLI flag | OPEN — recommendation: implement `--ignore-alternates` flag (~10 min) |
| 9 | Regenerate bundle v3 with corrected formats | **BLOCKED on Decisión 10** |
| 10 | TermID granularity (year vs semester vs quarter) | **PENDING client confirmation** — Hector consulting Columbus IT |

#### Pending external inputs

- **Columbus-side agent verifier JSON report** (Decisión 4): not yet received.
- **B1: Official list of required courses by grade**: client said "will be shared ASAP."
- **Decisión 10 confirmation from client**: Hector consulting on Q (Quarter) terminology and TermID granularity. Until this lands, bundle v3 cannot be safely regenerated.
- **MS grouping/separation matrix**: client confirmed incomplete; using docs proposal.

---

## Working environment

### Quick start

```bash
cd scheduler
python3.12 -m venv .venv          # ← MUST be 3.12, see footgun #1
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ --ignore=tests/test_hypothesis.py    # ~3.5 min, expect 106 passed
.venv/bin/streamlit run app.py    # demo UI on localhost:8501
```

### Test tiers (per Decisión 1 — slow is indicator only)

| Tier | Command | Duration | Status |
|---|---|---|---|
| Fast | `pytest tests/ --ignore=tests/test_hypothesis.py` | ~3.5 min | 106/106 ✓ at end of this session |
| Slow regression | `pytest -m slow` | ~2.5 min | Indicator only, not gate. Currently fails on this CPU due to multi-worker drift (golden snapshot calibration). |
| Hypothesis property | `pytest tests/test_hypothesis.py` | ~3 min | 4/5 pass; `test_property_solver_output_invariants` fails at seed=1 post-HC2b (Decisión 2). |

---

## What you should do

### Priority 1 — If Hector returns with a decisión answer (1-10)

Each decisión in `previous_session_outputs/QUESTIONS_FOR_HECTOR.md` has 2-4 numbered options and a recommendation. If Hector says "decisión N → option M", apply that option and:

1. Update `QUESTIONS_FOR_HECTOR.md` (in your `agent_returns_here/`) marking decisión N as resolved.
2. If the option requires code changes, make them, run the fast suite, document in `CHANGES_TO_CODE.md`.
3. Append to `SESSION_LOG.md`.

### Priority 2 — If the Columbus-side agent verifier report arrives

Read it. Format documented in `bundle_for_columbus/columbus_2026-2027_bundle_v2.zip → 03_AGENT_TEST_INSTRUCTIONS.md`. Expected fields:
- `verifier_exit_code` (0 = PASS, 1 = FAIL, 2 = bundle inválido)
- `schools[]` with `all_passed` and `failed_checks` per school
- `blocking_questions_unresolved` (the A1–A9 list)
- `recommendation` (free text)

If `verifier_exit_code == 0`: technically validated. Sandbox dry-run is the next external action (blocked on Decisión 10 result for the v3 bundle, not v2).

If `verifier_exit_code == 1`: investigate `failed_checks[]`. The current bundle's hash is documented; if it's the same hash, the bug is not from your changes.

### Priority 3 — If client confirms Decisión 10 (Q/TermID granularity)

If client says "TermID=3600 is the year-level term, all courses use it" → bundle v3 can be regenerated with current code.

If client says "TermID is per-quarter and there are separate IDs for semester/year" → need to extend `SchoolConfig` with a term-ID lookup table keyed on `Course.term`, update the exporter to read `Course.term` per section, and ask client for the actual ID values for each granularity.

### Priority 4 — Hardening that doesn't change the deliverable

If none of the above, low-risk additive work that doesn't touch the bundle:
- Audit `MAINTENANCE_GUIDE.md` for staleness vs the current code state
- Add unit tests for the new `_expression(slots)` function in `exporter.py`
- Add a CLI smoke-test fixture for `generate-sample-ms`
- Run the fast suite once on a fresh machine to confirm reproducibility

### Don't do without explicit ask

- Don't change `master_solver.py` constraints (especially the `max_consecutive_classes` auto-relax).
- Don't switch the stack to Java.
- Don't reattempt cohort Hall-matching (see skills log warning).
- Don't delete or rezip `bundle_for_columbus/columbus_2026-2027_bundle_v2.zip` — that's what Columbus is testing.
- Don't regenerate the slow-test golden snapshot blindly — it'd mask real solver regressions.

---

## File pointers (most relevant for the next agent)

| File | Purpose |
|---|---|
| `scheduler/src/scheduler/master_solver.py` | Master schedule CP-SAT model. HC2b at line ~158. |
| `scheduler/src/scheduler/student_solver.py` | Student assignment CP-SAT model. |
| `scheduler/src/scheduler/sample_data.py` | Synthetic data generator (HS + MS, scale param). |
| `scheduler/src/scheduler/ps_ingest.py` | Real Columbus xlsx → Dataset. Sets `school_id` 12000/13000 + `term_id="3600"` (post-Phase 2 this session). |
| `scheduler/src/scheduler/exporter.py` | PowerSchool CSV writer. **`_expression(slots)` is new** — produces `1(A)2(D)4(B)` format per Columbus IT confirmation. |
| `scheduler/src/scheduler/io_oneroster.py` | OneRoster v1.1 reader/writer. |
| `scheduler/src/scheduler/models.py` | Pydantic schemas. **`SchoolConfig.school_id` and `SchoolConfig.term_id` are new** (optional, fallback to existing strings). |
| `scheduler/data/_client_bundle_v2/verify_bundle.py` | Standalone verifier (no deps). Run `python3 verify_bundle.py` (NOT under venv — it's stdlib only). |
| `scheduler/data/_client_bundle_v2/03_AGENT_TEST_INSTRUCTIONS.md` | Runbook for Columbus-side agent. |
| `scheduler/MAINTENANCE_GUIDE.md` | Code conventions, recipes, footguns, **changelog**. |
| `scheduler/PRODUCTION_GAPS.md` | Inventory of done vs open. |
| `docs/scheduler_skills_log.md` | Living skills/lessons doc (update each milestone). |
| `docs/internal_pending_decisions.md` | Strategic + governance + Columbus answer audit trail. |
| `bundle_for_columbus/columbus_2026-2027_bundle_v2.zip` | The deliverable (intact). |

---

## When in doubt

- Hector prefers terse responses + pointed pushback when something is wrong.
- Spanish-first if speaking to him directly (he's bilingual).
- Don't refactor for fun; the prototype is small and consistent.
- **Always update `docs/scheduler_skills_log.md` with each milestone.** It's a deliverable.
- Don't add features that weren't asked for.

Good luck. The Phase 2 PS-format fixes are in the code; the bundle isn't regenerated yet because that decision (Decisión 9) is blocked on the client confirmation around Q/TermID granularity (Decisión 10). Most of what's left is execution + waiting.
