"""Pydantic models for rules extraction and indexing."""

import hashlib
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field

from ..config import settings

TaskType = Literal["code-review", "code-generation", "code-questions"]
Severity = Literal["must", "should", "can"]
Scope = Literal["repo", "directory", "file-pattern"]


class RuleCategory(str, Enum):
    """Categories for rules - aligned with ReviewComment.Category."""

    CRASH_OR_HANG = "crash_or_hang"
    LOGIC_ERROR = "logic_error"
    PERFORMANCE = "performance"
    SECURITY = "security"
    ERROR_HANDLING = "error_handling"
    READABILITY = "readability"
    CODE_STYLE = "code_style"
    MAINTAINABILITY = "maintainability"
    TESTABILITY = "testability"
    BEST_PRACTICE = "best_practice"


class Rule(BaseModel):
    """A single extracted rule/guideline from a rules file."""

    title: str = Field(
        default="",
        description="Concise, specific title with key technical context",
    )
    description: str = Field(
        default="",
        description="2-3 sentence description: WHAT the practice is, WHEN/WHERE to apply it (include any conditions), WHY it matters",
    )
    category: RuleCategory = Field(
        default=RuleCategory.BEST_PRACTICE,
        description=(
            "Category: crash_or_hang (crashes/deadlocks/infinite loops), "
            "logic_error (incorrect behavior/wrong results), "
            "performance (unnecessary slowdowns/resource waste), "
            "security (vulnerabilities/data exposure/auth issues), "
            "error_handling (missing/incorrect/unsafe error handling), "
            "readability (hard to understand/misleading code), "
            "code_style (formatting/naming/structural conventions), "
            "maintainability (makes future changes harder), "
            "testability (makes testing harder/breaks test patterns), "
            "best_practice (general recommended practice)"
        ),
    )
    tasks: list[TaskType] = Field(
        default_factory=list,
        description="Task types this rule applies to: code-review, code-generation, code-questions",
    )
    languages: list[str] = Field(
        default_factory=lambda: ["all"],
        description=(
            "Programming languages this rule applies to. Use 'all' if language-agnostic. "
            "Use lowercase language names: kotlin, typescript, javascript, python, go, "
            "java, ruby, rust, swift, scala, cpp, csharp, php, bash, shell, sql, css, "
            "html, dart, elixir, haskell, r, lua, perl. "
            "File extensions also accepted: kt, ts, js, py, rb, rs, etc."
        ),
    )
    scope: Scope = Field(
        default="repo",
        description="Scope of the rule. Most rules are 'repo' scope.",
    )
    severity: Severity = Field(
        default="should",
        description="Rule severity: must (required), should (recommended), can (optional)",
    )
    source_file: str = Field(default="", description="Origin file path for tracing")

    @computed_field
    @property
    def id(self) -> str:
        """Generate a deterministic ID from source_file and title."""
        # Use short hash for readability while maintaining uniqueness
        content = f"{self.source_file}:{self.title}"
        return hashlib.sha256(content.encode()).hexdigest()[: settings.rule_defaults.id_hash_length]

    def display_text(self) -> str:
        """Get display text for this rule."""
        if self.title and self.description:
            return f"{self.title}: {self.description}"
        if self.title:
            return self.title
        return self.description

    def source_filename(self) -> str:
        """Get just the filename from the source path."""
        return self.source_file.split("/")[-1] if self.source_file else ""


class RuleFile(BaseModel):
    """A discovered rules file with its extracted rules."""

    path: str = Field(description="Path to the rules file")
    tier: int = Field(description="Priority tier (1-4, lower is higher priority)")
    content_size: int = Field(default=0, description="Size of the raw file content in bytes")
    rules: list[Rule] = Field(default_factory=list, description="Extracted rules")
    content: Optional[str] = Field(default=None, description="Original source file content (when embedded)")


class RuleIndex(BaseModel):
    """Index of all rules extracted from a repository."""

    repo: str = Field(description="Repository root path")
    source_sha: str = Field(default="", description="Composite SHA256 of source rule files (git blob SHAs)")
    files: list[RuleFile] = Field(default_factory=list, description="All discovered rule files")
    rules: list[Rule] = Field(default_factory=list, description="All merged rules")
    conflicts: list[tuple[str, str]] = Field(
        default_factory=list,
        description="Pairs of conflicting rule texts",
    )

    @property
    def rule_count(self) -> int:
        """Total number of rules in the index."""
        return len(self.rules)

    @property
    def file_count(self) -> int:
        """Total number of rule files discovered."""
        return len(self.files)
