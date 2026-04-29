# Lessons for a future agent picking up the Columbus scheduler

Written 2026-04-29 after a full day of iteration that took the bundle from **~144 unmet / 65% coverage** to **~105 unmet / 81% coverage** without changing any input data — purely by fixing the engine and the data interpretation.

This is not a spec. The spec is `docs/powerschool_requirements_v2.md`. This is the operational lore: what to do, what not to do, and what to ask for first so you don't waste the school's patience or your tokens.

---

## TL;DR — the three things that mattered most

1. **The data source is the bug 80% of the time.** The biggest single improvement (from ~144 to ~105 unmet) came from switching the canonical xlsx and noticing a silent filter dropped 11 sections. Always cross-validate ingested counts against the school's own planning sheet before tuning the solver.

2. **The school's policies are not the model defaults.** Every default (`enforce_separations=True`, `max_section_spread=5`, `max_consecutive=4`, advisory-counts-as-course, etc.) was wrong for at least one decision the school made. Ask first, implement second.

3. **Coverage trades off with everything.** Every constraint costs cupos. Make the trade-off explicit: present "this rule costs N students" before turning anything on. The school will choose differently than the textbook suggests.

---

## About this project

- **Codebase:** `/Users/hector/Projects/handoff_2026-04-26_continuation/scheduler/`
- **Engine:** OR-Tools CP-SAT, two-stage solve.
  - Stage 1 (`master_solver.py`): assign each section to a scheme + room.
  - Stage 2 (`student_solver.py`): assign each student to one section per requested course.
- **Grid:** 5 days (A–E) × 5 blocks × 8 rotating schemes. Each course meets 3 cells/week. Advisory fixed at Day E, Block 3.
- **Real client:** Colegio Columbus, Medellín. HS 2026-2027. 509 students, ~67 courses, ~248 sections, 38 rooms, 48 teachers.
- **GitHub:** `tognoassistant-labs/scheduler`. Bundles live in `scheduler/data/_client_bundle_v4/`.
- **Build:** `cd scheduler && .venv/bin/python build_v4_bundle.py`. Takes ~5 minutes (300s student solve + master + reports).

---

## Ask the school these BEFORE any code change

Make a Q&A doc and don't move past it without answers. Defaults will burn you.

### Time structure
- Confirm 5×5 with 8 rotating schemes? Lunch slot? Flex periods?
- Advisory: which day, which block, how many meetings/week? Does it count as a "course" for student-load reporting? **Columbus answer: NO, advisory does not count.**

### Coverage policy
- Coverage 100% required, or partial OK?
- If partial, which courses can be dropped first (electives vs required vs AP)?
- Per-grade priority? **Columbus rule: G12 first, then G11, G10, G9.** This was a longstanding rule we had to add — without it, G9 was best-served (62%) and G12 worst (46%).

### Capacity
- Hard at room cap, or +1/+2 OK if approved?
- Per-section overrides via a CONSTRAINTS column? **Columbus has it: `"Numero Maximo de estudiantes es 26"` for AP Research.**

### Teacher load
- Max consecutive classes per day? **Columbus: strict 4.**
- Override allowed for teachers with mathematical impossibility (e.g. ≥7 sections × 3 meetings/week in a 5-block day)? Probably yes by necessity.
- Does advisory count toward consecutive load? **Probably no.**

### Counselor recommendations
- "Separado de" pairs: HARD or SOFT? **Columbus: started HARD, changed to SOFT with high weight (1000) — recovered ~22 cupos and still respected 81% of separations.**
- "Compartir clases con" pairs: SOFT (always).

### Co-planning
- HARD (must share a free scheme), SOFT (preferred), or off?
- **Columbus: SOFT for now. HARD costs ~50 cupos.**

### Salones
- Room TYPE hard (Science → Lab, PE → Gym, etc.)? Almost certainly yes.
- Preferred room (`PREFERRED_ROOM` column) hard or soft? **Soft is more humane.** Hard makes the engine drop sections when the preferred room is busy.
- Capacity over-fill OK in the assigned room?

### Data file cadence
- Who maintains the source xlsx? When does it change? Should the build re-pull each run?
- **Critical:** if multiple sheets in the file describe the same thing (e.g. `Teacher courses` vs `UPDATED MARCH 20 - COURSE_GRADE`), which is canonical? **At Columbus, both sheets disagreed. The canonical was `UPDATED MARCH 20`.**

---

## Project-specific gotchas (Columbus, but instructive)

### The "New X Teacher" silent drop (the bug that ate 11 sections)
The original ingester had `if teacher is None: continue` when looking up a `TEACHER_DCID` from `teacher_assignments`. Placeholder teachers ("New Science Teacher 1") had no `LASTFIRST` in the `teachers` sheet, so they were filtered. Their assignments were silently dropped. This made Physics 11 look like it had 2 sections instead of 5, Biology 9 look like 4 instead of 6, etc.

**Fix applied:** loud warnings on every drop + a validation gate that compares `SECTIONSTOOFFER` (planned) vs actual sections per course. **You will see this kind of bug again** in any client. Always compare planned vs ingested.

### Term-paired sections were a model-only feature, not enforced
`Course.term_pair = "I1212"` was set on Course objects (e.g. AP Micro ↔ AP Macro alternate semesters), but the master solver **never read it**. So Micro.1 ended up at scheme 5 and Macro.1 at scheme 2 — students taking both got two slots instead of sharing one. Visual chaos.

**Fix applied:** HC6 in `master_solver.py` — for each course pair, sections from same teacher must share scheme + room. Made +143 cupos available because students taking both no longer fight for two slots.

### Multi-sheet contradictions
Same school file had `Teacher courses` (showed 4 Bio 9 sections) and `UPDATED MARCH 20 - COURSE_GRADE` (showed 6 Bio 9 sections needed). They were out of sync. Took an iteration with the school to figure out which was canonical.

**Always ask which sheet is the source of truth, especially when it looks like both describe the same thing.**

### Advisory leakage into reports
The ingester adds Advisory as a synthetic request to every student. The per-student CSV's `n_courses` then included Advisory, so a student with 8 real requests + Advisory had `n_courses=8` (8 sections) but only 7 real courses if one didn't fit. The school read this as "student missing 1 course but report says 8" → confusion.

**Fix applied:** new columns `n_requested`, `n_assigned`, `n_missing`, `missing_courses` — all excluding Advisory.

---

## What worked

### Two-stage solve with grade-weighted unmet
- Master decides scheme + room (fast, OPTIMAL in seconds).
- Student decides which student goes in which section (300s, FEASIBLE).
- Coverage objective uses **per-grade weights** (G12: 10⁶, G11: 10⁴, G10: 10², G9: 1). Strong bias without overflow.

### Soft constraints with weights ratioed against coverage
- Separations: weight 1000 (between groupings ~4 and required ~10000+).
- Result: 81% of separations respected, ~22 cupos recovered.
- The pattern: **coverage weight × per-violation weight should dominate other softs** but stay within int64.

### Validation gates at ingest
- Compare `SECTIONSTOOFFER` (courses sheet) vs sum of `SECTIONS_PER_COURSE` (teacher_assignments).
- Compare demand (course_requests) vs capacity (sections × max_size).
- Drop nothing silently. Every dropped row gets a `[WARN]` with reason.

### Per-student `missing_courses` column in the output CSV
- The school can sort by `n_missing > 0` and see exactly who's short and which courses.
- Was the single most-asked-for feature. Should be in v1 of any future scheduler.

### Term-paired sections enforced as `section_in_scheme` equality + `section_room` equality
- Simple constraint, big effect. ~143 cupos came back.

### Tight commit messages with before/after KPIs
- Each commit had a metric block: balance compliance, coverage %, unmet count.
- When the school asked "did v4.X help?", git log answered immediately.

---

## What didn't work

### Trying to maximize coverage before policy was settled
- Spent cycles tweaking weights and constraints. Then the school said "no, balance ≤5" or "separations should be soft, not hard." Half the work was undone.
- **Lesson:** clarify policy first, then tune. Policy answers come in 1 hour from the school; tuning can take days.

### Strict lexicographic grade priority
- Tried weights `(10¹², 10⁸, 10⁴, 1)` for true lex.
- Multiplied by `coverage_weight` (10⁴), value = 10¹⁶ — **overflows int64 when combined**.
- **Fix:** "very strong bias" weights `(10⁶, 10⁴, 10², 1)`. Not strict lex but operationally equivalent in this dataset (max ~1500 unmet/grade keeps the math sane).

### F1 over-fill repair pass
- Built a post-solve pass that for each unmet student tries to add them to a section with +1 over capacity.
- Recovered only **3 cupos** in the test run — vs a 10–15 estimate.
- Reason: the unmet students are mostly **grid-bound** (no slot fits in their schedule), not capacity-bound (sections are full).
- Solver run-to-run variance (~±15 cupos) made the small gain invisible.
- **Lesson:** if your bottleneck is grid, capacity tweaks won't help. Diagnose before implementing.

### Comparing single-run results
- CP-SAT in FEASIBLE mode with 300s time limit is **non-deterministic across runs**. ±15 cupos variance is normal.
- **Lesson:** run 3 times and report the best/median, or set a deterministic seed, before claiming improvement.

### Hard separations
- 79 hard "Separado de" pairs cost ~94 cupos. School chose coverage; we made them soft. 81% still respected naturally.
- **Lesson:** counselor recommendations are almost never truly inviolable. Default to soft with high weight.

### Strict balance ≤3
- Tried it. Cost ~54 cupos vs ≤4. School said "≤3 ideal but ≤5 fine."
- **Lesson:** the academic literature says "tight balance is virtuous." The school says "I'd rather a kid get all his classes than have section sizes 18 vs 21."

### Adding sections to fix capacity gaps
- I kept proposing "open 1 more section of Bio 9 to recover 30 students."
- The school's answer (final): **no more sections; teacher loads are already coordinated.** Any proposal that requires opening sections is a waste of the conversation.
- **Lesson:** ask "are sections fixed?" early. If yes, focus only on grid + assignment optimization.

---

## Patterns to use

### Multi-tier room compatibility
```python
# Tier 1: right type AND fits
compat = [r for r in rooms if r.type == required and r.cap >= max_size]
# Tier 2: any room that fits
if not compat: compat = [r for r in rooms if r.cap >= max_size]
# Tier 3: right type, accept squeeze (school approved over-fill)
if not compat: compat = [r for r in rooms if r.type == required]
# Tier 4: ultimate fallback — any room
if not compat: compat = list(rooms)
```
Without tiers 3 and 4, a `CONSTRAINTS`-driven max_size bump (AP Research → 26) makes the model `MODEL_INVALID` because no 26-seat room exists. Tiers degrade gracefully.

### CONSTRAINTS column auto-parse
Free-text columns are common in school data. Most rules are conditional and can't auto-parse. But structured ones can:
```python
_MAX_SIZE_REGEX = re.compile(
    r"(?:numero\s+maximo|max(?:imo)?(?:\s+(?:class\s+size|de\s+estudiantes|students))?)"
    r"[^\d]*(\d+)",
    re.IGNORECASE,
)
```
For each row, try the regex. If matched → apply. If not → log as `[INFO]` for manual review.

### Per-grade weighted unmet
```python
GRADE_PRIORITY_WEIGHTS = {12: 10**6, 11: 10**4, 10: 10**2, 9: 1}
weighted_slack_terms = [slack * GRADE_PRIORITY_WEIGHTS[grade(sid)]
                        for slack, (sid, _) in zip(slacks, meta)]
```
The school's "G12 first" rule is a real-world institutional priority that's missing from textbook scheduling. Add it explicitly.

### Soft separations with high weight
```python
v = model.NewBoolVar(f"sep_v_{a}_{b}_{s.section_id}")
model.Add(x[ka] + x[kb] - 1 <= v)  # v=1 iff both=1
model.Add(v <= x[ka])
model.Add(v <= x[kb])
# Then in objective: - separation_violation * sum(violations)
```

### Friendly unmet report
For each student, output:
- `n_requested` (excluding advisory)
- `n_assigned` (excluding advisory)
- `n_missing`
- `missing_courses` (pipe-separated)

This is the school's primary review surface. They won't read raw section CSVs.

---

## What the next agent should NOT bother building

- A balance constraint enforcer set to ≤3 by default. Schools want coverage.
- An advisory-counts-as-course report. Just exclude advisory and move on.
- A "create sections automatically" feature. Schools coordinate teachers manually; engine should never propose sections to add (only flag deficits).
- Strict lexicographic optimization across many tiers. Weighted approximation works fine and fits in int64.
- A general-purpose SAT solver wrapper. Use OR-Tools CP-SAT directly; the abstractions add nothing here.
- A pre-flight that runs the solver twice for variance. Schools don't have time; just disclose variance in the report.
- Per-function unit tests of every solver helper. The solver helpers are tightly coupled to OR-Tools state; isolated unit tests give false confidence. **Use scenario-level random testing instead** (see "Engineering practices" below).

---

## What the next agent SHOULD build

- **A working visor** (web UI) where principals/counselors review per-student and per-teacher schedules visually. The current process is reading CSVs in Excel — painful and error-prone. There's a `scheduler/app.py` (Streamlit) but I haven't verified it works.
- **Per-unmet diagnostic** — for each unmet student, a one-liner explaining the cause (capacity-bound, grid-bound, separation-bound, restriction-bound). The school can then decide case-by-case.
- **Section expansion advisor** — given current unmet, output ranked list "open 1 section of course X taught by teacher Y in slots Z → recover N students." Translates the coverage gap into operational asks the school can take to admin.
- **Lock + re-solve partial** — once G12 is approved, lock those assignments and re-solve only G11/G10/G9. Today the engine re-solves everything from scratch.
- **PowerSchool import end-to-end test** — generate CSVs, attempt actual import to PS test environment, validate the round-trip. CSVs are useless if PS rejects them.
- **Diff viewer between bundle versions** — when new requests come in or rules change, see what the change actually did to which students.

---

## Key code locations (as of v4.13 / commit `5c84175`)

| What | Where |
|---|---|
| Ingester (xlsx → Dataset) | `scheduler/src/scheduler/ps_ingest_official.py` |
| Master solver (sections → schemes/rooms) | `scheduler/src/scheduler/master_solver.py` |
| Student solver (students → sections) | `scheduler/src/scheduler/student_solver.py` |
| Models (Course, Section, Student, Dataset) | `scheduler/src/scheduler/models.py` |
| Hard/Soft constraint defaults | `scheduler/src/scheduler/models.py` (HardConstraints, SoftConstraintWeights) |
| Build script | `scheduler/build_v4_bundle.py` |
| CSV/JSON I/O | `scheduler/src/scheduler/io_csv.py`, `io_oneroster.py` |
| Reports (per-student, per-section, KPI) | `scheduler/src/scheduler/reports.py`, `exporter.py` |
| Bundle output | `scheduler/data/_client_bundle_v4/HS_2026-2027_real/` |
| Canonical input file | `reference/schedule_master_data_hs.xlsx` |

---

## Specific traps you will hit

### Trap 1: "Just add more sections to fix capacity"
You can't. The school has already coordinated teacher loads. Sections are fixed. Look at grid, not capacity.

### Trap 2: "The KPI says 4-student max-dev, must be balance bug"
The KPI single-number max-dev compares each section to the per-course mean. A spread of 5 in an asymmetric distribution gives max-dev ~3.7 → "4". The hard cap controls SPREAD, not max-dev. Check both numbers.

### Trap 3: "Solver is OPTIMAL means we have the best solution"
Master solver hits OPTIMAL. Student solver hits FEASIBLE in 300s — meaning "good enough but not proven optimal." Run-to-run variance is real. Don't claim victory from one run.

### Trap 4: "ENFORCE_SEPARATIONS=True is the safe default"
It's the strict default. It's also the most expensive — costs ~94 cupos at Columbus. The school always prefers coverage. Default should be SOFT with high weight.

### Trap 5: "Course.term_pair is set, so paired sections are co-located"
No. The model field exists; the constraint is separate. Verify in master_solver.py that HC6 (or equivalent) actually enforces same scheme + same room for paired sections.

### Trap 6: "Just bump max_size and the school is happy"
Bumping max_size beyond room.capacity makes the master `MODEL_INVALID`. You need the room compat fallback tiers AND the school's explicit approval (via CONSTRAINTS column or direct sign-off).

### Trap 7: "Advisory is a course like any other"
Advisory is a fixed slot (Day E, Block 3 at Columbus), meets once a week (not 3), and the school does NOT count it as a "course" in coverage reports. Treat it specially in reports and in load calculations.

### Trap 8: "Group by student name to map IDs"
Student names appear in some sheets (`conselours_recommendations`, `teacher_avoid`) but the canonical ID is `STUDENT_NUMBER`. When name-only data comes in, build a `name → id` map from the conselours sheet (which has both) and use it for resolution. Some name-only rows may stay unmatched — log them, don't crash.

---

## How to start the conversation with the school (template)

> "Antes de empezar a generar horarios, necesito confirmar X cosas que afectan directamente lo que el motor produce. Cada una tiene un costo en cobertura — quiero que tomen decisiones informadas:
>
> 1. **Estructura de tiempo**: 5×5×8 schemes? Advisory día/bloque?
> 2. **¿Pueden abrir secciones nuevas si la demanda lo exige, o están fijas?** (decide si vale la pena calcular section-expansion proposals)
> 3. **Política de cobertura**: 100% de cursos requeridos por estudiante, o aceptan parcial?
> 4. **Prioridad por grado**: ¿G12 primero o todos iguales?
> 5. **Recomendaciones de consejería ('Separado de')**: HARD o SOFT? (HARD cuesta ~10-20% de cobertura típicamente)
> 6. **Co-planning**: HARD, SOFT, o off?
> 7. **Capacidad de sección**: ¿hay over-fill aprobado caso por caso, o cap rígido?
> 8. **Override de consecutive=4**: ¿se acepta para profes con ≥7 secciones (matemáticamente forzoso)?
> 9. **¿Cuál sheet/archivo es la fuente única de verdad?**
> 10. **Cadencia de actualización del archivo** + cómo nos avisan cuando cambia.
>
> Cada respuesta destraba una semana de iteración."

---

## Engineering practices (must-do)

Seven non-negotiable practices. If you skip any of these, the project will burn cycles in places that don't matter and break in places that do.

### 1. Extract every rule as a formal constraint

Don't carry rules around as comments, prose, or implicit defaults. Every rule the school states gets a row in a constraint registry:

```
| id  | name                          | type | source         | weight | cost-when-violated      |
|-----|-------------------------------|------|----------------|--------|--------------------------|
| HC1 | teacher in 1 section/scheme   | hard | textbook       | —      | infeasible               |
| HC4 | section in preferred room     | soft | school 04-29   | 50     | profe en aula no preferida |
| HC6 | term-paired same scheme+room  | hard | school 04-29   | —      | "se enloquece el horario" |
| SO1 | balance ≤ 5 per course        | hard | school 04-29   | —      | structural               |
| SO2 | counselor "Separado de"       | soft | counselor team | 1000   | adversaries in same sec  |
```

A registry like this lives in code (e.g. `models.py:HardConstraints/SoftConstraintWeights`) AND in a doc the school can read. When they say "change the rule," you go to the registry, not to the solver code.

**At Columbus this took me too long to formalize.** I treated each rule ad-hoc; the school changed their mind 4 times on balance and twice on separations because they didn't have a registry to point at.

### 2. Hard vs soft, ALWAYS labeled

For every constraint, the answer to "what happens if this is violated?" must be one of:
- **HARD**: model rejects (infeasible). Use sparingly.
- **SOFT (high)**: penalized at >> coverage_weight. Solver respects unless the alternative is breaking required courses. Example: term-paired sections.
- **SOFT (medium)**: penalized > other softs but < coverage. Example: separations (1000), preferred rooms.
- **SOFT (low)**: tie-breaker. Example: balance (8), groupings (4), teacher block preferences (2).

**The mistake to avoid:** putting everything as HARD because "the school said so." The school says HARD because they don't know the cost. Quantify the cost first, then offer them the choice.

**Pattern at Columbus:**
1. Implement as HARD initially (per school request)
2. Measure cost in cupos
3. Show school: "this rule costs 94 students their full schedule"
4. School chooses SOFT with weight X

### 3. Build validation tests BEFORE you optimize

Three layers of tests, in this order:

**Layer 1 — Ingestion validation (cheap, run every build):**
- Sum of `SECTIONS_PER_COURSE` across teacher_assignments == `SECTIONSTOOFFER` in courses sheet (per course)
- Sum of `course_requests` per course ≤ sum of `section.max_size` (capacity > demand sanity)
- Every TEACHER_DCID in teacher_assignments exists in teachers sheet
- Every COURSENUMBER in teacher_assignments exists in courses sheet
- Every STUDENT_NUMBER in course_requests exists in (an implied or explicit) students sheet

This already exists in the Columbus ingester (`[WARN]` blocks). It caught the silent New-Teacher drop. Don't skip it.

**Layer 2 — Constraint structural tests (run on every code change):**
- After building the model, walk it: "does this model contain HC6 enforcing term-pair?"
- For each constraint type, build a tiny test scenario (3 students, 2 courses) where the constraint is the only thing decisive, and verify the solver respects it.
- If you change a constraint, the corresponding test breaks. Fix it explicitly — don't silently accept the new behavior.

**Layer 3 — Random scenario tests (see #6):** see below.

**Order matters:** never write the optimization first and tests after. The optimization will be subtly wrong (e.g. `Course.term_pair` set but never enforced — that bug lived in production for weeks).

### 4. Use OR-Tools, never improvise

CP-SAT handles 10⁵ binary vars and 10⁶ constraints in seconds. Your hand-rolled greedy heuristic doesn't. Resist the urge to "just write a Python loop that assigns students to sections."

The legitimate exceptions:
- **Pre-processing**: building the input graph (e.g. multi-level merge, term-pair detection)
- **Post-processing**: F1-style repair pass that adds students greedily (cheap, only fires for cases the solver missed)
- **Reporting**: turning solver output into KPIs and CSVs

Inside those exceptions, you can write Python freely. **Inside the constraint formulation, use only OR-Tools primitives.** No "call the solver, then patch the result with a Python loop and re-call the solver" — that produces non-reproducible bundles and confuses everyone.

### 5. Generate infeasibility reports

When the master solver returns `MODEL_INVALID` or `INFEASIBLE`, the worst answer is "ABORTING: master infeasible." The right answer is:

> "Infeasible because of the following constraint conflict:
> - HC1 says teacher Sofia ≤ 4 consecutive classes/day
> - But her assignment list has 7 sections requiring 7 distinct schemes
> - With 5 blocks/day and rotating 8 schemes, pigeonhole forces ≥5 consecutive
> - Either: relax HC1 for Sofia (override max_consecutive), or reduce her sections to ≤6.
> Showing the minimal infeasible subset:
>   { HC1(Sofia), section_count(Sofia)=7, schemes_per_day(5) }"

Tooling:
- **Assumption variables**: wrap each "questionable" constraint in a Bool that's set to True. If model is infeasible, drop assumptions one at a time to find the minimal infeasible core.
- OR-Tools has `SolutionHint` and `model.AddBoolOr/AddBoolAnd` patterns that support this.
- Even a manual "drop constraint X, retry, see if feasible" loop is better than nothing.

**At Columbus**: when AP Research cap=26 made the model `MODEL_INVALID`, we lost 30 minutes diagnosing manually. An infeasibility report would have said "no room with capacity ≥ 26 exists" in 1 second. Build this before you need it.

### 6. Run random scenario tests

Property-based testing is the right tool for solvers. Write generators for synthetic Datasets and assert properties:

```python
def test_no_time_conflicts_for_random_dataset():
    for seed in range(50):
        ds = random_dataset(seed=seed, students=50, courses=10, teachers=5)
        master, _, _ = solve_master(ds, time_limit_s=10)
        students, _, _, _ = solve_students(ds, master, time_limit_s=30)
        # Property: no student is in 2 sections at the same (day, block)
        for sa in students:
            slots = []
            for sid in sa.section_ids:
                slots.extend(slots_of(master, sid))
            assert len(slots) == len(set(slots)), f"Conflict for {sa.student_id} in seed {seed}"
```

Properties to test:
- No student in 2 sections at same (day, block)
- No teacher in 2 sections at same (day, block)
- No room hosts 2 sections at same (day, block, term)
- Every assigned student-section pair has the student requesting that course
- max_consecutive is respected per teacher
- Term-paired sections share scheme + room
- All sections appear in the master assignment
- Every required course is granted OR appears in unmet (no silent drops)

**Run these on every PR.** They take seconds. They catch entire classes of bugs that scenario-specific tests miss.

**Common generator boundary cases:**
- 1 teacher (extreme over-load)
- 1 room (extreme room contention)
- All students requesting the same course (extreme demand)
- Tight grid (n_sections × meetings = total cells)
- Many separations (saturation of behavior matrix)

### 7. NEVER change rules silently

This is the scariest class of bug because it's invisible. Examples we hit:

- Ingester silently dropped 11 sections because `if teacher is None: continue` had no log → 30% capacity gap invisible for weeks.
- `Course.term_pair` was set but the solver never enforced it → AP Micro/Macro produced visually broken schedules.
- A SECTIONTYPE='LP' filter assumed LP rows were duplicates → dropped a real Life Purpose section.

Rules:
1. **Every dropped row gets a `[WARN]` log with reason and counts.**
2. **Every constraint has a structural test that fails if the constraint disappears.**
3. **Every soft weight has a default in `models.py` AND is reported in build output** (so the school sees what's enforced).
4. **A constraint registry doc lives next to the code.** Updates to the registry require updates to a `CHANGELOG` line.
5. **Every release/build emits a manifest** of (a) input file SHA256s, (b) constraint set in effect, (c) measured costs.

If a rule changes between two builds and the school can't tell from the build output, that's a process failure. Fix it before doing anything else.

---

## How these 7 practices map to the Columbus build (current state, 2026-04-29)

| Practice | Current state | Gap |
|---|---|---|
| 1. Formal constraint registry | Defaults in `HardConstraints`/`SoftConstraintWeights`. No external doc. | Need a registry doc the school can read. |
| 2. Hard vs soft labeled | Yes in `models.py` comments. | Document each weight's intuition (why 1000 for separations, why 4 for groupings). |
| 3. Validation tests before optimization | Layer 1 (ingest) ✅. Layer 2 (structural) partial. Layer 3 missing. | Add structural + random tests for HC1–HC6. |
| 4. OR-Tools used throughout | ✅ | F1 repair is the only Python post-pass; documented as such. |
| 5. Infeasibility reports | ❌ Build just says "ABORTING: master infeasible." | Add MUS (minimal unsatisfiable subset) extraction. |
| 6. Random scenario tests | ❌ Existing tests are fixture-based. | Add `tests/test_random_scenarios.py` with seed loop. |
| 7. Never silent rule changes | Loud warnings in ingest ✅. Constraint changes are commit messages, not registry diffs. | Build a constraint-changelog discipline. |

The four ❌ / ⚠️ rows are the next agent's actual to-do list. Without those, the project will keep regressing each time someone forgets to ask the school a question.

---

## Closing thought

The hardest thing in this project is **not the optimization**. The optimization is a textbook CP-SAT problem and there are 100 papers about it. The hardest thing is **negotiating with the human institution about what the rules actually are**. Every rule the textbook treats as fixed (capacity, separation, balance, consecutive) is in practice a school-specific policy choice that costs cupos. Your job is to surface those costs explicitly, let the school choose, and then make the engine reflect their choices — not impose academic defaults.

Also: when a build run takes 5 minutes, **batch your changes**. Don't run a full build to test a 1-line change if you can validate with a smoke test in 5 seconds. Use `scheduler/.venv/bin/python -c "..."` to spot-check ingestion, constraints, or specific edge cases without paying the solver cost.

Good luck.
