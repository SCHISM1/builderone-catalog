"""Entity resolution — which observations are the same part?

Steps:
  1. Embedding-based blocking (mocked in CI).
  2. Cosine + name similarity → deterministic merge score.
  3. Above match_threshold → auto-merge group.
  4. Below threshold → dedup queue entry.

All external calls (embeddings, LLM match) are injected via protocols.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol, runtime_checkable

from catalog.pipeline.audit import write_audit
from catalog.store.db import Database, ReviewQueueEntry, SourceObservationRow

# ── Protocols (injected; mocked in CI) ───────────────────────────────────────

@runtime_checkable
class EmbeddingClient(Protocol):
    """Returns a unit-norm embedding vector for each text."""

    call_count: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


@runtime_checkable
class LLMMatchClient(Protocol):
    """Asks the LLM whether two observations refer to the same part."""

    call_count: int

    def is_same_part(self, a: SourceObservationRow, b: SourceObservationRow) -> tuple[bool, float]:
        """Returns (is_same, confidence)."""
        ...


# ── Scoring ───────────────────────────────────────────────────────────────────

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def merge_score(emb1: list[float], emb2: list[float], name1: str, name2: str) -> float:
    """Deterministic score in [0, 1]. Same inputs → same output."""
    cos = cosine_similarity(emb1, emb2)
    name = name_similarity(name1, name2)
    return 0.7 * cos + 0.3 * name


# ── Groups ────────────────────────────────────────────────────────────────────

@dataclass
class ObservationGroup:
    """A set of observations resolved to refer to the same part."""

    observations: list[SourceObservationRow]
    merge_scores: list[float]  # scores used to form this group


# ── Main ER function ──────────────────────────────────────────────────────────

def resolve_entities(
    db: Database,
    category: str,
    embedding_client: EmbeddingClient,
    llm_match_client: LLMMatchClient,
    match_threshold: float = 0.85,
) -> list[ObservationGroup]:
    """Group observations (same category) into parts.

    Side effects:
    - Writes audit records for every merge and every dedup-queue flag.
    - Writes ReviewQueueEntry to DB for below-threshold pairs.
    """
    observations = db.get_observations_by_category(category)
    if not observations:
        return []

    if len(observations) == 1:
        return [ObservationGroup(observations=observations, merge_scores=[])]

    names = [o.raw_name for o in observations]
    embeddings = embedding_client.embed(names)

    # Union-find grouping
    parent = list(range(len(observations)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    scored_pairs: list[tuple[int, int, float]] = []
    for i in range(len(observations)):
        for j in range(i + 1, len(observations)):
            score = merge_score(embeddings[i], embeddings[j], names[i], names[j])
            scored_pairs.append((i, j, score))

    dedup_flagged: set[tuple[int, int]] = set()
    merge_scores_map: dict[tuple[int, int], float] = {}

    for i, j, score in scored_pairs:
        if score >= match_threshold:
            # High confidence — auto-merge (no LLM confirmation needed above threshold)
            union(i, j)
            merge_scores_map[(i, j)] = score
            obs_ids = [observations[i].id, observations[j].id]
            write_audit(
                db,
                event_type="merge",
                observation_ids=obs_ids,
                details={
                    "score": score,
                    "match_threshold": match_threshold,
                    "name_a": names[i],
                    "name_b": names[j],
                },
            )
        elif score > match_threshold * 0.5:
            # Borderline — consult LLM
            same, llm_conf = llm_match_client.is_same_part(observations[i], observations[j])
            if same and llm_conf >= match_threshold:
                union(i, j)
                merge_scores_map[(i, j)] = llm_conf
                write_audit(
                    db,
                    event_type="merge",
                    observation_ids=[observations[i].id, observations[j].id],
                    details={
                        "score": llm_conf,
                        "source": "llm_match",
                        "name_a": names[i],
                        "name_b": names[j],
                    },
                )
            else:
                # Ambiguous — flag to dedup queue
                pair_key = (i, j)
                if pair_key not in dedup_flagged:
                    dedup_flagged.add(pair_key)
                    entry = ReviewQueueEntry(
                        id=str(uuid.uuid4()),
                        queue_type="dedup",
                        category=category,
                        observation_ids=[observations[i].id, observations[j].id],
                        conflict_data={
                            "name_a": names[i],
                            "name_b": names[j],
                            "score": score,
                        },
                    )
                    db.enqueue_review(entry)
                    write_audit(
                        db,
                        event_type="flag",
                        observation_ids=[observations[i].id, observations[j].id],
                        details={
                            "reason": "below_threshold_dedup",
                            "score": score,
                            "queue_entry_id": entry.id,
                        },
                    )

    # Build groups from union-find
    groups_map: dict[int, list[SourceObservationRow]] = {}
    for idx, obs in enumerate(observations):
        root = find(idx)
        groups_map.setdefault(root, []).append(obs)

    result: list[ObservationGroup] = []
    for root, members in sorted(groups_map.items(), key=lambda kv: kv[0]):
        scores = [
            merge_scores_map.get((min(i, j), max(i, j)), 0.0)
            for i in range(len(observations))
            for j in range(i + 1, len(observations))
            if (observations[i] in members and observations[j] in members)
        ]
        result.append(ObservationGroup(observations=members, merge_scores=scores))

    return result
