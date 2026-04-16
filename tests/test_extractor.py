"""Tests for rules extraction."""

from unittest.mock import MagicMock

from rules_agent.rules.extractor import (
    EXTRACTION_TOOL,
    _chunk_content,
    _CHUNK_THRESHOLD,
    extract_rules_from_file,
)
from rules_agent.rules.models import RuleFile
from rules_agent.rules.prompts import EXTRACTION_SYSTEM, EXTRACTION_USER


def test_extraction_prompt_format():
    """Test that the extraction prompt is properly formatted."""
    content = "# Test content\n\nAlways use type hints."
    prompt = EXTRACTION_USER.format(
        file_path="/test/CLAUDE.md",
        content=content,
    )

    assert "/test/CLAUDE.md" in prompt
    assert "Always use type hints" in prompt


def test_small_content_skips_chunking():
    """Test that small content is returned as a single chunk."""
    content = "# Small file\n\nJust a few rules."
    chunks = _chunk_content("/test/CLAUDE.md", content)
    assert len(chunks) == 1
    assert chunks[0] == content


def test_large_markdown_is_chunked():
    """Test that large markdown content is split into multiple chunks."""
    # Build content that exceeds _CHUNK_THRESHOLD
    sections = [f"## Section {i}\n\n{'x' * 2000}\n\n" for i in range(10)]
    content = "".join(sections)
    assert len(content) > _CHUNK_THRESHOLD

    chunks = _chunk_content("/test/AGENTS.md", content)
    assert len(chunks) > 1
    # Each chunk should contain some content
    for chunk in chunks:
        assert len(chunk.strip()) > 0


def test_large_json_uses_plain_chunker():
    """Test that non-markdown files use plain text chunking."""
    content = "{\n" + ",\n".join([f'  "rule_{i}": "value"' for i in range(3000)]) + "\n}"
    assert len(content) > _CHUNK_THRESHOLD

    chunks = _chunk_content("/test/.cursorrules", content)
    assert len(chunks) > 1


def test_mdc_file_uses_markdown_chunker():
    """Test that .mdc files are treated as markdown."""
    sections = [f"## Rule {i}\n\n{'description ' * 200}\n\n" for i in range(10)]
    content = "".join(sections)
    assert len(content) > _CHUNK_THRESHOLD

    chunks = _chunk_content("/test/rules.mdc", content)
    assert len(chunks) > 1


def test_extraction_tool_schema_has_required_fields():
    """Test that the tool schema defines all expected rule fields."""
    rule_props = EXTRACTION_TOOL["function"]["parameters"]["properties"]["rules"]["items"]["properties"]
    expected_fields = {"title", "description", "category", "tasks", "languages", "scope", "severity"}
    assert set(rule_props.keys()) == expected_fields


def test_extraction_tool_schema_enums():
    """Test that the tool schema enums match the model."""
    rule_props = EXTRACTION_TOOL["function"]["parameters"]["properties"]["rules"]["items"]["properties"]
    assert "must" in rule_props["severity"]["enum"]
    assert "should" in rule_props["severity"]["enum"]
    assert "can" in rule_props["severity"]["enum"]
    assert "repo" in rule_props["scope"]["enum"]
    assert "security" in rule_props["category"]["enum"]
    assert "best_practice" in rule_props["category"]["enum"]
    # tasks items should be constrained by enum
    assert "code-review" in rule_props["tasks"]["items"]["enum"]
    assert "code-generation" in rule_props["tasks"]["items"]["enum"]
    assert "code-questions" in rule_props["tasks"]["items"]["enum"]


def test_extraction_tool_schema_excludes_source_file():
    """Test that source_file is excluded from the tool schema (set after extraction)."""
    rule_props = EXTRACTION_TOOL["function"]["parameters"]["properties"]["rules"]["items"]["properties"]
    assert "source_file" not in rule_props


def test_system_prompt_contains_key_instructions():
    """Test that the system prompt contains key extraction instructions."""
    assert "SPECIFIC" in EXTRACTION_SYSTEM
    assert "DO NOT extract" in EXTRACTION_SYSTEM
    assert "Prioritize by severity" in EXTRACTION_SYSTEM


def _make_function_call_response(rules_data):
    """Helper to create a mock OpenAI Chat Completions API response with a tool call."""
    import json

    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps({"rules": rules_data})
    message = MagicMock()
    message.tool_calls = [tool_call]
    choice = MagicMock()
    choice.message = message
    return MagicMock(choices=[choice])


def test_extract_rules_from_file_uses_tool_choice():
    """Test that extraction uses tool_choice to force structured output."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_function_call_response(
        [
            {
                "title": "Use type hints",
                "description": "Always add type hints to function signatures.",
                "category": "readability",
                "tasks": ["code-review"],
                "languages": ["py"],
                "scope": "repo",
                "severity": "should",
            }
        ]
    )

    rule_file = RuleFile(path="/test/CLAUDE.md", tier=1, content_size=26)
    rules = extract_rules_from_file(rule_file, "# Use type hints everywhere", client=mock_client)

    # Verify tool_choice was passed
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["tool_choice"] == {"type": "function", "function": {"name": "extract_rules"}}
    assert call_kwargs["tools"] == [EXTRACTION_TOOL]
    assert call_kwargs["messages"][0] == {"role": "system", "content": EXTRACTION_SYSTEM}

    assert len(rules) == 1
    assert rules[0].title == "Use type hints"
    assert rules[0].category == "readability"
    assert rules[0].source_file == "/test/CLAUDE.md"


def test_extract_rules_returns_empty_on_error():
    """Test that extraction returns empty list on API error."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")

    rule_file = RuleFile(path="/test/CLAUDE.md", tier=1, content_size=9)
    rules = extract_rules_from_file(rule_file, "# Content", client=mock_client)

    assert rules == []


def test_extract_rules_returns_empty_on_no_function_call():
    """Test that extraction returns empty list when API returns no tool_calls."""
    mock_client = MagicMock()
    message = MagicMock()
    message.tool_calls = None
    choice = MagicMock()
    choice.message = message
    mock_client.chat.completions.create.return_value = MagicMock(choices=[choice])

    rule_file = RuleFile(path="/test/CLAUDE.md", tier=1, content_size=9)
    rules = extract_rules_from_file(rule_file, "# Content", client=mock_client)

    assert rules == []


def test_large_content_triggers_multiple_llm_calls():
    """Test that large markdown content triggers multiple LLM calls and merges rules."""

    def make_response(title):
        return _make_function_call_response(
            [
                {
                    "title": title,
                    "description": f"Rule from {title}",
                    "category": "best_practice",
                    "tasks": ["code-review"],
                    "languages": ["py"],
                    "scope": "repo",
                    "severity": "should",
                }
            ]
        )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        make_response("Rule from chunk 1"),
        make_response("Rule from chunk 2"),
        make_response("Rule from chunk 3"),
        make_response("Rule from chunk 4"),
        make_response("Rule from chunk 5"),
    ]

    # Build large markdown content that will be chunked
    sections = [f"## Section {i}\n\n{'Guidelines here. ' * 200}\n\n" for i in range(10)]
    content = "".join(sections)
    assert len(content) > _CHUNK_THRESHOLD

    rule_file = RuleFile(path="/test/AGENTS.md", tier=1, content_size=len(content))
    rules = extract_rules_from_file(rule_file, content, client=mock_client)

    # Should have called create multiple times (once per chunk)
    assert mock_client.chat.completions.create.call_count > 1
    # Should have rules from multiple chunks
    assert len(rules) > 1
    # All rules should have the same source_file
    for rule in rules:
        assert rule.source_file == "/test/AGENTS.md"


def test_small_content_single_llm_call():
    """Test that small content results in exactly one LLM call."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_function_call_response(
        [
            {
                "title": "Use type hints",
                "description": "Always add type hints.",
                "category": "readability",
                "tasks": ["code-review"],
                "languages": ["py"],
                "scope": "repo",
                "severity": "should",
            }
        ]
    )

    rule_file = RuleFile(path="/test/CLAUDE.md", tier=1, content_size=50)
    rules = extract_rules_from_file(rule_file, "# Small content\n\nUse type hints.", client=mock_client)

    assert mock_client.chat.completions.create.call_count == 1
    assert len(rules) == 1
