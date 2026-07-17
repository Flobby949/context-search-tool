from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from generate_p5_graph_manifest import generate
from p5_graph_identity import (
    EXPECTED_CASE_NEGATIVES,
    EXPECTED_CASE_POSITIVES,
    EXPECTED_DETERMINISTIC_CASES,
    EXPECTED_REAL_CASES,
    GRAPH_ONLY_NEGATIVE_PATHS,
    P5_MANIFEST_PATH,
    P5_REPOSITORIES,
    P5_SOURCE_INVENTORY,
    PRE_P5_NO_EDGE_PATH,
    ROOT,
    assert_protected_inputs,
    canonical_json_bytes,
    load_input_manifest,
    load_raw_p5_catalog,
    load_raw_p5_real_catalog,
    source_inventory,
)


def _case_map(catalog: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        case["id"]: (repo["repo_key"], case)
        for repo in catalog["repos"]
        for case in repo["queries"]
    }


def _top_k_paths(case: dict[str, Any], field: str) -> tuple[str, ...]:
    return tuple(item["path"] for item in case.get(field, ()))


def _declared_positive_paths(case: dict[str, Any]) -> tuple[str, ...]:
    paths = list(_top_k_paths(case, "expected_top_k"))
    for values in case.get("expected_context_groups", {}).values():
        paths.extend(item["path"] for item in values)
    paths.extend(case.get("final_present", ()))
    paths.extend(case.get("final_at_least", {}).get("matchers", ()))
    return tuple(dict.fromkeys(paths))


def _visit(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in {"generated_at", "latency_ms", "workspace"}
            _visit(item)
    elif isinstance(value, list):
        for item in value:
            _visit(item)
    elif isinstance(value, str):
        assert str(ROOT) not in value


def test_p5_raw_catalogs_have_exact_closed_inventory() -> None:
    deterministic = load_raw_p5_catalog()
    real = load_raw_p5_real_catalog()

    assert sum(len(repo["queries"]) for repo in deterministic["repos"]) == 12
    assert sum(len(repo["queries"]) for repo in real["repos"]) == 2
    assert [
        (repo["repo_key"], case["id"], case["query"], case.get("mode", "results"))
        for repo in deterministic["repos"]
        for case in repo["queries"]
    ] == list(EXPECTED_DETERMINISTIC_CASES)
    assert [
        (repo["repo_key"], case["id"], case["query"], case.get("mode", "results"))
        for repo in real["repos"]
        for case in repo["queries"]
    ] == list(EXPECTED_REAL_CASES)


def test_p5_fixture_inventory_and_declared_proofs_are_exact() -> None:
    assert source_inventory() == P5_SOURCE_INVENTORY
    catalog = load_raw_p5_catalog()
    cases = _case_map(catalog)

    for case_id, expected in EXPECTED_CASE_POSITIVES.items():
        repo_key, case = cases[case_id]
        assert _declared_positive_paths(case) == expected
        root = ROOT / P5_REPOSITORIES[repo_key]
        assert all((root / path).is_file() for path in expected)

    for case_id, expected in EXPECTED_CASE_NEGATIVES.items():
        repo_key, case = cases[case_id]
        assert _top_k_paths(case, "absent_top_k") == expected
        root = ROOT / P5_REPOSITORIES[repo_key]
        assert all((root / path).is_file() for path in expected)

    for case_id, paths in GRAPH_ONLY_NEGATIVE_PATHS.items():
        repo_key, case = cases[case_id]
        assert case["notes"].startswith("raw graph assertion:")
        root = ROOT / P5_REPOSITORIES[repo_key]
        assert all((root / path).is_file() for path in paths)

    exploration = cases["vue-route-exploration"][1]
    assert exploration["initial_absent"] == [
        "src/router/index.ts",
        "src/types/order.ts",
    ]
    assert exploration["final_present"] == exploration["initial_absent"]
    assert exploration["maximum_retrieval_call_count"] == 3
    assert exploration["maximum_pack_bytes"] == 65536
    assert exploration["maximum_final_noise_items"] == 0


def test_p5_real_catalog_has_exact_pinned_proofs() -> None:
    catalog = load_raw_p5_real_catalog()
    cases = _case_map(catalog)
    petclinic = cases["petclinic-owner-graph"][1]
    assert petclinic["final_present"] == [
        "src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java",
        "src/main/java/org/springframework/samples/petclinic/owner/OwnerRepository.java",
        "src/main/java/org/springframework/samples/petclinic/owner/Owner.java",
        "src/test/java/org/springframework/samples/petclinic/owner/OwnerControllerTests.java",
    ]
    program_tool = cases["program-tool-qrcode-graph"][1]
    assert program_tool["final_present"] == ["src/router/index.ts"]
    assert program_tool["final_at_least"] == {
        "matchers": [
            "src/views/qrcode/QRCodeTool.vue",
            "src/utils/qrcodeUtils.ts",
            "src/types/qrcode-reader.d.ts",
        ],
        "min_matches": 2,
    }
    for case in (petclinic, program_tool):
        assert case["maximum_retrieval_call_count"] == 3
        assert case["maximum_pack_bytes"] == 65536


def test_p5_input_manifest_matches_every_frozen_byte() -> None:
    assert_protected_inputs()
    manifest = load_input_manifest()
    assert len(manifest["inputs"]) == sum(map(len, P5_SOURCE_INVENTORY.values())) + 3
    assert len({item["path"] for item in manifest["inputs"]}) == len(
        manifest["inputs"]
    )
    assert PRE_P5_NO_EDGE_PATH.is_file()


def test_p5_frozen_json_is_canonical_and_environment_free() -> None:
    manifest = json.loads(P5_MANIFEST_PATH.read_text(encoding="utf-8"))
    projection = json.loads(PRE_P5_NO_EDGE_PATH.read_text(encoding="utf-8"))
    assert P5_MANIFEST_PATH.read_bytes() == canonical_json_bytes(manifest)
    assert PRE_P5_NO_EDGE_PATH.read_bytes() == canonical_json_bytes(projection)
    assert projection["case_id"] == "no-legal-edge-compat"
    assert projection["query"] == "StandaloneUniqueToken"
    assert projection["results"][0]["file_path"] == (
        "src/main/java/com/example/standalone/Standalone.java"
    )
    _visit(manifest)
    _visit(projection)


def test_p5_manifest_excludes_post_implementation_outputs() -> None:
    manifest = load_input_manifest()
    input_paths = {item["path"] for item in manifest["inputs"]}
    assert not any("/expected/" in path for path in input_paths)
    assert not any(path.endswith("real_acceptance.json") for path in input_paths)
    assert not any(".context-search" in Path(path).parts for path in input_paths)
    assert not any(".quality" in Path(path).parts for path in input_paths)
    assert not any(Path(path).suffix in {".so", ".dylib", ".o"} for path in input_paths)


def test_p5_manifest_generator_refuses_to_refresh_frozen_outputs() -> None:
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        generate()
