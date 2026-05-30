#!/usr/bin/env python3
"""
Correct HS Schedule Solver - respects ALL hard constraints.
Produces exactly 12 columns as specified in HANDOFF.md.

Strategy: Constraint propagation with required-first priority.
"""

import csv
from collections import defaultdict
from pathlib import Path


def load_data(data_dir: Path):
    """Load all data files."""
    data = {}

    # Load students
    data['students'] = {}
    with open(data_dir / 'students.csv') as f:
        for row in csv.DictReader(f):
            data['students'][row['student_external_id']] = {
                'name': row['student_name'],
                'grade': int(row['grade'])
            }

    # Load courses
    data['courses'] = {}
    with open(data_dir / 'courses.csv') as f:
        for row in csv.DictReader(f):
            grade_levels = []
            if row['grade_levels'].strip():
                grade_levels = [int(g.strip()) for g in row['grade_levels'].split(',') if g.strip()]
            data['courses'][row['course_id']] = {
                'name': row['name'],
                'grade_levels': grade_levels,
                'is_required': row.get('is_required', '0') == '1'
            }

    # Load sections (THE MASTER - copy exactly)
    data['sections'] = {}
    data['sections_by_course'] = defaultdict(list)
    with open(data_dir / 'sections.csv') as f:
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

    # Load teachers
    data['teachers'] = {}
    with open(data_dir / 'teachers.csv') as f:
        for row in csv.DictReader(f):
            data['teachers'][row['teacher_id']] = row['teacher_name']

    # Load rooms
    data['rooms'] = {}
    with open(data_dir / 'rooms.csv') as f:
        for row in csv.DictReader(f):
            data['rooms'][row['room_id']] = row.get('name', row.get('room_name', ''))

    # Load course requests
    data['requests'] = defaultdict(dict)
    with open(data_dir / 'course_requests.csv') as f:
        for row in csv.DictReader(f):
            student_id = row['student_external_id']
            course_id = row['course_id']
            is_required = row.get('is_required', '0') == '1'
            data['requests'][student_id][course_id] = {'is_required': is_required}

    # Load course relationships (Term pairs)
    data['term_pairs'] = set()
    with open(data_dir / 'course_relationships.csv') as f:
        for row in csv.DictReader(f):
            if row['relationship_code'] == 'Term':
                pair = tuple(sorted([row['course_a_id'], row['course_b_id']]))
                data['term_pairs'].add(pair)

    # Load teacher assistants
    data['ta_assignments'] = {}
    with open(data_dir / 'teacher_assistants.csv') as f:
        for row in csv.DictReader(f):
            student_id = row['student_external_id']
            if student_id not in data['ta_assignments']:
                data['ta_assignments'][student_id] = {}
            data['ta_assignments'][student_id][row['target_course_name']] = row['target_teacher_id']

    # Load teacher avoid
    data['teacher_avoid'] = defaultdict(set)
    with open(data_dir / 'teacher_avoid.csv') as f:
        for row in csv.DictReader(f):
            data['teacher_avoid'][row['student_external_id']].add(row['teacher_id'])

    # Load student pair constraints
    data['separate_pairs'] = set()
    data['together_pairs'] = set()
    with open(data_dir / 'student_pair_constraints.csv') as f:
        for row in csv.DictReader(f):
            pair = tuple(sorted([row['student_a_external_id'], row['student_b_external_id']]))
            if 'separado' in row['relation'].lower() or 'separate' in row['relation'].lower():
                data['separate_pairs'].add(pair)
            elif 'junto' in row['relation'].lower() or 'together' in row['relation'].lower():
                data['together_pairs'].add(pair)

    print(f"Loaded: {len(data['students'])} students, {len(data['sections'])} sections, "
          f"{len(data['courses'])} courses, {sum(len(r) for r in data['requests'].values())} requests")

    return data


def is_term_pair(data, course_a, course_b):
    pair = tuple(sorted([course_a, course_b]))
    return pair in data['term_pairs']


def get_suffix(section_id):
    return section_id.split('.')[-1] if '.' in section_id else ''


class Solver:
    def __init__(self, data):
        self.data = data
        self.section_enrollment = defaultdict(int)
        self.section_students = defaultdict(set)
        self.student_slots = defaultdict(set)
        self.student_courses = defaultdict(dict)
        self.assignments = []

        # Build lookups
        self.course_name_to_id = {c['name']: cid for cid, c in data['courses'].items()}
        self.separate_partners = defaultdict(set)
        for pair in data['separate_pairs']:
            self.separate_partners[pair[0]].add(pair[1])
            self.separate_partners[pair[1]].add(pair[0])

    def can_assign(self, student_id, section_id):
        sec = self.data['sections'][section_id]
        course_id = sec['course_id']
        course = self.data['courses'].get(course_id, {})

        if course_id in self.student_courses[student_id]:
            return False
        if self.section_enrollment[section_id] >= sec['max_size']:
            return False

        # TA constraint
        if student_id in self.data['ta_assignments']:
            if course.get('name') in self.data['ta_assignments'][student_id]:
                required_teacher = self.data['ta_assignments'][student_id][course['name']]
                if sec['teacher_id'] != required_teacher:
                    return False

        # Teacher avoid
        if student_id in self.data['teacher_avoid']:
            if sec['teacher_id'] in self.data['teacher_avoid'][student_id]:
                return False

        # Double-booking
        for slot in sec['slots_set']:
            if slot in self.student_slots[student_id]:
                overlapping_course = None
                for existing_cid, existing_sid in self.student_courses[student_id].items():
                    existing_sec = self.data['sections'][existing_sid]
                    if slot in existing_sec['slots_set']:
                        overlapping_course = existing_cid
                        break
                if overlapping_course and is_term_pair(self.data, course_id, overlapping_course):
                    existing_sid = self.student_courses[student_id][overlapping_course]
                    if get_suffix(section_id) != get_suffix(existing_sid):
                        return False
                else:
                    return False

        # Separate constraint
        for partner_id in self.separate_partners.get(student_id, set()):
            if partner_id in self.section_students[section_id]:
                return False

        return True

    def assign(self, student_id, section_id):
        sec = self.data['sections'][section_id]
        course_id = sec['course_id']
        self.assignments.append((student_id, section_id))
        self.section_enrollment[section_id] += 1
        self.section_students[section_id].add(student_id)
        self.student_slots[student_id].update(sec['slots_set'])
        self.student_courses[student_id][course_id] = section_id

    def unassign(self, student_id, section_id):
        sec = self.data['sections'][section_id]
        course_id = sec['course_id']
        self.assignments = [(s, sid) for s, sid in self.assignments if not (s == student_id and sid == section_id)]
        self.section_enrollment[section_id] -= 1
        self.section_students[section_id].discard(student_id)
        for slot in sec['slots_set']:
            # Only remove if no other course uses this slot
            keep = False
            for cid, sid in self.student_courses[student_id].items():
                if cid != course_id:
                    s = self.data['sections'][sid]
                    if slot in s['slots_set']:
                        keep = True
                        break
            if not keep:
                self.student_slots[student_id].discard(slot)
        del self.student_courses[student_id][course_id]

    def get_valid_sections(self, student_id, course_id):
        sections = self.data['sections_by_course'].get(course_id, [])
        return [sid for sid in sections if self.can_assign(student_id, sid)]

    def solve(self):
        # Build all (student, course, is_required) tuples
        all_requests = []
        for student_id, requests in self.data['requests'].items():
            for course_id, req_data in requests.items():
                all_requests.append((student_id, course_id, req_data['is_required']))

        # Count how many sections each course has (for MRV)
        def num_sections(course_id):
            return len(self.data['sections_by_course'].get(course_id, []))

        # Sort: required first, then fewest sections (MRV), then by student grade (seniors first)
        all_requests.sort(key=lambda x: (
            -int(x[2]),  # required first
            num_sections(x[1]),  # fewest sections
            -self.data['students'][x[0]]['grade']  # seniors first
        ))

        print(f"Processing {len(all_requests)} requests...")

        # First pass - assign in priority order
        for student_id, course_id, is_required in all_requests:
            if course_id in self.student_courses[student_id]:
                continue
            valid = self.get_valid_sections(student_id, course_id)
            if valid:
                # Pick section with least enrollment
                best = min(valid, key=lambda s: self.section_enrollment[s])
                self.assign(student_id, best)

        print(f"After pass 1: {len(self.assignments)} assignments")

        # Count missing required
        missing_required = []
        for student_id, course_id, is_required in all_requests:
            if is_required and course_id not in self.student_courses[student_id]:
                missing_required.append((student_id, course_id))

        print(f"Missing required: {len(missing_required)}")

        # Pass 2: Try to swap electives out for required courses
        improved = True
        passes = 0
        while improved and passes < 10:
            improved = False
            passes += 1

            for student_id, required_course in list(missing_required):
                if required_course in self.student_courses[student_id]:
                    continue

                required_secs = self.data['sections_by_course'].get(required_course, [])
                for req_sec_id in required_secs:
                    req_sec = self.data['sections'][req_sec_id]

                    # Capacity check
                    if self.section_enrollment[req_sec_id] >= req_sec['max_size']:
                        continue

                    # TA/avoid checks
                    course = self.data['courses'].get(required_course, {})
                    if student_id in self.data['ta_assignments']:
                        if course.get('name') in self.data['ta_assignments'][student_id]:
                            if req_sec['teacher_id'] != self.data['ta_assignments'][student_id][course['name']]:
                                continue
                    if student_id in self.data['teacher_avoid']:
                        if req_sec['teacher_id'] in self.data['teacher_avoid'][student_id]:
                            continue

                    # Separate check
                    skip = False
                    for partner in self.separate_partners.get(student_id, set()):
                        if partner in self.section_students[req_sec_id]:
                            skip = True
                            break
                    if skip:
                        continue

                    # Find conflicting slots
                    conflict_slots = req_sec['slots_set'] & self.student_slots[student_id]
                    if not conflict_slots:
                        # No conflict - direct assign
                        if self.can_assign(student_id, req_sec_id):
                            self.assign(student_id, req_sec_id)
                            improved = True
                            break
                        continue

                    # Find what courses occupy conflicting slots
                    conflicting = []
                    for existing_cid, existing_sid in list(self.student_courses[student_id].items()):
                        existing_sec = self.data['sections'][existing_sid]
                        if existing_sec['slots_set'] & conflict_slots:
                            is_req = self.data['requests'][student_id].get(existing_cid, {}).get('is_required', False)
                            conflicting.append((existing_cid, existing_sid, is_req))

                    # Only try to swap electives (non-required)
                    electives_to_swap = [(c, s) for c, s, r in conflicting if not r]
                    if not electives_to_swap:
                        continue

                    # Try swapping one elective
                    for elec_cid, elec_sid in electives_to_swap:
                        alt_secs = self.data['sections_by_course'].get(elec_cid, [])
                        for alt_sec_id in alt_secs:
                            if alt_sec_id == elec_sid:
                                continue

                            # Save state
                            old_enrollment = dict(self.section_enrollment)
                            old_students = {k: set(v) for k, v in self.section_students.items()}
                            old_slots = {k: set(v) for k, v in self.student_slots.items()}
                            old_courses = {k: dict(v) for k, v in self.student_courses.items()}
                            old_assignments = list(self.assignments)

                            # Try swap
                            self.unassign(student_id, elec_sid)
                            if self.can_assign(student_id, alt_sec_id):
                                self.assign(student_id, alt_sec_id)
                                if self.can_assign(student_id, req_sec_id):
                                    self.assign(student_id, req_sec_id)
                                    improved = True
                                    break
                                else:
                                    # Restore
                                    self.section_enrollment = old_enrollment
                                    self.section_students = old_students
                                    self.student_slots = old_slots
                                    self.student_courses = old_courses
                                    self.assignments = old_assignments
                            else:
                                # Restore
                                self.section_enrollment = old_enrollment
                                self.section_students = old_students
                                self.student_slots = old_slots
                                self.student_courses = old_courses
                                self.assignments = old_assignments

                        if improved:
                            break
                    if improved:
                        break

            # Update missing list
            missing_required = [(s, c) for s, c, r in all_requests
                              if r and c not in self.student_courses[s]]

        print(f"After pass 2: {len(self.assignments)} assignments")

        # Final pass: fill any remaining valid assignments
        for student_id, course_id, is_required in all_requests:
            if course_id in self.student_courses[student_id]:
                continue
            valid = self.get_valid_sections(student_id, course_id)
            if valid:
                best = min(valid, key=lambda s: self.section_enrollment[s])
                self.assign(student_id, best)

        print(f"Final: {len(self.assignments)} assignments")
        return self.assignments


def compute_period_map(data):
    slot_patterns = {}
    period_num = 1
    for sec_id, sec in data['sections'].items():
        slots = sec['slots']
        if slots not in slot_patterns:
            slot_patterns[slots] = period_num
            period_num += 1
    return slot_patterns


def export_friendly_csv(data, assignments, output_path):
    period_map = compute_period_map(data)

    rows = []
    for student_id, section_id in assignments:
        student = data['students'][student_id]
        sec = data['sections'][section_id]
        course = data['courses'].get(sec['course_id'], {})

        teacher_name = data['teachers'].get(sec['teacher_id'], '') if sec['teacher_id'] else ''
        room_name = data['rooms'].get(sec['room_id'], '') if sec['room_id'] else ''

        rows.append({
            'StudentID': student_id,
            'StudentName': student['name'],
            'Grade': student['grade'],
            'CourseID': sec['course_id'],
            'CourseName': course.get('name', ''),
            'SectionID': section_id,
            'Period': period_map.get(sec['slots'], 0),
            'Slots': sec['slots'],
            'TeacherID': sec['teacher_id'],
            'TeacherName': teacher_name,
            'RoomID': sec['room_id'],
            'RoomName': room_name
        })

    rows.sort(key=lambda r: (r['StudentID'], r['CourseID']))

    fieldnames = ['StudentID', 'StudentName', 'Grade', 'CourseID', 'CourseName',
                  'SectionID', 'Period', 'Slots', 'TeacherID', 'TeacherName',
                  'RoomID', 'RoomName']

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total_requests = sum(len(r) for r in data['requests'].values())
    coverage = len(assignments) / total_requests * 100 if total_requests else 0

    students_complete = 0
    student_assigned = defaultdict(int)
    for sid, _ in assignments:
        student_assigned[sid] += 1
    for sid, count in student_assigned.items():
        if count >= len(data['requests'].get(sid, {})):
            students_complete += 1

    print(f"\nExported {len(assignments)} assignments to {output_path}")
    print(f"Coverage: {len(assignments)}/{total_requests} = {coverage:.2f}%")
    print(f"Students complete: {students_complete}/{len(data['students'])} = {students_complete/len(data['students'])*100:.2f}%")


def main():
    data_dir = Path('data')
    output_path = 'student_schedules_friendly.csv'

    print("=== HS Schedule Solver ===\n")
    data = load_data(data_dir)
    print()

    solver = Solver(data)
    assignments = solver.solve()

    export_friendly_csv(data, assignments, output_path)


if __name__ == '__main__':
    main()
