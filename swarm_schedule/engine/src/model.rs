//! Core data model for school scheduling.

use fnv::{FnvHashMap, FnvHashSet};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

pub type StudentId = u32;
pub type SectionId = u32;
pub type CourseId = u16;
pub type TeacherId = u16;
pub type Slot = u8; // 0-24 for 5 days x 5 periods

/// A section in the master schedule (fixed).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Section {
    pub id: SectionId,
    pub course_id: CourseId,
    pub teacher_id: TeacherId,
    pub slots: BTreeSet<Slot>,
    pub max_size: u16,
    pub name: String,
}

/// A student with their course requests.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Student {
    pub id: StudentId,
    pub grade: u8,
    pub requests: FnvHashSet<CourseId>,
    pub required: FnvHashSet<CourseId>,
    pub name: String,
}

/// An assignment of a student to a section.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Assignment {
    pub student_id: StudentId,
    pub section_id: SectionId,
}

/// A complete schedule: all assignments.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Schedule {
    pub assignments: Vec<Assignment>,
    pub generation: u32,
    pub id: String,
    pub parent_ids: Vec<String>,
    pub created_by: String,
}

impl Schedule {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_id(id: String) -> Self {
        Self {
            id,
            ..Default::default()
        }
    }
}

/// School data: all sections, students, and constraints.
#[derive(Debug, Clone, Default)]
pub struct SchoolData {
    pub sections: FnvHashMap<SectionId, Section>,
    pub students: FnvHashMap<StudentId, Student>,
    pub courses: FnvHashMap<CourseId, String>, // course_id -> name

    // Constraint data
    pub term_pairs: Vec<(CourseId, CourseId)>,
    pub simultaneous_pairs: Vec<(CourseId, CourseId)>,
    pub ta_assignments: FnvHashMap<StudentId, (CourseId, TeacherId)>,
    pub teacher_avoid: FnvHashMap<StudentId, FnvHashSet<TeacherId>>,
    pub student_separate: Vec<(StudentId, StudentId)>,
    pub student_together: Vec<(StudentId, StudentId)>,

    // Indexes for fast lookup
    pub sections_by_course: FnvHashMap<CourseId, Vec<SectionId>>,
    pub sections_by_slot: FnvHashMap<Slot, Vec<SectionId>>,
}

impl SchoolData {
    pub fn new() -> Self {
        Self::default()
    }

    /// Build indexes after loading data.
    pub fn build_indexes(&mut self) {
        self.sections_by_course.clear();
        self.sections_by_slot.clear();

        for (&sid, section) in &self.sections {
            self.sections_by_course
                .entry(section.course_id)
                .or_default()
                .push(sid);

            for &slot in &section.slots {
                self.sections_by_slot
                    .entry(slot)
                    .or_default()
                    .push(sid);
            }
        }
    }

    /// Get all sections for a course.
    pub fn get_sections_for_course(&self, course_id: CourseId) -> &[SectionId] {
        self.sections_by_course
            .get(&course_id)
            .map(|v| v.as_slice())
            .unwrap_or(&[])
    }

    /// Check if two courses are a term pair (can share slots).
    pub fn is_term_pair(&self, a: CourseId, b: CourseId) -> bool {
        self.term_pairs.iter().any(|&(c1, c2)| {
            (a == c1 && b == c2) || (a == c2 && b == c1)
        })
    }
}

/// Parse slot string (e.g., "A3" -> slot number).
/// A=0, B=1, C=2, D=3, E=4; periods 1-5.
pub fn parse_slot(s: &str) -> Option<Slot> {
    if s.len() != 2 {
        return None;
    }
    let day = match s.chars().next()? {
        'A' => 0,
        'B' => 1,
        'C' => 2,
        'D' => 3,
        'E' => 4,
        _ => return None,
    };
    let period: u8 = s[1..].parse().ok()?;
    if period < 1 || period > 5 {
        return None;
    }
    Some(day * 5 + (period - 1))
}

/// Format slot number back to string (e.g., 3 -> "A4").
pub fn format_slot(slot: Slot) -> String {
    let day = ['A', 'B', 'C', 'D', 'E'][(slot / 5) as usize];
    let period = (slot % 5) + 1;
    format!("{}{}", day, period)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_slot() {
        assert_eq!(parse_slot("A1"), Some(0));
        assert_eq!(parse_slot("A5"), Some(4));
        assert_eq!(parse_slot("B1"), Some(5));
        assert_eq!(parse_slot("E5"), Some(24));
        assert_eq!(parse_slot("E3"), Some(22));
    }

    #[test]
    fn test_format_slot() {
        assert_eq!(format_slot(0), "A1");
        assert_eq!(format_slot(4), "A5");
        assert_eq!(format_slot(5), "B1");
        assert_eq!(format_slot(22), "E3");
        assert_eq!(format_slot(24), "E5");
    }
}
