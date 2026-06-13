from __future__ import annotations

import json
from typing import Any

from context_search_tool.retrieval import QueryBundle


def format_markdown(bundle: QueryBundle) -> str:
    lines = [
        "# Context Search Results",
        "",
        f"Query: {bundle.query}",
        f"Expanded tokens: {_format_list(bundle.expanded_tokens)}",
        "",
        "## Results",
    ]

    if not bundle.results:
        lines.append("No results.")
    else:
        for index, result in enumerate(bundle.results, start=1):
            lines.extend(
                [
                    "",
                    (
                        f"### {index}. {result.file_path.as_posix()}:"
                        f"{result.start_line}-{result.end_line}"
                    ),
                    f"Score: {result.score}",
                    "",
                    "Reasons:",
                    *_format_bullets(result.reasons),
                    "",
                    "Score parts:",
                    *_format_score_parts(result.score_parts),
                    "",
                    "Snippet:",
                    "```",
                    result.content,
                    "```",
                ]
            )

    lines.extend(
        [
            "",
            "## Follow-up Keywords",
            *_format_bullets(bundle.followup_keywords),
            "",
        ]
    )
    return "\n".join(lines)


def format_json(bundle: QueryBundle) -> str:
    payload: dict[str, Any] = {
        "query": bundle.query,
        "expanded_tokens": bundle.expanded_tokens,
        "followup_keywords": bundle.followup_keywords,
        "results": [
            {
                "file_path": result.file_path.as_posix(),
                "start_line": result.start_line,
                "end_line": result.end_line,
                "content": result.content,
                "score": result.score,
                "score_parts": result.score_parts,
                "reasons": result.reasons,
                "followup_keywords": result.followup_keywords,
            }
            for result in bundle.results
        ],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


def _format_list(items: list[str]) -> str:
    return ", ".join(items) if items else "(none)"


def _format_bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- (none)"]


def _format_score_parts(score_parts: dict[str, float]) -> list[str]:
    return [
        f"- {key}: {score_parts[key]}"
        for key in sorted(score_parts)
    ] or ["- (none)"]
