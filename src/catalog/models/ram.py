"""RAM catalog model."""

from __future__ import annotations

from typing import ClassVar, Literal

from catalog.models.shared import CATASTROPHIC_ENGINE_FIELDS, ProvenanceField, SharedPart


class RAMPart(SharedPart):
    category: Literal["ram"] = "ram"

    ddr_generation: ProvenanceField[Literal["DDR4", "DDR5"]]
    speed_mhz: ProvenanceField[int]
    module_count: ProvenanceField[int]
    capacity_gb: ProvenanceField[int]

    CATASTROPHIC_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"ddr_generation"} & CATASTROPHIC_ENGINE_FIELDS
    )

    @classmethod
    def catastrophic_fields(cls) -> frozenset[str]:
        return cls.CATASTROPHIC_FIELDS
