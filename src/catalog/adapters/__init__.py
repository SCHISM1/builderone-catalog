"""Source adapters."""

from catalog.adapters.base import SourceAdapter, SourceObservation, content_hash
from catalog.adapters.case import CaseAdapter, CaseExtractionResult
from catalog.adapters.cooler import CoolerAdapter, CoolerExtractionResult
from catalog.adapters.cpu import CPUAdapter
from catalog.adapters.gpu import GPUAdapter
from catalog.adapters.motherboard import (
    LLMExtractor,
    MotherboardAdapter,
    MotherboardExtractionResult,
)
from catalog.adapters.psu import PSUAdapter, PSUExtractionResult
from catalog.adapters.ram import RAMAdapter, RAMExtractionResult
from catalog.adapters.storage import StorageAdapter

__all__ = [
    "SourceAdapter",
    "SourceObservation",
    "content_hash",
    "CaseAdapter",
    "CaseExtractionResult",
    "CoolerAdapter",
    "CoolerExtractionResult",
    "CPUAdapter",
    "GPUAdapter",
    "LLMExtractor",
    "MotherboardAdapter",
    "MotherboardExtractionResult",
    "PSUAdapter",
    "PSUExtractionResult",
    "RAMAdapter",
    "RAMExtractionResult",
    "StorageAdapter",
]
