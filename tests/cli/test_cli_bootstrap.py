"""Smoke tests for the phase-1 CLI surface."""

from typer.testing import CliRunner

from polymarket_app.main import app

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_health_check_json_readonly(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_ENABLED", "false")
    monkeypatch.setenv("PM_ENABLE_TRADING", "false")

    # The first health-check contract is intentionally tiny but stable: mode,
    # logging bootstrap state, and database status.
    result = runner.invoke(app, ["health", "check", "--json"])

    assert result.exit_code == 0
    assert '"mode": "readonly"' in result.stdout
    assert '"configured": true' in result.stdout
    assert '"status": "disabled"' in result.stdout
