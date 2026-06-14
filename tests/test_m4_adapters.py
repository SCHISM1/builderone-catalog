"""M4 — Source adapter tests (CPU clean-source + motherboard LLM-extraction)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from catalog.adapters import (
    CPUAdapter,
    MotherboardAdapter,
    MotherboardExtractionResult,
    SourceAdapter,
)
from catalog.store.db import Database

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── CPU adapter ───────────────────────────────────────────────────────────────

@pytest.fixture
def cpu_fixture() -> list[dict[str, Any]]:
    with open(FIXTURE_DIR / "cpu_source.json") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def test_cpu_adapter_protocol(cpu_fixture: list[dict[str, Any]]) -> None:
    """CPU adapter must satisfy the SourceAdapter protocol."""
    adapter = CPUAdapter(cpu_fixture)
    assert isinstance(adapter, SourceAdapter)


def test_cpu_adapter_produces_observations(cpu_fixture: list[dict[str, Any]]) -> None:
    adapter = CPUAdapter(cpu_fixture)
    obs_list = adapter.fetch()
    assert len(obs_list) == 2


def test_cpu_adapter_method_authoritative(cpu_fixture: list[dict[str, Any]]) -> None:
    adapter = CPUAdapter(cpu_fixture)
    for obs in adapter.fetch():
        assert obs.method == "authoritative-verified"
        assert obs.confidence == 1.0


def test_cpu_adapter_engine_fields(cpu_fixture: list[dict[str, Any]]) -> None:
    adapter = CPUAdapter(cpu_fixture)
    obs_list = adapter.fetch()
    ryzen = next(o for o in obs_list if "Ryzen" in o.raw_name)
    assert ryzen.engine_field_values["socket"] == "AM5"
    assert ryzen.engine_field_values["tdp_watts"] == 170
    intel = next(o for o in obs_list if "i9" in o.raw_name)
    assert intel.engine_field_values["socket"] == "LGA1700"
    assert intel.engine_field_values["tdp_watts"] == 253


def test_cpu_adapter_category(cpu_fixture: list[dict[str, Any]]) -> None:
    adapter = CPUAdapter(cpu_fixture)
    for obs in adapter.fetch():
        assert obs.category == "cpu"


def test_cpu_adapter_cache_hit(cpu_fixture: list[dict[str, Any]]) -> None:
    """Re-running fetch on identical data returns cache, same objects."""
    adapter = CPUAdapter(cpu_fixture)
    obs1 = adapter.fetch()
    obs2 = adapter.fetch()
    assert obs1 is obs2, "Cache hit must return the same list object"


def test_cpu_adapter_writes_to_db(db: Database, cpu_fixture: list[dict[str, Any]]) -> None:
    from catalog.store.db import SourceObservationRow
    adapter = CPUAdapter(cpu_fixture)
    for obs in adapter.fetch():
        db.save_observation(
            SourceObservationRow(
                id=obs.id,
                source_name=obs.source_name,
                source_content_hash=obs.source_content_hash,
                category=obs.category,
                raw_name=obs.raw_name,
                engine_field_values=obs.engine_field_values,
                attributes=obs.attributes,
                method=obs.method,
                confidence=obs.confidence,
                timestamp=obs.timestamp,
            )
        )
    rows = db.get_observations_by_category("cpu")
    assert len(rows) == 2


# ── Motherboard adapter ───────────────────────────────────────────────────────

def _make_mb_response(
    socket: str = "AM5",
    ram_type: str = "DDR5",
    form_factor: str = "ATX",
    memory_slots: int = 4,
    m2_slots: int = 3,
    sata_ports: int = 6,
) -> MotherboardExtractionResult:
    return MotherboardExtractionResult(
        reasoning="Board spec says AM5 socket.",
        socket=socket,
        form_factor=form_factor,
        ram_type=ram_type,  # type: ignore[arg-type]
        memory_slots=memory_slots,
        m2_slots=m2_slots,
        sata_ports=sata_ports,
        memory_max_gb=128,
    )


def test_motherboard_adapter_protocol(conftest_mock_extractor: Any) -> None:
    """Motherboard adapter must satisfy SourceAdapter protocol."""
    adapter = MotherboardAdapter(["ASUS ROG STRIX X670E\nSocket: AM5"], conftest_mock_extractor)
    assert isinstance(adapter, SourceAdapter)


@pytest.fixture
def mock_extractor_ok() -> Any:
    from tests.conftest import MockLLMExtractor
    return MockLLMExtractor(
        responses=[
            _make_mb_response(socket="AM5"),
            _make_mb_response(socket="AM5", m2_slots=3, sata_ports=6),
        ]
    )


@pytest.fixture
def conftest_mock_extractor() -> Any:
    from tests.conftest import MockLLMExtractor
    return MockLLMExtractor(responses=[_make_mb_response()])


def test_motherboard_adapter_produces_observations(mock_extractor_ok: Any) -> None:
    texts = ["ASUS ROG STRIX X670E-E\nSocket: AM5, DDR5", "MSI MAG B650\nSocket: AM5, DDR5"]
    adapter = MotherboardAdapter(texts, mock_extractor_ok)
    obs_list = adapter.fetch()
    assert len(obs_list) == 2


def test_motherboard_adapter_method_llm(mock_extractor_ok: Any) -> None:
    texts = ["ASUS ROG STRIX X670E-E\nSocket: AM5, DDR5"]
    adapter = MotherboardAdapter(texts, mock_extractor_ok)
    for obs in adapter.fetch():
        assert obs.method == "llm-extracted"
        assert obs.category == "motherboard"


def test_motherboard_adapter_engine_fields(conftest_mock_extractor: Any) -> None:
    texts = ["ASUS ROG STRIX X670E-E\nSocket: AM5"]
    adapter = MotherboardAdapter(texts, conftest_mock_extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 1
    ef = obs_list[0].engine_field_values
    assert ef["socket"] == "AM5"
    assert ef["ram_type"] == "DDR5"
    assert ef["form_factor"] == "ATX"
    assert ef["memory_slots"] == 4
    assert ef["m2_slots"] == 3
    assert ef["sata_ports"] == 6


def test_motherboard_malformed_then_repair(conftest_mock_extractor: Any) -> None:
    """Malformed LLM response → exactly one repair retry; success on retry."""
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(
        responses=[_make_mb_response()],
        fail_first_n=1,  # first call raises, second succeeds
    )
    adapter = MotherboardAdapter(["ASUS ROG STRIX X670E"], extractor)
    obs_list = adapter.fetch()
    # Should succeed on retry
    assert len(obs_list) == 1
    assert extractor.call_count == 2  # 1 failure + 1 retry


def test_motherboard_both_retries_fail() -> None:
    """If both attempts fail, the text is quarantined — no observation written."""
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(
        responses=[],
        fail_first_n=99,  # always fail
    )
    adapter = MotherboardAdapter(["ASUS ROG STRIX X670E"], extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 0, "Quarantined text must not produce an observation"


def test_motherboard_cache_hit_zero_llm_calls() -> None:
    """Re-running fetch on identical content must not call the extractor again."""
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_mb_response()])
    text = "ASUS ROG STRIX X670E-E\nSocket: AM5"
    adapter = MotherboardAdapter([text], extractor)

    # First fetch — calls LLM
    adapter.fetch()
    calls_after_first = extractor.call_count

    # Second fetch — cache hit; must not call LLM
    adapter.fetch()
    assert extractor.call_count == calls_after_first, "Cache hit must make zero LLM calls"


def test_motherboard_from_text_file(conftest_mock_extractor: Any) -> None:
    from tests.conftest import MockLLMExtractor
    # Provide enough responses for 2 fixture entries
    extractor = MockLLMExtractor(
        responses=[_make_mb_response(), _make_mb_response(m2_slots=3, sata_ports=6)]
    )
    adapter = MotherboardAdapter.from_text_file(
        str(FIXTURE_DIR / "mb_source.txt"), extractor
    )
    obs_list = adapter.fetch()
    assert len(obs_list) == 2
