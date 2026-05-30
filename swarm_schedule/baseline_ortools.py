#!/usr/bin/env python3
"""
OR-Tools CP-SAT baseline for comparison with Rust constraint engine.

This implements the same student scheduling problem using OR-Tools to
establish a baseline for the swarm experiment.
"""

import csv
import time
from collections import defaultdict
from pathlib import Path

from ortools.sat.python import cp_model


def load_data(data_dir: Path):
    """Load all data files."""
    data = {
        'sections': {},
        'sections_by_course': defaultdict(list),
        'students': {},
        'term_pairs': [],
        'separate_pairs': [],
    }

    # Load sections
    with open(data_dir / 'sections.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            section_id = row['section_id']
            slots = set(row['slots'].split(';')) if row['slots'] else set()
            slots.discard('')
            data['sections'][section_id] = {
                'course_id': row['course_id'],
                'teacher_id': int(row['teacher_id']) if row['teacher_id'] else 0,
                'max_size': int(row['max_size']),
                'slots': slots,
            }
            data['sections_by_course'][row['course_id']].append(section_id)

    # Load course requests
    with open(data_dir / 'course_requests.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            student_id = row['student_external_id']
            course_id = row['course_id']
            is_required = row.get('is_required', '0') == '1'

            if student_id not in data['students']:
                data['students'][student_id] = {
                    'requests': set(),
                    'required': set(),
                }

            data['students'][student_id]['requests'].add(course_id)
            if is_required:
                data['students'][student_id]['required'].add(course_id)

    # Load course relationships
    with open(data_dir / 'course_relationships.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['relationship_code'] == 'Term':
                data['term_pairs'].append((row['course_a_id'], row['course_b_id']))

    # Load student pair constraints
    with open(data_dir / 'student_pair_constraints.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if 'separate' in row['relation'].lower():
                student_a = str(int(float(row['student_a_id'])))
                student_b = str(int(float(row['student_b_id'])))
                data['separate_pairs'].append((student_a, student_b))

    # Apply request changes
    try:
        with open(data_dir / 'student_requests_changes.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                student_id = str(row['student_number'])
                course_id = row['course_number']
                action = row['action']
                if student_id in data['students']:
                    if action == 'add':
                        data['students'][student_id]['requests'].add(course_id)
                    elif action == 'drop':
                        data['students'][student_id]['requests'].discard(course_id)
                        data['students'][student_id]['required'].discard(course_id)
    except FileNotFoundError:
        pass

    print(f"Loaded {len(data['sections'])} sections")
    print(f"Loaded {len(data['students'])} students")
    print(f"Loaded {len(data['term_pairs'])} term pairs")
    print(f"Loaded {len(data['separate_pairs'])} separate pairs")

    return data


def is_term_pair(data, course_a, course_b):
    """Check if two courses are a term pair."""
    for a, b in data['term_pairs']:
        if (course_a == a and course_b == b) or (course_a == b and course_b == a):
            return True
    return False


def solve_with_ortools(data, time_limit_seconds=60):
    """Solve the scheduling problem with OR-Tools CP-SAT."""
    model = cp_model.CpModel()

    # Decision variables: x[student, section] = 1 if student assigned to section
    x = {}
    for student_id, student in data['students'].items():
        for course_id in student['requests']:
            for section_id in data['sections_by_course'].get(course_id, []):
                x[student_id, section_id] = model.NewBoolVar(f'x_{student_id}_{section_id}')

    print(f"Created {len(x)} decision variables")

    # Constraint: One section per course per student (H7)
    for student_id, student in data['students'].items():
        for course_id in student['requests']:
            sections = data['sections_by_course'].get(course_id, [])
            if sections:
                model.AddAtMostOne(
                    x[student_id, sid] for sid in sections
                    if (student_id, sid) in x
                )

    # Constraint: Section capacity (H2)
    for section_id, section in data['sections'].items():
        students_in_section = [
            x[sid, section_id]
            for sid in data['students']
            if (sid, section_id) in x
        ]
        if students_in_section:
            model.Add(sum(students_in_section) <= section['max_size'])

    # Constraint: No double-booking (H1) with term pair exception
    for student_id, student in data['students'].items():
        # Group sections by slot
        slot_sections = defaultdict(list)
        for course_id in student['requests']:
            for section_id in data['sections_by_course'].get(course_id, []):
                if (student_id, section_id) not in x:
                    continue
                section = data['sections'][section_id]
                for slot in section['slots']:
                    slot_sections[slot].append((section_id, course_id))

        # For each slot, at most one section (with term pair exception)
        for slot, sections_in_slot in slot_sections.items():
            if len(sections_in_slot) <= 1:
                continue

            # Group by term pair relationships
            for i, (sid_i, cid_i) in enumerate(sections_in_slot):
                for j, (sid_j, cid_j) in enumerate(sections_in_slot[i + 1:], i + 1):
                    if not is_term_pair(data, cid_i, cid_j):
                        # Can't both be assigned
                        model.Add(x[student_id, sid_i] + x[student_id, sid_j] <= 1)

    # Constraint: Separate pairs (H12)
    for student_a, student_b in data['separate_pairs']:
        if student_a not in data['students'] or student_b not in data['students']:
            continue

        # Find common courses
        courses_a = data['students'][student_a]['requests']
        courses_b = data['students'][student_b]['requests']
        common_courses = courses_a & courses_b

        for course_id in common_courses:
            sections = data['sections_by_course'].get(course_id, [])
            for section_id in sections:
                if (student_a, section_id) in x and (student_b, section_id) in x:
                    # Can't both be in same section
                    model.Add(x[student_a, section_id] + x[student_b, section_id] <= 1)

    # Objective: Maximize assignments (coverage)
    model.Maximize(sum(x.values()))

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_workers = 4

    print(f"\nSolving with {time_limit_seconds}s time limit...")
    start_time = time.time()
    status = solver.Solve(model)
    solve_time = time.time() - start_time

    # Extract results
    assignments = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (student_id, section_id), var in x.items():
            if solver.Value(var):
                assignments.append((student_id, section_id))

    total_requests = sum(len(s['requests']) for s in data['students'].values())
    coverage = len(assignments) / total_requests if total_requests else 0

    return {
        'status': solver.StatusName(status),
        'assignments': assignments,
        'coverage': coverage,
        'solve_time_ms': int(solve_time * 1000),
        'total_requests': total_requests,
    }


def main():
    data_dir = Path(__file__).parent / 'data'

    print("=== OR-Tools CP-SAT Baseline ===\n")

    data = load_data(data_dir)
    print()

    result = solve_with_ortools(data, time_limit_seconds=30)

    print(f"\n=== Results ===")
    print(f"Status: {result['status']}")
    print(f"Assignments: {len(result['assignments'])}")
    print(f"Coverage: {result['coverage'] * 100:.1f}%")
    print(f"Solve time: {result['solve_time_ms']}ms")

    # Export
    output_path = data_dir.parent / 'student_schedules_ortools.csv'
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['StudentID', 'SectionID'])
        for student_id, section_id in result['assignments']:
            writer.writerow([student_id, section_id])

    print(f"\nExported to {output_path}")


if __name__ == '__main__':
    main()
