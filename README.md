# Rules Agent

Extract and index AI coding instructions from rules files (CLAUDE.md, AGENTS.md, .cursorrules, etc.).

## Dependencies

- [`uv`](https://docs.astral.sh/uv/) — Python package manager
- [`git`](https://git-scm.com/) — used for blob SHA computation during indexing
- [Ollama](https://ollama.com/) — required if you use the default local provider; not needed if you configure OpenAI, Anthropic, or another hosted provider

## Setup

```bash
# Install dependencies
uv sync
```

## Configuration

The tool works with any OpenAI-compatible API provider. By default, it connects to a local [Ollama](https://ollama.com/) instance; OpenAI and Anthropic are also supported.

Copy `.env.example` to `.env` and uncomment the provider you want to use:

```bash
cp .env.example .env
# Edit .env with your API keys
```

The `.env` file is gitignored and loaded automatically at startup via `python-dotenv`. Shell environment variables take precedence over `.env` values, so you can always override a `.env` setting with an explicit export.

### Providers

**Local (Ollama — default, no API key needed):**

```bash
ollama pull qwen3-coder:30b
uv run repo-rules-agent index /path/to/repo
```

**Anthropic** (add to `.env`):

```
RULES_AGENT_LLM__BASE_URL=https://api.anthropic.com/v1
RULES_AGENT_LLM__API_KEY_ENV=ANTHROPIC_API_KEY
RULES_AGENT_LLM__EXTRACTION_MODEL=claude-haiku-4-5
ANTHROPIC_API_KEY=sk-ant-...
```

**OpenAI** (add to `.env`):

```
RULES_AGENT_LLM__BASE_URL=https://api.openai.com/v1
RULES_AGENT_LLM__API_KEY_ENV=OPENAI_API_KEY
RULES_AGENT_LLM__EXTRACTION_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-proj-...
```

All LLM settings can also be changed in `src/rules_agent/config.toml`.

## Usage

### Discover rules files

Check which files would be processed without extracting:

```bash
uv run repo-rules-agent discover /path/to/repo
```

### Index a repository

Extract rules from all discovered files. The index is written to a per-user cache directory by default (invisible to the repo), and `query` reads from the same place.

```bash
# Index the current repo (writes to the cache; prints the resolved path)
uv run repo-rules-agent index /path/to/repo

# Override the output path
uv run repo-rules-agent index /path/to/repo -o rules-index.json
```

### Query rules

Filter and format rules from the cached index. With no positional argument, `query` reads the cached index for the current directory.

```bash
# Table format (default)
uv run repo-rules-agent query --task code-review

# JSON format
uv run repo-rules-agent query --task code-review --format json

# Prompt format (for injection into LLM prompts)
uv run repo-rules-agent query --task code-review --format prompt

# Filter by language
uv run repo-rules-agent query --task code-review --lang py

# Filter by severity
uv run repo-rules-agent query --severity must

# Query an explicit index file instead of the cache
uv run repo-rules-agent query rules-index.json --task code-review
```

### Inspect the cache

```bash
uv run repo-rules-agent cache path          # where the cwd's index lives
uv run repo-rules-agent cache list          # all cached indices, newest first
uv run repo-rules-agent cache clear --all   # wipe the cache
```

### Evaluate extraction quality

Score how well the LLM extracted rules using a judge model:

```bash
# Evaluate from an existing index (requires --repo to read source files)
uv run repo-rules-agent eval rules-index.json --repo /path/to/repo

# Or run the full pipeline (discover → extract → eval) from a directory
uv run repo-rules-agent eval /path/to/repo

# Save results to file
uv run repo-rules-agent eval rules-index.json --repo /path/to/repo -o eval-results.json

# Use a different judge model
uv run repo-rules-agent eval /path/to/repo --judge-model gpt-4o-mini
```

The judge scores each file on precision (no hallucinated rules), recall (no missed rules), and F1.

### Install as an agent skill

The bundled `SKILL.md` works with any agent that speaks the open skill format — Claude Code, OpenAI Codex CLI, and Cursor. Only the destination directory differs.

```bash
# Claude Code (default), repo-local
uv run repo-rules-agent install-skill

# Claude Code, user-wide
uv run repo-rules-agent install-skill --scope user

# Codex CLI (user-scope only — Codex doesn't support project-scope skills)
uv run repo-rules-agent install-skill --target codex --scope user

# Cursor, repo-local
uv run repo-rules-agent install-skill --target cursor

# All supported agents at once
uv run repo-rules-agent install-skill --target all --scope user
```

| Target | Project scope | User scope |
|---|---|---|
| `claude` (default) | `.claude/skills/repo-rules/SKILL.md` | `~/.claude/skills/repo-rules/SKILL.md` |
| `codex` | n/a | `~/.codex/skills/repo-rules/SKILL.md` |
| `cursor` | `.cursor/skills/repo-rules/SKILL.md` | `~/.cursor/skills/repo-rules/SKILL.md` |
| `all` | claude + cursor (codex skipped) | claude + codex + cursor |

## Discovery Tiers

Files are discovered in priority order:

| Tier | Files |
|------|-------|
| 1 | Root files: AGENTS.md, CLAUDE.md, CONTRIBUTING.md, .cursorrules, etc. |
| 2 | Tool dirs: .claude/CLAUDE.md, .github/copilot-instructions.md |
| 3 | Rules dirs: .cursor/rules/*.mdc, .github/instructions/*.md |
| 4 | Recursive: **/CLAUDE.md, **/AGENTS.md, **/.rules/* |

## Rule Model

Each extracted rule includes:

- `title`: Concise rule title with key technical context
- `description`: 2-3 sentence description (what, when, why)
- `category`: crash_or_hang, logic_error, performance, security, error_handling, readability, code_style, maintainability, testability, best_practice
- `tasks`: code-review, code-generation, code-questions
- `languages`: ts, py, go, etc. or "all"
- `scope`: repo, directory, file-pattern
- `severity`: must, should, can
- `source_file`: Origin file for tracing

## Development

```bash
# Format code
make format

# Run tests
make test

# Format + test
make check
```

## Support

Please open issues and feature requests here: https://github.com/unblocked/repo-rules-agent/issues

Copyright © NextChapter Software
