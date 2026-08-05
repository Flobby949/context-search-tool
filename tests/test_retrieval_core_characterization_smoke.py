from pathlib import Path

from retrieval_core_characterization import (
    FULL_STAGE_LEDGER_KEYS,
    baseline_projection,
)


def test_baseline_projection_records_dependency_promotion_live_output(
    tmp_path: Path,
) -> None:
    actual = baseline_projection(tmp_path)

    assert tuple(actual["full_stage_ledgers"]) == FULL_STAGE_LEDGER_KEYS
    for ledger in actual["full_stage_ledgers"].values():
        stages = {stage["name"]: stage for stage in ledger["stages"]}
        assert "dependency_promotion" in stages
        assert isinstance(stages["dependency_promotion"]["live_output"], list)
