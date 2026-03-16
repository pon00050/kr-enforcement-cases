"""
download_prioritised.py — Selective download of FSS PDFs by tier.

Reads scored_index.csv, downloads PDFs for cases at or above the specified tier.
Idempotent — skips already-downloaded PDFs.

Usage:
  uv run python -m kr_enforcement_cases.download_prioritised --tier 1
  uv run python -m kr_enforcement_cases.download_prioritised --tier 2
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

import requests

from .paths import RAW_DIR, SCORED_INDEX
from .scrape_fss_cases import download_pdf, HEADERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)


def load_scored_index(path: Path | None = None) -> list[dict]:
    p = path or SCORED_INDEX
    if not p.exists():
        raise FileNotFoundError(
            f"Scored index not found at {p}. "
            "Run: uv run python -m kr_enforcement_cases.score_cases"
        )
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def download_tier(
    tier_max: int,
    sleep: float = 1.5,
    raw_dir: Path | None = None,
    scored_index: Path | None = None,
) -> tuple[int, int, int]:
    """
    Download PDFs for cases where tier <= tier_max.
    Returns (downloaded, skipped, failed).
    """
    rows = load_scored_index(scored_index)
    dest_dir = raw_dir or RAW_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    targets = [r for r in rows if int(r["tier"]) <= tier_max and r.get("atch_file_id")]
    log.info("Tier <= %d: %d downloadable cases", tier_max, len(targets))

    session = requests.Session()
    downloaded = skipped = failed = 0

    for i, row in enumerate(targets, 1):
        pdf_path = dest_dir / row["pdf_filename"]
        log.info("[%d/%d] %s", i, len(targets), row["공개번호"])
        ok = download_pdf(session, row["atch_file_id"], pdf_path, sleep)
        if ok:
            if pdf_path.stat().st_size > 1000 and not _was_just_written(pdf_path):
                skipped += 1
            else:
                downloaded += 1
        else:
            failed += 1

    return downloaded, skipped, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download FSS PDFs for cases at or above a specified tier"
    )
    parser.add_argument(
        "--tier", type=int, default=1, choices=[1, 2, 3],
        help="Download Tier 1 only (default), Tier 1+2, or all tiers.",
    )
    parser.add_argument(
        "--sleep", type=float, default=1.5,
        help="Seconds between requests (default: 1.5).",
    )
    args = parser.parse_args()

    downloaded, skipped, failed = download_tier(args.tier, args.sleep)
    log.info("Done — downloaded: %d | skipped: %d | failed: %d",
             downloaded, skipped, failed)


if __name__ == "__main__":
    main()
