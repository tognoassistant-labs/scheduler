"""Shared pytest fixtures for the scheduler test suite.

Fixtures:
- `tiny_dataset`: 30-student / 18-section dataset for fast solver tests
- `sample_dataset`: full 130-student / 62-section dataset (slower)
- `tmp_csv_dir`: pytest tmp_path with a written canonical CSV dataset
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.scheduler.io_csv import write_dataset
from src.scheduler.master_solver import solve_master
from src.scheduler.models import Dataset
from src.scheduler.sample_data import make_grade_12_dataset
from src.scheduler.student_solver import solve_students


@pytest.fixture(scope="session")
def tiny_dataset() -> Dataset:
    """Smallest reliably-feasible Grade-12 dataset for solver tests.

    Below ~120 students the sample generator produces too many 1-section
    courses, which can cluster into conflicting schemes and make the
    student solve infeasible at hard balance K=5 — especially after HC2b
    (advisory rooms must be distinct) tightened master's room domain.
    n=120 + seed=7 reliably solves in <30s while still being fast enough
    for CI. Some other (n, seed) pairs produce INFEASIBLE — solver
    behavior is seed-sensitive at small scale because of singleton
    clustering. Was n=100 seed=7 before 2026-04-26.
    """
    return make_grade_12_dataset(n_students=120, seed=7)


@pytest.fixture(scope="session")
def sample_dataset() -> Dataset:
    """Standard 130-student sample (matches the README KPI snapshot)."""
    return make_grade_12_dataset(n_students=130, seed=42)


@pytest.fixture(scope="session")
def tiny_solved(tiny_dataset: Dataset):
    """A solved tiny dataset — yields (dataset, master, students, unmet)."""
    master, _, m_status = solve_master(tiny_dataset, time_limit_s=10)
    assert master, f"Master failed: {m_status}"
    students, unmet, _, s_status = solve_students(tiny_dataset, master, time_limit_s=20, mode="single")
    assert students, f"Student solve failed: {s_status}"
    return tiny_dataset, master, students, unmet


@pytest.fixture
def tmp_csv_dir(tiny_dataset: Dataset, tmp_path: Path) -> Path:
    """Write the tiny dataset to a temp dir and return the path."""
    write_dataset(tiny_dataset, tmp_path)
    return tmp_path
