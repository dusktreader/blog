import snick
import typer

from blog.config import cli as config_cli
from blog.exceptions import handle_abort
from blog.format import terminal_message
from blog.write import cli as write_cli
from blog.logging import init_logs
from blog.schemas import CliContext
from blog.version import show_version


cli = typer.Typer(rich_markup_mode="rich")


@cli.callback(invoke_without_command=True)
@handle_abort
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, help="Enable verbose logging to the terminal"),
    version: bool = typer.Option(False, help="Print the version of this app and exit"),
):
    """
    Welcome to the.dusktrader blog generator!

    More information can be shown for each command listed below by running it with the
    --help option.
    """

    if version:
        show_version()
        ctx.exit()

    if ctx.invoked_subcommand is None:
        terminal_message(
            snick.conjoin(
                "No command provided. Please check [bold magenta]usage[/bold magenta]",
                "",
                f"[yellow]{ctx.get_help()}[/yellow]",
            ),
            subject="Need an Armasec command",
        )
        ctx.exit()

    init_logs(verbose=verbose)
    ctx.obj = CliContext()


cli.add_typer(config_cli, name="config")
cli.add_typer(write_cli, name="write")


if __name__ == "__main__":
    cli()
