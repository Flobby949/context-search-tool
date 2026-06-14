from __future__ import annotations

import re
from pathlib import Path


_WORD_RE = re.compile(r"[A-Za-z0-9]+|[^\W_]+", re.UNICODE)
_ASCII_TOKEN_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|[0-9]|\b)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+"
)
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_CJK_CODE_ALIASES = {
    "工作流": ["workflow", "process", "流程"],
    "接口": ["api", "endpoint"],
    "审批": ["审核", "audit"],
    "待我审批": ["待我审核"],
}


def tokenize_identifier(value: str) -> list[str]:
    tokens: list[str] = []
    for word in _WORD_RE.findall(value):
        if word.isascii():
            tokens.extend(token.lower() for token in _ASCII_TOKEN_RE.findall(word))
        else:
            for token in [word, *_cjk_search_ngrams(word)]:
                tokens.append(token)
                tokens.extend(_CJK_CODE_ALIASES.get(token, []))
    return [token for token in tokens if token]


def tokenize_query(value: str) -> list[str]:
    return tokenize_identifier(value)


def tokens_for_path(path: Path | str) -> list[str]:
    return tokenize_identifier(Path(path).as_posix())


def _cjk_search_ngrams(value: str) -> list[str]:
    if not _CJK_RE.search(value):
        return []
    chars = list(value)
    ngrams: list[str] = []
    for size in (2, 3):
        if len(chars) < size:
            continue
        for index in range(0, len(chars) - size + 1):
            token = "".join(chars[index : index + size])
            if _CJK_RE.search(token):
                ngrams.append(token)
    return ngrams
