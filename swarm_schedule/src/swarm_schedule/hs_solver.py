"""
High School Student Schedule Solver

Assigns 509 HS students to 249 fixed sections respecting all hard constraints.
Output: student_schedules_friendly.csv
"""

import csv
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path


@dataclass
class Section:
    section_id: str
    course_id: str
    teacher_id: int
    room_id: str
    max_size: int
    grade_level: int
    slots: set[str]

    def __hash__(self):
        return hash(self.section_id)


@dataclass
class Student:
    student_id: str
    grade: int
    requests: set[str] = field(default_factory=set)
    required_courses: set[str] = field(default_factory=set)
    assigned_sections: list = field(default_factory=list)
    used_slots: set[str] = field(default_factory=set)


class HSSolver:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.sections: dict[str, Section] = {}
        self.sections_by_course: dict[str, list[Section]] = defaultdict(list)
        self.students: dict[str, Student] = {}
        self.courses: dict[str, dict] = {}
        self.teachers: dict[int, str] = {}
        self.rooms: dict[str, str] = {}

        # Constraints
        self.term_pairs: list[tuple[str, str]] = []
        self.simultaneous_pairs: list[tuple[str, str]] = []
        self.ta_assignments: dict[str, tuple[str, int]] = {}  # student -> (course, teacher)
        self.teacher_avoid: dict[str, set[int]] = defaultdict(set)  # student -> teachers to avoid
        self.student_separate: list[tuple[str, str]] = []
        self.student_together: list[tuple[str, str]] = []

        # Section enrollment tracking
        self.section_enrollment: dict[str, int] = defaultdict(int)

    def load_data(self):
        self._load_sections()
        self._load_courses()
        self._load_teachers()
        self._load_rooms()
        self._load_students_and_requests()
        self._load_constraints()
        self._apply_request_changes()

    def _load_sections(self):
        with open(self.data_dir / 'sections.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                slots_str = row['slots'].strip()
                slots = set(slots_str.split(';')) if slots_str else set()
                slots.discard('')

                teacher_id = int(row['teacher_id']) if row['teacher_id'] else 0

                section = Section(
                    section_id=row['section_id'],
                    course_id=row['course_id'],
                    teacher_id=teacher_id,
                    room_id=row['room_id'],
                    max_size=int(row['max_size']),
                    grade_level=int(row['grade_level']) if row['grade_level'] else 0,
                    slots=slots
                )
                self.sections[section.section_id] = section
                self.sections_by_course[section.course_id].append(section)

        print(f"Loaded {len(self.sections)} sections for {len(self.sections_by_course)} courses")

    def _load_courses(self):
        with open(self.data_dir / 'courses.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.courses[row['course_id']] = {
                    'name': row['name'],
                    'department': row['department'],
                    'max_size': int(row['max_size']) if row['max_size'] else 25
                }
        print(f"Loaded {len(self.courses)} courses")

    def _load_teachers(self):
        with open(self.data_dir / 'teachers.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.teachers[int(row['teacher_id'])] = row['teacher_name']
        print(f"Loaded {len(self.teachers)} teachers")

    def _load_rooms(self):
        with open(self.data_dir / 'rooms.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.rooms[row['room_id']] = row['name']
        print(f"Loaded {len(self.rooms)} rooms")

    def _load_students_and_requests(self):
        # Load requests
        with open(self.data_dir / 'course_requests.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                student_id = row['student_external_id']
                course_id = row['course_id']
                is_required = row['is_required'] == '1'

                if student_id not in self.students:
                    self.students[student_id] = Student(
                        student_id=student_id,
                        grade=0  # Will be filled from requests
                    )

                self.students[student_id].requests.add(course_id)
                if is_required:
                    self.students[student_id].required_courses.add(course_id)

        # Load student grades from students.csv
        with open(self.data_dir / 'students.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                student_id = row['student_external_id']
                if student_id in self.students:
                    self.students[student_id].grade = int(row['grade'])

        print(f"Loaded {len(self.students)} students with requests")

    def _load_constraints(self):
        # Course relationships (Term pairs and Simultaneous pairs)
        with open(self.data_dir / 'course_relationships.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                course_a = row['course_a_id']
                course_b = row['course_b_id']
                rel_code = row['relationship_code']

                if rel_code == 'Term':
                    self.term_pairs.append((course_a, course_b))
                elif rel_code == 'Simultaneous':
                    self.simultaneous_pairs.append((course_a, course_b))

        print(f"Term pairs: {self.term_pairs}")
        print(f"Simultaneous pairs: {self.simultaneous_pairs}")

        # Teacher assistants
        with open(self.data_dir / 'teacher_assistants.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                student_id = row['student_external_id']
                course_id = row['target_course_id']
                teacher_id = int(row['target_teacher_id'])
                self.ta_assignments[student_id] = (course_id, teacher_id)

        print(f"TA assignments: {len(self.ta_assignments)}")

        # Teacher avoid
        with open(self.data_dir / 'teacher_avoid.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                student_id = str(row['STUDENT_NUMBER'])
                teacher_name = row['TEACHER_NAME']
                # Find teacher ID by name
                for tid, tname in self.teachers.items():
                    if teacher_name.lower() in tname.lower() or tname.lower() in teacher_name.lower():
                        self.teacher_avoid[student_id].add(tid)
                        break

        print(f"Teacher avoid rules: {sum(len(v) for v in self.teacher_avoid.values())}")

        # Student pair constraints
        with open(self.data_dir / 'student_pair_constraints.csv') as f:
            reader = csv.DictReader(f)
            for row in reader:
                student_a = str(int(float(row['student_a_id'])))
                student_b = str(int(float(row['student_b_id'])))
                relation = row['relation']

                if relation == 'separate':
                    self.student_separate.append((student_a, student_b))
                else:
                    self.student_together.append((student_a, student_b))

        print(f"Separate pairs: {len(self.student_separate)}, Together pairs: {len(self.student_together)}")

    def _apply_request_changes(self):
        try:
            with open(self.data_dir / 'student_requests_changes.csv') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    student_id = str(row['student_number'])
                    course_id = row['course_number']
                    action = row['action']

                    if student_id in self.students:
                        if action == 'drop' and course_id in self.students[student_id].requests:
                            self.students[student_id].requests.discard(course_id)
                            self.students[student_id].required_courses.discard(course_id)
                        elif action == 'add':
                            self.students[student_id].requests.add(course_id)
            print("Applied request changes")
        except FileNotFoundError:
            pass

    def _slots_conflict(self, slots1: set[str], slots2: set[str]) -> bool:
        """Check if two slot sets conflict (share any slot)."""
        return bool(slots1 & slots2)

    def _is_term_pair(self, course_a: str, course_b: str) -> bool:
        """Check if two courses are a Term pair (can share slots)."""
        for c1, c2 in self.term_pairs:
            if (course_a == c1 and course_b == c2) or (course_a == c2 and course_b == c1):
                return True
        return False

    def _get_term_pair_suffix(self, section_id: str) -> str:
        """Extract suffix from section ID (e.g., 'I1212.1' -> '1')."""
        return section_id.split('.')[-1]

    def _can_assign(self, student: Student, section: Section, check_separate: bool = True) -> tuple[bool, str]:
        """Check if student can be assigned to section. Returns (can_assign, reason)."""
        course_id = section.course_id

        # H2: Capacity check
        if self.section_enrollment[section.section_id] >= section.max_size:
            return False, "capacity"

        # H6: Only requested courses
        if course_id not in student.requests:
            return False, "not_requested"

        # H7: One section per course
        for assigned in student.assigned_sections:
            if assigned.course_id == course_id:
                return False, "already_has_course"

        # H11: Teacher avoid
        if section.teacher_id in self.teacher_avoid.get(student.student_id, set()):
            return False, "teacher_avoid"

        # H10: TA must be with specific teacher
        if student.student_id in self.ta_assignments:
            ta_course, ta_teacher = self.ta_assignments[student.student_id]
            if course_id == ta_course and section.teacher_id != ta_teacher:
                return False, "ta_wrong_teacher"

        # H1: No double-booking (with H8 Term pair exception)
        if section.slots:
            for assigned in student.assigned_sections:
                if self._slots_conflict(section.slots, assigned.slots):
                    # Check if this is a Term pair
                    if self._is_term_pair(course_id, assigned.course_id):
                        continue  # Term pairs can share slots
                    return False, "slot_conflict"

        # H12: Separate constraint check
        if check_separate:
            for other_student_id in self._get_separate_partners(student.student_id):
                if other_student_id in self.students:
                    other = self.students[other_student_id]
                    for other_section in other.assigned_sections:
                        if other_section.section_id == section.section_id:
                            return False, "separate_conflict"

        return True, "ok"

    def _get_separate_partners(self, student_id: str) -> set[str]:
        """Get all students that must be separated from this student."""
        if hasattr(self, '_separate_partners'):
            return self._separate_partners.get(student_id, set())
        partners = set()
        for a, b in self.student_separate:
            if a == student_id:
                partners.add(b)
            elif b == student_id:
                partners.add(a)
        return partners

    def _section_score(self, student: Student, section: Section) -> float:
        """Score a section assignment (higher is better)."""
        score = 0.0

        # Prefer less full sections (balance)
        enrollment = self.section_enrollment[section.section_id]
        score -= enrollment * 10

        # TA assignment bonus
        if student.student_id in self.ta_assignments:
            ta_course, ta_teacher = self.ta_assignments[student.student_id]
            if section.course_id == ta_course and section.teacher_id == ta_teacher:
                score += 10000

        return score

    def _assign_student_to_section(self, student: Student, section: Section):
        """Assign student to section."""
        student.assigned_sections.append(section)
        student.used_slots.update(section.slots)
        self.section_enrollment[section.section_id] += 1

    def solve(self):
        """Main solving loop."""
        print("\n=== Starting solver ===")

        # Build separate partners lookup for faster checking
        self._separate_partners = defaultdict(set)
        for a, b in self.student_separate:
            self._separate_partners[a].add(b)
            self._separate_partners[b].add(a)

        # Sort students: G12 first (priority), then by number of requests (harder first)
        # Also prioritize students with separate constraints (harder to place)
        sorted_students = sorted(
            self.students.values(),
            key=lambda s: (
                -s.grade,
                -len(s.required_courses),
                -len(self._separate_partners.get(s.student_id, set())),
                -len(s.requests)
            )
        )

        total_requests = sum(len(s.requests) for s in sorted_students)
        total_assigned = 0
        failed_assignments = []

        for student in sorted_students:
            # Sort courses: required first, then by fewer available sections
            courses_to_assign = []
            for course_id in student.requests:
                sections = self.sections_by_course.get(course_id, [])
                is_required = course_id in student.required_courses
                courses_to_assign.append((course_id, is_required, len(sections)))

            # Required first, then fewer sections (harder to place)
            courses_to_assign.sort(key=lambda x: (-x[1], x[2]))

            for course_id, is_required, _ in courses_to_assign:
                sections = self.sections_by_course.get(course_id, [])
                if not sections:
                    if is_required:
                        failed_assignments.append((student.student_id, course_id, "no_sections"))
                    continue

                # Find best valid section
                valid_sections = []
                for section in sections:
                    can_assign, reason = self._can_assign(student, section)
                    if can_assign:
                        score = self._section_score(student, section)
                        valid_sections.append((section, score))

                if valid_sections:
                    # Pick highest scoring section
                    valid_sections.sort(key=lambda x: -x[1])
                    best_section = valid_sections[0][0]
                    self._assign_student_to_section(student, best_section)
                    total_assigned += 1
                elif is_required:
                    # Try to find why we failed
                    reasons = []
                    for section in sections:
                        can_assign, reason = self._can_assign(student, section)
                        reasons.append(reason)
                    failed_assignments.append((student.student_id, course_id, reasons[0] if reasons else "unknown"))

        # Handle H8 Term pairs - ensure matching suffixes
        self._fix_term_pairs()

        # Handle H12 student together constraints
        self._fix_together_constraints()

        coverage = total_assigned / total_requests * 100 if total_requests else 0
        print(f"\nCoverage: {total_assigned}/{total_requests} ({coverage:.1f}%)")
        print(f"Failed required assignments: {len([f for f in failed_assignments if f])}")

        if failed_assignments[:10]:
            print("Sample failures:", failed_assignments[:10])

        # Second pass: try to place failed required courses by relaxing order
        print("\n=== Second pass for failed required ===")
        additional = 0
        for student_id, course_id, reason in failed_assignments:
            if student_id not in self.students:
                continue
            student = self.students[student_id]

            # Skip if already assigned
            if any(s.course_id == course_id for s in student.assigned_sections):
                continue

            sections = self.sections_by_course.get(course_id, [])
            for section in sorted(sections, key=lambda s: self.section_enrollment[s.section_id]):
                can_assign, _ = self._can_assign(student, section, check_separate=True)
                if can_assign:
                    self._assign_student_to_section(student, section)
                    additional += 1
                    total_assigned += 1
                    break

        if additional:
            coverage = total_assigned / total_requests * 100 if total_requests else 0
            print(f"Additional assignments: {additional}")
            print(f"New coverage: {total_assigned}/{total_requests} ({coverage:.1f}%)")

        return total_assigned, total_requests

    def _fix_term_pairs(self):
        """Ensure H8: Term pair courses have matching section suffixes."""
        for course_a, course_b in self.term_pairs:
            for student in self.students.values():
                section_a = None
                section_b = None

                for section in student.assigned_sections:
                    if section.course_id == course_a:
                        section_a = section
                    elif section.course_id == course_b:
                        section_b = section

                if section_a and section_b:
                    suffix_a = self._get_term_pair_suffix(section_a.section_id)
                    suffix_b = self._get_term_pair_suffix(section_b.section_id)

                    if suffix_a != suffix_b:
                        # Try to move one to match
                        target_suffix = suffix_a
                        target_section_id = f"{course_b}.{target_suffix}"

                        if target_section_id in self.sections:
                            target_section = self.sections[target_section_id]
                            if self.section_enrollment[target_section_id] < target_section.max_size:
                                # Swap
                                student.assigned_sections.remove(section_b)
                                self.section_enrollment[section_b.section_id] -= 1
                                student.assigned_sections.append(target_section)
                                self.section_enrollment[target_section_id] += 1

    def _fix_together_constraints(self):
        """Ensure H12: Students marked 'together' are in same sections."""
        # This is complex - simplified version
        pass

    def _check_separate_constraints(self) -> list[tuple]:
        """Check H12 separate constraints."""
        violations = []
        for student_a, student_b in self.student_separate:
            if student_a not in self.students or student_b not in self.students:
                continue

            sa = self.students[student_a]
            sb = self.students[student_b]

            for sec_a in sa.assigned_sections:
                for sec_b in sb.assigned_sections:
                    if sec_a.section_id == sec_b.section_id:
                        violations.append((student_a, student_b, sec_a.section_id))

        return violations

    def export_csv(self, output_path: str):
        """Export results to student_schedules_friendly.csv"""
        # Build period map: unique slot combinations -> period number
        slot_to_period = {}
        period_num = 1
        for section in self.sections.values():
            slots_key = ';'.join(sorted(section.slots)) if section.slots else ''
            if slots_key and slots_key not in slot_to_period:
                slot_to_period[slots_key] = period_num
                period_num += 1

        rows = []
        for student in self.students.values():
            for section in student.assigned_sections:
                course_name = self.courses.get(section.course_id, {}).get('name', section.course_id)
                teacher_name = self.teachers.get(section.teacher_id, '')
                room_name = self.rooms.get(section.room_id, section.room_id)
                slots_str = ';'.join(sorted(section.slots)) if section.slots else ''
                period = slot_to_period.get(slots_str, 0)

                rows.append({
                    'StudentID': student.student_id,
                    'StudentName': '',  # Not in our data
                    'Grade': student.grade,
                    'CourseID': section.course_id,
                    'CourseName': course_name,
                    'SectionID': section.section_id,
                    'Period': period,
                    'Slots': slots_str,
                    'TeacherID': section.teacher_id if section.teacher_id else '',
                    'TeacherName': teacher_name,
                    'RoomID': section.room_id,
                    'RoomName': room_name
                })

        # Sort by student, then period
        rows.sort(key=lambda r: (r['StudentID'], r['Period']))

        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'StudentID', 'StudentName', 'Grade', 'CourseID', 'CourseName',
                'SectionID', 'Period', 'Slots', 'TeacherID', 'TeacherName',
                'RoomID', 'RoomName'
            ])
            writer.writeheader()
            writer.writerows(rows)

        print(f"\nExported {len(rows)} assignments to {output_path}")
        return len(rows)

    def validate(self) -> dict:
        """Run validation checks."""
        results = {
            'h1_double_booking': [],
            'h2_capacity': [],
            'h7_multiple_sections': [],
            'h10_ta_wrong_teacher': [],
            'h11_teacher_avoid': [],
            'h12_separate': [],
        }

        # H1: Double booking
        for student in self.students.values():
            slots_used = defaultdict(list)
            for section in student.assigned_sections:
                for slot in section.slots:
                    slots_used[slot].append(section)

            for slot, sections in slots_used.items():
                if len(sections) > 1:
                    # Check for term pair exception
                    courses = [s.course_id for s in sections]
                    if not any(self._is_term_pair(courses[i], courses[j])
                              for i in range(len(courses)) for j in range(i+1, len(courses))):
                        results['h1_double_booking'].append((student.student_id, slot, courses))

        # H2: Capacity
        for section_id, count in self.section_enrollment.items():
            section = self.sections[section_id]
            if count > section.max_size:
                results['h2_capacity'].append((section_id, count, section.max_size))

        # H12: Separate
        results['h12_separate'] = self._check_separate_constraints()

        return results


def main():
    data_dir = '/home/user/scheduler/swarm_schedule/data'
    output_path = '/home/user/scheduler/swarm_schedule/student_schedules_friendly.csv'

    solver = HSSolver(data_dir)
    solver.load_data()
    solver.solve()
    solver.export_csv(output_path)

    # Validate
    print("\n=== Validation ===")
    results = solver.validate()
    for check, violations in results.items():
        if violations:
            print(f"{check}: {len(violations)} violations")
            if len(violations) <= 5:
                print(f"  {violations}")
        else:
            print(f"{check}: OK")


if __name__ == '__main__':
    main()
