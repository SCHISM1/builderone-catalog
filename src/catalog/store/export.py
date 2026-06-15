"""Versioned JSON export — produces the artifact consumed by the Run 5 engine."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from catalog.store.db import Database

SCHEMA_VERSION = "1.0"


class EngineFieldExport(BaseModel):
    value: Any
    source: str
    method: str
    confidence: float
    verification_status: str  # "verified" | "extracted" | "verify"


class DisplayExport(BaseModel):
    name: str
    attributes: dict[str, Any]
    retailer_refs: dict[str, str]
    price_snapshot: float | None = None


class PartExport(BaseModel):
    id: str
    category: str
    engine_fields: dict[str, EngineFieldExport]
    display: DisplayExport


class CatalogExport(BaseModel):
    schema_version: str = SCHEMA_VERSION
    generated_at: str
    parts: list[PartExport]


def _engine_field_names_for_category(category: str) -> frozenset[str]:
    """Return the set of engine-field names for a given category."""
    _MAP: dict[str, frozenset[str]] = {
        "cpu": frozenset({"socket", "tdp_watts"}),
        "motherboard": frozenset({"socket", "ram_type", "form_factor", "memory_slots",
                                  "memory_max_gb", "m2_slots", "sata_ports"}),
        "ram": frozenset({"ddr_generation", "speed_mhz", "module_count", "capacity_gb"}),
        "psu": frozenset({"wattage"}),
        "gpu": frozenset({"tdp_watts", "length_mm"}),
        "case": frozenset({"form_factors_supported", "max_gpu_length_mm", "max_cooler_height_mm"}),
        "storage": frozenset({"interface", "form_factor"}),
        "cooler": frozenset({"height_mm"}),
    }
    return _MAP.get(category, frozenset())


def _prov_to_status(method: str, confidence: float, field_name: str, trust_threshold: float) -> str:
    """Map provenance method + confidence to a VerificationStatus."""
    if method == "authoritative-verified":
        return "verified"
    if method == "corroborated":
        return "verified"
    # llm-extracted: flag uncertain fields
    if confidence < trust_threshold:
        return "verify"
    return "extracted"


def build_export(
    db: Database,
    field_trust_threshold: float = 0.80,
    generated_at: str | None = None,
) -> CatalogExport:
    """Read canonical parts from DB → emit versioned JSON artifact.

    Rules:
    - Parts with an unresolved catastrophic conflict are withheld.
    - Non-catastrophic uncertain fields export with ``verify`` status.
    - Output is deterministically ordered (by part id, then by field name).
    """
    rows = db.get_all_parts(include_conflicted=False)

    part_exports: list[PartExport] = []
    for part_id, data, _has_conflict in sorted(rows, key=lambda r: r[0]):
        category = data.get("category", "")
        engine_field_keys = _engine_field_names_for_category(category)

        engine_fields: dict[str, EngineFieldExport] = {}
        for field_name in sorted(engine_field_keys):
            field_data = data.get(field_name)
            if field_data is None:
                continue
            # field_data is a dict with {"value": ..., "provenance": {...}}
            value = field_data.get("value")
            prov = field_data.get("provenance", {})
            source = prov.get("source", "unknown")
            method = prov.get("method", "llm-extracted")
            confidence = prov.get("confidence", 0.0)
            status = _prov_to_status(method, confidence, field_name, field_trust_threshold)
            engine_fields[field_name] = EngineFieldExport(
                value=value,
                source=source,
                method=method,
                confidence=confidence,
                verification_status=status,
            )

        # Build display section — never leaks engine-field provenance
        display = DisplayExport(
            name=data.get("name", ""),
            attributes=data.get("attributes", {}),
            retailer_refs=data.get("retailer_refs", {}),
            price_snapshot=data.get("price_snapshot"),
        )

        part_exports.append(
            PartExport(id=part_id, category=category, engine_fields=engine_fields, display=display)
        )

    return CatalogExport(
        schema_version=SCHEMA_VERSION,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        parts=part_exports,
    )


def export_to_json(
    db: Database,
    field_trust_threshold: float = 0.80,
    generated_at: str | None = None,
) -> str:
    """Return a deterministic JSON string of the export artifact.

    Pass *generated_at* to pin the timestamp for byte-identical comparison.
    In production, the timestamp updates; in tests, pass a fixed value.
    """
    artifact = build_export(db, field_trust_threshold, generated_at=generated_at)
    return json.dumps(
        json.loads(artifact.model_dump_json()),
        sort_keys=True,
        indent=2,
    )
