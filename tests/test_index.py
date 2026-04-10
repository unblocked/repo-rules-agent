"""Tests for rules indexing and merging."""

from rules_agent.rules.index import _dedupe_rules, _rules_conflict, _text_similarity, build_index
from rules_agent.rules.models import Rule, RuleFile


def test_text_similarity_identical():
    """Test similarity of identical texts."""
    assert _text_similarity("hello world", "hello world") == 1.0


def test_text_similarity_different():
    """Test similarity of different texts."""
    similarity = _text_similarity("hello world", "goodbye moon")
    assert similarity < 0.5


def test_text_similarity_case_insensitive():
    """Test that similarity is case-insensitive."""
    assert _text_similarity("Hello World", "hello world") == 1.0


def test_dedupe_removes_duplicates():
    """Test that duplicate rules are removed."""
    rules = [
        Rule(title="Use type hints", tasks=["code-review"], source_file="a.md"),
        Rule(title="Use type hints", tasks=["code-review"], source_file="b.md"),
        Rule(title="Run tests", tasks=["code-review"], source_file="a.md"),
    ]

    deduped = _dedupe_rules(rules)

    assert len(deduped) == 2
    titles = [r.title for r in deduped]
    assert "Use type hints" in titles
    assert "Run tests" in titles


def test_dedupe_keeps_first():
    """Test that first occurrence (higher priority tier) is kept."""
    rules = [
        Rule(title="Use type hints", tasks=["code-review"], source_file="tier1.md"),
        Rule(title="Use type hints", tasks=["code-review"], source_file="tier2.md"),
    ]

    deduped = _dedupe_rules(rules)

    assert len(deduped) == 1
    assert deduped[0].source_file == "tier1.md"


def test_rules_conflict_different_severity():
    """Test that similar rules with different severity are flagged as conflicts."""
    rule1 = Rule(
        title="Always use semicolons",
        tasks=["code-review"],
        languages=["ts"],
        severity="must",
        source_file="a.md",
    )
    rule2 = Rule(
        title="Always use semicolons in TypeScript",
        tasks=["code-review"],
        languages=["ts"],
        severity="should",
        source_file="b.md",
    )

    assert _rules_conflict(rule1, rule2)


def test_rules_no_conflict_different_languages():
    """Test that rules for different languages don't conflict."""
    rule1 = Rule(
        title="Use semicolons",
        tasks=["code-review"],
        languages=["ts"],
        severity="must",
        source_file="a.md",
    )
    rule2 = Rule(
        title="Use semicolons",
        tasks=["code-review"],
        languages=["py"],
        severity="should",
        source_file="b.md",
    )

    assert not _rules_conflict(rule1, rule2)


def test_build_index():
    """Test building a complete index."""
    rule_files = [
        RuleFile(
            path="CLAUDE.md",
            tier=1,
            content_size=8,
            rules=[
                Rule(title="Rule 1", tasks=["code-review"], source_file="CLAUDE.md"),
            ],
        ),
        RuleFile(
            path=".cursor/rules/style.mdc",
            tier=3,
            content_size=7,
            rules=[
                Rule(title="Rule 2", tasks=["code-generation"], source_file=".cursor/rules/style.mdc"),
            ],
        ),
    ]

    index = build_index("/test/repo", rule_files)

    assert index.repo == "/test/repo"
    assert index.file_count == 2
    assert index.rule_count == 2
    assert len(index.source_sha) == 64  # SHA-256 hex, even for non-git repos
