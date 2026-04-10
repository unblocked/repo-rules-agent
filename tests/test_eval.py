"""Tests for LLM-as-judge evaluation."""

from unittest.mock import MagicMock

import pytest

from rules_agent.rules.eval import (
    JUDGE_TOOL,
    FileEvaluation,
    _format_rules_for_judge,
    evaluate_file,
    evaluate_index,
)
from rules_agent.rules.eval_prompts import JUDGE_SYSTEM, JUDGE_USER
from rules_agent.rules.models import Rule, RuleFile, RuleIndex


def _make_rule(**kwargs) -> Rule:
    """Helper to create a Rule with sensible defaults."""
    defaults = {
        "title": "Use type hints",
        "description": "Always add type hints to function signatures.",
        "category": "readability",
        "tasks": ["code-review"],
        "languages": ["python"],
        "scope": "repo",
        "severity": "should",
        "source_file": "/test/CLAUDE.md",
    }
    defaults.update(kwargs)
    return Rule(**defaults)


def _make_judge_response(matched=None, missed=None, hallucinated=None, redundant=None, source_count=3):
    """Helper to create a mock judge tool call response (OpenAI Chat Completions API format)."""
    import json

    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps(
        {
            "source_rule_count": source_count,
            "matched_rules": matched if matched is not None else ["Rule A", "Rule B"],
            "missed_rules": missed or [],
            "hallucinated_rules": hallucinated or [],
            "redundant_rules": redundant or [],
            "reasoning": "Good extraction overall.",
        }
    )
    message = MagicMock()
    message.tool_calls = [tool_call]
    choice = MagicMock()
    choice.message = message
    return MagicMock(choices=[choice])


# --- Computed metrics ---


def test_file_eval_perfect_extraction():
    """Test computed metrics for perfect extraction."""
    fe = FileEvaluation(
        matched_rules=["rule1", "rule2", "rule3"],
        missed_rules=[],
        hallucinated_rules=[],
        redundant_rules=[],
        source_rule_count=3,
    )
    assert fe.tp == 3
    assert fe.fp == 0
    assert fe.fn == 0
    assert fe.precision == 1.0
    assert fe.recall == 1.0
    assert fe.f1 == 1.0


def test_file_eval_partial_extraction():
    """Test computed metrics when some rules are missed and some hallucinated."""
    fe = FileEvaluation(
        matched_rules=["rule1"],
        missed_rules=["rule2", "rule3"],
        hallucinated_rules=["fake_rule"],
        redundant_rules=[],
        source_rule_count=3,
    )
    assert fe.tp == 1
    assert fe.fp == 1
    assert fe.fn == 2
    assert fe.precision == pytest.approx(0.5)
    assert fe.recall == pytest.approx(1 / 3)
    # F1 = 2 * 0.5 * (1/3) / (0.5 + 1/3) = 0.4
    assert fe.f1 == pytest.approx(0.4)


def test_file_eval_empty_source_and_extraction():
    """Test that empty source + empty extraction = perfect scores."""
    fe = FileEvaluation(
        matched_rules=[],
        missed_rules=[],
        hallucinated_rules=[],
        redundant_rules=[],
        source_rule_count=0,
    )
    assert fe.precision == 1.0
    assert fe.recall == 1.0
    assert fe.f1 == pytest.approx(1.0)


def test_file_eval_composite_matching():
    """Test that composite extracted rules covering multiple source rules improve recall."""
    # 1 extracted rule covers 4 source rules (composite match)
    # Judge reports: 1 matched extraction, 0 missed, source_rule_count=4
    fe = FileEvaluation(
        matched_rules=["Order imports: built-in, external, internal, relative"],
        missed_rules=[],
        hallucinated_rules=[],
        redundant_rules=[],
        source_rule_count=4,
    )
    assert fe.tp == 1
    assert fe.fp == 0
    assert fe.fn == 0
    # Precision: extraction-side = 1/1 = 100%
    assert fe.precision == 1.0
    # Recall: source-side = (4-0)/4 = 100% (all source rules covered)
    assert fe.recall == 1.0
    assert fe.f1 == 1.0


def test_file_eval_composite_with_misses():
    """Test composite matching with some source rules still missed."""
    # 2 extracted rules cover 6 source rules, but 2 source rules are missed
    fe = FileEvaluation(
        matched_rules=["Import ordering composite", "Formatting composite"],
        missed_rules=["Use semicolons", "Add trailing commas"],
        hallucinated_rules=[],
        redundant_rules=[],
        source_rule_count=8,
    )
    assert fe.tp == 2
    assert fe.fn == 2
    # Precision: extraction-side = 2/2 = 100%
    assert fe.precision == 1.0
    # Recall: source-side = (8-2)/8 = 75%
    assert fe.recall == pytest.approx(0.75)


def test_file_eval_redundant_counted_as_fp():
    """Test that redundant rules count as false positives."""
    fe = FileEvaluation(
        matched_rules=["rule1"],
        missed_rules=[],
        hallucinated_rules=[],
        redundant_rules=["rule1_dup"],
        source_rule_count=1,
    )
    assert fe.tp == 1
    assert fe.fp == 1
    assert fe.fn == 0
    assert fe.precision == pytest.approx(0.5)
    assert fe.recall == 1.0


# --- Judge prompt ---


def test_judge_system_prompt_contains_classification_keywords():
    """Test that the judge system prompt contains key classification terms."""
    assert "Matched" in JUDGE_SYSTEM
    assert "Hallucinated" in JUDGE_SYSTEM
    assert "Redundant" in JUDGE_SYSTEM
    assert "missed" in JUDGE_SYSTEM.lower()
    assert "submit_evaluation" in JUDGE_SYSTEM
    assert "composite" in JUDGE_SYSTEM.lower()


def test_judge_user_prompt_format():
    """Test that the judge user prompt formats correctly."""
    prompt = JUDGE_USER.format(
        file_path="/test/CLAUDE.md",
        source_content="# Rules\nUse type hints.",
        rule_count=1,
        rules_text="1. **Use type hints**",
    )
    assert "/test/CLAUDE.md" in prompt
    assert "Use type hints" in prompt
    assert "1" in prompt


# --- _format_rules_for_judge ---


def test_format_rules_shows_all_fields():
    """Test that formatted rules include all relevant fields."""
    rule = _make_rule()
    text = _format_rules_for_judge([rule])
    assert "Use type hints" in text
    assert "readability" in text
    assert "should" in text
    assert "repo" in text
    assert "python" in text
    assert "code-review" in text
    assert "Always add type hints" in text


def test_format_rules_handles_empty():
    """Test that empty rules list produces placeholder."""
    text = _format_rules_for_judge([])
    assert "no rules extracted" in text


def test_format_rules_numbers_multiple():
    """Test that multiple rules are numbered."""
    rules = [
        _make_rule(title="Rule one"),
        _make_rule(title="Rule two"),
    ]
    text = _format_rules_for_judge(rules)
    assert "1." in text
    assert "2." in text
    assert "Rule one" in text
    assert "Rule two" in text


# --- Judge tool schema ---


def test_judge_tool_has_classification_fields():
    """Test that the judge tool schema includes classification fields."""
    props = JUDGE_TOOL["parameters"]["properties"]
    assert "source_rule_count" in props
    assert "matched_rules" in props
    assert "missed_rules" in props
    assert "hallucinated_rules" in props
    assert "redundant_rules" in props
    assert "reasoning" in props


def test_judge_tool_excludes_metadata_fields():
    """Test that the judge tool schema excludes metadata fields set by us."""
    props = JUDGE_TOOL["parameters"]["properties"]
    assert "file_path" not in props
    assert "source_content_size" not in props
    assert "rule_count" not in props


def test_judge_tool_name():
    """Test that the judge tool has the correct name."""
    assert JUDGE_TOOL["name"] == "submit_evaluation"


# --- evaluate_file ---


def test_evaluate_file_uses_tool_choice():
    """Test that evaluate_file forces tool_choice for structured output."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_judge_response(
        matched=["Rule A", "Rule B"], missed=["Rule C"], source_count=3
    )

    rules = [_make_rule()]
    result = evaluate_file(
        file_path="/test/CLAUDE.md",
        source_content="# Use type hints",
        rules=rules,
        client=mock_client,
    )

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_evaluation"},
    }
    assert call_kwargs["tools"] == [JUDGE_TOOL]
    assert call_kwargs["messages"][0] == {"role": "system", "content": JUDGE_SYSTEM}

    assert len(result.matched_rules) == 2
    assert result.source_rule_count == 3
    assert result.precision == pytest.approx(1.0)  # 2 matched, 0 FP
    assert result.recall == pytest.approx(2 / 3)  # 2 matched out of 3 source
    assert result.file_path == "/test/CLAUDE.md"
    assert result.rule_count == 1


def test_evaluate_file_fallback_on_no_function_call():
    """Test that evaluate_file returns zero counts when no tool_calls in output."""
    mock_client = MagicMock()
    message = MagicMock()
    message.tool_calls = None
    choice = MagicMock()
    choice.message = message
    mock_client.chat.completions.create.return_value = MagicMock(choices=[choice])

    result = evaluate_file(
        file_path="/test/CLAUDE.md",
        source_content="# Rules",
        rules=[_make_rule()],
        client=mock_client,
    )

    assert result.tp == 0
    assert result.source_rule_count == 0
    assert "failed" in result.reasoning.lower()


def test_evaluate_file_fallback_on_exception():
    """Test that evaluate_file returns zero counts on API exception."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")

    result = evaluate_file(
        file_path="/test/CLAUDE.md",
        source_content="# Rules",
        rules=[_make_rule()],
        client=mock_client,
    )

    assert result.tp == 0
    assert result.source_rule_count == 0
    assert "failed" in result.reasoning.lower()


def test_evaluate_file_sets_metadata():
    """Test that evaluate_file sets metadata fields correctly."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_judge_response()

    rules = [_make_rule(), _make_rule(title="Second rule")]
    result = evaluate_file(
        file_path="/test/AGENTS.md",
        source_content="x" * 500,
        rules=rules,
        client=mock_client,
    )

    assert result.file_path == "/test/AGENTS.md"
    assert result.source_content_size == 500
    assert result.rule_count == 2


# --- evaluate_index ---


def test_evaluate_index_aggregates_scores():
    """Test that evaluate_index correctly computes micro-averaged metrics."""
    mock_client = MagicMock()
    # File 1: 2 matched, 1 missed => TP=2, FN=1
    # File 2: 1 matched, 1 hallucinated => TP=1, FP=1
    mock_client.chat.completions.create.side_effect = [
        _make_judge_response(matched=["r1", "r2"], missed=["r3"], hallucinated=[], source_count=3),
        _make_judge_response(matched=["r4"], missed=[], hallucinated=["fake"], source_count=1),
    ]

    rule_index = RuleIndex(
        repo="/test/repo",
        files=[
            RuleFile(
                path="CLAUDE.md",
                tier=1,
                content_size=100,
                rules=[_make_rule(source_file="CLAUDE.md")],
            ),
            RuleFile(
                path="AGENTS.md",
                tier=1,
                content_size=200,
                rules=[_make_rule(source_file="AGENTS.md")],
            ),
        ],
        rules=[],
    )
    source_contents = {
        "CLAUDE.md": "# Rules for Claude",
        "AGENTS.md": "# Agent guidelines",
    }

    summary = evaluate_index(rule_index, source_contents, mock_client)

    assert summary.total_files == 2
    assert summary.total_source_rules == 4
    # Micro-averaged: total TP=3, FP=1, FN=1
    assert summary.overall_precision == pytest.approx(3 / 4)  # 3/(3+1)
    assert summary.overall_recall == pytest.approx(3 / 4)  # 3/(3+1)
    assert summary.overall_f1 == pytest.approx(3 / 4)  # symmetric in this case
    assert len(summary.file_evaluations) == 2


def test_evaluate_index_skips_files_without_content():
    """Test that evaluate_index skips files not in source_contents."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_judge_response(matched=["r1", "r2", "r3"], source_count=3)

    rule_index = RuleIndex(
        repo="/test/repo",
        files=[
            RuleFile(path="CLAUDE.md", tier=1, content_size=100, rules=[_make_rule()]),
            RuleFile(path="missing.md", tier=2, content_size=50, rules=[]),
        ],
        rules=[],
    )
    source_contents = {"CLAUDE.md": "# Content"}

    summary = evaluate_index(rule_index, source_contents, mock_client)

    assert summary.total_files == 1
    assert mock_client.chat.completions.create.call_count == 1


def test_evaluate_index_empty():
    """Test that evaluate_index handles empty index."""
    mock_client = MagicMock()
    rule_index = RuleIndex(repo="/test/repo", files=[], rules=[])

    summary = evaluate_index(rule_index, {}, mock_client)

    assert summary.total_files == 0
    assert summary.total_rules == 0
    assert summary.overall_precision == 1.0
    assert summary.overall_recall == 1.0
    assert summary.overall_f1 == pytest.approx(1.0)
    assert mock_client.chat.completions.create.call_count == 0
