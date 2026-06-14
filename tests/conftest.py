"""Shared pytest fixtures and the network guard."""

from __future__ import annotations

import socket as _socket
from typing import Any

import pytest

from catalog.store.db import Database

# ── Network guard ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block all real network calls. Any attempted DNS lookup fails the suite."""

    def _blocked(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError(f"Network access blocked in CI test suite: args={args}")

    monkeypatch.setattr(_socket, "getaddrinfo", _blocked)


# ── In-memory DB ──────────────────────────────────────────────────────────────

@pytest.fixture
def db() -> Database:
    return Database(db_path=":memory:")


# ── Mock LLM extractor ────────────────────────────────────────────────────────

class MockLLMExtractor:
    """Returns canned extraction results; tracks call count."""

    def __init__(
        self,
        responses: list[Any],
        fail_first_n: int = 0,
    ) -> None:
        self.call_count = 0
        self._responses = responses
        self._fail_first_n = fail_first_n

    def extract(self, text: str, response_model: type, max_retries: int = 1) -> Any:
        self.call_count += 1
        if self.call_count <= self._fail_first_n:
            raise ValueError(f"Mock failure #{self.call_count}")
        idx = max(0, self.call_count - self._fail_first_n - 1)
        if idx >= len(self._responses):
            idx = len(self._responses) - 1
        return self._responses[idx]


# ── Mock embedding client ─────────────────────────────────────────────────────

class MockEmbeddingClient:
    """Returns pre-seeded embeddings; tracks call count."""

    def __init__(self, embeddings: dict[str, list[float]] | None = None) -> None:
        self.call_count = 0
        self._embeddings = embeddings or {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        result = []
        for t in texts:
            if t in self._embeddings:
                result.append(self._embeddings[t])
            else:
                # Default: unit vector [1, 0, 0]
                result.append([1.0, 0.0, 0.0])
        return result


# ── Mock LLM match client ─────────────────────────────────────────────────────

class MockLLMMatchClient:
    """Always says 'not the same part' by default; can be overridden."""

    def __init__(self, same: bool = False, confidence: float = 0.5) -> None:
        self.call_count = 0
        self._same = same
        self._confidence = confidence

    def is_same_part(self, a: Any, b: Any) -> tuple[bool, float]:
        self.call_count += 1
        return self._same, self._confidence


# ── Mock LLM reconciler ───────────────────────────────────────────────────────

class MockLLMReconciler:
    """Returns the first candidate value; tracks call count."""

    def __init__(self, chosen_index: int = 0, confidence: float = 0.9) -> None:
        self.call_count = 0
        self._idx = chosen_index
        self._confidence = confidence

    def reconcile_field(
        self,
        field_name: str,
        candidates: list[dict[str, Any]],
        context: str,
    ) -> tuple[Any, float]:
        self.call_count += 1
        value = candidates[min(self._idx, len(candidates) - 1)]["value"]
        return value, self._confidence


# ── Mock Telegram ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_telegram() -> Any:
    from catalog.review.telegram import MockTelegramClient
    return MockTelegramClient()
