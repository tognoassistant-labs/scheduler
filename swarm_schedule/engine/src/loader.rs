//! CSV data loader.

use fnv::{FnvHashMap, FnvHashSet};
use std::collections::BTreeSet;
use std::error::Error;
use std::path::Path;

use crate::model::*;

/// Load school data from CSV files.
pub fn load_school_data(data_dir: &Path) -> Result<SchoolData, Box<dyn Error>> {
    let mut data = SchoolData::new();

    // Load sections
    load_sections(&mut data, &data_dir.join("sections.csv"))?;

    // Load courses
    load_courses(&mut data, &data_dir.join("courses.csv"))?;

    // Load students and requests
    load_requests(&mut data, &data_dir.join("course_requests.csv"))?;

    // Load constraints
    load_course_relationships(&mut data, &data_dir.join("course_relationships.csv"))?;
    load_teacher_assistants(&mut data, &data_dir.join("teacher_assistants.csv"))?;
    load_teacher_avoid(&mut data, &data_dir.join("teacher_avoid.csv"))?;
    load_student_pair_constraints(&mut data, &data_dir.join("student_pair_constraints.csv"))?;

    // Apply request changes if present
    let _ = apply_request_changes(&mut data, &data_dir.join("student_requests_changes.csv"));

    data.build_indexes();
    Ok(data)
}

fn load_sections(data: &mut SchoolData, path: &Path) -> Result<(), Box<dyn Error>> {
    let mut rdr = csv::Reader::from_path(path)?;

    for result in rdr.records() {
        let record = result?;

        let section_id_str = &record[0];
        let course_id_str = &record[1];
        let teacher_id: TeacherId = record[2].parse().unwrap_or(0);
        let _room_id = &record[3];
        let max_size: u16 = record[4].parse().unwrap_or(25);
        let _grade_level: u8 = record[5].parse().unwrap_or(0);
        let slots_str = &record[6];

        // Parse section_id to numeric (e.g., "A0901.1" -> hash)
        let section_id: SectionId = get_section_id(section_id_str);
        let course_id: CourseId = get_course_id(course_id_str);

        // Parse slots
        let mut slots = BTreeSet::new();
        for slot_str in slots_str.split(';') {
            if let Some(slot) = parse_slot(slot_str.trim()) {
                slots.insert(slot);
            }
        }

        data.sections.insert(
            section_id,
            Section {
                id: section_id,
                course_id,
                teacher_id,
                slots,
                max_size,
                name: section_id_str.to_string(),
            },
        );
    }

    println!("Loaded {} sections", data.sections.len());
    Ok(())
}

fn load_courses(data: &mut SchoolData, path: &Path) -> Result<(), Box<dyn Error>> {
    let mut rdr = csv::Reader::from_path(path)?;

    for result in rdr.records() {
        let record = result?;
        let course_id_str = &record[0];
        let name = &record[1];

        let course_id: CourseId = get_course_id(course_id_str);
        data.courses.insert(course_id, name.to_string());
    }

    println!("Loaded {} courses", data.courses.len());
    Ok(())
}

fn load_requests(data: &mut SchoolData, path: &Path) -> Result<(), Box<dyn Error>> {
    let mut rdr = csv::Reader::from_path(path)?;

    for result in rdr.records() {
        let record = result?;

        let student_id_str = &record[0];
        let course_id_str = &record[1];
        let _enrollment_state = &record[2];
        let is_required: bool = record.get(3).map(|s| s == "1").unwrap_or(false);

        let student_id: StudentId = student_id_str.parse().unwrap_or(0);
        let course_id: CourseId = get_course_id(course_id_str);

        let student = data.students.entry(student_id).or_insert_with(|| Student {
            id: student_id,
            grade: 0,
            requests: FnvHashSet::default(),
            required: FnvHashSet::default(),
            name: student_id_str.to_string(),
        });

        student.requests.insert(course_id);
        if is_required {
            student.required.insert(course_id);
        }
    }

    println!("Loaded {} students with requests", data.students.len());
    Ok(())
}

fn load_course_relationships(data: &mut SchoolData, path: &Path) -> Result<(), Box<dyn Error>> {
    let mut rdr = csv::Reader::from_path(path)?;

    for result in rdr.records() {
        let record = result?;

        let course_a_str = &record[0];
        let course_b_str = &record[1];
        let rel_code = &record[3];

        let course_a: CourseId = get_course_id(course_a_str);
        let course_b: CourseId = get_course_id(course_b_str);

        match rel_code {
            "Term" => data.term_pairs.push((course_a, course_b)),
            "Simultaneous" => data.simultaneous_pairs.push((course_a, course_b)),
            _ => {}
        }
    }

    println!(
        "Loaded {} term pairs, {} simultaneous pairs",
        data.term_pairs.len(),
        data.simultaneous_pairs.len()
    );
    Ok(())
}

fn load_teacher_assistants(data: &mut SchoolData, path: &Path) -> Result<(), Box<dyn Error>> {
    let mut rdr = csv::Reader::from_path(path)?;

    for result in rdr.records() {
        let record = result?;

        let student_id: StudentId = record[0].parse().unwrap_or(0);
        let course_id_str = &record[1];
        let teacher_id: TeacherId = record[2].parse().unwrap_or(0);

        let course_id: CourseId = get_course_id(course_id_str);
        data.ta_assignments.insert(student_id, (course_id, teacher_id));
    }

    println!("Loaded {} TA assignments", data.ta_assignments.len());
    Ok(())
}

fn load_teacher_avoid(data: &mut SchoolData, path: &Path) -> Result<(), Box<dyn Error>> {
    let mut rdr = csv::Reader::from_path(path)?;

    for result in rdr.records() {
        let record = result?;

        let student_id: StudentId = record[0].parse().unwrap_or(0);
        // Teacher name is in column 2, but we need teacher ID
        // For now, skip if we can't map
        // In real implementation, we'd need a teacher name -> ID lookup

        data.teacher_avoid.entry(student_id).or_default();
    }

    println!("Loaded {} teacher avoid rules", data.teacher_avoid.len());
    Ok(())
}

fn load_student_pair_constraints(
    data: &mut SchoolData,
    path: &Path,
) -> Result<(), Box<dyn Error>> {
    let mut rdr = csv::Reader::from_path(path)?;

    for result in rdr.records() {
        let record = result?;

        let student_a: StudentId = record[0].parse::<f64>().unwrap_or(0.0) as u32;
        let student_b: StudentId = record[1].parse::<f64>().unwrap_or(0.0) as u32;
        let relation = &record[2];

        if relation.contains("separate") || relation == "separate" {
            data.student_separate.push((student_a, student_b));
        } else {
            data.student_together.push((student_a, student_b));
        }
    }

    println!(
        "Loaded {} separate pairs, {} together pairs",
        data.student_separate.len(),
        data.student_together.len()
    );
    Ok(())
}

fn apply_request_changes(data: &mut SchoolData, path: &Path) -> Result<(), Box<dyn Error>> {
    let mut rdr = csv::Reader::from_path(path)?;
    let mut added = 0;
    let mut dropped = 0;

    for result in rdr.records() {
        let record = result?;

        let student_id: StudentId = record[0].parse().unwrap_or(0);
        let course_id_str = &record[1];
        let action = &record[2];

        let course_id: CourseId = get_course_id(course_id_str);

        if let Some(student) = data.students.get_mut(&student_id) {
            match action {
                "add" => {
                    student.requests.insert(course_id);
                    added += 1;
                }
                "drop" => {
                    student.requests.remove(&course_id);
                    student.required.remove(&course_id);
                    dropped += 1;
                }
                _ => {}
            }
        }
    }

    if added > 0 || dropped > 0 {
        println!("Applied request changes: {} added, {} dropped", added, dropped);
    }
    Ok(())
}

// Global ID mappings to ensure consistency
use std::sync::Mutex;
use std::collections::HashMap;

lazy_static::lazy_static! {
    static ref SECTION_ID_MAP: Mutex<HashMap<String, SectionId>> = Mutex::new(HashMap::new());
    static ref COURSE_ID_MAP: Mutex<HashMap<String, CourseId>> = Mutex::new(HashMap::new());
    static ref SECTION_COUNTER: Mutex<SectionId> = Mutex::new(1);
    static ref COURSE_COUNTER: Mutex<CourseId> = Mutex::new(1);
}

/// Get or create section ID.
fn get_section_id(s: &str) -> SectionId {
    let mut map = SECTION_ID_MAP.lock().unwrap();
    if let Some(&id) = map.get(s) {
        return id;
    }
    let mut counter = SECTION_COUNTER.lock().unwrap();
    let id = *counter;
    *counter += 1;
    map.insert(s.to_string(), id);
    id
}

/// Get or create course ID.
fn get_course_id(s: &str) -> CourseId {
    let mut map = COURSE_ID_MAP.lock().unwrap();
    if let Some(&id) = map.get(s) {
        return id;
    }
    let mut counter = COURSE_COUNTER.lock().unwrap();
    let id = *counter;
    *counter += 1;
    map.insert(s.to_string(), id);
    id
}
