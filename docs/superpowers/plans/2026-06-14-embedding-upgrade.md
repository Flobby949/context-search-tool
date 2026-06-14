# Embedding Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade context-search-tool from hash-v1 to real semantic embeddings (text-embedding-3-small or BGE-M3) and quantify noise reduction.

**Architecture:** Add BGE-M3 local provider (via Ollama) alongside existing hash and openai-compatible providers. Create A/B comparison tooling to measure Precision@12, MRR, and noise reduction. Keep hash as default; real embeddings opt-in via config.

**Tech Stack:** Ollama API (BGE-M3), pytest (comparison tests), existing httpx (API client), numpy (vectors)

---

## File Structure

**New files:**
- `src/context_search_tool/embeddings_bge.py` - BGE-M3 Ollama provider
- `tests/test_embeddings_bge.py` - BGE provider tests
- `tests/fixtures/ab_comparison/` - Query fixtures for A/B testing
- `tests/test_ab_comparison.py` - A/B comparison harness
- `docs/embedding-comparison.md` - A/B results documentation

**Modified files:**
- `src/context_search_tool/embeddings.py:123-129` - Add BGE provider dispatch
- `README.md:278-302` - Document BGE provider usage

**Note:** No dependency changes needed - reuses existing httpx for Ollama API calls

---

## Task 1: Verify Ollama Service and Create Test Scaffold

**Files:**
- Create: `tests/test_embeddings_bge.py`

- [ ] **Step 1: Verify Ollama service is running**

Run: `ollama list | grep bge-m3`
Expected: `bge-m3:latest` appears in output

Run: `curl -s http://localhost:11434/api/embeddings -d '{"model": "bge-m3", "prompt": "test"}' | python3 -c "import sys, json; print(len(json.load(sys.stdin)['embedding']))"`
Expected: Output `1024` (embedding dimension)

- [ ] **Step 2: Write failing test for BGE provider import**

```python
# tests/test_embeddings_bge.py
import pytest


def test_bge_provider_can_be_imported() -> None:
    from context_search_tool.embeddings_bge import BGEEmbeddingProvider
    
    assert BGEEmbeddingProvider is not None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_embeddings_bge.py::test_bge_provider_can_be_imported -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'context_search_tool.embeddings_bge'"

- [ ] **Step 4: Commit test scaffold**

```bash
git add tests/test_embeddings_bge.py
git commit -m "test: add BGE provider test scaffold"
```

---

## Task 2: Implement BGE-M3 Provider via Ollama

**Files:**
- Create: `src/context_search_tool/embeddings_bge.py`
- Modify: `tests/test_embeddings_bge.py`

- [ ] **Step 1: Write test for BGE provider initialization (unit test with mock)**

```python
# tests/test_embeddings_bge.py
import pytest
import numpy as np
import httpx

from context_search_tool.config import EmbeddingConfig
from context_search_tool.embeddings_bge import BGEEmbeddingProvider


def test_bge_provider_initializes_with_model_name() -> None:
    """Unit test - no network calls."""
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=1024
    )
    
    provider = BGEEmbeddingProvider(config)
    
    assert provider.config.model == "bge-m3"
    assert provider.config.dimensions == 1024


def test_bge_provider_embeds_text_with_mock_response() -> None:
    """Unit test with mocked Ollama response."""
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=3
    )
    
    # Mock Ollama API
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"embedding": [0.6, 0.0, 0.8]},  # Will be normalized to unit vector
            request=request
        )
    
    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    provider = BGEEmbeddingProvider(config, client=mock_client)
    
    vectors = provider.embed_texts(["hello"])
    
    assert len(vectors) == 1
    assert vectors[0].shape == (3,)
    assert np.isclose(np.linalg.norm(vectors[0]), 1.0, atol=1e-5)


def test_bge_provider_rejects_invalid_dimensions() -> None:
    """Unit test - dimension mismatch detection."""
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=512  # Wrong dimension
    )
    
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"embedding": [0.5] * 1024},  # Returns 1024 dims
            request=request
        )
    
    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    provider = BGEEmbeddingProvider(config, client=mock_client)
    
    with pytest.raises(ValueError, match="model produced .* dimensions"):
        provider.embed_texts(["test"])


def test_bge_provider_handles_missing_embedding_field() -> None:
    """Unit test - malformed response handling."""
    config = EmbeddingConfig(provider="bge", model="bge-m3", dimensions=3)
    
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={}, request=request)  # Missing 'embedding'
    
    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    provider = BGEEmbeddingProvider(config, client=mock_client)
    
    with pytest.raises(ValueError, match="missing 'embedding' field"):
        provider.embed_texts(["test"])


@pytest.mark.slow
@pytest.mark.integration
def test_bge_provider_real_ollama_service() -> None:
    """Integration test - requires Ollama running with bge-m3 model.
    
    Skip by default: pytest -m "not slow"
    Run explicitly: pytest -m integration
    """
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=1024
    )
    provider = BGEEmbeddingProvider(config)
    
    vectors = provider.embed_texts(["hello world", "测试查询"])
    
    assert len(vectors) == 2
    assert vectors[0].shape == (1024,)
    assert vectors[1].shape == (1024,)
    assert np.isclose(np.linalg.norm(vectors[0]), 1.0, atol=1e-5)
    assert np.isclose(np.linalg.norm(vectors[1]), 1.0, atol=1e-5)
```

- [ ] **Step 2: Run unit tests to verify they fail**

Run: `pytest tests/test_embeddings_bge.py -m "not slow" -v`
Expected: FAIL with "cannot import name 'BGEEmbeddingProvider'"

- [ ] **Step 3: Implement BGE provider using Ollama API**

```python
# src/context_search_tool/embeddings_bge.py
from __future__ import annotations

import httpx
import numpy as np

from context_search_tool.config import EmbeddingConfig


class BGEEmbeddingProvider:
    """BGE-M3 embedding provider via local Ollama service.
    
    Requires:
    - Ollama running on localhost:11434
    - bge-m3 model installed: `ollama pull bge-m3`
    """
    
    def __init__(
        self,
        config: EmbeddingConfig,
        client: httpx.Client | None = None,
    ) -> None:
        if config.dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")
        self.config = config
        self._client = client or httpx.Client(
            base_url="http://localhost:11434",
            timeout=30.0
        )
    
    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        vectors = []
        for text in texts:
            response = self._client.post(
                "/api/embeddings",
                json={"model": self.config.model, "prompt": text}
            )
            response.raise_for_status()
            
            payload = response.json()
            embedding = payload.get("embedding")
            if embedding is None:
                raise ValueError("ollama response missing 'embedding' field")
            
            vector = np.asarray(embedding, dtype=np.float32)
            
            # Normalize to unit vector
            norm = float(np.linalg.norm(vector))
            if norm > 0:
                vector = vector / norm
            
            if vector.shape[0] != self.config.dimensions:
                raise ValueError(
                    f"model produced {vector.shape[0]} dimensions, "
                    f"expected {self.config.dimensions}"
                )
            
            vectors.append(vector)
        
        return vectors
    
    def fingerprint(self) -> dict[str, object]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "dimensions": self.config.dimensions,
            "backend": "ollama",
        }
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `pytest tests/test_embeddings_bge.py -m "not slow" -v`
Expected: All unit tests PASS (mocked, no Ollama needed)

- [ ] **Step 5: Run integration test (optional, requires Ollama)**

Run: `pytest tests/test_embeddings_bge.py -m integration -v`
Expected: PASS if Ollama running, SKIP otherwise

- [ ] **Step 6: Update pytest configuration**

```toml
# pyproject.toml - add to [tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests requiring external services"
]
```

- [ ] **Step 7: Commit**

```bash
git add src/context_search_tool/embeddings_bge.py tests/test_embeddings_bge.py pyproject.toml
git commit -m "feat: add BGE-M3 embedding provider via Ollama with unit/integration test split"
```

---

## Task 3: Wire BGE Provider into Config System

**Files:**
- Modify: `src/context_search_tool/embeddings.py:123-129`
- Modify: `tests/test_embeddings_vector_store.py`

- [ ] **Step 1: Write test for provider_from_config with bge**

```python
# tests/test_embeddings_vector_store.py (add at end)
def test_provider_from_config_supports_bge() -> None:
    from context_search_tool.embeddings import provider_from_config
    from context_search_tool.embeddings_bge import BGEEmbeddingProvider
    
    config = EmbeddingConfig(
        provider="bge",
        model="bge-m3",
        dimensions=1024
    )
    
    provider = provider_from_config(config)
    
    assert isinstance(provider, BGEEmbeddingProvider)
    assert provider.config.model == "bge-m3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_embeddings_vector_store.py::test_provider_from_config_supports_bge -v`
Expected: FAIL with "unsupported embedding provider: bge"

- [ ] **Step 3: Add BGE dispatch to provider_from_config**

```python
# src/context_search_tool/embeddings.py (replace lines 123-129)
def provider_from_config(config: EmbeddingConfig) -> EmbeddingProvider:
    if config.provider == "hash":
        return HashEmbeddingProvider(config)
    if config.provider == "openai-compatible":
        return OpenAICompatibleEmbeddingProvider(config)
    if config.provider == "bge":
        from context_search_tool.embeddings_bge import BGEEmbeddingProvider
        return BGEEmbeddingProvider(config)
    raise ValueError(f"unsupported embedding provider: {config.provider}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_embeddings_vector_store.py::test_provider_from_config_supports_bge -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/context_search_tool/embeddings.py tests/test_embeddings_vector_store.py
git commit -m "feat: wire BGE provider into config dispatch"
```

---

## Task 4: Create A/B Comparison Test Harness

**Files:**
- Create: `src/context_search_tool/metrics.py`
- Create: `tests/fixtures/ab_comparison/queries.json`
- Create: `tests/test_ab_comparison.py`
- Create: `tests/conftest.py` (if not exists, for shared fixtures)

- [ ] **Step 1: Create query fixtures for A/B testing**

```json
# tests/fixtures/ab_comparison/queries.json
[
  {
    "query": "开门校验场景",
    "description": "Access control validation scenario",
    "expected_relevant": ["whitelist", "blacklist", "access", "validation"],
    "expected_noise": ["region", "role", "announcement"]
  },
  {
    "query": "黑白名单管理",
    "description": "Whitelist/blacklist management",
    "expected_relevant": ["whitelist", "blacklist", "manage", "add", "remove"],
    "expected_noise": ["region", "user", "notification"]
  },
  {
    "query": "OrderService cancel method",
    "description": "Code token dense query",
    "expected_relevant": ["OrderService", "cancel", "order"],
    "expected_noise": ["payment", "user", "notification"]
  }
]
```

- [ ] **Step 2: Create metrics module for reusability**

```python
# src/context_search_tool/metrics.py
"""Information retrieval metrics for embedding evaluation."""

from pathlib import Path

from context_search_tool.models import RetrievalResult


def precision_at_k(
    results: list[RetrievalResult],
    relevant_keywords: list[str],
    k: int
) -> float:
    """Calculate precision at K.
    
    Args:
        results: Retrieval results ordered by score
        relevant_keywords: Keywords that indicate relevance (matched against file paths)
        k: Number of top results to consider
    
    Returns:
        Precision score [0, 1]
    """
    if not results or k <= 0:
        return 0.0
    
    top_k = results[:k]
    relevant_count = sum(
        1 for result in top_k
        if any(kw.lower() in result.file_path.as_posix().lower() 
               for kw in relevant_keywords)
    )
    return relevant_count / k


def mean_reciprocal_rank(
    results: list[RetrievalResult],
    relevant_keywords: list[str]
) -> float:
    """Calculate mean reciprocal rank.
    
    Args:
        results: Retrieval results ordered by score
        relevant_keywords: Keywords that indicate relevance
    
    Returns:
        MRR score [0, 1]
    """
    for rank, result in enumerate(results, start=1):
        if any(kw.lower() in result.file_path.as_posix().lower() 
               for kw in relevant_keywords):
            return 1.0 / rank
    return 0.0


def count_noise_files(
    results: list[RetrievalResult],
    noise_keywords: list[str],
    top_k: int
) -> int:
    """Count noise files in top-K results.
    
    Args:
        results: Retrieval results ordered by score
        noise_keywords: Keywords that indicate noise
        top_k: Number of top results to check
    
    Returns:
        Count of noise files
    """
    top_k_results = results[:top_k]
    return sum(
        1 for result in top_k_results
        if any(kw.lower() in result.file_path.as_posix().lower() 
               for kw in noise_keywords)
    )
```

- [ ] **Step 3: Write complete A/B comparison harness**

```python
# tests/test_ab_comparison.py
"""A/B comparison tests for hash vs BGE embeddings.

Run with: pytest tests/test_ab_comparison.py --ab-test-repo=/path/to/repo -v
"""
import json
import shutil
from pathlib import Path

import pytest

from context_search_tool.config import EmbeddingConfig, ToolConfig
from context_search_tool.indexer import index_repository
from context_search_tool.paths import index_dir_for
from context_search_tool.retrieval import query_repository
from context_search_tool.metrics import precision_at_k, mean_reciprocal_rank, count_noise_files


# Shared output directory for A/B results (session-scoped)
AB_RESULTS_DIR = None


def pytest_configure(config):
    """Create shared output directory for A/B results."""
    global AB_RESULTS_DIR
    AB_RESULTS_DIR = Path(config.cache.mkdir("ab_results"))


@pytest.fixture
def ab_queries():
    fixture_path = Path(__file__).parent / "fixtures" / "ab_comparison" / "queries.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture
def ab_results_dir():
    """Shared directory for A/B results across parameterized runs."""
    return AB_RESULTS_DIR


def test_ab_comparison_queries_load(ab_queries):
    """Verify query fixtures are well-formed."""
    assert len(ab_queries) >= 3
    assert "query" in ab_queries[0]
    assert "expected_relevant" in ab_queries[0]
    assert "expected_noise" in ab_queries[0]


@pytest.mark.slow
@pytest.mark.parametrize("provider_name,model,dimensions", [
    ("hash", "hash-v1", 384),
    ("bge", "bge-m3", 1024),
])
def test_ab_comparison_end_to_end(
    ab_queries,
    ab_results_dir,
    provider_name,
    model,
    dimensions,
    request
):
    """Run full A/B comparison: clean -> index -> query -> measure metrics.
    
    Requires --ab-test-repo CLI option.
    Usage:
        pytest tests/test_ab_comparison.py::test_ab_comparison_end_to_end \
            --ab-test-repo=/path/to/codebase -v
    """
    repo_path = request.config.getoption("--ab-test-repo", None)
    if not repo_path:
        pytest.skip("--ab-test-repo not provided")
    
    repo = Path(repo_path)
    if not repo.exists():
        pytest.skip(f"repo not found: {repo}")
    
    # Step 1: Clean existing index to avoid manifest compatibility issues
    index_dir = index_dir_for(repo)
    if index_dir.exists():
        shutil.rmtree(index_dir)
    
    # Step 2: Configure provider
    config = ToolConfig(
        embedding=EmbeddingConfig(
            provider=provider_name,
            model=model,
            dimensions=dimensions
        )
    )
    
    # Step 3: Index repository with this provider
    index_repository(repo, config)
    
    # Step 4: Run queries and collect metrics
    results = []
    for query_spec in ab_queries:
        query_bundle = query_repository(repo, query_spec["query"], config)
        
        p_at_12 = precision_at_k(
            query_bundle.results,
            query_spec["expected_relevant"],
            k=12
        )
        mrr = mean_reciprocal_rank(
            query_bundle.results,
            query_spec["expected_relevant"]
        )
        noise_count = count_noise_files(
            query_bundle.results,
            query_spec["expected_noise"],
            top_k=12
        )
        
        results.append({
            "query": query_spec["query"],
            "provider": provider_name,
            "precision_at_12": p_at_12,
            "mrr": mrr,
            "noise_count": noise_count,
        })
    
    # Step 5: Store results in shared directory (not tmp_path)
    output_file = ab_results_dir / f"ab_results_{provider_name}.json"
    output_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    
    # Step 6: Assert basic sanity
    assert all(r["precision_at_12"] >= 0 for r in results)
    assert all(r["mrr"] >= 0 for r in results)


@pytest.mark.slow
def test_ab_comparison_summary(ab_results_dir, request):
    """Compare hash vs bge results and quantify noise reduction.
    
    Run after test_ab_comparison_end_to_end completes for both providers.
    Depends on: both hash and bge results existing in ab_results_dir.
    """
    hash_file = ab_results_dir / "ab_results_hash.json"
    bge_file = ab_results_dir / "ab_results_bge.json"
    
    if not hash_file.exists() or not bge_file.exists():
        pytest.skip("Run test_ab_comparison_end_to_end first for both providers")
    
    hash_results = json.loads(hash_file.read_text())
    bge_results = json.loads(bge_file.read_text())
    
    # Compare metrics per query
    summary = []
    for hash_res, bge_res in zip(hash_results, bge_results):
        assert hash_res["query"] == bge_res["query"], \
            f"Query mismatch: {hash_res['query']} != {bge_res['query']}"
        
        precision_gain = bge_res["precision_at_12"] - hash_res["precision_at_12"]
        mrr_gain = bge_res["mrr"] - hash_res["mrr"]
        noise_reduction = hash_res["noise_count"] - bge_res["noise_count"]
        
        summary.append({
            "query": hash_res["query"],
            "hash_precision": hash_res["precision_at_12"],
            "bge_precision": bge_res["precision_at_12"],
            "precision_gain": precision_gain,
            "hash_noise": hash_res["noise_count"],
            "bge_noise": bge_res["noise_count"],
            "noise_reduction": noise_reduction,
            "mrr_gain": mrr_gain,
        })
    
    # Calculate aggregate metrics
    avg_precision_gain = sum(s["precision_gain"] for s in summary) / len(summary)
    avg_noise_reduction = sum(s["noise_reduction"] for s in summary) / len(summary)
    avg_mrr_gain = sum(s["mrr_gain"] for s in summary) / len(summary)
    
    comparison = {
        "per_query": summary,
        "aggregate": {
            "avg_precision_gain": avg_precision_gain,
            "avg_noise_reduction": avg_noise_reduction,
            "avg_mrr_gain": avg_mrr_gain,
            "total_queries": len(summary),
        }
    }
    
    # Write comparison summary
    output_file = ab_results_dir / "ab_comparison_summary.json"
    output_file.write_text(json.dumps(comparison, indent=2, ensure_ascii=False))
    
    # Assert: all queries aligned and output is well-formed
    assert len(summary) == len(hash_results) == len(bge_results), \
        "Query count mismatch between providers"
    assert all("precision_gain" in s for s in summary), \
        "Missing precision_gain in summary"
    assert all("noise_reduction" in s for s in summary), \
        "Missing noise_reduction in summary"
    
    # Print summary for human review
    print(f"\n{'='*60}")
    print("A/B Comparison Summary")
    print(f"{'='*60}")
    print(f"Queries tested: {len(summary)}")
    print(f"Avg Precision@12 gain: {avg_precision_gain:+.3f}")
    print(f"Avg noise reduction: {avg_noise_reduction:+.1f} files/query")
    print(f"Avg MRR gain: {avg_mrr_gain:+.3f}")
    print(f"{'='*60}")
    print(f"Detailed results: {output_file}")
    
    # Optional: Add regression detection
    # Uncomment to enforce improvement thresholds
    # assert avg_noise_reduction >= 0, f"Regression: BGE increased noise by {-avg_noise_reduction}"
    # assert avg_precision_gain >= 0, f"Regression: BGE decreased precision by {-avg_precision_gain}"
```

- [ ] **Step 4: Add pytest.ini configuration for slow tests**

```ini
# pytest.ini or pyproject.toml [tool.pytest.ini_options]
# Add slow and integration markers
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests requiring external services
```

- [ ] **Step 5: Create conftest.py for pytest hooks**

```python
# tests/conftest.py
"""Shared pytest configuration and fixtures."""

import pytest


def pytest_addoption(parser):
    """Add custom CLI options for tests."""
    parser.addoption(
        "--ab-test-repo",
        action="store",
        default=None,
        help="Path to repository for A/B comparison testing"
    )


# Note: pytest_configure is also defined in test_ab_comparison.py
# for creating shared AB_RESULTS_DIR. This is intentional - each test
# module can have its own pytest hooks for module-specific setup.
```

- [ ] **Step 6: Run unit test (fixture loading)**

Run: `pytest tests/test_ab_comparison.py::test_ab_comparison_queries_load -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/ab_comparison/queries.json tests/test_ab_comparison.py src/context_search_tool/metrics.py tests/conftest.py
git commit -m "test: add complete A/B comparison harness with metrics"
```

---

## Task 5: Add Unit Tests for Metrics Module

**Files:**
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Write unit tests for precision_at_k**

```python
# tests/test_metrics.py
from pathlib import Path

import pytest

from context_search_tool.models import RetrievalResult
from context_search_tool.metrics import precision_at_k, mean_reciprocal_rank, count_noise_files


def test_precision_at_k_calculates_correctly():
    results = [
        RetrievalResult(
            file_path=Path("src/whitelist.java"),
            start_line=10, end_line=20,
            content="", score=0.9, score_parts={}, reasons=[],
            followup_keywords=[]
        ),
        RetrievalResult(
            file_path=Path("src/region.java"),
            start_line=10, end_line=20,
            content="", score=0.8, score_parts={}, reasons=[],
            followup_keywords=[]
        ),
        RetrievalResult(
            file_path=Path("src/blacklist.java"),
            start_line=10, end_line=20,
            content="", score=0.7, score_parts={}, reasons=[],
            followup_keywords=[]
        ),
    ]
    relevant_keywords = ["whitelist", "blacklist"]
    
    precision = precision_at_k(results, relevant_keywords, k=3)
    
    assert precision == pytest.approx(2 / 3)


def test_precision_at_k_handles_empty_results():
    assert precision_at_k([], ["keyword"], k=10) == 0.0


def test_precision_at_k_handles_zero_k():
    results = [
        RetrievalResult(
            file_path=Path("test.java"),
            start_line=1, end_line=10,
            content="", score=1.0, score_parts={}, reasons=[],
            followup_keywords=[]
        )
    ]
    assert precision_at_k(results, ["test"], k=0) == 0.0


def test_mrr_calculates_correctly():
    results = [
        RetrievalResult(
            file_path=Path("src/region.java"),
            start_line=10, end_line=20,
            content="", score=0.9, score_parts={}, reasons=[],
            followup_keywords=[]
        ),
        RetrievalResult(
            file_path=Path("src/whitelist.java"),
            start_line=10, end_line=20,
            content="", score=0.8, score_parts={}, reasons=[],
            followup_keywords=[]
        ),
    ]
    relevant_keywords = ["whitelist", "blacklist"]
    
    mrr = mean_reciprocal_rank(results, relevant_keywords)
    
    assert mrr == pytest.approx(1 / 2)


def test_mrr_returns_zero_when_no_relevant_found():
    results = [
        RetrievalResult(
            file_path=Path("src/noise.java"),
            start_line=1, end_line=10,
            content="", score=1.0, score_parts={}, reasons=[],
            followup_keywords=[]
        )
    ]
    assert mean_reciprocal_rank(results, ["relevant"]) == 0.0


def test_count_noise_files_calculates_correctly():
    results = [
        RetrievalResult(
            file_path=Path("src/region.java"),
            start_line=10, end_line=20,
            content="", score=0.9, score_parts={}, reasons=[],
            followup_keywords=[]
        ),
        RetrievalResult(
            file_path=Path("src/announcement.java"),
            start_line=10, end_line=20,
            content="", score=0.8, score_parts={}, reasons=[],
            followup_keywords=[]
        ),
        RetrievalResult(
            file_path=Path("src/whitelist.java"),
            start_line=10, end_line=20,
            content="", score=0.7, score_parts={}, reasons=[],
            followup_keywords=[]
        ),
    ]
    noise_keywords = ["region", "announcement"]
    
    count = count_noise_files(results, noise_keywords, top_k=3)
    
    assert count == 2
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_metrics.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_metrics.py
git commit -m "test: add unit tests for IR metrics"
```

---

## Task 6: Document BGE Provider Usage

**Files:**
- Modify: `README.md:278-302`

- [ ] **Step 1: Add BGE provider documentation**

```markdown
# README.md (add after openai-compatible section around line 302)

### BGE Provider (Local via Ollama)

For local semantic embeddings without external API calls:

```toml
[embedding]
provider = "bge"
model = "bge-m3"
dimensions = 1024
```

BGE-M3 runs locally via Ollama service. Requires:
- Ollama installed and running
- BGE-M3 model: `ollama pull bge-m3`

Advantages:
- No API costs
- Works offline
- Strong multilingual support (English + Chinese)
- 1024-dimensional embeddings
- Fast inference via Ollama

Disadvantages:
- Requires Ollama service running
- HTTP API overhead (minimal)
- ~1.2GB model storage

Best for: Semantic searches on business descriptions, cross-language queries, or when API access is unavailable.
```

- [ ] **Step 2: Verify documentation builds correctly**

Run: `cat README.md | grep -A 10 "BGE Provider"`
Expected: BGE section appears in output

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add BGE provider usage guide"
```

---

## Task 7: Manual Verification on Real Project

**Files:**
- Create: `docs/embedding-comparison.md`

- [ ] **Step 1: Index test project with hash**

Run:
```bash
cd /path/to/test/java/project
cst clean .
cst index .
cst query . "开门校验场景" --json > /tmp/hash_results.json
```

Expected: Results saved to /tmp/hash_results.json

- [ ] **Step 2: Reconfigure to BGE and reindex**

```bash
# Edit .context-search/config.toml
# Change [embedding] section to:
# provider = "bge"
# model = "bge-m3"
# dimensions = 1024

cst clean .
cst index .  # Uses local Ollama, should be fast
cst query . "开门校验场景" --json > /tmp/bge_results.json
```

Expected: Results saved to /tmp/bge_results.json

- [ ] **Step 3: Compare top-12 results manually**

```bash
python -c "
import json
hash_data = json.load(open('/tmp/hash_results.json'))
bge_data = json.load(open('/tmp/bge_results.json'))
print('Hash top-12:')
for r in hash_data['results'][:12]:
    print(f\"  {r['file_path']} (score: {r['score']:.3f})\")
print()
print('BGE top-12:')
for r in bge_data['results'][:12]:
    print(f\"  {r['file_path']} (score: {r['score']:.3f})\")
"
```

Expected: Visual comparison shows BGE has fewer noise files

- [ ] **Step 4: Document findings**

```markdown
# docs/embedding-comparison.md
# Embedding Provider Comparison

## Test Setup
- Project: [project name]
- Query: "开门校验场景" (access control validation scenario)
- Metrics: Precision@12, MRR, manual inspection

## Results

### Hash-v1
- Precision@12: [count relevant files / 12]
- MRR: [1 / rank of first relevant]
- Noise: [list noise file paths]

### BGE-M3
- Precision@12: [count relevant files / 12]
- MRR: [1 / rank of first relevant]
- Noise: [list noise file paths]

## Conclusion
[Quantify improvement: "BGE reduced noise by X%, improved Precision@12 by Y%"]
```

- [ ] **Step 5: Commit documentation**

```bash
git add docs/embedding-comparison.md
git commit -m "docs: add embedding comparison results"
```

---

## Self-Review Checklist

**Spec coverage:**
- [ ] Add BGE-M3 provider - Task 2
- [ ] Keep hash as default - No config changes needed
- [ ] A/B comparison tooling - Task 4 (complete harness)
- [ ] Precision@12 and MRR metrics - Task 5 (dedicated module)
- [ ] Real project validation - Task 7
- [ ] Backward compatibility - Manifest checks already exist
- [ ] Config switching - Task 3 wires provider dispatch

**Placeholder scan:**
- [ ] No TBD/TODO present
- [ ] All test code is complete
- [ ] All implementation code is complete
- [ ] Exact file paths specified

**Type consistency:**
- [ ] EmbeddingConfig used consistently
- [ ] BGEEmbeddingProvider matches Protocol
- [ ] RetrievalResult used in metrics

**Test robustness:**
- [ ] Unit tests use mocks (no external dependencies)
- [ ] Integration tests marked with @pytest.mark.slow
- [ ] A/B harness is complete end-to-end test

**Dependency strategy:**
- [ ] No new Python dependencies required (uses existing httpx)
- [ ] External dependency: Ollama service documented clearly

---

## Execution Strategy

**Recommendation:** Use **superpowers:subagent-driven-development**

- Fresh subagent per task
- Review between tasks
- Fast iteration
- Tasks 1-3: Core provider implementation
- Tasks 4-5: Testing infrastructure
- Task 6: Documentation
- Task 7: Manual validation

Execute with:
```
Use skill: superpowers:subagent-driven-development
Plan: docs/superpowers/plans/2026-06-14-embedding-upgrade.md
```

---

## Notes

- Plan modified to use Ollama instead of sentence-transformers (reuses existing local bge-m3 model)
- All tests designed to run without network calls by default (mocks)
- Integration tests require explicit opt-in via `-m integration`
- A/B comparison harness outputs JSON for manual review
