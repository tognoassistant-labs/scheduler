"""Persistence layer for the Columbus scheduling engine (v4.27+).

Local SQLite. One file per deployment. Stores input bundles, rule
configurations, runs, results, and compliance metrics so every solve is
versioned and any historical run can be browsed, compared, and re-exported.

Public surface:
    DB                       — connection + schema manager
    open_db(path=None)       — convenience factory (uses $COLUMBUS_DB or default)
    InputBundleRepo
    RuleConfigRepo
    RunRepo
"""
from .db import DB, open_db
from .repo import (
    BundleMeta,
    InputBundleRepo,
    RuleConfigMeta,
    RuleConfigRepo,
    RunMeta,
    RunRepo,
)

__all__ = [
    "DB",
    "open_db",
    "BundleMeta",
    "RuleConfigMeta",
    "RunMeta",
    "InputBundleRepo",
    "RuleConfigRepo",
    "RunRepo",
]
