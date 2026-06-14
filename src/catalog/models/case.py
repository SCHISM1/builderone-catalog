"""Case catalog model."""

from __future__ import annotations

from typing import ClassVar, Literal

from catalog.models.shared import CATASTROPHIC_ENGINE_FIELDS, ProvenanceField, SharedPart


class CasePart(SharedPart):
    category: Literal["case"] = "case"

    form_factors_supported: ProvenanceField[list[str]]
    max_gpu_length_mm: ProvenanceField[int] | None = None
    max_cooler_height_mm: ProvenanceField[int] | None = None

    CATASTROPHIC_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"form_factor"} & CATASTROPHIC_ENGINE_FIELDS
    )

    @classmethod
    def catastrophic_fields(cls) -> frozenset[str]:
        return cls.CATASTROPHIC_FIELDS
