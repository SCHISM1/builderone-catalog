"""Reconciliation — resolve a group of observations into one canonical part record.

Rules:
  - All sources agree → ``corroborated``, high confidence.
  - Conflict → check authoritative source first (authoritative wins).
  - Still conflicted + catastrophic field → flag to human (ReviewQueue); part withheld.
  - Still conflicted + non-catastrophic → LLM-first auto-resolve; ``verify`` if uncertain.
  - Every decision (resolve/flag) writes an audit record.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from catalog.models.shared import CATASTROPHIC_ENGINE_FIELDS
from catalog.pipeline.audit import write_audit
from catalog.pipeline.entity_resolution import ObservationGroup
from catalog.store.db import Database, ReviewQueueEntry, SourceObservationRow

# ── LLM reconciler protocol (injected; mocked in CI) ─────────────────────────

@runtime_checkable
class LLMReconciler(Protocol):
    """Ask the LLM to pick the most likely correct value from conflicting options."""

    call_count: int

    def reconcile_field(
        self,
        field_name: str,
        candidates: list[dict[str, Any]],
        context: str,
    ) -> tuple[Any, float]:
        """Returns (chosen_value, confidence)."""
        ...


# ── Helpers ───────────────────────────────────────────────────────────────────

def _most_common(values: list[Any]) -> Any:
    from collections import Counter
    return Counter(values).most_common(1)[0][0]


def _all_same(values: list[Any]) -> bool:
    return len(set(str(v) for v in values)) == 1


def _authoritative_value(
    field_name: str,
    obs_list: list[SourceObservationRow],
) -> Any | None:
    """Return the value from the first authoritative-verified observation, or None."""
    for obs in obs_list:
        if obs.method == "authoritative-verified" and field_name in obs.engine_field_values:
            return obs.engine_field_values[field_name]
    return None


# ── Core reconciliation ───────────────────────────────────────────────────────

def reconcile_group(
    db: Database,
    group: ObservationGroup,
    llm_reconciler: LLMReconciler,
    field_trust_threshold: float = 0.80,
    part_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Reconcile a group of observations into a canonical part dict.

    Returns ``(part_data, has_catastrophic_conflict)``.

    ``part_data`` is a plain dict matching the structure expected by
    ``Database.save_part()`` and ``export.build_export()``.
    """
    if part_id is None:
        part_id = str(uuid.uuid4())

    obs_list = group.observations
    obs_ids = [o.id for o in obs_list]

    # Collect all engine-field names across the group
    all_field_names: set[str] = set()
    for obs in obs_list:
        all_field_names.update(obs.engine_field_values.keys())

    # Use the first observation's name/category as the canonical name
    representative = obs_list[0]
    category = representative.category
    name = _best_name(obs_list)

    part_data: dict[str, Any] = {
        "id": part_id,
        "category": category,
        "name": name,
        "retailer_refs": {},
        "price_snapshot": None,
        "attributes": _merge_attributes(obs_list),
    }

    has_catastrophic_conflict = False

    for field_name in sorted(all_field_names):
        # Gather all values + their provenance
        candidates = [
            {
                "source": obs.source_name,
                "value": obs.engine_field_values[field_name],
                "method": obs.method,
                "confidence": obs.confidence,
            }
            for obs in obs_list
            if field_name in obs.engine_field_values
        ]

        if not candidates:
            continue

        values = [c["value"] for c in candidates]

        if _all_same(values):
            # Agreement — corroborated
            chosen = values[0]
            confidence = max(c["confidence"] for c in candidates)
            method = "corroborated" if len(candidates) > 1 else candidates[0]["method"]
            source = candidates[0]["source"] if len(candidates) == 1 else "corroborated"
            write_audit(
                db, "resolve", obs_ids,
                {"field": field_name, "outcome": "corroborated", "value": chosen},
                part_id=part_id,
            )
        elif field_name in CATASTROPHIC_ENGINE_FIELDS:
            # Catastrophic conflict — ALWAYS flag to human, never auto-pick.
            # This holds even when an authoritative source is present; the human
            # sees all candidates (including the authoritative value) and decides.
            has_catastrophic_conflict = True
            entry = ReviewQueueEntry(
                id=str(uuid.uuid4()),
                queue_type="catastrophic_conflict",
                category=category,
                observation_ids=obs_ids,
                conflict_data={
                    "field_name": field_name,
                    "candidates": candidates,
                    "part_id": part_id,
                },
            )
            db.enqueue_review(entry)
            write_audit(
                db, "flag", obs_ids,
                {
                    "field": field_name,
                    "reason": "catastrophic_conflict",
                    "queue_entry_id": entry.id,
                    "candidates": candidates,
                },
                part_id=part_id,
            )
            # Do not set a value for this field — skip to next field
            continue
        else:
            # Non-catastrophic conflict — verification pass (authoritative wins) then LLM
            auth_value = _authoritative_value(field_name, obs_list)
            if auth_value is not None:
                chosen = auth_value
                confidence = 1.0
                method = "authoritative-verified"
                source = next(
                    o.source_name for o in obs_list
                    if o.method == "authoritative-verified"
                    and field_name in o.engine_field_values
                )
                write_audit(
                    db, "resolve", obs_ids,
                    {"field": field_name, "outcome": "authoritative_wins", "value": chosen},
                    part_id=part_id,
                )
            else:
                # LLM reconcile
                chosen, confidence = llm_reconciler.reconcile_field(
                    field_name, candidates, context=name
                )
                method = "llm-extracted"
                source = "llm-reconciled"
                write_audit(
                    db, "resolve", obs_ids,
                    {"field": field_name, "outcome": "llm_reconciled",
                     "value": chosen, "confidence": confidence},
                    part_id=part_id,
                )

        # Construct provenance-wrapped field
        part_data[field_name] = {
            "value": chosen,
            "provenance": {
                "source": source,
                "method": method,
                "confidence": confidence,
            },
        }

    return part_data, has_catastrophic_conflict


def finalize_part_from_review(
    db: Database,
    queue_entry_id: str,
    chosen_value: Any,
    llm_reconciler: LLMReconciler,
    field_trust_threshold: float = 0.80,
) -> bool:
    """Apply a human-resolved value and re-export the part.

    Returns True if the part is now fully resolved (no remaining catastrophic conflicts).
    """
    entry = db.get_review_entry(queue_entry_id)
    if entry is None or entry.status != "pending":
        return False

    db.resolve_review(queue_entry_id, chosen_value)

    part_id = entry.conflict_data.get("part_id")
    field_name = entry.conflict_data.get("field_name")
    if part_id is None or field_name is None:
        return False

    part_data = db.get_part(part_id)
    if part_data is None:
        return False

    # Apply the resolved value
    source = "human-resolved"
    part_data[field_name] = {
        "value": chosen_value,
        "provenance": {
            "source": source,
            "method": "authoritative-verified",
            "confidence": 1.0,
        },
    }

    write_audit(
        db, "resolve", entry.observation_ids,
        {"field": field_name, "outcome": "human_resolved", "value": chosen_value,
         "queue_entry_id": queue_entry_id},
        part_id=part_id,
    )

    # Check if any remaining catastrophic conflicts exist
    remaining = db.get_pending_reviews(queue_type="catastrophic_conflict")
    still_conflicted = any(
        e.conflict_data.get("part_id") == part_id for e in remaining
    )

    db.mark_part_conflict_resolved(part_id, part_data)
    return not still_conflicted


def _best_name(obs_list: list[SourceObservationRow]) -> str:
    for obs in obs_list:
        if obs.method == "authoritative-verified":
            return obs.raw_name
    return obs_list[0].raw_name


def _merge_attributes(obs_list: list[SourceObservationRow]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for obs in obs_list:
        merged.update(obs.attributes)
    return merged
