"""Core scheduling models."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class Task:
    """A task to be scheduled."""

    id: str
    name: str
    duration: timedelta
    priority: int = 1
    earliest_start: Optional[datetime] = None
    deadline: Optional[datetime] = None
    dependencies: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass
class Resource:
    """A resource that can execute tasks."""

    id: str
    name: str
    capacity: int = 1
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass
class Assignment:
    """Assignment of a task to a resource at a specific time."""

    task: Task
    resource: Resource
    start_time: datetime

    @property
    def end_time(self) -> datetime:
        return self.start_time + self.task.duration


@dataclass
class Schedule:
    """A complete schedule of task assignments."""

    assignments: list[Assignment] = field(default_factory=list)

    def add(self, assignment: Assignment) -> None:
        self.assignments.append(assignment)

    def makespan(self) -> timedelta:
        """Total time from first start to last finish."""
        if not self.assignments:
            return timedelta(0)
        start = min(a.start_time for a in self.assignments)
        end = max(a.end_time for a in self.assignments)
        return end - start

    def total_tardiness(self) -> timedelta:
        """Sum of deadline violations."""
        total = timedelta(0)
        for a in self.assignments:
            if a.task.deadline and a.end_time > a.task.deadline:
                total += a.end_time - a.task.deadline
        return total

    def is_valid(self) -> bool:
        """Check if schedule respects all constraints."""
        for a in self.assignments:
            if a.task.earliest_start and a.start_time < a.task.earliest_start:
                return False
        return True
