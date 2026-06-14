"""CPU catalog model."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import model_validator

from catalog.models.shared import CATASTROPHIC_ENGINE_FIELDS, ProvenanceField, SharedPart


class CPUPart(SharedPart):
    category: Literal["cpu"] = "cpu"

    # Engine-fields (Run 5 contract)
    socket: ProvenanceField[str]
    tdp_watts: ProvenanceField[int]

    CATASTROPHIC_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"socket", "tdp_watts"} & CATASTROPHIC_ENGINE_FIELDS
    )

    @model_validator(mode="after")
    def _category_is_cpu(self) -> CPUPart:
        assert self.category == "cpu"
        return self

    @classmethod
    def catastrophic_fields(cls) -> frozenset[str]:
        return cls.CATASTROPHIC_FIELDS
