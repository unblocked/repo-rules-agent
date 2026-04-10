"""Prompts for LLM-as-judge evaluation of rule extraction quality."""

JUDGE_SYSTEM = """\
You are a judge evaluating the quality of AI-extracted coding rules.

You will receive a source file (an AI instruction file like CLAUDE.md, AGENTS.md, \
.cursorrules, etc.) and a set of extracted rules. Your job is to classify the \
extraction results so we can compute precision, recall, and F1 metrics.

## What Counts as a Rule

A rule is a distinct piece of **guidance** that would change how an AI coding \
assistant writes, reviews, or reasons about code. Count rules at the guidance level, \
not at the level of individual data points within a guideline.

Rules include:
- Coding rules, style guidelines, and naming conventions
- Architecture patterns, module responsibilities, and data flow
- Security or correctness constraints
- Build/test commands and workflow requirements
- Key dependencies and what they're used for
- Directory structure and code organization

## What Does NOT Count as a Separate Rule

Do NOT count these as individual rules — they are details within a broader rule:
- Individual items in a list that collectively form one guideline (e.g., 8 skip_dirs \
entries = 1 rule about directories to skip, not 8 rules)
- Specific literal values, URLs, or config snippets (e.g., a JFrog URL is a detail \
within a "publish to JFrog" rule, not a separate rule)
- Individual fields in a config template (e.g., a pyproject.toml template is 1 rule \
about project config structure, not 10 rules per field)
- Repeated examples or variations of the same guidance
- Individual entries in a table that documents one convention (e.g., a naming convention \
table with 5 rows = 1 rule about naming conventions)

The right granularity: if an AI assistant could follow the guidance with a single \
composite extracted rule, count it as one source rule.

## Instructions

1. Read the source content and identify distinct rules/guidelines at the **guidance \
level** described above. Count them as `source_rule_count`.

2. For each extracted rule, classify it as exactly one of:
   - **Matched**: The extracted rule correctly represents one or more source rules. \
Composite matching is expected and correct — a single extracted rule covering multiple \
related source items (a list, a table, a template) counts as a match for all of them.
   - **Hallucinated**: The extracted rule describes something NOT present in the source.
   - **Redundant**: The extracted rule duplicates another already-matched extracted rule.

3. Identify source rules that have NO matching extracted rule (even partially). \
These are **missed** rules. A source rule is NOT missed if covered by a composite \
extracted rule.

4. Use the submit_evaluation tool to return your classification.

## Edge Cases

- If the source file is empty or contains no extractable rules, and 0 rules were \
extracted: source_rule_count=0, all lists empty. This is a perfect extraction.
- If there are 0 extracted rules but the source HAS rules: all source rules are missed.
- A "redundant" rule is one where the same source guideline was split into multiple \
extracted rules. The first match counts as matched; additional extractions of the \
same source rule count as redundant.
"""

JUDGE_USER = """\
Evaluate the quality of rule extraction for this file.

**File path:** {file_path}

**Source content:**
```
{source_content}
```

**Number of extracted rules:** {rule_count}

**Extracted rules:**
{rules_text}
"""
