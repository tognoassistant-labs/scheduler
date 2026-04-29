"""Student assignment solver — Stage 2 (v2 §7).

Given a fixed master schedule (section → scheme + room), assign each
student to one section per requested course such that:

Hard constraints (v2 §6.1 + balance):
- No student in two sections that share a (day, block)
- Section capacity ≤ max_size (25, or 26 for AP Research)
- Restricted teachers respected
- Separation pairs never share a section
- Required courses must be granted
- Per-course section spread (max - min enrollment) ≤ K (default 4 → max-dev ≈ 2)

Soft (two-phase lex-min):
1. Maximize first-choice electives
2. Subject to phase-1 optimum, maximize granted grouping pairs

Balance is hard, not soft, because minimizing it as a soft objective is
combinatorially expensive and rarely converges within practical time
budgets. Bounding it directly is faster and meets the v2 §10 ≤3 target.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Literal

from ortools.sat.python import cp_model

from .models import (
    Dataset,
    MasterAssignment,
    StudentAssignment,
)


def _clear_objective(model: cp_model.CpModel) -> None:
    """Remove the model's objective and any stale solution hints."""
    if hasattr(model, "ClearObjective"):
        model.ClearObjective()
    if hasattr(model, "ClearHints"):
        model.ClearHints()


def solve_students(
    ds: Dataset,
    master: list[MasterAssignment],
    time_limit_s: float = 180.0,
    mode: Literal["single", "lexmin"] = "single",
    verbose: bool = False,
) -> tuple[list[StudentAssignment], list[tuple[str, str]], cp_model.CpSolver, str]:
    """Returns (assignments, unmet_requests, solver, status_name).

    `mode='single'` (default): weighted-sum single solve. Balance is bounded
        hard via `max_section_spread_per_course` AND penalized softly via
        `balance_class_sizes` weight, so a strong balance signal coexists with
        elective and grouping objectives.
    `mode='lexmin'`: two-phase lex-min over electives → groupings, with
        balance as a hard cap. Slower but gives a clean lexicographic priority.

    `time_limit_s` is the total budget (split 60/40 across phases for lexmin).
    """
    model = cp_model.CpModel()

    master_by_sect: dict[str, MasterAssignment] = {m.section_id: m for m in master}

    # v4.2 — sections_by_course indexes a section under BOTH its primary
    # course_id and each linked_course_id. This makes a single combined
    # multi-level section visible to students who request any of the linked
    # courses (e.g. one Spanish FL section covers G0902, G1204, G1205, G1206).
    sections_by_course: dict[str, list[str]] = defaultdict(list)
    for s in ds.sections:
        sections_by_course[s.course_id].append(s.section_id)
        for linked in s.linked_course_ids:
            sections_by_course[linked].append(s.section_id)

    courses_by_id = {c.course_id: c for c in ds.courses}
    sections_by_id = {s.section_id: s for s in ds.sections}

    # Decision vars: x[student, section] ∈ {0, 1} only for sections of courses the student requested
    x: dict[tuple[str, str], cp_model.BoolVar] = {}
    for st in ds.students:
        for r in st.requested_courses:
            for sid in sections_by_course.get(r.course_id, []):
                sect = sections_by_id[sid]
                if sect.teacher_id in st.restricted_teacher_ids:
                    continue
                # Same key for multiple requests touching same section is fine —
                # NewBoolVar dict insertion is idempotent on key.
                if (st.student_id, sid) not in x:
                    x[(st.student_id, sid)] = model.NewBoolVar(f"x_{st.student_id}_{sid}")

    # student_course_sections is keyed by (student, requested_course) so that
    # the per-request constraint sees ALL sections covering that course,
    # including combined multi-level sections via linked_course_ids.
    student_course_sections: dict[tuple[str, str], list[str]] = defaultdict(list)
    for st in ds.students:
        for r in st.requested_courses:
            for sid in sections_by_course.get(r.course_id, []):
                if (st.student_id, sid) in x:
                    student_course_sections[(st.student_id, r.course_id)].append(sid)

    # HC: required = exactly 1 section (soft via slack); rank-1 elective = at most 1; rank-2 elective = at most 1
    # Soft slack lets us handle students who are over-assigned (e.g. 10 mandatory
    # requests vs 9 academic slots) without going INFEASIBLE. Slacks are penalized
    # heavily in the objective — the solver minimizes them, so only structurally
    # impossible requests end up unfulfilled.
    required_slacks: list[cp_model.BoolVar] = []
    required_slack_meta: list[tuple[str, str]] = []  # (student_id, course_id) for each slack
    for st in ds.students:
        rank1_courses = {r.course_id for r in st.requested_courses if r.rank == 1}
        rank2_courses = {r.course_id for r in st.requested_courses if r.rank == 2}
        required_courses = {r.course_id for r in st.requested_courses if r.is_required}

        for cid in rank1_courses:
            options = student_course_sections.get((st.student_id, cid), [])
            if not options:
                continue
            if cid in required_courses:
                slack = model.NewBoolVar(f"slack_{st.student_id}_{cid}")
                # sum + slack == 1: either we assign one section, OR slack=1 (unmet)
                model.Add(sum(x[(st.student_id, s)] for s in options) + slack == 1)
                required_slacks.append(slack)
                required_slack_meta.append((st.student_id, cid))
            else:
                model.Add(sum(x[(st.student_id, s)] for s in options) <= 1)

        for cid in rank2_courses:
            options = student_course_sections.get((st.student_id, cid), [])
            if not options:
                continue
            model.Add(sum(x[(st.student_id, s)] for s in options) <= 1)

        # If a student has BOTH a rank-1 and a rank-2 request for the SAME course
        # (alternates), grant at most one. Cross-course "at most 1 elective total"
        # is not enforced — students typically request electives across multiple
        # departments and want all of them, not just one.
        rank1_by_course: dict[str, list] = {r.course_id: r for r in st.requested_courses if r.rank == 1}
        for r2 in st.requested_courses:
            if r2.rank != 2:
                continue
            if r2.course_id in rank1_by_course:
                # Same course requested at both ranks — at most one wins
                opts1 = student_course_sections.get((st.student_id, r2.course_id), [])
                if opts1:
                    model.Add(sum(x[(st.student_id, s)] for s in opts1) <= 1)

    # HC: no time conflicts within a student's schedule.
    # Term-aware: sections only conflict if they're concurrent — a yearlong+S1
    # pair conflicts (both occupy the slot in S1), as does yearlong+S2; but an
    # S1 and S2 in the same slot don't (they alternate semesters).
    sections_at_slot: dict[tuple[str, int], list[str]] = defaultdict(list)
    for m in master:
        for (day, block) in m.slots:
            sections_at_slot[(day, block)].append(m.section_id)

    section_term: dict[str, str | None] = {s.section_id: s.term_id for s in ds.sections}

    for st in ds.students:
        for slot, sect_ids in sections_at_slot.items():
            xs_yearlong, xs_s1, xs_s2 = [], [], []
            for sid in sect_ids:
                if (st.student_id, sid) not in x:
                    continue
                t = section_term.get(sid)
                if t == "3601":
                    xs_s1.append(x[(st.student_id, sid)])
                elif t == "3602":
                    xs_s2.append(x[(st.student_id, sid)])
                else:
                    xs_yearlong.append(x[(st.student_id, sid)])
            for term_part in (xs_yearlong + xs_s1, xs_yearlong + xs_s2):
                if len(term_part) >= 2:
                    model.Add(sum(term_part) <= 1)

    # HC: section capacity
    student_ids = {sid for sid, _ in x.keys()}
    for s in ds.sections:
        terms = [x[(stu_id, s.section_id)] for stu_id in student_ids if (stu_id, s.section_id) in x]
        if terms:
            model.Add(sum(terms) <= s.max_size)

    # HC: separation codes
    if ds.config.hard.enforce_separations:
        for a, b in ds.behavior.separations:
            for s in ds.sections:
                ka, kb = (a, s.section_id), (b, s.section_id)
                if ka in x and kb in x:
                    model.Add(x[ka] + x[kb] <= 1)

    # === Build objective expressions (used by both single and lexmin modes) ===

    # 1. First-choice electives: count of granted rank-1 non-required requests
    elective_grants: list[cp_model.BoolVar] = []
    for st in ds.students:
        for r in st.requested_courses:
            if r.rank != 1 or r.is_required:
                continue
            for sid in student_course_sections.get((st.student_id, r.course_id), []):
                elective_grants.append(x[(st.student_id, sid)])
    n_elective_max = len(elective_grants)
    electives_obj = model.NewIntVar(0, n_elective_max, "electives_obj")
    if elective_grants:
        model.Add(electives_obj == sum(elective_grants))
    else:
        model.Add(electives_obj == 0)

    # 2. Balance: HARD constraint per course — max(enrollment) - min(enrollment) ≤ K
    enrollment_vars: dict[str, cp_model.IntVar] = {}
    for sid in {s.section_id for s in ds.sections}:
        enr = model.NewIntVar(0, sections_by_id[sid].max_size, f"enr_{sid}")
        terms = [x[(stu_id, sid)] for stu_id in student_ids if (stu_id, sid) in x]
        if terms:
            model.Add(enr == sum(terms))
        else:
            model.Add(enr == 0)
        enrollment_vars[sid] = enr

    spread_cap = ds.config.hard.max_section_spread_per_course
    min_sects = ds.config.hard.min_sections_for_balance
    spread_terms: list[cp_model.IntVar] = []  # used by single-pass soft balance
    for cid, sect_list in sections_by_course.items():
        if len(sect_list) < min_sects:
            continue
        cap = max(sections_by_id[sid].max_size for sid in sect_list)
        max_e = model.NewIntVar(0, cap, f"max_enr_{cid}")
        min_e = model.NewIntVar(0, cap, f"min_enr_{cid}")
        sec_enrollments = [enrollment_vars[sid] for sid in sect_list]
        model.AddMaxEquality(max_e, sec_enrollments)
        model.AddMinEquality(min_e, sec_enrollments)
        # Hard cap (loose) + soft term (tightens within the cap)
        model.Add(max_e - min_e <= spread_cap)
        spread = model.NewIntVar(0, spread_cap, f"spread_{cid}")
        model.Add(spread == max_e - min_e)
        spread_terms.append(spread)
    balance_obj = model.NewIntVar(0, max(1, spread_cap * max(1, len(spread_terms))), "balance_obj")
    if spread_terms:
        model.Add(balance_obj == sum(spread_terms))
    else:
        model.Add(balance_obj == 0)

    # 3. Groupings: count of pairs that share a section
    grouping_grants: list[cp_model.BoolVar] = []
    for a, b in ds.behavior.groupings:
        for s in ds.sections:
            ka, kb = (a, s.section_id), (b, s.section_id)
            if ka in x and kb in x:
                both = model.NewBoolVar(f"grp_{a}_{b}_{s.section_id}")
                model.AddBoolAnd([x[ka], x[kb]]).OnlyEnforceIf(both)
                model.AddBoolOr([x[ka].Not(), x[kb].Not()]).OnlyEnforceIf(both.Not())
                grouping_grants.append(both)
    n_grouping_max = len(grouping_grants)
    grouping_obj = model.NewIntVar(0, n_grouping_max, "grouping_obj")
    if grouping_grants:
        model.Add(grouping_obj == sum(grouping_grants))
    else:
        model.Add(grouping_obj == 0)

    # 4. Required-course coverage: weighted count of unmet required requests.
    #
    # School policy 2026-04-29: prioritize satisfying older grades first
    # ("primero los de 12, luego los de 11, luego los de 10, por último los
    # de 9"). We implement this by weighting each unmet slack by a per-grade
    # factor. Weights are heavy enough that the solver always prefers to
    # satisfy a higher-grade student over a lower one in the typical case
    # (single-swap), without overflowing int64 when multiplied by the
    # downstream `coverage_weight` (~10^4). Strict lex across all 4 grades
    # would need weights up to 10^16 which exceeds int64 once multiplied;
    # this configuration is "very strong bias" not pure lex.
    GRADE_PRIORITY_WEIGHTS = {12: 10**6, 11: 10**4, 10: 10**2, 9: 1}
    grade_by_student = {s.student_id: s.grade for s in ds.students}

    weighted_slack_terms: list[cp_model.LinearExpr] = []
    upper_bound = 0
    for slack, (sid, _) in zip(required_slacks, required_slack_meta):
        g = grade_by_student.get(sid, 9)
        w = GRADE_PRIORITY_WEIGHTS.get(g, 1)
        weighted_slack_terms.append(slack * w)
        upper_bound += w

    n_slack_max = max(1, len(required_slacks))
    unmet_required_obj = model.NewIntVar(0, max(1, upper_bound), "unmet_required_obj")
    if weighted_slack_terms:
        model.Add(unmet_required_obj == sum(weighted_slack_terms))
    else:
        model.Add(unmet_required_obj == 0)

    # === Solve ===
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 4
    if verbose:
        solver.parameters.log_search_progress = False  # set True if you want raw progress

    if mode == "single":
        # Single-pass weighted-sum: maximize electives + groupings, minimize balance spread
        # AND minimize unmet required requests (heavily weighted so coverage dominates).
        soft = ds.config.soft
        # Coverage already carries grade-priority weights up to ~10^12 per slack
        # (see GRADE_PRIORITY_WEIGHTS above). The G9 weight = 1, so coverage
        # of a single G9 unmet must still outrank ALL the soft-objective payoffs
        # combined — that's the role of `coverage_weight` here. Keep it bounded
        # so multiplying by the upper-bound of unmet_required_obj stays inside
        # int64 (cap at 10**4 since grade weights already carry the lex order).
        coverage_weight = max(
            10000,
            10 * (soft.first_choice_electives * n_elective_max
                  + soft.grouping_codes * n_grouping_max
                  + soft.balance_class_sizes * (spread_cap * max(1, len(spread_terms))))
        )
        weighted = (
            soft.first_choice_electives * electives_obj
            + soft.grouping_codes * grouping_obj
            - soft.balance_class_sizes * balance_obj
            - coverage_weight * unmet_required_obj
        )
        model.Maximize(weighted)
        solver.parameters.max_time_in_seconds = time_limit_s
        t0 = time.time()
        status = solver.Solve(model)
        elapsed = time.time() - t0
        status_name = solver.StatusName(status)
        if verbose:
            print(f"Single-pass: {status_name} in {elapsed:.2f}s")
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                print(f"  electives={solver.Value(electives_obj)}/{n_elective_max}, "
                      f"balance_spread={solver.Value(balance_obj)}, "
                      f"groupings={solver.Value(grouping_obj)}/{n_grouping_max}, "
                      f"unmet_required={solver.Value(unmet_required_obj)}/{len(required_slacks)}")
    else:
        # Two-phase lex-min: electives → groupings (balance is hard).
        # Allocate 60% / 40% of total budget.
        t0 = time.time()
        p1_budget = max(30.0, time_limit_s * 0.60)
        p2_budget = max(20.0, time_limit_s * 0.40)
        last_good_x: dict[tuple[str, str], int] | None = None
        status_name = "UNKNOWN"

        def _snapshot(s: cp_model.CpSolver) -> dict[tuple[str, str], int]:
            return {key: int(s.Value(var)) for key, var in x.items()}

        def _hint(snap: dict[tuple[str, str], int]) -> None:
            for key, val in snap.items():
                model.AddHint(x[key], val)

        # Phase 1: maximize electives
        model.Maximize(electives_obj)
        solver.parameters.max_time_in_seconds = p1_budget
        status = solver.Solve(model)
        status_name = solver.StatusName(status)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return [], [], solver, status_name
        v_elect = int(solver.Value(electives_obj))
        last_good_x = _snapshot(solver)
        if verbose:
            print(f"  Phase 1 (electives): {status_name}, value={v_elect}/{n_elective_max} in {time.time()-t0:.1f}s")

        # Phase 2: lock electives, maximize groupings
        model.Add(electives_obj >= v_elect)
        _clear_objective(model)
        _hint(last_good_x)  # warm-start from phase-1 solution
        model.Maximize(grouping_obj)
        solver.parameters.max_time_in_seconds = p2_budget
        t1 = time.time()
        status = solver.Solve(model)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            last_good_x = _snapshot(solver)
            v_grp = int(solver.Value(grouping_obj))
            status_name = solver.StatusName(status)
            if verbose:
                print(f"  Phase 2 (groupings): {status_name}, value={v_grp}/{n_grouping_max} in {time.time()-t1:.1f}s")
        elif verbose:
            print(f"  Phase 2 (groupings): {solver.StatusName(status)} — using phase-1 solution")

        elapsed = time.time() - t0
        if verbose:
            print(f"Lex-min total: {elapsed:.2f}s")

        # Use the last good solution snapshot for extraction
        by_student: dict[str, list[str]] = defaultdict(list)
        for (stu, sec), val in (last_good_x or {}).items():
            if val == 1:
                by_student[stu].append(sec)
        # Skip the generic-extract block below
        assignments = [StudentAssignment(student_id=sid, section_ids=sorted(secs)) for sid, secs in by_student.items()]
        unmet: list[tuple[str, str]] = []
        for st in ds.students:
            granted_courses = {sections_by_id[sec].course_id for sec in by_student.get(st.student_id, [])}
            for r in st.requested_courses:
                if r.rank != 1:
                    continue
                if r.course_id not in granted_courses:
                    unmet.append((st.student_id, r.course_id))
        if verbose:
            print(f"Result: {status_name}, {len(assignments)} students placed, unmet rank-1: {len(unmet)}")
        return assignments, unmet, solver, status_name

    # === Single-mode extraction ===
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], [], solver, status_name

    by_student: dict[str, list[str]] = defaultdict(list)
    for (stu, sec), var in x.items():
        if solver.Value(var) == 1:
            by_student[stu].append(sec)

    assignments = [StudentAssignment(student_id=sid, section_ids=sorted(secs)) for sid, secs in by_student.items()]

    unmet: list[tuple[str, str]] = []
    for st in ds.students:
        granted_courses = {sections_by_id[sec].course_id for sec in by_student.get(st.student_id, [])}
        for r in st.requested_courses:
            if r.rank != 1:
                continue
            if r.course_id not in granted_courses:
                unmet.append((st.student_id, r.course_id))

    if verbose:
        print(f"Result: {status_name}, {len(assignments)} students placed, unmet rank-1: {len(unmet)}")

    return assignments, unmet, solver, status_name


if __name__ == "__main__":
    from .sample_data import make_grade_12_dataset
    from .master_solver import solve_master

    ds = make_grade_12_dataset()
    print(f"Stage 1: master schedule for {len(ds.sections)} sections...")
    master, _, status = solve_master(ds, time_limit_s=30)
    print(f"  -> {status}, {len(master)} assigned")

    print(f"Stage 2 (lex-min): student assignment for {len(ds.students)} students...")
    students, unmet, _, status = solve_students(ds, master, time_limit_s=180, mode="lexmin", verbose=True)
    print(f"  -> {status}")
    print(f"  Students placed: {len(students)}/{len(ds.students)}")
    print(f"  Unmet rank-1 requests: {len(unmet)}")
    if unmet:
        from collections import Counter
        by_course = Counter(c for _, c in unmet)
        print(f"  Unmet by course: {dict(by_course.most_common(10))}")
