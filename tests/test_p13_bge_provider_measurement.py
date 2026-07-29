from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "p13_bge_provider_measurement.py"
PYTHON = Path(sys.executable)
ENVELOPE_SCHEMA = "p13-bge-provider-measurement-v1"
BASELINE_COMMIT = "122ed052284fa488943cb4464301a391bd2e7e24"
SYNTHETIC_CANDIDATE_COMMIT = "c" * 40
GOLD_SHA256 = (
    "459e6a56c0f7c3b033e34dafeba623b15e221d19ff59244d7fa29a47621f7767"
)
LEGACY_RUNNER_SHA256 = (
    "c768f3d5474ffe664654962fc22033af05bfaeeb4100b7afb0324b1d718a4809"
)
HASH_CONFIG_IDENTITY = (
    "5ab1cee713aff995519814538508a44cece92c285a746094e1cab8b86c7745be"
)
BGE_CONFIG_IDENTITY = (
    "c1cc02373a3d92d32afefaf6fcfb1cb8ba8e6cdbdd3f0298484965b94ca0896b"
)
BGE_DIGEST = (
    "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab"
)
BGE_DESCRIPTOR_IDENTITY = (
    "bge-ollama-v1:"
    "c1cc02373a3d92d32afefaf6fcfb1cb8ba8e6cdbdd3f0298484965b94ca0896b:"
    "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v1"
)
QUALITY_RUNNER = {
    "path": "src/context_search_tool/quality/runner.py",
    "sha256": (
        "47dc3cfd6b1daa2d65f86b54fc9d72596edf5b3d8915d4025f43af76f72ea724"
    ),
}
P1_QUALITY_INPUTS = {
    "fixture_catalog_gold": {
        "path": "tests/fixtures/retrieval_quality/queries.json",
        "blob_oid": "8bbe4d560fec1499aa1f436af929b8a6bb6f3eac",
        "sha256": (
            "ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5"
        ),
    },
    "acceptance_oracle": {
        "path": "tests/test_quality_p1.py",
        "blob_oid": "6dbbad2cb07b85f3f802b481655a4d8874cd9879",
        "sha256": (
            "a80d6e0183c76c05dc2284ab7b3f8791102bce9d26f454f4f94efa66d1bf0f67"
        ),
    },
    "committed_fixtures": {
        "tests/fixtures/java-spring-mini": {
            "file_count": 16,
            "tree_oid": "f005cb94bac1fd2e81705d0f9454803ea9ab7030",
            "tracked_listing_sha256": (
                "064c37bded5e5f6408d1e953a2a7be1dfd4854275b9eeb4365d575ddce2024e3"
            ),
        },
        "tests/fixtures/real_projects/cross_language_dashboard": {
            "file_count": 3,
            "tree_oid": "1001e3c929c9005d8c6d745e43fe4d8b93f32d3f",
            "tracked_listing_sha256": (
                "9c5165ea693159a779eae08d765351541c121f578fc6a38bf41e7b622996f7c7"
            ),
        },
        "tests/fixtures/real_projects/embedding_ab": {
            "file_count": 5,
            "tree_oid": "0f3d3d4419318bdd06633243015162fbb9eb6d6c",
            "tracked_listing_sha256": (
                "d973d364f36cd0ef6ba7fb86787cc8be77b7e1238e01adea07246a5602aad598"
            ),
        },
    },
}
P1_CASES = (
    ("java_spring_mini", "apply-audit-endpoint"),
    ("java_spring_mini", "audit-status-literal"),
    ("cross_language_dashboard", "dashboard-cross-language"),
    ("cross_language_dashboard", "dashboard-controller-path"),
    ("embedding_ab", "access-validation-cross-language"),
    ("embedding_ab", "blacklist-management-cross-language"),
    ("embedding_ab", "order-service-symbol"),
)
P1_CONFIG_HASHES = {
    "p1_vector_bge": (
        "sha256:b218204f3f064665e0aec7b4a9247c7949e8625e9e47f477a692e4fcb44cd6a4"
    ),
    "p1_hybrid_bge": (
        "sha256:47719ba626fb3c6bda4fc05c810d5d8db8eb975f1512c4a27dbed99adf3303c8"
    ),
}
ORIGIN_KEYS = {
    "context_search_tool",
    "context_search_tool.embeddings_bge",
    "p8_real_python_graphs_acceptance",
}
CAPTURE_ENVELOPE_KEYS = {
    "schema_version",
    "mode",
    "provider",
    "harness",
    "runner",
    "implementation",
    "module_origins",
    "transform_id",
    "attestation",
    "embedding_requests",
    "timing",
    "capture",
    "protected_inputs",
}
GATE_EVIDENCE_KEYS = {
    "raw_values",
    "numerator",
    "denominator",
    "ratio",
    "threshold",
    "passed",
    "input_capture_sha256",
    "evidence_path",
}
ENGINEERING_GATE_KEYS = {
    "baseline_index_stability_redink",
    "baseline_index_stability_daily",
    "baseline_query_p95_stability",
    "candidate_index_ratio_redink",
    "candidate_index_ratio_daily",
    "candidate_index_ratio_total",
    "candidate_query_p95_ratio",
    "requests_non_increasing_redink",
    "requests_non_increasing_daily",
    "requests_strictly_lower_total",
    "same_side_non_timing",
}
PRODUCT_GATE_KEYS = {
    "recall_non_decreasing",
    "zero_required_loss",
    "new_required",
    "noise_non_increasing",
    "p1_continuity",
    "query_p95_ratio",
    "per_repository_index_ratio",
    "same_provider_non_timing",
}
FROZEN_CANDIDATE_FILES = {
    "tests/fixtures/p8_python_graphs/input_manifest.json": (
        13539,
        "56071dfc281f9947b989de26ddd1d07ff4e35666d8314686d0ffbb16cd92a013",
    ),
    "tests/fixtures/p8_python_graphs/structural_expected.json": (
        58147,
        "37336cfaa701370cb7ad9855bdec15d2f2b512a2c11f1dc1463a7f564d2f561f",
    ),
    "tests/fixtures/retrieval_quality/p8_python_graphs.json": (
        13415,
        "34442cbae318a7874a1d789dddec78ca135be42b4bd5e9b11089d0cad78963da",
    ),
    "tests/fixtures/retrieval_quality/queries.json": (
        61830,
        "ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5",
    ),
    "tests/generate_p8_python_graph_manifest.py": (
        19862,
        "d9c34b60148d66125c6608b3c050608986aa4e682467eff33b06c7465691eb14",
    ),
    "tests/p8_python_graph_identity.py": (
        3581,
        "c17859916b59ba752184a3807d15c63bb2825d933f3a2aa70305b30f6fd475d8",
    ),
}
BASELINE_ORIGIN_SHA256 = {
    "context_search_tool": (
        "91447944015cec709e8aa7655f7e9d64e1e4508e7023a57fe3746911c0fc6fed"
    ),
    "context_search_tool.embeddings_bge": (
        "240ec2619232284c4971821e47f5011948b43a5d2971b371e40dbf2609df5202"
    ),
    "p8_real_python_graphs_acceptance": LEGACY_RUNNER_SHA256,
}


def _load_harness() -> Any:
    assert HARNESS.is_file(), "P13 measurement harness is absent"
    spec = importlib.util.spec_from_file_location(
        "p13_bge_provider_measurement_under_test",
        HARNESS,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, indent=1
    ) + "\n"


def _implementation(commit: str) -> dict[str, object]:
    return {
        "base_commit": commit,
        "tracked_diff_sha256": "0" * 64,
        "untracked_files": {},
        "dirty": False,
    }


def _attestation() -> dict[str, object]:
    return {
        "configured_model": "bge-m3",
        "canonical_model": "bge-m3:latest",
        "model_digest": BGE_DIGEST,
        "ollama_version": "0.30.10",
        "base_url": "http://localhost:11434",
        "dimensions": 1024,
        "input_transform_id": "bge-input-v1",
        "embedding_identity": BGE_DESCRIPTOR_IDENTITY,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), "rev-parse", "HEAD"),
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _discover_p13_evidence_layout() -> tuple[Path, Path, Path]:
    run_root = next(
        (
            ancestor.resolve()
            for ancestor in (ROOT, *ROOT.parents)
            if (ancestor / "protected-inputs.json").is_file()
        ),
        None,
    )
    if run_root is None:
        pointer = ROOT / ".quality" / "p13-run-root.txt"
        assert pointer.is_file()
        raw_run_root = pointer.read_text(encoding="utf-8").strip()
        assert raw_run_root
        configured_root = Path(raw_run_root)
        if not configured_root.is_absolute():
            configured_root = pointer.parent / configured_root
        run_root = configured_root.resolve(strict=True)

    protected_inputs = (run_root / "protected-inputs.json").resolve(
        strict=True
    )
    protected_inputs.relative_to(run_root)
    assert protected_inputs.is_file()

    roots = []
    for side, expected_head in (
        ("baseline", BASELINE_COMMIT),
        ("candidate", _git_head(ROOT)),
    ):
        implementation_root = (
            run_root / side / "context-search-tool"
        ).resolve(strict=True)
        implementation_root.relative_to(run_root)
        assert implementation_root.is_dir()
        assert _git_head(implementation_root) == expected_head
        roots.append(implementation_root)
    return run_root, roots[0], roots[1]


def _candidate_implementation_identity() -> dict[str, object]:
    def git(*arguments: str) -> str:
        completed = subprocess.run(
            ("git", "-C", str(ROOT), *arguments),
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout.strip()

    diff = git("diff", "--binary", "HEAD", "--", "src", "tests")
    untracked = {
        relative: _sha256(ROOT / relative)
        for relative in sorted(
            filter(
                None,
                git(
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    "--",
                    "src",
                    "tests",
                ).splitlines(),
            )
        )
    }
    return {
        "base_commit": git("rev-parse", "HEAD"),
        "tracked_diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
        "untracked_files": untracked,
        "dirty": bool(diff) or bool(untracked),
    }


def _bind_candidate_identity(payload: dict[str, object]) -> None:
    identity = _candidate_implementation_identity()
    payload["implementation"] = {
        "pre": copy.deepcopy(identity),
        "post": copy.deepcopy(identity),
    }
    payload["capture"]["implementation"] = copy.deepcopy(identity)


def _install_mocked_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return copy.deepcopy(self._payload)

    class Session:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.trust_env = True
            self.close_calls = 0
            self.closed = False

        def get(self, url: str, **kwargs: object) -> Response:
            if url.endswith("/api/version"):
                return Response({"version": "0.30.10"})
            assert url.endswith("/api/tags")
            return Response(
                {
                    "models": [
                        {
                            "name": "bge-m3:latest",
                            "model": "bge-m3:latest",
                            "digest": BGE_DIGEST,
                            "details": {"embedding_length": 1024},
                        }
                    ]
                }
            )

        def post(self, url: str, **kwargs: object) -> Response:
            assert url.endswith("/api/embed")
            return Response({"embeddings": [[1.0] + [0.0] * 1023]})

        def close(self) -> None:
            self.close_calls += 1
            self.closed = True

    import requests

    monkeypatch.setattr(requests, "Session", Session)


@pytest.mark.parametrize(
    ("helper_name", "outcome"),
    (
        pytest.param(
            "_runtime_attestation",
            "success",
            id="attestation-success",
        ),
        pytest.param(
            "_runtime_attestation",
            "request-error",
            id="attestation-request-error",
        ),
        pytest.param(
            "_warm_bge",
            "success",
            id="warmup-success",
        ),
        pytest.param(
            "_warm_bge",
            "request-error",
            id="warmup-request-error",
        ),
    ),
)
def test_live_http_helpers_close_each_allocated_session_once(
    monkeypatch: pytest.MonkeyPatch,
    helper_name: str,
    outcome: str,
) -> None:
    module = _load_harness()
    import requests

    observations: list[dict[str, object]] = []
    close_faults = (False,) if outcome == "success" else (False, True)
    for close_fails in close_faults:
        request_error = requests.RequestException(
            f"{helper_name}-request-sentinel-{close_fails}"
        )
        close_error = PermissionError(
            f"{helper_name}-close-sentinel-{close_fails}"
        )

        class Response:
            def __init__(self, payload: dict[str, object]) -> None:
                self._payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return copy.deepcopy(self._payload)

        class Session:
            def __init__(self) -> None:
                self.trust_env = True
                self.close_calls = 0
                self.request_calls: list[str] = []

            def __enter__(self) -> Session:
                return self

            def __exit__(
                self,
                exc_type: object,
                exc_value: object,
                traceback: object,
            ) -> bool:
                self.close()
                return False

            def get(self, url: str, **kwargs: object) -> Response:
                self.request_calls.append(url)
                if outcome == "request-error":
                    raise request_error
                if url.endswith("/api/version"):
                    return Response({"version": "0.30.10"})
                assert url.endswith("/api/tags")
                return Response(
                    {
                        "models": [
                            {
                                "name": "bge-m3:latest",
                                "model": "bge-m3:latest",
                                "digest": BGE_DIGEST,
                            }
                        ]
                    }
                )

            def post(self, url: str, **kwargs: object) -> Response:
                self.request_calls.append(url)
                if outcome == "request-error":
                    raise request_error
                assert url.endswith("/api/embed")
                return Response(
                    {"embeddings": [[1.0] + [0.0] * 1023]}
                )

            def close(self) -> None:
                self.close_calls += 1
                if close_fails:
                    raise close_error

        session = Session()
        monkeypatch.setattr(requests, "Session", lambda: session)
        result: object = None
        observed_error: Exception | None = None
        try:
            result = getattr(module, helper_name)()
        except Exception as error:
            observed_error = error
        observations.append(
            {
                "session": session,
                "result": result,
                "observed_error": observed_error,
                "request_error": request_error,
            }
        )

    for observation in observations:
        session = observation["session"]
        assert session.trust_env is False
        assert session.close_calls == 1
        assert session.request_calls
        if outcome == "request-error":
            assert (
                observation["observed_error"]
                is observation["request_error"]
            )
        else:
            assert observation["observed_error"] is None
            if helper_name == "_runtime_attestation":
                result = observation["result"]
                assert result["canonical_model"] == "bge-m3:latest"
                assert result["model_digest"] == BGE_DIGEST
            else:
                assert observation["result"] is None


def _install_mocked_capture_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    captures: list[dict[str, object]],
    *,
    calls: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    planned = copy.deepcopy(captures)
    real_subprocess_run = subprocess.run

    def run_process(
        argv: tuple[object, ...],
        *args: object,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        command = tuple(str(item) for item in argv)
        if len(command) >= 3 and command[:2] == (str(PYTHON), "-P"):
            assert "_capture-child" in command
            assert planned, "CLI started an unplanned capture child"
            output_index = command.index("--output") + 1
            output = Path(command[output_index])
            output.parent.mkdir(parents=True, exist_ok=True)
            payload = planned.pop(0)
            rendered = _canonical(payload)
            output.write_text(rendered, encoding="utf-8")
            if calls is not None:
                calls.append(
                    {
                        "argv": command,
                        "payload": copy.deepcopy(payload),
                    }
                )
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=rendered,
                stderr="",
            )
        return real_subprocess_run(argv, *args, **kwargs)

    _install_mocked_ollama(monkeypatch)
    monkeypatch.setattr(module.subprocess, "run", run_process)
    return planned


def _assert_persisted_capture_evidence(
    report: dict[str, object],
    evidence_root: Path,
) -> None:
    root = evidence_root.resolve()
    for gate in report["gates"].values():
        assert "input_capture_paths" in gate
        hashes = gate["input_capture_sha256"]
        paths = gate["input_capture_paths"]
        assert set(paths) == set(hashes)
        for label in hashes:
            assert len(paths[label]) == len(hashes[label])
            for relative, expected_sha256 in zip(
                paths[label],
                hashes[label],
            ):
                relative_path = Path(relative)
                assert not relative_path.is_absolute()
                assert ".." not in relative_path.parts
                capture_path = (root / relative_path).resolve()
                capture_path.relative_to(root)
                assert capture_path.is_file()
                assert _sha256(capture_path) == expected_sha256
                payload = json.loads(capture_path.read_text(encoding="utf-8"))
                assert capture_path.read_text(encoding="utf-8") == _canonical(
                    payload
                )


def _p1_planner(profile: str) -> dict[str, object]:
    hybrid = profile == "p1_hybrid_bge"
    return {
        "enabled": hybrid,
        "provider": "ollama",
        "model": "qwen3.5:4b-mlx",
        "base_url": "http://localhost:11434",
        "use_system_proxy": False,
        "timeout_seconds": 30 if hybrid else 8.0,
        "max_rewritten_queries": 4,
        "max_keywords": 12,
        "max_symbol_hints": 8,
    }


def _p1_catalog_queries() -> dict[tuple[str, str], str]:
    catalog_path = (
        ROOT / P1_QUALITY_INPUTS["fixture_catalog_gold"]["path"]
    )
    assert _sha256(catalog_path) == (
        P1_QUALITY_INPUTS["fixture_catalog_gold"]["sha256"]
    )
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    selected = []
    queries = {}
    required_profiles = {"p1_vector_bge", "p1_hybrid_bge"}
    for repository in catalog["repos"]:
        for case in repository["queries"]:
            if required_profiles <= set(case.get("profiles", ())):
                key = (repository["repo_key"], case["id"])
                selected.append(key)
                queries[key] = case["query"]
    assert tuple(selected) == P1_CASES
    assert all(isinstance(query, str) and query for query in queries.values())
    return queries


def _synthetic_p1_raw_report(
    profile: str,
    failed_cases: set[str],
    *,
    expected_candidate_commit: str,
) -> dict[str, object]:
    config_hash = P1_CONFIG_HASHES[profile]
    catalog_queries = _p1_catalog_queries()
    cases = []
    for repo_key, case_id in P1_CASES:
        failed = case_id in failed_cases
        cases.append(
            {
                "repo_key": repo_key,
                "case_id": case_id,
                "query": catalog_queries[(repo_key, case_id)],
                "tags": [],
                "gate": "required",
                "attempted": True,
                "known_gap_reason": None,
                "expanded_tokens": [],
                "planner": {
                    "status": (
                        "ok"
                        if profile == "p1_hybrid_bge"
                        else "disabled"
                    ),
                    "rewritten_queries": [],
                    "grep_keywords": [],
                    "symbol_hints": [],
                    "discarded_hints": [],
                    "provider": (
                        "ollama"
                        if profile == "p1_hybrid_bge"
                        else None
                    ),
                    "model": (
                        "qwen3.5:4b-mlx"
                        if profile == "p1_hybrid_bge"
                        else None
                    ),
                    "prompt_version": None,
                    "prompt_hash": None,
                    "latency_ms": 0,
                    "repo_profile_hash": None,
                    "repo_profile_truncated": False,
                },
                "query_variants": [],
                "variant_retrieval_status": (
                    "hybrid"
                    if profile == "p1_hybrid_bge"
                    else "original_only"
                ),
                "status": "fail" if failed else "pass",
                "metrics": {},
                "top_results": [],
                "failures": (
                    [f"required result missing for {case_id}"]
                    if failed
                    else []
                ),
            }
        )
    failed_count = len(failed_cases)
    return {
        "schema_version": 2,
        "generated_at": "2026-07-28T00:00:00+00:00",
        "command_args": {
            "fixture_path": (
                "tests/fixtures/retrieval_quality/queries.json"
            ),
            "profile": profile,
        },
        "tool": {
            "name": "context-search-tool",
            "git_commit": expected_candidate_commit,
        },
        "fixture": {
            "path": "tests/fixtures/retrieval_quality/queries.json",
            "sha256": (
                "sha256:"
                "ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5"
            ),
            "schema_version": 1,
            "fixture_case_count": 44,
            "run_case_count": 7,
        },
        "profile": profile,
        "config": {
            "config_hash": config_hash,
            "embedding": {
                "provider": "bge",
                "model": "bge-m3",
                "dimensions": 1024,
                "base_url": None,
                "api_key_env": None,
            },
        },
        "planner": _p1_planner(profile),
        "aggregate": {
            "total": 7,
            "selected": 7,
            "attempted": 7,
            "executed": 7,
            "passed": 7 - failed_count,
            "failed": failed_count,
            "skipped": 0,
            "known_gaps": 0,
            "informational": 0,
            "errors": 0,
            "metrics": {},
        },
        "repos": [{"repo_key": repo} for repo in dict(P1_CASES)],
        "cases": cases,
    }


def _write_p1_evidence(
    evidence_root: Path,
    captures: list[dict[str, object]],
    *,
    expected_candidate_commit: str,
    vector_failed: set[str] | None = None,
    hybrid_failed: set[str] | None = None,
) -> tuple[Path, dict[str, dict[str, object]]]:
    evidence_root.mkdir(parents=True, exist_ok=True)
    assert captures
    assert all(
        capture["implementation"]["pre"]["base_commit"]
        == expected_candidate_commit
        for capture in captures
    )
    failures = {
        "p1_vector_bge": (
            {"audit-status-literal"}
            if vector_failed is None
            else vector_failed
        ),
        "p1_hybrid_bge": (
            {"audit-status-literal"}
            if hybrid_failed is None
            else hybrid_failed
        ),
    }
    profiles = {}
    normalized = {}
    for profile in ("p1_vector_bge", "p1_hybrid_bge"):
        raw_report = _synthetic_p1_raw_report(
            profile,
            failures[profile],
            expected_candidate_commit=expected_candidate_commit,
        )
        relative = Path("p1-raw") / f"{profile}.json"
        raw_path = evidence_root / relative
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(_canonical(raw_report), encoding="utf-8")
        failed = failures[profile]
        profiles[profile] = {
            "profile": profile,
            "config_hash": P1_CONFIG_HASHES[profile],
            "provider": "bge",
            "embedding_identity": BGE_DESCRIPTOR_IDENTITY,
            "attestation": _attestation(),
            "cases": [
                {
                    "repo_key": repo_key,
                    "case_id": case_id,
                    "status": "fail" if case_id in failed else "pass",
                    "required_miss": case_id in failed,
                }
                for repo_key, case_id in P1_CASES
            ],
            "summary": {
                "passed": 7 - len(failed),
                "total": 7,
                "required_misses": sorted(failed),
            },
            "raw_report": {
                "path": relative.as_posix(),
                "sha256": _sha256(raw_path),
            },
        }
        normalized[profile] = {
            "passed": 7 - len(failed),
            "total": 7,
            "only_known_miss": (
                next(iter(failed)) if len(failed) == 1 else None
            ),
        }
    wrapper = {
        "schema_version": "p13-p1-continuity-v1",
        "implementation": copy.deepcopy(
            captures[0]["implementation"]["pre"]
        ),
        "quality_runner": copy.deepcopy(QUALITY_RUNNER),
        "quality_inputs": copy.deepcopy(P1_QUALITY_INPUTS),
        "profiles": profiles,
    }
    path = evidence_root / "p1-continuity.json"
    path.write_text(_canonical(wrapper), encoding="utf-8")
    return path, normalized


def _module_origins(*, legacy: bool) -> dict[str, dict[str, str]]:
    paths = {
        "context_search_tool": "src/context_search_tool/__init__.py",
        "context_search_tool.embeddings_bge": (
            "src/context_search_tool/embeddings_bge.py"
        ),
        "p8_real_python_graphs_acceptance": (
            "tests/p8_real_python_graphs_acceptance.py"
        ),
    }
    return {
        name: {
            "path": relative,
            "sha256": (
                BASELINE_ORIGIN_SHA256[name]
                if legacy
                else _sha256(ROOT / relative)
            ),
        }
        for name, relative in paths.items()
    }


def _protected_inputs() -> dict[str, dict[str, object]]:
    return {
        relative: {"bytes": size, "sha256": sha256}
        for relative, (size, sha256) in FROZEN_CANDIDATE_FILES.items()
    }


def _copy_contract_root(source_root: Path, target_root: Path) -> None:
    relative_paths = {
        *FROZEN_CANDIDATE_FILES,
        "src/context_search_tool/__init__.py",
        "src/context_search_tool/embeddings_bge.py",
        "tests/p8_real_python_graphs_acceptance.py",
        "tests/p13_bge_provider_measurement.py",
    }
    for relative in relative_paths:
        source = source_root / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _native_capture(provider: str) -> dict[str, object]:
    bge = provider == "bge"
    selected_paths = (
        ["required-a", "required-b", "required-c", "context-a", "noise-a"]
        if bge
        else [
            "required-a",
            "required-b",
            "context-a",
            "context-b",
            "noise-a",
        ]
    )
    contextual = ["context-a"] if bge else ["context-a", "context-b"]
    first_case = {
        "repo": "redink",
        "required": [
            {
                "path": path,
                "role": "implementation",
                "rank": (
                    index + 1
                    if path in selected_paths
                    else None
                ),
                "state": (
                    "selected"
                    if path in selected_paths
                    else "not_selected"
                ),
            }
            for index, path in enumerate(
                ("required-a", "required-b", "required-c")
            )
        ],
        "selected": [
            {
                "rank": index + 1,
                "path": path,
                "graph_origin": False,
                "relation_slot": False,
                "relation_witness": None,
            }
            for index, path in enumerate(selected_paths)
        ],
        "contextual": contextual,
        "unique_selected_paths": 5,
    }
    identity = {
        "provider": provider,
        "configured_model": "bge-m3" if bge else "hash-v1",
        "dimensions": 1024 if bge else 384,
        "static_config_identity": (
            BGE_CONFIG_IDENTITY if bge else HASH_CONFIG_IDENTITY
        ),
        "descriptor_identity": (
            BGE_DESCRIPTOR_IDENTITY if bge else HASH_CONFIG_IDENTITY
        ),
        "canonical_model": "bge-m3:latest" if bge else None,
        "model_digest": BGE_DIGEST if bge else None,
        "ollama_version": "0.30.10" if bge else None,
        "input_transform_id": "bge-input-v1" if bge else None,
        "pre_attestation": _attestation() if bge else None,
        "post_attestation": _attestation() if bge else None,
    }
    return {
        "schema_version": 4,
        "implementation": _implementation(SYNTHETIC_CANDIDATE_COMMIT),
        "environment": {
            "python_version": "3.13.12",
            "sqlite_version": "3.51.2",
            "numpy_version": "2.4.2",
        },
        "manifest_sha256": GOLD_SHA256,
        "embedding_identity": identity,
        "repositories": {
            "redink": {
                "selected_files": 28,
                "structure": {
                    "active_chunks": 40,
                    "signals_by_producer": {},
                    "relations_by_kind_resolution": {},
                },
                "index_sqlite_bytes": 4096,
            },
            "daily": {
                "selected_files": 203,
                "structure": {
                    "active_chunks": 300,
                    "signals_by_producer": {},
                    "relations_by_kind_resolution": {},
                },
                "index_sqlite_bytes": 8192,
            },
        },
        "cases": {
            **{"case-00": first_case},
            **{
                f"case-{index:02d}": {
                    "repo": "redink" if index < 6 else "daily",
                    "required": [],
                    "selected": [],
                    "contextual": [],
                    "unique_selected_paths": 0,
                }
                for index in range(1, 18)
            },
        },
        "witnesses": {
            "case-00:context_pack": {
                "mode": "context_pack",
                "case": "case-00",
                "covered_required": ["required-a"],
                "item_count": 5,
            },
            "case-01:exploration": {
                "mode": "exploration",
                "case": "case-01",
                "covered_required": [],
                "retrieval_calls": 2,
                "final_unique_paths": 4,
            },
        },
        "embedding_requests": {
            "redink": 4 if bge else 0,
            "daily": 9 if bge else 0,
            "total": 13 if bge else 0,
        },
        "timing": {
            "index_seconds": {"redink": 1.0, "daily": 2.0},
            "query_case_min_seconds": {
                f"case-{index:02d}": (index + 1) / 1000
                for index in range(18)
            },
            "query_p50_seconds": 0.009,
            "query_p95_seconds": 0.018,
        },
    }


def _legacy_capture() -> dict[str, object]:
    payload = copy.deepcopy(_native_capture("bge"))
    payload["schema_version"] = 3
    payload.pop("environment")
    payload.pop("embedding_requests")
    payload["embedding_identity"] = {
        "provider": "bge",
        "model": "bge-m3",
        "dimensions": 1024,
        "digest": BGE_DIGEST,
    }
    payload["timing"] = {"query_latency_mean_seconds": 0.01}
    return payload


def _capture_envelope(
    *,
    side: str,
    sequence: int,
    provider: str = "bge",
    legacy: bool = False,
    index_redink: float = 10.0,
    index_daily: float = 20.0,
    query_p95: float = 1.0,
    requests_redink: int = 10,
    requests_daily: int = 20,
) -> dict[str, object]:
    commit = (
        BASELINE_COMMIT if legacy else SYNTHETIC_CANDIDATE_COMMIT
    )
    implementation = _implementation(commit)
    attestation = _attestation() if provider == "bge" else None
    capture = _legacy_capture() if legacy else _native_capture(provider)
    query_case_min_seconds = {
        f"case-{index:02d}": query_p95 * (index + 1) / 18
        for index in range(18)
    }
    native_timing = {
        "index_seconds": {
            "redink": index_redink,
            "daily": index_daily,
        },
        "query_case_min_seconds": query_case_min_seconds,
        "query_p50_seconds": query_p95 * 0.5,
        "query_p95_seconds": query_p95,
    }
    requests = {
        "redink": requests_redink if provider == "bge" else 0,
        "daily": requests_daily if provider == "bge" else 0,
        "total": (
            requests_redink + requests_daily if provider == "bge" else 0
        ),
    }
    capture["implementation"] = copy.deepcopy(implementation)
    if not legacy:
        capture["embedding_requests"] = copy.deepcopy(requests)
        capture["timing"] = copy.deepcopy(native_timing)
    return {
        "schema_version": ENVELOPE_SCHEMA,
        "mode": "legacy-baseline" if legacy else "native",
        "provider": provider,
        "harness": {
            "path": "tests/p13_bge_provider_measurement.py",
            "sha256": _sha256(HARNESS),
        },
        "runner": {
            "path": "tests/p8_real_python_graphs_acceptance.py",
            "sha256": (
                LEGACY_RUNNER_SHA256
                if legacy
                else _sha256(ROOT / "tests/p8_real_python_graphs_acceptance.py")
            ),
        },
        "implementation": {
            "pre": copy.deepcopy(implementation),
            "post": copy.deepcopy(implementation),
        },
        "module_origins": _module_origins(legacy=legacy),
        "transform_id": (
            "p11-runner-head-4000"
            if legacy
            else ("bge-input-v1" if provider == "bge" else None)
        ),
        "attestation": {
            "pre": copy.deepcopy(attestation),
            "post": copy.deepcopy(attestation),
        },
        "embedding_requests": requests,
        "timing": native_timing,
        "capture": capture,
        "protected_inputs": _protected_inputs(),
        "_test_side": side,
        "_test_sequence": sequence,
    }


def _strip_test_fields(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result.pop("_test_side", None)
    result.pop("_test_sequence", None)
    return result


def _engineering_captures() -> list[dict[str, object]]:
    rows = [
        ("baseline", 1, True, 10.0, 20.0, 1.00, 10, 20),
        ("candidate", 1, False, 10.0, 20.0, 1.10, 10, 19),
        ("candidate", 2, False, 10.5, 21.0, 1.20, 10, 19),
        ("baseline", 2, True, 10.5, 21.0, 1.10, 10, 20),
        ("baseline", 3, True, 11.0, 22.0, 1.15, 10, 20),
        ("candidate", 3, False, 11.0, 22.0, 1.25, 10, 19),
    ]
    captures = []
    for side, sequence, legacy, redink, daily, query, req_r, req_d in rows:
        capture = _capture_envelope(
            side=side,
            sequence=sequence,
            legacy=legacy,
            index_redink=redink,
            index_daily=daily,
            query_p95=query,
            requests_redink=req_r,
            requests_daily=req_d,
        )
        captures.append(_strip_test_fields(capture))
    return captures


def _product_captures() -> list[dict[str, object]]:
    captures = [
        _capture_envelope(
            side="hash",
            sequence=1,
            provider="hash",
            index_redink=1.0,
            index_daily=2.0,
            query_p95=1.0,
            requests_redink=0,
            requests_daily=0,
        ),
        _capture_envelope(
            side="hash",
            sequence=2,
            provider="hash",
            index_redink=1.2,
            index_daily=2.2,
            query_p95=1.2,
            requests_redink=0,
            requests_daily=0,
        ),
        _capture_envelope(
            side="bge",
            sequence=1,
            provider="bge",
            index_redink=40.0,
            index_daily=80.0,
            query_p95=1.5,
            requests_redink=4,
            requests_daily=9,
        ),
        _capture_envelope(
            side="bge",
            sequence=2,
            provider="bge",
            index_redink=44.0,
            index_daily=88.0,
            query_p95=1.6,
            requests_redink=4,
            requests_daily=9,
        ),
    ]
    return [_strip_test_fields(capture) for capture in captures]


def _assert_gate_evidence(report: dict[str, object]) -> None:
    gates = report["gates"]
    assert isinstance(gates, dict) and gates
    for gate in gates.values():
        assert set(gate) == GATE_EVIDENCE_KEYS
        assert gate["input_capture_sha256"]
        assert gate["evidence_path"]


def _atomic_gate_report(
    captures: list[dict[str, object]],
    sides: list[str],
    evidence_name: str,
) -> dict[str, object]:
    grouped_sha256: dict[str, list[str]] = {}
    for capture, side in zip(captures, sides, strict=True):
        grouped_sha256.setdefault(side, []).append(
            hashlib.sha256(
                _canonical(capture).encode("utf-8")
            ).hexdigest()
        )
    return {
        "disposition": "pass",
        "gates": {
            "atomic": {
                "raw_values": {
                    "complete": True,
                    "label": "primary",
                },
                "numerator": 1,
                "denominator": 1,
                "ratio": 1.0,
                "threshold": 1.0,
                "passed": True,
                "input_capture_sha256": copy.deepcopy(grouped_sha256),
                "evidence_path": evidence_name,
            },
            "independent": {
                "raw_values": {
                    "complete": True,
                    "label": "secondary",
                    "samples": [2, 3],
                },
                "numerator": 3,
                "denominator": 2,
                "ratio": 1.5,
                "threshold": 2.0,
                "passed": True,
                "input_capture_sha256": copy.deepcopy(grouped_sha256),
                "evidence_path": evidence_name,
            },
        },
    }


def _public_comparison_case(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module: Any,
    output: Path,
) -> tuple[
    list[dict[str, object]],
    list[str],
    list[str],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    expected_candidate_commit = _git_head(ROOT)
    if command == "paired":
        captures = _engineering_captures()
        for capture in captures:
            if capture["mode"] == "native":
                _bind_candidate_identity(capture)
        sides = [
            (
                "baseline"
                if capture["mode"] == "legacy-baseline"
                else "candidate"
            )
            for capture in captures
        ]
        _, baseline_root, _ = _discover_p13_evidence_layout()
        argv = [
            "paired",
            "--baseline-root",
            str(baseline_root),
            "--candidate-root",
            str(ROOT),
            "--expected-candidate-commit",
            expected_candidate_commit,
            "--sources",
            str(tmp_path / "mocked-sources"),
            "--output",
            str(output),
        ]
    else:
        assert command == "product-paired"
        captures = _product_captures()
        for capture in captures:
            _bind_candidate_identity(capture)
        sides = [str(capture["provider"]) for capture in captures]
        p1_evidence, _profiles = _write_p1_evidence(
            output.parent / "p1-input",
            captures,
            expected_candidate_commit=expected_candidate_commit,
        )
        argv = [
            "product-paired",
            "--candidate-root",
            str(ROOT),
            "--expected-candidate-commit",
            expected_candidate_commit,
            "--sources",
            str(tmp_path / "mocked-sources"),
            "--output",
            str(output),
            "--p1-evidence",
            str(p1_evidence),
        ]
    child_calls: list[dict[str, object]] = []
    planned = _install_mocked_capture_boundaries(
        monkeypatch,
        module,
        captures,
        calls=child_calls,
    )
    return captures, sides, argv, planned, child_calls


def _guard_atomic_publication(
    monkeypatch: pytest.MonkeyPatch,
    final_path: Path,
    state: dict[str, bool],
) -> tuple[list[tuple[Path, Path]], list[str]]:
    real_replace = os.replace
    real_write_text = Path.write_text
    real_open = Path.open
    final = final_path.resolve()
    replace_calls: list[tuple[Path, Path]] = []
    forbidden_final_writes: list[str] = []

    def final_write_is_forbidden(path: Path) -> bool:
        return (
            path.resolve() == final
            and state["comparator_finished"]
            and not state["comparator_writing"]
        )

    def guarded_write_text(
        path: Path,
        data: str,
        *args: object,
        **kwargs: object,
    ) -> int:
        if final_write_is_forbidden(path):
            forbidden_final_writes.append("Path.write_text")
            raise AssertionError(
                "final comparison report must be published with os.replace"
            )
        return real_write_text(path, data, *args, **kwargs)

    def guarded_open(
        path: Path,
        mode: str = "r",
        *args: object,
        **kwargs: object,
    ) -> object:
        if (
            any(marker in mode for marker in ("w", "a", "x", "+"))
            and final_write_is_forbidden(path)
        ):
            forbidden_final_writes.append("Path.open")
            raise AssertionError(
                "final comparison report must be published with os.replace"
            )
        return real_open(path, mode, *args, **kwargs)

    def recording_replace(
        source: object,
        target: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        replace_calls.append(
            (Path(source).resolve(), Path(target).resolve())
        )
        real_replace(source, target, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(os, "replace", recording_replace)
    return replace_calls, forbidden_final_writes


def test_measurement_script_import_and_frozen_cli_are_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_harness()
    assert callable(module.main)

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    probe = subprocess.run(
        (
            str(PYTHON),
            "-P",
            "-c",
            (
                "import json,runpy,sys;"
                "before=set(sys.modules);"
                f"runpy.run_path({str(HARNESS)!r},run_name='p13_import_probe');"
                "print(json.dumps(sorted(name for name in set(sys.modules)-before"
                " if name.startswith('context_search_tool'))))"
            ),
        ),
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    assert json.loads(probe.stdout) == []

    for command, options in (
        (
            "paired",
            {
                "--baseline-root",
                "--candidate-root",
                "--expected-candidate-commit",
                "--sources",
                "--output",
            },
        ),
        (
            "product-paired",
            {
                "--candidate-root",
                "--expected-candidate-commit",
                "--sources",
                "--output",
                "--p1-evidence",
            },
        ),
    ):
        completed = subprocess.run(
            (str(PYTHON), "-P", str(HARNESS), command, "--help"),
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert options <= set(completed.stdout.split())

    run_root, baseline_root, _ = _discover_p13_evidence_layout()
    sources_root = Path(
        json.loads(
            (run_root / "protected-inputs.json").read_text(encoding="utf-8")
        )["p8_source_root"]
    )
    assert baseline_root.is_dir()
    assert sources_root.is_dir()
    expected_candidate_commit = _git_head(ROOT)
    monkeypatch.setenv(
        "P13_EXPECTED_CANDIDATE_COMMIT",
        "f" * 40,
    )

    paired_payloads = _engineering_captures()
    product_payloads = _product_captures()
    for capture in (*paired_payloads, *product_payloads):
        if capture["mode"] == "native":
            _bind_candidate_identity(capture)
    planned_payloads: list[dict[str, object]] = []
    process_calls: list[
        tuple[tuple[object, ...], dict[str, object], dict[str, object]]
    ] = []
    validation_calls: list[dict[str, object]] = []
    engineering_calls: list[list[dict[str, object]]] = []
    product_calls: list[
        tuple[list[dict[str, object]], dict[str, object]]
    ] = []
    p1_evidence, p1_profiles = _write_p1_evidence(
        tmp_path / "p1-evidence",
        product_payloads,
        expected_candidate_commit=expected_candidate_commit,
    )
    p1_loader_calls: list[
        tuple[Path, list[dict[str, object]]]
    ] = []
    paired_output = tmp_path / "engineering-gates.json"
    product_output = tmp_path / "product-comparison.json"
    real_subprocess_run = subprocess.run

    def comparison_report(
        captures: list[dict[str, object]],
        sides: list[str],
        output_path: Path,
    ) -> dict[str, object]:
        grouped_sha256: dict[str, list[str]] = {}
        for capture, side in zip(captures, sides, strict=True):
            grouped_sha256.setdefault(side, []).append(
                hashlib.sha256(
                    _canonical(capture).encode("utf-8")
                ).hexdigest()
            )
        report = {
            "disposition": "pass",
            "gates": {
                "wired": {
                    "raw_values": {"wired": True},
                    "numerator": 1,
                    "denominator": 1,
                    "ratio": 1.0,
                    "threshold": 1.0,
                    "passed": True,
                    "input_capture_sha256": grouped_sha256,
                    "evidence_path": output_path.name,
                }
            },
        }
        output_path.write_text(_canonical(report), encoding="utf-8")
        return report

    def run_process(
        argv: tuple[object, ...],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        if (
            len(argv) >= 2
            and str(argv[0]) == str(PYTHON)
            and argv[1] == "-P"
        ):
            assert planned_payloads, "CLI started an unplanned capture child"
            payload = planned_payloads.pop(0)
            process_calls.append((argv, kwargs, payload))
            rendered = _canonical(payload)
            for raw_path in argv:
                path = Path(str(raw_path))
                if (
                    path.suffix == ".json"
                    and path not in {paired_output, product_output}
                    and not path.exists()
                ):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(rendered, encoding="utf-8")
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=rendered,
                stderr="",
            )
        return real_subprocess_run(argv, **kwargs)

    def validate_capture(
        payload: dict[str, object],
        *args: object,
        **kwargs: object,
    ) -> None:
        validation_calls.append(payload)

    def compare_engineering(
        captures: list[dict[str, object]],
        output_path: Path,
    ) -> dict[str, object]:
        engineering_calls.append(captures)
        return comparison_report(
            captures,
            [
                (
                    "baseline"
                    if capture["mode"] == "legacy-baseline"
                    else "candidate"
                )
                for capture in captures
            ],
            output_path,
        )

    def compare_product(
        captures: list[dict[str, object]],
        p1_profiles: dict[str, object],
        output_path: Path,
    ) -> dict[str, object]:
        product_calls.append((captures, p1_profiles))
        return comparison_report(
            captures,
            [str(capture["provider"]) for capture in captures],
            output_path,
        )

    def load_p1_evidence(
        path: Path,
        captures: list[dict[str, object]],
    ) -> dict[str, object]:
        p1_loader_calls.append((path, captures))
        return copy.deepcopy(p1_profiles)

    class Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return copy.deepcopy(self._payload)

    class Session:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.trust_env = True
            self.close_calls = 0
            self.closed = False

        def get(self, url: str, **kwargs: object) -> Response:
            if url.endswith("/api/version"):
                return Response({"version": "0.30.10"})
            assert url.endswith("/api/tags")
            return Response(
                {
                    "models": [
                        {
                            "name": "bge-m3:latest",
                            "model": "bge-m3:latest",
                            "digest": BGE_DIGEST,
                            "details": {"embedding_length": 1024},
                        }
                    ]
                }
            )

        def post(self, url: str, **kwargs: object) -> Response:
            assert url.endswith("/api/embed")
            return Response({"embeddings": [[1.0] + [0.0] * 1023]})

        def close(self) -> None:
            self.close_calls += 1
            self.closed = True

    import requests

    monkeypatch.setattr(requests, "Session", Session)
    monkeypatch.setattr(module.subprocess, "run", run_process)
    monkeypatch.setattr(module, "validate_capture_envelope", validate_capture)
    monkeypatch.setattr(module, "compare_engineering", compare_engineering)
    monkeypatch.setattr(module, "compare_product", compare_product)
    monkeypatch.setattr(
        module,
        "load_p1_evidence",
        load_p1_evidence,
        raising=False,
    )

    planned_payloads.extend(copy.deepcopy(paired_payloads))
    assert (
        module.main(
            [
                "paired",
                "--baseline-root",
                str(baseline_root),
                "--candidate-root",
                str(ROOT),
                "--expected-candidate-commit",
                expected_candidate_commit,
                "--sources",
                str(sources_root),
                "--output",
                str(paired_output),
            ]
        )
        == 0
    )
    assert planned_payloads == []

    planned_payloads.extend(copy.deepcopy(product_payloads))
    assert (
        module.main(
            [
                "product-paired",
                "--candidate-root",
                str(ROOT),
                "--expected-candidate-commit",
                expected_candidate_commit,
                "--sources",
                str(sources_root),
                "--output",
                str(product_output),
                "--p1-evidence",
                str(p1_evidence),
            ]
        )
        == 0
    )
    assert planned_payloads == []

    assert len(process_calls) == 10
    expected_roots = [
        baseline_root,
        ROOT,
        ROOT,
        baseline_root,
        baseline_root,
        ROOT,
        ROOT,
        ROOT,
        ROOT,
        ROOT,
    ]
    for (argv, kwargs, payload), target_root in zip(
        process_calls,
        expected_roots,
    ):
        assert argv[0] == str(PYTHON)
        assert argv[1] == "-P"
        mode = argv[argv.index("--mode") + 1]
        if mode == "native":
            expected_index = argv.index("--expected-candidate-commit") + 1
            assert argv[expected_index] == expected_candidate_commit
        else:
            assert "--expected-candidate-commit" not in argv
        assert kwargs["env"]["PYTHONPATH"] == os.pathsep.join(
            (str(target_root / "src"), str(target_root / "tests"))
        )
        assert set(payload["module_origins"]) == ORIGIN_KEYS
        for origin in payload["module_origins"].values():
            relative = Path(origin["path"])
            assert not relative.is_absolute()
            assert origin["sha256"] == _sha256(target_root / relative)

    assert len(engineering_calls) == 1
    assert engineering_calls[0] == paired_payloads
    assert [row["mode"] for row in engineering_calls[0]] == [
        "legacy-baseline",
        "native",
        "native",
        "legacy-baseline",
        "legacy-baseline",
        "native",
    ]
    assert len(product_calls) == 1
    assert product_calls[0][0] == product_payloads
    assert [
        row["provider"] for row in product_calls[0][0]
    ] == ["hash", "hash", "bge", "bge"]
    assert product_calls[0][1] == p1_profiles
    assert p1_loader_calls == [(p1_evidence, product_payloads)]
    compared = [*engineering_calls[0], *product_calls[0][0]]
    assert all(row in validation_calls for row in compared)
    paired_report = json.loads(paired_output.read_text(encoding="utf-8"))
    product_report = json.loads(product_output.read_text(encoding="utf-8"))
    assert len(paired_report["input_captures"]) == 6
    assert len(product_report["input_captures"]) == 4
    for report in (paired_report, product_report):
        assert report["disposition"] == "pass"
        assert set(report["gates"]) == {"wired"}
        assert set(report["gates"]["wired"]) == (
            GATE_EVIDENCE_KEYS | {"input_capture_paths"}
        )
        _assert_persisted_capture_evidence(report, tmp_path)


@pytest.mark.parametrize("command", ("paired", "product-paired"))
def test_public_cli_requires_explicit_candidate_commit_before_any_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    module = _load_harness()
    expected_candidate_commit = _git_head(ROOT)
    attempted_actions: list[str] = []

    def forbidden_process(*args: object, **kwargs: object) -> object:
        attempted_actions.append("process")
        raise AssertionError(
            "missing candidate commit reached process boundary"
        )

    class ForbiddenSession:
        def __init__(self) -> None:
            attempted_actions.append("ollama")
            raise AssertionError(
                "missing candidate commit reached Ollama boundary"
            )

    import requests

    monkeypatch.setenv(
        "P13_EXPECTED_CANDIDATE_COMMIT",
        expected_candidate_commit,
    )
    monkeypatch.setattr(module.subprocess, "run", forbidden_process)
    monkeypatch.setattr(requests, "Session", ForbiddenSession)
    output = tmp_path / "must-not-exist.json"
    if command == "paired":
        argv = [
            command,
            "--baseline-root",
            str(tmp_path / "baseline"),
            "--candidate-root",
            str(ROOT),
            "--sources",
            str(tmp_path / "sources"),
            "--output",
            str(output),
        ]
    else:
        argv = [
            command,
            "--candidate-root",
            str(ROOT),
            "--sources",
            str(tmp_path / "sources"),
            "--output",
            str(output),
            "--p1-evidence",
            str(tmp_path / "p1-evidence.json"),
        ]

    with pytest.raises(SystemExit) as caught:
        module.main(argv)
    assert caught.value.code == 2
    assert "--expected-candidate-commit" in capsys.readouterr().err
    assert attempted_actions == []
    assert not output.exists()


def test_paired_cli_rejects_pair_override_before_any_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_harness()
    expected_candidate_commit = _git_head(ROOT)
    attempted_actions: list[str] = []

    def forbidden_capture(*args: object, **kwargs: object) -> object:
        attempted_actions.append("capture")
        raise AssertionError("pair override reached capture boundary")

    def forbidden_validator(*args: object, **kwargs: object) -> object:
        attempted_actions.append("validator")
        raise AssertionError("pair override reached validator boundary")

    def forbidden_comparator(*args: object, **kwargs: object) -> object:
        attempted_actions.append("comparator")
        raise AssertionError("pair override reached comparator boundary")

    class ForbiddenSession:
        def __init__(self) -> None:
            attempted_actions.append("ollama")
            raise AssertionError("pair override reached Ollama boundary")

    import requests

    monkeypatch.setattr(requests, "Session", ForbiddenSession)
    monkeypatch.setattr(module.subprocess, "run", forbidden_capture)
    monkeypatch.setattr(
        module,
        "validate_capture_envelope",
        forbidden_validator,
    )
    monkeypatch.setattr(module, "compare_engineering", forbidden_comparator)
    output = tmp_path / "must-not-exist.json"

    with pytest.raises(SystemExit) as caught:
        module.main(
            [
                "paired",
                "--baseline-root",
                str(tmp_path / "baseline"),
                "--candidate-root",
                str(ROOT),
                "--expected-candidate-commit",
                expected_candidate_commit,
                "--sources",
                str(tmp_path / "mocked-sources"),
                "--output",
                str(output),
                "--pairs",
                "1",
            ]
        )
    assert caught.value.code == 2
    assert attempted_actions == []
    assert not output.exists()
    with pytest.raises(SystemExit) as help_exit:
        module.main(["paired", "--help"])
    assert help_exit.value.code == 0
    assert "--pairs" not in capsys.readouterr().out


def test_product_cli_requires_p1_evidence_before_any_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_harness()
    expected_candidate_commit = _git_head(ROOT)
    attempted_actions: list[str] = []

    def forbidden_capture(*args: object, **kwargs: object) -> object:
        attempted_actions.append("capture")
        raise AssertionError("missing P1 evidence reached capture boundary")

    def forbidden_validator(*args: object, **kwargs: object) -> object:
        attempted_actions.append("validator")
        raise AssertionError("missing P1 evidence reached validator boundary")

    def forbidden_comparator(*args: object, **kwargs: object) -> object:
        attempted_actions.append("comparator")
        raise AssertionError("missing P1 evidence reached comparator boundary")

    class ForbiddenSession:
        def __init__(self) -> None:
            attempted_actions.append("ollama")
            raise AssertionError("missing P1 evidence reached Ollama boundary")

    import requests

    monkeypatch.setattr(requests, "Session", ForbiddenSession)
    monkeypatch.setattr(module.subprocess, "run", forbidden_capture)
    monkeypatch.setattr(
        module,
        "validate_capture_envelope",
        forbidden_validator,
    )
    monkeypatch.setattr(module, "compare_product", forbidden_comparator)
    output = tmp_path / "must-not-exist.json"

    with pytest.raises(SystemExit) as caught:
        module.main(
            [
                "product-paired",
                "--candidate-root",
                str(ROOT),
                "--expected-candidate-commit",
                expected_candidate_commit,
                "--sources",
                str(tmp_path / "mocked-sources"),
                "--output",
                str(output),
            ]
        )
    assert caught.value.code == 2
    assert attempted_actions == []
    assert not output.exists()


def test_paired_cli_persists_every_capture_used_by_each_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_harness()
    captures = _engineering_captures()
    for capture in captures:
        if capture["mode"] == "native":
            _bind_candidate_identity(capture)
    child_calls: list[dict[str, object]] = []
    planned = _install_mocked_capture_boundaries(
        monkeypatch,
        module,
        captures,
        calls=child_calls,
    )
    evidence_root = tmp_path / "engineering-evidence"
    output = evidence_root / "engineering-gates.json"
    _, baseline_root, _ = _discover_p13_evidence_layout()
    expected_sides = [
        "baseline",
        "candidate",
        "candidate",
        "baseline",
        "baseline",
        "candidate",
    ]
    expected_modes = [
        "legacy-baseline",
        "native",
        "native",
        "legacy-baseline",
        "legacy-baseline",
        "native",
    ]
    expected_roots = [
        baseline_root,
        ROOT,
        ROOT,
        baseline_root,
        baseline_root,
        ROOT,
    ]
    expected_sha256 = [
        hashlib.sha256(_canonical(capture).encode("utf-8")).hexdigest()
        for capture in captures
    ]
    assert len(set(expected_sha256)) == 6

    assert (
        module.main(
            [
                "paired",
                "--baseline-root",
                str(baseline_root),
                "--candidate-root",
                str(ROOT),
                "--expected-candidate-commit",
                _git_head(ROOT),
                "--sources",
                str(tmp_path / "mocked-sources"),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert planned == []
    assert len(child_calls) == 6
    for index, call in enumerate(child_calls):
        argv = call["argv"]
        assert Path(argv[argv.index("--implementation-root") + 1]) == (
            expected_roots[index]
        )
        assert argv[argv.index("--mode") + 1] == expected_modes[index]
        assert argv[argv.index("--provider") + 1] == "bge"
        assert call["payload"] == captures[index]

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["disposition"] == "pass"
    assert "input_captures" in report
    records = report["input_captures"]
    assert isinstance(records, list) and len(records) == 6
    assert all(
        set(record) == {"side", "provider", "sha256", "path"}
        for record in records
    )
    assert [record["side"] for record in records] == expected_sides
    assert [record["provider"] for record in records] == ["bge"] * 6
    assert [record["sha256"] for record in records] == expected_sha256

    persisted_paths: list[Path] = []
    for record, expected_capture, expected_hash in zip(
        records,
        captures,
        expected_sha256,
    ):
        relative = Path(record["path"])
        assert not relative.is_absolute()
        assert ".." not in relative.parts
        persisted = (evidence_root / relative).resolve()
        persisted.relative_to(evidence_root.resolve())
        assert persisted.is_file()
        assert _sha256(persisted) == expected_hash
        assert persisted.read_text(encoding="utf-8") == _canonical(
            expected_capture
        )
        persisted_paths.append(persisted)
    assert len(set(persisted_paths)) == 6
    assert (
        set(evidence_root.rglob("*.json")) - {output}
        == set(persisted_paths)
    )

    expected_grouped_sha256 = {
        "baseline": [
            expected_sha256[index] for index in (0, 3, 4)
        ],
        "candidate": [
            expected_sha256[index] for index in (1, 2, 5)
        ],
    }
    expected_grouped_paths = {
        "baseline": [records[index]["path"] for index in (0, 3, 4)],
        "candidate": [records[index]["path"] for index in (1, 2, 5)],
    }
    for gate in report["gates"].values():
        assert gate["input_capture_sha256"] == expected_grouped_sha256
        assert gate["input_capture_paths"] == expected_grouped_paths
    _assert_persisted_capture_evidence(report, evidence_root)


@pytest.mark.parametrize(
    "malformed_gates",
    (
        pytest.param([], id="gates-not-mapping"),
        pytest.param(
            {"wired": {"passed": True}},
            id="gate-missing-evidence",
        ),
    ),
)
def test_paired_cli_rejects_malformed_gate_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    malformed_gates: object,
) -> None:
    module = _load_harness()
    captures = _engineering_captures()
    for capture in captures:
        if capture["mode"] == "native":
            _bind_candidate_identity(capture)
    child_calls: list[dict[str, object]] = []
    planned = _install_mocked_capture_boundaries(
        monkeypatch,
        module,
        captures,
        calls=child_calls,
    )
    comparator_calls: list[list[dict[str, object]]] = []
    comparator_paths: list[Path] = []
    output = tmp_path / "must-not-exist.json"
    publication_state = {
        "comparator_writing": False,
        "comparator_finished": False,
    }
    replace_calls, forbidden_final_writes = _guard_atomic_publication(
        monkeypatch,
        output,
        publication_state,
    )

    def malformed_comparator(
        received: list[dict[str, object]],
        output_path: Path,
    ) -> dict[str, object]:
        comparator_calls.append(copy.deepcopy(received))
        comparator_paths.append(output_path.resolve())
        report = {
            "disposition": "pass",
            "gates": copy.deepcopy(malformed_gates),
        }
        rendered = _canonical(report)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        publication_state["comparator_writing"] = True
        try:
            output_path.write_text(rendered, encoding="utf-8")
            assert output_path.read_text(encoding="utf-8") == rendered
        finally:
            publication_state["comparator_writing"] = False
            publication_state["comparator_finished"] = True
        return report

    monkeypatch.setattr(
        module,
        "compare_engineering",
        malformed_comparator,
    )
    _, baseline_root, _ = _discover_p13_evidence_layout()

    with pytest.raises(ValueError, match="gate evidence"):
        module.main(
            [
                "paired",
                "--baseline-root",
                str(baseline_root),
                "--candidate-root",
                str(ROOT),
                "--expected-candidate-commit",
                _git_head(ROOT),
                "--sources",
                str(tmp_path / "mocked-sources"),
                "--output",
                str(output),
            ]
        )
    assert planned == []
    assert len(child_calls) == 6
    assert comparator_calls == [captures]
    assert len(comparator_paths) == 1
    assert replace_calls == []
    assert forbidden_final_writes == []
    assert not output.exists()
    assert comparator_paths[0] != output.resolve()
    assert comparator_paths[0].parent == output.resolve().parent
    assert not comparator_paths[0].exists()


@pytest.mark.parametrize(
    ("command", "fault"),
    (
        pytest.param("paired", "nan-numerator", id="paired-nan"),
        pytest.param("paired", "wrong-capture-sha", id="paired-sha"),
        pytest.param(
            "product-paired",
            "wrong-evidence-path",
            id="product-evidence-path",
        ),
    ),
)
def test_public_cli_rejects_written_malformed_report_without_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    fault: str,
) -> None:
    module = _load_harness()
    evidence_root = tmp_path / "published-evidence"
    output = evidence_root / "comparison.json"
    captures, sides, argv, planned, child_calls = (
        _public_comparison_case(
            command,
            tmp_path,
            monkeypatch,
            module,
            output,
        )
    )
    comparator_paths: list[Path] = []
    rendered_reports: list[str] = []
    publication_state = {
        "comparator_writing": False,
        "comparator_finished": False,
    }
    replace_calls, forbidden_final_writes = _guard_atomic_publication(
        monkeypatch,
        output,
        publication_state,
    )

    def write_malformed(
        received: list[dict[str, object]],
        output_path: Path,
    ) -> dict[str, object]:
        assert received == captures
        comparator_paths.append(output_path.resolve())
        report = _atomic_gate_report(
            received,
            sides,
            output_path.name,
        )
        gate = report["gates"]["atomic"]
        if fault == "nan-numerator":
            gate["numerator"] = float("nan")
        elif fault == "wrong-capture-sha":
            hashes = gate["input_capture_sha256"]
            first_side = next(iter(hashes))
            hashes[first_side][0] = "0" * 64
        else:
            assert fault == "wrong-evidence-path"
            gate["evidence_path"] = f"wrong-{output_path.name}"
        rendered = _canonical(report)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        publication_state["comparator_writing"] = True
        try:
            output_path.write_text(rendered, encoding="utf-8")
            assert output_path.read_text(encoding="utf-8") == rendered
        finally:
            publication_state["comparator_writing"] = False
            publication_state["comparator_finished"] = True
        rendered_reports.append(rendered)
        return report

    if command == "paired":
        monkeypatch.setattr(module, "compare_engineering", write_malformed)
    else:
        def compare_product(
            received: list[dict[str, object]],
            p1_profiles: dict[str, object],
            output_path: Path,
        ) -> dict[str, object]:
            assert p1_profiles
            return write_malformed(received, output_path)

        monkeypatch.setattr(module, "compare_product", compare_product)

    with pytest.raises(ValueError, match="gate evidence"):
        module.main(argv)

    assert planned == []
    assert len(child_calls) == len(captures)
    assert len(comparator_paths) == 1
    assert len(rendered_reports) == 1
    assert replace_calls == []
    assert forbidden_final_writes == []
    assert not output.exists(), (
        "malformed comparator output remained at the user final path; "
        f"comparator received {comparator_paths[0]}"
    )
    assert comparator_paths[0] != output.resolve()
    assert comparator_paths[0].parent == output.resolve().parent
    assert not comparator_paths[0].exists()


@pytest.mark.parametrize("command", ("paired", "product-paired"))
def test_public_cli_atomically_publishes_attached_comparator_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    module = _load_harness()
    evidence_root = tmp_path / "published-evidence"
    output = evidence_root / "comparison.json"
    captures, sides, argv, planned, child_calls = (
        _public_comparison_case(
            command,
            tmp_path,
            monkeypatch,
            module,
            output,
        )
    )
    comparator_paths: list[Path] = []
    staged_bytes: list[str] = []
    returned_reports: list[dict[str, object]] = []
    final_absent_after_write: list[bool] = []
    publication_state = {
        "comparator_writing": False,
        "comparator_finished": False,
    }
    replace_calls, forbidden_final_writes = _guard_atomic_publication(
        monkeypatch,
        output,
        publication_state,
    )

    def write_valid(
        received: list[dict[str, object]],
        output_path: Path,
    ) -> dict[str, object]:
        assert received == captures
        assert not output.exists()
        comparator_paths.append(output_path.resolve())
        report = _atomic_gate_report(
            received,
            sides,
            output_path.name,
        )
        rendered = _canonical(report)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        publication_state["comparator_writing"] = True
        try:
            output_path.write_text(rendered, encoding="utf-8")
            assert output_path.read_text(encoding="utf-8") == rendered
        finally:
            publication_state["comparator_writing"] = False
            publication_state["comparator_finished"] = True
        staged_bytes.append(rendered)
        returned_reports.append(report)
        final_absent_after_write.append(not output.exists())
        return report

    if command == "paired":
        monkeypatch.setattr(module, "compare_engineering", write_valid)
    else:
        def compare_product(
            received: list[dict[str, object]],
            p1_profiles: dict[str, object],
            output_path: Path,
        ) -> dict[str, object]:
            assert p1_profiles
            return write_valid(received, output_path)

        monkeypatch.setattr(module, "compare_product", compare_product)

    assert module.main(argv) == 0
    assert planned == []
    assert len(child_calls) == len(captures)
    assert output.is_file()
    assert len(returned_reports) == 1
    published = json.loads(output.read_text(encoding="utf-8"))
    staged = json.loads(staged_bytes[0])
    assert comparator_paths[0].name != output.name
    expected_gate_fields = {
        "atomic": {
            "raw_values": {
                "complete": True,
                "label": "primary",
            },
            "numerator": 1,
            "denominator": 1,
            "ratio": 1.0,
            "threshold": 1.0,
            "passed": True,
        },
        "independent": {
            "raw_values": {
                "complete": True,
                "label": "secondary",
                "samples": [2, 3],
            },
            "numerator": 3,
            "denominator": 2,
            "ratio": 1.5,
            "threshold": 2.0,
            "passed": True,
        },
    }
    assert set(staged["gates"]) == set(expected_gate_fields)
    assert set(published["gates"]) == set(expected_gate_fields)
    for name, expected_fields in expected_gate_fields.items():
        gate = staged["gates"][name]
        for field, expected in expected_fields.items():
            assert gate[field] == expected
        assert gate["evidence_path"] == comparator_paths[0].name
        final_gate = published["gates"][name]
        for field, expected in expected_fields.items():
            assert final_gate[field] == expected
        assert final_gate["evidence_path"] == output.name
        assert final_gate["evidence_path"] != gate["evidence_path"]
        assert final_gate["input_capture_sha256"] == (
            gate["input_capture_sha256"]
        )
    assert published == returned_reports[0]
    assert output.read_text(encoding="utf-8") == _canonical(
        returned_reports[0]
    )
    assert output.read_text(encoding="utf-8") != staged_bytes[0]
    _assert_persisted_capture_evidence(published, evidence_root)
    assert forbidden_final_writes == []
    assert final_absent_after_write == [True]
    assert comparator_paths[0] != output.resolve()
    assert replace_calls == [
        (comparator_paths[0], output.resolve())
    ]
    source, target = replace_calls[0]
    assert source.parent == target.parent
    assert not comparator_paths[0].exists()


def test_public_cli_preserves_primary_failure_when_staging_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_unlink = Path.unlink
    observations: list[dict[str, object]] = []
    for command in ("paired", "product-paired"):
        module = _load_harness()
        case_root = tmp_path / command
        output = case_root / "published-evidence" / "comparison.json"
        captures, _sides, argv, planned, child_calls = (
            _public_comparison_case(
                command,
                case_root,
                monkeypatch,
                module,
                output,
            )
        )
        primary_error = RuntimeError(f"{command}-primary-sentinel")
        cleanup_error = PermissionError(f"{command}-cleanup-sentinel")
        staging_paths: list[Path] = []
        cleanup_calls: list[Path] = []

        def fail_comparison(*arguments: object) -> dict[str, object]:
            assert arguments[0] == captures
            staging_path = Path(arguments[-1]).resolve()
            staging_paths.append(staging_path)
            assert staging_path.is_file()
            raise primary_error

        if command == "paired":
            monkeypatch.setattr(
                module,
                "compare_engineering",
                fail_comparison,
            )
        else:
            monkeypatch.setattr(module, "compare_product", fail_comparison)

        def fail_staging_cleanup(
            path: Path,
            *args: object,
            **kwargs: object,
        ) -> None:
            resolved = path.resolve()
            if resolved in staging_paths:
                cleanup_calls.append(resolved)
                raise cleanup_error
            real_unlink(path, *args, **kwargs)

        observed_error: Exception | None = None
        with monkeypatch.context() as cleanup_patch:
            cleanup_patch.setattr(Path, "unlink", fail_staging_cleanup)
            try:
                module.main(argv)
            except Exception as error:
                observed_error = error
        for staging_path in staging_paths:
            real_unlink(staging_path, missing_ok=True)

        assert planned == []
        assert len(child_calls) == len(captures)
        assert len(staging_paths) == 1
        assert cleanup_calls == staging_paths
        assert not output.exists()
        assert not staging_paths[0].exists()
        assert list(
            output.parent.glob(f".{output.name}.*.tmp")
        ) == []
        observations.append(
            {
                "observed_error": observed_error,
                "primary_error": primary_error,
            }
        )

    assert all(
        observation["observed_error"] is observation["primary_error"]
        for observation in observations
    )


@pytest.mark.parametrize(
    ("vector_failed", "expected_pass"),
    (
        (("audit-status-literal",), True),
        (("audit-status-literal", "apply-audit-endpoint"), False),
        (("apply-audit-endpoint",), False),
    ),
    ids=("historical-6-of-7", "live-regression", "wrong-known-miss"),
)
def test_product_cli_binds_p1_gate_to_supplied_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    vector_failed: tuple[str, ...],
    expected_pass: bool,
) -> None:
    module = _load_harness()
    expected_candidate_commit = _git_head(ROOT)
    captures = _product_captures()
    for capture in captures:
        _bind_candidate_identity(capture)
    planned = _install_mocked_capture_boundaries(
        monkeypatch,
        module,
        captures,
    )
    evidence_root = tmp_path / "product-evidence"
    evidence_root.mkdir()
    output = evidence_root / "product-comparison.json"
    p1_evidence, profiles = _write_p1_evidence(
        evidence_root,
        captures,
        expected_candidate_commit=expected_candidate_commit,
        vector_failed=set(vector_failed),
    )
    p1_sha256 = _sha256(p1_evidence)
    vector_passed = 7 - len(vector_failed)

    assert (
        module.main(
            [
                "product-paired",
                "--candidate-root",
                str(ROOT),
                "--expected-candidate-commit",
                expected_candidate_commit,
                "--sources",
                str(tmp_path / "mocked-sources"),
                "--output",
                str(output),
                "--p1-evidence",
                str(p1_evidence),
            ]
        )
        == 0
    )
    assert planned == []
    assert p1_evidence.is_file()
    assert _sha256(p1_evidence) == p1_sha256
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["p1_profiles"] == profiles
    gate = report["gates"]["p1_continuity"]
    assert gate["passed"] is expected_pass
    assert gate["raw_values"]["actual_passed"] == {
        "p1_vector_bge": vector_passed,
        "p1_hybrid_bge": 6,
    }
    assert gate["raw_values"]["p1_evidence"] == {
        "path": p1_evidence.name,
        "sha256": p1_sha256,
    }
    failed = {
        name
        for name, current in report["gates"].items()
        if current["passed"] is False
    }
    assert failed == (set() if expected_pass else {"p1_continuity"})
    assert report["disposition"] == ("pass" if expected_pass else "fail")
    _assert_persisted_capture_evidence(report, evidence_root)


def test_p1_loader_rejects_plain_summary(tmp_path: Path) -> None:
    module = _load_harness()
    captures = _product_captures()
    summary = {
        profile: {
            "passed": 6,
            "total": 7,
            "only_known_miss": "audit-status-literal",
        }
        for profile in ("p1_vector_bge", "p1_hybrid_bge")
    }
    evidence = tmp_path / "plain-summary.json"
    evidence.write_text(_canonical(summary), encoding="utf-8")

    with pytest.raises(ValueError):
        module.load_p1_evidence(evidence, captures)


def test_p1_loader_reads_raw_reports_and_recomputes_profiles(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    expected_candidate_commit = SYNTHETIC_CANDIDATE_COMMIT
    captures = _product_captures()
    evidence, expected = _write_p1_evidence(
        tmp_path,
        captures,
        expected_candidate_commit=expected_candidate_commit,
    )
    wrapper = json.loads(evidence.read_text(encoding="utf-8"))
    assert set(wrapper) == {
        "schema_version",
        "implementation",
        "quality_runner",
        "quality_inputs",
        "profiles",
    }
    assert set(wrapper["profiles"]) == {
        "p1_vector_bge",
        "p1_hybrid_bge",
    }
    catalog_queries = _p1_catalog_queries()
    for profile in wrapper["profiles"].values():
        assert set(profile) == {
            "profile",
            "config_hash",
            "provider",
            "embedding_identity",
            "attestation",
            "cases",
            "summary",
            "raw_report",
        }
        assert [case["case_id"] for case in profile["cases"]] == [
            case_id for _, case_id in P1_CASES
        ]
        raw_path = evidence.parent / profile["raw_report"]["path"]
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        assert raw["tool"]["git_commit"] == expected_candidate_commit
        assert [
            (case["repo_key"], case["case_id"], case["query"])
            for case in raw["cases"]
        ] == [
            (repo_key, case_id, catalog_queries[(repo_key, case_id)])
            for repo_key, case_id in P1_CASES
        ]

    profiles = module.load_p1_evidence(evidence, captures)
    expected_profiles = {
        profile: {
            "passed": 6,
            "total": 7,
            "only_known_miss": "audit-status-literal",
        }
        for profile in ("p1_vector_bge", "p1_hybrid_bge")
    }
    assert expected == expected_profiles
    assert profiles == expected_profiles
    report = module.compare_product(
        captures,
        profiles,
        tmp_path / "product-comparison.json",
    )
    assert report["disposition"] == "pass"


def test_p1_loader_rejects_catalog_query_mismatch(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    expected_candidate_commit = SYNTHETIC_CANDIDATE_COMMIT
    captures = _product_captures()
    evidence, _ = _write_p1_evidence(
        tmp_path,
        captures,
        expected_candidate_commit=expected_candidate_commit,
    )
    wrapper = json.loads(evidence.read_text(encoding="utf-8"))
    original_wrapper = copy.deepcopy(wrapper)
    forged_query = "P13 forged non-catalog query"
    assert forged_query not in set(_p1_catalog_queries().values())

    for profile in ("p1_vector_bge", "p1_hybrid_bge"):
        record = wrapper["profiles"][profile]["raw_report"]
        raw_path = evidence.parent / record["path"]
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        assert raw["cases"][0]["query"] == (
            _p1_catalog_queries()[P1_CASES[0]]
        )
        raw["cases"][0]["query"] = forged_query
        raw_path.write_text(_canonical(raw), encoding="utf-8")
        record["sha256"] = _sha256(raw_path)

    for profile in ("p1_vector_bge", "p1_hybrid_bge"):
        before = copy.deepcopy(original_wrapper["profiles"][profile])
        after = copy.deepcopy(wrapper["profiles"][profile])
        before["raw_report"]["sha256"] = after["raw_report"]["sha256"]
        assert after == before
    assert {
        key: value
        for key, value in wrapper.items()
        if key != "profiles"
    } == {
        key: value
        for key, value in original_wrapper.items()
        if key != "profiles"
    }
    evidence.write_text(_canonical(wrapper), encoding="utf-8")

    with pytest.raises(ValueError, match="catalog query mismatch"):
        module.load_p1_evidence(evidence, captures)


def test_p1_loader_rejects_unbound_or_inconsistent_provenance(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    expected_candidate_commit = SYNTHETIC_CANDIDATE_COMMIT
    captures = _product_captures()

    for mutation in (
        "wrapper-extra",
        "candidate",
        "candidate-untracked",
        "runner",
        "runner-path",
        "fixture",
        "p1-tree",
        "profile-extra",
        "profile-config",
        "profile-provider",
        "descriptor",
        "attestation",
        "summary",
        "case-order",
        "raw-report-extra",
        "raw-path",
        "raw-sha",
        "raw-root-extra",
        "raw-tool",
        "raw-tool-commit",
        "raw-tool-extra",
        "raw-command-extra",
        "raw-profile",
        "raw-fixture",
        "raw-fixture-extra",
        "raw-config",
        "raw-config-extra",
        "raw-planner",
        "raw-planner-extra",
        "raw-aggregate",
        "raw-cases",
    ):
        evidence, _ = _write_p1_evidence(
            tmp_path / mutation,
            captures,
            expected_candidate_commit=expected_candidate_commit,
        )
        wrapper = json.loads(evidence.read_text(encoding="utf-8"))
        vector = wrapper["profiles"]["p1_vector_bge"]
        if mutation == "wrapper-extra":
            wrapper["unexpected"] = True
        elif mutation == "candidate":
            wrapper["implementation"]["tracked_diff_sha256"] = "f" * 64
        elif mutation == "candidate-untracked":
            wrapper["implementation"]["untracked_files"][
                "tests/forged.py"
            ] = "f" * 64
        elif mutation == "runner":
            wrapper["quality_runner"]["sha256"] = "f" * 64
        elif mutation == "runner-path":
            wrapper["quality_runner"]["path"] = "../runner.py"
        elif mutation == "fixture":
            wrapper["quality_inputs"]["fixture_catalog_gold"][
                "sha256"
            ] = "f" * 64
        elif mutation == "p1-tree":
            wrapper["quality_inputs"]["committed_fixtures"][
                "tests/fixtures/java-spring-mini"
            ]["tree_oid"] = "f" * 40
        elif mutation == "profile-extra":
            vector["unexpected"] = True
        elif mutation == "profile-config":
            vector["config_hash"] = "sha256:" + "f" * 64
        elif mutation == "profile-provider":
            vector["provider"] = "hash"
        elif mutation == "descriptor":
            vector["embedding_identity"] = "forged-descriptor"
        elif mutation == "attestation":
            vector["attestation"]["model_digest"] = "f" * 64
        elif mutation == "summary":
            vector["summary"]["passed"] = 7
        elif mutation == "case-order":
            vector["cases"].reverse()
            raw_path = evidence.parent / vector["raw_report"]["path"]
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["cases"].reverse()
            raw_path.write_text(_canonical(raw), encoding="utf-8")
            vector["raw_report"]["sha256"] = _sha256(raw_path)
        elif mutation == "raw-report-extra":
            vector["raw_report"]["unexpected"] = True
        elif mutation == "raw-path":
            raw_path = evidence.parent / vector["raw_report"]["path"]
            escaped = evidence.parent.parent / "escaped-raw-report.json"
            escaped.write_bytes(raw_path.read_bytes())
            vector["raw_report"] = {
                "path": "../escaped-raw-report.json",
                "sha256": _sha256(escaped),
            }
        elif mutation == "raw-sha":
            vector["raw_report"]["sha256"] = "f" * 64
        else:
            raw_path = evidence.parent / vector["raw_report"]["path"]
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            if mutation == "raw-root-extra":
                raw["unexpected"] = True
            elif mutation == "raw-tool":
                raw["tool"]["name"] = "forged-tool"
            elif mutation == "raw-tool-commit":
                raw["tool"]["git_commit"] = "f" * 40
            elif mutation == "raw-tool-extra":
                raw["tool"]["unexpected"] = True
            elif mutation == "raw-command-extra":
                raw["command_args"]["unexpected"] = True
            elif mutation == "raw-profile":
                raw["command_args"]["profile"] = "p1_hybrid_bge"
            elif mutation == "raw-fixture":
                raw["fixture"]["sha256"] = "sha256:" + "f" * 64
            elif mutation == "raw-fixture-extra":
                raw["fixture"]["unexpected"] = True
            elif mutation == "raw-config":
                raw["config"]["config_hash"] = "sha256:" + "f" * 64
            elif mutation == "raw-config-extra":
                raw["config"]["unexpected"] = True
            elif mutation == "raw-planner":
                raw["planner"]["enabled"] = True
            elif mutation == "raw-planner-extra":
                raw["planner"]["unexpected"] = True
            elif mutation == "raw-aggregate":
                raw["aggregate"]["passed"] = 7
                raw["aggregate"]["failed"] = 0
            else:
                raw["cases"][0]["status"] = "fail"
                raw["cases"][0]["failures"] = ["forged required miss"]
                raw["aggregate"]["passed"] = 5
                raw["aggregate"]["failed"] = 2
            raw_path.write_text(_canonical(raw), encoding="utf-8")
            vector["raw_report"]["sha256"] = _sha256(raw_path)
        evidence.write_text(_canonical(wrapper), encoding="utf-8")

        with pytest.raises(ValueError):
            module.load_p1_evidence(evidence, captures)


def test_capture_envelope_is_closed_and_v3_is_legacy_only() -> None:
    module = _load_harness()
    legacy = _strip_test_fields(
        _capture_envelope(side="baseline", sequence=1, legacy=True)
    )
    native = _strip_test_fields(
        _capture_envelope(side="candidate", sequence=1)
    )
    assert set(legacy) == CAPTURE_ENVELOPE_KEYS
    assert set(native) == CAPTURE_ENVELOPE_KEYS
    assert set(native["module_origins"]) == ORIGIN_KEYS
    module.validate_capture_envelope(legacy)
    module.validate_capture_envelope(native)

    native_v3 = copy.deepcopy(native)
    native_v3["capture"] = _legacy_capture()
    legacy_v4 = copy.deepcopy(legacy)
    legacy_v4["capture"] = _native_capture("bge")
    extra = copy.deepcopy(native)
    extra["controller_cwd"] = "/private/controller"
    for invalid in (native_v3, legacy_v4, extra):
        with pytest.raises(ValueError):
            module.validate_capture_envelope(invalid)


@pytest.mark.parametrize(
    "mutation",
    (
        "capture-extra",
        "identity-extra",
        "repository-extra",
        "missing-repositories",
        "missing-witnesses",
    ),
)
def test_native_v4_capture_requires_closed_runner_schema(
    mutation: str,
) -> None:
    module = _load_harness()
    valid = _strip_test_fields(
        _capture_envelope(side="candidate", sequence=1)
    )
    assert set(valid["capture"]) == {
        "schema_version",
        "implementation",
        "environment",
        "manifest_sha256",
        "embedding_identity",
        "repositories",
        "cases",
        "witnesses",
        "embedding_requests",
        "timing",
    }
    module.validate_capture_envelope(valid)
    invalid = copy.deepcopy(valid)
    capture = invalid["capture"]
    if mutation == "capture-extra":
        capture["unexpected"] = True
    elif mutation == "identity-extra":
        capture["embedding_identity"]["unexpected"] = True
    elif mutation == "repository-extra":
        capture["repositories"]["redink"]["unexpected"] = True
    elif mutation == "missing-repositories":
        capture.pop("repositories")
    else:
        capture.pop("witnesses")

    with pytest.raises(ValueError):
        module.validate_capture_envelope(invalid)


def test_native_v4_nested_records_are_closed() -> None:
    module = _load_harness()
    valid = _strip_test_fields(
        _capture_envelope(side="candidate", sequence=1)
    )
    module.validate_capture_envelope(valid)

    mutations = []
    for location in (
        "implementation",
        "environment",
        "structure",
        "case",
        "selected",
        "required",
        "witness",
    ):
        invalid = copy.deepcopy(valid)
        capture = invalid["capture"]
        if location == "implementation":
            capture["implementation"]["unexpected"] = True
        elif location == "environment":
            capture["environment"]["unexpected"] = True
        elif location == "structure":
            capture["repositories"]["redink"]["structure"][
                "unexpected"
            ] = True
        elif location == "case":
            capture["cases"]["case-00"]["unexpected"] = True
        elif location == "selected":
            capture["cases"]["case-00"]["selected"][0][
                "unexpected"
            ] = True
        elif location == "required":
            capture["cases"]["case-00"]["required"][0][
                "unexpected"
            ] = True
        else:
            capture["witnesses"]["case-00:context_pack"][
                "unexpected"
            ] = True
        mutations.append(invalid)

    for invalid in mutations:
        with pytest.raises(ValueError):
            module.validate_capture_envelope(invalid)


def test_envelope_rejects_origin_implementation_and_attestation_drift() -> None:
    module = _load_harness()
    payload = _strip_test_fields(
        _capture_envelope(side="candidate", sequence=1)
    )
    invalid_rows = []

    outside = copy.deepcopy(payload)
    outside["module_origins"]["context_search_tool"]["path"] = (
        "../other/context_search_tool/__init__.py"
    )
    invalid_rows.append(outside)
    bad_sha = copy.deepcopy(payload)
    bad_sha["runner"]["sha256"] = "not-a-sha"
    invalid_rows.append(bad_sha)
    implementation_drift = copy.deepcopy(payload)
    implementation_drift["implementation"]["post"]["tracked_diff_sha256"] = (
        "9" * 64
    )
    invalid_rows.append(implementation_drift)
    attestation_drift = copy.deepcopy(payload)
    attestation_drift["attestation"]["post"]["ollama_version"] = "0.30.11"
    invalid_rows.append(attestation_drift)
    marker = copy.deepcopy(payload)
    marker["transform_id"] = "p11-runner-head-4000"
    invalid_rows.append(marker)

    for invalid in invalid_rows:
        with pytest.raises(ValueError):
            module.validate_capture_envelope(invalid)


def test_legacy_requires_exact_clean_baseline_and_frozen_runner(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    payload = _strip_test_fields(
        _capture_envelope(side="baseline", sequence=1, legacy=True)
    )
    module.validate_capture_envelope(payload)

    baseline_root = tmp_path / "baseline-root"
    subprocess.run(
        (
            "git",
            "clone",
            "-q",
            "--no-checkout",
            str(ROOT),
            str(baseline_root),
        ),
        check=True,
    )
    subprocess.run(
        (
            "git",
            "-C",
            str(baseline_root),
            "checkout",
            "-q",
            "--detach",
            BASELINE_COMMIT,
        ),
        check=True,
    )
    module.validate_capture_envelope(
        payload,
        implementation_root=baseline_root,
    )

    subprocess.run(
        (
            "git",
            "-C",
            str(baseline_root),
            "switch",
            "-q",
            "-c",
            "p13-attached",
        ),
        check=True,
    )
    with pytest.raises(ValueError, match="clean detached baseline"):
        module.validate_capture_envelope(
            payload,
            implementation_root=baseline_root,
        )
    subprocess.run(
        (
            "git",
            "-C",
            str(baseline_root),
            "checkout",
            "-q",
            "--detach",
            BASELINE_COMMIT,
        ),
        check=True,
    )
    dirty_path = baseline_root / "tests" / "p8_python_graph_identity.py"
    dirty_path.write_bytes(dirty_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="clean detached baseline"):
        module.validate_capture_envelope(
            payload,
            implementation_root=baseline_root,
        )
    subprocess.run(
        (
            "git",
            "-C",
            str(baseline_root),
            "checkout",
            "-q",
            "--",
            "tests/p8_python_graph_identity.py",
        ),
        check=True,
    )
    subprocess.run(
        (
            "git",
            "-C",
            str(baseline_root),
            "-c",
            "user.name=P13 Test",
            "-c",
            "user.email=p13@example.invalid",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "wrong baseline identity",
        ),
        check=True,
    )
    assert _git_head(baseline_root) != BASELINE_COMMIT
    with pytest.raises(ValueError, match="clean detached baseline"):
        module.validate_capture_envelope(
            payload,
            implementation_root=baseline_root,
        )

    wrong_commit = copy.deepcopy(payload)
    wrong_commit["implementation"]["pre"]["base_commit"] = (
        SYNTHETIC_CANDIDATE_COMMIT
    )
    wrong_commit["implementation"]["post"]["base_commit"] = (
        SYNTHETIC_CANDIDATE_COMMIT
    )
    dirty = copy.deepcopy(payload)
    dirty["implementation"]["pre"]["dirty"] = True
    dirty["implementation"]["post"]["dirty"] = True
    wrong_runner = copy.deepcopy(payload)
    wrong_runner["runner"]["sha256"] = "f" * 64
    wrong_transform = copy.deepcopy(payload)
    wrong_transform["transform_id"] = "bge-input-v1"
    for invalid in (wrong_commit, dirty, wrong_runner, wrong_transform):
        with pytest.raises(ValueError):
            module.validate_capture_envelope(invalid)

    for relative, (expected_size, expected_sha256) in (
        FROZEN_CANDIDATE_FILES.items()
    ):
        frozen = ROOT / relative
        assert len(frozen.read_bytes()) == expected_size
        assert _sha256(frozen) == expected_sha256

    native = _strip_test_fields(
        _capture_envelope(side="candidate", sequence=1)
    )

    def commit_contract_tree(
        root: Path,
        message: str,
        *,
        initialize: bool = False,
    ) -> dict[str, object]:
        if initialize:
            subprocess.run(("git", "init", "-q", str(root)), check=True)
        subprocess.run(
            ("git", "-C", str(root), "add", "--", "src", "tests"),
            check=True,
        )
        subprocess.run(
            (
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=P13 Test",
                "-c",
                "user.email=p13@example.invalid",
                "commit",
                "-q",
                "-m",
                message,
            ),
            check=True,
        )
        return {
            "base_commit": _git_head(root),
            "tracked_diff_sha256": hashlib.sha256(b"").hexdigest(),
            "untracked_files": {},
            "dirty": False,
        }

    def bind_native_identity(
        payload: dict[str, object],
        identity: dict[str, object],
    ) -> None:
        payload["implementation"] = {
            "pre": copy.deepcopy(identity),
            "post": copy.deepcopy(identity),
        }
        payload["capture"]["implementation"] = copy.deepcopy(identity)

    pristine_root = tmp_path / "pristine"
    _copy_contract_root(ROOT, pristine_root)
    pristine_identity = commit_contract_tree(
        pristine_root,
        "pristine candidate contract",
        initialize=True,
    )
    bind_native_identity(native, pristine_identity)
    module.validate_capture_envelope(
        native,
        implementation_root=pristine_root,
        expected_candidate_commit=pristine_identity["base_commit"],
    )

    drift_paths = {
        "source": "tests/fixtures/p8_python_graphs/input_manifest.json",
        "gold": "tests/fixtures/p8_python_graphs/structural_expected.json",
        "catalog": "tests/fixtures/retrieval_quality/p8_python_graphs.json",
        "pin": "tests/p8_python_graph_identity.py",
        "runner": "tests/p8_real_python_graphs_acceptance.py",
    }
    for label, relative in drift_paths.items():
        drift_root = tmp_path / label
        subprocess.run(
            ("git", "clone", "-q", str(pristine_root), str(drift_root)),
            check=True,
        )
        target = drift_root / relative
        original = target.read_bytes()
        target.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        drift_identity = commit_contract_tree(
            drift_root,
            f"{label} drift",
        )
        drift_payload = copy.deepcopy(native)
        bind_native_identity(drift_payload, drift_identity)
        with pytest.raises(
            ValueError,
            match=(
                "runner mismatch"
                if label == "runner"
                else "protected input mismatch"
            ),
        ):
            module.validate_capture_envelope(
                drift_payload,
                implementation_root=drift_root,
                expected_candidate_commit=drift_identity["base_commit"],
            )


def test_hash_envelope_is_offline_and_has_no_bge_attestation() -> None:
    module = _load_harness()
    payload = _strip_test_fields(
        _capture_envelope(
            side="hash",
            sequence=1,
            provider="hash",
            requests_redink=0,
            requests_daily=0,
        )
    )
    assert payload["attestation"] == {"pre": None, "post": None}
    assert payload["transform_id"] is None
    assert payload["embedding_requests"] == {
        "redink": 0,
        "daily": 0,
        "total": 0,
    }
    module.validate_capture_envelope(payload)

    for mutation in (
        ("attestation", {"pre": _attestation(), "post": _attestation()}),
        ("transform_id", "bge-input-v1"),
        (
            "embedding_requests",
            {"redink": 1, "daily": 0, "total": 1},
        ),
    ):
        invalid = copy.deepcopy(payload)
        invalid[mutation[0]] = mutation[1]
        with pytest.raises(ValueError):
            module.validate_capture_envelope(invalid)


def test_native_hash_envelope_binds_descriptor_to_static_identity() -> None:
    module = _load_harness()
    payload = _strip_test_fields(
        _capture_envelope(
            side="hash",
            sequence=1,
            provider="hash",
            requests_redink=0,
            requests_daily=0,
        )
    )
    identity = payload["capture"]["embedding_identity"]
    assert identity["static_config_identity"] == HASH_CONFIG_IDENTITY
    assert identity["descriptor_identity"] == HASH_CONFIG_IDENTITY
    assert all(
        identity[field] is None
        for field in (
            "canonical_model",
            "model_digest",
            "ollama_version",
            "input_transform_id",
            "pre_attestation",
            "post_attestation",
        )
    )
    module.validate_capture_envelope(payload)

    invalid = copy.deepcopy(payload)
    invalid["capture"]["embedding_identity"]["descriptor_identity"] = "f" * 64
    with pytest.raises(ValueError) as exc_info:
        module.validate_capture_envelope(invalid)
    assert str(exc_info.value) == "native hash embedding identity mismatch"


@pytest.mark.parametrize(
    "privacy_case",
    ("raw-payload", "source-body", "tmp-absolute-path"),
)
def test_native_envelope_recursively_rejects_private_payloads(
    privacy_case: str,
) -> None:
    module = _load_harness()
    payload = _strip_test_fields(
        _capture_envelope(
            side="hash",
            sequence=1,
            provider="hash",
            requests_redink=0,
            requests_daily=0,
        )
    )
    module.validate_capture_envelope(payload)
    if privacy_case == "raw-payload":
        payload["capture"]["witnesses"]["nested"] = {
            "outer": {
                "raw_payload": "SECRET SOURCE BODY SENTINEL",
            }
        }
    elif privacy_case == "source-body":
        payload["capture"]["witnesses"]["nested"] = {
            "outer": {
                "source_body": "SECRET SOURCE BODY SENTINEL",
            }
        }
    else:
        payload["capture"]["cases"]["case-00"]["selected"][0]["path"] = (
            "/tmp/P13_PRIVATE.py"
        )

    with pytest.raises(ValueError) as exc_info:
        module.validate_capture_envelope(payload)
    assert str(exc_info.value) == "capture envelope violates privacy contract"


def test_native_envelope_requires_independent_clean_candidate_commit(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    implementation_root = tmp_path / "candidate"
    _copy_contract_root(ROOT, implementation_root)
    subprocess.run(
        ("git", "init", "-q", str(implementation_root)),
        check=True,
    )
    subprocess.run(
        (
            "git",
            "-C",
            str(implementation_root),
            "add",
            "--",
            "src",
            "tests",
        ),
        check=True,
    )
    subprocess.run(
        (
            "git",
            "-C",
            str(implementation_root),
            "-c",
            "user.name=P13 Test",
            "-c",
            "user.email=p13@example.invalid",
            "commit",
            "-q",
            "-m",
            "candidate fixture",
        ),
        check=True,
    )
    expected_candidate_commit = _git_head(implementation_root)
    implementation = {
        "base_commit": expected_candidate_commit,
        "tracked_diff_sha256": hashlib.sha256(b"").hexdigest(),
        "untracked_files": {},
        "dirty": False,
    }
    payload = _strip_test_fields(
        _capture_envelope(
            side="hash",
            sequence=1,
            provider="hash",
            requests_redink=0,
            requests_daily=0,
        )
    )
    payload["implementation"] = {
        "pre": copy.deepcopy(implementation),
        "post": copy.deepcopy(implementation),
    }
    payload["capture"]["implementation"] = copy.deepcopy(implementation)
    module.validate_capture_envelope(
        payload,
        implementation_root=implementation_root,
        expected_candidate_commit=expected_candidate_commit,
    )

    with pytest.raises(
        ValueError,
        match="expected candidate commit is required",
    ):
        module.validate_capture_envelope(
            payload,
            implementation_root=implementation_root,
        )

    with pytest.raises(
        ValueError,
        match="native candidate commit mismatch",
    ):
        module.validate_capture_envelope(
            payload,
            implementation_root=implementation_root,
            expected_candidate_commit="f" * 40,
        )

    forged_commit = "f" * 40
    payload["implementation"]["pre"]["base_commit"] = forged_commit
    payload["implementation"]["post"]["base_commit"] = forged_commit
    payload["capture"]["implementation"]["base_commit"] = forged_commit
    with pytest.raises(ValueError) as exc_info:
        module.validate_capture_envelope(
            payload,
            implementation_root=implementation_root,
            expected_candidate_commit=expected_candidate_commit,
        )
    assert str(exc_info.value) == "native implementation identity mismatch"

    payload["implementation"] = {
        "pre": copy.deepcopy(implementation),
        "post": copy.deepcopy(implementation),
    }
    payload["capture"]["implementation"] = copy.deepcopy(implementation)
    harness_copy = implementation_root / "tests/p13_bge_provider_measurement.py"
    harness_copy.write_bytes(harness_copy.read_bytes() + b"\n")
    with pytest.raises(
        ValueError,
        match="native candidate must be clean",
    ):
        module.validate_capture_envelope(
            payload,
            implementation_root=implementation_root,
            expected_candidate_commit=expected_candidate_commit,
        )

    child_output = tmp_path / "must-not-capture.json"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(implementation_root / "src"),
            str(implementation_root / "tests"),
        )
    )
    completed = subprocess.run(
        (
            str(PYTHON),
            "-P",
            str(HARNESS),
            "_capture-child",
            "--implementation-root",
            str(implementation_root),
            "--expected-candidate-commit",
            expected_candidate_commit,
            "--sources",
            str(tmp_path / "missing-sources"),
            "--output",
            str(child_output),
            "--mode",
            "native",
            "--provider",
            "hash",
        ),
        cwd=implementation_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "native candidate must be clean" in completed.stderr
    assert not child_output.exists()


def test_legacy_query_timing_is_exactly_once_and_transparent() -> None:
    module = _load_harness()
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    result = object()

    def target(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return result

    target_module = SimpleNamespace(query_repository=target)
    original = target_module.query_repository
    arguments: list[tuple[tuple[object, ...], object]] = []
    cases = tuple(object() for _ in range(18))
    repository = object()
    repetitions = 3
    with module.legacy_query_timing_wrapper(
        target_module,
        measured_call_count=len(cases) * repetitions,
    ) as samples:
        assert target_module.query_repository is not original
        for _ in range(repetitions):
            for case in cases:
                args = (repository, case)
                marker = object()
                arguments.append((args, marker))
                assert (
                    target_module.query_repository(*args, marker=marker)
                    is result
                )
        witness_arguments = []
        for _ in range(4):
            args = (repository, object())
            marker = object()
            witness_arguments.append((args, marker))
            assert (
                target_module.query_repository(*args, marker=marker) is result
            )
        assert len(samples) == len(cases) * repetitions
        assert all(
            isinstance(value, float) and value >= 0.0 for value in samples
        )

    assert target_module.query_repository is original
    assert len(calls) == len(cases) * repetitions + 4
    assert all(
        actual_args[0] is expected_args[0]
        and actual_args[1] is expected_args[1]
        and actual_kwargs["marker"] is expected_marker
        for (actual_args, actual_kwargs), (
            expected_args,
            expected_marker,
        ) in zip(calls, arguments + witness_arguments)
    )


def test_legacy_query_timing_propagates_the_same_exception() -> None:
    module = _load_harness()
    sentinel = RuntimeError("frozen-query-failure")
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def target(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise sentinel

    target_module = SimpleNamespace(query_repository=target)
    original = target_module.query_repository
    repo = object()
    query = object()
    marker = object()
    with pytest.raises(RuntimeError) as caught:
        with module.legacy_query_timing_wrapper(
            target_module,
            measured_call_count=1,
        ) as samples:
            target_module.query_repository(repo, query, marker=marker)
    assert caught.value is sentinel
    assert target_module.query_repository is original
    assert len(calls) == 1
    assert calls[0][0][0] is repo
    assert calls[0][0][1] is query
    assert calls[0][1]["marker"] is marker
    assert len(samples) == 1


def test_legacy_child_maps_samples_in_manifest_insertion_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_harness()
    evidence_roots = [
        ancestor
        for ancestor in (ROOT, *ROOT.parents)
        if (ancestor / "baseline" / "context-search-tool").is_dir()
    ]
    assert len(evidence_roots) == 1
    baseline_root = evidence_roots[0] / "baseline" / "context-search-tool"
    case_ids = (
        "z-first",
        "a-second",
        *(f"case-{index:02d}" for index in range(2, 18)),
    )
    durations = {
        "z-first": (0.009, 0.007),
        "a-second": (0.004, 0.003),
        **{
            f"case-{index:02d}": (
                0.020 + index / 1000,
                0.010 + index / 1000,
            )
            for index in range(2, 18)
        },
    }
    clock_values: list[float] = []
    clock_base = 0.0
    for case_id in case_ids:
        for duration in durations[case_id]:
            clock_values.extend((clock_base, clock_base + duration))
            clock_base += 1.0
    clock = iter(clock_values)
    monkeypatch.setattr(
        module,
        "time",
        SimpleNamespace(perf_counter=lambda: next(clock)),
    )
    _install_mocked_ollama(monkeypatch)

    query_result = object()
    retrieval = SimpleNamespace(
        query_repository=lambda *args, **kwargs: query_result
    )

    class Provider:
        def _embed_batch(self, texts: object) -> object:
            return texts

    identity_module = SimpleNamespace(
        validate_protected_source=lambda *args, **kwargs: ()
    )
    baseline_identity = _implementation(BASELINE_COMMIT)

    def capture(
        implementation_root: Path,
        sources: Path,
        raw_output: Path,
        *,
        timing_reps: int,
        embedding: str,
    ) -> dict[str, object]:
        assert implementation_root == baseline_root
        assert timing_reps == 2
        assert embedding == "bge"
        for source_name in ("RedInk", "daily_stock_analysis"):
            identity_module.validate_protected_source(
                Path("sources") / source_name
            )
            Provider()._embed_batch([source_name])
        for case_id in case_ids:
            for _ in range(timing_reps):
                assert (
                    retrieval.query_repository(
                        Path("RedInk"),
                        case_id,
                        object(),
                    )
                    is query_result
                )
        for _ in range(2):
            assert (
                retrieval.query_repository(
                    Path("RedInk"),
                    "witness",
                    object(),
                )
                is query_result
            )
        return {
            "schema_version": 3,
            "manifest_sha256": GOLD_SHA256,
            "implementation": copy.deepcopy(baseline_identity),
            "embedding_identity": {
                "provider": "bge",
                "model": "bge-m3",
                "dimensions": 1024,
                "digest": BGE_DIGEST,
            },
            "repositories": {},
            "cases": {
                case_id: {
                    "repo": "redink",
                    "selected": [],
                    "required": [],
                    "contextual": [],
                    "unique_selected_paths": 0,
                }
                for case_id in case_ids
            },
            "witnesses": {},
            "timing": {
                "index_seconds_redink": 1.0,
                "index_seconds_daily": 2.0,
                "query_latency_mean_seconds": 0.01,
            },
        }

    fake_modules = {
        "context_search_tool": SimpleNamespace(
            __file__=str(
                baseline_root / "src/context_search_tool/__init__.py"
            )
        ),
        "context_search_tool.embeddings_bge": SimpleNamespace(
            __file__=str(
                baseline_root / "src/context_search_tool/embeddings_bge.py"
            ),
            BGEEmbeddingProvider=Provider,
        ),
        "p8_real_python_graphs_acceptance": SimpleNamespace(
            __file__=str(
                baseline_root / "tests/p8_real_python_graphs_acceptance.py"
            ),
            CAPTURE_SCHEMA_VERSION=3,
            identity=identity_module,
            implementation_identity=(
                lambda root: copy.deepcopy(baseline_identity)
            ),
            capture=capture,
        ),
        "context_search_tool.retrieval": retrieval,
    }
    monkeypatch.setattr(
        module,
        "importlib",
        SimpleNamespace(
            import_module=lambda name: fake_modules[name],
        ),
    )
    output = tmp_path / "legacy-envelope.json"

    assert (
        module.main(
            [
                "_capture-child",
                "--implementation-root",
                str(baseline_root),
                "--sources",
                str(tmp_path / "mocked-sources"),
                "--output",
                str(output),
                "--mode",
                "legacy-baseline",
                "--provider",
                "bge",
                "--repetitions",
                "2",
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    minima = payload["timing"]["query_case_min_seconds"]
    assert minima["z-first"] == 0.007
    assert minima["a-second"] == 0.003


def test_embedding_request_counting_is_transparent_and_per_repository() -> None:
    module = _load_harness()
    current = {"repo": "redink"}
    counts = {"redink": 0, "daily": 0, "total": 0}
    calls: list[tuple[object, object]] = []
    result = object()

    def target(provider: object, texts: object, *, marker: object) -> object:
        calls.append((provider, texts))
        assert marker is marker_by_text[id(texts)]
        return result

    class Provider:
        _embed_batch = target

    original = Provider._embed_batch
    provider = object()
    redink_texts = ["redink"]
    daily_texts = ["daily"]
    redink_marker = object()
    daily_marker = object()
    marker_by_text = {
        id(redink_texts): redink_marker,
        id(daily_texts): daily_marker,
    }
    with module.embedding_request_wrapper(
        Provider,
        repository=lambda: current["repo"],
        counts=counts,
    ):
        assert Provider._embed_batch is not original
        assert (
            Provider._embed_batch(
                provider,
                redink_texts,
                marker=redink_marker,
            )
            is result
        )
        current["repo"] = "daily"
        assert (
            Provider._embed_batch(
                provider,
                daily_texts,
                marker=daily_marker,
            )
            is result
        )

    assert Provider._embed_batch is original
    assert calls == [(provider, redink_texts), (provider, daily_texts)]
    assert calls[0][1] is redink_texts
    assert calls[1][1] is daily_texts
    assert counts == {"redink": 1, "daily": 1, "total": 2}

    sentinel = ValueError("embed-failure")

    def fail(provider: object, texts: object, *, marker: object) -> object:
        assert provider is provider_arg
        assert texts is daily_texts
        assert marker is failure_marker
        raise sentinel

    class FailingProvider:
        _embed_batch = fail

    failure_original = FailingProvider._embed_batch
    provider_arg = object()
    failure_marker = object()
    with pytest.raises(ValueError) as caught:
        with module.embedding_request_wrapper(
            FailingProvider,
            repository=lambda: "daily",
            counts=counts,
        ):
            FailingProvider._embed_batch(
                provider_arg,
                daily_texts,
                marker=failure_marker,
            )
    assert caught.value is sentinel
    assert FailingProvider._embed_batch is failure_original
    assert counts == {"redink": 1, "daily": 2, "total": 3}


def test_engineering_comparison_uses_three_pairs_and_frozen_reducers(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    output = tmp_path / "engineering-gates.json"
    report = module.compare_engineering(
        _engineering_captures(),
        output,
    )

    assert report["pair_order"] == [
        ["baseline", "candidate"],
        ["candidate", "baseline"],
        ["baseline", "candidate"],
    ]
    assert report["statistics"] == {
        "baseline": {
            "index_seconds": {"redink": 10.5, "daily": 21.0, "total": 31.5},
            "query_p95_seconds": 1.1,
            "embedding_requests": {"redink": 10, "daily": 20, "total": 30},
        },
        "candidate": {
            "index_seconds": {"redink": 10.5, "daily": 21.0, "total": 31.5},
            "query_p95_seconds": 1.2,
            "embedding_requests": {"redink": 10, "daily": 19, "total": 29},
        },
    }
    assert report["ratios"]["candidate_over_baseline"] == {
        "index_redink": 1.0,
        "index_daily": 1.0,
        "index_total": 1.0,
        "query_p95": pytest.approx(1.0909090909090908),
    }
    assert report["baseline_stability"] == {
        "index_redink": pytest.approx(0.10),
        "index_daily": pytest.approx(0.10),
        "query_p95": pytest.approx(0.15),
    }
    assert set(report["gates"]) == ENGINEERING_GATE_KEYS
    assert report["disposition"] == "pass"
    assert all(gate["passed"] for gate in report["gates"].values())
    _assert_gate_evidence(report)
    assert output.read_text(encoding="utf-8") == _canonical(report)


def test_engineering_negative_gates_are_not_tuned_after_results(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    base = _engineering_captures()

    def set_index(
        capture: dict[str, object],
        repository: str,
        value: float,
    ) -> None:
        capture["timing"]["index_seconds"][repository] = value
        if capture["mode"] == "native":
            capture["capture"]["timing"] = copy.deepcopy(capture["timing"])

    def set_query(capture: dict[str, object], value: float) -> None:
        capture["timing"]["query_p95_seconds"] = value
        capture["timing"]["query_p50_seconds"] = value / 2
        capture["timing"]["query_case_min_seconds"] = {
            f"case-{case:02d}": value * (case + 1) / 18
            for case in range(18)
        }
        if capture["mode"] == "native":
            capture["capture"]["timing"] = copy.deepcopy(capture["timing"])

    def set_requests(
        capture: dict[str, object],
        redink: int,
        daily: int,
    ) -> None:
        requests = {"redink": redink, "daily": daily, "total": redink + daily}
        capture["embedding_requests"] = requests
        capture["capture"]["embedding_requests"] = copy.deepcopy(requests)

    rows: list[
        tuple[
            str,
            str,
            list[dict[str, object]],
            dict[str, object],
        ]
    ] = []

    baseline_redink = copy.deepcopy(base)
    set_index(baseline_redink[4], "redink", 11.01)
    rows.append(
        (
            "baseline_index_stability_redink",
            "blocked",
            baseline_redink,
            {
                "raw_values": [10.0, 10.5, 11.01],
                "numerator": 11.01,
                "denominator": 10.0,
                "ratio": 0.101,
                "threshold": 0.10,
            },
        )
    )

    baseline_daily = copy.deepcopy(base)
    set_index(baseline_daily[4], "daily", 22.01)
    rows.append(
        (
            "baseline_index_stability_daily",
            "blocked",
            baseline_daily,
            {
                "raw_values": [20.0, 21.0, 22.01],
                "numerator": 22.01,
                "denominator": 20.0,
                "ratio": 0.1005,
                "threshold": 0.10,
            },
        )
    )

    baseline_query = copy.deepcopy(base)
    set_query(baseline_query[4], 1.151)
    rows.append(
        (
            "baseline_query_p95_stability",
            "blocked",
            baseline_query,
            {
                "raw_values": [1.0, 1.1, 1.151],
                "numerator": 1.151,
                "denominator": 1.0,
                "ratio": 0.151,
                "threshold": 0.15,
            },
        )
    )

    candidate_redink = copy.deepcopy(base)
    for capture in candidate_redink:
        if capture["mode"] == "native":
            set_index(capture, "redink", 11.56)
    rows.append(
        (
            "candidate_index_ratio_redink",
            "fail",
            candidate_redink,
            {
                "raw_values": {"baseline": 10.5, "candidate": 11.56},
                "numerator": 11.56,
                "denominator": 10.5,
                "ratio": 11.56 / 10.5,
                "threshold": 1.10,
            },
        )
    )

    candidate_daily = copy.deepcopy(base)
    for capture in candidate_daily:
        if capture["mode"] == "native":
            set_index(capture, "daily", 23.11)
    rows.append(
        (
            "candidate_index_ratio_daily",
            "fail",
            candidate_daily,
            {
                "raw_values": {"baseline": 21.0, "candidate": 23.11},
                "numerator": 23.11,
                "denominator": 21.0,
                "ratio": 23.11 / 21.0,
                "threshold": 1.10,
            },
        )
    )

    candidate_total = copy.deepcopy(base)
    native = [row for row in candidate_total if row["mode"] == "native"]
    for capture, redink, daily in zip(
        native,
        (10.5, 10.5, 25.0),
        (21.0, 30.0, 21.0),
    ):
        set_index(capture, "redink", redink)
        set_index(capture, "daily", daily)
    rows.append(
        (
            "candidate_index_ratio_total",
            "fail",
            candidate_total,
            {
                "raw_values": {"baseline": 31.5, "candidate": 40.5},
                "numerator": 40.5,
                "denominator": 31.5,
                "ratio": 40.5 / 31.5,
                "threshold": 1.10,
            },
        )
    )

    candidate_query = copy.deepcopy(base)
    for capture in candidate_query:
        if capture["mode"] == "native":
            set_query(capture, 1.266)
    rows.append(
        (
            "candidate_query_p95_ratio",
            "fail",
            candidate_query,
            {
                "raw_values": {"baseline": 1.1, "candidate": 1.266},
                "numerator": 1.266,
                "denominator": 1.1,
                "ratio": 1.266 / 1.1,
                "threshold": 1.15,
            },
        )
    )

    requests_redink = copy.deepcopy(base)
    for capture in requests_redink:
        if capture["mode"] == "native":
            set_requests(capture, 11, 18)
    rows.append(
        (
            "requests_non_increasing_redink",
            "fail",
            requests_redink,
            {
                "raw_values": {"baseline": 10, "candidate": 11},
                "numerator": 11,
                "denominator": 10,
                "ratio": 1.1,
                "threshold": 1.0,
            },
        )
    )

    requests_daily = copy.deepcopy(base)
    for capture in requests_daily:
        if capture["mode"] == "native":
            set_requests(capture, 8, 21)
    rows.append(
        (
            "requests_non_increasing_daily",
            "fail",
            requests_daily,
            {
                "raw_values": {"baseline": 20, "candidate": 21},
                "numerator": 21,
                "denominator": 20,
                "ratio": 1.05,
                "threshold": 1.0,
            },
        )
    )

    requests_total = copy.deepcopy(base)
    for capture in requests_total:
        if capture["mode"] == "native":
            set_requests(capture, 10, 20)
    rows.append(
        (
            "requests_strictly_lower_total",
            "fail",
            requests_total,
            {
                "raw_values": {"baseline": 30, "candidate": 30},
                "numerator": 30,
                "denominator": 30,
                "ratio": 1.0,
                "threshold": 1.0,
            },
        )
    )

    non_timing = copy.deepcopy(base)
    non_timing[2]["capture"]["cases"]["case-00"]["selected"][0]["path"] = (
        "drift.py"
    )
    rows.append(
        (
            "same_side_non_timing",
            "fail",
            non_timing,
            {
                "raw_values": {"mismatched_captures": 1},
                "numerator": 1,
                "denominator": 0,
                "ratio": None,
                "threshold": 0,
            },
        )
    )

    assert {name for name, _, _, _ in rows} == ENGINEERING_GATE_KEYS
    for index, (failed_gate, disposition, captures, expected) in enumerate(rows):
        report = module.compare_engineering(
            captures,
            tmp_path / f"engineering-negative-{index}.json",
        )
        assert report["disposition"] == disposition
        assert {
            name
            for name, gate in report["gates"].items()
            if gate["passed"] is False
        } == {failed_gate}
        gate = report["gates"][failed_gate]
        for field, literal in expected.items():
            if isinstance(literal, float):
                assert gate[field] == pytest.approx(literal)
            else:
                assert gate[field] == literal
        _assert_gate_evidence(report)


def test_product_comparison_requires_one_candidate_identity(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    captures = _product_captures()
    second_identity = _implementation(SYNTHETIC_CANDIDATE_COMMIT)
    second_identity["tracked_diff_sha256"] = "b" * 64
    second_identity["dirty"] = True
    for capture in captures[2:]:
        capture["implementation"] = {
            "pre": copy.deepcopy(second_identity),
            "post": copy.deepcopy(second_identity),
        }
        capture["capture"]["implementation"] = copy.deepcopy(
            second_identity
        )
    profiles = {
        profile: {
            "passed": 6,
            "total": 7,
            "only_known_miss": "audit-status-literal",
        }
        for profile in ("p1_vector_bge", "p1_hybrid_bge")
    }
    output = tmp_path / "must-not-exist.json"

    with pytest.raises(
        ValueError,
        match="candidate implementation identity mismatch",
    ):
        module.compare_product(captures, profiles, output)
    assert not output.exists()


def test_product_comparison_applies_all_eight_frozen_gates(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    output = tmp_path / "product-comparison.json"
    p1_profiles = {
        "p1_vector_bge": {
            "passed": 6,
            "total": 7,
            "only_known_miss": "audit-status-literal",
        },
        "p1_hybrid_bge": {
            "passed": 6,
            "total": 7,
            "only_known_miss": "audit-status-literal",
        },
    }
    report = module.compare_product(
        _product_captures(),
        p1_profiles,
        output,
    )

    assert report["statistics"] == {
        "hash": {
            "index_seconds": {"redink": 1.1, "daily": 2.1},
            "query_p95_seconds": 1.1,
            "recall_at_12": pytest.approx(2 / 3),
            "noise_ratio": 0.20,
        },
        "bge": {
            "index_seconds": {"redink": 42.0, "daily": 84.0},
            "query_p95_seconds": 1.55,
            "recall_at_12": 1.0,
            "noise_ratio": 0.20,
        },
    }
    assert report["required"] == {
        "newly_satisfied": ["required-c"],
        "lost": [],
    }
    assert report["ratios"]["bge_over_hash"] == {
        "index_redink": pytest.approx(42.0 / 1.1),
        "index_daily": 40.0,
        "query_p95": pytest.approx(1.55 / 1.1),
    }
    assert report["p1_profiles"] == p1_profiles
    assert set(report["gates"]) == PRODUCT_GATE_KEYS
    assert all(gate["passed"] for gate in report["gates"].values())
    assert report["disposition"] == "pass"
    _assert_gate_evidence(report)
    assert output.name == "product-comparison.json"
    assert output.read_text(encoding="utf-8") == _canonical(report)


def test_product_negative_gates_fail_without_reusing_p8_comparator(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    good_p1 = {
        "p1_vector_bge": {
            "passed": 6,
            "total": 7,
            "only_known_miss": "audit-status-literal",
        },
        "p1_hybrid_bge": {
            "passed": 6,
            "total": 7,
            "only_known_miss": "audit-status-literal",
        },
    }

    def set_bge_case(
        captures: list[dict[str, object]],
        selected_paths: tuple[str, ...],
    ) -> None:
        for capture in captures:
            if capture["provider"] != "bge":
                continue
            case = capture["capture"]["cases"]["case-00"]
            case["selected"] = [
                {
                    "rank": index + 1,
                    "path": path,
                    "graph_origin": False,
                    "relation_slot": False,
                    "relation_witness": None,
                }
                for index, path in enumerate(selected_paths)
            ]
            case["contextual"] = ["context-a"]
            case["unique_selected_paths"] = len(selected_paths)
            ranks = {
                path: index + 1
                for index, path in enumerate(selected_paths)
            }
            for required in case["required"]:
                required["rank"] = ranks.get(required["path"])
                required["state"] = (
                    "selected"
                    if required["rank"] is not None
                    else "not_selected"
                )

    def set_bge_query(
        captures: list[dict[str, object]],
        value: float,
    ) -> None:
        for capture in captures:
            if capture["provider"] != "bge":
                continue
            capture["timing"]["query_p95_seconds"] = value
            capture["timing"]["query_p50_seconds"] = value / 2
            capture["timing"]["query_case_min_seconds"] = {
                f"case-{case:02d}": value * (case + 1) / 18
                for case in range(18)
            }
            capture["capture"]["timing"] = copy.deepcopy(capture["timing"])

    def set_bge_index(
        captures: list[dict[str, object]],
        repository: str,
        value: float,
    ) -> None:
        for capture in captures:
            if capture["provider"] != "bge":
                continue
            capture["timing"]["index_seconds"][repository] = value
            capture["capture"]["timing"] = copy.deepcopy(capture["timing"])

    def input_hashes(
        captures: list[dict[str, object]],
    ) -> dict[str, list[str]]:
        result = {"hash": [], "bge": []}
        for capture in captures:
            result[capture["provider"]].append(
                hashlib.sha256(
                    _canonical(capture).encode("utf-8")
                ).hexdigest()
            )
        return result

    rows: list[
        tuple[
            str,
            set[str],
            list[dict[str, object]],
            dict[str, object],
            dict[str, object],
        ]
    ] = []

    recall = _product_captures()
    set_bge_case(recall, ("required-c", "context-a"))
    # With one shared gold universe, lower recall logically entails a loss.
    rows.append(
        (
            "recall_non_decreasing",
            {"recall_non_decreasing", "zero_required_loss"},
            recall,
            copy.deepcopy(good_p1),
            {
                "raw_values": {"hash": 2 / 3, "bge": 1 / 3},
                "numerator": 1 / 3,
                "denominator": 2 / 3,
                "ratio": 0.5,
                "threshold": 1.0,
            },
        )
    )

    loss = _product_captures()
    set_bge_case(
        loss,
        ("required-a", "required-c", "context-a"),
    )
    rows.append(
        (
            "zero_required_loss",
            {"zero_required_loss"},
            loss,
            copy.deepcopy(good_p1),
            {
                "raw_values": {"lost": ["required-b"]},
                "numerator": 1,
                "denominator": 0,
                "ratio": None,
                "threshold": 0,
            },
        )
    )

    no_gain = _product_captures()
    set_bge_case(
        no_gain,
        ("required-a", "required-b", "context-a"),
    )
    rows.append(
        (
            "new_required",
            {"new_required"},
            no_gain,
            copy.deepcopy(good_p1),
            {
                "raw_values": {"newly_satisfied": []},
                "numerator": 0,
                "denominator": 1,
                "ratio": 0.0,
                "threshold": 1,
            },
        )
    )

    noise = _product_captures()
    for capture in noise:
        if capture["provider"] != "bge":
            continue
        case = capture["capture"]["cases"]["case-00"]
        case["selected"].append(
            {
                "rank": 6,
                "path": "noise-b",
                "graph_origin": False,
                "relation_slot": False,
                "relation_witness": None,
            }
        )
        case["unique_selected_paths"] = 6
    rows.append(
        (
            "noise_non_increasing",
            {"noise_non_increasing"},
            noise,
            copy.deepcopy(good_p1),
            {
                "raw_values": {"hash": 0.20, "bge": 1 / 3},
                "numerator": 1 / 3,
                "denominator": 0.20,
                "ratio": 5 / 3,
                "threshold": 1.0,
            },
        )
    )

    regressed_p1 = copy.deepcopy(good_p1)
    regressed_p1["p1_vector_bge"]["passed"] = 5
    rows.append(
        (
            "p1_continuity",
            {"p1_continuity"},
            _product_captures(),
            regressed_p1,
            {
                "raw_values": {
                    "expected_passed": {
                        "p1_vector_bge": 6,
                        "p1_hybrid_bge": 6,
                    },
                    "actual_passed": {
                        "p1_vector_bge": 5,
                        "p1_hybrid_bge": 6,
                    },
                },
                "numerator": 5,
                "denominator": 6,
                "ratio": 5 / 6,
                "threshold": 1.0,
            },
        )
    )

    query = _product_captures()
    set_bge_query(query, 1.66)
    rows.append(
        (
            "query_p95_ratio",
            {"query_p95_ratio"},
            query,
            copy.deepcopy(good_p1),
            {
                "raw_values": {"hash": 1.1, "bge": 1.66},
                "numerator": 1.66,
                "denominator": 1.1,
                "ratio": 1.66 / 1.1,
                "threshold": 1.50,
            },
        )
    )

    index = _product_captures()
    set_bge_index(index, "redink", 56.0)
    rows.append(
        (
            "per_repository_index_ratio",
            {"per_repository_index_ratio"},
            index,
            copy.deepcopy(good_p1),
            {
                "raw_values": {
                    "redink": {"hash": 1.1, "bge": 56.0},
                    "daily": {"hash": 2.1, "bge": 84.0},
                },
                "numerator": 56.0,
                "denominator": 1.1,
                "ratio": 56.0 / 1.1,
                "threshold": 50.0,
            },
        )
    )

    assert {row[0] for row in rows} == (
        PRODUCT_GATE_KEYS - {"same_provider_non_timing"}
    )
    for index, (
        target_gate,
        failed_gates,
        captures,
        p1_profiles,
        expected,
    ) in enumerate(rows):
        output = tmp_path / f"product-negative-{index}.json"
        report = module.compare_product(captures, p1_profiles, output)
        assert report["disposition"] == "fail"
        assert {
            name
            for name, gate in report["gates"].items()
            if gate["passed"] is False
        } == failed_gates
        assert all(
            gate["passed"] is (name not in failed_gates)
            for name, gate in report["gates"].items()
        )
        gate = report["gates"][target_gate]
        for field, literal in expected.items():
            if isinstance(literal, float):
                assert gate[field] == pytest.approx(literal)
            else:
                assert gate[field] == literal
        assert gate["input_capture_sha256"] == input_hashes(captures)
        assert gate["evidence_path"] == output.name
        _assert_gate_evidence(report)


def test_product_requires_two_exact_nontiming_captures_per_provider(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    captures = _product_captures()
    captures[1]["capture"]["repositories"]["redink"][
        "index_sqlite_bytes"
    ] = 2
    p1_profiles = {
        name: {
            "passed": 6,
            "total": 7,
            "only_known_miss": "audit-status-literal",
        }
        for name in ("p1_vector_bge", "p1_hybrid_bge")
    }
    output = tmp_path / "product-comparison.json"
    report = module.compare_product(
        captures,
        p1_profiles,
        output,
    )
    assert report["disposition"] == "fail"
    assert {
        name
        for name, gate in report["gates"].items()
        if gate["passed"] is False
    } == {"same_provider_non_timing"}
    assert all(
        gate["passed"] is (name != "same_provider_non_timing")
        for name, gate in report["gates"].items()
    )
    gate = report["gates"]["same_provider_non_timing"]
    assert gate["raw_values"] == {"mismatched_providers": ["hash"]}
    assert gate["numerator"] == 1
    assert gate["denominator"] == 0
    assert gate["ratio"] is None
    assert gate["threshold"] == 0
    assert gate["input_capture_sha256"] == {
        provider: [
            hashlib.sha256(_canonical(capture).encode("utf-8")).hexdigest()
            for capture in captures
            if capture["provider"] == provider
        ]
        for provider in ("hash", "bge")
    }
    assert gate["evidence_path"] == output.name
    _assert_gate_evidence(report)
