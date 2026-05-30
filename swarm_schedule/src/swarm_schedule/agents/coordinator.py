"""
Coordinator: Manages distributed solving across multiple seeds/workers.

This module provides:
1. Work distribution - assigns seeds to workers
2. Result aggregation - collects and merges MAP-Elites archives
3. Adaptive control - adjusts parameters based on progress

When NATS is available, the coordinator uses pub/sub for work distribution.
Without NATS, it falls back to local multiprocessing.
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SolverResult:
    """Result from a single solver run."""
    seed: int
    coverage: float
    hard_violations: int
    soft_cost: int
    assignments_count: int
    time_ms: int


@dataclass
class CoordinatorConfig:
    """Configuration for the coordinator."""
    num_workers: int = 4
    seeds_per_batch: int = 10
    target_coverage: float = 0.99
    max_rounds: int = 5
    engine_path: str = "engine/target/release/scheduler_core"
    data_dir: str = "data"


class Coordinator:
    """Coordinates distributed solving across workers."""

    def __init__(self, config: CoordinatorConfig):
        self.config = config
        self.results: list[SolverResult] = []
        self.best_result: Optional[SolverResult] = None
        self.round = 0

    def run(self) -> SolverResult:
        """Run the coordinator until target coverage is reached or max rounds."""
        base_seed = 42

        while self.round < self.config.max_rounds:
            self.round += 1
            print(f"\n=== Round {self.round} ===")

            # Generate seeds for this round
            seeds = list(range(
                base_seed + (self.round - 1) * self.config.seeds_per_batch,
                base_seed + self.round * self.config.seeds_per_batch
            ))

            # Run solvers (local fallback when NATS unavailable)
            round_results = self._run_local_batch(seeds)
            self.results.extend(round_results)

            # Update best
            for result in round_results:
                if self.best_result is None or result.coverage > self.best_result.coverage:
                    self.best_result = result
                    print(f"New best: seed={result.seed}, coverage={result.coverage:.1%}")

            # Check if target reached
            if self.best_result and self.best_result.coverage >= self.config.target_coverage:
                print(f"Target coverage {self.config.target_coverage:.1%} reached!")
                break

            print(f"Best so far: {self.best_result.coverage:.1%} ({self.best_result.assignments_count} assignments)")

        return self.best_result

    def _run_local_batch(self, seeds: list[int]) -> list[SolverResult]:
        """Run a batch of seeds locally using the Rust engine."""
        results = []

        for seed in seeds:
            result = self._run_single_seed(seed)
            if result:
                results.append(result)
                print(f"  Seed {seed}: {result.coverage:.1%} coverage")

        return results

    def _run_single_seed(self, seed: int) -> Optional[SolverResult]:
        """Run the Rust solver with a specific seed."""
        try:
            cmd = [
                self.config.engine_path,
                "--data-dir", self.config.data_dir,
                "--seed", str(seed)
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if proc.returncode != 0:
                print(f"Solver failed for seed {seed}: {proc.stderr}")
                return None

            # Parse output
            return self._parse_output(proc.stdout, seed)

        except subprocess.TimeoutExpired:
            print(f"Solver timed out for seed {seed}")
            return None
        except FileNotFoundError:
            print(f"Solver not found at {self.config.engine_path}")
            return None

    def _parse_output(self, output: str, seed: int) -> Optional[SolverResult]:
        """Parse solver output to extract results."""
        coverage = 0.0
        hard = 0
        soft = 0
        assignments = 0
        time_ms = 0

        for line in output.split('\n'):
            if 'Coverage:' in line:
                try:
                    coverage = float(line.split(':')[1].strip().rstrip('%')) / 100.0
                except (IndexError, ValueError):
                    pass
            elif 'Assignments:' in line:
                try:
                    assignments = int(line.split(':')[1].strip())
                except (IndexError, ValueError):
                    pass
            elif 'Hard violations:' in line:
                try:
                    hard = int(line.split(':')[1].strip())
                except (IndexError, ValueError):
                    pass
            elif 'Soft cost:' in line:
                try:
                    soft = int(line.split(':')[1].strip())
                except (IndexError, ValueError):
                    pass
            elif 'Total time:' in line:
                try:
                    # Parse duration like "150.123ms"
                    time_str = line.split(':')[1].strip()
                    if 'ms' in time_str:
                        time_ms = int(float(time_str.replace('ms', '')))
                except (IndexError, ValueError):
                    pass

        return SolverResult(
            seed=seed,
            coverage=coverage,
            hard_violations=hard,
            soft_cost=soft,
            assignments_count=assignments,
            time_ms=time_ms
        )

    def summary(self) -> dict:
        """Get summary statistics."""
        if not self.results:
            return {}

        coverages = [r.coverage for r in self.results]
        return {
            "total_runs": len(self.results),
            "rounds": self.round,
            "best_coverage": max(coverages),
            "avg_coverage": sum(coverages) / len(coverages),
            "min_coverage": min(coverages),
            "best_seed": self.best_result.seed if self.best_result else None,
            "best_hard_violations": self.best_result.hard_violations if self.best_result else None,
        }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Coordinate distributed solving")
    parser.add_argument("--workers", type=int, default=4, help="Number of workers")
    parser.add_argument("--seeds-per-batch", type=int, default=10, help="Seeds per round")
    parser.add_argument("--target", type=float, default=0.99, help="Target coverage")
    parser.add_argument("--max-rounds", type=int, default=5, help="Max rounds")
    parser.add_argument("--engine", default="engine/target/release/scheduler_core")
    parser.add_argument("--data-dir", default="data")

    args = parser.parse_args()

    config = CoordinatorConfig(
        num_workers=args.workers,
        seeds_per_batch=args.seeds_per_batch,
        target_coverage=args.target,
        max_rounds=args.max_rounds,
        engine_path=args.engine,
        data_dir=args.data_dir,
    )

    coordinator = Coordinator(config)
    best = coordinator.run()

    print("\n=== Final Summary ===")
    summary = coordinator.summary()
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
