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


@pytest.fixture
def ab_queries():
    fixture_path = Path(__file__).parent / "fixtures" / "ab_comparison" / "queries.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def ab_results_dir(request):
    """Shared directory for A/B results across parameterized runs."""
    return Path(request.config.cache.mkdir("ab_results"))


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
    if not request.config.getoption("--ab-test-repo", None):
        pytest.skip("--ab-test-repo not provided")

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
