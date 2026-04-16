"""Extract rules from file content using an LLM via the OpenAI Chat Completions API."""

import json
import logging
import os
import re
from typing import Optional

from chonkie import RecursiveChunker, RecursiveLevel, RecursiveRules
from openai import OpenAI

from ..config import settings
from .models import Rule, RuleFile
from .prompts import EXTRACTION_SYSTEM, EXTRACTION_USER

logger = logging.getLogger(__name__)

_cfg_chunking = settings.chunking
_cfg_llm = settings.llm


def _build_extraction_tool() -> dict:
    """Build the extraction tool schema from the Rule Pydantic model."""
    schema = Rule.model_json_schema()
    # Inline $defs references for Claude tool use compatibility
    defs = schema.pop("$defs", {})
    for prop in schema.get("properties", {}).values():
        if "$ref" in prop:
            ref_name = prop["$ref"].split("/")[-1]
            if ref_name in defs:
                ref_schema = defs[ref_name]
                prop.pop("$ref")
                # Preserve field-level description over enum class docstring
                field_desc = prop.pop("description", None)
                prop.update(ref_schema)
                if field_desc:
                    prop["description"] = field_desc
    # Remove model-level metadata not needed for tool schema
    schema.pop("title", None)
    schema.pop("description", None)
    # Remove fields the LLM shouldn't fill (set by us after extraction)
    schema.get("properties", {}).pop("source_file", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
        prop.pop("default", None)
    return {
        "type": "function",
        "function": {
            "name": "extract_rules",
            "description": "Extract coding rules and guidelines from the file content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rules": {
                        "type": "array",
                        "description": "List of extracted rules. Empty array if no rules found.",
                        "items": schema,
                    },
                },
                "required": ["rules"],
            },
        },
    }


EXTRACTION_TOOL = _build_extraction_tool()

_CHUNK_THRESHOLD = _cfg_chunking.threshold_chars
_CHUNK_SIZE = _cfg_chunking.chunk_size_chars
_MARKDOWN_EXTS = _cfg_chunking.markdown_extensions

_MARKDOWN_RULES = RecursiveRules(
    levels=[
        RecursiveLevel(
            delimiters=["\n# ", "\n## ", "\n### ", "\n#### ", "\n##### ", "\n###### "],
            whitespace=False,
            include_delim="next",
        ),
        RecursiveLevel(
            delimiters=["\n\n", "\r\n\r\n"],
            whitespace=False,
            include_delim="prev",
        ),
        RecursiveLevel(
            delimiters=[". ", "! ", "? "],
            whitespace=False,
            include_delim="prev",
        ),
        RecursiveLevel(
            delimiters=None,
            whitespace=True,
            include_delim="prev",
        ),
    ]
)

_markdown_chunker = RecursiveChunker(
    "character",
    chunk_size=_CHUNK_SIZE,
    rules=_MARKDOWN_RULES,
    min_characters_per_chunk=_cfg_chunking.min_chars_per_chunk,
)

_plain_chunker = RecursiveChunker(
    "character",
    chunk_size=_CHUNK_SIZE,
    min_characters_per_chunk=_cfg_chunking.min_chars_per_chunk,
)


def _chunk_content(path: str, content: str) -> list[str]:
    """
    Split content into chunks suitable for LLM extraction.

    Small files are returned as-is. Markdown files are split on headings
    using chonkie's RecursiveChunker with markdown rules; other file types
    use the default recursive chunker.
    """
    if len(content) <= _CHUNK_THRESHOLD:
        return [content]

    ext = os.path.splitext(path)[1].lower()
    chunker = _markdown_chunker if ext in _MARKDOWN_EXTS else _plain_chunker
    chunks = chunker.chunk(content)
    return [c.text for c in chunks]


def _parse_json_from_content(content: str | None, label: str) -> dict | None:
    """Try to extract a JSON object with a 'rules' key from text content.

    Handles JSON wrapped in markdown code fences or bare JSON.  Returns the
    parsed dict on success, or ``None`` on failure (with an error logged).
    """
    if not content:
        logger.error(f"{label}: no tool_calls and no text content in response")
        return None

    # Strip markdown code fences if present
    stripped = content.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", stripped, re.DOTALL)
    json_str = fence_match.group(1).strip() if fence_match else stripped

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"{label}: failed to parse JSON from content fallback: {e}")
        return None

    # The content may be {"rules": [...]} or a bare [...] array
    if isinstance(parsed, list):
        logger.info(f"{label}: parsed rules array from text content fallback")
        return {"rules": parsed}
    if isinstance(parsed, dict):
        if "rules" in parsed:
            logger.info(f"{label}: parsed rules object from text content fallback")
            return parsed
        logger.error(f"{label}: JSON object missing 'rules' key: {list(parsed.keys())}")
        return None

    logger.error(f"{label}: unexpected JSON type in content fallback: {type(parsed).__name__}")
    return None


def _call_llm_for_chunk(
    client: OpenAI,
    rule_file: RuleFile,
    chunk: str,
    chunk_label: str,
) -> list[Rule]:
    """Call the LLM to extract rules from a single chunk of content."""
    user_prompt = EXTRACTION_USER.format(
        file_path=rule_file.path,
        content=chunk,
    )

    response = client.chat.completions.create(
        model=_cfg_llm.extraction_model,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "function", "function": {"name": "extract_rules"}},
        max_tokens=_cfg_llm.extraction_max_tokens,
    )

    # Find the tool call in the response
    message = response.choices[0].message if response.choices else None
    tool_calls = message.tool_calls if message else None

    if tool_calls:
        try:
            tool_input = json.loads(tool_calls[0].function.arguments)
        except json.JSONDecodeError as e:
            logger.error(f"{chunk_label}: failed to parse function arguments: {e}")
            return []
    else:
        # Fallback: some models (e.g. Ollama) ignore tool_choice and return
        # the JSON in the message content instead. Try to extract it.
        tool_input = _parse_json_from_content(message.content if message else None, chunk_label)
        if tool_input is None:
            return []

    if "rules" not in tool_input:
        logger.warning(
            f"{chunk_label}: tool response missing 'rules' key. "
            f"Keys returned: {list(tool_input.keys())}. "
            f"Response (truncated): {str(tool_input)[:500]}"
        )
        return []

    rules = []
    for i, rule_data in enumerate(tool_input["rules"]):
        if not isinstance(rule_data, dict):
            logger.error(
                f"{chunk_label}: rule[{i}] is {type(rule_data).__name__}, expected dict. "
                f"Value (truncated): {str(rule_data)[:200]}"
            )
            continue
        try:
            rule = Rule(
                source_file=rule_file.path,
                **rule_data,
            )
            rules.append(rule)
        except Exception as e:
            logger.error(f"{chunk_label}: rule[{i}] failed to parse: {e}. Data: {str(rule_data)[:300]}")

    return rules


def _make_client(client: Optional[OpenAI] = None) -> Optional[OpenAI]:
    """Return the given client or create one from config."""
    if client is not None:
        return client
    api_key = os.environ.get(_cfg_llm.api_key_env, "ollama")
    return OpenAI(base_url=_cfg_llm.base_url, api_key=api_key)


def extract_rules_from_file(
    rule_file: RuleFile,
    content: str,
    client: Optional[OpenAI] = None,
) -> list[Rule]:
    """
    Extract rules from a single file using an LLM.

    Args:
        rule_file: The RuleFile metadata
        content: Raw file content to extract rules from
        client: Optional OpenAI client (creates one if not provided)

    Returns:
        List of extracted Rule objects
    """
    client = _make_client(client)

    chunks = _chunk_content(rule_file.path, content)
    logger.info(f"Extracting rules from {rule_file.path} ({len(chunks)} chunk(s))")

    all_rules: list[Rule] = []
    for idx, chunk in enumerate(chunks):
        chunk_label = f"{rule_file.path}[chunk {idx + 1}/{len(chunks)}]" if len(chunks) > 1 else rule_file.path
        try:
            rules = _call_llm_for_chunk(client, rule_file, chunk, chunk_label)
            all_rules.extend(rules)
        except Exception as e:
            logger.error(f"Failed to extract rules from {chunk_label}: {e}", exc_info=True)

    logger.info(f"Extracted {len(all_rules)} rules from {rule_file.path}")
    return all_rules


def extract_rules_from_files(
    rule_files: list[RuleFile],
    contents: dict[str, str],
    client: Optional[OpenAI] = None,
) -> list[RuleFile]:
    """
    Extract rules from multiple files.

    Args:
        rule_files: List of RuleFile objects to process
        contents: Mapping of file path to raw content
        client: Optional OpenAI client (creates one if not provided)

    Returns:
        List of RuleFile objects with rules populated
    """
    client = _make_client(client)

    processed_files = []
    for rule_file in rule_files:
        content = contents.get(rule_file.path, "")
        rules = extract_rules_from_file(rule_file, content, client)
        processed_file = RuleFile(
            path=rule_file.path,
            tier=rule_file.tier,
            content_size=rule_file.content_size,
            rules=rules,
        )
        processed_files.append(processed_file)

    return processed_files
