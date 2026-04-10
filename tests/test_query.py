"""Tests for rules querying."""

import pytest

from rules_agent.rules.models import Rule, RuleFile, RuleIndex
from rules_agent.rules.query import (
    format_rules_for_prompt,
    format_rules_with_sources,
    query_rules,
    resolve_source_contents,
)


@pytest.fixture
def sample_index() -> RuleIndex:
    """Create a sample index for testing."""
    rules = [
        Rule(
            title="Use type hints for all functions",
            tasks=["code-review", "code-generation"],
            languages=["py"],
            scope="repo",
            severity="must",
            source_file="CONTRIBUTING.md",
        ),
        Rule(
            title="Add JSDoc comments to public APIs",
            tasks=["code-generation"],
            languages=["ts", "js"],
            scope="repo",
            severity="should",
            source_file="CONTRIBUTING.md",
        ),
        Rule(
            title="Run tests before committing",
            tasks=["code-review"],
            languages=["all"],
            scope="repo",
            severity="must",
            source_file="CLAUDE.md",
        ),
    ]
    return RuleIndex(repo="/test/repo", rules=rules, files=[], conflicts=[])


def test_query_by_task(sample_index: RuleIndex):
    """Test filtering by task type."""
    rules = query_rules(sample_index, task="code-generation")

    assert len(rules) == 2
    assert all("code-generation" in r.tasks for r in rules)


def test_query_by_language(sample_index: RuleIndex):
    """Test filtering by language."""
    rules = query_rules(sample_index, language="py")

    assert len(rules) == 2  # py-specific + "all"
    assert any(r.languages == ["py"] for r in rules)
    assert any("all" in r.languages for r in rules)


def test_query_by_severity(sample_index: RuleIndex):
    """Test filtering by severity."""
    rules = query_rules(sample_index, severity="must")

    assert len(rules) == 2
    assert all(r.severity == "must" for r in rules)


def test_query_combined_filters(sample_index: RuleIndex):
    """Test multiple filters combined."""
    rules = query_rules(sample_index, task="code-review", language="py")

    assert len(rules) == 2  # py-specific + "all" language rule


def test_format_rules_for_prompt(sample_index: RuleIndex):
    """Test formatting rules for prompt injection."""
    rules = query_rules(sample_index, severity="must")
    output = format_rules_for_prompt(rules)

    # Category is no longer included in prompt text (moved to metadata)
    assert "[BEST PRACTICE]" not in output
    assert "Use type hints" in output
    assert "Run tests" in output


def test_format_rules_empty():
    """Test formatting empty rules list."""
    output = format_rules_for_prompt([])

    assert output == "No specific rules apply."


# --- resolve_source_contents tests ---


def test_resolve_source_contents_from_embedded():
    """Test resolving content from embedded RuleFile.content field."""
    files = [
        RuleFile(path="CLAUDE.md", tier=1, content="# Rules\nUse type hints"),
        RuleFile(path=".cursorrules", tier=2, content="Always run tests"),
    ]
    index = RuleIndex(repo="/test", files=files, rules=[], conflicts=[])

    result = resolve_source_contents(index)

    assert result == {
        "CLAUDE.md": "# Rules\nUse type hints",
        ".cursorrules": "Always run tests",
    }


def test_resolve_source_contents_from_disk(tmp_path):
    """Test resolving content from disk when no embedded content."""
    # Create files on disk
    (tmp_path / "CLAUDE.md").write_text("# Disk content")
    (tmp_path / ".cursorrules").write_text("Disk rules")

    files = [
        RuleFile(path="CLAUDE.md", tier=1),
        RuleFile(path=".cursorrules", tier=2),
    ]
    index = RuleIndex(repo=str(tmp_path), files=files, rules=[], conflicts=[])

    result = resolve_source_contents(index, repo_path=tmp_path)

    assert result == {
        "CLAUDE.md": "# Disk content",
        ".cursorrules": "Disk rules",
    }


def test_resolve_source_contents_embedded_priority(tmp_path):
    """Test that embedded content takes priority over disk."""
    (tmp_path / "CLAUDE.md").write_text("Disk version")

    files = [
        RuleFile(path="CLAUDE.md", tier=1, content="Embedded version"),
    ]
    index = RuleIndex(repo=str(tmp_path), files=files, rules=[], conflicts=[])

    result = resolve_source_contents(index, repo_path=tmp_path)

    assert result["CLAUDE.md"] == "Embedded version"


def test_resolve_source_contents_missing_skipped(tmp_path):
    """Test that missing files are gracefully skipped."""
    files = [
        RuleFile(path="CLAUDE.md", tier=1),  # no content, not on disk
        RuleFile(path=".cursorrules", tier=2, content="Has content"),
    ]
    index = RuleIndex(repo=str(tmp_path), files=files, rules=[], conflicts=[])

    result = resolve_source_contents(index, repo_path=tmp_path)

    assert "CLAUDE.md" not in result
    assert result[".cursorrules"] == "Has content"


# --- format_rules_with_sources tests ---


def test_format_rules_with_sources_includes_content():
    """Test that output includes both rules and source file blocks."""
    rules = [
        Rule(
            title="Use type hints",
            description="Always add type hints",
            tasks=["code-review"],
            source_file="CLAUDE.md",
        ),
    ]
    source_contents = {"CLAUDE.md": "# Rules\nUse type hints for all functions"}

    output = format_rules_with_sources(rules, source_contents)

    assert "Use type hints" in output
    assert "--- Source Files ---" in output
    assert "### CLAUDE.md" in output
    assert "# Rules\nUse type hints for all functions" in output


def test_format_rules_with_sources_deduplicates():
    """Test that the same source file appears only once."""
    rules = [
        Rule(title="Rule 1", tasks=["code-review"], source_file="CLAUDE.md"),
        Rule(title="Rule 2", tasks=["code-review"], source_file="CLAUDE.md"),
    ]
    source_contents = {"CLAUDE.md": "# Rules content"}

    output = format_rules_with_sources(rules, source_contents)

    assert output.count("### CLAUDE.md") == 1


def test_format_rules_with_sources_no_content():
    """Test that rules still render when source dict is empty."""
    rules = [
        Rule(title="Rule 1", tasks=["code-review"], source_file="CLAUDE.md"),
    ]

    output = format_rules_with_sources(rules, {})

    assert "Rule 1" in output
    assert "--- Source Files ---" not in output


def test_format_rules_with_sources_empty_rules():
    """Test that empty rules list returns fallback message."""
    output = format_rules_with_sources([], {"CLAUDE.md": "content"})

    assert output == "No specific rules apply."
