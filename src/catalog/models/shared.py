"""Shared model primitives: ProvenanceField, SharedPart, catastrophic-field registry."""

from __future__ import annotations

import uuid
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

__all__ = [
    "Provenance",
    "ProvenanceField",
    "SharedPart",
    "CATASTROPHIC_ENGINE_FIELDS",
    "ProvenanceMethod",
    "VerificationStatus",
]

ProvenanceMethod = Literal["authoritative-verified", "llm-extracted", "corroborated"]
VerificationStatus = Literal["verified", "extracted", "verify"]

# The exact catastrophic-field set from the spec §1.
# A source conflict on any of these always routes to a human — never auto-picked.
CATASTROPHIC_ENGINE_FIELDS: frozenset[str] = frozenset(
    {
        "socket",
        "ram_type",
        "ddr_generation",
        "form_factor",
        "wattage",
        "tdp_watts",
        "interface",
        "m2_slots",
        "sata_ports",
    }
)

T = TypeVar("T")


class Provenance(BaseModel):
    source: str
    method: ProvenanceMethod
    confidence: float  # 0.0 – 1.0


class ProvenanceField(BaseModel, Generic[T]):
    """Engine-field wrapper — a value cannot exist without provenance."""

    value: T
    provenance: Provenance


class SharedPart(BaseModel):
    """Fields present on every catalog part."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str
    name: str
    retailer_refs: dict[str, str] = Field(default_factory=dict)
    price_snapshot: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
