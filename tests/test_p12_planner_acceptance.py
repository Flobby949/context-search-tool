from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p12_planner_acceptance as runner


def _capture(hits_by_case: dict[str, int], mean_latency: float = 1.0) -> dict:
    cases = {}
    for index, (cid, hit) in enumerate(sorted(hits_by_case.items())):
        project = ("backend-template", "Investment-Assistant", "git-course")[
            index % 3
        ]
        cases[cid] = {
            "project": project,
            "hit": hit,
            "of": 3,
            "passes": [
                {
                    "required_ranks": {"a.py": 1 if hit else None},
                    "selected": ["a.py"],
                    "planner_status": "ok",
                    "kept_hints": 2,
                    "discarded_hints": 1,
                    "surviving": {
                        "grep_keywords": ["alpha"],
                        "symbol_hints": [],
                        "rewritten_queries": [],
                    },
                    "latency_seconds": mean_latency,
                }
            ]
            * 2,
        }
    return {
        "schema_version": 1,
        "implementation": {"base_commit": "c" * 40, "dirty": False},
        "planner_on": True,
        "embedding_identity": {"provider": "bge"},
        "planner_identity": {"model": "qwen3.5:4b-mlx"},
        "cases": cases,
        "timing": {"mean_latency_seconds": mean_latency},
    }


def _cases(n: int, hits: int) -> dict[str, int]:
    return {f"q-{i:02d}": (1 if i < hits else 0) for i in range(n)}


def test_gate_polarities() -> None:
    reference = _capture(_cases(21, 10))
    baseline = _capture(_cases(21, 12))
    good = _capture(_cases(21, 18))

    report = runner.compare(baseline, good, reference)
    assert report["disposition"] == "ship"
    assert all(report["gates"].values()), report["gates"]

    small_gain = runner.compare(baseline, _capture(_cases(21, 16)), reference)
    assert small_gain["gates"]["g1_gain_at_least_5"] is False

    zeroed = _capture(_cases(21, 18))
    zeroed["cases"]["q-00"]["hit"] = 0
    assert runner.compare(baseline, zeroed, reference)["gates"][
        "g3_no_query_zeroed"
    ] is False

    slow = _capture(_cases(21, 18), mean_latency=2.0)
    assert runner.compare(baseline, slow, reference)["gates"][
        "g4_latency_bounded"
    ] is False

    weak_reference = _capture(_cases(21, 17))
    assert runner.compare(baseline, good, weak_reference)["gates"][
        "g6_beats_planner_off"
    ] is False


def test_g2_catches_project_regression() -> None:
    reference = _capture(_cases(21, 5))
    baseline = _capture(_cases(21, 12))
    candidate = _capture(_cases(21, 18))
    victim = next(
        cid
        for cid, case in baseline["cases"].items()
        if case["hit"] and candidate["cases"][cid]["project"] == case["project"]
    )
    candidate["cases"][victim]["hit"] = 0
    # give the gain elsewhere so g1 still passes
    report = runner.compare(baseline, candidate, reference)
    assert report["gates"]["g3_no_query_zeroed"] is False


def test_check_rejects_leaks_and_wrong_schema(tmp_path: Path) -> None:
    payload = _capture(_cases(21, 12))
    good = tmp_path / "good.json"
    good.write_text(runner._canonical(payload), encoding="utf-8")
    runner.check(good)

    stale = copy.deepcopy(payload)
    stale["schema_version"] = 0
    bad = tmp_path / "stale.json"
    bad.write_text(runner._canonical(stale), encoding="utf-8")
    with pytest.raises(ValueError, match="capture schema"):
        runner.check(bad)

    leaked = copy.deepcopy(payload)
    first = next(iter(leaked["cases"].values()))
    leaked_pass = dict(first["passes"][0])
    leaked_pass["selected"] = ["/Users/someone/private.py"]
    first["passes"] = [leaked_pass, leaked_pass]
    bad2 = tmp_path / "leak.json"
    bad2.write_text(runner._canonical(leaked), encoding="utf-8")
    with pytest.raises(ValueError, match="absolute path"):
        runner.check(bad2)

    contentful = copy.deepcopy(payload)
    first = next(iter(contentful["cases"].values()))
    withbody = dict(first["passes"][0])
    withbody["content"] = "def secret(): ..."
    first["passes"] = [withbody, withbody]
    bad3 = tmp_path / "content.json"
    bad3.write_text(runner._canonical(contentful), encoding="utf-8")
    with pytest.raises(ValueError, match="source content"):
        runner.check(bad3)


def test_sources_validation_detects_drift(tmp_path: Path) -> None:
    gold = {
        "projects": {
            "demo": {
                "aggregate_sha256": "0" * 64,
                "file_count": 1,
                "queries": [],
            }
        }
    }
    root = tmp_path / "sources"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"demo": {"aggregate_sha256": "0" * 64}}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="drift"):
        runner._validate_sources(root, gold)

    with pytest.raises(RuntimeError, match="BLOCKED"):
        runner._validate_sources(
            root,
            {
                "projects": {
                    "missing": {
                        "aggregate_sha256": "0" * 64,
                        "file_count": 0,
                        "queries": [],
                    }
                }
            },
        )


def test_fixture_matches_the_durable_manifest() -> None:
    fixture = json.loads(
        (
            Path(__file__).resolve().parent
            / "fixtures/p12_planner/gold.json"
        ).read_text(encoding="utf-8")
    )
    manifest_path = (
        Path(__file__).resolve().parent.parent
        / ".quality/p12-eval-sources/manifest.json"
    )
    if not manifest_path.exists():
        pytest.skip("durable eval sources not present in this checkout")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, proj in fixture["projects"].items():
        assert proj["aggregate_sha256"] == manifest[name]["aggregate_sha256"]
        assert proj["file_count"] == manifest[name]["file_count"]
    total = sum(
        len(case["required"])
        for proj in fixture["projects"].values()
        for case in proj["queries"]
    )
    assert total == 53
    assert (
        sum(len(proj["queries"]) for proj in fixture["projects"].values())
        == 21
    )
