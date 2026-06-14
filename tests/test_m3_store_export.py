"""M3 — SQLite store + JSON export contract tests."""

from __future__ import annotations

import json
from typing import Any

from catalog.store.db import Database, SourceObservationRow, new_id
from catalog.store.export import SCHEMA_VERSION, build_export, export_to_json

# ── Helpers ───────────────────────────────────────────────────────────────────

def pf(value: Any, method: str = "authoritative-verified", confidence: float = 1.0) -> dict[str, Any]:
    return {"value": value, "provenance": {"source": "test", "method": method, "confidence": confidence}}


def make_cpu_part(part_id: str, name: str = "Test CPU") -> dict[str, Any]:
    return {
        "id": part_id,
        "category": "cpu",
        "name": name,
        "retailer_refs": {},
        "price_snapshot": None,
        "attributes": {"cores": 16},
        "socket": pf("AM5"),
        "tdp_watts": pf(170),
    }


def make_mb_part(part_id: str, has_socket_conflict: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": part_id,
        "category": "motherboard",
        "name": "Test MB",
        "retailer_refs": {},
        "price_snapshot": None,
        "attributes": {},
        "ram_type": pf("DDR5"),
        "form_factor": pf("ATX"),
        "memory_slots": pf(4),
        "m2_slots": pf(3),
        "sata_ports": pf(6),
    }
    if not has_socket_conflict:
        data["socket"] = pf("AM5")
    return data


def save_cpu(db: Database, part_id: str | None = None) -> str:
    pid = part_id or new_id()
    db.save_part(pid, "cpu", make_cpu_part(pid), has_conflict=False)
    return pid


def save_mb_conflict(db: Database) -> str:
    pid = new_id()
    db.save_part(pid, "motherboard", make_mb_part(pid, has_socket_conflict=True), has_conflict=True)
    return pid


# ── Schema creation ───────────────────────────────────────────────────────────

def test_schema_creates(db: Database) -> None:
    # Tables must exist (no error on insert)
    db.save_part("test-id", "cpu", {"id": "test-id", "category": "cpu", "name": "X"})
    part = db.get_part("test-id")
    assert part is not None


# ── Parts persistence ─────────────────────────────────────────────────────────

def test_part_round_trips(db: Database) -> None:
    pid = save_cpu(db)
    part = db.get_part(pid)
    assert part is not None
    assert part["category"] == "cpu"
    assert part["socket"]["value"] == "AM5"


def test_get_all_parts_excludes_conflicts(db: Database) -> None:
    good_pid = save_cpu(db)
    conflict_pid = save_mb_conflict(db)
    rows = db.get_all_parts(include_conflicted=False)
    ids = [r[0] for r in rows]
    assert good_pid in ids
    assert conflict_pid not in ids


def test_get_all_parts_include_conflicted(db: Database) -> None:
    good_pid = save_cpu(db)
    conflict_pid = save_mb_conflict(db)
    rows = db.get_all_parts(include_conflicted=True)
    ids = [r[0] for r in rows]
    assert good_pid in ids
    assert conflict_pid in ids


# ── Export: schema version + structure ───────────────────────────────────────

def test_export_schema_version(db: Database) -> None:
    save_cpu(db)
    artifact = build_export(db)
    assert artifact.schema_version == SCHEMA_VERSION


def test_export_has_engine_fields_and_display(db: Database) -> None:
    pid = save_cpu(db)
    artifact = build_export(db)
    assert len(artifact.parts) == 1
    part_exp = artifact.parts[0]
    assert part_exp.id == pid
    # engine_fields present
    assert "socket" in part_exp.engine_fields
    assert "tdp_watts" in part_exp.engine_fields
    # display present
    assert part_exp.display.name == "Test CPU"


def test_no_blob_leak_in_engine_fields(db: Database) -> None:
    """The attributes blob must never appear in engine_fields."""
    pid = save_cpu(db)
    artifact = build_export(db)
    part_exp = next(p for p in artifact.parts if p.id == pid)
    ef_keys = set(part_exp.engine_fields.keys())
    assert "attributes" not in ef_keys
    assert "cores" not in ef_keys  # was in attributes blob


# ── Export: withheld on catastrophic conflict ─────────────────────────────────

def test_catastrophic_conflict_withheld(db: Database) -> None:
    good_pid = save_cpu(db)
    conflict_pid = save_mb_conflict(db)
    artifact = build_export(db)
    ids = [p.id for p in artifact.parts]
    assert good_pid in ids
    assert conflict_pid not in ids, "Parts with catastrophic conflict must be withheld"


# ── Export: verify status for non-catastrophic uncertain fields ───────────────

def test_verify_status_for_low_confidence_field(db: Database) -> None:
    pid = new_id()
    data = make_cpu_part(pid)
    # Override tdp_watts with low-confidence llm-extracted field
    data["tdp_watts"] = pf(105, method="llm-extracted", confidence=0.5)
    db.save_part(pid, "cpu", data, has_conflict=False)

    artifact = build_export(db, field_trust_threshold=0.80)
    part_exp = next(p for p in artifact.parts if p.id == pid)
    assert part_exp.engine_fields["tdp_watts"].verification_status == "verify"


def test_verified_status_for_authoritative_field(db: Database) -> None:
    pid = save_cpu(db)
    artifact = build_export(db)
    part_exp = next(p for p in artifact.parts if p.id == pid)
    assert part_exp.engine_fields["socket"].verification_status == "verified"


# ── Export: deterministic ─────────────────────────────────────────────────────

def test_export_deterministic(db: Database) -> None:
    save_cpu(db)
    ts = "2026-01-01T00:00:00+00:00"
    json1 = export_to_json(db, generated_at=ts)
    json2 = export_to_json(db, generated_at=ts)
    assert json1 == json2


def test_export_byte_identical_on_rerun(db: Database) -> None:
    save_cpu(db)
    save_cpu(db, part_id=new_id())
    ts = "2026-01-01T00:00:00+00:00"
    first = export_to_json(db, generated_at=ts)
    second = export_to_json(db, generated_at=ts)
    assert first == second


# ── Export: additive versioning ───────────────────────────────────────────────

def test_additive_versioning(db: Database) -> None:
    """An unknown field on a newer record does not break the reader."""
    save_cpu(db)
    artifact = build_export(db)
    # Simulate adding a new field that the reader doesn't know about yet
    dumped = json.loads(artifact.model_dump_json())
    dumped["new_future_field"] = "ignored"
    # Re-parse without the new field — should not fail
    from catalog.store.export import CatalogExport
    restored = CatalogExport.model_validate(dumped)
    assert restored.schema_version == SCHEMA_VERSION


# ── Source observations ───────────────────────────────────────────────────────

def test_observation_round_trips(db: Database) -> None:
    row = SourceObservationRow(
        id=new_id(),
        source_name="test",
        source_content_hash="abc123",
        category="cpu",
        raw_name="Test CPU",
        engine_field_values={"socket": "AM5", "tdp_watts": 105},
        attributes={"cores": 8},
        method="authoritative-verified",
        confidence=1.0,
        timestamp="2026-01-01T00:00:00+00:00",
    )
    db.save_observation(row)
    rows = db.get_observations_by_category("cpu")
    assert len(rows) == 1
    assert rows[0].engine_field_values["socket"] == "AM5"
    assert rows[0].attributes["cores"] == 8
