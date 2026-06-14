"""Unit tests for information retrieval metrics."""

from pathlib import Path

import pytest

from context_search_tool.metrics import (
    count_noise_files,
    mean_reciprocal_rank,
    precision_at_k,
)
from context_search_tool.models import RetrievalResult


def _make_result(file_path: str, score: float = 1.0) -> RetrievalResult:
    """Helper to create a RetrievalResult for testing."""
    return RetrievalResult(
        file_path=Path(file_path),
        start_line=1,
        end_line=10,
        content="test content",
        score=score,
        score_parts={},
        reasons=[],
        followup_keywords=[]
    )


class TestPrecisionAtK:
    """Tests for precision_at_k function."""

    def test_precision_at_k_calculates_correctly(self):
        """Test precision calculation with mixed relevant and irrelevant results."""
        results = [
            _make_result("src/auth/login.py", 0.9),
            _make_result("src/utils/helper.py", 0.8),
            _make_result("src/auth/logout.py", 0.7),
            _make_result("src/models/user.py", 0.6),
            _make_result("tests/test_auth.py", 0.5),
        ]
        relevant_keywords = ["auth"]

        # Top 3 results: 2 contain "auth" (login.py, logout.py)
        precision = precision_at_k(results, relevant_keywords, k=3)
        assert precision == pytest.approx(2.0 / 3.0)

        # Top 5 results: 3 contain "auth" (login.py, logout.py, test_auth.py)
        precision = precision_at_k(results, relevant_keywords, k=5)
        assert precision == pytest.approx(3.0 / 5.0)

    def test_precision_at_k_handles_empty_results(self):
        """Test precision returns 0 for empty result list."""
        results = []
        relevant_keywords = ["auth"]

        precision = precision_at_k(results, relevant_keywords, k=5)
        assert precision == 0.0

    def test_precision_at_k_handles_zero_k(self):
        """Test precision returns 0 when k is 0 or negative."""
        results = [
            _make_result("src/auth/login.py", 0.9),
            _make_result("src/utils/helper.py", 0.8),
        ]
        relevant_keywords = ["auth"]

        precision = precision_at_k(results, relevant_keywords, k=0)
        assert precision == 0.0

        precision = precision_at_k(results, relevant_keywords, k=-1)
        assert precision == 0.0


class TestMeanReciprocalRank:
    """Tests for mean_reciprocal_rank function."""

    def test_mrr_calculates_correctly(self):
        """Test MRR calculation with relevant result at different positions."""
        # Relevant result at position 1
        results = [
            _make_result("src/auth/login.py", 0.9),
            _make_result("src/utils/helper.py", 0.8),
            _make_result("src/models/user.py", 0.7),
        ]
        relevant_keywords = ["auth"]

        mrr = mean_reciprocal_rank(results, relevant_keywords)
        assert mrr == pytest.approx(1.0 / 1.0)

        # Relevant result at position 3
        results = [
            _make_result("src/utils/helper.py", 0.9),
            _make_result("src/models/user.py", 0.8),
            _make_result("src/auth/login.py", 0.7),
        ]

        mrr = mean_reciprocal_rank(results, relevant_keywords)
        assert mrr == pytest.approx(1.0 / 3.0)

    def test_mrr_returns_zero_when_no_relevant_found(self):
        """Test MRR returns 0 when no relevant results exist."""
        results = [
            _make_result("src/utils/helper.py", 0.9),
            _make_result("src/models/user.py", 0.8),
            _make_result("src/views/home.py", 0.7),
        ]
        relevant_keywords = ["auth"]

        mrr = mean_reciprocal_rank(results, relevant_keywords)
        assert mrr == 0.0


class TestCountNoiseFiles:
    """Tests for count_noise_files function."""

    def test_count_noise_files_calculates_correctly(self):
        """Test noise file counting in top-K results."""
        results = [
            _make_result("src/auth/login.py", 0.9),
            _make_result("node_modules/lib/index.js", 0.8),
            _make_result("src/models/user.py", 0.7),
            _make_result("dist/bundle.min.js", 0.6),
            _make_result("src/utils/helper.py", 0.5),
        ]
        noise_keywords = ["node_modules", "dist"]

        # Top 3 results: 1 noise file (node_modules)
        noise_count = count_noise_files(results, noise_keywords, top_k=3)
        assert noise_count == 1

        # Top 5 results: 2 noise files (node_modules, dist)
        noise_count = count_noise_files(results, noise_keywords, top_k=5)
        assert noise_count == 2

        # Top 1 result: 0 noise files
        noise_count = count_noise_files(results, noise_keywords, top_k=1)
        assert noise_count == 0
