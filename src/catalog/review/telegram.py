"""Telegram transport — ported pattern from Fanfare (no shared dep).

The real implementation POSTs to api.telegram.org using httpx.
Tests inject MockTelegramClient — no real network, no bot token needed.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TelegramClient(Protocol):
    """Minimal Telegram Bot API surface needed by the review queue."""

    def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> str:
        """Send a message; return the message_id string."""
        ...


class HttpxTelegramClient:
    """Real Telegram Bot API client via httpx (for production use)."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._base = f"https://api.telegram.org/bot{token}"

    def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> str:
        import httpx  # imported here so tests never import httpx network stack

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        resp = httpx.post(f"{self._base}/sendMessage", json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return str(data["result"]["message_id"])


class MockTelegramClient:
    """In-memory mock — records sent messages; no network."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self._counter = 0

    def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> str:
        self._counter += 1
        msg_id = str(self._counter)
        self.sent.append(
            {"message_id": msg_id, "chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )
        return msg_id
