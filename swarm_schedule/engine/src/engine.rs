//! Constraint Engine - the single source of mechanical truth.
//!
//! Responsibilities:
//! - Own the full catalog of constraints (hard and soft)
//! - Maintain live, legal-value domains for every unassigned variable
//! - Propagate consequences of every assignment immediately
//! - Answer feasibility and cost queries incrementally
//! - Explain every conflict in human-readable terms
//! - Detect over-constrained inputs (minimal conflicting set)

use fnv::{FnvHashMap, FnvHashSet};
use std::collections::BTreeSet;

use crate::model::*;

/// Result of trying an assignment.
#[derive(Debug, Clone)]
pub struct TryResult {
    pub feasible: bool,
    pub cost_delta: i32,
    pub conflicts: Vec<Conflict>,
    pub pruned_domains: Vec<(StudentId, CourseId, Vec<SectionId>)>,
}

/// A constraint violation or conflict.
#[derive(Debug, Clone)]
pub struct Conflict {
    pub severity: Severity,
    pub constraint_type: ConstraintType,
    pub entities: Vec<String>,
    pub explanation: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Severity {
    Hard,
    Soft,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConstraintType {
    DoubleBooking,
    Capacity,
    NotRequested,
    AlreadyHasCourse,
    TeacherAvoid,
    TaWrongTeacher,
    SeparateViolation,
    TogetherViolation,
    TermPairMismatch,
}

/// Trail entry for backtracking.
#[derive(Debug, Clone)]
enum TrailEntry {
    Assign {
        student_id: StudentId,
        section_id: SectionId,
    },
    DomainPrune {
        student_id: StudentId,
        course_id: CourseId,
        removed: Vec<SectionId>,
    },
    EnrollmentChange {
        section_id: SectionId,
        old_count: u16,
    },
}

/// The constraint engine state.
pub struct ConstraintEngine {
    pub data: SchoolData,

    // Current state (pub for solver access)
    pub student_sections: FnvHashMap<StudentId, Vec<SectionId>>,
    pub student_slots: FnvHashMap<StudentId, BTreeSet<Slot>>,
    pub student_courses: FnvHashMap<StudentId, FnvHashSet<CourseId>>,
    pub section_enrollment: FnvHashMap<SectionId, u16>,

    // Live domains: for each (student, course), which sections are still legal
    domains: FnvHashMap<(StudentId, CourseId), FnvHashSet<SectionId>>,

    // Trail for backtracking
    trail: Vec<TrailEntry>,
    trail_markers: Vec<usize>, // Stack of trail positions for push/pop

    // Separate partners cache
    separate_partners: FnvHashMap<StudentId, FnvHashSet<StudentId>>,
    // Section -> students assigned (for separate constraint checking)
    section_students: FnvHashMap<SectionId, FnvHashSet<StudentId>>,

    // Statistics
    pub propagations: u64,
    pub domain_prunes: u64,
}

impl ConstraintEngine {
    /// Create a new engine from school data.
    pub fn new(mut data: SchoolData) -> Self {
        data.build_indexes();

        // Build separate partners cache
        let mut separate_partners: FnvHashMap<StudentId, FnvHashSet<StudentId>> =
            FnvHashMap::default();
        for &(a, b) in &data.student_separate {
            separate_partners.entry(a).or_default().insert(b);
            separate_partners.entry(b).or_default().insert(a);
        }

        let mut engine = Self {
            data,
            student_sections: FnvHashMap::default(),
            student_slots: FnvHashMap::default(),
            student_courses: FnvHashMap::default(),
            section_enrollment: FnvHashMap::default(),
            domains: FnvHashMap::default(),
            trail: Vec::new(),
            trail_markers: Vec::new(),
            separate_partners,
            section_students: FnvHashMap::default(),
            propagations: 0,
            domain_prunes: 0,
        };

        engine.initialize_domains();
        engine
    }

    /// Initialize domains for all (student, course) pairs.
    fn initialize_domains(&mut self) {
        for (&student_id, student) in &self.data.students {
            for &course_id in &student.requests {
                let sections: FnvHashSet<SectionId> = self
                    .data
                    .get_sections_for_course(course_id)
                    .iter()
                    .copied()
                    .collect();
                if !sections.is_empty() {
                    self.domains.insert((student_id, course_id), sections);
                }
            }
        }
    }

    /// Get legal sections for a student-course pair.
    pub fn legal_values(&self, student_id: StudentId, course_id: CourseId) -> Vec<SectionId> {
        self.domains
            .get(&(student_id, course_id))
            .map(|s| s.iter().copied().collect())
            .unwrap_or_default()
    }

    /// Check if an assignment is feasible and compute cost delta.
    pub fn try_assign(&mut self, student_id: StudentId, section_id: SectionId) -> TryResult {
        let mut conflicts = Vec::new();
        let mut cost_delta = 0i32;

        let section = match self.data.sections.get(&section_id) {
            Some(s) => s.clone(),
            None => {
                return TryResult {
                    feasible: false,
                    cost_delta: 0,
                    conflicts: vec![Conflict {
                        severity: Severity::Hard,
                        constraint_type: ConstraintType::NotRequested,
                        entities: vec![format!("section:{}", section_id)],
                        explanation: "Section does not exist".to_string(),
                    }],
                    pruned_domains: vec![],
                }
            }
        };

        let student = match self.data.students.get(&student_id) {
            Some(s) => s,
            None => {
                return TryResult {
                    feasible: false,
                    cost_delta: 0,
                    conflicts: vec![],
                    pruned_domains: vec![],
                }
            }
        };

        let course_id = section.course_id;

        // H6: Only requested courses
        if !student.requests.contains(&course_id) {
            conflicts.push(Conflict {
                severity: Severity::Hard,
                constraint_type: ConstraintType::NotRequested,
                entities: vec![
                    format!("student:{}", student_id),
                    format!("course:{}", course_id),
                ],
                explanation: format!(
                    "Student {} did not request course {}",
                    student_id, course_id
                ),
            });
        }

        // H2: Capacity
        let current_enrollment = *self.section_enrollment.get(&section_id).unwrap_or(&0);
        if current_enrollment >= section.max_size {
            conflicts.push(Conflict {
                severity: Severity::Hard,
                constraint_type: ConstraintType::Capacity,
                entities: vec![format!("section:{}", section_id)],
                explanation: format!(
                    "Section {} is at capacity ({}/{})",
                    section.name, current_enrollment, section.max_size
                ),
            });
        }

        // H7: One section per course
        if let Some(courses) = self.student_courses.get(&student_id) {
            if courses.contains(&course_id) {
                conflicts.push(Conflict {
                    severity: Severity::Hard,
                    constraint_type: ConstraintType::AlreadyHasCourse,
                    entities: vec![
                        format!("student:{}", student_id),
                        format!("course:{}", course_id),
                    ],
                    explanation: format!(
                        "Student {} already has a section for course {}",
                        student_id, course_id
                    ),
                });
            }
        }

        // H11: Teacher avoid
        if let Some(avoid_teachers) = self.data.teacher_avoid.get(&student_id) {
            if avoid_teachers.contains(&section.teacher_id) {
                conflicts.push(Conflict {
                    severity: Severity::Hard,
                    constraint_type: ConstraintType::TeacherAvoid,
                    entities: vec![
                        format!("student:{}", student_id),
                        format!("teacher:{}", section.teacher_id),
                    ],
                    explanation: format!(
                        "Student {} must avoid teacher {}",
                        student_id, section.teacher_id
                    ),
                });
            }
        }

        // H10: TA assignment
        if let Some(&(ta_course, ta_teacher)) = self.data.ta_assignments.get(&student_id) {
            if course_id == ta_course && section.teacher_id != ta_teacher {
                conflicts.push(Conflict {
                    severity: Severity::Hard,
                    constraint_type: ConstraintType::TaWrongTeacher,
                    entities: vec![
                        format!("student:{}", student_id),
                        format!("course:{}", course_id),
                        format!("expected_teacher:{}", ta_teacher),
                    ],
                    explanation: format!(
                        "Student {} is TA for course {} with teacher {}, not {}",
                        student_id, course_id, ta_teacher, section.teacher_id
                    ),
                });
            }
        }

        // H1: Double booking (with H8 term pair exception)
        if let Some(used_slots) = self.student_slots.get(&student_id) {
            for &slot in &section.slots {
                if used_slots.contains(&slot) {
                    // Check if this is a term pair exception
                    let mut is_term_pair = false;
                    if let Some(sections) = self.student_sections.get(&student_id) {
                        for &other_sid in sections {
                            if let Some(other_sec) = self.data.sections.get(&other_sid) {
                                if other_sec.slots.contains(&slot) {
                                    if self.data.is_term_pair(course_id, other_sec.course_id) {
                                        is_term_pair = true;
                                        break;
                                    }
                                }
                            }
                        }
                    }

                    if !is_term_pair {
                        conflicts.push(Conflict {
                            severity: Severity::Hard,
                            constraint_type: ConstraintType::DoubleBooking,
                            entities: vec![
                                format!("student:{}", student_id),
                                format!("slot:{}", format_slot(slot)),
                            ],
                            explanation: format!(
                                "Student {} already has a class at slot {}",
                                student_id,
                                format_slot(slot)
                            ),
                        });
                        break;
                    }
                }
            }
        }

        // H12: Separate constraint
        if let Some(partners) = self.separate_partners.get(&student_id) {
            if let Some(section_students) = self.section_students.get(&section_id) {
                for &partner_id in partners {
                    if section_students.contains(&partner_id) {
                        conflicts.push(Conflict {
                            severity: Severity::Hard,
                            constraint_type: ConstraintType::SeparateViolation,
                            entities: vec![
                                format!("student:{}", student_id),
                                format!("partner:{}", partner_id),
                                format!("section:{}", section_id),
                            ],
                            explanation: format!(
                                "Students {} and {} must be separated but would share section {}",
                                student_id, partner_id, section.name
                            ),
                        });
                    }
                }
            }
        }

        // Soft: Balance penalty (less full sections preferred)
        cost_delta += current_enrollment as i32 * 10;

        let feasible = conflicts.iter().all(|c| c.severity != Severity::Hard);

        TryResult {
            feasible,
            cost_delta,
            conflicts,
            pruned_domains: vec![],
        }
    }

    /// Actually commit an assignment (after try_assign returned feasible=true).
    pub fn commit_assign(&mut self, student_id: StudentId, section_id: SectionId) {
        let section = match self.data.sections.get(&section_id) {
            Some(s) => s.clone(),
            None => return,
        };

        // Record on trail for backtracking
        self.trail.push(TrailEntry::Assign {
            student_id,
            section_id,
        });

        // Update student state
        self.student_sections
            .entry(student_id)
            .or_default()
            .push(section_id);
        self.student_slots
            .entry(student_id)
            .or_default()
            .extend(section.slots.iter().copied());
        self.student_courses
            .entry(student_id)
            .or_default()
            .insert(section.course_id);

        // Update section enrollment
        let old_enrollment = *self.section_enrollment.get(&section_id).unwrap_or(&0);
        self.trail.push(TrailEntry::EnrollmentChange {
            section_id,
            old_count: old_enrollment,
        });
        self.section_enrollment
            .insert(section_id, old_enrollment + 1);

        // Update section->students mapping
        self.section_students
            .entry(section_id)
            .or_default()
            .insert(student_id);

        // Remove this course from student's domain (H7)
        self.domains.remove(&(student_id, section.course_id));

        // Propagate: prune domains based on new constraints
        self.propagate(student_id, section_id);
    }

    /// Propagate constraints after an assignment.
    fn propagate(&mut self, student_id: StudentId, section_id: SectionId) {
        self.propagations += 1;

        let section = match self.data.sections.get(&section_id) {
            Some(s) => s.clone(),
            None => return,
        };

        // Prune sections with conflicting slots from this student's remaining domains
        let mut to_prune: Vec<(StudentId, CourseId, SectionId)> = Vec::new();

        for (&(sid, cid), domain) in &self.domains {
            if sid != student_id {
                continue;
            }

            for &candidate_sid in domain {
                if let Some(candidate) = self.data.sections.get(&candidate_sid) {
                    // Check slot conflict
                    let has_conflict = candidate.slots.iter().any(|slot| {
                        section.slots.contains(slot)
                            && !self.data.is_term_pair(section.course_id, candidate.course_id)
                    });

                    if has_conflict {
                        to_prune.push((sid, cid, candidate_sid));
                    }
                }
            }
        }

        // Apply pruning
        for (sid, cid, prune_sid) in to_prune {
            if let Some(domain) = self.domains.get_mut(&(sid, cid)) {
                if domain.remove(&prune_sid) {
                    self.domain_prunes += 1;
                    self.trail.push(TrailEntry::DomainPrune {
                        student_id: sid,
                        course_id: cid,
                        removed: vec![prune_sid],
                    });
                }
            }
        }

        // Propagate separate constraints: if student A is assigned to section S,
        // remove S from domains of all partners of A
        if let Some(partners) = self.separate_partners.get(&student_id).cloned() {
            for partner_id in partners {
                let course_id = section.course_id;
                if let Some(domain) = self.domains.get_mut(&(partner_id, course_id)) {
                    if domain.remove(&section_id) {
                        self.domain_prunes += 1;
                        self.trail.push(TrailEntry::DomainPrune {
                            student_id: partner_id,
                            course_id,
                            removed: vec![section_id],
                        });
                    }
                }
            }
        }
    }

    /// Push a checkpoint for backtracking.
    pub fn push(&mut self) {
        self.trail_markers.push(self.trail.len());
    }

    /// Pop back to last checkpoint, undoing all assignments since then.
    pub fn pop(&mut self) {
        let marker = self.trail_markers.pop().unwrap_or(0);

        while self.trail.len() > marker {
            match self.trail.pop() {
                Some(TrailEntry::Assign {
                    student_id,
                    section_id,
                }) => {
                    if let Some(sections) = self.student_sections.get_mut(&student_id) {
                        sections.retain(|&s| s != section_id);
                    }
                    if let Some(section) = self.data.sections.get(&section_id) {
                        if let Some(slots) = self.student_slots.get_mut(&student_id) {
                            for slot in &section.slots {
                                slots.remove(slot);
                            }
                        }
                        if let Some(courses) = self.student_courses.get_mut(&student_id) {
                            courses.remove(&section.course_id);
                        }
                        // Restore domain
                        self.domains
                            .entry((student_id, section.course_id))
                            .or_default()
                            .insert(section_id);
                    }
                    if let Some(students) = self.section_students.get_mut(&section_id) {
                        students.remove(&student_id);
                    }
                }
                Some(TrailEntry::EnrollmentChange {
                    section_id,
                    old_count,
                }) => {
                    self.section_enrollment.insert(section_id, old_count);
                }
                Some(TrailEntry::DomainPrune {
                    student_id,
                    course_id,
                    removed,
                }) => {
                    if let Some(domain) = self.domains.get_mut(&(student_id, course_id)) {
                        for sid in removed {
                            domain.insert(sid);
                        }
                    }
                }
                None => break,
            }
        }
    }

    /// Get current score: (hard_violations, soft_cost).
    pub fn score(&self) -> (u32, i32) {
        // For now, just count unassigned required courses as hard violations
        let mut hard = 0u32;
        let mut soft = 0i32;

        for (student_id, student) in &self.data.students {
            let assigned = self
                .student_courses
                .get(student_id)
                .map(|c| c.len())
                .unwrap_or(0);
            let requested = student.requests.len();

            // Soft: penalize unassigned courses
            soft += ((requested - assigned) * 100) as i32;

            // Hard: penalize unassigned required courses
            if let Some(courses) = self.student_courses.get(student_id) {
                for &req in &student.required {
                    if !courses.contains(&req) {
                        hard += 1;
                    }
                }
            } else {
                hard += student.required.len() as u32;
            }
        }

        (hard, soft)
    }

    /// Get statistics.
    pub fn stats(&self) -> EngineStats {
        let total_assigned: usize = self.student_sections.values().map(|v| v.len()).sum();
        let total_requests: usize = self.data.students.values().map(|s| s.requests.len()).sum();

        EngineStats {
            students: self.data.students.len(),
            sections: self.data.sections.len(),
            total_requests,
            total_assigned,
            coverage: if total_requests > 0 {
                total_assigned as f64 / total_requests as f64
            } else {
                0.0
            },
            propagations: self.propagations,
            domain_prunes: self.domain_prunes,
        }
    }

    /// Export current assignments.
    pub fn get_assignments(&self) -> Vec<Assignment> {
        let mut assignments = Vec::new();
        for (&student_id, sections) in &self.student_sections {
            for &section_id in sections {
                assignments.push(Assignment {
                    student_id,
                    section_id,
                });
            }
        }
        assignments
    }
}

#[derive(Debug, Clone)]
pub struct EngineStats {
    pub students: usize,
    pub sections: usize,
    pub total_requests: usize,
    pub total_assigned: usize,
    pub coverage: f64,
    pub propagations: u64,
    pub domain_prunes: u64,
}
