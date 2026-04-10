# repo-rules-agent Development Guide

## Architecture

The pipeline flows: **discover** → **extract** → **index** → **query**

1. **Discovery** (`rules/discovery.py`): Scans a repo for rules files (CLAUDE.md, .cursorrules, etc.) organized by priority tiers defined in `config.toml`.
2. **Extraction** (`rules/extractor.py`): Sends file contents to Claude via tool use to extract structured rules. Large files are chunked using `chonkie` (markdown-aware chunking).
3. **Indexing** (`rules/index.py`): Deduplicates rules (text similarity), detects conflicts (contradictory severity), and builds a `RuleIndex`.
4. **Query** (`rules/query.py`): Filters rules by task, language, scope, severity. Formats output as table, JSON, or prompt.
5. **Eval** (`rules/eval.py`): Uses an LLM judge to score extraction quality (precision, recall, F1).

## Data Flow

- `discover_rules_files(repo_path)` → `list[RuleFile], dict[str, str]` (files + contents)
- `extract_rules_from_files(rule_files, contents)` → `list[ProcessedFile]`
- `build_index(repo_path, processed_files)` → `RuleIndex`
- `query_rules(index, task=, lang=, ...)` → `list[Rule]`

## Adding a New CLI Command

1. Add the command function in `cli.py` with `@app.command(name="command-name")`
2. Use `typer.Argument` / `typer.Option` for parameters
3. Use `console` (Rich) for output, not `print()`
4. Add tests using `typer.testing.CliRunner` in `tests/test_<name>.py`
5. Update the bundled skill files if the command should be user-facing:
   - `src/rules_agent/skill/SKILL.md` (bundled package copy)
   - `skills/repo-rules/SKILL.md` (plugin copy)
   - `.claude/skills/repo-rules/SKILL.md` (local dev copy, uses `poetry run`)

## Adding Discovery Patterns

Edit `src/rules_agent/config.toml` to add new file patterns or tiers. The config is loaded via pydantic-settings at module import time.

## Testing Conventions

- Tests live in `tests/test_*.py`, one file per module
- Mock all LLM/API calls — tests must run offline
- Use `tmp_path` fixture for filesystem tests
- Use `typer.testing.CliRunner` for CLI integration tests
- Run `make test` (which runs `poetry run pytest tests -v`)

## Dependencies

- `typer` + `rich` — CLI framework and terminal output
- `pydantic` v2 — data models and validation
- `openai` — OpenAI SDK client (works with any OpenAI-compatible API: Ollama, Anthropic, OpenAI, etc.)
- `chonkie` — markdown-aware text chunking
- `git` CLI — git operations (blob SHA computation via `git ls-tree`)
- `pydantic-settings` — configuration management (TOML + env var loading)
