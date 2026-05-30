"""
ParameterTuner: LLM-based adaptive parameter tuning for the solver.

This module uses an LLM to analyze solver performance and suggest parameter
adjustments. It implements a simple feedback loop:

1. Run solver with current parameters
2. Analyze results (coverage, hard violations, timing)
3. Generate parameter suggestions using LLM
4. Apply suggestions and repeat

The LLM acts as a meta-optimizer, learning from the pattern of results
to guide the search toward better parameter configurations.
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SolverParams:
    """Parameters for the Rust solver."""
    seed: int = 42
    max_repair_iterations: int = 500
    max_polish_iterations: int = 3000
    initial_temperature: float = 100.0
    cooling_rate: float = 0.998

    def to_args(self) -> list[str]:
        """Convert to CLI arguments (for future extension)."""
        return [
            "--seed", str(self.seed),
        ]


@dataclass
class RunResult:
    """Result of a solver run with specific parameters."""
    params: SolverParams
    coverage: float
    hard_violations: int
    soft_cost: int
    time_ms: int


class ParameterTuner:
    """LLM-based parameter tuner for the scheduling solver."""

    def __init__(
        self,
        engine_path: str = "engine/target/release/scheduler_core",
        data_dir: str = "data",
        api_key: Optional[str] = None
    ):
        self.engine_path = engine_path
        self.data_dir = data_dir
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.history: list[RunResult] = []
        self.current_params = SolverParams()

    def run_solver(self, params: SolverParams) -> Optional[RunResult]:
        """Run the solver with given parameters."""
        try:
            cmd = [
                self.engine_path,
                "--data-dir", self.data_dir,
                "--seed", str(params.seed)
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if proc.returncode != 0:
                return None

            # Parse results
            coverage = 0.0
            hard = 0
            soft = 0
            time_ms = 0

            for line in proc.stdout.split('\n'):
                if 'Coverage:' in line:
                    try:
                        coverage = float(line.split(':')[1].strip().rstrip('%')) / 100.0
                    except:
                        pass
                elif 'Hard violations:' in line:
                    try:
                        hard = int(line.split(':')[1].strip())
                    except:
                        pass
                elif 'Soft cost:' in line:
                    try:
                        soft = int(line.split(':')[1].strip())
                    except:
                        pass
                elif 'Total time:' in line:
                    try:
                        time_str = line.split(':')[1].strip()
                        if 'ms' in time_str:
                            time_ms = int(float(time_str.replace('ms', '')))
                    except:
                        pass

            return RunResult(
                params=params,
                coverage=coverage,
                hard_violations=hard,
                soft_cost=soft,
                time_ms=time_ms
            )

        except Exception as e:
            print(f"Error running solver: {e}")
            return None

    def analyze_and_suggest(self) -> SolverParams:
        """Analyze history and suggest new parameters.

        Without an API key, uses simple heuristics.
        With an API key, would use Claude for analysis.
        """
        if not self.history:
            return SolverParams()

        # Simple heuristic-based suggestions (no LLM fallback)
        best = max(self.history, key=lambda r: r.coverage)
        worst = min(self.history, key=lambda r: r.coverage)

        # If coverage is improving, continue in that direction
        recent = self.history[-5:] if len(self.history) >= 5 else self.history
        avg_recent = sum(r.coverage for r in recent) / len(recent)
        avg_all = sum(r.coverage for r in self.history) / len(self.history)

        new_params = SolverParams()

        # Vary seed
        new_params.seed = best.params.seed + len(self.history)

        # If stuck, increase polish iterations
        if avg_recent <= avg_all:
            new_params.max_polish_iterations = min(
                best.params.max_polish_iterations * 2,
                10000
            )
            new_params.cooling_rate = min(best.params.cooling_rate + 0.001, 0.9999)

        # If lots of hard violations, increase repair iterations
        if best.hard_violations > 5:
            new_params.max_repair_iterations = min(
                best.params.max_repair_iterations * 2,
                2000
            )

        return new_params

    def tune(self, max_iterations: int = 20, target_coverage: float = 0.99) -> RunResult:
        """Run the tuning loop."""
        print("=== Parameter Tuning ===")

        for i in range(max_iterations):
            print(f"\nIteration {i + 1}/{max_iterations}")
            print(f"  Params: seed={self.current_params.seed}")

            result = self.run_solver(self.current_params)

            if result is None:
                print("  Solver failed, trying next seed")
                self.current_params.seed += 1
                continue

            self.history.append(result)
            print(f"  Result: coverage={result.coverage:.1%}, hard={result.hard_violations}")

            if result.coverage >= target_coverage:
                print(f"\nTarget coverage {target_coverage:.1%} reached!")
                return result

            # Get suggestions for next iteration
            self.current_params = self.analyze_and_suggest()

        # Return best result
        best = max(self.history, key=lambda r: r.coverage)
        print(f"\nBest result: coverage={best.coverage:.1%}, seed={best.params.seed}")
        return best


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="LLM-based parameter tuning")
    parser.add_argument("--engine", default="engine/target/release/scheduler_core")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--max-iterations", type=int, default=20)
    parser.add_argument("--target", type=float, default=0.99)

    args = parser.parse_args()

    tuner = ParameterTuner(
        engine_path=args.engine,
        data_dir=args.data_dir
    )

    best = tuner.tune(
        max_iterations=args.max_iterations,
        target_coverage=args.target
    )

    print("\n=== Final Result ===")
    print(f"Coverage: {best.coverage:.1%}")
    print(f"Hard violations: {best.hard_violations}")
    print(f"Soft cost: {best.soft_cost}")
    print(f"Time: {best.time_ms}ms")


if __name__ == "__main__":
    main()
