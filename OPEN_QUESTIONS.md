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

---

## Run 4b ambiguities

**Q7: Should `form_factors_supported` (the case field) be added to `CATASTROPHIC_ENGINE_FIELDS`?**
Choice: Yes — added `form_factors_supported` to the global `CATASTROPHIC_ENGINE_FIELDS` set and updated `CasePart.CATASTROPHIC_FIELDS` to reference it.
Why: Spec 4b §2 explicitly states "form_factor (incl. case form_factors_supported)" is catastrophic. The reconciler uses `CATASTROPHIC_ENGINE_FIELDS` to decide conflict routing, so the actual field name used in observations (`form_factors_supported`) must appear in that set. The test suite now asserts this 10-element set.

**Q8: Should the six new LLM-extraction adapters (RAM, PSU, Case, Cooler) re-import `LLMExtractor` from `motherboard.py` or define their own protocol?**
Choice: Re-import `LLMExtractor` from `catalog.adapters.motherboard` — it's already a clean, injected protocol that all mocked extractors satisfy.
Why: The protocol is generic (`extract(text, response_model, max_retries)`) and works for any Pydantic schema. Duplicating it would violate the "reuse, don't rebuild" directive.

**Q9: Are cooler height_mm and case clearance fields (`max_gpu_length_mm`, `max_cooler_height_mm`) engine-fields or attributes?**
Choice: Engine-fields (stored in `engine_field_values` and exported under `engine_fields`). The spec calls them "P3 — non-catastrophic, flagged-not-asserted" but they are still engine-fields (just with `verify` status when uncertain), not display attributes.
Why: Spec 4b §2 lists them as engine-fields of their respective categories. The export contract's `_engine_field_names_for_category` already includes them.

**Q10: What is the cooler's `CATASTROPHIC_FIELDS` set?**
Choice: Empty frozenset — the only cooler engine-field is `height_mm`, which is a clearance field (non-catastrophic per spec).
Why: Spec 4b §2 says "Clearance fields (max_gpu_length_mm, max_cooler_height_mm, cooler height_mm) are P3 — non-catastrophic." The existing `CoolerPart` model already reflects this.
