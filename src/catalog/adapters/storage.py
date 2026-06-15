"""Storage/SSD source adapter — structured JSON → authoritative-verified observations."""

from __future__ import annotations

import json
from typing import Any

from catalog.adapters.base import SourceObservation, content_hash


class StorageAdapter:
    """Reads a structured storage JSON fixture → SourceObservations.

    Clean-source path (TechPowerUp shape): no LLM, method = authoritative-verified.
    Engine fields: interface, form_factor.
    Anything else goes to attributes.
    """

    source_name: str = "storage-structured"

    def __init__(self, fixture_data: list[dict[str, Any]]) -> None:
        self._fixture = fixture_data
        self._cache: dict[str, list[SourceObservation]] = {}

    @classmethod
    def from_json_file(cls, path: str) -> StorageAdapter:
        with open(path) as fh:
            return cls(json.load(fh))

    def fetch(self) -> list[SourceObservation]:
        raw = json.dumps(self._fixture, sort_keys=True)
        chash = content_hash(raw)

        if chash in self._cache:
            return self._cache[chash]

        _engine_keys = {"name", "interface", "form_factor", "retailer_refs", "price_snapshot"}

        observations: list[SourceObservation] = []
        for item in self._fixture:
            obs = SourceObservation(
                source_name=self.source_name,
                source_content_hash=content_hash(json.dumps(item, sort_keys=True)),
                category="storage",
                raw_name=item["name"],
                engine_field_values={
                    "interface": item["interface"],
                    "form_factor": item["form_factor"],
                },
                attributes={k: v for k, v in item.items() if k not in _engine_keys},
                method="authoritative-verified",
                confidence=1.0,
            )
            observations.append(obs)

        self._cache[chash] = observations
        return observations
