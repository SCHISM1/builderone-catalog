"""SourceAdapter protocol and SourceObservation data class."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


def _now() -> str:
    return datetime.now(UTC).isoformat()


def content_hash(content: str) -> str:
    """SHA-256 of the source content — used as cache key."""
    return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class SourceObservation:
    """Raw per-source observation, before entity resolution or reconciliation."""

    source_name: str
    source_content_hash: str
    category: str
    raw_name: str
    engine_field_values: dict[str, Any]
    attributes: dict[str, Any] = field(default_factory=dict)
    method: str = "authoritative-verified"
    confidence: float = 1.0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=_now)


@runtime_checkable
class SourceAdapter(Protocol):
    """Every source adapter implements this protocol."""

    source_name: str

    def fetch(self) -> list[SourceObservation]:
        """Fetch / extract observations from the source.

        Returns a list of SourceObservation objects.
        May use a local cache keyed by content hash.
        """
        ...
