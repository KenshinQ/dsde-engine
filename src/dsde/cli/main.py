"""DSDE CLI — Phase 0: --help, version, doctor."""

from __future__ import annotations

from pathlib import Path

import typer

from dsde import __version__
from dsde.config import DEFAULT_CONFIG_DIR, load_configs
from dsde.domain.errors import ConfigValidationError
from dsde.experiment.ids import config_hash

app = typer.Typer(
    name="dsde",
    help="Dynamic State-Contingent Decision Engine (Phase 0 skeleton).",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print package version."""
    typer.echo(__version__)


@app.command()
def doctor(
    config_dir: Path | None = typer.Option(
        None,
        "--config-dir",
        help="Path to configs/ (default: package sibling configs/)",
    ),
) -> None:
    """Load and validate YAML configs; print OK or errors."""
    root = config_dir or DEFAULT_CONFIG_DIR
    typer.echo(f"config_dir={root}")
    try:
        cfg = load_configs(root)
    except ConfigValidationError as exc:
        typer.echo(f"FAIL: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"FAIL: unexpected error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    h = config_hash(cfg)
    typer.echo("OK: all configs loaded and schema-valid")
    typer.echo(f"  decision.position_deadband={cfg.decision.position_deadband}")
    typer.echo(f"  decision.min_elg_improvement={cfg.decision.min_elg_improvement}")
    typer.echo(
        f"  risk.preservation_floor_annual={cfg.risk.preservation_floor_annual}"
    )
    typer.echo(f"  risk.kelly_note={cfg.risk.kelly_note}")
    typer.echo(f"  validation.primary_metric={cfg.validation.primary_metric}")
    typer.echo(
        "  validation.market_regime_gate.gate_passed="
        f"{cfg.validation.market_regime_gate.gate_passed}"
    )
    typer.echo(f"  config_hash={h[:16]}…")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
