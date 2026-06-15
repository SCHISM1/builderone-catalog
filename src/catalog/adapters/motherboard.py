"""Motherboard source adapter — raw text → LLM extraction → llm-extracted observations."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from catalog.adapters.base import SourceObservation, content_hash

# ── Extraction schema (reasoning-first field ordering) ────────────────────────

class MotherboardExtractionResult(BaseModel):
    """Schema fed to the LLM extractor. Fields are ordered reasoning-first."""

    reasoning: str = Field(description="Step-by-step reasoning before answering.")
    socket: str = Field(description="CPU socket, e.g. AM5, LGA1700.")
    form_factor: str = Field(description="ATX, mATX, Mini-ITX, etc.")
    ram_type: Literal["DDR4", "DDR5"] = Field(description="Memory standard supported.")
    memory_slots: int = Field(description="Number of DIMM slots.", ge=1)
    m2_slots: int = Field(description="Number of M.2 slots.", ge=0)
    sata_ports: int = Field(description="Number of SATA ports.", ge=0)
    memory_max_gb: int | None = Field(None, description="Maximum supported memory in GB.")
    extra_attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Any other notable specs not captured above.",
    )


# ── LLM extractor protocol ────────────────────────────────────────────────────

class LLMExtractor(Protocol):
    """Injected dependency — real impl uses instructor; mock returns canned data."""

    call_count: int

    def extract(
        self,
        text: str,
        response_model: type,
        max_retries: int,
    ) -> Any:
        """Extract structured data from *text* into *response_model*.

        Raises on unrecoverable failure.
        """
        ...


# ── Adapter ───────────────────────────────────────────────────────────────────

class MotherboardAdapter:
    """Reads raw motherboard spec text → schema-enforced LLM extraction → observations.

    LLM-extraction path: method = llm-extracted.
    Caches extraction by SHA-256 hash of the source text.
    Single repair retry: if extraction fails, retries once; second failure quarantines.
    """

    source_name: str = "motherboard-llm"

    def __init__(self, fixture_texts: list[str], extractor: LLMExtractor) -> None:
        self._texts = fixture_texts
        self._extractor = extractor
        # Cache: per-item content_hash -> SourceObservation
        self._cache: dict[str, SourceObservation] = {}

    @classmethod
    def from_text_file(cls, path: str, extractor: LLMExtractor) -> MotherboardAdapter:
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
                # Quarantined — do not write a trusted engine-field observation
                continue

            name_guess = _first_line(text)
            obs = SourceObservation(
                source_name=self.source_name,
                source_content_hash=chash,
                category="motherboard",
                raw_name=name_guess,
                engine_field_values={
                    "socket": result.socket,
                    "ram_type": result.ram_type,
                    "form_factor": result.form_factor,
                    "memory_slots": result.memory_slots,
                    "m2_slots": result.m2_slots,
                    "sata_ports": result.sata_ports,
                    **({"memory_max_gb": result.memory_max_gb}
                       if result.memory_max_gb is not None else {}),
                },
                attributes=result.extra_attributes,
                method="llm-extracted",
                confidence=0.85,
            )
            self._cache[chash] = obs
            observations.append(obs)

        return observations

    def _extract_with_retry(self, text: str) -> MotherboardExtractionResult | None:
        try:
            result = self._extractor.extract(text, MotherboardExtractionResult, max_retries=1)
            return result  # type: ignore[no-any-return]
        except Exception:
            pass
        # Single repair retry
        try:
            result = self._extractor.extract(text, MotherboardExtractionResult, max_retries=1)
            return result  # type: ignore[no-any-return]
        except Exception:
            return None  # quarantine


def _first_line(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[0] if lines else "Unknown Motherboard"
