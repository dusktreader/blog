from typing import Any

import snick
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown


def terminal_message(
    message,
    subject=None,
    color="green",
    footer=None,
    indent=True,
    markdown=False,
):
    panel_kwargs: dict[str, Any] = dict(padding=1)
    if subject is not None:
        panel_kwargs["title"] = f"[{color}]{subject}"
    if footer is not None:
        panel_kwargs["subtitle"] = f"[dim italic]{footer}[/dim italic]"
    text = snick.dedent(message)
    if indent:
        text = snick.indent(text, prefix="  ")
    if markdown:
        text = Markdown(text)
    console = Console()
    console.print()
    console.print(Panel(text, **panel_kwargs))
    console.print()


def simple_message(message, indent=False, markdown=False):
    text = snick.dedent(message)
    if indent:
        text = snick.indent(text, prefix="  ")
    if markdown:
        text = Markdown(text)
    console = Console()
    console.print()
    console.print(text)
    console.print()
