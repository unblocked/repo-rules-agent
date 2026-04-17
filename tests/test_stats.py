"""Tests for the `stats` CLI subcommand."""

import json
from pathlib import Path

from typer.testing import CliRunner

from rules_agent.cli import app

runner = CliRunner()


def _write_index(tmp_path: Path) -> Path:
    """Write a small RuleIndex JSON file and return its path."""
    index = {
        "repo": "/fake/repo",
        "source_sha": "abc123",
        "files": [
            {"path": "AGENTS.md", "tier": 1, "content_size": 100, "rules": []},
            {"path": "frontend/AGENTS.md", "tier": 4, "content_size": 200, "rules": []},
        ],
        "rules": [
            {
                "title": "rule A",
                "description": "must",
                "category": "best_practice",
                "tasks": ["code-review"],
                "languages": ["py"],
                "scope": "repo",
                "severity": "must",
                "source_file": "AGENTS.md",
            },
            {
                "title": "rule B",
                "description": "should",
                "category": "best_practice",
                "tasks": ["code-generation", "code-review"],
                "languages": ["ts", "js"],
                "scope": "repo",
                "severity": "should",
                "source_file": "frontend/AGENTS.md",
            },
            {
                "title": "rule C",
                "description": "can",
                "category": "best_practice",
                "tasks": ["code-questions"],
                "languages": ["ts"],
                "scope": "repo",
                "severity": "can",
                "source_file": "frontend/AGENTS.md",
            },
        ],
        "conflicts": [],
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index))
    return path


def test_stats_reports_total_and_per_file(tmp_path):
    index_path = _write_index(tmp_path)
    result = runner.invoke(app, ["stats", str(index_path)])

    assert result.exit_code == 0
    assert "3 rules" in result.stdout
    assert "2 files" in result.stdout
    assert "AGENTS.md" in result.stdout
    assert "frontend/AGENTS.md" in result.stdout


def test_stats_reports_breakdowns(tmp_path):
    index_path = _write_index(tmp_path)
    result = runner.invoke(app, ["stats", str(index_path)])

    assert result.exit_code == 0
    # Severity breakdown — one each
    assert "must 1" in result.stdout
    assert "should 1" in result.stdout
    assert "can 1" in result.stdout
    # Task breakdown — code-review appears on 2 rules
    assert "code-review 2" in result.stdout
    # Language breakdown — ts appears on 2 rules
    assert "ts 2" in result.stdout


def test_stats_errors_when_index_missing(tmp_path):
    missing = tmp_path / "nope.json"
    result = runner.invoke(app, ["stats", str(missing)])

    assert result.exit_code == 1
    assert "no index found" in result.stdout.lower()
