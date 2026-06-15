# Run 4b — Catalog Pipeline (Remaining Categories + Full Wire-Through) — Build Spec

**Owner:** Brooks · **Architect:** Lodestar · **Developer:** Speed Demon (Claude Code, cloud Routine) · **Auditor:** Gatekeeper
**Date:** June 14, 2026 · **Version:** 1.0 · **Repo:** `SCHISM1/builderone-catalog`

**Status:** The second and final catalog-pipeline build. **Run 4a is merged on `main`** — its mechanisms are proven and must be **reused, not rebuilt**. 4b is breadth: the six remaining category adapters plus the full-catalog wire-through. Companion to `specs/run-4a.md`, the Master Spec (Part 3 §3.5), the Master Build Plan, the Engineering Rules, and the Progressive Autonomy Principle. Stricter rule wins on conflict.

---

## ⚡ MOCKS-FIRST ONE-SHOT BUILD DIRECTIVE (read first, agent)

Built **end-to-end in a single unattended run, M1 → M4, zero human pauses**, entirely against **mocked data: no live API calls, no real credentials.**

- **Reuse the 4a foundation already on `main` — do not rebuild it.** The data model, SQLite store, export contract, `SourceAdapter` interface, entity resolution, reconciliation, review queue + Telegram transport, caps, cache, and network guard all exist. 4b *adds adapters* and *wires the full catalog*; it must not re-create or fork the existing modules.
- **Never stop to ask a question.** On ambiguity, make the most reasonable choice consistent with this spec, record it in `OPEN_QUESTIONS.md` (one line: question, choice, why), and keep building.
- **Mocks only.** Every external call (vendor APIs, the LLM, embeddings, Telegram) stays behind the existing injected/mocked clients. Zero network in CI.
- **No approval at any milestone.** Milestones are commit structure. A red test is fixed, not escalated.
- **Out of scope — do not build:** the price-refresh path (a separate P1 pass — the compatibility engine needs specs, not prices); real API adapters; live Telegram; the systemd schedule.
- **Done means:** all M1–M4 acceptance tests green; the full pipeline runs end-to-end on mocks across **all 8 categories** (ingest → resolve → flag → complete export artifact); runbook updated.

---

## 0. What Run 4b is

Breadth on the proven 4a spine. 4a proved every mechanism on two categories (CPU = clean-source, motherboard = LLM-extraction). 4b adds the **six remaining category adapters** — GPU, storage, RAM, PSU, case, cooler — each slotting onto one of those two proven paths, then runs the **whole catalog end-to-end**. No new model, store, export, ER, reconciliation, or queue work — those are done and on `main`.

---

## 1. Foundation already on `main` (from 4a — reuse)

- **Data model** — Pydantic discriminated union, all 8 categories' typed engine-fields + quarantined `attributes` blob + per-field provenance/confidence + the catastrophic-field tag.
- **SQLite store** — `source_observations` (raw per-source rows) and `parts` (canonical merged records).
- **Versioned JSON export contract** — two sections (`engine_fields` trusted / `display` untrusted), withhold-on-unresolved-catastrophic, `verify` status for non-catastrophic uncertainty, deterministic output.
- **`SourceAdapter` interface** — `fetch() → SourceObservation[]`. Reuse unchanged.
- **CPU adapter** (clean-source pattern) and **motherboard adapter** (LLM-extraction pattern — Instructor + Pydantic, reasoning-first ordering, single repair retry, injected/mocked LLM).
- **Entity resolution + reconciliation** — embedding-block → vector top-k → LLM match → deterministic merge score; the two config threshold dials; verification pass against authoritative sources; catastrophic-conflict → human review, never auto-picked; audit record per decision.
- **Review queue + Telegram transport** (ported from Fanfare), **caps** (parts/run, LLM-calls/run, budget/run), **cache-by-source-hash**, and the **network guard**.

---

## 2. Locked context carried in

- **Engine-fields for the six new categories:**
  - GPU: `tdp_watts`, `length_mm?`
  - Storage: `interface` (M.2 NVMe | SATA | …), `form_factor`
  - RAM: `ddr_generation` (DDR4|DDR5), `speed_mhz`, `module_count`, `capacity_gb`
  - PSU: `wattage`
  - Case: `form_factors_supported[]`, `max_gpu_length_mm?`, `max_cooler_height_mm?`
  - Cooler: `height_mm`
- **Source-path per category:**
  - *Clean-source* (CPU pattern, no LLM): GPU (TechPowerUp / DBGPU shape), storage/SSD (TechPowerUp shape).
  - *LLM-extraction* (motherboard pattern): RAM, PSU, case, cooler.
- **Catastrophic fields** (conflict → human, never auto-picked): `socket`, `ram_type`/`ddr_generation`, `form_factor` (incl. case `form_factors_supported`), `wattage`, `tdp_watts`, `interface`, `m2_slots`/`sata_ports`. Clearance fields (`max_gpu_length_mm`, `max_cooler_height_mm`, cooler `height_mm`) are P3 — non-catastrophic, flagged-not-asserted.

---

## 3. Milestones

> Each milestone is independently committable, leaves `main` green, ships its tests in the same PR. Adapters only **produce observations** (→ `source_observations`); the full-catalog ER + export is M4. All external clients mocked; CI offline.

### M1 — Clean-source adapters: GPU + storage (SSD)

**Scope**
- Two adapters on the existing `SourceAdapter` interface (no interface change), following the CPU clean-source pattern. No LLM.
- **GPU adapter (mock):** structured GPU fixture (TechPowerUp / DBGPU shape) → `tdp_watts`, `length_mm?`, `method = authoritative-verified`.
- **Storage / SSD adapter (mock):** structured SSD fixture → `interface`, `form_factor`, `method = authoritative-verified`.
- Canned fixtures; cache-by-source-hash and the network guard apply as-is.

**Acceptance**
- GPU adapter → valid GPU observations; `tdp_watts` populated, `length_mm?` populated when present in fixture; `method = authoritative-verified`; written to `source_observations`.
- Storage adapter → valid storage observations; `interface` + `form_factor` populated; `method = authoritative-verified`.
- Both satisfy the existing `SourceAdapter` protocol, unchanged.
- Cache hit: re-run on identical fixture → zero re-pull (counter assertion).
- Optional-field handling: GPU fixture missing `length_mm` → tolerated (null), not an error.
- Network guard holds; CI offline.

---

### M2 — LLM-extraction adapters: RAM + PSU

**Scope**
- Two adapters on the LLM-extraction path, reusing the motherboard machinery (injected/mocked LLM, reasoning-first ordering, single repair retry, cache). New schemas + fixtures only.
- **RAM adapter (mock):** raw-text fixture → extraction → `ddr_generation`, `speed_mhz`, `module_count`, `capacity_gb`, `method = llm-extracted`.
- **PSU adapter (mock):** raw-text fixture → extraction → `wattage`, `method = llm-extracted`.
- Canned fixtures + LLM responses; cache + network guard apply.

**Acceptance**
- RAM adapter → valid RAM observations via mocked LLM; all four engine-fields populated; `method = llm-extracted`.
- PSU adapter → valid PSU observations; `wattage` populated; `method = llm-extracted`.
- Malformed LLM response → exactly one repair retry; still-invalid → quarantined, never written as a trusted engine-field.
- Cache hit: re-run on identical fixture → zero LLM calls (counter assertion).
- Both satisfy the `SourceAdapter` protocol; network guard holds; CI offline.

---

### M3 — LLM-extraction adapters: case + cooler

**Scope**
- Two more LLM-extraction adapters (same reused machinery). New schemas + fixtures only.
- **Case adapter (mock):** raw-text fixture → extraction → `form_factors_supported[]`, `max_gpu_length_mm?`, `max_cooler_height_mm?`, `method = llm-extracted`.
- **Cooler adapter (mock):** raw-text fixture → extraction → `height_mm`, `method = llm-extracted`.
- Canned fixtures + LLM responses; cache + network guard apply.

**Acceptance**
- Case adapter → valid case observations; `form_factors_supported[]` populated, clearance fields populated where present / null when absent; `method = llm-extracted`.
- **List-field check:** `form_factors_supported` parses to a proper list (e.g. `["ATX","mATX","ITX"]`), never a single string blob.
- Cooler adapter → valid cooler observations; `height_mm` populated; `method = llm-extracted`.
- Malformed LLM response → one repair retry; still-invalid → quarantined, never trusted.
- Optional clearance fields absent → tolerated (null), not an error.
- Cache hit → zero LLM calls; both satisfy the `SourceAdapter` protocol; network guard holds; CI offline.

---

### M4 — Full-catalog wire-through + hardening (the 4b-done gate)

**Scope**
- **Full-catalog end-to-end on mocks:** all 8 adapters ingest → `source_observations` → ER + reconciliation across the complete set → canonical `parts` for every category → the **complete export artifact** (both sections, all 8 categories).
- **Cross-category ER:** dedup/matching exercised on the new categories, not just CPU/motherboard.
- **Catastrophic-conflict coverage, every category:** a seeded conflict on each catastrophic field across all categories routes to the review queue (Telegram) and is withheld from export — table-driven.
- **Hardening:** broader fixtures + edge cases across the full set (the D-R4-4 breadth pass).

**Acceptance**
- Full run: 8 adapters → ER + reconciliation → complete canonical catalog → export artifact covering all 8 categories.
- Cross-category dedup: same-part observations from two sources merge (GPU case asserted).
- **Per-category catastrophic invariant:** a seeded catastrophic conflict in each catastrophic-bearing category → review-queue entry, part withheld from export (table-driven — the catalog-wide proof of the 4a rule).
- Non-catastrophic uncertainty (e.g. a clearance field) → exports with `verify` status.
- Complete export validates against the contract; `engine_fields` has zero `attributes` leak in any category; byte-identical on re-run (deterministic).
- Caps halt the full run; cross-category cache hits skip work; network guard holds; CI offline.
- Runbook updated: run a full-catalog cycle + the swap-mocks-for-real-adapters checklist now covering all 8 categories' sources.

---

## 4. Outside this run (deferred)

- **Price-refresh path** — its own P1 pass (scheduled, cheap structured pulls; not launch-blocking).
- Real source adapters + credentials swapped in for the mocks (all 8 categories' sources).
- Infra: systemd timer schedule; VPS deploy (runbook checklist, human step).
- gitleaks secret scan (before any real keys/users).
- Live Telegram demo verified on a phone.
- **Run 5** — the compatibility engine that reads this catalog's export artifact.

---

## END OF SPEC
