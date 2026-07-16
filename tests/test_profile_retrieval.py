from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

import pytest

from scripts import profile_retrieval


def _configured_targets() -> list[tuple[str, ModuleType, str]]:
    targets: list[tuple[str, ModuleType, str]] = []
    for configured in profile_retrieval.RETRIEVAL_FUNCTIONS:
        if isinstance(configured, str):
            targets.append((configured, profile_retrieval.retrieval, configured))
            continue
        display_name, owner, attribute_name = configured
        owner_module = importlib.import_module(owner) if isinstance(owner, str) else owner
        targets.append((display_name, owner_module, attribute_name))
    return targets


@pytest.mark.parametrize(
    ("display_name", "owner_module", "attribute_name"),
    _configured_targets(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_every_profile_target_exists_and_wrapper_is_hit(
    display_name: str,
    owner_module: ModuleType,
    attribute_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert hasattr(owner_module, attribute_name)
    calls = 0

    def probe(*args: Any, **kwargs: Any) -> str:
        nonlocal calls
        calls += 1
        return display_name

    monkeypatch.setattr(owner_module, attribute_name, probe)
    timings: dict[str, profile_retrieval.Timing] = {}
    originals = profile_retrieval._wrap_retrieval_functions(timings)
    try:
        assert getattr(owner_module, attribute_name)() == display_name
    finally:
        profile_retrieval._restore(originals)

    assert calls == 1
    assert timings[display_name].calls == 1
