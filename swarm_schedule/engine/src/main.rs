//! Scheduler Core - Constraint engine + solver for school scheduling.
//!
//! Architecture (from swarm_scheduler_agent_instructions_v2.md):
//! - Constraint engine is the single source of mechanical truth
//! - Live domains + propagation (AC-3 style)
//! - Incremental backtrackable state (push/pop)
//! - Greedy construction → min-conflicts repair → SA polish
//! - MAP-Elites quality-diversity archive
//!
//! Usage:
//!   cargo run --release -- --data-dir ../data
//!   cargo run --release -- --data-dir ../data --multi-seed 20

mod archive;
mod engine;
mod export;
mod loader;
mod model;
mod runner;
mod solver;

use std::env;
use std::path::PathBuf;
use std::time::Instant;

use engine::ConstraintEngine;
use runner::{run_multi_seed, RunnerConfig};
use solver::{Solver, SolverConfig};

fn main() {
    let args: Vec<String> = env::args().collect();

    let data_dir = if let Some(idx) = args.iter().position(|a| a == "--data-dir") {
        PathBuf::from(args.get(idx + 1).expect("--data-dir requires a path"))
    } else {
        PathBuf::from("../data")
    };

    let seed: u64 = args
        .iter()
        .position(|a| a == "--seed")
        .and_then(|idx| args.get(idx + 1))
        .and_then(|s| s.parse().ok())
        .unwrap_or(42);

    let multi_seed: Option<u32> = args
        .iter()
        .position(|a| a == "--multi-seed")
        .and_then(|idx| args.get(idx + 1))
        .and_then(|s| s.parse().ok());

    // Load data
    let start = Instant::now();
    let school_data = match loader::load_school_data(&data_dir) {
        Ok(data) => data,
        Err(e) => {
            eprintln!("Error loading data: {}", e);
            return;
        }
    };
    println!("Data loaded in {:?}", start.elapsed());
    println!();

    // Multi-seed mode with MAP-Elites
    if let Some(num_seeds) = multi_seed {
        let config = RunnerConfig {
            num_seeds,
            base_seed: seed,
            max_repair_iterations: 500,
            max_polish_iterations: 3000,
        };

        let result = run_multi_seed(school_data, config);

        // Export best solution
        if let Some(ref best) = result.archive.best {
            // Re-create engine to export
            let output_path = data_dir.join("../student_schedules_rust.csv");
            println!("\nBest solution has {} assignments", best.assignments.len());

            // Write assignments directly
            if let Ok(mut file) = std::fs::File::create(&output_path) {
                use std::io::Write;
                writeln!(file, "StudentID,StudentName,Grade,CourseID,CourseName,SectionID,Period,Slots,TeacherID,TeacherName,RoomID,RoomName").ok();
                for a in &best.assignments {
                    writeln!(file, "{},,,,,{},,,,,,", a.student_id, a.section_id).ok();
                }
                println!("Exported to {:?}", output_path);
            }
        }

        return;
    }

    // Single-seed mode
    println!("=== Scheduler Core ===");
    println!("Data dir: {:?}", data_dir);
    println!("Seed: {}", seed);
    println!();

    // Create engine
    let engine = ConstraintEngine::new(school_data);
    let stats = engine.stats();
    println!("Engine initialized:");
    println!("  Students: {}", stats.students);
    println!("  Sections: {}", stats.sections);
    println!("  Total requests: {}", stats.total_requests);
    println!();

    // Configure solver
    let config = SolverConfig {
        seed,
        max_repair_iterations: 500,
        max_polish_iterations: 5000,
        initial_temperature: 100.0,
        cooling_rate: 0.998,
    };

    // Run solver
    println!("=== Running Solver ===");
    let mut solver = Solver::new(engine, config);
    let result = solver.solve();

    println!();
    println!("=== Results ===");
    println!("Assignments: {}", result.assignments.len());
    println!("Coverage: {:.1}%", result.coverage * 100.0);
    println!("Hard violations: {}", result.hard_violations);
    println!("Soft cost: {}", result.soft_cost);
    println!();
    println!("Timing:");
    println!("  Construction: {}ms", result.construction_time_ms);
    println!(
        "  Repair: {}ms ({} iterations)",
        result.repair_time_ms, result.repair_iterations
    );
    println!(
        "  Polish: {}ms ({} iterations)",
        result.polish_time_ms, result.polish_iterations
    );

    // Engine stats
    let final_stats = solver.engine.stats();
    println!();
    println!("=== Engine Stats ===");
    println!("  Propagations: {}", final_stats.propagations);
    println!("  Domain prunes: {}", final_stats.domain_prunes);

    // Export to CSV
    let output_path = data_dir.join("../student_schedules_rust.csv");
    match export::export_schedule(&solver.engine, &output_path) {
        Ok(count) => println!("\nExported {} assignments to {:?}", count, output_path),
        Err(e) => eprintln!("\nFailed to export: {}", e),
    }
}
