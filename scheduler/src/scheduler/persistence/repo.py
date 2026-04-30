"""Typed repositories over the SQLite schema.

Each repo encapsulates one table family. They take a DB instance, never a
raw connection — keeps lifecycle in one place.

Design notes:
- Inserts return autoincrement IDs.
- Reads return frozen dataclasses (BundleMeta etc.) for the indexed columns
  plus the deserialized pydantic model where applicable.
- Hash-based dedup is opt-in via `save_unique` — caller decides whether
  identical content should reuse an existing row or create a new revision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from ..models import (
    Dataset,
    HardConstraints,
    MasterAssignment,
    SoftConstraintWeights,
    StudentAssignment,
)
from .db import DB
from .serialize import (
    dataset_from_blob,
    dataset_to_blob,
    hard_from_blob,
    hard_to_blob,
    hash_payload,
    master_to_blob,
    soft_from_blob,
    soft_to_blob,
    students_to_blob,
    unmet_to_blob,
)

VALID_SOURCE_KINDS = {"csv", "xlsx", "sample", "synthetic", "imported"}
VALID_RUN_STATUS = {"running", "completed", "failed", "infeasible"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Input bundles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BundleMeta:
    id: int
    label: str
    source_kind: str
    created_at: str
    hash: str


@dataclass(frozen=True)
class StoredFile:
    role: str
    filename: str
    content: bytes
    sha256: str


class InputBundleRepo:
    """Persists Dataset + optional raw-file attachments for re-export/audit."""

    def __init__(self, db: DB) -> None:
        self.db = db

    def save(
        self,
        label: str,
        source_kind: str,
        dataset: Dataset,
        raw_files: Iterable[StoredFile] | None = None,
    ) -> int:
        if source_kind not in VALID_SOURCE_KINDS:
            raise ValueError(f"source_kind={source_kind!r} not in {VALID_SOURCE_KINDS}")
        blob = dataset_to_blob(dataset)
        h = hash_payload(blob)
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO input_bundle(label, source_kind, created_at, dataset_json, hash) "
                "VALUES (?, ?, ?, ?, ?)",
                (label, source_kind, _now(), blob, h),
            )
            bundle_id = int(cur.lastrowid)
            for f in raw_files or ():
                conn.execute(
                    "INSERT INTO input_file(bundle_id, role, filename, content, sha256) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (bundle_id, f.role, f.filename, f.content, f.sha256),
                )
        return bundle_id

    def find_by_hash(self, h: str) -> BundleMeta | None:
        cur = self.db.conn.execute(
            "SELECT id, label, source_kind, created_at, hash FROM input_bundle WHERE hash = ? "
            "ORDER BY id ASC LIMIT 1",
            (h,),
        )
        row = cur.fetchone()
        return BundleMeta(**dict(row)) if row else None

    def get(self, bundle_id: int) -> tuple[BundleMeta, Dataset]:
        cur = self.db.conn.execute(
            "SELECT id, label, source_kind, created_at, dataset_json, hash "
            "FROM input_bundle WHERE id = ?",
            (bundle_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"input_bundle id={bundle_id} not found")
        meta = BundleMeta(
            id=row["id"],
            label=row["label"],
            source_kind=row["source_kind"],
            created_at=row["created_at"],
            hash=row["hash"],
        )
        ds = dataset_from_blob(row["dataset_json"])
        return meta, ds

    def list_all(self, limit: int = 100) -> list[BundleMeta]:
        cur = self.db.conn.execute(
            "SELECT id, label, source_kind, created_at, hash FROM input_bundle "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [BundleMeta(**dict(r)) for r in cur.fetchall()]

    def get_files(self, bundle_id: int) -> list[StoredFile]:
        cur = self.db.conn.execute(
            "SELECT role, filename, content, sha256 FROM input_file WHERE bundle_id = ? "
            "ORDER BY id ASC",
            (bundle_id,),
        )
        return [StoredFile(**dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Rule configurations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleConfigMeta:
    id: int
    label: str
    created_at: str
    hash: str


class RuleConfigRepo:
    def __init__(self, db: DB) -> None:
        self.db = db

    def save(
        self,
        label: str,
        hard: HardConstraints,
        soft: SoftConstraintWeights,
        registry_overrides: bytes | None = None,
    ) -> int:
        hard_blob = hard_to_blob(hard)
        soft_blob = soft_to_blob(soft)
        # Hash spans both blobs + overrides → identical config detection.
        combined = hard_blob + b"\x00" + soft_blob + b"\x00" + (registry_overrides or b"")
        h = hash_payload(combined)
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO rule_config(label, created_at, hard_json, soft_json, "
                "registry_overrides_json, hash) VALUES (?, ?, ?, ?, ?, ?)",
                (label, _now(), hard_blob, soft_blob, registry_overrides, h),
            )
            return int(cur.lastrowid)

    def find_by_hash(self, h: str) -> RuleConfigMeta | None:
        cur = self.db.conn.execute(
            "SELECT id, label, created_at, hash FROM rule_config WHERE hash = ? "
            "ORDER BY id ASC LIMIT 1",
            (h,),
        )
        row = cur.fetchone()
        return RuleConfigMeta(**dict(row)) if row else None

    def get(
        self, config_id: int
    ) -> tuple[RuleConfigMeta, HardConstraints, SoftConstraintWeights, bytes | None]:
        cur = self.db.conn.execute(
            "SELECT id, label, created_at, hard_json, soft_json, registry_overrides_json, hash "
            "FROM rule_config WHERE id = ?",
            (config_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"rule_config id={config_id} not found")
        meta = RuleConfigMeta(
            id=row["id"], label=row["label"], created_at=row["created_at"], hash=row["hash"]
        )
        return (
            meta,
            hard_from_blob(row["hard_json"]),
            soft_from_blob(row["soft_json"]),
            row["registry_overrides_json"],
        )

    def list_all(self, limit: int = 100) -> list[RuleConfigMeta]:
        cur = self.db.conn.execute(
            "SELECT id, label, created_at, hash FROM rule_config "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [RuleConfigMeta(**dict(r)) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunMeta:
    id: int
    label: str
    created_at: str
    bundle_id: int
    rule_config_id: int
    status: str
    master_seconds: float | None
    student_seconds: float | None
    objective: float | None
    git_sha: str | None
    app_version: str | None
    error_message: str | None


class RunRepo:
    """Run lifecycle: start → save_result → save_kpi/compliance → mark_complete."""

    def __init__(self, db: DB) -> None:
        self.db = db

    def start(
        self,
        label: str,
        bundle_id: int,
        rule_config_id: int,
        *,
        git_sha: str | None = None,
        app_version: str | None = None,
    ) -> int:
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO run(label, created_at, bundle_id, rule_config_id, status, "
                "git_sha, app_version) VALUES (?, ?, ?, ?, 'running', ?, ?)",
                (label, _now(), bundle_id, rule_config_id, git_sha, app_version),
            )
            return int(cur.lastrowid)

    def mark_complete(
        self,
        run_id: int,
        *,
        master_seconds: float,
        student_seconds: float,
        objective: float,
        status: str = "completed",
    ) -> None:
        if status not in VALID_RUN_STATUS:
            raise ValueError(f"status={status!r} not in {VALID_RUN_STATUS}")
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE run SET status = ?, master_seconds = ?, student_seconds = ?, "
                "objective = ? WHERE id = ?",
                (status, master_seconds, student_seconds, objective, run_id),
            )

    def mark_failed(self, run_id: int, error: str, status: str = "failed") -> None:
        if status not in VALID_RUN_STATUS:
            raise ValueError(f"status={status!r} not in {VALID_RUN_STATUS}")
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE run SET status = ?, error_message = ? WHERE id = ?",
                (status, error, run_id),
            )

    def save_result(
        self,
        run_id: int,
        master: list[MasterAssignment],
        students: list[StudentAssignment],
        unmet: list[tuple[str, str]],
    ) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO run_result(run_id, master_json, students_json, unmet_json) "
                "VALUES (?, ?, ?, ?)",
                (run_id, master_to_blob(master), students_to_blob(students), unmet_to_blob(unmet)),
            )

    def save_kpis(self, run_id: int, rows: Iterable[tuple[str, str, str, float]]) -> None:
        """rows = iterable of (metric, scope, key, value)."""
        with self.db.transaction() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO run_kpi(run_id, metric, scope, key, value) "
                "VALUES (?, ?, ?, ?, ?)",
                [(run_id, m, s, k, v) for (m, s, k, v) in rows],
            )

    def save_compliance(
        self,
        run_id: int,
        rows: Iterable[tuple[str, int, int, float, bytes | None]],
    ) -> None:
        """rows = iterable of (rule_id, satisfied, violated, pct, sample_violations_json)."""
        with self.db.transaction() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO rule_compliance(run_id, rule_id, satisfied, violated, "
                "pct, sample_violations_json) VALUES (?, ?, ?, ?, ?, ?)",
                [(run_id, rid, sat, vio, pct, sv) for (rid, sat, vio, pct, sv) in rows],
            )

    def get(self, run_id: int) -> RunMeta:
        cur = self.db.conn.execute(
            "SELECT id, label, created_at, bundle_id, rule_config_id, status, "
            "master_seconds, student_seconds, objective, git_sha, app_version, error_message "
            "FROM run WHERE id = ?",
            (run_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"run id={run_id} not found")
        return RunMeta(**dict(row))

    def list_all(self, limit: int = 100) -> list[RunMeta]:
        cur = self.db.conn.execute(
            "SELECT id, label, created_at, bundle_id, rule_config_id, status, "
            "master_seconds, student_seconds, objective, git_sha, app_version, error_message "
            "FROM run ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [RunMeta(**dict(r)) for r in cur.fetchall()]

    def get_kpis(self, run_id: int) -> list[tuple[str, str, str, float]]:
        cur = self.db.conn.execute(
            "SELECT metric, scope, key, value FROM run_kpi WHERE run_id = ? "
            "ORDER BY metric, scope, key",
            (run_id,),
        )
        return [(r["metric"], r["scope"], r["key"], r["value"]) for r in cur.fetchall()]

    def get_compliance(
        self, run_id: int
    ) -> list[tuple[str, int, int, float, bytes | None]]:
        cur = self.db.conn.execute(
            "SELECT rule_id, satisfied, violated, pct, sample_violations_json "
            "FROM rule_compliance WHERE run_id = ? ORDER BY rule_id",
            (run_id,),
        )
        return [
            (r["rule_id"], r["satisfied"], r["violated"], r["pct"], r["sample_violations_json"])
            for r in cur.fetchall()
        ]

    def get_result_blobs(self, run_id: int) -> tuple[bytes, bytes, bytes]:
        cur = self.db.conn.execute(
            "SELECT master_json, students_json, unmet_json FROM run_result WHERE run_id = ?",
            (run_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"run_result for run_id={run_id} not found")
        return row["master_json"], row["students_json"], row["unmet_json"]
