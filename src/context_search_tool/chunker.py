from __future__ import annotations

import hashlib
from pathlib import Path

from context_search_tool.models import DocumentChunk, SymbolRef
from context_search_tool.tokenizer import tokenize_identifier, tokens_for_path


def expand_lines(
    lines: list[str], start_line: int, end_line: int, before: int, after: int
) -> tuple[int, int, str]:
    expanded_start = max(1, start_line - before)
    expanded_end = min(len(lines), end_line + after)
    return (
        expanded_start,
        expanded_end,
        "\n".join(lines[expanded_start - 1 : expanded_end]),
    )


def chunk_text(
    path: Path,
    content: str,
    language: str,
    plugin_symbols: list[SymbolRef],
    max_lines: int = 80,
) -> list[DocumentChunk]:
    if max_lines <= 0:
        raise ValueError("max_lines must be positive")

    lines = content.splitlines()
    chunks: list[DocumentChunk] = []

    for index in range(0, len(lines), max_lines):
        start_line = index + 1
        end_line = min(index + max_lines, len(lines))
        chunk_content = "\n".join(lines[index:end_line])
        symbols = [
            symbol
            for symbol in plugin_symbols
            if _line_ranges_overlap(start_line, end_line, symbol.start_line, symbol.end_line)
        ]
        chunk_type = "symbol" if symbols else "generic"
        lexical_tokens = _dedupe_tokens(
            [
                *tokens_for_path(path),
                *tokenize_identifier(chunk_content),
                *(token for symbol in symbols for token in tokenize_identifier(symbol.name)),
            ]
        )

        chunks.append(
            DocumentChunk(
                chunk_id=_chunk_id(path, start_line, end_line, chunk_content),
                file_path=path,
                start_line=start_line,
                end_line=end_line,
                content=chunk_content,
                chunk_type=chunk_type,
                symbols=symbols,
                lexical_tokens=lexical_tokens,
                embedding_id=None,
                deleted_at=None,
                metadata={"language": language},
            )
        )

    return chunks


def _chunk_id(path: Path, start_line: int, end_line: int, content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    raw_id = f"{path.as_posix()}:{start_line}-{end_line}:{digest}"
    return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()


def _dedupe_tokens(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _line_ranges_overlap(
    left_start: int, left_end: int, right_start: int, right_end: int
) -> bool:
    return left_start <= right_end and right_start <= left_end
