import snick
import typer

from blog.write import cli as write_cli
from blog.logging import init_logs
from blog.version import show_version


cli = typer.Typer(rich_markup_mode="rich")


@cli.callback(invoke_without_command=True)
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
        ctx.get_help()
        ctx.exit()

    init_logs(verbose=verbose)


cli.add_typer(write_cli, name="write")


if __name__ == "__main__":
    cli()
