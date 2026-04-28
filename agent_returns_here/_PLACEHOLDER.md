# Drop your outputs here

The agent that picks up this handoff should drop ALL outputs into this directory.

**Required files** (see `../WHAT_TO_REPORT_BACK.md` for details):

- `SESSION_LOG.md` — chronological log of work done
- `CHANGES_TO_CODE.md` — every code change with summary + test results
- `COLUMBUS_AGENT_REPORT.md` — what the Columbus-side agent reported back (or "no response"); also Hector's relays of client answers to Decisiones 1-10
- `QUESTIONS_FOR_HECTOR.md` — pending decisions for Hector; carry forward unresolved items from `previous_session_outputs/QUESTIONS_FOR_HECTOR.md` if still open

**Optional files** (only if relevant):

- `KPI_DIFF.md` — if KPIs changed since the previous session's snapshot
- `DEMO_PREP.md` — if work was done on demo preparation
- `screenshots/` — visual fallback for the demo
- `bundle_v3_release_notes.md` — if a v3 bundle was generated (only after Decisiones 9 + 10 are resolved)

If nothing changed during the agent's session, leave a single `SESSION_LOG.md` with the entry "no work performed; waited for X / Y" and the bundle SHA256 to confirm integrity.

---

## ⚠️ FIRST THING TO DO

Before doing anything else, run:

```bash
# 1. Verify bundle integrity
cd /Users/hector/Projects/handoff_2026-04-26_continuation
shasum -a 256 bundle_for_columbus/columbus_2026-2027_bundle_v2.zip
# Expected: 5a2932b8a9b7f0371b488c012296073549b000976d93ade08b4c65432ab46a89

# 2. Set up env — USE PYTHON 3.12 EXPLICITLY (see START_HERE.md footguns)
cd scheduler
python3.12 -m venv .venv          # NOT python3, NOT python — see START_HERE
.venv/bin/pip install -r requirements.txt

# 3. Smoke-test the solver runtime BEFORE running the test suite
.venv/bin/python -c "
from ortools.sat.python import cp_model
m = cp_model.CpModel()
x = m.NewIntVar(0, 10, 'x'); y = m.NewIntVar(0, 10, 'y')
m.Add(x + y == 5); m.Maximize(x)
s = cp_model.CpSolver(); s.parameters.max_time_in_seconds = 5
print(f'CP-SAT smoke: {s.StatusName(s.Solve(m))}')
"
# Expected: CP-SAT smoke: OPTIMAL
# If this hangs >5s or returns MODEL_INVALID → ortools wheel is broken; STOP.

# 4. Run the fast suite to confirm baseline
.venv/bin/python -m pytest tests/ --ignore=tests/test_hypothesis.py
# Expected: 106 passed, 1 deselected
```

If any of these fail before you've changed anything, STOP and document it in `SESSION_LOG.md` — don't try to fix it without context. The previous session left this in working state.

---

This file is a placeholder. Delete it after dropping your outputs.
