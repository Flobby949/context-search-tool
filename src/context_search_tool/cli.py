from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional, Sequence

import typer

from context_search_tool.config import load_config
from context_search_tool.formatters import format_json, format_markdown
from context_search_tool.indexer import IncompatibleIndexError, index_repository
from context_search_tool.manifest import load_manifest
from context_search_tool.models import SymbolRef
from context_search_tool.paths import (
    RepositoryNotFoundError,
    find_repo_root,
    index_dir_for,
)
from context_search_tool.retrieval import query_repository
from context_search_tool.sqlite_store import SQLiteStore

app = typer.Typer(
    help="Context Search Tool",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Context Search Tool"""


@app.command()
def index(repo: Optional[Path] = typer.Argument(None)) -> None:
    resolved_repo = _resolve_repo(repo)
    config = load_config(resolved_repo)
    try:
        summary = index_repository(resolved_repo, config)
    except IncompatibleIndexError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        (
            f"Indexed {summary.files_indexed} files "
            f"({summary.chunks_indexed} chunks indexed, "
            f"{summary.files_skipped} skipped, {summary.files_deleted} deleted)."
        )
    )


@app.command()
def query(
    repo_or_question: str,
    question: Optional[str] = typer.Argument(None),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    context_lines: Optional[int] = typer.Option(
        None,
        "--context-lines",
        help="Override context lines around each result.",
    ),
    full_file: bool = typer.Option(
        False,
        "--full-file",
        help="Return full files when they are below the configured size limit.",
    ),
) -> None:
    if question is None:
        repo = _resolve_repo(None)
        query_text = repo_or_question
    else:
        repo = _resolve_repo(Path(repo_or_question))
        query_text = question

    config = load_config(repo)
    try:
        bundle = query_repository(
            repo,
            query_text,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(format_json(bundle))
        return
    typer.echo(format_markdown(bundle))


@app.command()
def status(repo: Optional[Path] = typer.Argument(None)) -> None:
    resolved_repo = _resolve_repo(repo)
    index_dir = index_dir_for(resolved_repo)
    paths = [
        ("index.sqlite", index_dir / "index.sqlite"),
        ("manifest.json", index_dir / "manifest.json"),
        ("vectors.npy", index_dir / "vectors.npy"),
        ("vector_ids.json", index_dir / "vector_ids.json"),
    ]

    typer.echo(f"Repository: {resolved_repo}")
    for name, path in paths:
        state = "present" if path.exists() else "missing"
        typer.echo(f"{name}: {state}")


@app.command()
def stats(repo: Optional[Path] = typer.Argument(None)) -> None:
    resolved_repo = _resolve_repo(repo)
    config = load_config(resolved_repo)
    index_dir = index_dir_for(resolved_repo)
    store = SQLiteStore(index_dir / "index.sqlite")
    store.initialize()
    counts = store.stats()
    manifest = (
        load_manifest(resolved_repo)
        if (index_dir / "manifest.json").exists()
        else None
    )

    provider = (
        manifest.embedding_provider
        if manifest is not None
        else config.embedding.provider
    )
    model = manifest.embedding_model if manifest is not None else config.embedding.model
    dimensions = (
        manifest.embedding_dimensions
        if manifest is not None
        else config.embedding.dimensions
    )

    typer.echo(f"Repository: {resolved_repo}")
    typer.echo(f"Total files: {counts['source_files']}")
    typer.echo(f"Total chunks: {counts['active_chunks']}")
    typer.echo(f"Deleted chunks: {counts['deleted_chunks']}")
    typer.echo(f"Symbols: {counts['symbols']}")
    typer.echo(f"Lexical tokens: {counts['tokens']}")
    typer.echo(
        f"Embedding: provider={provider} model={model} dimensions={dimensions}"
    )
    typer.echo(f"Disk usage: {_disk_usage(index_dir)} bytes")


@app.command()
def explain(
    repo_or_location: str,
    location: Optional[str] = typer.Argument(None),
) -> None:
    if location is None:
        resolved_repo = _resolve_repo(None)
        location_text = repo_or_location
    else:
        resolved_repo = _resolve_repo(Path(repo_or_location))
        location_text = location
    file_path, line = _parse_location(location_text, resolved_repo)
    index_dir = index_dir_for(resolved_repo)
    store = SQLiteStore(index_dir / "index.sqlite")
    store.initialize()

    try:
        chunk = store.chunk_for_line(file_path, line)
    except KeyError as exc:
        typer.echo(
            f"Error: no indexed chunk covers {file_path.as_posix()}:{line}",
            err=True,
        )
        raise typer.Exit(code=1) from exc

    typer.echo(f"File: {chunk.file_path.as_posix()}")
    typer.echo(f"Chunk ID: {chunk.chunk_id}")
    typer.echo(f"Type: {chunk.chunk_type}")
    typer.echo(f"Lines: {chunk.start_line}-{chunk.end_line}")
    typer.echo(f"Symbols: {_format_symbols(chunk.symbols)}")
    typer.echo(f"Lexical tokens: {_format_list(chunk.lexical_tokens)}")
    typer.echo(f"Embedding ID: {chunk.embedding_id or '(none)'}")
    typer.echo(f"Metadata: {chunk.metadata}")


@app.command()
def clean(repo: Optional[Path] = typer.Argument(None)) -> None:
    resolved_repo = _resolve_repo(repo)
    index_dir = index_dir_for(resolved_repo)
    if index_dir.exists():
        shutil.rmtree(index_dir)
    typer.echo(f"Cleaned {index_dir}")


def _resolve_repo(repo: Optional[Path]) -> Path:
    try:
        return find_repo_root(repo)
    except RepositoryNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _parse_location(location: str, repo: Path) -> tuple[Path, int]:
    if ":" not in location:
        raise typer.BadParameter("location must be file:line")
    raw_path, raw_line = location.rsplit(":", 1)
    try:
        line = int(raw_line)
    except ValueError as exc:
        raise typer.BadParameter("line must be an integer") from exc
    if line < 1:
        raise typer.BadParameter("line must be greater than zero")

    path = Path(raw_path)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(repo)
        except ValueError:
            pass
    return path, line


def _disk_usage(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _format_symbols(symbols: Sequence[SymbolRef]) -> str:
    rendered = [
        f"{symbol.kind}:{symbol.name}@{symbol.start_line}-{symbol.end_line}"
        for symbol in symbols
    ]
    return _format_list(rendered)


def _format_list(items: list[str]) -> str:
    return ", ".join(items) if items else "(none)"


if __name__ == "__main__":
    app()
