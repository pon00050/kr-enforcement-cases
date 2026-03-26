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
    if not VIOLATIONS_CSV.exists():
        raise FileNotFoundError(
            f"violations.csv not found at {VIOLATIONS_CSV}. "
            "Run: python -m kr_enforcement_cases.build_violation_db"
        )
    return pd.read_csv(VIOLATIONS_CSV)


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
    if not BENEISH_RATIOS_CSV.exists():
        raise FileNotFoundError(
            f"beneish_ratios.csv not found at {BENEISH_RATIOS_CSV}. "
            "Run: python -m kr_enforcement_cases.compute_beneish"
        )
    return pd.read_csv(BENEISH_RATIOS_CSV)


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
    if not DART_MATCHES_CSV.exists():
        raise FileNotFoundError(
            f"dart_matches.csv not found at {DART_MATCHES_CSV}. "
            "Run: python -m kr_enforcement_cases.match_dart_companies"
        )
    return pd.read_csv(DART_MATCHES_CSV)
