"""CLI entry point for pimp-my-repo."""

import typer

app = typer.Typer(
    name="pimp-my-repo",
    help="🧙🏼‍♂️ A CLI wizard designed to modernize your Python repositories",
)


@app.command()
def run(
    path: str = typer.Option(
        ".",
        "--path",
        "-p",
        help="Path to the repository to pimp",
    ),
    wizard: bool = typer.Option(  # noqa: FBT001
        False,  # noqa: FBT003
        "--wizard",
        "-w",
        help="Enable interactive wizard mode (not implemented yet)",
    ),
) -> None:
    """Pimp a repository."""
    typer.echo(f"Pimping repository at: {path}")
    if wizard:
        typer.echo("Wizard mode is not yet implemented")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
