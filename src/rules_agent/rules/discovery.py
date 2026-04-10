"""Discover rules files in a repository by priority tiers."""

import hashlib
import logging
import subprocess
from pathlib import Path

from ..config import settings
from .models import RuleFile

logger = logging.getLogger(__name__)

_cfg = settings.discovery

# Module-level repo root, set during discover_rules_files() and used by
# include resolution to prevent path traversal outside the repository.
_active_repo_root: Path | None = None


def _is_within_repo(target_path: Path) -> bool:
    """Check that target_path resolves to a location within the active repo root."""
    if _active_repo_root is None:
        return True
    try:
        target_path.resolve().relative_to(_active_repo_root)
        return True
    except ValueError:
        logger.warning(f"Path traversal blocked: {target_path} is outside {_active_repo_root}")
        return False


def _resolve_inline_includes(content: str, base_dir: Path, _depth: int) -> str:
    """Resolve @file references within multi-line content, inlining target file content.

    Only resolves lines where the stripped content is solely ``@<path>`` (no spaces
    in the path, no other text on the line).  Skips ``@`` references inside fenced
    code blocks to avoid false positives from code examples.
    """
    lines = content.split("\n")
    resolved: list[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        # Track fenced code blocks (``` or ~~~) to avoid resolving inside them
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            resolved.append(line)
            continue

        if in_code_block:
            resolved.append(line)
            continue

        # Match lines that are just @<path> (no spaces in path, under max length)
        if stripped.startswith("@") and " " not in stripped and len(stripped) < _cfg.include_max_length:
            target = stripped[1:]
            if target:
                target_path = base_dir / target
                if target_path.is_file() and not target_path.is_symlink() and _is_within_repo(target_path):
                    try:
                        included = target_path.read_text(encoding="utf-8")
                        if _depth + 1 < _cfg.include_max_depth:
                            included = _resolve_inline_includes(included, target_path.parent, _depth + 1)
                        logger.info(f"Inlined include: @{target} from {base_dir}")
                        resolved.append(included)
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to read inline include @{target}: {e}")

        resolved.append(line)

    return "\n".join(resolved)


def _read_file_if_valid(path: Path, _depth: int = 0) -> tuple[str, Path] | None:
    """Read file content if it exists and is under size limit.

    Returns:
        Tuple of (content, actual_source_path) where actual_source_path is the
        final resolved path after following any whole-file include directives.
        Returns None if the file is invalid or unreadable.
    """
    if path.is_symlink():
        logger.warning(f"Skipping symlink: {path}")
        return None
    if not path.is_file():
        return None
    if path.stat().st_size > _cfg.max_file_size_bytes:
        logger.warning(f"Skipping {path}: exceeds {_cfg.max_file_size_bytes} bytes")
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to read {path}: {e}")
        return None
    # Resolve @filename include directives (e.g., "@AGENTS.md" -> read AGENTS.md from same dir)
    stripped = content.strip()
    if stripped.startswith("@") and "\n" not in stripped and len(stripped) < _cfg.include_max_length:
        if _depth >= _cfg.include_max_depth:
            logger.warning(f"Include directive too deep (depth {_depth}): {path}")
            return None
        target = stripped[1:]  # Remove leading @
        resolved = path.parent / target
        if resolved.is_file() and not resolved.is_symlink() and _is_within_repo(resolved):
            logger.info(f"Resolving include directive: {path} -> {resolved}")
            return _read_file_if_valid(resolved, _depth + 1)
        logger.warning(f"Include directive target not found: {path} -> {target}")
        return None
    # Resolve inline @includes in multi-line content
    if _depth < _cfg.include_max_depth and "\n" in content:
        content = _resolve_inline_includes(content, path.parent, _depth)
    return content, path


def _get_canonical_path(path: Path) -> str:
    """Get canonical path for deduplication (handles case-insensitive filesystems)."""
    try:
        # Use stat to get inode - same inode = same file
        return f"{path.stat().st_dev}:{path.stat().st_ino}"
    except OSError:
        return str(path.resolve())


def _discover_tier_1(repo_root: Path) -> tuple[list[RuleFile], dict[str, str]]:
    """Discover tier 1: root-level rules files."""
    files = []
    contents: dict[str, str] = {}
    seen_inodes: set[str] = set()  # Track by inode for case-insensitive dedup
    for filename in _cfg.tier1.files:
        path = repo_root / filename
        if not path.exists():
            continue
        canonical = _get_canonical_path(path)
        if canonical in seen_inodes:
            continue  # Skip case-insensitive duplicates (e.g., CLAUDE.md vs claude.md on macOS)
        result = _read_file_if_valid(path)
        if result:
            content, actual_path = result
            seen_inodes.add(canonical)
            rel = str(actual_path.relative_to(repo_root))
            files.append(RuleFile(path=rel, tier=1, content_size=len(content)))
            contents[rel] = content
            if len(files) >= _cfg.max_files_per_tier:
                break
    return files, contents


def _discover_tier_2(repo_root: Path) -> tuple[list[RuleFile], dict[str, str]]:
    """Discover tier 2: tool-specific directories."""
    files = []
    contents: dict[str, str] = {}
    for rel_path in _cfg.tier2.files:
        path = repo_root / rel_path
        result = _read_file_if_valid(path)
        if result:
            content, actual_path = result
            rel = str(actual_path.relative_to(repo_root))
            files.append(RuleFile(path=rel, tier=2, content_size=len(content)))
            contents[rel] = content
            if len(files) >= _cfg.max_files_per_tier:
                break
    return files, contents


def _discover_tier_3(repo_root: Path) -> tuple[list[RuleFile], dict[str, str]]:
    """Discover tier 3: rules directories with glob patterns."""
    files = []
    contents: dict[str, str] = {}
    for entry in _cfg.tier3.dirs:
        rules_dir = repo_root / entry.path
        if rules_dir.is_dir():
            for path in sorted(rules_dir.glob(entry.pattern)):
                if path.is_symlink():
                    continue
                result = _read_file_if_valid(path)
                if result:
                    content, actual_path = result
                    rel = str(actual_path.relative_to(repo_root))
                    files.append(RuleFile(path=rel, tier=3, content_size=len(content)))
                    contents[rel] = content
                    if len(files) >= _cfg.max_files_per_tier:
                        return files, contents
    return files, contents


def _discover_tier_4(repo_root: Path) -> tuple[list[RuleFile], dict[str, str]]:
    """Discover tier 4: recursive patterns (excluding already found)."""
    files = []
    contents: dict[str, str] = {}
    seen_paths: set[str] = set()
    skip_dirs_set = set(_cfg.skip_dirs)

    for pattern in _cfg.tier4.patterns:
        for path in sorted(repo_root.glob(pattern)):
            if path.is_symlink():
                continue
            # Skip if already seen or in excluded directories
            path_str = str(path)
            if path_str in seen_paths:
                continue
            rel_parts = set(path.relative_to(repo_root).parts)
            if rel_parts & skip_dirs_set:
                continue

            result = _read_file_if_valid(path)
            if result:
                content, actual_path = result
                seen_paths.add(path_str)
                rel = str(actual_path.relative_to(repo_root))
                files.append(RuleFile(path=rel, tier=4, content_size=len(content)))
                contents[rel] = content
                if len(files) >= _cfg.max_files_per_tier:
                    return files, contents
    return files, contents


def discover_rules_files(repo_path: str | Path) -> tuple[list[RuleFile], dict[str, str]]:
    """
    Discover all rules files in a repository, ordered by priority tier.

    Args:
        repo_path: Path to the repository root

    Returns:
        Tuple of (list of RuleFile objects ordered by tier, dict mapping path to content)
    """
    global _active_repo_root
    repo_root = Path(repo_path).resolve()
    if not repo_root.is_dir():
        raise ValueError(f"Not a directory: {repo_root}")

    _active_repo_root = repo_root
    logger.info(f"Discovering rules files in {repo_root}")

    all_files: list[RuleFile] = []
    all_contents: dict[str, str] = {}
    seen_paths: set[str] = set()
    seen_content_hashes: set[str] = set()  # Deduplicate by content (e.g., @include resolves)

    # Discover each tier
    for tier_num, discover_fn in [
        (1, _discover_tier_1),
        (2, _discover_tier_2),
        (3, _discover_tier_3),
        (4, _discover_tier_4),
    ]:
        tier_files, tier_contents = discover_fn(repo_root)
        for f in tier_files:
            if f.path in seen_paths:
                continue
            content = tier_contents.get(f.path, "")
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            if content_hash in seen_content_hashes:
                logger.info(f"Skipping {f.path}: duplicate content (already discovered)")
                continue
            seen_paths.add(f.path)
            seen_content_hashes.add(content_hash)
            all_files.append(f)
            if content:
                all_contents[f.path] = content
        logger.info(f"Tier {tier_num}: found {len(tier_files)} files")

    logger.info(f"Total: {len(all_files)} rules files discovered")
    return all_files, all_contents


def _git_blob_shas(repo_dir: str | Path, file_paths: list[str]) -> dict[str, str]:
    """Get git blob SHAs for files via ``git ls-tree HEAD -- <paths>``.

    Returns dict of ``{path: blob_sha}`` for tracked files.
    """
    if not file_paths:
        return {}
    cmd = ["git", "-C", str(repo_dir), "ls-tree", "HEAD", "--"] + file_paths
    try:
        out = subprocess.check_output(cmd, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    result: dict[str, str] = {}
    for line in out.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            tokens = parts[0].split()
            if len(tokens) >= 3:
                result[parts[1]] = tokens[2]
    return result


def compute_rules_source_sha(repo_path: str | Path, rule_files: list[RuleFile]) -> str:
    """Compute composite SHA256 from sorted (path, git_blob_sha) pairs.

    Uses git blob SHAs so the hash changes only when file content changes in git.
    """
    file_paths = [f.path for f in rule_files]
    blob_shas = _git_blob_shas(str(repo_path), file_paths)

    lines = sorted(f"{path}:{blob_shas[path]}\n" for path in file_paths if path in blob_shas)
    return hashlib.sha256("".join(lines).encode()).hexdigest()
