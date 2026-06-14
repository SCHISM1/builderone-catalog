"""Human review queue delivery via Telegram.

M5 writes flag entries; M6 (this module) delivers them.
"""

from __future__ import annotations

from typing import Any

from catalog.review.telegram import TelegramClient
from catalog.store.db import Database, ReviewQueueEntry


def _format_conflict_message(entry: ReviewQueueEntry) -> str:
    if entry.queue_type == "catastrophic_conflict":
        field = entry.conflict_data.get("field_name", "?")
        candidates = entry.conflict_data.get("candidates", [])
        lines = [f"*Conflict on `{field}`* (catastrophic — human resolution required)\n"]
        for i, c in enumerate(candidates):
            lines.append(f"  [{i + 1}] Source `{c['source']}` → `{c['value']}` (conf {c['confidence']:.2f})")
        lines.append("\nPlease choose the correct value:")
        return "\n".join(lines)
    else:
        # dedup
        name_a = entry.conflict_data.get("name_a", "?")
        name_b = entry.conflict_data.get("name_b", "?")
        score = entry.conflict_data.get("score", 0.0)
        return (
            f"*Possible duplicate parts* (similarity {score:.2f})\n"
            f"  A: `{name_a}`\n"
            f"  B: `{name_b}`\n\n"
            "Are these the same part?"
        )


def _build_conflict_keyboard(entry: ReviewQueueEntry) -> dict[str, Any]:
    if entry.queue_type == "catastrophic_conflict":
        candidates = entry.conflict_data.get("candidates", [])
        buttons = [
            [{"text": f"[{i + 1}] {c['value']}", "callback_data": f"resolve:{entry.id}:{c['value']}"}]
            for i, c in enumerate(candidates)
        ]
        buttons.append([{"text": "Hold for later", "callback_data": f"hold:{entry.id}"}])
        return {"inline_keyboard": buttons}
    else:
        return {
            "inline_keyboard": [
                [
                    {"text": "Yes — same part", "callback_data": f"dedup_yes:{entry.id}"},
                    {"text": "No — different", "callback_data": f"dedup_no:{entry.id}"},
                ]
            ]
        }


def deliver_review_queue(
    db: Database,
    telegram: TelegramClient,
    chat_id: str,
    queue_type: str | None = None,
) -> int:
    """Send all pending review-queue entries to Telegram.

    Returns the number of messages sent.
    """
    entries = db.get_pending_reviews(queue_type=queue_type)
    count = 0
    for entry in entries:
        text = _format_conflict_message(entry)
        keyboard = _build_conflict_keyboard(entry)
        telegram.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
        count += 1
    return count


def handle_callback(
    db: Database,
    callback_data: str,
) -> dict[str, Any]:
    """Process a Telegram inline-keyboard callback.

    callback_data formats:
    - ``resolve:<entry_id>:<value>`` — user picked a value for a catastrophic conflict.
    - ``hold:<entry_id>``            — user deferred.
    - ``dedup_yes:<entry_id>``       — user confirmed same part.
    - ``dedup_no:<entry_id>``        — user confirmed different parts.

    Returns a result dict with "action" and "entry_id".
    """
    parts = callback_data.split(":", 2)
    action = parts[0]
    entry_id = parts[1] if len(parts) > 1 else ""

    if action == "resolve" and len(parts) == 3:
        chosen_value = parts[2]
        db.resolve_review(entry_id, chosen_value)
        return {"action": "resolved", "entry_id": entry_id, "value": chosen_value}

    elif action == "hold":
        return {"action": "held", "entry_id": entry_id}

    elif action == "dedup_yes":
        db.resolve_review(entry_id, True)
        return {"action": "dedup_merged", "entry_id": entry_id}

    elif action == "dedup_no":
        db.resolve_review(entry_id, False)
        return {"action": "dedup_kept_separate", "entry_id": entry_id}

    return {"action": "unknown", "entry_id": entry_id}
