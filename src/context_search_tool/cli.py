import typer

app = typer.Typer(
    help="Context Search Tool",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Context Search Tool"""


if __name__ == "__main__":
    app()
