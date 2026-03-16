"""Canonical path constants for kr-enforcement-cases."""

from pathlib import Path

PROJECT_ROOT   = Path(__file__).resolve().parent.parent.parent
RAW_DIR        = PROJECT_ROOT / "data" / "raw" / "fss_enforcement"
PROCESSED_DIR  = PROJECT_ROOT / "data" / "processed"
CURATED_DIR    = PROJECT_ROOT / "data" / "curated"
INDEX_PATH     = PROCESSED_DIR / "fss_enforcement_index.csv"
REPORTS_DIR    = PROJECT_ROOT / "reports"
SCORED_INDEX   = REPORTS_DIR / "scored_index.csv"
EXTRACTED_JSON     = CURATED_DIR / "fss_extracted.json"
ENRICHED_JSON      = CURATED_DIR / "fss_enriched.json"
BLIND_TEST_JSON    = CURATED_DIR / "fss_blind_test.json"
SONNET_REVIEW_JSON = CURATED_DIR / "fss_sonnet_review.json"
VIOLATIONS_CSV     = REPORTS_DIR / "violations.csv"

# ─── FSS Source 2 paths ────────────────────────────────────────────────────────
SOURCE2_RAW_DIR        = PROJECT_ROOT / "data" / "raw" / "fss_source2"
SOURCE2_INDEX          = PROCESSED_DIR / "fss_source2_index.csv"
SOURCE2_EXTRACTED_JSON = CURATED_DIR / "fss_source2_extracted.json"
SOURCE2_ENRICHED_JSON  = CURATED_DIR / "fss_source2_enriched.json"
DART_MATCHES_CSV       = CURATED_DIR / "dart_matches.csv"
BENEISH_RATIOS_CSV     = REPORTS_DIR / "beneish_ratios.csv"
BENEISH_VALIDATION_MD  = REPORTS_DIR / "beneish-validation.md"
RESEARCH_JOURNEY_MD    = REPORTS_DIR / "research-journey.md"

# ─── SFC Source 1 paths ────────────────────────────────────────────────────────
SFC1_RAW_DIR        = PROJECT_ROOT / "data" / "raw" / "SFC Source 1"
SFC1_MINUTES_DIR    = SFC1_RAW_DIR / "minutes"
SFC1_INDEX          = PROCESSED_DIR / "sfc_source1_index.csv"
SFC1_EXTRACTED_JSON = CURATED_DIR / "sfc_source1_extracted.json"
SFC1_ENRICHED_JSON  = CURATED_DIR / "sfc_source1_enriched.json"
