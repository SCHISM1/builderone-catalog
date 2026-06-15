"""M1 — Skeleton & conventions tests."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_version_import() -> None:
    from catalog import __version__
    assert __version__ == "0.1.0"


def test_cli_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "catalog", "version"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout


def test_cli_run_dry_run() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "catalog", "run", "--dry-run"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "dry-run" in result.stdout.lower()


def test_no_unpinned_deps() -> None:
    """All project dependencies must have version constraints."""
    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)

    deps = data["project"]["dependencies"]
    for dep in deps:
        # A valid pinned dep has >= or == or ~=
        has_constraint = any(op in dep for op in (">=", "==", "~=", "<=", "!="))
        assert has_constraint, f"Unpinned dependency: {dep!r}"


def test_lockfile_exists() -> None:
    assert (REPO_ROOT / "uv.lock").exists(), "uv.lock must be committed"


def test_env_example_present() -> None:
    assert (REPO_ROOT / ".env.example").exists()
    content = (REPO_ROOT / ".env.example").read_text()
    # Must not contain real keys — placeholder values only
    assert "your-" in content


def test_env_example_has_required_keys() -> None:
    content = (REPO_ROOT / ".env.example").read_text()
    for key in [
        "LLM_API_KEY", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID",
        "MATCH_THRESHOLD", "FIELD_TRUST_THRESHOLD",
    ]:
        assert key in content, f"Missing key {key!r} in .env.example"


def test_claude_md_present() -> None:
    assert (REPO_ROOT / "CLAUDE.md").exists()
    content = (REPO_ROOT / "CLAUDE.md").read_text()
    assert "catastrophic" in content.lower()
    assert "attributes" in content


def test_runbook_present() -> None:
    assert (REPO_ROOT / "RUNBOOK.md").exists()
    content = (REPO_ROOT / "RUNBOOK.md").read_text()
    assert "uv sync" in content
    assert "systemd" in content


def test_no_real_secrets_in_tree() -> None:
    """Spot-check project source files for real API keys (not .venv or generated files)."""
    import re
    # Real OpenAI key pattern: "sk-" followed by 40+ alphanumeric chars
    real_key_re = re.compile(r"sk-[A-Za-z0-9]{40,}")
    suspicious = []
    skip_dirs = {".git", ".venv", "__pycache__", "uv.lock"}
    for path in REPO_ROOT.rglob("*"):
        if any(skip in path.parts for skip in skip_dirs):
            continue
        if path.is_dir():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if real_key_re.search(text):
            suspicious.append(str(path))
    assert not suspicious, f"Possible real secrets found in: {suspicious}"
