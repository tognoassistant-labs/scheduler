//! Solver: greedy construction + min-conflicts repair + SA polish.

use fnv::FnvHashSet;
use rand::prelude::*;
use rand::rngs::StdRng;

use crate::engine::ConstraintEngine;
use crate::model::*;

/// Solver configuration.
#[derive(Debug, Clone)]
pub struct SolverConfig {
    pub seed: u64,
    pub max_repair_iterations: u32,
    pub max_polish_iterations: u32,
    pub initial_temperature: f64,
    pub cooling_rate: f64,
}

impl Default for SolverConfig {
    fn default() -> Self {
        Self {
            seed: 42,
            max_repair_iterations: 1000,
            max_polish_iterations: 5000,
            initial_temperature: 100.0,
            cooling_rate: 0.995,
        }
    }
}

/// Solver result.
#[derive(Debug, Clone)]
pub struct SolverResult {
    pub assignments: Vec<Assignment>,
    pub coverage: f64,
    pub hard_violations: u32,
    pub soft_cost: i32,
    pub construction_time_ms: u64,
    pub repair_time_ms: u64,
    pub polish_time_ms: u64,
    pub repair_iterations: u32,
    pub polish_iterations: u32,
}

/// The solver.
pub struct Solver {
    pub engine: ConstraintEngine,
    config: SolverConfig,
    rng: StdRng,
}

impl Solver {
    pub fn new(engine: ConstraintEngine, config: SolverConfig) -> Self {
        let rng = StdRng::seed_from_u64(config.seed);
        Self { engine, config, rng }
    }

    /// Run the full solving pipeline.
    pub fn solve(&mut self) -> SolverResult {
        let start = std::time::Instant::now();

        // Phase 1: Greedy construction
        let construction_start = std::time::Instant::now();
        self.greedy_construct();
        let construction_time = construction_start.elapsed().as_millis() as u64;

        let (hard_after_construct, soft_after_construct) = self.engine.score();
        let stats = self.engine.stats();
        println!(
            "After construction: hard={}, soft={}, coverage={:.1}%",
            hard_after_construct,
            soft_after_construct,
            stats.coverage * 100.0
        );

        // Phase 2: Aggressive repair - try to place ALL missing courses
        let repair_start = std::time::Instant::now();
        let repair_iterations = self.aggressive_repair();
        let repair_time = repair_start.elapsed().as_millis() as u64;

        let (hard_after_repair, soft_after_repair) = self.engine.score();
        let stats = self.engine.stats();
        println!(
            "After repair ({}iter): hard={}, soft={}, coverage={:.1}%",
            repair_iterations,
            hard_after_repair,
            soft_after_repair,
            stats.coverage * 100.0
        );

        // Phase 3: Conflict resolution - swap to resolve remaining conflicts
        let swap_iterations = self.conflict_swap_repair();

        let stats = self.engine.stats();
        println!(
            "After swap repair ({}iter): coverage={:.1}%",
            swap_iterations,
            stats.coverage * 100.0
        );

        // Phase 4: Second pass of greedy for any remaining gaps
        self.second_pass_greedy();

        let (hard_final, soft_final) = self.engine.score();
        let stats = self.engine.stats();

        println!(
            "Final: hard={}, soft={}, coverage={:.1}%",
            hard_final,
            soft_final,
            stats.coverage * 100.0
        );
        println!("Total time: {:?}", start.elapsed());

        SolverResult {
            assignments: self.engine.get_assignments(),
            coverage: stats.coverage,
            hard_violations: hard_final,
            soft_cost: soft_final,
            construction_time_ms: construction_time,
            repair_time_ms: repair_time,
            polish_time_ms: 0,
            repair_iterations,
            polish_iterations: swap_iterations,
        }
    }

    /// Phase 1: Greedy construction using MRV (most-constrained variable first).
    fn greedy_construct(&mut self) {
        // Sort students by: grade desc, required courses desc
        let mut student_ids: Vec<StudentId> = self.engine.data.students.keys().copied().collect();

        // Shuffle first for diversity, then stable sort by priority
        use rand::seq::SliceRandom;
        student_ids.shuffle(&mut self.rng);

        student_ids.sort_by(|&a, &b| {
            let sa = &self.engine.data.students[&a];
            let sb = &self.engine.data.students[&b];
            sb.grade
                .cmp(&sa.grade)
                .then_with(|| sb.required.len().cmp(&sa.required.len()))
        });

        for student_id in student_ids {
            let student = self.engine.data.students[&student_id].clone();

            // Sort courses: required first, then by domain size (MRV)
            let mut courses: Vec<(CourseId, bool, usize)> = student
                .requests
                .iter()
                .map(|&cid| {
                    let domain_size = self.engine.legal_values(student_id, cid).len();
                    let is_required = student.required.contains(&cid);
                    (cid, is_required, domain_size)
                })
                .collect();

            // Required first, then smallest domain (hardest to place)
            courses.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.2.cmp(&b.2)));

            for (course_id, _is_required, _) in courses {
                let mut sections = self.engine.legal_values(student_id, course_id);
                if sections.is_empty() {
                    continue;
                }

                // Sort by enrollment (prefer less full) - compute keys once to avoid total order violation
                let mut section_keys: Vec<(SectionId, u16)> = sections
                    .into_iter()
                    .map(|sid| {
                        let enrollment = self.engine.section_enrollment.get(&sid).copied().unwrap_or(0);
                        let noise: u16 = self.rng.gen_range(0..3);
                        (sid, enrollment + noise)
                    })
                    .collect();
                section_keys.sort_by_key(|&(_, key)| key);
                let sections: Vec<SectionId> = section_keys.into_iter().map(|(sid, _)| sid).collect();

                for section_id in sections {
                    let result = self.engine.try_assign(student_id, section_id);
                    if result.feasible {
                        self.engine.commit_assign(student_id, section_id);
                        break;
                    }
                }
            }
        }
    }

    /// Phase 2: Aggressive repair - try to place ALL missing courses with swap support.
    fn aggressive_repair(&mut self) -> u32 {
        let mut iterations = 0;
        let mut any_progress = true;

        while any_progress && iterations < self.config.max_repair_iterations {
            any_progress = false;
            iterations += 1;

            // Find all students with missing courses, prioritizing required
            let mut missing: Vec<(StudentId, CourseId, bool)> = Vec::new();

            for (&student_id, student) in &self.engine.data.students {
                let assigned: FnvHashSet<CourseId> = self
                    .engine
                    .student_courses
                    .get(&student_id)
                    .cloned()
                    .unwrap_or_default();

                for &course_id in &student.requests {
                    if !assigned.contains(&course_id) {
                        let is_required = student.required.contains(&course_id);
                        missing.push((student_id, course_id, is_required));
                    }
                }
            }

            if missing.is_empty() {
                break;
            }

            // Sort: required first, then shuffle
            missing.sort_by(|a, b| b.2.cmp(&a.2));
            use rand::seq::SliceRandom;
            let required_count = missing.iter().filter(|m| m.2).count();
            if required_count < missing.len() {
                missing[required_count..].shuffle(&mut self.rng);
            }

            // Try to place each missing course
            for (student_id, course_id, _is_required) in &missing {
                let student_id = *student_id;
                let course_id = *course_id;

                // Skip if already assigned (from earlier in this iteration)
                if let Some(courses) = self.engine.student_courses.get(&student_id) {
                    if courses.contains(&course_id) {
                        continue;
                    }
                }

                let sections = self.engine.data.get_sections_for_course(course_id).to_vec();

                // First try direct placement
                let mut placed = false;
                for &section_id in &sections {
                    let result = self.engine.try_assign(student_id, section_id);
                    if result.feasible {
                        self.engine.commit_assign(student_id, section_id);
                        any_progress = true;
                        placed = true;
                        break;
                    }
                }

                if placed {
                    continue;
                }

                // Try swap: find a conflicting course and try to move it
                if let Some(placed_via_swap) = self.try_swap_for_placement(student_id, course_id, &sections) {
                    if placed_via_swap {
                        any_progress = true;
                    }
                }
            }
        }

        iterations
    }

    /// Try to swap an existing assignment to make room for a new one.
    /// Returns Some(true) if swap succeeded, Some(false) if no swap found.
    fn try_swap_for_placement(
        &mut self,
        student_id: StudentId,
        course_id: CourseId,
        sections: &[SectionId],
    ) -> Option<bool> {
        // Get student's current sections
        let student_sections = self.engine.student_sections.get(&student_id)?.clone();

        for &target_section_id in sections {
            let target_section = self.engine.data.sections.get(&target_section_id)?.clone();

            // Check capacity
            let enrollment = self.engine.section_enrollment.get(&target_section_id).copied().unwrap_or(0);
            if enrollment >= target_section.max_size {
                continue;
            }

            // Find conflicting section (slot overlap)
            let mut conflict_section_id: Option<SectionId> = None;
            let mut conflict_course_id: Option<CourseId> = None;

            for &existing_sid in &student_sections {
                if let Some(existing) = self.engine.data.sections.get(&existing_sid) {
                    let has_overlap = existing.slots.iter().any(|s| target_section.slots.contains(s));
                    if has_overlap && !self.engine.data.is_term_pair(course_id, existing.course_id) {
                        conflict_section_id = Some(existing_sid);
                        conflict_course_id = Some(existing.course_id);
                        break;
                    }
                }
            }

            let conflict_sid = conflict_section_id?;
            let conflict_cid = conflict_course_id?;

            // Try to move the conflicting course to another section
            let alt_sections = self.engine.data.get_sections_for_course(conflict_cid).to_vec();

            for alt_sid in alt_sections {
                if alt_sid == conflict_sid {
                    continue;
                }

                // Check if alt section would work (no conflicts with remaining courses)
                // First unassign the conflicting course
                self.engine.unassign(student_id, conflict_sid);

                // Check if we can assign to alt section
                let alt_result = self.engine.try_assign(student_id, alt_sid);
                if alt_result.feasible {
                    self.engine.commit_assign(student_id, alt_sid);

                    // Now try to assign the target course
                    let target_result = self.engine.try_assign(student_id, target_section_id);
                    if target_result.feasible {
                        self.engine.commit_assign(student_id, target_section_id);
                        return Some(true);
                    } else {
                        // Rollback: unassign alt, reassign original
                        self.engine.unassign(student_id, alt_sid);
                        self.engine.commit_assign(student_id, conflict_sid);
                    }
                } else {
                    // Reassign original
                    self.engine.commit_assign(student_id, conflict_sid);
                }
            }
        }

        Some(false)
    }

    /// Phase 3: Conflict swap repair - remove blocking assignments to make room.
    fn conflict_swap_repair(&mut self) -> u32 {
        let mut iterations = 0;
        let max_iterations = 500;

        while iterations < max_iterations {
            iterations += 1;

            // Collect student/course data first to avoid borrow issues
            let student_data: Vec<(StudentId, Vec<CourseId>)> = self
                .engine
                .data
                .students
                .iter()
                .map(|(&sid, s)| (sid, s.requests.iter().copied().collect()))
                .collect();

            // Find a student with missing courses where we might be able to help
            let mut candidates: Vec<(StudentId, CourseId, Vec<SectionId>)> = Vec::new();

            for (student_id, requests) in &student_data {
                let assigned: FnvHashSet<CourseId> = self
                    .engine
                    .student_courses
                    .get(student_id)
                    .cloned()
                    .unwrap_or_default();

                for &course_id in requests {
                    if assigned.contains(&course_id) {
                        continue;
                    }

                    // Get all sections and check why they fail
                    let sections = self.engine.data.get_sections_for_course(course_id).to_vec();

                    // Find sections that would work if we removed a conflicting assignment
                    let mut workable_sections = Vec::new();
                    for section_id in sections {
                        let result = self.engine.try_assign(*student_id, section_id);
                        if !result.feasible {
                            // Check if it's a slot conflict we might resolve
                            let section = match self.engine.data.sections.get(&section_id) {
                                Some(s) => s,
                                None => continue,
                            };

                            // Check capacity
                            let enrollment = self.engine.section_enrollment.get(&section_id).copied().unwrap_or(0);
                            if enrollment < section.max_size {
                                workable_sections.push(section_id);
                            }
                        }
                    }

                    if !workable_sections.is_empty() {
                        candidates.push((*student_id, course_id, workable_sections));
                    }
                }
            }

            if candidates.is_empty() {
                break;
            }

            // Pick random candidate
            use rand::seq::SliceRandom;
            let (student_id, course_id, sections) = candidates.choose(&mut self.rng).unwrap().clone();

            // Try each section
            let mut placed = false;
            for section_id in sections {
                let section = match self.engine.data.sections.get(&section_id) {
                    Some(s) => s.clone(),
                    None => continue,
                };

                // Find conflicting assignment for this student
                let student_sections = self.engine.student_sections.get(&student_id).cloned().unwrap_or_default();

                let mut conflict_section: Option<SectionId> = None;
                for &existing_sid in &student_sections {
                    if let Some(existing) = self.engine.data.sections.get(&existing_sid) {
                        // Check slot overlap
                        let has_overlap = existing.slots.iter().any(|s| section.slots.contains(s));
                        if has_overlap {
                            // Check if this is a term pair (allowed overlap)
                            if !self.engine.data.is_term_pair(course_id, existing.course_id) {
                                conflict_section = Some(existing_sid);
                                break;
                            }
                        }
                    }
                }

                if let Some(conflict_sid) = conflict_section {
                    // Try to reassign the conflicting course to a different section
                    let conflict_course = self.engine.data.sections.get(&conflict_sid).map(|s| s.course_id);

                    if let Some(ccid) = conflict_course {
                        let alt_sections = self.engine.data.get_sections_for_course(ccid).to_vec();

                        for alt_sid in alt_sections {
                            if alt_sid == conflict_sid {
                                continue;
                            }

                            // Check if alternative would work
                            // This is complex - for now just try the direct assignment
                        }
                    }
                }

                // Try direct assignment
                let result = self.engine.try_assign(student_id, section_id);
                if result.feasible {
                    self.engine.commit_assign(student_id, section_id);
                    placed = true;
                    break;
                }
            }

            if !placed {
                // No progress on this candidate
            }
        }

        iterations
    }

    /// Final pass: try any remaining unassigned courses.
    fn second_pass_greedy(&mut self) {
        // Collect student data upfront to avoid borrow issues
        let student_data: Vec<(StudentId, Vec<CourseId>)> = self
            .engine
            .data
            .students
            .iter()
            .map(|(&sid, s)| (sid, s.requests.iter().copied().collect()))
            .collect();

        for (student_id, requests) in student_data {
            let assigned: FnvHashSet<CourseId> = self
                .engine
                .student_courses
                .get(&student_id)
                .cloned()
                .unwrap_or_default();

            for course_id in requests {
                if assigned.contains(&course_id) {
                    continue;
                }

                let sections = self.engine.data.get_sections_for_course(course_id).to_vec();
                for section_id in sections {
                    let result = self.engine.try_assign(student_id, section_id);
                    if result.feasible {
                        self.engine.commit_assign(student_id, section_id);
                        break;
                    }
                }
            }
        }
    }
}
