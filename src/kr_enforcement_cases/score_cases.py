"""
score_cases.py — Metadata scoring + tiered download priority for FSS enforcement cases.

Scoring formula (max 10 pts):
  Beneish relevance (0–5): keyword match on 쟁점_분야
  K-IFRS standard bonus (0–2): K-IFRS 1115/1018/1011/1002 → +2; 1036/1038 → +1
  Recency (0–2): 2022+ → +2; 2018–2021 → +1; ≤2017 → +0
  Structured format (0–1): 공개번호 non-empty → +1

Tiers: 7–10 = Tier 1, 4–6 = Tier 2, 0–3 = Tier 3

Output: reports/scored_index.csv

Usage:
  uv run python -m kr_enforcement_cases.score_cases
"""

from __future__ import annotations

import csv
import logging
import re
import sys
from pathlib import Path

from .paths import INDEX_PATH, REPORTS_DIR, SCORED_INDEX

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)

# ─── Keyword tables for Beneish relevance ─────────────────────────────────────

_BENEISH_KEYWORDS: list[tuple[int, list[str]]] = [
    (5, ["매출", "수익인식", "매출원가"]),
    (4, ["매출채권", "대손충당금", "재고자산", "허위", "가공", "횡령"]),
    (3, ["무형자산", "개발비", "유형자산", "손상차손", "선급금"]),
    (2, ["충당부채", "부채", "퇴직급여"]),
    (1, ["관계기업", "종속기업", "금융자산"]),
    # 0 pts: 파생상품, 리스, 사용권 — explicitly not in Beneish
]

_KIFRS_BONUS_2: set[str] = {"1115", "1018", "1011", "1002"}
_KIFRS_BONUS_1: set[str] = {"1036", "1038"}


# ─── Pure scoring functions ────────────────────────────────────────────────────

def score_beneish(쟁점_분야: str) -> int:
    """Return 0–5 Beneish relevance score based on keyword match."""
    for pts, keywords in _BENEISH_KEYWORDS:
        if any(kw in 쟁점_분야 for kw in keywords):
            return pts
    return 0


def score_kifrs(관련_기준서: str) -> int:
    """Return 0–2 K-IFRS standard bonus."""
    numbers = re.findall(r"1\d{3}", 관련_기준서)
    for n in numbers:
        if n in _KIFRS_BONUS_2:
            return 2
    for n in numbers:
        if n in _KIFRS_BONUS_1:
            return 1
    return 0


def score_recency(결정년도: str) -> int:
    """Return 0–2 recency score."""
    try:
        year = int(결정년도)
    except (ValueError, TypeError):
        return 0
    if year >= 2022:
        return 2
    if year >= 2018:
        return 1
    return 0


def score_structured(공개번호: str) -> int:
    """Return 0–1 structured format bonus."""
    return 1 if 공개번호.strip() else 0


def compute_score(
    쟁점_분야: str,
    관련_기준서: str,
    결정년도: str,
    공개번호: str,
) -> tuple[int, int]:
    """Return (beneish_score, tier)."""
    score = (
        score_beneish(쟁점_분야)
        + score_kifrs(관련_기준서)
        + score_recency(결정년도)
        + score_structured(공개번호)
    )
    if score >= 7:
        tier = 1
    elif score >= 4:
        tier = 2
    else:
        tier = 3
    return score, tier


# ─── I/O ──────────────────────────────────────────────────────────────────────

def load_index(path: Path | None = None) -> list[dict]:
    """Load fss_enforcement_index.csv, return list of row dicts."""
    p = path or INDEX_PATH
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def score_index(rows: list[dict]) -> list[dict]:
    """Add beneish_score and tier columns to each row."""
    out = []
    for row in rows:
        score, tier = compute_score(
            row.get("쟁점_분야", ""),
            row.get("관련_기준서", ""),
            row.get("결정년도", ""),
            row.get("공개번호", ""),
        )
        out.append({**row, "beneish_score": score, "tier": tier})
    return out


def save_scored_index(rows: list[dict], path: Path | None = None) -> Path:
    """Write scored_index.csv. Returns the path written."""
    p = path or SCORED_INDEX
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("No rows to write")
    fieldnames = list(rows[0].keys())
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return p


def main() -> None:
    log.info("Loading index from %s", INDEX_PATH)
    rows = load_index()
    log.info("  %d cases loaded", len(rows))

    scored = score_index(rows)

    tier_counts = {1: 0, 2: 0, 3: 0}
    for r in scored:
        tier_counts[r["tier"]] += 1

    out = save_scored_index(scored)
    log.info("Scored index saved: %s", out)
    log.info("  Tier 1 (7–10): %d cases", tier_counts[1])
    log.info("  Tier 2 (4–6):  %d cases", tier_counts[2])
    log.info("  Tier 3 (0–3):  %d cases", tier_counts[3])


if __name__ == "__main__":
    main()
