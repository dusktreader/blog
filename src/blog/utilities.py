from contextlib import contextmanager

from rich.progress import Progress, SpinnerColumn, TextColumn


@contextmanager
def spinner(text: str, max_length: int = 80):
    text = text[:max_length] if len(text) > max_length else text
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        progress.add_task(description=f"{text}...", total=None)
        yield


