"""Pipeline: entity resolution + reconciliation + audit."""

from catalog.pipeline.audit import write_audit
from catalog.pipeline.entity_resolution import (
    EmbeddingClient,
    LLMMatchClient,
    ObservationGroup,
    merge_score,
    resolve_entities,
)
from catalog.pipeline.reconciliation import (
    LLMReconciler,
    finalize_part_from_review,
    reconcile_group,
)

__all__ = [
    "write_audit",
    "EmbeddingClient",
    "LLMMatchClient",
    "ObservationGroup",
    "merge_score",
    "resolve_entities",
    "LLMReconciler",
    "finalize_part_from_review",
    "reconcile_group",
]
