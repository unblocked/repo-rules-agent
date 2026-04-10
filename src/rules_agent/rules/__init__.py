"""Rules extraction and indexing modules."""

from ..config import Settings, settings
from .models import Rule, RuleFile, RuleIndex
from .discovery import discover_rules_files
from .eval import (
    EvalSummary,
    FileEvaluation,
    evaluate_file,
    evaluate_index,
    load_index_with_sources,
)
from .extractor import extract_rules_from_file, extract_rules_from_files
from .index import build_index
from .query import (
    format_rules_for_prompt,
    format_rules_with_sources,
    query_rules,
    resolve_source_contents,
)

__all__ = [
    "Settings",
    "settings",
    "Rule",
    "RuleFile",
    "RuleIndex",
    "discover_rules_files",
    "extract_rules_from_file",
    "extract_rules_from_files",
    "build_index",
    "query_rules",
    "format_rules_for_prompt",
    "format_rules_with_sources",
    "resolve_source_contents",
    "FileEvaluation",
    "EvalSummary",
    "evaluate_file",
    "evaluate_index",
    "load_index_with_sources",
]
