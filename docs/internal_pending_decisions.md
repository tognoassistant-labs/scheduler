# Pending decisions — internal, NOT for client bundle

Living document with the strategic / governance / scope questions that block the project but should NOT ship inside the client schedule bundle. Originally written into `01_PREGUNTAS_PARA_COLUMBUS.md` (in v2 client bundle) but moved here on 2026-04-26 because the client bundle should only contain schedule-related questions.

These questions are between the agent / Hector / Columbus leadership — not between the engine and the school's IT team that imports the schedule.

---

## Scope decisions (define next 2-14 weeks)

| # | Question | Impact |
|---|---|---|
| S1 | **What does "May 1" mean exactly?** Demo of the tool, signed proposal for Track B (production rollout), or pilot go-live? | Each answer implies a different timeline. Demo = ready now. Signed proposal = start Track B phase 0 Monday (14-18 weeks). Go-live = need PowerSchool API or accept manual import every semester. |
| S2 | **Initial pilot scope:** HS Grade 12 only, full HS (9-12), or HS + MS combined? | Current bundle includes full real HS (510 students) + synthetic MS (PoC). |
| S3 | **Is there real Middle School data for 2026-2027?** We have `rfi_MS_schedule_2024-2025.xlsx` but its structure differs from HS (no `Esquemas` tab) and is from last year. | Without real data, MS remains a synthetic PoC. Production MS requires a new ingester (~1 week). |
| S4 | **Is Elementary (ES) in scope?** v2 spec marked it "deferred until MS and HS are done". | If in scope: ~3-4 additional weeks for the different structure (homerooms, 7 blocks, K-5). |
| S5 | **Is multi-tenant relevant?** Is Columbus the only school using this, or will it be sold to others? | Today deployment is single-CLI + CSV. Multi-tenant requires Postgres + queue + RBAC + auth (~2 additional weeks). |

## Governance / operations (Track B fase 0+)

| # | Question | Why it matters |
|---|---|---|
| G1 | **Who can run the solver and view schedules?** Coordinator, principal, dept chair, sysadmin? | Defines RBAC (needed if moving to multi-tenant). |
| G2 | **What events require an audit log?** v2 §13 mentions overrides and approvals. | Defines what's stored in the DB (needed if moving to Postgres). |
| G3 | **What's the change-approval workflow?** If a coordinator wants to move a section, who signs off? | Defines UX of the lock/override panel. |
| G4 | **How is the academic-year rollover handled?** Archive last year + activate new year + copy config? | Defines data retention and annual workflow. |
| G5 | **Habeas Data (Ley 1581) compliance** — is a signed DPA / consent tracking required for student data? | If cloud-deploying with real data, this is a legal prerequisite. |
| G6 | **AI assistant layer (v2 §6.3)** — is this still a deliverable, or deferred indefinitely? | The user deferred it "until the end" earlier; confirm whether it's still on the menu. |

## Bundle delivery logistics

| # | Question |
|---|---|
| L1 | Who at Columbus receives this zip? (IT, academic coordination, principal) |
| L2 | What format do they expect to receive it in? (zip, shared folder, secure transfer) |
| L3 | Can the student data in this bundle be shared by email, or does it require a secure channel (SFTP, encrypted drive)? |
| L4 | When does Columbus need the final bundle? (date and time) |

---

**Audit trail:**

- 2026-04-26: extracted from `01_PREGUNTAS_PARA_COLUMBUS.md` (in client bundle v2) after Hector flagged that AI / governance questions don't belong in a client-facing schedule package. Client bundle now has only A (PS format), B (scheduling rules applied), and C (sandbox verification) — questions strictly tied to importing the attached schedule.

---

## Columbus client responses received 2026-04-26 (Hector forwarded)

### Section 1 — PowerSchool format (A1–A7) — ALL ANSWERED

| # | Question | Columbus answer | Action taken |
|---|---|---|---|
| A1 | SchoolID number or name? | **Number. MS=12000, HS=13000.** | Implemented `SchoolConfig.school_id` field; `ps_ingest` sets 12000/13000 by detected grade range. |
| A2 | Period / Expression format? | **`1(A)2(B)3(C)` per slot; `1(D-E)` for shared block.** | Replaced `_period_code` with `_expression(slots)` in `exporter.py`. Advisory now exports as `3(E)`. |
| A3 | TermID for 2026-2027? | **3600.** | Implemented `SchoolConfig.term_id` field; `ps_ingest` sets `"3600"` when year contains "2026-2027". |
| A4 | CourseID matches PS? | **Yes** — IDs delivered in input data are the real PS IDs. | No change needed; ingester preserves input IDs. |
| A5 | TeacherID matches PS? | **Yes.** | Same — preserved. |
| A6 | StudentID matches PS? | **Yes.** | Same — preserved. |
| A7 | RoomID matches PS? | **Yes.** | Same — preserved. |

### Section 2 — Test environment (A8–A9) — ALL ANSWERED

| # | Question | Columbus answer | Action taken |
|---|---|---|---|
| A8 | PS sandbox available? | **Yes — sandbox available.** | Updates `internal_pending_decisions` audit. Dry-run blocked only on bundle regeneration decision. |
| A9 | IT contacts? | **Juan Pablo Vallejo and Luis Botero.** | Captured. |

### Section 3 — Academic validation (NEW round B1–B6) — PARTIAL

| # | Question | Columbus answer | Status |
|---|---|---|---|
| B1 | Official list of required courses by grade? | "Will be shared as soon as possible." | **Pending input from Columbus.** |
| B2 | Grouping/separation matrix complete? | **HS: complete. MS: incomplete** — using scheme constructor proposal in docs. | HS OK; MS treated as PoC quality (already documented). |
| B3 | Max consecutive classes for teachers: 4 or 5? | **4.** | ⚠️ Conflict with current code — see decisión 5 in QUESTIONS_FOR_HECTOR. The skills-log entry from 2026-04-26 morning explains the auto-relax to 5 was added because 3 real Columbus teachers carry 7 sections each, which is provably infeasible at strict 4. Hector confirmed 4 — this needs reconciliation. |
| B4 | Advisory always fixed at E3? | **HS: yes. MS: no — no fixed blocks; only course frequency is fixed.** | ⚠️ Structural change needed for MS — see decisión 6 in QUESTIONS_FOR_HECTOR. Current bell schedule hardcodes Advisory at E3 for both. |
| B5 | Section balance ≤3 obligatory or aspirational? | "For teachers, the quantity of sections per teacher is defined beforehand based on school policies and student demand." | ⚠️ Ambiguous — possibly reinterprets "balance" as teacher-section count rather than per-course class-size balance (which is what we currently enforce). See decisión 7 in QUESTIONS_FOR_HECTOR. |
| B6 | Electives + alternates interpretation correct? | **NO — for 2026-2027 there are NO alternates.** Requests already cleaned. For HS: only PE is required; rest are electives by department/area. | ⚠️ Behavioral change for 2026-2027 — see decisión 8 in QUESTIONS_FOR_HECTOR. The ingester currently flags "Electives Alternative N" rows as rank-2; this should be disabled for 2026-2027. |
