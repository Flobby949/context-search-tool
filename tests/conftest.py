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
