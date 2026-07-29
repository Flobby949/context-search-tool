from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p8_real_python_graphs_acceptance as runner


_HASH_CONFIG_IDENTITY = (
    "5ab1cee713aff995519814538508a44cece92c285a746094e1cab8b86c7745be"
)
_BGE_CONFIG_IDENTITY = (
    "c1cc02373a3d92d32afefaf6fcfb1cb8ba8e6cdbdd3f0298484965b94ca0896b"
)
_BGE_DIGEST = (
    "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab"
)
_BGE_DESCRIPTOR_IDENTITY = (
    "bge-ollama-v1:"
    "c1cc02373a3d92d32afefaf6fcfb1cb8ba8e6cdbdd3f0298484965b94ca0896b:"
    "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v2"
)
_SUPERSEDED_BGE_V1_DESCRIPTOR_IDENTITY = (
    "bge-ollama-v1:"
    "c1cc02373a3d92d32afefaf6fcfb1cb8ba8e6cdbdd3f0298484965b94ca0896b:"
    "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v1"
)
_CAPTURE_ROOT_KEYS = {
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
_IDENTITY_KEYS = {
    "provider",
    "configured_model",
    "dimensions",
    "static_config_identity",
    "descriptor_identity",
    "canonical_model",
    "model_digest",
    "ollama_version",
    "input_transform_id",
    "pre_attestation",
    "post_attestation",
}
_ATTESTATION_KEYS = {
    "configured_model",
    "canonical_model",
    "model_digest",
    "ollama_version",
    "base_url",
    "dimensions",
    "input_transform_id",
    "embedding_identity",
}


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
        "schema_version": 4,
        "manifest_sha256": (
            "459e6a56c0f7c3b033e34dafeba623b15e221d19ff59244d7fa29a47621f7767"
        ),
        "implementation": {
            "base_commit": "a7c35368061283a9fadaacf81b3b6a318ce996f3",
            "tracked_diff_sha256": "0" * 64,
            "untracked_files": {},
            "dirty": False,
        },
        "environment": {
            "python_version": "3.13.12",
            "sqlite_version": "3.51.2",
            "numpy_version": "2.4.2",
        },
        "embedding_identity": {
            "provider": "hash",
            "configured_model": "hash-v1",
            "dimensions": 384,
            "static_config_identity": _HASH_CONFIG_IDENTITY,
            "descriptor_identity": _HASH_CONFIG_IDENTITY,
            "canonical_model": None,
            "model_digest": None,
            "ollama_version": None,
            "input_transform_id": None,
            "pre_attestation": None,
            "post_attestation": None,
        },
        "repositories": {
            "redink": {
                "selected_files": 28,
                "structure": {},
                "index_sqlite_bytes": 1,
            },
            "daily": {
                "selected_files": 203,
                "structure": {},
                "index_sqlite_bytes": 1,
            },
        },
        "cases": cases,
        "witnesses": {},
        "embedding_requests": {"redink": 0, "daily": 0, "total": 0},
        "timing": {
            "index_seconds": {"redink": 0.1, "daily": 0.2},
            "query_case_min_seconds": {
                case_id: (index + 1) / 1000
                for index, case_id in enumerate(sorted(cases))
            },
            "query_p50_seconds": 0.010,
            "query_p95_seconds": 0.019,
        },
    }


def _real_shaped_capture(*, provider: str = "hash") -> dict:
    payload = _synthetic_capture(improved=False)
    del payload["cases"]["daily-case-11"]
    payload["timing"]["query_case_min_seconds"] = {
        case_id: (index + 1) / 1000
        for index, case_id in enumerate(sorted(payload["cases"]))
    }
    payload["timing"]["query_p50_seconds"] = 0.009
    payload["timing"]["query_p95_seconds"] = 0.018
    if provider == "hash":
        return payload
    assert provider == "bge"
    attestation = {
        "configured_model": "bge-m3",
        "canonical_model": "bge-m3:latest",
        "model_digest": _BGE_DIGEST,
        "ollama_version": "0.30.10",
        "base_url": "http://localhost:11434",
        "dimensions": 1024,
        "input_transform_id": "bge-input-v2",
        "embedding_identity": _BGE_DESCRIPTOR_IDENTITY,
    }
    payload["embedding_identity"] = {
        "provider": "bge",
        "configured_model": "bge-m3",
        "dimensions": 1024,
        "static_config_identity": _BGE_CONFIG_IDENTITY,
        "descriptor_identity": _BGE_DESCRIPTOR_IDENTITY,
        "canonical_model": "bge-m3:latest",
        "model_digest": _BGE_DIGEST,
        "ollama_version": "0.30.10",
        "input_transform_id": "bge-input-v2",
        "pre_attestation": copy.deepcopy(attestation),
        "post_attestation": copy.deepcopy(attestation),
    }
    payload["embedding_requests"] = {"redink": 4, "daily": 9, "total": 13}
    return payload


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, indent=1
    ) + "\n"


def _write_capture(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(_canonical_json(payload), encoding="utf-8")
    return path


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

    real_shaped = _real_shaped_capture()
    ok = tmp_path / "ok.json"
    ok.write_text(runner._canonical(real_shaped), encoding="utf-8")
    runner.check(ok)

    for index, absolute_path in enumerate(
        ("/Users/someone/private/file.py", "/tmp/P13_PRIVATE.py")
    ):
        leaked = copy.deepcopy(real_shaped)
        first = next(iter(leaked["cases"].values()))
        first["selected"][0]["path"] = absolute_path
        bad = tmp_path / f"absolute-{index}.json"
        bad.write_text(runner._canonical(leaked), encoding="utf-8")
        with pytest.raises(ValueError) as exc_info:
            runner.check(bad)
        assert str(exc_info.value) == "capture privacy violation: absolute path"

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


def test_native_capture_schema_v4_is_exactly_closed(
    tmp_path: Path,
) -> None:
    payload = _real_shaped_capture()
    assert runner.CAPTURE_SCHEMA_VERSION == 4
    assert set(payload) == _CAPTURE_ROOT_KEYS
    assert set(payload["embedding_identity"]) == _IDENTITY_KEYS
    runner.check(_write_capture(tmp_path, "valid-v4.json", payload))

    mutations = []
    extra_root = copy.deepcopy(payload)
    extra_root["legacy"] = {}
    mutations.append(extra_root)
    extra_identity = copy.deepcopy(payload)
    extra_identity["embedding_identity"]["backend"] = "ollama"
    mutations.append(extra_identity)
    extra_environment = copy.deepcopy(payload)
    extra_environment["environment"]["machine"] = "private-host"
    mutations.append(extra_environment)
    extra_timing = copy.deepcopy(payload)
    extra_timing["timing"]["query_latency_mean_seconds"] = 0.01
    mutations.append(extra_timing)
    extra_requests = copy.deepcopy(payload)
    extra_requests["embedding_requests"]["unattributed"] = 0
    mutations.append(extra_requests)

    for index, mutation in enumerate(mutations):
        with pytest.raises(ValueError):
            runner.check(
                _write_capture(tmp_path, f"open-mapping-{index}.json", mutation)
            )


def test_hash_v4_requires_static_descriptor_identity_and_zero_ollama(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _real_shaped_capture(provider="hash")
    identity = payload["embedding_identity"]
    assert identity == {
        "provider": "hash",
        "configured_model": "hash-v1",
        "dimensions": 384,
        "static_config_identity": _HASH_CONFIG_IDENTITY,
        "descriptor_identity": _HASH_CONFIG_IDENTITY,
        "canonical_model": None,
        "model_digest": None,
        "ollama_version": None,
        "input_transform_id": None,
        "pre_attestation": None,
        "post_attestation": None,
    }
    assert payload["embedding_requests"] == {
        "redink": 0,
        "daily": 0,
        "total": 0,
    }
    import requests

    from context_search_tool.embeddings_bge import BGEEmbeddingProvider

    repository_root = Path(__file__).resolve().parents[1]
    evidence_files = [
        ancestor / "protected-inputs.json"
        for ancestor in (repository_root, *repository_root.parents)
        if (ancestor / "protected-inputs.json").is_file()
    ]
    pointer = repository_root / ".quality" / "p13-run-root.txt"
    if not evidence_files and pointer.is_file():
        evidence_files.append(
            Path(pointer.read_text(encoding="utf-8").strip())
            / "protected-inputs.json"
        )
    assert len(evidence_files) == 1, "frozen P8 source evidence is unavailable"
    protected = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    sources_root = Path(protected["p8_source_root"])
    assert (sources_root / "RedInk").is_dir()
    assert (sources_root / "daily_stock_analysis").is_dir()

    ollama_calls = {
        "session": 0,
        "version_tags": 0,
        "embed": 0,
        "warmup": 0,
    }

    def forbidden(boundary: str):
        def fail(*args: object, **kwargs: object) -> object:
            ollama_calls[boundary] += 1
            raise AssertionError(f"hash capture attempted Ollama {boundary}")

        return fail

    monkeypatch.setattr(requests, "Session", forbidden("session"))
    monkeypatch.setattr(
        BGEEmbeddingProvider,
        "runtime_fingerprint",
        forbidden("version_tags"),
    )
    monkeypatch.setattr(
        BGEEmbeddingProvider,
        "assert_runtime_unchanged",
        forbidden("version_tags"),
    )
    monkeypatch.setattr(
        BGEEmbeddingProvider,
        "embed_texts",
        forbidden("embed"),
    )
    if hasattr(runner, "_ollama_model_digest"):
        monkeypatch.setattr(
            runner,
            "_ollama_model_digest",
            forbidden("version_tags"),
        )
    for name, value in tuple(vars(runner).items()):
        if "warm" in name.lower() and callable(value):
            monkeypatch.setattr(runner, name, forbidden("warmup"))

    output = tmp_path / "hash-capture-v4.json"
    captured = runner.capture(
        repository_root,
        sources_root,
        output,
        timing_reps=1,
        embedding="hash",
    )
    assert captured["schema_version"] == 4
    assert json.loads(output.read_text(encoding="utf-8")) == captured
    runner.check(output)
    assert captured["embedding_identity"] == identity
    assert captured["embedding_requests"] == {
        "redink": 0,
        "daily": 0,
        "total": 0,
    }
    assert ollama_calls == {
        "session": 0,
        "version_tags": 0,
        "embed": 0,
        "warmup": 0,
    }

    runner.check(_write_capture(tmp_path, "hash-v4.json", payload))
    for field, value in (
        ("canonical_model", "bge-m3:latest"),
        ("model_digest", _BGE_DIGEST),
        ("ollama_version", "0.30.10"),
        ("input_transform_id", "bge-input-v2"),
        ("pre_attestation", {}),
        ("post_attestation", {}),
    ):
        invalid = copy.deepcopy(payload)
        invalid["embedding_identity"][field] = value
        with pytest.raises(ValueError):
            runner.check(
                _write_capture(tmp_path, f"hash-{field}.json", invalid)
            )

    attempted = copy.deepcopy(payload)
    attempted["embedding_requests"] = {"redink": 1, "daily": 0, "total": 1}
    with pytest.raises(ValueError):
        runner.check(_write_capture(tmp_path, "hash-egress.json", attempted))


def test_bge_v4_requires_one_matching_attested_descriptor_identity(
    tmp_path: Path,
) -> None:
    payload = _real_shaped_capture(provider="bge")
    identity = payload["embedding_identity"]
    assert set(identity) == _IDENTITY_KEYS
    assert set(identity["pre_attestation"]) == _ATTESTATION_KEYS
    assert identity["pre_attestation"] == identity["post_attestation"]
    assert identity["descriptor_identity"] == _BGE_DESCRIPTOR_IDENTITY
    assert identity["static_config_identity"] == _BGE_CONFIG_IDENTITY
    assert identity["canonical_model"] == "bge-m3:latest"
    assert identity["model_digest"] == _BGE_DIGEST
    assert identity["ollama_version"] == "0.30.10"
    assert identity["input_transform_id"] == "bge-input-v2"
    runner.check(_write_capture(tmp_path, "bge-v4.json", payload))

    mutations: list[dict] = []
    for field in (
        "static_config_identity",
        "descriptor_identity",
        "canonical_model",
        "model_digest",
        "ollama_version",
        "input_transform_id",
        "pre_attestation",
        "post_attestation",
    ):
        missing = copy.deepcopy(payload)
        missing["embedding_identity"].pop(field)
        mutations.append(missing)
    drifted = copy.deepcopy(payload)
    drifted["embedding_identity"]["post_attestation"]["ollama_version"] = "0.30.11"
    mutations.append(drifted)
    mismatched = copy.deepcopy(payload)
    mismatched["embedding_identity"]["pre_attestation"][
        "embedding_identity"
    ] = "bge-ollama-v1:wrong"
    mutations.append(mismatched)
    bad_total = copy.deepcopy(payload)
    bad_total["embedding_requests"]["total"] = 12
    mutations.append(bad_total)

    for index, mutation in enumerate(mutations):
        with pytest.raises(ValueError):
            runner.check(
                _write_capture(tmp_path, f"bge-invalid-{index}.json", mutation)
            )


def test_bge_v4_rejects_coherent_superseded_v1_identity(
    tmp_path: Path,
) -> None:
    payload = _real_shaped_capture(provider="bge")
    identity = payload["embedding_identity"]
    identity["descriptor_identity"] = (
        _SUPERSEDED_BGE_V1_DESCRIPTOR_IDENTITY
    )
    identity["input_transform_id"] = "bge-input-v1"
    for phase in ("pre_attestation", "post_attestation"):
        identity[phase]["input_transform_id"] = "bge-input-v1"
        identity[phase]["embedding_identity"] = (
            _SUPERSEDED_BGE_V1_DESCRIPTOR_IDENTITY
        )

    assert identity["pre_attestation"] == identity["post_attestation"]
    assert identity["descriptor_identity"] == (
        identity["pre_attestation"]["embedding_identity"]
    )
    assert identity["input_transform_id"] == (
        identity["pre_attestation"]["input_transform_id"]
    )
    with pytest.raises(
        ValueError,
        match="BGE embedding descriptor identity mismatch",
    ):
        runner.check(
            _write_capture(tmp_path, "bge-superseded-v1.json", payload)
        )


def test_bge_v4_requires_at_least_one_recorded_embedding_request(
    tmp_path: Path,
) -> None:
    payload = _real_shaped_capture(provider="bge")
    assert payload["embedding_requests"] == {
        "redink": 4,
        "daily": 9,
        "total": 13,
    }
    runner.check(_write_capture(tmp_path, "bge-with-requests.json", payload))
    payload["embedding_requests"] = {"redink": 0, "daily": 0, "total": 0}

    with pytest.raises(ValueError) as exc_info:
        runner.check(_write_capture(tmp_path, "bge-no-requests.json", payload))
    assert str(exc_info.value) == "BGE embedding request counts are invalid"


@pytest.mark.parametrize(
    ("field", "frozen_value", "forged_value"),
    (
        ("configured_model", "bge-m3", "forged-bge-model"),
        ("canonical_model", "bge-m3:latest", "forged-bge-model:latest"),
    ),
    ids=("configured-model", "canonical-model"),
)
def test_bge_v4_rejects_frozen_model_drift_when_attestations_agree(
    tmp_path: Path,
    field: str,
    frozen_value: str,
    forged_value: str,
) -> None:
    payload = _real_shaped_capture(provider="bge")
    identity = payload["embedding_identity"]
    assert identity[field] == frozen_value
    assert all(
        identity[phase][field] == frozen_value
        for phase in ("pre_attestation", "post_attestation")
    )
    runner.check(_write_capture(tmp_path, f"bge-frozen-{field}.json", payload))
    identity[field] = forged_value
    for phase in ("pre_attestation", "post_attestation"):
        identity[phase][field] = forged_value

    with pytest.raises(ValueError) as exc_info:
        runner.check(
            _write_capture(tmp_path, f"bge-forged-{field}.json", payload)
        )
    assert str(exc_info.value) == "BGE embedding model identity mismatch"


def test_native_check_rejects_schema_v3_without_upgrading(
    tmp_path: Path,
) -> None:
    payload = _real_shaped_capture()
    payload["schema_version"] = 3
    with pytest.raises(ValueError, match="capture schema"):
        runner.check(_write_capture(tmp_path, "historical-v3.json", payload))


def test_v4_timing_uses_18_case_minima_and_nearest_rank_percentiles(
    tmp_path: Path,
) -> None:
    payload = _real_shaped_capture()
    timing = payload["timing"]
    assert set(timing) == {
        "index_seconds",
        "query_case_min_seconds",
        "query_p50_seconds",
        "query_p95_seconds",
    }
    assert len(timing["query_case_min_seconds"]) == 18
    assert timing["query_p50_seconds"] == 0.009
    assert timing["query_p95_seconds"] == 0.018
    runner.check(_write_capture(tmp_path, "timing-v4.json", payload))

    missing_case = copy.deepcopy(payload)
    missing_case["timing"]["query_case_min_seconds"].pop(
        next(iter(missing_case["cases"]))
    )
    wrong_p50 = copy.deepcopy(payload)
    wrong_p50["timing"]["query_p50_seconds"] = 0.0095
    wrong_p95 = copy.deepcopy(payload)
    wrong_p95["timing"]["query_p95_seconds"] = 0.017
    negative_index = copy.deepcopy(payload)
    negative_index["timing"]["index_seconds"]["daily"] = -1.0
    for index, invalid in enumerate(
        (missing_case, wrong_p50, wrong_p95, negative_index)
    ):
        with pytest.raises(ValueError):
            runner.check(
                _write_capture(tmp_path, f"bad-timing-{index}.json", invalid)
            )


def test_v4_check_recursively_rejects_private_payloads(
    tmp_path: Path,
) -> None:
    payload = _real_shaped_capture(provider="bge")
    runner.check(_write_capture(tmp_path, "privacy-v4.json", payload))
    private_mutations: list[dict] = []

    source = copy.deepcopy(payload)
    first_case = next(iter(source["cases"].values()))
    first_case["selected"][0]["path"] = (
        "relative/P13_RAW_SOURCE_SENTINEL.py"
    )
    private_mutations.append(source)

    query = copy.deepcopy(payload)
    raw_version = "P13_RAW_QUERY_SENTINEL"
    version_sha = hashlib.sha256(raw_version.encode("utf-8")).hexdigest()
    descriptor = (
        f"bge-ollama-v1:{_BGE_CONFIG_IDENTITY}:{_BGE_DIGEST}:"
        f"{version_sha}:bge-input-v2"
    )
    identity = query["embedding_identity"]
    identity["ollama_version"] = raw_version
    identity["descriptor_identity"] = descriptor
    for phase in ("pre_attestation", "post_attestation"):
        identity[phase]["ollama_version"] = raw_version
        identity[phase]["embedding_identity"] = descriptor
    private_mutations.append(query)

    credential = copy.deepcopy(payload)
    for phase in ("pre_attestation", "post_attestation"):
        credential["embedding_identity"][phase]["base_url"] = (
            "http://user:P13_CREDENTIAL_SENTINEL@localhost:11434"
        )
    private_mutations.append(credential)

    absolute = copy.deepcopy(payload)
    first_case = next(iter(absolute["cases"].values()))
    first_case["selected"][0]["path"] = "/Users/person/private.py"
    private_mutations.append(absolute)

    for index, invalid in enumerate(private_mutations):
        with pytest.raises(ValueError, match="capture privacy violation"):
            runner.check(
                _write_capture(tmp_path, f"private-{index}.json", invalid)
            )


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
    payload = _real_shaped_capture()
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


def test_check_rejects_v2_captures(tmp_path: Path) -> None:
    payload = _real_shaped_capture()
    payload["schema_version"] = 2
    payload.pop("embedding_identity", None)
    stale = tmp_path / "v2.json"
    stale.write_text(runner._canonical(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="capture schema"):
        runner.check(stale)


def test_embedding_config_builds_bge_and_hash_identities() -> None:
    hash_config = runner._embedding_config("hash")
    assert hash_config.embedding.provider == "hash"

    bge_config = runner._embedding_config("bge")
    assert bge_config.embedding.provider == "bge"
    assert bge_config.embedding.model == "bge-m3"
    assert bge_config.embedding.dimensions == 1024

    with pytest.raises(ValueError, match="embedding"):
        runner._embedding_config("openai")


def test_check_requires_a_known_embedding_identity(tmp_path: Path) -> None:
    payload = _real_shaped_capture()
    payload["embedding_identity"]["provider"] = "word2vec"
    bad = tmp_path / "unknown-provider.json"
    bad.write_text(runner._canonical(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="embedding identity"):
        runner.check(bad)


def test_indexed_identity_assertion_rejects_mismatch(tmp_path: Path) -> None:
    from context_search_tool.config import DEFAULT_CONFIG
    from context_search_tool.indexer import index_repository

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    index_repository(workspace, DEFAULT_CONFIG)

    # Matching identity passes silently.
    runner._assert_indexed_identity(workspace, DEFAULT_CONFIG)

    with pytest.raises(ValueError, match="indexed embedding identity"):
        runner._assert_indexed_identity(
            workspace, runner._embedding_config("bge")
        )


def test_bge_truncation_bounds_every_embedded_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import requests

    from context_search_tool.embeddings_bge import BGEEmbeddingProvider

    class Response:
        status_code = 200
        text = ""

        def __init__(self, payload: object) -> None:
            self.payload = payload

        def json(self) -> object:
            return self.payload

        def raise_for_status(self) -> None:
            return None

    class Session:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.trust_env = True

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
                            "digest": _BGE_DIGEST,
                            "details": {"embedding_length": 1024},
                        }
                    ]
                }
            )

        def post(self, url: str, **kwargs: object) -> Response:
            assert url.endswith("/api/embed")
            request = kwargs["json"]
            texts = tuple(request["input"])
            http_embed_inputs.append(texts)
            vectors = []
            for text in texts:
                vector = [0.0] * 1024
                digest = hashlib.sha256(text.encode("utf-8")).digest()
                vector[int.from_bytes(digest[:2], "big") % 1024] = 1.0
                vectors.append(vector)
            return Response({"embeddings": vectors})

    repository_root = Path(__file__).resolve().parents[1]
    evidence_files = [
        ancestor / "protected-inputs.json"
        for ancestor in (repository_root, *repository_root.parents)
        if (ancestor / "protected-inputs.json").is_file()
    ]
    pointer = repository_root / ".quality" / "p13-run-root.txt"
    if not evidence_files and pointer.is_file():
        evidence_files.append(
            Path(pointer.read_text(encoding="utf-8").strip())
            / "protected-inputs.json"
        )
    assert len(evidence_files) == 1, "frozen P13 inputs are unavailable"
    protected = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    legacy_runner = protected["acceptance_runner"]
    assert legacy_runner == {
        "path": "tests/p8_real_python_graphs_acceptance.py",
        "sha256": (
            "c768f3d5474ffe664654962fc22033af05bfaeeb4100b7afb0324b1d718a4809"
        ),
    }
    candidate_runner_path = Path(runner.__file__).resolve()
    assert candidate_runner_path == (
        repository_root / legacy_runner["path"]
    ).resolve()
    baseline_root = evidence_files[0].parent / "baseline" / "context-search-tool"
    assert runner._git(baseline_root, "rev-parse", "HEAD") == (
        "122ed052284fa488943cb4464301a391bd2e7e24"
    )
    assert hashlib.sha256(
        (baseline_root / legacy_runner["path"]).read_bytes()
    ).hexdigest() == legacy_runner["sha256"]
    sources_root = Path(protected["p8_source_root"])
    assert (sources_root / "RedInk").is_dir()
    assert (sources_root / "daily_stock_analysis").is_dir()
    for relative, expected in protected["protected_files"].items():
        if relative == legacy_runner["path"]:
            continue
        assert hashlib.sha256(
            (repository_root / relative).read_bytes()
        ).hexdigest() == expected["sha256"]
    for relative, expected in protected["p1_committed_fixtures"].items():
        assert runner._git(
            repository_root,
            "rev-parse",
            f"HEAD:{relative}",
        ) == expected["tree_oid"]

    original_embed_texts = BGEEmbeddingProvider.embed_texts
    original_class_keys = set(vars(BGEEmbeddingProvider))
    public_embed_calls: list[dict[str, object]] = []
    http_embed_inputs: list[tuple[str, ...]] = []

    def observe_embed_calls(frame, event: str, arg: object) -> None:
        if event != "call":
            return
        provider = frame.f_locals.get("self")
        if not isinstance(provider, BGEEmbeddingProvider):
            return
        current = BGEEmbeddingProvider.embed_texts
        if frame.f_code is not getattr(current, "__code__", None):
            return
        public_embed_calls.append(
            {
                "inputs": tuple(frame.f_locals["texts"]),
                "callable_is_original": current is original_embed_texts,
                "added_class_attributes": sorted(
                    set(vars(BGEEmbeddingProvider)) - original_class_keys
                ),
            }
        )

    monkeypatch.setattr(requests, "Session", Session)
    previous_profile = sys.getprofile()
    try:
        try:
            sys.setprofile(observe_embed_calls)
            output = tmp_path / "native-bge-capture.json"
            captured = runner.capture(
                repository_root,
                sources_root,
                output,
                timing_reps=1,
                embedding="bge",
            )
        finally:
            sys.setprofile(previous_profile)

        after_capture = (
            BGEEmbeddingProvider.embed_texts is original_embed_texts,
            set(vars(BGEEmbeddingProvider)) - original_class_keys,
        )
        assert captured["embedding_identity"]["provider"] == "bge"
        assert json.loads(output.read_text(encoding="utf-8")) == captured
        runner.check(output)
        after_check = (
            BGEEmbeddingProvider.embed_texts is original_embed_texts,
            set(vars(BGEEmbeddingProvider)) - original_class_keys,
        )

        assert public_embed_calls
        assert any(
            len(text) > 4000
            for call in public_embed_calls
            for text in call["inputs"]
        )
        expected_http_inputs = []
        for call in public_embed_calls:
            prepared = [
                (
                    text
                    if len(text) <= 2000
                    else text[:1500] + "\n" + text[-499:]
                )
                for text in call["inputs"]
            ]
            expected_http_inputs.extend(
                tuple(prepared[index : index + 8])
                for index in range(0, len(prepared), 8)
            )
            assert call["callable_is_original"] is True
            assert call["added_class_attributes"] == []
        assert http_embed_inputs == expected_http_inputs
        assert all(
            len(text) <= 2000
            for request in http_embed_inputs
            for text in request
        )
        assert after_capture == (True, set())
        assert after_check == (True, set())
    finally:
        sys.setprofile(previous_profile)
        BGEEmbeddingProvider.embed_texts = original_embed_texts
        for name in set(vars(BGEEmbeddingProvider)) - original_class_keys:
            delattr(BGEEmbeddingProvider, name)
