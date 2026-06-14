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
