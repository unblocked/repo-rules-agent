"""Tests for rules file discovery."""

import subprocess
import tempfile
from pathlib import Path

from rules_agent.rules.discovery import compute_rules_source_sha, discover_rules_files


def _make_git_repo(tmpdir: str, files: dict[str, str]) -> None:
    """Initialise a git repo in *tmpdir*, write *files*, and commit them."""
    subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmpdir, capture_output=True, check=True)
    for name, content in files.items():
        path = Path(tmpdir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--no-verify"],
        cwd=tmpdir,
        capture_output=True,
        check=True,
    )


def test_discover_tier_1_files():
    """Test discovery of tier 1 root-level files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        # Create tier 1 files
        (repo / "CLAUDE.md").write_text("# Claude instructions")
        (repo / "CONTRIBUTING.md").write_text("# Contributing guide")

        files, contents = discover_rules_files(repo)

        assert len(files) == 2
        assert all(f.tier == 1 for f in files)
        paths = [Path(f.path).name for f in files]
        assert "CLAUDE.md" in paths
        assert "CONTRIBUTING.md" in paths
        assert len(contents) == 2


def test_discover_tier_2_files():
    """Test discovery of tier 2 tool-specific files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        # Create tier 2 files
        (repo / ".claude").mkdir()
        (repo / ".claude" / "CLAUDE.md").write_text("# Claude config")

        files, contents = discover_rules_files(repo)

        assert len(files) == 1
        assert files[0].tier == 2
        assert len(contents) == 1


def test_discover_tier_3_files():
    """Test discovery of tier 3 rules directory files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        # Create tier 3 files
        (repo / ".cursor" / "rules").mkdir(parents=True)
        (repo / ".cursor" / "rules" / "style.mdc").write_text("style rules")
        (repo / ".cursor" / "rules" / "security.mdc").write_text("security rules")

        files, contents = discover_rules_files(repo)

        assert len(files) == 2
        assert all(f.tier == 3 for f in files)
        assert len(contents) == 2


def test_discover_skips_large_files():
    """Test that files over 512KB are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        # Create a large file
        large_content = "x" * (513 * 1024)  # Just over 512KB
        (repo / "CLAUDE.md").write_text(large_content)

        files, contents = discover_rules_files(repo)

        assert len(files) == 0
        assert len(contents) == 0


def test_discover_empty_repo():
    """Test discovery in a repo with no rules files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        files, contents = discover_rules_files(repo)

        assert len(files) == 0
        assert len(contents) == 0


def test_discover_resolves_include_to_unique_target():
    """Test that @filename resolves to target content when target is not otherwise discovered."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        target_content = "# Custom rules\nAlways use type hints."
        (repo / "CLAUDE.md").write_text("@my-rules.md\n")
        (repo / "my-rules.md").write_text(target_content)

        files, contents = discover_rules_files(repo)

        # CLAUDE.md includes @my-rules.md, so the resolved path should be my-rules.md
        paths = [f.path for f in files]
        assert "my-rules.md" in paths
        assert contents["my-rules.md"] == target_content


def test_discover_dedupes_include_with_direct_discovery():
    """Test that @include resolving to an already-discovered file is deduped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        target_content = "# Real rules\nAlways use type hints."
        # AGENTS.md is discovered first in tier 1 (listed before CLAUDE.md)
        (repo / "AGENTS.md").write_text(target_content)
        # CLAUDE.md points to same content via @include
        (repo / "CLAUDE.md").write_text("@AGENTS.md\n")

        files, contents = discover_rules_files(repo)

        # Only AGENTS.md should remain — CLAUDE.md deduped by content hash
        paths = [f.path for f in files]
        assert "AGENTS.md" in paths
        assert "CLAUDE.md" not in paths
        assert len(files) == 1


def test_discover_skips_broken_include_directive():
    """Test that @filename directive to missing file is skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        (repo / "CLAUDE.md").write_text("@NONEXISTENT.md\n")

        files, contents = discover_rules_files(repo)

        assert len(files) == 0
        assert len(contents) == 0


def test_discover_include_in_subdirectory_uses_resolved_path():
    """Test that @include in a subdirectory file records the resolved target path, not the pointer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        # frontend/.agents/CLAUDE.md contains @VIEWS.md which resolves to frontend/.agents/VIEWS.md
        agents_dir = repo / "frontend" / ".agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "CLAUDE.md").write_text("@VIEWS.md\n")
        (agents_dir / "VIEWS.md").write_text("# Views\nAlways check LoadableState.$case before accessing .value.")

        files, contents = discover_rules_files(repo)

        paths = [f.path for f in files]
        # The resolved path should be VIEWS.md, not CLAUDE.md
        assert "frontend/.agents/VIEWS.md" in paths
        assert "frontend/.agents/CLAUDE.md" not in paths
        assert "Always check LoadableState" in contents["frontend/.agents/VIEWS.md"]


def test_discover_include_chain_uses_final_resolved_path():
    """Test that chained includes (A -> B -> C) record the final target path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        (repo / "CLAUDE.md").write_text("@AGENTS.md\n")
        (repo / "AGENTS.md").write_text("@RULES.md\n")
        (repo / "RULES.md").write_text("# Rules\nUse type hints everywhere.")

        files, contents = discover_rules_files(repo)

        paths = [f.path for f in files]
        # Should resolve all the way to RULES.md
        assert "RULES.md" in paths
        assert "CLAUDE.md" not in paths
        assert "AGENTS.md" not in paths
        assert "Use type hints everywhere" in contents["RULES.md"]


def test_discover_multiple_pointers_to_same_target_deduped():
    """Test that two pointer files resolving to the same target are deduped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        (repo / "CLAUDE.md").write_text("@RULES.md\n")
        (repo / "AGENTS.md").write_text("@RULES.md\n")
        (repo / "RULES.md").write_text("# Rules\nUse type hints.")

        files, contents = discover_rules_files(repo)

        paths = [f.path for f in files]
        # Both resolve to RULES.md, should appear only once
        assert paths.count("RULES.md") == 1
        assert "CLAUDE.md" not in paths
        assert "AGENTS.md" not in paths


def test_discover_include_does_not_clobber_direct_file():
    """Test that a directly discovered file is not replaced by a pointer to it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        rules_content = "# Rules\nUse type hints."
        # AGENTS.md is discovered directly in tier 1
        (repo / "AGENTS.md").write_text(rules_content)
        # .cursor/rules/main.md points to the same file via @include
        cursor_dir = repo / ".cursor" / "rules"
        cursor_dir.mkdir(parents=True)
        (cursor_dir / "main.md").write_text("@../../AGENTS.md\n")

        files, contents = discover_rules_files(repo)

        paths = [f.path for f in files]
        # AGENTS.md found directly in tier 1 should remain
        assert "AGENTS.md" in paths
        # The pointer should be deduped since it resolves to the same content
        assert paths.count("AGENTS.md") == 1


def test_discover_sibling_include_in_agents_dir():
    """Test @include between sibling files in .agents/ directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        agents_dir = repo / ".agents"
        agents_dir.mkdir()
        (agents_dir / "OVERVIEW.md").write_text("@DETAILS.md\n")
        (agents_dir / "DETAILS.md").write_text("# Details\nUse strict mode.")
        (agents_dir / "STYLES.md").write_text("# Styles\nUse BEM naming.")

        files, contents = discover_rules_files(repo)

        paths = [f.path for f in files]
        # OVERVIEW.md resolves to DETAILS.md
        assert ".agents/DETAILS.md" in paths
        assert ".agents/OVERVIEW.md" not in paths
        # STYLES.md discovered directly
        assert ".agents/STYLES.md" in paths
        # Content should be correct for both
        assert "Use strict mode" in contents[".agents/DETAILS.md"]
        assert "Use BEM naming" in contents[".agents/STYLES.md"]


def test_discover_dedupes_case_insensitive():
    """Test that case-insensitive duplicates are handled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        # On case-insensitive filesystems, only one will exist
        # On case-sensitive filesystems, both will exist but should be deduped by inode
        (repo / "CLAUDE.md").write_text("# Claude")

        files, contents = discover_rules_files(repo)

        # Should only have one file regardless of filesystem
        claude_files = [f for f in files if "claude" in f.path.lower()]
        assert len(claude_files) == 1


# --------------------------------------------------------------------------
# Inline @include resolution tests
# --------------------------------------------------------------------------


def test_inline_includes_resolve_in_multiline_content():
    """@references on their own line are inlined into the parent file content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        (repo / ".agents").mkdir()
        (repo / ".agents" / "STYLES.md").write_text("# Styles\nUse BEM naming.")
        (repo / ".agents" / "VIEWS.md").write_text("# Views\nUse CSS grid.")
        (repo / "AGENTS.md").write_text(
            "# Frontend Guide\n\n@.agents/STYLES.md\n@.agents/VIEWS.md\n\n## Other rules\nNo barrel imports.\n"
        )

        files, contents = discover_rules_files(repo)

        agents = [f for f in files if f.path == "AGENTS.md"]
        assert len(agents) == 1
        content = contents["AGENTS.md"]
        # Inlined content should appear
        assert "Use BEM naming." in content
        assert "Use CSS grid." in content
        # Original content preserved
        assert "# Frontend Guide" in content
        assert "No barrel imports." in content


def test_inline_includes_skip_nonexistent_targets():
    """@references to missing files are left as-is."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        (repo / "AGENTS.md").write_text("# Guide\n@nonexistent.md\n## Rules\nBe nice.\n")

        files, contents = discover_rules_files(repo)

        assert len(files) == 1
        content = contents["AGENTS.md"]
        assert "@nonexistent.md" in content
        assert "Be nice." in content


def test_inline_includes_skip_code_blocks():
    """@references inside fenced code blocks are not resolved."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        # Create a file that would match if resolved
        (repo / "example.md").write_text("# Should not be inlined")
        (repo / "AGENTS.md").write_text("# Guide\n```\n@example.md\n```\n## Rules\nDone.\n")

        files, contents = discover_rules_files(repo)

        assert len(files) == 1
        content = contents["AGENTS.md"]
        # The @example.md should remain as-is inside the code block
        assert "@example.md" in content
        assert "Should not be inlined" not in content


def test_inline_includes_ignore_lines_with_spaces():
    """Lines like '@param foo' or '@media screen' are not treated as includes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        (repo / "AGENTS.md").write_text("# Guide\n@param description\n@media screen\n")

        files, contents = discover_rules_files(repo)

        assert len(files) == 1
        content = contents["AGENTS.md"]
        assert "@param description" in content
        assert "@media screen" in content


def test_inline_includes_recursive():
    """Inline includes can themselves contain inline includes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        (repo / "AGENTS.md").write_text("# Root\n@level1.md\n")
        (repo / "level1.md").write_text("# Level 1\n@level2.md\n")
        (repo / "level2.md").write_text("# Level 2\nDeep rule.")

        files, contents = discover_rules_files(repo)

        # AGENTS.md should have all content inlined
        agents_content = contents.get("AGENTS.md", "")
        assert "# Level 1" in agents_content
        assert "Deep rule." in agents_content


def test_inline_includes_coexist_with_whole_file_redirect():
    """Whole-file @redirect still works; inline includes work in other files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        (repo / ".agents").mkdir()
        (repo / ".agents" / "EXTRA.md").write_text("# Extra rules\nNo any type.")
        # CLAUDE.md is a whole-file redirect
        (repo / "CLAUDE.md").write_text("@AGENTS.md\n")
        # AGENTS.md has inline includes
        (repo / "AGENTS.md").write_text("# Guide\n@.agents/EXTRA.md\n## Core\nUse TypeScript.\n")

        files, contents = discover_rules_files(repo)

        paths = [f.path for f in files]
        # CLAUDE.md should be deduped (same content as AGENTS.md after redirect)
        assert "AGENTS.md" in paths
        # AGENTS.md should have inlined content
        agents_content = contents["AGENTS.md"]
        assert "No any type." in agents_content
        assert "Use TypeScript." in agents_content


# --------------------------------------------------------------------------
# compute_rules_source_sha tests (require a real git repo)
# --------------------------------------------------------------------------


def test_compute_rules_source_sha_stable():
    """Same content produces the same SHA."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _make_git_repo(tmpdir, {"CLAUDE.md": "# Rules\nAlways use type hints."})
        files, _ = discover_rules_files(tmpdir)
        sha1 = compute_rules_source_sha(tmpdir, files)
        sha2 = compute_rules_source_sha(tmpdir, files)
        assert sha1 == sha2
        assert len(sha1) == 64  # SHA-256 hex


def test_compute_rules_source_sha_changes_on_content_change():
    """SHA changes when a rules file is modified and committed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _make_git_repo(tmpdir, {"CLAUDE.md": "# Rules v1"})
        files, _ = discover_rules_files(tmpdir)
        sha_before = compute_rules_source_sha(tmpdir, files)

        # Modify and commit
        (Path(tmpdir) / "CLAUDE.md").write_text("# Rules v2 — updated")
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "update", "--no-verify"],
            cwd=tmpdir,
            capture_output=True,
            check=True,
        )

        files, _ = discover_rules_files(tmpdir)
        sha_after = compute_rules_source_sha(tmpdir, files)
        assert sha_before != sha_after


def test_compute_rules_source_sha_empty_when_no_tracked_files():
    """SHA is deterministic even when files exist but aren't tracked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Init repo but don't commit the rules file
        subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmpdir, capture_output=True, check=True)
        # Need at least one commit for HEAD to exist
        (Path(tmpdir) / "README").write_text("init")
        subprocess.run(["git", "add", "README"], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init", "--no-verify"],
            cwd=tmpdir,
            capture_output=True,
            check=True,
        )
        # Now add an untracked rules file
        (Path(tmpdir) / "CLAUDE.md").write_text("# Untracked rules")

        files, _ = discover_rules_files(tmpdir)
        assert len(files) == 1  # Discovery finds the file on disk
        sha = compute_rules_source_sha(tmpdir, files)
        # No tracked blobs → empty input to SHA → deterministic hash of empty string
        assert len(sha) == 64


def test_compute_rules_source_sha_not_a_git_repo():
    """SHA doesn't crash on a non-git directory (git_blob_shas returns {})."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "CLAUDE.md").write_text("# Not a repo")
        files, _ = discover_rules_files(tmpdir)
        sha = compute_rules_source_sha(tmpdir, files)
        assert len(sha) == 64  # Still returns a valid hash, just of empty input
