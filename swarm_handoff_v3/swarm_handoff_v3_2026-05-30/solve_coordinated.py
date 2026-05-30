#!/usr/bin/env python3
"""
Coordinated OR-Tools CP-SAT solver for HS scheduling.
Uses auxiliary variables to track "together group" section choices
and heavily penalizes leaving hub students unassigned.
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
    data['teacher_name_to_id'] = {}
    with open('data/teachers.csv') as f:
        for row in csv.DictReader(f):
            data['teachers'][row['teacher_id']] = row['teacher_name']
            data['teacher_name_to_id'][row['teacher_name']] = row['teacher_id']

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

    # Build course name to id lookup
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

    # Identify hub students
    data['hub_students'] = {sid for sid, partners in data['together_graph'].items() if len(partners) >= 3}

    # Build together groups (connected components)
    visited = set()
    data['together_groups'] = []
    for start in data['together_graph']:
        if start in visited:
            continue
        group = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            group.add(node)
            stack.extend(data['together_graph'][node])
        if len(group) > 1:
            data['together_groups'].append(group)

    print(f"Loaded: {len(data['students'])} students, {len(data['sections'])} sections, "
          f"{len(data['courses'])} courses")
    print(f"Requests: {sum(len(r) for r in data['requests'].values())}")
    print(f"Hub students: {len(data['hub_students'])}")
    print(f"Together groups: {len(data['together_groups'])} groups")
    for i, g in enumerate(data['together_groups']):
        print(f"  Group {i}: {len(g)} students")

    return data


def is_term_pair(data, c1, c2):
    return tuple(sorted([c1, c2])) in data['term_pairs']


def solve(data):
    """Build and solve CP-SAT model with coordinated together constraints."""
    model = cp_model.CpModel()

    # Decision variables: x[student, section] = 1 if assigned
    x = {}
    for sid in data['students']:
        for cid in data['requests'].get(sid, {}):
            for sec_id in data['sections_by_course'].get(cid, []):
                x[sid, sec_id] = model.NewBoolVar(f'x_{sid}_{sec_id}')

    print(f"Created {len(x)} decision variables")

    # H7: At most one section per course per student
    for sid in data['students']:
        for cid in data['requests'].get(sid, {}):
            secs = data['sections_by_course'].get(cid, [])
            if secs:
                model.AddAtMostOne(x[sid, sec_id] for sec_id in secs if (sid, sec_id) in x)

    # H2: Section capacity
    for sec_id, sec in data['sections'].items():
        vars_in_sec = [x[sid, sec_id] for sid in data['students'] if (sid, sec_id) in x]
        if vars_in_sec:
            model.Add(sum(vars_in_sec) <= sec['max_size'])

    # H1: No double-booking (with term pair exception)
    for sid in data['students']:
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
    for sid, ta_courses in data['ta_assignments'].items():
        for target_cid, target_teacher in ta_courses.items():
            if target_cid not in data['requests'].get(sid, {}):
                continue
            for sec_id in data['sections_by_course'].get(target_cid, []):
                if (sid, sec_id) in x:
                    if data['sections'][sec_id]['teacher_id'] != target_teacher:
                        model.Add(x[sid, sec_id] == 0)

    # H11: Teacher avoid
    for sid, avoided_teachers in data['teacher_avoid'].items():
        for cid in data['requests'].get(sid, {}):
            for sec_id in data['sections_by_course'].get(cid, []):
                if (sid, sec_id) in x:
                    if data['sections'][sec_id]['teacher_id'] in avoided_teachers:
                        model.Add(x[sid, sec_id] == 0)

    # H12: Separate pairs
    for pair in data['separate_pairs']:
        s1, s2 = pair
        common = set(data['requests'].get(s1, {}).keys()) & set(data['requests'].get(s2, {}).keys())
        for cid in common:
            for sec_id in data['sections_by_course'].get(cid, []):
                if (s1, sec_id) in x and (s2, sec_id) in x:
                    model.Add(x[s1, sec_id] + x[s2, sec_id] <= 1)

    # H12: Together pairs - use original pairwise constraints
    for pair in data['together_pairs']:
        s1, s2 = pair
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

    # Objective: maximize weighted coverage
    # Give MASSIVE weight to hub students with required courses
    # Also penalize uneven partner assignments
    objective_terms = []

    for (sid, sec_id), var in x.items():
        cid = data['sections'][sec_id]['course_id']
        grade = str(data['students'][sid]['grade'])
        is_required = data['requests'].get(sid, {}).get(cid, {}).get('is_required', False)

        # Base weight
        base = 10000 if is_required else 1

        # Flexibility weight
        flex = data['flexibility'].get((cid, grade), 5)

        # Hub multiplier - VERY high for hub students
        if sid in data['hub_students']:
            hub_mult = 1000  # Massive boost for hub students
        else:
            hub_mult = 1

        weight = base * flex * hub_mult
        objective_terms.append(weight * var)

    # Add coordination bonus: if hub and ALL partners take same section, bonus
    # This encourages coordinated placement
    for group in data['together_groups']:
        hubs_in_group = group & data['hub_students']
        if not hubs_in_group:
            continue

        # For each course that multiple group members share
        group_list = list(group)
        for cid in data['courses']:
            members_with_course = [s for s in group_list if cid in data['requests'].get(s, {})]
            if len(members_with_course) < 2:
                continue

            for sec_id in data['sections_by_course'].get(cid, []):
                vars_in_sec = [x[s, sec_id] for s in members_with_course if (s, sec_id) in x]
                if len(vars_in_sec) >= 2:
                    # Bonus for placing multiple group members together
                    bonus = model.NewBoolVar(f'bonus_{cid}_{sec_id}_group')
                    # bonus = 1 if at least 2 members in same section
                    model.Add(sum(vars_in_sec) >= 2).OnlyEnforceIf(bonus)
                    model.Add(sum(vars_in_sec) < 2).OnlyEnforceIf(bonus.Not())
                    objective_terms.append(5000 * bonus)  # Good bonus for coordination

    model.Maximize(sum(objective_terms))

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 600
    solver.parameters.num_workers = 16

    print("Solving (max 600s)...")
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"Solver failed: {solver.StatusName(status)}")
        return []

    print(f"Status: {solver.StatusName(status)}")

    assignments = []
    for (sid, sec_id), var in x.items():
        if solver.Value(var):
            assignments.append((sid, sec_id))

    return assignments


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
    missing_details = []
    for sid, reqs in data['requests'].items():
        for cid, rdata in reqs.items():
            if rdata['is_required'] and cid not in student_courses[sid]:
                missing_req += 1
                missing_details.append((sid, cid))

    students_complete = sum(1 for sid in data['students']
                          if len(student_courses[sid]) >= len(data['requests'].get(sid, {})))

    print(f"\nExported {len(assignments)} assignments to {output_path}")
    print(f"Coverage: {len(assignments)}/{total_requests} = {coverage:.2f}%")
    print(f"Missing required: {missing_req}")
    if missing_details:
        print("Missing required courses:")
        for sid, cid in sorted(missing_details)[:20]:
            is_hub = "HUB" if sid in data['hub_students'] else ""
            print(f"  {sid} {is_hub}: {cid}")
    print(f"Students complete: {students_complete}/{len(data['students'])} = "
          f"{students_complete / len(data['students']) * 100:.2f}%")


def main():
    print("=== Coordinated OR-Tools CP-SAT Solver ===\n")

    data = load_data()
    print()

    assignments = solve(data)
    print(f"\nSolver found {len(assignments)} assignments")

    export_csv(data, assignments, 'student_schedules_friendly.csv')


if __name__ == '__main__':
    main()
