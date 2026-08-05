from __future__ import annotations

from copy import deepcopy
import inspect
import json
import os
from pathlib import Path

import pytest

import p15_v2_python_import_symbol_acceptance as acceptance


pytestmark = pytest.mark.archival_acceptance


MANIFEST = (
    Path(__file__).parent
    / "fixtures/p15_v2_python_import_symbols/input_manifest.json"
)


def _payload() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_v2_skeleton_validates_hash_only_authorization() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)

    assert manifest["program"] == "p15-v2"
    assert manifest["attempt_id"] == "p15-v2-attempt-001"
    assert manifest["status"] == "task0d_hash_capture_authorized"
    assert manifest["capture_authorized"] is True
    assert [
        slot["status"]
        for slot in manifest["replacement_efficacy_development"]["slots"]
    ] == [
        "sealed_development_released_digest_verified",
        "sealed_development_released_digest_verified",
    ]


def test_v2_online_capture_remains_blocked_before_hash_proceed() -> None:
    with pytest.raises(ValueError, match="online capture remains blocked"):
        acceptance.main(("capture", "--manifest", str(MANIFEST)))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.__setitem__("attempt_id", "p15-v1-attempt-003"), "identity"),
        (lambda value: value.__setitem__("capture_authorized", False), "identity"),
        (
            lambda value: value["r2"].__setitem__(
                "development_minimum_new_required_items", 2
            ),
            "R2",
        ),
        (
            lambda value: value["r2"]["credit_rule"]["required_all"].pop(),
            "R2",
        ),
        (
            lambda value: value["protected_characterization"].__setitem__(
                "gold_sha256", "0" * 64
            ),
            "hard anchor",
        ),
        (
            lambda value: value["protected_characterization"]["sources"][
                "daily"
            ].__setitem__("role", "efficacy_development"),
            "protected daily",
        ),
        (
            lambda value: value["replacement_efficacy_development"]["slots"][
                0
            ].__setitem__("released_payload_sha256", "0" * 64),
            "binding",
        ),
        (
            lambda value: value["heldout_seal"].__setitem__(
                "required_item_denominator", 11
            ),
            "Click",
        ),
        (
            lambda value: value["online"].__setitem__("planner_enabled", True),
            "online",
        ),
        (
            lambda value: value["v1_terminal"].__setitem__(
                "captures_reusable", True
            ),
            "v1 terminal",
        ),
        (
            lambda value: value["v1_terminal"].__setitem__(
                "reject_index_sha256", "0" * 64
            ),
            "v1 terminal",
        ),
        (
            lambda value: value.__setitem__("closed_world_rule", "changed"),
            "closed-world",
        ),
        (
            lambda value: value["review"].__setitem__(
                "independent_disposition_path", "review.json"
            ),
            "review closure",
        ),
        (
            lambda value: value["review"].__setitem__(
                "task0d_engine_disposition_path", "review.json"
            ),
            "review closure",
        ),
        (
            lambda value: value["review"].__setitem__(
                "task0d_engine_disposition_sha256", "0" * 64
            ),
            "review closure",
        ),
        (
            lambda value: value["review"].__setitem__(
                "task0d_runtime_privacy_fix_disposition_path", "review.json"
            ),
            "review closure",
        ),
        (
            lambda value: value["review"].__setitem__(
                "task0d_runtime_privacy_fix_disposition_sha256", "0" * 64
            ),
            "review closure",
        ),
        (
            lambda value: value["review"].__setitem__(
                "task0d_signal_name_privacy_fix_disposition_path", "review.json"
            ),
            "review closure",
        ),
        (
            lambda value: value["review"].__setitem__(
                "task0d_signal_name_privacy_fix_disposition_sha256", "0" * 64
            ),
            "review closure",
        ),
        (
            lambda value: value["review"].__setitem__(
                "task0d_module_metadata_privacy_fix_disposition_path",
                "review.json",
            ),
            "review closure",
        ),
        (
            lambda value: value["review"].__setitem__(
                "task0d_module_metadata_privacy_fix_disposition_sha256",
                "0" * 64,
            ),
            "review closure",
        ),
        (
            lambda value: value["review"].__setitem__(
                "task0d_structured_identity_privacy_disposition_path",
                "review.json",
            ),
            "review closure",
        ),
        (
            lambda value: value["review"].__setitem__(
                "task0d_structured_identity_privacy_disposition_sha256",
                "0" * 64,
            ),
            "review closure",
        ),
    ],
)
def test_v2_skeleton_mutations_fail_closed(
    tmp_path: Path, mutate, message: str
) -> None:
    payload = deepcopy(_payload())
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        acceptance.validate_manifest(_write(tmp_path, payload))


def test_v1_reject_index_recomputes_all_immutable_artifact_hashes() -> None:
    manifest = _payload()

    acceptance._assert_v1_terminal(manifest["v1_terminal"])


def test_v2_hard_anchors_are_not_taken_from_manifest_self_report() -> None:
    manifest = _payload()

    assert manifest["v1_terminal"]["reject_index_sha256"] == acceptance.V1_REJECT_INDEX_SHA256
    assert manifest["protected_characterization"]["gold_path"] == acceptance.P8_GOLD_PATH
    assert manifest["protected_characterization"]["gold_sha256"] == acceptance.P8_GOLD_SHA256
    assert (
        manifest["replacement_efficacy_development"]["roster_contract_sha256"]
        == acceptance.ROSTER_CONTRACT_SHA256
    )
    assert (
        manifest["replacement_efficacy_development"]["seal_hashes_sha256"]
        == acceptance.SEAL_HASHES_SHA256
    )
    assert (
        manifest["review"]["independent_disposition_path"]
        == acceptance.PLAN_REVIEW_DISPOSITION_PATH
    )
    assert (
        manifest["review"]["independent_disposition_sha256"]
        == acceptance.PLAN_REVIEW_DISPOSITION_SHA256
    )
    assert (
        manifest["review"]["task0d_engine_disposition_path"]
        == acceptance.TASK0D_ENGINE_DISPOSITION_PATH
    )
    assert (
        manifest["review"]["task0d_engine_disposition_sha256"]
        == acceptance.TASK0D_ENGINE_DISPOSITION_SHA256
    )
    assert (
        manifest["review"]["task0d_runtime_privacy_fix_disposition_path"]
        == acceptance.RUNTIME_PRIVACY_FIX_DISPOSITION_PATH
    )
    assert (
        manifest["review"]["task0d_runtime_privacy_fix_disposition_sha256"]
        == acceptance.RUNTIME_PRIVACY_FIX_DISPOSITION_SHA256
    )
    assert (
        manifest["review"]["task0d_signal_name_privacy_fix_disposition_path"]
        == acceptance.SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_PATH
    )
    assert (
        manifest["review"]["task0d_signal_name_privacy_fix_disposition_sha256"]
        == acceptance.SIGNAL_NAME_PRIVACY_FIX_DISPOSITION_SHA256
    )
    assert (
        manifest["review"]["task0d_module_metadata_privacy_fix_disposition_path"]
        == acceptance.MODULE_METADATA_PRIVACY_FIX_DISPOSITION_PATH
    )
    assert (
        manifest["review"]["task0d_module_metadata_privacy_fix_disposition_sha256"]
        == acceptance.MODULE_METADATA_PRIVACY_FIX_DISPOSITION_SHA256
    )
    assert (
        manifest["review"]["task0d_structured_identity_privacy_disposition_path"]
        == acceptance.STRUCTURED_IDENTITY_PRIVACY_DISPOSITION_PATH
    )
    assert (
        manifest["review"]["task0d_structured_identity_privacy_disposition_sha256"]
        == acceptance.STRUCTURED_IDENTITY_PRIVACY_DISPOSITION_SHA256
    )


def test_independent_disposition_binds_reviewed_documents_and_click() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)

    assert manifest["design"] == {
        "path": acceptance.REVIEWED_DESIGN_PATH,
        "sha256": acceptance.REVIEWED_DESIGN_SHA256,
    }
    assert manifest["plan"] == {
        "path": acceptance.REVIEWED_PLAN_PATH,
        "sha256": acceptance.REVIEWED_PLAN_SHA256,
    }
    assert manifest["heldout_seal"]["status"] == "sealed_unopened"
    assert manifest["heldout_seal"]["carry_forward_review"] == "approved"


def test_v2_manifest_rejects_absolute_or_escaping_paths(tmp_path: Path) -> None:
    payload = _payload()
    payload["design"]["path"] = "/tmp/design.md"
    with pytest.raises(ValueError, match="repository-relative"):
        acceptance.validate_manifest(_write(tmp_path, payload))

    payload = _payload()
    payload["plan"]["path"] = "../plan.md"
    with pytest.raises(ValueError, match="repository-relative"):
        acceptance.validate_manifest(_write(tmp_path, payload))


def test_task0d_inputs_close_two_efficacy_and_two_protected_repositories() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)

    assert tuple(inputs["source_specs"]) == acceptance.CAPTURE_REPOSITORIES
    assert len(inputs["gold"]["cases"]) == 26
    assert inputs["input_identity"]["required_item_count"] == {
        "starlette": 12,
        "requests": 12,
        "redink": 17,
        "daily": 40,
    }
    assert inputs["input_identity"]["replacement_payload_sha256"] == {
        "starlette": "309388945b12fb9becc15e2d037d85bfc7f09299f469dde5d8d5a8642fcd6182",
        "requests": "cfa75bd1cf2cba1b4456fbf590c02fe85fd418d0e1e1c4032e880c569fd7f1ee",
    }
    assert {
        contract["evidence_role"]
        for contract in inputs["case_contracts"].values()
    } == {"efficacy_development", "protected_characterization"}


def test_task0d_v1_adapter_restores_all_monkeypatched_inputs() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    v1 = acceptance._v1_harness()
    p8 = __import__("p8_real_python_graphs_acceptance")
    original_validate = v1.validate_manifest
    original_root = v1.DEFAULT_SOURCES
    original_module_projection = v1._module_projection
    original_overlay = v1._overlay_oracle
    original_sources = p8.SOURCES
    original_gold = p8._manifest_or_fail

    with acceptance._adapt_v1_capture(inputs, manifest) as capture:
        assert callable(capture)
        assert v1._module_projection is not original_module_projection
        assert v1._overlay_oracle is not original_overlay
        assert tuple(p8.SOURCES) == acceptance.CAPTURE_REPOSITORIES
        assert len(p8._manifest_or_fail()["cases"]) == 26
        assert all(
            (v1.DEFAULT_SOURCES / spec["dir_name"]).is_symlink()
            for spec in p8.SOURCES.values()
        )

    assert v1.validate_manifest is original_validate
    assert v1.DEFAULT_SOURCES == original_root
    assert v1._module_projection is original_module_projection
    assert v1._overlay_oracle is original_overlay
    assert p8.SOURCES is original_sources
    assert p8._manifest_or_fail is original_gold


def test_task0d_causal_capture_reads_exact_sqlite_identity(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    database = workspace / ".context-search/index.sqlite"
    database.parent.mkdir(parents=True)
    connection = acceptance.sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE code_signals (
              signal_id TEXT, chunk_id TEXT, file_path TEXT, kind TEXT,
              name TEXT, qualified_name TEXT, signature TEXT, arity INTEGER,
              project_unit_key TEXT, producer TEXT, start_line INTEGER,
              start_column INTEGER, end_line INTEGER, end_column INTEGER,
              language TEXT, recallable INTEGER, deleted_at TEXT
            );
            CREATE TABLE chunks (
              chunk_id TEXT, file_path TEXT, start_line INTEGER,
              end_line INTEGER, content TEXT, deleted_at TEXT
            );
            CREATE TABLE code_relations (
              relation_id TEXT, source_signal_id TEXT, kind TEXT,
              target_kind TEXT, target_qualified_name TEXT,
              target_signature TEXT, target_arity INTEGER,
              target_project_unit_key TEXT, target_signal_id TEXT,
              resolution TEXT, producer TEXT, metadata TEXT,
              deleted_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO code_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
            (
                "s5:source",
                "chunk:source",
                "pkg/source.py",
                "module",
                "source",
                "pkg/source.py",
                "",
                None,
                "",
                "core_module",
                1,
                0,
                20,
                0,
                "python",
                1,
            ),
        )
        connection.execute(
            "INSERT INTO code_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
            (
                "s5:target",
                "chunk:target",
                "pkg/target.py",
                "function",
                "run",
                "pkg.target.run",
                "",
                None,
                "",
                "python_ast",
                3,
                0,
                5,
                8,
                "python",
                1,
            ),
        )
        connection.execute(
            "INSERT INTO chunks VALUES (?,?,?,?,?,NULL)",
            ("chunk:target", "pkg/target.py", 1, 8, "def run():\n    pass"),
        )
        connection.execute(
            "INSERT INTO chunks VALUES (?,?,?,?,?,NULL)",
            ("chunk:source", "pkg/source.py", 1, 20, "from .target import run"),
        )
        connection.execute(
            "INSERT INTO code_relations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
            (
                "r5:relation",
                "s5:source",
                "imports",
                "function",
                "pkg.target.run",
                "",
                None,
                "",
                "s5:target",
                "resolved_exact",
                "python_ast",
                json.dumps(
                    {"resolution_basis": "exact_python_imported_symbol"}
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    captured = acceptance._capture_causal_relations(workspace)
    with acceptance.sqlite3.connect(database) as connection:
        active = acceptance._capture_active_python_signal_chunks(connection)

    assert len(captured) == 1
    assert captured[0]["relation"]["relation_id"] == "r5:relation"
    assert captured[0]["source_signal"]["file_path"] == "pkg/source.py"
    assert captured[0]["target_signal"]["qualified_name"] == "pkg.target.run"
    assert captured[0]["target_uniqueness_count"] == 1
    assert len(active) == 2
    target_active = next(
        row for row in active if row["signal"]["signal_id"] == "s5:target"
    )
    assert target_active == {
        "signal": {
            "signal_id": "s5:target",
            "chunk_id": "chunk:target",
            "file_path": "pkg/target.py",
            "kind": "function",
            "name": "run",
            "qualified_name": "pkg.target.run",
            "signature": "",
            "arity": None,
            "project_unit_key": "",
            "producer": "python_ast",
            "start_line": 3,
            "start_column": 0,
            "end_line": 5,
            "end_column": 8,
            "language": "python",
            "recallable": 1,
            "deleted_at": None,
        },
        "chunk": {
            "chunk_id": "chunk:target",
            "file_path": "pkg/target.py",
            "start_line": 1,
            "end_line": 8,
            "content_sha256": acceptance.hashlib.sha256(
                b"def run():\n    pass"
            ).hexdigest(),
            "deleted_at": None,
        },
    }


def test_task0d_privacy_rejects_source_window_or_fragment_in_any_field() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    source = inputs["source_directories"]["starlette"] / (
        "starlette/middleware/exceptions.py"
    )
    lines = source.read_text(encoding="utf-8").splitlines()
    source_window = "\n".join(lines[:80])
    source_fragment = next(
        line
        for line in lines
        if len(line.strip()) >= 32 and " " in line.strip()
    )
    no_whitespace_fragment = "parsed_request_url.scheme.lower()"
    requests_source = (
        inputs["source_directories"]["requests"]
        / "src/requests/adapters.py"
    ).read_text(encoding="utf-8")
    assert no_whitespace_fragment in requests_source
    wrapped_fragment = f"prefix:{no_whitespace_fragment}:suffix"

    for payload in (
        {"opaque": {"value": source_window}},
        {"unrelated_note": source_fragment},
        {source_fragment: "key-position"},
        {"expression": no_whitespace_fragment},
        {"wrapped_value": wrapped_fragment},
        {wrapped_fragment: "wrapped-key-position"},
    ):
        with pytest.raises(ValueError, match="source-body value"):
            acceptance._privacy_check(payload, inputs=inputs)


def test_task0d_privacy_narrowly_allows_closure_validated_qualified_name() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    qualified_name = "starlette.exceptions.StarletteDeprecationWarning"
    frozen_body = (
        inputs["source_directories"]["starlette"]
        / "tests/test_applications.py"
    ).read_text(encoding="utf-8")
    assert qualified_name in frozen_body
    acceptance._privacy_check(
        {
            "index_projections": {
                "starlette": {
                    "active_python_signal_chunks": [
                        {"signal": {"qualified_name": qualified_name}}
                    ]
                }
            }
        },
        inputs=inputs,
    )

    for payload in (
        {"unvalidated_value": qualified_name},
        {qualified_name: "unvalidated-key"},
        {
            "not_the_projection.active_python_signal_chunks[": {
                "signal": {"qualified_name": qualified_name}
            }
        },
        {
            "not_the_projection.causal_relations[": {
                "source_signal": {"qualified_name": qualified_name}
            }
        },
        {
            "not_the_projection.causal_relations[": {
                "target_signal": {"qualified_name": qualified_name}
            }
        },
        {
            "not_the_projection.causal_relations[": {
                "relation": {"target_qualified_name": qualified_name}
            }
        },
    ):
        with pytest.raises(ValueError, match="source-body value"):
            acceptance._privacy_check(payload, inputs=inputs)


def test_task0d_privacy_narrowly_allows_closure_validated_signal_name() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    signal_name = "AwaitableOrContextManagerWrapper"
    frozen_body = (
        inputs["source_directories"]["starlette"]
        / "starlette/_utils.py"
    ).read_text(encoding="utf-8")
    assert signal_name in frozen_body
    acceptance._privacy_check(
        {
            "index_projections": {
                "starlette": {
                    "active_python_signal_chunks": [
                        {"signal": {"name": signal_name}}
                    ]
                }
            }
        },
        inputs=inputs,
    )

    for payload in (
        {"unvalidated_value": signal_name},
        {signal_name: "unvalidated-key"},
        {
            "not_the_projection.active_python_signal_chunks[": {
                "signal": {"name": signal_name}
            }
        },
    ):
        with pytest.raises(ValueError, match="source-body value"):
            acceptance._privacy_check(payload, inputs=inputs)


def test_task0d_privacy_narrowly_allows_closed_module_metadata() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    specifier = "src.services.market_symbol_utils"
    frozen_body = (
        inputs["source_directories"]["daily"]
        / "data_provider/base.py"
    ).read_text(encoding="utf-8")
    assert specifier in frozen_body
    metadata = {
        "selector_state": "exact",
        "specifier": specifier,
        "candidates": ["src/services/market_symbol_utils.py"],
        "import_form": "from",
        "relative_level": 0,
        "first_source_line": 29,
        "first_source_column": 0,
        "occurrence_count": 1,
    }
    metadata_json = json.dumps(
        metadata, separators=(",", ":"), sort_keys=True
    )

    acceptance._privacy_check(
        {
            "index_projections": {
                "daily": {
                    "module_relations": [
                        {
                            "target_name": specifier,
                            "metadata_json": metadata_json,
                        }
                    ]
                }
            }
        },
        inputs=inputs,
    )

    with pytest.raises(ValueError, match="source-body value"):
        acceptance._privacy_check(
            {"displaced_metadata_json": metadata_json}, inputs=inputs
        )
    with pytest.raises(ValueError, match="invalid closed module metadata"):
        acceptance._privacy_check(
            {
                "index_projections": {
                    "daily": {
                        "module_relations": [
                            {"metadata_json": "not-json"}
                        ]
                    }
                }
            },
            inputs=inputs,
        )
    injected = dict(metadata)
    injected["source_body"] = "parsed_request_url.scheme.lower()"
    with pytest.raises(ValueError, match="invalid closed module metadata"):
        acceptance._privacy_check(
            {
                "index_projections": {
                    "daily": {
                        "module_relations": [
                            {
                                "metadata_json": json.dumps(
                                    injected,
                                    separators=(",", ":"),
                                    sort_keys=True,
                                )
                            }
                        ]
                    }
                }
            },
            inputs=inputs,
        )


def _payload_at_tuple_path(path: tuple[str | int, ...], value: str) -> dict:
    root: dict = {}
    current: dict | list = root
    for index, segment in enumerate(path):
        last = index == len(path) - 1
        if isinstance(current, dict):
            if last:
                current[segment] = value
            else:
                child = [] if type(path[index + 1]) is int else {}
                current[segment] = child
                current = child
        else:
            assert type(segment) is int and segment == len(current)
            if last:
                current.append(value)
            else:
                child = [] if type(path[index + 1]) is int else {}
                current.append(child)
                current = child
    return root


def test_task0d_privacy_structured_identity_allowlist_is_exact() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    file_path = "src/services/generation_backend_status_service.py"
    signal_name = "AwaitableOrContextManagerWrapper"
    qualified_name = "starlette.exceptions.StarletteDeprecationWarning"
    specifier = "src.services.market_symbol_utils"
    causal_metadata = json.dumps(
        {
            "resolution_basis": "exact_python_imported_symbol",
            "selector_state": "exact",
            "target_file_path": "src/services/market_symbol_utils.py",
            "target_signal_kinds": ["type", "function"],
            "imported_name": "is_suffix_market_symbol",
            "local_names": ["is_suffix_market_symbol"],
            "relative_level": 0,
            "first_source_line": 29,
            "first_source_column": 0,
            "occurrence_count": 1,
            "module_relation_id": "r5:" + "1" * 64,
            "module_selector": {
                "state": "exact",
                "specifier": specifier,
                "target_file_path": "src/services/market_symbol_utils.py",
            },
            "oracle_actual_target_kind": "function",
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    module_metadata = json.dumps(
        {
            "selector_state": "exact",
            "specifier": specifier,
            "candidates": ["src/services/market_symbol_utils.py"],
            "import_form": "from",
            "relative_level": 0,
            "first_source_line": 29,
            "first_source_column": 0,
            "occurrence_count": 1,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    cases = [
        (
            ("cases", "daily-runtime-scheduler", "selected", 0, "path"),
            file_path,
        ),
        (
            (
                "index_projections",
                "daily",
                "active_python_signal_chunks",
                0,
                "chunk",
                "file_path",
            ),
            file_path,
        ),
        (
            (
                "index_projections",
                "daily",
                "active_python_signal_chunks",
                0,
                "signal",
                "file_path",
            ),
            file_path,
        ),
        (
            (
                "index_projections",
                "starlette",
                "active_python_signal_chunks",
                0,
                "signal",
                "name",
            ),
            signal_name,
        ),
        (
            (
                "index_projections",
                "starlette",
                "active_python_signal_chunks",
                0,
                "signal",
                "qualified_name",
            ),
            qualified_name,
        ),
        (
            (
                "index_projections",
                "daily",
                "causal_relations",
                0,
                "relation",
                "metadata_json",
            ),
            causal_metadata,
        ),
        (
            (
                "index_projections",
                "starlette",
                "causal_relations",
                0,
                "relation",
                "target_qualified_name",
            ),
            qualified_name,
        ),
        (
            (
                "index_projections",
                "daily",
                "causal_relations",
                0,
                "source_signal",
                "file_path",
            ),
            file_path,
        ),
        (
            (
                "index_projections",
                "starlette",
                "causal_relations",
                0,
                "source_signal",
                "qualified_name",
            ),
            qualified_name,
        ),
        (
            (
                "index_projections",
                "daily",
                "causal_relations",
                0,
                "target_signal",
                "file_path",
            ),
            file_path,
        ),
        (
            (
                "index_projections",
                "starlette",
                "causal_relations",
                0,
                "target_signal",
                "qualified_name",
            ),
            qualified_name,
        ),
        (
            (
                "index_projections",
                "daily",
                "exact_targets",
                0,
                "target_file_path",
            ),
            file_path,
        ),
        (
            (
                "index_projections",
                "daily",
                "module_relations",
                0,
                "metadata_json",
            ),
            module_metadata,
        ),
        (
            (
                "index_projections",
                "daily",
                "module_relations",
                0,
                "source_file_path",
            ),
            file_path,
        ),
        (
            (
                "index_projections",
                "daily",
                "module_relations",
                0,
                "target_name",
            ),
            specifier,
        ),
        (
            (
                "index_projections",
                "starlette",
                "module_relations",
                0,
                "target_qualified_name",
            ),
            qualified_name,
        ),
        (
            (
                "index_projections",
                "daily",
                "target_states",
                0,
                "target_file_path",
            ),
            file_path,
        ),
    ]
    assert len(cases) == len(acceptance._STRUCTURED_IDENTITY_PRIVACY_ALLOWLIST) == 17
    for path, value in cases:
        acceptance._privacy_check(
            _payload_at_tuple_path(path, value), inputs=inputs
        )
        for displaced in (
            {"displaced_value": value},
            {value: "mapping-key"},
            {f"not-real:{'.'.join(map(str, path))}": {"value": value}},
        ):
            with pytest.raises(ValueError, match="source-body value"):
                acceptance._privacy_check(displaced, inputs=inputs)

    with pytest.raises(ValueError, match="source-body value"):
        acceptance._privacy_check(
            {
                "index_projections": {
                    "starlette": {
                        "active_python_signal_chunks": [
                            {"signal": {"signature": qualified_name}}
                        ]
                    }
                }
            },
            inputs=inputs,
        )


def test_task0d_slots_are_complete_and_write_new(tmp_path: Path) -> None:
    slots = acceptance._allowed_capture_paths(tmp_path)

    assert len(slots) == 8
    assert {
        path.name for path in slots
    } == {
        f"{variant}-r{repeat}-{order}.json"
        for variant in ("baseline", "oracle")
        for repeat in (1, 2)
        for order in ("canonical", "reverse")
    }
    run_root_fd = os.open(tmp_path, acceptance._directory_open_flags())
    staging = tmp_path / "staging"
    staging.mkdir()
    staging_fd = os.open(staging, acceptance._directory_open_flags())
    try:
        relative = acceptance._capture_relative(
            variant="baseline", repeat=1, input_order="reverse"
        )
        acceptance._write_new_json_at(
            run_root_fd, staging_fd, relative, {"value": 1}
        )
        with pytest.raises(ValueError, match="already exists"):
            acceptance._write_new_json_at(
                run_root_fd, staging_fd, relative, {"value": 2}
            )
    finally:
        os.close(staging_fd)
        os.close(run_root_fd)


def _selected(path: str, *, rank: int, exact: bool = False) -> dict:
    chunk_id = f"chunk:{path}"
    row = {
        "rank": rank,
        "path": path,
        "start_line": 1,
        "end_line": 20,
        "score": 1.0 / rank,
        "score_parts": {"direct": 1.0},
        "reasons": ["direct"],
        "chunk_id": chunk_id,
        "origin_chunk_ids": [chunk_id],
        "rank_history": [],
        "stage_trajectory": [],
        "exact_witness": None,
    }
    if exact:
        row["score_parts"] = {"graph_imports_match": 0.68}
        row["reasons"] = ["static module dependency"]
        row["exact_witness"] = {
            "relation_id": f"r5:exact:{path}",
            "module_relation_id": f"r5:module:{path}",
            "source_signal_id": f"s5:source:{path}",
            "target_signal_id": f"s5:target:{path}",
            "target_chunk_id": chunk_id,
            "target_file_path": path,
            "actual_target_kind": "function",
            "target_start_line": 1,
            "target_end_line": 10,
        }
    return row


def _synthetic_causal_relation(inputs: dict, repository: str, target_path: str):
    source_root = inputs["source_directories"][repository]
    spec = inputs["source_specs"][repository]
    identity = __import__("p8_python_graph_identity")
    files = identity.validate_protected_source(
        source_root,
        patterns=spec["patterns"],
        expected_count=spec["expected_count"],
        expected_inventory_sha256=spec["inventory_sha256"],
        expected_content_sha256=spec["content_sha256"],
    )
    unit = ""
    active_paths = {str(relative): unit for relative in files}
    v1 = acceptance._v1_harness()
    chosen = None
    for source_relative_value in files:
        source_relative = Path(source_relative_value)
        if source_relative.suffix not in {".py", ".pyw"}:
            continue
        source_path = source_relative.as_posix()
        source_tree = acceptance.ast.parse(
            (source_root / source_relative).read_bytes(), filename=source_path
        )
        for node in acceptance.ast.walk(source_tree):
            if not isinstance(node, acceptance.ast.ImportFrom) or not node.module:
                continue
            state, specifier, resolved = v1._independent_module_selector(
                source_path=source_path,
                project_unit_key=unit,
                module=node.module,
                relative_level=node.level or 0,
                active_paths=active_paths,
            )
            if state != "exact" or resolved != target_path:
                continue
            target_tree = acceptance.ast.parse(
                (source_root / target_path).read_bytes(), filename=target_path
            )
            declarations = {
                declaration.name: declaration
                for declaration in target_tree.body
                if isinstance(
                    declaration,
                    (
                        acceptance.ast.ClassDef,
                        acceptance.ast.FunctionDef,
                        acceptance.ast.AsyncFunctionDef,
                    ),
                )
            }
            for alias in node.names:
                if alias.name in declarations:
                    chosen = (
                        source_path,
                        source_tree,
                        node,
                        alias,
                        specifier,
                        declarations[alias.name],
                    )
                    break
            if chosen:
                break
        if chosen:
            break
    assert chosen is not None, target_path
    source_path, source_tree, import_node, alias, specifier, declaration = chosen
    target_kind = (
        "type" if isinstance(declaration, acceptance.ast.ClassDef) else "function"
    )
    declaration_start = min(
        [declaration, *declaration.decorator_list],
        key=lambda node: (node.lineno, node.col_offset),
    )
    target_qname = f"{v1._module_name(target_path, unit)}.{alias.name}"
    graph = __import__("context_search_tool.graph_contract", fromlist=["*"])
    target_lines = (source_root / target_path).read_text(
        encoding="utf-8"
    ).splitlines()
    chunk_start_line = ((declaration_start.lineno - 1) // 80) * 80 + 1
    chunk_end_line = min(chunk_start_line + 79, len(target_lines))
    chunk_content = "\n".join(
        target_lines[chunk_start_line - 1 : chunk_end_line]
    )
    target_chunk_id = acceptance._deterministic_chunk_id(
        target_path, chunk_start_line, chunk_end_line, chunk_content
    )
    target_module_chunk_end = min(80, len(target_lines))
    target_module_chunk_content = "\n".join(
        target_lines[:target_module_chunk_end]
    )
    target_module_chunk_id = acceptance._deterministic_chunk_id(
        target_path,
        1,
        target_module_chunk_end,
        target_module_chunk_content,
    )
    source_lines = (source_root / source_path).read_text(
        encoding="utf-8"
    ).splitlines()
    source_chunk_end = min(80, len(source_lines))
    source_chunk_content = "\n".join(source_lines[:source_chunk_end])
    source_chunk_id = acceptance._deterministic_chunk_id(
        source_path, 1, source_chunk_end, source_chunk_content
    )
    source_signal = {
        "file_path": source_path,
        "kind": "module",
        "qualified_name": source_path,
        "signature": "",
        "start_line": 1,
        "start_column": 0,
        "end_line": source_chunk_end,
        "end_column": 0,
        "producer": "core_module",
        "project_unit_key": unit,
        "chunk_id": source_chunk_id,
        "language": "python",
    }
    target_signal = {
        "file_path": target_path,
        "kind": target_kind,
        "qualified_name": target_qname,
        "signature": "",
        "start_line": declaration_start.lineno,
        "start_column": declaration_start.col_offset,
        "end_line": declaration.end_lineno,
        "end_column": declaration.end_col_offset,
        "producer": "python_ast",
        "project_unit_key": unit,
        "chunk_id": target_chunk_id,
        "language": "python",
    }
    source_id = graph.generate_v5_signal_id(
        **{key: source_signal[key] for key in (
            "file_path", "kind", "qualified_name", "signature", "start_line",
            "start_column", "end_line", "end_column", "producer"
        )}
    )
    target_id = graph.generate_v5_signal_id(
        **{key: target_signal[key] for key in (
            "file_path", "kind", "qualified_name", "signature", "start_line",
            "start_column", "end_line", "end_column", "producer"
        )}
    )
    relation_id = graph.generate_v5_relation_id(
        source_signal_id=source_id,
        kind="imports",
        target_kind=target_kind,
        target_qualified_name=target_qname,
        target_signature="",
        target_arity=None,
        target_project_unit_key=unit,
        producer="python_ast",
    )
    module_relation_id = graph.generate_v5_relation_id(
        source_signal_id=source_id,
        kind="imports",
        target_kind="module",
        target_qualified_name=target_path,
        target_signature="",
        target_arity=None,
        target_project_unit_key=unit,
        producer="python_ast",
    )
    same_facts = [
        (node, candidate)
        for node in acceptance.ast.walk(source_tree)
        if isinstance(node, acceptance.ast.ImportFrom)
        and "." * (node.level or 0) + (node.module or "") == specifier
        for candidate in node.names
        if candidate.name == alias.name
    ]
    same_module_nodes = [
        node
        for node in acceptance.ast.walk(source_tree)
        if isinstance(node, acceptance.ast.ImportFrom)
        and "." * (node.level or 0) + (node.module or "") == specifier
    ]
    metadata = {
        "resolution_basis": "exact_python_imported_symbol",
        "selector_state": "exact",
        "target_file_path": target_path,
        "target_signal_kinds": ["type", "function"],
        "imported_name": alias.name,
        "local_names": sorted({candidate.asname or candidate.name for _, candidate in same_facts}),
        "relative_level": import_node.level or 0,
        "first_source_line": min(node.lineno for node, _ in same_facts),
        "first_source_column": min(
            node.col_offset
            for node, _ in same_facts
            if node.lineno == min(value.lineno for value, _ in same_facts)
        ),
        "occurrence_count": len(same_facts),
        "module_relation_id": module_relation_id,
        "module_selector": {
            "state": "exact",
            "specifier": specifier,
            "target_file_path": target_path,
        },
        "oracle_actual_target_kind": target_kind,
    }
    relation = {
        "relation_id": relation_id,
        "source_signal_id": source_id,
        "kind": "imports",
        "target_kind": target_kind,
        "target_qualified_name": target_qname,
        "target_signature": "",
        "target_arity": None,
        "target_project_unit_key": unit,
        "target_signal_id": target_id,
        "resolution": "resolved_exact",
        "producer": "python_ast",
        "metadata_json": json.dumps(metadata, separators=(",", ":"), sort_keys=True),
    }
    causal = {
        "relation": relation,
        "source_signal": source_signal,
        "target_signal": target_signal,
        "target_uniqueness_count": 1,
    }
    exact = {
        "relation_id": relation_id,
        "module_relation_id": module_relation_id,
        "source_signal_id": source_id,
        "source_chunk_id": source_signal["chunk_id"],
        "target_signal_id": target_id,
        "target_chunk_id": target_signal["chunk_id"],
        "actual_target_kind": target_kind,
    }
    witness = {
        "relation_id": relation_id,
        "module_relation_id": module_relation_id,
        "source_signal_id": source_id,
        "target_signal_id": target_id,
        "target_chunk_id": target_signal["chunk_id"],
        "target_file_path": target_path,
        "actual_target_kind": target_kind,
        "target_start_line": target_signal["start_line"],
        "target_end_line": target_signal["end_line"],
    }
    module = {
        "relation_id": module_relation_id,
        "source_signal_id": source_id,
        "source_chunk_id": source_chunk_id,
        "source_file_path": source_path,
        "target_name": specifier,
        "kind": "imports",
        "target_kind": "module",
        "target_qualified_name": target_path,
        "target_signature": "",
        "target_arity": None,
        "target_project_unit_key": unit,
        "target_signal_id": graph.generate_core_module_signal_id(
            file_path=target_path,
            start_line=1,
            start_column=0,
            end_line=target_module_chunk_end,
            end_column=0,
        ),
        "resolution": "resolved_exact",
        "producer": "python_ast",
        "metadata_json": json.dumps(
            {
                "selector_state": "exact",
                "specifier": specifier,
                "candidates": [target_path],
                "import_form": "from",
                "relative_level": import_node.level or 0,
                "first_source_line": min(
                    node.lineno for node in same_module_nodes
                ),
                "first_source_column": min(
                    node.col_offset
                    for node in same_module_nodes
                    if node.lineno
                    == min(value.lineno for value in same_module_nodes)
                ),
                "occurrence_count": len(same_module_nodes),
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
    }
    source_active = {
        "signal": {
            "signal_id": source_id,
            "chunk_id": source_chunk_id,
            "file_path": source_path,
            "kind": "module",
            "name": source_path,
            "qualified_name": source_path,
            "signature": "",
            "arity": None,
            "project_unit_key": unit,
            "producer": "core_module",
            "start_line": 1,
            "start_column": 0,
            "end_line": source_chunk_end,
            "end_column": 0,
            "language": "python",
            "recallable": 0,
            "deleted_at": None,
        },
        "chunk": {
            "chunk_id": source_chunk_id,
            "file_path": source_path,
            "start_line": 1,
            "end_line": source_chunk_end,
            "content_sha256": acceptance.hashlib.sha256(
                source_chunk_content.encode("utf-8")
            ).hexdigest(),
            "deleted_at": None,
        },
    }
    target_module_active = {
        "signal": {
            "signal_id": module["target_signal_id"],
            "chunk_id": target_module_chunk_id,
            "file_path": target_path,
            "kind": "module",
            "name": target_path,
            "qualified_name": target_path,
            "signature": "",
            "arity": None,
            "project_unit_key": unit,
            "producer": "core_module",
            "start_line": 1,
            "start_column": 0,
            "end_line": target_module_chunk_end,
            "end_column": 0,
            "language": "python",
            "recallable": 0,
            "deleted_at": None,
        },
        "chunk": {
            "chunk_id": target_module_chunk_id,
            "file_path": target_path,
            "start_line": 1,
            "end_line": target_module_chunk_end,
            "content_sha256": acceptance.hashlib.sha256(
                target_module_chunk_content.encode("utf-8")
            ).hexdigest(),
            "deleted_at": None,
        },
    }
    target_active = {
        "signal": {
            "signal_id": target_id,
            "chunk_id": target_chunk_id,
            "file_path": target_path,
            "kind": target_kind,
            "name": alias.name,
            "qualified_name": target_qname,
            "signature": "",
            "arity": None,
            "project_unit_key": unit,
            "producer": "python_ast",
            "start_line": declaration_start.lineno,
            "start_column": declaration_start.col_offset,
            "end_line": declaration.end_lineno,
            "end_column": declaration.end_col_offset,
            "language": "python",
            "recallable": 1,
            "deleted_at": None,
        },
        "chunk": {
            "chunk_id": target_chunk_id,
            "file_path": target_path,
            "start_line": chunk_start_line,
            "end_line": chunk_end_line,
            "content_sha256": acceptance.hashlib.sha256(
                chunk_content.encode("utf-8")
            ).hexdigest(),
            "deleted_at": None,
        },
    }
    return causal, exact, witness, module, [
        source_active,
        target_module_active,
        target_active,
    ]


def _synthetic_capture(variant: str) -> dict:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    cases = {}
    projections = {}
    repositories = {}
    gain_cases = {
        "starlette-static-files",
        "starlette-exception-dispatch",
        "requests-session-flow",
    }
    for repository in acceptance.CAPTURE_REPOSITORIES:
        exact_targets = {}
        projections[repository] = {
            "exact_relation_count": 0,
            "graph_omitted_imported_symbols": 0,
            "omitted_by_source": {},
            "maximum_exact_relations_per_source": 0,
            "terminal_counts": {},
            "target_states": {},
            "exact_targets": exact_targets,
            "causal_relations": [],
            "active_python_signal_chunks": [],
            "active_python_signal_chunk_count": 0,
            "active_python_signal_chunk_sha256": "",
            "module_relation_count": 0,
            "module_relations": [],
            "module_projection_sha256": "",
            "non_python_projection_sha256": "f" * 64,
            "work_caps": {
                "max_graph_seed_signals": 512,
                "max_resolved_graph_hops": 4,
                "max_edges_per_signal_direction": 64,
                "max_relation_expanded_candidates": 1000,
                "observed_maximum_outgoing_rows": 10,
                "observed_maximum_incoming_rows": 10,
            },
        }
        repositories[repository] = {
            "selected_files": inputs["source_specs"][repository][
                "expected_count"
            ],
            "structure": {"chunks": 1},
            "index_sqlite_bytes": 100,
        }
    for frozen in inputs["gold"]["cases"]:
        case_id = frozen["id"]
        repository = frozen["repo"]
        contract = inputs["case_contracts"][case_id]
        winner = contract["protected_winner"] or frozen["required"][0]["path"]
        selected = [_selected(winner, rank=1)]
        gain_path = None
        if case_id in gain_cases:
            gain_path = next(
                item["path"] for item in frozen["required"] if item["path"] != winner
            )
            causal, exact, witness, module, active = _synthetic_causal_relation(
                inputs, repository, gain_path
            )
            projections[repository]["module_relations"].append(module)
            active_rows = projections[repository][
                "active_python_signal_chunks"
            ]
            for active_row in active:
                if all(
                    row["signal"]["signal_id"]
                    != active_row["signal"]["signal_id"]
                    for row in active_rows
                ):
                    active_rows.append(active_row)
            if variant == "oracle":
                target_active = next(
                    row
                    for row in active
                    if row["signal"]["producer"] == "python_ast"
                )
                selected.append(_selected(gain_path, rank=2, exact=True))
                selected[-1].update(
                    {
                        "start_line": target_active["chunk"]["start_line"],
                        "end_line": target_active["chunk"]["end_line"],
                        "chunk_id": target_active["chunk"]["chunk_id"],
                        "origin_chunk_ids": [
                            target_active["chunk"]["chunk_id"]
                        ],
                        "exact_witness": witness,
                    }
                )
                projections[repository]["exact_relation_count"] += 1
                projections[repository]["maximum_exact_relations_per_source"] = 1
                projections[repository]["exact_targets"][gain_path] = [exact]
                projections[repository]["causal_relations"].append(causal)
        required = []
        for item in frozen["required"]:
            rank = next(
                (row["rank"] for row in selected if row["path"] == item["path"]),
                None,
            )
            required.append(
                {
                    "path": item["path"],
                    "role": item["role"],
                    "rank": rank,
                    "state": "selected" if rank is not None else "not_selected",
                }
            )
        cases[case_id] = {
            "repo": repository,
            "selected": selected,
            "required": required,
            "contextual": frozen["contextual"],
            "trace": {"stages": []},
            "evidence_role": contract["evidence_role"],
            "protected_winner": contract["protected_winner"],
            "membership_change_eligible": contract[
                "membership_change_eligible"
            ],
        }
    for projection in projections.values():
        active_rows = sorted(
            projection["active_python_signal_chunks"],
            key=lambda row: row["signal"]["signal_id"],
        )
        projection["active_python_signal_chunks"] = active_rows
        projection["active_python_signal_chunk_count"] = len(active_rows)
        projection["active_python_signal_chunk_sha256"] = (
            acceptance._json_value_sha256(active_rows)
        )
        exact_source_counts = {}
        for rows in projection["exact_targets"].values():
            for row in rows:
                source = row["source_signal_id"]
                exact_source_counts[source] = exact_source_counts.get(source, 0) + 1
        projection["maximum_exact_relations_per_source"] = max(
            exact_source_counts.values(), default=0
        )
        module_rows = projection["module_relations"]
        rendered = [
            [
                row["relation_id"],
                row["source_signal_id"],
                row["target_signal_id"],
                row["resolution"],
                row["target_qualified_name"],
                row["metadata_json"],
            ]
            for row in module_rows
        ]
        projection["module_relation_count"] = len(module_rows)
        projection["module_projection_sha256"] = acceptance.hashlib.sha256(
            acceptance._v1_harness()._canonical(rendered).encode("utf-8")
        ).hexdigest()
        projection["exact_targets"] = [
            {"target_file_path": path, "relations": rows}
            for path, rows in sorted(projection["exact_targets"].items())
        ]
        projection["target_states"] = [
            {"target_file_path": path, "states": states}
            for path, states in sorted(projection["target_states"].items())
        ]
    return {
        "schema_version": 2,
        "program": acceptance.PROGRAM,
        "attempt_id": acceptance.ATTEMPT_ID,
        "phase": "oracle",
        "corpora": acceptance.CAPTURE_CORPORA,
        "profile": "hash",
        "variant": variant,
        "input_order": "canonical",
        "repeat": 1,
        "slot": f"oracle:{acceptance.CAPTURE_CORPORA}:hash:{variant}:r1:canonical",
        "manifest_sha256": acceptance._sha256(MANIFEST),
        "harness_sha256": acceptance._sha256(Path(acceptance.__file__)),
        "review_disposition_sha256": acceptance.REVIEW_DISPOSITION_SHA256,
        "input_identity": inputs["input_identity"],
        "source_roles": acceptance.SOURCE_ROLES,
        "product_identity": {
            "baseline": acceptance.BASELINE,
            "head": "7e05f6f5766acbc61e8ab639f5cb92aa3996be1a",
            "tracked_diff_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "untracked": {},
            "product_tree_sha256": "a" * 64,
            "clean_against_baseline": True,
        },
        "implementation": {
            **acceptance._expected_implementation_identity(),
            "process_identity": {
                "pid": 1000,
                "invocation_id": "1" * 64,
            },
        },
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
            "base_url": None,
            "planner_enabled": False,
        },
        "embedding_requests": {
            **{repository: 0 for repository in acceptance.CAPTURE_REPOSITORIES},
            "total": 0,
        },
        "repositories": repositories,
        "index_projections": projections,
        "cases": cases,
        "timing": {
            "index_seconds": {
                repository: 1.0 for repository in acceptance.CAPTURE_REPOSITORIES
            },
            "query_case_seconds": {case_id: 0.01 for case_id in cases},
        },
        "observed": {
            "local_model_calls": 0,
            "planner_calls": 0,
            "fallback_count": 0,
            "error_count": 0,
            "skip_count": 0,
            "retrieval_calls": len(cases),
        },
    }


def _exact_relation_groups(projection: dict) -> list[list[dict]]:
    return [item["relations"] for item in projection["exact_targets"]]


def test_task0d_capture_schema_closes_identity_caps_witness_and_counters() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    capture = _synthetic_capture("oracle")

    acceptance._validate_hash_capture(
        capture,
        manifest_path=MANIFEST,
        manifest=manifest,
        inputs=inputs,
        variant="oracle",
        repeat=1,
        input_order="canonical",
    )

    broken = deepcopy(capture)
    broken["observed"]["local_model_calls"] = 1
    with pytest.raises(ValueError, match="observed counters"):
        acceptance._validate_hash_capture(
            broken,
            manifest_path=MANIFEST,
            manifest=manifest,
            inputs=inputs,
            variant="oracle",
            repeat=1,
            input_order="canonical",
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda capture: capture["implementation"].__setitem__(
                "base_commit", "0" * 40
            ),
            "implementation identity changed",
        ),
        (
            lambda capture: capture["cases"]["starlette-static-files"][
                "selected"
            ][1]["exact_witness"].__setitem__("relation_id", "r5:forged"),
            "not projection-bound",
        ),
        (
            lambda capture: capture["index_projections"]["starlette"][
                "exact_targets"
            ][0]["relations"][0].__setitem__(
                "module_relation_id", "r5:missing-module"
            ),
            "lacks its module relation",
        ),
        (
            lambda capture: capture["index_projections"]["starlette"][
                "work_caps"
            ].__setitem__("observed_maximum_outgoing_rows", 1001),
            "work cap changed",
        ),
    ],
)
def test_task0d_capture_rejects_forged_nested_evidence(mutate, message: str) -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    capture = _synthetic_capture("oracle")
    mutate(capture)

    with pytest.raises(ValueError, match=message):
        acceptance._validate_hash_capture(
            capture,
            manifest_path=MANIFEST,
            manifest=manifest,
            inputs=inputs,
            variant="oracle",
            repeat=1,
            input_order="canonical",
        )


def test_task0d_trusted_run_root_rejects_symlink_and_non_directory_components(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(acceptance, "ROOT", tmp_path)
    manifest = {"evidence": {"run_root": "expected/evidence"}}
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "expected").symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink or non-directory"):
        with acceptance._trusted_run_root_fd(
            tmp_path / "expected/evidence", manifest, create=True
        ):
            pass

    (tmp_path / "expected").unlink()
    ordinary_file = tmp_path / "ordinary-file"
    ordinary_file.write_text("not a directory", encoding="utf-8")
    manifest = {"evidence": {"run_root": "ordinary-file/evidence"}}
    with pytest.raises(ValueError, match="symlink or non-directory"):
        with acceptance._trusted_run_root_fd(
            tmp_path / "ordinary-file/evidence", manifest, create=True
        ):
            pass


def test_task0d_run_root_dir_fd_survives_parent_swap(
    tmp_path: Path, monkeypatch
) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    retained = tmp_path / "retained"
    manifest = {"evidence": {"run_root": "safe/run"}}
    monkeypatch.setattr(acceptance, "ROOT", tmp_path)
    original = acceptance._open_child_directory
    swapped = False

    def swap_after_open(parent_fd: int, name: str, *, create: bool) -> int:
        nonlocal swapped
        descriptor = original(parent_fd, name, create=create)
        if name == "safe" and not swapped:
            safe.rename(retained)
            safe.symlink_to(attacker, target_is_directory=True)
            swapped = True
        return descriptor

    monkeypatch.setattr(acceptance, "_open_child_directory", swap_after_open)
    with acceptance._trusted_run_root_fd(
        tmp_path / "safe/run", manifest, create=True
    ) as run_root_fd:
        assert run_root_fd is not None

    assert (retained / "run").is_dir()
    assert not (attacker / "run").exists()


def test_task0d_run_root_does_not_resolve_a_symlink_alias(
    tmp_path: Path, monkeypatch
) -> None:
    expected = tmp_path / "expected"
    expected.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(expected, target_is_directory=True)
    manifest = {"evidence": {"run_root": "expected"}}
    monkeypatch.setattr(acceptance, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="run root changed"):
        acceptance._validate_run_root(alias, manifest)


def test_task0d_requires_eight_distinct_capture_processes() -> None:
    slots = {
        (variant, repeat, order): _synthetic_capture(variant)
        for variant in ("baseline", "oracle")
        for repeat in (1, 2)
        for order in ("canonical", "reverse")
    }
    with pytest.raises(ValueError, match="eight separate processes"):
        acceptance._assert_distinct_capture_processes(slots)

    for index, capture in enumerate(slots.values(), start=1):
        capture["implementation"]["process_identity"] = {
            "pid": 1000,
            "invocation_id": f"{index:064x}",
        }
    with pytest.raises(ValueError, match="eight separate processes"):
        acceptance._assert_distinct_capture_processes(slots)

    for index, capture in enumerate(slots.values(), start=1):
        capture["implementation"]["process_identity"]["pid"] = 1000 + index
    acceptance._assert_distinct_capture_processes(slots)


def test_task0d_module_binding_rejects_rehashed_forged_metadata() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    capture = _synthetic_capture("oracle")
    projection = capture["index_projections"]["starlette"]
    forged_metadata = json.loads(
        projection["module_relations"][0]["metadata_json"]
    )
    forged_metadata["candidates"] = ["forged.py"]
    projection["module_relations"][0]["metadata_json"] = json.dumps(
        forged_metadata,
        separators=(",", ":"),
        sort_keys=True,
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
        for row in projection["module_relations"]
    ]
    projection["module_projection_sha256"] = acceptance.hashlib.sha256(
        acceptance._v1_harness()._canonical(rendered).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ValueError, match="module relation metadata is inconsistent"):
        acceptance._validate_hash_capture(
            capture,
            manifest_path=MANIFEST,
            manifest=manifest,
            inputs=inputs,
            variant="oracle",
            repeat=1,
            input_order="canonical",
        )


def test_task0d_module_binding_rejects_unreferenced_self_consistent_row() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    capture = _synthetic_capture("oracle")
    projection = capture["index_projections"]["starlette"]
    source_active = next(
        row
        for row in projection["active_python_signal_chunks"]
        if row["signal"]["producer"] == "core_module"
    )
    source = source_active["signal"]
    specifier = "AwaitableOrContextManagerWrapper"
    assert specifier in (
        inputs["source_directories"]["starlette"]
        / "starlette/_utils.py"
    ).read_text(encoding="utf-8")
    metadata = {
        "selector_state": "exact",
        "specifier": specifier,
        "candidates": [source["file_path"]],
        "import_form": "from",
        "relative_level": 0,
        "first_source_line": 1,
        "first_source_column": 0,
        "occurrence_count": 1,
    }
    graph = __import__("context_search_tool.graph_contract", fromlist=["*"])
    forged = {
        "relation_id": graph.generate_v5_relation_id(
            source_signal_id=source["signal_id"],
            kind="imports",
            target_kind="module",
            target_qualified_name=source["file_path"],
            target_signature="",
            target_arity=None,
            target_project_unit_key=source["project_unit_key"],
            producer="python_ast",
        ),
        "source_signal_id": source["signal_id"],
        "source_chunk_id": source["chunk_id"],
        "source_file_path": source["file_path"],
        "target_name": specifier,
        "kind": "imports",
        "target_kind": "module",
        "target_qualified_name": source["file_path"],
        "target_signature": "",
        "target_arity": None,
        "target_project_unit_key": source["project_unit_key"],
        "target_signal_id": source["signal_id"],
        "resolution": "resolved_exact",
        "producer": "python_ast",
        "metadata_json": json.dumps(
            metadata, separators=(",", ":"), sort_keys=True
        ),
    }
    assert all(
        row["relation_id"] != forged["relation_id"]
        for row in projection["module_relations"]
    )
    projection["module_relations"].append(forged)
    projection["module_relations"].sort(key=lambda row: row["relation_id"])
    projection["module_relation_count"] = len(projection["module_relations"])
    rendered = [
        [
            row["relation_id"],
            row["source_signal_id"],
            row["target_signal_id"],
            row["resolution"],
            row["target_qualified_name"],
            row["metadata_json"],
        ]
        for row in projection["module_relations"]
    ]
    projection["module_projection_sha256"] = acceptance.hashlib.sha256(
        acceptance._v1_harness()._canonical(rendered).encode("utf-8")
    ).hexdigest()

    with pytest.raises(
        ValueError, match="not reconstructed from frozen imports"
    ):
        acceptance._validate_hash_capture(
            capture,
            manifest_path=MANIFEST,
            manifest=manifest,
            inputs=inputs,
            variant="oracle",
            repeat=1,
            input_order="canonical",
        )


def test_task0d_module_binding_rejects_257th_real_import(
    tmp_path: Path,
) -> None:
    assert acceptance.FROZEN_MAX_PYTHON_IMPORTS_PER_FILE == 256
    root = tmp_path / "boundary"
    root.mkdir()
    source_path = "source.py"
    (root / source_path).write_text(
        "\n".join(f"import target_{index:03d}" for index in range(257)),
        encoding="utf-8",
    )
    for index in range(257):
        (root / f"target_{index:03d}.py").write_text(
            f"TARGET_{index:03d} = {index}\n", encoding="utf-8"
        )
    inputs = {
        "source_specs": {"boundary": {"patterns": ("*.py",)}},
        "source_directories": {"boundary": root},
    }
    graph = __import__("context_search_tool.graph_contract", fromlist=["*"])

    def active_module(path: str) -> dict:
        lines = (root / path).read_text(encoding="utf-8").splitlines()
        end_line = min(80, len(lines))
        content = "\n".join(lines[:end_line])
        chunk_id = acceptance._deterministic_chunk_id(
            path, 1, end_line, content
        )
        signal_id = graph.generate_core_module_signal_id(
            file_path=path,
            start_line=1,
            start_column=0,
            end_line=end_line,
            end_column=0,
        )
        return {
            "signal": {
                "signal_id": signal_id,
                "chunk_id": chunk_id,
                "file_path": path,
                "kind": "module",
                "name": path,
                "qualified_name": path,
                "signature": "",
                "arity": None,
                "project_unit_key": "",
                "producer": "core_module",
                "start_line": 1,
                "start_column": 0,
                "end_line": end_line,
                "end_column": 0,
                "language": "python",
                "recallable": 0,
                "deleted_at": None,
            },
            "chunk": {
                "chunk_id": chunk_id,
                "file_path": path,
                "start_line": 1,
                "end_line": end_line,
                "content_sha256": acceptance.hashlib.sha256(
                    content.encode("utf-8")
                ).hexdigest(),
                "deleted_at": None,
            },
        }

    active_rows = [
        active_module(path)
        for path in [
            source_path,
            *(f"target_{index:03d}.py" for index in range(257)),
        ]
    ]
    active_rows.sort(key=lambda row: row["signal"]["signal_id"])
    active_by_path = {
        row["signal"]["file_path"]: row for row in active_rows
    }
    source = active_by_path[source_path]["signal"]

    def module_row(index: int) -> dict:
        specifier = f"target_{index:03d}"
        target_path = f"{specifier}.py"
        metadata = {
            "selector_state": "exact",
            "specifier": specifier,
            "candidates": [target_path],
            "import_form": "import",
            "relative_level": 0,
            "first_source_line": index + 1,
            "first_source_column": 0,
            "occurrence_count": 1,
        }
        return {
            "relation_id": graph.generate_v5_relation_id(
                source_signal_id=source["signal_id"],
                kind="imports",
                target_kind="module",
                target_qualified_name=target_path,
                target_signature="",
                target_arity=None,
                target_project_unit_key="",
                producer="python_ast",
            ),
            "source_signal_id": source["signal_id"],
            "source_chunk_id": source["chunk_id"],
            "source_file_path": source_path,
            "target_name": specifier,
            "kind": "imports",
            "target_kind": "module",
            "target_qualified_name": target_path,
            "target_signature": "",
            "target_arity": None,
            "target_project_unit_key": "",
            "target_signal_id": active_by_path[target_path]["signal"][
                "signal_id"
            ],
            "resolution": "resolved_exact",
            "producer": "python_ast",
            "metadata_json": json.dumps(
                metadata, separators=(",", ":"), sort_keys=True
            ),
        }

    module_rows = [module_row(index) for index in range(257)]
    module_rows.sort(key=lambda row: row["relation_id"])
    rendered = [
        [
            row["relation_id"],
            row["source_signal_id"],
            row["target_signal_id"],
            row["resolution"],
            row["target_qualified_name"],
            row["metadata_json"],
        ]
        for row in module_rows
    ]
    projection = {
        "active_python_signal_chunks": active_rows,
        "active_python_signal_chunk_count": len(active_rows),
        "active_python_signal_chunk_sha256": acceptance._json_value_sha256(
            active_rows
        ),
        "module_relations": module_rows,
        "module_relation_count": len(module_rows),
        "module_projection_sha256": acceptance.hashlib.sha256(
            acceptance._v1_harness()._canonical(rendered).encode("utf-8")
        ).hexdigest(),
    }
    active_signals = acceptance._validate_active_python_signal_chunks(
        projection, repository="boundary", inputs=inputs
    )

    with pytest.raises(
        ValueError, match="not reconstructed from frozen imports"
    ):
        acceptance._validate_module_relations(
            projection,
            repository="boundary",
            inputs=inputs,
            active_signals=active_signals,
        )


def test_task0d_causal_closure_rejects_consistently_forged_relation_id() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    capture = _synthetic_capture("oracle")
    projection = capture["index_projections"]["starlette"]
    causal = projection["causal_relations"][0]
    original = causal["relation"]["relation_id"]
    forged = "r5:" + "0" * 64
    causal["relation"]["relation_id"] = forged
    for rows in _exact_relation_groups(projection):
        for row in rows:
            if row["relation_id"] == original:
                row["relation_id"] = forged
    for case in capture["cases"].values():
        for selected in case["selected"]:
            witness = selected["exact_witness"]
            if witness and witness["relation_id"] == original:
                witness["relation_id"] = forged

    with pytest.raises(ValueError, match="causal relation identity"):
        acceptance._validate_hash_capture(
            capture,
            manifest_path=MANIFEST,
            manifest=manifest,
            inputs=inputs,
            variant="oracle",
            repeat=1,
            input_order="canonical",
        )


def test_task0d_causal_closure_rejects_rehashed_fake_target_location() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    capture = _synthetic_capture("oracle")
    projection = capture["index_projections"]["starlette"]
    causal = projection["causal_relations"][0]
    target = causal["target_signal"]
    old_target_id = causal["relation"]["target_signal_id"]
    active = next(
        row
        for row in projection["active_python_signal_chunks"]
        if row["signal"]["signal_id"] == old_target_id
    )
    target["start_line"] += 1
    graph = __import__("context_search_tool.graph_contract", fromlist=["*"])
    new_target_id = graph.generate_v5_signal_id(
        **{
            key: target[key]
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
    causal["relation"]["target_signal_id"] = new_target_id
    active["signal"]["signal_id"] = new_target_id
    active["signal"]["start_line"] = target["start_line"]
    for rows in _exact_relation_groups(projection):
        for row in rows:
            if row["target_signal_id"] == old_target_id:
                row["target_signal_id"] = new_target_id
    for case in capture["cases"].values():
        for selected in case["selected"]:
            witness = selected["exact_witness"]
            if witness and witness["target_signal_id"] == old_target_id:
                witness["target_signal_id"] = new_target_id
                witness["target_start_line"] = target["start_line"]
    projection["active_python_signal_chunk_sha256"] = (
        acceptance._json_value_sha256(
            projection["active_python_signal_chunks"]
        )
    )

    with pytest.raises(ValueError, match="active Python declaration identity"):
        acceptance._validate_hash_capture(
            capture,
            manifest_path=MANIFEST,
            manifest=manifest,
            inputs=inputs,
            variant="oracle",
            repeat=1,
            input_order="canonical",
        )


def test_task0d_rejects_forged_signature_with_recomputed_id_propagation() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    capture = _synthetic_capture("oracle")
    projection = capture["index_projections"]["starlette"]
    causal = projection["causal_relations"][0]
    target = causal["target_signal"]
    old_target_id = causal["relation"]["target_signal_id"]
    active = next(
        row
        for row in projection["active_python_signal_chunks"]
        if row["signal"]["signal_id"] == old_target_id
    )
    target["signature"] = "(forged: str) -> str"
    active["signal"]["signature"] = target["signature"]
    graph = __import__("context_search_tool.graph_contract", fromlist=["*"])
    new_target_id = graph.generate_v5_signal_id(
        **{
            key: target[key]
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
    active["signal"]["signal_id"] = new_target_id
    causal["relation"]["target_signal_id"] = new_target_id
    for rows in _exact_relation_groups(projection):
        for row in rows:
            if row["target_signal_id"] == old_target_id:
                row["target_signal_id"] = new_target_id
    for case in capture["cases"].values():
        for selected in case["selected"]:
            witness = selected["exact_witness"]
            if witness and witness["target_signal_id"] == old_target_id:
                witness["target_signal_id"] = new_target_id
    projection["active_python_signal_chunk_sha256"] = (
        acceptance._json_value_sha256(
            projection["active_python_signal_chunks"]
        )
    )

    with pytest.raises(
        ValueError, match="active Python (signal/chunk|declaration) identity"
    ):
        acceptance._validate_hash_capture(
            capture,
            manifest_path=MANIFEST,
            manifest=manifest,
            inputs=inputs,
            variant="oracle",
            repeat=1,
            input_order="canonical",
        )


def test_task0d_rejects_synchronously_propagated_forged_chunk_id() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    capture = _synthetic_capture("oracle")
    projection = capture["index_projections"]["starlette"]
    causal = projection["causal_relations"][0]
    target_id = causal["relation"]["target_signal_id"]
    active = next(
        row
        for row in projection["active_python_signal_chunks"]
        if row["signal"]["signal_id"] == target_id
    )
    old_chunk_id = active["chunk"]["chunk_id"]
    forged_chunk_id = "0" * 64
    active["signal"]["chunk_id"] = forged_chunk_id
    active["chunk"]["chunk_id"] = forged_chunk_id
    causal["target_signal"]["chunk_id"] = forged_chunk_id
    for rows in _exact_relation_groups(projection):
        for row in rows:
            if row["target_chunk_id"] == old_chunk_id:
                row["target_chunk_id"] = forged_chunk_id
    for case in capture["cases"].values():
        for selected in case["selected"]:
            witness = selected["exact_witness"]
            if witness and witness["target_chunk_id"] == old_chunk_id:
                witness["target_chunk_id"] = forged_chunk_id
                selected["chunk_id"] = forged_chunk_id
                selected["origin_chunk_ids"] = [
                    forged_chunk_id
                    if value == old_chunk_id
                    else value
                    for value in selected["origin_chunk_ids"]
                ]
    projection["active_python_signal_chunk_sha256"] = (
        acceptance._json_value_sha256(
            projection["active_python_signal_chunks"]
        )
    )

    with pytest.raises(ValueError, match="active Python chunk identity"):
        acceptance._validate_hash_capture(
            capture,
            manifest_path=MANIFEST,
            manifest=manifest,
            inputs=inputs,
            variant="oracle",
            repeat=1,
            input_order="canonical",
        )


def test_task0d_rejects_synchronously_recomputed_source_module_window() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    capture = _synthetic_capture("oracle")
    projection = capture["index_projections"]["starlette"]
    causal = projection["causal_relations"][0]
    relation = causal["relation"]
    source = causal["source_signal"]
    old_source_id = relation["source_signal_id"]
    old_relation_id = relation["relation_id"]
    metadata = json.loads(relation["metadata_json"])
    old_module_id = metadata["module_relation_id"]
    active = next(
        row
        for row in projection["active_python_signal_chunks"]
        if row["signal"]["signal_id"] == old_source_id
    )
    source["end_line"] += 1
    active["signal"]["end_line"] = source["end_line"]
    graph = __import__("context_search_tool.graph_contract", fromlist=["*"])
    new_source_id = graph.generate_v5_signal_id(
        **{
            key: source[key]
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
    active["signal"]["signal_id"] = new_source_id
    relation["source_signal_id"] = new_source_id
    new_relation_id = graph.generate_v5_relation_id(
        source_signal_id=new_source_id,
        kind=relation["kind"],
        target_kind=relation["target_kind"],
        target_qualified_name=relation["target_qualified_name"],
        target_signature=relation["target_signature"],
        target_arity=relation["target_arity"],
        target_project_unit_key=relation["target_project_unit_key"],
        producer=relation["producer"],
    )
    relation["relation_id"] = new_relation_id
    module = next(
        row
        for row in projection["module_relations"]
        if row["relation_id"] == old_module_id
    )
    new_module_id = graph.generate_v5_relation_id(
        source_signal_id=new_source_id,
        kind="imports",
        target_kind="module",
        target_qualified_name=module["target_qualified_name"],
        target_signature="",
        target_arity=None,
        target_project_unit_key=relation["target_project_unit_key"],
        producer="python_ast",
    )
    module["relation_id"] = new_module_id
    module["source_signal_id"] = new_source_id
    metadata["module_relation_id"] = new_module_id
    relation["metadata_json"] = json.dumps(
        metadata, separators=(",", ":"), sort_keys=True
    )
    for rows in _exact_relation_groups(projection):
        for row in rows:
            if row["relation_id"] == old_relation_id:
                row["relation_id"] = new_relation_id
                row["source_signal_id"] = new_source_id
                row["module_relation_id"] = new_module_id
    source_counts = {}
    for rows in _exact_relation_groups(projection):
        for row in rows:
            source_id = row["source_signal_id"]
            source_counts[source_id] = source_counts.get(source_id, 0) + 1
    projection["maximum_exact_relations_per_source"] = max(
        source_counts.values(), default=0
    )
    for case in capture["cases"].values():
        for selected in case["selected"]:
            witness = selected["exact_witness"]
            if witness and witness["relation_id"] == old_relation_id:
                witness["relation_id"] = new_relation_id
                witness["source_signal_id"] = new_source_id
                witness["module_relation_id"] = new_module_id
    projection["active_python_signal_chunks"].sort(
        key=lambda row: row["signal"]["signal_id"]
    )
    projection["active_python_signal_chunk_sha256"] = (
        acceptance._json_value_sha256(
            projection["active_python_signal_chunks"]
        )
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
        for row in projection["module_relations"]
    ]
    projection["module_projection_sha256"] = acceptance.hashlib.sha256(
        acceptance._v1_harness()._canonical(rendered).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ValueError, match="active Python module identity"):
        acceptance._validate_hash_capture(
            capture,
            manifest_path=MANIFEST,
            manifest=manifest,
            inputs=inputs,
            variant="oracle",
            repeat=1,
            input_order="canonical",
        )


def test_task0d_rejects_synchronously_recomputed_non_indexer_chunk_window() -> None:
    manifest = acceptance.validate_manifest(MANIFEST)
    inputs = acceptance._capture_inputs(manifest)
    capture = _synthetic_capture("oracle")
    projection = capture["index_projections"]["starlette"]
    causal = next(
        item
        for item in projection["causal_relations"]
        if next(
            row
            for row in projection["active_python_signal_chunks"]
            if row["signal"]["signal_id"]
            == item["relation"]["target_signal_id"]
        )["chunk"]["end_line"]
        == 80
    )
    target_id = causal["relation"]["target_signal_id"]
    active = next(
        row
        for row in projection["active_python_signal_chunks"]
        if row["signal"]["signal_id"] == target_id
    )
    old_chunk_id = active["chunk"]["chunk_id"]
    active["chunk"]["end_line"] = 81
    target_path = active["signal"]["file_path"]
    lines = (inputs["source_directories"]["starlette"] / target_path).read_text(
        encoding="utf-8"
    ).splitlines()
    forged_content = "\n".join(lines[:81])
    active["chunk"]["content_sha256"] = acceptance.hashlib.sha256(
        forged_content.encode("utf-8")
    ).hexdigest()
    new_chunk_id = acceptance._deterministic_chunk_id(
        target_path, 1, 81, forged_content
    )
    active["chunk"]["chunk_id"] = new_chunk_id
    active["signal"]["chunk_id"] = new_chunk_id
    causal["target_signal"]["chunk_id"] = new_chunk_id
    for rows in _exact_relation_groups(projection):
        for row in rows:
            if row["target_signal_id"] == target_id:
                row["target_chunk_id"] = new_chunk_id
    for case in capture["cases"].values():
        for selected in case["selected"]:
            witness = selected["exact_witness"]
            if witness and witness["target_signal_id"] == target_id:
                witness["target_chunk_id"] = new_chunk_id
                selected["chunk_id"] = new_chunk_id
                selected["origin_chunk_ids"] = [
                    new_chunk_id if value == old_chunk_id else value
                    for value in selected["origin_chunk_ids"]
                ]
    projection["active_python_signal_chunk_sha256"] = (
        acceptance._json_value_sha256(
            projection["active_python_signal_chunks"]
        )
    )

    with pytest.raises(ValueError, match="active Python chunk range"):
        acceptance._validate_hash_capture(
            capture,
            manifest_path=MANIFEST,
            manifest=manifest,
            inputs=inputs,
            variant="oracle",
            repeat=1,
            input_order="canonical",
        )


def _populate_capture_slots_fd(run_root_fd: int, staging_fd: int) -> None:
    for variant in ("baseline", "oracle"):
        for repeat in (1, 2):
            for order in ("canonical", "reverse"):
                acceptance._write_new_json_at(
                    run_root_fd,
                    staging_fd,
                    acceptance._capture_relative(
                        variant=variant, repeat=repeat, input_order=order
                    ),
                    {"slot": f"{variant}-{repeat}-{order}"},
                )


def test_task0d_reject_writes_terminal_and_inventory_allows_only_engine_outputs(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "reject-run"
    run_root.mkdir()
    run_root_fd = os.open(run_root, acceptance._directory_open_flags())
    staging = tmp_path / "reject-staging"
    staging.mkdir()
    staging_fd = os.open(staging, acceptance._directory_open_flags())
    report = {
        "disposition": "reject",
        "gates": {"efficacy": False, "integrity": True},
    }
    try:
        _populate_capture_slots_fd(run_root_fd, staging_fd)
        acceptance._write_hash_outcome_at(
            run_root_fd,
            staging_fd,
            report,
            manifest_path=MANIFEST,
            product_tree_sha256="a" * 64,
        )
        acceptance._assert_capture_inventory_fd(run_root_fd, state="terminal")

        terminal = acceptance._read_json_at(
            run_root_fd, acceptance.PurePosixPath("terminal-reject.json")
        )
        assert terminal["status"] == "reject"
        assert terminal["terminal"] is True
        assert terminal["failed_gates"] == ["efficacy"]
        assert not (run_root / "oracle/hash-proceed.json").exists()

        missing = acceptance._capture_relative(
            variant="baseline", repeat=1, input_order="canonical"
        )
        missing_path = run_root.joinpath(*missing.parts)
        missing_path.unlink()
        with pytest.raises(ValueError, match="not valid for terminal"):
            acceptance._assert_capture_inventory_fd(
                run_root_fd, state="terminal"
            )
        acceptance._write_new_json_at(
            run_root_fd,
            staging_fd,
            missing,
            {"slot": "baseline-1-canonical"},
        )

        extra = run_root / "unapproved.json"
        extra.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="unapproved file"):
            acceptance._assert_capture_inventory_fd(
                run_root_fd, state="terminal"
            )
    finally:
        os.close(staging_fd)
        os.close(run_root_fd)


def test_task0d_proceed_marker_is_a_legal_engine_output(tmp_path: Path) -> None:
    run_root = tmp_path / "proceed-run"
    run_root.mkdir()
    run_root_fd = os.open(run_root, acceptance._directory_open_flags())
    staging = tmp_path / "proceed-staging"
    staging.mkdir()
    staging_fd = os.open(staging, acceptance._directory_open_flags())
    try:
        _populate_capture_slots_fd(run_root_fd, staging_fd)
        acceptance._write_hash_outcome_at(
            run_root_fd,
            staging_fd,
            {"disposition": "proceed", "gates": {"all": True}},
            manifest_path=MANIFEST,
            product_tree_sha256="a" * 64,
        )
        acceptance._assert_capture_inventory_fd(run_root_fd, state="terminal")
    finally:
        os.close(staging_fd)
        os.close(run_root_fd)

    assert (run_root / "oracle/hash-proceed.json").is_file()
    assert not (run_root / "terminal-reject.json").exists()


def test_task0d_marker_interruption_recovers_without_overwriting_comparison(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = tmp_path / "retry-run"
    run_root.mkdir()
    run_root_fd = os.open(run_root, acceptance._directory_open_flags())
    staging = tmp_path / "retry-staging"
    staging.mkdir()
    staging_fd = os.open(staging, acceptance._directory_open_flags())
    report = {"disposition": "reject", "gates": {"integrity": False}}
    original_write = acceptance._write_new_json_at

    def interrupt_marker(run_fd, stage_fd, relative, payload):
        if relative.name == "terminal-reject.json":
            raise RuntimeError("simulated marker interruption")
        return original_write(run_fd, stage_fd, relative, payload)

    try:
        _populate_capture_slots_fd(run_root_fd, staging_fd)
        monkeypatch.setattr(acceptance, "_write_new_json_at", interrupt_marker)
        with pytest.raises(RuntimeError, match="marker interruption"):
            acceptance._write_hash_outcome_at(
                run_root_fd,
                staging_fd,
                report,
                manifest_path=MANIFEST,
                product_tree_sha256="a" * 64,
            )
        acceptance._assert_capture_inventory_fd(
            run_root_fd, state="compare_input"
        )
        comparison = acceptance._read_json_at(
            run_root_fd,
            acceptance.PurePosixPath(
                "oracle/hash", acceptance.CAPTURE_CORPORA, "comparison.json"
            ),
        )
        assert comparison == report

        monkeypatch.setattr(acceptance, "_write_new_json_at", original_write)
        acceptance._write_hash_outcome_at(
            run_root_fd,
            staging_fd,
            report,
            manifest_path=MANIFEST,
            product_tree_sha256="a" * 64,
        )
        acceptance._assert_capture_inventory_fd(run_root_fd, state="terminal")
    finally:
        os.close(staging_fd)
        os.close(run_root_fd)


def test_task0d_compare_has_no_write_bypass() -> None:
    assert "write" not in inspect.signature(
        acceptance.compare_hash_captures
    ).parameters


def test_task0d_compare_validation_failure_always_writes_terminal(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    (tmp_path / ".quality").mkdir()
    staging = tmp_path / "fixture-staging"
    staging.mkdir()
    run_root_fd = os.open(run_root, acceptance._directory_open_flags())
    staging_fd = os.open(staging, acceptance._directory_open_flags())
    try:
        for variant in ("baseline", "oracle"):
            for repeat in (1, 2):
                for order in ("canonical", "reverse"):
                    acceptance._write_new_json_at(
                        run_root_fd,
                        staging_fd,
                        acceptance._capture_relative(
                            variant=variant,
                            repeat=repeat,
                            input_order=order,
                        ),
                        {
                            "product_identity": {
                                "product_tree_sha256": "a" * 64
                            }
                        },
                    )
    finally:
        os.close(staging_fd)
        os.close(run_root_fd)

    manifest = {
        "capture_authorized": True,
        "evidence": {"run_root": "run"},
    }
    monkeypatch.setattr(acceptance, "ROOT", tmp_path)
    monkeypatch.setattr(
        acceptance, "validate_manifest", lambda *_args, **_kwargs: manifest
    )
    monkeypatch.setattr(acceptance, "_capture_inputs", lambda _manifest: {})
    monkeypatch.setattr(
        acceptance, "_privacy_check", lambda _value, *, inputs: None
    )
    monkeypatch.setattr(
        acceptance,
        "_validate_hash_capture",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("forged capture")
        ),
    )

    report = acceptance.compare_hash_captures(MANIFEST, run_root)

    assert report["disposition"] == "reject"
    assert report["gates"] == {"capture_integrity": False}
    assert "forged capture" in report["integrity_error"]
    terminal_fd = os.open(run_root, acceptance._directory_open_flags())
    try:
        acceptance._assert_capture_inventory_fd(terminal_fd, state="terminal")
        terminal = acceptance._read_json_at(
            terminal_fd, acceptance.PurePosixPath("terminal-reject.json")
        )
    finally:
        os.close(terminal_fd)
    assert terminal["status"] == "reject"


def test_task0d_pair_applies_efficacy_and_all_corpora_protection() -> None:
    report = acceptance._compare_hash_pair(
        _payload(), _synthetic_capture("baseline"), _synthetic_capture("oracle")
    )

    assert report["disposition"] == "proceed"
    assert len(report["new_required_items"]) == 3
    assert {item["repo"] for item in report["exact_rank_gains"]} == {
        "starlette",
        "requests",
    }
    assert set(report["gates"].values()) == {True}
    assert "performance_within_bounds" not in report["gates"]


def test_task0d_pair_rejects_protected_loss_without_changing_efficacy() -> None:
    baseline = _synthetic_capture("baseline")
    oracle = _synthetic_capture("oracle")
    protected_case = next(
        case_id
        for case_id, case in oracle["cases"].items()
        if case["repo"] == "redink"
    )
    oracle["cases"][protected_case]["selected"] = []
    oracle["cases"][protected_case]["required"][0].update(
        rank=None, state="not_selected"
    )

    report = acceptance._compare_hash_pair(_payload(), baseline, oracle)

    assert report["disposition"] == "reject"
    assert report["gates"]["all_corpora_zero_required_loss"] is False
    assert report["gates"]["all_corpora_protected_winners_stable"] is False


def test_task0d_stable_projection_masks_timing_implementation_and_sqlite_size() -> None:
    first = _synthetic_capture("oracle")
    second = deepcopy(first)
    second["timing"]["index_seconds"]["starlette"] = 99.0
    second["implementation"] = {"changed": True}
    second["repositories"]["starlette"]["index_sqlite_bytes"] = 999999

    assert acceptance._stable_hash_projection(first) == acceptance._stable_hash_projection(second)


def test_task0d_hash_capture_authorization_reaches_engine_without_writing(
    monkeypatch,
) -> None:
    called = False

    def permitted(*_args, **_kwargs):
        nonlocal called
        called = True
        raise RuntimeError("hash engine reached")

    run_root = acceptance.ROOT / _payload()["evidence"]["run_root"]
    assert not run_root.exists()
    monkeypatch.setattr(acceptance, "_build_hash_capture", permitted)
    with pytest.raises(RuntimeError, match="hash engine reached"):
        acceptance.capture_hash_to_disk(
            MANIFEST,
            run_root,
            variant="baseline",
            repeat=1,
            input_order="canonical",
        )
    assert called is True
    assert not run_root.exists()
