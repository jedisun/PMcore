"""第一阶段 CLI 冒烟测试。"""

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

    # 第一版 health check 的契约很小，但要稳定：
    # mode、logging 状态、database 状态必须始终存在。
    result = runner.invoke(app, ["health", "check", "--json"])

    assert result.exit_code == 0
    assert '"mode": "readonly"' in result.stdout
    assert '"configured": true' in result.stdout
    assert '"status": "disabled"' in result.stdout
