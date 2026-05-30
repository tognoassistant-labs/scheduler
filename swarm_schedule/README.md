# Swarm Schedule

A high-performance constraint-based scheduling engine with MAP-Elites quality-diversity search.

## Overview

Swarm Schedule assigns students to course sections while respecting hard constraints (capacity, slot conflicts, separation rules) and optimizing soft constraints (coverage, balance). It uses:

1. **Rust Constraint Engine** - Fast incremental propagation with live domains
2. **Greedy Construction** - MRV (Most Restrained Variable) heuristic
3. **Swap-Based Repair** - Relocate blocking assignments to make room
4. **Simulated Annealing** - Escape local optima via random moves
5. **MAP-Elites Archive** - Maintain diverse high-quality solutions
6. **Python Coordination** - Distributed solving and adaptive tuning

## Results

On Columbus HS data (509 students, 249 sections, 4611 course requests):

| Solver | Coverage | Time |
|--------|----------|------|
| Rust (single seed) | 97.6% | 0.25s |
| Rust (best of 50) | **98.2%** | 12.4s |
| OR-Tools CP-SAT | 99.8% | 12.4s |

The Rust solver achieves competitive coverage with much faster individual solves, enabling multi-seed exploration.

## Installation

### Rust Engine

```bash
cd engine
cargo build --release
```

### Python Coordination Layer

```bash
cd swarm_schedule
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### Single Solve

```bash
cd engine
./target/release/scheduler_core --data-dir ../data --seed 42
```

### Multi-Seed with MAP-Elites

```bash
./target/release/scheduler_core --data-dir ../data --multi-seed 50
```

### Python Coordinator

```bash
python -m src.swarm_schedule.agents.coordinator \
    --engine engine/target/release/scheduler_core \
    --data-dir data \
    --seeds-per-batch 10 \
    --max-rounds 5 \
    --target 0.99
```

## Project Structure

```
swarm_schedule/
├── engine/                     # Rust constraint engine
│   └── src/
│       ├── main.rs            # CLI entry point
│       ├── engine.rs          # Constraint engine with domains
│       ├── solver.rs          # Greedy + repair + SA
│       ├── archive.rs         # MAP-Elites archive
│       ├── runner.rs          # Multi-seed runner
│       ├── model.rs           # Data structures
│       ├── loader.rs          # CSV parsing
│       └── export.rs          # CSV export
│
├── src/swarm_schedule/
│   └── agents/
│       ├── coordinator.py     # Distributed work distribution
│       ├── parameter_tuner.py # Adaptive parameter optimization
│       └── messaging.py       # NATS/local message bus
│
├── data/                       # Input CSV files
├── baseline_ortools.py         # OR-Tools comparison baseline
└── student_schedules_rust.csv  # Output schedules
```

## Constraint Model

### Hard Constraints (must satisfy)
- H1: No double-booking (student in one place at a time)
- H2: Section capacity limits
- H7: One section per course per student
- H12: Separation rules (keep certain student pairs apart)

### Soft Constraints (optimize)
- S1: Maximize coverage (% of requests satisfied)
- S2: Balance section enrollments
- S3: Minimize hard violation count

## Architecture

The system follows an engine-centric design:

1. **Constraint Engine** is the single source of truth for feasibility
2. **Domains** track legal values for each (student, course) pair
3. **Propagation** prunes domains after each assignment
4. **Trail** enables backtracking via push/pop checkpoints
5. **Solver** orchestrates construction, repair, and polish phases
6. **Archive** maintains diverse elite solutions across behavioral dimensions

## NATS Coordination (Optional)

When `nats-py` is installed and a NATS server is available, the coordinator uses pub/sub for distributed work. Otherwise it falls back to local sequential execution.

```bash
pip install nats-py
# Start NATS server separately
python -m src.swarm_schedule.agents.coordinator --use-nats
```
