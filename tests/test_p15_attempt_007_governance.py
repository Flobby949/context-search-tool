from __future__ import annotations

import copy
import hashlib
import json
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pytest

from p15_attempt_007_governance import (
    Attempt007ValidationError,
    validate_attempt_002_identity_audit,
    validate_attempt_003_catalog_failure_audit,
    validate_attempt_004_catalog_failure_audit,
    validate_attempt_005_ref_failure_audit,
    validate_attempt_006_catalog_failure_audit,
    validate_catalog_allowlist,
    validate_catalog_capture,
    validate_execution_selection,
    validate_git_catalog_allowlist,
    validate_git_resolution_receipt,
    validate_pre_catalog_contract,
    validate_repository_bundle,
    validate_sealed_catalog_receipt,
    run_bounded_prefix2_resolution,
)


pytestmark = pytest.mark.archival_acceptance


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = (
    PROJECT_ROOT / "tests/fixtures/p15_v7_minimal_online_causal"
)
CONTRACT_PATH = FIXTURE_ROOT / "attempt-contract.json"
ATTEMPT_002_AUDIT_PATH = (
    FIXTURE_ROOT / "audit/attempt-002-identity-query-audit.json"
)
ATTEMPT_003_AUDIT_PATH = (
    FIXTURE_ROOT / "audit/attempt-003-catalog-failure-audit.json"
)
ATTEMPT_004_AUDIT_PATH = (
    FIXTURE_ROOT / "audit/attempt-004-catalog-failure-audit.json"
)
ATTEMPT_005_AUDIT_PATH = (
    FIXTURE_ROOT / "audit/attempt-005-ref-failure-audit.json"
)
ATTEMPT_006_AUDIT_PATH = (
    FIXTURE_ROOT / "audit/attempt-006-catalog-validation-failure-audit.json"
)

FROZEN_AT = "2026-08-02T08:37:12Z"
WINDOW_START = "2026-07-05T08:00:00Z"
WINDOW_END = "2026-07-05T08:04:59Z"
PRIOR_WINDOW_START = "2026-07-04T06:00:00Z"
PRIOR_WINDOW_END = "2026-07-04T06:04:59Z"
QUERY = (
    "language:Python is:public "
    f"created:{WINDOW_START}..{WINDOW_END}"
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _repository_key(item: dict[str, object]) -> str:
    return "/".join(
        (
            _normalize(str(item["provider"])),
            _normalize(str(item["owner"])),
            _normalize(str(item["repository"])),
        )
    )


def _pre_ref_sort_key(item: dict[str, object]) -> tuple[str, str, str]:
    return (
        _normalize(str(item["provider"])),
        _normalize(str(item["owner"])),
        _normalize(str(item["repository"])),
    )


def _identity_sha256(item: dict[str, object], revision: str) -> str:
    return _sha(
        {
            "provider": item["provider"],
            "owner": item["owner"],
            "repository": item["repository"],
            "default_branch": item["default_branch"],
            "immutable_revision": revision,
        }
    )


def _contract_projection(contract: dict[str, object]) -> str:
    projection = copy.deepcopy(contract)
    projection["contract_binding"]["projection_sha256"] = ""
    projection["catalog_receipt"] = {
        "received": False,
        "path": "",
        "sha256": "",
    }
    projection["future_allowlist"] = {
        "received": False,
        "path": "",
        "sha256": "",
        "identity_selected": False,
    }
    projection["approval_receipt"] = {
        "received": False,
        "path": "",
        "sha256": "",
    }
    return _sha(projection)


def _contract() -> dict[str, object]:
    exclusions = ["github/old-owner/old-repo"] + [
        f"github/excluded-owner-{index:02d}/excluded-repo-{index:02d}"
        for index in range(19)
    ] + ["github/coinhubmedia/melt-calculator-domains"]
    contract: dict[str, object] = {
        "schema_version": "p15-v7-minimal-online-causal-attempt-v7",
        "attempt_id": "p15-v7-attempt-007",
        "execution_role": "two_repository_acceptance_draft",
        "status": "DRAFT",
        "execution_eligible": False,
        "user_approval_required": True,
        "approval_receipt": {
            "received": False,
            "path": "",
            "sha256": "",
        },
        "approval_rule": {
            "scope": (
                "single_receipt_authorizes_two_refs_then_source_then_fresh_"
                "then_if_fresh_passes_heldout_and_release"
            ),
            "reapproval_triggers": [
                "plan_field_change",
                "threshold_change",
                "query_change",
                "model_change",
                "case_rule_change",
            ],
        },
        "contract_frozen_at_utc": FROZEN_AT,
        "contract_binding": {
            "projection_algorithm": (
                "sha256_of_canonical_contract_with_empty_catalog_allowlist_"
                "and_approval_receipts"
            ),
            "projection_sha256": "",
        },
        "catalog_contract": {
            "provider": "github",
            "transport": "GitHub REST",
            "api_version": "2022-11-28",
            "window_derivation": (
                "window_start=floor_utc_hour(contract_frozen_at_utc)-P28D;"
                "duration=PT5M;window_end=window_start+PT5M-PT1S"
            ),
            "window_duration": "PT5M",
            "window_start_utc": WINDOW_START,
            "window_end_utc": WINDOW_END,
            "prior_universe_exclusion": {
                "rule": "closed_interval_disjoint_from_attempt_005_catalog_window",
                "attempt_id": "p15-v7-attempt-005",
                "window_start_utc": PRIOR_WINDOW_START,
                "window_end_utc": PRIOR_WINDOW_END,
            },
            "search_endpoint": "https://api.github.com/search/repositories",
            "q": QUERY,
            "sort": "updated",
            "order": "asc",
            "per_page": 100,
            "max_total_count": 1000,
            "required_full_passes": 2,
            "catalog_integrity_rule": (
                "two_full_passes_exact_total_and_canonical_body_projection"
            ),
            "page_receipt_etag_rule": (
                "hash_bound_nullable_observation_not_integrity_evidence"
            ),
            "catalog_receipt_rule": (
                "append_only_full_ordered_catalog_and_page_evidence_"
                "sealed_before_refs"
            ),
            "max_server_date_lag_seconds": 5,
            "page_attempts": 1,
            "request_headers": {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            "ref_resolution_protocol": _git_transport_contract(),
            "resolution_receipt_rule": (
                "append_only_all_attempts_for_canonical_prefix2_only"
            ),
            "failure_policy": (
                "resolution_exhaustion_inconclusive_no_third_repository_or_"
                "substitution"
            ),
        },
        "offline_catalog_source": {
            "mode": "immutable_attempt_006_capture_no_requery",
            "attempt_id": "p15-v7-attempt-006",
            "archived_contract_path": "audit/p15-v7-attempt-006-contract.json",
            "archived_contract_sha256": "ba8e5b5a48b8d3f5e5699db033c931eab958f851c7075d8a7d5b6354e980341b",
            "archived_contract_projection_sha256": "74ac868812404ca83b23eab82571b264cd9e4d8a822202a77276cae2bc3e3afc",
            "audit_path": "audit/attempt-006-catalog-validation-failure-audit.json",
            "audit_sha256": "d055aed2a4b9742a4812df3be1875ff2589c1dea94284b990b4a27bf604d2691",
            "capture_path": "audit/attempt-006-catalog-validation-failure-capture.json",
            "capture_sha256": "c7ec58c12b3acafe8f3bd92598e28e51b47c8b70680e2719a722be5c2ae251db",
            "capture_projection_sha256": "5974cb5b74708608a4ecc8b328367c025cb7f9b117ba78961edb67e88cceab72",
            "catalog_requests_exact": 0,
        },
        "catalog_ordering": {
            "pre_ref": {
                "tuple": [
                    "NFKC(provider).casefold()",
                    "NFKC(owner).casefold()",
                    "NFKC(repository).casefold()",
                ],
                "order": "unicode_lex_ascending",
                "tie_policy": (
                    "duplicate_normalized_repository_fail_no_input_or_api_tie"
                ),
            },
            "post_ref": {
                "tuple": [
                    "NFKC(provider).casefold()",
                    "NFKC(owner).casefold()",
                    "NFKC(repository).casefold()",
                    "immutable_revision.lower()",
                    "identity_sha256.lower()",
                ],
                "identity_fields": [
                    "provider",
                    "owner",
                    "repository",
                    "default_branch",
                    "immutable_revision",
                ],
                "identity_sha256_algorithm": (
                    "sha256_of_canonical_json_identity_sort_keys_compact_ascii"
                ),
                "order": "unicode_lex_ascending",
                "tie_policy": "duplicate_repository_or_tuple_fail",
            },
            "updated_at_role": "evidence_only_forbidden_from_eligibility_and_sort",
        },
        "exclusion_projection": {
            "normalization": "provider_owner_repository_unicode_nfkc_casefold",
            "canonical_repositories": exclusions,
            "count": 21,
            "canonical_repository_list_algorithm": (
                "sha256_of_canonical_json_canonical_repositories_array_"
                "sort_keys_compact_ascii"
            ),
            "canonical_repository_list_sha256": _sha(exclusions),
            "projection_algorithm": (
                "sha256_of_canonical_json_normalization_canonical_repositories_"
                "count_sort_keys_compact_ascii"
            ),
            "projection_sha256": _sha(
                {
                    "normalization": (
                        "provider_owner_repository_unicode_nfkc_casefold"
                    ),
                    "canonical_repositories": exclusions,
                    "count": 21,
                }
            ),
            "source_audits": [
                {
                    "attempt_id": "p15-v7-attempt-001",
                    "path": "audit/p15-v7-attempt-001-supersession.json",
                    "sha256": "a" * 64,
                    "audit_only_hashes": True,
                },
                {
                    "attempt_id": "p15-v7-attempt-002",
                    "path": "audit/attempt-002-identity-query-audit.json",
                    "sha256": "b" * 64,
                    "audit_only_hashes": True,
                },
                {
                    "attempt_id": "p15-v7-attempt-003",
                    "path": "audit/attempt-003-catalog-failure-audit.json",
                    "sha256": "c" * 64,
                    "audit_only_hashes": True,
                },
                {
                    "attempt_id": "p15-v7-attempt-004",
                    "path": "audit/attempt-004-catalog-failure-audit.json",
                    "sha256": "d" * 64,
                    "audit_only_hashes": True,
                },
                {
                    "attempt_id": "p15-v7-attempt-005",
                    "path": "audit/attempt-005-ref-failure-audit.json",
                    "sha256": "e" * 64,
                    "audit_only_hashes": True,
                },
                {
                    "attempt_id": "p15-v7-attempt-006",
                    "path": "audit/attempt-006-catalog-validation-failure-audit.json",
                    "sha256": "d055aed2a4b9742a4812df3be1875ff2589c1dea94284b990b4a27bf604d2691",
                    "audit_only_hashes": True,
                },
            ],
        },
        "eligibility": {
            "only": [
                "public",
                "language_python",
                "default_branch_commit_resolved",
                "not_excluded",
            ]
        },
        "allowlist_rule": {
            "contents": "resolved_eligible_canonical_prefix2_only",
            "order": "frozen_post_ref_five_tuple_ascending",
        },
        "execution_rule": {
            "repository_count": 2,
            "selection": "canonical_catalog_prefix2",
            "distinct_canonical_repositories": True,
            "fallback_beyond_prefix_forbidden": True,
            "resolution_attempts_per_repository": 3,
            "resolution_timeout_seconds": 30,
            "resolution_backoff_seconds": [0, 2, 5],
            "resolution_exhaustion_disposition": "INCONCLUSIVE",
        },
        "catalog_receipt": {
            "received": True,
            "path": "attempt-007-sealed-catalog-receipt.json",
            "sha256": "0" * 64,
        },
        "future_allowlist": {
            "received": False,
            "path": "",
            "sha256": "",
            "identity_selected": False,
        },
        "corpus": {
            "fresh_repositories": [],
            "fresh_cases": [],
            "fixed_denominators": {
                "repositories": 2,
                "cases": 12,
                "efficacy_targets": 8,
                "guard_cases": 4,
                "planner_samples": 24,
                "local_arm_replays": 96,
            },
            "per_repository": {"efficacy_cases": 4, "guard_cases": 2},
            "selection_contract": {
                "stage": "before_any_online_request",
                "repository_order": "resolved_canonical_prefix2",
                "structural_order": "frozen_independent_ast_order",
                "per_repository_indices": [1, 2, 3, 4, 5, 6],
                "guard_indices": [1, 2],
                "efficacy_candidate_indices": [3, 4, 5, 6],
                "cases_per_repository": 6,
                "repository_count": 2,
                "total_cases": 12,
                "scan_beyond_index_6_allowed": False,
                "case_replacement_allowed": False,
                "repository_replacement_allowed": False,
                "qualification_online_requests": 0,
                "efficacy_control_requirement": (
                    "gold_missing_in_both_complete_frozen_samples_else_"
                    "INCONCLUSIVE_CORPUS"
                ),
            },
        },
        "sampling": {"expanded_schedule": []},
        "zero_state": {
            "catalog_requests": 0,
            "ref_requests": 0,
            "source_accesses": 0,
            "planner_calls": 0,
            "embedding_calls": 0,
            "control_executions": 0,
            "treatment_executions": 0,
            "effect_observations": 0,
            "online_model_calls": 0,
            "ollama_calls": 0,
            "held_out_accesses": 0,
        },
    }
    contract["contract_binding"]["projection_sha256"] = _contract_projection(
        contract
    )
    return contract


def _item(index: int) -> dict[str, object]:
    updated_at = datetime(2026, 7, 3, 8, tzinfo=timezone.utc) + timedelta(
        minutes=index
    )
    return {
        "provider": "github",
        "owner": f"fresh-owner-{index:03d}",
        "repository": f"fresh-repo-{index:03d}",
        "visibility": "public",
        "language": "Python",
        "default_branch": "main",
        "updated_at": updated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _seal_request(request: dict[str, object]) -> None:
    request["projection_sha256"] = _sha(
        {key: value for key, value in request.items() if key != "projection_sha256"}
    )


def _seal_response(response: dict[str, object]) -> None:
    response["projection_sha256"] = _sha(
        {key: value for key, value in response.items() if key != "projection_sha256"}
    )


def _search_page(
    page: int,
    total_count: int,
    items: list[dict[str, object]],
    *,
    pass_number: int,
) -> dict[str, object]:
    request: dict[str, object] = {
        "method": "GET",
        "endpoint": "https://api.github.com/search/repositories",
        "issued_at_utc": (
            f"2026-08-02T08:{39 + pass_number:02d}:{page:02d}Z"
        ),
        "headers": {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        "params": {
            "q": QUERY,
            "sort": "updated",
            "order": "asc",
            "per_page": 100,
            "page": page,
        },
        "attempt_count": 1,
    }
    response: dict[str, object] = {
        "status": 200,
        "headers": {
            "Date": f"Sun, 02 Aug 2026 08:{41 + pass_number:02d}:{page:02d} GMT",
            "etag_present": True,
            "etag": f'"pass-{pass_number}-page-{page}"',
        },
        "total_count": total_count,
        "incomplete_results": False,
        "items": items,
    }
    _seal_request(request)
    _seal_response(response)
    return {"page": page, "request": request, "response": response}


def _seal_pass(catalog_pass: dict[str, object]) -> None:
    for page in catalog_pass["pages"]:
        _seal_request(page["request"])
        _seal_response(page["response"])
    repositories = [
        item
        for page in catalog_pass["pages"]
        for item in page["response"]["items"]
    ]
    catalog_pass["canonical_projection_sha256"] = _sha(
        {
            "total_count": catalog_pass["total_count"],
            "repositories": repositories,
        }
    )


def _ref_resolution(item: dict[str, object], index: int) -> dict[str, object]:
    branch = quote(str(item["default_branch"]), safe="")
    issued_minute, issued_second = divmod(index, 60)
    request: dict[str, object] = {
        "method": "GET",
        "endpoint": (
            "https://api.github.com/repos/"
            f"{item['owner']}/{item['repository']}/git/ref/heads/{branch}"
        ),
        "issued_at_utc": (
            f"2026-08-02T08:{50 + issued_minute:02d}:{issued_second:02d}Z"
        ),
        "headers": {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        "attempt_count": 1,
    }
    response: dict[str, object] = {
        "status": 200,
        "headers": {
            "Date": "Sun, 02 Aug 2026 09:00:00 GMT",
            "ETag": f'"ref-{index}"',
        },
        "object": {
            "type": "commit",
            "sha": f"{index + 1:040x}",
        },
    }
    _seal_request(request)
    _seal_response(response)
    return {
        "canonical_repository": _repository_key(item),
        "default_branch": item["default_branch"],
        "request": request,
        "response": response,
    }


def _capture(contract: dict[str, object], count: int = 3) -> dict[str, object]:
    items = [_item(index) for index in range(count)]
    passes = []
    for pass_number in (1, 2):
        pages = [
            _search_page(
                page_number,
                count,
                items[offset : offset + 100],
                pass_number=pass_number,
            )
            for page_number, offset in enumerate(range(0, count, 100), start=1)
        ]
        catalog_pass: dict[str, object] = {
            "pass_number": pass_number,
            "total_count": count,
            "pages": pages,
            "canonical_projection_sha256": "",
        }
        _seal_pass(catalog_pass)
        passes.append(catalog_pass)
    return {
        "schema_version": "p15-v7-attempt-007-catalog-capture-v1",
        "attempt_id": "p15-v7-attempt-007",
        "contract_projection_sha256": contract["contract_binding"][
            "projection_sha256"
        ],
        "passes": passes,
        "ref_resolutions": [
            _ref_resolution(item, index) for index, item in enumerate(items)
        ],
    }


def _text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _catalog_receipt(
    contract: dict[str, object], count: int = 3
) -> dict[str, object]:
    capture = _capture(contract, count=count)
    ordered_catalog = [
        copy.deepcopy(item)
        for page in capture["passes"][0]["pages"]
        for item in page["response"]["items"]
    ]
    receipt: dict[str, object] = {
        "schema_version": "p15-v7-attempt-007-sealed-catalog-receipt-v1",
        "attempt_id": contract["attempt_id"],
        "contract_projection_sha256": contract["contract_binding"][
            "projection_sha256"
        ],
        "source_capture_sha256": contract["offline_catalog_source"][
            "capture_sha256"
        ],
        "storage_mode": "append_only",
        "sealed": True,
        "sealed_at_utc": "2026-08-02T09:00:00Z",
        "passes": copy.deepcopy(capture["passes"]),
        "ordered_catalog_count": count,
        "ordered_catalog": ordered_catalog,
        "ordered_catalog_sha256": _sha(ordered_catalog),
    }
    receipt["projection_sha256"] = _sha(receipt)
    return receipt


def _reseal_catalog_receipt(receipt: dict[str, object]) -> None:
    for catalog_pass in receipt["passes"]:
        _seal_pass(catalog_pass)
    raw_catalog = [
        item
        for page in receipt["passes"][0]["pages"]
        for item in page["response"]["items"]
    ]
    receipt["ordered_catalog"] = sorted(
        (copy.deepcopy(item) for item in raw_catalog),
        key=_pre_ref_sort_key,
    )
    receipt["ordered_catalog_count"] = len(raw_catalog)
    receipt["ordered_catalog_sha256"] = _sha(receipt["ordered_catalog"])
    receipt["projection_sha256"] = _sha(
        {
            key: value
            for key, value in receipt.items()
            if key != "projection_sha256"
        }
    )


def _git_transport_contract() -> dict[str, object]:
    return {
        "protocol": "git_ls_remote_https_identity_only_v1",
        "argv_template": [
            "git",
            "-c",
            "credential.helper=",
            "ls-remote",
            "--refs",
            "https://github.com/{owner}/{repository}.git",
            "refs/heads/{default_branch_literal}",
        ],
        "default_branch_encoding": "literal_separate_argv_no_url_encoding",
        "environment": {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "LC_ALL": "C",
        },
        "timeout_seconds": 30,
        "attempts_per_repository": 3,
        "backoff_schedule_seconds": [0, 2, 5],
        "checkout_allowed": False,
        "repository_failure_policy": "retry_same_selected_repository_then_inconclusive",
        "global_failure_policy": "stop_inconclusive_no_fallback_beyond_canonical_prefix2",
        "order": "sealed_catalog_canonical_prefix2",
    }


def _seal_resolution_receipt(receipt: dict[str, object]) -> None:
    previous = "0" * 64
    for entry in receipt["entries"]:
        entry["previous_entry_sha256"] = previous
        entry["entry_sha256"] = _sha(
            {key: value for key, value in entry.items() if key != "entry_sha256"}
        )
        previous = entry["entry_sha256"]
    receipt["entries_count"] = len(receipt["entries"])
    receipt["entries_tail_sha256"] = previous
    receipt["projection_sha256"] = _sha(
        {
            key: value
            for key, value in receipt.items()
            if key != "projection_sha256"
        }
    )


def _git_resolution_receipt(
    contract: dict[str, object], catalog_receipt: dict[str, object]
) -> dict[str, object]:
    entries = []
    for ordinal, item in enumerate(
        catalog_receipt["ordered_catalog"][:2], start=1
    ):
        exact_ref = f"refs/heads/{item['default_branch']}"
        stdout = f"{ordinal:040x}\t{exact_ref}\n"
        entries.append(
            {
                "ordinal": ordinal,
                "canonical_repository": _repository_key(item),
                "owner": item["owner"],
                "repository": item["repository"],
                "default_branch": item["default_branch"],
                "request": {
                    "argv": [
                        "git",
                        "-c",
                        "credential.helper=",
                        "ls-remote",
                        "--refs",
                        (
                            "https://github.com/"
                            f"{item['owner']}/{item['repository']}.git"
                        ),
                        exact_ref,
                    ],
                    "environment": _git_transport_contract()["environment"],
                    "timeout_seconds": 30,
                    "attempt_count": 1,
                    "shell": False,
                },
                "observation": {
                    "transport_status": "exited",
                    "exit_code": 0,
                    "stdout": stdout,
                    "stdout_sha256": _text_sha(stdout),
                    "stderr_sha256": _text_sha(""),
                },
                "resolution": {
                    "status": "resolved",
                    "reason": "exact_single_ref",
                    "immutable_revision": f"{ordinal:040x}",
                },
                "previous_entry_sha256": "",
                "entry_sha256": "",
            }
        )
    receipt: dict[str, object] = {
        "schema_version": "p15-v7-attempt-007-git-resolution-receipt-v1",
        "attempt_id": contract["attempt_id"],
        "contract_projection_sha256": contract["contract_binding"][
            "projection_sha256"
        ],
        "catalog_receipt_sha256": _sha(catalog_receipt),
        "storage_mode": "append_only",
        "transport_contract": _git_transport_contract(),
        "entries": entries,
        "entries_count": len(entries),
        "entries_tail_sha256": "",
        "projection_sha256": "",
    }
    _seal_resolution_receipt(receipt)
    return receipt


def _git_allowlist(
    contract: dict[str, object],
    catalog_receipt: dict[str, object],
    resolution_receipt: dict[str, object],
) -> dict[str, object]:
    resolved = {
        entry["canonical_repository"]: entry["resolution"]["immutable_revision"]
        for entry in resolution_receipt["entries"]
        if entry["resolution"]["status"] == "resolved"
    }
    eligible = sorted(
        (
            item
            for item in catalog_receipt["ordered_catalog"]
            if _repository_key(item) in resolved
            and _repository_key(item)
            not in {
                _normalize(value)
                for value in contract["exclusion_projection"][
                    "canonical_repositories"
                ]
            }
        ),
        key=_repository_key,
    )
    entries = [
        {
            "ordinal": ordinal,
            "provider": item["provider"],
            "owner": item["owner"],
            "repository": item["repository"],
            "default_branch": item["default_branch"],
            "immutable_revision": resolved[_repository_key(item)],
            "identity_sha256": _identity_sha256(
                item, resolved[_repository_key(item)]
            ),
            "canonical_repository": _repository_key(item),
        }
        for ordinal, item in enumerate(eligible, start=1)
    ]
    allowlist: dict[str, object] = {
        "schema_version": "p15-v7-attempt-007-git-complete-allowlist-v1",
        "attempt_id": contract["attempt_id"],
        "catalog_receipt_sha256": _sha(catalog_receipt),
        "resolution_receipt_sha256": _sha(resolution_receipt),
        "entries": entries,
    }
    allowlist["projection_sha256"] = _sha(allowlist)
    return allowlist


def _allowlist(capture: dict[str, object]) -> dict[str, object]:
    items = sorted(
        (
            item
            for page in capture["passes"][0]["pages"]
            for item in page["response"]["items"]
        ),
        key=_repository_key,
    )
    refs = {
        item["canonical_repository"]: item
        for item in capture["ref_resolutions"]
    }
    entries = []
    for ordinal, item in enumerate(items, start=1):
        repository_key = _repository_key(item)
        entries.append(
            {
                "ordinal": ordinal,
                "provider": item["provider"],
                "owner": item["owner"],
                "repository": item["repository"],
                "default_branch": item["default_branch"],
                "immutable_revision": refs[repository_key]["response"]["object"][
                    "sha"
                ],
                "canonical_repository": repository_key,
            }
        )
    allowlist: dict[str, object] = {
        "schema_version": "p15-v7-attempt-007-complete-allowlist-v1",
        "attempt_id": "p15-v7-attempt-007",
        "catalog_capture_sha256": _sha(capture),
        "entries": entries,
    }
    allowlist["projection_sha256"] = _sha(
        {key: value for key, value in allowlist.items() if key != "projection_sha256"}
    )
    return allowlist


def test_repository_bundle_is_attempt_007_pre_ref_stable() -> None:
    validate_repository_bundle(PROJECT_ROOT)
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["attempt_id"] == "p15-v7-attempt-007"
    assert contract["status"] == "DRAFT"
    assert contract["execution_eligible"] is False
    assert contract["user_approval_required"] is True


def test_pre_catalog_contract_freezes_literal_window_and_zero_state() -> None:
    contract = _contract()
    validate_pre_catalog_contract(contract)
    assert contract["catalog_contract"]["window_start_utc"] == WINDOW_START
    assert contract["catalog_contract"]["window_end_utc"] == WINDOW_END
    assert contract["catalog_contract"]["q"] == QUERY
    assert all(value == 0 for value in contract["zero_state"].values())
    assert contract["approval_receipt"] == {
        "received": False,
        "path": "",
        "sha256": "",
    }
    assert contract["approval_rule"]["reapproval_triggers"] == [
        "plan_field_change",
        "threshold_change",
        "query_change",
        "model_change",
        "case_rule_change",
    ]


def test_corpus_contract_rejects_a_seventh_structural_candidate() -> None:
    contract = _contract()
    contract["corpus"]["selection_contract"][
        "per_repository_indices"
    ].append(7)
    contract["contract_binding"]["projection_sha256"] = _contract_projection(
        contract
    )

    with pytest.raises(Attempt007ValidationError):
        validate_pre_catalog_contract(contract)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("selection_contract", "qualification_online_requests", 1),
        ("selection_contract", "case_replacement_allowed", True),
        ("per_repository", "efficacy_cases", 5),
    ],
)
def test_corpus_contract_rejects_qualification_replacement_or_non_2_plus_4(
    section: str, field: str, value: object
) -> None:
    contract = _contract()
    contract["corpus"][section][field] = value
    contract["contract_binding"]["projection_sha256"] = _contract_projection(
        contract
    )

    with pytest.raises(Attempt007ValidationError):
        validate_pre_catalog_contract(contract)


def test_catalog_window_uses_p28d_five_minute_nonoverlap_protocol() -> None:
    contract = _contract()
    validate_pre_catalog_contract(contract)
    catalog = contract["catalog_contract"]
    assert catalog["window_derivation"] == (
        "window_start=floor_utc_hour(contract_frozen_at_utc)-P28D;"
        "duration=PT5M;window_end=window_start+PT5M-PT1S"
    )
    assert catalog["window_duration"] == "PT5M"
    assert catalog["window_start_utc"] == "2026-07-05T08:00:00Z"
    assert catalog["window_end_utc"] == "2026-07-05T08:04:59Z"
    assert catalog["q"] == (
        "language:Python is:public "
        "created:2026-07-05T08:00:00Z..2026-07-05T08:04:59Z"
    )


def test_catalog_window_rejects_overlap_with_attempt_005_universe() -> None:
    contract = _contract()
    contract["contract_frozen_at_utc"] = "2026-08-01T06:37:12Z"
    catalog = contract["catalog_contract"]
    catalog["window_start_utc"] = "2026-07-04T06:00:00Z"
    catalog["window_end_utc"] = "2026-07-04T06:04:59Z"
    catalog["q"] = (
        "language:Python is:public "
        "created:2026-07-04T06:00:00Z..2026-07-04T06:04:59Z"
    )
    contract["contract_binding"]["projection_sha256"] = _contract_projection(
        contract
    )

    with pytest.raises(Attempt007ValidationError):
        validate_pre_catalog_contract(contract)


def test_exclusion_union21_binds_list_and_object_projection_hashes() -> None:
    contract = _contract()
    exclusion = contract["exclusion_projection"]
    assert exclusion["canonical_repository_list_algorithm"] == (
        "sha256_of_canonical_json_canonical_repositories_array_"
        "sort_keys_compact_ascii"
    )
    assert exclusion["canonical_repository_list_sha256"] == _sha(
        exclusion["canonical_repositories"]
    )
    assert exclusion["projection_algorithm"] == (
        "sha256_of_canonical_json_normalization_canonical_repositories_"
        "count_sort_keys_compact_ascii"
    )
    assert exclusion["projection_sha256"] == _sha(
        {
            "normalization": exclusion["normalization"],
            "canonical_repositories": exclusion["canonical_repositories"],
            "count": exclusion["count"],
        }
    )
    validate_pre_catalog_contract(contract)


@pytest.mark.parametrize(
    "field",
    [
        "canonical_repository_list_algorithm",
        "canonical_repository_list_sha256",
        "projection_algorithm",
        "projection_sha256",
    ],
)
def test_exclusion_union21_hash_bindings_reject_resealed_mutation(field: str) -> None:
    contract = _contract()
    exclusion = contract["exclusion_projection"]
    exclusion[field] = "0" * 64
    contract["contract_binding"]["projection_sha256"] = _contract_projection(
        contract
    )

    with pytest.raises(Attempt007ValidationError):
        validate_pre_catalog_contract(contract)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("api_version", "2022-01-01"),
        ("window_derivation", "floor_utc_hour(contract_frozen_at_utc)-P28D"),
        ("window_duration", "PT1H"),
        ("window_start_utc", "2026-07-03T08:00:01Z"),
        ("window_end_utc", "2026-07-03T09:00:00Z"),
        ("q", QUERY + " stars:>1000"),
        ("sort", "stars"),
        ("order", "desc"),
        ("per_page", 99),
        ("max_total_count", 1001),
        ("required_full_passes", 1),
        ("catalog_integrity_rule", "etag_equality"),
        ("page_receipt_etag_rule", "required_integrity_evidence"),
        ("max_server_date_lag_seconds", 6),
        ("page_attempts", 2),
    ],
)
def test_pre_catalog_contract_rejects_catalog_boundary_changes(
    field: str, value: object
) -> None:
    contract = _contract()
    contract["catalog_contract"][field] = value
    contract["contract_binding"]["projection_sha256"] = _contract_projection(
        contract
    )
    with pytest.raises(Attempt007ValidationError):
        validate_pre_catalog_contract(contract)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("capture_sha256", "0" * 64),
        ("capture_projection_sha256", "0" * 64),
        ("catalog_requests_exact", 1),
    ],
)
def test_offline_source_binding_or_requery_change_fails_closed(
    field: str, value: object
) -> None:
    contract = _contract()
    contract["offline_catalog_source"][field] = value
    contract["contract_binding"]["projection_sha256"] = _contract_projection(
        contract
    )

    with pytest.raises(Attempt007ValidationError):
        validate_pre_catalog_contract(contract)


def test_valid_double_pass_catalog_and_complete_allowlist_are_accepted() -> None:
    contract = _contract()
    capture = _capture(contract)
    allowlist = _allowlist(capture)
    selected = [entry["canonical_repository"] for entry in allowlist["entries"][:2]]
    validate_catalog_capture(contract, capture)
    validate_catalog_allowlist(contract, capture, allowlist)
    validate_execution_selection(contract, allowlist, selected)


def test_sealed_catalog_precedes_complete_git_resolution_ledger() -> None:
    contract = _contract()
    catalog_receipt = _catalog_receipt(contract)
    resolution_receipt = _git_resolution_receipt(contract, catalog_receipt)
    allowlist = _git_allowlist(contract, catalog_receipt, resolution_receipt)

    catalog = validate_sealed_catalog_receipt(contract, catalog_receipt)
    resolved = validate_git_resolution_receipt(
        contract, catalog_receipt, resolution_receipt
    )
    validate_git_catalog_allowlist(
        contract, catalog_receipt, resolution_receipt, allowlist
    )

    assert len(catalog) == 3
    assert resolved == {
        "github/fresh-owner-000/fresh-repo-000": "0000000000000000000000000000000000000001",
        "github/fresh-owner-001/fresh-repo-001": "0000000000000000000000000000000000000002",
    }
    assert allowlist["entries"][0]["identity_sha256"] == (
        "de1a758a912e569e1ac192b557955044129c9114244bc15b06583c64dabf8dfd"
    )


def test_provider_order_inversions_canonicalize_before_pre_ref_receipt() -> None:
    contract = _contract()
    receipt = _catalog_receipt(contract)
    for catalog_pass in receipt["passes"]:
        items = catalog_pass["pages"][0]["response"]["items"]
        catalog_pass["pages"][0]["response"]["items"] = [
            items[2],
            items[0],
            items[1],
        ]
    _reseal_catalog_receipt(receipt)

    catalog = validate_sealed_catalog_receipt(contract, receipt)

    assert catalog == sorted(catalog, key=_pre_ref_sort_key)
    assert [item["owner"] for item in catalog] == [
        "fresh-owner-000",
        "fresh-owner-001",
        "fresh-owner-002",
    ]


def test_bounded_resolution_calls_exact_canonical_prefix2_of_130() -> None:
    contract = _contract()
    receipt = _catalog_receipt(contract, count=130)
    calls: list[dict[str, object]] = []

    def success(request: dict[str, object]) -> dict[str, object]:
        calls.append(copy.deepcopy(request))
        exact_ref = request["argv"][-1]
        return {
            "transport_status": "exited",
            "exit_code": 0,
            "stdout": f"{len(calls):040x}\t{exact_ref}\n",
            "stderr": "",
        }

    result = run_bounded_prefix2_resolution(
        contract,
        receipt,
        run_command=success,
        sleep=lambda _: None,
        user_approved=True,
    )

    assert result["status"] == "RESOLVED_PREFIX2"
    assert len(calls) == 2
    assert [request["argv"][-2] for request in calls] == [
        "https://github.com/fresh-owner-000/fresh-repo-000.git",
        "https://github.com/fresh-owner-001/fresh-repo-001.git",
    ]


def test_bounded_resolution_retries_timeout_on_same_selected_repository() -> None:
    contract = _contract()
    receipt = _catalog_receipt(contract)
    calls: list[dict[str, object]] = []
    sleeps: list[int] = []

    def timeout_then_success(request: dict[str, object]) -> dict[str, object]:
        calls.append(copy.deepcopy(request))
        if len(calls) == 1:
            return {
                "transport_status": "timeout",
                "exit_code": None,
                "stdout": "",
                "stderr": "",
            }
        return {
            "transport_status": "exited",
            "exit_code": 0,
            "stdout": f"{len(calls):040x}\t{request['argv'][-1]}\n",
            "stderr": "",
        }

    result = run_bounded_prefix2_resolution(
        contract,
        receipt,
        run_command=timeout_then_success,
        sleep=sleeps.append,
        user_approved=True,
    )

    assert result["status"] == "RESOLVED_PREFIX2"
    assert [request["argv"][-2] for request in calls] == [
        "https://github.com/fresh-owner-000/fresh-repo-000.git",
        "https://github.com/fresh-owner-000/fresh-repo-000.git",
        "https://github.com/fresh-owner-001/fresh-repo-001.git",
    ]
    assert sleeps == [2]
    assert len(result["entries"][0]["attempts"]) == 2


def test_bounded_resolution_stops_inconclusive_after_three_failures() -> None:
    contract = _contract()
    receipt = _catalog_receipt(contract)
    calls: list[dict[str, object]] = []
    sleeps: list[int] = []

    def always_timeout(request: dict[str, object]) -> dict[str, object]:
        calls.append(copy.deepcopy(request))
        return {
            "transport_status": "timeout",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
        }

    result = run_bounded_prefix2_resolution(
        contract,
        receipt,
        run_command=always_timeout,
        sleep=sleeps.append,
        user_approved=True,
    )

    assert result["status"] == "INCONCLUSIVE"
    assert len(calls) == 3
    assert {request["argv"][-2] for request in calls} == {
        "https://github.com/fresh-owner-000/fresh-repo-000.git"
    }
    assert [request["attempt_count"] for request in calls] == [1, 2, 3]
    assert sleeps == [2, 5]


@pytest.mark.parametrize("mutation", ["fewer_than_two", "duplicate_prefix"])
def test_bounded_resolution_rejects_invalid_prefix_before_calls(
    mutation: str,
) -> None:
    contract = _contract()
    receipt = _catalog_receipt(
        contract, count=1 if mutation == "fewer_than_two" else 2
    )
    if mutation == "duplicate_prefix":
        for catalog_pass in receipt["passes"]:
            items = catalog_pass["pages"][0]["response"]["items"]
            duplicate = copy.deepcopy(items[0])
            duplicate["owner"] = duplicate["owner"].upper()
            duplicate["repository"] = duplicate["repository"].upper()
            catalog_pass["pages"][0]["response"]["items"][1] = duplicate
        _reseal_catalog_receipt(receipt)
    calls: list[dict[str, object]] = []

    with pytest.raises(Attempt007ValidationError):
        run_bounded_prefix2_resolution(
            contract,
            receipt,
            run_command=lambda request: calls.append(request),
            sleep=lambda _: None,
            user_approved=True,
        )

    assert calls == []


def test_server_date_lag_of_exactly_five_seconds_is_accepted() -> None:
    contract = _contract()
    receipt = _catalog_receipt(contract)
    receipt["passes"][0]["pages"][0]["response"]["headers"]["Date"] = (
        "Sun, 02 Aug 2026 08:39:56 GMT"
    )
    _reseal_catalog_receipt(receipt)

    validate_sealed_catalog_receipt(contract, receipt)


def test_server_date_lag_over_five_seconds_is_rejected_after_rehash() -> None:
    contract = _contract()
    receipt = _catalog_receipt(contract)
    receipt["passes"][0]["pages"][0]["response"]["headers"]["Date"] = (
        "Sun, 02 Aug 2026 08:39:55 GMT"
    )
    _reseal_catalog_receipt(receipt)

    with pytest.raises(Attempt007ValidationError):
        validate_sealed_catalog_receipt(contract, receipt)


@pytest.mark.parametrize("mutation", ["prefreeze", "response_order"])
def test_server_dates_remain_frozen_and_ordered(mutation: str) -> None:
    contract = _contract()
    receipt = _catalog_receipt(contract, count=101)
    if mutation == "prefreeze":
        receipt["passes"][0]["pages"][0]["response"]["headers"]["Date"] = (
            "Sun, 02 Aug 2026 08:37:11 GMT"
        )
    else:
        receipt["passes"][0]["pages"][1]["response"]["headers"]["Date"] = (
            "Sun, 02 Aug 2026 08:42:00 GMT"
        )
    _reseal_catalog_receipt(receipt)

    with pytest.raises(Attempt007ValidationError):
        validate_sealed_catalog_receipt(contract, receipt)


def test_git_resolution_rejects_catalog_that_was_not_sealed_first() -> None:
    contract = _contract()
    catalog_receipt = _catalog_receipt(contract)
    catalog_receipt["sealed"] = False
    catalog_receipt["projection_sha256"] = _sha(
        {
            key: value
            for key, value in catalog_receipt.items()
            if key != "projection_sha256"
        }
    )
    resolution_receipt = _git_resolution_receipt(contract, catalog_receipt)

    with pytest.raises(Attempt007ValidationError, match="sealed"):
        validate_git_resolution_receipt(
            contract, catalog_receipt, resolution_receipt
        )


def test_prefix2_resolution_receipt_does_not_require_full_catalog_ledger() -> None:
    contract = _contract()
    catalog_receipt = _catalog_receipt(contract)
    receipt = _git_resolution_receipt(contract, catalog_receipt)
    receipt["entries"] = receipt["entries"][:2]
    _seal_resolution_receipt(receipt)

    resolved = validate_git_resolution_receipt(
        contract, catalog_receipt, receipt
    )

    assert list(resolved) == [
        "github/fresh-owner-000/fresh-repo-000",
        "github/fresh-owner-001/fresh-repo-001",
    ]


def test_partial_old_ledger_cannot_replace_prefix2_with_later_repository() -> None:
    contract = _contract()
    catalog_receipt = _catalog_receipt(contract)
    receipt = _git_resolution_receipt(contract, catalog_receipt)
    later = catalog_receipt["ordered_catalog"][2]
    entry = receipt["entries"][1]
    entry.update(
        {
            "canonical_repository": _repository_key(later),
            "owner": later["owner"],
            "repository": later["repository"],
            "default_branch": later["default_branch"],
        }
    )
    entry["request"]["argv"][-2] = (
        f"https://github.com/{later['owner']}/{later['repository']}.git"
    )
    _seal_resolution_receipt(receipt)

    with pytest.raises(Attempt007ValidationError):
        validate_git_resolution_receipt(contract, catalog_receipt, receipt)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "order", "count", "chain"]
)
def test_git_resolution_rejects_incomplete_or_non_append_only_ledger(
    mutation: str,
) -> None:
    contract = _contract()
    catalog_receipt = _catalog_receipt(contract)
    receipt = _git_resolution_receipt(contract, catalog_receipt)
    if mutation == "missing":
        receipt["entries"].pop()
        _seal_resolution_receipt(receipt)
    elif mutation == "duplicate":
        receipt["entries"][1] = copy.deepcopy(receipt["entries"][0])
        _seal_resolution_receipt(receipt)
    elif mutation == "order":
        receipt["entries"][0], receipt["entries"][1] = (
            receipt["entries"][1],
            receipt["entries"][0],
        )
        _seal_resolution_receipt(receipt)
    elif mutation == "count":
        receipt["entries_count"] -= 1
        receipt["projection_sha256"] = _sha(
            {
                key: value
                for key, value in receipt.items()
                if key != "projection_sha256"
            }
        )
    elif mutation == "chain":
        receipt["entries"][1]["previous_entry_sha256"] = "f" * 64
        receipt["projection_sha256"] = _sha(
            {
                key: value
                for key, value in receipt.items()
                if key != "projection_sha256"
            }
        )

    with pytest.raises(Attempt007ValidationError):
        validate_git_resolution_receipt(contract, catalog_receipt, receipt)


@pytest.mark.parametrize(
    ("stdout", "reason"),
    [
        ("", "empty_stdout"),
        ("malformed\n", "malformed_stdout"),
        (
            "0000000000000000000000000000000000000001\trefs/heads/main\n"
            "0000000000000000000000000000000000000002\trefs/heads/main\n",
            "multiple_lines",
        ),
        (
            "0000000000000000000000000000000000000001\trefs/heads/wrong\n",
            "wrong_ref",
        ),
    ],
)
def test_git_stdout_that_is_not_one_exact_ref_is_unresolved_and_continues(
    stdout: str, reason: str
) -> None:
    contract = _contract()
    catalog_receipt = _catalog_receipt(contract)
    receipt = _git_resolution_receipt(contract, catalog_receipt)
    entry = receipt["entries"][0]
    entry["observation"]["stdout"] = stdout
    entry["observation"]["stdout_sha256"] = _text_sha(stdout)
    entry["resolution"] = {
        "status": "unresolved",
        "reason": reason,
        "immutable_revision": None,
    }
    _seal_resolution_receipt(receipt)

    resolved = validate_git_resolution_receipt(
        contract, catalog_receipt, receipt
    )

    assert "github/fresh-owner-000/fresh-repo-000" not in resolved
    assert len(resolved) == 1


def test_git_repo_nonzero_is_deterministic_unresolved_and_continues() -> None:
    contract = _contract()
    catalog_receipt = _catalog_receipt(contract)
    receipt = _git_resolution_receipt(contract, catalog_receipt)
    entry = receipt["entries"][0]
    entry["observation"].update(
        {
            "exit_code": 128,
            "stdout": "",
            "stdout_sha256": _text_sha(""),
        }
    )
    entry["resolution"] = {
        "status": "unresolved",
        "reason": "process_nonzero",
        "immutable_revision": None,
    }
    _seal_resolution_receipt(receipt)

    resolved = validate_git_resolution_receipt(
        contract, catalog_receipt, receipt
    )
    allowlist = _git_allowlist(contract, catalog_receipt, receipt)
    validate_git_catalog_allowlist(
        contract, catalog_receipt, receipt, allowlist
    )

    assert len(resolved) == 1
    assert "github/fresh-owner-000/fresh-repo-000" not in resolved
    assert len(allowlist["entries"]) == 1


@pytest.mark.parametrize("failure", ["spawn_error", "timeout"])
def test_git_global_transport_failure_fails_attempt_and_preserves_catalog_receipt(
    failure: str,
) -> None:
    contract = _contract()
    catalog_receipt = _catalog_receipt(contract)
    original_catalog_sha256 = _sha(catalog_receipt)
    receipt = _git_resolution_receipt(contract, catalog_receipt)
    entry = receipt["entries"][0]
    entry["observation"].update(
        {
            "transport_status": failure,
            "exit_code": None,
            "stdout": "",
            "stdout_sha256": _text_sha(""),
        }
    )
    entry["resolution"] = {
        "status": "global_failure",
        "reason": failure,
        "immutable_revision": None,
    }
    _seal_resolution_receipt(receipt)

    with pytest.raises(Attempt007ValidationError, match="global git transport"):
        validate_git_resolution_receipt(contract, catalog_receipt, receipt)
    assert _sha(catalog_receipt) == original_catalog_sha256
    validate_sealed_catalog_receipt(contract, catalog_receipt)


def test_catalog_accepts_hash_bound_null_etag_receipt() -> None:
    contract = _contract()
    capture = _capture(contract)
    first_pass = capture["passes"][0]
    headers = first_pass["pages"][0]["response"]["headers"]
    headers["etag_present"] = False
    headers["etag"] = None
    _seal_pass(first_pass)

    validate_catalog_capture(contract, capture)


@pytest.mark.parametrize(
    ("etag_present", "etag"),
    [
        (True, None),
        (False, '"forged"'),
        (True, "null"),
    ],
)
def test_catalog_rejects_resealed_etag_presence_or_null_string_spoof(
    etag_present: bool, etag: str | None
) -> None:
    contract = _contract()
    capture = _capture(contract)
    first_pass = capture["passes"][0]
    headers = first_pass["pages"][0]["response"]["headers"]
    headers["etag_present"] = etag_present
    headers["etag"] = etag
    _seal_pass(first_pass)

    with pytest.raises(Attempt007ValidationError):
        validate_catalog_capture(contract, capture)


def test_catalog_null_etag_receipt_rejects_unsealed_field_tamper() -> None:
    contract = _contract()
    capture = _capture(contract)
    first_pass = capture["passes"][0]
    headers = first_pass["pages"][0]["response"]["headers"]
    headers["etag_present"] = False
    headers["etag"] = None
    _seal_pass(first_pass)
    headers["etag_present"] = True
    headers["etag"] = '"forged"'

    with pytest.raises(Attempt007ValidationError, match="projection hash mismatch"):
        validate_catalog_capture(contract, capture)


@pytest.mark.parametrize(
    "mutation",
    [
        "incomplete",
        "over_limit",
        "missing_page",
        "short_nonfinal_page",
        "duplicate_repository",
        "pass_drift",
        "non_200",
        "missing_date",
        "missing_etag",
        "retry",
        "query_change",
        "request_hash",
        "response_hash",
    ],
)
def test_catalog_capture_fail_closed_matrix(mutation: str) -> None:
    contract = _contract()
    capture = _capture(
        contract,
        count=101 if mutation in {"missing_page", "short_nonfinal_page"} else 3,
    )
    first_pass = capture["passes"][0]
    first_page = first_pass["pages"][0]
    if mutation == "incomplete":
        first_page["response"]["incomplete_results"] = True
        _seal_pass(first_pass)
    elif mutation == "over_limit":
        first_pass["total_count"] = 1001
        first_page["response"]["total_count"] = 1001
        _seal_pass(first_pass)
    elif mutation == "missing_page":
        first_pass["pages"].pop()
        _seal_pass(first_pass)
    elif mutation == "short_nonfinal_page":
        first_page["response"]["items"].pop()
        _seal_pass(first_pass)
    elif mutation == "duplicate_repository":
        duplicate = copy.deepcopy(first_page["response"]["items"][0])
        duplicate["owner"] = duplicate["owner"].upper()
        duplicate["repository"] = duplicate["repository"].upper()
        first_page["response"]["items"][1] = duplicate
        _seal_pass(first_pass)
    elif mutation == "pass_drift":
        second_item = capture["passes"][1]["pages"][0]["response"]["items"][0]
        second_item["repository"] = "drifted-repository"
        _seal_pass(capture["passes"][1])
    elif mutation == "non_200":
        first_page["response"]["status"] = 503
        _seal_pass(first_pass)
    elif mutation == "missing_date":
        first_page["response"]["headers"].pop("Date")
        _seal_pass(first_pass)
    elif mutation == "missing_etag":
        first_page["response"]["headers"].pop("etag")
        _seal_pass(first_pass)
    elif mutation == "retry":
        first_page["request"]["attempt_count"] = 2
        _seal_pass(first_pass)
    elif mutation == "query_change":
        first_page["request"]["params"]["q"] += " stars:>1000"
        _seal_pass(first_pass)
    elif mutation == "request_hash":
        first_page["request"]["projection_sha256"] = "0" * 64
    elif mutation == "response_hash":
        first_page["response"]["projection_sha256"] = "0" * 64
    with pytest.raises(Attempt007ValidationError):
        validate_catalog_capture(contract, capture)


@pytest.mark.parametrize("pass_index", [0, 1])
@pytest.mark.parametrize("timestamp_kind", ["issued_at_utc", "response_date"])
def test_catalog_rejects_pre_freeze_timestamp_after_resealing_hashes(
    pass_index: int, timestamp_kind: str
) -> None:
    contract = _contract()
    capture = _capture(contract, count=101)
    catalog_pass = capture["passes"][pass_index]
    page = catalog_pass["pages"][1]
    if timestamp_kind == "issued_at_utc":
        page["request"]["issued_at_utc"] = "2026-08-02T08:37:11Z"
    else:
        page["response"]["headers"]["Date"] = (
            "Sun, 02 Aug 2026 08:37:11 GMT"
        )
    _seal_pass(catalog_pass)

    with pytest.raises(Attempt007ValidationError):
        validate_catalog_capture(contract, capture)


@pytest.mark.parametrize(
    ("timestamp_kind", "invalid_value"),
    [
        ("issued_at_utc", "2026-13-02T08:42:01Z"),
        ("response_date", "Sun, 02 Aug 2026 08:42:01 UTC"),
    ],
)
def test_catalog_rejects_non_strict_timestamp_after_resealing_hashes(
    timestamp_kind: str, invalid_value: str
) -> None:
    contract = _contract()
    capture = _capture(contract)
    catalog_pass = capture["passes"][0]
    page = catalog_pass["pages"][0]
    if timestamp_kind == "issued_at_utc":
        page["request"]["issued_at_utc"] = invalid_value
    else:
        page["response"]["headers"]["Date"] = invalid_value
    _seal_pass(catalog_pass)

    with pytest.raises(Attempt007ValidationError):
        validate_catalog_capture(contract, capture)


@pytest.mark.parametrize("position", ["within_pass", "between_passes"])
def test_catalog_request_timestamps_are_nondecreasing_in_pass_page_order(
    position: str,
) -> None:
    contract = _contract()
    capture = _capture(contract, count=101)
    if position == "within_pass":
        catalog_pass = capture["passes"][0]
        catalog_pass["pages"][1]["request"]["issued_at_utc"] = (
            "2026-08-02T08:39:59Z"
        )
    else:
        catalog_pass = capture["passes"][1]
        catalog_pass["pages"][0]["request"]["issued_at_utc"] = (
            "2026-08-02T08:39:59Z"
        )
    _seal_pass(catalog_pass)

    with pytest.raises(Attempt007ValidationError):
        validate_catalog_capture(contract, capture)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "non_200",
        "wrong_endpoint",
        "wrong_object_type",
        "invalid_commit",
        "missing_date",
        "missing_etag",
        "retry",
        "request_hash",
        "response_hash",
    ],
)
def test_default_branch_ref_resolution_fail_closed_matrix(mutation: str) -> None:
    contract = _contract()
    capture = _capture(contract)
    if mutation == "missing":
        capture["ref_resolutions"].pop()
    elif mutation == "extra":
        capture["ref_resolutions"].append(
            copy.deepcopy(capture["ref_resolutions"][0])
        )
    else:
        ref = capture["ref_resolutions"][0]
        if mutation == "non_200":
            ref["response"]["status"] = 404
            _seal_response(ref["response"])
        elif mutation == "wrong_endpoint":
            ref["request"]["endpoint"] += "-other"
            _seal_request(ref["request"])
        elif mutation == "wrong_object_type":
            ref["response"]["object"]["type"] = "tag"
            _seal_response(ref["response"])
        elif mutation == "invalid_commit":
            ref["response"]["object"]["sha"] = "abc"
            _seal_response(ref["response"])
        elif mutation == "missing_date":
            ref["response"]["headers"].pop("Date")
            _seal_response(ref["response"])
        elif mutation == "missing_etag":
            ref["response"]["headers"].pop("ETag")
            _seal_response(ref["response"])
        elif mutation == "retry":
            ref["request"]["attempt_count"] = 2
            _seal_request(ref["request"])
        elif mutation == "request_hash":
            ref["request"]["projection_sha256"] = "0" * 64
        elif mutation == "response_hash":
            ref["response"]["projection_sha256"] = "0" * 64
    with pytest.raises(Attempt007ValidationError):
        validate_catalog_capture(contract, capture)


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("issued_at_utc", "2026-08-02T08:37:11Z"),
        ("issued_at_utc", "2026-13-02T08:50:00Z"),
        ("response_date", "Sun, 02 Aug 2026 08:37:11 GMT"),
        ("response_date", "Sun, 02 Aug 2026 08:55:00 UTC"),
    ],
)
def test_ref_resolution_rejects_invalid_request_response_timestamps(
    mutation: str, value: str
) -> None:
    contract = _contract()
    capture = _capture(contract)
    ref = capture["ref_resolutions"][0]
    if mutation == "issued_at_utc":
        ref["request"]["issued_at_utc"] = value
        _seal_request(ref["request"])
    else:
        ref["response"]["headers"]["Date"] = value
        _seal_response(ref["response"])

    with pytest.raises(Attempt007ValidationError):
        validate_catalog_capture(contract, capture)


def test_allowlist_is_complete_eligible_catalog_and_excludes_union21() -> None:
    contract = _contract()
    capture = _capture(contract)
    excluded = capture["passes"][0]["pages"][0]["response"]["items"][0]
    excluded.update(
        {
            "provider": "ＧｉｔＨｕｂ",
            "owner": "ＯＬＤ－ＯＷＮＥＲ",
            "repository": "Ｏｌｄ－Ｒｅｐｏ",
        }
    )
    for catalog_pass in capture["passes"]:
        catalog_pass["pages"][0]["response"]["items"][0] = copy.deepcopy(
            excluded
        )
        _seal_pass(catalog_pass)
    capture["ref_resolutions"][0] = _ref_resolution(excluded, 0)
    allowlist = _allowlist(capture)
    allowlist["entries"] = [
        entry
        for entry in allowlist["entries"]
        if entry["canonical_repository"] != "github/old-owner/old-repo"
    ]
    for ordinal, entry in enumerate(allowlist["entries"], start=1):
        entry["ordinal"] = ordinal
    allowlist["projection_sha256"] = _sha(
        {key: value for key, value in allowlist.items() if key != "projection_sha256"}
    )
    validate_catalog_capture(contract, capture)
    validate_catalog_allowlist(contract, capture, allowlist)


@pytest.mark.parametrize("mutation", ["missing", "extra", "reordered", "excluded"])
def test_allowlist_rejects_incomplete_extra_reordered_or_excluded_entries(
    mutation: str,
) -> None:
    contract = _contract()
    capture = _capture(contract)
    allowlist = _allowlist(capture)
    if mutation == "missing":
        allowlist["entries"].pop()
    elif mutation == "extra":
        extra = copy.deepcopy(allowlist["entries"][-1])
        extra["ordinal"] += 1
        extra["repository"] = "unobserved"
        extra["canonical_repository"] = "github/fresh-owner-999/unobserved"
        allowlist["entries"].append(extra)
    elif mutation == "reordered":
        allowlist["entries"][0], allowlist["entries"][1] = (
            allowlist["entries"][1],
            allowlist["entries"][0],
        )
    elif mutation == "excluded":
        allowlist["entries"][0]["provider"] = "github"
        allowlist["entries"][0]["owner"] = "old-owner"
        allowlist["entries"][0]["repository"] = "old-repo"
        allowlist["entries"][0]["canonical_repository"] = (
            "github/old-owner/old-repo"
        )
    allowlist["projection_sha256"] = _sha(
        {key: value for key, value in allowlist.items() if key != "projection_sha256"}
    )
    with pytest.raises(Attempt007ValidationError):
        validate_catalog_allowlist(contract, capture, allowlist)


@pytest.mark.parametrize("mutation", ["too_few", "skip", "reorder", "duplicate"])
def test_execution_is_exact_first_two_distinct_canonical_repositories(
    mutation: str,
) -> None:
    contract = _contract()
    capture = _capture(contract)
    allowlist = _allowlist(capture)
    selected = [entry["canonical_repository"] for entry in allowlist["entries"][:2]]
    if mutation == "too_few":
        selected.pop()
    elif mutation == "skip":
        selected[1] = allowlist["entries"][2]["canonical_repository"]
    elif mutation == "reorder":
        selected.reverse()
    elif mutation == "duplicate":
        selected[1] = selected[0].upper()
    with pytest.raises(Attempt007ValidationError):
        validate_execution_selection(contract, allowlist, selected)


def test_execution_fails_when_complete_eligible_catalog_has_fewer_than_two() -> None:
    contract = _contract()
    capture = _capture(contract, count=1)
    allowlist = _allowlist(capture)
    validate_catalog_capture(contract, capture)
    validate_catalog_allowlist(contract, capture, allowlist)
    with pytest.raises(Attempt007ValidationError):
        validate_execution_selection(
            contract,
            allowlist,
            [allowlist["entries"][0]["canonical_repository"]],
        )


def test_attempt_002_identity_audit_is_nonexecutable_and_audit_only() -> None:
    audit = json.loads(ATTEMPT_002_AUDIT_PATH.read_text(encoding="utf-8"))
    validate_attempt_002_identity_audit(audit)
    assert audit["status"] == "INCONCLUSIVE"
    assert audit["execution_eligible"] is False
    assert audit["disposition"] == (
        "noncompliant-catalog-observed-before-allowlist-and-source"
    )
    assert audit["canonical_projection"]["next_attempt_exclusion_candidate"][
        "canonical_repository_count"
    ] == 20


def test_attempt_003_failure_audit_closes_empty_identity_exposure() -> None:
    audit = json.loads(ATTEMPT_003_AUDIT_PATH.read_text(encoding="utf-8"))
    validate_attempt_003_catalog_failure_audit(audit, PROJECT_ROOT)
    assert audit["execution_eligible"] is False
    projection = audit["canonical_projection"]
    assert projection["body_observation"]["content_identity_observed"] is False
    assert projection["exposure_closure"]["canonical_repositories"] == []
    assert projection["exposure_closure"][
        "newly_exposed_canonical_repository_count"
    ] == 0


def test_attempt_004_failure_audit_is_nonexecutable_and_identity_empty() -> None:
    audit = json.loads(ATTEMPT_004_AUDIT_PATH.read_text(encoding="utf-8"))
    validate_attempt_004_catalog_failure_audit(audit, PROJECT_ROOT)
    assert audit["status"] == "INCONCLUSIVE"
    assert audit["execution_eligible"] is False
    projection = audit["canonical_projection"]
    assert projection["catalog_result"]["raw_total"] == 1903
    assert projection["body_observation"]["items_iterated"] is False
    assert projection["exposure_closure"]["canonical_repositories"] == []


def test_attempt_005_ref_failure_audit_is_nonexecutable_and_exposes_known_repo() -> None:
    audit = json.loads(ATTEMPT_005_AUDIT_PATH.read_text(encoding="utf-8"))
    validate_attempt_005_ref_failure_audit(audit, PROJECT_ROOT)
    assert audit["status"] == "INCONCLUSIVE"
    assert audit["execution_eligible"] is False
    projection = audit["canonical_projection"]
    assert projection["catalog_observation"]["double_pass_complete"] is True
    assert projection["catalog_observation"]["complete_identity_set_persisted"] is False
    assert projection["identity_exposure"] == {
        "closure_complete": False,
        "known_exposed_canonical_repositories": [
            "github/coinhubmedia/melt-calculator-domains"
        ],
        "known_exposed_canonical_repository_count": 1,
        "status": (
            "full_catalog_identity_exposure_not_established_and_not_recoverable_"
            "without_forbidden_requery"
        ),
    }


def test_attempt_006_catalog_failure_audit_binds_complete_offline_capture() -> None:
    audit = json.loads(ATTEMPT_006_AUDIT_PATH.read_text(encoding="utf-8"))
    catalog = validate_attempt_006_catalog_failure_audit(audit, PROJECT_ROOT)

    assert audit["status"] == "INCONCLUSIVE"
    assert audit["execution_eligible"] is False
    assert len(catalog) == 130
    observation = audit["canonical_projection"]["catalog_observation"]
    assert observation["page_item_counts"] == [[100, 30], [100, 30]]
    assert observation["updated_at_adjacent_descent_count"] == 11
    assert audit["canonical_projection"]["zero_after_catalog"] == {
        "effect_observations": 0,
        "git_ref_requests": 0,
        "heldout_accesses": 0,
        "ollama_calls": 0,
        "online_model_calls": 0,
        "source_content_accesses": 0,
        "source_tree_accesses": 0,
    }
