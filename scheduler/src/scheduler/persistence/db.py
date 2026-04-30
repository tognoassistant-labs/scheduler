"""SQLite connection + schema bootstrap for the scheduler persistence layer.

Schema is forward-compatible: all tables created at version 1 even though
M1 only populates a subset (input_bundle, input_file, rule_config, run,
run_result). M4 adds run_kpi + rule_compliance population.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path("data/columbus.sqlite")
SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS input_bundle (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    label        TEXT NOT NULL,
    source_kind  TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    dataset_json BLOB NOT NULL,
    hash         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_input_bundle_hash ON input_bundle(hash);
CREATE INDEX IF NOT EXISTS ix_input_bundle_created ON input_bundle(created_at DESC);

CREATE TABLE IF NOT EXISTS input_file (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    bundle_id INTEGER NOT NULL REFERENCES input_bundle(id) ON DELETE CASCADE,
    role      TEXT NOT NULL,
    filename  TEXT NOT NULL,
    content   BLOB NOT NULL,
    sha256    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_input_file_bundle ON input_file(bundle_id);

CREATE TABLE IF NOT EXISTS rule_config (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    label                    TEXT NOT NULL,
    created_at               TEXT NOT NULL,
    hard_json                BLOB NOT NULL,
    soft_json                BLOB NOT NULL,
    registry_overrides_json  BLOB,
    hash                     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_rule_config_hash ON rule_config(hash);
CREATE INDEX IF NOT EXISTS ix_rule_config_created ON rule_config(created_at DESC);

CREATE TABLE IF NOT EXISTS run (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    label           TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    bundle_id       INTEGER NOT NULL REFERENCES input_bundle(id) ON DELETE RESTRICT,
    rule_config_id  INTEGER NOT NULL REFERENCES rule_config(id) ON DELETE RESTRICT,
    status          TEXT NOT NULL,
    master_seconds  REAL,
    student_seconds REAL,
    objective       REAL,
    git_sha         TEXT,
    app_version     TEXT,
    error_message   TEXT
);
CREATE INDEX IF NOT EXISTS ix_run_bundle ON run(bundle_id);
CREATE INDEX IF NOT EXISTS ix_run_rule_config ON run(rule_config_id);
CREATE INDEX IF NOT EXISTS ix_run_created ON run(created_at DESC);

CREATE TABLE IF NOT EXISTS run_result (
    run_id        INTEGER PRIMARY KEY REFERENCES run(id) ON DELETE CASCADE,
    master_json   BLOB NOT NULL,
    students_json BLOB NOT NULL,
    unmet_json    BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS run_kpi (
    run_id  INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    metric  TEXT NOT NULL,
    scope   TEXT NOT NULL,
    key     TEXT NOT NULL,
    value   REAL NOT NULL,
    PRIMARY KEY (run_id, metric, scope, key)
);
CREATE INDEX IF NOT EXISTS ix_run_kpi_metric ON run_kpi(metric, scope);

CREATE TABLE IF NOT EXISTS rule_compliance (
    run_id                  INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    rule_id                 TEXT NOT NULL,
    satisfied               INTEGER NOT NULL,
    violated                INTEGER NOT NULL,
    pct                     REAL NOT NULL,
    sample_violations_json  BLOB,
    PRIMARY KEY (run_id, rule_id)
);
"""


def resolve_db_path(path: str | os.PathLike | None = None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get("COLUMBUS_DB")
    if env:
        return Path(env)
    return DEFAULT_DB_PATH


class DB:
    """Thin SQLite wrapper with schema bootstrap and transaction helper.

    Per-thread connection (sqlite3 connections are not thread-safe by default).
    Foreign keys enabled. WAL mode for concurrent readers.
    """

    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._bootstrap()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = self._connect()
        return self._local.conn

    def close(self) -> None:
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn

    def _bootstrap(self) -> None:
        with self._connect() as boot:
            boot.executescript(_SCHEMA_SQL)
            cur = boot.execute("SELECT MAX(version) FROM schema_meta")
            row = cur.fetchone()
            current = row[0] if row else None
            if current is None or current < SCHEMA_VERSION:
                from datetime import datetime, timezone
                boot.execute(
                    "INSERT INTO schema_meta(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
                )
            boot.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def open_db(path: str | os.PathLike | None = None) -> DB:
    return DB(resolve_db_path(path))
