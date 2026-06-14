"""Scheduled-not-looping batch entry point.

Runs ONE bounded cycle and exits — the systemd timer handles scheduling.
Caps are kill-switches: any cap hit halts cleanly and logs why.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from catalog.adapters.base import SourceAdapter, SourceObservation
from catalog.config import Config
from catalog.pipeline.entity_resolution import EmbeddingClient, LLMMatchClient, resolve_entities
from catalog.pipeline.reconciliation import LLMReconciler, reconcile_group
from catalog.store.db import Database, SourceObservationRow
from catalog.store.export import build_export


@dataclass
class BatchResult:
    observations_written: int = 0
    parts_finalized: int = 0
    parts_withheld: int = 0
    llm_calls_used: int = 0
    budget_used: float = 0.0
    halted_by: str | None = None
    export: Any = None  # CatalogExport | None


@dataclass
class _Counters:
    llm_calls: int = 0
    budget_usd: float = 0.0
    parts_processed: int = 0

    def charge_llm(self, n: int = 1, cost_usd: float = 0.002) -> None:
        self.llm_calls += n
        self.budget_usd += cost_usd * n


def run_batch(
    config: Config,
    db: Database,
    adapters: list[SourceAdapter],
    embedding_client: EmbeddingClient,
    llm_match_client: LLMMatchClient,
    llm_reconciler: LLMReconciler,
    send_telegram: bool = False,
    telegram_client: Any = None,
) -> BatchResult:
    """Run a single bounded batch cycle.

    Pipeline:
    1. Run each adapter → write source_observations.
    2. Entity resolution per category → groups.
    3. Reconciliation per group → canonical part or conflict flag.
    4. Deliver pending review queue to Telegram (if requested).
    5. Export artifact.
    """
    result = BatchResult()
    counters = _Counters()

    # ── Step 1: Ingest ────────────────────────────────────────────────────────
    all_observations: list[SourceObservation] = []
    for adapter in adapters:
        for obs in adapter.fetch():
            all_observations.append(obs)

    for obs in all_observations:
        row = SourceObservationRow(
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
        db.save_observation(row)
        result.observations_written += 1

    # ── Step 2: Entity resolution ─────────────────────────────────────────────
    categories = list({obs.category for obs in all_observations})
    all_groups = []
    for cat in sorted(categories):
        counters.charge_llm(n=1, cost_usd=0.0001)  # embedding call
        if counters.llm_calls > config.max_llm_calls_per_run:
            result.halted_by = "max_llm_calls_per_run"
            _log_halt(result)
            return result
        if counters.budget_usd > config.max_budget_per_run:
            result.halted_by = "max_budget_per_run"
            _log_halt(result)
            return result

        groups = resolve_entities(
            db, cat, embedding_client, llm_match_client,
            match_threshold=config.match_threshold,
        )
        all_groups.extend(groups)

    # ── Step 3: Reconciliation ────────────────────────────────────────────────
    for group in all_groups:
        # Parts cap: pre-check before processing the next group
        if counters.parts_processed >= config.max_parts_per_run:
            result.halted_by = "max_parts_per_run"
            _log_halt(result)
            return result

        counters.charge_llm(n=1, cost_usd=0.005)
        if counters.llm_calls > config.max_llm_calls_per_run:
            result.halted_by = "max_llm_calls_per_run"
            _log_halt(result)
            return result
        if counters.budget_usd > config.max_budget_per_run:
            result.halted_by = "max_budget_per_run"
            _log_halt(result)
            return result

        part_id = str(uuid.uuid4())
        part_data, has_conflict = reconcile_group(
            db, group, llm_reconciler,
            field_trust_threshold=config.field_trust_threshold,
            part_id=part_id,
        )
        db.save_part(part_id, part_data.get("category", ""), part_data, has_conflict)
        counters.parts_processed += 1

        if has_conflict:
            result.parts_withheld += 1
        else:
            result.parts_finalized += 1

    # ── Step 4: Deliver review queue to Telegram (if requested) ──────────────
    if send_telegram and telegram_client is not None and config.telegram_chat_id:
        from catalog.review.queue import deliver_review_queue
        deliver_review_queue(db, telegram_client, config.telegram_chat_id)

    # ── Step 5: Export ────────────────────────────────────────────────────────
    result.llm_calls_used = counters.llm_calls
    result.budget_used = counters.budget_usd
    result.export = build_export(db, field_trust_threshold=config.field_trust_threshold)

    return result


def _log_halt(result: BatchResult) -> None:
    print(f"[catalog] Batch halted: cap reached — {result.halted_by}")
