#!/usr/bin/env python3
"""
Two-phase OR-Tools CP-SAT solver for HS scheduling.
Phase 1: Assign ONLY hub students (>=3 together partners)
Phase 2: Fix hub assignments and solve ALL remaining students
"""

import csv
from collections import defaultdict
from ortools.sat.python import cp_model


def load_data():
    """Load all data files."""
    data = {}

    # Students
    data['students'] = {}
    with open('data/students.csv') as f:
        for row in csv.DictReader(f):
            data['students'][row['student_external_id']] = {
                'name': row['student_name'],
                'grade': int(row['grade'])
            }

    # Courses
    data['courses'] = {}
    with open('data/courses.csv') as f:
        for row in csv.DictReader(f):
            data['courses'][row['course_id']] = {'name': row['name']}

    # Sections
    data['sections'] = {}
    data['sections_by_course'] = defaultdict(list)
    with open('data/sections.csv') as f:
        for row in csv.DictReader(f):
            sec_id = row['section_id']
            data['sections'][sec_id] = {
                'course_id': row['course_id'],
                'teacher_id': row['teacher_id'],
                'room_id': row['room_id'],
                'max_size': int(row['max_size']) if row['max_size'] else 25,
                'slots': row['slots'],
                'slots_set': set(row['slots'].split(';')) if row['slots'] else set()
            }
            data['sections_by_course'][row['course_id']].append(sec_id)

    # Teachers
    data['teachers'] = {}
    with open('data/teachers.csv') as f:
        for row in csv.DictReader(f):
            data['teachers'][row['teacher_id']] = row['teacher_name']

    # Rooms
    data['rooms'] = {}
    with open('data/rooms.csv') as f:
        for row in csv.DictReader(f):
            data['rooms'][row['room_id']] = row.get('name', '')

    # Requests
    data['requests'] = defaultdict(dict)
    with open('data/course_requests.csv') as f:
        for row in csv.DictReader(f):
            data['requests'][row['student_external_id']][row['course_id']] = {
                'is_required': row.get('is_required', '0') == '1'
            }

    # Term pairs
    data['term_pairs'] = set()
    with open('data/course_relationships.csv') as f:
        for row in csv.DictReader(f):
            if row['relationship_code'] == 'Term':
                data['term_pairs'].add(tuple(sorted([row['course_a_id'], row['course_b_id']])))

    # Course name to id lookup
    data['course_name_to_id'] = {}
    for cid, cdata in data['courses'].items():
        data['course_name_to_id'][cdata['name']] = cid

    # Teacher assistants
    data['ta_assignments'] = defaultdict(dict)
    with open('data/teacher_assistants.csv') as f:
        for row in csv.DictReader(f):
            course_name = row['target_course_name']
            course_id = data['course_name_to_id'].get(course_name)
            if course_id:
                data['ta_assignments'][row['student_external_id']][course_id] = row['target_teacher_id']

    # Teacher avoid
    data['teacher_avoid'] = defaultdict(set)
    with open('data/teacher_avoid.csv') as f:
        for row in csv.DictReader(f):
            student_id = row['student_external_id']
            teacher_id = row['teacher_id']
            if teacher_id:
                data['teacher_avoid'][student_id].add(teacher_id)

    # Student pair constraints
    data['separate_pairs'] = set()
    data['together_pairs'] = set()
    data['together_graph'] = defaultdict(set)
    with open('data/student_pair_constraints.csv') as f:
        for row in csv.DictReader(f):
            a, b = row['student_a_external_id'], row['student_b_external_id']
            pair = tuple(sorted([a, b]))
            if 'separa' in row['relation'].lower():
                data['separate_pairs'].add(pair)
            elif 'compartir' in row['relation'].lower():
                data['together_pairs'].add(pair)
                data['together_graph'][a].add(b)
                data['together_graph'][b].add(a)

    # Flexibility weights
    FLEX_WEIGHTS = {'A': 1, 'B': 2, 'C': 5, 'D': 50, 'F': 500}
    data['flexibility'] = {}
    with open('data/course_flexibility.csv') as f:
        for row in csv.DictReader(f):
            key = (row['course_id'], row['grade'])
            data['flexibility'][key] = FLEX_WEIGHTS.get(row['flexibility'], 5)

    # Identify hub students (>=3 together partners)
    data['hub_students'] = {sid for sid, partners in data['together_graph'].items() if len(partners) >= 3}

    print(f"Loaded: {len(data['students'])} students, {len(data['sections'])} sections")
    print(f"Hub students (>=3 partners): {len(data['hub_students'])}")
    for hub in sorted(data['hub_students']):
        print(f"  {hub}: {len(data['together_graph'][hub])} partners")

    return data


def is_term_pair(data, c1, c2):
    return tuple(sorted([c1, c2])) in data['term_pairs']


def build_phase1_model(data, hub_students):
    """Build model for hub students only - no together constraints with non-hubs."""
    model = cp_model.CpModel()

    # Decision variables for hub students only
    x = {}
    for sid in hub_students:
        for cid in data['requests'].get(sid, {}):
            for sec_id in data['sections_by_course'].get(cid, []):
                x[sid, sec_id] = model.NewBoolVar(f'x_{sid}_{sec_id}')

    print(f"Phase 1: {len(x)} decision variables for {len(hub_students)} hub students")

    # H7: At most one section per course per student
    for sid in hub_students:
        for cid in data['requests'].get(sid, {}):
            secs = data['sections_by_course'].get(cid, [])
            if secs:
                model.AddAtMostOne(x[sid, sec_id] for sec_id in secs if (sid, sec_id) in x)

    # H2: Section capacity (relaxed - only count hub students)
    for sec_id, sec in data['sections'].items():
        vars_in_sec = [x[sid, sec_id] for sid in hub_students if (sid, sec_id) in x]
        if vars_in_sec:
            model.Add(sum(vars_in_sec) <= sec['max_size'])

    # H1: No double-booking
    for sid in hub_students:
        slot_sections = defaultdict(list)
        for cid in data['requests'].get(sid, {}):
            for sec_id in data['sections_by_course'].get(cid, []):
                if (sid, sec_id) not in x:
                    continue
                for slot in data['sections'][sec_id]['slots_set']:
                    slot_sections[slot].append((sec_id, cid))

        for slot, secs_in_slot in slot_sections.items():
            if len(secs_in_slot) <= 1:
                continue
            for i, (s1, c1) in enumerate(secs_in_slot):
                for s2, c2 in secs_in_slot[i + 1:]:
                    if not is_term_pair(data, c1, c2):
                        model.Add(x[sid, s1] + x[sid, s2] <= 1)

    # H10: TA must go to specific teacher
    for sid in hub_students:
        for target_cid, target_teacher in data['ta_assignments'].get(sid, {}).items():
            if target_cid not in data['requests'].get(sid, {}):
                continue
            for sec_id in data['sections_by_course'].get(target_cid, []):
                if (sid, sec_id) in x:
                    if data['sections'][sec_id]['teacher_id'] != target_teacher:
                        model.Add(x[sid, sec_id] == 0)

    # H11: Teacher avoid
    for sid in hub_students:
        for cid in data['requests'].get(sid, {}):
            for sec_id in data['sections_by_course'].get(cid, []):
                if (sid, sec_id) in x:
                    if data['sections'][sec_id]['teacher_id'] in data['teacher_avoid'].get(sid, set()):
                        model.Add(x[sid, sec_id] == 0)

    # H12: Separate pairs (only between hub students)
    for pair in data['separate_pairs']:
        s1, s2 = pair
        if s1 not in hub_students or s2 not in hub_students:
            continue
        common = set(data['requests'].get(s1, {}).keys()) & set(data['requests'].get(s2, {}).keys())
        for cid in common:
            for sec_id in data['sections_by_course'].get(cid, []):
                if (s1, sec_id) in x and (s2, sec_id) in x:
                    model.Add(x[s1, sec_id] + x[s2, sec_id] <= 1)

    # H12: Together pairs between hub students only
    for pair in data['together_pairs']:
        s1, s2 = pair
        if s1 not in hub_students or s2 not in hub_students:
            continue
        common = set(data['requests'].get(s1, {}).keys()) & set(data['requests'].get(s2, {}).keys())
        for cid in common:
            secs = data['sections_by_course'].get(cid, [])
            for i, sec1 in enumerate(secs):
                for sec2 in secs[i+1:]:
                    v1 = x.get((s1, sec1))
                    v2 = x.get((s2, sec2))
                    if v1 is not None and v2 is not None:
                        model.Add(v1 + v2 <= 1)
                    v1 = x.get((s1, sec2))
                    v2 = x.get((s2, sec1))
                    if v1 is not None and v2 is not None:
                        model.Add(v1 + v2 <= 1)

    # Objective: maximize weighted coverage - VERY high weight for hub students
    objective_terms = []
    for (sid, sec_id), var in x.items():
        cid = data['sections'][sec_id]['course_id']
        grade = str(data['students'][sid]['grade'])
        is_required = data['requests'].get(sid, {}).get(cid, {}).get('is_required', False)
        base = 100000 if is_required else 1000  # Very high weights for hubs
        flex = data['flexibility'].get((cid, grade), 5)
        weight = base * flex
        objective_terms.append(weight * var)
    model.Maximize(sum(objective_terms))

    return model, x


def build_phase2_model(data, remaining_students, fixed_assignments):
    """Build model for remaining students with hub assignments fixed."""
    model = cp_model.CpModel()

    # Count fixed assignments per section for capacity
    fixed_counts = defaultdict(int)
    for sid, assignments in fixed_assignments.items():
        for cid, sec_id in assignments:
            fixed_counts[sec_id] += 1

    # Decision variables for remaining students
    x = {}
    for sid in remaining_students:
        for cid in data['requests'].get(sid, {}):
            for sec_id in data['sections_by_course'].get(cid, []):
                x[sid, sec_id] = model.NewBoolVar(f'x_{sid}_{sec_id}')

    print(f"Phase 2: {len(x)} decision variables for {len(remaining_students)} remaining students")

    # H7: At most one section per course per student
    for sid in remaining_students:
        for cid in data['requests'].get(sid, {}):
            secs = data['sections_by_course'].get(cid, [])
            if secs:
                model.AddAtMostOne(x[sid, sec_id] for sec_id in secs if (sid, sec_id) in x)

    # H2: Section capacity (accounting for fixed hub assignments)
    for sec_id, sec in data['sections'].items():
        vars_in_sec = [x[sid, sec_id] for sid in remaining_students if (sid, sec_id) in x]
        if vars_in_sec:
            remaining_capacity = sec['max_size'] - fixed_counts[sec_id]
            model.Add(sum(vars_in_sec) <= remaining_capacity)

    # H1: No double-booking
    for sid in remaining_students:
        slot_sections = defaultdict(list)
        for cid in data['requests'].get(sid, {}):
            for sec_id in data['sections_by_course'].get(cid, []):
                if (sid, sec_id) not in x:
                    continue
                for slot in data['sections'][sec_id]['slots_set']:
                    slot_sections[slot].append((sec_id, cid))

        for slot, secs_in_slot in slot_sections.items():
            if len(secs_in_slot) <= 1:
                continue
            for i, (s1, c1) in enumerate(secs_in_slot):
                for s2, c2 in secs_in_slot[i + 1:]:
                    if not is_term_pair(data, c1, c2):
                        model.Add(x[sid, s1] + x[sid, s2] <= 1)

    # H10: TA must go to specific teacher
    for sid in remaining_students:
        for target_cid, target_teacher in data['ta_assignments'].get(sid, {}).items():
            if target_cid not in data['requests'].get(sid, {}):
                continue
            for sec_id in data['sections_by_course'].get(target_cid, []):
                if (sid, sec_id) in x:
                    if data['sections'][sec_id]['teacher_id'] != target_teacher:
                        model.Add(x[sid, sec_id] == 0)

    # H11: Teacher avoid
    for sid in remaining_students:
        for cid in data['requests'].get(sid, {}):
            for sec_id in data['sections_by_course'].get(cid, []):
                if (sid, sec_id) in x:
                    if data['sections'][sec_id]['teacher_id'] in data['teacher_avoid'].get(sid, set()):
                        model.Add(x[sid, sec_id] == 0)

    # H12: Separate pairs
    for pair in data['separate_pairs']:
        s1, s2 = pair
        # Between remaining students
        if s1 in remaining_students and s2 in remaining_students:
            common = set(data['requests'].get(s1, {}).keys()) & set(data['requests'].get(s2, {}).keys())
            for cid in common:
                for sec_id in data['sections_by_course'].get(cid, []):
                    if (s1, sec_id) in x and (s2, sec_id) in x:
                        model.Add(x[s1, sec_id] + x[s2, sec_id] <= 1)
        # Between remaining and fixed hub
        for s_rem, s_fixed in [(s1, s2), (s2, s1)]:
            if s_rem in remaining_students and s_fixed in fixed_assignments:
                fixed_secs = {sec for cid, sec in fixed_assignments[s_fixed]}
                common = set(data['requests'].get(s_rem, {}).keys()) & set(data['requests'].get(s_fixed, {}).keys())
                for cid in common:
                    for sec_id in data['sections_by_course'].get(cid, []):
                        if sec_id in fixed_secs and (s_rem, sec_id) in x:
                            model.Add(x[s_rem, sec_id] == 0)

    # H12: Together pairs
    for pair in data['together_pairs']:
        s1, s2 = pair
        # Between remaining students
        if s1 in remaining_students and s2 in remaining_students:
            common = set(data['requests'].get(s1, {}).keys()) & set(data['requests'].get(s2, {}).keys())
            for cid in common:
                secs = data['sections_by_course'].get(cid, [])
                for i, sec1 in enumerate(secs):
                    for sec2 in secs[i+1:]:
                        v1 = x.get((s1, sec1))
                        v2 = x.get((s2, sec2))
                        if v1 is not None and v2 is not None:
                            model.Add(v1 + v2 <= 1)
                        v1 = x.get((s1, sec2))
                        v2 = x.get((s2, sec1))
                        if v1 is not None and v2 is not None:
                            model.Add(v1 + v2 <= 1)

        # Between remaining and fixed hub - remaining must go to hub's section
        for s_rem, s_fixed in [(s1, s2), (s2, s1)]:
            if s_rem in remaining_students and s_fixed in fixed_assignments:
                fixed_by_course = {cid: sec for cid, sec in fixed_assignments[s_fixed]}
                common = set(data['requests'].get(s_rem, {}).keys()) & set(fixed_by_course.keys())
                for cid in common:
                    hub_sec = fixed_by_course[cid]
                    # Remaining student must go to hub's section or not take course
                    for sec_id in data['sections_by_course'].get(cid, []):
                        if sec_id != hub_sec and (s_rem, sec_id) in x:
                            model.Add(x[s_rem, sec_id] == 0)

    # Objective: maximize weighted coverage
    objective_terms = []
    for (sid, sec_id), var in x.items():
        cid = data['sections'][sec_id]['course_id']
        grade = str(data['students'][sid]['grade'])
        is_required = data['requests'].get(sid, {}).get(cid, {}).get('is_required', False)
        base = 10000 if is_required else 1
        flex = data['flexibility'].get((cid, grade), 5)
        weight = base * flex
        objective_terms.append(weight * var)
    model.Maximize(sum(objective_terms))

    return model, x


def solve_twophase(data):
    """Two-phase solving: hubs first (alone), then rest."""
    hub_students = data['hub_students']

    print("\n=== PHASE 1: Solving for hub students ONLY ===")
    print(f"Hub students: {sorted(hub_students)}")

    model1, x1 = build_phase1_model(data, hub_students)

    solver1 = cp_model.CpSolver()
    solver1.parameters.max_time_in_seconds = 120
    solver1.parameters.num_workers = 8

    status1 = solver1.Solve(model1)
    if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"Phase 1 failed: {solver1.StatusName(status1)}")
        return []

    hub_assignments = defaultdict(list)
    for (sid, sec_id), var in x1.items():
        if solver1.Value(var):
            cid = data['sections'][sec_id]['course_id']
            hub_assignments[sid].append((cid, sec_id))

    hub_assigned_count = sum(len(a) for a in hub_assignments.values())
    hub_total_requests = sum(len(data['requests'].get(sid, {})) for sid in hub_students)
    print(f"Phase 1: {hub_assigned_count}/{hub_total_requests} courses assigned to {len(hub_assignments)} hub students")

    # Show hub assignments
    for sid in sorted(hub_students):
        reqs = len(data['requests'].get(sid, {}))
        assigned = len(hub_assignments.get(sid, []))
        print(f"  {sid}: {assigned}/{reqs} courses")

    print("\n=== PHASE 2: Solving for remaining students ===")
    remaining_students = set(data['students'].keys()) - hub_students
    print(f"Remaining students: {len(remaining_students)}")

    model2, x2 = build_phase2_model(data, remaining_students, hub_assignments)

    solver2 = cp_model.CpSolver()
    solver2.parameters.max_time_in_seconds = 300
    solver2.parameters.num_workers = 8

    status2 = solver2.Solve(model2)
    if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"Phase 2 failed: {solver2.StatusName(status2)}")
        # Still return hub assignments
        return [(sid, sec_id) for sid, assigns in hub_assignments.items() for cid, sec_id in assigns]

    # Merge assignments
    all_assignments = []
    for sid, assigns in hub_assignments.items():
        for cid, sec_id in assigns:
            all_assignments.append((sid, sec_id))
    for (sid, sec_id), var in x2.items():
        if solver2.Value(var):
            all_assignments.append((sid, sec_id))

    return all_assignments


def export_csv(data, assignments, output_path):
    """Export to 12-column friendly CSV."""
    period_map = {}
    pn = 1
    for sec_id, sec in data['sections'].items():
        if sec['slots'] not in period_map:
            period_map[sec['slots']] = pn
            pn += 1

    rows = []
    for sid, sec_id in assignments:
        sec = data['sections'][sec_id]
        student = data['students'][sid]
        course = data['courses'].get(sec['course_id'], {})

        rows.append({
            'StudentID': sid,
            'StudentName': student['name'],
            'Grade': student['grade'],
            'CourseID': sec['course_id'],
            'CourseName': course.get('name', ''),
            'SectionID': sec_id,
            'Period': period_map.get(sec['slots'], 0),
            'Slots': sec['slots'],
            'TeacherID': sec['teacher_id'],
            'TeacherName': data['teachers'].get(sec['teacher_id'], ''),
            'RoomID': sec['room_id'],
            'RoomName': data['rooms'].get(sec['room_id'], '')
        })

    rows.sort(key=lambda r: (r['StudentID'], r['CourseID']))

    fieldnames = ['StudentID', 'StudentName', 'Grade', 'CourseID', 'CourseName',
                  'SectionID', 'Period', 'Slots', 'TeacherID', 'TeacherName',
                  'RoomID', 'RoomName']

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Stats
    total_requests = sum(len(r) for r in data['requests'].values())
    coverage = len(assignments) / total_requests * 100 if total_requests else 0

    student_courses = defaultdict(set)
    for sid, sec_id in assignments:
        student_courses[sid].add(data['sections'][sec_id]['course_id'])

    missing_req = 0
    for sid, reqs in data['requests'].items():
        for cid, rdata in reqs.items():
            if rdata['is_required'] and cid not in student_courses[sid]:
                missing_req += 1

    students_complete = sum(1 for sid in data['students']
                          if len(student_courses[sid]) >= len(data['requests'].get(sid, {})))

    print(f"\nExported {len(assignments)} assignments to {output_path}")
    print(f"Coverage: {len(assignments)}/{total_requests} = {coverage:.2f}%")
    print(f"Missing required: {missing_req}")
    print(f"Students complete: {students_complete}/{len(data['students'])} = "
          f"{students_complete / len(data['students']) * 100:.2f}%")


def main():
    print("=== Two-Phase OR-Tools Solver v2 (Hub-Only Phase 1) ===\n")

    data = load_data()
    print()

    assignments = solve_twophase(data)
    print(f"\nTotal assignments: {len(assignments)}")

    export_csv(data, assignments, 'student_schedules_friendly.csv')


if __name__ == '__main__':
    main()
