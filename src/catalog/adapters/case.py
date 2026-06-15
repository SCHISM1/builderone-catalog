"""Case source adapter — raw text → LLM extraction → llm-extracted observations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from catalog.adapters.base import SourceObservation, content_hash
from catalog.adapters.motherboard import LLMExtractor


class CaseExtractionResult(BaseModel):
    """Schema fed to the LLM extractor. Fields are ordered reasoning-first."""

    reasoning: str = Field(description="Step-by-step reasoning before answering.")
    form_factors_supported: list[str] = Field(
        description="List of motherboard form factors the case supports, e.g. ['ATX', 'mATX', 'ITX'].",
        min_length=1,
    )
    max_gpu_length_mm: int | None = Field(
        None,
        description="Maximum GPU length supported in mm. Null if not specified.",
    )
    max_cooler_height_mm: int | None = Field(
        None,
        description="Maximum CPU cooler height supported in mm. Null if not specified.",
    )
    extra_attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Any other notable specs not captured above.",
    )


class CaseAdapter:
    """Reads raw case spec text → schema-enforced LLM extraction → observations.

    LLM-extraction path: method = llm-extracted.
    Caches extraction by SHA-256 hash of the source text.
    Single repair retry on failure; second failure quarantines the text block.
    """

    source_name: str = "case-llm"

    def __init__(self, fixture_texts: list[str], extractor: LLMExtractor) -> None:
        self._texts = fixture_texts
        self._extractor = extractor
        self._cache: dict[str, SourceObservation] = {}

    @classmethod
    def from_text_file(cls, path: str, extractor: LLMExtractor) -> CaseAdapter:
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

            engine_field_values: dict[str, Any] = {
                "form_factors_supported": result.form_factors_supported,
            }
            if result.max_gpu_length_mm is not None:
                engine_field_values["max_gpu_length_mm"] = result.max_gpu_length_mm
            if result.max_cooler_height_mm is not None:
                engine_field_values["max_cooler_height_mm"] = result.max_cooler_height_mm

            obs = SourceObservation(
                source_name=self.source_name,
                source_content_hash=chash,
                category="case",
                raw_name=_first_line(text),
                engine_field_values=engine_field_values,
                attributes=result.extra_attributes,
                method="llm-extracted",
                confidence=0.85,
            )
            self._cache[chash] = obs
            observations.append(obs)

        return observations

    def _extract_with_retry(self, text: str) -> CaseExtractionResult | None:
        try:
            return self._extractor.extract(text, CaseExtractionResult, max_retries=1)  # type: ignore[no-any-return]
        except Exception:
            pass
        try:
            return self._extractor.extract(text, CaseExtractionResult, max_retries=1)  # type: ignore[no-any-return]
        except Exception:
            return None


def _first_line(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[0] if lines else "Unknown Case"
