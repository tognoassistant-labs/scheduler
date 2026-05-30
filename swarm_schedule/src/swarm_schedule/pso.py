"""Particle Swarm Optimization for scheduling."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import random
from typing import Callable

import numpy as np

from .core import Task, Resource, Schedule, Assignment


@dataclass
class Particle:
    """A particle in the swarm."""

    position: np.ndarray
    velocity: np.ndarray
    best_position: np.ndarray = field(default=None)
    best_fitness: float = float("inf")

    def __post_init__(self):
        if self.best_position is None:
            self.best_position = self.position.copy()


@dataclass
class ParticleSwarmOptimizer:
    """PSO-based scheduler."""

    tasks: list[Task]
    resources: list[Resource]
    num_particles: int = 30
    max_iterations: int = 100
    w: float = 0.7  # inertia
    c1: float = 1.5  # cognitive
    c2: float = 1.5  # social

    def _fitness(self, position: np.ndarray, base_time: datetime) -> float:
        """Evaluate fitness of a position (lower is better)."""
        schedule = self._decode(position, base_time)
        if not schedule.is_valid():
            return float("inf")
        makespan = schedule.makespan().total_seconds()
        tardiness = schedule.total_tardiness().total_seconds()
        return makespan + 10 * tardiness

    def _decode(self, position: np.ndarray, base_time: datetime) -> Schedule:
        """Decode position vector into a schedule."""
        schedule = Schedule()
        n_tasks = len(self.tasks)

        for i, task in enumerate(self.tasks):
            resource_idx = int(position[i]) % len(self.resources)
            time_offset = max(0, position[n_tasks + i])
            start = base_time + timedelta(hours=time_offset)
            schedule.add(
                Assignment(
                    task=task,
                    resource=self.resources[resource_idx],
                    start_time=start,
                )
            )
        return schedule

    def optimize(self, base_time: datetime | None = None) -> Schedule:
        """Run PSO optimization."""
        if base_time is None:
            base_time = datetime.now()

        n_tasks = len(self.tasks)
        dim = 2 * n_tasks  # resource index + time offset per task

        particles = []
        for _ in range(self.num_particles):
            pos = np.random.uniform(0, len(self.resources), dim)
            pos[n_tasks:] = np.random.uniform(0, 24, n_tasks)
            vel = np.random.uniform(-1, 1, dim)
            particles.append(Particle(position=pos, velocity=vel))

        global_best_pos = particles[0].position.copy()
        global_best_fitness = float("inf")

        for iteration in range(self.max_iterations):
            for p in particles:
                fitness = self._fitness(p.position, base_time)
                if fitness < p.best_fitness:
                    p.best_fitness = fitness
                    p.best_position = p.position.copy()
                if fitness < global_best_fitness:
                    global_best_fitness = fitness
                    global_best_pos = p.position.copy()

            for p in particles:
                r1, r2 = random.random(), random.random()
                cognitive = self.c1 * r1 * (p.best_position - p.position)
                social = self.c2 * r2 * (global_best_pos - p.position)
                p.velocity = self.w * p.velocity + cognitive + social
                p.position = p.position + p.velocity
                p.position[:n_tasks] = np.clip(
                    p.position[:n_tasks], 0, len(self.resources) - 1
                )
                p.position[n_tasks:] = np.clip(p.position[n_tasks:], 0, 168)

        return self._decode(global_best_pos, base_time)
