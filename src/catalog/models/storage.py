"""Storage catalog model."""

from __future__ import annotations

from typing import ClassVar, Literal

from catalog.models.shared import CATASTROPHIC_ENGINE_FIELDS, ProvenanceField, SharedPart


class StoragePart(SharedPart):
    category: Literal["storage"] = "storage"

    interface: ProvenanceField[str]  # "M.2 NVMe" | "SATA" | …
    form_factor: ProvenanceField[str]

    CATASTROPHIC_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"interface", "form_factor"} & CATASTROPHIC_ENGINE_FIELDS
    )

    @classmethod
    def catastrophic_fields(cls) -> frozenset[str]:
        return cls.CATASTROPHIC_FIELDS
