"""Master schedule solver — Stage 1 (v2 §7).

Decision: for each non-advisory section, pick (scheme 1..8, room).
Advisory sections all map to the ADVISORY slot (Day E, Block 3) and
need only a room choice.

Hard constraints (v2 §6.1):
- No teacher in two classes at the same time
- No room used by multiple classes simultaneously
- Room capacity ≥ section max_size
- Lab courses must be in lab rooms (room_type match)
- Advisory fixed at Day E, Block 3 (handled by separate variable space)
- No teacher with > max_consecutive_classes consecutive classes per day
- Teacher must be qualified (already enforced at section construction)

Soft (objective):
- Balanced teacher load across days
- Co-planning windows (best-effort: minimize spread of free slots within
  same department, deferred to v1.1)
"""
from __future__ import annotations

import time
from collections import defaultdict

from ortools.sat.python import cp_model

from .models import (
    DAYS,
    BLOCKS,
    Dataset,
    MasterAssignment,
)


SCHEMES = list(range(1, 9))  # 1..8


def solve_master(ds: Dataset, time_limit_s: float = 60.0, verbose: bool = False) -> tuple[list[MasterAssignment], cp_model.CpSolver, str]:
    """Returns (assignments, solver, status_name). Empty list if infeasible."""
    model = cp_model.CpModel()
    bell = ds.config.bell

    # Partition sections
    advisory_sections = [s for s in ds.sections if ds.course_by_id(s.course_id).is_advisory]
    academic_sections = [s for s in ds.sections if not ds.course_by_id(s.course_id).is_advisory]

    # Map (day, block) → scheme for non-advisory cells
    slot_to_scheme: dict[tuple[str, int], int] = {}
    for cell in bell.rotation:
        if cell.scheme == "ADVISORY":
            continue
        slot_to_scheme[(cell.day, cell.block)] = cell.scheme  # type: ignore[assignment]

    # Variables: section_scheme[s] ∈ 1..8, section_room[s] ∈ rooms
    section_scheme: dict[str, cp_model.IntVar] = {}
    for s in academic_sections:
        section_scheme[s.section_id] = model.NewIntVar(1, 8, f"scheme_{s.section_id}")

    # Room compat: only rooms whose type matches the course's required type.
    # If a section is locked to a specific room that doesn't match the type,
    # include it anyway (operator override). Same for HC4 home_room (added
    # 2026-04-28): when a teacher has a home_room_id set, that room is added
    # to the section's compat list — so HC2 (no two sections same scheme+room)
    # iterates over it correctly even if the home_room is the wrong "type" for
    # the course (e.g. Valentina teaching Anatomy in her science-lab home_room).
    teachers_by_id = {t.teacher_id: t for t in ds.teachers}
    course_rooms: dict[str, list[str]] = {}
    for s in academic_sections:
        c = ds.course_by_id(s.course_id)
        compat = [r.room_id for r in ds.rooms if r.room_type == c.required_room_type and r.capacity >= s.max_size]
        if not compat:
            compat = [r.room_id for r in ds.rooms if r.capacity >= s.max_size]
        if s.locked_room_id is not None and s.locked_room_id not in compat:
            compat = list(compat) + [s.locked_room_id]
        teacher = teachers_by_id.get(s.teacher_id)
        if (teacher is not None
                and teacher.home_room_id is not None
                and teacher.home_room_id not in compat):
            compat = list(compat) + [teacher.home_room_id]
        course_rooms[s.section_id] = compat

    # HC4 (added 2026-04-28): "salón es por profesor" — when a teacher has a
    # home_room_id set (from LISTADO MAESTRO column ROOM), all of their academic
    # sections must use that room. Per the Reglas Horarios HS doc 2026-04-22.
    # `locked_room_id` (operator override) takes precedence over home_room.
    room_index: dict[str, int] = {r.room_id: i for i, r in enumerate(ds.rooms)}
    section_room: dict[str, cp_model.IntVar] = {}
    for s in academic_sections:
        teacher = teachers_by_id.get(s.teacher_id)
        if (s.locked_room_id is None
                and teacher is not None
                and teacher.home_room_id is not None
                and teacher.home_room_id in room_index):
            # HC4: pin domain to the teacher's home room only
            compat_idx = [room_index[teacher.home_room_id]]
        else:
            compat_idx = [room_index[rid] for rid in course_rooms[s.section_id]]
        v = model.NewIntVarFromDomain(cp_model.Domain.FromValues(compat_idx), f"room_{s.section_id}")
        section_room[s.section_id] = v

    # Advisory: only choose room (scheme is fixed)
    advisory_room: dict[str, cp_model.IntVar] = {}
    for s in advisory_sections:
        compat_idx = [room_index[r.room_id] for r in ds.rooms if r.capacity >= s.max_size]
        advisory_room[s.section_id] = model.NewIntVarFromDomain(cp_model.Domain.FromValues(compat_idx), f"adv_room_{s.section_id}")

    # Locks (v2 §13): if a section has a locked_scheme or locked_room_id, force it.
    for s in academic_sections:
        if s.locked_scheme is not None and s.locked_scheme != "ADVISORY":
            if s.locked_scheme not in SCHEMES:
                raise ValueError(f"Section {s.section_id} locked to invalid scheme {s.locked_scheme}")
            model.Add(section_scheme[s.section_id] == s.locked_scheme)
        if s.locked_room_id is not None:
            if s.locked_room_id not in room_index:
                raise ValueError(f"Section {s.section_id} locked to unknown room {s.locked_room_id}")
            if s.locked_room_id not in course_rooms[s.section_id]:
                # Allow override even if room type doesn't match — operator's choice
                # but warn by failing fast if locked room can't accommodate the section
                room = ds.room_by_id(s.locked_room_id)
                if room.capacity < s.max_size:
                    raise ValueError(f"Section {s.section_id} locked to room {s.locked_room_id} with insufficient capacity")
                # Add the locked room idx to the section's domain via direct equality
                model.Add(section_room[s.section_id] == room_index[s.locked_room_id])
            else:
                model.Add(section_room[s.section_id] == room_index[s.locked_room_id])

    for s in advisory_sections:
        if s.locked_room_id is not None and s.locked_room_id in room_index:
            model.Add(advisory_room[s.section_id] == room_index[s.locked_room_id])

    # Booleans: section s placed in scheme k
    section_in_scheme: dict[tuple[str, int], cp_model.BoolVar] = {}
    for s in academic_sections:
        for k in SCHEMES:
            b = model.NewBoolVar(f"in_scheme_{s.section_id}_{k}")
            model.Add(section_scheme[s.section_id] == k).OnlyEnforceIf(b)
            model.Add(section_scheme[s.section_id] != k).OnlyEnforceIf(b.Not())
            section_in_scheme[(s.section_id, k)] = b

    # Booleans: section s in room r
    section_in_room: dict[tuple[str, str], cp_model.BoolVar] = {}
    for s in academic_sections:
        for rid in course_rooms[s.section_id]:
            b = model.NewBoolVar(f"in_room_{s.section_id}_{rid}")
            model.Add(section_room[s.section_id] == room_index[rid]).OnlyEnforceIf(b)
            model.Add(section_room[s.section_id] != room_index[rid]).OnlyEnforceIf(b.Not())
            section_in_room[(s.section_id, rid)] = b

    # HC1: Teacher cannot be in two academic sections in the same scheme
    sections_by_teacher: dict[str, list[str]] = defaultdict(list)
    for s in academic_sections:
        sections_by_teacher[s.teacher_id].append(s.section_id)
    for tid, sect_ids in sections_by_teacher.items():
        if len(sect_ids) < 2:
            continue
        for k in SCHEMES:
            model.Add(sum(section_in_scheme[(sid, k)] for sid in sect_ids) <= 1)

    # HC2: Room cannot host two academic sections at the same scheme
    for k in SCHEMES:
        for r in ds.rooms:
            terms = []
            for s in academic_sections:
                if r.room_id in course_rooms[s.section_id]:
                    a = section_in_scheme[(s.section_id, k)]
                    b = section_in_room[(s.section_id, r.room_id)]
                    both = model.NewBoolVar(f"both_{s.section_id}_{k}_{r.room_id}")
                    model.AddBoolAnd([a, b]).OnlyEnforceIf(both)
                    model.AddBoolOr([a.Not(), b.Not()]).OnlyEnforceIf(both.Not())
                    terms.append(both)
            if terms:
                model.Add(sum(terms) <= 1)

    # HC2b: Advisory sections all meet at E3, so they must be in distinct rooms.
    # Without this, the solver is free to put every advisory section in the same
    # room (since the academic HC2 above only iterates schemes 1..8). Caught by
    # the standalone bundle verifier on 2026-04-26.
    if advisory_sections:
        model.AddAllDifferent([advisory_room[s.section_id] for s in advisory_sections])

    # HC3: No teacher > max_consecutive_classes consecutive classes per day.
    # Per-teacher override (added 2026-04-28): if Teacher.max_consecutive_classes
    # is set, use that value instead of the school-wide default. Used for the
    # 3 real Columbus teachers carrying ≥7 academic sections where strict 4 is
    # pigeonhole-infeasible; everyone else stays at 4 per the Reglas Horarios HS
    # doc 2026-04-22.
    default_max_cons = ds.config.hard.max_consecutive_classes
    for tid, sect_ids in sections_by_teacher.items():
        if not sect_ids:
            continue
        teacher = teachers_by_id.get(tid)
        max_cons = (teacher.max_consecutive_classes
                    if teacher is not None and teacher.max_consecutive_classes is not None
                    else default_max_cons)
        if max_cons >= len(BLOCKS):
            continue  # cap ≥ blocks/day → no constraint to enforce for this teacher
        for day in DAYS:
            # For each block in this day, indicator = teacher teaches in that (day, block)
            block_busy: dict[int, cp_model.BoolVar] = {}
            for block in BLOCKS:
                scheme = slot_to_scheme.get((day, block))
                if scheme is None:
                    block_busy[block] = model.NewConstant(0)  # advisory cell
                    continue
                indicators = [section_in_scheme[(sid, scheme)] for sid in sect_ids]
                busy = model.NewBoolVar(f"busy_{tid}_{day}_{block}")
                model.AddMaxEquality(busy, indicators)
                block_busy[block] = busy
            # Sliding window of size max_cons + 1
            window = max_cons + 1
            for start in range(1, len(BLOCKS) - window + 2):
                window_blocks = list(range(start, start + window))
                model.Add(sum(block_busy[b] for b in window_blocks) <= max_cons)

    # Hard: balance sections across schemes tightly so the student solver has room
    # to fit per-course balance constraints. Tight bounds: avg-1 to avg+1.
    n_academic = len(academic_sections)
    avg = n_academic // 8
    scheme_min = max(1, avg - 1)
    scheme_max = avg + 1 if (n_academic % 8 == 0) else avg + 2
    for k in SCHEMES:
        scheme_count = sum(section_in_scheme[(s.section_id, k)] for s in academic_sections)
        model.Add(scheme_count >= scheme_min)
        model.Add(scheme_count <= scheme_max)

    # Hard: each multi-section course must span at least ceil(n_sections / 2) distinct
    # schemes so the student solver isn't forced into bottleneck slots. Without this,
    # the co-planning soft objective concentrates same-dept sections, making student
    # placement infeasible under tight per-course balance constraints.
    sections_by_course_local: dict[str, list[str]] = defaultdict(list)
    for s in academic_sections:
        sections_by_course_local[s.course_id].append(s.section_id)
    for cid, sect_list in sections_by_course_local.items():
        if len(sect_list) < 2:
            continue
        # Cap at len(SCHEMES): a course with >14 sections still cannot exceed
        # the 8 schemes that physically exist, even though ceil(n/2) would say so.
        min_distinct_schemes = min(len(SCHEMES), (len(sect_list) + 1) // 2)
        # scheme_used[k] = OR over course's sections of (section in scheme k)
        scheme_used_vars: list[cp_model.BoolVar] = []
        for k in SCHEMES:
            used = model.NewBoolVar(f"course_{cid}_in_scheme_{k}")
            indicators = [section_in_scheme[(sid, k)] for sid in sect_list]
            model.AddMaxEquality(used, indicators)
            scheme_used_vars.append(used)
        model.Add(sum(scheme_used_vars) >= min_distinct_schemes)

    # === Soft objectives (combined into a single weighted Minimize/Maximize) ===
    soft_terms: list[tuple[int, cp_model.IntVar | cp_model.LinearExpr]] = []  # (signed_weight, expr)

    # Soft 1: Balance teacher load across days
    teacher_day_load: list[cp_model.IntVar] = []
    for tid, sect_ids in sections_by_teacher.items():
        for day in DAYS:
            load_terms = []
            for block in BLOCKS:
                scheme = slot_to_scheme.get((day, block))
                if scheme is None:
                    continue
                for sid in sect_ids:
                    load_terms.append(section_in_scheme[(sid, scheme)])
            if load_terms:
                load_var = model.NewIntVar(0, len(BLOCKS), f"load_{tid}_{day}")
                model.Add(load_var == sum(load_terms))
                teacher_day_load.append(load_var)

    if teacher_day_load:
        max_load = model.NewIntVar(0, len(BLOCKS), "max_teacher_day_load")
        model.AddMaxEquality(max_load, teacher_day_load)
        # Negative because we minimize max_load (penalty)
        soft_terms.append((-ds.config.soft.teacher_load_balance, max_load))

    # Soft 2: Co-planning windows (v2 §6.2).
    # For each department with ≥2 teachers, create a BoolVar coplan_dept[d] = 1 iff
    # there exists a (day, block) where ≥2 teachers from d are simultaneously free.
    # Objective: maximize the count of departments with at least one such window.
    teachers_by_dept: dict[str, list[str]] = defaultdict(list)
    for t in ds.teachers:
        # Skip teachers with no academic sections (e.g., advisory-only) — coplanning
        # windows are meaningful only for teachers with teaching loads.
        if t.teacher_id in sections_by_teacher and sections_by_teacher[t.teacher_id]:
            teachers_by_dept[t.department].append(t.teacher_id)

    coplan_dept_vars: list[cp_model.BoolVar] = []
    for dept, teacher_ids in teachers_by_dept.items():
        if len(teacher_ids) < 2:
            continue  # Single-teacher dept can't have co-planning by definition

        # For each (day, block), build a per-teacher "free" indicator and count free teachers
        per_slot_window: list[cp_model.BoolVar] = []
        for day in DAYS:
            for block in BLOCKS:
                scheme = slot_to_scheme.get((day, block))
                if scheme is None:
                    continue  # Advisory cell — everyone busy with advisory
                # busy_at_t = OR over teacher's sections of (section in this scheme)
                free_indicators: list[cp_model.IntVar] = []
                for tid in teacher_ids:
                    sect_ids = sections_by_teacher.get(tid, [])
                    if not sect_ids:
                        # Teacher has no sections → always free
                        free_indicators.append(model.NewConstant(1))
                        continue
                    busy = model.NewBoolVar(f"busy_{tid}_{day}_{block}")
                    teaching_indicators = [section_in_scheme[(sid, scheme)] for sid in sect_ids]
                    model.AddMaxEquality(busy, teaching_indicators)
                    free = model.NewBoolVar(f"free_{tid}_{day}_{block}")
                    model.Add(free == 1 - busy)
                    free_indicators.append(free)
                # window_at_slot = (sum of free indicators ≥ 2)
                free_count = model.NewIntVar(0, len(teacher_ids), f"freecount_{dept}_{day}_{block}")
                model.Add(free_count == sum(free_indicators))
                window = model.NewBoolVar(f"coplan_{dept}_{day}_{block}")
                model.Add(free_count >= 2).OnlyEnforceIf(window)
                model.Add(free_count <= 1).OnlyEnforceIf(window.Not())
                per_slot_window.append(window)

        # coplan_dept = OR over all slots
        coplan_dept = model.NewBoolVar(f"coplan_dept_{dept}")
        if per_slot_window:
            model.AddMaxEquality(coplan_dept, per_slot_window)
        else:
            model.Add(coplan_dept == 0)
        coplan_dept_vars.append(coplan_dept)

    if coplan_dept_vars:
        coplan_total = model.NewIntVar(0, len(coplan_dept_vars), "coplan_total")
        model.Add(coplan_total == sum(coplan_dept_vars))
        # Positive weight — maximize
        soft_terms.append((ds.config.soft.co_planning, coplan_total))

    # Soft 3: Teacher preferences (v2 §6.2).
    # For each section, reward if its teacher prefers this course; penalize if avoided.
    # For each section's slot(s), reward preferred blocks and penalize avoided blocks.
    teachers_by_id = {t.teacher_id: t for t in ds.teachers}
    pref_course_rewards: list[cp_model.IntVar] = []
    avoid_course_penalties: list[cp_model.IntVar] = []
    for s in academic_sections:
        t = teachers_by_id.get(s.teacher_id)
        if t is None:
            continue
        # Course preferences are static per section assignment — once we know which
        # teacher teaches this section, the reward is binary based on whether the
        # teacher's preferred_course_ids contains this course. Since teacher
        # assignment is fixed at section construction, the reward is a constant for
        # each section (1 if preferred, 0 otherwise). We sum these up.
        if s.course_id in t.preferred_course_ids:
            # Constant reward — model with a fixed BoolVar set to 1
            v = model.NewConstant(1)
            pref_course_rewards.append(v)
        if s.course_id in t.avoid_course_ids:
            v = model.NewConstant(1)
            avoid_course_penalties.append(v)

    if pref_course_rewards:
        pref_total = model.NewIntVar(0, len(pref_course_rewards), "pref_course_total")
        model.Add(pref_total == sum(pref_course_rewards))
        soft_terms.append((ds.config.soft.teacher_preferred_courses, pref_total))
    if avoid_course_penalties:
        avoid_total = model.NewIntVar(0, len(avoid_course_penalties), "avoid_course_total")
        model.Add(avoid_total == sum(avoid_course_penalties))
        soft_terms.append((-ds.config.soft.teacher_avoid_courses, avoid_total))

    # Block preferences: reward if teacher's section lands in a preferred block,
    # penalize if it lands in an avoided block.
    pref_block_rewards: list[cp_model.BoolVar] = []
    avoid_block_penalties: list[cp_model.BoolVar] = []
    for s in academic_sections:
        t = teachers_by_id.get(s.teacher_id)
        if t is None:
            continue
        if not t.preferred_blocks and not t.avoid_blocks:
            continue
        # For each scheme, determine which blocks it occupies
        for k in SCHEMES:
            blocks_for_scheme = [b for (d, b) in ds.config.bell.slots_for_scheme(k)]
            in_scheme = section_in_scheme[(s.section_id, k)]
            for block in blocks_for_scheme:
                if block in t.preferred_blocks:
                    pref_block_rewards.append(in_scheme)
                if block in t.avoid_blocks:
                    avoid_block_penalties.append(in_scheme)

    if pref_block_rewards:
        pref_b_total = model.NewIntVar(0, len(pref_block_rewards), "pref_block_total")
        model.Add(pref_b_total == sum(pref_block_rewards))
        soft_terms.append((ds.config.soft.teacher_preferred_blocks, pref_b_total))
    if avoid_block_penalties:
        avoid_b_total = model.NewIntVar(0, len(avoid_block_penalties), "avoid_block_total")
        model.Add(avoid_b_total == sum(avoid_block_penalties))
        soft_terms.append((-ds.config.soft.teacher_avoid_blocks, avoid_b_total))

    # Soft 4: Singleton-section conflict avoidance (v2 §5.2).
    # For courses with exactly 1 section, prefer placing them in DIFFERENT schemes
    # so a student needing two singletons isn't forced into a conflict.
    sections_by_course_count: dict[str, int] = defaultdict(int)
    for s in academic_sections:
        sections_by_course_count[s.course_id] += 1
    singleton_section_ids = [s.section_id for s in academic_sections
                              if sections_by_course_count[s.course_id] == 1]
    if len(singleton_section_ids) >= 2:
        # For each scheme, count how many singletons land there. Penalize the max.
        singleton_per_scheme: list[cp_model.IntVar] = []
        for k in SCHEMES:
            cnt = model.NewIntVar(0, len(singleton_section_ids), f"singleton_in_scheme_{k}")
            indicators = [section_in_scheme[(sid, k)] for sid in singleton_section_ids]
            model.Add(cnt == sum(indicators))
            singleton_per_scheme.append(cnt)
        max_singletons = model.NewIntVar(0, len(singleton_section_ids), "max_singletons_per_scheme")
        model.AddMaxEquality(max_singletons, singleton_per_scheme)
        soft_terms.append((-ds.config.soft.singleton_separation, max_singletons))

    # Combine all soft terms into one objective
    if soft_terms:
        weighted = sum(w * expr for w, expr in soft_terms)
        model.Maximize(weighted)

    # Solve — multi-worker for speed, fixed seed for reproducibility (within OR-Tools' guarantees)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = 4
    solver.parameters.random_seed = 42
    if verbose:
        solver.parameters.log_search_progress = True

    t0 = time.time()
    status = solver.Solve(model)
    elapsed = time.time() - t0
    status_name = solver.StatusName(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], solver, status_name

    # Extract solution
    assignments: list[MasterAssignment] = []
    rooms_by_idx = {i: r for r, i in room_index.items()}

    for s in academic_sections:
        scheme = solver.Value(section_scheme[s.section_id])
        room_idx = solver.Value(section_room[s.section_id])
        room_id = rooms_by_idx[room_idx]
        slots = ds.config.bell.slots_for_scheme(scheme)
        assignments.append(MasterAssignment(
            section_id=s.section_id,
            scheme=scheme,
            room_id=room_id,
            slots=slots,
        ))

    for s in advisory_sections:
        room_idx = solver.Value(advisory_room[s.section_id])
        room_id = rooms_by_idx[room_idx]
        assignments.append(MasterAssignment(
            section_id=s.section_id,
            scheme="ADVISORY",
            room_id=room_id,
            slots=[(ds.config.hard.advisory_day, ds.config.hard.advisory_block)],
        ))

    if verbose:
        print(f"Master solve: {status_name} in {elapsed:.2f}s, objective={solver.ObjectiveValue() if status == cp_model.OPTIMAL else 'feasible-only'}")

    return assignments, solver, status_name


if __name__ == "__main__":
    from .sample_data import make_grade_12_dataset
    ds = make_grade_12_dataset()
    print(f"Solving master schedule for {len(ds.sections)} sections...")
    assignments, solver, status = solve_master(ds, time_limit_s=30, verbose=True)
    print(f"Status: {status}, assignments: {len(assignments)}")
    if assignments:
        from collections import Counter
        scheme_counts = Counter(a.scheme for a in assignments)
        print(f"Scheme distribution: {dict(scheme_counts)}")
