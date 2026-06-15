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
    parser.addoption(
        "--calibration-operation-client-repo",
        action="store",
        default=None,
        help="Path to operation-client-api for retrieval calibration tests",
    )
    parser.addoption(
        "--calibration-console-iot-repo",
        action="store",
        default=None,
        help="Path to console-iot-api for retrieval calibration tests",
    )


# A/B comparison result cache is created by the test_ab_comparison fixture.
