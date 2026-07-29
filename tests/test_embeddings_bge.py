import numpy as np
import pytest
import requests
from unittest.mock import Mock, call, patch

from context_search_tool.config import EmbeddingConfig
from context_search_tool.embeddings_bge import BGEEmbeddingProvider


_DIGEST_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_VERSION_A = "0.30.10"
_VERSION_B = "0.30.11"
_DESCRIPTOR_LITERAL = (
    "bge-ollama-v1:"
    "a31c280ece569f71b682328fbeb5c2fef9c85cca0e42acf7425724d134fd80d8:"
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v1"
)
_DESCRIPTOR_EXPLICIT_TAG_LITERAL = (
    "bge-ollama-v1:"
    "f98644e6e7a650147c9acb84f3809db5e12b95ea91fbd65a0fa8492a0cb2f58b:"
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v1"
)
_DESCRIPTOR_DIGEST_B_LITERAL = (
    "bge-ollama-v1:"
    "a31c280ece569f71b682328fbeb5c2fef9c85cca0e42acf7425724d134fd80d8:"
    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v1"
)
_DESCRIPTOR_VERSION_B_LITERAL = (
    "bge-ollama-v1:"
    "a31c280ece569f71b682328fbeb5c2fef9c85cca0e42acf7425724d134fd80d8:"
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:"
    "e8b0cd5b6a434c25fc264f14215453212e8a2a9f2ee92853edcab28cf3ba369a:"
    "bge-input-v1"
)
_EXPECTED_RUNTIME_A = {
    "configured_model": "bge-m3",
    "canonical_model": "bge-m3:latest",
    "model_digest": _DIGEST_A,
    "ollama_version": _VERSION_A,
    "base_url": "http://localhost:11434",
    "dimensions": 3,
    "input_transform_id": "bge-input-v1",
    "embedding_identity": _DESCRIPTOR_LITERAL,
}


def _config(
    *,
    model: str = "bge-m3",
    dimensions: int = 3,
    base_url: str | None = None,
) -> EmbeddingConfig:
    return EmbeddingConfig(
        provider="bge",
        model=model,
        dimensions=dimensions,
        base_url=base_url,
    )


def _response(
    payload: object,
    *,
    status_code: int = 200,
    json_error: Exception | None = None,
) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    error_text = (
        payload.get("error")
        if isinstance(payload, dict) and isinstance(payload.get("error"), str)
        else "mocked Ollama response"
    )
    response.text = error_text
    if json_error is None:
        response.json.return_value = payload
    else:
        response.json.side_effect = json_error
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(
            f"{status_code} {error_text}",
            response=response,
        )
    else:
        response.raise_for_status.return_value = None
    return response


def _version_response(
    version: object = _VERSION_A,
    *,
    status_code: int = 200,
) -> Mock:
    return _response({"version": version}, status_code=status_code)


def _tags_response(
    *,
    digest: object = _DIGEST_A,
    name: object = "bge-m3:latest",
    models: object | None = None,
    status_code: int = 200,
) -> Mock:
    payload_models = (
        [{"name": name, "digest": digest}] if models is None else models
    )
    return _response({"models": payload_models}, status_code=status_code)


def _session(
    *,
    get_responses: list[Mock] | None = None,
    embedding_batches: list[list[object]] | None = None,
    post_responses: list[Mock | Exception] | None = None,
) -> Mock:
    session = Mock(spec=requests.Session)
    session.headers = {}
    session.trust_env = True
    session.proxies = {"https": "http://proxy.example.test"}
    session.get.side_effect = get_responses or [
        _version_response(),
        _tags_response(),
    ]
    if post_responses is not None:
        session.post.side_effect = post_responses
    else:
        batches = embedding_batches or [[[1.0, 0.0, 0.0]]]
        session.post.side_effect = [
            _response({"embeddings": batch}) for batch in batches
        ]
    return session


def _assert_error_code(error: pytest.ExceptionInfo[ValueError], code: str) -> None:
    assert isinstance(error.value, ValueError)
    assert getattr(error.value, "code", None) == code


def test_bge_provider_can_be_imported() -> None:
    from context_search_tool.embeddings_bge import BGEEmbeddingProvider


def test_bge_provider_initializes_with_model_name() -> None:
    """Unit test - no network calls."""
    config = _config(dimensions=1024)
    session = _session()

    provider = BGEEmbeddingProvider(config, session=session)

    assert provider.config.model == "bge-m3"
    assert provider.config.dimensions == 1024
    assert provider.fingerprint() == {
        "provider": "bge",
        "model": "bge-m3",
        "dimensions": 1024,
        "backend": "ollama",
    }
    session.get.assert_not_called()
    session.post.assert_not_called()


def test_bge_provider_default_session_bypasses_environment_proxies() -> None:
    config = _config(dimensions=1024)
    created_session = requests.Session()
    created_session.trust_env = True

    with patch(
        "context_search_tool.embeddings_bge.requests.Session",
        return_value=created_session,
    ):
        BGEEmbeddingProvider(config)

    assert created_session.trust_env is False


def test_bge_provider_embeds_text_with_mock_response() -> None:
    """Unit test with mocked Ollama response."""
    config = _config()
    mock_session = _session(embedding_batches=[[[0.6, 0.0, 0.8]]])

    provider = BGEEmbeddingProvider(config, session=mock_session)
    vectors = provider.embed_texts(["hello"])

    assert len(vectors) == 1
    assert vectors[0].shape == (3,)
    assert vectors[0].dtype == np.float32
    assert vectors[0].tolist() == pytest.approx([0.6, 0.0, 0.8])
    assert float(np.linalg.norm(vectors[0])) == pytest.approx(1.0)
    assert mock_session.get.call_args_list == [
        call("http://localhost:11434/api/version", timeout=5.0),
        call("http://localhost:11434/api/tags", timeout=5.0),
    ]
    mock_session.post.assert_called_once_with(
        "http://localhost:11434/api/embed",
        json={"model": "bge-m3", "input": ["hello"], "truncate": False},
        timeout=60.0,
    )


def test_bge_provider_splits_large_embedding_requests() -> None:
    config = _config()
    first_batch = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ]
    second_batch = [[0.0, 0.0, 1.0]]
    mock_session = _session(embedding_batches=[first_batch, second_batch])
    texts = [f"text-{index}" for index in range(9)]

    provider = BGEEmbeddingProvider(config, session=mock_session)
    vectors = provider.embed_texts(texts)

    assert [vector.tolist() for vector in vectors] == first_batch + second_batch
    assert mock_session.post.call_count == 2
    assert [request.kwargs["json"]["input"] for request in mock_session.post.call_args_list] == [
        texts[:8],
        texts[8:],
    ]


def test_bge_provider_rejects_invalid_dimensions() -> None:
    """Unit test - dimension mismatch detection."""
    config = _config(dimensions=512)
    mock_session = _session(embedding_batches=[[[0.5] * 1024]])

    provider = BGEEmbeddingProvider(config, session=mock_session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["test"])

    _assert_error_code(error, "bge_response_invalid")


def test_bge_provider_handles_missing_embedding_field() -> None:
    """Unit test - malformed response handling."""
    config = _config()
    mock_session = _session(post_responses=[_response({})])

    provider = BGEEmbeddingProvider(config, session=mock_session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["test"])

    _assert_error_code(error, "bge_response_invalid")


@pytest.mark.parametrize("base_url", [None, ""], ids=["none", "empty"])
def test_bge_provider_uses_default_root_for_empty_base_url(
    base_url: str | None,
) -> None:
    session = _session()
    provider = BGEEmbeddingProvider(
        _config(base_url=base_url),
        session=session,
    )

    provider.embed_texts(["hello"])

    assert [request.args[0] for request in session.get.call_args_list] == [
        "http://localhost:11434/api/version",
        "http://localhost:11434/api/tags",
    ]
    assert session.post.call_args.args[0] == "http://localhost:11434/api/embed"


def test_bge_provider_normalizes_custom_base_url_for_all_endpoints() -> None:
    session = _session()
    provider = BGEEmbeddingProvider(
        _config(base_url="https://ollama.example.test/root///"),
        session=session,
    )

    provider.embed_texts(["hello"])

    assert [request.args[0] for request in session.get.call_args_list] == [
        "https://ollama.example.test/root/api/version",
        "https://ollama.example.test/root/api/tags",
    ]
    assert (
        session.post.call_args.args[0]
        == "https://ollama.example.test/root/api/embed"
    )


def test_bge_provider_uses_custom_root_for_preflight_and_forced_postflight() -> None:
    session = _session(
        get_responses=[
            _version_response(),
            _tags_response(),
            _version_response(),
            _tags_response(),
        ]
    )
    provider = BGEEmbeddingProvider(
        _config(base_url="https://ollama.example.test/root///"),
        session=session,
    )

    provider.runtime_fingerprint()
    provider.assert_runtime_unchanged()

    assert session.get.call_args_list == [
        call("https://ollama.example.test/root/api/version", timeout=5.0),
        call("https://ollama.example.test/root/api/tags", timeout=5.0),
        call("https://ollama.example.test/root/api/version", timeout=5.0),
        call("https://ollama.example.test/root/api/tags", timeout=5.0),
    ]


def test_bge_provider_does_not_mutate_injected_session_proxy_settings() -> None:
    session = requests.Session()
    session.trust_env = True
    session.proxies = {
        "http": "http://proxy.example.test",
        "https": "https://proxy.example.test",
    }
    expected_proxies = dict(session.proxies)

    BGEEmbeddingProvider(_config(), session=session)

    assert session.trust_env is True
    assert session.proxies == expected_proxies
    assert session.headers["Content-Type"] == "application/json"


@pytest.mark.parametrize(
    ("stage", "failure", "expected_gets", "expected_posts", "expected_code"),
    [
        (
            "version",
            requests.ConnectionError("connection failed"),
            1,
            0,
            "bge_unavailable",
        ),
        (
            "embed",
            requests.Timeout("request timed out"),
            2,
            1,
            "bge_unavailable",
        ),
        (
            "response",
            _response({"error": "service busy"}, status_code=503),
            2,
            1,
            "bge_request_rejected",
        ),
    ],
    ids=["version-connection", "embed-timeout", "embed-http-response"],
)
def test_bge_provider_does_not_retry_failed_requests(
    stage: str,
    failure: Exception | Mock,
    expected_gets: int,
    expected_posts: int,
    expected_code: str,
) -> None:
    if stage == "version":
        session = _session(
            get_responses=[
                failure,
                _tags_response(),
            ]
        )
    else:
        session = _session(post_responses=[failure])
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, expected_code)
    assert session.get.call_count == expected_gets
    assert session.post.call_count == expected_posts


def test_bge_provider_resolves_untagged_model_only_to_latest() -> None:
    models = [
        {"name": "bge-m3:v1", "digest": _DIGEST_B},
        {"name": "bge-m3:latest", "digest": _DIGEST_A},
        {"name": "bge-m3:latest-extra", "digest": _DIGEST_B},
    ]
    session = _session(
        get_responses=[
            _version_response(),
            _tags_response(models=models),
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    runtime = provider.runtime_fingerprint()

    assert runtime["configured_model"] == "bge-m3"
    assert runtime["canonical_model"] == "bge-m3:latest"
    assert runtime["model_digest"] == _DIGEST_A


def test_bge_provider_resolves_explicit_tag_only_by_exact_name() -> None:
    models = [
        {"name": "bge-m3:latest", "digest": _DIGEST_A},
        {"name": "bge-m3:v1", "digest": _DIGEST_B},
        {"name": "bge-m3:v1-extra", "digest": _DIGEST_A},
    ]
    session = _session(
        get_responses=[
            _version_response(),
            _tags_response(models=models),
        ]
    )
    provider = BGEEmbeddingProvider(
        _config(model="bge-m3:v1"),
        session=session,
    )

    runtime = provider.runtime_fingerprint()

    assert runtime["configured_model"] == "bge-m3:v1"
    assert runtime["canonical_model"] == "bge-m3:v1"
    assert runtime["model_digest"] == _DIGEST_B
    assert runtime["embedding_identity"] == (
        "bge-ollama-v1:"
        "f98644e6e7a650147c9acb84f3809db5e12b95ea91fbd65a0fa8492a0cb2f58b:"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb:"
        "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
        "bge-input-v1"
    )


def test_bge_descriptor_identity_changes_with_static_model_config() -> None:
    session = _session(
        get_responses=[
            _version_response(),
            _tags_response(name="bge-m3:v1"),
        ]
    )
    provider = BGEEmbeddingProvider(
        _config(model="bge-m3:v1"),
        session=session,
    )

    runtime = provider.runtime_fingerprint()

    assert runtime["canonical_model"] == "bge-m3:v1"
    assert runtime["embedding_identity"] == _DESCRIPTOR_EXPLICIT_TAG_LITERAL


def test_bge_descriptor_identity_changes_with_model_digest() -> None:
    session = _session(
        get_responses=[
            _version_response(),
            _tags_response(digest=_DIGEST_B),
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    runtime = provider.runtime_fingerprint()

    assert runtime["model_digest"] == _DIGEST_B
    assert runtime["embedding_identity"] == _DESCRIPTOR_DIGEST_B_LITERAL


def test_bge_descriptor_identity_changes_with_raw_version() -> None:
    session = _session(
        get_responses=[
            _version_response(_VERSION_B),
            _tags_response(),
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    runtime = provider.runtime_fingerprint()

    assert runtime["ollama_version"] == _VERSION_B
    assert runtime["embedding_identity"] == _DESCRIPTOR_VERSION_B_LITERAL


@pytest.mark.parametrize(
    "models",
    [
        [],
        [{"name": "bge-m3:latest-extra", "digest": _DIGEST_A}],
        [
            {"name": "bge-m3:latest", "digest": _DIGEST_A},
            {"name": "bge-m3:latest", "digest": _DIGEST_B},
        ],
    ],
    ids=["zero", "prefix-only", "duplicate-exact"],
)
def test_bge_provider_rejects_non_exact_or_ambiguous_model_matches(
    models: list[dict[str, object]],
) -> None:
    session = _session(
        get_responses=[
            _version_response(),
            _tags_response(models=models),
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.runtime_fingerprint()

    _assert_error_code(error, "bge_model_unavailable")


@pytest.mark.parametrize(
    "digest",
    [
        "a" * 63,
        "a" * 65,
        "g" * 64,
        "A" * 64,
        "",
        None,
        7,
    ],
    ids=[
        "short",
        "long",
        "non-hex",
        "uppercase",
        "empty",
        "none",
        "non-string",
    ],
)
def test_bge_provider_rejects_invalid_model_digest(digest: object) -> None:
    session = _session(
        get_responses=[
            _version_response(),
            _tags_response(digest=digest),
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.runtime_fingerprint()

    _assert_error_code(error, "bge_model_unavailable")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"models": None},
        {"models": {}},
    ],
    ids=["missing", "none", "mapping"],
)
def test_bge_provider_rejects_missing_models_list(payload: object) -> None:
    session = _session(
        get_responses=[
            _version_response(),
            _response(payload),
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.runtime_fingerprint()

    _assert_error_code(error, "bge_unavailable")


@pytest.mark.parametrize(
    "response",
    [
        _response([]),
        _response({}),
        _version_response(""),
        _version_response("   "),
        _version_response(30),
        _response(
            {},
            json_error=ValueError("invalid version JSON RESPONSE_BODY_SENTINEL_P13"),
        ),
    ],
    ids=["non-object", "missing", "empty", "whitespace", "non-string", "json"],
)
def test_bge_provider_rejects_invalid_preflight_version(response: Mock) -> None:
    session = _session(
        get_responses=[
            response,
            _tags_response(),
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.runtime_fingerprint()

    _assert_error_code(error, "bge_unavailable")


@pytest.mark.parametrize(
    "response",
    [
        _response([]),
        _response(
            {},
            json_error=ValueError("invalid tags JSON RESPONSE_BODY_SENTINEL_P13"),
        ),
        _response({"error": "tags failed"}, status_code=503),
    ],
    ids=["non-object", "json", "http"],
)
def test_bge_provider_rejects_invalid_tags_transport(response: Mock) -> None:
    session = _session(
        get_responses=[
            _version_response(),
            response,
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.runtime_fingerprint()

    _assert_error_code(error, "bge_unavailable")


def test_bge_provider_runtime_fingerprint_matches_literal() -> None:
    session = _session()
    provider = BGEEmbeddingProvider(_config(), session=session)

    runtime = provider.runtime_fingerprint()

    assert runtime == _EXPECTED_RUNTIME_A


def test_bge_provider_runtime_fingerprint_caches_preflight() -> None:
    session = _session()
    provider = BGEEmbeddingProvider(_config(), session=session)

    provider.runtime_fingerprint()
    provider.runtime_fingerprint()

    assert session.get.call_args_list == [
        call("http://localhost:11434/api/version", timeout=5.0),
        call("http://localhost:11434/api/tags", timeout=5.0),
    ]


def test_bge_provider_runtime_fingerprint_returns_independent_dicts() -> None:
    session = _session()
    provider = BGEEmbeddingProvider(_config(), session=session)

    first = provider.runtime_fingerprint()
    second = provider.runtime_fingerprint()
    first["model_digest"] = _DIGEST_B

    assert second == _EXPECTED_RUNTIME_A
    assert first is not second


def test_bge_provider_preflight_runs_once_across_embed_batches() -> None:
    embeddings = [
        [[1.0, 0.0, 0.0] for _ in range(8)],
        [[0.0, 1.0, 0.0] for _ in range(8)],
        [[0.0, 0.0, 1.0]],
    ]
    session = _session(embedding_batches=embeddings)
    provider = BGEEmbeddingProvider(_config(), session=session)

    vectors = provider.embed_texts([f"text-{index}" for index in range(17)])

    assert len(vectors) == 17
    assert session.get.call_count == 2
    assert session.post.call_count == 3


def test_bge_provider_assert_runtime_unchanged_bypasses_cache() -> None:
    session = _session(
        get_responses=[
            _version_response(),
            _tags_response(),
            _version_response(),
            _tags_response(),
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    initial = provider.runtime_fingerprint()
    postflight = provider.assert_runtime_unchanged()
    cached = provider.runtime_fingerprint()

    assert initial == _EXPECTED_RUNTIME_A
    assert postflight == _EXPECTED_RUNTIME_A
    assert cached == _EXPECTED_RUNTIME_A
    assert postflight is not initial
    assert cached is not postflight
    assert session.get.call_count == 4


@pytest.mark.parametrize(
    "fresh_responses",
    [
        [
            _version_response(),
            _tags_response(digest=_DIGEST_B),
        ],
        [
            _version_response(_VERSION_B),
            _tags_response(),
        ],
    ],
    ids=["digest", "version"],
)
def test_bge_provider_assert_runtime_unchanged_rejects_runtime_drift(
    fresh_responses: list[Mock],
) -> None:
    session = _session(
        get_responses=[
            _version_response(),
            _tags_response(),
            *fresh_responses,
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)
    assert provider.runtime_fingerprint() == _EXPECTED_RUNTIME_A

    with pytest.raises(ValueError) as error:
        provider.assert_runtime_unchanged()

    _assert_error_code(error, "bge_runtime_mismatch")
    assert provider.runtime_fingerprint() == _EXPECTED_RUNTIME_A
    assert session.get.call_count == 4


@pytest.mark.parametrize(
    ("fresh_responses", "expected_code"),
    [
        (
            [
                _response({"error": "version failed"}, status_code=503),
                _tags_response(),
            ],
            "bge_unavailable",
        ),
        (
            [
                _version_response(),
                _response({}),
            ],
            "bge_unavailable",
        ),
        (
            [
                _version_response(),
                _tags_response(models=[]),
            ],
            "bge_model_unavailable",
        ),
        (
            [
                _version_response(),
                _tags_response(digest="A" * 64),
            ],
            "bge_model_unavailable",
        ),
    ],
    ids=["transport", "missing-models", "model-absent", "invalid-digest"],
)
def test_bge_provider_postflight_preserves_attestation_error_taxonomy(
    fresh_responses: list[Mock],
    expected_code: str,
) -> None:
    session = _session(
        get_responses=[
            _version_response(),
            _tags_response(),
            *fresh_responses,
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)
    assert provider.runtime_fingerprint() == _EXPECTED_RUNTIME_A

    with pytest.raises(ValueError) as error:
        provider.assert_runtime_unchanged()

    _assert_error_code(error, expected_code)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "x" * 3999,
        "x" * 4000,
    ],
    ids=["zero", "3999", "4000"],
)
def test_bge_provider_preserves_text_through_4000_code_points(text: str) -> None:
    session = _session()
    provider = BGEEmbeddingProvider(_config(), session=session)

    provider.embed_texts([text])

    assert session.post.call_args.kwargs["json"]["input"] == [text]


def test_bge_provider_applies_exact_head_tail_transform_at_4001() -> None:
    text = ("H" * 3000) + "XY" + ("T" * 999)
    expected = ("H" * 3000) + "\n" + ("T" * 999)
    session = _session()
    provider = BGEEmbeddingProvider(_config(), session=session)

    provider.embed_texts([text])

    prepared = session.post.call_args.kwargs["json"]["input"][0]
    assert prepared == expected
    assert len(prepared) == 4000


def test_bge_provider_counts_dense_cjk_by_code_point() -> None:
    text = "界" * 4001
    expected = ("界" * 3000) + "\n" + ("界" * 999)
    session = _session()
    provider = BGEEmbeddingProvider(_config(), session=session)

    provider.embed_texts([text])

    prepared = session.post.call_args.kwargs["json"]["input"][0]
    assert prepared == expected
    assert len(prepared) == 4000


def test_bge_provider_preserves_tail_and_removes_middle_sentinel() -> None:
    head_sentinel = "HEAD_SENTINEL_P13"
    middle_sentinel = "MIDDLE_SENTINEL_P13"
    tail_sentinel = "TAIL_SENTINEL_P13"
    head = head_sentinel + ("h" * (3000 - len(head_sentinel)))
    middle = middle_sentinel + ("m" * 1000)
    tail = ("t" * (999 - len(tail_sentinel))) + tail_sentinel
    session = _session()
    provider = BGEEmbeddingProvider(_config(), session=session)

    provider.embed_texts([head + middle + tail])

    prepared = session.post.call_args.kwargs["json"]["input"][0]
    assert head_sentinel in prepared
    assert tail_sentinel in prepared
    assert middle_sentinel not in prepared


def test_bge_provider_does_not_mutate_input_list() -> None:
    long_text = ("A" * 3000) + "REMOVED" + ("Z" * 999)
    texts = [long_text, "short"]
    original = list(texts)
    session = _session(
        embedding_batches=[
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    provider.embed_texts(texts)

    assert texts == original


def test_bge_provider_preserves_input_order() -> None:
    long_text = ("A" * 3000) + "REMOVED" + ("Z" * 999)
    expected_long = ("A" * 3000) + "\n" + ("Z" * 999)
    session = _session(
        embedding_batches=[
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    provider.embed_texts([long_text, "short"])

    assert session.post.call_args.kwargs["json"]["input"] == [
        expected_long,
        "short",
    ]


def test_bge_provider_empty_input_performs_zero_http() -> None:
    session = _session()
    provider = BGEEmbeddingProvider(_config(), session=session)

    assert provider.embed_texts([]) == []
    session.get.assert_not_called()
    session.post.assert_not_called()


def test_bge_provider_keeps_eight_maximum_inputs_in_one_request() -> None:
    texts = [str(index) + ("x" * 3999) for index in range(8)]
    embeddings = [[1.0, 0.0, 0.0] for _ in range(8)]
    session = _session(embedding_batches=[embeddings])
    provider = BGEEmbeddingProvider(_config(), session=session)

    vectors = provider.embed_texts(texts)

    assert len(vectors) == 8
    assert session.post.call_count == 1
    assert session.post.call_args.kwargs["json"]["input"] == texts


def test_bge_provider_batches_seventeen_inputs_as_eight_eight_one() -> None:
    texts = [f"text-{index}" for index in range(17)]
    session = _session(
        embedding_batches=[
            [[1.0, 0.0, 0.0] for _ in range(8)],
            [[0.0, 1.0, 0.0] for _ in range(8)],
            [[0.0, 0.0, 1.0]],
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    vectors = provider.embed_texts(texts)

    assert len(vectors) == 17
    assert [
        request.kwargs["json"]["input"]
        for request in session.post.call_args_list
    ] == [
        texts[:8],
        texts[8:16],
        texts[16:],
    ]


def test_bge_provider_returns_float32_unit_vectors() -> None:
    session = _session(embedding_batches=[[[3.0, 4.0, 0.0]]])
    provider = BGEEmbeddingProvider(_config(), session=session)

    vectors = provider.embed_texts(["hello"])

    assert len(vectors) == 1
    assert vectors[0].dtype == np.float32
    assert vectors[0].tolist() == pytest.approx([0.6, 0.8, 0.0])
    assert float(np.linalg.norm(vectors[0])) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "not-an-object",
    ],
    ids=["none", "list", "string"],
)
def test_bge_provider_rejects_non_object_response_root(payload: object) -> None:
    session = _session(post_responses=[_response(payload)])
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


@pytest.mark.parametrize(
    "payload",
    [
        {"embeddings": None},
        {"embeddings": {}},
        {"embeddings": "not-a-list"},
    ],
    ids=["none", "mapping", "string"],
)
def test_bge_provider_requires_embeddings_list(payload: object) -> None:
    session = _session(post_responses=[_response(payload)])
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


@pytest.mark.parametrize(
    "embeddings",
    [
        [],
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
    ],
    ids=["zero", "two"],
)
def test_bge_provider_rejects_embedding_count_mismatch(
    embeddings: list[object],
) -> None:
    session = _session(post_responses=[_response({"embeddings": embeddings})])
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


@pytest.mark.parametrize(
    "embedding",
    [
        None,
        1.0,
        [[1.0, 0.0, 0.0]],
    ],
    ids=["non-sequence", "scalar", "two-dimensional"],
)
def test_bge_provider_rejects_invalid_embedding_shape(
    embedding: object,
) -> None:
    session = _session(
        post_responses=[_response({"embeddings": [embedding]})]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


def test_bge_provider_rejects_nonnumeric_embedding() -> None:
    session = _session(
        post_responses=[
            _response({"embeddings": [["not-a-number", 0.0, 1.0]]})
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


def test_bge_provider_rejects_numeric_string_embedding_values() -> None:
    session = _session(
        post_responses=[_response({"embeddings": [["1", "0", "0"]]})]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


def test_bge_provider_rejects_boolean_embedding_values() -> None:
    session = _session(
        post_responses=[
            _response({"embeddings": [[True, False, False]]})
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
    ids=["nan", "positive-inf", "negative-inf"],
)
def test_bge_provider_rejects_nonfinite_embedding_values(value: float) -> None:
    session = _session(
        post_responses=[
            _response({"embeddings": [[value, 0.0, 1.0]]})
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


def test_bge_provider_rejects_zero_vector() -> None:
    session = _session(embedding_batches=[[[0.0, 0.0, 0.0]]])
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


def test_bge_provider_rejects_nonfinite_float32_norm() -> None:
    session = _session(embedding_batches=[[[3.4e38, 3.4e38, 0.0]]])
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


def test_bge_provider_fails_whole_call_after_late_invalid_batch() -> None:
    session = _session(
        embedding_batches=[
            [[1.0, 0.0, 0.0] for _ in range(8)],
            [[0.0, 0.0, 0.0]],
        ]
    )
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts([f"text-{index}" for index in range(9)])

    _assert_error_code(error, "bge_response_invalid")
    assert session.post.call_count == 2


def test_bge_provider_maps_embed_json_decode_to_response_invalid() -> None:
    response = _response(
        {},
        json_error=ValueError("invalid embed JSON RESPONSE_BODY_SENTINEL_P13"),
    )
    session = _session(post_responses=[response])
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_response_invalid")


@pytest.mark.parametrize(
    ("status_code", "error_text", "expected_code"),
    [
        (
            400,
            "INPUT   LENGTH\nEXCEEDS THE CONTEXT LENGTH: rejected",
            "bge_context_limit",
        ),
        (
            400,
            "prefix Input Length Exceeds The Context Window suffix",
            "bge_context_limit",
        ),
        (
            400,
            "context length exceeded",
            "bge_request_rejected",
        ),
        (
            400,
            "input length exceeds model context length",
            "bge_request_rejected",
        ),
        (
            413,
            "input length exceeds the context length",
            "bge_request_rejected",
        ),
    ],
    ids=[
        "context-length-normalized",
        "context-window-casefold",
        "different-order",
        "missing-the",
        "non-400",
    ],
)
def test_bge_provider_classifies_only_frozen_context_limit_phrases(
    status_code: int,
    error_text: str,
    expected_code: str,
) -> None:
    response = _response({"error": error_text}, status_code=status_code)
    session = _session(post_responses=[response])
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["SOURCE_QUERY_SENTINEL_P13"])

    _assert_error_code(error, expected_code)


@pytest.mark.parametrize(
    "status_code",
    [400, 401, 429, 500],
    ids=["generic-400", "unauthorized", "rate-limit", "server-error"],
)
def test_bge_provider_maps_other_embed_http_errors_to_request_rejected(
    status_code: int,
) -> None:
    response = _response(
        {"error": "ordinary embedding rejection"},
        status_code=status_code,
    )
    session = _session(post_responses=[response])
    provider = BGEEmbeddingProvider(_config(), session=session)

    with pytest.raises(ValueError) as error:
        provider.embed_texts(["hello"])

    _assert_error_code(error, "bge_request_rejected")
    assert session.post.call_count == 1


@pytest.mark.parametrize(
    "stage",
    [
        "version-connection",
        "tags-timeout",
        "embed-connection",
        "embed-timeout",
        "version-json-decode",
        "tags-json-decode",
    ],
)
def test_bge_provider_transport_and_preflight_decode_errors_are_private(
    stage: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_sentinel = "SOURCE_QUERY_SENTINEL_P13"
    response_sentinel = "RESPONSE_BODY_SENTINEL_P13"
    credential_sentinel = "user:password"
    path_sentinel = "/private/tmp/secret-repo/file.py"
    leaky_message = (
        f"{source_sentinel} {response_sentinel} "
        f"{credential_sentinel} {path_sentinel}"
    )
    if stage == "version-connection":
        session = _session(
            get_responses=[requests.ConnectionError(leaky_message)]
        )
    elif stage == "tags-timeout":
        session = _session(
            get_responses=[
                _version_response(),
                requests.Timeout(leaky_message),
            ]
        )
    elif stage == "embed-connection":
        session = _session(
            post_responses=[requests.ConnectionError(leaky_message)]
        )
    elif stage == "embed-timeout":
        session = _session(
            post_responses=[requests.Timeout(leaky_message)]
        )
    elif stage == "version-json-decode":
        session = _session(
            get_responses=[
                _response({}, json_error=ValueError(leaky_message)),
            ]
        )
    else:
        session = _session(
            get_responses=[
                _version_response(),
                _response({}, json_error=ValueError(leaky_message)),
            ]
        )
    provider = BGEEmbeddingProvider(
        _config(base_url="https://user:password@ollama.example.test/root"),
        session=session,
    )

    with pytest.raises(ValueError) as error:
        provider.embed_texts([source_sentinel])

    _assert_error_code(error, "bge_unavailable")
    rendered = f"{error.value!s}\n{error.value!r}\n{caplog.text}"
    assert source_sentinel not in rendered
    assert response_sentinel not in rendered
    assert credential_sentinel not in rendered
    assert path_sentinel not in rendered


@pytest.mark.parametrize(
    "stage",
    [
        "preflight-http",
        "embed-context",
        "embed-http",
        "embed-json",
    ],
)
def test_bge_provider_errors_do_not_leak_private_values(
    stage: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_sentinel = "SOURCE_QUERY_SENTINEL_P13"
    response_sentinel = "RESPONSE_BODY_SENTINEL_P13"
    credential_sentinel = "user:password"
    path_sentinel = "/private/tmp/secret-repo/file.py"
    response_text = f"{response_sentinel} {path_sentinel}"
    if stage == "preflight-http":
        session = _session(
            get_responses=[
                _response(
                    {"error": response_text},
                    status_code=503,
                ),
                _tags_response(),
            ]
        )
    elif stage == "embed-context":
        session = _session(
            post_responses=[
                _response(
                    {
                        "error": (
                            "input length exceeds the context length "
                            f"{response_text}"
                        )
                    },
                    status_code=400,
                )
            ]
        )
    elif stage == "embed-http":
        session = _session(
            post_responses=[
                _response(
                    {"error": response_text},
                    status_code=500,
                )
            ]
        )
    else:
        session = _session(
            post_responses=[
                _response(
                    {},
                    json_error=ValueError(response_text),
                )
            ]
        )
    provider = BGEEmbeddingProvider(
        _config(base_url="https://user:password@ollama.example.test/root"),
        session=session,
    )

    with pytest.raises(ValueError) as error:
        provider.embed_texts([source_sentinel])

    expected_codes = {
        "preflight-http": "bge_unavailable",
        "embed-context": "bge_context_limit",
        "embed-http": "bge_request_rejected",
        "embed-json": "bge_response_invalid",
    }
    _assert_error_code(error, expected_codes[stage])
    rendered = f"{error.value!s}\n{error.value!r}\n{caplog.text}"
    assert source_sentinel not in rendered
    assert response_sentinel not in rendered
    assert credential_sentinel not in rendered
    assert path_sentinel not in rendered


@pytest.mark.slow
@pytest.mark.integration
def test_bge_provider_real_ollama_service() -> None:
    """Integration test - requires Ollama running with bge-m3 model.

    Skip by default: pytest -m "not slow"
    Run explicitly: pytest -m integration
    """
    config = _config(dimensions=1024)
    provider = BGEEmbeddingProvider(config)
    runtime = provider.runtime_fingerprint()
    texts = [
        "hello world",
        "测试查询",
        "mixed API 接口 timeout",
        "x" * 4000,
        "界" * 6924,
    ]

    vectors = provider.embed_texts(texts)
    postflight = provider.assert_runtime_unchanged()

    assert runtime["canonical_model"] == "bge-m3:latest"
    assert postflight == runtime
    assert len(vectors) == len(texts)
    for vector in vectors:
        assert vector.shape == (1024,)
        assert vector.dtype == np.float32
        assert float(np.linalg.norm(vector)) == pytest.approx(1.0, abs=1e-5)


@pytest.mark.slow
@pytest.mark.integration
def test_bge_provider_real_ollama_singleton_batch_equivalence() -> None:
    provider = BGEEmbeddingProvider(_config(dimensions=1024))
    texts = [
        "hello world",
        "测试查询",
        "mixed API 接口 timeout",
        "x" * 4000,
        "界" * 6924,
        "tail lexical sentinel",
        "class RuntimeIdentity:",
        "where is the query embedding validated",
    ]
    provider.runtime_fingerprint()

    singleton_vectors = [
        provider.embed_texts([text])[0]
        for text in texts
    ]
    batch_vectors = provider.embed_texts(texts)
    provider.assert_runtime_unchanged()

    for singleton, batched in zip(
        singleton_vectors,
        batch_vectors,
        strict=True,
    ):
        assert float(np.dot(singleton, batched)) >= 0.999999
        assert float(np.max(np.abs(singleton - batched))) <= 1e-5
