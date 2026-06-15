"""Motherboard catalog model."""

from __future__ import annotations

from typing import ClassVar, Literal

from catalog.models.shared import CATASTROPHIC_ENGINE_FIELDS, ProvenanceField, SharedPart


class MotherboardPart(SharedPart):
    category: Literal["motherboard"] = "motherboard"

    # Engine-fields (Run 5 contract)
    socket: ProvenanceField[str]
    ram_type: ProvenanceField[Literal["DDR4", "DDR5"]]
    form_factor: ProvenanceField[str]
    memory_slots: ProvenanceField[int]
    memory_max_gb: ProvenanceField[int] | None = None
    m2_slots: ProvenanceField[int]
    sata_ports: ProvenanceField[int]

    CATASTROPHIC_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"socket", "ram_type", "form_factor", "m2_slots", "sata_ports"} & CATASTROPHIC_ENGINE_FIELDS
    )

    @classmethod
    def catastrophic_fields(cls) -> frozenset[str]:
        return cls.CATASTROPHIC_FIELDS
