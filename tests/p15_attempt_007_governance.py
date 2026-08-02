from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jsonschema import Draft202012Validator


_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures/p15_v7_minimal_online_causal"
_CONTRACT_SCHEMA = _FIXTURE_ROOT / "attempt-contract.schema.json"
_CAPTURE_SCHEMA = _FIXTURE_ROOT / "attempt-007-catalog-capture.schema.json"
_ALLOWLIST_SCHEMA = _FIXTURE_ROOT / "attempt-007-complete-allowlist.schema.json"
_SEALED_CATALOG_SCHEMA = (
    _FIXTURE_ROOT / "attempt-007-sealed-catalog-receipt.schema.json"
)
_GIT_RESOLUTION_SCHEMA = (
    _FIXTURE_ROOT / "attempt-007-git-resolution-receipt.schema.json"
)
_GIT_ALLOWLIST_SCHEMA = (
    _FIXTURE_ROOT / "attempt-007-git-complete-allowlist.schema.json"
)
_ATTEMPT_006_SEALED_CATALOG_SCHEMA = (
    _FIXTURE_ROOT / "attempt-006-sealed-catalog-receipt.schema.json"
)
_ATTEMPT_002_AUDIT_SCHEMA = (
    _FIXTURE_ROOT / "attempt-002-identity-query-audit.schema.json"
)

_SEARCH_ENDPOINT = "https://api.github.com/search/repositories"
_API_VERSION = "2022-11-28"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": _API_VERSION,
}
_GIT_TRANSPORT_CONTRACT = {
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
_ZERO_STATE_FIELDS = (
    "catalog_requests",
    "ref_requests",
    "source_accesses",
    "planner_calls",
    "embedding_calls",
    "control_executions",
    "treatment_executions",
    "effect_observations",
    "online_model_calls",
    "ollama_calls",
    "held_out_accesses",
)
_ITEM_FIELDS = {
    "provider",
    "owner",
    "repository",
    "visibility",
    "language",
    "default_branch",
    "updated_at",
}
_ALLOWLIST_ENTRY_FIELDS = {
    "ordinal",
    "provider",
    "owner",
    "repository",
    "default_branch",
    "immutable_revision",
    "canonical_repository",
}


class Attempt007ValidationError(ValueError):
    pass


def _validate_schema(instance: dict[str, Any], path: Path, label: str) -> None:
    schema = json.loads(path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path) or "<root>"
        raise Attempt007ValidationError(
            f"{label} schema violation at {location}: {error.message}"
        )


def _canonical_sha256(value: object) -> str:
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


def _repository_key(provider: str, owner: str, repository: str) -> str:
    return "/".join(
        (_normalize(provider), _normalize(owner), _normalize(repository))
    )


def _item_repository_key(item: dict[str, Any]) -> str:
    return _repository_key(
        item["provider"], item["owner"], item["repository"]
    )


def _pre_ref_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _normalize(item["provider"]),
        _normalize(item["owner"]),
        _normalize(item["repository"]),
    )


def _identity_sha256(item: dict[str, Any], revision: str) -> str:
    return _canonical_sha256(
        {
            "provider": item["provider"],
            "owner": item["owner"],
            "repository": item["repository"],
            "default_branch": item["default_branch"],
            "immutable_revision": revision,
        }
    )


def _post_ref_sort_key(
    item: dict[str, Any], revision: str
) -> tuple[str, str, str, str, str]:
    return (
        *_pre_ref_sort_key(item),
        revision.lower(),
        _identity_sha256(item, revision).lower(),
    )


def _projection_without_hash(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "projection_sha256"}


def _validate_projection(value: dict[str, Any], label: str) -> None:
    if value.get("projection_sha256") != _canonical_sha256(
        _projection_without_hash(value)
    ):
        raise Attempt007ValidationError(f"{label} projection hash mismatch")


def _contract_projection_sha256(contract: dict[str, Any]) -> str:
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
    return _canonical_sha256(projection)


def _utc_literal(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc_rfc3339(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        value,
    ):
        raise Attempt007ValidationError(f"{label} must be strict UTC RFC3339")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise Attempt007ValidationError(
            f"{label} must be strict UTC RFC3339"
        ) from error
    if _utc_literal(parsed) != value:
        raise Attempt007ValidationError(f"{label} must be strict UTC RFC3339")
    return parsed


def _parse_rfc1123(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise Attempt007ValidationError(f"{label} Date must be strict RFC1123")
    try:
        parsed = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise Attempt007ValidationError(
            f"{label} Date must be strict RFC1123"
        ) from error
    if parsed.strftime("%a, %d %b %Y %H:%M:%S GMT") != value:
        raise Attempt007ValidationError(f"{label} Date must be strict RFC1123")
    return parsed


def _expected_window(frozen_at: str) -> tuple[str, str]:
    utc = _parse_utc_rfc3339(frozen_at, "contract freeze timestamp")
    floored = utc.replace(minute=0, second=0, microsecond=0)
    start = floored - timedelta(days=28)
    end = start + timedelta(minutes=5) - timedelta(seconds=1)
    return _utc_literal(start), _utc_literal(end)


def validate_pre_catalog_contract(contract: dict[str, Any]) -> None:
    _validate_schema(contract, _CONTRACT_SCHEMA, "attempt-007 contract")
    if contract.get("schema_version") != "p15-v7-minimal-online-causal-attempt-v7":
        raise Attempt007ValidationError("attempt-007 contract schema mismatch")
    if contract.get("attempt_id") != "p15-v7-attempt-007":
        raise Attempt007ValidationError("attempt-007 id mismatch")
    if contract.get("execution_role") != "two_repository_acceptance_draft":
        raise Attempt007ValidationError("attempt-007 execution role mismatch")
    if contract.get("status") != "DRAFT":
        raise Attempt007ValidationError("attempt-007 status mismatch")
    binding = contract.get("contract_binding", {})
    if binding.get("projection_algorithm") != (
        "sha256_of_canonical_contract_with_empty_catalog_allowlist_and_approval_receipts"
    ):
        raise Attempt007ValidationError("attempt-007 projection algorithm mismatch")
    if binding.get("projection_sha256") != _contract_projection_sha256(contract):
        raise Attempt007ValidationError("attempt-007 contract projection mismatch")

    catalog = contract.get("catalog_contract", {})
    start, end = _expected_window(contract["contract_frozen_at_utc"])
    expected_query = f"language:Python is:public created:{start}..{end}"
    expected_catalog = {
        "provider": "github",
        "transport": "GitHub REST",
        "api_version": _API_VERSION,
        "window_derivation": (
            "window_start=floor_utc_hour(contract_frozen_at_utc)-P28D;"
            "duration=PT5M;window_end=window_start+PT5M-PT1S"
        ),
        "window_duration": "PT5M",
        "window_start_utc": start,
        "window_end_utc": end,
        "prior_universe_exclusion": {
            "rule": "closed_interval_disjoint_from_attempt_005_catalog_window",
            "attempt_id": "p15-v7-attempt-005",
            "window_start_utc": "2026-07-04T06:00:00Z",
            "window_end_utc": "2026-07-04T06:04:59Z",
        },
        "search_endpoint": _SEARCH_ENDPOINT,
        "q": expected_query,
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
            "append_only_full_ordered_catalog_and_page_evidence_sealed_before_refs"
        ),
        "max_server_date_lag_seconds": 5,
        "page_attempts": 1,
        "request_headers": _HEADERS,
        "ref_resolution_protocol": _GIT_TRANSPORT_CONTRACT,
        "resolution_receipt_rule": (
            "append_only_all_attempts_for_canonical_prefix2_only"
        ),
        "failure_policy": (
            "resolution_exhaustion_inconclusive_no_third_repository_or_"
            "substitution"
        ),
    }
    if catalog != expected_catalog:
        raise Attempt007ValidationError("catalog boundary is not exactly frozen")
    offline_source = contract.get("offline_catalog_source")
    if (
        not isinstance(offline_source, dict)
        or set(offline_source)
        != {
            "mode",
            "attempt_id",
            "archived_contract_path",
            "archived_contract_sha256",
            "archived_contract_projection_sha256",
            "audit_path",
            "audit_sha256",
            "capture_path",
            "capture_sha256",
            "capture_projection_sha256",
            "catalog_requests_exact",
        }
        or offline_source.get("mode")
        != "immutable_attempt_006_capture_no_requery"
        or offline_source.get("attempt_id") != "p15-v7-attempt-006"
        or offline_source.get("archived_contract_path")
        != "audit/p15-v7-attempt-006-contract.json"
        or offline_source.get("audit_path")
        != "audit/attempt-006-catalog-validation-failure-audit.json"
        or offline_source.get("capture_path")
        != "audit/attempt-006-catalog-validation-failure-capture.json"
        or offline_source.get("catalog_requests_exact") != 0
        or offline_source.get("archived_contract_sha256")
        != "ba8e5b5a48b8d3f5e5699db033c931eab958f851c7075d8a7d5b6354e980341b"
        or offline_source.get("archived_contract_projection_sha256")
        != "74ac868812404ca83b23eab82571b264cd9e4d8a822202a77276cae2bc3e3afc"
        or offline_source.get("audit_sha256")
        != "d055aed2a4b9742a4812df3be1875ff2589c1dea94284b990b4a27bf604d2691"
        or offline_source.get("capture_sha256")
        != "c7ec58c12b3acafe8f3bd92598e28e51b47c8b70680e2719a722be5c2ae251db"
        or offline_source.get("capture_projection_sha256")
        != "5974cb5b74708608a4ecc8b328367c025cb7f9b117ba78961edb67e88cceab72"
    ):
        raise Attempt007ValidationError("offline catalog source is not exactly frozen")
    if contract.get("catalog_ordering") != {
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
    }:
        raise Attempt007ValidationError("catalog ordering is not exactly frozen")
    prior = catalog["prior_universe_exclusion"]
    window_start = _parse_utc_rfc3339(
        catalog["window_start_utc"], "catalog window start"
    )
    window_end = _parse_utc_rfc3339(
        catalog["window_end_utc"], "catalog window end"
    )
    prior_start = _parse_utc_rfc3339(
        prior["window_start_utc"], "attempt-005 catalog window start"
    )
    prior_end = _parse_utc_rfc3339(
        prior["window_end_utc"], "attempt-005 catalog window end"
    )
    if not (window_end < prior_start or window_start > prior_end):
        raise Attempt007ValidationError(
            "catalog window overlaps attempt-005 catalog universe"
        )

    exclusion = contract.get("exclusion_projection", {})
    repositories = exclusion.get("canonical_repositories")
    if (
        exclusion.get("normalization")
        != "provider_owner_repository_unicode_nfkc_casefold"
        or not isinstance(repositories, list)
        or exclusion.get("count") != 21
        or len(repositories) != 21
        or len({_normalize(item) for item in repositories}) != 21
    ):
        raise Attempt007ValidationError("attempt-007 exclusion union must contain 21")
    if exclusion.get("canonical_repository_list_algorithm") != (
        "sha256_of_canonical_json_canonical_repositories_array_"
        "sort_keys_compact_ascii"
    ) or exclusion.get("canonical_repository_list_sha256") != _canonical_sha256(
        repositories
    ):
        raise Attempt007ValidationError(
            "attempt-007 exclusion repository list hash mismatch"
        )
    if exclusion.get("projection_algorithm") != (
        "sha256_of_canonical_json_normalization_canonical_repositories_"
        "count_sort_keys_compact_ascii"
    ) or exclusion.get("projection_sha256") != _canonical_sha256(
        {
            "normalization": exclusion["normalization"],
            "canonical_repositories": repositories,
            "count": exclusion["count"],
        }
    ):
        raise Attempt007ValidationError(
            "attempt-007 exclusion object projection hash mismatch"
        )
    source_audits = exclusion.get("source_audits")
    if (
        not isinstance(source_audits, list)
        or len(source_audits) != 6
        or [item.get("attempt_id") for item in source_audits]
        != [
            "p15-v7-attempt-001",
            "p15-v7-attempt-002",
            "p15-v7-attempt-003",
            "p15-v7-attempt-004",
            "p15-v7-attempt-005",
            "p15-v7-attempt-006",
        ]
        or any(
            set(item) != {
                "attempt_id",
                "path",
                "sha256",
                "audit_only_hashes",
            }
            or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
            or item.get("audit_only_hashes") is not True
            for item in source_audits
        )
    ):
        raise Attempt007ValidationError("superseded audit bindings are incomplete")
    if contract.get("eligibility") != {
        "only": [
            "public",
            "language_python",
            "default_branch_commit_resolved",
            "not_excluded",
        ]
    }:
        raise Attempt007ValidationError("eligibility filters are not exactly frozen")
    if contract.get("allowlist_rule") != {
        "contents": "resolved_eligible_canonical_prefix2_only",
        "order": "frozen_post_ref_five_tuple_ascending",
    }:
        raise Attempt007ValidationError("allowlist rule is not exactly frozen")
    if contract.get("execution_rule") != {
        "repository_count": 2,
        "selection": "canonical_catalog_prefix2",
        "distinct_canonical_repositories": True,
        "fallback_beyond_prefix_forbidden": True,
        "resolution_attempts_per_repository": 3,
        "resolution_timeout_seconds": 30,
        "resolution_backoff_seconds": [0, 2, 5],
        "resolution_exhaustion_disposition": "INCONCLUSIVE",
    }:
        raise Attempt007ValidationError("execution rule is not exactly frozen")

    if contract.get("execution_eligible") is not False:
        raise Attempt007ValidationError("draft must not be execution eligible")
    if contract.get("user_approval_required") is not True:
        raise Attempt007ValidationError("draft must require user approval")
    if contract.get("approval_receipt") != {
        "received": False,
        "path": "",
        "sha256": "",
    }:
        raise Attempt007ValidationError("draft approval receipt must be empty")
    if contract.get("approval_rule") != {
        "scope": (
            "single_receipt_authorizes_two_refs_then_source_then_fresh_then_"
            "if_fresh_passes_heldout_and_release"
        ),
        "reapproval_triggers": [
            "plan_field_change",
            "threshold_change",
            "query_change",
            "model_change",
            "case_rule_change",
        ],
    }:
        raise Attempt007ValidationError("approval rule is not exactly frozen")

    catalog_receipt = contract.get("catalog_receipt")
    if (
        not isinstance(catalog_receipt, dict)
        or catalog_receipt.get("received") is not True
        or catalog_receipt.get("path")
        != "attempt-007-sealed-catalog-receipt.json"
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(catalog_receipt.get("sha256", ""))
        )
    ):
        raise Attempt007ValidationError("catalog receipt must be sealed before refs")
    if contract.get("future_allowlist") != {
        "received": False,
        "path": "",
        "sha256": "",
        "identity_selected": False,
    }:
        raise Attempt007ValidationError("allowlist receipt must be empty")
    corpus = contract.get("corpus", {})
    if corpus.get("fresh_repositories") != [] or corpus.get("fresh_cases") != []:
        raise Attempt007ValidationError("attempt-007 corpus must be empty")
    if corpus.get("fixed_denominators") != {
        "repositories": 2,
        "cases": 12,
        "efficacy_targets": 8,
        "guard_cases": 4,
        "planner_samples": 24,
        "local_arm_replays": 96,
    } or corpus.get("per_repository") != {
        "efficacy_cases": 4,
        "guard_cases": 2,
    }:
        raise Attempt007ValidationError("corpus denominators are not exactly frozen")
    if corpus.get("selection_contract") != {
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
    }:
        raise Attempt007ValidationError("corpus selection contract is not exact")
    if contract.get("sampling", {}).get("expanded_schedule") != []:
        raise Attempt007ValidationError("attempt-007 schedule must be empty")
    zero_state = contract.get("zero_state", {})
    if set(zero_state) != set(_ZERO_STATE_FIELDS) or any(
        zero_state[field] != 0 for field in _ZERO_STATE_FIELDS
    ):
        raise Attempt007ValidationError("attempt-007 zero state is not zero")


def _validate_search_request(
    contract: dict[str, Any],
    request: dict[str, Any],
    page_number: int,
    frozen_at: datetime,
) -> datetime:
    _validate_projection(request, "catalog request")
    issued_at = _parse_utc_rfc3339(
        request.get("issued_at_utc"), "catalog request issued_at_utc"
    )
    if issued_at < frozen_at:
        raise Attempt007ValidationError(
            "catalog request issued_at_utc predates contract freeze"
        )
    catalog = contract["catalog_contract"]
    if _projection_without_hash(request) != {
        "method": "GET",
        "endpoint": catalog["search_endpoint"],
        "issued_at_utc": request.get("issued_at_utc"),
        "headers": catalog["request_headers"],
        "params": {
            "q": catalog["q"],
            "sort": catalog["sort"],
            "order": catalog["order"],
            "per_page": catalog["per_page"],
            "page": page_number,
        },
        "attempt_count": 1,
    }:
        raise Attempt007ValidationError("catalog request differs from frozen request")
    return issued_at


def _validate_response_headers(
    response: dict[str, Any],
    label: str,
    frozen_at: datetime,
    issued_at: datetime,
    *,
    nullable_etag: bool = False,
    max_server_date_lag_seconds: int = 0,
) -> datetime:
    headers = response.get("headers")
    if not isinstance(headers, dict) or not headers.get("Date"):
        raise Attempt007ValidationError(f"{label} Date is required")
    if nullable_etag:
        etag_present = headers.get("etag_present")
        etag = headers.get("etag")
        if (
            etag_present is True
            and (
                not isinstance(etag, str)
                or etag.strip().casefold() == "null"
            )
        ) or (
            etag_present is False and etag is not None
        ):
            raise Attempt007ValidationError(
                f"{label} ETag presence and value mismatch"
            )
    elif not headers.get("ETag"):
        raise Attempt007ValidationError(f"{label} ETag is required")
    response_date = _parse_rfc1123(headers["Date"], label)
    if response_date < frozen_at:
        raise Attempt007ValidationError(f"{label} Date predates contract freeze")
    if response_date < issued_at - timedelta(
        seconds=max_server_date_lag_seconds
    ):
        raise Attempt007ValidationError(f"{label} Date predates request")
    return response_date


def _validate_catalog_pass(
    contract: dict[str, Any],
    catalog_pass: dict[str, Any],
    pass_number: int,
    frozen_at: datetime,
    previous_issued_at: datetime | None,
    *,
    max_server_date_lag_seconds: int = 0,
) -> tuple[int, str, list[dict[str, Any]], datetime | None]:
    if catalog_pass.get("pass_number") != pass_number:
        raise Attempt007ValidationError("catalog pass number mismatch")
    total = catalog_pass.get("total_count")
    maximum = contract["catalog_contract"]["max_total_count"]
    if not isinstance(total, int) or total < 0 or total > maximum:
        raise Attempt007ValidationError("catalog total exceeds frozen maximum")
    per_page = contract["catalog_contract"]["per_page"]
    expected_page_count = math.ceil(total / per_page)
    pages = catalog_pass.get("pages")
    if not isinstance(pages, list) or len(pages) != expected_page_count:
        raise Attempt007ValidationError("catalog traversal has missing or extra pages")

    repositories: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous_response_date: datetime | None = None
    for page_number, page in enumerate(pages, start=1):
        if page.get("page") != page_number:
            raise Attempt007ValidationError("catalog page numbers must be contiguous")
        request = page.get("request")
        response = page.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise Attempt007ValidationError("catalog page capture is incomplete")
        issued_at = _validate_search_request(
            contract, request, page_number, frozen_at
        )
        if previous_issued_at is not None and issued_at < previous_issued_at:
            raise Attempt007ValidationError(
                "catalog request timestamps must be nondecreasing in pass/page order"
            )
        previous_issued_at = issued_at
        _validate_projection(response, "catalog response")
        if response.get("status") != 200:
            raise Attempt007ValidationError("catalog response must be HTTP 200")
        response_date = _validate_response_headers(
            response,
            "catalog response",
            frozen_at,
            issued_at,
            nullable_etag=True,
            max_server_date_lag_seconds=max_server_date_lag_seconds,
        )
        if (
            previous_response_date is not None
            and response_date < previous_response_date
        ):
            raise Attempt007ValidationError(
                "catalog response Dates must be nondecreasing in pass/page order"
            )
        previous_response_date = response_date
        if response.get("total_count") != total:
            raise Attempt007ValidationError("catalog total drifted within pass")
        if response.get("incomplete_results") is not False:
            raise Attempt007ValidationError("catalog response is incomplete")
        items = response.get("items")
        expected_count = min(per_page, total - (page_number - 1) * per_page)
        if not isinstance(items, list) or len(items) != expected_count:
            raise Attempt007ValidationError("catalog contains a short or long page")
        for item in items:
            if not isinstance(item, dict) or set(item) != _ITEM_FIELDS:
                raise Attempt007ValidationError("catalog repository fields are not exact")
            key = _item_repository_key(item)
            if key in seen:
                raise Attempt007ValidationError("catalog contains duplicate repository")
            seen.add(key)
            repositories.append(item)
    if len(repositories) != total:
        raise Attempt007ValidationError("catalog traversal total is incomplete")
    expected_projection = _canonical_sha256(
        {"total_count": total, "repositories": repositories}
    )
    if catalog_pass.get("canonical_projection_sha256") != expected_projection:
        raise Attempt007ValidationError("catalog pass projection hash mismatch")
    return total, expected_projection, repositories, previous_issued_at


def _validate_ref_resolutions(
    contract: dict[str, Any],
    capture: dict[str, Any],
    repositories: list[dict[str, Any]],
    frozen_at: datetime,
) -> None:
    resolutions = capture.get("ref_resolutions")
    expected_by_key = {_item_repository_key(item): item for item in repositories}
    if not isinstance(resolutions, list) or len(resolutions) != len(repositories):
        raise Attempt007ValidationError("ref resolution set is missing or extra")
    seen: set[str] = set()
    for resolution in resolutions:
        key = resolution.get("canonical_repository")
        if key not in expected_by_key or key in seen:
            raise Attempt007ValidationError("ref resolution set is missing or extra")
        seen.add(key)
        repository = expected_by_key[key]
        if resolution.get("default_branch") != repository["default_branch"]:
            raise Attempt007ValidationError("ref default branch mismatch")
        request = resolution.get("request")
        response = resolution.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise Attempt007ValidationError("ref capture is incomplete")
        _validate_projection(request, "ref request")
        issued_at = _parse_utc_rfc3339(
            request.get("issued_at_utc"), "ref request issued_at_utc"
        )
        if issued_at < frozen_at:
            raise Attempt007ValidationError(
                "ref request issued_at_utc predates contract freeze"
            )
        branch = quote(repository["default_branch"], safe="")
        endpoint = (
            "https://api.github.com/repos/"
            f"{repository['owner']}/{repository['repository']}/git/ref/heads/{branch}"
        )
        if _projection_without_hash(request) != {
            "method": "GET",
            "endpoint": endpoint,
            "issued_at_utc": request.get("issued_at_utc"),
            "headers": contract["catalog_contract"]["request_headers"],
            "attempt_count": 1,
        }:
            raise Attempt007ValidationError("ref request differs from exact endpoint")
        _validate_projection(response, "ref response")
        if response.get("status") != 200:
            raise Attempt007ValidationError("ref response must be HTTP 200")
        _validate_response_headers(response, "ref response", frozen_at, issued_at)
        ref_object = response.get("object")
        if (
            not isinstance(ref_object, dict)
            or set(ref_object) != {"type", "sha"}
            or ref_object.get("type") != "commit"
            or not re.fullmatch(r"[0-9a-f]{40}", str(ref_object.get("sha", "")))
        ):
            raise Attempt007ValidationError(
                "default branch ref must resolve to a 40-hex commit"
            )
    if seen != set(expected_by_key):
        raise Attempt007ValidationError("ref resolution set is missing or extra")


def validate_catalog_capture(
    contract: dict[str, Any], capture: dict[str, Any]
) -> None:
    validate_pre_catalog_contract(contract)
    _validate_schema(capture, _CAPTURE_SCHEMA, "catalog capture")
    if capture.get("schema_version") != "p15-v7-attempt-007-catalog-capture-v1":
        raise Attempt007ValidationError("catalog capture schema mismatch")
    if capture.get("attempt_id") != contract["attempt_id"]:
        raise Attempt007ValidationError("catalog capture attempt mismatch")
    if (
        capture.get("contract_projection_sha256")
        != contract["contract_binding"]["projection_sha256"]
    ):
        raise Attempt007ValidationError("catalog capture contract binding mismatch")
    passes = capture.get("passes")
    if not isinstance(passes, list) or len(passes) != 2:
        raise Attempt007ValidationError("catalog requires exactly two full passes")
    frozen_at = _parse_utc_rfc3339(
        contract["contract_frozen_at_utc"], "contract freeze timestamp"
    )
    max_lag = contract["catalog_contract"]["max_server_date_lag_seconds"]
    first = _validate_catalog_pass(
        contract,
        passes[0],
        1,
        frozen_at,
        None,
        max_server_date_lag_seconds=max_lag,
    )
    second = _validate_catalog_pass(
        contract,
        passes[1],
        2,
        frozen_at,
        first[3],
        max_server_date_lag_seconds=max_lag,
    )
    if first[:2] != second[:2] or first[2] != second[2]:
        raise Attempt007ValidationError("catalog double-pass projection drift")
    _validate_ref_resolutions(contract, capture, first[2], frozen_at)


def validate_sealed_catalog_receipt(
    contract: dict[str, Any], receipt: dict[str, Any]
) -> list[dict[str, Any]]:
    validate_pre_catalog_contract(contract)
    _validate_schema(receipt, _SEALED_CATALOG_SCHEMA, "sealed catalog receipt")
    if set(receipt) != {
        "schema_version",
        "attempt_id",
        "contract_projection_sha256",
        "source_capture_sha256",
        "storage_mode",
        "sealed",
        "sealed_at_utc",
        "passes",
        "ordered_catalog_count",
        "ordered_catalog",
        "ordered_catalog_sha256",
        "projection_sha256",
    }:
        raise Attempt007ValidationError("sealed catalog receipt fields are not exact")
    _validate_projection(receipt, "sealed catalog receipt")
    if (
        receipt.get("schema_version")
        != "p15-v7-attempt-007-sealed-catalog-receipt-v1"
        or receipt.get("attempt_id") != contract["attempt_id"]
        or receipt.get("contract_projection_sha256")
        != contract["contract_binding"]["projection_sha256"]
        or receipt.get("source_capture_sha256")
        != contract["offline_catalog_source"]["capture_sha256"]
        or receipt.get("storage_mode") != "append_only"
        or receipt.get("sealed") is not True
    ):
        raise Attempt007ValidationError("catalog receipt is not sealed and bound")
    frozen_at = _parse_utc_rfc3339(
        contract["contract_frozen_at_utc"], "contract freeze timestamp"
    )
    sealed_at = _parse_utc_rfc3339(
        receipt.get("sealed_at_utc"), "catalog receipt sealed_at_utc"
    )
    if sealed_at < frozen_at:
        raise Attempt007ValidationError("catalog receipt predates contract freeze")
    archived_contract = json.loads(
        (
            _FIXTURE_ROOT
            / contract["offline_catalog_source"]["archived_contract_path"]
        ).read_text(encoding="utf-8")
    )
    evidence_frozen_at = _parse_utc_rfc3339(
        archived_contract["contract_frozen_at_utc"],
        "offline source contract freeze timestamp",
    )
    passes = receipt.get("passes")
    if not isinstance(passes, list) or len(passes) != 2:
        raise Attempt007ValidationError("catalog receipt requires exactly two passes")
    max_lag = contract["catalog_contract"]["max_server_date_lag_seconds"]
    first = _validate_catalog_pass(
        contract,
        passes[0],
        1,
        evidence_frozen_at,
        None,
        max_server_date_lag_seconds=max_lag,
    )
    second = _validate_catalog_pass(
        contract,
        passes[1],
        2,
        evidence_frozen_at,
        first[3],
        max_server_date_lag_seconds=max_lag,
    )
    if first[:2] != second[:2] or first[2] != second[2]:
        raise Attempt007ValidationError("sealed catalog double-pass projection drift")
    repositories = sorted(first[2], key=_pre_ref_sort_key)
    if (
        receipt.get("ordered_catalog_count") != len(repositories)
        or receipt.get("ordered_catalog") != repositories
        or receipt.get("ordered_catalog_sha256")
        != _canonical_sha256(repositories)
    ):
        raise Attempt007ValidationError("sealed ordered catalog is incomplete")
    return repositories


def run_bounded_prefix2_resolution(
    contract: dict[str, Any],
    catalog_receipt: dict[str, Any],
    *,
    run_command: Any,
    sleep: Any,
    user_approved: bool,
) -> dict[str, Any]:
    repositories = validate_sealed_catalog_receipt(contract, catalog_receipt)
    if not user_approved:
        raise Attempt007ValidationError("explicit user approval is required")
    selected = repositories[:2]
    if len(selected) != 2 or len(
        {_item_repository_key(item) for item in selected}
    ) != 2:
        raise Attempt007ValidationError(
            "canonical catalog prefix must contain two distinct repositories"
        )

    entries: list[dict[str, Any]] = []
    for ordinal, repository in enumerate(selected, start=1):
        exact_ref = f"refs/heads/{repository['default_branch']}"
        attempts: list[dict[str, Any]] = []
        revision: str | None = None
        for attempt_number, backoff_seconds in enumerate((0, 2, 5), start=1):
            if backoff_seconds:
                sleep(backoff_seconds)
            request = {
                "argv": [
                    "git",
                    "-c",
                    "credential.helper=",
                    "ls-remote",
                    "--refs",
                    (
                        "https://github.com/"
                        f"{repository['owner']}/{repository['repository']}.git"
                    ),
                    exact_ref,
                ],
                "environment": _GIT_TRANSPORT_CONTRACT["environment"],
                "timeout_seconds": 30,
                "attempt_count": attempt_number,
                "shell": False,
                "backoff_seconds": backoff_seconds,
            }
            observed = run_command(request)
            stdout = observed.get("stdout", "")
            match = re.fullmatch(r"([0-9a-f]{40})\t(.+)\n?", stdout)
            attempts.append(
                {
                    "attempt_number": attempt_number,
                    "request": request,
                    "observation": observed,
                }
            )
            if (
                observed.get("transport_status") == "exited"
                and observed.get("exit_code") == 0
                and match is not None
                and match.group(2) == exact_ref
            ):
                revision = match.group(1)
                break
        entries.append(
            {
                "ordinal": ordinal,
                "canonical_repository": _item_repository_key(repository),
                "attempts": attempts,
                "resolution": {
                    "status": "resolved" if revision is not None else "unresolved",
                    "immutable_revision": revision,
                },
            }
        )
        if revision is None:
            return {
                "status": "INCONCLUSIVE",
                "selected_count": 2,
                "entries": entries,
            }
    return {
        "status": "RESOLVED_PREFIX2",
        "selected_count": 2,
        "entries": entries,
    }


def validate_git_resolution_receipt(
    contract: dict[str, Any],
    catalog_receipt: dict[str, Any],
    resolution_receipt: dict[str, Any],
) -> dict[str, str]:
    repositories = validate_sealed_catalog_receipt(contract, catalog_receipt)
    _validate_schema(
        resolution_receipt, _GIT_RESOLUTION_SCHEMA, "git resolution receipt"
    )
    if set(resolution_receipt) != {
        "schema_version",
        "attempt_id",
        "contract_projection_sha256",
        "catalog_receipt_sha256",
        "storage_mode",
        "transport_contract",
        "entries",
        "entries_count",
        "entries_tail_sha256",
        "projection_sha256",
    }:
        raise Attempt007ValidationError("git resolution receipt fields are not exact")
    _validate_projection(resolution_receipt, "git resolution receipt")
    if (
        resolution_receipt.get("schema_version")
        != "p15-v7-attempt-007-git-resolution-receipt-v1"
        or resolution_receipt.get("attempt_id") != contract["attempt_id"]
        or resolution_receipt.get("contract_projection_sha256")
        != contract["contract_binding"]["projection_sha256"]
        or resolution_receipt.get("catalog_receipt_sha256")
        != _canonical_sha256(catalog_receipt)
        or resolution_receipt.get("storage_mode") != "append_only"
        or resolution_receipt.get("transport_contract") != _GIT_TRANSPORT_CONTRACT
    ):
        raise Attempt007ValidationError("git resolution receipt binding mismatch")
    entries = resolution_receipt.get("entries")
    if (
        not isinstance(entries, list)
        or len(repositories) < 2
        or resolution_receipt.get("entries_count") != 2
        or len(entries) != 2
    ):
        raise Attempt007ValidationError("git resolution receipt must equal prefix2")

    resolved: dict[str, str] = {}
    previous = "0" * 64
    global_failure: str | None = None
    for ordinal, (repository, entry) in enumerate(
        zip(repositories[:2], entries, strict=True), start=1
    ):
        if not isinstance(entry, dict) or set(entry) != {
            "ordinal",
            "canonical_repository",
            "owner",
            "repository",
            "default_branch",
            "request",
            "observation",
            "resolution",
            "previous_entry_sha256",
            "entry_sha256",
        }:
            raise Attempt007ValidationError("git resolution entry fields are not exact")
        expected_key = _item_repository_key(repository)
        if (
            entry.get("ordinal") != ordinal
            or entry.get("canonical_repository") != expected_key
            or entry.get("owner") != repository["owner"]
            or entry.get("repository") != repository["repository"]
            or entry.get("default_branch") != repository["default_branch"]
        ):
            raise Attempt007ValidationError(
                "git resolution entries must equal canonical catalog prefix2"
            )
        if entry.get("previous_entry_sha256") != previous or entry.get(
            "entry_sha256"
        ) != _canonical_sha256(
            {key: value for key, value in entry.items() if key != "entry_sha256"}
        ):
            raise Attempt007ValidationError("git resolution append-only chain mismatch")
        previous = entry["entry_sha256"]

        exact_ref = f"refs/heads/{repository['default_branch']}"
        expected_request = {
            "argv": [
                "git",
                "-c",
                "credential.helper=",
                "ls-remote",
                "--refs",
                (
                    "https://github.com/"
                    f"{repository['owner']}/{repository['repository']}.git"
                ),
                exact_ref,
            ],
            "environment": _GIT_TRANSPORT_CONTRACT["environment"],
            "timeout_seconds": 30,
            "attempt_count": 1,
            "shell": False,
        }
        if entry.get("request") != expected_request:
            raise Attempt007ValidationError("git ls-remote request is not exact")
        observation = entry.get("observation")
        if not isinstance(observation, dict) or set(observation) != {
            "transport_status",
            "exit_code",
            "stdout",
            "stdout_sha256",
            "stderr_sha256",
        }:
            raise Attempt007ValidationError("git observation fields are not exact")
        stdout = observation.get("stdout")
        if not isinstance(stdout, str) or observation.get(
            "stdout_sha256"
        ) != hashlib.sha256(stdout.encode("utf-8")).hexdigest() or not re.fullmatch(
            r"[0-9a-f]{64}", str(observation.get("stderr_sha256", ""))
        ):
            raise Attempt007ValidationError("git observation hash mismatch")

        transport_status = observation.get("transport_status")
        exit_code = observation.get("exit_code")
        if transport_status in {"spawn_error", "timeout"}:
            expected_resolution = {
                "status": "global_failure",
                "reason": transport_status,
                "immutable_revision": None,
            }
            if exit_code is not None:
                raise Attempt007ValidationError("global transport failure has exit code")
            global_failure = transport_status
        elif transport_status != "exited" or not isinstance(exit_code, int):
            raise Attempt007ValidationError("git transport status is invalid")
        elif exit_code != 0:
            expected_resolution = {
                "status": "unresolved",
                "reason": "process_nonzero",
                "immutable_revision": None,
            }
        else:
            lines = stdout.splitlines()
            if not lines:
                expected_resolution = {
                    "status": "unresolved",
                    "reason": "empty_stdout",
                    "immutable_revision": None,
                }
            elif len(lines) != 1:
                expected_resolution = {
                    "status": "unresolved",
                    "reason": "multiple_lines",
                    "immutable_revision": None,
                }
            else:
                match = re.fullmatch(r"([0-9a-f]{40})\t(.+)", lines[0])
                if match is None:
                    expected_resolution = {
                        "status": "unresolved",
                        "reason": "malformed_stdout",
                        "immutable_revision": None,
                    }
                elif match.group(2) != exact_ref:
                    expected_resolution = {
                        "status": "unresolved",
                        "reason": "wrong_ref",
                        "immutable_revision": None,
                    }
                else:
                    expected_resolution = {
                        "status": "resolved",
                        "reason": "exact_single_ref",
                        "immutable_revision": match.group(1),
                    }
                    resolved[expected_key] = match.group(1)
        if entry.get("resolution") != expected_resolution:
            raise Attempt007ValidationError("git resolution classification mismatch")
    if resolution_receipt.get("entries_tail_sha256") != previous:
        raise Attempt007ValidationError("git resolution tail hash mismatch")
    if global_failure is not None:
        raise Attempt007ValidationError(
            f"global git transport failure: {global_failure}"
        )
    return resolved


def validate_git_catalog_allowlist(
    contract: dict[str, Any],
    catalog_receipt: dict[str, Any],
    resolution_receipt: dict[str, Any],
    allowlist: dict[str, Any],
) -> None:
    resolved = validate_git_resolution_receipt(
        contract, catalog_receipt, resolution_receipt
    )
    _validate_schema(allowlist, _GIT_ALLOWLIST_SCHEMA, "git catalog allowlist")
    _validate_projection(allowlist, "git catalog allowlist")
    if (
        allowlist.get("attempt_id") != contract["attempt_id"]
        or allowlist.get("catalog_receipt_sha256")
        != _canonical_sha256(catalog_receipt)
        or allowlist.get("resolution_receipt_sha256")
        != _canonical_sha256(resolution_receipt)
    ):
        raise Attempt007ValidationError("git allowlist receipt binding mismatch")
    exclusions = {
        _normalize(item)
        for item in contract["exclusion_projection"]["canonical_repositories"]
    }
    eligible = [
        item
        for item in catalog_receipt["ordered_catalog"]
        if item["visibility"] == "public"
        and item["language"] == "Python"
        and _item_repository_key(item) in resolved
        and _item_repository_key(item) not in exclusions
    ]
    eligible.sort(
        key=lambda item: _post_ref_sort_key(
            item, resolved[_item_repository_key(item)]
        )
    )
    expected = [
        {
            "ordinal": ordinal,
            "provider": item["provider"],
            "owner": item["owner"],
            "repository": item["repository"],
            "default_branch": item["default_branch"],
            "immutable_revision": resolved[_item_repository_key(item)],
            "identity_sha256": _identity_sha256(
                item, resolved[_item_repository_key(item)]
            ),
            "canonical_repository": _item_repository_key(item),
        }
        for ordinal, item in enumerate(eligible, start=1)
    ]
    if allowlist.get("entries") != expected:
        raise Attempt007ValidationError(
            "git allowlist must equal complete resolved eligible catalog"
        )


def _resolved_revisions(capture: dict[str, Any]) -> dict[str, str]:
    return {
        resolution["canonical_repository"]: resolution["response"]["object"][
            "sha"
        ]
        for resolution in capture["ref_resolutions"]
    }


def _expected_allowlist_entries(
    contract: dict[str, Any], capture: dict[str, Any]
) -> list[dict[str, Any]]:
    exclusions = {
        _normalize(item)
        for item in contract["exclusion_projection"]["canonical_repositories"]
    }
    items = [
        item
        for page in capture["passes"][0]["pages"]
        for item in page["response"]["items"]
    ]
    revisions = _resolved_revisions(capture)
    eligible = [
        item
        for item in items
        if item["visibility"] == "public"
        and item["language"] == "Python"
        and _item_repository_key(item) in revisions
        and _item_repository_key(item) not in exclusions
    ]
    eligible.sort(key=_item_repository_key)
    return [
        {
            "ordinal": ordinal,
            "provider": item["provider"],
            "owner": item["owner"],
            "repository": item["repository"],
            "default_branch": item["default_branch"],
            "immutable_revision": revisions[_item_repository_key(item)],
            "canonical_repository": _item_repository_key(item),
        }
        for ordinal, item in enumerate(eligible, start=1)
    ]


def validate_catalog_allowlist(
    contract: dict[str, Any],
    capture: dict[str, Any],
    allowlist: dict[str, Any],
) -> None:
    validate_catalog_capture(contract, capture)
    _validate_schema(allowlist, _ALLOWLIST_SCHEMA, "catalog allowlist")
    _validate_projection(allowlist, "allowlist")
    if allowlist.get("schema_version") != (
        "p15-v7-attempt-007-complete-allowlist-v1"
    ):
        raise Attempt007ValidationError("allowlist schema mismatch")
    if allowlist.get("attempt_id") != contract["attempt_id"]:
        raise Attempt007ValidationError("allowlist attempt mismatch")
    if allowlist.get("catalog_capture_sha256") != _canonical_sha256(capture):
        raise Attempt007ValidationError("allowlist catalog binding mismatch")
    if allowlist.get("entries") != _expected_allowlist_entries(contract, capture):
        raise Attempt007ValidationError(
            "allowlist must equal the complete eligible canonical catalog"
        )


def validate_execution_selection(
    contract: dict[str, Any],
    allowlist: dict[str, Any],
    selected_canonical_repositories: list[str],
) -> None:
    required = contract["execution_rule"]["repository_count"]
    entries = allowlist.get("entries")
    if not isinstance(entries, list) or len(entries) < required:
        raise Attempt007ValidationError("eligible catalog has fewer than two repositories")
    if len(selected_canonical_repositories) != required:
        raise Attempt007ValidationError("execution must select exactly two repositories")
    expected = [entry["canonical_repository"] for entry in entries[:required]]
    if selected_canonical_repositories != expected:
        raise Attempt007ValidationError("execution must use the exact allowlist prefix")
    if len({_normalize(item) for item in selected_canonical_repositories}) != required:
        raise Attempt007ValidationError(
            "execution repositories must be canonically distinct"
        )


def validate_attempt_002_identity_audit(audit: dict[str, Any]) -> None:
    _validate_schema(
        audit, _ATTEMPT_002_AUDIT_SCHEMA, "attempt-002 identity audit"
    )
    if audit.get("schema_version") != (
        "p15-v7-attempt-002-identity-query-audit-artifact-v1"
    ):
        raise Attempt007ValidationError("attempt-002 identity audit schema mismatch")
    if audit.get("status") != "INCONCLUSIVE" or audit.get("execution_eligible") is not False:
        raise Attempt007ValidationError("attempt-002 identity audit must be nonexecutable")
    if audit.get("disposition") != (
        "noncompliant-catalog-observed-before-allowlist-and-source"
    ):
        raise Attempt007ValidationError("attempt-002 disposition mismatch")
    projection = audit.get("canonical_projection")
    if not isinstance(projection, dict) or audit.get(
        "canonical_projection_sha256"
    ) != _canonical_sha256(projection):
        raise Attempt007ValidationError("attempt-002 audit projection hash mismatch")
    exclusion = projection.get("next_attempt_exclusion_candidate", {})
    repositories = exclusion.get("canonical_repositories")
    if (
        exclusion.get("canonical_repository_count") != 20
        or exclusion.get("prior_canonical_repository_count") != 13
        or exclusion.get("newly_exposed_canonical_repository_count") != 7
        or exclusion.get("intersection_count") != 0
        or not isinstance(repositories, list)
        or len(repositories) != 20
        or len({_normalize(item) for item in repositories}) != 20
    ):
        raise Attempt007ValidationError("attempt-002 union20 projection mismatch")
    raw = projection.get("raw_query_order")
    if not isinstance(raw, list) or len(raw) != 7:
        raise Attempt007ValidationError("attempt-002 raw7 projection mismatch")
    raw_keys = {_normalize(item["canonical_repository"]) for item in raw}
    if not raw_keys.issubset({_normalize(item) for item in repositories}):
        raise Attempt007ValidationError("attempt-002 raw7 is absent from union20")
    zero_state = projection.get("zero_state")
    if not isinstance(zero_state, dict) or any(value != 0 for value in zero_state.values()):
        raise Attempt007ValidationError("attempt-002 post-query execution state is not zero")


def validate_attempt_003_catalog_failure_audit(
    audit: dict[str, Any], project_root: Path
) -> None:
    if (
        audit.get("schema_version")
        != "p15-v7-attempt-003-catalog-failure-audit-artifact-v1"
        or audit.get("attempt_id") != "p15-v7-attempt-003"
        or audit.get("status") != "FAILED"
        or audit.get("disposition")
        != "catalog-failed-missing-required-etag-before-body-parse"
        or audit.get("execution_eligible") is not False
    ):
        raise Attempt007ValidationError("attempt-003 failure audit disposition mismatch")
    projection = audit.get("canonical_projection")
    if not isinstance(projection, dict) or audit.get(
        "canonical_projection_sha256"
    ) != _canonical_sha256(projection):
        raise Attempt007ValidationError("attempt-003 audit projection hash mismatch")
    if (
        projection.get("schema_version")
        != "p15-v7-attempt-003-catalog-failure-audit-projection-v1"
        or projection.get("attempt_id") != "p15-v7-attempt-003"
    ):
        raise Attempt007ValidationError("attempt-003 audit projection mismatch")

    fixture_root = project_root / "tests/fixtures/p15_v7_minimal_online_causal"
    archived_contract_path = fixture_root / "audit/p15-v7-attempt-003-contract.json"
    archived_contract = json.loads(archived_contract_path.read_text(encoding="utf-8"))
    authoritative = projection.get("authoritative_contract", {})
    if authoritative != {
        "file_sha256": hashlib.sha256(
            archived_contract_path.read_bytes()
        ).hexdigest(),
        "modified": False,
        "projection_sha256": archived_contract["contract_binding"][
            "projection_sha256"
        ],
    }:
        raise Attempt007ValidationError("attempt-003 archived contract binding mismatch")

    request = projection.get("exact_catalog_request", {})
    request_projection = {
        key: value
        for key, value in request.items()
        if key not in {"projection_algorithm", "projection_sha256"}
    }
    if (
        request.get("projection_algorithm")
        != "sha256_of_canonical_json_exact_request_without_projection_hash_sort_keys_compact_ascii"
        or request.get("projection_sha256")
        != _canonical_sha256(request_projection)
        or request_projection
        != {
            "attempt_count": 1,
            "endpoint": archived_contract["catalog_contract"]["search_endpoint"],
            "headers": archived_contract["catalog_contract"]["request_headers"],
            "issued_at_utc": request.get("issued_at_utc"),
            "method": "GET",
            "params": {
                "order": archived_contract["catalog_contract"]["order"],
                "page": 1,
                "per_page": archived_contract["catalog_contract"]["per_page"],
                "q": archived_contract["catalog_contract"]["q"],
                "sort": archived_contract["catalog_contract"]["sort"],
            },
        }
    ):
        raise Attempt007ValidationError("attempt-003 exact request audit mismatch")
    issued_at = _parse_utc_rfc3339(
        request["issued_at_utc"], "attempt-003 request issued_at_utc"
    )
    frozen_at = _parse_utc_rfc3339(
        archived_contract["contract_frozen_at_utc"],
        "attempt-003 contract freeze timestamp",
    )
    if issued_at < frozen_at:
        raise Attempt007ValidationError("attempt-003 request predates contract freeze")

    response = projection.get("observed_response_metadata", {})
    response_projection = {
        key: value
        for key, value in response.items()
        if key not in {"projection_algorithm", "projection_sha256"}
    }
    if (
        response.get("projection_algorithm")
        != "sha256_of_canonical_json_status_and_observed_headers_sort_keys_compact_ascii"
        or response.get("projection_sha256")
        != _canonical_sha256(response_projection)
        or response_projection.get("status") != 200
        or response_projection.get("headers", {}).get("ETag") is not None
    ):
        raise Attempt007ValidationError("attempt-003 response receipt audit mismatch")
    response_date = _parse_rfc1123(
        response_projection["headers"].get("Date"), "attempt-003 response"
    )
    if response_date < issued_at:
        raise Attempt007ValidationError("attempt-003 response predates request")

    body = projection.get("body_observation", {})
    if (
        body.get("body_bytes_materialized_in_http_client_process_memory") is not True
        or body.get("body_bytes_persisted") is not False
        or body.get("body_json_parsed") is not False
        or body.get("content_identity_observed") is not False
        or body.get("repository_identity_observed_by_agent") is not False
        or body.get("repository_identity_observed_in_tool_output") is not False
        or body.get("total_count_observed") is not False
    ):
        raise Attempt007ValidationError("attempt-003 body exposure audit mismatch")
    if projection.get("exposure_closure") != {
        "canonical_repositories": [],
        "newly_exposed_canonical_repository_count": 0,
        "reason": "no_repository_identity_was_parsed_or_observed",
    }:
        raise Attempt007ValidationError("attempt-003 identity exposure is not empty")
    zero_state = projection.get("zero_state")
    if not isinstance(zero_state, dict) or any(value != 0 for value in zero_state.values()):
        raise Attempt007ValidationError("attempt-003 execution state is not zero")


def validate_attempt_004_catalog_failure_audit(
    audit: dict[str, Any], project_root: Path
) -> None:
    if (
        audit.get("schema_version")
        != "p15-v7-attempt-004-catalog-failure-audit-artifact-v1"
        or audit.get("attempt_id") != "p15-v7-attempt-004"
        or audit.get("status") != "INCONCLUSIVE"
        or audit.get("disposition")
        != "external-catalog-universe-over-limit-before-allowlist-source"
        or audit.get("execution_eligible") is not False
    ):
        raise Attempt007ValidationError("attempt-004 failure audit disposition mismatch")
    projection = audit.get("canonical_projection")
    if not isinstance(projection, dict) or audit.get(
        "canonical_projection_sha256"
    ) != _canonical_sha256(projection):
        raise Attempt007ValidationError("attempt-004 audit projection hash mismatch")
    if (
        projection.get("schema_version")
        != "p15-v7-attempt-004-catalog-failure-audit-projection-v1"
        or projection.get("attempt_id") != "p15-v7-attempt-004"
    ):
        raise Attempt007ValidationError("attempt-004 audit projection mismatch")

    fixture_root = project_root / "tests/fixtures/p15_v7_minimal_online_causal"
    archived_contract_path = fixture_root / "audit/p15-v7-attempt-004-contract.json"
    archived_contract = json.loads(archived_contract_path.read_text(encoding="utf-8"))
    authoritative = projection.get("authoritative_contract", {})
    if authoritative != {
        "file_sha256": hashlib.sha256(
            archived_contract_path.read_bytes()
        ).hexdigest(),
        "modified": False,
        "projection_sha256": archived_contract["contract_binding"][
            "projection_sha256"
        ],
    }:
        raise Attempt007ValidationError("attempt-004 archived contract binding mismatch")

    request = projection.get("exact_catalog_request", {})
    catalog = archived_contract["catalog_contract"]
    if request != {
        "attempt_count": 1,
        "endpoint": catalog["search_endpoint"],
        "headers": catalog["request_headers"],
        "issued_at_utc": "not_established",
        "method": "GET",
        "params": {
            "order": catalog["order"],
            "page": 1,
            "per_page": catalog["per_page"],
            "q": catalog["q"],
            "sort": catalog["sort"],
        },
        "wire_request_projection_sha256": "not_established",
    }:
        raise Attempt007ValidationError("attempt-004 exact request audit mismatch")

    result = projection.get("catalog_result", {})
    if (
        result.get("raw_total") != 1903
        or result.get("raw_total") <= catalog["max_total_count"]
        or result.get("accepted_page_counts") != [0, 0]
        or result.get("allowlist_artifact_created") is not False
        or result.get("capture_artifact_created") is not False
        or result.get("stop_reason")
        != "first_catalog_response_total_count_exceeds_frozen_maximum_before_page_acceptance"
    ):
        raise Attempt007ValidationError("attempt-004 over-limit result mismatch")
    if projection.get("observed_response") != {
        "Date": "not_established",
        "etag": "not_established",
        "etag_present": "not_established",
        "status": 200,
        "total_count": 1903,
    }:
        raise Attempt007ValidationError("attempt-004 response audit mismatch")

    body = projection.get("body_observation", {})
    if (
        body.get("body_bytes_materialized_in_http_client_process_memory") is not True
        or body.get("body_bytes_persisted") is not False
        or body.get("body_json_parsed") is not True
        or body.get("content_identity_observed") is not False
        or body.get("items_list_type_checked") is not True
        or body.get("items_iterated") is not False
        or body.get("item_identity_fields_accessed") is not False
        or body.get("repository_identity_observed_by_agent") is not False
        or body.get("repository_identity_observed_in_tool_output") is not False
    ):
        raise Attempt007ValidationError("attempt-004 body exposure audit mismatch")
    if projection.get("exposure_closure") != {
        "canonical_repositories": [],
        "newly_exposed_canonical_repository_count": 0,
        "reason": (
            "no_item_was_iterated_and_no_repository_identity_field_was_"
            "accessed_or_emitted"
        ),
    }:
        raise Attempt007ValidationError("attempt-004 identity exposure is not empty")
    zero_state = projection.get("zero_state")
    if not isinstance(zero_state, dict) or any(value != 0 for value in zero_state.values()):
        raise Attempt007ValidationError("attempt-004 execution state is not zero")


def validate_attempt_005_ref_failure_audit(
    audit: dict[str, Any], project_root: Path
) -> None:
    if (
        audit.get("schema_version")
        != "p15-v7-attempt-005-ref-failure-audit-artifact-v1"
        or audit.get("attempt_id") != "p15-v7-attempt-005"
        or audit.get("status") != "INCONCLUSIVE"
        or audit.get("disposition")
        != "ref-resolution-403-after-catalog-consistency-before-allowlist-source"
        or audit.get("execution_eligible") is not False
    ):
        raise Attempt007ValidationError("attempt-005 ref failure audit disposition mismatch")
    projection = audit.get("canonical_projection")
    if not isinstance(projection, dict) or audit.get(
        "canonical_projection_sha256"
    ) != _canonical_sha256(projection):
        raise Attempt007ValidationError("attempt-005 audit projection hash mismatch")
    if (
        projection.get("schema_version")
        != "p15-v7-attempt-005-ref-failure-audit-projection-v1"
        or projection.get("attempt_id") != "p15-v7-attempt-005"
    ):
        raise Attempt007ValidationError("attempt-005 audit projection mismatch")

    fixture_root = project_root / "tests/fixtures/p15_v7_minimal_online_causal"
    archived_contract_path = fixture_root / "audit/p15-v7-attempt-005-contract.json"
    archived_contract = json.loads(archived_contract_path.read_text(encoding="utf-8"))
    archived_contract_sha256 = hashlib.sha256(
        archived_contract_path.read_bytes()
    ).hexdigest()
    authoritative = projection.get("authoritative_contract", {})
    expected_contract_binding = {
        "file_sha256": archived_contract_sha256,
        "modified": False,
        "projection_sha256": archived_contract["contract_binding"][
            "projection_sha256"
        ],
    }
    if authoritative != expected_contract_binding:
        raise Attempt007ValidationError("attempt-005 archived contract binding mismatch")
    phase_1 = projection.get("phase_1", {})
    if (
        phase_1.get("status") != "PASS"
        or phase_1.get("focused_tests_passed") is not True
        or phase_1.get("governance_tests_passed") is not True
        or phase_1.get("focused_tests") != 216
        or phase_1.get("governance_tests") != 78
        or phase_1.get("contract_file_sha256") != archived_contract_sha256
        or phase_1.get("contract_projection_sha256")
        != archived_contract["contract_binding"]["projection_sha256"]
    ):
        raise Attempt007ValidationError("attempt-005 phase-1 receipt mismatch")

    catalog_observation = projection.get("catalog_observation", {})
    if catalog_observation != {
        "complete_identity_set_persisted": False,
        "double_pass_body_projection_equal": True,
        "double_pass_complete": True,
        "double_pass_total_equal": True,
        "drift": False,
        "identity_fields_parsed_and_iterated_by_code": True,
        "ordered_catalog": "not_established",
        "pass_page_counts": "not_established",
        "raw_total": "not_established",
        "recoverable_from_existing_process_memory": False,
        "temporary_result_written": False,
    }:
        raise Attempt007ValidationError("attempt-005 catalog persistence audit mismatch")
    if projection.get("catalog_result") != {
        "allowlist_artifact_created": False,
        "capture_artifact_created": False,
        "eligible_count": "not_established",
        "excluded_count": "not_established",
        "ordered_allowlist": [],
        "prefix2": [],
        "stop_reason": "http_403_during_exact_default_branch_ref_resolution",
    }:
        raise Attempt007ValidationError("attempt-005 stopped result mismatch")

    request = projection.get("failed_ref_request", {})
    request_projection = {
        key: value
        for key, value in request.items()
        if key not in {"projection_algorithm", "projection_sha256"}
    }
    if (
        request.get("projection_algorithm")
        != "sha256_of_canonical_json_request_and_identity_context_without_projection_metadata_sort_keys_compact_ascii"
        or request.get("projection_sha256") != _canonical_sha256(request_projection)
        or request_projection
        != {
            "attempt_count": 1,
            "canonical_repository": "github/coinhubmedia/melt-calculator-domains",
            "default_branch": "main",
            "endpoint": (
                "https://api.github.com/repos/coinhubmedia/"
                "melt-calculator-domains/git/ref/heads/main"
            ),
            "headers": archived_contract["catalog_contract"]["request_headers"],
            "issued_at_utc": request.get("issued_at_utc"),
            "method": "GET",
        }
    ):
        raise Attempt007ValidationError("attempt-005 exact failed ref request mismatch")
    issued_at = _parse_utc_rfc3339(
        request["issued_at_utc"], "attempt-005 ref request issued_at_utc"
    )
    frozen_at = _parse_utc_rfc3339(
        archived_contract["contract_frozen_at_utc"],
        "attempt-005 contract freeze timestamp",
    )
    if issued_at < frozen_at:
        raise Attempt007ValidationError("attempt-005 ref request predates contract freeze")

    response = projection.get("failed_ref_response_observation", {})
    if response != {
        "body_materialized": "not_established",
        "body_read_by_handler": False,
        "etag": None,
        "etag_present": False,
        "headers_accessed_by_handler": ["Date", "ETag"],
        "message": "not_established",
        "projection_algorithm": (
            "sha256_of_canonical_json_status_and_observed_headers_sort_keys_compact_ascii"
        ),
        "projection_sha256": (
            "864f782b9f37d6184306dec81222b89d6f243ef180784fc4c2260e1bf6feaf77"
        ),
        "rate_limit_evidence": "not_established",
        "retry_after_evidence": "not_established",
        "server_date": "Sun, 02 Aug 2026 06:59:49 GMT",
        "status": 403,
    }:
        raise Attempt007ValidationError("attempt-005 ref response receipt mismatch")
    if _parse_rfc1123(response["server_date"], "attempt-005 ref response") < issued_at:
        raise Attempt007ValidationError("attempt-005 ref response predates request")

    known_repository = "github/coinhubmedia/melt-calculator-domains"
    if projection.get("identity_exposure") != {
        "closure_complete": False,
        "known_exposed_canonical_repositories": [known_repository],
        "known_exposed_canonical_repository_count": 1,
        "status": (
            "full_catalog_identity_exposure_not_established_and_not_recoverable_"
            "without_forbidden_requery"
        ),
    }:
        raise Attempt007ValidationError("attempt-005 known identity exposure mismatch")
    accounting = projection.get("accounting", {})
    if accounting != {
        "catalog_requests_exact": "not_established",
        "catalog_requests_minimum": 2,
        "failing_ref_request_included": True,
        "ref_requests_exact": "not_established",
        "ref_requests_minimum": 1,
    }:
        raise Attempt007ValidationError("attempt-005 request accounting mismatch")
    zero_state = projection.get("zero_state")
    if not isinstance(zero_state, dict) or any(value != 0 for value in zero_state.values()):
        raise Attempt007ValidationError("attempt-005 execution state is not zero")


def validate_attempt_006_catalog_failure_audit(
    audit: dict[str, Any], project_root: Path
) -> list[dict[str, Any]]:
    if (
        audit.get("schema_version")
        != "p15-v7-attempt-006-catalog-validation-failure-audit-artifact-v1"
        or audit.get("attempt_id") != "p15-v7-attempt-006"
        or audit.get("status") != "INCONCLUSIVE"
        or audit.get("disposition")
        != "provider-updated-order-nonmonotonic-after-complete-double-pass-before-refs"
        or audit.get("execution_eligible") is not False
    ):
        raise Attempt007ValidationError("attempt-006 catalog failure disposition mismatch")
    projection = audit.get("canonical_projection")
    if not isinstance(projection, dict) or audit.get(
        "canonical_projection_sha256"
    ) != _canonical_sha256(projection):
        raise Attempt007ValidationError("attempt-006 audit projection hash mismatch")
    if (
        projection.get("schema_version")
        != "p15-v7-attempt-006-catalog-validation-failure-audit-projection-v1"
        or projection.get("attempt_id") != "p15-v7-attempt-006"
    ):
        raise Attempt007ValidationError("attempt-006 audit projection mismatch")

    fixture_root = project_root / "tests/fixtures/p15_v7_minimal_online_causal"
    archived_contract_path = fixture_root / "audit/p15-v7-attempt-006-contract.json"
    archived_contract = json.loads(archived_contract_path.read_text(encoding="utf-8"))
    if projection.get("authoritative_contract") != {
        "file_sha256": hashlib.sha256(archived_contract_path.read_bytes()).hexdigest(),
        "modified": False,
        "projection_sha256": archived_contract["contract_binding"][
            "projection_sha256"
        ],
    }:
        raise Attempt007ValidationError("attempt-006 archived contract binding mismatch")

    capture_ref = projection.get("immutable_capture", {})
    capture_path = fixture_root / str(capture_ref.get("path", ""))
    capture_bytes = capture_path.read_bytes()
    capture = json.loads(capture_bytes)
    _validate_schema(
        capture,
        _ATTEMPT_006_SEALED_CATALOG_SCHEMA,
        "attempt-006 immutable catalog capture",
    )
    if (
        capture_ref
        != {
            "file_sha256": hashlib.sha256(capture_bytes).hexdigest(),
            "ordered_catalog_sha256": capture["ordered_catalog_sha256"],
            "path": "audit/attempt-006-catalog-validation-failure-capture.json",
            "projection_sha256": capture["projection_sha256"],
            "sealed": True,
            "storage_mode": "append_only",
        }
        or capture.get("contract_projection_sha256")
        != archived_contract["contract_binding"]["projection_sha256"]
        or capture.get("projection_sha256")
        != _canonical_sha256(_projection_without_hash(capture))
    ):
        raise Attempt007ValidationError("attempt-006 immutable capture binding mismatch")

    frozen_at = _parse_utc_rfc3339(
        archived_contract["contract_frozen_at_utc"],
        "attempt-006 contract freeze timestamp",
    )
    passes = capture.get("passes")
    if not isinstance(passes, list) or len(passes) != 2:
        raise Attempt007ValidationError("attempt-006 capture requires two passes")
    first = _validate_catalog_pass(
        archived_contract,
        passes[0],
        1,
        frozen_at,
        None,
        max_server_date_lag_seconds=5,
    )
    second = _validate_catalog_pass(
        archived_contract,
        passes[1],
        2,
        frozen_at,
        first[3],
        max_server_date_lag_seconds=5,
    )
    if first[:2] != second[:2] or first[2] != second[2]:
        raise Attempt007ValidationError("attempt-006 capture double-pass drift")
    raw_catalog = first[2]
    updated_at = [item["updated_at"] for item in raw_catalog]
    adjacent_descents = sum(
        updated_at[index] < updated_at[index - 1]
        for index in range(1, len(updated_at))
    )
    if (
        capture.get("ordered_catalog_count") != len(raw_catalog)
        or capture.get("ordered_catalog") != raw_catalog
        or capture.get("ordered_catalog_sha256")
        != _canonical_sha256(raw_catalog)
    ):
        raise Attempt007ValidationError("attempt-006 persisted catalog is incomplete")
    if projection.get("catalog_observation") != {
        "catalog_requests_exact": 4,
        "complete_identity_set_persisted": True,
        "double_pass_body_projection_equal": True,
        "double_pass_complete": True,
        "double_pass_total_equal": True,
        "incomplete_results": [False, False, False, False],
        "page_item_counts": [[100, 30], [100, 30]],
        "pass_canonical_projection_sha256": [first[1], second[1]],
        "raw_total": 130,
        "unique_normalized_repository_count": 130,
        "updated_at_adjacent_descent_count": adjacent_descents,
        "validator_stop_reason": "catalog_is_not_in_updated_ascending_order",
    } or adjacent_descents != 11:
        raise Attempt007ValidationError("attempt-006 provider-order audit mismatch")
    if projection.get("zero_after_catalog") != {
        "effect_observations": 0,
        "git_ref_requests": 0,
        "heldout_accesses": 0,
        "ollama_calls": 0,
        "online_model_calls": 0,
        "source_content_accesses": 0,
        "source_tree_accesses": 0,
    }:
        raise Attempt007ValidationError("attempt-006 post-catalog state is not zero")
    return sorted(raw_catalog, key=_pre_ref_sort_key)


def validate_repository_bundle(project_root: Path) -> None:
    fixture_root = project_root / "tests/fixtures/p15_v7_minimal_online_causal"
    canonical_path = fixture_root / "attempt-contract.json"
    if list(fixture_root.glob("**/attempt-contract.json")) != [canonical_path]:
        raise Attempt007ValidationError("exactly one executable contract is required")
    contract = json.loads(canonical_path.read_text(encoding="utf-8"))
    validate_pre_catalog_contract(contract)
    audit_refs = {
        item["attempt_id"]: item
        for item in contract["exclusion_projection"]["source_audits"]
    }
    if set(audit_refs) != {
        "p15-v7-attempt-001",
        "p15-v7-attempt-002",
        "p15-v7-attempt-003",
        "p15-v7-attempt-004",
        "p15-v7-attempt-005",
        "p15-v7-attempt-006",
    }:
        raise Attempt007ValidationError("all superseded attempts must be audit-bound")
    for audit_ref in audit_refs.values():
        audit_path = fixture_root / audit_ref["path"]
        if hashlib.sha256(audit_path.read_bytes()).hexdigest() != audit_ref["sha256"]:
            raise Attempt007ValidationError("supersession audit file hash mismatch")
    attempt_002_audit = json.loads(
        (fixture_root / audit_refs["p15-v7-attempt-002"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    validate_attempt_002_identity_audit(attempt_002_audit)
    attempt_003_audit = json.loads(
        (fixture_root / audit_refs["p15-v7-attempt-003"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    validate_attempt_003_catalog_failure_audit(attempt_003_audit, project_root)
    attempt_004_audit = json.loads(
        (fixture_root / audit_refs["p15-v7-attempt-004"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    validate_attempt_004_catalog_failure_audit(attempt_004_audit, project_root)
    attempt_005_audit = json.loads(
        (fixture_root / audit_refs["p15-v7-attempt-005"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    validate_attempt_005_ref_failure_audit(attempt_005_audit, project_root)
    attempt_006_audit_path = fixture_root / audit_refs[
        "p15-v7-attempt-006"
    ]["path"]
    attempt_006_audit = json.loads(
        attempt_006_audit_path.read_text(encoding="utf-8")
    )
    offline_catalog = validate_attempt_006_catalog_failure_audit(
        attempt_006_audit, project_root
    )
    offline_source = contract["offline_catalog_source"]
    archived_contract_path = fixture_root / offline_source[
        "archived_contract_path"
    ]
    capture_path = fixture_root / offline_source["capture_path"]
    if offline_source != {
        "mode": "immutable_attempt_006_capture_no_requery",
        "attempt_id": "p15-v7-attempt-006",
        "archived_contract_path": "audit/p15-v7-attempt-006-contract.json",
        "archived_contract_sha256": hashlib.sha256(
            archived_contract_path.read_bytes()
        ).hexdigest(),
        "archived_contract_projection_sha256": json.loads(
            archived_contract_path.read_text(encoding="utf-8")
        )["contract_binding"]["projection_sha256"],
        "audit_path": "audit/attempt-006-catalog-validation-failure-audit.json",
        "audit_sha256": hashlib.sha256(
            attempt_006_audit_path.read_bytes()
        ).hexdigest(),
        "capture_path": "audit/attempt-006-catalog-validation-failure-capture.json",
        "capture_sha256": hashlib.sha256(capture_path.read_bytes()).hexdigest(),
        "capture_projection_sha256": json.loads(
            capture_path.read_text(encoding="utf-8")
        )["projection_sha256"],
        "catalog_requests_exact": 0,
    }:
        raise Attempt007ValidationError("offline catalog file binding mismatch")
    receipt_path = fixture_root / contract["catalog_receipt"]["path"]
    if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != contract[
        "catalog_receipt"
    ]["sha256"]:
        raise Attempt007ValidationError("sealed catalog receipt file hash mismatch")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    validated_catalog = validate_sealed_catalog_receipt(contract, receipt)
    source_capture = json.loads(capture_path.read_text(encoding="utf-8"))
    if (
        receipt["passes"] != source_capture["passes"]
        or receipt["source_capture_sha256"] != offline_source["capture_sha256"]
        or validated_catalog != offline_catalog
    ):
        raise Attempt007ValidationError(
            "sealed catalog receipt differs from immutable capture"
        )
    expected_union = attempt_002_audit["canonical_projection"][
        "next_attempt_exclusion_candidate"
    ]["canonical_repositories"] + attempt_005_audit["canonical_projection"][
        "identity_exposure"
    ]["known_exposed_canonical_repositories"]
    if contract["exclusion_projection"]["canonical_repositories"] != expected_union:
        raise Attempt007ValidationError("contract exclusion does not equal audited union21")
