"""Command-line interface for swarm schedule."""

import argparse
from datetime import datetime, timedelta

from .core import Task, Resource
from .pso import ParticleSwarmOptimizer
from .aco import AntColonyOptimizer


def main():
    parser = argparse.ArgumentParser(description="Swarm Schedule CLI")
    parser.add_argument(
        "--algorithm",
        choices=["pso", "aco"],
        default="pso",
        help="Optimization algorithm to use",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo with sample tasks",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo(args.algorithm)
    else:
        print("Use --demo to run a demonstration")
        print("Or import swarm_schedule in your code")


def run_demo(algorithm: str):
    """Run a demonstration with sample data."""
    tasks = [
        Task(id="t1", name="Design", duration=timedelta(hours=2), priority=1),
        Task(id="t2", name="Develop", duration=timedelta(hours=4), priority=2),
        Task(id="t3", name="Test", duration=timedelta(hours=2), priority=1),
        Task(id="t4", name="Deploy", duration=timedelta(hours=1), priority=3),
    ]

    resources = [
        Resource(id="r1", name="Alice", capacity=1),
        Resource(id="r2", name="Bob", capacity=1),
    ]

    base_time = datetime(2026, 6, 1, 9, 0)

    if algorithm == "pso":
        optimizer = ParticleSwarmOptimizer(
            tasks=tasks,
            resources=resources,
            num_particles=20,
            max_iterations=50,
        )
    else:
        optimizer = AntColonyOptimizer(
            tasks=tasks,
            resources=resources,
            num_ants=15,
            max_iterations=30,
        )

    print(f"Running {algorithm.upper()} optimization...")
    schedule = optimizer.optimize(base_time)

    print(f"\nSchedule (makespan: {schedule.makespan()}):")
    for a in schedule.assignments:
        print(f"  {a.task.name}: {a.resource.name} @ {a.start_time}")


if __name__ == "__main__":
    main()
