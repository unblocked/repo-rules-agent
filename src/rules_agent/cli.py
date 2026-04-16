#!/usr/bin/env python3
"""CLI for extracting and querying AI coding rules from repositories."""

import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from .config import settings
from .rules.discovery import discover_rules_files
from .rules.eval import (
    DEFAULT_JUDGE_MODEL,
    evaluate_index,
    load_index_with_sources,
)
from .rules.extractor import extract_rules_from_files
from .rules.index import build_index
from .rules.models import RuleIndex
from .rules.query import (
    format_rules_for_prompt,
    format_rules_with_sources,
    query_rules,
    resolve_source_contents,
)

_cfg_output = settings.output

app = typer.Typer(
    name="rules-agent",
    help="Extract and query AI coding rules from repositories",
)
console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_time=False, show_path=False)],
    )


@app.command()
def index(
    repo_path: Path = typer.Argument(
        ...,
        help="Path to the repository to index",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (defaults to stdout as JSON)",
    ),
    embed_content: bool = typer.Option(
        False,
        "--embed-content",
        help="Embed source file content in the index JSON",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """
    Index a repository to extract AI coding rules.

    Discovers rules files (CLAUDE.md, .cursorrules, etc.) and extracts
    individual rules using an LLM. Outputs a JSON index.
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        # Discover rules files
        console.print(f"[bold]Discovering rules files in {repo_path}...[/bold]")
        rule_files, contents = discover_rules_files(repo_path)

        if not rule_files:
            console.print("[yellow]No rules files found.[/yellow]")
            raise typer.Exit(0)

        # Show discovered files
        table = Table(title="Discovered Rules Files")
        table.add_column("Tier", style="cyan")
        table.add_column("Path", style="green")
        table.add_column("Size", justify="right")

        for rf in rule_files:
            table.add_row(str(rf.tier), rf.path, f"{rf.content_size:,} bytes")

        console.print(table)

        # Extract rules
        console.print("\n[bold]Extracting rules...[/bold]")
        processed_files = extract_rules_from_files(rule_files, contents)

        # Build index
        rule_index = build_index(
            str(repo_path),
            processed_files,
            contents=contents if embed_content else None,
            embed_content=embed_content,
        )

        # Show summary
        console.print("\n[bold green]Extraction complete![/bold green]")
        console.print(f"  Files processed: {rule_index.file_count}")
        console.print(f"  Rules extracted: {rule_index.rule_count}")
        if rule_index.conflicts:
            console.print(f"  [yellow]Conflicts detected: {len(rule_index.conflicts)}[/yellow]")

        # Output
        index_json = rule_index.model_dump_json(indent=2, exclude_none=True)

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(index_json)
            console.print(f"\n[bold]Index saved to {output}[/bold]")
        else:
            console.print("\n[bold]Index JSON:[/bold]")
            console.print(index_json)

    except typer.Exit:
        raise
    except Exception as e:
        logger.exception("Failed to index repository")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def query(
    index_path: Path = typer.Argument(
        ...,
        help="Path to the rules index JSON file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    task: Optional[str] = typer.Option(
        None,
        "--task",
        "-t",
        help="Filter by task: code-review, code-generation, code-questions",
    ),
    language: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Filter by language: ts, py, go, java, rust, etc.",
    ),
    scope: Optional[str] = typer.Option(
        None,
        "--scope",
        "-s",
        help="Filter by scope: repo, directory, file-pattern",
    ),
    severity: Optional[str] = typer.Option(
        None,
        "--severity",
        help="Filter by severity: must, should, can",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table, json, prompt",
    ),
    repo: Optional[Path] = typer.Option(
        None,
        "--repo",
        help="Repository path for resolving source files from disk",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    include_sources: bool = typer.Option(
        False,
        "--include-sources",
        help="Include source file content in output (prompt and json formats)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """
    Query rules from an index file.

    Filter by task type, language, scope, or severity.
    """
    setup_logging(verbose)

    try:
        # Load index
        index_data = json.loads(index_path.read_text())
        rule_index = RuleIndex.model_validate(index_data)

        # Query
        rules = query_rules(
            rule_index,
            task=task,
            language=language,
            scope=scope,
            severity=severity,
        )

        if not rules:
            console.print("[yellow]No rules match the query.[/yellow]")
            raise typer.Exit(0)

        # Resolve source contents if requested
        source_contents: dict[str, str] = {}
        if include_sources:
            source_contents = resolve_source_contents(rule_index, repo)

        # Output
        if format == "json":
            data = [r.model_dump() for r in rules]
            if include_sources and source_contents:
                output = json.dumps(
                    {"rules": data, "source_files": source_contents},
                    indent=2,
                )
            else:
                output = json.dumps(data, indent=2)
            console.print(output)

        elif format == "prompt":
            if include_sources:
                output = format_rules_with_sources(rules, source_contents)
            else:
                output = format_rules_for_prompt(rules)
            console.print(output)

        else:  # table
            table = Table(title=f"Query Results ({len(rules)} rules)")
            table.add_column("Severity", style="cyan", width=10)
            table.add_column("Rule", style="white", max_width=60)
            table.add_column("Tasks", style="green", width=20)
            table.add_column("Languages", style="yellow", width=15)
            table.add_column("Source", style="dim", max_width=30)

            for rule in rules:
                table.add_row(
                    rule.severity,
                    rule.display_text()[:60] + ("..." if len(rule.display_text()) > 60 else ""),
                    ", ".join(rule.tasks),
                    ", ".join(rule.languages),
                    Path(rule.source_file).name,
                )

            console.print(table)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def discover(
    repo_path: Path = typer.Argument(
        ...,
        help="Path to the repository",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """
    Discover rules files in a repository without extracting.

    Useful for checking which files would be processed.
    """
    setup_logging(verbose)

    try:
        rule_files, _contents = discover_rules_files(repo_path)

        if not rule_files:
            console.print("[yellow]No rules files found.[/yellow]")
            raise typer.Exit(0)

        table = Table(title="Discovered Rules Files")
        table.add_column("Tier", style="cyan", justify="center")
        table.add_column("Path", style="green")
        table.add_column("Size", justify="right")

        for rf in rule_files:
            table.add_row(str(rf.tier), rf.path, f"{rf.content_size:,} bytes")

        console.print(table)
        console.print(f"\n[bold]Total: {len(rule_files)} files[/bold]")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command(name="eval")
def eval_cmd(
    source: Path = typer.Argument(
        ...,
        help="Path to index JSON file or repository directory",
        exists=True,
        resolve_path=True,
    ),
    repo: Optional[Path] = typer.Option(
        None,
        "--repo",
        help="Repository path for reading source files from disk (when JSON lacks embedded content)",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path for eval results JSON",
    ),
    judge_model: str = typer.Option(
        DEFAULT_JUDGE_MODEL,
        "--judge-model",
        help="Model to use as judge",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """
    Evaluate rule extraction quality using an LLM judge.

    SOURCE can be a rules index JSON file or a repository directory.
    If a directory, runs discover → extract → eval pipeline.
    """
    from .rules.extractor import _make_client

    setup_logging(verbose)
    logger = logging.getLogger(__name__)

    try:
        if source.is_file():
            # Load existing index
            console.print(f"[bold]Loading index from {source}...[/bold]")
            rule_index, source_contents = load_index_with_sources(source, repo)
        else:
            # Run full pipeline: discover → extract → eval
            console.print(f"[bold]Discovering rules files in {source}...[/bold]")
            rule_files, source_contents = discover_rules_files(source)

            if not rule_files:
                console.print("[yellow]No rules files found.[/yellow]")
                raise typer.Exit(0)

            console.print(f"  Found {len(rule_files)} files")
            console.print("\n[bold]Extracting rules...[/bold]")
            processed_files = extract_rules_from_files(rule_files, source_contents)
            rule_index = build_index(str(source), processed_files)
            console.print(f"  Extracted {rule_index.rule_count} rules")

        if not rule_index.files:
            console.print("[yellow]No files to evaluate.[/yellow]")
            raise typer.Exit(0)

        # Run evaluation
        console.print(f"\n[bold]Evaluating with judge model: {judge_model}[/bold]")
        client = _make_client()
        summary = evaluate_index(rule_index, source_contents, client, model=judge_model)

        # Display results table
        table = Table(title="Evaluation Results")
        table.add_column("File", style="green", max_width=40)
        table.add_column("Rules", justify="right", style="cyan")
        table.add_column("Precision", justify="center")
        table.add_column("Recall", justify="center")
        table.add_column("F1", justify="center")

        for fe in summary.file_evaluations:
            _good = _cfg_output.metric_good_threshold
            _warn = _cfg_output.metric_warn_threshold
            p_style = "green" if fe.precision >= _good else ("yellow" if fe.precision >= _warn else "red")
            r_style = "green" if fe.recall >= _good else ("yellow" if fe.recall >= _warn else "red")
            f1_style = "green" if fe.f1 >= _good else ("yellow" if fe.f1 >= _warn else "red")
            table.add_row(
                Path(fe.file_path).name,
                str(fe.rule_count),
                f"[{p_style}]{fe.precision:.0%}[/{p_style}]",
                f"[{r_style}]{fe.recall:.0%}[/{r_style}]",
                f"[{f1_style}]{fe.f1:.0%}[/{f1_style}]",
            )

        console.print(table)

        # Overall summary
        console.print(f"\n[bold]Overall Precision:[/bold] {summary.overall_precision:.0%}")
        console.print(f"[bold]Overall Recall:[/bold]    {summary.overall_recall:.0%}")
        console.print(f"[bold]Overall F1:[/bold]        {summary.overall_f1:.0%}")
        console.print(f"[bold]Source Rules:[/bold]      {summary.total_source_rules}")
        console.print(f"[bold]Extracted Rules:[/bold]   {summary.total_rules}")
        console.print(f"[bold]Files Evaluated:[/bold]   {summary.total_files}")

        # Show detailed reasoning for low-scoring files
        low_scoring = [fe for fe in summary.file_evaluations if fe.f1 < _cfg_output.low_score_detail_threshold]
        if low_scoring:
            console.print("\n[bold yellow]Detailed reasoning for files with F1 < 80%:[/bold yellow]")
            for fe in low_scoring:
                console.print(f"\n  [bold]{fe.file_path}[/bold]")
                console.print(f"    Precision: {fe.precision:.0%}  Recall: {fe.recall:.0%}  F1: {fe.f1:.0%}")
                console.print(f"    {fe.reasoning}")
                if fe.missed_rules:
                    console.print("    Missed rules:")
                    for mr in fe.missed_rules:
                        console.print(f"      - {mr}")
                if fe.hallucinated_rules:
                    console.print("    Hallucinated rules:")
                    for hr in fe.hallucinated_rules:
                        console.print(f"      - {hr}")
                if fe.redundant_rules:
                    console.print("    Redundant rules:")
                    for rr in fe.redundant_rules:
                        console.print(f"      - {rr}")

        # Output JSON
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(summary.model_dump_json(indent=2))
            console.print(f"\n[bold]Results saved to {output}[/bold]")

    except typer.Exit:
        raise
    except Exception as e:
        logger.exception("Evaluation failed")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command(name="install-skill")
def install_skill(
    scope: str = typer.Option(
        "project",
        "--scope",
        help="Install scope: 'project' (.claude/skills/) or 'user' (~/.claude/skills/)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing SKILL.md without confirmation",
    ),
) -> None:
    """
    Install the repo-rules Claude Code skill.

    Copies the bundled SKILL.md to the appropriate skills directory
    so Claude Code can discover and use the repo-rules-agent CLI.
    """
    # Locate the bundled SKILL.md
    skill_source = Path(__file__).parent / "skill" / "SKILL.md"
    if not skill_source.exists():
        console.print("[red]Error: bundled SKILL.md not found in package[/red]")
        raise typer.Exit(1)

    # Determine target path
    if scope == "user":
        target = Path.home() / ".claude" / "skills" / "repo-rules" / "SKILL.md"
    elif scope == "project":
        target = Path.cwd() / ".claude" / "skills" / "repo-rules" / "SKILL.md"
    else:
        console.print(f"[red]Error: invalid scope '{scope}'. Use 'project' or 'user'.[/red]")
        raise typer.Exit(1)

    # Check if target already exists
    if target.exists() and not force:
        overwrite = typer.confirm(f"SKILL.md already exists at {target}. Overwrite?")
        if not overwrite:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    # Copy the skill file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(skill_source.read_text())
    console.print(f"[bold green]Skill installed to {target}[/bold green]")


if __name__ == "__main__":
    app()
