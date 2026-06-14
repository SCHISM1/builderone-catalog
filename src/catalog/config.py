"""Pipeline configuration — all dials and caps in one place."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    # ── Entity-resolution dial ────────────────────────────────────────────────
    match_threshold: float = 0.85
    """Cosine+name similarity score above which two observations auto-merge."""

    # ── Reconciliation dial ───────────────────────────────────────────────────
    field_trust_threshold: float = 0.80
    """Confidence level above which a single-source field is trusted, not flagged."""

    # ── Batch kill-switch caps ────────────────────────────────────────────────
    max_parts_per_run: int = 1000
    max_llm_calls_per_run: int = 200
    max_budget_per_run: float = 5.00  # USD

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_model: str = "gpt-4o"
    llm_api_key: str = ""

    # ── Storage ───────────────────────────────────────────────────────────────
    db_path: str = "catalog.db"
    export_path: str = "catalog_export.json"

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            match_threshold=float(os.environ.get("MATCH_THRESHOLD", "0.85")),
            field_trust_threshold=float(os.environ.get("FIELD_TRUST_THRESHOLD", "0.80")),
            max_parts_per_run=int(os.environ.get("MAX_PARTS_PER_RUN", "1000")),
            max_llm_calls_per_run=int(os.environ.get("MAX_LLM_CALLS_PER_RUN", "200")),
            max_budget_per_run=float(os.environ.get("MAX_BUDGET_PER_RUN", "5.00")),
            telegram_token=os.environ.get("TELEGRAM_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            llm_model=os.environ.get("LLM_MODEL", "gpt-4o"),
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            db_path=os.environ.get("DB_PATH", "catalog.db"),
            export_path=os.environ.get("EXPORT_PATH", "catalog_export.json"),
        )
