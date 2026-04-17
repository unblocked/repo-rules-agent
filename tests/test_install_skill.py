"""Tests for the install-skill CLI command."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from rules_agent.cli import app

runner = CliRunner()


def test_install_skill_project_scope(tmp_path, monkeypatch):
    """install-skill --scope project writes SKILL.md to .claude/skills/repo-rules/."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["install-skill", "--scope", "project"])
    assert result.exit_code == 0, result.output

    skill_path = tmp_path / ".claude" / "skills" / "repo-rules" / "SKILL.md"
    assert skill_path.exists()
    content = skill_path.read_text()
    assert "repo-rules-agent" in content
    assert "poetry run" not in content


def test_install_skill_user_scope(tmp_path):
    """install-skill --scope user writes SKILL.md to ~/.claude/skills/repo-rules/."""
    with patch.object(Path, "home", return_value=tmp_path):
        result = runner.invoke(app, ["install-skill", "--scope", "user"])
    assert result.exit_code == 0, result.output

    skill_path = tmp_path / ".claude" / "skills" / "repo-rules" / "SKILL.md"
    assert skill_path.exists()
    content = skill_path.read_text()
    assert "repo-rules-agent" in content
    assert "poetry run" not in content


def test_install_skill_content_valid():
    """Bundled SKILL.md contains expected frontmatter and commands."""
    skill_source = Path(__file__).parent.parent / "src" / "rules_agent" / "skill" / "SKILL.md"
    assert skill_source.exists(), f"Bundled SKILL.md not found at {skill_source}"

    content = skill_source.read_text()
    assert "name: repo-rules" in content
    assert "repo-rules-agent discover" in content
    assert "repo-rules-agent index" in content
    assert "repo-rules-agent query" in content
    assert "repo-rules-agent eval" in content
    assert "repo-rules-agent install-skill" in content
    assert "poetry run" not in content


def test_install_skill_overwrite_with_force(tmp_path, monkeypatch):
    """install-skill --force overwrites existing SKILL.md without prompting."""
    monkeypatch.chdir(tmp_path)

    # Install once
    result = runner.invoke(app, ["install-skill", "--scope", "project"])
    assert result.exit_code == 0, result.output

    # Install again with --force
    result = runner.invoke(app, ["install-skill", "--scope", "project", "--force"])
    assert result.exit_code == 0, result.output
    assert "installed" in result.output.lower()


def test_install_skill_overwrite_decline(tmp_path, monkeypatch):
    """install-skill skips the destination when user declines overwrite."""
    monkeypatch.chdir(tmp_path)

    # Install once
    result = runner.invoke(app, ["install-skill", "--scope", "project"])
    assert result.exit_code == 0, result.output

    # Try to install again, decline
    result = runner.invoke(app, ["install-skill", "--scope", "project"], input="n\n")
    assert result.exit_code == 0
    assert "skipped" in result.output.lower()


def test_install_skill_invalid_scope(tmp_path, monkeypatch):
    """install-skill with invalid scope shows error."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["install-skill", "--scope", "invalid"])
    assert result.exit_code == 1
    assert "invalid scope" in result.output.lower()


def test_install_skill_invalid_target(tmp_path, monkeypatch):
    """install-skill with invalid target shows error."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["install-skill", "--target", "gemini"])
    assert result.exit_code == 1
    assert "invalid target" in result.output.lower()


def test_install_skill_codex_user_scope(tmp_path, monkeypatch):
    """--target codex --scope user writes to ~/.codex/skills/repo-rules/."""
    monkeypatch.chdir(tmp_path)
    with patch.object(Path, "home", return_value=tmp_path):
        result = runner.invoke(app, ["install-skill", "--target", "codex", "--scope", "user"])
    assert result.exit_code == 0, result.output

    skill_path = tmp_path / ".codex" / "skills" / "repo-rules" / "SKILL.md"
    assert skill_path.exists()


def test_install_skill_codex_project_scope_rejected(tmp_path, monkeypatch):
    """--target codex --scope project errors (codex is user-scope only)."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["install-skill", "--target", "codex", "--scope", "project"])
    assert result.exit_code == 1
    assert "codex" in result.output.lower()
    assert "user" in result.output.lower()


def test_install_skill_cursor_project_scope(tmp_path, monkeypatch):
    """--target cursor --scope project writes to .cursor/skills/repo-rules/."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["install-skill", "--target", "cursor", "--scope", "project"])
    assert result.exit_code == 0, result.output

    skill_path = tmp_path / ".cursor" / "skills" / "repo-rules" / "SKILL.md"
    assert skill_path.exists()


def test_install_skill_cursor_user_scope(tmp_path, monkeypatch):
    """--target cursor --scope user writes to ~/.cursor/skills/repo-rules/."""
    monkeypatch.chdir(tmp_path)
    with patch.object(Path, "home", return_value=tmp_path):
        result = runner.invoke(app, ["install-skill", "--target", "cursor", "--scope", "user"])
    assert result.exit_code == 0, result.output

    skill_path = tmp_path / ".cursor" / "skills" / "repo-rules" / "SKILL.md"
    assert skill_path.exists()


def test_install_skill_target_all_project(tmp_path, monkeypatch):
    """--target all --scope project writes to claude + cursor, skips codex."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["install-skill", "--target", "all", "--scope", "project"])
    assert result.exit_code == 0, result.output

    assert (tmp_path / ".claude" / "skills" / "repo-rules" / "SKILL.md").exists()
    assert (tmp_path / ".cursor" / "skills" / "repo-rules" / "SKILL.md").exists()
    assert not (tmp_path / ".codex" / "skills" / "repo-rules" / "SKILL.md").exists()
    # Codex skip is surfaced to the user
    assert "codex" in result.output.lower()


def test_install_skill_target_all_user(tmp_path, monkeypatch):
    """--target all --scope user writes to every agent's user-scope location."""
    monkeypatch.chdir(tmp_path)
    with patch.object(Path, "home", return_value=tmp_path):
        result = runner.invoke(app, ["install-skill", "--target", "all", "--scope", "user"])
    assert result.exit_code == 0, result.output

    assert (tmp_path / ".claude" / "skills" / "repo-rules" / "SKILL.md").exists()
    assert (tmp_path / ".codex" / "skills" / "repo-rules" / "SKILL.md").exists()
    assert (tmp_path / ".cursor" / "skills" / "repo-rules" / "SKILL.md").exists()
