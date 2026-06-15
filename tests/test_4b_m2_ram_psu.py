"""4b M2 — RAM + PSU LLM-extraction adapter tests."""

from __future__ import annotations

from pathlib import Path

from catalog.adapters import (
    PSUAdapter,
    PSUExtractionResult,
    RAMAdapter,
    RAMExtractionResult,
    SourceAdapter,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ram_response(
    ddr_generation: str = "DDR5",
    speed_mhz: int = 6000,
    module_count: int = 2,
    capacity_gb: int = 32,
) -> RAMExtractionResult:
    return RAMExtractionResult(
        reasoning="Spec says DDR5-6000 2x16GB kit.",
        ddr_generation=ddr_generation,  # type: ignore[arg-type]
        speed_mhz=speed_mhz,
        module_count=module_count,
        capacity_gb=capacity_gb,
    )


def _make_psu_response(wattage: int = 1000) -> PSUExtractionResult:
    return PSUExtractionResult(
        reasoning="Spec states 1000W rated output.",
        wattage=wattage,
    )


# ── RAM adapter ───────────────────────────────────────────────────────────────

def test_ram_adapter_protocol() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = RAMAdapter(["Corsair DDR5-6000"], MockLLMExtractor(responses=[_make_ram_response()]))
    assert isinstance(adapter, SourceAdapter)


def test_ram_adapter_produces_observations() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_ram_response(), _make_ram_response(speed_mhz=7200, capacity_gb=64)])
    texts = ["Corsair Vengeance DDR5-6000 32GB", "G.Skill Trident Z5 DDR5-7200 64GB"]
    obs_list = RAMAdapter(texts, extractor).fetch()
    assert len(obs_list) == 2


def test_ram_adapter_method_llm_extracted() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = RAMAdapter(["Corsair DDR5-6000 32GB"], MockLLMExtractor(responses=[_make_ram_response()]))
    for obs in adapter.fetch():
        assert obs.method == "llm-extracted"
        assert obs.category == "ram"


def test_ram_adapter_engine_fields_populated() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = RAMAdapter(["Corsair DDR5-6000 32GB"], MockLLMExtractor(responses=[_make_ram_response()]))
    obs_list = adapter.fetch()
    assert len(obs_list) == 1
    ef = obs_list[0].engine_field_values
    assert ef["ddr_generation"] == "DDR5"
    assert ef["speed_mhz"] == 6000
    assert ef["module_count"] == 2
    assert ef["capacity_gb"] == 32


def test_ram_adapter_ddr4_accepted() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = RAMAdapter(
        ["Corsair Vengeance LPX DDR4-3200 16GB"],
        MockLLMExtractor(responses=[_make_ram_response(ddr_generation="DDR4", speed_mhz=3200, capacity_gb=16)]),
    )
    obs_list = adapter.fetch()
    assert obs_list[0].engine_field_values["ddr_generation"] == "DDR4"


def test_ram_adapter_malformed_then_repair() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_ram_response()], fail_first_n=1)
    adapter = RAMAdapter(["Corsair DDR5-6000 32GB"], extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 1
    assert extractor.call_count == 2


def test_ram_adapter_both_retries_fail() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[], fail_first_n=99)
    adapter = RAMAdapter(["Corsair DDR5-6000 32GB"], extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 0


def test_ram_adapter_cache_hit_zero_llm_calls() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_ram_response()])
    text = "Corsair Vengeance DDR5-6000 32GB"
    adapter = RAMAdapter([text], extractor)
    adapter.fetch()
    calls_after_first = extractor.call_count
    adapter.fetch()
    assert extractor.call_count == calls_after_first


def test_ram_adapter_from_text_file() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(
        responses=[_make_ram_response(), _make_ram_response(speed_mhz=7200, capacity_gb=64, module_count=2)]
    )
    adapter = RAMAdapter.from_text_file(str(FIXTURE_DIR / "ram_source.txt"), extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 2


# ── PSU adapter ───────────────────────────────────────────────────────────────

def test_psu_adapter_protocol() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = PSUAdapter(["Corsair RM1000x 1000W"], MockLLMExtractor(responses=[_make_psu_response()]))
    assert isinstance(adapter, SourceAdapter)


def test_psu_adapter_produces_observations() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_psu_response(), _make_psu_response(wattage=850)])
    texts = ["Corsair RM1000x 1000W", "SeaSonic Focus GX-850 850W"]
    obs_list = PSUAdapter(texts, extractor).fetch()
    assert len(obs_list) == 2


def test_psu_adapter_method_llm_extracted() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = PSUAdapter(["Corsair RM1000x 1000W"], MockLLMExtractor(responses=[_make_psu_response()]))
    for obs in adapter.fetch():
        assert obs.method == "llm-extracted"
        assert obs.category == "psu"


def test_psu_adapter_wattage_populated() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = PSUAdapter(["Corsair RM1000x 1000W"], MockLLMExtractor(responses=[_make_psu_response(1000)]))
    obs_list = adapter.fetch()
    assert obs_list[0].engine_field_values["wattage"] == 1000


def test_psu_adapter_malformed_then_repair() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_psu_response()], fail_first_n=1)
    adapter = PSUAdapter(["Corsair RM1000x 1000W"], extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 1
    assert extractor.call_count == 2


def test_psu_adapter_both_retries_fail() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[], fail_first_n=99)
    adapter = PSUAdapter(["Corsair RM1000x 1000W"], extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 0


def test_psu_adapter_cache_hit_zero_llm_calls() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_psu_response()])
    text = "Corsair RM1000x 1000W"
    adapter = PSUAdapter([text], extractor)
    adapter.fetch()
    calls_after_first = extractor.call_count
    adapter.fetch()
    assert extractor.call_count == calls_after_first


def test_psu_adapter_from_text_file() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_psu_response(), _make_psu_response(850)])
    adapter = PSUAdapter.from_text_file(str(FIXTURE_DIR / "psu_source.txt"), extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 2
