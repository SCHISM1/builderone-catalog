"""Source adapters."""

from catalog.adapters.base import SourceAdapter, SourceObservation, content_hash
from catalog.adapters.cpu import CPUAdapter
from catalog.adapters.motherboard import (
    LLMExtractor,
    MotherboardAdapter,
    MotherboardExtractionResult,
)

__all__ = [
    "SourceAdapter",
    "SourceObservation",
    "content_hash",
    "CPUAdapter",
    "LLMExtractor",
    "MotherboardAdapter",
    "MotherboardExtractionResult",
]
