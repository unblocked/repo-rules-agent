"""Tests for the cache path helpers and the `cache` CLI subcommand."""

from pathlib import Path

from typer.testing import CliRunner

from rules_agent.cli import app
from rules_agent.rules import paths

runner = CliRunner()


def _set_cache_root(monkeypatch, tmp_path: Path) -> Path:
    """Point platformdirs.user_cache_dir at a temp directory for the test."""
    monkeypatch.setattr(paths, "user_cache_dir", lambda _app: str(tmp_path))
    return tmp_path


def test_default_index_path_stable_per_repo(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path)
    repo_a = tmp_path / "repo-a"
    repo_a.mkdir()

    first = paths.default_index_path(repo_a)
    second = paths.default_index_path(repo_a)

    assert first == second
    assert first.name == "index.json"
    assert first.parent.parent == tmp_path


def test_default_index_path_differs_between_repos(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path)
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()

    assert paths.default_index_path(repo_a) != paths.default_index_path(repo_b)


def test_default_index_path_basename_in_dirname(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path)
    repo = tmp_path / "My Cool Repo"
    repo.mkdir()

    # Basename is lowercased and sanitized so `cache list` is readable
    assert paths.default_index_path(repo).parent.name.startswith("my-cool-repo-")


def test_list_cached_indices_empty(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path / "does-not-exist-yet")
    assert paths.list_cached_indices() == []


def test_list_cached_indices_sorted_by_mtime(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path)
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()

    idx_a = paths.default_index_path(repo_a)
    idx_b = paths.default_index_path(repo_b)
    idx_a.parent.mkdir(parents=True)
    idx_b.parent.mkdir(parents=True)
    idx_a.write_text("{}")
    idx_b.write_text("{}")
    # Force idx_b to be more recent than idx_a
    idx_a_stat = idx_a.stat()
    import os

    os.utime(idx_a, (idx_a_stat.st_atime, idx_a_stat.st_mtime - 100))

    entries = paths.list_cached_indices()
    assert entries == [idx_b, idx_a]


def test_clear_cache_specific_repo(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path)
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()

    idx_a = paths.default_index_path(repo_a)
    idx_b = paths.default_index_path(repo_b)
    idx_a.parent.mkdir(parents=True)
    idx_b.parent.mkdir(parents=True)
    idx_a.write_text("{}")
    idx_b.write_text("{}")

    removed = paths.clear_cache(repo_a)

    assert len(removed) == 1
    assert not idx_a.exists()
    assert idx_b.exists()


def test_clear_cache_all(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()

    idx = paths.default_index_path(repo)
    idx.parent.mkdir(parents=True)
    idx.write_text("{}")

    removed = paths.clear_cache(None)

    assert len(removed) >= 1
    assert not idx.exists()


def test_clear_cache_nonexistent_is_noop(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path / "nope")
    assert paths.clear_cache(None) == []
    assert paths.clear_cache(tmp_path) == []


def test_cache_path_command(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path)
    repo = tmp_path / "example"
    repo.mkdir()

    result = runner.invoke(app, ["cache", "path", str(repo)])

    assert result.exit_code == 0, result.output
    # Rich may wrap long paths across lines; compare after collapsing whitespace
    printed = "".join(result.output.split())
    expected = "".join(str(paths.default_index_path(repo)).split())
    assert printed == expected


def test_cache_list_command_empty(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path / "empty")
    result = runner.invoke(app, ["cache", "list"])
    assert result.exit_code == 0
    assert "No cached indices" in result.output


def test_cache_list_command_with_entries(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path)
    repo = tmp_path / "example"
    repo.mkdir()
    idx = paths.default_index_path(repo)
    idx.parent.mkdir(parents=True)
    idx.write_text("{}")

    result = runner.invoke(app, ["cache", "list"])

    assert result.exit_code == 0, result.output
    assert "example" in result.output


def test_cache_clear_requires_target(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path)
    result = runner.invoke(app, ["cache", "clear"])
    assert result.exit_code == 1
    assert "pass a repo path, or --all" in result.output


def test_cache_clear_specific_repo_via_cli(monkeypatch, tmp_path):
    _set_cache_root(monkeypatch, tmp_path)
    repo = tmp_path / "example"
    repo.mkdir()
    idx = paths.default_index_path(repo)
    idx.parent.mkdir(parents=True)
    idx.write_text("{}")

    result = runner.invoke(app, ["cache", "clear", str(repo)])

    assert result.exit_code == 0, result.output
    assert not idx.exists()


def test_query_errors_without_index(monkeypatch, tmp_path):
    """`query` with no arg and no cached index should error with a helpful message."""
    _set_cache_root(monkeypatch, tmp_path / "empty")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["query"])

    assert result.exit_code == 1
    assert "no index found" in result.output.lower()
    assert "repo-rules-agent index" in result.output
