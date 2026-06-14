"""CLI entry point for the catalog pipeline."""

from __future__ import annotations

import click

from catalog import __version__
from catalog.config import Config


@click.group()
def main() -> None:
    """BuilderOne catalog pipeline."""


@main.command()
def version() -> None:
    """Print version and exit."""
    click.echo(f"catalog {__version__}")


@main.command(name="run")
@click.option("--dry-run", is_flag=True, default=False, help="Run on mock fixtures; print summary.")
@click.option("--telegram", is_flag=True, default=False, help="Send review-queue items to Telegram.")
def run_cmd(dry_run: bool, telegram: bool) -> None:
    """Run one catalog pipeline cycle and exit."""
    cfg = Config.from_env()
    click.echo(f"catalog {__version__} — starting cycle (dry_run={dry_run})")
    if dry_run:
        click.echo("Dry-run mode: using mock fixtures, no live calls.")
        return
    click.echo(f"Config: match_threshold={cfg.match_threshold}, max_parts={cfg.max_parts_per_run}")
    click.echo("Pipeline cycle complete.")


if __name__ == "__main__":
    main()
