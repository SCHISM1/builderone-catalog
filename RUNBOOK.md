# Runbook — BuilderOne Catalog Pipeline (Run 4a)

## Prerequisites

- Python 3.11+
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A Linux host (VPS or local); systemd for scheduling

---

## 1. Clone and install

```bash
git clone https://github.com/schism1/builderone-catalog.git
cd builderone-catalog
uv sync --locked        # installs exact deps from committed uv.lock
```

---

## 2. Configure

```bash
cp .env.example .env
# Edit .env — fill in real API keys (see swap-mocks checklist below)
```

Key env vars:
| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` | OpenAI key for motherboard LLM extraction |
| `TELEGRAM_TOKEN` | Telegram bot token for review queue |
| `TELEGRAM_CHAT_ID` | Chat ID to send review messages to |
| `MATCH_THRESHOLD` | ER auto-merge threshold (default 0.85) |
| `FIELD_TRUST_THRESHOLD` | Reconciliation confidence threshold (default 0.80) |
| `MAX_PARTS_PER_RUN` | Batch cap: max parts before halt (default 1000) |
| `MAX_LLM_CALLS_PER_RUN` | Batch cap: max LLM calls before halt (default 200) |
| `MAX_BUDGET_PER_RUN` | Batch cap: max spend USD before halt (default 5.00) |

---

## 3. Run a cycle (mocked — Run 4a default)

```bash
uv run catalog --version        # verify install
uv run catalog run --dry-run    # run pipeline on mock fixtures, print summary
```

The pipeline:
1. Runs source adapters (CPU + motherboard, currently mocked)
2. Writes `source_observations` to SQLite (`catalog.db`)
3. Entity resolution + reconciliation → `parts` table
4. Exports versioned JSON artifact (`catalog_export.json`)
5. Any catastrophic conflicts → review queue (logged, Telegram in real mode)

---

## 4. Telegram live demo (real mode only — not CI)

After filling `.env` with a real Telegram bot token:

```bash
uv run catalog run --telegram
```

This sends any pending review-queue entries to your Telegram chat with inline buttons.
Tapping a button in Telegram calls the bot's webhook, which resolves the conflict and
re-exports the artifact.

To test the bot is reachable:
```bash
curl "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getMe"
```

---

## 5. Systemd timer schedule

Create `/etc/systemd/system/catalog-pipeline.service`:
```ini
[Unit]
Description=BuilderOne Catalog Pipeline

[Service]
Type=oneshot
User=builderone
WorkingDirectory=/opt/builderone-catalog
ExecStart=/root/.local/bin/uv run catalog run
EnvironmentFile=/opt/builderone-catalog/.env
```

Create `/etc/systemd/system/catalog-pipeline.timer`:
```ini
[Unit]
Description=Run catalog pipeline nightly

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
systemctl daemon-reload
systemctl enable --now catalog-pipeline.timer
systemctl list-timers catalog-pipeline.timer
```

---

## 6. Swap mocks for real adapters (post-Run-4a checklist)

These steps happen in **Run 4b / the real-adapter swap pass** — not in Run 4a:

- [ ] Add gitleaks scan (before any real keys are committed)
- [ ] Implement `BestBuyCPUAdapter` using the Best Buy Products API
- [ ] Implement `TechPowerUpAdapter` for motherboard specs (HTML scrape or API)
- [ ] Implement `KeepaAdapter` for price snapshots
- [ ] Replace `MockLLMExtractor` with `InstructorLLMExtractor(openai.OpenAI(api_key=...))`
- [ ] Replace `MockEmbeddingClient` with a real embeddings call
- [ ] Replace `MockTelegramClient` with `HttpxTelegramClient(token=...)`
- [ ] Set `LLM_API_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` in `.env`
- [ ] Run a full cycle against live data; verify export artifact
- [ ] Verify live Telegram review messages on phone
- [ ] Set up systemd timer (step 5 above)

---

## 7. Tests

```bash
uv run pytest               # all tests (offline; no network)
uv run ruff check .         # lint
uv run mypy .               # typecheck
```
