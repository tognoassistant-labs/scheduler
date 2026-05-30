//! Multi-seed runner with MAP-Elites archive.

use std::time::Instant;

use crate::archive::{Archive, Behavior, Elite};
use crate::engine::ConstraintEngine;
use crate::model::SchoolData;
use crate::solver::{Solver, SolverConfig};

/// Runner configuration.
#[derive(Debug, Clone)]
pub struct RunnerConfig {
    pub num_seeds: u32,
    pub base_seed: u64,
    pub max_repair_iterations: u32,
    pub max_polish_iterations: u32,
}

impl Default for RunnerConfig {
    fn default() -> Self {
        Self {
            num_seeds: 20,
            base_seed: 42,
            max_repair_iterations: 500,
            max_polish_iterations: 2000,
        }
    }
}

/// Result of a multi-seed run.
#[derive(Debug)]
pub struct RunResult {
    pub archive: Archive,
    pub total_time_ms: u64,
    pub runs_completed: u32,
}

/// Run multiple seeds and populate archive.
pub fn run_multi_seed(data: SchoolData, config: RunnerConfig) -> RunResult {
    let start = Instant::now();
    let mut archive = Archive::new();

    println!("=== Multi-Seed Runner ===");
    println!("Seeds: {}", config.num_seeds);
    println!();

    for i in 0..config.num_seeds {
        let seed = config.base_seed + i as u64;

        // Create fresh engine for each run
        let engine = ConstraintEngine::new(data.clone());

        let solver_config = SolverConfig {
            seed,
            max_repair_iterations: config.max_repair_iterations,
            max_polish_iterations: config.max_polish_iterations,
            initial_temperature: 100.0,
            cooling_rate: 0.998,
        };

        let mut solver = Solver::new(engine, solver_config);
        let result = solver.solve();

        // Compute behavior
        let behavior = Behavior::compute(
            &result.assignments,
            &solver.engine.data.sections,
            &solver.engine.data.students,
        );

        let elite = Elite {
            id: format!("seed_{}", seed),
            generation: 0,
            seed,
            assignments: result.assignments,
            behavior,
            hard_violations: result.hard_violations,
            soft_cost: result.soft_cost,
            coverage: result.coverage as f32,
        };

        let added = archive.try_add(elite);

        println!(
            "Seed {}: coverage={:.1}%, hard={}, soft={} {}",
            seed,
            result.coverage * 100.0,
            result.hard_violations,
            result.soft_cost,
            if added { "[ADDED]" } else { "" }
        );
    }

    let total_time = start.elapsed().as_millis() as u64;

    println!();
    println!("=== Archive Summary ===");
    let summary = archive.summary();
    println!("Cells filled: {}", summary.cells_filled);
    println!("Best coverage: {:.1}%", summary.best_coverage * 100.0);
    println!("Avg coverage: {:.1}%", summary.avg_coverage * 100.0);
    println!("Min hard violations: {}", summary.min_hard_violations);
    println!("Total time: {}ms", total_time);

    if let Some(ref best) = archive.best {
        println!();
        println!("=== Best Solution ===");
        println!("ID: {}", best.id);
        println!("Coverage: {:.1}%", best.coverage * 100.0);
        println!("Hard violations: {}", best.hard_violations);
        println!("Soft cost: {}", best.soft_cost);
    }

    RunResult {
        archive,
        total_time_ms: total_time,
        runs_completed: config.num_seeds,
    }
}
