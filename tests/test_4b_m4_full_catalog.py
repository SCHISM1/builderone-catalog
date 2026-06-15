"""4b M4 — Full-catalog wire-through, cross-category ER, catastrophic-conflict coverage."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from catalog.adapters import (
    CaseAdapter,
    CaseExtractionResult,
    CoolerAdapter,
    CoolerExtractionResult,
    CPUAdapter,
    GPUAdapter,
    MotherboardAdapter,
    MotherboardExtractionResult,
    PSUAdapter,
    PSUExtractionResult,
    RAMAdapter,
    RAMExtractionResult,
    StorageAdapter,
)
from catalog.batch import run_batch
from catalog.config import Config
from catalog.pipeline.entity_resolution import ObservationGroup
from catalog.pipeline.reconciliation import reconcile_group
from catalog.store.db import Database, SourceObservationRow
from catalog.store.export import build_export, export_to_json

# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _make_obs_row(
    category: str,
    name: str,
    source: str,
    engine_fields: dict[str, Any],
    method: str = "authoritative-verified",
    confidence: float = 1.0,
) -> SourceObservationRow:
    return SourceObservationRow(
        id=_new_id(),
        source_name=source,
        source_content_hash=_new_id(),
        category=category,
        raw_name=name,
        engine_field_values=engine_fields,
        attributes={},
        method=method,
        confidence=confidence,
        timestamp="2026-01-01T00:00:00+00:00",
    )


def _llm_extractor_ram(n: int = 1) -> Any:
    from tests.conftest import MockLLMExtractor
    responses = [
        RAMExtractionResult(
            reasoning="DDR5 kit.",
            ddr_generation="DDR5",
            speed_mhz=6000,
            module_count=2,
            capacity_gb=32,
        )
    ] * n
    return MockLLMExtractor(responses=responses)


def _llm_extractor_psu(n: int = 1) -> Any:
    from tests.conftest import MockLLMExtractor
    responses = [
        PSUExtractionResult(reasoning="1000W PSU.", wattage=1000)
    ] * n
    return MockLLMExtractor(responses=responses)


def _llm_extractor_case(n: int = 1) -> Any:
    from tests.conftest import MockLLMExtractor
    responses = [
        CaseExtractionResult(
            reasoning="ATX case.",
            form_factors_supported=["ATX", "mATX", "ITX"],
            max_gpu_length_mm=461,
            max_cooler_height_mm=188,
        )
    ] * n
    return MockLLMExtractor(responses=responses)


def _llm_extractor_cooler(n: int = 1) -> Any:
    from tests.conftest import MockLLMExtractor
    responses = [
        CoolerExtractionResult(reasoning="165mm cooler.", height_mm=165)
    ] * n
    return MockLLMExtractor(responses=responses)


def _llm_extractor_mb(n: int = 1) -> Any:
    from tests.conftest import MockLLMExtractor
    responses = [
        MotherboardExtractionResult(
            reasoning="AM5 DDR5 ATX board.",
            socket="AM5",
            form_factor="ATX",
            ram_type="DDR5",
            memory_slots=4,
            m2_slots=3,
            sata_ports=6,
        )
    ] * n
    return MockLLMExtractor(responses=responses)


def _build_all_adapters() -> list[Any]:
    """Return one adapter per category, each with one part, no conflicts."""
    cpu = CPUAdapter([{"name": "AMD Ryzen 9 7950X", "socket": "AM5", "tdp_watts": 170}])
    mb = MotherboardAdapter(["ASUS ROG STRIX X670E\nSocket: AM5, DDR5, ATX"], _llm_extractor_mb())
    gpu = GPUAdapter([{"name": "NVIDIA GeForce RTX 4090", "tdp_watts": 450, "length_mm": 336}])
    storage = StorageAdapter([{"name": "Samsung 990 Pro 2TB", "interface": "M.2 NVMe", "form_factor": "M.2 2280"}])
    ram = RAMAdapter(["Corsair Vengeance DDR5-6000 32GB"], _llm_extractor_ram())
    psu = PSUAdapter(["Corsair RM1000x 1000W"], _llm_extractor_psu())
    case = CaseAdapter(["Fractal Design Torrent"], _llm_extractor_case())
    cooler = CoolerAdapter(["Noctua NH-D15"], _llm_extractor_cooler())
    return [cpu, mb, gpu, storage, ram, psu, case, cooler]


# ── Full run ──────────────────────────────────────────────────────────────────

def test_full_catalog_run_all_8_categories(db: Database) -> None:
    """All 8 adapters → complete export covering all 8 categories."""
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    result = run_batch(
        config=Config(),
        db=db,
        adapters=_build_all_adapters(),
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(same=False),
        llm_reconciler=MockLLMReconciler(),
    )

    assert result.halted_by is None
    assert result.observations_written == 8
    artifact = result.export
    assert artifact is not None
    assert artifact.schema_version == "1.0"

    categories_exported = {p.category for p in artifact.parts}
    assert categories_exported == {"cpu", "motherboard", "gpu", "storage", "ram", "psu", "case", "cooler"}


def test_full_catalog_no_blob_leak(db: Database) -> None:
    """engine_fields must not contain attributes keys in any category."""
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    result = run_batch(
        config=Config(),
        db=db,
        adapters=_build_all_adapters(),
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(same=False),
        llm_reconciler=MockLLMReconciler(),
    )

    for part in result.export.parts:
        # attributes field must only appear in display, never in engine_fields
        assert "attributes" not in part.engine_fields


def test_full_catalog_deterministic(db: Database) -> None:
    """Same inputs → byte-identical JSON on two calls."""
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    run_batch(
        config=Config(),
        db=db,
        adapters=_build_all_adapters(),
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(same=False),
        llm_reconciler=MockLLMReconciler(),
    )

    ts = "2026-01-01T00:00:00+00:00"
    assert export_to_json(db, generated_at=ts) == export_to_json(db, generated_at=ts)


def test_full_catalog_network_guard(db: Database) -> None:
    """Entire 8-category pipeline must not touch the network."""
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    result = run_batch(
        config=Config(),
        db=db,
        adapters=_build_all_adapters(),
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(same=False),
        llm_reconciler=MockLLMReconciler(),
    )
    assert result.observations_written == 8  # completed without raising network error


# ── Cross-category ER: GPU dedup ──────────────────────────────────────────────

def test_cross_category_gpu_same_part_merges(db: Database) -> None:
    """Two GPU observations from different sources with identical name → merged into one part."""
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    gpu_data = [
        {"name": "NVIDIA GeForce RTX 4090", "tdp_watts": 450, "length_mm": 336},
    ]
    # Two sources with same part name — adapter 1 and adapter 2
    class _GPUSrc2(GPUAdapter):
        source_name: str = "gpu-structured-2"

    adapter1 = GPUAdapter(gpu_data)
    adapter2 = _GPUSrc2(gpu_data)

    # Embeddings: same name → identical vector → cosine_sim = 1.0 → above threshold
    emb_map = {"NVIDIA GeForce RTX 4090": [1.0, 0.0, 0.0]}

    result = run_batch(
        config=Config(match_threshold=0.85),
        db=db,
        adapters=[adapter1, adapter2],
        embedding_client=MockEmbeddingClient(embeddings=emb_map),
        llm_match_client=MockLLMMatchClient(same=True, confidence=0.95),
        llm_reconciler=MockLLMReconciler(),
    )

    # Two observations ingested, but one merged part exported
    assert result.observations_written == 2
    gpu_parts = [p for p in result.export.parts if p.category == "gpu"]
    assert len(gpu_parts) == 1, "Same-name GPU from two sources must merge into one part"


# ── Catastrophic-conflict invariant — table-driven across all categories ──────

@pytest.mark.parametrize("category,conflict_field,val_a,val_b,base_fields", [
    (
        "cpu", "socket", "AM5", "LGA1700",
        {"tdp_watts": 65},
    ),
    (
        "gpu", "tdp_watts", 350, 450,
        {},
    ),
    (
        "ram", "ddr_generation", "DDR4", "DDR5",
        {"speed_mhz": 6000, "module_count": 2, "capacity_gb": 32},
    ),
    (
        "psu", "wattage", 850, 1000,
        {},
    ),
    (
        "case", "form_factors_supported", ["ATX", "mATX"], ["ATX", "ITX"],
        {},
    ),
    (
        "storage", "interface", "M.2 NVMe", "SATA",
        {"form_factor": "M.2 2280"},
    ),
    (
        "motherboard", "socket", "AM5", "LGA1700",
        {"ram_type": "DDR5", "form_factor": "ATX", "memory_slots": 4, "m2_slots": 3, "sata_ports": 6},
    ),
])
def test_catastrophic_conflict_withheld_per_category(
    db: Database,
    category: str,
    conflict_field: str,
    val_a: Any,
    val_b: Any,
    base_fields: dict[str, Any],
) -> None:
    """Per-category: seeded catastrophic conflict → review-queue entry + withheld from export."""
    from tests.conftest import MockLLMReconciler

    obs_a = _make_obs_row(
        category, f"{category.upper()} Part Alpha", "src-a",
        {conflict_field: val_a, **base_fields},
    )
    obs_b = _make_obs_row(
        category, f"{category.upper()} Part Alpha", "src-b",
        {conflict_field: val_b, **base_fields},
        method="llm-extracted",
        confidence=0.85,
    )
    db.save_observation(obs_a)
    db.save_observation(obs_b)

    group = ObservationGroup(observations=[obs_a, obs_b], merge_scores=[0.95])
    part_id = _new_id()
    part_data, has_conflict = reconcile_group(db, group, MockLLMReconciler(), part_id=part_id)
    db.save_part(part_id, category, part_data, has_conflict=has_conflict)

    # Invariant 1: flagged as catastrophic
    assert has_conflict, f"[{category}/{conflict_field}] must be flagged catastrophic"

    # Invariant 2: review queue entry created
    queue = db.get_pending_reviews(queue_type="catastrophic_conflict")
    assert len(queue) >= 1, f"[{category}/{conflict_field}] must create review-queue entry"

    # Invariant 3: withheld from export
    artifact = build_export(db)
    parts_in_export = [p for p in artifact.parts if p.category == category]
    assert len(parts_in_export) == 0, (
        f"[{category}/{conflict_field}] conflicted part must be withheld from export"
    )


# ── Non-catastrophic uncertainty → verify status ──────────────────────────────

def test_non_catastrophic_uncertainty_exports_verify_status(db: Database) -> None:
    """Cooler height_mm with low-confidence LLM extraction → exports with 'verify' status."""
    from tests.conftest import MockLLMReconciler

    obs = _make_obs_row(
        "cooler", "Noctua NH-D15", "cooler-llm",
        {"height_mm": 165},
        method="llm-extracted",
        confidence=0.60,  # below default field_trust_threshold of 0.80
    )
    db.save_observation(obs)

    group = ObservationGroup(observations=[obs], merge_scores=[])
    part_id = _new_id()
    part_data, has_conflict = reconcile_group(db, group, MockLLMReconciler(), part_id=part_id)
    db.save_part(part_id, "cooler", part_data, has_conflict=False)

    artifact = build_export(db, field_trust_threshold=0.80)
    cooler_parts = [p for p in artifact.parts if p.category == "cooler"]
    assert len(cooler_parts) == 1
    height_field = cooler_parts[0].engine_fields.get("height_mm")
    assert height_field is not None
    assert height_field.verification_status == "verify"


def test_clearance_field_absent_tolerated_in_export(db: Database) -> None:
    """Case with no clearance fields still exports form_factors_supported without error."""
    from tests.conftest import MockLLMReconciler

    obs = _make_obs_row(
        "case", "Compact Mini Case", "case-llm",
        {"form_factors_supported": ["ITX"]},
        method="llm-extracted",
        confidence=0.85,
    )
    db.save_observation(obs)

    group = ObservationGroup(observations=[obs], merge_scores=[])
    part_id = _new_id()
    part_data, has_conflict = reconcile_group(db, group, MockLLMReconciler(), part_id=part_id)
    db.save_part(part_id, "case", part_data, has_conflict=False)

    artifact = build_export(db)
    case_parts = [p for p in artifact.parts if p.category == "case"]
    assert len(case_parts) == 1
    assert "form_factors_supported" in case_parts[0].engine_fields
    assert "max_gpu_length_mm" not in case_parts[0].engine_fields
    assert "max_cooler_height_mm" not in case_parts[0].engine_fields


# ── Cache hits across full catalog ────────────────────────────────────────────

def test_full_catalog_cache_hits_skip_work(db: Database) -> None:
    """Re-running identical adapters uses cache — no extra LLM calls for LLM adapters."""

    ram_extractor = _llm_extractor_ram(n=5)
    psu_extractor = _llm_extractor_psu(n=5)
    case_extractor = _llm_extractor_case(n=5)
    cooler_extractor = _llm_extractor_cooler(n=5)
    mb_extractor = _llm_extractor_mb(n=5)

    ram_text = "Corsair Vengeance DDR5-6000 32GB"
    psu_text = "Corsair RM1000x 1000W"
    case_text = "Fractal Design Torrent"
    cooler_text = "Noctua NH-D15"
    mb_text = "ASUS ROG STRIX X670E\nSocket: AM5"

    ram_adapter = RAMAdapter([ram_text], ram_extractor)
    psu_adapter = PSUAdapter([psu_text], psu_extractor)
    case_adapter = CaseAdapter([case_text], case_extractor)
    cooler_adapter = CoolerAdapter([cooler_text], cooler_extractor)
    mb_adapter = MotherboardAdapter([mb_text], mb_extractor)

    # First fetch — calls LLM
    ram_adapter.fetch()
    psu_adapter.fetch()
    case_adapter.fetch()
    cooler_adapter.fetch()
    mb_adapter.fetch()

    calls_after_first = (
        ram_extractor.call_count + psu_extractor.call_count
        + case_extractor.call_count + cooler_extractor.call_count
        + mb_extractor.call_count
    )

    # Second fetch — cache hit, zero LLM calls
    ram_adapter.fetch()
    psu_adapter.fetch()
    case_adapter.fetch()
    cooler_adapter.fetch()
    mb_adapter.fetch()

    calls_after_second = (
        ram_extractor.call_count + psu_extractor.call_count
        + case_extractor.call_count + cooler_extractor.call_count
        + mb_extractor.call_count
    )

    assert calls_after_first == calls_after_second, "Cache hit must make zero LLM calls"


# ── Caps halt the full run ────────────────────────────────────────────────────

def test_full_catalog_parts_cap_halts(db: Database) -> None:
    """max_parts_per_run=0 halts before any group is reconciled."""
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    cfg = Config(max_parts_per_run=0, max_llm_calls_per_run=9999, max_budget_per_run=9999.0)
    result = run_batch(
        config=cfg,
        db=db,
        adapters=_build_all_adapters(),
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(same=False),
        llm_reconciler=MockLLMReconciler(),
    )
    assert result.halted_by == "max_parts_per_run"
