from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "p6_benchmark.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("p6_entry_publish", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _case(*, extra: str | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "attempted": True,
        "case_id": "case",
        "expanded_tokens": [],
        "failures": [],
        "gate": {},
        "known_gap_reason": None,
        "metrics": {},
        "planner": {},
        "query": {},
        "query_variants": [],
        "repo_key": "repo",
        "status": "pass",
        "tags": [],
        "top_results": [],
        "variant_retrieval_status": {},
    }
    if extra:
        value[extra] = {} if extra == "context_pack" else False
    return value


def _quality(profile: str, count: int, *, case_extra: str | None = None) -> dict:
    cases = []
    for index in range(count):
        case = _case(extra=case_extra)
        case["case_id"] = f"case-{index}"
        cases.append(case)
    return {
        "schema_version": 2,
        "generated_at": "frozen",
        "tool": {},
        "fixture": {},
        "profile": profile,
        "command_args": [],
        "config": {},
        "planner": {},
        "repos": [],
        "cases": cases,
        "aggregate": {
            "total": count,
            "selected": count,
            "attempted": count,
            "executed": count,
            "passed": count,
            "failed": 0,
            "skipped": 0,
            "known_gaps": 0,
            "informational": 0,
            "errors": 0,
            "metrics": {},
        },
    }


def _pinned_case(index: int) -> dict:
    return {
        "budgets": {},
        "case_id": f"case-{index}",
        "failures": [],
        "final_context_pack_paths": [],
        "final_context_pack_sha256": "sha256:" + "1" * 64,
        "initial_context_pack_paths": [],
        "initial_context_pack_sha256": "sha256:" + "2" * 64,
        "initial_result_paths": [],
        "non_timing_metrics": {},
        "query": {},
        "repo_key": "repo",
        "source": {},
        "status": "pass",
        "trace": {},
    }


def _write_junit(path: Path, skip_ids: list[str]) -> None:
    suite = ET.Element("testsuite")
    for index in range(2625):
        ET.SubElement(
            suite,
            "testcase",
            classname="tests.test_passing",
            name=f"test_{index}",
        )
    for node_id in skip_ids:
        classname, name = node_id.rsplit("::", 1)
        case = ET.SubElement(suite, "testcase", classname=classname, name=name)
        ET.SubElement(case, "skipped", message="frozen skip")
    path.write_bytes(ET.tostring(suite, encoding="utf-8"))


def _write_manifest(directory: Path, names: set[str]) -> None:
    lines = [
        f"{hashlib.sha256((directory / name).read_bytes()).hexdigest()}  {name}"
        for name in sorted(names)
    ]
    (directory / "entry-evidence-hashes.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _evidence_bundle(tmp_path: Path):
    module = _load_harness()
    _write_junit(tmp_path / "entry-full.xml", list(module.FROZEN_ENTRY_SKIP_NODE_IDS))
    quality = {
        "entry-p5.json": _quality("p5_language_graphs", 12),
        "entry-p4.json": _quality("p4_exploration", 4, case_extra="context_pack"),
        "entry-p2.json": _quality("p2_context_pack", 5, case_extra="context_pack"),
        "entry-ci.json": _quality("ci", 8),
    }
    for name, value in quality.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    pinned = {
        "schema_version": 1,
        "fixture_sha256": "sha256:" + "3" * 64,
        "input_manifest_sha256": "sha256:" + "4" * 64,
        "profile_definition_sha256": "sha256:" + "5" * 64,
        "effective_config_hash": "sha256:" + "6" * 64,
        "profile": "p5_real_language_graphs",
        "cases": [_pinned_case(0), _pinned_case(1)],
        "aggregate": {
            "selected": 2,
            "executed": 2,
            "passed": 2,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
        },
    }
    pinned_text = json.dumps(pinned, sort_keys=True)
    (tmp_path / "entry-real-a.json").write_text(pinned_text, encoding="utf-8")
    (tmp_path / "entry-real-b.json").write_text(pinned_text, encoding="utf-8")
    (tmp_path / "entry-runtime.json").write_text(
        json.dumps(
            {
                "python": "3.13.1",
                "sqlite": "3.51.0",
                "platform": "test-platform",
                "machine": "test-machine",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "entry-dependencies.txt").write_text(
        "Demo_Pkg @ git+https://token@example.invalid/repo.git\njsonschema==0\n",
        encoding="utf-8",
    )
    _write_manifest(tmp_path, set(module.ENTRY_RAW_EVIDENCE_NAMES))
    inputs = {
        name: tmp_path / name
        for name in module.ENTRY_RAW_EVIDENCE_NAMES | {"entry-evidence-hashes.txt"}
    }
    return module, inputs


def test_entry_evidence_binds_bytes_and_redacts_direct_urls(tmp_path: Path) -> None:
    module, inputs = _evidence_bundle(tmp_path)
    result = module.validate_entry_evidence(
        inputs,
        installed_versions={"demo-pkg": "1.2.3", "jsonschema": "4.26.0"},
    )

    assert result["dependency_projection"]["packages"] == [
        "demo-pkg==1.2.3",
        "jsonschema==4.26.0",
    ]
    serialized = module.canonical_json(result["dependency_projection"])
    assert "https://" not in serialized
    assert "token@" not in serialized
    assert result["dependency_sha256"] == hashlib.sha256(serialized.encode()).hexdigest()


@pytest.mark.parametrize("mutation", ["digest", "missing", "extra"])
def test_entry_evidence_manifest_fails_closed(tmp_path: Path, mutation: str) -> None:
    module, inputs = _evidence_bundle(tmp_path)
    manifest = inputs["entry-evidence-hashes.txt"]
    lines = manifest.read_text(encoding="utf-8").splitlines()
    if mutation == "digest":
        lines[0] = "0" * 64 + lines[0][64:]
    elif mutation == "missing":
        lines.pop()
    else:
        lines.append("0" * 64 + "  unexpected.json")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest|digest|allowlist"):
        module.validate_entry_evidence(
            inputs,
            installed_versions={"demo-pkg": "1.2.3", "jsonschema": "4.26.0"},
        )


def test_entry_evidence_rejects_skip_node_drift(tmp_path: Path) -> None:
    module, inputs = _evidence_bundle(tmp_path)
    skips = list(module.FROZEN_ENTRY_SKIP_NODE_IDS)
    skips[-1] = "tests/test_quality_planner.py::test_drifted_skip"
    _write_junit(inputs["entry-full.xml"], skips)
    _write_manifest(tmp_path, set(module.ENTRY_RAW_EVIDENCE_NAMES))

    with pytest.raises(ValueError, match="JUnit"):
        module.validate_entry_evidence(
            inputs,
            installed_versions={"demo-pkg": "1.2.3", "jsonschema": "4.26.0"},
        )


def _decision(module) -> dict:
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    tree = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD:src/context_search_tool"],
        text=True,
    ).strip()
    return module.make_decision(
        "exact_ann",
        implementation_commit=commit,
        production_tree=tree,
        evidence_report_sha256="7" * 64,
        trigger_crossed=False,
        reason_codes=["semantic_within_budget", "rss_within_budget"],
    )


def test_publish_is_root_bounded_no_overwrite_and_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_harness()
    source = tmp_path / "source.json"
    decision = _decision(module)
    source.write_text(json.dumps(decision), encoding="utf-8")
    publication_root = tmp_path / "docs" / "benchmarks" / "p6"
    destination = publication_root / "accepted" / "decision.json"
    real_link = os.link
    link_paths: list[tuple[Path, Path]] = []

    def recording_link(source_path, destination_path):
        link_paths.append((Path(source_path), Path(destination_path)))
        real_link(source_path, destination_path)

    monkeypatch.setattr(module.os, "link", recording_link)
    module.publish_report(
        source, destination, publication_root=publication_root
    )

    assert destination.read_text(encoding="utf-8") == module.canonical_json(decision)
    assert link_paths[0][0].parent == destination.parent
    assert list(destination.parent.glob(".decision.json.*.tmp")) == []
    with pytest.raises(FileExistsError):
        module.publish_report(source, destination, publication_root=publication_root)
    with pytest.raises(ValueError, match="outside"):
        module.publish_report(
            source,
            tmp_path / "outside.json",
            publication_root=publication_root,
        )


def test_publish_rejects_broken_symlink_destination(tmp_path: Path) -> None:
    module = _load_harness()
    source = tmp_path / "source.json"
    source.write_text(json.dumps(_decision(module)), encoding="utf-8")
    publication_root = tmp_path / "publication"
    publication_root.mkdir()
    missing_target = tmp_path / "missing-target.json"
    destination = publication_root / "decision.json"
    destination.symlink_to(missing_target)

    with pytest.raises(FileExistsError):
        module.publish_report(source, destination, publication_root=publication_root)
    assert not missing_target.exists()
