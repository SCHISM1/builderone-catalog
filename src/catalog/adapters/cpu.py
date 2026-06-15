"""CPU source adapter — structured JSON → authoritative-verified observations."""

from __future__ import annotations

import json
from typing import Any

from catalog.adapters.base import SourceObservation, content_hash


class CPUAdapter:
    """Reads a structured CPU JSON fixture → SourceObservations.

    Clean-source path: no LLM, method = authoritative-verified.
    The fixture is a list of dicts with keys: name, socket, tdp_watts,
    and optionally retailer_refs, price_snapshot, and attributes.
    """

    source_name: str = "cpu-structured"

    def __init__(self, fixture_data: list[dict[str, Any]]) -> None:
        self._fixture = fixture_data
        # Cache: content_hash -> list[SourceObservation]
        self._cache: dict[str, list[SourceObservation]] = {}

    @classmethod
    def from_json_file(cls, path: str) -> CPUAdapter:
        with open(path) as fh:
            return cls(json.load(fh))

    def fetch(self) -> list[SourceObservation]:
        raw = json.dumps(self._fixture, sort_keys=True)
        chash = content_hash(raw)

        if chash in self._cache:
            return self._cache[chash]

        observations: list[SourceObservation] = []
        for item in self._fixture:
            obs = SourceObservation(
                source_name=self.source_name,
                source_content_hash=content_hash(json.dumps(item, sort_keys=True)),
                category="cpu",
                raw_name=item["name"],
                engine_field_values={
                    "socket": item["socket"],
                    "tdp_watts": int(item["tdp_watts"]),
                },
                attributes={k: v for k, v in item.items()
                            if k not in {"name", "socket", "tdp_watts",
                                         "retailer_refs", "price_snapshot"}},
                method="authoritative-verified",
                confidence=1.0,
            )
            observations.append(obs)

        self._cache[chash] = observations
        return observations
