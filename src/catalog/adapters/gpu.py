"""GPU source adapter — structured JSON → authoritative-verified observations."""

from __future__ import annotations

import json
from typing import Any

from catalog.adapters.base import SourceObservation, content_hash


class GPUAdapter:
    """Reads a structured GPU JSON fixture → SourceObservations.

    Clean-source path (TechPowerUp / DBGPU shape): no LLM, method = authoritative-verified.
    Engine fields: tdp_watts (required), length_mm (optional).
    Anything else goes to attributes.
    """

    source_name: str = "gpu-structured"

    def __init__(self, fixture_data: list[dict[str, Any]]) -> None:
        self._fixture = fixture_data
        self._cache: dict[str, list[SourceObservation]] = {}

    @classmethod
    def from_json_file(cls, path: str) -> GPUAdapter:
        with open(path) as fh:
            return cls(json.load(fh))

    def fetch(self) -> list[SourceObservation]:
        raw = json.dumps(self._fixture, sort_keys=True)
        chash = content_hash(raw)

        if chash in self._cache:
            return self._cache[chash]

        _engine_keys = {"name", "tdp_watts", "length_mm", "retailer_refs", "price_snapshot"}

        observations: list[SourceObservation] = []
        for item in self._fixture:
            engine_field_values: dict[str, Any] = {
                "tdp_watts": int(item["tdp_watts"]),
            }
            if item.get("length_mm") is not None:
                engine_field_values["length_mm"] = int(item["length_mm"])

            obs = SourceObservation(
                source_name=self.source_name,
                source_content_hash=content_hash(json.dumps(item, sort_keys=True)),
                category="gpu",
                raw_name=item["name"],
                engine_field_values=engine_field_values,
                attributes={k: v for k, v in item.items() if k not in _engine_keys},
                method="authoritative-verified",
                confidence=1.0,
            )
            observations.append(obs)

        self._cache[chash] = observations
        return observations
