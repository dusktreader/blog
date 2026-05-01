from collections import Counter
from pathlib import Path

import typer
import yaml
from loguru import logger
from rich.console import Console
from rich.table import Table


POSTS_DIR = Path("docs/source/posts")

console = Console()


def _parse_frontmatter(post_path: Path) -> dict:
    """Parse the YAML frontmatter from a post file."""
    text = post_path.read_text()
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("---", 3)
    except ValueError:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        logger.warning(f"Could not parse frontmatter in {post_path.name}")
        return {}


def _collect(field: str) -> Counter:
    """Count occurrences of each value for a frontmatter field across all posts."""
    counts: Counter = Counter()
    for post_path in sorted(POSTS_DIR.glob("*.md")):
        fm = _parse_frontmatter(post_path)
        raw = fm.get(field) or []
        if isinstance(raw, str):
            raw = [raw]
        # Split any comma-joined entries (e.g. "Python,Typer" -> ["Python", "Typer"])
        for item in raw:
            for value in (v.strip() for v in str(item).split(",") if v.strip()):
                counts[value] += 1
    return counts


def _display(counts: Counter, label: str) -> None:
    """Render a sorted table of names and post counts."""
    if not counts:
        console.print(f"[yellow]No {label} found.[/yellow]")
        return

    table = Table(title=label.capitalize(), show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Posts", justify="right", style="green")

    for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        table.add_row(name, str(count))

    console.print(table)


cli = typer.Typer(help="Show information about the blog's posts.")


@cli.command()
def tags():
    """List all tags used across posts, sorted by frequency."""
    logger.debug("Collecting tags from posts")
    counts = _collect("tags")
    _display(counts, "tags")


@cli.command()
def categories():
    """List all categories used across posts, sorted by frequency."""
    logger.debug("Collecting categories from posts")
    counts = _collect("categories")
    _display(counts, "categories")
