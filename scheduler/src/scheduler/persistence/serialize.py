"""Pydantic ↔ JSON helpers and content hashing.

Goal: round-trip Dataset, HardConstraints, SoftConstraintWeights,
ScheduleResult through SQLite BLOB columns without touching `models.py`.

Hashing is content-addressable: identical canonical JSON → identical hash.
Used to detect bundle/config reuse.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from ..models import (
    Dataset,
    HardConstraints,
    MasterAssignment,
    ScheduleResult,
    SoftConstraintWeights,
    StudentAssignment,
)


def _to_canonical_json(payload: dict[str, Any]) -> bytes:
    """Sort keys + compact separators → deterministic bytes for hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def hash_payload(payload: bytes | dict[str, Any]) -> str:
    if isinstance(payload, dict):
        payload = _to_canonical_json(payload)
    return hashlib.sha256(payload).hexdigest()


def model_to_blob(m: BaseModel) -> bytes:
    """Serialize a pydantic model to canonical (sorted-key) JSON bytes."""
    return _to_canonical_json(m.model_dump(mode="json"))


def model_from_blob(cls: type[BaseModel], blob: bytes | str) -> Any:
    if isinstance(blob, bytes):
        blob = blob.decode("utf-8")
    return cls.model_validate_json(blob)


# Convenience wrappers — explicit per-type entry points are nicer at call sites
# than a single generic helper when the type is fixed.

def dataset_to_blob(ds: Dataset) -> bytes:
    return model_to_blob(ds)


def dataset_from_blob(blob: bytes | str) -> Dataset:
    return model_from_blob(Dataset, blob)


def hard_to_blob(hc: HardConstraints) -> bytes:
    return model_to_blob(hc)


def hard_from_blob(blob: bytes | str) -> HardConstraints:
    return model_from_blob(HardConstraints, blob)


def soft_to_blob(sc: SoftConstraintWeights) -> bytes:
    return model_to_blob(sc)


def soft_from_blob(blob: bytes | str) -> SoftConstraintWeights:
    return model_from_blob(SoftConstraintWeights, blob)


# ScheduleResult is split across run_result columns to keep individual blobs
# small and let future tooling stream students_json without loading master.

def master_to_blob(master: list[MasterAssignment]) -> bytes:
    return _to_canonical_json([m.model_dump(mode="json") for m in master])


def master_from_blob(blob: bytes | str) -> list[MasterAssignment]:
    if isinstance(blob, bytes):
        blob = blob.decode("utf-8")
    return [MasterAssignment.model_validate(item) for item in json.loads(blob)]


def students_to_blob(students: list[StudentAssignment]) -> bytes:
    return _to_canonical_json([s.model_dump(mode="json") for s in students])


def students_from_blob(blob: bytes | str) -> list[StudentAssignment]:
    if isinstance(blob, bytes):
        blob = blob.decode("utf-8")
    return [StudentAssignment.model_validate(item) for item in json.loads(blob)]


def unmet_to_blob(unmet: list[tuple[str, str]]) -> bytes:
    return _to_canonical_json([list(t) for t in unmet])


def unmet_from_blob(blob: bytes | str) -> list[tuple[str, str]]:
    if isinstance(blob, bytes):
        blob = blob.decode("utf-8")
    return [tuple(item) for item in json.loads(blob)]


def schedule_result_to_blobs(result: ScheduleResult) -> tuple[bytes, bytes, bytes]:
    return (
        master_to_blob(result.master),
        students_to_blob(result.students),
        unmet_to_blob(result.unscheduled_requests),
    )


def schedule_result_from_blobs(
    master_blob: bytes | str,
    students_blob: bytes | str,
    unmet_blob: bytes | str,
    *,
    objective_value: float = 0.0,
    solve_seconds: float = 0.0,
) -> ScheduleResult:
    return ScheduleResult(
        master=master_from_blob(master_blob),
        students=students_from_blob(students_blob),
        unscheduled_requests=unmet_from_blob(unmet_blob),
        unscheduled_students=[],
        objective_value=objective_value,
        solve_seconds=solve_seconds,
    )
