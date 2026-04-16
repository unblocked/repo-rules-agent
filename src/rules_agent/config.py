"""Centralized configuration using pydantic-settings.

All config lives in config.toml. Override at runtime via env vars.

Load order (last wins):
  1. Python field defaults (fallback if TOML missing)
  2. config.toml values
  3. .env file (loaded via python-dotenv, does not override existing env vars)
  4. Environment variables with RULES_AGENT_ prefix

Env var examples:
    RULES_AGENT_LLM__EXTRACTION_MODEL=claude-haiku-4-5
    RULES_AGENT_CHUNKING__THRESHOLD_CHARS=12000
    RULES_AGENT_DEDUP__SIMILARITY_THRESHOLD=0.85
"""

from pathlib import Path
from typing import Tuple, Type

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource

load_dotenv()

_CONFIG_TOML = Path(__file__).parent / "config.toml"


# ── Sub-models for discovery tier data ───────────────────────


class Tier3Dir(BaseModel):
    """A single tier-3 directory + glob pattern pair."""

    path: str
    pattern: str


class Tier1Config(BaseModel):
    """Tier 1: root-level files."""

    files: list[str] = []


class Tier2Config(BaseModel):
    """Tier 2: tool-specific directory files."""

    files: list[str] = []


class Tier3Config(BaseModel):
    """Tier 3: rules directories with glob patterns."""

    dirs: list[Tier3Dir] = []


class Tier4Config(BaseModel):
    """Tier 4: recursive patterns."""

    patterns: list[str] = []


# ── Settings classes ─────────────────────────────────────────


class LLMConfig(BaseSettings):
    """LLM model and token budget settings."""

    base_url: str = "http://localhost:11434/v1"
    api_key_env: str = "OLLAMA_API_KEY"
    extraction_model: str = "qwen3-coder:30b"
    extraction_max_tokens: int = 16384
    judge_model: str = "qwen3-coder:30b"
    judge_max_tokens: int = 4096


class ChunkingConfig(BaseSettings):
    """Content chunking parameters for large files."""

    threshold_chars: int = 12000
    chunk_size_chars: int = 10000
    min_chars_per_chunk: int = 100
    markdown_extensions: set[str] = {".md", ".mdc", ".markdown"}


class DiscoveryConfig(BaseModel):
    """File discovery limits, patterns, and tier definitions."""

    max_file_size_bytes: int = 512 * 1024
    max_files_per_tier: int = 50
    include_max_depth: int = 5
    include_max_length: int = 256
    skip_dirs: list[str] = [
        "node_modules",
        "vendor",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
    ]
    tier1: Tier1Config = Field(default_factory=Tier1Config)
    tier2: Tier2Config = Field(default_factory=Tier2Config)
    tier3: Tier3Config = Field(default_factory=Tier3Config)
    tier4: Tier4Config = Field(default_factory=Tier4Config)


class DeduplicationConfig(BaseSettings):
    """Thresholds for rule deduplication and conflict detection."""

    similarity_threshold: float = 0.85
    conflict_lower_bound: float = 0.5


class OutputConfig(BaseSettings):
    """Display and output defaults."""

    default_format: str = "table"
    metric_good_threshold: float = 0.8
    metric_warn_threshold: float = 0.6
    low_score_detail_threshold: float = 0.8
    output_filename: str = "repo_rules.json"


class RuleDefaultsConfig(BaseSettings):
    """Defaults applied to extracted rules when the LLM omits a field."""

    id_hash_length: int = 12


class Settings(BaseSettings):
    """Top-level settings container.

    All values loaded from config.toml, overridden by env vars.
    """

    model_config = SettingsConfigDict(
        env_prefix="RULES_AGENT_",
        env_nested_delimiter="__",
        toml_file=str(_CONFIG_TOML),
    )

    llm: LLMConfig = Field(default_factory=LLMConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    dedup: DeduplicationConfig = Field(default_factory=DeduplicationConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    rule_defaults: RuleDefaultsConfig = Field(default_factory=RuleDefaultsConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """Load config.toml first, then let env vars override.

        Sources are listed highest-priority-first: init_settings > env > TOML.
        """
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls),
        )


# Module-level singleton — import this wherever config is needed.
settings = Settings()
