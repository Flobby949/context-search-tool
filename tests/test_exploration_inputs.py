from __future__ import annotations

import json
from typing import Any

from p4_exploration_identity import (
    CI_PROJECTION_PATH,
    EXPECTED_CASES,
    P2_PROJECTION_PATH,
    P4_MANIFEST_PATH,
    assert_protected_inputs,
    load_input_manifest,
    load_raw_p4_catalog,
)


def test_protected_p0_p3_inputs_are_exact_and_clean() -> None:
    assert_protected_inputs()


def test_p4_catalog_has_exact_closed_inventory() -> None:
    catalog = load_raw_p4_catalog()
    counts = {profile: 0 for profile in EXPECTED_CASES}
    for repo in catalog["repos"]:
        for case in repo["queries"]:
            counts[case["profiles"][0]] += 1
    assert counts == {"p4_exploration": 4, "p4_real_exploration": 1}


def test_p4_input_manifest_matches_every_frozen_input() -> None:
    manifest = load_input_manifest()
    assert len(manifest["assays"]) == 4
    assert all(assay["expected_required_goal_classes"] for assay in manifest["assays"])


def test_p0_p3_quality_projections_are_committed_json() -> None:
    manifest = json.loads(P4_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert json.loads(P2_PROJECTION_PATH.read_text(encoding="utf-8"))["profile"] == (
        "p2_context_pack"
    )
    assert json.loads(CI_PROJECTION_PATH.read_text(encoding="utf-8"))["profile"] == "ci"
    assert len(manifest["quality_projections"]) == 2


def test_frozen_outputs_contain_no_timing_or_absolute_workspace_values() -> None:
    payloads = (
        json.loads(P4_MANIFEST_PATH.read_text(encoding="utf-8")),
        json.loads(P2_PROJECTION_PATH.read_text(encoding="utf-8")),
        json.loads(CI_PROJECTION_PATH.read_text(encoding="utf-8")),
    )

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            assert "generated_at" not in value
            assert "latency_ms" not in value
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str):
            assert "/Users/flobby/vibe_coding/context-search-tool" not in value

    for payload in payloads:
        visit(payload)
