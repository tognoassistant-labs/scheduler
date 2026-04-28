# Changes to code — 2026-04-28 session (HC4 + revert auto-relax)

## Summary

Two cliente-reported bugs addressed:
- **A. "Salón es por profesor"** → new HC4 hard constraint in master solver
- **B. "Max consecutive 4, no 5"** → reverted silent auto-relax; explicit WARNING + operator decision

Two cliente-reported issues confirmed as cosmetic false alarms (no code change):
- C. Julián Zúñiga sin cursos → he has 2 sections; name mismatch only
- D. Tecnología falta → Technology 9 is in the bundle (taught by Higuita, not Julián)

## Files modified

| File | Lines | Change |
|---|---|---|
| `scheduler/src/scheduler/ps_ingest.py` | ~30 net | (1) Reverted `max_consecutive_classes` auto-relax to 5; replaced with explicit WARNING-to-stderr listing each teacher with ≥7 academic sections + mitigation options. (2) New HC4-prep block: assigns `Teacher.home_room_id` from LISTADO MAESTRO column ROOM. Skips placeholder teachers ("New X Teacher") and multi-room teachers (those with >1 distinct ROOM in LISTADO). 39/43 real Columbus teachers receive home_room; 4 float (Sindy + 3 placeholders). |
| `scheduler/src/scheduler/master_solver.py` | ~12 net | New HC4 (lines ~73-85): when `Teacher.home_room_id` is set and there's no `Section.locked_room_id`, the section's room domain is restricted to ONLY the home_room. `locked_room_id` (operator override) takes precedence over HC4. |
| `scheduler/tests/test_master_solver.py` | +47 | New `TestHomeRoom` class: `test_home_room_pins_academic_sections` (academic sections of teacher T → T.home_room_id) and `test_home_room_unset_keeps_default_behavior` (sections without home_room behave as before). |
| `scheduler/tests/test_ps_ingest.py` | +20 net | Replaced obsolete `test_full_hs_relaxes_max_consecutive_classes` with `test_full_hs_keeps_strict_max_consecutive` (asserts default=4 + WARNING captured via capsys). New `test_full_hs_assigns_home_rooms_from_listado` (asserts ≥80% teachers receive home_room from LISTADO). |

## Files NOT modified (intentionally)

- `bundle_for_columbus/columbus_2026-2027_bundle_v2.zip` — sha256 unchanged. Bundle still ships the OLD format (per agent previo's note: regen blocked by Decisión 9/10 on TermID granularity).
- `scheduler/src/scheduler/sample_data.py` — not affected.
- `scheduler/src/scheduler/student_solver.py` — not affected by HC4.
- Auto-relax revert affects ONLY ps_ingest path. Direct callers of `solve_master(ds, ...)` who set `ds.config.hard.max_consecutive_classes=5` explicitly still get the relaxed behavior.

## Test results

### Fast suite
**Run before this session:** 107 passed, 1 deselected (per previous agent's notes — count includes their additions).
**Run after this session:** in progress at write time. 3 net new tests added (TestHomeRoom × 2 + the renamed/updated max_consec test which still counts as 1, plus test_full_hs_assigns_home_rooms_from_listado = +3). Expect ~110 passed.

### Real Columbus full HS re-solve (data/columbus_full_hs_v4/)

```
WARNING: 3 teacher(s) carry ≥7 academic sections; strict max_consecutive_classes=4 may be infeasible. Offenders:
  - Arcila Fernandez, Sofia: 7 sections
  - Velez Cardona, Gloria Isabel: 7 sections
  - Martinez Cubillos, Clara Andrea: 7 sections

students=510 sections=234 home_rooms=39/43
master OPTIMAL in 1.2s, 234 assignments
students FEASIBLE in 1800.5s, placed=510, unmet=214

KPIs:
- Fully scheduled: 100%
- Required fulfillment: 100%
- First-choice electives: 92.7% (was 98.7% in v3 — cost of HC4 room pinning)
- Section balance: 3 (target ≤3) ✅
- 0 unscheduled, 0 time conflicts
- HC4 violations: 0
- Teachers académicos en >1 salón: 4 (Sindy + 3 placeholders, by design)
```

Confirmed: Hoyos Camilo (the cliente's example case from feedback) now has all 5 of his sections in R900A only.

### Bundle verifier

`verify_bundle.py` still PASSES on the unchanged v2 bundle (16/16 invariants × 2 schools). Note: the verifier runs against the v2 bundle artifacts; v4 outputs in `data/columbus_full_hs_v4/` are NOT yet bundled. See QUESTIONS Decisión 11 for whether to regenerate.

## Hashes

```bash
$ shasum -a 256 src/scheduler/master_solver.py src/scheduler/ps_ingest.py
<hashes after this session — recompute on next session>

$ shasum -a 256 bundle_for_columbus/columbus_2026-2027_bundle_v2.zip
5a2932b8a9b7f0371b488c012296073549b000976d93ade08b4c65432ab46a89  bundle_for_columbus/columbus_2026-2027_bundle_v2.zip
```

Bundle hash matches `SHA256SUM.txt` from initial handoff.
