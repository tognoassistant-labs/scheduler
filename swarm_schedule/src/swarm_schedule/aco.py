"""Ant Colony Optimization for scheduling."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import random

import numpy as np

from .core import Task, Resource, Schedule, Assignment


@dataclass
class AntColonyOptimizer:
    """ACO-based scheduler for discrete assignment problems."""

    tasks: list[Task]
    resources: list[Resource]
    num_ants: int = 20
    max_iterations: int = 50
    alpha: float = 1.0  # pheromone importance
    beta: float = 2.0  # heuristic importance
    evaporation: float = 0.5
    q: float = 100  # pheromone deposit factor

    def __post_init__(self):
        n = len(self.tasks)
        m = len(self.resources)
        self.pheromone = np.ones((n, m))

    def _heuristic(self, task_idx: int, resource_idx: int) -> float:
        """Heuristic value for assigning task to resource."""
        return 1.0 / (1.0 + self.resources[resource_idx].capacity)

    def _construct_solution(self, base_time: datetime) -> Schedule:
        """Single ant constructs a solution."""
        schedule = Schedule()
        resource_end_times: dict[str, datetime] = {}

        for i, task in enumerate(self.tasks):
            probs = []
            for j in range(len(self.resources)):
                tau = self.pheromone[i, j] ** self.alpha
                eta = self._heuristic(i, j) ** self.beta
                probs.append(tau * eta)

            total = sum(probs)
            probs = [p / total for p in probs]
            chosen = random.choices(range(len(self.resources)), weights=probs)[0]

            resource = self.resources[chosen]
            start = resource_end_times.get(resource.id, base_time)
            resource_end_times[resource.id] = start + task.duration

            schedule.add(Assignment(task=task, resource=resource, start_time=start))

        return schedule

    def _evaluate(self, schedule: Schedule) -> float:
        """Lower is better."""
        if not schedule.is_valid():
            return float("inf")
        return schedule.makespan().total_seconds()

    def optimize(self, base_time: datetime | None = None) -> Schedule:
        """Run ACO optimization."""
        if base_time is None:
            base_time = datetime.now()

        best_schedule = None
        best_fitness = float("inf")

        for iteration in range(self.max_iterations):
            solutions = []
            for _ in range(self.num_ants):
                schedule = self._construct_solution(base_time)
                fitness = self._evaluate(schedule)
                solutions.append((schedule, fitness))
                if fitness < best_fitness:
                    best_fitness = fitness
                    best_schedule = schedule

            self.pheromone *= 1 - self.evaporation

            for schedule, fitness in solutions:
                if fitness < float("inf"):
                    deposit = self.q / fitness
                    for i, assignment in enumerate(schedule.assignments):
                        j = self.resources.index(assignment.resource)
                        self.pheromone[i, j] += deposit

        return best_schedule or Schedule()
