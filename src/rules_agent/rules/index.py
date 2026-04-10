"""Merge rules from multiple files and detect conflicts."""

import logging
from difflib import SequenceMatcher
from typing import Optional

from ..config import settings
from .discovery import compute_rules_source_sha
from .models import Rule, RuleFile, RuleIndex

logger = logging.getLogger(__name__)

_cfg_dedup = settings.dedup

SIMILARITY_THRESHOLD = _cfg_dedup.similarity_threshold


def _text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity ratio between two texts."""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def _rules_conflict(rule1: Rule, rule2: Rule) -> bool:
    """
    Check if two rules might conflict.

    Conflicts are detected when:
    - Rules have similar text but different severity
    - Rules have overlapping scope/tasks but contradictory guidance
    """
    # Must have overlapping tasks
    if not set(rule1.tasks) & set(rule2.tasks):
        return False

    # Must have overlapping languages
    if "all" not in rule1.languages and "all" not in rule2.languages:
        if not set(rule1.languages) & set(rule2.languages):
            return False

    # Check for contradictory severity on similar rules
    similarity = _text_similarity(rule1.display_text(), rule2.display_text())
    if similarity > _cfg_dedup.conflict_lower_bound and similarity < SIMILARITY_THRESHOLD:
        # Similar but not duplicate - check for severity conflict
        if rule1.severity != rule2.severity:
            return True

    return False


def _dedupe_rules(rules: list[Rule]) -> list[Rule]:
    """Remove duplicate rules based on text similarity."""
    if not rules:
        return []

    deduped: list[Rule] = []
    for rule in rules:
        is_duplicate = False
        for existing in deduped:
            if _text_similarity(rule.display_text(), existing.display_text()) >= SIMILARITY_THRESHOLD:
                is_duplicate = True
                # Keep the one from higher priority tier (lower tier number)
                # Since rules are processed in tier order, existing is kept
                logger.debug(f"Skipping duplicate rule: {rule.display_text()[:50]}...")
                break
        if not is_duplicate:
            deduped.append(rule)

    return deduped


def _detect_conflicts(rules: list[Rule]) -> list[tuple[str, str]]:
    """Detect potentially conflicting rules."""
    conflicts: list[tuple[str, str]] = []

    for i, rule1 in enumerate(rules):
        for rule2 in rules[i + 1 :]:
            if _rules_conflict(rule1, rule2):
                conflicts.append((rule1.display_text(), rule2.display_text()))
                logger.warning(
                    f"Potential conflict detected:\n"
                    f"  Rule 1 ({rule1.source_file}): {rule1.display_text()[:50]}...\n"
                    f"  Rule 2 ({rule2.source_file}): {rule2.display_text()[:50]}..."
                )

    return conflicts


def build_index(
    repo_path: str,
    rule_files: list[RuleFile],
    contents: Optional[dict[str, str]] = None,
    embed_content: bool = False,
) -> RuleIndex:
    """
    Build a unified index from multiple rule files.

    Args:
        repo_path: Path to the repository root
        rule_files: List of RuleFile objects with extracted rules
        contents: Optional dict mapping file paths to source content
        embed_content: When True and contents provided, embed source content in RuleFile entries

    Returns:
        RuleIndex with merged rules and detected conflicts
    """
    # Optionally embed source content in rule files
    if embed_content and contents:
        for rule_file in rule_files:
            if rule_file.path in contents:
                rule_file.content = contents[rule_file.path]

    # Collect all rules, preserving tier order
    all_rules: list[Rule] = []
    for rule_file in sorted(rule_files, key=lambda f: f.tier):
        all_rules.extend(rule_file.rules)

    logger.info(f"Total rules before deduplication: {len(all_rules)}")

    # Deduplicate
    deduped_rules = _dedupe_rules(all_rules)
    logger.info(f"Total rules after deduplication: {len(deduped_rules)}")

    # Detect conflicts
    conflicts = _detect_conflicts(deduped_rules)
    if conflicts:
        logger.warning(f"Detected {len(conflicts)} potential conflicts")

    source_sha = compute_rules_source_sha(repo_path, rule_files)

    return RuleIndex(
        repo=repo_path,
        source_sha=source_sha,
        files=rule_files,
        rules=deduped_rules,
        conflicts=conflicts,
    )
