import subprocess
import textwrap
from pathlib import Path
from typing import Annotated

import snick
import typer
import yaml
from inflection import parameterize
from loguru import logger

from blog.config import attach_settings


def build_post(
    timestamp: str,
    title: str,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    logger.debug("Assembling post")
    parts: list[str] = []
    metadata = dict(
        date=timestamp,
        authors=["the.dusktreader"],
        comments=True,
    )
    if tags:
        metadata["tags"] = tags
    if categories:
        metadata["categories"] = categories

    parts.append("---")
    parts.append(yaml.dump(metadata, sort_keys=False))
    parts.append("---")
    parts.append("")
    parts.append(f"# {title}")
    parts.append("")
    parts.append(
        snick.dedent(
            """
            !!! tip "TLDR"
                ...tldr...
            """
        )
    )
    parts.append("")
    parts.append("...summary...")
    parts.append("")
    parts.append("<!-- more -->")
    parts.append("")
    parts.append("...body...")
    parts.append("")
    parts.append("Thanks for reading!")

    return "\n".join(parts)

def wrap_post(post_text: str, markdown_textwrap: int) -> str:
    logger.debug(f"Wrapping post to {markdown_textwrap} characters")
    long_paragraphs: list[str] = post_text.split("\n\n")
    short_paragraphs: list[str] = [textwrap.fill(p, width=markdown_textwrap) for p in long_paragraphs]
    post_text = "\n\n".join(short_paragraphs)
    return post_text


def get_post_path(title: str, timestamp: str) -> Path:
    return Path("docs/source/posts") / f"{timestamp}--{parameterize(title)}.md"


def save_post(post_text: str, post_path: Path):
    logger.debug(f"Saving post to {post_path}")
    post_path.write_text(post_text)


def edit_post(post_path: Path, editor_command: str):
    logger.debug(f"Editing post at {post_path}")
    subprocess.run([editor_command, str(post_path)])


cli = typer.Typer()


@cli.callback(invoke_without_command=True)
@attach_settings
def write(
    ctx: typer.Context,
    title: Annotated[str, typer.Argument(help="The title of the new post")],
    categories: Annotated[list[str] | None, typer.Option(help="Categories to add to the post")] = None,
    tags: Annotated[list[str] | None, typer.Option(help="Tags to add to the post")] = None,
):
    """
    Genarate a new post for the blog and open it in an editor.
    """
    editor_command = ctx.obj.settings.editor_command
    markdown_textwrap = ctx.obj.settings.markdown_textwrap
    timestamp = ctx.obj.timestamp

    post_text: str = build_post(timestamp, title, categories=categories, tags=tags)
    post_text = wrap_post(post_text, markdown_textwrap=markdown_textwrap)
    post_path = get_post_path(title, timestamp)
    save_post(post_text, post_path)
    edit_post(post_path, editor_command)
