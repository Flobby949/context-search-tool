from __future__ import annotations

from dataclasses import replace
import shutil
from pathlib import Path
from typing import Optional, Sequence

import requests
import typer

from context_search_tool.config import ToolConfig, load_config
from context_search_tool.context_pack import (
    UNEXPECTED_CONTEXT_ERROR,
    ContextPackError,
    build_context_pack,
    resolve_context_pack_options,
)
from context_search_tool.formatters import (
    format_context_json,
    format_context_markdown,
    format_json,
    format_markdown,
    query_payload,
)
from context_search_tool.indexer import (
    IncompatibleIndexError,
    index_repository,
    signal_schema_is_current,
)
from context_search_tool.manifest import load_manifest
from context_search_tool.models import SymbolRef
from context_search_tool.paths import (
    RepositoryNotFoundError,
    find_repo_root,
    index_dir_for,
)
from context_search_tool.retrieval import evidence_anchor_top_k, query_repository
from context_search_tool.sqlite_store import SQLiteStore

app = typer.Typer(
    help="Context Search Tool",
    no_args_is_help=True,
)

from context_search_tool.quality.__main__ import quality_app

app.add_typer(quality_app, name="quality")


@app.callback()
def main() -> None:
    """Context Search Tool"""


@app.command()
def index(repo: Optional[Path] = typer.Argument(None)) -> None:
    resolved_repo = _resolve_repo(repo)
    config = load_config(resolved_repo)
    try:
        summary = index_repository(resolved_repo, config)
    except (IncompatibleIndexError, ValueError, requests.HTTPError) as exc:
        _exit_with_error(exc)

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
    planner: bool = typer.Option(False, "--planner", help="Force query planner on."),
    no_planner: bool = typer.Option(
        False,
        "--no-planner",
        help="Force query planner off.",
    ),
) -> None:
    repo, query_text, config = _prepare_query_command(
        repo_or_question,
        question,
        planner=planner,
        no_planner=no_planner,
    )
    try:
        bundle = query_repository(
            repo,
            query_text,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
    except (ValueError, requests.HTTPError) as exc:
        _exit_with_error(exc)

    if json_output:
        typer.echo(format_json(bundle))
        return
    typer.echo(format_markdown(bundle))


@app.command()
def context(
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
    planner: bool = typer.Option(False, "--planner", help="Force query planner on."),
    no_planner: bool = typer.Option(
        False,
        "--no-planner",
        help="Force query planner off.",
    ),
) -> None:
    repo, query_text, config = _prepare_query_command(
        repo_or_question,
        question,
        planner=planner,
        no_planner=no_planner,
    )
    try:
        bundle = query_repository(
            repo,
            query_text,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
        raw_payload = query_payload(bundle)
    except (ValueError, requests.HTTPError) as exc:
        _exit_with_error(exc)

    try:
        anchor_limit = evidence_anchor_top_k(config.retrieval.final_top_k)
        pack_options = resolve_context_pack_options(
            config,
            context_lines=context_lines,
            full_file=full_file,
            max_evidence_anchors=anchor_limit,
        )
        pack = build_context_pack(bundle, pack_options)
        output = (
            format_context_json(raw_payload, bundle, pack)
            if json_output
            else format_context_markdown(bundle, pack)
        )
    except ContextPackError as exc:
        _exit_context_error(str(exc))
    except Exception:
        _exit_context_error(UNEXPECTED_CONTEXT_ERROR)
    typer.echo(output)


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
    index_dir = _require_index(resolved_repo)
    config = load_config(resolved_repo)
    store = SQLiteStore(index_dir / "index.sqlite")
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
    index_dir = _require_index(resolved_repo)
    store = SQLiteStore(index_dir / "index.sqlite")

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


def _prepare_query_command(
    repo_or_question: str,
    question: str | None,
    *,
    planner: bool,
    no_planner: bool,
) -> tuple[Path, str, ToolConfig]:
    if question is None:
        repo = _resolve_repo(None)
        query_text = repo_or_question
    else:
        repo = _resolve_repo(Path(repo_or_question))
        query_text = question
    _require_index(repo)
    config = load_config(repo)
    if planner and no_planner:
        typer.echo(
            "Error: --planner and --no-planner cannot be used together",
            err=True,
        )
        raise typer.Exit(code=1)
    if planner or no_planner:
        config = replace(
            config,
            query_planner=replace(config.query_planner, enabled=planner),
        )
    _warn_if_signal_schema_stale(repo)
    return repo, query_text, config


def _resolve_repo(repo: Optional[Path]) -> Path:
    try:
        return find_repo_root(repo)
    except RepositoryNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _require_index(repo: Path) -> Path:
    index_dir = index_dir_for(repo)
    if not (index_dir / "index.sqlite").exists():
        typer.echo(
            f"Error: missing index for {repo}. Run 'cst index {repo}' first.",
            err=True,
        )
        raise typer.Exit(code=1)
    return index_dir


def _warn_if_signal_schema_stale(repo: Path) -> None:
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    store.initialize()
    if signal_schema_is_current(store):
        return
    typer.echo(
        "Warning: index signal schema is older than this version. "
        "Run index again for signal-aware retrieval.",
        err=True,
    )


def _exit_with_error(exc: Exception) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1) from exc


def _exit_context_error(message: str) -> None:
    typer.echo(f"Error: context_failed: {message}", err=True)
    raise typer.Exit(code=1) from None


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
