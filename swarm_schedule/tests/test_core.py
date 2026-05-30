"""Tests for core scheduling models."""

from datetime import datetime, timedelta

from swarm_schedule.core import Task, Resource, Assignment, Schedule


def test_task_creation():
    task = Task(id="t1", name="Test Task", duration=timedelta(hours=1))
    assert task.id == "t1"
    assert task.duration == timedelta(hours=1)


def test_resource_creation():
    resource = Resource(id="r1", name="Worker")
    assert resource.id == "r1"
    assert resource.capacity == 1


def test_assignment_end_time():
    task = Task(id="t1", name="Task", duration=timedelta(hours=2))
    resource = Resource(id="r1", name="Worker")
    start = datetime(2026, 1, 1, 9, 0)
    assignment = Assignment(task=task, resource=resource, start_time=start)
    assert assignment.end_time == datetime(2026, 1, 1, 11, 0)


def test_schedule_makespan():
    task1 = Task(id="t1", name="Task1", duration=timedelta(hours=1))
    task2 = Task(id="t2", name="Task2", duration=timedelta(hours=2))
    resource = Resource(id="r1", name="Worker")

    schedule = Schedule()
    schedule.add(Assignment(task=task1, resource=resource, start_time=datetime(2026, 1, 1, 9, 0)))
    schedule.add(Assignment(task=task2, resource=resource, start_time=datetime(2026, 1, 1, 10, 0)))

    assert schedule.makespan() == timedelta(hours=3)


def test_schedule_tardiness():
    task = Task(
        id="t1",
        name="Task",
        duration=timedelta(hours=2),
        deadline=datetime(2026, 1, 1, 10, 0),
    )
    resource = Resource(id="r1", name="Worker")
    schedule = Schedule()
    schedule.add(Assignment(task=task, resource=resource, start_time=datetime(2026, 1, 1, 9, 0)))

    assert schedule.total_tardiness() == timedelta(hours=1)


def test_schedule_validity():
    task = Task(
        id="t1",
        name="Task",
        duration=timedelta(hours=1),
        earliest_start=datetime(2026, 1, 1, 10, 0),
    )
    resource = Resource(id="r1", name="Worker")

    valid_schedule = Schedule()
    valid_schedule.add(Assignment(task=task, resource=resource, start_time=datetime(2026, 1, 1, 10, 0)))
    assert valid_schedule.is_valid()

    invalid_schedule = Schedule()
    invalid_schedule.add(Assignment(task=task, resource=resource, start_time=datetime(2026, 1, 1, 9, 0)))
    assert not invalid_schedule.is_valid()
