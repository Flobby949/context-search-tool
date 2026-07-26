from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p8_real_python_graphs_acceptance as runner


def _case(
    case_id: str,
    repo: str,
    required: list[tuple[str, str, int | None]],
    selected: list[tuple[str, bool, bool]],
    contextual: list[str] | None = None,
) -> dict:
    return {
        "repo": repo,
        "required": [
            {
                "path": path,
                "role": role,
                "rank": rank,
                "state": "selected" if rank else "not_selected",
            }
            for path, role, rank in required
        ],
        "selected": [
            {
                "rank": index + 1,
                "path": path,
                "graph_origin": graph_origin,
                "relation_slot": witness,
                "relation_witness": (
                    {"relation_id": f"r5:{path}", "target_path": path}
                    if witness
                    else None
                ),
            }
            for index, (path, graph_origin, witness) in enumerate(selected)
        ],
        "contextual": contextual or [],
        "unique_selected_paths": len({path for path, _, _ in selected}),
    }


def _synthetic_capture(*, improved: bool) -> dict:
    cases: dict[str, dict] = {}
    # Six redink + twelve daily case ids mirror the real manifest shape.
    redink_ids = [f"redink-case-{i}" for i in range(6)]
    daily_ids = [f"daily-case-{i}" for i in range(12)]
    for index, case_id in enumerate(redink_ids):
        path = f"backend/mod{index}.py"
        support = f"backend/rel{index}.py"
        if improved and index < 2:
            required = [(path, "entrypoint", 1), (support, "support", 2)]
            selected = [(path, False, False), (support, True, True)]
        else:
            required = [(path, "entrypoint", 1), (support, "support", None)]
            selected = [(path, False, False)]
        cases[case_id] = _case(case_id, "redink", required, selected)
    for index, case_id in enumerate(daily_ids):
        path = f"src/mod{index}.py"
        extra = f"src/extra{index}.py"
        if improved and index < 4:
            required = [(path, "implementation", 1), (extra, "support", 2)]
            selected = [(path, False, False), (extra, True, True)]
        else:
            required = [(path, "implementation", 1), (extra, "support", None)]
            selected = [(path, False, False)]
        cases[case_id] = _case(case_id, "daily", required, selected)
    continuity = "daily-prefetch-continuity"
    cases[continuity] = _case(
        continuity,
        "daily",
        [
            ("src/core/pipeline.py", "implementation", 1),
            ("data_provider/base.py", "implementation", 2),
        ],
        [("src/core/pipeline.py", False, False), ("data_provider/base.py", False, False)]
        + [(f"data_provider/f{i}.py", False, False) for i in range(10)],
        contextual=[f"data_provider/f{i}.py" for i in range(10)],
    )
    return {
        "schema_version": 2,
        "manifest_sha256": "m" * 64,
        "implementation": {"base_commit": "c" * 40, "dirty": False},
        "repositories": {},
        "cases": cases,
        "witnesses": {},
        "timing": {"query_latency_mean_seconds": 0.01},
    }


def test_compare_rejects_gold_change_between_captures() -> None:
    baseline = _synthetic_capture(improved=False)
    candidate = _synthetic_capture(improved=True)
    candidate["manifest_sha256"] = "x" * 64

    with pytest.raises(ValueError, match="gold manifest changed"):
        runner.compare(baseline, candidate)


def test_compare_ships_when_all_gates_pass() -> None:
    baseline = _synthetic_capture(improved=False)
    candidate = _synthetic_capture(improved=True)

    report = runner.compare(baseline, candidate)

    assert report["disposition"] == "ship"
    assert all(report["gates"].values()), report["gates"]
    assert report["combined_recall"]["delta"] > 0
    assert len(report["credited_cases"]) >= 4


def test_gate_negatives_flip_the_disposition() -> None:
    baseline = _synthetic_capture(improved=False)

    # Gate 3: a required path falls out of the top 12.
    dropped = _synthetic_capture(improved=True)
    dropped["cases"]["daily-case-8"]["required"][0]["rank"] = None
    report = runner.compare(baseline, dropped)
    assert report["gates"]["gate3_no_required_falls_out"] is False
    assert report["disposition"] == "reject"

    # Gate 2/4/5: no credited graph-origin gains.
    uncredited = _synthetic_capture(improved=True)
    for case in uncredited["cases"].values():
        for entry in case["selected"]:
            entry["graph_origin"] = False
            entry["relation_witness"] = None
    report = runner.compare(baseline, uncredited)
    assert report["gates"]["gate2_credited_gain_at_least_5pct"] is False
    assert report["gates"]["gate4_four_credited_case_improvements"] is False
    assert report["disposition"] == "ranking_followup"

    # Gate 8: noise explosion.
    noisy = _synthetic_capture(improved=True)
    for case in noisy["cases"].values():
        case["selected"] = case["selected"] + [
            {
                "rank": len(case["selected"]) + 1 + offset,
                "path": f"noise/extra{offset}.py",
                "graph_origin": False,
                "relation_witness": None,
            }
            for offset in range(2)
        ]
    report = runner.compare(baseline, noisy)
    assert report["gates"]["gate8_noise_bounded"] is False

    # Gate 9: continuity loses a required path.
    broken_continuity = _synthetic_capture(improved=True)
    continuity = broken_continuity["cases"]["daily-prefetch-continuity"]
    continuity["selected"] = [
        entry
        for entry in continuity["selected"]
        if entry["path"] != "data_provider/base.py"
    ]
    continuity["unique_selected_paths"] = len(continuity["selected"])
    report = runner.compare(baseline, broken_continuity)
    assert report["gates"]["gate9_p7_continuity"] is False

    # Gate 7: a claimed witness that does not match its selected path.
    bad_witness = _synthetic_capture(improved=True)
    for case in bad_witness["cases"].values():
        for entry in case["selected"]:
            if entry["relation_witness"]:
                entry["relation_witness"]["target_path"] = "other/path.py"
    report = runner.compare(baseline, bad_witness)
    assert report["gates"]["gate7_witnesses_are_persisted"] is False


def test_check_rejects_absolute_paths_and_source_content(tmp_path: Path) -> None:
    payload = _synthetic_capture(improved=False)
    good = tmp_path / "good.json"
    good.write_text(runner._canonical(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="18 gold cases"):
        runner.check(good)  # synthetic capture has 19 cases

    real_shaped = copy.deepcopy(payload)
    del real_shaped["cases"]["daily-case-11"]
    ok = tmp_path / "ok.json"
    ok.write_text(runner._canonical(real_shaped), encoding="utf-8")
    runner.check(ok)

    leaked = copy.deepcopy(real_shaped)
    first = next(iter(leaked["cases"].values()))
    first["selected"][0]["path"] = "/Users/someone/private/file.py"
    bad = tmp_path / "bad.json"
    bad.write_text(runner._canonical(leaked), encoding="utf-8")
    with pytest.raises(ValueError, match="absolute path"):
        runner.check(bad)

    contentful = copy.deepcopy(real_shaped)
    first = next(iter(contentful["cases"].values()))
    first["selected"][0]["content"] = "def secret(): ..."
    bad2 = tmp_path / "bad2.json"
    bad2.write_text(runner._canonical(contentful), encoding="utf-8")
    with pytest.raises(ValueError, match="source content"):
        runner.check(bad2)

    stale = tmp_path / "stale.json"
    stale.write_text(
        json.dumps(real_shaped, sort_keys=False) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="canonically rendered"):
        runner.check(stale)


def test_implementation_identity_tracks_dirty_state(tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "impl"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(("git", "init", "-q", str(repo)), check=True)
    subprocess.run(
        ("git", "-C", str(repo), "add", "-A"), check=True
    )
    subprocess.run(
        (
            "git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-qm", "init",
        ),
        check=True,
    )

    clean = runner.implementation_identity(repo)
    assert clean["dirty"] is False

    (repo / "src" / "mod.py").write_text("VALUE = 2\n", encoding="utf-8")
    tracked_dirty = runner.implementation_identity(repo)
    assert tracked_dirty["dirty"] is True
    assert tracked_dirty["tracked_diff_sha256"] != clean["tracked_diff_sha256"]

    (repo / "tests" / "new_test.py").write_text("X = 1\n", encoding="utf-8")
    untracked_dirty = runner.implementation_identity(repo)
    assert untracked_dirty["untracked_files"] == {
        "tests/new_test.py": untracked_dirty["untracked_files"]["tests/new_test.py"]
    }
    assert untracked_dirty != tracked_dirty


def test_check_rejects_v1_captures(tmp_path: Path) -> None:
    payload = _synthetic_capture(improved=False)
    del payload["cases"]["daily-case-11"]
    payload["schema_version"] = 1
    stale = tmp_path / "v1.json"
    stale.write_text(runner._canonical(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="capture schema"):
        runner.check(stale)


def test_credit_requires_relation_slot_and_witness() -> None:
    baseline = _synthetic_capture(improved=False)

    credited = _synthetic_capture(improved=True)
    for case in credited["cases"].values():
        for entry in case["selected"]:
            if entry["graph_origin"]:
                entry["relation_slot"] = True
    report = runner.compare(baseline, credited)
    assert report["gates"]["gate2_credited_gain_at_least_5pct"] is True
    assert len(report["credited_cases"]) >= 4

    # Gained through drift (no relation_slot): reported, never credited.
    drift = _synthetic_capture(improved=True)
    for case in drift["cases"].values():
        for entry in case["selected"]:
            entry["relation_slot"] = False
    report = runner.compare(baseline, drift)
    assert report["newly_satisfied"]
    assert all(not row["credited"] for row in report["newly_satisfied"])
    assert report["gates"]["gate2_credited_gain_at_least_5pct"] is False

    # relation_slot without a persisted witness: uncredited.
    unwitnessed = _synthetic_capture(improved=True)
    for case in unwitnessed["cases"].values():
        for entry in case["selected"]:
            if entry["graph_origin"]:
                entry["relation_slot"] = True
                entry["relation_witness"] = None
    report = runner.compare(baseline, unwitnessed)
    assert all(not row["credited"] for row in report["newly_satisfied"])
