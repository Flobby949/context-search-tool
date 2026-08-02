from __future__ import annotations

import copy
import hashlib
import json
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/p15_v7_minimal_online_causal/audit/p15-v7-attempt-002-contract.schema.json"
)
AUDIT_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/p15_v7_minimal_online_causal/supersession-audit.schema.json"
)

_HASH_BINDING_FIELDS = frozenset(
    {"projection_sha256", "expected_allowlist_sha256"}
)
_ALLOWLIST_RECEIPT_FIELDS = frozenset(
    {"received", "identity_selected", "path", "sha256"}
)
_ZERO_COUNTERS = (
    "planner_calls",
    "embedding_calls",
    "source_accesses",
    "treatment_executions",
    "held_out_accesses",
)
_FALSE_GOVERNANCE_FLAGS = (
    "fresh_identity_selected",
    "fresh_source_accessed",
    "candidate_executed",
    "online_requests_made",
    "ollama_requests_made",
    "held_out_opened",
)


class GovernanceValidationError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def contract_projection_sha256(contract: dict[str, Any]) -> str:
    projection = copy.deepcopy(contract)
    identity_selection = projection.get("identity_selection", {})
    binding = identity_selection.get("contract_binding", {})
    for field in _HASH_BINDING_FIELDS:
        binding.pop(field, None)
    future_allowlist = identity_selection.get("future_allowlist", {})
    for field in _ALLOWLIST_RECEIPT_FIELDS:
        future_allowlist.pop(field, None)
    return canonical_sha256(projection)


def _schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_schema(
    instance: dict[str, Any], path: Path, *, label: str
) -> None:
    errors = sorted(
        Draft202012Validator(_schema(path)).iter_errors(instance),
        key=lambda error: list(error.absolute_path),
    )
    if not errors:
        return
    first = errors[0]
    location = ".".join(str(part) for part in first.absolute_path) or "<root>"
    raise GovernanceValidationError(
        f"{label} schema violation at {location}: {first.message}"
    )


def _identity_projection(entry: dict[str, Any]) -> dict[str, str]:
    return {
        "provider": entry["provider"],
        "owner": entry["owner"],
        "repository": entry["repository"],
        "immutable_revision": entry["immutable_revision"],
    }


def _normalize_identity_part(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _canonical_repository_key(owner: str, repository: str) -> tuple[str, str]:
    return _normalize_identity_part(owner), _normalize_identity_part(repository)


def _canonical_identity_key(
    provider: str, owner: str, repository: str
) -> tuple[str, str, str]:
    return (
        _normalize_identity_part(provider),
        *_canonical_repository_key(owner, repository),
    )


def _normalized_sort_key(entry: dict[str, Any]) -> tuple[str, ...]:
    return (
        _normalize_identity_part(entry["provider"]),
        _normalize_identity_part(entry["owner"]),
        _normalize_identity_part(entry["repository"]),
        entry["immutable_revision"].lower(),
        entry["identity_sha256"],
    )


def _exclusion_source(
    exclusion: dict[str, Any], source_allowlist_sha256: str
) -> dict[str, Any]:
    return {
        "schema_version": "p15-v7-attempt-001-exclusion-projection-v1",
        "attempt_id": exclusion["complete_for_superseded_attempt"],
        "source_allowlist_sha256": source_allowlist_sha256,
        "fresh": exclusion["fresh"],
        "heldout": exclusion["heldout"],
        "unbound_commit_sentinel": exclusion["unbound_commit_sentinel"],
        "counts": exclusion["counts"],
    }


def _expected_excluded_hashes(exclusion: dict[str, Any]) -> list[str]:
    hashes: list[str] = []
    for identity in [*exclusion["fresh"], *exclusion["heldout"]]:
        owner_repository, revision = identity.rsplit("@", 1)
        owner, repository = owner_repository.split("/", 1)
        hashes.append(
            canonical_sha256(
                {
                    "provider": "github",
                    "owner": owner,
                    "repository": repository,
                    "immutable_revision": revision,
                }
            )
        )
    return hashes


def _validate_exclusion_projection(contract: dict[str, Any]) -> None:
    exclusion = contract["identity_selection"]["exclusion_projection"]
    fresh = exclusion["fresh"]
    heldout = exclusion["heldout"]
    counts = exclusion["counts"]
    if counts != {
        "fresh": len(fresh),
        "heldout": len(heldout),
        "total": len(fresh) + len(heldout),
    }:
        raise GovernanceValidationError("exclusion counts are not complete")
    if len(set(fresh)) != len(fresh) or len(set(heldout)) != len(heldout):
        raise GovernanceValidationError("exclusion identities must be unique")
    if set(fresh) & set(heldout):
        raise GovernanceValidationError("fresh and heldout exclusions must be disjoint")
    if exclusion["identity_sha256"] != _expected_excluded_hashes(exclusion):
        raise GovernanceValidationError("excluded identity hash projection mismatch")


def _validate_contract_projection(contract: dict[str, Any]) -> None:
    stored = contract["identity_selection"]["contract_binding"][
        "projection_sha256"
    ]
    actual = contract_projection_sha256(contract)
    if stored != actual:
        raise GovernanceValidationError(
            f"contract projection hash mismatch: expected {stored}, got {actual}"
        )


def validate_pre_corpus_contract(contract: dict[str, Any]) -> None:
    _validate_schema(contract, SCHEMA_PATH, label="attempt contract")
    _validate_contract_projection(contract)
    _validate_exclusion_projection(contract)

    binding = contract["identity_selection"]["contract_binding"]
    future_allowlist = contract["identity_selection"]["future_allowlist"]
    if binding["expected_allowlist_sha256"]:
        raise GovernanceValidationError(
            "future allowlist hash must be empty before allowlist receipt"
        )
    if future_allowlist != {
        "schema_version": "p15-v7-fresh-identity-allowlist-v1",
        "attempt_id": contract["attempt_id"],
        "received": False,
        "identity_selected": False,
        "path": "",
        "sha256": "",
    }:
        raise GovernanceValidationError(
            "future allowlist receipt must be empty at pre-corpus freeze"
        )

    corpus = contract["corpus"]
    if corpus["fresh_repositories"] or corpus["fresh_cases"]:
        raise GovernanceValidationError("fresh corpus must be empty")
    if contract["sampling"]["expanded_schedule"]:
        raise GovernanceValidationError("expanded schedule must be empty")
    if corpus["held_out"]["identity_selected"] or corpus["held_out"]["opened"]:
        raise GovernanceValidationError("heldout access must remain zero")

    counters = contract["pre_corpus_counters"]
    if any(counters[key] != 0 for key in _ZERO_COUNTERS):
        raise GovernanceValidationError("pre-corpus counters must all be zero")
    governance = contract["governance"]
    if any(governance[key] is not False for key in _FALSE_GOVERNANCE_FLAGS):
        raise GovernanceValidationError("pre-corpus execution flags must all be false")


def validate_future_allowlist_binding(
    contract: dict[str, Any], allowlist: dict[str, Any]
) -> None:
    _validate_schema(contract, SCHEMA_PATH, label="attempt contract")
    _validate_contract_projection(contract)
    _validate_exclusion_projection(contract)

    if allowlist.get("schema_version") != "p15-v7-fresh-identity-allowlist-v1":
        raise GovernanceValidationError("future allowlist schema mismatch")
    if allowlist.get("attempt_id") != contract["attempt_id"]:
        raise GovernanceValidationError("future allowlist attempt mismatch")
    actual_contract_hash = contract_projection_sha256(contract)
    if allowlist.get("contract_projection_sha256") != actual_contract_hash:
        raise GovernanceValidationError("future allowlist contract projection mismatch")

    actual_allowlist_hash = canonical_sha256(allowlist)
    binding = contract["identity_selection"]["contract_binding"]
    future_allowlist = contract["identity_selection"]["future_allowlist"]
    if binding["expected_allowlist_sha256"] != actual_allowlist_hash:
        raise GovernanceValidationError("future allowlist hash mismatch in contract")
    if future_allowlist["sha256"] != actual_allowlist_hash:
        raise GovernanceValidationError("future allowlist hash mismatch in receipt")
    if future_allowlist["attempt_id"] != allowlist["attempt_id"]:
        raise GovernanceValidationError("future allowlist receipt attempt mismatch")
    if not future_allowlist["received"] or not future_allowlist["identity_selected"]:
        raise GovernanceValidationError("future allowlist receipt is not sealed")

    entries = allowlist.get("entries")
    permitting = contract["identity_selection"]["allowlist_permitting"]
    required = permitting["allowlist_minimum_entries"]
    if not isinstance(entries, list) or len(entries) < required:
        raise GovernanceValidationError(
            f"future allowlist requires at least {required} entries"
        )
    expected_ordinals = list(range(1, len(entries) + 1))
    if [entry.get("ordinal") for entry in entries] != expected_ordinals:
        raise GovernanceValidationError("allowlist ordinals must be contiguous from one")
    expected_keys = set()
    for key in [
        *contract["identity_selection"]["exclusion_projection"]["fresh"],
        *contract["identity_selection"]["exclusion_projection"]["heldout"],
    ]:
        owner_repository = key.rsplit("@", 1)[0]
        owner, repository = owner_repository.split("/", 1)
        expected_keys.add(_canonical_identity_key("github", owner, repository))
    excluded_hashes = set(
        contract["identity_selection"]["exclusion_projection"][
            "identity_sha256"
        ]
    )
    seen: set[str] = set()
    for entry in entries:
        if set(entry) != {
            "ordinal",
            "provider",
            "owner",
            "repository",
            "immutable_revision",
            "identity_sha256",
        }:
            raise GovernanceValidationError("allowlist entry fields are not exact")
        identity_hash = canonical_sha256(_identity_projection(entry))
        if entry["identity_sha256"] != identity_hash:
            raise GovernanceValidationError("allowlist identity hash mismatch")
        repository_key = _canonical_identity_key(
            entry["provider"], entry["owner"], entry["repository"]
        )
        if identity_hash in excluded_hashes or repository_key in expected_keys:
            raise GovernanceValidationError("allowlist contains excluded identity")
        if identity_hash in seen:
            raise GovernanceValidationError("allowlist identities must be unique")
        seen.add(identity_hash)
    prefix_repositories = {
        _canonical_repository_key(entry["owner"], entry["repository"])
        for entry in entries[:required]
    }
    if len(prefix_repositories) != required:
        raise GovernanceValidationError(
            "allowlist execution prefix must contain distinct repositories"
        )
    if [_normalized_sort_key(entry) for entry in entries] != sorted(
        _normalized_sort_key(entry) for entry in entries
    ):
        raise GovernanceValidationError("allowlist entries violate frozen sort order")


def validate_selected_identity_schedule(
    contract: dict[str, Any],
    allowlist: dict[str, Any],
    selected_identity_sha256: list[str],
) -> None:
    permitting = contract["identity_selection"]["allowlist_permitting"]
    required = permitting["selected_identity_count"]
    if (
        len(allowlist["entries"]) < required
        or len(selected_identity_sha256) != required
    ):
        raise GovernanceValidationError(
            f"selected schedule requires exactly {required} identities"
        )
    selected_repositories = {
        _canonical_repository_key(entry["owner"], entry["repository"])
        for entry in allowlist["entries"][:required]
    }
    if len(selected_repositories) != required:
        raise GovernanceValidationError(
            "selected schedule must contain distinct repositories"
        )
    expected = [
        entry["identity_sha256"] for entry in allowlist["entries"][:required]
    ]
    if selected_identity_sha256 != expected:
        raise GovernanceValidationError(
            "selected identities must equal the exact allowlist prefix"
        )


def validate_supersession_audit(
    contract: dict[str, Any], audit: dict[str, Any]
) -> None:
    source_evidence = audit.get("source_evidence", {})
    if (
        audit.get("disposition") != "superseded-before-execution"
        or source_evidence.get("source_materialized") is not True
        or source_evidence.get("source_touched") is not True
        or source_evidence.get("materialized_checkout_count_minimum", 0) < 1
    ):
        raise GovernanceValidationError(
            "source materialization evidence must be recorded before supersession"
        )
    _validate_schema(audit, AUDIT_SCHEMA_PATH, label="supersession audit")
    timeline = audit["timeline"]
    if not (
        datetime.fromisoformat(timeline["allowlist_recorded_at"])
        < datetime.fromisoformat(timeline["source_materialized_at"])
        < datetime.fromisoformat(timeline["audit_created_at"])
    ):
        raise GovernanceValidationError(
            "supersession audit timeline is not monotonic"
        )
    if audit["execution_eligible"] is not False:
        raise GovernanceValidationError("superseded attempt must not be executable")
    old_hashes = {
        audit["old_contract"]["sha256"],
        audit["old_allowlist"]["identity_only_sha256"],
    }
    exclusion = contract["identity_selection"]["exclusion_projection"]
    if audit["exclusion_projection"]["sha256"] != exclusion["projection_sha256"]:
        raise GovernanceValidationError("audit exclusion projection hash mismatch")
    if exclusion["projection_sha256"] != canonical_sha256(
        _exclusion_source(
            exclusion, audit["old_allowlist"]["identity_only_sha256"]
        )
    ):
        raise GovernanceValidationError("exclusion projection hash mismatch")
    execution_projection = copy.deepcopy(contract)
    execution_projection.pop("supersession_audit", None)
    serialized = json.dumps(execution_projection, sort_keys=True)
    if any(old_hash in serialized for old_hash in old_hashes):
        raise GovernanceValidationError(
            "audit-only hash leaked into contract execution inputs"
        )


def validate_repository_bundle(project_root: Path) -> None:
    fixture_root = (
        project_root / "tests/fixtures/p15_v7_minimal_online_causal"
    )
    contract_paths = list(fixture_root.glob("**/attempt-contract.json"))
    canonical_contract_path = fixture_root / "attempt-contract.json"
    if contract_paths != [canonical_contract_path]:
        raise GovernanceValidationError(
            "exactly one canonical executable attempt contract is required"
        )
    contract = json.loads(canonical_contract_path.read_text(encoding="utf-8"))
    validate_pre_corpus_contract(contract)

    audit_ref = contract["supersession_audit"]
    audit_path = fixture_root / audit_ref["path"]
    if hashlib.sha256(audit_path.read_bytes()).hexdigest() != audit_ref["sha256"]:
        raise GovernanceValidationError("supersession audit file hash mismatch")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    validate_supersession_audit(contract, audit)

    old_contract_path = fixture_root / audit["old_contract"]["path"]
    if (
        hashlib.sha256(old_contract_path.read_bytes()).hexdigest()
        != audit["old_contract"]["sha256"]
    ):
        raise GovernanceValidationError("immutable old contract hash mismatch")
