"""
kr-enforcement-cases — Korean FSS/SFC enforcement case dataset.

Public API
----------
load_violations() -> pd.DataFrame
    240-case enforcement violations dataset with scheme taxonomy.

load_beneish_ratios() -> pd.DataFrame
    Beneish M-Score ratio computations for enforcement-case companies.

load_dart_matches() -> pd.DataFrame
    DART-matched enforcement companies (86 matches with corp_code).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from kr_enforcement_cases.paths import (
    BENEISH_RATIOS_CSV,
    DART_MATCHES_CSV,
    VIOLATIONS_CSV,
)

__all__ = [
    "load_violations",
    "load_beneish_ratios",
    "load_dart_matches",
]


def _load_csv(path: Path, build_cmd: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"{path.name} not found at {path}. Run: {build_cmd}"
        )
    return pd.read_csv(path)


def load_violations() -> pd.DataFrame:
    """Load the enforcement violations dataset.

    Returns
    -------
    pd.DataFrame
        240 rows (FSS + SFC cases) with columns including:
        company_name, violation_type, scheme_type, year, source.

    Raises
    ------
    FileNotFoundError
        If violations.csv has not been built yet.
        Run: python -m kr_enforcement_cases.build_violation_db
    """
    return _load_csv(VIOLATIONS_CSV, "python -m kr_enforcement_cases.build_violation_db")


def load_beneish_ratios() -> pd.DataFrame:
    """Load Beneish M-Score ratio computations for enforcement cases.

    Returns
    -------
    pd.DataFrame
        ~60 rows with Beneish ratio components for enforcement-case companies
        that could be matched to DART financial data.

    Raises
    ------
    FileNotFoundError
        If beneish_ratios.csv has not been built.
        Run: python -m kr_enforcement_cases.compute_beneish
    """
    return _load_csv(BENEISH_RATIOS_CSV, "python -m kr_enforcement_cases.compute_beneish")


def load_dart_matches() -> pd.DataFrame:
    """Load DART-matched enforcement companies.

    Returns
    -------
    pd.DataFrame
        86 rows with company_name, corp_code, ticker, and match confidence.

    Raises
    ------
    FileNotFoundError
        If dart_matches.csv has not been built.
        Run: python -m kr_enforcement_cases.match_dart_companies
    """
    return _load_csv(DART_MATCHES_CSV, "python -m kr_enforcement_cases.match_dart_companies")
