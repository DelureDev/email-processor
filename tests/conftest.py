"""Shared fixtures for tests."""
import os
import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'test_files')


@pytest.fixture
def fixtures_dir():
    return os.path.abspath(FIXTURES_DIR)


def fixture_path(filename: str) -> str:
    """Get absolute path to a test fixture file."""
    path = os.path.join(FIXTURES_DIR, filename)
    if not os.path.exists(path):
        pytest.skip(f"Fixture not found: {filename}")
    return os.path.abspath(path)
