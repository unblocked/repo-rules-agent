"""Query and filter rules from an index."""

import logging
from pathlib import Path
from typing import Optional

from .models import Rule, RuleIndex

logger = logging.getLogger(__name__)


def query_rules(
    index: RuleIndex,
    task: Optional[str] = None,
    language: Optional[str] = None,
    scope: Optional[str] = None,
    severity: Optional[str] = None,
) -> list[Rule]:
    """
    Filter rules from an index based on criteria.

    Args:
        index: The RuleIndex to query
        task: Filter by task type (code-review, code-generation, code-questions)
        language: Filter by language (ts, py, go, etc.)
        scope: Filter by scope (repo, directory, file-pattern)
        severity: Filter by severity (must, should, can)

    Returns:
        List of matching Rule objects
    """
    rules = index.rules

    if task:
        rules = [r for r in rules if task in r.tasks]
        logger.debug(f"After task filter ({task}): {len(rules)} rules")

    if language:
        rules = [r for r in rules if language in r.languages or "all" in r.languages]
        logger.debug(f"After language filter ({language}): {len(rules)} rules")

    if scope:
        rules = [r for r in rules if r.scope == scope]
        logger.debug(f"After scope filter ({scope}): {len(rules)} rules")

    if severity:
        rules = [r for r in rules if r.severity == severity]
        logger.debug(f"After severity filter ({severity}): {len(rules)} rules")

    logger.info(f"Query returned {len(rules)} rules")
    return rules


def format_rules_for_prompt(
    rules: list[Rule],
    include_metadata: bool = True,
) -> str:
    """
    Format rules for injection into an LLM prompt.

    Args:
        rules: List of rules to format
        include_metadata: Whether to include source file and category

    Returns:
        Formatted string suitable for prompt injection
    """
    if not rules:
        return "No specific rules apply."

    lines = []
    for i, rule in enumerate(rules, 1):
        if include_metadata:
            source = f"(from {rule.source_file})"
            lines.append(f"{i}. {rule.display_text()} {source}")
        else:
            lines.append(f"- {rule.display_text()}")

    return "\n".join(lines)


def resolve_source_contents(
    index: RuleIndex,
    repo_path: Optional[Path] = None,
) -> dict[str, str]:
    """
    Resolve source file contents from an index.

    Checks embedded content on RuleFile first, falls back to reading
    from disk via repo_path.

    Args:
        index: The RuleIndex to resolve sources from
        repo_path: Optional path to the repository root for disk fallback

    Returns:
        Dict mapping source file path to content string
    """
    contents: dict[str, str] = {}
    for rule_file in index.files:
        if rule_file.content is not None:
            contents[rule_file.path] = rule_file.content
        elif repo_path:
            file_on_disk = repo_path / rule_file.path
            if file_on_disk.is_file():
                try:
                    contents[rule_file.path] = file_on_disk.read_text()
                except Exception as e:
                    logger.warning(f"Could not read {file_on_disk}: {e}")
    return contents


def format_rules_with_sources(
    rules: list[Rule],
    source_contents: dict[str, str],
    include_metadata: bool = True,
) -> str:
    """
    Format rules for prompt injection with deduplicated source file content appended.

    Args:
        rules: List of rules to format
        source_contents: Dict mapping source file path to content
        include_metadata: Whether to include source file and category in rule lines

    Returns:
        Formatted string with numbered rules followed by source file blocks
    """
    if not rules:
        return "No specific rules apply."

    # Format rules section
    rules_text = format_rules_for_prompt(rules, include_metadata=include_metadata)

    # Collect unique source files referenced by the rules
    seen: dict[str, str] = {}
    for rule in rules:
        path = rule.source_file
        if path and path not in seen and path in source_contents:
            seen[path] = source_contents[path]

    if not seen:
        return rules_text

    # Build source files section
    source_lines = ["\n\n--- Source Files ---"]
    for path, content in seen.items():
        # Use quadruple backticks to avoid breaking if content contains triple backticks
        source_lines.append(f"\n### {path}\n````\n{content}\n````")

    return rules_text + "\n".join(source_lines)


def get_rules_for_code_review(
    index: RuleIndex,
    language: Optional[str] = None,
) -> list[Rule]:
    """Get rules relevant for code review tasks."""
    return query_rules(index, task="code-review", language=language)


def get_rules_for_code_generation(
    index: RuleIndex,
    language: Optional[str] = None,
) -> list[Rule]:
    """Get rules relevant for code generation tasks."""
    return query_rules(index, task="code-generation", language=language)


def get_rules_for_code_questions(
    index: RuleIndex,
    language: Optional[str] = None,
) -> list[Rule]:
    """Get rules relevant for code questions tasks."""
    return query_rules(index, task="code-questions", language=language)
