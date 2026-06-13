from typer.testing import CliRunner

from context_search_tool.cli import app


def test_cli_app_imports_and_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Context Search Tool" in result.output
