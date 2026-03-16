"""
compute_beneish.py — Compute Beneish M-Score components from DART financial statements.

For each matched company in dart_matches.csv, fetches DART annual financial statements
for violation_year (t), t-1, and t-2. Computes all 7 Beneish components per year.

Each Beneish ratio requires the current year AND prior year values:
  - DART finstate(corp_code, year) returns thstrm (current) + frmtrm (prior)
  - So one API call gives us the ratio for a given year
  - 3 calls per company: finstate(t), finstate(t-1), finstate(t-2)

Prerequisite: DART_API_KEY in .env, dart_matches.csv populated.

Output: reports/beneish_ratios.csv (committed — empirical output)

Usage:
  uv run python -m kr_enforcement_cases.compute_beneish --limit 5   # dev
  uv run python -m kr_enforcement_cases.compute_beneish             # production
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

from .constants import BENEISH_COMPONENTS, DART_ACCOUNT_MAP
from .paths import BENEISH_RATIOS_CSV, DART_MATCHES_CSV, SFC1_ENRICHED_JSON, SOURCE2_ENRICHED_JSON

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)

# Minimum violation year for reliable DART XBRL data
MIN_VIOLATION_YEAR = 2016


# ─── DART data fetching ───────────────────────────────────────────────────────

def _parse_amount(val: str | None) -> float | None:
    """Convert DART amount string to float. Returns None if empty or non-numeric."""
    if not val or str(val).strip() in ("", "-", "－"):
        return None
    cleaned = re.sub(r'[,\s]', '', str(val))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fetch_finstate(
    dart,
    corp_code: str,
    year: int,
) -> dict[str, dict[str, float]] | None:
    """
    Fetch annual financial statement from DART for the given corp and year.

    Uses finstate_all (detailed line items) with CFS preferred, OFS fallback.

    Returns:
      {
        "current": {"sales": X, "receivables": Y, ...},  # thstrm (year)
        "prior":   {"sales": X, "receivables": Y, ...},  # frmtrm (year-1)
        "fs_div":  "CFS" | "OFS" | "unknown",
      }
    or None on failure.
    """
    from rapidfuzz import fuzz  # type: ignore[import]

    def _try_fs_div(fs_div: str):
        try:
            df = dart.finstate_all(corp_code, year, fs_div=fs_div)
            if df is None or len(df) == 0:
                return None, None
            return df, fs_div
        except Exception as e:
            log.debug("  finstate_all(%s, %s, %d) failed: %s", corp_code, fs_div, year, e)
            return None, None

    df, fs_div_detected = _try_fs_div("CFS")
    if df is None:
        df, fs_div_detected = _try_fs_div("OFS")
    if df is None:
        return None

    current_vals: dict[str, float] = {}
    prior_vals: dict[str, float] = {}

    for _, row in df.iterrows():
        account_nm = str(row.get("account_nm", "")).strip()
        thstrm = _parse_amount(row.get("thstrm_amount"))
        frmtrm = _parse_amount(row.get("frmtrm_amount"))

        # Try exact mapping first
        canonical = DART_ACCOUNT_MAP.get(account_nm)

        # Fuzzy fallback
        if not canonical:
            best_score = 0
            best_key = None
            for dart_name, can_name in DART_ACCOUNT_MAP.items():
                score = fuzz.ratio(account_nm, dart_name)
                if score > best_score:
                    best_score = score
                    best_key = can_name
            if best_score >= 85 and best_key:
                canonical = best_key

        if not canonical:
            continue

        # First occurrence wins (higher-level aggregated item appears first)
        if canonical not in current_vals and thstrm is not None:
            current_vals[canonical] = thstrm
        if canonical not in prior_vals and frmtrm is not None:
            prior_vals[canonical] = frmtrm

    if not current_vals:
        return None

    return {"current": current_vals, "prior": prior_vals, "fs_div": fs_div_detected or "unknown"}


# ─── Beneish component calculations ──────────────────────────────────────────

def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def compute_beneish_ratios(
    current: dict[str, float],
    prior: dict[str, float],
) -> tuple[dict[str, float | None], list[str]]:
    """
    Compute all 7 Beneish components from current and prior year account values.

    Returns (components_dict, missing_accounts_list).
    Components are None when required accounts are missing.

    Formulas (Beneish 1999):
      DSRI = (Recv_t / Sales_t) / (Recv_{t-1} / Sales_{t-1})
      GMI  = ((Sales_{t-1} - COGS_{t-1}) / Sales_{t-1}) / ((Sales_t - COGS_t) / Sales_t)
      AQI  = (1 - (CA_t + PPE_t) / TA_t) / (1 - (CA_{t-1} + PPE_{t-1}) / TA_{t-1})
      SGI  = Sales_t / Sales_{t-1}
      DEPI = (Dep_{t-1} / (Dep_{t-1} + PPE_{t-1})) / (Dep_t / (Dep_t + PPE_t))
      SGAI = (SGA_t / Sales_t) / (SGA_{t-1} / Sales_{t-1})  [often missing]
      LVGI = ((LTD_t + CL_t) / TA_t) / ((LTD_{t-1} + CL_{t-1}) / TA_{t-1})
      TATA = (NetInc_t - OpCF_t) / TA_t
    """
    missing: list[str] = []

    def get_c(field: str) -> float | None:
        v = current.get(field)
        if v is None:
            missing.append(field)
        return v

    def get_p(field: str) -> float | None:
        v = prior.get(field)
        if v is None:
            if f"{field}_prior" not in missing:
                missing.append(f"{field}(prior)")
        return v

    # ── DSRI ──────────────────────────────────────────────────────────────────
    recv_c  = get_c("receivables");  sales_c = get_c("sales")
    recv_p  = get_p("receivables");  sales_p = get_p("sales")
    dsri_t = _safe_div(recv_c, sales_c)
    dsri_p = _safe_div(recv_p, sales_p)
    DSRI = _safe_div(dsri_t, dsri_p)

    # ── GMI ───────────────────────────────────────────────────────────────────
    cogs_c = get_c("cogs");  cogs_p = get_p("cogs")
    if sales_c and cogs_c:
        gm_c = (sales_c - cogs_c) / sales_c
    else:
        gm_c = None
        if "cogs" not in missing:
            missing.append("cogs")
    if sales_p and cogs_p:
        gm_p = (sales_p - cogs_p) / sales_p
    else:
        gm_p = None
    GMI = _safe_div(gm_p, gm_c)  # prior / current (index > 1 = margin deteriorated)

    # ── AQI ───────────────────────────────────────────────────────────────────
    ca_c  = get_c("current_assets"); ppe_c = get_c("ppe"); ta_c = get_c("total_assets")
    ca_p  = get_p("current_assets"); ppe_p = get_p("ppe"); ta_p = get_p("total_assets")
    if ca_c is not None and ppe_c is not None and ta_c:
        aq_c = 1 - (ca_c + ppe_c) / ta_c
    else:
        aq_c = None
    if ca_p is not None and ppe_p is not None and ta_p:
        aq_p = 1 - (ca_p + ppe_p) / ta_p
    else:
        aq_p = None
    AQI = _safe_div(aq_c, aq_p)  # current / prior

    # ── SGI ───────────────────────────────────────────────────────────────────
    SGI = _safe_div(sales_c, sales_p)

    # ── DEPI ──────────────────────────────────────────────────────────────────
    dep_c = get_c("depreciation"); dep_p = get_p("depreciation")
    if dep_c is not None and ppe_c is not None:
        dep_rate_c = _safe_div(dep_c, dep_c + ppe_c)
    else:
        dep_rate_c = None
    if dep_p is not None and ppe_p is not None:
        dep_rate_p = _safe_div(dep_p, dep_p + ppe_p)
    else:
        dep_rate_p = None
    DEPI = _safe_div(dep_rate_p, dep_rate_c)  # prior / current

    # ── SGAI (often missing in DART) ─────────────────────────────────────────
    sga_c = current.get("sga")  # don't add to missing if absent — expected
    sga_p = prior.get("sga")
    if sga_c is not None and sales_c and sga_p is not None and sales_p:
        SGAI = _safe_div(sga_c / sales_c, sga_p / sales_p)
    else:
        SGAI = None

    # ── LVGI ──────────────────────────────────────────────────────────────────
    ltd_c = current.get("long_term_debt") or current.get("noncurrent_liabilities")
    ltd_p = prior.get("long_term_debt") or prior.get("noncurrent_liabilities")
    cl_c  = get_c("current_liabilities")
    cl_p  = get_p("current_liabilities")
    if ltd_c is not None and cl_c is not None and ta_c:
        lev_c = (ltd_c + cl_c) / ta_c
    else:
        lev_c = None
    if ltd_p is not None and cl_p is not None and ta_p:
        lev_p = (ltd_p + cl_p) / ta_p
    else:
        lev_p = None
    LVGI = _safe_div(lev_c, lev_p)  # current / prior

    # ── TATA ──────────────────────────────────────────────────────────────────
    net_inc_c  = get_c("net_income")
    op_cf_c    = get_c("operating_cf")
    TATA = _safe_div(
        (net_inc_c - op_cf_c) if (net_inc_c is not None and op_cf_c is not None) else None,
        ta_c,
    )

    components = {
        "DSRI": DSRI,
        "GMI":  GMI,
        "AQI":  AQI,
        "SGI":  SGI,
        "DEPI": DEPI,
        "SGAI": SGAI,
        "LVGI": LVGI,
        "TATA": TATA,
    }

    # Deduplicate missing list
    missing_deduped = list(dict.fromkeys(missing))
    return components, missing_deduped


def compute_m_score(components: dict[str, float | None]) -> float | None:
    """
    Beneish M-Score composite:
    M = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
           + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

    Core components (DSRI, GMI, AQI, SGI, LVGI, TATA) are required.
    DEPI and SGAI are optional — DART finstate_all rarely reports depreciation
    as a main statement line item, and SG&A may be absent for some companies.
    When optional components are absent, M-Score is computed without their contribution.
    """
    required = {"DSRI": 0.920, "GMI": 0.528, "AQI": 0.404, "SGI": 0.892,
                "LVGI": -0.327, "TATA": 4.679}
    optional = {"DEPI": 0.115, "SGAI": -0.172}
    intercept = -4.84

    total = intercept
    for comp, weight in required.items():
        val = components.get(comp)
        if val is None:
            return None
        total += weight * val

    for comp, weight in optional.items():
        val = components.get(comp)
        if val is not None:
            total += weight * val

    return total


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute Beneish M-Score components from DART financial statements"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max companies to process (for dev validation).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-compute even if output already exists.",
    )
    parser.add_argument(
        "--source", default="fss_source2", choices=["fss_source2", "sfc_source1"],
        help="Which source's companies to process (default: fss_source2).",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    dart_api_key = os.environ.get("DART_API_KEY", "")
    if not dart_api_key:
        log.error("DART_API_KEY not set in .env")
        sys.exit(1)

    try:
        import OpenDartReader as dart_cls  # type: ignore[import]
        dart = dart_cls(dart_api_key)
    except ImportError:
        log.error("opendartreader not installed. Run: uv sync")
        sys.exit(1)

    # Load DART matches
    if not DART_MATCHES_CSV.exists():
        log.error("dart_matches.csv not found. Run match_dart_companies first.")
        sys.exit(1)

    with open(DART_MATCHES_CSV, encoding="utf-8-sig", newline="") as f:
        all_matches = [r for r in csv.DictReader(f) if r.get("corp_code")]
        for r in all_matches:
            r.setdefault("source", "fss_source2")

    log.info("Loaded %d matched companies from dart_matches.csv", len(all_matches))

    # Load enriched data for violation_type (source-specific)
    vtype_map: dict[str, str] = {}
    enriched_path = SFC1_ENRICHED_JSON if args.source == "sfc_source1" else SOURCE2_ENRICHED_JSON
    if enriched_path.exists():
        with open(enriched_path, encoding="utf-8") as f:
            for entry in json.load(f):
                vtype_map[entry["company_name"]] = entry.get("violation_type") or ""

    # Load existing results (idempotent); backfill source column for old rows
    existing: set[tuple[str, int]] = set()
    if BENEISH_RATIOS_CSV.exists() and not args.force:
        with open(BENEISH_RATIOS_CSV, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                row.setdefault("source", "fss_source2")
                if row.get("corp_code") and row.get("year"):
                    existing.add((row["corp_code"], int(row["year"])))
        log.info("Loaded %d existing rows from beneish_ratios.csv", len(existing))

    # Filter to selected source
    matches = [
        m for m in all_matches
        if m.get("source", "fss_source2") == args.source
    ]
    log.info("Processing %d companies from source=%s", len(matches), args.source)

    to_process = [
        m for m in matches
        if m.get("match_confidence") in ("high", "medium") and m.get("violation_year")
    ]
    if args.limit is not None:
        to_process = to_process[:args.limit]

    log.info("Processing %d companies with valid corp_code + violation_year", len(to_process))

    new_rows: list[dict] = []

    for i, match in enumerate(to_process, 1):
        company_name      = match["company_name"]
        corp_code         = match["corp_code"]
        violation_year_s  = match.get("violation_year", "")
        violation_type    = vtype_map.get(company_name, "")

        if not violation_year_s or not violation_year_s.isdigit():
            log.warning("[%d/%d] %s — missing violation_year, skipping", i, len(to_process), company_name)
            continue

        violation_year = int(violation_year_s)
        if violation_year < MIN_VIOLATION_YEAR:
            log.warning("[%d/%d] %s — violation_year %d < %d, skipping",
                        i, len(to_process), company_name, violation_year, MIN_VIOLATION_YEAR)
            continue

        log.info("[%d/%d] %s — corp_code=%s violation_year=%d", i, len(to_process), company_name, corp_code, violation_year)

        for year_offset in [0, -1, -2]:
            year = violation_year + year_offset
            if (corp_code, year) in existing:
                log.debug("  Skip year=%d (cached)", year)
                continue

            log.info("  Fetching DART finstate year=%d ...", year)
            data = _fetch_finstate(dart, corp_code, year)
            if data is None:
                log.warning("  No data for year=%d", year)
                continue

            current   = data["current"]
            prior_yr  = data["prior"]
            fs_div    = data["fs_div"]

            components, missing_accounts = compute_beneish_ratios(current, prior_yr)
            m_score = compute_m_score(components)

            row: dict = {
                "company_name_norm": match.get("company_name_norm", company_name),
                "corp_code": corp_code,
                "violation_year": violation_year,
                "year": year,
                "year_offset": year_offset,
                "violation_type": violation_type,
                "source": args.source,
                "fs_div": fs_div,
                "accounts_missing": ",".join(missing_accounts),
                "M_score": f"{m_score:.4f}" if m_score is not None else "",
            }
            for comp in BENEISH_COMPONENTS:
                val = components.get(comp)
                row[comp] = f"{val:.4f}" if val is not None else ""

            new_rows.append(row)

    # Load all existing rows to merge; backfill source column
    all_rows: list[dict] = []
    if BENEISH_RATIOS_CSV.exists() and not args.force:
        with open(BENEISH_RATIOS_CSV, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                row.setdefault("source", "fss_source2")
                all_rows.append(row)

    all_rows.extend(new_rows)

    fieldnames = [
        "company_name_norm", "corp_code", "violation_year", "year", "year_offset",
        "violation_type", "source", "fs_div", "accounts_missing", "M_score",
    ] + BENEISH_COMPONENTS

    BENEISH_RATIOS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(BENEISH_RATIOS_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    log.info("=== Done ===")
    log.info("  New rows computed: %d", len(new_rows))
    log.info("  Total rows in output: %d", len(all_rows))
    log.info("  Written: %s", BENEISH_RATIOS_CSV)

    # Quick sanity summary
    with_mscore = sum(1 for r in all_rows if r.get("M_score"))
    log.info("  Rows with M_score: %d / %d", with_mscore, len(all_rows))


if __name__ == "__main__":
    main()
