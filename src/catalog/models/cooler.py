"""Cooler catalog model."""

from __future__ import annotations

from typing import ClassVar, Literal

from catalog.models.shared import CATASTROPHIC_ENGINE_FIELDS, ProvenanceField, SharedPart


class CoolerPart(SharedPart):
    category: Literal["cooler"] = "cooler"

    height_mm: ProvenanceField[int]

    CATASTROPHIC_FIELDS: ClassVar[frozenset[str]] = frozenset(
        set() & CATASTROPHIC_ENGINE_FIELDS
    )

    @classmethod
    def catastrophic_fields(cls) -> frozenset[str]:
        return cls.CATASTROPHIC_FIELDS
