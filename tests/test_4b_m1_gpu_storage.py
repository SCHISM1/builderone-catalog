"""4b M1 — GPU + storage clean-source adapter tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from catalog.adapters import GPUAdapter, SourceAdapter, StorageAdapter
from catalog.store.db import Database, SourceObservationRow

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── GPU adapter ───────────────────────────────────────────────────────────────

@pytest.fixture
def gpu_fixture() -> list[dict[str, Any]]:
    with open(FIXTURE_DIR / "gpu_source.json") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def test_gpu_adapter_protocol(gpu_fixture: list[dict[str, Any]]) -> None:
    assert isinstance(GPUAdapter(gpu_fixture), SourceAdapter)


def test_gpu_adapter_produces_observations(gpu_fixture: list[dict[str, Any]]) -> None:
    obs_list = GPUAdapter(gpu_fixture).fetch()
    assert len(obs_list) == 3


def test_gpu_adapter_category(gpu_fixture: list[dict[str, Any]]) -> None:
    for obs in GPUAdapter(gpu_fixture).fetch():
        assert obs.category == "gpu"


def test_gpu_adapter_method_authoritative(gpu_fixture: list[dict[str, Any]]) -> None:
    for obs in GPUAdapter(gpu_fixture).fetch():
        assert obs.method == "authoritative-verified"
        assert obs.confidence == 1.0


def test_gpu_adapter_tdp_watts_populated(gpu_fixture: list[dict[str, Any]]) -> None:
    obs_list = GPUAdapter(gpu_fixture).fetch()
    rtx_4090 = next(o for o in obs_list if "4090" in o.raw_name)
    assert rtx_4090.engine_field_values["tdp_watts"] == 450


def test_gpu_adapter_length_mm_when_present(gpu_fixture: list[dict[str, Any]]) -> None:
    obs_list = GPUAdapter(gpu_fixture).fetch()
    rtx_4090 = next(o for o in obs_list if "4090" in o.raw_name)
    assert rtx_4090.engine_field_values["length_mm"] == 336


def test_gpu_adapter_length_mm_absent_is_tolerated(gpu_fixture: list[dict[str, Any]]) -> None:
    """GPU with no length_mm in fixture → field absent from engine_field_values, not an error."""
    obs_list = GPUAdapter(gpu_fixture).fetch()
    rtx_4060ti = next(o for o in obs_list if "4060" in o.raw_name)
    assert "length_mm" not in rtx_4060ti.engine_field_values


def test_gpu_adapter_cache_hit(gpu_fixture: list[dict[str, Any]]) -> None:
    adapter = GPUAdapter(gpu_fixture)
    obs1 = adapter.fetch()
    obs2 = adapter.fetch()
    assert obs1 is obs2, "Cache hit must return the same list object"


def test_gpu_adapter_writes_to_db(db: Database, gpu_fixture: list[dict[str, Any]]) -> None:
    adapter = GPUAdapter(gpu_fixture)
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
    rows = db.get_observations_by_category("gpu")
    assert len(rows) == 3


def test_gpu_adapter_extra_fields_in_attributes(gpu_fixture: list[dict[str, Any]]) -> None:
    obs_list = GPUAdapter(gpu_fixture).fetch()
    rtx_4090 = next(o for o in obs_list if "4090" in o.raw_name)
    assert "memory_gb" in rtx_4090.attributes
    assert "tdp_watts" not in rtx_4090.attributes
    assert "length_mm" not in rtx_4090.attributes


# ── Storage adapter ───────────────────────────────────────────────────────────

@pytest.fixture
def storage_fixture() -> list[dict[str, Any]]:
    with open(FIXTURE_DIR / "storage_source.json") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def test_storage_adapter_protocol(storage_fixture: list[dict[str, Any]]) -> None:
    assert isinstance(StorageAdapter(storage_fixture), SourceAdapter)


def test_storage_adapter_produces_observations(storage_fixture: list[dict[str, Any]]) -> None:
    obs_list = StorageAdapter(storage_fixture).fetch()
    assert len(obs_list) == 3


def test_storage_adapter_category(storage_fixture: list[dict[str, Any]]) -> None:
    for obs in StorageAdapter(storage_fixture).fetch():
        assert obs.category == "storage"


def test_storage_adapter_method_authoritative(storage_fixture: list[dict[str, Any]]) -> None:
    for obs in StorageAdapter(storage_fixture).fetch():
        assert obs.method == "authoritative-verified"
        assert obs.confidence == 1.0


def test_storage_adapter_interface_populated(storage_fixture: list[dict[str, Any]]) -> None:
    obs_list = StorageAdapter(storage_fixture).fetch()
    samsung = next(o for o in obs_list if "Samsung" in o.raw_name)
    assert samsung.engine_field_values["interface"] == "M.2 NVMe"
    wd = next(o for o in obs_list if "Western" in o.raw_name)
    assert wd.engine_field_values["interface"] == "SATA"


def test_storage_adapter_form_factor_populated(storage_fixture: list[dict[str, Any]]) -> None:
    obs_list = StorageAdapter(storage_fixture).fetch()
    samsung = next(o for o in obs_list if "Samsung" in o.raw_name)
    assert samsung.engine_field_values["form_factor"] == "M.2 2280"


def test_storage_adapter_cache_hit(storage_fixture: list[dict[str, Any]]) -> None:
    adapter = StorageAdapter(storage_fixture)
    obs1 = adapter.fetch()
    obs2 = adapter.fetch()
    assert obs1 is obs2


def test_storage_adapter_writes_to_db(db: Database, storage_fixture: list[dict[str, Any]]) -> None:
    adapter = StorageAdapter(storage_fixture)
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
    rows = db.get_observations_by_category("storage")
    assert len(rows) == 3


def test_storage_adapter_extra_fields_in_attributes(storage_fixture: list[dict[str, Any]]) -> None:
    obs_list = StorageAdapter(storage_fixture).fetch()
    samsung = next(o for o in obs_list if "Samsung" in o.raw_name)
    assert "read_mb_s" in samsung.attributes
    assert "interface" not in samsung.attributes
    assert "form_factor" not in samsung.attributes
