import os
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger
from rich.console import Console
from rich.prompt import IntPrompt
from rich.table import Table


POSTS_DIR = Path("docs/source/posts")

console = Console()


def find_posts() -> list[Path]:
    return sorted(POSTS_DIR.glob("*.md"))


def match_posts(posts: list[Path], pattern: str) -> list[Path]:
    lower = pattern.lower()
    return [p for p in posts if lower in p.name.lower()]


def pick_post(matches: list[Path]) -> Path:
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="bold", justify="right")
    table.add_column("Post", no_wrap=True)

    for i, post in enumerate(matches, start=1):
        table.add_row(str(i), post.name)

    console.print(table)
    choice = IntPrompt.ask("Which post would you like to edit?", console=console)

    if not 1 <= choice <= len(matches):
        console.print(f"[red]Invalid choice: {choice}[/red]")
        raise typer.Exit(1)

    return matches[choice - 1]


cli = typer.Typer()


@cli.callback(invoke_without_command=True)
def edit(
    pattern: Annotated[
        str | None,
        typer.Argument(help="Substring or pattern to match against post filenames"),
    ] = None,
):
    """
    Open a blog post in an editor.

    With no argument, opens the most recently dated post. If a pattern is given,
    it is matched against post filenames as a case-insensitive substring. When
    multiple posts match, an interactive table lets you choose which one to open.
    """
    posts = find_posts()

    if not posts:
        console.print("[red]No posts found.[/red]")
        raise typer.Exit(1)

    if pattern is None:
        post = posts[-1]
        logger.debug(f"No pattern given; selecting latest post: {post.name}")
    else:
        matches = match_posts(posts, pattern)
        logger.debug(f"Pattern {pattern!r} matched {len(matches)} post(s)")

        if not matches:
            console.print(f"[red]No posts matched pattern: {pattern!r}[/red]")
            raise typer.Exit(1)
        elif len(matches) == 1:
            post = matches[0]
        else:
            post = pick_post(matches)

    logger.debug(f"Opening {post} in editor")
    subprocess.run([os.environ["EDITOR"], str(post)])
