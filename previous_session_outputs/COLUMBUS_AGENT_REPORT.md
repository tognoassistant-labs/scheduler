# Columbus client responses — 2026-04-26 (received via Hector)

**Status:** Partial response received. Hector forwarded answers to A1–A9 (PowerSchool format + test environment) and a new round B1–B6 (academic validation).

The Columbus-side agent has NOT yet run `verify_bundle.py` against the v2 bundle. The structured JSON `verifier_exit_code` report is still pending.

---

## Section 1 — PowerSchool format (A1–A7) — ALL ANSWERED

| # | Question | Answer |
|---|---|---|
| A1 | SchoolID number or name? | **Number. MS=12000, HS=13000.** |
| A2 | Period / Expression format? | **`1(A)2(B)3(C)` per slot, concatenated. `1(D-E)` for shared block.** |
| A3 | TermID for 2026-2027? | **3600.** |
| A4 | CourseID matches PS? | Yes — input data carries real PS IDs. |
| A5 | TeacherID matches PS? | Yes. |
| A6 | StudentID matches PS? | Yes. |
| A7 | RoomID matches PS? | Yes. |

## Section 2 — Test environment (A8–A9) — ALL ANSWERED

| # | Question | Answer |
|---|---|---|
| A8 | PS sandbox available? | Yes. |
| A9 | IT contact for dry-run? | Juan Pablo Vallejo and Luis Botero. |

## Section 3 — Academic validation (NEW B1–B6)

| # | Question | Answer |
|---|---|---|
| B1 | List of required courses by grade? | Will be shared ASAP — **pending**. |
| B2 | Grouping/separation matrix complete? | HS: yes. MS: incomplete (scheme constructor proposal in docs). |
| B3 | Max consecutive classes for teachers: 4 or 5? | **4.** |
| B4 | Advisory fixed at E3? | HS: yes. **MS: NO fixed blocks — only course frequency is fixed.** |
| B5 | Section balance ≤3 obligatory or aspirational? | "For teachers, the quantity of sections per teacher is defined beforehand based on school policies and student demand." (Possibly reinterpreting balance as teacher-load.) |
| B6 | Electives + alternates correct? | **NO — for 2026-2027 there are NO alternates.** Requests already cleaned. HS: only PE required; rest electives by department/area. |

## Code changes implemented in this session (autonomous, additive)

Per the bug-fix scope (PS field formats were demonstrably wrong, now corrected to client-confirmed values):

1. **`src/scheduler/models.py`** — added `SchoolConfig.school_id` and `SchoolConfig.term_id` (both optional, fall back to current behavior).
2. **`src/scheduler/exporter.py`** — replaced `_period_code(scheme)` with `_expression(slots)`. SchoolID column reads from `cfg.school_id` (falls back to `cfg.school`). TermID column reads from `cfg.term_id` (falls back to `cfg.year`). Field-mapping doc updated.
3. **`src/scheduler/ps_ingest.py`** — auto-sets `school_id=12000` for ingested MS grades, `13000` for HS. Sets `term_id="3600"` when year contains "2026-2027".
4. **`tests/test_reports_exporter.py`** — assertion updated: advisory `Period == "3(E)"` (was `"ADV"`).
5. **`tests/check_invariants.py`** — refactored to detect advisory by `CourseID == "ADV"` (was `Period == "ADV"`); added explicit HC2b advisory-rooms-distinct check; switched HC1/HC2 from `Period`-based to `Slots`-based (more direct ground truth, robust against the format change).

Test results after changes: **106 fast tests passing** (no regression). Period format verified end-to-end with a manual smoke run; all sample sections show correct `<block>(<day>)<block>(<day>)...` output.

## Decision points for Hector (4 new + the original 4)

See `QUESTIONS_FOR_HECTOR.md` for full detail. Summary of the new ones:

- **decisión 5 — `max_consecutive_classes`: client says 4, code auto-relaxes to 5 for real Columbus where 3 teachers carry 7 sections.** Conflict.
- **decisión 6 — MS Advisory not fixed at E3.** Structural change to bell schedule for MS context.
- **decisión 7 — "Section balance ≤3" semantic.** Currently enforced as per-course class-size deviation; client answer suggests it might mean teacher-section count. Need clarification.
- **decisión 8 — "No alternates for 2026-2027".** Add ingester flag to ignore "Electives Alternative N" tagging this year.

## What's still pending from Columbus

1. **`verify_bundle.py` JSON report** — not yet received. Bundle hash still matches `SHA256SUM.txt`.
2. **B1 list of required courses by grade** — Hector said "will be shared ASAP."
3. **MS grouping/separation matrix** — incomplete; using docs-proposal scheme.
4. **Sandbox dry-run** — sandbox available (A8), but waiting on bundle regeneration decision (decisión 9 in QUESTIONS) before pointing it at sandbox.

## Bundle integrity

```
$ shasum -a 256 bundle_for_columbus/columbus_2026-2027_bundle_v2.zip
5a2932b8a9b7f0371b488c012296073549b000976d93ade08b4c65432ab46a89  columbus_2026-2027_bundle_v2.zip
```

Matches `SHA256SUM.txt`. Bundle NOT regenerated. The code changes above mean a freshly-generated v3 bundle would have different SchoolID/Period/TermID values from v2 — but I did not re-zip the bundle.
