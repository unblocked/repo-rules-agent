"""Cache path resolution for the per-repo index.

The default index location is a per-user cache dir (XDG-style on Linux,
Library/Caches on macOS, LocalAppData on Windows), keyed by a hash of
the absolute repo path so two checkouts of the same repo don't collide.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from platformdirs import user_cache_dir

_APP_NAME = "repo-rules"
_INDEX_FILENAME = "index.json"


def cache_root() -> Path:
    """Root directory where all per-repo cached indices live."""
    return Path(user_cache_dir(_APP_NAME))


def _cache_dir_name(repo_path: Path) -> str:
    abspath = str(repo_path.resolve())
    digest = hashlib.sha256(abspath.encode("utf-8")).hexdigest()[:8]
    basename = re.sub(r"[^a-zA-Z0-9._-]+", "-", repo_path.resolve().name).strip("-").lower() or "repo"
    return f"{basename}-{digest}"


def default_index_path(repo_path: Path | str) -> Path:
    """Return the default cache path where the index for this repo lives."""
    repo = Path(repo_path)
    return cache_root() / _cache_dir_name(repo) / _INDEX_FILENAME


def list_cached_indices() -> list[Path]:
    """Return all cached index.json paths, sorted by most-recently-modified first."""
    root = cache_root()
    if not root.exists():
        return []
    entries = [p for p in root.glob(f"*/{_INDEX_FILENAME}") if p.is_file()]
    entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return entries


def clear_cache(repo_path: Path | str | None = None) -> list[Path]:
    """Delete cached index(es). Returns the paths that were removed.

    If ``repo_path`` is given, only that repo's cache dir is removed. Otherwise
    the entire cache root is removed.
    """
    root = cache_root()
    if not root.exists():
        return []

    if repo_path is not None:
        target = root / _cache_dir_name(Path(repo_path))
        if not target.exists():
            return []
        shutil.rmtree(target)
        return [target]

    removed = list(root.iterdir())
    shutil.rmtree(root)
    return removed
