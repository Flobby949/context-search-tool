from __future__ import annotations

from dataclasses import replace
import json
import shutil
from pathlib import Path
from typing import Optional, Sequence

import requests
import typer

from context_search_tool import index_health
from context_search_tool.config import ToolConfig, load_config
from context_search_tool.context_pack import (
    ContextPackError,
    build_context_pack,
    resolve_context_pack_options,
)
from context_search_tool.formatters import (
    context_payload,
    format_context_json,
    format_context_markdown,
    format_explore_json,
    format_explore_markdown,
    format_json,
    format_markdown,
    format_trace_json,
    format_trace_markdown,
    explore_payload,
    trace_payload,
)
from context_search_tool.indexer import (
    IncompatibleIndexError,
    RefreshFailure,
    RefreshSuccess,
    index_repository,
    refresh_repository,
)
from context_search_tool.graph_lifecycle import (
    IncompatibleOperationalSchemaError,
    IncompatibleSignalSchemaError,
    IndexBusyError,
    read_graph_capability,
)
from context_search_tool.manifest import IncompatibleManifestSchemaError
from context_search_tool.models import SymbolRef
from context_search_tool.paths import (
    RepositoryNotFoundError,
    find_repo_root,
    index_dir_for,
)
from context_search_tool.retrieval import (
    evidence_anchor_top_k,
    query_repository,
    trace_repository,
)
from context_search_tool.retrieval_trace import RetrievalTraceError
from context_search_tool.sqlite_store import SQLiteStore

app = typer.Typer(
    help="Context Search Tool",
    no_args_is_help=True,
)

_CONTEXT_FAILED_MESSAGE = "Context pack construction failed"

from context_search_tool.quality.__main__ import quality_app

app.add_typer(quality_app, name="quality")


@app.callback()
def main() -> None:
    """Context Search Tool"""


@app.command()
def index(repo: Optional[Path] = typer.Argument(None)) -> None:
    resolved_repo = _resolve_repo(repo)
    try:
        index_health.preflight_public_operation(resolved_repo, "index")
        summary = index_repository(
            resolved_repo,
            config_loader=load_config,
        )
    except requests.RequestException:
        _exit_with_error(ValueError("remote embedding request failed"))
    except (
        IncompatibleIndexError,
        IncompatibleManifestSchemaError,
        IncompatibleOperationalSchemaError,
        IncompatibleSignalSchemaError,
        IndexBusyError,
        index_health.IndexCorruptionError,
        ValueError,
    ) as exc:
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
        operation="query",
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
def trace(
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
        help="Trace full-file result expansion when configured limits allow it.",
    ),
    planner: bool = typer.Option(False, "--planner", help="Force query planner on."),
    no_planner: bool = typer.Option(
        False,
        "--no-planner",
        help="Force query planner off.",
    ),
) -> None:
    """Return a bounded RetrievalTrace v1 diagnostic response."""
    repo, query_text, config = _prepare_query_command(
        repo_or_question,
        question,
        operation="trace",
        planner=planner,
        no_planner=no_planner,
    )
    try:
        traced = trace_repository(
            repo,
            query_text,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
        envelope = trace_payload(repo, query_text, traced.trace)
        output = (
            format_trace_json(envelope)
            if json_output
            else format_trace_markdown(envelope)
        )
    except RetrievalTraceError:
        typer.echo("Retrieval trace failed", err=True)
        raise typer.Exit(code=1)
    except (ValueError, requests.HTTPError) as exc:
        _exit_with_error(exc)
    except Exception:
        typer.echo("Retrieval trace failed", err=True)
        raise typer.Exit(code=1)
    typer.echo(output)


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
    max_items: Optional[int] = typer.Option(
        None,
        "--max-items",
        help="Override the maximum number of context items.",
    ),
    max_context_bytes: Optional[int] = typer.Option(
        None,
        "--max-context-bytes",
        help="Override the canonical JSON context pack byte limit.",
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
        operation="context",
        planner=planner,
        no_planner=no_planner,
    )
    try:
        anchor_limit = evidence_anchor_top_k(config.retrieval.final_top_k)
        pack_options = resolve_context_pack_options(
            config,
            context_lines=context_lines,
            max_evidence_anchors=anchor_limit,
            max_items=max_items,
            max_pack_bytes=max_context_bytes,
        )
    except ContextPackError as exc:
        _exit_context_error(exc.code, exc.message)

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

    try:
        pack = build_context_pack(bundle, pack_options)
        envelope = context_payload(repo, bundle, pack)
        output = (
            format_context_json(envelope)
            if json_output
            else format_context_markdown(envelope)
        )
    except ContextPackError:
        _exit_context_error("context_failed", _CONTEXT_FAILED_MESSAGE)
    except Exception:
        _exit_context_error("context_failed", _CONTEXT_FAILED_MESSAGE)
    typer.echo(output)


@app.command()
def explore(
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
    max_items: Optional[int] = typer.Option(
        None,
        "--max-items",
        help="Override the maximum number of context items.",
    ),
    max_context_bytes: Optional[int] = typer.Option(
        None,
        "--max-context-bytes",
        help="Override the canonical JSON context pack byte limit.",
    ),
    planner: bool = typer.Option(False, "--planner", help="Force query planner on."),
    no_planner: bool = typer.Option(
        False,
        "--no-planner",
        help="Force query planner off.",
    ),
) -> None:
    """Return a bounded two-round controlled exploration result."""
    from context_search_tool.exploration import (
        explore_repository,
        resolve_explore_pack_options,
    )
    from context_search_tool.exploration.options import resolve_explore_config

    repo, query_text, config = _prepare_query_command(
        repo_or_question,
        question,
        operation="explore",
        planner=planner,
        no_planner=no_planner,
    )
    try:
        explore_config, _, effective_initial_top_k = resolve_explore_config(
            config,
            final_top_k=None,
        )
        pack_options = resolve_explore_pack_options(
            explore_config,
            context_lines=context_lines,
            max_items=max_items,
            max_pack_bytes=max_context_bytes,
        )
    except ContextPackError as exc:
        _exit_context_error(exc.code, exc.message)
    except ValueError as exc:
        _exit_with_error(exc)
    except Exception:
        _exit_explore_error()

    try:
        explored = explore_repository(
            repo,
            query_text,
            explore_config,
            pack_options,
            context_lines=context_lines,
            full_file=full_file,
        )
    except (ValueError, requests.HTTPError) as exc:
        _exit_with_error(exc)
    except Exception:
        _exit_explore_error()

    try:
        envelope = explore_payload(
            repo,
            query_text,
            explored,
            requested_final_top_k=None,
        )
        if (
            envelope["retrieval"]["effective_initial_top_k"]
            != effective_initial_top_k
        ):
            raise ValueError("exploration limit mismatch")
        output = (
            format_explore_json(envelope)
            if json_output
            else format_explore_markdown(envelope)
        )
    except Exception:
        _exit_explore_error()
    typer.echo(output)


@app.command()
def status(
    repo: Optional[Path] = typer.Argument(None),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verify: bool = typer.Option(
        False,
        "--verify",
        help="Verify source content and vector identities.",
    ),
    requirement: Optional[str] = typer.Option(
        None,
        "--require",
        help="Require verified, metadata, or queryable health.",
    ),
) -> None:
    if requirement not in {None, "verified", "metadata", "queryable"}:
        typer.echo(
            "Error: --require must be verified, metadata, or queryable",
            err=True,
        )
        raise typer.Exit(code=1)
    try:
        resolved_repo = find_repo_root(repo)
    except RepositoryNotFoundError:
        envelope = index_health.status_error_envelope("repo_not_found")
        if json_output:
            typer.echo(_json(envelope))
        else:
            typer.echo("Error: repository root was not found", err=True)
        raise typer.Exit(code=1)
    try:
        report = index_health.inspect_repository_health(
            resolved_repo,
            mode="verified" if verify else "quick",
        )
    except Exception:
        envelope = index_health.status_error_envelope("status_failed")
        if json_output:
            typer.echo(_json(envelope))
        else:
            typer.echo("Error: status inspection failed", err=True)
        raise typer.Exit(code=1)

    envelope = index_health.status_success_envelope(str(resolved_repo), report)
    if json_output:
        typer.echo(_json(envelope))
    else:
        typer.echo(index_health.format_index_health_human(resolved_repo, report))
    if requirement is not None and not index_health.status_requirement_satisfied(
        report,
        requirement,
    ):
        typer.echo(
            f"Error: status requirement '{requirement}' was not met",
            err=True,
        )
        raise typer.Exit(code=1)


@app.command()
def refresh(
    repo: Optional[Path] = typer.Argument(None),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Mutates an index; new/content-changed text may be sent to a remote provider."""
    try:
        resolved_repo = find_repo_root(repo)
    except RepositoryNotFoundError:
        _exit_refresh_error(
            index_health.refresh_error_envelope("repo_not_found"),
            json_output=json_output,
        )
    try:
        result = refresh_repository(
            resolved_repo,
            config_loader=load_config,
        )
    except Exception:
        _exit_refresh_error(
            index_health.refresh_error_envelope("refresh_failed"),
            json_output=json_output,
        )
    if isinstance(result, RefreshFailure):
        _exit_refresh_error(
            index_health.refresh_error_envelope(
                result.code,
                result.network_egress_outcome,
            ),
            json_output=json_output,
        )
    if not isinstance(result, RefreshSuccess):
        _exit_refresh_error(
            index_health.refresh_error_envelope("refresh_failed", "possible"),
            json_output=json_output,
        )
    try:
        report = index_health.inspect_repository_health(resolved_repo, mode="quick")
        envelope = index_health.refresh_success_envelope(
            str(resolved_repo),
            summary=result.summary,
            indexed_before=result.indexed_before,
            configured=result.configured,
            network_egress_performed=result.network_egress_performed,
            report=report,
        )
    except Exception:
        _exit_refresh_error(
            index_health.refresh_error_envelope(
                "refresh_failed",
                (
                    "performed"
                    if result.network_egress_performed
                    else "not_attempted"
                ),
            ),
            json_output=json_output,
        )
    typer.echo(
        _json(envelope)
        if json_output
        else index_health.format_refresh_human(envelope)
    )


@app.command()
def stats(
    repo: Optional[Path] = typer.Argument(None),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    verify: bool = typer.Option(
        False,
        "--verify",
        help="Verify source content and vector identities.",
    ),
) -> None:
    try:
        resolved_repo = find_repo_root(repo)
    except RepositoryNotFoundError as exc:
        _exit_stats_error("repo_not_found", str(exc), json_output=json_output)
    try:
        index_health.preflight_public_operation(resolved_repo, "stats")
        report = index_health.inspect_repository_health(
            resolved_repo,
            mode="verified" if verify else "quick",
        )
        payload = index_health.build_index_stats_payload(resolved_repo, report)
    except index_health.MissingIndexError:
        _exit_stats_error(
            "missing_index",
            f"missing index for {resolved_repo}. Run 'cst index {resolved_repo}' first.",
            json_output=json_output,
        )
    except (
        IncompatibleManifestSchemaError,
        IncompatibleOperationalSchemaError,
        IncompatibleSignalSchemaError,
    ) as exc:
        _exit_stats_error(exc.code, str(exc), json_output=json_output)
    except index_health.IndexCorruptionError as exc:
        _exit_stats_error(exc.code, str(exc), json_output=json_output)
    except Exception:
        _exit_stats_error(
            "stats_failed",
            "statistics inspection failed",
            json_output=json_output,
        )

    if report.integrity.graph == "stale":
        typer.echo(
            "Warning: P5 graph index is stale; "
            "signal and relation evidence was skipped.",
            err=True,
        )
    if json_output:
        typer.echo(_json(payload))
        return
    stats_payload = payload["stats"]
    embedding = payload["embedding"]
    typer.echo(f"Repository: {resolved_repo}")
    typer.echo(f"Total files: {stats_payload['total_files']}")
    typer.echo(f"Total chunks: {stats_payload['total_chunks']}")
    typer.echo(f"Deleted chunks: {stats_payload['deleted_chunks']}")
    typer.echo(f"Symbols: {stats_payload['symbols']}")
    typer.echo(f"Lexical tokens: {stats_payload['lexical_tokens']}")
    typer.echo(
        "Embedding: "
        f"provider={embedding['provider']} model={embedding['model']} "
        f"dimensions={embedding['dimensions']}"
    )
    typer.echo(f"Disk usage: {stats_payload['disk_usage_bytes']} bytes")
    typer.echo(f"Indexed files: {_format_stat(stats_payload['indexed_files'])}")
    typer.echo(f"Coverage skips: {_format_stat(stats_payload['coverage_skips'])}")
    typer.echo(
        "Vector coverage: "
        f"{_format_stat(stats_payload['vector_rows'])}/"
        f"{_format_stat(stats_payload['vector_eligible_chunks'])} "
        f"({stats_payload['vector_coverage_evidence']})"
    )
    typer.echo(
        "Schemas: "
        f"manifest={_format_stat(stats_payload['manifest_schema_version'])} "
        f"operational={_format_stat(stats_payload['operational_schema_version'])} "
        f"graph={_format_stat(stats_payload['graph_schema_version'])}"
    )
    typer.echo(f"Last work: {stats_payload['last_work'] or '(none)'}")
    typer.echo(f"Health: {report.health}")
    typer.echo(
        f"Freshness: {report.freshness.status} "
        f"({report.freshness.inspection_mode})"
    )


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
    _preflight_cli_consumer(resolved_repo, "explain")
    file_path, line = _parse_location(location_text, resolved_repo)
    index_dir = index_dir_for(resolved_repo)
    _warn_if_signal_schema_stale(resolved_repo)
    store = SQLiteStore(index_dir / "index.sqlite")

    try:
        with store.graph_read_session() as graph_session:
            chunk = graph_session.chunk_for_line(file_path, line)
            if chunk is None:
                raise KeyError(file_path)
            graph = graph_session.explain_projection(chunk)
    except KeyError as exc:
        typer.echo(
            f"Error: no indexed chunk covers {file_path.as_posix()}:{line}",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except IncompatibleSignalSchemaError as exc:
        _exit_with_error(exc)

    typer.echo(f"File: {chunk.file_path.as_posix()}")
    typer.echo(f"Chunk ID: {chunk.chunk_id}")
    typer.echo(f"Type: {chunk.chunk_type}")
    typer.echo(f"Lines: {chunk.start_line}-{chunk.end_line}")
    typer.echo(f"Symbols: {_format_symbols(chunk.symbols)}")
    typer.echo(f"Lexical tokens: {_format_list(chunk.lexical_tokens)}")
    typer.echo(f"Embedding ID: {chunk.embedding_id or '(none)'}")
    typer.echo(f"Metadata: {chunk.metadata}")
    typer.echo(
        f"Graph: {graph['status']} (signal schema {graph['schema_version']})"
    )
    typer.echo(
        f"Graph signals: {len(graph['signals'])} "
        f"(omitted {graph['omitted_signal_count']})"
    )
    typer.echo(
        f"Graph outgoing: {len(graph['outgoing'])} "
        f"(omitted {graph['omitted_outgoing_count']})"
    )
    typer.echo(
        f"Graph incoming: {len(graph['incoming'])} "
        f"(omitted {graph['omitted_incoming_count']})"
    )
    for signal in graph["signals"]:
        name = signal["qualified_name"] or signal["name"]
        typer.echo(
            f"Signal: {signal['kind']} {name} [{signal['producer']}] "
            f"{signal['start_line']}-{signal['end_line']}"
        )
    for direction, rows in (("Outgoing", graph["outgoing"]), ("Incoming", graph["incoming"])):
        for relation in rows:
            source = relation["source_name"] or relation["source_signal_id"]
            target = relation["target_name"] or relation["target_signal_id"]
            typer.echo(
                f"{direction}: {relation['kind']} {relation['resolution']} "
                f"{source} -> {target} ({relation['confidence']:.6g})"
            )


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
    operation: str,
    planner: bool,
    no_planner: bool,
) -> tuple[Path, str, ToolConfig]:
    if question is None:
        repo = _resolve_repo(None)
        query_text = repo_or_question
    else:
        repo = _resolve_repo(Path(repo_or_question))
        query_text = question
    _preflight_cli_consumer(repo, operation)
    if planner and no_planner:
        typer.echo(
            "Error: --planner and --no-planner cannot be used together",
            err=True,
        )
        raise typer.Exit(code=1)
    _warn_if_signal_schema_stale(repo)
    config = load_config(repo)
    if planner or no_planner:
        config = replace(
            config,
            query_planner=replace(config.query_planner, enabled=planner),
        )
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


def _preflight_cli_consumer(repo: Path, operation: str) -> None:
    try:
        index_health.preflight_public_operation(repo, operation)
    except index_health.MissingIndexError:
        _require_index(repo)
    except (
        IncompatibleManifestSchemaError,
        IncompatibleOperationalSchemaError,
        IncompatibleSignalSchemaError,
        index_health.IndexCorruptionError,
    ) as exc:
        _exit_with_error(exc)


def _warn_if_signal_schema_stale(repo: Path) -> None:
    capability = _graph_capability(repo)
    if capability.status != "stale":
        return
    typer.echo(
        "Warning: P5 graph index is stale; signal and relation evidence was skipped.",
        err=True,
    )


def _graph_capability(repo: Path):
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    try:
        return read_graph_capability(store)
    except IncompatibleSignalSchemaError as exc:
        _exit_with_error(exc)


def _exit_with_error(exc: Exception) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1) from exc


def _exit_stats_error(
    code: str,
    message: str,
    *,
    json_output: bool,
) -> None:
    if json_output:
        typer.echo(_json({"ok": False, "error": {"code": code, "message": message}}))
    else:
        typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


def _exit_context_error(code: str, message: str) -> None:
    typer.echo(f"Error: {code}: {message}", err=True)
    raise typer.Exit(code=1) from None


def _exit_refresh_error(
    envelope: dict[str, object],
    *,
    json_output: bool,
) -> None:
    if json_output:
        typer.echo(_json(envelope))
    else:
        error = envelope["error"]
        assert isinstance(error, dict)
        typer.echo(f"Error: {error['message']}", err=True)
    raise typer.Exit(code=1)


def _exit_explore_error() -> None:
    typer.echo("Controlled exploration failed", err=True)
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


def _json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _format_stat(value: object) -> str:
    return "unknown" if value is None else str(value)


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
