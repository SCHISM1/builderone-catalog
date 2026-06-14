# Run 4a — Catalog Pipeline (Vertical Slice) — Build Spec

**Owner:** Brooks · **Architect:** Lodestar · **Developer:** Speed Demon (Claude Code, cloud Routine) · **Auditor:** Gatekeeper
**Date:** June 13, 2026 · **Version:** 1.0 · **Repo:** `Team-Lodestar/builderone-catalog`

**Status:** The definitive build spec for **Run 4a** — the first of two catalog-pipeline builds (4a = vertical slice through every mechanism on two categories; 4b = the remaining categories + hardening). Derived from `Run4_Catalog_Pipeline_Design_Decisions.md` and the architecture session of June 13. Companion to the Master Spec (Part 3 §3.5), the Master Build Plan (§1.3, §2.2), the Engineering Rules, and the Progressive Autonomy Principle. Where this conflicts with one of those, the stricter rule wins until reconciled in writing.

The catalog pipeline builds and maintains the **parts database** the compatibility engine (Run 5) reads. Run 4 + Run 5 are the two trust-critical builds remaining before Builder One launches publicly.

---

## ⚡ MOCKS-FIRST ONE-SHOT BUILD DIRECTIVE (read first, agent)

This spec is built **end-to-end in a single unattended run, M1 → M6, with zero human pauses** — entirely against **mocked data: no live API calls, no real credentials.**

- **Never stop to ask a question.** If something is ambiguous, make the most reasonable choice consistent with this spec, record it in `OPEN_QUESTIONS.md` at the repo root (one line: the question, the choice made, why), and keep building.
- **Mocks only.** Every external call — vendor APIs, the LLM, the embedding model, Telegram — sits behind an **injected client that is mocked in CI**. The build runs and every test passes with **zero network**. Real adapters and real keys are swapped in *outside this run* (a later pass). Do not call any live service.
- **No approval at any milestone.** Milestones are commit structure, not checkpoints. Run all tests; a red test is fixed, not escalated.
- **Out of scope for this run — do not build:** the other six part categories (RAM, PSU, GPU, case, storage, cooler — those are Run 4b); real API adapters; live Telegram; gitleaks; the systemd schedule (a runbook step, not code).
- **Done means:** all M1–M6 acceptance tests green; the full pipeline runs end-to-end on mocked fixtures (ingest → resolve → flag → export artifact); a from-scratch runbook exists.

---

## 0. What Run 4a is

A **vertical slice through every mechanism** of the catalog pipeline, proven on **two categories**: **CPU** (the clean-source path) and **motherboard** (the LLM-extraction path). The full data model, the SQLite store, the export contract, entity resolution, reconciliation, the human review queue, caps, and caching are all real and tested here — just exercised on two categories. Run 4b then repeats the proven pattern across the remaining six.

Everything is **Python**, a separate concern from the TypeScript app, behind a clean service boundary. The app consumes the catalog this pipeline produces; they do not share a runtime.

---

## 1. Locked decisions carried in (context for the agent)

- **Language / stack:** Python via `uv`, `src/`-layout, pinned deps + committed `uv.lock`.
- **Data model (3 layers):** shared fields + **strict typed engine-fields** (the Run 5 contract) + a **quarantined `attributes` JSON blob** (display-only, never read by a check). **Per-field provenance + confidence.**
- **Engine-fields by category** (4a builds CPU + motherboard; the rest are listed so the model is whole):
  - CPU: `socket`, `tdp_watts`
  - Motherboard: `socket`, `ram_type` (DDR4|DDR5), `form_factor`, `memory_slots`, `memory_max_gb?`, `m2_slots`, `sata_ports`
  - RAM: `ddr_generation` (DDR4|DDR5), `speed_mhz`, `module_count`, `capacity_gb`
  - PSU: `wattage`
  - GPU: `tdp_watts`, `length_mm?`
  - Case: `form_factors_supported[]`, `max_gpu_length_mm?`, `max_cooler_height_mm?`
  - Storage: `interface` (M.2 NVMe | SATA | …), `form_factor`
  - Cooler: `height_mm`
- **Catastrophic fields** (a source conflict on these always routes to a human, never auto-picked): `socket`, `ram_type`/`ddr_generation`, `form_factor`, `wattage`, `tdp_watts`, `interface`, `m2_slots`/`sata_ports`.
- **Storage:** internal **SQLite**. The Run 5 contract is a **versioned JSON export**, never direct DB access.
- **Export:** one versioned artifact, two structural sections — `engine_fields` (typed, trusted; the engine reads only this) and `display` (`name`, `attributes`, retailer refs, `price_snapshot?`; the app reads this). Parts with an unresolved catastrophic conflict are **withheld**; non-catastrophic uncertainty exports with a `verify` status; output is **deterministic**.
- **Thresholds are config dials, not hardcoded** (Progressive Autonomy). Two dials: **match-threshold** (ER auto-merge) and **field-trust-threshold** (reconciliation). Start strict; loosen on data later. Every merge / resolve / flag writes an audit record.
- **Reconciliation:** LLM-first; **catastrophic conflict unresolved → human review queue via Telegram** (transport ported from Fanfare).
- **Cost controls:** scheduled-not-looping batch; caps as kill-switches (parts/run, LLM-calls/run, budget/run); cache extraction by source-content hash.

---

## 2. Milestones

> Convention: each milestone is independently committable, leaves `main` green, and ships its tests in the same PR. Every external client is injected and mocked; CI runs offline.

### M1 — Skeleton & conventions

**Scope**
- Python project via `uv`, `src/`-layout package (`src/catalog/`); pinned deps + committed `uv.lock`; documented Python version. No loose version ranges.
- Repo-root `CLAUDE.md` (pipeline rules — derived from Engineering Rules + the Run 4 decisions), `.env.example` (placeholder keys: Best Buy, TechPowerUp, Keepa, Walmart, Telegram token + chat ID, LLM key — no real values), and a from-scratch runbook (clone → `uv sync` → configure → run a cycle → how the real-adapter swap works later).
- A trivial entry point that runs and exits clean (`catalog --version` / a no-op cycle) — the skeleton "hello," so there is a green thing from commit #1.
- **Python Gatekeeper** workflow (`.github/workflows/gatekeeper.yml`): `ruff` (lint) + `mypy` (typecheck) + `pytest` + `pip-audit` (dependency vulns) + the Claude review step pointed at `CLAUDE.md`. Mirrors the app's Gatekeeper, Python-flavored.
- **Zero live calls anywhere** — CI runs fully offline. gitleaks deferred to the real-API-swap pass (4a is placeholders only).

**Acceptance**
- `uv sync` installs from the committed lockfile; CI green on `ruff`, `mypy`, `pytest`.
- No unpinned dependencies (asserted).
- The trivial entry point runs and exits 0.
- `.env.example` present with placeholder keys; no real secret in the tree.
- Gatekeeper workflow runs on every PR (lint / typecheck / test / audit + Claude review).
- The test suite makes no network calls (offline-enforced).

---

### M2 — Catalog data model

**Scope**
- Pydantic models, one per category, as a **discriminated union on `category`**. Three layers:
  - **Shared fields** (every part): `id`, `category`, `name`, retailer refs, `price_snapshot?`.
  - **Typed engine-fields** (the Run 5 contract — strict, schema-validated): per the §1 field list, all 8 categories.
  - **`attributes`** — loose JSON blob, everything else; permissive, **never read by a check**.
- **Provenance wrapper on every engine-field:** a value cannot exist without `{ source, method (authoritative-verified | llm-extracted | corroborated), confidence }`. The blob carries no provenance (untrusted, display-only).
- **Catastrophic-field tag** in the model — the §1 catastrophic set is explicitly marked so M5's conflict logic references it, not a hardcoded list scattered around.

**Acceptance**
- All 8 category models validate; round-trip (serialize → deserialize) preserves engine-fields **and** provenance.
- A required engine-field missing/invalid **fails** validation (CPU with no `socket` → reject); the `attributes` blob accepts arbitrary extra keys.
- Unknown keys aimed at the strict model are rejected or quarantined to `attributes` — never silently accepted as engine-fields.
- Every engine-field carries provenance (enforced by the wrapper type — cannot construct a bare value).
- The discriminated union resolves the correct model by `category`.
- The catastrophic-field set is queryable from the model (a test asserts the exact set).

---

### M3 — SQLite store + JSON export contract

**Scope**
- SQLite schema: `source_observations` (raw per-source pulls, pre-merge — M4 fills these) and `parts` (the canonical merged record — M5 produces these; M3 builds against seeded fixtures). Provenance rides inside the canonical record (the M2 wrapper).
- The **versioned JSON export**: reads canonical `parts` → emits a two-section artifact — `engine_fields` (typed, trusted) and `display` (`name`, `attributes`, retailer refs, `price_snapshot?`) — with top-level `schema_version` and per-part `id` + `category`. Additive contract (new fields never break an existing reader).
- **Export rule:**
  - A part with an **unresolved catastrophic-field conflict** is **withheld** from the artifact — it is in the review queue, not asserted as fact.
  - A **non-catastrophic** uncertain field still exports, carrying a `verify` status — flag-don't-assert preserved downstream.
  - Resolved/trusted fields export with a `verified` / `extracted` status.
- **Deterministic output** (stable key + part ordering) so the committed artifact diffs cleanly and an app redeploy triggers only on real change.

**Acceptance**
- Schema creates; a canonical part persists and round-trips through SQLite.
- Export emits valid versioned JSON with `engine_fields` + `display` + `schema_version`; validates against the published contract model.
- **No blob leak:** `engine_fields` contains only typed engine-fields — a test asserts `attributes` never appears there.
- A seeded **unresolved catastrophic conflict** → that part is **absent** from the artifact (and present in the queue stub).
- A seeded non-catastrophic uncertain field → exported with `verify` status.
- Additive-versioning: an unknown extra field on a newer record does not break the reader.
- Re-running export on unchanged data produces a **byte-identical** artifact (deterministic).

---

### M4 — Two source adapters, on mocks

> Seam: adapters only **produce observations** (raw per-source rows → `source_observations`). Cross-source comparison, verification, conflict detection, and merge are all M5.

**Scope**
- A uniform **`SourceAdapter` interface** (`fetch() → SourceObservation[]`), designed so a real adapter drops in where the mock sits later. All output lands in `source_observations`.
- **CPU — clean-source path:** mock adapter reads a structured CPU fixture → maps straight to CPU engine-fields (`socket`, `tdp_watts`), `method = authoritative-verified`, high confidence. No LLM.
- **Motherboard — LLM-extraction path:** mock adapter reads a raw-text fixture → schema-enforced extraction (Instructor + Pydantic, reasoning-first field ordering, **single repair retry**) through an **injected LLM client that is mocked in CI** → motherboard engine-fields, `method = llm-extracted`. The extraction *logic* is real; only the LLM call is canned.
- **Cache-by-source-hash:** pulls + extraction keyed by a hash of the source content. Unchanged content → cache hit → **zero** LLM work.
- Fully offline: source fetch mocked, LLM mocked, **no network in CI**.

**Acceptance**
- CPU adapter → valid CPU observations from fixture; `method = authoritative-verified`; written to `source_observations`.
- Motherboard adapter → valid motherboard observations via the mocked LLM; `method = llm-extracted`; all engine-fields populated.
- **Malformed LLM response** → exactly one repair retry; a still-invalid response is quarantined/flagged, **never** written as a trusted engine-field.
- **Cache hit:** re-run on identical source content makes **zero** extraction/LLM calls (asserted via a call counter on the mock).
- Both adapters satisfy the same `SourceAdapter` protocol (a test confirms the swap-in shape).
- **Network guard:** any attempted real call in the test run fails the suite.

---

### M5 — Entity resolution + reconciliation

> The trust core — hammered (test-by-risk). Embedding / LLM-match / LLM-reconcile calls are injected and mocked in CI; deterministic merge scoring is real code, fully tested. M5 **detects and flags** (writes review-queue entries + audit records); M6 **delivers** the queue and handles resolution.

**Scope — two jobs**

1. **Entity resolution (which observations are the same part):**
   - Embedding-based blocking → vector top-k → LLM match/select → **deterministic final-merge scoring** (pinned).
   - **Match-threshold dial** (config): above → auto-merge into one group; below → flag to the **dedup queue**.

2. **Reconciliation (resolve field values into one canonical record):**
   - Per engine-field, gather values + method + confidence across the group.
   - Agree → `corroborated`, trusted. Conflict → **verification pass** against the authoritative source (authoritative wins) → if still unresolved, **LLM-first** reconcile.
   - **Catastrophic field unresolved → flag to human, never auto-pick** — even if one source looks more confident. **Non-catastrophic → auto-resolve** (carries `verify` if uncertain).
   - **Field-trust-threshold dial** (config) governs trusted vs flagged.
   - Output: the canonical `parts` record with per-field provenance + verification status.
   - **Every decision** (merge / resolve / flag) writes an **audit record** — score, inputs, outcome.

**Acceptance (hammered)**
- Clean match (high similarity + mocked-LLM confirm) → auto-merges; audit record + score written.
- Below-threshold match → **dedup queue**, not merged.
- Agreement on `socket` → canonical field `corroborated`, high confidence.
- **Catastrophic conflict (`socket` etc.) unresolved → review-queue entry; part NOT finalized; no auto-pick even with a higher-confidence source** (explicit invariant test).
- Non-catastrophic conflict → auto-resolved, `verify` status where uncertain.
- Verification pass: an LLM-extracted field conflicting with the authoritative source → authoritative wins (or flags if catastrophic).
- **Dials are config:** two different threshold configs → different merge/flag outcomes, **zero code change** (proves dial-not-wall).
- Deterministic merge scoring: same inputs → same score.
- Network guard holds (embeddings + LLM mocked).

---

### M6 — Review queue + batch entry + wire-through (the 4a-done gate)

> Telegram transport is **ported** from Fanfare (copied into this repo — not a shared dependency). Live Telegram is a runbook demo, not CI; resolution logic is tested against a mocked callback.

**Scope — three parts**

1. **Human review queue + Telegram.**
   - M5 writes flag entries (dedup-queue + catastrophic conflicts); M6 delivers them. A catastrophic conflict → Telegram message showing the conflict (sources + values) + an inline-keyboard resolution (pick the correct value / hold). A dedup ambiguity → "same part?" yes/no.
   - A resolution writes back → reconciliation finalizes the part.

2. **Scheduled-not-looping batch entry + caps.**
   - One entry point that runs a **single bounded batch and exits** — no loop. The schedule itself (systemd timer) is a runbook/infra step, not code.
   - **Caps as kill-switches** (config): max parts/run, max LLM-calls/run, max budget/run — any cap hit halts cleanly and logs why.

3. **End-to-end wire-through.**
   - Full run on mocks: adapters (M4) → `source_observations` → ER + reconciliation (M5) → canonical `parts` → export (M3) → artifact. Seed scenario includes a clean CPU **and** a motherboard carrying a catastrophic conflict.

**Acceptance**
- Catastrophic-conflict flag → Telegram message with conflict detail + resolution options; a mocked resolve callback writes the value back and finalizes the part.
- Dedup ambiguity → Telegram "same part?"; mocked yes merges, no keeps separate.
- Batch entry runs **one** cycle and exits (no loop).
- Each cap (parts / LLM-calls / budget) independently halts the run when hit (table-driven).
- **End-to-end:** CPU + motherboard ingest → resolve → the seeded catastrophic conflict is **withheld from the export and present in the queue/Telegram**; the artifact emits the clean parts; after a mocked resolution, re-export includes the resolved part.
- Export validates against the M3 contract and is deterministic. Network guard holds; CI offline.
- Runbook carries: run a cycle, the live Telegram demo command, the systemd-timer schedule step, and the **swap-mocks-for-real-adapters** checklist.

---

## 3. Outside this run (deferred — blocks launch, not this build)

- Real source adapters + credentials (Best Buy, TechPowerUp, Keepa, Walmart) swapped in for the mocks.
- **Run 4b:** RAM, PSU, GPU, case, storage, cooler + remaining adapters + hardening.
- Infra: the systemd timer schedule; the VPS deploy (runbook checklist, human step).
- gitleaks secret scan (added before any real keys/users).
- Live Telegram demo verified on a phone (runbook command).
- The Run 5 read-side: how the compatibility engine consumes the export artifact (settled before Run 5).

---

## END OF SPEC
