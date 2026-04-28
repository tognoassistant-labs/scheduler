# Development Proposal — Columbus Scheduling Engine

**Version:** 1.0
**Date:** 2026-04-25
**Source requirements:** `/home/hector/Documents/powerschool_requirements_v2.md`
**Working prototype:** `/home/hector/scheduler/` (Track A — runs end-to-end)
**Skills inventory:** `/home/hector/Documents/scheduler_skills_log.md`

---

## 1. Executive summary

We propose a **two-track delivery** for the Columbus scheduling engine:

| Track | Goal | Status | Effort |
|---|---|---|---|
| **A. May 1 Demo** | Prove end-to-end feasibility on synthetic Grade-12 data with real solver and PS-compatible exports | **Done** (working prototype) | Already invested |
| **B. Production rollout** | Real Columbus data, admin UI, PS sandbox roundtrip, multi-school | Proposed | 14–18 weeks, ~5–6 FTE |

The Track A prototype demonstrates that the core technical risk (constraint satisfaction at Columbus's complexity) is **resolved**. What remains is engineering execution — UI, real-data integration, ops, compliance — none of which carry combinatorial uncertainty.

---

## 2. What's already proven (Track A)

The working prototype at `/home/hector/scheduler/` solves a 130-student × 62-section Grade-12 instance against the v2 §4.1 rotation (5 days × 5 blocks × 8 schemes + Advisory at Day E Block 3) and:

- Hits **100% fully-scheduled** and **100% required-course fulfillment**
- Hits **93% first-choice elective** rate (target ≥80%)
- Generates **zero time conflicts**, **zero teacher/room double-bookings**, **zero capacity violations**
- Locks Advisory at Day E Block 3, enforces lab-course-in-lab-room, max-4-consecutive-classes per teacher, separation/restricted-teacher pairs
- Exports PowerSchool-compatible CSVs (sections, enrollments, master schedule) with documented field mapping
- Master solve in ~0.5s, student solve in ~2 minutes

**Key insight validated empirically:** OR-Tools CP-SAT handles the problem at this scale comfortably. Solution *quality* (not feasibility) is the tuning surface — and the multi-objective trade-off between electives, balance, teacher load, and grouping is now visible and quantifiable.

---

## 3. Recommended approach — Track B (production)

### 3.1 Architecture decisions (locking)

| Decision | Recommendation | Why |
|---|---|---|
| **Engine language** | Python 3.12 | Already proven; faster iteration with AI-assisted dev (v2 §12); OR-Tools' best-documented binding |
| **Solver** | OR-Tools CP-SAT, two-stage | Master then student; mirrors Columbus's existing process |
| **PowerSchool integration** | CSV first (Phase 1), API later (Phase 2) | Lower risk; sandbox-validates before any prod write |
| **Constraint config** | Stored as data (JSON in Postgres), not code | Allows scheduling coordinator to add rules without dev cycle (v2 §3.1 parametrization) |
| **AI assistant** | Anthropic Claude API, advisory-only, reads solver traces (never invents) | Avoids hallucination; meets v2 §6.3 / §13 explainability with safety |
| **Data store** | Postgres + CSV import/export | DB authoritative for working data; PS authoritative for published schedule |
| **Frontend** | Next.js + Shadcn/Tailwind | Standard admin-dashboard stack; matches v2 §14.2 |
| **Compliance** | FERPA-aligned + Colombian Habeas Data (Ley 1581) | Both apply; PII redaction before any LLM call |

### 3.2 Phased plan

```
Phase 0 — Discovery (2 weeks)
  ├─ PowerSchool data dictionary + sandbox access
  ├─ Real Columbus HS dataset (anonymized) for Grade 12
  ├─ Behavioral matrix format documented
  ├─ Hard vs soft constraint workshop with scheduling coordinator
  └─ Exit: signed-off scope memo, real data validates at ≥90% readiness

Phase 1 — Real-data foundation (3 weeks)
  ├─ Replace sample_data.py with real PS CSV ingester
  ├─ Schema migrations + Postgres persistence
  ├─ ID reconciliation across PS exports (per the messy real CSVs)
  └─ Exit: full Grade-12 cohort solves end-to-end on real data

Phase 2 — Solver hardening (3 weeks)
  ├─ Lex-min objective ordering (electives → balance → preferences)
  ├─ Co-planning windows for teachers (v2 §6.2)
  ├─ Multi-term support (semester/quarter/year)
  ├─ Locked / pre-assigned sections
  ├─ Symmetry breaking + warm-start from prior year
  └─ Exit: 5-min OPTIMAL on 520-student HS data; section balance ≤3 dev

Phase 3 — Admin dashboard (5 weeks)
  ├─ Next.js + Shadcn UI
  ├─ Schedule grid + section detail + override panel
  ├─ Conflict review with one-click fixes
  ├─ Scenario clone-and-tweak (v2 §10)
  ├─ RBAC (principal / counselor / dept chair / sysadmin)
  └─ Exit: coordinator runs full HS schedule end-to-end without CLI

Phase 4 — PowerSchool roundtrip (3 weeks)
  ├─ Sandbox tenant integration
  ├─ Field mapping verified per Columbus PS instance
  ├─ PS API client (Phase 2 integration)
  └─ Exit: zero blocking errors on sandbox import; signed-off mapping

Phase 5 — Middle School expansion (2 weeks)
  ├─ MS rotation (per v2 §4.2)
  ├─ Grade 6 vs 7-8 split logic
  └─ Exit: MS pilot solves cleanly

Phase 6 — AI assistant layer (4 weeks, parallelizable with Phase 4-5)
  ├─ Solver-trace store + structured prompt rendering
  ├─ NL Q&A over current schedule
  ├─ "Why was X assigned Y?" with grounded explanations
  ├─ What-if scenario tool (LLM calls solver)
  ├─ PII redaction wrapper
  └─ Exit: 5 canonical queries pass eval set; zero hallucinated assignments

Phase 7 — Pilot & launch (3 weeks)
  ├─ Full HS + MS production run (2026-2027 year)
  ├─ A/B comparison vs manual schedule
  ├─ Admin training + runbooks
  └─ Exit: schedule pushed to PS prod with admin sign-off
```

**Total:** 14–18 weeks (some phases parallelizable). Elementary School (v2 §4.2 — explicitly deferred) adds 3–4 weeks in a follow-on.

### 3.3 Team / agent profiles needed

From the skills log (`/home/hector/Documents/scheduler_skills_log.md`):

| Role | Phases | Why |
|---|---|---|
| `scheduling-modeler` | 0–2, 5 | Owns the formal CP-SAT model |
| `optimization-engineer` | 2, 5 | Solver perf, lex-min, warm-start |
| `data-engineer` | 0–1 | Real PS ingest, schema, validation |
| `powerschool-integration` | 1, 4 | Field mapping, sandbox roundtrip |
| `backend-engineer` | 1, 3, 6 | Service layer, queue, RBAC |
| `admin-ui-engineer` | 3 | Dashboard, override UX |
| `ai-assistant-engineer` | 6 | Claude API, retrieval, traces |
| `solver-qa` | 2, 4, 7 | Property tests, sandbox roundtrip |
| `security-compliance` | 1, 6, 7 | FERPA + Habeas Data |
| `school-scheduling-sme` | 0, 3, 7 | Domain validation, training |

For an **AI agent team** delivery (rather than human team), the same profiles map; the skills log is structured to be reused as agent specs for the next scheduler project.

---

## 4. Decisions still open

These four block Phase 0 startup:

1. **What does "May 1" really mean?** Demo only, or hard production date? The prototype answers the demo. Production by May 1 is not feasible.
2. **Pilot scope confirmation** — Grade 12 only, or all HS? Recommend Grade 12 only for Phase 0–2, expand to all HS in Phase 3.
3. **Stack approval** — Python (recommended) vs Java (v2 listed first). The prototype is Python; switching now resets ~2 weeks.
4. **Data access** — sanitized Grade-12 dataset + PS sandbox credentials available for Phase 0?

Two non-blocking but desirable:

5. PS instance specifics (term IDs, Period field semantics, Expression format)
6. Exact format of the behavioral matrix file (separation/grouping codes)

---

## 5. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Real PS data is dirtier than sample (ID format drift, missing fields) | High | Medium | Phase 1 readiness score gates the solver; data cleanup is a discrete deliverable |
| Constraint discovery never ends (new rules surface during pilot) | Medium | Medium | Constraints-as-data + a "constraint owner" role on the school side |
| Solver intractability at full HS (520 students) | Low | High | Two-stage solve; warm-start; time-budgeted; prototype already proves Grade 12 in 2 min |
| PS field mapping surprises | Medium | Medium | Sandbox tenant from Phase 0; field-by-field roundtrip test before Phase 4 ends |
| Compliance gap (FERPA / Habeas Data) | Low | High | Compliance reviewer engaged from Phase 1; PII redaction before LLM calls |
| Scope creep from English RFP wishlist | High | Medium | Track every English requirement to a phase or "deferred"; sign-off matrix |
| AI assistant hallucination | Medium | High | Advisory-only; solver-trace-grounded; never autonomous writes |

---

## 6. What changes if we DON'T do Track B

If we ship only the Track A prototype:
- Useful as **proof of concept** — can be shown to school leadership to validate the approach
- Cannot operate Columbus's real schedule (synthetic data, no UI, no PS roundtrip)
- Still answers the v2 §15 "key insight": *this is solvable; the AI is the thin layer*

If the May 1 deliverable is a **proposal + working demo**, we have it. If it's a **production rollout**, we need Track B.

---

## 7. Recommended next actions (in order)

1. **Decide on "May 1" interpretation** — proposal, demo, or production date.
2. **If demo**: package the prototype + this proposal + record a 5-minute screencast of the end-to-end run. No new code needed.
3. **If continuing**: kick off Phase 0 with PS sandbox access + real anonymized Grade-12 data + a 90-min constraint workshop with the scheduling coordinator.
4. **In parallel**: lock the four open decisions in section 4.
5. **In parallel**: align on team/agent profile assignments from the skills log.

---

## 8. Appendix — what's in the working prototype today

```
/home/hector/scheduler/
├── README.md                 — quickstart + run results
├── PRODUCTION_GAPS.md        — full gap analysis with effort estimates
├── DEVELOPMENT_PROPOSAL.md   — this document
├── requirements.txt
├── src/scheduler/
│   ├── models.py             — Pydantic schemas + default rotation
│   ├── sample_data.py        — reproducible Grade-12 generator
│   ├── io_csv.py             — round-trip-safe CSV
│   ├── validate.py           — readiness score 0..100
│   ├── master_solver.py      — Stage 1 (OR-Tools CP-SAT)
│   ├── student_solver.py     — Stage 2 (OR-Tools CP-SAT)
│   ├── reports.py            — KPI + report generation
│   ├── exporter.py           — PowerSchool-compatible CSVs
│   └── cli.py                — entry point
├── data/
│   ├── sample/               — generated CSVs (130 students, 62 sections)
│   └── exports/
│       ├── reports/          — KPI markdown + section/student CSVs
│       └── powerschool/      — PS-import CSVs + field mapping
└── tests/                    — placeholder for property/regression tests
```

Run end-to-end:
```bash
cd /home/hector/scheduler
.venv/bin/python -m src.scheduler.cli generate-sample --out data/sample
.venv/bin/python -m src.scheduler.cli solve --in data/sample --out data/exports
```

Outputs include `data/exports/reports/schedule_report.md` (KPI vs v2 §10 targets) and `data/exports/powerschool/ps_*.csv` (PS-import-ready).
