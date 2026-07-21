from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool import scanner


ROOT = Path(__file__).resolve().parents[1]
HEALTH_FIXTURE = ROOT / "tests" / "fixtures" / "p6_contracts" / "index_health_v1.json"


def _health_module() -> Any:
    spec = importlib.util.find_spec("context_search_tool.index_health")
    assert spec is not None, "P6 index-health capability is absent"
    return importlib.import_module("context_search_tool.index_health")


def _fixture() -> dict[str, Any]:
    return json.loads(HEALTH_FIXTURE.read_text(encoding="utf-8"))


def _case(case_id: str) -> dict[str, Any]:
    return next(
        case["report"]
        for case in _fixture()["cases"]
        if case["id"] == case_id
    )


def _tree_snapshot(root: Path) -> dict[str, tuple[str, int, int, str | None]]:
    snapshot: dict[str, tuple[str, int, int, str | None]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        stat = path.lstat()
        if path.is_symlink():
            snapshot[relative] = ("symlink", stat.st_size, stat.st_mtime_ns, None)
        elif path.is_dir():
            snapshot[relative] = ("directory", stat.st_size, stat.st_mtime_ns, None)
        else:
            snapshot[relative] = (
                "file",
                stat.st_size,
                stat.st_mtime_ns,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
    return snapshot


def test_report_model_round_trips_every_frozen_golden_case() -> None:
    module = _health_module()
    fixture = _fixture()

    for case in fixture["cases"]:
        report = module.IndexHealthReport.from_dict(case["report"])
        assert module.serialize_index_health(report) == case["report"]
        assert list(module.serialize_index_health(report)) == fixture[
            "canonical_report_keys"
        ]

    frozen = module.IndexHealthReport.from_dict(_case("healthy_metadata"))
    with pytest.raises(FrozenInstanceError):
        frozen.health = "stale"


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"availability": "missing"}, "missing"),
        ({"availability": "incompatible"}, "incompatible"),
        ({"availability": "corrupt", "integrity": "invalid"}, "corrupt"),
        (
            {
                "availability": "present",
                "integrity": "invalid",
                "writer_active": True,
            },
            "degraded",
        ),
        ({"graph": "stale", "freshness": "stale"}, "stale"),
        ({"graph": "unfinished", "freshness": "unknown"}, "stale"),
        ({"inventory": "incomplete", "freshness": "unknown"}, "stale"),
        ({"freshness": "stale"}, "stale"),
        ({"writer_active": True, "integrity": "unchecked"}, "degraded"),
        ({"generation_stable": False, "integrity": "unchecked"}, "degraded"),
        ({"writer_active": None, "integrity": "unchecked"}, "degraded"),
        ({"coverage": "degraded"}, "degraded"),
        (
            {"freshness": "verified_fresh", "integrity": "valid_verified"},
            "healthy_verified",
        ),
        (
            {"freshness": "metadata_fresh", "integrity": "valid_quick"},
            "healthy_metadata",
        ),
    ],
)
def test_health_derivation_is_total_and_priority_ordered(
    values: dict[str, Any], expected: str
) -> None:
    module = _health_module()
    defaults = {
        "availability": "present",
        "freshness": "metadata_fresh",
        "coverage": "complete",
        "integrity": "valid_quick",
        "inventory": "complete",
        "graph": "ready",
        "writer_active": False,
        "generation_stable": True,
    }
    derivation = module.HealthDerivation(**{**defaults, **values})

    assert module.derive_health(derivation) == expected


def test_serializer_canonicalizes_and_bounds_closed_samples() -> None:
    module = _health_module()
    raw = copy.deepcopy(_case("stale"))
    raw["freshness"].update(
        {
            "changed": 25,
            "samples": [
                {
                    "category": "changed",
                    "path": f"src/z{index:02d}.py",
                    "reason": "source_changed",
                }
                for index in reversed(range(25))
            ],
            "sampled_total": 25,
        }
    )
    raw["refresh"]["reasons"] = [
        "topology_changed",
        "coverage_changed",
        "path_inventory_changed",
        "source_changed",
    ]
    raw["diagnostics"] = [
        {"code": "coverage_pending", "scope": "coverage", "path": "z.py"},
        {"code": "control_file_error", "scope": "inventory", "path": ".gitignore"},
    ]

    rendered = module.serialize_index_health(module.IndexHealthReport.from_dict(raw))

    assert len(rendered["freshness"]["samples"]) == 20
    assert [item["path"] for item in rendered["freshness"]["samples"]] == [
        f"src/z{index:02d}.py" for index in range(20)
    ]
    assert rendered["freshness"]["sampled_total"] == 25
    assert rendered["refresh"]["reasons"] == [
        "source_changed",
        "path_inventory_changed",
        "coverage_changed",
        "topology_changed",
    ]
    assert [item["code"] for item in rendered["diagnostics"]] == [
        "control_file_error",
        "coverage_pending",
    ]


def test_report_model_rejects_non_fail_closed_embedding_evidence() -> None:
    module = _health_module()
    raw = copy.deepcopy(_case("missing"))
    raw["configured_embedding"]["network_egress_capable"] = False

    with pytest.raises(ValueError, match="network egress"):
        module.IndexHealthReport.from_dict(raw)

    raw = copy.deepcopy(_case("healthy_metadata"))
    raw["indexed_embedding"]["provider"] = None
    with pytest.raises(ValueError, match="embedding identity"):
        module.IndexHealthReport.from_dict(raw)


def _compatible_raw(module: Any) -> Any:
    return module.RawIndexCapability(
        status="compatible",
        index_exists=True,
        manifest_version=2,
        operational_version=1,
        graph_version=5,
        error_code=None,
    )


def _snapshot_for_inventory(module: Any, inventory: Any, repo: Path) -> Any:
    indexed: list[Any] = []
    for observation in inventory.eligible:
        result = scanner.read_observed_file(
            repo,
            observation,
            max_file_bytes=DEFAULT_CONFIG.index.max_file_bytes,
        )
        assert result.status == "read"
        indexed.append(
            module.IndexedFileObservation(
                path=observation.path.as_posix(),
                language=observation.language,
                size=observation.size,
                mtime_ns=observation.mtime_ns,
                change_token=observation.change_token,
                change_token_kind=observation.change_token_kind,
                sha256=result.sha256,
            )
        )
    return module.CommittedIndexSnapshot(
        ready_generation="obs-0001",
        manifest_version=2,
        operational_version=1,
        graph_version=5,
        graph_status="ready",
        graph_stale_reason="",
        queryable=True,
        indexed_at_epoch_s=1,
        indexed_files=tuple(indexed),
        coverage_skips=(),
        eligible_chunks=2,
        vector_rows=2,
        vector_generation="vectors-0001",
        vector_dimensions=384,
        manifest_valid=True,
        sqlite_valid=True,
        vector_identity_valid=True,
        indexed_embedding=module.EmbeddingIdentity.hash_v1("sha256:indexed", 384),
    )


def _adapters(
    module: Any,
    inventory: Any,
    snapshot: Any,
    *,
    raw: Any | None = None,
    file_reader: Any | None = None,
    vector_verifier: Any | None = None,
    writer_probe: Any | None = None,
    snapshot_reader: Any | None = None,
    inventory_reader: Any | None = None,
) -> Any:
    ticks = iter((1000, 1010))
    return module.InspectionAdapters(
        raw_probe=lambda _repo: raw or _compatible_raw(module),
        snapshot_reader=snapshot_reader or (lambda _repo: snapshot),
        inventory_reader=inventory_reader
        or (lambda _repo, _config: inventory),
        file_reader=file_reader or scanner.read_observed_file,
        vector_verifier=vector_verifier
        or (lambda _repo, _snapshot: module.VectorVerification.valid()),
        configured_embedding_reader=lambda _repo: module.EmbeddingIdentity.hash_v1(
            "sha256:indexed", 384
        ),
        writer_probe=writer_probe or (lambda _repo: module.WriterProbe.idle()),
        clock_ms=lambda: next(ticks),
    )


def test_missing_preflight_returns_before_all_injected_work(tmp_path: Path) -> None:
    module = _health_module()
    repo = tmp_path / "repo"
    repo.mkdir()

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("schema-first preflight crossed a forbidden adapter")

    ticks = iter((1000, 1010))
    adapters = module.InspectionAdapters(
        raw_probe=lambda _repo: module.RawIndexCapability(
            status="missing",
            index_exists=False,
            manifest_version=None,
            operational_version=None,
            graph_version=None,
            error_code="missing_index",
        ),
        snapshot_reader=forbidden,
        inventory_reader=forbidden,
        file_reader=forbidden,
        vector_verifier=forbidden,
        configured_embedding_reader=forbidden,
        writer_probe=forbidden,
        clock_ms=lambda: next(ticks),
    )

    report = module.inspect_index_health(repo, mode="quick", adapters=adapters)

    assert module.serialize_index_health(report) == _case("missing")


def test_quick_inspector_uses_two_snapshots_and_inventories_without_body_reads(
    tmp_path: Path,
) -> None:
    module = _health_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    inventory = scanner.observe_workspace(repo, DEFAULT_CONFIG)
    snapshot = _snapshot_for_inventory(module, inventory, repo)
    calls = {"snapshot": 0, "inventory": 0}

    def read_snapshot(_repo: Path) -> Any:
        calls["snapshot"] += 1
        return snapshot

    def read_inventory(_repo: Path, _config: Any) -> Any:
        calls["inventory"] += 1
        return inventory

    def forbidden_body(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("quick inspection read an eligible body")

    adapters = _adapters(
        module,
        inventory,
        snapshot,
        file_reader=forbidden_body,
        vector_verifier=forbidden_body,
        snapshot_reader=read_snapshot,
        inventory_reader=read_inventory,
    )

    before = _tree_snapshot(repo)
    report = module.inspect_index_health(repo, mode="quick", adapters=adapters)
    after = _tree_snapshot(repo)
    rendered = module.serialize_index_health(report)

    assert before == after
    assert calls == {"snapshot": 2, "inventory": 2}
    assert rendered["health"] == "healthy_metadata"
    assert rendered["freshness"]["metadata_unchanged"] == 1
    assert rendered["freshness"]["content_verified"] == 0
    assert rendered["integrity"]["status"] == "valid_quick"
    assert rendered["vectors"]["coverage_evidence"] == "count_only"


def test_verified_inspector_streams_each_source_and_vector_tuple_once(
    tmp_path: Path,
) -> None:
    module = _health_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("a = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("b = 2\n", encoding="utf-8")
    inventory = scanner.observe_workspace(repo, DEFAULT_CONFIG)
    snapshot = _snapshot_for_inventory(module, inventory, repo)
    calls = {"body": 0, "vector": 0}

    def read_body(*args: Any, **kwargs: Any) -> Any:
        calls["body"] += 1
        return scanner.read_observed_file(*args, **kwargs)

    def verify_vector(_repo: Path, _snapshot: Any) -> Any:
        calls["vector"] += 1
        return module.VectorVerification.valid()

    adapters = _adapters(
        module,
        inventory,
        snapshot,
        file_reader=read_body,
        vector_verifier=verify_vector,
    )

    before = _tree_snapshot(repo)
    report = module.inspect_index_health(repo, mode="verified", adapters=adapters)
    after = _tree_snapshot(repo)
    rendered = module.serialize_index_health(report)

    assert before == after
    assert calls == {"body": 2, "vector": 1}
    assert rendered["health"] == "healthy_verified"
    assert rendered["freshness"]["content_verified"] == 2
    assert rendered["coverage"]["evidence"] == "verified_workspace"
    assert rendered["integrity"]["status"] == "valid_verified"
    assert rendered["vectors"]["coverage_evidence"] == "exact_ids"
    assert rendered["vectors"]["missing_ids"] == []
    assert rendered["vectors"]["orphan_ids"] == []


def test_inspector_treats_generation_drift_as_interrupted_not_corrupt(
    tmp_path: Path,
) -> None:
    module = _health_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    inventory = scanner.observe_workspace(repo, DEFAULT_CONFIG)
    first = _snapshot_for_inventory(module, inventory, repo)
    second = replace(first, ready_generation="obs-0002", vector_identity_valid=False)
    snapshots = iter((first, second))
    adapters = _adapters(
        module,
        inventory,
        first,
        snapshot_reader=lambda _repo: next(snapshots),
        writer_probe=lambda _repo: module.WriterProbe.unknown("generation_drift"),
    )

    rendered = module.serialize_index_health(
        module.inspect_index_health(repo, mode="quick", adapters=adapters)
    )

    assert rendered["health"] == "degraded"
    assert rendered["availability"] == "present"
    assert rendered["integrity"]["status"] == "unchecked"
    assert rendered["refresh"]["recommended_action"] == "retry_inspection"
    assert rendered["writer"] == {
        "active": None,
        "state": "unknown",
        "evidence": "generation_drift",
    }
    assert {item["code"] for item in rendered["diagnostics"]} == {
        "inspection_interrupted"
    }


def test_incomplete_inventory_is_stale_and_never_infers_deletions(
    tmp_path: Path,
) -> None:
    module = _health_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    complete = scanner.observe_workspace(repo, DEFAULT_CONFIG)
    snapshot = _snapshot_for_inventory(module, complete, repo)
    incomplete = replace(
        complete,
        eligible=(),
        complete=False,
        unscannable_subtrees=("blocked",),
        diagnostics=(
            scanner.InventoryDiagnostic(
                code="unscannable_subtree", scope="inventory", path="blocked"
            ),
        ),
    )
    adapters = _adapters(module, incomplete, snapshot)

    rendered = module.serialize_index_health(
        module.inspect_index_health(repo, mode="quick", adapters=adapters)
    )

    assert rendered["health"] == "stale"
    assert rendered["freshness"]["status"] == "unknown"
    assert rendered["freshness"]["deleted"] == 0
    assert rendered["refresh"]["reasons"] == ["inventory_incomplete"]
    assert rendered["refresh"]["recommended_action"] == "retry_inspection"
    assert rendered["observation"]["unscannable_subtree_count"] == 1
