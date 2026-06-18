from __future__ import annotations

import argparse
import functools
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

import context_search_tool.retrieval as retrieval
from context_search_tool.config import load_config
from context_search_tool.paths import index_dir_for
from context_search_tool.sqlite_store import SQLiteStore


RETRIEVAL_FUNCTIONS = [
    "_semantic_candidates",
    "_lexical_candidates",
    "_direct_text_candidates",
    "_signal_candidates",
    "_planner_hint_candidates",
    "_anchor_expansion_candidates",
    "_relation_expansion_candidates",
    "_rank_chunks",
    "_expand_ranked_chunks",
    "_split_code_results_and_evidence_anchors",
    "_summarize_results",
]

STORE_METHODS = [
    "deleted_chunk_ids",
    "direct_text_search",
    "signal_search",
    "path_symbol_search",
    "signals_for_chunk",
    "signals_for_chunks",
    "relations_for_source",
    "relations_for_sources",
    "chunks_matching_signal_or_symbol",
    "chunks_matching_signal_or_symbols",
    "chunk_for_id",
    "chunks_for_ids",
    "chunks_for_file",
    "chunks_in_directory",
    "lexical_search",
    "relations_targeting",
]


@dataclass
class Timing:
    seconds: float = 0.0
    calls: int = 0


Original = tuple[Any, str, Any]


def _timed(
    name: str,
    original: Callable[..., Any],
    timings: dict[str, Timing],
) -> Callable[..., Any]:
    @functools.wraps(original)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            timing = timings[name]
            timing.seconds += elapsed
            timing.calls += 1

    return wrapper


def _wrap_retrieval_functions(timings: dict[str, Timing]) -> list[Original]:
    originals: list[Original] = []
    for name in RETRIEVAL_FUNCTIONS:
        original = getattr(retrieval, name, None)
        if original is None:
            continue
        timings[name] = Timing()
        setattr(retrieval, name, _timed(name, original, timings))
        originals.append((retrieval, name, original))
    return originals


def _wrap_store_methods(timings: dict[str, Timing]) -> list[Original]:
    originals: list[Original] = []
    for name in STORE_METHODS:
        original = getattr(SQLiteStore, name, None)
        if original is None:
            continue
        timing_name = f"store.{name}"
        timings[timing_name] = Timing()
        setattr(SQLiteStore, name, _timed(timing_name, original, timings))
        originals.append((SQLiteStore, name, original))
    return originals


def _restore(originals: list[Original]) -> None:
    for target, name, original in reversed(originals):
        setattr(target, name, original)


def _print_timings(timings: dict[str, Timing]) -> None:
    for name, timing in sorted(
        timings.items(),
        key=lambda item: (-item[1].seconds, item[0]),
    ):
        print(f"{name}: {timing.seconds * 1000:.1f}ms calls={timing.calls}")


def _print_top_results(results: list[Any]) -> None:
    print("top:")
    for result in results[:5]:
        print(
            f"{result.file_path}:{result.start_line}-{result.end_line} "
            f"score={result.score:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Local retrieval profiling helper for real-project smoke checks."
    )
    parser.add_argument("repo", type=Path)
    parser.add_argument("query")
    args = parser.parse_args()

    index_path = index_dir_for(args.repo) / "index.sqlite"
    if not index_path.exists():
        parser.error(f"missing index: {index_path}")

    timings: dict[str, Timing] = {}
    originals = [
        *_wrap_retrieval_functions(timings),
        *_wrap_store_methods(timings),
    ]

    start = time.perf_counter()
    try:
        bundle = retrieval.query_repository(args.repo, args.query, load_config(args.repo))
    finally:
        total_seconds = time.perf_counter() - start
        _restore(originals)

    print(f"total_ms={total_seconds * 1000:.1f} results={len(bundle.results)}")
    _print_timings(timings)
    _print_top_results(bundle.results)


if __name__ == "__main__":
    main()
