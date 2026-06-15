# CLAUDE.md — BuilderOne Catalog Pipeline (Run 4a)

## What this is

A Python pipeline that builds and maintains the **parts database** consumed by the Run 5 compatibility engine.
Proven on two categories (CPU + motherboard) in Run 4a; extended to all eight in Run 4b.

## Safety invariants — enforced always

1. **Engine-fields are the trust boundary.** The `attributes` JSON blob is display-only and is never
   read by any compatibility check. Do not promote blob values into engine-fields.

2. **Catastrophic conflicts go to humans, never auto-picked.** If sources conflict on a catastrophic
   engine-field (`socket`, `ram_type`, `ddr_generation`, `form_factor`, `wattage`, `tdp_watts`,
   `interface`, `m2_slots`, `sata_ports`) and the conflict is not resolved by the authoritative
   source, the part is flagged to the human review queue and withheld from the export artifact.
   No code path may auto-pick a value for a catastrophic conflict.

3. **Every engine-field carries provenance.** A value cannot exist without `{source, method,
   confidence}`. The `ProvenanceField[T]` wrapper enforces this — bare values are rejected.

4. **All external calls are injected and mocked in CI.** Vendor APIs, LLM, embeddings, and Telegram
   are behind injected clients. CI runs fully offline. No live credentials in the tree.

5. **Export is the contract.** The Run 5 engine reads only the versioned JSON export, never the
   SQLite DB. The export schema is additive (new fields never break an existing reader).

## Stack

- Python 3.11, managed by `uv`
- Pydantic v2 for data models; `instructor` for schema-enforced LLM extraction
- SQLite (`sqlite3` stdlib) for internal storage
- `click` for CLI
- `ruff` (lint), `mypy` (typecheck), `pytest` (tests)

## Running locally

```bash
uv sync --locked          # install from committed lockfile
uv run catalog --version  # smoke test
uv run pytest             # all tests (offline, no network)
uv run ruff check .       # lint
uv run mypy .             # typecheck
```

## Config dials

Two key dials (all in `Config`, loaded from env):
- `MATCH_THRESHOLD` (default 0.85) — ER auto-merge threshold
- `FIELD_TRUST_THRESHOLD` (default 0.80) — reconciliation trusted-vs-flagged threshold

Start strict; loosen on real data after Run 4b.

## Catastrophic fields (exact set)

```python
{"socket", "ram_type", "ddr_generation", "form_factor",
 "wattage", "tdp_watts", "interface", "m2_slots", "sata_ports"}
```

## Adding a new source adapter

1. Implement `SourceAdapter` protocol in `src/catalog/adapters/`.
2. Return `SourceObservation` objects; populate `engine_field_values` + `attributes`.
3. Inject an `LLMExtractor` if LLM extraction is needed.
4. Add the adapter to the `run_batch()` adapter list in `batch.py`.
5. Write tests with the adapter against fixture files (no real network).
