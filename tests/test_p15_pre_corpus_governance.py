from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from p15_pre_corpus_governance import (
    GovernanceValidationError,
    canonical_sha256,
    contract_projection_sha256,
    validate_future_allowlist_binding,
    validate_pre_corpus_contract,
    validate_selected_identity_schedule,
    validate_supersession_audit,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests/fixtures/p15_v7_minimal_online_causal"
CONTRACT_PATH = FIXTURE_ROOT / "audit/p15-v7-attempt-002-contract.json"
AUDIT_PATH = (
    FIXTURE_ROOT / "audit/p15-v7-attempt-001-supersession.json"
)


def _identity(owner: str, repository: str, revision: str) -> dict[str, object]:
    projection = {
        "provider": "github",
        "owner": owner,
        "repository": repository,
        "immutable_revision": revision,
    }
    return {
        "ordinal": 0,
        **projection,
        "identity_sha256": canonical_sha256(projection),
    }


def _contract(*, excluded_identity_keys: list[str] | None = None) -> dict[str, object]:
    excluded_identity_keys = excluded_identity_keys or []
    excluded_identity_sha256 = []
    for identity in excluded_identity_keys:
        owner_repository, revision = identity.rsplit("@", 1)
        owner, repository = owner_repository.split("/", 1)
        excluded_identity_sha256.append(
            canonical_sha256(
                {
                    "provider": "github",
                    "owner": owner,
                    "repository": repository,
                    "immutable_revision": revision,
                }
            )
        )
    exclusion_source = {
        "schema_version": "p15-v7-attempt-001-exclusion-projection-v1",
        "attempt_id": "p15-v7-attempt-001",
        "source_allowlist_sha256": "d" * 64,
        "fresh": excluded_identity_keys,
        "heldout": [],
        "unbound_commit_sentinel": "UNBOUND",
        "counts": {
            "fresh": len(excluded_identity_keys),
            "heldout": 0,
            "total": len(excluded_identity_keys),
        },
    }
    contract: dict[str, object] = {
        "schema_version": "p15-v7-minimal-online-causal-attempt-v2",
        "attempt_id": "p15-v7-attempt-002",
        "execution_role": "authoritative_pre_corpus",
        "status": "pre_corpus_frozen_before_allowlist",
        "candidate": {"product_projection_sha256": "a" * 64},
        "identity_selection": {
            "contract_binding": {
                "projection_algorithm": (
                    "sha256_of_canonical_contract_excluding_future_binding_and_receipt_fields"
                ),
                "projection_sha256": "",
                "expected_allowlist_sha256": "",
            },
            "selector": {
                "rule_version": "p15-v7-identity-selector-v1",
                "input": "identity_only_repository_catalog",
                "sort_keys": [
                    "normalized_provider",
                    "normalized_owner",
                    "normalized_repository",
                    "immutable_revision",
                    "identity_sha256",
                ],
                "sort_direction": "ascending",
                "normalization": {
                    "provider_owner_repository": "unicode_nfkc_casefold",
                    "immutable_revision": "lowercase_full_commit_sha",
                },
                "permitted_filters": [
                    "public_repository",
                    "supported_python_repository",
                    "immutable_revision_resolved",
                    "not_in_exclusion_projection",
                ],
                "forbidden_inputs": [
                    "repository_source",
                    "query_text",
                    "gold_target",
                    "planner_output",
                    "embedding_output",
                    "control_output",
                    "treatment_output",
                    "held_out_payload",
                ],
            },
            "exclusion_projection": {
                "algorithm": "sha256_of_canonical_repository_identity",
                "identity_fields": [
                    "provider",
                    "owner",
                    "repository",
                    "immutable_revision",
                ],
                "identity_sha256": excluded_identity_sha256,
                "complete_for_superseded_attempt": "p15-v7-attempt-001",
                "projection_sha256": canonical_sha256(exclusion_source),
                "fresh": excluded_identity_keys,
                "heldout": [],
                "unbound_commit_sentinel": "UNBOUND",
                "counts": exclusion_source["counts"],
            },
            "allowlist_permitting": {
                "required_repository_count": 2,
                "allowlist_minimum_entries": 2,
                "selected_identity_count": 2,
                "selection_rule": (
                    "first_two_eligible_identities_in_exact_selector_order"
                ),
                "identity_comparison_fields": [
                    "provider",
                    "owner",
                    "repository",
                ],
                "identity_comparison_normalization": "unicode_nfkc_casefold",
                "execution_repository_distinct_fields": [
                    "owner",
                    "repository",
                ],
                "execution_prefix_distinct_canonical_repositories": True,
                "ordinals_must_be_contiguous_from_one": True,
                "skip_forbidden": True,
                "cherry_pick_forbidden": True,
                "subset_copy_forbidden": True,
            },
            "future_allowlist": {
                "schema_version": "p15-v7-fresh-identity-allowlist-v1",
                "attempt_id": "p15-v7-attempt-002",
                "received": False,
                "identity_selected": False,
                "path": "",
                "sha256": "",
            },
        },
        "corpus": {
            "fresh_repositories": [],
            "fresh_cases": [],
            "held_out": {"identity_selected": False, "opened": False},
        },
        "sampling": {"expanded_schedule": []},
        "governance": {
            "fresh_identity_selected": False,
            "fresh_source_accessed": False,
            "candidate_executed": False,
            "online_requests_made": False,
            "ollama_requests_made": False,
            "held_out_opened": False,
        },
        "pre_corpus_counters": {
            "planner_calls": 0,
            "embedding_calls": 0,
            "source_accesses": 0,
            "treatment_executions": 0,
            "held_out_accesses": 0,
        },
        "supersession_audit": {
            "path": "audit/p15-v7-attempt-001-supersession.json",
            "sha256": "b" * 64,
            "execution_input": False,
        },
    }
    binding = contract["identity_selection"]["contract_binding"]
    binding["projection_sha256"] = contract_projection_sha256(contract)
    return contract


def _allowlist(contract: dict[str, object]) -> dict[str, object]:
    entries = [
        _identity("fresh-owner-a", "fresh-repo-a", "1" * 40),
        _identity("fresh-owner-b", "fresh-repo-b", "2" * 40),
        _identity("fresh-owner-c", "fresh-repo-c", "3" * 40),
    ]
    for ordinal, entry in enumerate(entries, start=1):
        entry["ordinal"] = ordinal
    return {
        "schema_version": "p15-v7-fresh-identity-allowlist-v1",
        "attempt_id": "p15-v7-attempt-002",
        "contract_projection_sha256": contract_projection_sha256(contract),
        "entries": entries,
    }


def _bind(contract: dict[str, object], allowlist: dict[str, object]) -> None:
    contract["identity_selection"]["contract_binding"][
        "expected_allowlist_sha256"
    ] = canonical_sha256(allowlist)
    contract["identity_selection"]["future_allowlist"].update(
        {
            "received": True,
            "identity_selected": True,
            "path": "fresh-allowlist.json",
            "sha256": canonical_sha256(allowlist),
        }
    )


def test_repository_contract_is_attempt_002_and_frozen_before_allowlist() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    validate_pre_corpus_contract(contract)

    assert contract["attempt_id"] == "p15-v7-attempt-002"
    assert contract["execution_role"] == "authoritative_pre_corpus"
    assert contract["status"] == "pre_corpus_frozen_before_allowlist"


def test_repository_bundle_has_one_executable_contract_and_valid_audit() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    validate_pre_corpus_contract(contract)
    audit_ref = contract["supersession_audit"]
    audit_path = FIXTURE_ROOT / audit_ref["path"]
    assert hashlib.sha256(audit_path.read_bytes()).hexdigest() == audit_ref["sha256"]
    validate_supersession_audit(
        contract,
        json.loads(audit_path.read_text(encoding="utf-8")),
    )


def test_repository_audit_records_source_materialization_before_supersession() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    assert audit["schema_version"] == "p15-v7-supersession-audit-v2"
    assert audit["disposition"] == "superseded-before-execution"
    assert audit["source_evidence"]["source_materialized"] is True
    assert audit["source_evidence"]["source_touched"] is True
    assert audit["source_evidence"]["materialized_checkout_count_minimum"] == 1
    assert audit["source_evidence"]["source_content_observed"] == "not_established"
    validate_supersession_audit(contract, audit)

    dishonest = copy.deepcopy(audit)
    dishonest["disposition"] = "superseded-before-source"
    dishonest["source_evidence"]["source_materialized"] = False
    dishonest["source_evidence"]["materialized_checkout_count_minimum"] = 0
    with pytest.raises(GovernanceValidationError, match="source materialization"):
        validate_supersession_audit(contract, dishonest)


def test_future_allowlist_is_bound_bidirectionally_to_frozen_contract() -> None:
    contract = _contract()
    allowlist = _allowlist(contract)
    _bind(contract, allowlist)

    validate_future_allowlist_binding(contract, allowlist)

    wrong_attempt = copy.deepcopy(allowlist)
    wrong_attempt["attempt_id"] = "p15-v7-attempt-001"
    with pytest.raises(GovernanceValidationError, match="attempt"):
        validate_future_allowlist_binding(contract, wrong_attempt)

    wrong_contract_hash = copy.deepcopy(allowlist)
    wrong_contract_hash["contract_projection_sha256"] = "0" * 64
    with pytest.raises(GovernanceValidationError, match="contract projection"):
        validate_future_allowlist_binding(contract, wrong_contract_hash)

    wrong_allowlist_hash = copy.deepcopy(contract)
    wrong_allowlist_hash["identity_selection"]["contract_binding"][
        "expected_allowlist_sha256"
    ] = "0" * 64
    with pytest.raises(GovernanceValidationError, match="allowlist hash"):
        validate_future_allowlist_binding(wrong_allowlist_hash, allowlist)


def test_future_allowlist_requires_minimum_repository_count() -> None:
    contract = _contract()
    allowlist = _allowlist(contract)
    allowlist["entries"] = allowlist["entries"][:1]
    _bind(contract, allowlist)

    with pytest.raises(GovernanceValidationError, match="at least 2 entries"):
        validate_future_allowlist_binding(contract, allowlist)


@pytest.mark.parametrize("selected_count", [1, 3])
def test_selected_schedule_requires_exact_repository_count(
    selected_count: int,
) -> None:
    contract = _contract()
    allowlist = _allowlist(contract)
    selected = [
        entry["identity_sha256"]
        for entry in allowlist["entries"][:selected_count]
    ]

    with pytest.raises(GovernanceValidationError, match="exactly 2 identities"):
        validate_selected_identity_schedule(contract, allowlist, selected)


def test_contract_projection_proves_contract_was_frozen_before_allowlist() -> None:
    contract = _contract()
    allowlist = _allowlist(contract)
    _bind(contract, allowlist)

    mutated_contract = copy.deepcopy(contract)
    mutated_contract["candidate"]["product_projection_sha256"] = "c" * 64

    with pytest.raises(GovernanceValidationError, match="contract projection"):
        validate_future_allowlist_binding(mutated_contract, allowlist)


def test_pre_corpus_contract_has_no_corpus_effect_or_execution() -> None:
    contract = _contract()
    validate_pre_corpus_contract(contract)

    for counter in contract["pre_corpus_counters"].values():
        assert counter == 0
    assert contract["corpus"]["fresh_repositories"] == []
    assert contract["corpus"]["fresh_cases"] == []
    assert contract["sampling"]["expanded_schedule"] == []

    for key in (
        "fresh_identity_selected",
        "fresh_source_accessed",
        "candidate_executed",
        "online_requests_made",
        "ollama_requests_made",
        "held_out_opened",
    ):
        assert contract["governance"][key] is False


def test_superseded_hashes_are_audit_only_and_never_execution_inputs() -> None:
    contract = _contract()
    audit = {
        "schema_version": "p15-v7-supersession-audit-v2",
        "attempt_id": "p15-v7-attempt-001",
        "status": "INCONCLUSIVE",
        "disposition": "superseded-before-execution",
        "execution_eligible": False,
        "old_contract": {"sha256": "c" * 64, "audit_only": True},
        "old_allowlist": {
            "identity_only_sha256": "d" * 64,
            "audit_only": True,
        },
        "exclusion_projection": {
            "sha256": contract["identity_selection"]["exclusion_projection"][
                "projection_sha256"
            ],
            "identity_only": True,
            "contract_exclusion_input": True,
        },
        "timeline": {
            "allowlist_recorded_at": "2026-08-02T11:24:52+08:00",
            "source_materialized_at": "2026-08-02T11:25:22+08:00",
            "audit_created_at": "2026-08-02T12:58:47+08:00",
        },
        "source_evidence": {
            "checkout_identity": (
                "agronholm/anyio@003e5d6bc3eba8f4e75bf2b2b5fb3f7dd11e6330"
            ),
            "checkout_root": (
                ".quality/p15-v7-attempt-001/stage2/sources/rank-01-anyio"
            ),
            "observed_paths": [".git/index", "src/anyio/__init__.py"],
            "source_materialized": True,
            "source_touched": True,
            "materialized_checkout_count_minimum": 1,
            "source_content_observed": "not_established",
        },
        "execution_observations": {
            "corpus_generated": False,
            "planner_calls": 0,
            "embedding_calls": 0,
            "online_calls": 0,
            "control_executions": 0,
            "treatment_executions": 0,
            "effect_observations": 0,
            "ollama_calls": 0,
            "held_out_accesses": 0,
        },
    }

    validate_supersession_audit(contract, audit)

    leaked = copy.deepcopy(contract)
    leaked["candidate"]["old_allowlist_sha256"] = "d" * 64
    with pytest.raises(GovernanceValidationError, match="audit-only hash"):
        validate_supersession_audit(leaked, audit)


@pytest.mark.parametrize("copy_mode", ["single_reuse", "subset_copy"])
def test_old_identity_reuse_and_subset_copy_are_rejected(copy_mode: str) -> None:
    excluded = _identity("old-owner", "old-repo", "4" * 40)
    contract = _contract(
        excluded_identity_keys=[f"old-owner/old-repo@{'4' * 40}"]
    )
    allowlist = _allowlist(contract)
    reused = copy.deepcopy(excluded)
    reused["ordinal"] = 1
    if copy_mode == "single_reuse":
        second = allowlist["entries"][1]
        second["ordinal"] = 2
        allowlist["entries"] = [reused, second]
    else:
        allowlist["entries"] = [reused, *allowlist["entries"]]
        for ordinal, entry in enumerate(allowlist["entries"], start=1):
            entry["ordinal"] = ordinal
    _bind(contract, allowlist)

    with pytest.raises(GovernanceValidationError, match="excluded identity"):
        validate_future_allowlist_binding(contract, allowlist)


def test_old_repository_reuse_at_a_different_revision_is_rejected() -> None:
    contract = _contract(
        excluded_identity_keys=[f"old-owner/old-repo@{'4' * 40}"]
    )
    allowlist = _allowlist(contract)
    allowlist["entries"][0] = _identity(
        "old-owner", "old-repo", "5" * 40
    )
    allowlist["entries"][0]["ordinal"] = 1
    _bind(contract, allowlist)

    with pytest.raises(GovernanceValidationError, match="excluded identity"):
        validate_future_allowlist_binding(contract, allowlist)


def test_old_repository_case_variant_at_a_different_revision_is_rejected() -> None:
    contract = _contract(
        excluded_identity_keys=[f"old-owner/old-repo@{'4' * 40}"]
    )
    allowlist = _allowlist(contract)
    allowlist["entries"][0] = _identity(
        "OLD-OWNER", "Old-Repo", "5" * 40
    )
    allowlist["entries"][0]["ordinal"] = 1
    _bind(contract, allowlist)

    with pytest.raises(GovernanceValidationError, match="excluded identity"):
        validate_future_allowlist_binding(contract, allowlist)


def test_old_repository_nfkc_variant_at_a_different_revision_is_rejected() -> None:
    contract = _contract(
        excluded_identity_keys=[f"old-owner/old-repo@{'4' * 40}"]
    )
    allowlist = _allowlist(contract)
    reused = _identity("ＯＬＤ－ＯＷＮＥＲ", "Ｏｌｄ－Ｒｅｐｏ", "5" * 40)
    reused["provider"] = "ＧｉｔＨｕｂ"
    reused["identity_sha256"] = canonical_sha256(
        {
            "provider": reused["provider"],
            "owner": reused["owner"],
            "repository": reused["repository"],
            "immutable_revision": reused["immutable_revision"],
        }
    )
    reused["ordinal"] = 1
    allowlist["entries"][0] = reused
    _bind(contract, allowlist)

    with pytest.raises(GovernanceValidationError, match="excluded identity"):
        validate_future_allowlist_binding(contract, allowlist)


@pytest.mark.parametrize(
    "selected_ordinals",
    [
        [2, 3],
        [1, 3],
        [2, 1],
    ],
    ids=["skip_first", "cherry_pick_third", "reorder"],
)
def test_skip_and_cherry_pick_selection_are_rejected(
    selected_ordinals: list[int],
) -> None:
    contract = _contract()
    allowlist = _allowlist(contract)
    _bind(contract, allowlist)
    validate_future_allowlist_binding(contract, allowlist)
    selected = [
        allowlist["entries"][ordinal - 1]["identity_sha256"]
        for ordinal in selected_ordinals
    ]

    with pytest.raises(GovernanceValidationError, match="exact allowlist prefix"):
        validate_selected_identity_schedule(contract, allowlist, selected)


def test_allowlist_ordinals_must_be_contiguous_and_sorted() -> None:
    contract = _contract()
    allowlist = _allowlist(contract)
    allowlist["entries"][1]["ordinal"] = 4
    _bind(contract, allowlist)

    with pytest.raises(GovernanceValidationError, match="contiguous"):
        validate_future_allowlist_binding(contract, allowlist)


def test_allowlist_prefix_requires_two_distinct_canonical_repositories() -> None:
    contract = _contract()
    allowlist = _allowlist(contract)
    allowlist["entries"][:2] = [
        _identity("a-owner", "same-repo", "1" * 40),
        _identity("A-OWNER", "Same-Repo", "2" * 40),
    ]
    for ordinal, entry in enumerate(allowlist["entries"], start=1):
        entry["ordinal"] = ordinal
    _bind(contract, allowlist)

    with pytest.raises(GovernanceValidationError, match="distinct repositories"):
        validate_future_allowlist_binding(contract, allowlist)


def test_selected_schedule_requires_two_distinct_canonical_repositories() -> None:
    contract = _contract()
    allowlist = _allowlist(contract)
    allowlist["entries"][:2] = [
        _identity("a-owner", "same-repo", "1" * 40),
        _identity("A-OWNER", "Same-Repo", "2" * 40),
    ]
    selected = [
        entry["identity_sha256"] for entry in allowlist["entries"][:2]
    ]

    with pytest.raises(GovernanceValidationError, match="distinct repositories"):
        validate_selected_identity_schedule(contract, allowlist, selected)
