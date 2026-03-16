"""
build_violation_db.py — Join scored index + extracted + enriched → violations.csv.

One row per case. All text columns are included for MCP tool #12 full-text search.
Cases not yet downloaded have empty text columns but are still present.

Output: reports/violations.csv

Usage:
  uv run python -m kr_enforcement_cases.build_violation_db
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from pathlib import Path

from .paths import (
    ENRICHED_JSON,
    EXTRACTED_JSON,
    REPORTS_DIR,
    SCORED_INDEX,
    VIOLATIONS_CSV,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)

# Column order in output CSV
_COLUMNS = [
    # From scored index
    "공개번호", "제목", "쟁점_분야", "관련_기준서", "결정년도",
    "beneish_score", "tier",
    # From PDF extraction (Phase A3)
    "결정일", "회계결산일", "extract_status",
    "full_text", "s1_text", "s2_text", "s3_text", "s4_text", "s5_text",
    # From Haiku enrichment (Phase B1)
    "violation_type", "scheme_type",
    "beneish_components", "forensic_signals",
    "key_issue", "fss_ruling", "implications",
    "enrichment_status",
]


def _load_scored(path: Path) -> dict[str, dict]:
    """Load scored_index.csv keyed by 공개번호.

    Rows with blank 공개번호 are annual summary documents (not individual cases).
    They receive a synthetic key FSS/BATCH-{번호} so they are not collapsed.
    """
    if not path.exists():
        log.warning("scored_index.csv not found at %s — using empty", path)
        return {}
    result = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            key = r["공개번호"].strip() or f"FSS/BATCH-{r['번호']}"
            r["공개번호"] = key  # normalise in-place
            result[key] = r
    return result


def _load_extracted(path: Path) -> dict[str, dict]:
    """Load fss_extracted.json keyed by 공개번호."""
    if not path.exists():
        log.warning("fss_extracted.json not found at %s — using empty", path)
        return {}
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    return {c["공개번호"]: c for c in cases}


def _load_enriched(path: Path) -> dict[str, dict]:
    """Load fss_enriched.json keyed by 공개번호."""
    if not path.exists():
        log.warning("fss_enriched.json not found at %s — using empty", path)
        return {}
    with open(path, encoding="utf-8") as f:
        cases = json.load(f)
    return {c["공개번호"]: c for c in cases}


def build(
    scored_index: Path | None = None,
    extracted_json: Path | None = None,
    enriched_json: Path | None = None,
    output: Path | None = None,
) -> Path:
    """Join all sources and write violations.csv. Returns output path."""
    scored = _load_scored(scored_index or SCORED_INDEX)
    extracted = _load_extracted(extracted_json or EXTRACTED_JSON)
    enriched = _load_enriched(enriched_json or ENRICHED_JSON)

    # Union of all known 공개번호
    all_ids = sorted(
        set(scored) | set(extracted) | set(enriched),
        key=lambda x: scored.get(x, {}).get("번호", "0"),
        reverse=True,
    )

    rows = []
    for cid in all_ids:
        s = scored.get(cid, {})
        e = extracted.get(cid, {})
        n = enriched.get(cid, {})

        sections = e.get("sections", {})
        row = {
            # Scored index
            "공개번호": cid,
            "제목": s.get("제목", ""),
            "쟁점_분야": s.get("쟁점_분야", ""),
            "관련_기준서": s.get("관련_기준서", ""),
            "결정년도": s.get("결정년도", ""),
            "beneish_score": s.get("beneish_score", ""),
            "tier": s.get("tier", ""),
            # Extracted
            "결정일": e.get("결정일", ""),
            "회계결산일": e.get("회계결산일", ""),
            "extract_status": e.get("extract_status", ""),
            "full_text": e.get("full_text", ""),
            "s1_text": sections.get("s1", ""),
            "s2_text": sections.get("s2", ""),
            "s3_text": sections.get("s3", ""),
            "s4_text": sections.get("s4", ""),
            "s5_text": sections.get("s5", ""),
            # Enriched
            "violation_type": n.get("violation_type", ""),
            "scheme_type": n.get("scheme_type", ""),
            "beneish_components": ",".join(n.get("beneish_components") or []),
            "forensic_signals": ",".join(n.get("forensic_signals") or []),
            "key_issue": n.get("key_issue", ""),
            "fss_ruling": n.get("fss_ruling", ""),
            "implications": n.get("implications", ""),
            "enrichment_status": n.get("enrichment_status", ""),
        }
        rows.append(row)

    out = output or VIOLATIONS_CSV
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return out


def main() -> None:
    out = build()
    log.info("violations.csv written -> %s (%d rows)", out, _count_rows(out))


def _count_rows(path: Path) -> int:
    import csv as _csv
    with open(path, encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in _csv.reader(f)) - 1  # subtract header


if __name__ == "__main__":
    main()
