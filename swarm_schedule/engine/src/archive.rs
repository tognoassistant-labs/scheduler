//! MAP-Elites Quality-Diversity Archive
//!
//! Maintains a grid of high-performing schedules across behavioral axes.
//! Instead of converging to one best schedule, we keep diverse options.

use fnv::FnvHashMap;
use serde::{Deserialize, Serialize};

use crate::model::*;

/// Behavioral signature for a schedule.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Behavior {
    /// Average section fill rate (0.0 - 1.0)
    pub fill_balance: f32,
    /// Number of students with incomplete schedules
    pub incomplete_students: u32,
    /// Coverage percentage bucket (0-10 representing 0-100%)
    pub coverage_bucket: u8,
}

impl Behavior {
    /// Compute behavioral signature from assignments.
    pub fn compute(
        assignments: &[Assignment],
        sections: &FnvHashMap<SectionId, Section>,
        students: &FnvHashMap<StudentId, Student>,
    ) -> Self {
        // Count enrollments per section
        let mut section_counts: FnvHashMap<SectionId, u32> = FnvHashMap::default();
        let mut student_counts: FnvHashMap<StudentId, u32> = FnvHashMap::default();

        for a in assignments {
            *section_counts.entry(a.section_id).or_default() += 1;
            *student_counts.entry(a.student_id).or_default() += 1;
        }

        // Fill balance: stddev of fill rates
        let fill_rates: Vec<f32> = sections
            .iter()
            .filter(|(_, s)| s.max_size > 0)
            .map(|(sid, s)| {
                let count = section_counts.get(sid).copied().unwrap_or(0);
                count as f32 / s.max_size as f32
            })
            .collect();

        let fill_balance = if fill_rates.is_empty() {
            0.0
        } else {
            let mean: f32 = fill_rates.iter().sum::<f32>() / fill_rates.len() as f32;
            let variance: f32 = fill_rates.iter().map(|r| (r - mean).powi(2)).sum::<f32>()
                / fill_rates.len() as f32;
            1.0 - variance.sqrt().min(1.0) // Invert: higher = more balanced
        };

        // Incomplete students: those with fewer assignments than requests
        let incomplete_students = students
            .iter()
            .filter(|(sid, s)| {
                let assigned = student_counts.get(sid).copied().unwrap_or(0);
                assigned < s.requests.len() as u32
            })
            .count() as u32;

        // Coverage bucket
        let total_requests: u32 = students.values().map(|s| s.requests.len() as u32).sum();
        let total_assigned = assignments.len() as u32;
        let coverage = if total_requests > 0 {
            total_assigned as f32 / total_requests as f32
        } else {
            0.0
        };
        let coverage_bucket = (coverage * 10.0).min(10.0) as u8;

        Self {
            fill_balance,
            incomplete_students,
            coverage_bucket,
        }
    }

    /// Get grid cell coordinates for this behavior.
    pub fn cell(&self) -> (u8, u8, u8) {
        // Discretize to grid cells
        let fill_cell = (self.fill_balance * 5.0).min(4.0) as u8; // 0-4
        let incomplete_cell = (self.incomplete_students / 50).min(4) as u8; // 0-4 (buckets of 50)
        let coverage_cell = self.coverage_bucket; // 0-10

        (fill_cell, incomplete_cell, coverage_cell)
    }
}

/// An elite schedule in the archive.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Elite {
    pub id: String,
    pub generation: u32,
    pub seed: u64,
    pub assignments: Vec<Assignment>,
    pub behavior: Behavior,
    pub hard_violations: u32,
    pub soft_cost: i32,
    pub coverage: f32,
}

impl Elite {
    /// Fitness for comparison (lexicographic: hard first, then soft).
    pub fn fitness(&self) -> (i64, i64) {
        (-(self.hard_violations as i64), -(self.soft_cost as i64))
    }

    /// Is this elite better than another?
    pub fn is_better_than(&self, other: &Elite) -> bool {
        self.fitness() > other.fitness()
    }
}

/// MAP-Elites archive.
#[derive(Debug, Default)]
pub struct Archive {
    /// Grid of elites indexed by behavioral cell.
    elites: FnvHashMap<(u8, u8, u8), Elite>,
    /// Best overall elite.
    pub best: Option<Elite>,
    /// Statistics
    pub total_evaluated: u64,
    pub total_added: u64,
    pub total_replaced: u64,
}

impl Archive {
    pub fn new() -> Self {
        Self::default()
    }

    /// Try to add an elite to the archive.
    /// Returns true if it was added (new cell or better than existing).
    pub fn try_add(&mut self, elite: Elite) -> bool {
        self.total_evaluated += 1;

        let cell = elite.behavior.cell();

        // Update best
        if let Some(ref best) = self.best {
            if elite.is_better_than(best) {
                self.best = Some(elite.clone());
            }
        } else {
            self.best = Some(elite.clone());
        }

        // Check cell
        if let Some(existing) = self.elites.get(&cell) {
            if elite.is_better_than(existing) {
                self.elites.insert(cell, elite);
                self.total_replaced += 1;
                return true;
            }
            return false;
        }

        self.elites.insert(cell, elite);
        self.total_added += 1;
        true
    }

    /// Get number of filled cells.
    pub fn size(&self) -> usize {
        self.elites.len()
    }

    /// Get all elites.
    pub fn all_elites(&self) -> Vec<&Elite> {
        self.elites.values().collect()
    }

    /// Get top N elites by fitness.
    pub fn top_n(&self, n: usize) -> Vec<&Elite> {
        let mut elites: Vec<_> = self.elites.values().collect();
        elites.sort_by(|a, b| b.fitness().cmp(&a.fitness()));
        elites.into_iter().take(n).collect()
    }

    /// Summary statistics.
    pub fn summary(&self) -> ArchiveSummary {
        let elites: Vec<_> = self.elites.values().collect();

        if elites.is_empty() {
            return ArchiveSummary::default();
        }

        let coverages: Vec<f32> = elites.iter().map(|e| e.coverage).collect();
        let hard_violations: Vec<u32> = elites.iter().map(|e| e.hard_violations).collect();

        ArchiveSummary {
            cells_filled: elites.len(),
            best_coverage: coverages.iter().cloned().fold(0.0, f32::max),
            worst_coverage: coverages.iter().cloned().fold(1.0, f32::min),
            avg_coverage: coverages.iter().sum::<f32>() / coverages.len() as f32,
            min_hard_violations: *hard_violations.iter().min().unwrap_or(&0),
            total_evaluated: self.total_evaluated,
            total_added: self.total_added,
            total_replaced: self.total_replaced,
        }
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ArchiveSummary {
    pub cells_filled: usize,
    pub best_coverage: f32,
    pub worst_coverage: f32,
    pub avg_coverage: f32,
    pub min_hard_violations: u32,
    pub total_evaluated: u64,
    pub total_added: u64,
    pub total_replaced: u64,
}
