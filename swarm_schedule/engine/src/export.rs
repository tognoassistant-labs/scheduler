//! CSV export for student schedules.

use std::collections::HashMap;
use std::error::Error;
use std::fs::File;
use std::io::Write;
use std::path::Path;

use crate::engine::ConstraintEngine;
use crate::loader::{COURSE_ID_MAP, SECTION_ID_MAP};
use crate::model::*;

/// Export schedule to student_schedules_friendly.csv
pub fn export_schedule(
    engine: &ConstraintEngine,
    output_path: &Path,
) -> Result<usize, Box<dyn Error>> {
    let mut file = File::create(output_path)?;

    // Header
    writeln!(
        file,
        "StudentID,StudentName,Grade,CourseID,CourseName,SectionID,Period,Slots,TeacherID,TeacherName,RoomID,RoomName"
    )?;

    // Build reverse lookup maps
    let section_names: HashMap<SectionId, String> = {
        let map = SECTION_ID_MAP.lock().unwrap();
        map.iter().map(|(k, &v)| (v, k.clone())).collect()
    };

    let course_names: HashMap<CourseId, String> = {
        let map = COURSE_ID_MAP.lock().unwrap();
        map.iter().map(|(k, &v)| (v, k.clone())).collect()
    };

    // Build slot -> period mapping
    let mut slot_sets: Vec<String> = Vec::new();
    for section in engine.data.sections.values() {
        let slots_str: String = section
            .slots
            .iter()
            .map(|&s| format_slot(s))
            .collect::<Vec<_>>()
            .join(";");
        if !slots_str.is_empty() && !slot_sets.contains(&slots_str) {
            slot_sets.push(slots_str);
        }
    }
    slot_sets.sort();
    let slot_to_period: HashMap<String, usize> = slot_sets
        .iter()
        .enumerate()
        .map(|(i, s)| (s.clone(), i + 1))
        .collect();

    let mut count = 0;

    // Export each assignment
    for (&student_id, sections) in &engine.student_sections {
        let student = match engine.data.students.get(&student_id) {
            Some(s) => s,
            None => continue,
        };

        for &section_id in sections {
            let section = match engine.data.sections.get(&section_id) {
                Some(s) => s,
                None => continue,
            };

            let section_name = section_names
                .get(&section_id)
                .cloned()
                .unwrap_or_else(|| format!("{}", section_id));

            let course_code = course_names
                .get(&section.course_id)
                .cloned()
                .unwrap_or_else(|| format!("{}", section.course_id));

            let course_name = engine
                .data
                .courses
                .get(&section.course_id)
                .cloned()
                .unwrap_or_default();

            let slots_str: String = section
                .slots
                .iter()
                .map(|&s| format_slot(s))
                .collect::<Vec<_>>()
                .join(";");

            let period = slot_to_period.get(&slots_str).copied().unwrap_or(0);

            writeln!(
                file,
                "{},{},{},{},{},{},{},{},{},,,",
                student_id,
                "",  // StudentName
                student.grade,
                course_code,
                course_name,
                section_name,
                period,
                slots_str,
                section.teacher_id,
            )?;

            count += 1;
        }
    }

    Ok(count)
}
