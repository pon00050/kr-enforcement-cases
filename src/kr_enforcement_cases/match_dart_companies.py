"""
match_dart_companies.py — Match FSS Source 2 company names to DART corp_code.

Two-stage matching:
  Stage 1 — opendartreader automated lookup (deterministic)
    - Exact match → match_confidence="high"
    - No result after name variants → flag for Stage 2
    - Multiple results → flag for Stage 2
  Stage 2 — Sonnet review for ambiguous/unresolved cases (max 20 calls)
    - Sonnet selects best match or returns null

Prerequisite: DART_API_KEY in .env
  Register free at: https://opendart.fss.or.kr/

Output: data/curated/dart_matches.csv (committed — encodes name-resolution expertise)

Usage:
  uv run python -m kr_enforcement_cases.match_dart_companies --limit 10  # dev
  uv run python -m kr_enforcement_cases.match_dart_companies             # production
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from pathlib import Path

from .constants import SOURCE2_NAME_STRIP, SONNET_MODEL
from .paths import DART_MATCHES_CSV, SFC1_ENRICHED_JSON, SOURCE2_ENRICHED_JSON

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)

# Maximum Sonnet calls in Stage 2
STAGE2_CAP = 20

# Fuzzy match threshold (rapidfuzz partial_ratio)
FUZZY_THRESHOLD = 85


# ─── Name normalisation ───────────────────────────────────────────────────────

def normalise_name(name: str) -> str:
    """Strip Korean corporate form prefixes and normalise whitespace."""
    result = name.strip()
    # Sort by length descending so longer prefixes match first
    for prefix in sorted(SOURCE2_NAME_STRIP, key=len, reverse=True):
        result = result.replace(prefix, "")
    # Also strip common suffixes
    for suffix in ["㈜", "(주)", "주식회사"]:
        if result.endswith(suffix):
            result = result[:-len(suffix)]
    result = re.sub(r'\s+', ' ', result).strip()
    return result


# ─── Stage 1: opendartreader lookup ───────────────────────────────────────────

def _make_dart(api_key: str):
    """Instantiate OpenDartReader with the given API key."""
    try:
        import OpenDartReader as dart_cls  # type: ignore[import]
        return dart_cls(api_key)
    except ImportError:
        log.error("opendartreader not installed. Run: uv sync")
        return None


def _dart_lookup(
    corp_name: str,
    dart,
) -> tuple[str, str, str, str]:
    """
    Look up company in DART. Returns (corp_code, stock_code, confidence, method).

    OpenDartReader.find_corp_code(name) returns:
      - str (8-digit corp_code): exact single match → "high"
      - None: no match → try name variants → "unresolved"

    confidence: "high" | "unresolved"
    method: "dart_exact" | "dart_variant" | "unresolved"
    """
    if dart is None:
        return "", "", "unresolved", "unresolved"

    def _get_stock_code(corp_code: str) -> str:
        try:
            info = dart.company(corp_code)
            return info.get("stock_code", "") if isinstance(info, dict) else ""
        except Exception:
            return ""

    # Try 1: exact corp name
    try:
        result = dart.find_corp_code(corp_name)
        if isinstance(result, str) and len(result) == 8:
            return result, _get_stock_code(result), "high", "dart_exact"
    except Exception as e:
        log.debug("  dart.find_corp_code('%s') failed: %s", corp_name, e)

    # Try 2: name variants (partial strips)
    variants: list[str] = []
    stripped = corp_name
    for suffix in ["㈜", "(주)", "주식회사", " ", "　"]:
        if stripped.endswith(suffix):
            stripped = stripped[:-len(suffix)].strip()
            if stripped and stripped != corp_name and stripped not in variants:
                variants.append(stripped)

    for variant in variants:
        try:
            result = dart.find_corp_code(variant)
            if isinstance(result, str) and len(result) == 8:
                return result, _get_stock_code(result), "high", "dart_variant"
        except Exception:
            pass

    return "", "", "unresolved", "unresolved"


# ─── Stage 2: Sonnet review ───────────────────────────────────────────────────

def _sonnet_resolve(
    client,
    company_name: str,
    company_name_norm: str,
    violation_year: int | None,
    listed_status: str,
    candidates: list[dict],
) -> tuple[str, str]:
    """
    Ask Sonnet to select the best DART match from candidates.
    Returns (corp_code, stock_code) or ("", "") if no match.
    """
    if not candidates:
        candidate_text = "No candidates found in DART."
    else:
        lines = [f"  {i+1}. {c['corp_name']} (corp_code={c['corp_code']}, stock_code={c.get('stock_code','')})"
                 for i, c in enumerate(candidates[:10])]
        candidate_text = "\n".join(lines)

    prompt = (
        f"Match this Korean company to the correct DART corp_code.\n\n"
        f"Company: {company_name} (normalised: {company_name_norm})\n"
        f"Violation year: {violation_year}\n"
        f"Listed status: {listed_status}\n\n"
        f"DART candidates:\n{candidate_text}\n\n"
        f"Reply with ONLY the corp_code (8-digit string) of the best match, "
        f"or 'null' if none of the candidates matches. No explanation needed."
    )

    try:
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=32,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = response.content[0].text.strip()
        if answer.lower() in ("null", "none", "n/a", ""):
            return "", ""
        # Extract corp_code pattern (8 digits)
        m = re.search(r'\b(\d{8})\b', answer)
        if m:
            corp_code = m.group(1)
            # Find stock_code for this corp_code
            stock_code = ""
            for c in candidates:
                if c.get("corp_code") == corp_code:
                    stock_code = c.get("stock_code", "")
                    break
            return corp_code, stock_code
    except Exception as e:
        log.warning("  Sonnet Stage 2 failed for %s: %s", company_name, e)

    return "", ""


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Match FSS Source 2 / SFC Source 1 companies to DART corp_codes"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max companies to process (for dev validation).",
    )
    parser.add_argument(
        "--no-stage2", action="store_true",
        help="Skip Sonnet Stage 2 disambiguation (Stage 1 only).",
    )
    parser.add_argument(
        "--source", default="fss_source2", choices=["fss_source2", "sfc_source1"],
        help="Which enriched JSON to read company names from (default: fss_source2).",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    dart_api_key = os.environ.get("DART_API_KEY", "")
    if not dart_api_key:
        log.error(
            "DART_API_KEY not set in .env\n"
            "Register free at: https://opendart.fss.or.kr/\n"
            "Add to .env: DART_API_KEY=your_key_here"
        )
        sys.exit(1)

    # Load enriched data for company list
    enriched_path = SFC1_ENRICHED_JSON if args.source == "sfc_source1" else SOURCE2_ENRICHED_JSON
    if not enriched_path.exists():
        log.error("%s not found. Run the appropriate enrichment step first.", enriched_path.name)
        sys.exit(1)

    with open(enriched_path, encoding="utf-8") as f:
        enriched = json.load(f)

    log.info("Loaded %d companies from %s", len(enriched), enriched_path.name)

    # Load existing matches (idempotent); backfill source column for old rows
    existing: dict[str, dict] = {}
    if DART_MATCHES_CSV.exists():
        with open(DART_MATCHES_CSV, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                row.setdefault("source", "fss_source2")
                existing[row["company_name"]] = row
        log.info("Loaded %d existing matches from dart_matches.csv", len(existing))

    to_process = [
        e for e in enriched
        if e["company_name"] not in existing
        or existing[e["company_name"]].get("match_confidence") == "unresolved"
    ]
    if args.limit is not None:
        to_process = to_process[:args.limit]

    log.info("Processing %d companies (skipping %d already matched)", len(to_process), len(enriched) - len(to_process))

    import anthropic
    client = anthropic.Anthropic()

    dart_inst = _make_dart(dart_api_key)
    if dart_inst is None:
        sys.exit(1)

    results: list[dict] = []
    stage2_used = 0

    for i, company in enumerate(to_process, 1):
        company_name      = company["company_name"]
        company_name_norm = company.get("company_name_norm") or normalise_name(company_name)
        violation_year    = company.get("violation_year")
        listed_status     = company.get("listed_status", "")

        log.info("[%d/%d] %s (norm: %s)", i, len(to_process), company_name, company_name_norm)

        corp_code, stock_code, confidence, method = _dart_lookup(company_name_norm, dart_inst)

        # Stage 2: Sonnet for unresolved (no exact DART match found)
        if confidence == "unresolved" and not args.no_stage2 and stage2_used < STAGE2_CAP:
            log.info("  Unresolved — sending to Sonnet Stage 2 (%d/%d used)", stage2_used + 1, STAGE2_CAP)
            # Get partial-match candidates via company_by_name for Sonnet to choose from
            try:
                candidate_result = dart_inst.company_by_name(company_name_norm)
                # company_by_name returns a list of dicts
                if isinstance(candidate_result, list):
                    candidates = candidate_result
                elif hasattr(candidate_result, "to_dict"):
                    candidates = candidate_result.to_dict("records")
                else:
                    candidates = []
            except Exception:
                candidates = []

            corp_code, stock_code = _sonnet_resolve(
                client, company_name, company_name_norm, violation_year, listed_status, candidates
            )
            if corp_code:
                confidence = "medium"
                method = "sonnet"
            else:
                confidence = "unresolved"
                method = "unresolved"
            stage2_used += 1

        results.append({
            "company_name": company_name,
            "company_name_norm": company_name_norm,
            "corp_code": corp_code,
            "stock_code": stock_code,
            "match_confidence": confidence,
            "match_method": method,
            "violation_year": str(violation_year) if violation_year else "",
            "listed_status": listed_status,
            "source": args.source,
        })

        if confidence == "high":
            log.info("  → corp_code=%s stock_code=%s (high, %s)", corp_code, stock_code, method)
        else:
            log.info("  → confidence=%s method=%s", confidence, method)

    # Merge with existing
    merged = dict(existing)
    for r in results:
        # Only overwrite if we now have a better result
        prev = existing.get(r["company_name"], {})
        prev_conf = prev.get("match_confidence", "")
        if prev_conf == "high" and r["match_confidence"] != "high":
            continue  # don't downgrade
        merged[r["company_name"]] = r

    merged_list = list(merged.values())
    DART_MATCHES_CSV.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["company_name", "company_name_norm", "corp_code", "stock_code",
                  "match_confidence", "match_method", "violation_year", "listed_status", "source"]
    with open(DART_MATCHES_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged_list)

    high   = sum(1 for r in merged_list if r.get("match_confidence") == "high")
    medium = sum(1 for r in merged_list if r.get("match_confidence") == "medium")
    unres  = sum(1 for r in merged_list if r.get("match_confidence") == "unresolved")

    log.info("=== Done ===")
    log.info("  high: %d | medium: %d | unresolved: %d", high, medium, unres)
    log.info("  Sonnet Stage 2 calls used: %d/%d", stage2_used, STAGE2_CAP)
    log.info("  Written: %s", DART_MATCHES_CSV)


if __name__ == "__main__":
    main()
