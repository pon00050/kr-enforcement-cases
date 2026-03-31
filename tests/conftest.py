"""conftest.py — Shared pytest fixtures for kr-enforcement-cases tests.

Fixtures for pipeline modules that need data paths or sample inputs go here.
"""

from pathlib import Path
import pytest

# Repository root — tests/ is one level below
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def repo_root() -> Path:
    """Path to the repository root."""
    return REPO_ROOT
