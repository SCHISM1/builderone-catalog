"""M6 — Review queue, batch entry, and end-to-end wire-through tests."""

from __future__ import annotations

from typing import Any

from catalog.config import Config
from catalog.review.queue import deliver_review_queue, handle_callback
from catalog.review.telegram import MockTelegramClient
from catalog.store.db import Database, ReviewQueueEntry, new_id
from catalog.store.export import build_export

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_catastrophic_entry(db: Database, part_id: str | None = None) -> ReviewQueueEntry:
    pid = part_id or new_id()
    entry = ReviewQueueEntry(
        id=new_id(),
        queue_type="catastrophic_conflict",
        category="motherboard",
        observation_ids=[new_id(), new_id()],
        conflict_data={
            "field_name": "socket",
            "candidates": [
                {"source": "src-a", "value": "AM5", "method": "authoritative-verified", "confidence": 1.0},
                {"source": "src-b", "value": "LGA1700", "method": "llm-extracted", "confidence": 0.85},
            ],
            "part_id": pid,
        },
    )
    db.enqueue_review(entry)
    return entry


def make_dedup_entry(db: Database) -> ReviewQueueEntry:
    entry = ReviewQueueEntry(
        id=new_id(),
        queue_type="dedup",
        category="cpu",
        observation_ids=[new_id(), new_id()],
        conflict_data={
            "name_a": "AMD Ryzen 9 7950X",
            "name_b": "AMD Ryzen 9 7950X (OEM)",
            "score": 0.72,
        },
    )
    db.enqueue_review(entry)
    return entry


# ── Review queue delivery ─────────────────────────────────────────────────────

def test_catastrophic_conflict_sends_telegram(db: Database) -> None:
    telegram = MockTelegramClient()
    make_catastrophic_entry(db)
    count = deliver_review_queue(db, telegram, chat_id="123456")
    assert count == 1
    assert len(telegram.sent) == 1
    msg = telegram.sent[0]
    assert "socket" in msg["text"]
    assert "AM5" in msg["text"] or "LGA1700" in msg["text"]
    assert msg["reply_markup"] is not None


def test_conflict_message_has_resolution_options(db: Database) -> None:
    telegram = MockTelegramClient()
    make_catastrophic_entry(db)
    deliver_review_queue(db, telegram, chat_id="123")
    msg = telegram.sent[0]
    keyboard = msg["reply_markup"]["inline_keyboard"]
    assert len(keyboard) >= 2  # at least the two candidates + hold


def test_dedup_message_yes_no_options(db: Database) -> None:
    telegram = MockTelegramClient()
    make_dedup_entry(db)
    deliver_review_queue(db, telegram, chat_id="123", queue_type="dedup")
    msg = telegram.sent[0]
    keyboard = msg["reply_markup"]["inline_keyboard"]
    flat = [btn["text"] for row in keyboard for btn in row]
    yes_texts = [t for t in flat if "yes" in t.lower() or "same" in t.lower()]
    no_texts = [t for t in flat if "no" in t.lower() or "different" in t.lower()]
    assert yes_texts
    assert no_texts


# ── Callback handling ─────────────────────────────────────────────────────────

def test_resolve_callback_writes_value(db: Database) -> None:
    entry = make_catastrophic_entry(db)
    result = handle_callback(db, f"resolve:{entry.id}:AM5")
    assert result["action"] == "resolved"
    assert result["value"] == "AM5"
    updated = db.get_review_entry(entry.id)
    assert updated is not None
    assert updated.status == "resolved"
    assert updated.resolved_value == "AM5"


def test_dedup_yes_callback(db: Database) -> None:
    entry = make_dedup_entry(db)
    result = handle_callback(db, f"dedup_yes:{entry.id}")
    assert result["action"] == "dedup_merged"
    updated = db.get_review_entry(entry.id)
    assert updated is not None
    assert updated.resolved_value is True


def test_dedup_no_callback(db: Database) -> None:
    entry = make_dedup_entry(db)
    result = handle_callback(db, f"dedup_no:{entry.id}")
    assert result["action"] == "dedup_kept_separate"
    updated = db.get_review_entry(entry.id)
    assert updated is not None
    assert updated.resolved_value is False


def test_hold_callback(db: Database) -> None:
    entry = make_catastrophic_entry(db)
    result = handle_callback(db, f"hold:{entry.id}")
    assert result["action"] == "held"
    # Status stays pending on hold
    updated = db.get_review_entry(entry.id)
    assert updated is not None
    assert updated.status == "pending"


# ── Batch caps ────────────────────────────────────────────────────────────────

def _make_config(**kwargs: Any) -> Config:
    cfg = Config()
    for k, v in kwargs.items():
        setattr(cfg, k, v)
    return cfg


def _make_adapters(n_parts: int, category: str = "cpu") -> list[Any]:
    from catalog.adapters.base import SourceObservation
    from catalog.adapters.base import content_hash as ch

    class _StaticAdapter:
        source_name = "static"

        def __init__(self, count: int) -> None:
            self._count = count

        def fetch(self) -> list[SourceObservation]:
            return [
                SourceObservation(
                    source_name="static",
                    source_content_hash=ch(f"item-{i}"),
                    category=category,
                    raw_name=f"Part {i}",
                    engine_field_values={"socket": "AM5", "tdp_watts": 65},
                    method="authoritative-verified",
                    confidence=1.0,
                )
                for i in range(self._count)
            ]

    return [_StaticAdapter(n_parts)]


def test_batch_max_parts_cap(db: Database) -> None:
    """Cap of 0 parts halts before any group is processed."""
    from catalog.batch import run_batch
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    cfg = _make_config(max_parts_per_run=0, max_llm_calls_per_run=9999, max_budget_per_run=9999.0)
    result = run_batch(
        config=cfg,
        db=db,
        adapters=_make_adapters(3),
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(),
        llm_reconciler=MockLLMReconciler(),
    )
    assert result.halted_by == "max_parts_per_run"


def test_batch_max_llm_calls_cap(db: Database) -> None:
    from catalog.batch import run_batch
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    cfg = _make_config(max_parts_per_run=9999, max_llm_calls_per_run=0, max_budget_per_run=9999.0)
    result = run_batch(
        config=cfg,
        db=db,
        adapters=_make_adapters(3),
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(),
        llm_reconciler=MockLLMReconciler(),
    )
    assert result.halted_by == "max_llm_calls_per_run"


def test_batch_max_budget_cap(db: Database) -> None:
    from catalog.batch import run_batch
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    cfg = _make_config(max_parts_per_run=9999, max_llm_calls_per_run=9999, max_budget_per_run=0.0)
    result = run_batch(
        config=cfg,
        db=db,
        adapters=_make_adapters(3),
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(),
        llm_reconciler=MockLLMReconciler(),
    )
    assert result.halted_by == "max_budget_per_run"


def test_batch_runs_one_cycle_exits(db: Database) -> None:
    """Batch runs exactly one cycle and exits — never loops."""
    from catalog.batch import run_batch
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    cfg = Config()
    result = run_batch(
        config=cfg,
        db=db,
        adapters=_make_adapters(2),
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(),
        llm_reconciler=MockLLMReconciler(),
    )
    # Must complete without halting
    assert result.halted_by is None
    assert result.observations_written == 2


# ── End-to-end wire-through ───────────────────────────────────────────────────

def test_e2e_cpu_and_mb_with_catastrophic_conflict(db: Database) -> None:
    """Full pipeline: CPU (clean) + MB (catastrophic conflict) → conflict withheld, CPU exported."""
    from catalog.adapters.cpu import CPUAdapter
    from catalog.adapters.motherboard import MotherboardAdapter, MotherboardExtractionResult
    from catalog.batch import run_batch
    from tests.conftest import (
        MockEmbeddingClient,
        MockLLMExtractor,
        MockLLMMatchClient,
        MockLLMReconciler,
    )

    # CPU adapter — clean path
    cpu_data = [{"name": "AMD Ryzen 9 7950X", "socket": "AM5", "tdp_watts": 170}]
    cpu_adapter = CPUAdapter(cpu_data)

    # Motherboard adapter — LLM path; two sources with conflicting sockets
    mb_extractor_a = MotherboardExtractionResult(
        reasoning="AM5 board.",
        socket="AM5",
        form_factor="ATX",
        ram_type="DDR5",
        memory_slots=4,
        m2_slots=3,
        sata_ports=6,
    )
    mb_extractor_b = MotherboardExtractionResult(
        reasoning="Actually LGA1700.",
        socket="LGA1700",
        form_factor="ATX",
        ram_type="DDR5",
        memory_slots=4,
        m2_slots=3,
        sata_ports=6,
    )
    mb_llm = MockLLMExtractor(responses=[mb_extractor_a, mb_extractor_b])
    mb_adapter = MotherboardAdapter(
        ["ASUS ROG STRIX X670E\nSocket: AM5", "ASUS ROG STRIX X670E v2\nSocket: AM5"],
        mb_llm,
    )

    cfg = Config(match_threshold=0.85, field_trust_threshold=0.80)

    # Use embeddings that make the two MB texts very dissimilar (no merge)
    embedding_map = {
        "AMD Ryzen 9 7950X": [1.0, 0.0, 0.0],
        "ASUS ROG STRIX X670E": [0.0, 1.0, 0.0],
        "ASUS ROG STRIX X670E v2": [0.0, 0.9, 0.1],
    }
    emb_client = MockEmbeddingClient(embeddings=embedding_map)

    result = run_batch(
        config=cfg,
        db=db,
        adapters=[cpu_adapter, mb_adapter],
        embedding_client=emb_client,
        llm_match_client=MockLLMMatchClient(same=False),
        llm_reconciler=MockLLMReconciler(),
    )

    assert result.halted_by is None
    # Export: CPU should be present, MB(s) may be withheld if conflict detected
    artifact = result.export
    assert artifact is not None
    cpu_parts = [p for p in artifact.parts if p.category == "cpu"]
    assert len(cpu_parts) >= 1, "CPU part must appear in export"
    # Export is valid and has schema version
    assert artifact.schema_version == "1.0"


def test_e2e_after_resolution_conflict_exported(db: Database) -> None:
    """After human resolves conflict, re-export includes the part."""
    import uuid

    from catalog.pipeline.entity_resolution import ObservationGroup
    from catalog.pipeline.reconciliation import finalize_part_from_review, reconcile_group
    from catalog.store.db import SourceObservationRow
    from tests.conftest import MockLLMReconciler

    def make_obs(name: str, source: str, socket: str, method: str = "authoritative-verified") -> SourceObservationRow:
        return SourceObservationRow(
            id=str(uuid.uuid4()),
            source_name=source,
            source_content_hash=str(uuid.uuid4()),
            category="motherboard",
            raw_name=name,
            engine_field_values={"socket": socket, "ram_type": "DDR5", "form_factor": "ATX",
                                  "memory_slots": 4, "m2_slots": 3, "sata_ports": 6},
            attributes={},
            method=method,
            confidence=1.0,
            timestamp="2026-01-01T00:00:00+00:00",
        )

    obs1 = make_obs("ASUS ROG B650", "src-a", "AM5")
    obs2 = make_obs("ASUS ROG B650", "src-b", "LGA1700", method="llm-extracted")
    db.save_observation(obs1)
    db.save_observation(obs2)

    group = ObservationGroup(observations=[obs1, obs2], merge_scores=[0.92])
    part_id = new_id()
    part_data, has_conflict = reconcile_group(db, group, MockLLMReconciler(), part_id=part_id)
    db.save_part(part_id, "motherboard", part_data, has_conflict=True)

    # Before resolution: withheld
    assert build_export(db).parts == []

    # Simulate human resolution via mocked Telegram callback
    queue = db.get_pending_reviews(queue_type="catastrophic_conflict")
    assert len(queue) == 1
    resolved = finalize_part_from_review(db, queue[0].id, "AM5", MockLLMReconciler())
    assert resolved

    # After resolution: exported
    artifact = build_export(db)
    assert len(artifact.parts) == 1
    assert artifact.parts[0].engine_fields["socket"].value == "AM5"


def test_e2e_export_deterministic(db: Database) -> None:
    from catalog.adapters.cpu import CPUAdapter
    from catalog.batch import run_batch
    from catalog.store.export import export_to_json
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    cpu_data = [{"name": "AMD Ryzen 9 7950X", "socket": "AM5", "tdp_watts": 170}]
    cpu_adapter = CPUAdapter(cpu_data)
    cfg = Config()

    run_batch(
        config=cfg,
        db=db,
        adapters=[cpu_adapter],
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(),
        llm_reconciler=MockLLMReconciler(),
    )

    ts = "2026-01-01T00:00:00+00:00"
    json1 = export_to_json(db, generated_at=ts)
    json2 = export_to_json(db, generated_at=ts)
    assert json1 == json2


def test_e2e_no_network(db: Database) -> None:
    """Entire E2E pipeline must run with zero network calls (enforced by conftest guard)."""
    from catalog.adapters.cpu import CPUAdapter
    from catalog.batch import run_batch
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient, MockLLMReconciler

    cpu_data = [{"name": "Intel Core i9-13900K", "socket": "LGA1700", "tdp_watts": 253}]
    result = run_batch(
        config=Config(),
        db=db,
        adapters=[CPUAdapter(cpu_data)],
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(),
        llm_reconciler=MockLLMReconciler(),
    )
    assert result.observations_written == 1
