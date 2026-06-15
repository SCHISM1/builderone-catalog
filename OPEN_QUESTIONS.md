# OPEN_QUESTIONS.md

Ambiguities encountered during Run 4a, recorded per the One-Shot Build Directive.

---

**Q1: What is the exact format of the Fanfare Telegram transport to port?**
Choice: Implemented a clean Telegram Bot API client using httpx (POST to api.telegram.org) with inline-keyboard support. Fanfare source was unavailable; the bot-API approach is the standard pattern referenced by the spec and satisfies the M6 acceptance criteria.
Why: No access to the Fanfare repo in this session; the Telegram Bot HTTP API is the obvious underlying mechanism.

**Q2: Should `pip-audit` be a dev dependency in the lockfile or invoked via `uvx`?**
Choice: Invoked via `uvx pip-audit` (not in lockfile), matching the existing gatekeeper.yml which already uses `uvx pip-audit`.
Why: The workflow is not modified; it already uses uvx, so no lockfile entry is needed.

**Q3: Should `memory_max_gb` be `int | None` or `float | None`?**
Choice: `int | None` — GB values are always integers in practice for consumer motherboards.
Why: Simpler to validate, matches the spec's `memory_max_gb?` notation (no float precision needed).

**Q4: What scoring weights to use for the deterministic merge score?**
Choice: `score = 0.7 * cosine_similarity + 0.3 * name_similarity`. Both are in [0, 1]; output is in [0, 1].
Why: Embedding similarity is the stronger signal; name similarity provides a tiebreaker. Weights chosen to keep the formula simple and deterministic.

**Q5: Should LLM reconciliation be mocked the same way as LLM extraction?**
Choice: Yes — both use the injected `LLMExtractor` / `LLMReconciler` protocol; mocked in all tests.
Why: Consistent with the spec's requirement that all LLM calls are injected and mocked in CI.

**Q6: Does the export artifact need to be written to disk or returned as a Python object?**
Choice: Returns a `CatalogExport` Pydantic model and can optionally write to a file path. Tests work with the in-memory object; the runbook shows the file-write path.
Why: Enables determinism testing without touching the filesystem.
