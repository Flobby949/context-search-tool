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


# A/B comparison result cache is created by the test_ab_comparison fixture.
