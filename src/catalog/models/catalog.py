"""Discriminated union of all catalog part models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from catalog.models.case import CasePart
from catalog.models.cooler import CoolerPart
from catalog.models.cpu import CPUPart
from catalog.models.gpu import GPUPart
from catalog.models.motherboard import MotherboardPart
from catalog.models.psu import PSUPart
from catalog.models.ram import RAMPart
from catalog.models.storage import StoragePart

__all__ = ["CatalogPart", "parse_catalog_part"]

CatalogPart = Annotated[
    CPUPart | MotherboardPart | RAMPart | PSUPart | GPUPart | CasePart | StoragePart | CoolerPart,
    Field(discriminator="category"),
]


def parse_catalog_part(data: dict) -> CatalogPart:  # type: ignore[return]
    """Parse a raw dict into the correct part model via discriminated union."""
    from pydantic import TypeAdapter

    adapter: TypeAdapter[CatalogPart] = TypeAdapter(CatalogPart)
    return adapter.validate_python(data)
