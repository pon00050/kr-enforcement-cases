"""
normalise_fss.py — Post-processing validation of fss_enriched.json.

Checks all classification fields against closed enumerations.
Flags OOV values and logs counts per field.
Strict mode strips OOV forensic_signals from the output.

Usage:
  uv run python -m kr_enforcement_cases.normalise_fss
  uv run python -m kr_enforcement_cases.normalise_fss --strict
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .constants import (
    BENEISH_COMPONENTS,
    FSS_VIOLATION_CATEGORIES,
    SCHEME_TYPES,
    SIGNAL_SEED_VOCABULARY,
)
from .paths import ENRICHED_JSON

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)

_VIOLATION_SET = set(FSS_VIOLATION_CATEGORIES)
_SCHEME_SET = set(SCHEME_TYPES)
_BENEISH_SET = set(BENEISH_COMPONENTS)


def normalise(cases: list[dict], strict: bool = False) -> tuple[list[dict], dict]:
    """
    Validate and clean enriched cases.
    Returns (cleaned_cases, oov_counts_per_field).
    """
    oov: dict[str, list[str]] = {
        "violation_type": [],
        "scheme_type": [],
        "beneish_components": [],
        "forensic_signals": [],
    }
    out = []
    for case in cases:
        c = dict(case)

        # violation_type
        vt = c.get("violation_type")
        if vt is not None and vt not in _VIOLATION_SET:
            oov["violation_type"].append(f"{c['공개번호']}:{vt}")
            c["violation_type"] = None

        # scheme_type
        st = c.get("scheme_type")
        if st is not None and st not in _SCHEME_SET:
            oov["scheme_type"].append(f"{c['공개번호']}:{st}")
            c["scheme_type"] = None

        # beneish_components — remove OOV entries
        raw_bc = c.get("beneish_components") or []
        clean_bc = []
        for bc in raw_bc:
            if bc in _BENEISH_SET:
                clean_bc.append(bc)
            else:
                oov["beneish_components"].append(f"{c['공개번호']}:{bc}")
        c["beneish_components"] = clean_bc

        # forensic_signals — remove OOV in strict mode; flag always
        raw_fs = c.get("forensic_signals") or []
        clean_fs = []
        for sig in raw_fs:
            if sig in SIGNAL_SEED_VOCABULARY:
                clean_fs.append(sig)
            else:
                oov["forensic_signals"].append(f"{c['공개번호']}:{sig}")
                if not strict:
                    clean_fs.append(sig)  # keep in non-strict mode
        c["forensic_signals"] = clean_fs

        out.append(c)

    return out, oov


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate fss_enriched.json against closed enumerations"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Strip OOV forensic_signals from output (default: flag only).",
    )
    args = parser.parse_args()

    if not ENRICHED_JSON.exists():
        log.error(
            "fss_enriched.json not found. "
            "Run: uv run python -m kr_enforcement_cases.enrich_fss_cases"
        )
        sys.exit(1)

    with open(ENRICHED_JSON, encoding="utf-8") as f:
        cases = json.load(f)
    log.info("Loaded %d enriched cases", len(cases))

    cleaned, oov = normalise(cases, strict=args.strict)

    any_oov = False
    for field, items in oov.items():
        if items:
            any_oov = True
            log.warning("OOV %s (%d): %s", field, len(items), items[:5])
        else:
            log.info("  %s: all values in-vocab", field)

    if any_oov:
        log.warning("OOV values detected — consider tightening the Haiku prompt.")
    else:
        log.info("All fields validated — no OOV values found.")

    # Write back normalised output in-place
    with open(ENRICHED_JSON, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    log.info("Normalised output written to %s", ENRICHED_JSON)


if __name__ == "__main__":
    main()
