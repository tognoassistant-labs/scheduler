"""Tests for optimization algorithms."""

from datetime import datetime, timedelta

from swarm_schedule.core import Task, Resource
from swarm_schedule.pso import ParticleSwarmOptimizer
from swarm_schedule.aco import AntColonyOptimizer


def _sample_tasks():
    return [
        Task(id="t1", name="Task1", duration=timedelta(hours=1)),
        Task(id="t2", name="Task2", duration=timedelta(hours=2)),
    ]


def _sample_resources():
    return [
        Resource(id="r1", name="R1"),
        Resource(id="r2", name="R2"),
    ]


def test_pso_produces_valid_schedule():
    optimizer = ParticleSwarmOptimizer(
        tasks=_sample_tasks(),
        resources=_sample_resources(),
        num_particles=10,
        max_iterations=20,
    )
    schedule = optimizer.optimize(datetime(2026, 1, 1, 9, 0))
    assert len(schedule.assignments) == 2
    assert schedule.is_valid()


def test_aco_produces_valid_schedule():
    optimizer = AntColonyOptimizer(
        tasks=_sample_tasks(),
        resources=_sample_resources(),
        num_ants=10,
        max_iterations=20,
    )
    schedule = optimizer.optimize(datetime(2026, 1, 1, 9, 0))
    assert len(schedule.assignments) == 2
    assert schedule.is_valid()
