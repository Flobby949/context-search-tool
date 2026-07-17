from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from shutil import copytree
import socket

import requests

import context_search_tool.indexer as indexer
from context_search_tool.context_pack import (
    build_context_pack,
    resolve_context_pack_options,
)
from context_search_tool.context_pack.roles import normalize_candidates
from context_search_tool.embeddings import HashEmbeddingProvider
from context_search_tool.formatters import query_payload, trace_payload
from context_search_tool.indexer import index_repository
from context_search_tool.mcp_tools import (
    _query_payload,
    context_search_context_tool,
    context_search_explain_tool,
    context_search_explore_tool,
    context_search_query_tool,
    context_search_trace_tool,
)
from context_search_tool.models import RetrievalResult
from context_search_tool.retrieval import (
    QueryBundle,
    evidence_anchor_top_k,
    query_repository,
    trace_repository,
)
from context_search_tool.retrieval_core import candidates
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.config import DEFAULT_CONFIG


def test_mapper_role_hint_is_private_but_survives_normalization() -> None:
    result = RetrievalResult(
        file_path=Path("mappers/OrderMapper.xml"),
        start_line=1,
        end_line=1,
        content="<mapper/>",
        score=1.0,
        score_parts={},
        reasons=[],
        followup_keywords=[],
        _context_role_hint="mybatis_repository",
    )

    replaced = replace(result)
    deep_copied = deepcopy(result)
    [candidate] = normalize_candidates(QueryBundle("mapper", [], [replaced], []))

    assert (candidate.group, candidate.role, candidate.classification_basis) == (
        "implementations",
        "repository",
        "content",
    )
    assert replaced._context_role_hint == "mybatis_repository"
    assert deep_copied._context_role_hint == "mybatis_repository"
    assert result == replace(result, _context_role_hint=None)
    assert "context_role_hint" not in repr(result)
    assert "_context_role_hint" not in _query_payload(
        QueryBundle("mapper", [], [result], [])
    )["results"][0]


def test_real_mapper_role_hint_is_ready_only_and_stays_private(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    copytree(
        Path(__file__).parent / "fixtures" / "p5-language-graphs" / "java-spring",
        repo,
    )
    rejected_path = Path("src/main/resources/mappers/RejectedMapper.xml")
    (repo / rejected_path).write_text(
        '<root namespace="com.example.order.RejectedMapper">\n'
        '  <select id="find">SELECT REJECTED_MAPPER_SENTINEL</select>\n'
        "</root>\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    query = "insert into orders"
    accepted_path = Path("src/main/resources/mappers/OrderMapper.xml")
    ready_bundle = query_repository(repo, query, DEFAULT_CONFIG)
    accepted = _result_at(ready_bundle, accepted_path)
    rejected = _result_at(
        query_repository(repo, "REJECTED_MAPPER_SENTINEL", DEFAULT_CONFIG),
        rejected_path,
    )

    assert accepted._context_role_hint == "mybatis_repository"
    assert rejected._context_role_hint is None

    options = resolve_context_pack_options(
        DEFAULT_CONFIG,
        context_lines=None,
        max_evidence_anchors=evidence_anchor_top_k(
            DEFAULT_CONFIG.retrieval.final_top_k
        ),
    )
    pack = build_context_pack(ready_bundle, options)
    mapper_item = next(
        item for item in pack.items if item.file_path == accepted_path.as_posix()
    )
    assert (
        mapper_item.group,
        mapper_item.role,
        mapper_item.classification_basis,
    ) == ("implementations", "repository", "content")
    assert mapper_item.id in pack.groups["implementations"]
    assert mapper_item.source_kind == "result"
    assert any(
        "insert into orders" in excerpt.content
        for excerpt in mapper_item.excerpts
    )

    traced = trace_repository(repo, query, DEFAULT_CONFIG)
    public_payloads = (
        query_payload(ready_bundle),
        _query_payload(ready_bundle),
        trace_payload(repo, query, traced.trace),
        context_search_query_tool(str(repo), query),
        context_search_trace_tool(str(repo), query),
        context_search_context_tool(str(repo), query),
    )
    for payload in public_payloads:
        encoded = json.dumps(payload, sort_keys=True)
        assert "_context_role_hint" not in encoded
        assert "mybatis_repository" not in encoded
    assert "mybatis_repository" not in repr(ready_bundle)
    assert "mybatis_repository" not in repr(traced.trace)

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    store.set_metadata("graph_resolution_state", "stale")
    assert (
        _result_at(query_repository(repo, query, DEFAULT_CONFIG), accepted_path)
        ._context_role_hint
        is None
    )

    store.set_metadata("signal_schema_version", "4")
    store.set_metadata("graph_resolution_state", "ready")
    assert (
        _result_at(query_repository(repo, query, DEFAULT_CONFIG), accepted_path)
        ._context_role_hint
        is None
    )


def _result_at(bundle: QueryBundle, path: Path) -> RetrievalResult:
    return next(result for result in bundle.results if result.file_path == path)


def test_v5_remote_disclosure_boundary_records_only_sources_queries_and_probes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _graph_exploration_repo(tmp_path)
    recorder = _RecordingEmbeddingProvider()

    def provider(_config):
        return recorder

    def network_forbidden(*args, **kwargs):
        raise AssertionError("P5 graph flow attempted a remote client")

    monkeypatch.setattr(indexer, "provider_from_config", provider)
    monkeypatch.setattr(candidates, "provider_from_config", provider)
    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", network_forbidden)

    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    store.set_metadata("signal_schema_version", "4")
    recorder.batches.clear()

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_indexed == summary.files_seen == 4
    rebuild_batches = tuple(tuple(batch) for batch in recorder.batches)
    rebuilt_texts = [text for batch in rebuild_batches for text in batch]
    assert len(rebuilt_texts) == len(store.active_embedding_ids())
    assert all(type(text) is str for text in rebuilt_texts)
    assert any("ORDER_CONTROLLER_SOURCE_SENTINEL" in text for text in rebuilt_texts)
    assert any("ORDER_SERVICE_SOURCE_SENTINEL" in text for text in rebuilt_texts)
    assert any("ORDER_TEST_SOURCE_SENTINEL" in text for text in rebuilt_texts)

    query = "/orders/{id}"
    bundle = query_repository(repo, query, DEFAULT_CONFIG)
    assert bundle.results
    after_query = len(recorder.batches)
    assert recorder.batches[-1] == [query]

    explained = context_search_explain_tool(
        str(repo),
        "src/main/java/demo/OrderController.java:9",
    )
    assert explained["ok"] is True
    assert explained["graph"]["status"] == "ready"
    assert len(recorder.batches) == after_query

    explored = context_search_explore_tool(str(repo), query)

    assert explored["ok"] is True
    assert explored["trace"]["executed_probe_count"] >= 1
    assert explored["trace"]["retrieval_call_count"] <= 3
    followups = [
        probe
        for round_record in explored["trace"]["rounds"][1:]
        for probe in round_record["probes"]
    ]
    assert any(probe["source"] == "relation_target" for probe in followups)
    assert all(probe["query"] in _recorded_texts(recorder) for probe in followups)

    disclosed = _recorded_texts(recorder)
    feedback_path = repo / ".context-search" / "mcp_calls.jsonl"
    assert feedback_path.exists()
    assert feedback_path.read_text(encoding="utf-8") not in disclosed
    assert json.dumps(explained, sort_keys=True) not in disclosed
    for forbidden in (
        '"signal_id"',
        '"relation_id"',
        "resolution_confidence",
        "parser_diagnostic",
        "graph_index_stale",
        "_context_role_hint",
        "mcp_calls.jsonl",
    ):
        assert forbidden not in disclosed


class _RecordingEmbeddingProvider:
    def __init__(self) -> None:
        self.delegate = HashEmbeddingProvider(DEFAULT_CONFIG.embedding)
        self.batches: list[list[str]] = []

    def fingerprint(self) -> dict[str, object]:
        return self.delegate.fingerprint()

    def embed_texts(self, texts: list[str]):
        assert all(type(text) is str for text in texts)
        self.batches.append(list(texts))
        return self.delegate.embed_texts(texts)


def _recorded_texts(recorder: _RecordingEmbeddingProvider) -> str:
    return "\n".join(text for batch in recorder.batches for text in batch)


def _graph_exploration_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    main = repo / "src" / "main" / "java" / "demo"
    tests = repo / "src" / "test" / "java" / "demo"
    main.mkdir(parents=True)
    tests.mkdir(parents=True)
    (repo / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    (main / "OrderController.java").write_text(
        """package demo;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
@RestController
class OrderController {
  // ORDER_CONTROLLER_SOURCE_SENTINEL
  private final OrderService service = new OrderService();
  @GetMapping("/orders/{id}")
  String getOrder() { return service.load(); }
}
""",
        encoding="utf-8",
    )
    (main / "OrderService.java").write_text(
        """package demo;
class OrderService {
  // ORDER_SERVICE_SOURCE_SENTINEL
  String load() { return "order"; }
}
""",
        encoding="utf-8",
    )
    (tests / "OrderControllerTests.java").write_text(
        """package demo;
class OrderControllerTests {
  // ORDER_TEST_SOURCE_SENTINEL
  void loadsOrder() { new OrderController().getOrder(); }
}
""",
        encoding="utf-8",
    )
    return repo
