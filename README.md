# Rules Agent

Extract and index AI coding instructions from rules files (CLAUDE.md, AGENTS.md, .cursorrules, etc.).

## Setup

```bash
# Install dependencies
poetry install
```

## Configuration

The tool uses the OpenAI SDK, so it works with any OpenAI-compatible API provider. By default it connects to a local [Ollama](https://ollama.com/) instance.

**Local (Ollama — default, no API key needed):**

```bash
ollama pull gemma4
poetry run repo-rules-agent index /path/to/repo
```

**Anthropic:**

```bash
export RULES_AGENT_LLM__BASE_URL=https://api.anthropic.com/v1
export RULES_AGENT_LLM__API_KEY_ENV=ANTHROPIC_API_KEY
export RULES_AGENT_LLM__EXTRACTION_MODEL=claude-haiku-4-5-20251001
export ANTHROPIC_API_KEY=your-api-key
```

**OpenAI:**

```bash
export RULES_AGENT_LLM__BASE_URL=https://api.openai.com/v1
export RULES_AGENT_LLM__API_KEY_ENV=OPENAI_API_KEY
export RULES_AGENT_LLM__EXTRACTION_MODEL=gpt-4o-mini
export OPENAI_API_KEY=your-api-key
```

All LLM settings can also be changed in `src/rules_agent/config.toml`.

## Usage

### Discover rules files

Check which files would be processed without extracting:

```bash
poetry run repo-rules-agent discover /path/to/repo
```

### Index a repository

Extract rules from all discovered files:

```bash
# Output to stdout
poetry run repo-rules-agent index /path/to/repo

# Output to file
poetry run repo-rules-agent index /path/to/repo -o rules-index.json
```

### Query rules

Filter and format rules from an index:

```bash
# Table format (default)
poetry run repo-rules-agent query rules-index.json --task code-review

# JSON format
poetry run repo-rules-agent query rules-index.json --task code-review --format json

# Prompt format (for injection into LLM prompts)
poetry run repo-rules-agent query rules-index.json --task code-review --format prompt

# Filter by language
poetry run repo-rules-agent query rules-index.json --task code-review --lang py

# Filter by severity
poetry run repo-rules-agent query rules-index.json --severity must
```

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
