---
name: repo-rules
description: Query AI coding rules for this repo (extracted from CLAUDE.md, AGENTS.md, .cursorrules, .github/copilot-instructions.md, and ~40 other rules-file conventions). Invoke when the user asks about team rules, coding standards, or conventions — or when reviewing, generating, or refactoring code and you need to know which rules apply. Builds a fresh index if one doesn't exist yet.
argument-hint: [command] [args...]
allowed-tools: Bash(repo-rules-agent *)
---

# repo-rules-agent

Extract and query AI coding rules (CLAUDE.md, .cursorrules, .github/copilot-instructions.md, etc.) from the current repository.

## Default workflow

When you need to consult the rules for a task:

1. Check whether a rules index exists for this repo:

   ```bash
   test -f "$(repo-rules-agent cache path)" && echo "index exists" || echo "missing"
   ```

2. If it doesn't exist — or if any rules source file has changed since it was last built — regenerate it:

   ```bash
   repo-rules-agent index .
   ```

   The index is written to a per-user cache directory (not the repo). The command prints the exact path.

3. Query the index scoped to the current task:

   ```bash
   repo-rules-agent query \
     --task <code-review|code-generation|code-questions> \
     [--lang py|ts|go|...] \
     [--severity must|should|can] \
     --format prompt
   ```

   Use `--format prompt` when injecting rules into your own context. Use `--format table` when showing them to the user.

## Commands

### index — Extract rules and build a JSON index

```bash
repo-rules-agent index <repo-path> [-o output.json] [-v]
```

- Discovers rules files, extracts individual rules via any OpenAI-compatible LLM, and writes a JSON index.
- Default output location is a per-user cache directory keyed by the absolute repo path.
- `-o path`: override the output path.
- Defaults to local Ollama (`qwen3-coder:30b`); configure provider via `RULES_AGENT_LLM__BASE_URL` and `RULES_AGENT_LLM__API_KEY_ENV`.

### query — Filter and retrieve rules from an index

```bash
repo-rules-agent query [index.json] [options]
```

With no positional argument, reads the cached index for the current directory.

Options:
- `-t, --task`: Filter by task type (`code-review`, `code-generation`, `code-questions`)
- `-l, --lang`: Filter by language (`py`, `ts`, `go`, `java`, `rust`, etc.)
- `-s, --scope`: Filter by scope (`repo`, `directory`, `file-pattern`)
- `--severity`: Filter by severity (`must`, `should`, `can`)
- `-f, --format`: Output format (`table`, `json`, `prompt`)

### discover — Find rules files without extracting

```bash
repo-rules-agent discover <repo-path> [-v]
```

Lists all rules files found in a repository with their priority tiers and sizes.

### cache — Manage the per-repo index cache

```bash
repo-rules-agent cache path [repo-path]   # print where this repo's index lives
repo-rules-agent cache list               # list every cached index, most recent first
repo-rules-agent cache clear <repo-path>  # remove one repo's cache
repo-rules-agent cache clear --all        # wipe the whole cache
```

### eval — Evaluate extraction quality with LLM judge

```bash
repo-rules-agent eval <source> [--repo <path>] [-o results.json] [--judge-model <model>] [-v]
```

- `<source>`: index JSON path or a repository directory (directory runs the full pipeline).
- `--judge-model`: model used as judge (default: `qwen3-coder:30b`).
- Reports precision, recall, and F1 per file and overall.

### install-skill — Install this skill

```bash
repo-rules-agent install-skill [--scope project|user] [--force]
```

- `--scope project` (default): `.claude/skills/repo-rules/SKILL.md` in the current directory.
- `--scope user`: `~/.claude/skills/repo-rules/SKILL.md`.
- `--force`: overwrite without confirmation.
