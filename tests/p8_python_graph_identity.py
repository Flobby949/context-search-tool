"""Frozen P8 identity constants and protected-input validation.

Behavior-baseline note: the P8 plan originally anchored the A/B baseline to
75cc65ed627dd5982460a4d4a10d28f10e7151b8 (pre storage-layout-v2 main). Between
plan review and implementation authorization, main merged storage layout v2
(retrieval-output neutral, characterization-proven) and followup-keyword
filtering (rendered-output change). To keep the A/B comparison a pure P8
delta, the baseline is re-anchored to the last pre-P8 main commit. The
original anchor is retained below for audit.
"""

from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path

P8_BEHAVIOR_BASELINE = "117f46bdd9f067d50ce66b553cd85d7488649eed"
P8_PLAN_ORIGINAL_BASELINE = "75cc65ed627dd5982460a4d4a10d28f10e7151b8"

REDINK_URL = "https://github.com/HisMax/RedInk.git"
REDINK_COMMIT = "4d48722344594cf00e0498f0e1ed3df9cd4fd6be"
REDINK_INCLUDE = (
    "backend/**/*.py",
    "backend/*.py",
    "tests/**/*.py",
    "tests/*.py",
    "pyproject.toml",
)
REDINK_SELECTED_COUNT = 28
REDINK_INVENTORY_SHA256 = (
    "0da08ce10d82b76b7020f083da194fa14b3663c19dac24d4adad9e324b3eed74"
)
REDINK_CONTENT_SHA256 = (
    "53644c921010b3c32b9b82a45c4ab4e70bd993af5dab07b4de2fa90945b6d632"
)

DAILY_URL = "https://github.com/ZhuLinsen/daily_stock_analysis.git"
DAILY_COMMIT = "487e49e565ffd1b96a7cf4d855f99cee3c981eaa"
DAILY_INCLUDE = (
    "data_provider/**/*.py",
    "data_provider/*.py",
    "src/**/*.py",
    "src/*.py",
    "tests/test_data_fetcher_prefetch_stock_names.py",
)
DAILY_SELECTED_COUNT = 203
DAILY_INVENTORY_SHA256 = (
    "76cca5c6f2ae1ee83c563b11678559a70d8a4adf0356b4410a2f36d3ff7e37ee"
)
DAILY_CONTENT_SHA256 = (
    "0b77bceb5225e7ff75a9ee2b1e0db04b70ecd0bd5aaef5c1b861b143f54423bb"
)

FORBIDDEN_SELECTION_SUFFIXES = (".env", ".log", ".db", ".sqlite")
FORBIDDEN_SELECTION_DIRS = (".git", ".context-search", "__pycache__")


def select_protected_inventory(root: Path, patterns: tuple[str, ...]) -> list[str]:
    selected: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        segments = relative.split("/")
        if any(segment in FORBIDDEN_SELECTION_DIRS for segment in segments):
            continue
        if relative.endswith(FORBIDDEN_SELECTION_SUFFIXES):
            continue
        if any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
            selected.append(relative)
    return selected


def inventory_sha256(files: list[str]) -> str:
    return hashlib.sha256("\n".join(files).encode("utf-8")).hexdigest()


def content_sha256(root: Path, files: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
    return digest.hexdigest()


def validate_protected_source(
    root: Path,
    *,
    patterns: tuple[str, ...],
    expected_count: int,
    expected_inventory_sha256: str,
    expected_content_sha256: str,
) -> list[str]:
    files = select_protected_inventory(root, patterns)
    if len(files) != expected_count:
        raise ValueError(
            f"selected inventory count {len(files)} != {expected_count}"
        )
    if inventory_sha256(files) != expected_inventory_sha256:
        raise ValueError("selected inventory hash mismatch")
    if content_sha256(root, files) != expected_content_sha256:
        raise ValueError("selected content hash mismatch")
    return files
