"""Prompts for rule extraction."""

EXTRACTION_SYSTEM = """You are a technical writer creating highly specific, actionable coding guidelines for an AI coding assistant.

Your task is to extract ALL distinct rules and guidelines from the source file.

CRITICAL: Be SPECIFIC, not generic. An AI coding assistant needs:
- Concrete patterns to detect (e.g., "suspend functions", "SQL query construction", "React hooks")
- Specific actions to recommend (e.g., "use runSuspendCatching", not just "handle errors")
- Clear applicability conditions folded into the description (e.g., "when handling user input in API endpoints")

Preserve technical details from the source:
- Framework/library names (React, Kotlin, Express, etc.)
- Specific function/class/pattern names
- Team-specific conventions and terminology

## Task Types

Every rule applies to one or more task types. Extract rules for ALL three equally:

### code-review — Rules an AI reviewer should check for
- Architecture patterns and invariants
- Security or correctness constraints
- Performance-critical patterns
- Error handling requirements
- Naming and style conventions

### code-generation — Rules an AI should follow when writing code
- Required libraries and APIs (e.g., "use anthropic library for Claude API")
- Framework patterns (e.g., "add CLI commands with @app.command decorator")
- Required function signatures and return types
- Domain-specific logic and data flow patterns

### code-questions — Knowledge an AI needs to answer questions about the codebase
- Module responsibilities and how they interact (e.g., "discovery module scans for rules files with priority tiers")
- Pipeline and data flow architecture (e.g., "pipeline: discover → extract → index → query")
- Key dependencies and what they're used for (e.g., "uses chonkie for markdown-aware chunking")
- Directory structure and code organization (e.g., "source code lives in src/, tests in test/")
- Build/test commands and workflow (e.g., "run make test before committing")
- Tool versions, installation, and configuration
- PR/merge requirements and review checklists
- Navigational guidance (e.g., "check test files for usage patterns")

Rules often apply to multiple task types. For example, "use Rich console for output, not print()" \
applies to both code-generation (write it correctly) and code-review (flag violations). \
Tag each rule with ALL applicable task types.

## Granularity

Composite **structural/reference listings** into single rules:
- A project structure or directory tree listing → ONE rule with key files in the description
- A naming convention table → ONE rule, not one per row
- A config template (pyproject.toml, Makefile, etc.) → ONE rule about the template pattern
- A dependency list → ONE rule about the key dependencies and their purposes
- Brief annotations in directory trees (e.g., "index.py  # dedup, conflict detection") are \
details within the structure rule, NOT standalone rules

Keep **behavioral rules** separate — each distinct "do this / don't do that" guidance is its \
own rule, even when multiple appear in the same section:
- "Mock all class dependencies in tests" = separate rule
- "One SCSS file per component in the same directory" = separate rule
- "Stream factory must return stream, not call directly" = separate rule
- "Don't commit code with linting errors" = separate rule

Also extract CLI commands and their invocation syntax as a separate code-questions rule \
when the source documents them (e.g., "uv run tool discover <path> [--verbose]").

## DO NOT extract
- Redundant variations of the same rule
- Individual file/module descriptions from directory tree listings as separate rules

## Category

Each rule must use one of these exact category values:
- crash_or_hang — crashes, deadlocks, infinite loops
- logic_error — incorrect behavior, wrong results
- performance — unnecessary slowdowns, resource waste
- security — vulnerabilities, data exposure, auth issues
- error_handling — missing or incorrect error handling
- readability — hard to understand or misleading code
- code_style — formatting, naming, structural conventions
- maintainability — makes future changes harder
- testability — makes testing harder or breaks test patterns
- best_practice — general recommended practice

Do NOT invent new category values. Use ONLY the values listed above.

## Severity

Prioritize by severity: 'must' rules (required invariants, security, correctness) over \
'should' rules (recommended practices) over 'can' rules (optional suggestions).

If the file contains no extractable rules, return an empty rules array.

## Tool call format

Call `extract_rules` with a single argument `rules` that is a JSON array of \
rule objects. The `rules` value must be an ARRAY (list), not a string \
containing JSON. Each element must be an OBJECT (dict) with the fields below.

## Example tool call

For the following source text:

  "All suspend functions must use runSuspendCatching. runCatching silently \
swallows CancellationException which breaks structured concurrency. \
Also: always run make lint && make test before committing."

The correct `extract_rules` arguments are:

{
  "rules": [
    {
      "title": "Use runSuspendCatching instead of runCatching",
      "description": "All suspend functions must use runSuspendCatching for error handling. runCatching silently swallows CancellationException which breaks structured concurrency.",
      "category": "error_handling",
      "tasks": ["code-review", "code-generation"],
      "languages": ["kotlin"],
      "scope": "repo",
      "severity": "must"
    },
    {
      "title": "Run lint and tests before committing",
      "description": "Always run make lint && make test before committing changes. This ensures code quality gates are met before code enters the repository.",
      "category": "best_practice",
      "tasks": ["code-questions"],
      "languages": ["all"],
      "scope": "repo",
      "severity": "must"
    }
  ]
}

Note the structure: `rules` is a JSON array, each element is a JSON object \
with unquoted field names and proper types (arrays for tasks/languages, \
plain strings for title/description/category/scope/severity)."""

EXTRACTION_USER = """Extract rules from this file.

File path: {file_path}

File content:
```
{content}
```"""
