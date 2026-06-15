"""4b M3 — Case + Cooler LLM-extraction adapter tests."""

from __future__ import annotations

from pathlib import Path

from catalog.adapters import (
    CaseAdapter,
    CaseExtractionResult,
    CoolerAdapter,
    CoolerExtractionResult,
    SourceAdapter,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_case_response(
    form_factors_supported: list[str] | None = None,
    max_gpu_length_mm: int | None = 461,
    max_cooler_height_mm: int | None = 188,
) -> CaseExtractionResult:
    return CaseExtractionResult(
        reasoning="Spec lists ATX, mATX, ITX support.",
        form_factors_supported=form_factors_supported or ["ATX", "mATX", "ITX"],
        max_gpu_length_mm=max_gpu_length_mm,
        max_cooler_height_mm=max_cooler_height_mm,
    )


def _make_cooler_response(height_mm: int = 165) -> CoolerExtractionResult:
    return CoolerExtractionResult(
        reasoning="Spec states 165mm total height.",
        height_mm=height_mm,
    )


# ── Case adapter ──────────────────────────────────────────────────────────────

def test_case_adapter_protocol() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = CaseAdapter(["Fractal Torrent ATX"], MockLLMExtractor(responses=[_make_case_response()]))
    assert isinstance(adapter, SourceAdapter)


def test_case_adapter_produces_observations() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_case_response(), _make_case_response(form_factors_supported=["ATX", "mATX", "ITX", "E-ATX"])])
    texts = ["Fractal Design Torrent ATX", "Lian Li O11 Dynamic EVO"]
    obs_list = CaseAdapter(texts, extractor).fetch()
    assert len(obs_list) == 2


def test_case_adapter_method_llm_extracted() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = CaseAdapter(["Fractal Torrent ATX"], MockLLMExtractor(responses=[_make_case_response()]))
    for obs in adapter.fetch():
        assert obs.method == "llm-extracted"
        assert obs.category == "case"


def test_case_adapter_form_factors_is_list() -> None:
    """form_factors_supported must parse to a proper list, never a single string blob."""
    from tests.conftest import MockLLMExtractor
    adapter = CaseAdapter(
        ["Fractal Design Torrent ATX"],
        MockLLMExtractor(responses=[_make_case_response(form_factors_supported=["ATX", "mATX", "ITX"])]),
    )
    obs_list = adapter.fetch()
    ff = obs_list[0].engine_field_values["form_factors_supported"]
    assert isinstance(ff, list), "form_factors_supported must be a list"
    assert len(ff) == 3
    assert "ATX" in ff
    assert "mATX" in ff
    assert "ITX" in ff


def test_case_adapter_clearance_fields_present() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = CaseAdapter(
        ["Fractal Design Torrent ATX"],
        MockLLMExtractor(responses=[_make_case_response(max_gpu_length_mm=461, max_cooler_height_mm=188)]),
    )
    obs_list = adapter.fetch()
    ef = obs_list[0].engine_field_values
    assert ef["max_gpu_length_mm"] == 461
    assert ef["max_cooler_height_mm"] == 188


def test_case_adapter_clearance_fields_absent_tolerated() -> None:
    """Optional clearance fields absent → not in engine_field_values, not an error."""
    from tests.conftest import MockLLMExtractor
    adapter = CaseAdapter(
        ["No-clearance Case"],
        MockLLMExtractor(responses=[_make_case_response(max_gpu_length_mm=None, max_cooler_height_mm=None)]),
    )
    obs_list = adapter.fetch()
    ef = obs_list[0].engine_field_values
    assert "max_gpu_length_mm" not in ef
    assert "max_cooler_height_mm" not in ef
    assert "form_factors_supported" in ef


def test_case_adapter_malformed_then_repair() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_case_response()], fail_first_n=1)
    adapter = CaseAdapter(["Fractal Design Torrent ATX"], extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 1
    assert extractor.call_count == 2


def test_case_adapter_both_retries_fail() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[], fail_first_n=99)
    adapter = CaseAdapter(["Fractal Design Torrent ATX"], extractor)
    assert len(adapter.fetch()) == 0


def test_case_adapter_cache_hit_zero_llm_calls() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_case_response()])
    text = "Fractal Design Torrent ATX"
    adapter = CaseAdapter([text], extractor)
    adapter.fetch()
    calls_after_first = extractor.call_count
    adapter.fetch()
    assert extractor.call_count == calls_after_first


def test_case_adapter_from_text_file() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[
        _make_case_response(),
        _make_case_response(form_factors_supported=["ATX", "mATX", "ITX", "E-ATX"]),
    ])
    adapter = CaseAdapter.from_text_file(str(FIXTURE_DIR / "case_source.txt"), extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 2


# ── Cooler adapter ────────────────────────────────────────────────────────────

def test_cooler_adapter_protocol() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = CoolerAdapter(["Noctua NH-D15"], MockLLMExtractor(responses=[_make_cooler_response()]))
    assert isinstance(adapter, SourceAdapter)


def test_cooler_adapter_produces_observations() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_cooler_response(), _make_cooler_response(163)])
    texts = ["Noctua NH-D15", "be quiet! Dark Rock Pro 4"]
    obs_list = CoolerAdapter(texts, extractor).fetch()
    assert len(obs_list) == 2


def test_cooler_adapter_method_llm_extracted() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = CoolerAdapter(["Noctua NH-D15"], MockLLMExtractor(responses=[_make_cooler_response()]))
    for obs in adapter.fetch():
        assert obs.method == "llm-extracted"
        assert obs.category == "cooler"


def test_cooler_adapter_height_mm_populated() -> None:
    from tests.conftest import MockLLMExtractor
    adapter = CoolerAdapter(
        ["Noctua NH-D15 chromax.black"],
        MockLLMExtractor(responses=[_make_cooler_response(165)]),
    )
    obs_list = adapter.fetch()
    assert obs_list[0].engine_field_values["height_mm"] == 165


def test_cooler_adapter_malformed_then_repair() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_cooler_response()], fail_first_n=1)
    adapter = CoolerAdapter(["Noctua NH-D15"], extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 1
    assert extractor.call_count == 2


def test_cooler_adapter_both_retries_fail() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[], fail_first_n=99)
    adapter = CoolerAdapter(["Noctua NH-D15"], extractor)
    assert len(adapter.fetch()) == 0


def test_cooler_adapter_cache_hit_zero_llm_calls() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_cooler_response()])
    text = "Noctua NH-D15 chromax.black"
    adapter = CoolerAdapter([text], extractor)
    adapter.fetch()
    calls_after_first = extractor.call_count
    adapter.fetch()
    assert extractor.call_count == calls_after_first


def test_cooler_adapter_from_text_file() -> None:
    from tests.conftest import MockLLMExtractor
    extractor = MockLLMExtractor(responses=[_make_cooler_response(), _make_cooler_response(163)])
    adapter = CoolerAdapter.from_text_file(str(FIXTURE_DIR / "cooler_source.txt"), extractor)
    obs_list = adapter.fetch()
    assert len(obs_list) == 2
