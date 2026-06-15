"""Audit record helpers — every merge/resolve/flag writes one."""

from __future__ import annotations

import uuid
from typing import Any

from catalog.store.db import AuditRecord, Database


def write_audit(
    db: Database,
    event_type: str,
    observation_ids: list[str],
    details: dict[str, Any],
    part_id: str | None = None,
) -> AuditRecord:
    record = AuditRecord(
        id=str(uuid.uuid4()),
        event_type=event_type,
        observation_ids=observation_ids,
        details=details,
        part_id=part_id,
    )
    db.save_audit_record(record)
    return record
