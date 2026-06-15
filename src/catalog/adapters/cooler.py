"""Cooler source adapter — raw text → LLM extraction → llm-extracted observations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from catalog.adapters.base import SourceObservation, content_hash
from catalog.adapters.motherboard import LLMExtractor


class CoolerExtractionResult(BaseModel):
    """Schema fed to the LLM extractor. Fields are ordered reasoning-first."""

    reasoning: str = Field(description="Step-by-step reasoning before answering.")
    height_mm: int = Field(description="Total cooler height in mm, e.g. 165.", ge=1)
    extra_attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Any other notable specs not captured above.",
    )


class CoolerAdapter:
    """Reads raw cooler spec text → schema-enforced LLM extraction → observations.

    LLM-extraction path: method = llm-extracted.
    Caches extraction by SHA-256 hash of the source text.
    Single repair retry on failure; second failure quarantines the text block.
    """

    source_name: str = "cooler-llm"

    def __init__(self, fixture_texts: list[str], extractor: LLMExtractor) -> None:
        self._texts = fixture_texts
        self._extractor = extractor
        self._cache: dict[str, SourceObservation] = {}

    @classmethod
    def from_text_file(cls, path: str, extractor: LLMExtractor) -> CoolerAdapter:
        with open(path) as fh:
            texts = [block.strip() for block in fh.read().split("---") if block.strip()]
        return cls(texts, extractor)

    def fetch(self) -> list[SourceObservation]:
        observations: list[SourceObservation] = []
        for text in self._texts:
            chash = content_hash(text)
            if chash in self._cache:
                observations.append(self._cache[chash])
                continue

            result = self._extract_with_retry(text)
            if result is None:
                continue

            obs = SourceObservation(
                source_name=self.source_name,
                source_content_hash=chash,
                category="cooler",
                raw_name=_first_line(text),
                engine_field_values={
                    "height_mm": result.height_mm,
                },
                attributes=result.extra_attributes,
                method="llm-extracted",
                confidence=0.85,
            )
            self._cache[chash] = obs
            observations.append(obs)

        return observations

    def _extract_with_retry(self, text: str) -> CoolerExtractionResult | None:
        try:
            return self._extractor.extract(text, CoolerExtractionResult, max_retries=1)  # type: ignore[no-any-return]
        except Exception:
            pass
        try:
            return self._extractor.extract(text, CoolerExtractionResult, max_retries=1)  # type: ignore[no-any-return]
        except Exception:
            return None


def _first_line(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[0] if lines else "Unknown Cooler"
