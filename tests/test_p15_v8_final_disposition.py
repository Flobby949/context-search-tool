from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISPOSITION_PATH = (
    ROOT
    / "tests/fixtures/p15_v8_closure/attempt-003-final-disposition.json"
)


def _load() -> tuple[bytes, dict[str, object]]:
    raw = DISPOSITION_PATH.read_bytes()
    return raw, json.loads(raw)


def test_attempt_003_final_disposition_is_canonical_and_terminal() -> None:
    raw, disposition = _load()

    assert raw == (
        json.dumps(
            disposition,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    assert disposition["schema_version"] == (
        "p15-v8-task7-final-disposition-v1"
    )
    assert disposition["attempt_id"] == "p15-v8-attempt-003"
    assert disposition["outcome"] == "FAIL"
    assert disposition["final_disposition"] == "reject"


def test_attempt_003_records_a_complete_fresh_matrix_and_stop_rule() -> None:
    _, disposition = _load()
    fresh = disposition["fresh"]

    assert fresh["matrix_complete"] is True
    assert fresh["observed"] == {
        "cases": 12,
        "fallback_plans": 0,
        "local_arm_replays": 96,
        "planner_samples": 24,
        "repositories": 2,
        "valid_plans": 24,
    }
    assert fresh["stable_causal_new_targets"] == 0
    assert fresh["rank1_changes"] == 0
    assert fresh["required_losses"] == 0
    assert fresh["treatment_only_irrelevant"] == 4
    assert disposition["held_out"] == {
        "opened": False,
        "reason": "fresh_outcome_failed",
        "status": "NOT_EVALUATED",
    }
    assert disposition["release"]["status"] == "NOT_EVALUATED"
    assert disposition["governance"]["status"] == "NOT_EVALUATED"


def test_attempt_003_binds_ignored_evidence_by_relative_path_and_sha256() -> None:
    _, disposition = _load()

    for evidence in disposition["evidence"].values():
        assert evidence["path"].startswith(".quality/p15-v8-attempt-003/")
        assert len(evidence["sha256"]) == 64
        assert set(evidence["sha256"]) <= set("0123456789abcdef")
    assert disposition["provider"] == {
        "authentication_failure": False,
        "status": "complete",
    }
    assert disposition["comparator"] == {
        "expected_reports": 12,
        "incomplete_reports": 0,
        "policy": "report_only",
        "success_reports": 12,
    }
