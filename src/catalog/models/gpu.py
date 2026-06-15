"""GPU catalog model."""

from __future__ import annotations

from typing import ClassVar, Literal

from catalog.models.shared import CATASTROPHIC_ENGINE_FIELDS, ProvenanceField, SharedPart


class GPUPart(SharedPart):
    category: Literal["gpu"] = "gpu"

    tdp_watts: ProvenanceField[int]
    length_mm: ProvenanceField[int] | None = None

    CATASTROPHIC_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"tdp_watts"} & CATASTROPHIC_ENGINE_FIELDS
    )

    @classmethod
    def catastrophic_fields(cls) -> frozenset[str]:
        return cls.CATASTROPHIC_FIELDS
