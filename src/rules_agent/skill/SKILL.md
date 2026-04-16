---
name: repo-rules
description: Extract and query AI coding rules from repositories using the repo-rules-agent CLI. Use when asked to index a repo for rules, query an existing rules index, discover rules files, or evaluate extraction quality.
argument-hint: [command] [args...]
allowed-tools: Bash(repo-rules-agent *)
---

# repo-rules-agent CLI

Extract and query AI coding rules (CLAUDE.md, .cursorrules, .github/copilot-instructions.md, etc.) from repositories.

## Commands

### discover — Find rules files without extracting

```bash
repo-rules-agent discover <repo-path> [-v]
```

Lists all rules files found in a repository with their priority tiers and sizes.

### index — Extract rules and build a JSON index

```bash
repo-rules-agent index <repo-path> [-o output.json] [--embed-content] [-v]
```

- Discovers rules files, extracts individual rules via any OpenAI-compatible LLM, and outputs a JSON index
- `--embed-content`: Embeds the original source file content in the index JSON (useful for later querying with `--include-sources`)
- `-o path`: Write index to file instead of stdout
- Defaults to local Ollama; configure provider via `RULES_AGENT_LLM__BASE_URL` and `RULES_AGENT_LLM__API_KEY_ENV` env vars

### query — Filter and retrieve rules from an index

```bash
repo-rules-agent query <index.json> [options]
```

Options:
- `-t, --task`: Filter by task type (`code-review`, `code-generation`, `code-questions`)
- `-l, --lang`: Filter by language (`py`, `ts`, `go`, `java`, `rust`, etc.)
- `-s, --scope`: Filter by scope (`repo`, `directory`, `file-pattern`)
- `--severity`: Filter by severity (`must`, `should`, `can`)
- `-f, --format`: Output format (`table`, `json`, `prompt`)
- `--include-sources`: Include source file content in output (for `prompt` and `json` formats)
- `--repo <path>`: Repository path for resolving source files from disk when content is not embedded

Examples:
```bash
# Get all must-follow rules for Python code review as a prompt
repo-rules-agent query index.json -t code-review -l py --severity must -f prompt

# Get rules with source context included
repo-rules-agent query index.json -t code-review -f prompt --include-sources

# Get rules as JSON with source files resolved from disk
repo-rules-agent query index.json -f json --include-sources --repo /path/to/repo
```

### eval — Evaluate extraction quality with LLM judge

```bash
repo-rules-agent eval <source> [--repo <path>] [-o results.json] [--judge-model <model>] [-v]
```

- `<source>`: Path to an index JSON file or a repository directory
- If given a directory, runs the full discover -> extract -> eval pipeline
- `--repo`: Repository path for reading source files from disk when index lacks embedded content
- `--judge-model`: Model to use as judge (default: `qwen3-coder:30b`)
- Reports precision, recall, and F1 scores per file and overall

### install-skill — Install the Claude Code skill

```bash
repo-rules-agent install-skill [--scope project|user] [--force]
```

- `--scope project` (default): Installs to `.claude/skills/repo-rules/SKILL.md` in the current directory
- `--scope user`: Installs to `~/.claude/skills/repo-rules/SKILL.md`
- `--force`: Overwrite existing SKILL.md without confirmation

## Typical workflows

**Index a repo and query it:**
```bash
repo-rules-agent index /path/to/repo --embed-content -o /tmp/rules-index.json
repo-rules-agent query /tmp/rules-index.json -t code-review -f prompt --include-sources
```

**Quick discovery scan:**
```bash
repo-rules-agent discover /path/to/repo
```

**Evaluate extraction quality on an existing index:**
```bash
repo-rules-agent eval /tmp/rules-index.json -o /tmp/eval-results.json
```
