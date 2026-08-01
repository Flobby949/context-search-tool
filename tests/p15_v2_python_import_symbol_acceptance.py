from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
import errno
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import sqlite3
import stat
import subprocess
import tempfile
from typing import Callable, Iterator, Sequence


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = "p15-v2"
ATTEMPT_ID = "p15-v2-attempt-001"
TASK0D_HASH_CAPTURE_AUTHORIZED_STATUS = "task0d_hash_capture_authorized"
BASELINE = "5f56de2e1b57ed7f1ec0ee9a513b508461d78233"
V1_REJECT_INDEX_SHA256 = "d6942a94256351e510d7efc4b1719219de9f9529471645c627a5b5524aba8a10"
V1_REJECT_INDEX_PATH = ".quality/p15-runs/p15-v1-attempt-003/reject-index.json"
V1_TRACKED_REJECT_INDEX_PATH = "tests/fixtures/p15_v1_reject/attempt_003_reject_index.json"
P8_GOLD_PATH = "tests/fixtures/p8_python_graphs/input_manifest.json"
P8_GOLD_SHA256 = "56071dfc281f9947b989de26ddd1d07ff4e35666d8314686d0ffbb16cd92a013"
P8_CASES_SHA256 = "f2bfd16a9889f1182ac5ae65fa28892a6779d6a2b8baa7c9741b060cbf9f1143"
P8_SOURCES_SHA256 = "6edb13efa7f331401bee0c7f0853fecef29529ab731a0914253b8b7662716032"
ROSTER_CONTRACT_SHA256 = "27ad5f2b6abb2f9d11c202877bb56f3e76cbcaaa5d58e1059b79fdffb1446823"
SEAL_HASHES_SHA256 = "17e069d90f66899d0dab7b433b91b40620a55bcc92df881d1e038aa55cc78b1f"
PLAN_REVIEW_DISPOSITION_PATH = ".quality/p15-v2-review-seal/independent_plan_harness_disposition.json"
PLAN_REVIEW_DISPOSITION_SHA256 = "d9113575dfeb04b847cbe4acfe47027ff2a9f2e61467be6d84eaecacdaa0ce18"
TASK0D_ENGINE_DISPOSITION_PATH = ".quality/p15-v2-review-seal/independent_task0d_engine_disposition.json"
TASK0D_ENGINE_DISPOSITION_SHA256 = "3ec9cecc9e6c8abc435761768e03bc6f103a08438ba93a03bed9be5a735ed480"
RUNTIME_PRIVACY_FIX_DISPOSITION_PATH = ".quality/p15-v2-review-seal/independent_task0d_runtime_privacy_fix_disposition.json"
RUNTIME_PRIVACY_FIX_DISPOSITION_SHA256 = "029bb607366c2ac3f460f87dedc72f82bfce5fd87933dee95caecdbdd0433764"
SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_PATH = ".quality/p15-v2-review-seal/independent_task0d_signal_name_privacy_fix_disposition.json"
SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_SHA256 = "d9e266b670aa1f8406602b7c6b41aa397c4e83f65eda67faa50ff28aa297e4be"
MODULE_METADATA_PRIVACY_FIX_DISPOSITION_PATH = ".quality/p15-v2-review-seal/independent_task0d_module_metadata_privacy_fix_disposition.json"
MODULE_METADATA_PRIVACY_FIX_DISPOSITION_SHA256 = "c25a0a53c646a61640ef1b41ce86c5e51608868df5b7432baa4c6768350d88dd"
STRUCTURED_IDENTITY_PRIVACY_DISPOSITION_PATH = ".quality/p15-v2-review-seal/independent_task0d_structured_identity_privacy_disposition.json"
STRUCTURED_IDENTITY_PRIVACY_DISPOSITION_SHA256 = "c969079ed71b24dcb5ccb36cdca031a99e58d4c7eeb7bdc4be79d1d700d6d68c"
REVIEW_DISPOSITION_PATH = STRUCTURED_IDENTITY_PRIVACY_DISPOSITION_PATH
REVIEW_DISPOSITION_SHA256 = STRUCTURED_IDENTITY_PRIVACY_DISPOSITION_SHA256
REVIEWED_DESIGN_PATH = "docs/superpowers/specs/2026-08-01-p15-v2-python-exact-imported-symbol-relations-design.md"
REVIEWED_DESIGN_SHA256 = "054f44d4a0a7ab53efa13394b2e471afe04eca1eb92581f01a40d0b3c64d15d5"
REVIEWED_PLAN_PATH = "docs/superpowers/plans/2026-08-01-p15-v2-python-exact-imported-symbol-relations.md"
REVIEWED_PLAN_SHA256 = "c874a8d5bace18aabec54fa94260989bfac3cecf4eadb7e0b6d08275618cbc3b"
REVIEWED_MANIFEST_SHA256 = "7377ddbe8f4bf178e3ba4b531f10f4d0e98f0a5db41e9b4d78bbc77b64f24f69"
REVIEWED_HARNESS_SHA256 = "6baedf2564caeb0f529f6770c6dc5e6c7e0eeb9b30b112943a21a7bb2c47edc0"
REVIEWED_HARNESS_TESTS_SHA256 = "8d74df4dfc9a1037d3d70d356692369f360ac975864dfbdefeb18129fa49a4ee"
TASK0D_REVIEWED_MANIFEST_SHA256 = "2ad6d22522e84eee43054e00fe89ffa22573c8426e9422ab568a90b2c199ac2f"
TASK0D_REVIEWED_HARNESS_SHA256 = "981f904e8e1946424218ebb7a400f08b59e34b5cd6ab957d20087303960bf2e0"
TASK0D_REVIEWED_HARNESS_TESTS_SHA256 = "724ee30ee5a2e4e01d286a923ea1faea1e4ab85cec0870dc767c43994486dec0"
RUNTIME_PRIVACY_REVIEWED_MANIFEST_SHA256 = "116b9b197ad3e4695467fb85b52b26ea4b82f6d6398490f3955643c1addfcd6f"
RUNTIME_PRIVACY_REVIEWED_HARNESS_SHA256 = "df93bb6dbcab5b8a0ff92c49b0d993ad993fea5de87f3d2a5ea2e987c4a477e2"
RUNTIME_PRIVACY_REVIEWED_HARNESS_TESTS_SHA256 = "3dfc250e5225437a57c760d3f70ea59a7a5c8cae22bbd8547675087aac3f9084"
SIGNAL_NAME_REVIEWED_MANIFEST_SHA256 = "a9c7511269a774f903768afc9842a8d6aa62ca650e9e12ab4202c00a1c8c598d"
SIGNAL_NAME_REVIEWED_HARNESS_SHA256 = "11d0d19a15a97740589913bcfd9037fca56d1346a1ec57ad7575a98a01617182"
SIGNAL_NAME_REVIEWED_HARNESS_TESTS_SHA256 = "01f03b4b4c5a50db09038699747056fbd72feef2d6d040b02af481aa46f10df5"
MODULE_METADATA_REVIEWED_MANIFEST_SHA256 = "1561c113e13973109e524688c49a7e498f64338be81b61b040e53e34557d055c"
MODULE_METADATA_REVIEWED_HARNESS_SHA256 = "8646857b98a7e99021a9069702332cf43a61d02cba054676fe3c761b9f7f4e18"
MODULE_METADATA_REVIEWED_HARNESS_TESTS_SHA256 = "709cfde29d0f654b728297cfc889cd59db4646d3407f2d26ebf1797187326725"
STRUCTURED_IDENTITY_REVIEWED_MANIFEST_SHA256 = "1187c823b0aeae8889505d9b775a4d03ce007643372af5410d0d4548f4a78771"
STRUCTURED_IDENTITY_REVIEWED_HARNESS_SHA256 = "0eb4fa6bda0bc2414d908ae1355de0f2b4957ddddd6277d02d11589f6a69c5c5"
STRUCTURED_IDENTITY_REVIEWED_HARNESS_TESTS_SHA256 = "a4792a2405ad6a40d4b900eefff7ab954778f51b1ceb93b3db63e998b862642c"
FROZEN_MAX_PYTHON_IMPORTS_PER_FILE = 256
CLOSED_WORLD_RULE = (
    "For each case, a selected ordinary path is relevant only when frozen as "
    "required or contextual; every other selected ordinary path is noise; no "
    "post-candidate relabeling."
)
CREDIT_RULE = {
    "version": "p15_exact_imported_symbol_chain_v1",
    "required_all": [
        "frozen_named_importfrom_source_fact",
        "preserved_resolved_exact_module_relation_same_target_file_unit",
        "exact_symbol_relation_references_module_relation",
        "unique_active_python_ast_python_type_or_function_same_file_unit_qualified_name",
        "resolved_exact_target_signal_provenance",
        "selected_primary_chunk_equals_target_signal_chunk",
        "selected_result_has_graph_imports_match_and_static_module_dependency",
        "baseline_outside_top12_candidate_inside_top12_no_unrelated_difference",
    ],
    "forbidden_credit": "relation_slot",
}


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_value_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_relative(value: object, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a repository-relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "\\" in value:
        raise ValueError(f"{field} must be a repository-relative path")
    path = ROOT.joinpath(*pure.parts)
    if not path.exists():
        raise ValueError(f"{field} does not exist")
    return path


def _require_sha(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _assert_file_hash(path_value: object, sha_value: object, *, field: str) -> Path:
    path = _resolve_relative(path_value, field=f"{field}.path")
    if _sha256(path) != _require_sha(sha_value, field=f"{field}.sha256"):
        raise ValueError(f"{field} hash changed")
    return path


def _assert_v1_terminal(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "attempt_id",
        "status",
        "reject_index_path",
        "reject_index_sha256",
        "tracked_reject_index_path",
        "tracked_reject_index_sha256",
        "captures_reusable",
    }:
        raise ValueError("v1 terminal schema changed")
    if value != {
        "attempt_id": "p15-v1-attempt-003",
        "status": "task0_hash_reject",
        "reject_index_path": V1_REJECT_INDEX_PATH,
        "reject_index_sha256": V1_REJECT_INDEX_SHA256,
        "tracked_reject_index_path": V1_TRACKED_REJECT_INDEX_PATH,
        "tracked_reject_index_sha256": V1_REJECT_INDEX_SHA256,
        "captures_reusable": False,
    }:
        raise ValueError("v1 terminal identity changed")
    index_path = _assert_file_hash(
        value["reject_index_path"],
        V1_REJECT_INDEX_SHA256,
        field="v1 reject index",
    )
    tracked_index_path = _assert_file_hash(
        value["tracked_reject_index_path"],
        V1_REJECT_INDEX_SHA256,
        field="tracked v1 reject index",
    )
    if index_path.read_bytes() != tracked_index_path.read_bytes():
        raise ValueError("runtime and tracked v1 reject indexes differ")
    index = _read_json(index_path)
    if any(
        (
            index.get("program") != "p15-v1",
            index.get("attempt_id") != "p15-v1-attempt-003",
            index.get("status") != "task0_hash_reject",
            index.get("disposition") != "reject",
            index.get("immutable") is not True,
            index.get("online_started") is not False,
            index.get("heldout_opened") is not False,
            index.get("hash_proceed_marker_created") is not False,
            index.get("new_required_items") != 0,
            index.get("exact_rank_gains") != 0,
        )
    ):
        raise ValueError("v1 terminal disposition changed")
    run_root = index_path.parent
    artifacts = index.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("v1 artifact index is missing")
    actual = {
        str(path.relative_to(run_root))
        for path in run_root.rglob("*")
        if path.is_file() and path != index_path
    }
    if actual != set(artifacts):
        raise ValueError("v1 artifact inventory changed")
    for relative, expected in artifacts.items():
        if _sha256(run_root / relative) != _require_sha(
            expected, field=f"v1 artifact {relative}"
        ):
            raise ValueError(f"v1 artifact changed: {relative}")
    comparison = _read_json(run_root / "oracle/hash/development/comparison.json")
    if comparison.get("disposition") != "reject":
        raise ValueError("v1 comparison no longer rejects")
    if (run_root / "oracle/hash-proceed.json").exists() or (
        run_root / "oracle/online-bge"
    ).exists():
        raise ValueError("v1 terminal evidence grew after reject")
    identities = index.get("identities", {})
    identity_files = {
        "manifest_sha256": ROOT
        / "tests/fixtures/p15_python_import_symbols/input_manifest.json",
        "harness_sha256": ROOT / "tests/p15_python_import_symbol_acceptance.py",
        "harness_tests_sha256": ROOT
        / "tests/test_p15_python_import_symbol_acceptance.py",
    }
    for field, path in identity_files.items():
        if identities.get(field) != _sha256(path):
            raise ValueError(f"v1 {field} changed")


def _assert_product_clean() -> None:
    tracked = subprocess.run(
        ("git", "-C", str(ROOT), "diff", "--quiet", BASELINE, "--", "src/context_search_tool"),
        check=False,
    )
    if tracked.returncode != 0:
        raise ValueError("v2 preflight found a product diff")
    untracked = subprocess.run(
        (
            "git",
            "-C",
            str(ROOT),
            "ls-files",
            "--others",
            "--exclude-standard",
            "src/context_search_tool",
        ),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if untracked:
        raise ValueError("v2 preflight found an untracked product file")


def validate_manifest(path: Path, *, require_zero_evidence: bool = True) -> dict:
    manifest = _read_json(path)
    expected = {
        "schema_version",
        "program",
        "attempt_id",
        "status",
        "capture_authorized",
        "behavior_baseline",
        "design",
        "plan",
        "v1_terminal",
        "protected_characterization",
        "replacement_efficacy_development",
        "heldout_seal",
        "r1",
        "r2",
        "online",
        "review",
        "evidence",
        "closed_world_rule",
    }
    if set(manifest) != expected or manifest.get("schema_version") != 2:
        raise ValueError("P15-v2 skeleton schema is not closed")
    if any(
        (
            manifest["program"] != PROGRAM,
            manifest["attempt_id"] != ATTEMPT_ID,
            manifest["status"] != TASK0D_HASH_CAPTURE_AUTHORIZED_STATUS,
            manifest["capture_authorized"] is not True,
            manifest["behavior_baseline"] != BASELINE,
        )
    ):
        raise ValueError("P15-v2 authorized identity changed")
    for field in ("design", "plan"):
        value = manifest[field]
        if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
            raise ValueError(f"{field} identity schema changed")
        _assert_file_hash(value["path"], value["sha256"], field=field)
    _assert_v1_terminal(manifest["v1_terminal"])

    protected = manifest["protected_characterization"]
    if not isinstance(protected, dict) or set(protected) != {
        "gold_path",
        "gold_sha256",
        "efficacy_credit",
        "sources",
    } or protected["efficacy_credit"] is not False:
        raise ValueError("protected characterization schema changed")
    if (
        protected["gold_path"] != P8_GOLD_PATH
        or protected["gold_sha256"] != P8_GOLD_SHA256
    ):
        raise ValueError("protected P8 gold hard anchor changed")
    gold_path = _assert_file_hash(P8_GOLD_PATH, P8_GOLD_SHA256, field="P8 gold")
    gold = _read_json(gold_path)
    if (
        _json_value_sha256(gold.get("cases")) != P8_CASES_SHA256
        or _json_value_sha256(gold.get("sources")) != P8_SOURCES_SHA256
        or len(gold.get("cases", ())) != 18
        or sum(case.get("repo") == "redink" for case in gold["cases"]) != 6
        or sum(case.get("repo") == "daily" for case in gold["cases"]) != 12
        or sum(
            len(case.get("required", ()))
            for case in gold["cases"]
            if case.get("repo") == "redink"
        )
        != 17
        or sum(
            len(case.get("required", ()))
            for case in gold["cases"]
            if case.get("repo") == "daily"
        )
        != 40
    ):
        raise ValueError("protected P8 roster or case projection changed")
    if set(protected["sources"]) != {"redink", "daily"}:
        raise ValueError("protected source roster changed")
    for name, source in protected["sources"].items():
        frozen = gold["sources"][name]
        if source.get("role") != "protected_characterization" or any(
            source.get(field) != frozen[field]
            for field in (
                "url",
                "commit",
                "selected_count",
                "inventory_sha256",
                "content_sha256",
            )
        ):
            raise ValueError(f"protected {name} identity changed")

    replacements = manifest["replacement_efficacy_development"]
    if not isinstance(replacements, dict) or set(replacements) != {
        "required_count",
        "roster_contract_path",
        "roster_contract_sha256",
        "seal_hashes_path",
        "seal_hashes_sha256",
        "release_digests_verified",
        "slots",
    } or replacements["required_count"] != 2 or replacements["release_digests_verified"] is not True:
        raise ValueError("replacement efficacy roster changed")
    if replacements["roster_contract_sha256"] != ROSTER_CONTRACT_SHA256:
        raise ValueError("replacement roster hard anchor changed")
    if replacements["seal_hashes_sha256"] != SEAL_HASHES_SHA256:
        raise ValueError("replacement seal hashes hard anchor changed")
    roster_path = _assert_file_hash(
        replacements["roster_contract_path"],
        ROSTER_CONTRACT_SHA256,
        field="replacement roster contract",
    )
    seal_hashes_path = _assert_file_hash(
        replacements["seal_hashes_path"],
        SEAL_HASHES_SHA256,
        field="replacement seal hashes",
    )
    seal_hashes = _read_json(seal_hashes_path)
    roster = _read_json(roster_path)
    if (
        roster.get("roster_id") != "p15-v2-replacement-development-roster-v1"
        or roster.get("efficacy_development")
        != [
            {
                "repository_key": "starlette",
                "seal_id": "p15-v2-dev-starlette-5174d4c-v1",
                "public_contract": ".quality/p15-v2-review-seal/starlette_public_contract.json",
            },
            {
                "repository_key": "requests",
                "seal_id": "p15-v2-dev-requests-414f051-v1",
                "public_contract": ".quality/p15-v2-review-seal/requests_public_contract.json",
            },
        ]
        or roster.get("frozen_behavior")
        != {
            "r1": "unchanged",
            "product_mechanism": "unchanged",
            "ranking_weights_budgets": "unchanged",
            "numeric_r2_credit": "unchanged",
            "top_k": 12,
            "heldout_contract": "unchanged",
        }
        or roster.get("selection_policy", {}).get("oracle_used_for_selection")
        is not False
        or roster.get("selection_policy", {}).get("ollama_used") is not False
        or roster.get("heldout", {}).get("status")
        != "sealed_unopened_unchanged"
        or roster.get("protected_characterization")
        != [
            {
                "repository_key": "redink",
                "commit": "4d48722344594cf00e0498f0e1ed3df9cd4fd6be",
                "gold_policy": "unchanged_from_p15_v1",
            },
            {
                "repository_key": "daily",
                "commit": "487e49e565ffd1b96a7cf4d855f99cee3c981eaa",
                "gold_policy": "unchanged_from_p15_v1",
            },
        ]
    ):
        raise ValueError("replacement roster contract changed")
    slot_schema = {
        "slot",
        "repository_key",
        "role",
        "status",
        "commit",
        "case_count",
        "required_item_denominator",
        "top_k",
        "public_contract_path",
        "public_contract_sha256",
        "sealed_payload_path",
        "sealed_payload_sha256",
        "released_payload_path",
        "released_payload_sha256",
    }
    slots = replacements["slots"]
    if not isinstance(slots, list) or len(slots) != 2:
        raise ValueError("two replacement seals are required")
    if [slot.get("slot") for slot in slots] != ["replacement_a", "replacement_b"]:
        raise ValueError("replacement seal slots changed")
    expected_replacements = {
        "replacement_a": {
            "repository_key": "starlette",
            "commit": "5174d4c8358a6f06aa8056bafd14c2272dab8dd1",
            "seal_id": "p15-v2-dev-starlette-5174d4c-v1",
            "public_contract_path": ".quality/p15-v2-review-seal/starlette_public_contract.json",
            "public_contract_sha256": "d230a78f86ab1225305e454b83a674e391faec5c4c024ee89c050fb6eefc35d8",
            "sealed_payload_path": ".quality/p15-v2-review-seal/starlette_development_payload.json.enc",
            "sealed_payload_sha256": "39e322da78cc0bc3fd863a1cdf34650102e459b0279231c0a6c6fca699c0c8fb",
            "released_payload_path": ".quality/p15-v2-review-seal/starlette_development_payload.released.json",
            "released_payload_sha256": "309388945b12fb9becc15e2d037d85bfc7f09299f469dde5d8d5a8642fcd6182",
        },
        "replacement_b": {
            "repository_key": "requests",
            "commit": "414f0513c33883adf6f2b46901d4f0b38a455851",
            "seal_id": "p15-v2-dev-requests-414f051-v1",
            "public_contract_path": ".quality/p15-v2-review-seal/requests_public_contract.json",
            "public_contract_sha256": "19a116a434debaba3dde6dfbeb3848d5a298477f79280be06d0c982c1a2ede51",
            "sealed_payload_path": ".quality/p15-v2-review-seal/requests_development_payload.json.enc",
            "sealed_payload_sha256": "71e203e4af21bac7092525b00205b2a56d15de9f20ac9700516e561729b20821",
            "released_payload_path": ".quality/p15-v2-review-seal/requests_development_payload.released.json",
            "released_payload_sha256": "cfa75bd1cf2cba1b4456fbf590c02fe85fd418d0e1e1c4032e880c569fd7f1ee",
        },
    }
    for slot in slots:
        expected_slot = expected_replacements[slot["slot"]]
        if set(slot) != slot_schema or any(
            (
                slot["role"] != "efficacy_development",
                slot["status"] != "sealed_development_released_digest_verified",
                slot["repository_key"] != expected_slot["repository_key"],
                slot["commit"] != expected_slot["commit"],
                slot["case_count"] != 4,
                slot["required_item_denominator"] != 12,
                slot["top_k"] != 12,
                any(
                    slot[field] != expected_slot[field]
                    for field in (
                        "public_contract_path",
                        "public_contract_sha256",
                        "sealed_payload_path",
                        "sealed_payload_sha256",
                        "released_payload_path",
                        "released_payload_sha256",
                    )
                ),
            )
        ):
            raise ValueError("replacement seal binding changed")
        contract_path = _assert_file_hash(
            slot["public_contract_path"],
            slot["public_contract_sha256"],
            field=f"{slot['repository_key']} public contract",
        )
        _assert_file_hash(
            slot["sealed_payload_path"],
            slot["sealed_payload_sha256"],
            field=f"{slot['repository_key']} sealed payload",
        )
        released_path = _assert_file_hash(
            slot["released_payload_path"],
            slot["released_payload_sha256"],
            field=f"{slot['repository_key']} released payload",
        )
        contract = _read_json(contract_path)
        sealed = contract.get("sealed_payload", {})
        source = contract.get("source", {})
        admissibility = contract.get("admissibility", {})
        if any(
            (
                contract.get("seal_id") != expected_slot["seal_id"],
                contract.get("status")
                != "sealed_development_ready_for_release",
                source.get("repository_key") != slot["repository_key"],
                source.get("repository_role") != "efficacy_development",
                source.get("commit") != slot["commit"],
                sealed.get("cipher") != "aes-256-cbc",
                sealed.get("kdf") != "pbkdf2-hmac-sha256",
                sealed.get("iterations") != 600000,
                sealed.get("salted") is not True,
                sealed.get("round_trip_verified") is not True,
                sealed.get("ciphertext_sha256")
                != slot["sealed_payload_sha256"],
                sealed.get("plaintext_sha256")
                != slot["released_payload_sha256"],
                admissibility.get("top_k") != 12,
                admissibility.get("case_count") != 4,
                admissibility.get("required_item_denominator") != 12,
                admissibility.get("oracle_executed_before_seal") is not False,
                admissibility.get("gold_adjusted_after_oracle") is not False,
                admissibility.get("click_heldout_accessed") is not False,
            )
        ):
            raise ValueError("replacement public contract changed")
        sealed_hash_entry = seal_hashes.get(slot["repository_key"], {})
        if sealed_hash_entry != {
            "public_contract_sha256": slot["public_contract_sha256"],
            "payload_plaintext_sha256": slot["released_payload_sha256"],
            "payload_ciphertext_sha256": slot["sealed_payload_sha256"],
        } or seal_hashes.get("roster_contract_sha256") != ROSTER_CONTRACT_SHA256:
            raise ValueError("replacement seal-hashes manifest changed")
        released = _read_json(released_path)
        if (
            released.get("schema_version") != 1
            or released.get("seal_id") != expected_slot["seal_id"]
            or not isinstance(released.get("cases"), list)
            or len(released["cases"]) != 4
            or sum(len(case.get("required", ())) for case in released["cases"])
            != 12
            or released.get("frozen_contract", {}).get("closed_world_rule")
            != CLOSED_WORLD_RULE
            or released.get("frozen_contract", {}).get("oracle_executed_before_seal")
            is not False
            or released.get("frozen_contract", {}).get("gold_adjusted_after_oracle")
            is not False
            or released.get("frozen_contract", {}).get("click_heldout_accessed")
            is not False
        ):
            raise ValueError("replacement released payload schema changed")

    heldout = manifest["heldout_seal"]
    expected_heldout = {
        "seal_id": "p15-heldout-click-00e592c-v2",
        "repository": "pallets/click",
        "commit": "00e592cea702e0b2caa0dee42489fdb1c22cd845",
        "case_count": 4,
        "required_item_denominator": 12,
        "top_k": 12,
        "public_contract_path": ".quality/p15-review-seal/public_contract.json",
        "public_contract_sha256": "a0b881dee27fdc05155139a97d398f22f5a14bb2fb33fc492fb512565753e582",
        "sealed_payload_path": ".quality/p15-review-seal/heldout_payload_v2.json.enc",
        "sealed_plaintext_sha256": "cbe4efbcd88a41f61d643a9200d6acc817fcc4784eaecd575f869a7650b61217",
        "sealed_ciphertext_sha256": "329226be63911c8f7fddd0b6ff9ec6b9a5cd5c2217b3c482964fceab9329d979",
        "status": "sealed_unopened",
        "carry_forward_review": "approved",
    }
    if heldout != expected_heldout:
        raise ValueError("Click held-out contract changed")
    contract_path = _assert_file_hash(
        heldout["public_contract_path"],
        heldout["public_contract_sha256"],
        field="Click public contract",
    )
    _assert_file_hash(
        heldout["sealed_payload_path"],
        heldout["sealed_ciphertext_sha256"],
        field="Click sealed payload",
    )
    contract = _read_json(contract_path)
    if contract.get("seal_id") != heldout["seal_id"] or contract.get("status") != "sealed_unopened":
        raise ValueError("Click public contract is not sealed")

    if manifest["r1"] != {
        "target_kind": "python_declaration",
        "target_signal_kinds": ["type", "function"],
        "relation_kind": "imports",
        "producer": "python_ast",
        "resolution_basis": "exact_python_imported_symbol",
    }:
        raise ValueError("R1 changed")
    if manifest["r2"] != {
        "development_minimum_micro_recall_gain": 0.05,
        "development_minimum_new_required_items": 3,
        "development_minimum_distinct_cases": 3,
        "development_required_efficacy_repository_count": 2,
        "heldout_minimum_new_required_items": 2,
        "heldout_minimum_distinct_cases": 2,
        "maximum_index_regression_ratio": 0.25,
        "maximum_query_regression_ratio": 0.1,
        "minimum_query_regression_seconds": 0.005,
        "required_loss_limit": 0,
        "noise_growth_limit": 0,
        "top_k": 12,
        "credit_rule": CREDIT_RULE,
    }:
        raise ValueError("numeric R2 or credit changed")
    if manifest["online"] != {
        "provider": "openai-compatible",
        "model": "Pro/BAAI/bge-m3",
        "dimensions": 1024,
        "base_url": "https://api.siliconflow.cn/v1",
        "planner_enabled": False,
        "tokens_per_minute": 240000,
        "tokens_per_request": 80000,
        "minimum_interval_seconds": 2.0,
        "batching": "p14-bounded-greedy-v1",
    }:
        raise ValueError("online safety identity changed")
    expected_review = {
        "replacement_seals": "hash_bound_release_digests_verified",
        "design": "approved",
        "plan": "approved",
        "click_carry_forward": "approved",
        "independent_disposition_path": PLAN_REVIEW_DISPOSITION_PATH,
        "independent_disposition_sha256": PLAN_REVIEW_DISPOSITION_SHA256,
        "task0d_engine_disposition_path": TASK0D_ENGINE_DISPOSITION_PATH,
        "task0d_engine_disposition_sha256": TASK0D_ENGINE_DISPOSITION_SHA256,
        "task0d_runtime_privacy_fix_disposition_path": RUNTIME_PRIVACY_FIX_DISPOSITION_PATH,
        "task0d_runtime_privacy_fix_disposition_sha256": RUNTIME_PRIVACY_FIX_DISPOSITION_SHA256,
        "task0d_signal_name_privacy_fix_disposition_path": SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_PATH,
        "task0d_signal_name_privacy_fix_disposition_sha256": SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_SHA256,
        "task0d_module_metadata_privacy_fix_disposition_path": MODULE_METADATA_PRIVACY_FIX_DISPOSITION_PATH,
        "task0d_module_metadata_privacy_fix_disposition_sha256": MODULE_METADATA_PRIVACY_FIX_DISPOSITION_SHA256,
        "task0d_structured_identity_privacy_disposition_path": STRUCTURED_IDENTITY_PRIVACY_DISPOSITION_PATH,
        "task0d_structured_identity_privacy_disposition_sha256": STRUCTURED_IDENTITY_PRIVACY_DISPOSITION_SHA256,
    }
    if manifest["review"] != expected_review:
        raise ValueError("independent review closure changed")
    disposition_path = _assert_file_hash(
        PLAN_REVIEW_DISPOSITION_PATH,
        PLAN_REVIEW_DISPOSITION_SHA256,
        field="independent review disposition",
    )
    if disposition_path.stat().st_mode & 0o777 != 0o444:
        raise ValueError("independent review disposition is not read-only")
    disposition = _read_json(disposition_path)
    reviewed_candidate = disposition.get("reviewed_candidate")
    if reviewed_candidate != {
        "design": {"path": REVIEWED_DESIGN_PATH, "sha256": REVIEWED_DESIGN_SHA256},
        "plan": {"path": REVIEWED_PLAN_PATH, "sha256": REVIEWED_PLAN_SHA256},
        "manifest": {
            "path": "tests/fixtures/p15_v2_python_import_symbols/input_manifest.json",
            "sha256": REVIEWED_MANIFEST_SHA256,
        },
        "harness": {
            "path": "tests/p15_v2_python_import_symbol_acceptance.py",
            "sha256": REVIEWED_HARNESS_SHA256,
        },
        "harness_tests": {
            "path": "tests/test_p15_v2_python_import_symbol_acceptance.py",
            "sha256": REVIEWED_HARNESS_TESTS_SHA256,
        },
    }:
        raise ValueError("independent review candidate binding changed")
    if any(
        (
            disposition.get("program") != PROGRAM,
            disposition.get("attempt_id") != ATTEMPT_ID,
            disposition.get("disposition") != "approved",
            disposition.get("blocking_findings") != [],
            disposition.get("reviewer", {}).get(
                "independent_from_implementation_executor"
            )
            is not True,
            disposition.get("heldout", {}).get("status") != "sealed_unopened",
            disposition.get("heldout", {}).get("carry_forward_review")
            != "approved",
            disposition.get("heldout", {}).get("opened_during_review")
            is not False,
            disposition.get("verification", {}).get("v2_run_root_state")
            != "absent",
            disposition.get("verification", {}).get("click_open_record_state")
            != "absent",
            disposition.get("verification", {}).get("online_model_calls") != 0,
            disposition.get("verification", {}).get("ollama_calls") != 0,
            disposition.get("verification", {}).get("local_model_calls") != 0,
            disposition.get("verification", {}).get("click_decryption_attempts")
            != 0,
            disposition.get("capture_authorization_boundary", {}).get(
                "online_before_hash_proceed"
            )
            is not False,
            disposition.get("capture_authorization_boundary", {}).get(
                "product_changes_before_task0_proceed"
            )
            is not False,
            disposition.get("capture_authorization_boundary", {}).get(
                "click_open_before_candidate_freeze_and_preopen_gates"
            )
            is not False,
            disposition.get("capture_authorization_boundary", {}).get(
                "ollama_or_local_model_use"
            )
            is not False,
            disposition.get("write_policy")
            != "write_new_only_never_overwrite_or_reinterpret",
        )
    ):
        raise ValueError("independent review disposition changed")
    engine_disposition_path = _assert_file_hash(
        TASK0D_ENGINE_DISPOSITION_PATH,
        TASK0D_ENGINE_DISPOSITION_SHA256,
        field="Task0D engine disposition",
    )
    if engine_disposition_path.stat().st_mode & 0o777 != 0o444:
        raise ValueError("Task0D engine disposition is not read-only")
    engine_disposition = _read_json(engine_disposition_path)
    if engine_disposition.get("reviewed_candidate") != {
        "design": {"path": REVIEWED_DESIGN_PATH, "sha256": REVIEWED_DESIGN_SHA256},
        "plan": {"path": REVIEWED_PLAN_PATH, "sha256": REVIEWED_PLAN_SHA256},
        "manifest": {
            "path": "tests/fixtures/p15_v2_python_import_symbols/input_manifest.json",
            "sha256": TASK0D_REVIEWED_MANIFEST_SHA256,
        },
        "harness": {
            "path": "tests/p15_v2_python_import_symbol_acceptance.py",
            "sha256": TASK0D_REVIEWED_HARNESS_SHA256,
        },
        "harness_tests": {
            "path": "tests/test_p15_v2_python_import_symbol_acceptance.py",
            "sha256": TASK0D_REVIEWED_HARNESS_TESTS_SHA256,
        },
        "prior_plan_harness_disposition": {
            "path": PLAN_REVIEW_DISPOSITION_PATH,
            "sha256": PLAN_REVIEW_DISPOSITION_SHA256,
        },
    }:
        raise ValueError("Task0D engine reviewed-candidate binding changed")
    if any(
        (
            engine_disposition.get("program") != PROGRAM,
            engine_disposition.get("attempt_id") != ATTEMPT_ID,
            engine_disposition.get("disposition") != "approved",
            engine_disposition.get("blocking_findings") != [],
            engine_disposition.get("reviewer", {}).get(
                "independent_from_implementation_executor"
            )
            is not True,
            engine_disposition.get("engine_review", {}).get(
                "product_free_hash_only"
            )
            is not True,
            engine_disposition.get("engine_review", {}).get(
                "source_body_evidence_forbidden"
            )
            is not True,
            engine_disposition.get("verification", {}).get(
                "v2_run_root_state"
            )
            != "absent",
            engine_disposition.get("verification", {}).get(
                "click_open_record_state"
            )
            != "absent",
            engine_disposition.get("verification", {}).get(
                "actual_capture_calls"
            )
            != 0,
            engine_disposition.get("capture_authorization_boundary", {}).get(
                "approved_next_transition"
            )
            != "bind this exact disposition path and SHA-256 into the post-review manifest and harness, set Task0D hash capture authorization only, then rerun a zero-evidence closure check",
            engine_disposition.get("write_policy")
            != "write_new_only_never_overwrite_or_reinterpret",
        )
    ):
        raise ValueError("Task0D engine disposition changed")
    privacy_disposition_path = _assert_file_hash(
        RUNTIME_PRIVACY_FIX_DISPOSITION_PATH,
        RUNTIME_PRIVACY_FIX_DISPOSITION_SHA256,
        field="Task0D runtime privacy-fix disposition",
    )
    if privacy_disposition_path.stat().st_mode & 0o777 != 0o444:
        raise ValueError("Task0D runtime privacy-fix disposition is not read-only")
    privacy_disposition = _read_json(privacy_disposition_path)
    if privacy_disposition.get("reviewed_candidate") != {
        "design": {"path": REVIEWED_DESIGN_PATH, "sha256": REVIEWED_DESIGN_SHA256},
        "plan": {"path": REVIEWED_PLAN_PATH, "sha256": REVIEWED_PLAN_SHA256},
        "manifest": {
            "path": "tests/fixtures/p15_v2_python_import_symbols/input_manifest.json",
            "sha256": RUNTIME_PRIVACY_REVIEWED_MANIFEST_SHA256,
        },
        "harness": {
            "path": "tests/p15_v2_python_import_symbol_acceptance.py",
            "sha256": RUNTIME_PRIVACY_REVIEWED_HARNESS_SHA256,
        },
        "harness_tests": {
            "path": "tests/test_p15_v2_python_import_symbol_acceptance.py",
            "sha256": RUNTIME_PRIVACY_REVIEWED_HARNESS_TESTS_SHA256,
        },
        "prior_plan_harness_disposition": {
            "path": PLAN_REVIEW_DISPOSITION_PATH,
            "sha256": PLAN_REVIEW_DISPOSITION_SHA256,
        },
        "prior_task0d_engine_disposition": {
            "path": TASK0D_ENGINE_DISPOSITION_PATH,
            "sha256": TASK0D_ENGINE_DISPOSITION_SHA256,
        },
    }:
        raise ValueError("Task0D runtime privacy-fix binding changed")
    if any(
        (
            privacy_disposition.get("program") != PROGRAM,
            privacy_disposition.get("attempt_id") != ATTEMPT_ID,
            privacy_disposition.get("disposition") != "approved",
            privacy_disposition.get("blocking_findings") != [],
            privacy_disposition.get("reviewer", {}).get(
                "independent_from_implementation_executor"
            )
            is not True,
            privacy_disposition.get("runtime_privacy_fix_review", {}).get(
                "traversal_path_representation"
            )
            != "tuple_of_string_or_integer_segments",
            privacy_disposition.get("runtime_privacy_fix_review", {}).get(
                "mapping_keys_never_exempt"
            )
            is not True,
            privacy_disposition.get("verification", {}).get(
                "v2_run_root_state_before_fix_review"
            )
            != "absent",
            privacy_disposition.get("verification", {}).get(
                "staging_root_state_before_fix_review"
            )
            != "absent",
            privacy_disposition.get("verification", {}).get(
                "click_open_record_state"
            )
            != "absent",
            privacy_disposition.get("verification", {}).get(
                "actual_capture_calls"
            )
            != 0,
            privacy_disposition.get("authorization_boundary", {}).get(
                "approved_next_transition"
            )
            != "bind this exact post-fix disposition path and SHA-256 into the manifest and harness, restore Task0D hash-only authorization, then rerun the complete post-binding zero-evidence preflight",
            privacy_disposition.get("write_policy")
            != "write_new_only_never_overwrite_or_reinterpret",
        )
    ):
        raise ValueError("Task0D runtime privacy-fix disposition changed")
    signal_name_disposition_path = _assert_file_hash(
        SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_PATH,
        SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_SHA256,
        field="Task0D signal-name privacy-fix disposition",
    )
    if signal_name_disposition_path.stat().st_mode & 0o777 != 0o444:
        raise ValueError("Task0D signal-name privacy-fix disposition is not read-only")
    signal_name_disposition = _read_json(signal_name_disposition_path)
    if signal_name_disposition.get("reviewed_candidate") != {
        "design": {"path": REVIEWED_DESIGN_PATH, "sha256": REVIEWED_DESIGN_SHA256},
        "plan": {"path": REVIEWED_PLAN_PATH, "sha256": REVIEWED_PLAN_SHA256},
        "manifest": {
            "path": "tests/fixtures/p15_v2_python_import_symbols/input_manifest.json",
            "sha256": SIGNAL_NAME_REVIEWED_MANIFEST_SHA256,
        },
        "harness": {
            "path": "tests/p15_v2_python_import_symbol_acceptance.py",
            "sha256": SIGNAL_NAME_REVIEWED_HARNESS_SHA256,
        },
        "harness_tests": {
            "path": "tests/test_p15_v2_python_import_symbol_acceptance.py",
            "sha256": SIGNAL_NAME_REVIEWED_HARNESS_TESTS_SHA256,
        },
        "prior_plan_harness_disposition": {
            "path": PLAN_REVIEW_DISPOSITION_PATH,
            "sha256": PLAN_REVIEW_DISPOSITION_SHA256,
        },
        "prior_task0d_engine_disposition": {
            "path": TASK0D_ENGINE_DISPOSITION_PATH,
            "sha256": TASK0D_ENGINE_DISPOSITION_SHA256,
        },
        "prior_runtime_privacy_fix_disposition": {
            "path": RUNTIME_PRIVACY_FIX_DISPOSITION_PATH,
            "sha256": RUNTIME_PRIVACY_FIX_DISPOSITION_SHA256,
        },
    }:
        raise ValueError("Task0D signal-name privacy-fix binding changed")
    if any(
        (
            signal_name_disposition.get("program") != PROGRAM,
            signal_name_disposition.get("attempt_id") != ATTEMPT_ID,
            signal_name_disposition.get("disposition") != "approved",
            signal_name_disposition.get("blocking_findings") != [],
            signal_name_disposition.get("reviewer", {}).get(
                "independent_from_implementation_executor"
            )
            is not True,
            signal_name_disposition.get(
                "signal_name_privacy_fix_review", {}
            ).get("mapping_keys_exempt")
            is not False,
            signal_name_disposition.get(
                "signal_name_privacy_fix_review", {}
            ).get("declaration_name_rebuilt_from_frozen_ast")
            is not True,
            signal_name_disposition.get("verification", {}).get(
                "v2_run_root_state_after_failure_and_before_review"
            )
            != "absent",
            signal_name_disposition.get("verification", {}).get(
                "staging_root_state_after_failure_and_before_review"
            )
            != "absent",
            signal_name_disposition.get("verification", {}).get(
                "click_open_record_state"
            )
            != "absent",
            signal_name_disposition.get("verification", {}).get(
                "reviewer_capture_calls"
            )
            != 0,
            signal_name_disposition.get("authorization_boundary", {}).get(
                "approved_next_transition"
            )
            != "bind this exact signal-name privacy-fix disposition path and SHA-256 into the manifest and harness, restore Task0D hash-only authorization, then rerun the complete post-binding zero-evidence preflight",
            signal_name_disposition.get("write_policy")
            != "write_new_only_never_overwrite_or_reinterpret",
        )
    ):
        raise ValueError("Task0D signal-name privacy-fix disposition changed")
    module_metadata_disposition_path = _assert_file_hash(
        MODULE_METADATA_PRIVACY_FIX_DISPOSITION_PATH,
        MODULE_METADATA_PRIVACY_FIX_DISPOSITION_SHA256,
        field="Task0D module-metadata privacy-fix disposition",
    )
    if module_metadata_disposition_path.stat().st_mode & 0o777 != 0o444:
        raise ValueError(
            "Task0D module-metadata privacy-fix disposition is not read-only"
        )
    module_metadata_disposition = _read_json(
        module_metadata_disposition_path
    )
    if module_metadata_disposition.get("reviewed_candidate") != {
        "design": {"path": REVIEWED_DESIGN_PATH, "sha256": REVIEWED_DESIGN_SHA256},
        "plan": {"path": REVIEWED_PLAN_PATH, "sha256": REVIEWED_PLAN_SHA256},
        "manifest": {
            "path": "tests/fixtures/p15_v2_python_import_symbols/input_manifest.json",
            "sha256": MODULE_METADATA_REVIEWED_MANIFEST_SHA256,
        },
        "harness": {
            "path": "tests/p15_v2_python_import_symbol_acceptance.py",
            "sha256": MODULE_METADATA_REVIEWED_HARNESS_SHA256,
        },
        "harness_tests": {
            "path": "tests/test_p15_v2_python_import_symbol_acceptance.py",
            "sha256": MODULE_METADATA_REVIEWED_HARNESS_TESTS_SHA256,
        },
        "prior_plan_harness_disposition": {
            "path": PLAN_REVIEW_DISPOSITION_PATH,
            "sha256": PLAN_REVIEW_DISPOSITION_SHA256,
        },
        "prior_task0d_engine_disposition": {
            "path": TASK0D_ENGINE_DISPOSITION_PATH,
            "sha256": TASK0D_ENGINE_DISPOSITION_SHA256,
        },
        "prior_runtime_privacy_fix_disposition": {
            "path": RUNTIME_PRIVACY_FIX_DISPOSITION_PATH,
            "sha256": RUNTIME_PRIVACY_FIX_DISPOSITION_SHA256,
        },
        "prior_signal_name_privacy_fix_disposition": {
            "path": SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_PATH,
            "sha256": SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_SHA256,
        },
    }:
        raise ValueError("Task0D module-metadata privacy-fix binding changed")
    module_review = module_metadata_disposition.get(
        "module_metadata_privacy_fix_review", {}
    )
    boundary = module_metadata_disposition.get("authorization_boundary", {})
    verification = module_metadata_disposition.get("verification", {})
    if any(
        (
            module_metadata_disposition.get("program") != PROGRAM,
            module_metadata_disposition.get("attempt_id") != ATTEMPT_ID,
            module_metadata_disposition.get("disposition") != "approved",
            module_metadata_disposition.get("blocking_findings") != [],
            module_metadata_disposition.get("reviewer", {}).get(
                "independent_from_implementation_executor"
            )
            is not True,
            module_review.get("every_presented_row_independently_reconstructed")
            is not True,
            module_review.get("frozen_max_python_imports_per_file") != 256,
            module_review.get("row_exact_equality_required") is not True,
            verification.get(
                "v2_run_root_state_after_failure_and_before_review"
            )
            != "absent",
            verification.get(
                "staging_root_state_after_failure_and_before_review"
            )
            != "absent",
            verification.get("click_open_record_state") != "absent",
            verification.get("reviewer_capture_calls") != 0,
            verification.get("reviewer_online_model_calls") != 0,
            verification.get("reviewer_ollama_calls") != 0,
            verification.get("reviewer_local_model_calls") != 0,
            boundary.get("approved_next_transition")
            != "bind this exact module-metadata privacy-fix disposition path and SHA-256 into the manifest and harness, restore Task0D hash-only authorization, then rerun the complete post-binding zero-evidence preflight",
            boundary.get("online_before_hash_proceed") is not False,
            boundary.get("product_changes_before_task0_proceed") is not False,
            boundary.get(
                "click_open_before_candidate_freeze_and_preopen_gates"
            )
            is not False,
            boundary.get("ollama_or_local_model_use") is not False,
            module_metadata_disposition.get("write_policy")
            != "write_new_only_never_overwrite_or_reinterpret",
        )
    ):
        raise ValueError("Task0D module-metadata privacy-fix disposition changed")
    structured_identity_disposition_path = _assert_file_hash(
        STRUCTURED_IDENTITY_PRIVACY_DISPOSITION_PATH,
        STRUCTURED_IDENTITY_PRIVACY_DISPOSITION_SHA256,
        field="Task0D structured-identity privacy disposition",
    )
    if structured_identity_disposition_path.stat().st_mode & 0o777 != 0o444:
        raise ValueError(
            "Task0D structured-identity privacy disposition is not read-only"
        )
    structured_identity_disposition = _read_json(
        structured_identity_disposition_path
    )
    if structured_identity_disposition.get("reviewed_candidate") != {
        "design": {"path": REVIEWED_DESIGN_PATH, "sha256": REVIEWED_DESIGN_SHA256},
        "plan": {"path": REVIEWED_PLAN_PATH, "sha256": REVIEWED_PLAN_SHA256},
        "manifest": {
            "path": "tests/fixtures/p15_v2_python_import_symbols/input_manifest.json",
            "sha256": STRUCTURED_IDENTITY_REVIEWED_MANIFEST_SHA256,
        },
        "harness": {
            "path": "tests/p15_v2_python_import_symbol_acceptance.py",
            "sha256": STRUCTURED_IDENTITY_REVIEWED_HARNESS_SHA256,
        },
        "harness_tests": {
            "path": "tests/test_p15_v2_python_import_symbol_acceptance.py",
            "sha256": STRUCTURED_IDENTITY_REVIEWED_HARNESS_TESTS_SHA256,
        },
        "prior_plan_harness_disposition": {
            "path": PLAN_REVIEW_DISPOSITION_PATH,
            "sha256": PLAN_REVIEW_DISPOSITION_SHA256,
        },
        "prior_task0d_engine_disposition": {
            "path": TASK0D_ENGINE_DISPOSITION_PATH,
            "sha256": TASK0D_ENGINE_DISPOSITION_SHA256,
        },
        "prior_runtime_privacy_fix_disposition": {
            "path": RUNTIME_PRIVACY_FIX_DISPOSITION_PATH,
            "sha256": RUNTIME_PRIVACY_FIX_DISPOSITION_SHA256,
        },
        "prior_signal_name_privacy_fix_disposition": {
            "path": SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_PATH,
            "sha256": SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_SHA256,
        },
        "prior_module_metadata_privacy_fix_disposition": {
            "path": MODULE_METADATA_PRIVACY_FIX_DISPOSITION_PATH,
            "sha256": MODULE_METADATA_PRIVACY_FIX_DISPOSITION_SHA256,
        },
    }:
        raise ValueError("Task0D structured-identity candidate binding changed")
    structured_review = structured_identity_disposition.get(
        "structured_identity_privacy_review", {}
    )
    adversarial = structured_identity_disposition.get(
        "adversarial_verification", {}
    )
    dry_run = structured_identity_disposition.get("pure_memory_dry_run", {})
    structured_verification = structured_identity_disposition.get(
        "verification", {}
    )
    structured_boundary = structured_identity_disposition.get(
        "authorization_boundary", {}
    )
    if any(
        (
            structured_identity_disposition.get("program") != PROGRAM,
            structured_identity_disposition.get("attempt_id") != ATTEMPT_ID,
            structured_identity_disposition.get("disposition") != "approved",
            structured_identity_disposition.get("blocking_findings") != [],
            structured_identity_disposition.get("reviewer", {}).get(
                "independent_from_implementation_executor"
            )
            is not True,
            structured_review.get("source_privacy_gram_size") != 32,
            structured_review.get("exact_allowlist_tuple_count") != 17,
            structured_review.get("mapping_keys_exempt") is not False,
            structured_review.get("unlisted_value_paths_exempt") is not False,
            structured_review.get(
                "every_allowlisted_tuple_has_downstream_closure"
            )
            is not True,
            structured_review.get("closure_validation_occurs_before_evidence_write")
            is not True,
            adversarial.get("parameterized_allowlist_items") != 17,
            adversarial.get("legal_exact_path_cases_accepted") != 17,
            adversarial.get("displaced_value_cases_rejected") != 17,
            adversarial.get("mapping_key_cases_rejected") != 17,
            adversarial.get("path_token_injection_cases_rejected") != 17,
            adversarial.get("wrong_structured_field_rejected") is not True,
            dry_run.get("time_limit_seconds") != 120,
            dry_run.get("variants") != ["baseline", "oracle"],
            dry_run.get("profile") != "hash",
            dry_run.get("planner_enabled") is not False,
            dry_run.get("formal_evidence_written") is not False,
            dry_run.get("observed_source_overlap_patterns") != 17,
            dry_run.get("mapping_key_hits") != 0,
            dry_run.get("uncovered_patterns") != [],
            dry_run.get("extra_allowlist_patterns") != [],
            dry_run.get("privacy_check") != "pass",
            dry_run.get("full_capture_validator") != "pass",
            dry_run.get("embedding_requests") != 0,
            dry_run.get("local_model_calls") != 0,
            structured_verification.get("v2_run_root_state") != "absent",
            structured_verification.get("staging_root_state") != "absent",
            structured_verification.get("click_open_record_state") != "absent",
            structured_verification.get("click_plaintext_state") != "absent",
            structured_verification.get("reviewer_formal_capture_calls") != 0,
            structured_verification.get("reviewer_online_model_calls") != 0,
            structured_verification.get("reviewer_ollama_calls") != 0,
            structured_verification.get("reviewer_local_model_calls") != 0,
            structured_verification.get("reviewer_click_decryption_attempts")
            != 0,
            structured_boundary.get("current_manifest_capture_authorized")
            is not False,
            structured_boundary.get("direct_capture_authorized_by_this_file_alone")
            is not False,
            structured_boundary.get("approved_next_transition")
            != "bind this exact structured-identity privacy disposition path and SHA-256 into the manifest and harness, restore Task0D hash-only authorization, then rerun the complete post-binding zero-evidence preflight",
            structured_boundary.get("online_before_hash_proceed") is not False,
            structured_boundary.get("product_changes_before_task0_proceed")
            is not False,
            structured_boundary.get(
                "click_open_before_candidate_freeze_and_preopen_gates"
            )
            is not False,
            structured_boundary.get("ollama_or_local_model_use") is not False,
            structured_identity_disposition.get("write_policy")
            != "write_new_only_never_overwrite_or_reinterpret",
        )
    ):
        raise ValueError("Task0D structured-identity privacy disposition changed")
    if manifest["design"] != {
        "path": REVIEWED_DESIGN_PATH,
        "sha256": REVIEWED_DESIGN_SHA256,
    } or manifest["plan"] != {
        "path": REVIEWED_PLAN_PATH,
        "sha256": REVIEWED_PLAN_SHA256,
    }:
        raise ValueError("reviewed design or plan binding changed")
    evidence = manifest["evidence"]
    if evidence != {
        "run_root": ".quality/p15-runs/p15-v2-attempt-001",
        "required_initial_state": "absent",
        "v1_capture_import_allowed": False,
        "write_policy": "write_new_only",
    }:
        raise ValueError("v2 evidence identity changed")
    run_root = ROOT / evidence["run_root"]
    if require_zero_evidence and run_root.exists():
        raise ValueError("P15-v2 evidence must start from an absent run root")
    if (ROOT / ".quality/p15-review-seal/heldout-open-record.json").exists():
        raise ValueError("Click held-out was opened before v2 candidate freeze")
    if manifest["closed_world_rule"] != CLOSED_WORLD_RULE:
        raise ValueError("closed-world rule changed")
    _assert_product_clean()
    return manifest


CAPTURE_CORPORA = "development_and_protected"
CAPTURE_REPOSITORIES = ("starlette", "requests", "redink", "daily")
EFFICACY_REPOSITORIES = frozenset(("starlette", "requests"))
SOURCE_ROLES = {
    "starlette": "efficacy_development",
    "requests": "efficacy_development",
    "redink": "protected_characterization",
    "daily": "protected_characterization",
}
PROCESS_INVOCATION_ID = secrets.token_hex(32)


def _v1_harness():
    return importlib.import_module("p15_python_import_symbol_acceptance")


def _capture_active_python_signal_chunks(
    connection: sqlite3.Connection,
) -> list[dict]:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT signals.signal_id, signals.chunk_id, signals.file_path,
               signals.kind, signals.name, signals.qualified_name,
               signals.signature, signals.arity, signals.project_unit_key,
               signals.producer, signals.start_line, signals.start_column,
               signals.end_line, signals.end_column, signals.language,
               signals.recallable, signals.deleted_at AS signal_deleted_at,
               chunks.chunk_id AS active_chunk_id,
               chunks.file_path AS chunk_file_path,
               chunks.start_line AS chunk_start_line,
               chunks.end_line AS chunk_end_line,
               chunks.content AS chunk_content,
               chunks.deleted_at AS chunk_deleted_at
        FROM code_signals signals
        LEFT JOIN chunks
          ON chunks.chunk_id = signals.chunk_id
        WHERE signals.deleted_at IS NULL
          AND signals.language = 'python'
          AND (
            (signals.producer = 'python_ast'
             AND signals.kind IN ('type', 'function'))
            OR
            (signals.producer = 'core_module' AND signals.kind = 'module')
          )
        ORDER BY signals.signal_id
        """
    ).fetchall()
    return [
        {
            "signal": {
                "signal_id": row["signal_id"],
                "chunk_id": row["chunk_id"],
                "file_path": row["file_path"],
                "kind": row["kind"],
                "name": row["name"],
                "qualified_name": row["qualified_name"],
                "signature": row["signature"],
                "arity": row["arity"],
                "project_unit_key": row["project_unit_key"],
                "producer": row["producer"],
                "start_line": row["start_line"],
                "start_column": row["start_column"],
                "end_line": row["end_line"],
                "end_column": row["end_column"],
                "language": row["language"],
                "recallable": row["recallable"],
                "deleted_at": row["signal_deleted_at"],
            },
            "chunk": {
                "chunk_id": row["active_chunk_id"],
                "file_path": row["chunk_file_path"],
                "start_line": row["chunk_start_line"],
                "end_line": row["chunk_end_line"],
                "content_sha256": (
                    hashlib.sha256(row["chunk_content"].encode("utf-8")).hexdigest()
                    if isinstance(row["chunk_content"], str)
                    else None
                ),
                "deleted_at": row["chunk_deleted_at"],
            },
        }
        for row in rows
    ]


def _capture_causal_relations(workspace: Path) -> list[dict]:
    database = workspace / ".context-search/index.sqlite"
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT relations.relation_id, relations.source_signal_id,
                   relations.kind, relations.target_kind,
                   relations.target_qualified_name, relations.target_signature,
                   relations.target_arity, relations.target_project_unit_key,
                   relations.target_signal_id, relations.resolution,
                   relations.producer, relations.metadata,
                   sources.file_path AS source_file_path,
                   sources.kind AS source_kind,
                   sources.qualified_name AS source_qualified_name,
                   sources.signature AS source_signature,
                   sources.start_line AS source_start_line,
                   sources.start_column AS source_start_column,
                   sources.end_line AS source_end_line,
                   sources.end_column AS source_end_column,
                   sources.producer AS source_producer,
                   sources.project_unit_key AS source_project_unit_key,
                   sources.chunk_id AS source_chunk_id,
                   sources.language AS source_language,
                   targets.file_path AS target_file_path,
                   targets.kind AS target_signal_kind,
                   targets.qualified_name AS target_signal_qualified_name,
                   targets.signature AS target_signal_signature,
                   targets.start_line AS target_start_line,
                   targets.start_column AS target_start_column,
                   targets.end_line AS target_end_line,
                   targets.end_column AS target_end_column,
                   targets.producer AS target_producer,
                   targets.project_unit_key AS target_project_unit_key_actual,
                   targets.chunk_id AS target_chunk_id,
                   targets.language AS target_language,
                   (
                     SELECT COUNT(*) FROM code_signals peers
                     WHERE peers.deleted_at IS NULL
                       AND peers.file_path = targets.file_path
                       AND peers.project_unit_key = targets.project_unit_key
                       AND peers.producer = 'python_ast'
                       AND peers.language = 'python'
                       AND peers.kind IN ('type', 'function')
                       AND peers.qualified_name = targets.qualified_name
                   ) AS target_uniqueness_count
            FROM code_relations relations
            JOIN code_signals sources
              ON sources.signal_id = relations.source_signal_id
             AND sources.deleted_at IS NULL
            JOIN code_signals targets
              ON targets.signal_id = relations.target_signal_id
             AND targets.deleted_at IS NULL
            WHERE relations.deleted_at IS NULL
              AND relations.kind = 'imports'
              AND relations.producer = 'python_ast'
              AND relations.resolution = 'resolved_exact'
              AND json_extract(relations.metadata, '$.resolution_basis')
                  = 'exact_python_imported_symbol'
            ORDER BY relations.relation_id
            """
        ).fetchall()
    signal_fields = (
        "file_path",
        "kind",
        "qualified_name",
        "signature",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        "producer",
        "project_unit_key",
        "chunk_id",
        "language",
    )
    captured = []
    for row in rows:
        source = {
            field: row[f"source_{field}"] for field in signal_fields
        }
        target = {
            field: row[
                "target_project_unit_key_actual"
                if field == "project_unit_key"
                else f"target_{'signal_' if field in {'kind', 'qualified_name', 'signature'} else ''}{field}"
            ]
            for field in signal_fields
        }
        captured.append(
            {
                "relation": {
                    "relation_id": row["relation_id"],
                    "source_signal_id": row["source_signal_id"],
                    "kind": row["kind"],
                    "target_kind": row["target_kind"],
                    "target_qualified_name": row["target_qualified_name"],
                    "target_signature": row["target_signature"],
                    "target_arity": row["target_arity"],
                    "target_project_unit_key": row[
                        "target_project_unit_key"
                    ],
                    "target_signal_id": row["target_signal_id"],
                    "resolution": row["resolution"],
                    "producer": row["producer"],
                    "metadata_json": row["metadata"],
                },
                "source_signal": source,
                "target_signal": target,
                "target_uniqueness_count": row["target_uniqueness_count"],
            }
        )
    return captured


def _capture_inputs(manifest: dict) -> dict:
    p8_runner = importlib.import_module("p8_real_python_graphs_acceptance")
    protected_gold = _read_json(ROOT / P8_GOLD_PATH)
    cases: list[dict] = []
    contracts: dict[str, dict] = {}
    source_specs: dict[str, dict] = {}
    source_directories: dict[str, Path] = {}
    replacement_payload_sha256: dict[str, str] = {}

    for slot in manifest["replacement_efficacy_development"]["slots"]:
        repository = slot["repository_key"]
        released = _read_json(ROOT / slot["released_payload_path"])
        source = released["source"]
        replacement_payload_sha256[repository] = slot["released_payload_sha256"]
        for frozen_case in released["cases"]:
            case = deepcopy(frozen_case)
            case["repo"] = repository
            cases.append(case)
            contracts[case["id"]] = {
                "evidence_role": "efficacy_development",
                "protected_winner": case["protected_winner"],
                "membership_change_eligible": bool(
                    case["membership_change_eligible"]
                ),
            }
        source_specs[repository] = {
            "dir_name": repository,
            "patterns": tuple(source["include"]),
            "expected_count": source["selected_count"],
            "inventory_sha256": source["inventory_sha256"],
            "content_sha256": source["content_sha256"],
        }
        source_directories[repository] = ROOT / ".quality/p15-sources" / repository

    for repository in ("redink", "daily"):
        cases.extend(
            deepcopy(case)
            for case in protected_gold["cases"]
            if case["repo"] == repository
        )
        for case in protected_gold["cases"]:
            if case["repo"] == repository:
                contracts[case["id"]] = {
                    "evidence_role": "protected_characterization",
                    "protected_winner": None,
                    "membership_change_eligible": None,
                }
        source_specs[repository] = deepcopy(p8_runner.SOURCES[repository])
        source_directories[repository] = (
            ROOT / ".quality/p14-sources" / source_specs[repository]["dir_name"]
        )

    case_projection_sha256 = _json_value_sha256(cases)
    input_identity = {
        "protected_gold_sha256": P8_GOLD_SHA256,
        "protected_cases_projection_sha256": P8_CASES_SHA256,
        "replacement_roster_sha256": ROSTER_CONTRACT_SHA256,
        "replacement_seal_hashes_sha256": SEAL_HASHES_SHA256,
        "replacement_payload_sha256": replacement_payload_sha256,
        "combined_cases_projection_sha256": case_projection_sha256,
        "case_count": len(cases),
        "required_item_count": {
            repository: sum(
                len(case["required"])
                for case in cases
                if case["repo"] == repository
            )
            for repository in CAPTURE_REPOSITORIES
        },
    }
    if input_identity["case_count"] != 26 or input_identity[
        "required_item_count"
    ] != {"starlette": 12, "requests": 12, "redink": 17, "daily": 40}:
        raise ValueError("v2 capture case roster changed")
    if tuple(source_specs) != CAPTURE_REPOSITORIES or set(contracts) != {
        case["id"] for case in cases
    }:
        raise ValueError("v2 capture source or case order changed")
    return {
        "gold": {"cases": cases},
        "case_contracts": contracts,
        "source_specs": source_specs,
        "source_directories": source_directories,
        "input_identity": input_identity,
    }


_SOURCE_PRIVACY_GRAM_SIZE = 32
_SOURCE_PRIVACY_BLOOM_BITS = 1 << 27
_STRUCTURED_IDENTITY_PRIVACY_ALLOWLIST = frozenset(
    {
        ("cases", "<case>", "selected", "<int>", "path"),
        (
            "index_projections",
            "<repo>",
            "active_python_signal_chunks",
            "<int>",
            "chunk",
            "file_path",
        ),
        (
            "index_projections",
            "<repo>",
            "active_python_signal_chunks",
            "<int>",
            "signal",
            "file_path",
        ),
        (
            "index_projections",
            "<repo>",
            "active_python_signal_chunks",
            "<int>",
            "signal",
            "name",
        ),
        (
            "index_projections",
            "<repo>",
            "active_python_signal_chunks",
            "<int>",
            "signal",
            "qualified_name",
        ),
        (
            "index_projections",
            "<repo>",
            "causal_relations",
            "<int>",
            "relation",
            "metadata_json",
        ),
        (
            "index_projections",
            "<repo>",
            "causal_relations",
            "<int>",
            "relation",
            "target_qualified_name",
        ),
        (
            "index_projections",
            "<repo>",
            "causal_relations",
            "<int>",
            "source_signal",
            "file_path",
        ),
        (
            "index_projections",
            "<repo>",
            "causal_relations",
            "<int>",
            "source_signal",
            "qualified_name",
        ),
        (
            "index_projections",
            "<repo>",
            "causal_relations",
            "<int>",
            "target_signal",
            "file_path",
        ),
        (
            "index_projections",
            "<repo>",
            "causal_relations",
            "<int>",
            "target_signal",
            "qualified_name",
        ),
        (
            "index_projections",
            "<repo>",
            "exact_targets",
            "<int>",
            "target_file_path",
        ),
        (
            "index_projections",
            "<repo>",
            "module_relations",
            "<int>",
            "metadata_json",
        ),
        (
            "index_projections",
            "<repo>",
            "module_relations",
            "<int>",
            "source_file_path",
        ),
        (
            "index_projections",
            "<repo>",
            "module_relations",
            "<int>",
            "target_name",
        ),
        (
            "index_projections",
            "<repo>",
            "module_relations",
            "<int>",
            "target_qualified_name",
        ),
        (
            "index_projections",
            "<repo>",
            "target_states",
            "<int>",
            "target_file_path",
        ),
    }
)
_SOURCE_PRIVACY_CACHE: dict[
    tuple[tuple[str, str], ...], tuple[tuple[str, ...], bytearray]
] = {}


def _source_gram_bloom_positions(value: str) -> tuple[int, int]:
    hashed = hash(value) & ((1 << 64) - 1)
    mask = _SOURCE_PRIVACY_BLOOM_BITS - 1
    return (
        hashed & mask,
        ((hashed >> 32) ^ (hashed * 0x9E3779B185EBCA87)) & mask,
    )


def _closed_module_relation_metadata(value: str) -> dict | None:
    try:
        metadata = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    keys = {
        "selector_state",
        "specifier",
        "candidates",
        "import_form",
        "relative_level",
        "first_source_line",
        "first_source_column",
        "occurrence_count",
    }
    if not isinstance(metadata, dict) or set(metadata) != keys:
        return None
    state = metadata["selector_state"]
    specifier = metadata["specifier"]
    candidates = metadata["candidates"]
    relative_level = metadata["relative_level"]
    if (
        state not in {"exact", "candidates", "external", "unresolved"}
        or not isinstance(specifier, str)
        or not specifier
        or not isinstance(candidates, list)
        or any(not isinstance(candidate, str) for candidate in candidates)
        or metadata["import_form"] not in {"import", "from"}
        or type(relative_level) is not int
        or relative_level < 0
        or type(metadata["first_source_line"]) is not int
        or metadata["first_source_line"] < 1
        or type(metadata["first_source_column"]) is not int
        or metadata["first_source_column"] < 0
        or type(metadata["occurrence_count"]) is not int
        or metadata["occurrence_count"] < 1
    ):
        return None
    leading_dots = len(specifier) - len(specifier.lstrip("."))
    module = specifier[leading_dots:]
    if relative_level != leading_dots or (
        module and any(not segment.isidentifier() for segment in module.split("."))
    ):
        return None
    if metadata["import_form"] == "import" and relative_level != 0:
        return None
    for candidate in candidates:
        pure = PurePosixPath(candidate)
        if (
            not candidate
            or pure.is_absolute()
            or ".." in pure.parts
            or "\\" in candidate
            or pure.as_posix() != candidate
            or pure.suffix not in {".py", ".pyw"}
        ):
            return None
    if candidates != sorted(set(candidates)):
        return None
    if (
        (state == "exact" and len(candidates) != 1)
        or (state == "candidates" and len(candidates) < 2)
        or (state in {"external", "unresolved"} and candidates)
    ):
        return None
    return metadata


def _frozen_source_privacy_index(
    inputs: dict,
) -> tuple[tuple[str, ...], bytearray]:
    cache_key = tuple(
        (
            str(inputs["source_directories"][repository]),
            str(inputs["source_specs"][repository]["content_sha256"]),
        )
        for repository in CAPTURE_REPOSITORIES
    )
    cached = _SOURCE_PRIVACY_CACHE.get(cache_key)
    if cached is not None:
        return cached
    bodies: list[str] = []
    bloom = bytearray(_SOURCE_PRIVACY_BLOOM_BITS // 8)
    for repository in CAPTURE_REPOSITORIES:
        root = inputs["source_directories"][repository]
        spec = inputs["source_specs"][repository]
        selected = {
            path
            for pattern in spec["patterns"]
            for path in root.glob(pattern)
            if path.is_file() and not path.is_symlink()
        }
        for path in sorted(selected):
            body = path.read_bytes().decode("utf-8", errors="replace")
            bodies.append(body)
            for start in range(
                max(0, len(body) - _SOURCE_PRIVACY_GRAM_SIZE + 1)
            ):
                gram = body[start : start + _SOURCE_PRIVACY_GRAM_SIZE]
                for position in _source_gram_bloom_positions(gram):
                    bloom[position >> 3] |= 1 << (position & 7)
    cached = (tuple(bodies), bloom)
    _SOURCE_PRIVACY_CACHE[cache_key] = cached
    return cached


def _privacy_check(value: object, *, inputs: dict) -> None:
    _v1_harness()._privacy_check(value)
    bodies, bloom = _frozen_source_privacy_index(inputs)

    def is_source_gram(gram: str) -> bool:
        positions = _source_gram_bloom_positions(gram)
        if any(
            not (bloom[position >> 3] & (1 << (position & 7)))
            for position in positions
        ):
            return False
        return any(gram in body for body in bodies)

    def normalized_structured_path(
        path: tuple[str | int, ...],
    ) -> tuple[str, ...]:
        normalized = [
            "<int>" if type(segment) is int else segment
            for segment in path
        ]
        if (
            len(path) >= 2
            and path[0] == "index_projections"
            and path[1] in CAPTURE_REPOSITORIES
        ):
            normalized[1] = "<repo>"
        elif (
            len(path) >= 2
            and path[0] == "cases"
            and path[1] in inputs["case_contracts"]
        ):
            normalized[1] = "<case>"
        return tuple(normalized)

    def render_path(path: tuple[str | int, ...]) -> str:
        rendered = "root"
        for segment in path:
            rendered += (
                f"[{segment}]" if type(segment) is int else f".{segment}"
            )
        return rendered

    def check(
        candidate: object,
        path: tuple[str | int, ...] = (),
    ) -> None:
        if isinstance(candidate, dict):
            for child_key, child in candidate.items():
                check(child_key, (*path, "<mapping-key>"))
                check(child, (*path, child_key))
            return
        if isinstance(candidate, list):
            for index, child in enumerate(candidate):
                check(child, (*path, index))
            return
        structured_path = normalized_structured_path(path)
        if structured_path == (
            "index_projections",
            "<repo>",
            "module_relations",
            "<int>",
            "metadata_json",
        ):
            if not isinstance(candidate, str) or _closed_module_relation_metadata(
                candidate
            ) is None:
                raise ValueError(
                    f"invalid closed module metadata at {render_path(path)}"
                )
            return
        if not isinstance(candidate, str):
            return
        if structured_path in _STRUCTURED_IDENTITY_PRIVACY_ALLOWLIST:
            return
        fragment = candidate
        if len(fragment) < _SOURCE_PRIVACY_GRAM_SIZE:
            return
        if any(
            is_source_gram(
                fragment[start : start + _SOURCE_PRIVACY_GRAM_SIZE]
            )
            for start in range(
                len(fragment) - _SOURCE_PRIVACY_GRAM_SIZE + 1
            )
        ):
            raise ValueError(f"source-body value at {render_path(path)}")

    check(value)


@contextmanager
def _adapt_v1_capture(inputs: dict, manifest: dict) -> Iterator[Callable]:
    v1 = _v1_harness()
    p8_runner = importlib.import_module("p8_real_python_graphs_acceptance")
    original_validate = v1.validate_manifest
    original_sources_root = v1.DEFAULT_SOURCES
    original_sources = p8_runner.SOURCES
    original_manifest = p8_runner._manifest_or_fail
    original_module_projection = v1._module_projection
    original_overlay_oracle = v1._overlay_oracle
    repository_by_directory = {
        spec["dir_name"]: repository
        for repository, spec in inputs["source_specs"].items()
    }
    module_relations: dict[str, list[dict]] = {}
    active_python_signal_chunks: dict[str, list[dict]] = {}
    proxy_manifest = {
        "behavior_baseline": manifest["behavior_baseline"],
        "development_gold": {
            "sha256": inputs["input_identity"][
                "combined_cases_projection_sha256"
            ]
        },
        "heldout_seal": {
            "public_contract_path": manifest["heldout_seal"][
                "public_contract_path"
            ]
        },
    }
    with tempfile.TemporaryDirectory(prefix="cst-p15-v2-source-registry-") as temporary:
        registry = Path(temporary)
        for repository, spec in inputs["source_specs"].items():
            source = inputs["source_directories"][repository]
            if not source.is_dir():
                raise ValueError(f"frozen source is unavailable: {repository}")
            os.symlink(source.resolve(), registry / spec["dir_name"], target_is_directory=True)

        def audited_module_projection(connection) -> tuple[int, str]:
            count, projection_sha256 = original_module_projection(connection)
            rows = connection.execute(
                """
                SELECT relation_id, source_signal_id, source_chunk_id,
                       source_file_path, target_name, kind, target_kind,
                       target_qualified_name, target_signature, target_arity,
                       target_project_unit_key, target_signal_id, resolution,
                       producer, metadata
                FROM code_relations
                WHERE deleted_at IS NULL AND producer = 'python_ast'
                  AND kind = 'imports' AND target_kind = 'module'
                ORDER BY relation_id
                """
            ).fetchall()
            rendered = [list(row) for row in rows]
            legacy_projection = [
                [row[index] for index in (0, 1, 11, 12, 7, 14)]
                for row in rendered
            ]
            if count != len(rendered) or projection_sha256 != hashlib.sha256(
                v1._canonical(legacy_projection).encode("utf-8")
            ).hexdigest():
                raise ValueError("module relation projection changed during capture")
            database = Path(
                connection.execute("PRAGMA database_list").fetchone()[2]
            )
            repository = repository_by_directory.get(database.parents[1].name)
            if repository is None:
                raise ValueError("module relation repository identity changed")
            captured = [
                {
                    "relation_id": str(row[0]),
                    "source_signal_id": str(row[1]),
                    "source_chunk_id": str(row[2]),
                    "source_file_path": str(row[3]),
                    "target_name": str(row[4]),
                    "kind": str(row[5]),
                    "target_kind": str(row[6]),
                    "target_qualified_name": str(row[7]),
                    "target_signature": str(row[8]),
                    "target_arity": row[9],
                    "target_project_unit_key": str(row[10]),
                    "target_signal_id": str(row[11]),
                    "resolution": str(row[12]),
                    "producer": str(row[13]),
                    "metadata_json": str(row[14]),
                }
                for row in rendered
            ]
            previous = module_relations.setdefault(repository, captured)
            if previous != captured:
                raise ValueError("module relations changed during oracle overlay")
            active_rows = _capture_active_python_signal_chunks(connection)
            previous_active = active_python_signal_chunks.setdefault(
                repository, active_rows
            )
            if previous_active != active_rows:
                raise ValueError(
                    "active Python signal/chunk projection changed during oracle overlay"
                )
            return count, projection_sha256

        def capture_with_module_relations(*args, **kwargs) -> dict:
            raw = v1._capture_development(*args, **kwargs)
            if set(module_relations) != set(CAPTURE_REPOSITORIES):
                raise ValueError("module relation capture is incomplete")
            for repository, rows in module_relations.items():
                projection = raw["index_projections"][repository]
                active_rows = active_python_signal_chunks.get(repository)
                if active_rows is None:
                    raise ValueError(
                        "active Python signal/chunk capture is incomplete"
                    )
                projection["module_relations"] = rows
                projection["active_python_signal_chunks"] = active_rows
                projection["active_python_signal_chunk_count"] = len(
                    active_rows
                )
                projection["active_python_signal_chunk_sha256"] = (
                    _json_value_sha256(active_rows)
                )
                projection.setdefault(
                    "causal_relations", []
                )
            return raw

        def audited_overlay_oracle(workspace: Path) -> dict:
            projection = original_overlay_oracle(workspace)
            projection["causal_relations"] = _capture_causal_relations(workspace)
            return projection

        v1.validate_manifest = lambda _path: proxy_manifest
        v1.DEFAULT_SOURCES = registry
        v1._module_projection = audited_module_projection
        v1._overlay_oracle = audited_overlay_oracle
        p8_runner.SOURCES = inputs["source_specs"]
        p8_runner._manifest_or_fail = lambda: deepcopy(inputs["gold"])
        try:
            yield capture_with_module_relations
        finally:
            v1.validate_manifest = original_validate
            v1.DEFAULT_SOURCES = original_sources_root
            v1._module_projection = original_module_projection
            v1._overlay_oracle = original_overlay_oracle
            p8_runner.SOURCES = original_sources
            p8_runner._manifest_or_fail = original_manifest


def _normalize_v1_capture(
    raw: dict,
    *,
    manifest_path: Path,
    manifest: dict,
    inputs: dict,
    variant: str,
    repeat: int,
    input_order: str,
) -> dict:
    payload = deepcopy(raw)
    payload["schema_version"] = 2
    payload["program"] = PROGRAM
    payload["attempt_id"] = ATTEMPT_ID
    payload["corpora"] = CAPTURE_CORPORA
    payload["slot"] = (
        f"oracle:{CAPTURE_CORPORA}:hash:{variant}:r{repeat}:{input_order}"
    )
    payload["manifest_sha256"] = _sha256(manifest_path)
    payload["harness_sha256"] = _sha256(Path(__file__))
    payload["review_disposition_sha256"] = REVIEW_DISPOSITION_SHA256
    payload["input_identity"] = inputs["input_identity"]
    payload["source_roles"] = SOURCE_ROLES
    payload["implementation"]["process_identity"] = {
        "pid": os.getpid(),
        "invocation_id": PROCESS_INVOCATION_ID,
    }
    payload.pop("development_gold_sha256", None)
    for case_id, case in payload["cases"].items():
        contract = inputs["case_contracts"][case_id]
        case["evidence_role"] = contract["evidence_role"]
        case["protected_winner"] = contract["protected_winner"]
        case["membership_change_eligible"] = contract[
            "membership_change_eligible"
        ]
    for projection in payload["index_projections"].values():
        exact_targets = projection["exact_targets"]
        target_states = projection["target_states"]
        if not isinstance(exact_targets, dict) or not isinstance(
            target_states, dict
        ):
            raise ValueError("Task0D raw path-keyed projection changed")
        projection["exact_targets"] = [
            {"target_file_path": path, "relations": rows}
            for path, rows in sorted(exact_targets.items())
        ]
        projection["target_states"] = [
            {"target_file_path": path, "states": states}
            for path, states in sorted(target_states.items())
        ]
    if payload["profile"] != "hash" or payload["phase"] != "oracle":
        raise ValueError("Task0D accepts hash oracle captures only")
    _privacy_check(payload, inputs=inputs)
    return payload


def _build_hash_capture(
    manifest_path: Path,
    run_root: Path,
    *,
    variant: str,
    repeat: int,
    input_order: str,
) -> dict:
    manifest = validate_manifest(manifest_path, require_zero_evidence=False)
    if manifest["capture_authorized"] is not True:
        raise ValueError("Task0D engine review has not authorized capture")
    if variant not in {"baseline", "oracle"} or repeat not in {1, 2}:
        raise ValueError("invalid Task0D capture slot")
    if input_order not in {"canonical", "reverse"}:
        raise ValueError("invalid Task0D input order")
    inputs = _capture_inputs(manifest)
    with _adapt_v1_capture(inputs, manifest) as capture:
        raw = capture(
            manifest_path,
            run_root=run_root,
            phase="oracle",
            corpora="development",
            profile="hash",
            variant=variant,
            repeat=repeat,
            input_order=input_order,
            implementation_root=ROOT,
        )
    return _normalize_v1_capture(
        raw,
        manifest_path=manifest_path,
        manifest=manifest,
        inputs=inputs,
        variant=variant,
        repeat=repeat,
        input_order=input_order,
    )


def _capture_path(
    run_root: Path, *, variant: str, repeat: int, input_order: str
) -> Path:
    return (
        run_root
        / "oracle/hash"
        / CAPTURE_CORPORA
        / f"{variant}-r{repeat}-{input_order}.json"
    )


def _capture_relative(*, variant: str, repeat: int, input_order: str) -> PurePosixPath:
    return PurePosixPath(
        "oracle/hash",
        CAPTURE_CORPORA,
        f"{variant}-r{repeat}-{input_order}.json",
    )


def _directory_open_flags() -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _open_child_directory(parent_fd: int, name: str, *, create: bool) -> int:
    if not name or name in {".", ".."} or "/" in name:
        raise ValueError("Task0D evidence directory component is invalid")
    try:
        return os.open(name, _directory_open_flags(), dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        return os.open(name, _directory_open_flags(), dir_fd=parent_fd)
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError(
                "Task0D evidence path contains a symlink or non-directory"
            ) from None
        raise


@contextmanager
def _trusted_run_root_fd(
    run_root: Path, manifest: dict, *, create: bool
) -> Iterator[int | None]:
    supplied = _validate_run_root(run_root, manifest)
    relative = supplied.relative_to(ROOT)
    current = os.open(ROOT, _directory_open_flags())
    try:
        for part in relative.parts:
            try:
                child = _open_child_directory(current, part, create=create)
            except FileNotFoundError:
                os.close(current)
                current = -1
                yield None
                return
            os.close(current)
            current = child
        yield current
    finally:
        if current >= 0:
            os.close(current)


@contextmanager
def _trusted_staging_fd() -> Iterator[int]:
    root_fd = os.open(ROOT, _directory_open_flags())
    quality_fd = -1
    staging_fd = -1
    try:
        quality_fd = _open_child_directory(root_fd, ".quality", create=False)
        staging_fd = _open_child_directory(
            quality_fd, ".p15-v2-engine-staging", create=True
        )
        yield staging_fd
    finally:
        for descriptor in (staging_fd, quality_fd, root_fd):
            if descriptor >= 0:
                os.close(descriptor)


@contextmanager
def _relative_parent_fd(
    run_root_fd: int, relative: PurePosixPath, *, create: bool
) -> Iterator[tuple[int, str]]:
    if relative.is_absolute() or ".." in relative.parts or not relative.name:
        raise ValueError("Task0D evidence relative path is invalid")
    current = os.dup(run_root_fd)
    try:
        for part in relative.parts[:-1]:
            child = _open_child_directory(current, part, create=create)
            os.close(current)
            current = child
        yield current, relative.name
    finally:
        os.close(current)


def _read_json_at(run_root_fd: int, relative: PurePosixPath) -> dict:
    with _relative_parent_fd(run_root_fd, relative, create=False) as (
        parent_fd,
        name,
    ):
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ValueError("Task0D evidence entry is not a regular file")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _write_new_json_at(
    run_root_fd: int,
    staging_fd: int,
    relative: PurePosixPath,
    payload: dict,
) -> None:
    with _relative_parent_fd(run_root_fd, relative, create=True) as (
        parent_fd,
        name,
    ):
        stage = f".{name}.stage-{PROCESS_INVOCATION_ID}-{secrets.token_hex(8)}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(stage, flags, 0o600, dir_fd=staging_fd)
        published = False
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(_canonical(payload))
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(
                    stage,
                    name,
                    src_dir_fd=staging_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                raise ValueError("immutable evidence slot already exists") from None
            published = True
            os.fsync(parent_fd)
        finally:
            try:
                os.unlink(stage, dir_fd=staging_fd)
            except FileNotFoundError:
                pass
            if published:
                os.fsync(parent_fd)
            os.fsync(staging_fd)


def _absolute_without_resolving(path: Path) -> Path:
    if ".." in path.parts:
        raise ValueError("Task0D evidence path may not contain parent traversal")
    return Path(os.path.abspath(path))


def _allowed_engine_paths(run_root: Path) -> set[Path]:
    captures = {
        _capture_path(
            run_root,
            variant=variant,
            repeat=repeat,
            input_order=input_order,
        )
        for variant in ("baseline", "oracle")
        for repeat in (1, 2)
        for input_order in ("canonical", "reverse")
    }
    return captures | {
        run_root / "oracle/hash" / CAPTURE_CORPORA / "comparison.json",
        run_root / "oracle/hash-proceed.json",
        run_root / "terminal-reject.json",
    }


def _allowed_engine_relatives() -> set[PurePosixPath]:
    captures = {
        _capture_relative(
            variant=variant, repeat=repeat, input_order=input_order
        )
        for variant in ("baseline", "oracle")
        for repeat in (1, 2)
        for input_order in ("canonical", "reverse")
    }
    return captures | {
        PurePosixPath("oracle/hash", CAPTURE_CORPORA, "comparison.json"),
        PurePosixPath("oracle/hash-proceed.json"),
        PurePosixPath("terminal-reject.json"),
    }


def _inventory_relative_files(run_root_fd: int) -> set[PurePosixPath]:
    actual: set[PurePosixPath] = set()
    for directory, directory_names, file_names, directory_fd in os.fwalk(
        ".", follow_symlinks=False, dir_fd=run_root_fd
    ):
        base = PurePosixPath() if directory == "." else PurePosixPath(directory)
        for name in directory_names:
            mode = os.stat(
                name, dir_fd=directory_fd, follow_symlinks=False
            ).st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ValueError(
                    "Task0D evidence inventory contains an unsafe entry"
                )
        for name in file_names:
            mode = os.stat(
                name, dir_fd=directory_fd, follow_symlinks=False
            ).st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise ValueError(
                    "Task0D evidence inventory contains an unsafe entry"
                )
            actual.add(base / name)
    if not actual <= _allowed_engine_relatives():
        raise ValueError("Task0D evidence inventory contains an unapproved file")
    return actual


def _assert_capture_inventory_fd(run_root_fd: int, *, state: str) -> None:
    actual = _inventory_relative_files(run_root_fd)
    captures = {
        path
        for path in _allowed_engine_relatives()
        if path.name.startswith(("baseline-", "oracle-"))
    }
    comparison = PurePosixPath(
        "oracle/hash", CAPTURE_CORPORA, "comparison.json"
    )
    markers = {
        PurePosixPath("oracle/hash-proceed.json"),
        PurePosixPath("terminal-reject.json"),
    }
    present_markers = actual & markers
    if state == "capture":
        valid = actual <= captures
    elif state == "compare_input":
        valid = not present_markers and (
            actual == captures or actual == captures | {comparison}
        )
    elif state == "terminal":
        valid = (
            len(present_markers) == 1
            and actual == captures | {comparison} | present_markers
        )
    else:
        raise ValueError("unknown Task0D inventory state")
    if not valid:
        raise ValueError(f"Task0D evidence inventory is not valid for {state}")


def _allowed_capture_paths(run_root: Path) -> set[Path]:
    return {
        path
        for path in _allowed_engine_paths(run_root)
        if path.name.startswith(("baseline-", "oracle-"))
    }


def _expected_capture_root_keys() -> set[str]:
    return {
        "schema_version",
        "program",
        "attempt_id",
        "phase",
        "corpora",
        "profile",
        "variant",
        "input_order",
        "repeat",
        "slot",
        "manifest_sha256",
        "harness_sha256",
        "review_disposition_sha256",
        "input_identity",
        "source_roles",
        "product_identity",
        "implementation",
        "embedding",
        "embedding_requests",
        "repositories",
        "index_projections",
        "cases",
        "timing",
        "observed",
    }


def _expected_implementation_identity() -> dict:
    runner = importlib.import_module("p8_real_python_graphs_acceptance")
    return runner.implementation_identity(ROOT)


def _validate_implementation_identity(implementation: object) -> dict:
    expected = _expected_implementation_identity()
    if not isinstance(implementation, dict) or set(implementation) != set(
        expected
    ) | {"process_identity"}:
        raise ValueError("Task0D implementation identity is not closed")
    if {key: implementation[key] for key in expected} != expected:
        raise ValueError("Task0D implementation identity changed")
    process = implementation["process_identity"]
    if (
        not isinstance(process, dict)
        or set(process) != {"pid", "invocation_id"}
        or type(process["pid"]) is not int
        or process["pid"] <= 0
        or not isinstance(process["invocation_id"], str)
        or len(process["invocation_id"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in process["invocation_id"]
        )
    ):
        raise ValueError("Task0D capture process identity is invalid")
    return process


def _frozen_python_inventory_units(
    *, repository: str, inputs: dict, active_signals: dict[str, dict]
) -> tuple[dict[str, str], dict[str, dict]]:
    spec = inputs["source_specs"][repository]
    root = inputs["source_directories"][repository]
    selected = {
        path.relative_to(root).as_posix()
        for pattern in spec["patterns"]
        for path in root.glob(pattern)
        if path.is_file()
        and not path.is_symlink()
    }
    paths = {
        path
        for path in selected
        if PurePosixPath(path).suffix in {".py", ".pyw"}
    }
    modules_by_path = {
        row["signal"]["file_path"]: row
        for row in active_signals.values()
        if row["signal"]["producer"] == "core_module"
        and row["signal"]["kind"] == "module"
    }
    marker_names = {
        "package.json",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "Cargo.toml",
        "pyproject.toml",
    }
    unit_roots = {
        (
            ""
            if PurePosixPath(path).parent == PurePosixPath(".")
            else PurePosixPath(path).parent.as_posix()
        )
        for path in selected
        if PurePosixPath(path).name in marker_names
    } or {""}

    def unit_for_path(path: str) -> str:
        matches = [
            unit
            for unit in unit_roots
            if not unit or path == unit or path.startswith(f"{unit}/")
        ]
        return (
            max(
                matches,
                key=lambda unit: (len(PurePosixPath(unit).parts), unit),
            )
            if matches
            else ""
        )

    units = {path: unit_for_path(path) for path in paths}
    if any(
        path not in units
        or units[path] != row["signal"]["project_unit_key"]
        for path, row in modules_by_path.items()
    ):
        raise ValueError("Task0D frozen Python project-unit projection is inconsistent")
    return units, modules_by_path


def _independent_python_module_selector(
    *,
    source_path: str,
    project_unit_key: str,
    module: str,
    relative_level: int,
    path_units: dict[str, str],
) -> tuple[str, str, tuple[str, ...]]:
    specifier = "." * relative_level + module
    prefix = f"{project_unit_key.rstrip('/')}/" if project_unit_key else ""

    def candidates(base: str, *, package_only: bool = False) -> tuple[str, ...]:
        possible = (
            (f"{base}/__init__.py", f"{base}/__init__.pyw")
            if package_only
            else (
                f"{base}.py",
                f"{base}.pyw",
                f"{base}/__init__.py",
                f"{base}/__init__.pyw",
            )
        )
        return tuple(
            sorted(
                path
                for path in set(possible)
                if path_units.get(path) == project_unit_key
            )
        )

    if relative_level == 0:
        if not module:
            return "unresolved", specifier, ()
        relative = module.replace(".", "/")
        selected = tuple(
            sorted(
                {
                    path
                    for base in (f"{prefix}{relative}", f"{prefix}src/{relative}")
                    for path in candidates(base)
                }
            )
        )
        if not selected:
            return "external", specifier, ()
        return (
            "exact" if len(selected) == 1 else "candidates",
            specifier,
            selected,
        )

    inner = (
        source_path[len(prefix) :]
        if prefix and source_path.startswith(prefix)
        else source_path
    )
    segments = inner.split("/")
    stem = segments[-1]
    for suffix in (".py", ".pyw"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    package = segments[:-1]
    remove = relative_level - 1
    if remove > len(package):
        return "unresolved", specifier, ()
    base_segments = package[: len(package) - remove] if remove else package
    if not base_segments:
        if stem == "__init__" and not package and relative_level == 1 and module:
            selected = candidates(f"{prefix}{module.replace('.', '/')}")
            if selected:
                return (
                    "exact" if len(selected) == 1 else "candidates",
                    specifier,
                    selected,
                )
        return "unresolved", specifier, ()
    base = (
        "/".join(base_segments + module.split("."))
        if module
        else "/".join(base_segments)
    )
    selected = candidates(f"{prefix}{base}", package_only=not module)
    if not selected:
        return "unresolved", specifier, ()
    return (
        "exact" if len(selected) == 1 else "candidates",
        specifier,
        selected,
    )


def _expected_frozen_module_relations(
    *,
    source_active: dict,
    repository: str,
    inputs: dict,
    path_units: dict[str, str],
    modules_by_path: dict[str, dict],
) -> dict[str, dict]:
    source = source_active["signal"]
    source_path = source["file_path"]
    project_unit_key = source["project_unit_key"]
    tree = _frozen_python_tree(inputs, repository, source_path)
    facts: list[tuple[str, str, int, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            facts.extend(
                ("import", alias.name, 0, node.lineno, node.col_offset)
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            relative_level = node.level or 0
            if node.module is not None:
                facts.append(
                    (
                        "from",
                        node.module,
                        relative_level,
                        node.lineno,
                        node.col_offset,
                    )
                )
            else:
                facts.extend(
                    (
                        "from",
                        "" if alias.name == "*" else alias.name,
                        relative_level,
                        node.lineno,
                        node.col_offset,
                    )
                    for alias in node.names
                )

    graph_contract = importlib.import_module("context_search_tool.graph_contract")
    grouped: dict[str, list[tuple[tuple[int, int], dict]]] = {}
    for import_form, module, relative_level, line, column in facts:
        state, specifier, candidates = _independent_python_module_selector(
            source_path=source_path,
            project_unit_key=project_unit_key,
            module=module,
            relative_level=relative_level,
            path_units=path_units,
        )
        target_qualified_name = candidates[0] if candidates else specifier
        target = modules_by_path.get(candidates[0]) if state == "exact" else None
        target_signal_id = target["signal"]["signal_id"] if target else ""
        resolution = (
            "resolved_exact"
            if target is not None
            else "ambiguous"
            if state == "candidates"
            else "external"
            if state == "external"
            else "unresolved"
        )
        relation_id = graph_contract.generate_v5_relation_id(
            source_signal_id=source["signal_id"],
            kind="imports",
            target_kind="module",
            target_qualified_name=target_qualified_name,
            target_signature="",
            target_arity=None,
            target_project_unit_key=project_unit_key,
            producer="python_ast",
        )
        metadata = {
            "selector_state": state,
            "specifier": specifier,
            "candidates": list(candidates),
            "import_form": import_form,
            "relative_level": relative_level,
            "first_source_line": line,
            "first_source_column": column,
            "occurrence_count": 1,
        }
        row = {
            "relation_id": relation_id,
            "source_signal_id": source["signal_id"],
            "source_chunk_id": source["chunk_id"],
            "source_file_path": source_path,
            "target_name": specifier,
            "kind": "imports",
            "target_kind": "module",
            "target_qualified_name": target_qualified_name,
            "target_signature": "",
            "target_arity": None,
            "target_project_unit_key": project_unit_key,
            "target_signal_id": target_signal_id,
            "resolution": resolution,
            "producer": "python_ast",
            "metadata_json": json.dumps(
                metadata, separators=(",", ":"), sort_keys=True
            ),
        }
        grouped.setdefault(relation_id, []).append(((line, column), row))

    expected: dict[str, dict] = {}
    for relation_id, occurrences in grouped.items():
        occurrences.sort(key=lambda item: item[0])
        comparable = {
            key: value
            for key, value in occurrences[0][1].items()
            if key != "metadata_json"
        }
        if any(
            {
                key: value
                for key, value in row.items()
                if key != "metadata_json"
            }
            != comparable
            for _position, row in occurrences[1:]
        ):
            raise ValueError("Task0D frozen module relation identity conflicts")
        selected = deepcopy(occurrences[0][1])
        metadata = json.loads(selected["metadata_json"])
        metadata["occurrence_count"] = len(occurrences)
        metadata["first_source_line"], metadata["first_source_column"] = min(
            position for position, _row in occurrences
        )
        selected["metadata_json"] = json.dumps(
            metadata, separators=(",", ":"), sort_keys=True
        )
        expected[relation_id] = selected
    ordered = sorted(
        expected.values(),
        key=lambda row: (
            json.loads(row["metadata_json"])["first_source_line"],
            json.loads(row["metadata_json"])["first_source_column"],
            row["kind"],
            row["target_kind"],
            row["target_qualified_name"],
            row["target_signature"],
            -1,
            row["target_project_unit_key"],
            row["relation_id"],
        ),
    )[:FROZEN_MAX_PYTHON_IMPORTS_PER_FILE]
    return {row["relation_id"]: row for row in ordered}


def _validate_module_relations(
    projection: dict,
    *,
    repository: str,
    inputs: dict,
    active_signals: dict[str, dict],
) -> dict[str, dict]:
    rows = projection["module_relations"]
    keys = {
        "relation_id",
        "source_signal_id",
        "source_chunk_id",
        "source_file_path",
        "target_name",
        "kind",
        "target_kind",
        "target_signal_id",
        "resolution",
        "target_qualified_name",
        "target_signature",
        "target_arity",
        "target_project_unit_key",
        "producer",
        "metadata_json",
    }
    if not isinstance(rows, list) or any(
        not isinstance(row, dict)
        or set(row) != keys
        or any(
            not isinstance(row[key], str)
            for key in keys - {"target_arity"}
        )
        or row["target_arity"] is not None
        for row in rows
    ):
        raise ValueError("Task0D module relation rows are not closed")
    path_units, modules_by_path = _frozen_python_inventory_units(
        repository=repository, inputs=inputs, active_signals=active_signals
    )
    expected_by_source: dict[str, dict[str, dict]] = {}
    for row in rows:
        metadata = _closed_module_relation_metadata(row["metadata_json"])
        if metadata is None:
            raise ValueError("Task0D module relation metadata is not closed")
        expected_target = (
            metadata["candidates"][0]
            if metadata["candidates"]
            else metadata["specifier"]
        )
        if row["target_qualified_name"] != expected_target:
            raise ValueError("Task0D module relation metadata is inconsistent")
        source_active = active_signals.get(row["source_signal_id"])
        if (
            source_active is None
            or source_active["signal"]["producer"] != "core_module"
            or source_active["signal"]["kind"] != "module"
        ):
            raise ValueError("Task0D module relation source is not an active module")
        expected_rows = expected_by_source.get(row["source_signal_id"])
        if expected_rows is None:
            expected_rows = _expected_frozen_module_relations(
                source_active=source_active,
                repository=repository,
                inputs=inputs,
                path_units=path_units,
                modules_by_path=modules_by_path,
            )
            expected_by_source[row["source_signal_id"]] = expected_rows
        if expected_rows.get(row["relation_id"]) != row:
            raise ValueError(
                "Task0D module relation is not reconstructed from frozen imports"
            )
    rendered = [
        [
            row["relation_id"],
            row["source_signal_id"],
            row["target_signal_id"],
            row["resolution"],
            row["target_qualified_name"],
            row["metadata_json"],
        ]
        for row in rows
    ]
    expected_sha256 = hashlib.sha256(
        _v1_harness()._canonical(rendered).encode("utf-8")
    ).hexdigest()
    by_id = {row["relation_id"]: row for row in rows}
    if (
        len(by_id) != len(rows)
        or projection["module_relation_count"] != len(rows)
        or projection["module_projection_sha256"] != expected_sha256
    ):
        raise ValueError("Task0D module relation projection is inconsistent")
    return by_id


def _frozen_python_path(inputs: dict, repository: str, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or pure.suffix not in {".py", ".pyw"}:
        raise ValueError("Task0D causal source path is invalid")
    path = inputs["source_directories"][repository].joinpath(*pure.parts)
    if not path.is_file() or path.is_symlink():
        raise ValueError("Task0D causal source file is unavailable")
    return path


def _frozen_python_tree(inputs: dict, repository: str, relative: str) -> ast.Module:
    path = _frozen_python_path(inputs, repository, relative)
    return ast.parse(path.read_bytes(), filename=relative, type_comments=True)


def _deterministic_chunk_id(
    file_path: str, start_line: int, end_line: int, content: str
) -> str:
    content_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    raw_id = f"{file_path}:{start_line}-{end_line}:{content_sha}"
    return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()


def _frozen_declaration_identities(
    tree: ast.Module, *, file_path: str, project_unit_key: str
) -> dict[str, dict]:
    declarations: list[dict] = []
    function_scopes = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
    )

    def collect(node: ast.AST, owner: str, owner_is_class: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                kind = "type"
                child_owner = f"{owner}.{child.name}" if owner else child.name
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if owner_is_class else "function"
                child_owner = owner
            elif isinstance(child, function_scopes):
                continue
            else:
                collect(child, owner, owner_is_class)
                continue
            start = min(
                [child, *child.decorator_list],
                key=lambda value: (value.lineno, value.col_offset),
            )
            declarations.append(
                {
                    "kind": kind,
                    "name": child.name,
                    "owner": owner,
                    "start_line": start.lineno,
                    "start_column": start.col_offset,
                    "end_line": (
                        child.end_lineno
                        if child.end_lineno is not None
                        else child.lineno
                    ),
                    "end_column": (
                        child.end_col_offset
                        if child.end_col_offset is not None
                        else child.col_offset
                    ),
                }
            )
            if isinstance(child, ast.ClassDef):
                collect(child, child_owner, True)

    collect(tree, "", False)
    declarations.sort(
        key=lambda item: (
            item["start_line"],
            item["start_column"],
            item["end_line"],
            item["end_column"],
            "class" if item["kind"] == "type" else item["kind"],
            item["owner"],
            item["name"],
        )
    )
    graph_contract = importlib.import_module("context_search_tool.graph_contract")
    module = _v1_harness()._module_name(file_path, project_unit_key)
    identities: dict[str, dict] = {}
    for declaration in declarations[:4095]:
        if declaration["kind"] not in {"type", "function"}:
            continue
        owner = f".{declaration['owner']}" if declaration["owner"] else ""
        qualified_name = f"{module}{owner}.{declaration['name']}"
        identity = {
            "file_path": file_path,
            "kind": declaration["kind"],
            "name": declaration["name"],
            "qualified_name": qualified_name,
            "signature": "",
            "arity": None,
            "project_unit_key": project_unit_key,
            "producer": "python_ast",
            "start_line": declaration["start_line"],
            "start_column": declaration["start_column"],
            "end_line": declaration["end_line"],
            "end_column": declaration["end_column"],
            "language": "python",
            "recallable": 1,
            "deleted_at": None,
        }
        signal_id = graph_contract.generate_v5_signal_id(
            **{
                key: identity[key]
                for key in (
                    "file_path",
                    "kind",
                    "qualified_name",
                    "signature",
                    "start_line",
                    "start_column",
                    "end_line",
                    "end_column",
                    "producer",
                )
            }
        )
        if signal_id in identities:
            raise ValueError("Task0D frozen declaration identity is duplicated")
        identities[signal_id] = identity
    return identities


def _validate_active_python_signal_chunks(
    projection: dict, *, repository: str, inputs: dict
) -> dict[str, dict]:
    rows = projection["active_python_signal_chunks"]
    signal_keys = {
        "signal_id",
        "chunk_id",
        "file_path",
        "kind",
        "name",
        "qualified_name",
        "signature",
        "arity",
        "project_unit_key",
        "producer",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        "language",
        "recallable",
        "deleted_at",
    }
    chunk_keys = {
        "chunk_id",
        "file_path",
        "start_line",
        "end_line",
        "content_sha256",
        "deleted_at",
    }
    if (
        not isinstance(rows, list)
        or type(projection["active_python_signal_chunk_count"]) is not int
        or projection["active_python_signal_chunk_count"] != len(rows)
        or projection["active_python_signal_chunk_sha256"]
        != _json_value_sha256(rows)
        or any(
            not isinstance(row, dict)
            or set(row) != {"signal", "chunk"}
            or not isinstance(row["signal"], dict)
            or set(row["signal"]) != signal_keys
            or not isinstance(row["chunk"], dict)
            or set(row["chunk"]) != chunk_keys
            for row in rows
        )
    ):
        raise ValueError("Task0D active Python signal/chunk projection is not closed")
    by_id: dict[str, dict] = {}
    declaration_cache: dict[tuple[str, str], dict[str, dict]] = {}
    frozen_lines: dict[str, list[str]] = {}
    for row in rows:
        signal = row["signal"]
        chunk = row["chunk"]
        is_declaration = (
            signal["producer"] == "python_ast"
            and signal["kind"] in {"type", "function"}
        )
        is_module = (
            signal["producer"] == "core_module"
            and signal["kind"] == "module"
        )
        if any(
            (
                not isinstance(signal["signal_id"], str),
                not isinstance(signal["chunk_id"], str),
                not isinstance(signal["file_path"], str),
                not (is_declaration or is_module),
                not isinstance(signal["name"], str),
                not isinstance(signal["qualified_name"], str),
                signal["signature"] != "",
                signal["arity"] is not None,
                not isinstance(signal["project_unit_key"], str),
                signal["language"] != "python",
                signal["recallable"] != (1 if is_declaration else 0),
                signal["deleted_at"] is not None,
                chunk["deleted_at"] is not None,
                chunk["chunk_id"] != signal["chunk_id"],
                chunk["file_path"] != signal["file_path"],
                any(
                    type(value) is not int
                    for value in (
                        signal["start_line"],
                        signal["start_column"],
                        signal["end_line"],
                        signal["end_column"],
                        chunk["start_line"],
                        chunk["end_line"],
                    )
                ),
                not isinstance(chunk["content_sha256"], str),
            )
        ):
            raise ValueError("Task0D active Python signal/chunk identity is invalid")
        path = signal["file_path"]
        source_path = _frozen_python_path(inputs, repository, path)
        lines = frozen_lines.setdefault(
            path, source_path.read_text(encoding="utf-8").splitlines()
        )
        expected_chunk_start = (
            ((signal["start_line"] - 1) // 80) * 80 + 1
            if is_declaration
            else 1
        )
        expected_chunk_end = min(expected_chunk_start + 79, len(lines))
        if (
            chunk["start_line"] != expected_chunk_start
            or chunk["end_line"] != expected_chunk_end
            or not (
                chunk["start_line"]
                <= signal["start_line"]
                <= chunk["end_line"]
            )
        ):
            raise ValueError("Task0D active Python chunk range is invalid")
        actual_content = "\n".join(
            lines[chunk["start_line"] - 1 : chunk["end_line"]]
        )
        actual_chunk_id = _deterministic_chunk_id(
            path, chunk["start_line"], chunk["end_line"], actual_content
        )
        actual_content_sha256 = hashlib.sha256(
            actual_content.encode("utf-8")
        ).hexdigest()
        if (
            chunk["content_sha256"] != actual_content_sha256
            or chunk["chunk_id"] != actual_chunk_id
        ):
            raise ValueError("Task0D active Python chunk identity is invalid")
        if is_module:
            module_identity = {
                "file_path": path,
                "kind": "module",
                "name": path,
                "qualified_name": path,
                "signature": "",
                "arity": None,
                "project_unit_key": signal["project_unit_key"],
                "producer": "core_module",
                "start_line": 1,
                "start_column": 0,
                "end_line": expected_chunk_end,
                "end_column": 0,
                "language": "python",
                "recallable": 0,
                "deleted_at": None,
            }
            expected_signal_id = importlib.import_module(
                "context_search_tool.graph_contract"
            ).generate_v5_signal_id(
                **{
                    key: module_identity[key]
                    for key in (
                        "file_path",
                        "kind",
                        "qualified_name",
                        "signature",
                        "start_line",
                        "start_column",
                        "end_line",
                        "end_column",
                        "producer",
                    )
                }
            )
            if signal["signal_id"] != expected_signal_id or any(
                signal[key] != module_identity[key] for key in module_identity
            ):
                raise ValueError("Task0D active Python module identity is invalid")
            if signal["signal_id"] in by_id:
                raise ValueError("Task0D active Python signal identity is duplicated")
            by_id[signal["signal_id"]] = row
            continue
        declaration_key = (path, signal["project_unit_key"])
        declarations = declaration_cache.get(declaration_key)
        if declarations is None:
            declarations = _frozen_declaration_identities(
                _frozen_python_tree(inputs, repository, path),
                file_path=path,
                project_unit_key=signal["project_unit_key"],
            )
            declaration_cache[declaration_key] = declarations
        expected = declarations.get(signal["signal_id"])
        if expected is None or any(
            signal[key] != expected[key] for key in expected
        ):
            raise ValueError("Task0D active Python declaration identity is invalid")
        if signal["signal_id"] in by_id:
            raise ValueError("Task0D active Python signal identity is duplicated")
        by_id[signal["signal_id"]] = row
    return by_id


def _validate_causal_relations(
    projection: dict,
    *,
    repository: str,
    inputs: dict,
    module_relations: dict[str, dict],
    active_signals: dict[str, dict],
) -> dict[str, dict]:
    causal = projection["causal_relations"]
    relation_keys = {
        "relation_id",
        "source_signal_id",
        "kind",
        "target_kind",
        "target_qualified_name",
        "target_signature",
        "target_arity",
        "target_project_unit_key",
        "target_signal_id",
        "resolution",
        "producer",
        "metadata_json",
    }
    signal_keys = {
        "file_path",
        "kind",
        "qualified_name",
        "signature",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        "producer",
        "project_unit_key",
        "chunk_id",
        "language",
    }
    if not isinstance(causal, list) or any(
        not isinstance(item, dict)
        or set(item)
        != {
            "relation",
            "source_signal",
            "target_signal",
            "target_uniqueness_count",
        }
        or not isinstance(item["relation"], dict)
        or set(item["relation"]) != relation_keys
        or not isinstance(item["source_signal"], dict)
        or set(item["source_signal"]) != signal_keys
        or not isinstance(item["target_signal"], dict)
        or set(item["target_signal"]) != signal_keys
        or item["target_uniqueness_count"] != 1
        for item in causal
    ):
        raise ValueError("Task0D causal relation schema is not closed")
    graph_contract = importlib.import_module("context_search_tool.graph_contract")
    by_id: dict[str, dict] = {}
    metadata_keys = {
        "resolution_basis",
        "selector_state",
        "target_file_path",
        "target_signal_kinds",
        "imported_name",
        "local_names",
        "relative_level",
        "first_source_line",
        "first_source_column",
        "occurrence_count",
        "module_relation_id",
        "module_selector",
        "oracle_actual_target_kind",
    }
    for item in causal:
        relation = item["relation"]
        source = item["source_signal"]
        target = item["target_signal"]
        try:
            metadata = json.loads(relation["metadata_json"])
        except (TypeError, json.JSONDecodeError):
            metadata = None
        if not isinstance(metadata, dict) or set(metadata) != metadata_keys:
            raise ValueError("Task0D causal relation metadata is not closed")
        active_source = active_signals.get(relation["source_signal_id"])
        active = active_signals.get(relation["target_signal_id"])
        if active_source is None or active is None:
            raise ValueError("Task0D causal endpoint is not an active SQLite signal")
        active_source_signal = active_source["signal"]
        active_source_chunk = active_source["chunk"]
        active_signal = active["signal"]
        active_chunk = active["chunk"]
        source_projection = {
            key: active_source_signal[key]
            for key in (
                "file_path",
                "kind",
                "qualified_name",
                "signature",
                "start_line",
                "start_column",
                "end_line",
                "end_column",
                "producer",
                "project_unit_key",
                "chunk_id",
                "language",
            )
        }
        target_projection = {
            key: active_signal[key]
            for key in (
                "file_path",
                "kind",
                "qualified_name",
                "signature",
                "start_line",
                "start_column",
                "end_line",
                "end_column",
                "producer",
                "project_unit_key",
                "chunk_id",
                "language",
            )
        }
        uniqueness_count = sum(
            1
            for candidate in active_signals.values()
            if candidate["signal"]["file_path"] == active_signal["file_path"]
            and candidate["signal"]["project_unit_key"]
            == active_signal["project_unit_key"]
            and candidate["signal"]["producer"] == "python_ast"
            and candidate["signal"]["language"] == "python"
            and candidate["signal"]["kind"] in {"type", "function"}
            and candidate["signal"]["qualified_name"]
            == active_signal["qualified_name"]
        )
        if (
            source != source_projection
            or active_source_signal["kind"] != "module"
            or active_source_signal["producer"] != "core_module"
            or active_source_chunk["chunk_id"] != source["chunk_id"]
            or target != target_projection
            or item["target_uniqueness_count"] != uniqueness_count
            or uniqueness_count != 1
            or active_chunk["chunk_id"] != target["chunk_id"]
        ):
            raise ValueError("Task0D causal target is not the active SQLite declaration")
        module_selector = metadata["module_selector"]
        if not isinstance(module_selector, dict) or set(module_selector) != {
            "state",
            "specifier",
            "target_file_path",
        }:
            raise ValueError("Task0D causal module selector is not closed")
        if any(
            (
                relation["kind"] != "imports",
                relation["producer"] != "python_ast",
                relation["resolution"] != "resolved_exact",
                relation["target_signature"] != "",
                relation["target_arity"] is not None,
                source["kind"] != "module",
                source["producer"] != "core_module",
                source["language"] != "python",
                target["kind"] not in {"type", "function"},
                target["producer"] != "python_ast",
                target["language"] != "python",
                relation["source_signal_id"]
                != graph_contract.generate_v5_signal_id(
                    file_path=source["file_path"],
                    kind=source["kind"],
                    qualified_name=source["qualified_name"],
                    signature=source["signature"],
                    start_line=source["start_line"],
                    start_column=source["start_column"],
                    end_line=source["end_line"],
                    end_column=source["end_column"],
                    producer=source["producer"],
                ),
                relation["target_signal_id"]
                != graph_contract.generate_v5_signal_id(
                    file_path=target["file_path"],
                    kind=target["kind"],
                    qualified_name=target["qualified_name"],
                    signature=target["signature"],
                    start_line=target["start_line"],
                    start_column=target["start_column"],
                    end_line=target["end_line"],
                    end_column=target["end_column"],
                    producer=target["producer"],
                ),
                relation["relation_id"]
                != graph_contract.generate_v5_relation_id(
                    source_signal_id=relation["source_signal_id"],
                    kind=relation["kind"],
                    target_kind=relation["target_kind"],
                    target_qualified_name=relation["target_qualified_name"],
                    target_signature=relation["target_signature"],
                    target_arity=relation["target_arity"],
                    target_project_unit_key=relation[
                        "target_project_unit_key"
                    ],
                    producer=relation["producer"],
                ),
                relation["target_kind"] != target["kind"],
                relation["target_qualified_name"] != target["qualified_name"],
                relation["target_project_unit_key"]
                != target["project_unit_key"],
                source["project_unit_key"] != target["project_unit_key"],
                metadata["resolution_basis"]
                != "exact_python_imported_symbol",
                metadata["selector_state"] != "exact",
                metadata["target_signal_kinds"] != ["type", "function"],
                metadata["target_file_path"] != target["file_path"],
                metadata["oracle_actual_target_kind"] != target["kind"],
                module_selector["state"] != "exact",
                module_selector["target_file_path"] != target["file_path"],
            )
        ):
            raise ValueError("Task0D causal relation identity is invalid")
        module = module_relations.get(metadata["module_relation_id"])
        if (
            module is None
            or module["source_signal_id"] != relation["source_signal_id"]
            or module["resolution"] != "resolved_exact"
        ):
            raise ValueError("Task0D causal module relation is invalid")

        source_tree = _frozen_python_tree(
            inputs, repository, source["file_path"]
        )
        facts = []
        for node in ast.walk(source_tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            specifier = "." * (node.level or 0) + (node.module or "")
            if specifier != module_selector["specifier"]:
                continue
            for alias in node.names:
                if alias.name == metadata["imported_name"]:
                    facts.append(
                        {
                            "local_name": alias.asname or alias.name,
                            "line": node.lineno,
                            "column": node.col_offset,
                        }
                    )
        if (
            not facts
            or len(facts) != metadata["occurrence_count"]
            or sorted({fact["local_name"] for fact in facts})
            != metadata["local_names"]
            or min((fact["line"], fact["column"]) for fact in facts)
            != (
                metadata["first_source_line"],
                metadata["first_source_column"],
            )
            or metadata["relative_level"]
            != len(module_selector["specifier"])
            - len(module_selector["specifier"].lstrip("."))
        ):
            raise ValueError("Task0D causal ImportFrom fact is invalid")

        target_tree = _frozen_python_tree(
            inputs, repository, target["file_path"]
        )
        declarations = [
            node
            for node in target_tree.body
            if isinstance(
                node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and node.name == metadata["imported_name"]
        ]
        if len(declarations) != 1:
            raise ValueError("Task0D causal target declaration is invalid")
        expected_kind = (
            "type" if isinstance(declarations[0], ast.ClassDef) else "function"
        )
        expected_qualified_name = (
            f"{_v1_harness()._module_name(target['file_path'], target['project_unit_key'])}."
            f"{metadata['imported_name']}"
        )
        declaration_start = min(
            [declarations[0], *declarations[0].decorator_list],
            key=lambda node: (node.lineno, node.col_offset),
        )
        if (
            target["kind"] != expected_kind
            or target["qualified_name"] != expected_qualified_name
            or target["start_line"] != declaration_start.lineno
            or target["start_column"] != declaration_start.col_offset
            or target["end_line"] != declarations[0].end_lineno
            or target["end_column"] != declarations[0].end_col_offset
        ):
            raise ValueError("Task0D causal target declaration is invalid")
        if relation["relation_id"] in by_id:
            raise ValueError("Task0D causal relation identity is duplicated")
        by_id[relation["relation_id"]] = {
            **item,
            "_active_source_signal_chunk": active_source,
            "_active_signal_chunk": active,
        }
    return by_id


def _validate_hash_capture(
    capture: dict,
    *,
    manifest_path: Path,
    manifest: dict,
    inputs: dict,
    variant: str,
    repeat: int,
    input_order: str,
) -> None:
    if set(capture) != _expected_capture_root_keys() or capture.get(
        "schema_version"
    ) != 2:
        raise ValueError("Task0D capture schema is not closed")
    expected_slot = (
        f"oracle:{CAPTURE_CORPORA}:hash:{variant}:r{repeat}:{input_order}"
    )
    if any(
        (
            capture["program"] != PROGRAM,
            capture["attempt_id"] != ATTEMPT_ID,
            capture["phase"] != "oracle",
            capture["corpora"] != CAPTURE_CORPORA,
            capture["profile"] != "hash",
            capture["variant"] != variant,
            capture["repeat"] != repeat,
            capture["input_order"] != input_order,
            capture["slot"] != expected_slot,
            capture["manifest_sha256"] != _sha256(manifest_path),
            capture["harness_sha256"] != _sha256(Path(__file__)),
            capture["review_disposition_sha256"]
            != REVIEW_DISPOSITION_SHA256,
            capture["input_identity"] != inputs["input_identity"],
            capture["source_roles"] != SOURCE_ROLES,
        )
    ):
        raise ValueError("Task0D capture identity changed")
    product = capture["product_identity"]
    if (
        not isinstance(product, dict)
        or set(product)
        != {
            "baseline",
            "head",
            "tracked_diff_sha256",
            "untracked",
            "product_tree_sha256",
            "clean_against_baseline",
        }
        or product["clean_against_baseline"] is not True
        or product["baseline"] != BASELINE
    ):
        raise ValueError("Task0D capture contains a product change")
    _validate_implementation_identity(capture["implementation"])
    if capture["embedding"] != {
        "provider": "hash",
        "model": "hash-v1",
        "dimensions": 384,
        "base_url": None,
        "planner_enabled": False,
    }:
        raise ValueError("Task0D capture used a non-hash provider or planner")
    if set(capture["embedding_requests"]) != set(CAPTURE_REPOSITORIES) | {
        "total"
    } or any(capture["embedding_requests"].values()):
        raise ValueError("hash capture made an embedding request")
    if (
        set(capture["repositories"]) != set(CAPTURE_REPOSITORIES)
        or set(capture["index_projections"]) != set(CAPTURE_REPOSITORIES)
    ):
        raise ValueError("Task0D repository roster changed")
    expected_selected_files = {
        repository: inputs["source_specs"][repository]["expected_count"]
        for repository in CAPTURE_REPOSITORIES
    }
    projection_keys = {
        "exact_relation_count",
        "graph_omitted_imported_symbols",
        "omitted_by_source",
        "maximum_exact_relations_per_source",
        "terminal_counts",
        "target_states",
        "exact_targets",
        "causal_relations",
        "active_python_signal_chunks",
        "active_python_signal_chunk_count",
        "active_python_signal_chunk_sha256",
        "module_relation_count",
        "module_relations",
        "module_projection_sha256",
        "non_python_projection_sha256",
        "work_caps",
    }
    module_relations_by_repository: dict[str, dict[str, dict]] = {}
    causal_relations_by_repository: dict[str, dict[str, dict]] = {}
    frozen_paths_by_repository: dict[str, set[str]] = {}
    for repository in CAPTURE_REPOSITORIES:
        repository_row = capture["repositories"][repository]
        if set(repository_row) != {
            "selected_files",
            "structure",
            "index_sqlite_bytes",
        } or repository_row["selected_files"] != expected_selected_files[repository]:
            raise ValueError("Task0D source materialization changed")
        projection = capture["index_projections"][repository]
        if set(projection) != projection_keys:
            raise ValueError("Task0D oracle projection is not closed")
        exact_targets = projection["exact_targets"]
        target_states = projection["target_states"]
        exact_keys = {
            "relation_id",
            "module_relation_id",
            "source_signal_id",
            "source_chunk_id",
            "target_signal_id",
            "target_chunk_id",
            "actual_target_kind",
        }
        frozen_paths = {
            path.relative_to(inputs["source_directories"][repository]).as_posix()
            for pattern in inputs["source_specs"][repository]["patterns"]
            for path in inputs["source_directories"][repository].glob(pattern)
            if path.is_file() and not path.is_symlink()
        }
        frozen_paths_by_repository[repository] = frozen_paths
        if (
            not isinstance(exact_targets, list)
            or len(
                {
                    item.get("target_file_path")
                    for item in exact_targets
                    if isinstance(item, dict)
                }
            )
            != len(exact_targets)
            or any(
            not isinstance(item, dict)
            or set(item) != {"target_file_path", "relations"}
            or item["target_file_path"] not in frozen_paths
            or not isinstance(item["relations"], list)
            or any(
                not isinstance(row, dict)
                or set(row) != exact_keys
                or any(not isinstance(row[key], str) for key in exact_keys)
                for row in item["relations"]
            )
            for item in exact_targets
            )
        ):
            raise ValueError("Task0D exact target projection is not closed")
        state_names = {
            "resolved",
            "not_representable",
            "no_exact_signal",
            "ambiguous_signal",
        }
        if (
            not isinstance(target_states, list)
            or len(
                {
                    item.get("target_file_path")
                    for item in target_states
                    if isinstance(item, dict)
                }
            )
            != len(target_states)
            or any(
            not isinstance(item, dict)
            or set(item) != {"target_file_path", "states"}
            or item["target_file_path"] not in frozen_paths
            or not isinstance(item["states"], dict)
            or not set(item["states"]).issubset(state_names)
            or any(
                type(count) is not int or count < 0
                for count in item["states"].values()
            )
            for item in target_states
            )
        ):
            raise ValueError("Task0D target-state projection is not closed")
        exact_rows = [
            (item["target_file_path"], row)
            for item in exact_targets
            for row in item["relations"]
        ]
        if any(
            not row["relation_id"].startswith("r5:")
            or not row["module_relation_id"].startswith("r5:")
            or not row["source_signal_id"].startswith("s5:")
            or not row["target_signal_id"].startswith("s5:")
            or not row["source_chunk_id"]
            or not row["target_chunk_id"]
            or row["actual_target_kind"] not in {"type", "function"}
            for _path, row in exact_rows
        ):
            raise ValueError("Task0D exact target identity is invalid")
        source_counts: dict[str, int] = {}
        for _path, row in exact_rows:
            source = row["source_signal_id"]
            source_counts[source] = source_counts.get(source, 0) + 1
        maximum_exact = max(source_counts.values(), default=0)
        if any(
            (
                type(projection["exact_relation_count"]) is not int,
                projection["exact_relation_count"] != len(exact_rows),
                type(projection["maximum_exact_relations_per_source"]) is not int,
                projection["maximum_exact_relations_per_source"] != maximum_exact,
                maximum_exact > 256,
                len({row["relation_id"] for _path, row in exact_rows})
                != len(exact_rows),
            )
        ):
            raise ValueError("Task0D exact target counts are inconsistent")
        active_signals = _validate_active_python_signal_chunks(
            projection, repository=repository, inputs=inputs
        )
        module_relations = _validate_module_relations(
            projection,
            repository=repository,
            inputs=inputs,
            active_signals=active_signals,
        )
        module_relations_by_repository[repository] = module_relations
        causal_relations = _validate_causal_relations(
            projection,
            repository=repository,
            inputs=inputs,
            module_relations=module_relations,
            active_signals=active_signals,
        )
        causal_relations_by_repository[repository] = causal_relations
        if set(causal_relations) != {
            row["relation_id"] for _path, row in exact_rows
        }:
            raise ValueError("Task0D exact targets lack causal relations")
        for target_path, row in exact_rows:
            module = module_relations.get(row["module_relation_id"])
            causal = causal_relations.get(row["relation_id"])
            active = (
                causal["_active_signal_chunk"] if causal is not None else None
            )
            active_source = (
                causal["_active_source_signal_chunk"]
                if causal is not None
                else None
            )
            try:
                module_metadata = json.loads(module["metadata_json"] if module else "")
            except json.JSONDecodeError:
                module_metadata = None
            if (
                module is None
                or module["source_signal_id"] != row["source_signal_id"]
                or module["resolution"] != "resolved_exact"
                or causal is None
                or causal["relation"]["source_signal_id"]
                != row["source_signal_id"]
                or causal["relation"]["target_signal_id"]
                != row["target_signal_id"]
                or causal["relation"]["target_kind"]
                != row["actual_target_kind"]
                or active_source is None
                or active_source["signal"]["signal_id"]
                != row["source_signal_id"]
                or active_source["chunk"]["chunk_id"]
                != row["source_chunk_id"]
                or active is None
                or active["signal"]["file_path"] != target_path
                or active["signal"]["signal_id"] != row["target_signal_id"]
                or active["chunk"]["chunk_id"] != row["target_chunk_id"]
                or not isinstance(module_metadata, dict)
                or module_metadata.get("selector_state") != "exact"
                or module_metadata.get("candidates") != [target_path]
            ):
                raise ValueError("Task0D exact target lacks its module relation")
        caps = projection["work_caps"]
        cap_values = {
            "max_graph_seed_signals": 512,
            "max_resolved_graph_hops": 4,
            "max_edges_per_signal_direction": 64,
            "max_relation_expanded_candidates": 1000,
        }
        observed_cap_keys = {
            "observed_maximum_outgoing_rows",
            "observed_maximum_incoming_rows",
        }
        if (
            not isinstance(caps, dict)
            or set(caps) != set(cap_values) | observed_cap_keys
            or any(type(value) is not int for value in caps.values())
            or any(caps[key] != value for key, value in cap_values.items())
            or any(
                caps[key] < 0
                or caps[key] > caps["max_relation_expanded_candidates"]
                for key in observed_cap_keys
            )
        ):
            raise ValueError("Task0D work cap changed")
    expected_case_ids = {case["id"] for case in inputs["gold"]["cases"]}
    if set(capture["cases"]) != expected_case_ids:
        raise ValueError("Task0D case roster changed")
    selected_keys = {
        "rank",
        "path",
        "start_line",
        "end_line",
        "score",
        "score_parts",
        "reasons",
        "chunk_id",
        "origin_chunk_ids",
        "rank_history",
        "stage_trajectory",
        "exact_witness",
    }
    case_keys = {
        "repo",
        "selected",
        "required",
        "contextual",
        "trace",
        "evidence_role",
        "protected_winner",
        "membership_change_eligible",
    }
    v1 = _v1_harness()
    for case_id, case in capture["cases"].items():
        contract = inputs["case_contracts"][case_id]
        if (
            set(case) != case_keys
            or case["evidence_role"] != contract["evidence_role"]
            or case["protected_winner"] != contract["protected_winner"]
            or case["membership_change_eligible"]
            != contract["membership_change_eligible"]
        ):
            raise ValueError("Task0D case contract changed")
        for row in case["selected"]:
            witness = row.get("exact_witness")
            if (
                set(row) != selected_keys
                or row.get("path")
                not in frozen_paths_by_repository[case["repo"]]
                or (
                witness is not None and not v1._valid_exact_selected(row)
                )
            ):
                raise ValueError("Task0D selected-row witness is invalid")
            if witness is not None:
                exact_rows = capture["index_projections"][case["repo"]][
                    "exact_targets"
                ]
                exact_rows = next(
                    (
                        item["relations"]
                        for item in exact_rows
                        if item["target_file_path"] == row["path"]
                    ),
                    [],
                )
                exact = next(
                    (
                        target
                        for target in exact_rows
                        if all(
                            (
                                target["relation_id"] == witness["relation_id"],
                                target["module_relation_id"]
                                == witness["module_relation_id"],
                                target["source_signal_id"]
                                == witness["source_signal_id"],
                                target["target_signal_id"]
                                == witness["target_signal_id"],
                                target["target_chunk_id"]
                                == witness["target_chunk_id"],
                                target["actual_target_kind"]
                                == witness["actual_target_kind"],
                            )
                        )
                    ),
                    None,
                )
                module = module_relations_by_repository[case["repo"]].get(
                    witness["module_relation_id"]
                )
                causal = causal_relations_by_repository[case["repo"]].get(
                    witness["relation_id"]
                )
                active = (
                    causal["_active_signal_chunk"]
                    if causal is not None
                    else None
                )
                if (
                    exact is None
                    or module is None
                    or causal is None
                    or module["source_signal_id"] != witness["source_signal_id"]
                    or causal["relation"]["target_signal_id"]
                    != witness["target_signal_id"]
                    or active is None
                    or active["signal"]["signal_id"]
                    != witness["target_signal_id"]
                    or active["signal"]["file_path"]
                    != witness["target_file_path"]
                    or active["signal"]["start_line"]
                    != witness["target_start_line"]
                    or active["signal"]["end_line"]
                    != witness["target_end_line"]
                    or active["chunk"]["chunk_id"]
                    != witness["target_chunk_id"]
                    or row["chunk_id"] != active["chunk"]["chunk_id"]
                    or row["origin_chunk_ids"][0]
                    != active["chunk"]["chunk_id"]
                ):
                    raise ValueError(
                        "Task0D selected-row witness is not projection-bound"
                    )
    observed = capture["observed"]
    if observed != {
        "local_model_calls": 0,
        "planner_calls": 0,
        "fallback_count": 0,
        "error_count": 0,
        "skip_count": 0,
        "retrieval_calls": len(expected_case_ids),
    }:
        raise ValueError("Task0D observed counters changed")
    _privacy_check(capture, inputs=inputs)


def _stable_hash_projection(capture: dict) -> dict:
    projection = _v1_harness()._stable_projection(capture)
    projection.update(
        {
            "program": capture["program"],
            "attempt_id": capture["attempt_id"],
            "corpora": capture["corpora"],
            "review_disposition_sha256": capture[
                "review_disposition_sha256"
            ],
            "input_identity": capture["input_identity"],
            "source_roles": capture["source_roles"],
            "case_contracts": {
                case_id: {
                    "evidence_role": case["evidence_role"],
                    "protected_winner": case["protected_winner"],
                    "membership_change_eligible": case[
                        "membership_change_eligible"
                    ],
                }
                for case_id, case in sorted(capture["cases"].items())
            },
        }
    )
    return projection


def _filtered_capture(capture: dict, repositories: set[str]) -> dict:
    filtered = deepcopy(capture)
    filtered["cases"] = {
        case_id: case
        for case_id, case in capture["cases"].items()
        if case["repo"] in repositories
    }
    filtered["repositories"] = {
        repository: capture["repositories"][repository]
        for repository in repositories
    }
    filtered["index_projections"] = {
        repository: deepcopy(capture["index_projections"][repository])
        for repository in repositories
    }
    for projection in filtered["index_projections"].values():
        projection["exact_targets"] = {
            item["target_file_path"]: item["relations"]
            for item in projection["exact_targets"]
        }
        projection["target_states"] = {
            item["target_file_path"]: item["states"]
            for item in projection["target_states"]
        }
    filtered["embedding_requests"] = {
        **{
            repository: capture["embedding_requests"][repository]
            for repository in repositories
        },
        "total": sum(
            capture["embedding_requests"][repository]
            for repository in repositories
        ),
    }
    filtered["observed"] = {
        **capture["observed"],
        "retrieval_calls": len(filtered["cases"]),
    }
    filtered["timing"] = {
        "index_seconds": {
            repository: capture["timing"]["index_seconds"][repository]
            for repository in repositories
        },
        "query_case_seconds": {
            case_id: capture["timing"]["query_case_seconds"][case_id]
            for case_id in filtered["cases"]
        },
    }
    return filtered


def _assert_distinct_capture_processes(
    captures: dict[tuple[str, int, str], dict]
) -> None:
    processes = [
        capture["implementation"]["process_identity"]
        for capture in captures.values()
    ]
    if (
        len(captures) != 8
        or len({process["pid"] for process in processes}) != 8
        or len({process["invocation_id"] for process in processes}) != 8
    ):
        raise ValueError("Task0D hash slots must come from eight separate processes")


def _compare_hash_pair(manifest: dict, baseline: dict, oracle: dict) -> dict:
    v1 = _v1_harness()
    r2 = manifest["r2"]
    proxy_manifest = {
        "r2": {
            "development_minimum_micro_recall_gain": r2[
                "development_minimum_micro_recall_gain"
            ],
            "development_minimum_new_required_items": r2[
                "development_minimum_new_required_items"
            ],
            "development_minimum_distinct_cases": r2[
                "development_minimum_distinct_cases"
            ],
            "development_required_repository_spread": sorted(
                EFFICACY_REPOSITORIES
            ),
            "heldout_minimum_new_required_items": r2[
                "heldout_minimum_new_required_items"
            ],
            "heldout_minimum_distinct_cases": r2[
                "heldout_minimum_distinct_cases"
            ],
            "maximum_index_regression_ratio": r2[
                "maximum_index_regression_ratio"
            ],
            "maximum_query_regression_ratio": r2[
                "maximum_query_regression_ratio"
            ],
            "minimum_query_regression_seconds": r2[
                "minimum_query_regression_seconds"
            ],
            "required_loss_limit": r2["required_loss_limit"],
            "noise_growth_limit": r2["noise_growth_limit"],
        }
    }
    baseline_efficacy = _filtered_capture(baseline, set(EFFICACY_REPOSITORIES))
    oracle_efficacy = _filtered_capture(oracle, set(EFFICACY_REPOSITORIES))
    report = v1._compare_pair(proxy_manifest, baseline_efficacy, oracle_efficacy)
    report["non_gating_performance"] = report.pop("performance")
    report["gates"].pop("performance_within_bounds")

    all_required = [
        (case_id, case["repo"], item["path"])
        for case_id, case in baseline["cases"].items()
        for item in case["required"]
    ]
    losses = [
        {"case": case_id, "repo": repository, "path": path}
        for case_id, repository, path in all_required
        if v1._required_rank(baseline, case_id, path) <= 12
        and v1._required_rank(oracle, case_id, path) > 12
    ]
    per_repository_non_decreasing = all(
        sum(
            v1._required_rank(oracle, case_id, path) <= 12
            for case_id, item_repository, path in all_required
            if item_repository == repository
        )
        >= sum(
            v1._required_rank(baseline, case_id, path) <= 12
            for case_id, item_repository, path in all_required
            if item_repository == repository
        )
        for repository in CAPTURE_REPOSITORIES
    )
    noise_growth = {
        case_id: v1._noise(oracle["cases"][case_id])
        - v1._noise(baseline["cases"][case_id])
        for case_id in baseline["cases"]
    }
    protected_winner_drift: list[str] = []
    membership_drift: list[str] = []
    for case_id, baseline_case in baseline["cases"].items():
        oracle_case = oracle["cases"][case_id]
        baseline_winner = (
            baseline_case["selected"][0]["path"]
            if baseline_case["selected"]
            else None
        )
        oracle_winner = (
            oracle_case["selected"][0]["path"]
            if oracle_case["selected"]
            else None
        )
        frozen_winner = baseline_case["protected_winner"]
        if baseline_winner != oracle_winner or (
            frozen_winner is not None
            and (baseline_winner != frozen_winner or oracle_winner != frozen_winner)
        ):
            protected_winner_drift.append(case_id)
        baseline_paths = {row["path"] for row in baseline_case["selected"]}
        oracle_paths = {row["path"] for row in oracle_case["selected"]}
        if baseline_paths != oracle_paths:
            has_exact = any(
                v1._valid_exact_selected(row) for row in oracle_case["selected"]
            )
            frozen_eligible = baseline_case["membership_change_eligible"]
            if not has_exact or frozen_eligible is False:
                membership_drift.append(case_id)

    module_stable = all(
        baseline["index_projections"][repository][
            "module_projection_sha256"
        ]
        == oracle["index_projections"][repository][
            "module_projection_sha256"
        ]
        for repository in CAPTURE_REPOSITORIES
    )
    non_python_stable = all(
        baseline["index_projections"][repository][
            "non_python_projection_sha256"
        ]
        == oracle["index_projections"][repository][
            "non_python_projection_sha256"
        ]
        for repository in CAPTURE_REPOSITORIES
    )
    structure_stable = all(
        {
            "selected_files": baseline["repositories"][repository][
                "selected_files"
            ],
            "structure": baseline["repositories"][repository]["structure"],
        }
        == {
            "selected_files": oracle["repositories"][repository][
                "selected_files"
            ],
            "structure": oracle["repositories"][repository]["structure"],
        }
        for repository in CAPTURE_REPOSITORIES
    )
    work_caps_stable = all(
        baseline["index_projections"][repository]["work_caps"]
        == oracle["index_projections"][repository]["work_caps"]
        and oracle["index_projections"][repository][
            "maximum_exact_relations_per_source"
        ]
        <= 256
        for repository in CAPTURE_REPOSITORIES
    )
    baseline_v1 = _filtered_capture(baseline, set(CAPTURE_REPOSITORIES))
    oracle_v1 = _filtered_capture(oracle, set(CAPTURE_REPOSITORIES))
    residuals = v1._residual_classifications(baseline_v1, oracle_v1)
    baseline_missing = sum(
        v1._required_rank(baseline, case_id, path) > 12
        for case_id, _repository, path in all_required
    )
    protection_gates = {
        "all_corpora_zero_required_loss": not losses,
        "all_corpora_per_repository_recall_non_decreasing": per_repository_non_decreasing,
        "all_corpora_zero_noise_growth": all(
            value <= r2["noise_growth_limit"] for value in noise_growth.values()
        ),
        "all_corpora_protected_winners_stable": not protected_winner_drift,
        "all_corpora_membership_drift_closed": not membership_drift,
        "all_corpora_module_relations_stable": module_stable,
        "all_corpora_non_python_projection_stable": non_python_stable,
        "all_corpora_structure_stable": structure_stable,
        "all_corpora_request_counts_stable": baseline["embedding_requests"]
        == oracle["embedding_requests"],
        "all_corpora_retrieval_calls_stable": baseline["observed"][
            "retrieval_calls"
        ]
        == oracle["observed"]["retrieval_calls"]
        == len(baseline["cases"]),
        "all_corpora_work_caps_stable": work_caps_stable,
        "all_corpora_no_local_model_or_fallback": all(
            capture["observed"][field] == 0
            for capture in (baseline, oracle)
            for field in (
                "local_model_calls",
                "planner_calls",
                "fallback_count",
                "error_count",
                "skip_count",
            )
        ),
        "all_residuals_total": len(residuals) == baseline_missing,
        "input_identity_stable": baseline["input_identity"]
        == oracle["input_identity"],
        "source_roles_stable": baseline["source_roles"] == oracle["source_roles"],
    }
    report["gates"].update(protection_gates)
    report["all_corpora_lost_required_items"] = losses
    report["all_corpora_noise_growth"] = noise_growth
    report["protected_winner_drift"] = protected_winner_drift
    report["membership_drift"] = membership_drift
    report["residual_classifications"] = residuals
    report["efficacy_repositories"] = sorted(EFFICACY_REPOSITORIES)
    report["protected_characterization_repositories"] = ["redink", "daily"]
    report["disposition"] = (
        "proceed" if all(report["gates"].values()) else "reject"
    )
    return report


def _expected_run_root(manifest: dict) -> Path:
    return ROOT / manifest["evidence"]["run_root"]


def _validate_run_root(run_root: Path, manifest: dict) -> Path:
    supplied = _absolute_without_resolving(run_root)
    expected = _absolute_without_resolving(_expected_run_root(manifest))
    if supplied != expected:
        raise ValueError("Task0D run root changed")
    return supplied


def capture_hash_to_disk(
    manifest_path: Path,
    run_root: Path,
    *,
    variant: str,
    repeat: int,
    input_order: str,
) -> Path:
    manifest = validate_manifest(manifest_path, require_zero_evidence=False)
    if manifest["capture_authorized"] is not True:
        raise ValueError("Task0D engine review has not authorized capture")
    run_root = _validate_run_root(run_root, manifest)
    with _trusted_run_root_fd(run_root, manifest, create=False) as run_root_fd:
        if run_root_fd is not None:
            _assert_capture_inventory_fd(run_root_fd, state="capture")
    output = _capture_path(
        run_root,
        variant=variant,
        repeat=repeat,
        input_order=input_order,
    )
    capture = _build_hash_capture(
        manifest_path,
        run_root,
        variant=variant,
        repeat=repeat,
        input_order=input_order,
    )
    inputs = _capture_inputs(manifest)
    _validate_hash_capture(
        capture,
        manifest_path=manifest_path,
        manifest=manifest,
        inputs=inputs,
        variant=variant,
        repeat=repeat,
        input_order=input_order,
    )
    relative = _capture_relative(
        variant=variant, repeat=repeat, input_order=input_order
    )
    with _trusted_run_root_fd(
        run_root, manifest, create=True
    ) as run_root_fd, _trusted_staging_fd() as staging_fd:
        assert run_root_fd is not None
        _assert_capture_inventory_fd(run_root_fd, state="capture")
        _write_new_json_at(run_root_fd, staging_fd, relative, capture)
    return output


def _write_hash_outcome_at(
    run_root_fd: int,
    staging_fd: int,
    report: dict,
    *,
    manifest_path: Path,
    product_tree_sha256: str | None,
) -> None:
    comparison = PurePosixPath(
        "oracle/hash", CAPTURE_CORPORA, "comparison.json"
    )
    actual = _inventory_relative_files(run_root_fd)
    if comparison in actual:
        if _read_json_at(run_root_fd, comparison) != report:
            raise ValueError("immutable Task0D comparison does not match retry")
    else:
        _write_new_json_at(run_root_fd, staging_fd, comparison, report)
    common = {
        "schema_version": 1,
        "program": PROGRAM,
        "attempt_id": ATTEMPT_ID,
        "manifest_sha256": _sha256(manifest_path),
        "harness_sha256": _sha256(Path(__file__)),
        "review_disposition_sha256": REVIEW_DISPOSITION_SHA256,
        "product_tree_sha256": product_tree_sha256,
        "comparison_sha256": hashlib.sha256(
            _canonical(report).encode("utf-8")
        ).hexdigest(),
    }
    if report["disposition"] == "proceed":
        marker = PurePosixPath("oracle/hash-proceed.json")
        marker_payload = {**common, "status": "proceed"}
    else:
        marker = PurePosixPath("terminal-reject.json")
        marker_payload = {
            **common,
            "status": "reject",
            "terminal": True,
            "phase": "task0d_hash_oracle",
            "failed_gates": sorted(
                key
                for key, value in report["gates"].items()
                if value is not True
            ),
        }
    _write_new_json_at(run_root_fd, staging_fd, marker, marker_payload)
    _assert_capture_inventory_fd(run_root_fd, state="terminal")


def compare_hash_captures(
    manifest_path: Path, run_root: Path
) -> dict:
    manifest = validate_manifest(manifest_path, require_zero_evidence=False)
    if manifest["capture_authorized"] is not True:
        raise ValueError("Task0D engine review has not authorized comparison")
    run_root = _validate_run_root(run_root, manifest)
    inputs = _capture_inputs(manifest)
    with _trusted_run_root_fd(run_root, manifest, create=False) as run_root_fd:
        if run_root_fd is None:
            raise ValueError("Task0D hash captures do not exist")
        _assert_capture_inventory_fd(run_root_fd, state="compare_input")
        captures: dict[tuple[str, int, str], dict] = {}
        product_tree_sha256: str | None = None
        try:
            for variant in ("baseline", "oracle"):
                for repeat in (1, 2):
                    for input_order in ("canonical", "reverse"):
                        relative = _capture_relative(
                            variant=variant,
                            repeat=repeat,
                            input_order=input_order,
                        )
                        capture = _read_json_at(run_root_fd, relative)
                        product = capture.get("product_identity")
                        if (
                            product_tree_sha256 is None
                            and isinstance(product, dict)
                            and isinstance(product.get("product_tree_sha256"), str)
                        ):
                            product_tree_sha256 = product["product_tree_sha256"]
                        _validate_hash_capture(
                            capture,
                            manifest_path=manifest_path,
                            manifest=manifest,
                            inputs=inputs,
                            variant=variant,
                            repeat=repeat,
                            input_order=input_order,
                        )
                        captures[(variant, repeat, input_order)] = capture
            _assert_distinct_capture_processes(captures)
            deterministic = {}
            for variant in ("baseline", "oracle"):
                projections = {
                    _canonical(
                        _stable_hash_projection(
                            captures[(variant, repeat, input_order)]
                        )
                    )
                    for repeat in (1, 2)
                    for input_order in ("canonical", "reverse")
                }
                deterministic[variant] = len(projections) == 1
            baseline = captures[("baseline", 1, "canonical")]
            oracle = captures[("oracle", 1, "canonical")]
            report = _compare_hash_pair(manifest, baseline, oracle)
            report["deterministic"] = deterministic
            report["gates"]["deterministic"] = all(deterministic.values())
        except Exception as error:
            report = {
                "gates": {"capture_integrity": False},
                "integrity_error": f"{type(error).__name__}: {error}",
                "deterministic": {"baseline": False, "oracle": False},
            }
        report.update(
            {
                "schema_version": 1,
                "program": PROGRAM,
                "attempt_id": ATTEMPT_ID,
                "profile": "hash",
                "corpora": CAPTURE_CORPORA,
                "manifest_sha256": _sha256(manifest_path),
                "harness_sha256": _sha256(Path(__file__)),
                "review_disposition_sha256": REVIEW_DISPOSITION_SHA256,
            }
        )
        report["disposition"] = (
            "proceed" if all(report["gates"].values()) else "reject"
        )
        _privacy_check(report, inputs=inputs)
        with _trusted_staging_fd() as staging_fd:
            _write_hash_outcome_at(
                run_root_fd,
                staging_fd,
                report,
                manifest_path=manifest_path,
                product_tree_sha256=product_tree_sha256,
            )
        return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-skeleton")
    validate.add_argument("--manifest", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--manifest", required=True)
    capture_hash = commands.add_parser("capture-hash")
    capture_hash.add_argument("--manifest", required=True)
    capture_hash.add_argument("--run-root", required=True)
    capture_hash.add_argument("--variant", choices=("baseline", "oracle"), required=True)
    capture_hash.add_argument("--repeat", type=int, choices=(1, 2), required=True)
    capture_hash.add_argument(
        "--input-order", choices=("canonical", "reverse"), required=True
    )
    compare_hash = commands.add_parser("compare-hash")
    compare_hash.add_argument("--manifest", required=True)
    compare_hash.add_argument("--run-root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    manifest_path = Path(arguments.manifest).resolve()
    manifest = validate_manifest(
        manifest_path,
        require_zero_evidence=arguments.command
        not in {"capture-hash", "compare-hash"},
    )
    if arguments.command == "capture-hash":
        output = capture_hash_to_disk(
            manifest_path,
            Path(arguments.run_root),
            variant=arguments.variant,
            repeat=arguments.repeat,
            input_order=arguments.input_order,
        )
        print(str(output.relative_to(ROOT)))
        return 0
    if arguments.command == "compare-hash":
        report = compare_hash_captures(
            manifest_path, Path(arguments.run_root)
        )
        print(_canonical(report), end="")
        return 0 if report["disposition"] == "proceed" else 2
    if arguments.command == "capture":
        raise ValueError(
            "P15-v2 authorizes Task0D hash capture only; online capture remains blocked"
        )
    result = {
        "program": manifest["program"],
        "attempt_id": manifest["attempt_id"],
        "status": manifest["status"],
        "capture_authorized": manifest["capture_authorized"],
        "replacement_seals_pending": 0,
        "v1_status": manifest["v1_terminal"]["status"],
        "click_status": manifest["heldout_seal"]["status"],
        "evidence_state": "absent",
    }
    print(_canonical(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
