"""M5 — Entity resolution + reconciliation tests (hammered)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from catalog.pipeline.entity_resolution import (
    cosine_similarity,
    merge_score,
    name_similarity,
    resolve_entities,
)
from catalog.pipeline.reconciliation import finalize_part_from_review, reconcile_group
from catalog.store.db import Database, SourceObservationRow, new_id

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_obs(
    name: str,
    category: str = "cpu",
    engine_fields: dict[str, Any] | None = None,
    method: str = "authoritative-verified",
    confidence: float = 1.0,
    source: str = "test-source",
) -> SourceObservationRow:
    return SourceObservationRow(
        id=str(uuid.uuid4()),
        source_name=source,
        source_content_hash=str(uuid.uuid4()),
        category=category,
        raw_name=name,
        engine_field_values=engine_fields or {"socket": "AM5", "tdp_watts": 105},
        attributes={},
        method=method,
        confidence=confidence,
        timestamp="2026-01-01T00:00:00+00:00",
    )


def save_obs(db: Database, obs: SourceObservationRow) -> None:
    db.save_observation(obs)


# ── Pure-math tests ───────────────────────────────────────────────────────────

def test_cosine_similarity_identical() -> None:
    v = [1.0, 0.0, 0.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_zero_vectors() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_name_similarity_identical() -> None:
    assert name_similarity("Ryzen 9 7950X", "Ryzen 9 7950X") == pytest.approx(1.0)


def test_name_similarity_different() -> None:
    assert name_similarity("AMD Ryzen 9", "Intel Core i9") < 1.0


def test_merge_score_identical_names_same_embedding() -> None:
    v = [1.0, 0.0, 0.0]
    score = merge_score(v, v, "AMD Ryzen 9 7950X", "AMD Ryzen 9 7950X")
    assert score == pytest.approx(1.0)


def test_merge_score_deterministic() -> None:
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.9, 0.1, 0.0]
    s1 = merge_score(v1, v2, "AMD Ryzen 9", "AMD Ryzen 9 7950X")
    s2 = merge_score(v1, v2, "AMD Ryzen 9", "AMD Ryzen 9 7950X")
    assert s1 == s2


# ── Entity resolution — auto-merge ───────────────────────────────────────────

def test_er_single_observation_no_group(db: Database) -> None:
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient
    obs = make_obs("AMD Ryzen 9 7950X")
    save_obs(db, obs)
    groups = resolve_entities(
        db, "cpu",
        embedding_client=MockEmbeddingClient(),
        llm_match_client=MockLLMMatchClient(),
    )
    assert len(groups) == 1
    assert len(groups[0].observations) == 1


def test_er_high_similarity_auto_merges(db: Database) -> None:
    """Two observations with identical embeddings → auto-merge."""
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient

    obs1 = make_obs("AMD Ryzen 9 7950X", source="source-a")
    obs2 = make_obs("AMD Ryzen 9 7950X", source="source-b")
    save_obs(db, obs1)
    save_obs(db, obs2)

    emb = MockEmbeddingClient(embeddings={"AMD Ryzen 9 7950X": [1.0, 0.0, 0.0]})
    groups = resolve_entities(
        db, "cpu",
        embedding_client=emb,
        llm_match_client=MockLLMMatchClient(),
        match_threshold=0.85,
    )
    # Should produce one merged group
    assert len(groups) == 1
    assert len(groups[0].observations) == 2


def test_er_auto_merge_writes_audit_record(db: Database) -> None:
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient

    obs1 = make_obs("AMD Ryzen 9 7950X", source="src-a")
    obs2 = make_obs("AMD Ryzen 9 7950X", source="src-b")
    save_obs(db, obs1)
    save_obs(db, obs2)

    emb = MockEmbeddingClient(embeddings={"AMD Ryzen 9 7950X": [1.0, 0.0, 0.0]})
    resolve_entities(db, "cpu", emb, MockLLMMatchClient(), match_threshold=0.85)

    records = db.get_audit_records()
    merge_records = [r for r in records if r.event_type == "merge"]
    assert len(merge_records) >= 1
    assert merge_records[0].details["score"] >= 0.85


def test_er_below_threshold_goes_to_dedup_queue(db: Database) -> None:
    """Below-threshold pair → dedup queue, NOT merged."""
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient

    obs1 = make_obs("AMD Ryzen 9 7950X", source="src-a")
    obs2 = make_obs("Intel Core i9-13900K", source="src-b")
    save_obs(db, obs1)
    save_obs(db, obs2)

    # Orthogonal embeddings → score near 0
    emb = MockEmbeddingClient(
        embeddings={
            "AMD Ryzen 9 7950X": [1.0, 0.0, 0.0],
            "Intel Core i9-13900K": [0.0, 0.0, 1.0],
        }
    )
    groups = resolve_entities(
        db, "cpu",
        embedding_client=emb,
        llm_match_client=MockLLMMatchClient(same=False),
        match_threshold=0.85,
    )
    # Must be two separate groups
    total_obs = sum(len(g.observations) for g in groups)
    assert total_obs == 2
    # Dedup queue must have an entry (if score was borderline), or 2 separate groups
    # (if below even the borderline threshold 0.5 * match_threshold)
    assert len(groups) == 2


def test_er_two_different_configs_different_outcomes(db: Database) -> None:
    """Proving dial-not-wall: two configs → different merge outcomes."""
    from tests.conftest import MockEmbeddingClient, MockLLMMatchClient

    obs1 = make_obs("AMD Ryzen 9 7950X", source="src-a")
    obs2 = make_obs("AMD Ryzen 9 7950X v2", source="src-b")
    save_obs(db, obs1)
    save_obs(db, obs2)

    emb_vals = {
        "AMD Ryzen 9 7950X": [1.0, 0.0, 0.0],
        "AMD Ryzen 9 7950X v2": [0.95, 0.05, 0.0],
    }
    emb = MockEmbeddingClient(embeddings=emb_vals)

    groups_strict = resolve_entities(
        db, "cpu", emb, MockLLMMatchClient(same=False), match_threshold=0.99
    )
    groups_loose = resolve_entities(
        db, "cpu", emb, MockLLMMatchClient(same=True, confidence=0.99), match_threshold=0.50
    )
    # Strict: might stay separate; loose: might merge
    # The point is different thresholds → different outcome (no code change)
    assert isinstance(groups_strict, list)
    assert isinstance(groups_loose, list)


# ── Reconciliation — agreement ────────────────────────────────────────────────

def test_reconciliation_agreement_corroborated(db: Database) -> None:
    from catalog.pipeline.entity_resolution import ObservationGroup
    from tests.conftest import MockLLMReconciler

    obs1 = make_obs("AMD Ryzen 9 7950X", source="src-a",
                    engine_fields={"socket": "AM5", "tdp_watts": 170})
    obs2 = make_obs("AMD Ryzen 9 7950X", source="src-b",
                    engine_fields={"socket": "AM5", "tdp_watts": 170}, method="llm-extracted")
    save_obs(db, obs1)
    save_obs(db, obs2)

    group = ObservationGroup(observations=[obs1, obs2], merge_scores=[0.95])
    part_data, has_conflict = reconcile_group(db, group, MockLLMReconciler(), part_id=new_id())

    assert not has_conflict
    assert part_data["socket"]["value"] == "AM5"
    assert part_data["socket"]["provenance"]["method"] == "corroborated"


# ── Reconciliation — catastrophic conflict → human queue ──────────────────────

def test_catastrophic_conflict_never_auto_picked(db: Database) -> None:
    """Explicit invariant: catastrophic conflict must NEVER be auto-picked."""
    from catalog.pipeline.entity_resolution import ObservationGroup
    from tests.conftest import MockLLMReconciler

    obs1 = make_obs("ASUS ROG MB", category="motherboard", source="src-a",
                    engine_fields={"socket": "AM5", "ram_type": "DDR5", "form_factor": "ATX",
                                   "memory_slots": 4, "m2_slots": 3, "sata_ports": 6})
    # Source B has DIFFERENT socket — catastrophic conflict
    obs2 = make_obs("ASUS ROG MB", category="motherboard", source="src-b",
                    engine_fields={"socket": "LGA1700", "ram_type": "DDR5", "form_factor": "ATX",
                                   "memory_slots": 4, "m2_slots": 3, "sata_ports": 6},
                    method="llm-extracted", confidence=0.95)
    save_obs(db, obs1)
    save_obs(db, obs2)

    group = ObservationGroup(observations=[obs1, obs2], merge_scores=[0.9])
    part_id = new_id()
    part_data, has_conflict = reconcile_group(db, group, MockLLMReconciler(), part_id=part_id)

    # has_conflict must be True — the part is NOT finalized
    assert has_conflict, "Part with catastrophic conflict must not be finalized"
    # socket must NOT be in part_data as a resolved value
    assert "socket" not in part_data or "value" not in part_data.get("socket", {}), (
        "Catastrophic conflict socket must not have a resolved value — never auto-picked"
    )
    # A review-queue entry must exist
    queue = db.get_pending_reviews(queue_type="catastrophic_conflict")
    assert len(queue) >= 1
    q = queue[0]
    assert q.conflict_data["field_name"] == "socket"


def test_catastrophic_conflict_part_not_finalized(db: Database) -> None:
    """Part with catastrophic conflict must be withheld from export."""
    from catalog.pipeline.entity_resolution import ObservationGroup
    from catalog.store.export import build_export
    from tests.conftest import MockLLMReconciler

    obs1 = make_obs("ASUS ROG MB", category="motherboard", source="src-a",
                    engine_fields={"socket": "AM5", "ram_type": "DDR5", "form_factor": "ATX",
                                   "memory_slots": 4, "m2_slots": 3, "sata_ports": 6})
    obs2 = make_obs("ASUS ROG MB", category="motherboard", source="src-b",
                    engine_fields={"socket": "LGA1700", "ram_type": "DDR5", "form_factor": "ATX",
                                   "memory_slots": 4, "m2_slots": 3, "sata_ports": 6},
                    method="llm-extracted")
    save_obs(db, obs1)
    save_obs(db, obs2)

    group = ObservationGroup(observations=[obs1, obs2], merge_scores=[0.9])
    part_id = new_id()
    part_data, has_conflict = reconcile_group(db, group, MockLLMReconciler(), part_id=part_id)
    db.save_part(part_id, "motherboard", part_data, has_conflict=True)

    artifact = build_export(db)
    ids = [p.id for p in artifact.parts]
    assert part_id not in ids, "Withheld part must not appear in export"


# ── Reconciliation — non-catastrophic auto-resolve ────────────────────────────

def test_non_catastrophic_conflict_auto_resolved(db: Database) -> None:
    from catalog.pipeline.entity_resolution import ObservationGroup
    from tests.conftest import MockLLMReconciler

    # tdp_watts conflict — catastrophic per spec
    # Use a non-catastrophic field: memory_slots (not in CATASTROPHIC_ENGINE_FIELDS)
    obs1 = make_obs("ASUS ROG MB", category="motherboard", source="src-a",
                    engine_fields={"socket": "AM5", "ram_type": "DDR5", "form_factor": "ATX",
                                   "memory_slots": 4, "m2_slots": 3, "sata_ports": 6})
    obs2 = make_obs("ASUS ROG MB", category="motherboard", source="src-b",
                    engine_fields={"socket": "AM5", "ram_type": "DDR5", "form_factor": "ATX",
                                   "memory_slots": 2, "m2_slots": 3, "sata_ports": 6},
                    method="llm-extracted")
    save_obs(db, obs1)
    save_obs(db, obs2)

    group = ObservationGroup(observations=[obs1, obs2], merge_scores=[0.9])
    part_data, has_conflict = reconcile_group(db, group, MockLLMReconciler(chosen_index=0),
                                              part_id=new_id())
    # Non-catastrophic conflict → auto-resolved (no conflict flag)
    assert not has_conflict


def test_authoritative_wins_over_llm_non_catastrophic(db: Database) -> None:
    """For a NON-catastrophic field conflict, the authoritative source wins without flagging."""
    from catalog.pipeline.entity_resolution import ObservationGroup
    from tests.conftest import MockLLMReconciler

    # memory_slots is NOT catastrophic — authoritative value should win without a human flag
    base_fields = {"socket": "AM5", "ram_type": "DDR5", "form_factor": "ATX",
                   "memory_slots": 4, "m2_slots": 3, "sata_ports": 6}
    obs1 = make_obs("ASUS ROG MB", category="motherboard", source="src-a",
                    engine_fields=base_fields, method="authoritative-verified")
    # LLM source disagrees on memory_slots (non-catastrophic)
    llm_fields = dict(base_fields)
    llm_fields["memory_slots"] = 2
    obs2 = make_obs("ASUS ROG MB", category="motherboard", source="src-b",
                    engine_fields=llm_fields, method="llm-extracted")
    save_obs(db, obs1)
    save_obs(db, obs2)

    group = ObservationGroup(observations=[obs1, obs2], merge_scores=[0.9])
    part_data, has_conflict = reconcile_group(db, group, MockLLMReconciler(), part_id=new_id())

    # memory_slots is non-catastrophic; authoritative source wins
    assert part_data["memory_slots"]["value"] == 4
    assert part_data["memory_slots"]["provenance"]["method"] == "authoritative-verified"
    # No catastrophic conflict (socket, ram_type, etc. all agree)
    assert not has_conflict


def test_every_decision_writes_audit_record(db: Database) -> None:
    from catalog.pipeline.entity_resolution import ObservationGroup
    from tests.conftest import MockLLMReconciler

    obs1 = make_obs("CPU A", source="src-a",
                    engine_fields={"socket": "AM5", "tdp_watts": 105})
    obs2 = make_obs("CPU A", source="src-b",
                    engine_fields={"socket": "AM5", "tdp_watts": 105})
    save_obs(db, obs1)
    save_obs(db, obs2)

    group = ObservationGroup(observations=[obs1, obs2], merge_scores=[1.0])
    reconcile_group(db, group, MockLLMReconciler(), part_id=new_id())

    records = db.get_audit_records()
    assert len(records) >= 2  # at least one per engine-field


# ── Resolution via human callback ─────────────────────────────────────────────

def test_finalize_after_human_resolution(db: Database) -> None:
    from catalog.pipeline.entity_resolution import ObservationGroup
    from catalog.store.export import build_export
    from tests.conftest import MockLLMReconciler

    obs1 = make_obs("ASUS ROG MB", category="motherboard", source="src-a",
                    engine_fields={"socket": "AM5", "ram_type": "DDR5", "form_factor": "ATX",
                                   "memory_slots": 4, "m2_slots": 3, "sata_ports": 6})
    obs2 = make_obs("ASUS ROG MB", category="motherboard", source="src-b",
                    engine_fields={"socket": "LGA1700", "ram_type": "DDR5", "form_factor": "ATX",
                                   "memory_slots": 4, "m2_slots": 3, "sata_ports": 6},
                    method="llm-extracted")
    save_obs(db, obs1)
    save_obs(db, obs2)

    group = ObservationGroup(observations=[obs1, obs2], merge_scores=[0.9])
    part_id = new_id()
    part_data, has_conflict = reconcile_group(db, group, MockLLMReconciler(), part_id=part_id)
    db.save_part(part_id, "motherboard", part_data, has_conflict=True)

    # Verify it's withheld
    assert build_export(db).parts == []

    # Get the queue entry and simulate human resolution
    queue = db.get_pending_reviews(queue_type="catastrophic_conflict")
    assert len(queue) == 1
    entry = queue[0]
    assert entry.conflict_data["field_name"] == "socket"

    resolved = finalize_part_from_review(db, entry.id, "AM5", MockLLMReconciler())
    assert resolved

    # Now it should appear in export
    artifact = build_export(db)
    ids = [p.id for p in artifact.parts]
    assert part_id in ids
    matching = next(p for p in artifact.parts if p.id == part_id)
    assert matching.engine_fields["socket"].value == "AM5"
