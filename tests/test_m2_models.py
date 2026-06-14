"""M2 — Catalog data model tests."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from catalog.models import (
    CATASTROPHIC_ENGINE_FIELDS,
    CasePart,
    CoolerPart,
    CPUPart,
    GPUPart,
    MotherboardPart,
    Provenance,
    ProvenanceField,
    PSUPart,
    RAMPart,
    StoragePart,
    parse_catalog_part,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_pf(value: Any, source: str = "test", method: str = "authoritative-verified", confidence: float = 1.0) -> dict[str, Any]:
    return {"value": value, "provenance": {"source": source, "method": method, "confidence": confidence}}


def make_cpu(**kwargs: Any) -> dict[str, Any]:
    base = {
        "category": "cpu",
        "name": "Test CPU",
        "socket": make_pf("AM5"),
        "tdp_watts": make_pf(105),
    }
    base.update(kwargs)
    return base


def make_motherboard(**kwargs: Any) -> dict[str, Any]:
    base = {
        "category": "motherboard",
        "name": "Test MB",
        "socket": make_pf("AM5"),
        "ram_type": make_pf("DDR5"),
        "form_factor": make_pf("ATX"),
        "memory_slots": make_pf(4),
        "m2_slots": make_pf(3),
        "sata_ports": make_pf(6),
    }
    base.update(kwargs)
    return base


# ── ProvenanceField tests ─────────────────────────────────────────────────────

def test_provenance_field_requires_provenance() -> None:
    """A bare value without provenance must fail validation."""
    with pytest.raises((ValidationError, TypeError)):
        ProvenanceField[str](value="AM5")  # type: ignore[call-arg]


def test_provenance_field_round_trip() -> None:
    pf: ProvenanceField[str] = ProvenanceField[str](
        value="AM5",
        provenance=Provenance(source="test", method="authoritative-verified", confidence=1.0),
    )
    dumped = pf.model_dump()
    restored = ProvenanceField[str].model_validate(dumped)
    assert restored.value == "AM5"
    assert restored.provenance.source == "test"


# ── CPU model ─────────────────────────────────────────────────────────────────

def test_cpu_valid() -> None:
    part = CPUPart.model_validate(make_cpu())
    assert part.socket.value == "AM5"
    assert part.tdp_watts.value == 105
    assert part.category == "cpu"


def test_cpu_missing_socket_fails() -> None:
    data = make_cpu()
    del data["socket"]
    with pytest.raises(ValidationError):
        CPUPart.model_validate(data)


def test_cpu_missing_tdp_fails() -> None:
    data = make_cpu()
    del data["tdp_watts"]
    with pytest.raises(ValidationError):
        CPUPart.model_validate(data)


def test_cpu_round_trip() -> None:
    part = CPUPart.model_validate(make_cpu())
    dumped = part.model_dump()
    restored = CPUPart.model_validate(dumped)
    assert restored.socket.value == part.socket.value
    assert restored.socket.provenance.method == part.socket.provenance.method


def test_cpu_extra_goes_to_attributes() -> None:
    data = make_cpu()
    data["attributes"] = {"cores": 16, "threads": 32}
    part = CPUPart.model_validate(data)
    assert part.attributes["cores"] == 16
    assert not hasattr(part, "cores")


def test_cpu_unknown_field_not_engine_field() -> None:
    """Unknown top-level keys must NOT become engine-fields."""
    data = make_cpu()
    data["secret_extra_field"] = "bad"
    # Pydantic v2 ignores extra fields by default; they must not leak into engine space
    part = CPUPart.model_validate(data)
    assert not hasattr(part, "secret_extra_field")


# ── Motherboard model ─────────────────────────────────────────────────────────

def test_motherboard_valid() -> None:
    part = MotherboardPart.model_validate(make_motherboard())
    assert part.socket.value == "AM5"
    assert part.ram_type.value == "DDR5"
    assert part.form_factor.value == "ATX"
    assert part.memory_slots.value == 4
    assert part.m2_slots.value == 3
    assert part.sata_ports.value == 6


def test_motherboard_invalid_ram_type() -> None:
    data = make_motherboard(ram_type=make_pf("DDR3"))
    with pytest.raises(ValidationError):
        MotherboardPart.model_validate(data)


def test_motherboard_optional_memory_max_gb() -> None:
    data = make_motherboard(memory_max_gb=make_pf(128))
    part = MotherboardPart.model_validate(data)
    assert part.memory_max_gb is not None
    assert part.memory_max_gb.value == 128


def test_motherboard_round_trip() -> None:
    part = MotherboardPart.model_validate(make_motherboard())
    restored = MotherboardPart.model_validate(part.model_dump())
    assert restored.socket.value == part.socket.value
    assert restored.ram_type.value == part.ram_type.value


# ── All 8 categories validate ─────────────────────────────────────────────────

def test_all_categories_validate() -> None:
    models = [
        CPUPart.model_validate(make_cpu()),
        MotherboardPart.model_validate(make_motherboard()),
        RAMPart.model_validate({
            "category": "ram", "name": "Test RAM",
            "ddr_generation": make_pf("DDR5"),
            "speed_mhz": make_pf(6000),
            "module_count": make_pf(2),
            "capacity_gb": make_pf(32),
        }),
        PSUPart.model_validate({
            "category": "psu", "name": "Test PSU",
            "wattage": make_pf(850),
        }),
        GPUPart.model_validate({
            "category": "gpu", "name": "Test GPU",
            "tdp_watts": make_pf(300),
        }),
        CasePart.model_validate({
            "category": "case", "name": "Test Case",
            "form_factors_supported": make_pf(["ATX", "mATX"]),
        }),
        StoragePart.model_validate({
            "category": "storage", "name": "Test SSD",
            "interface": make_pf("M.2 NVMe"),
            "form_factor": make_pf("M.2 2280"),
        }),
        CoolerPart.model_validate({
            "category": "cooler", "name": "Test Cooler",
            "height_mm": make_pf(165),
        }),
    ]
    assert len(models) == 8


# ── Discriminated union ───────────────────────────────────────────────────────

def test_discriminated_union_cpu() -> None:
    part = parse_catalog_part(make_cpu())
    assert isinstance(part, CPUPart)


def test_discriminated_union_motherboard() -> None:
    part = parse_catalog_part(make_motherboard())
    assert isinstance(part, MotherboardPart)


def test_discriminated_union_wrong_category() -> None:
    with pytest.raises(Exception):
        parse_catalog_part({"category": "spaceship", "name": "X"})


# ── Catastrophic fields ───────────────────────────────────────────────────────

def test_catastrophic_field_set_exact() -> None:
    """The exact catastrophic field set from the spec §1."""
    expected = frozenset({
        "socket", "ram_type", "ddr_generation", "form_factor",
        "wattage", "tdp_watts", "interface", "m2_slots", "sata_ports",
    })
    assert CATASTROPHIC_ENGINE_FIELDS == expected


def test_cpu_catastrophic_fields() -> None:
    # socket and tdp_watts are catastrophic
    assert "socket" in CPUPart.CATASTROPHIC_FIELDS
    assert "tdp_watts" in CPUPart.CATASTROPHIC_FIELDS


def test_motherboard_catastrophic_fields() -> None:
    assert "socket" in MotherboardPart.CATASTROPHIC_FIELDS
    assert "ram_type" in MotherboardPart.CATASTROPHIC_FIELDS
    assert "form_factor" in MotherboardPart.CATASTROPHIC_FIELDS
    assert "m2_slots" in MotherboardPart.CATASTROPHIC_FIELDS
    assert "sata_ports" in MotherboardPart.CATASTROPHIC_FIELDS


def test_catastrophic_fields_queryable() -> None:
    assert CPUPart.catastrophic_fields() == CPUPart.CATASTROPHIC_FIELDS
    assert MotherboardPart.catastrophic_fields() == MotherboardPart.CATASTROPHIC_FIELDS
