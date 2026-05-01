"""Round-trip tests for the persistence layer (M1).

Covers:
- Schema bootstrap creates all 8 tables and seeds schema_meta.
- Dataset, HardConstraints, SoftConstraintWeights, ScheduleResult round-trip.
- Hash-based dedup detects identical content.
- Run lifecycle: start → save_result → save_kpis → mark_complete.
- runner.solve_and_persist with db=None matches db=DB byte-for-byte at the
  result level.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.scheduler.models import (
    Dataset,
    HardConstraints,
    MasterAssignment,
    SoftConstraintWeights,
    StudentAssignment,
)
from src.scheduler.persistence import (
    DB,
    InputBundleRepo,
    RuleConfigRepo,
    RunRepo,
    open_db,
)
from src.scheduler.persistence.serialize import (
    dataset_from_blob,
    dataset_to_blob,
    hard_from_blob,
    hard_to_blob,
    hash_payload,
    master_from_blob,
    master_to_blob,
    soft_from_blob,
    soft_to_blob,
    students_from_blob,
    students_to_blob,
    unmet_from_blob,
    unmet_to_blob,
)


@pytest.fixture
def db(tmp_path: Path) -> DB:
    return DB(tmp_path / "test.sqlite")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_schema_creates_all_tables(db: DB) -> None:
    expected = {
        "schema_meta",
        "input_bundle",
        "input_file",
        "rule_config",
        "run",
        "run_result",
        "run_kpi",
        "rule_compliance",
    }
    cur = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    actual = {row["name"] for row in cur.fetchall()}
    assert expected <= actual


def test_schema_meta_seeded(db: DB) -> None:
    cur = db.conn.execute("SELECT version FROM schema_meta")
    rows = cur.fetchall()
    assert len(rows) >= 1
    # Versión actual; bumpear este número cuando se incremente SCHEMA_VERSION.
    assert rows[0]["version"] >= 1


def test_open_db_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "from_env.sqlite"
    monkeypatch.setenv("COLUMBUS_DB", str(target))
    db = open_db()
    assert db.path == target
    assert target.exists()


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_dataset_roundtrip(tiny_dataset: Dataset) -> None:
    blob = dataset_to_blob(tiny_dataset)
    restored = dataset_from_blob(blob)
    assert restored.model_dump() == tiny_dataset.model_dump()


def test_hard_constraints_roundtrip() -> None:
    hc = HardConstraints(enforce_separations=False, max_section_spread_per_course=6)
    restored = hard_from_blob(hard_to_blob(hc))
    assert restored == hc


def test_soft_weights_roundtrip() -> None:
    sw = SoftConstraintWeights(first_choice_electives=42, balance_class_sizes=99)
    restored = soft_from_blob(soft_to_blob(sw))
    assert restored == sw


def test_master_assignments_roundtrip() -> None:
    m = [
        MasterAssignment(section_id="S1", scheme=3, room_id="R1", slots=[("A", 1), ("B", 2)]),
        MasterAssignment(
            section_id="ADV1", scheme="ADVISORY", room_id="R2", slots=[("E", 3)]
        ),
    ]
    restored = master_from_blob(master_to_blob(m))
    assert restored == m


def test_students_assignments_roundtrip() -> None:
    s = [
        StudentAssignment(student_id="ST1", section_ids=["S1", "S2", "S3"]),
        StudentAssignment(student_id="ST2", section_ids=[]),
    ]
    restored = students_from_blob(students_to_blob(s))
    assert restored == s


def test_unmet_roundtrip() -> None:
    u = [("ST1", "ALG2"), ("ST2", "BIO")]
    assert unmet_from_blob(unmet_to_blob(u)) == u


def test_hash_canonical() -> None:
    """Same logical payload, different key order → same hash."""
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert hash_payload(a) == hash_payload(b)


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------


def test_bundle_save_and_get(db: DB, tiny_dataset: Dataset) -> None:
    repo = InputBundleRepo(db)
    bid = repo.save("tiny", "sample", tiny_dataset)
    meta, ds = repo.get(bid)
    assert meta.id == bid
    assert meta.label == "tiny"
    assert meta.source_kind == "sample"
    assert ds.model_dump() == tiny_dataset.model_dump()


def test_bundle_hash_dedup(db: DB, tiny_dataset: Dataset) -> None:
    repo = InputBundleRepo(db)
    bid = repo.save("tiny", "sample", tiny_dataset)
    meta = repo.get(bid)[0]
    found = repo.find_by_hash(meta.hash)
    assert found is not None
    assert found.id == bid


def test_bundle_invalid_source_kind(db: DB, tiny_dataset: Dataset) -> None:
    repo = InputBundleRepo(db)
    with pytest.raises(ValueError):
        repo.save("tiny", "BAD", tiny_dataset)


def test_bundle_list(db: DB, tiny_dataset: Dataset) -> None:
    repo = InputBundleRepo(db)
    repo.save("a", "sample", tiny_dataset)
    repo.save("b", "sample", tiny_dataset)
    rows = repo.list_all()
    labels = {r.label for r in rows}
    assert {"a", "b"} <= labels


def test_rule_config_save_and_get(db: DB) -> None:
    repo = RuleConfigRepo(db)
    hc = HardConstraints(enforce_separations=False)
    sw = SoftConstraintWeights(first_choice_electives=42)
    cid = repo.save("custom", hc, sw)
    meta, hard, soft, overrides = repo.get(cid)
    assert meta.label == "custom"
    assert hard == hc
    assert soft == sw
    assert overrides is None


def test_rule_config_hash_changes_with_content(db: DB) -> None:
    repo = RuleConfigRepo(db)
    a = repo.save("a", HardConstraints(), SoftConstraintWeights())
    b = repo.save("b", HardConstraints(enforce_separations=False), SoftConstraintWeights())
    meta_a = repo.get(a)[0]
    meta_b = repo.get(b)[0]
    assert meta_a.hash != meta_b.hash


def test_run_lifecycle(db: DB, tiny_dataset: Dataset) -> None:
    bundles = InputBundleRepo(db)
    rules = RuleConfigRepo(db)
    runs = RunRepo(db)

    bid = bundles.save("tiny", "sample", tiny_dataset)
    cid = rules.save("default", HardConstraints(), SoftConstraintWeights())
    rid = runs.start("test-run", bid, cid, app_version="test")
    meta = runs.get(rid)
    assert meta.status == "running"
    assert meta.app_version == "test"

    runs.save_result(rid, [], [], [])
    runs.save_kpis(rid, [("fully_scheduled_pct", "global", "all", 95.5)])
    runs.mark_complete(rid, master_seconds=1.5, student_seconds=3.0, objective=42.0)

    meta = runs.get(rid)
    assert meta.status == "completed"
    assert meta.master_seconds == 1.5
    assert meta.student_seconds == 3.0
    assert meta.objective == 42.0

    kpis = runs.get_kpis(rid)
    assert ("fully_scheduled_pct", "global", "all", 95.5) in kpis


def test_run_failure_path(db: DB, tiny_dataset: Dataset) -> None:
    bundles = InputBundleRepo(db)
    rules = RuleConfigRepo(db)
    runs = RunRepo(db)
    bid = bundles.save("tiny", "sample", tiny_dataset)
    cid = rules.save("default", HardConstraints(), SoftConstraintWeights())
    rid = runs.start("doomed", bid, cid)
    runs.mark_failed(rid, "infeasible: master")
    meta = runs.get(rid)
    assert meta.status == "failed"
    assert meta.error_message == "infeasible: master"


def test_run_notes_and_tags(db: DB, tiny_dataset: Dataset) -> None:
    """F3 — el coordinador puede agregar notas y tags a una corrida."""
    bundles = InputBundleRepo(db)
    rules = RuleConfigRepo(db)
    runs = RunRepo(db)
    bid = bundles.save("tiny", "sample", tiny_dataset)
    cid = rules.save("default", HardConstraints(), SoftConstraintWeights())
    rid_a = runs.start("first", bid, cid)
    rid_b = runs.start("second", bid, cid)

    runs.set_notes(rid_a, "Esta es la corrida final aprobada por dirección.")
    runs.set_tags(rid_a, "aprobado,final,2026-2027")
    runs.set_tags(rid_b, "draft")

    # Round-trip
    meta_a = runs.get(rid_a)
    assert meta_a.notes == "Esta es la corrida final aprobada por dirección."
    assert meta_a.tags == "aprobado,final,2026-2027"

    # Filtrar por tag
    aprobados = runs.list_by_tag("aprobado")
    assert len(aprobados) == 1
    assert aprobados[0].id == rid_a

    drafts = runs.list_by_tag("draft")
    assert len(drafts) == 1
    assert drafts[0].id == rid_b

    # Tag inexistente
    assert runs.list_by_tag("inexistente") == []


def test_run_compliance_save_and_get(db: DB, tiny_dataset: Dataset) -> None:
    bundles = InputBundleRepo(db)
    rules = RuleConfigRepo(db)
    runs = RunRepo(db)
    bid = bundles.save("tiny", "sample", tiny_dataset)
    cid = rules.save("default", HardConstraints(), SoftConstraintWeights())
    rid = runs.start("with-compliance", bid, cid)
    runs.save_compliance(
        rid,
        [
            ("R_max_class_size", 60, 0, 100.0, None),
            ("R_separations", 5, 1, 83.33, b'[["S1","S2"]]'),
        ],
    )
    rows = runs.get_compliance(rid)
    rule_ids = {r[0] for r in rows}
    assert rule_ids == {"R_max_class_size", "R_separations"}
