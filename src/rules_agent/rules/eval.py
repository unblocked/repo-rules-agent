"""LLM-as-judge evaluation of rule extraction quality."""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel, Field

from ..config import settings
from .eval_prompts import JUDGE_SYSTEM, JUDGE_USER
from .models import Rule, RuleIndex

logger = logging.getLogger(__name__)

_cfg_llm = settings.llm

DEFAULT_JUDGE_MODEL = _cfg_llm.judge_model


class FileEvaluation(BaseModel):
    """Evaluation result for a single file's rule extraction."""

    # Metadata fields (set by us, excluded from tool schema)
    file_path: str = Field(default="", description="Path to the evaluated file")
    source_content_size: int = Field(default=0, description="Size of source content in chars")
    rule_count: int = Field(default=0, description="Number of extracted rules evaluated")

    # Judge-provided classification fields
    source_rule_count: int = Field(
        default=0,
        description="Number of distinct rules/guidelines identified in the source",
    )
    matched_rules: list[str] = Field(
        default_factory=list,
        description="Extracted rules that correctly match a source rule",
    )
    missed_rules: list[str] = Field(
        default_factory=list,
        description="Source rules that were NOT captured by any extracted rule",
    )
    hallucinated_rules: list[str] = Field(
        default_factory=list,
        description="Extracted rules that describe something NOT present in the source",
    )
    redundant_rules: list[str] = Field(
        default_factory=list,
        description="Extracted rules that are over-fragmented duplicates of another matched rule",
    )
    reasoning: str = Field(default="", description="Brief reasoning for the classification decisions")

    @property
    def tp(self) -> int:
        return len(self.matched_rules)

    @property
    def fp(self) -> int:
        return len(self.hallucinated_rules) + len(self.redundant_rules)

    @property
    def fn(self) -> int:
        return len(self.missed_rules)

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom > 0 else 1.0

    @property
    def recall(self) -> float:
        # Source-side: what fraction of source rules are covered?
        # Covered = source_rule_count - missed (accounts for composite matching)
        if self.source_rule_count == 0:
            return 1.0
        covered = self.source_rule_count - self.fn
        # Clamp: judge may list more missed rules than source_rule_count
        return max(0.0, covered / self.source_rule_count)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


class EvalSummary(BaseModel):
    """Summary of evaluation across all files in an index."""

    repo: str = Field(default="", description="Repository path")
    file_evaluations: list[FileEvaluation] = Field(default_factory=list)
    overall_precision: float = Field(default=0.0, description="Micro-averaged precision across all files")
    overall_recall: float = Field(default=0.0, description="Micro-averaged recall across all files")
    overall_f1: float = Field(default=0.0, description="Micro-averaged F1 across all files")
    total_rules: int = Field(default=0, description="Total extracted rules evaluated")
    total_source_rules: int = Field(default=0, description="Total source rules identified by judge")
    total_files: int = Field(default=0, description="Total files evaluated")
    judge_model: str = Field(default=DEFAULT_JUDGE_MODEL)


# Fields the LLM should NOT fill (set by us)
_METADATA_FIELDS = {"file_path", "source_content_size", "rule_count"}


def _build_judge_tool() -> dict:
    """Build the judge tool schema from the FileEvaluation model."""
    schema = FileEvaluation.model_json_schema()
    schema.pop("title", None)
    schema.pop("description", None)
    # Remove metadata fields the LLM shouldn't set
    props = schema.get("properties", {})
    for field_name in _METADATA_FIELDS:
        props.pop(field_name, None)
    # Clean up property metadata
    for prop in props.values():
        prop.pop("title", None)
        prop.pop("default", None)
    return {
        "type": "function",
        "function": {
            "name": "submit_evaluation",
            "description": "Submit the evaluation classification for the file.",
            "parameters": schema,
        },
    }


JUDGE_TOOL = _build_judge_tool()


def _parse_json_from_content(content: str | None, label: str) -> dict | None:
    """Try to extract a JSON object from text content.

    Handles JSON wrapped in markdown code fences or bare JSON.  Returns the
    parsed dict on success, or ``None`` on failure (with an error logged).
    """
    if not content:
        logger.error(f"{label}: no tool_calls and no text content in response")
        return None

    stripped = content.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", stripped, re.DOTALL)
    json_str = fence_match.group(1).strip() if fence_match else stripped

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"{label}: failed to parse JSON from content fallback: {e}")
        return None

    if isinstance(parsed, dict):
        logger.info(f"{label}: parsed evaluation from text content fallback")
        return parsed

    logger.error(f"{label}: unexpected JSON type in content fallback: {type(parsed).__name__}")
    return None


def _format_rules_for_judge(rules: list[Rule]) -> str:
    """Format extracted rules as numbered markdown for the judge prompt."""
    if not rules:
        return "(no rules extracted)"
    lines = []
    for i, rule in enumerate(rules, 1):
        lines.append(
            f"{i}. **{rule.title}** [{rule.category.value}] "
            f"(severity: {rule.severity}, scope: {rule.scope})\n"
            f"   {rule.description}\n"
            f"   Languages: {', '.join(rule.languages)} | "
            f"Tasks: {', '.join(rule.tasks) if rule.tasks else 'none'}"
        )
    return "\n\n".join(lines)


def evaluate_file(
    file_path: str,
    source_content: str,
    rules: list[Rule],
    client: OpenAI,
    model: str = DEFAULT_JUDGE_MODEL,
) -> FileEvaluation:
    """Evaluate extraction quality for a single file using LLM judge."""
    rules_text = _format_rules_for_judge(rules)
    user_prompt = JUDGE_USER.format(
        file_path=file_path,
        source_content=source_content,
        rule_count=len(rules),
        rules_text=rules_text,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            tools=[JUDGE_TOOL],
            tool_choice={"type": "function", "function": {"name": "submit_evaluation"}},
            max_tokens=_cfg_llm.judge_max_tokens,
        )

        # Find the tool call in the response
        message = response.choices[0].message if response.choices else None
        tool_calls = message.tool_calls if message else None

        if tool_calls:
            tool_input = json.loads(tool_calls[0].function.arguments)
        else:
            # Fallback: parse JSON from text content for models that ignore tool_choice
            tool_input = _parse_json_from_content(message.content if message else None, file_path)
            if tool_input is None:
                return FileEvaluation(
                    file_path=file_path,
                    source_content_size=len(source_content),
                    rule_count=len(rules),
                    reasoning="Judge evaluation failed: no tool_calls in response",
                )
        return FileEvaluation(
            file_path=file_path,
            source_content_size=len(source_content),
            rule_count=len(rules),
            **tool_input,
        )

    except Exception as e:
        logger.error(f"Judge evaluation failed for {file_path}: {e}")
        return FileEvaluation(
            file_path=file_path,
            source_content_size=len(source_content),
            rule_count=len(rules),
            reasoning=f"Judge evaluation failed: {e}",
        )


def evaluate_index(
    rule_index: RuleIndex,
    source_contents: dict[str, str],
    client: OpenAI,
    model: str = DEFAULT_JUDGE_MODEL,
) -> EvalSummary:
    """Evaluate extraction quality for all files in an index."""
    evaluations: list[FileEvaluation] = []

    for rule_file in rule_index.files:
        content = source_contents.get(rule_file.path)
        if content is None:
            logger.warning(f"No source content for {rule_file.path}, skipping eval")
            continue

        file_eval = evaluate_file(
            file_path=rule_file.path,
            source_content=content,
            rules=rule_file.rules,
            client=client,
            model=model,
        )
        evaluations.append(file_eval)

    total_files = len(evaluations)
    total_rules = sum(e.rule_count for e in evaluations)
    total_source_rules = sum(e.source_rule_count for e in evaluations)

    # Micro-averaged metrics across all files
    total_tp = sum(e.tp for e in evaluations)
    total_fp = sum(e.fp for e in evaluations)
    total_fn = sum(e.fn for e in evaluations)

    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
    # Source-side recall: what fraction of all source rules are covered?
    # Clamp: judge may list more missed rules than source_rule_count
    overall_recall = max(0.0, (total_source_rules - total_fn) / total_source_rules) if total_source_rules > 0 else 1.0
    overall_f1 = (
        2 * overall_precision * overall_recall / (overall_precision + overall_recall)
        if (overall_precision + overall_recall) > 0
        else 0.0
    )

    return EvalSummary(
        repo=rule_index.repo,
        file_evaluations=evaluations,
        overall_precision=overall_precision,
        overall_recall=overall_recall,
        overall_f1=overall_f1,
        total_rules=total_rules,
        total_source_rules=total_source_rules,
        total_files=total_files,
        judge_model=model,
    )


def load_index_with_sources(
    index_path: Path,
    repo_path: Optional[Path] = None,
) -> tuple[RuleIndex, dict[str, str]]:
    """Load a rule index JSON and extract source contents.

    Source content is read from embedded 'content' fields in file entries
    if present, otherwise falls back to reading from disk via repo_path.

    Returns:
        Tuple of (RuleIndex, dict mapping file_path -> source content)
    """
    from .query import resolve_source_contents

    raw = json.loads(index_path.read_text())
    rule_index = RuleIndex.model_validate(raw)
    source_contents = resolve_source_contents(rule_index, repo_path)

    return rule_index, source_contents
