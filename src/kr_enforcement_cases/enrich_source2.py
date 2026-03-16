"""
enrich_source2.py — Sonnet enrichment of FSS Source 2 named company cases.

Reads fss_source2_extracted.json (HWP text, where available) or falls back to
fss_source2_index.csv (metadata-only). Calls the model to classify each company.
Writes fss_source2_enriched.json.

Key differences from enrich_fss_cases.py:
  - Default model is Sonnet (A3 showed better calibration for labeled training data)
  - Output keyed by company_name (no 공개번호)
  - Adds company_name_norm, violation_year, sanction_summary fields
  - Metadata-only mode reads from SOURCE2_INDEX (not SCORED_INDEX)

Usage:
  uv run python -m kr_enforcement_cases.enrich_source2 --limit 3          # dev
  uv run python -m kr_enforcement_cases.enrich_source2 --batch             # production
  uv run python -m kr_enforcement_cases.enrich_source2 --metadata-only     # skip HWP text
  uv run python -m kr_enforcement_cases.enrich_source2 --limit 3 --model haiku  # cost test
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path

from pydantic import BaseModel

from .constants import (
    BENEISH_COMPONENTS,
    FSS_VIOLATION_CATEGORIES,
    HAIKU_MODEL,
    SCHEME_TYPES,
    SIGNAL_SEED_VOCABULARY,
    SONNET_MODEL,
    SOURCE2_ENRICHMENT_SYSTEM_PROMPT,
)
from .paths import (
    SOURCE2_ENRICHED_JSON,
    SOURCE2_EXTRACTED_JSON,
    SOURCE2_INDEX,
)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── Output model ─────────────────────────────────────────────────────────────

class EnrichedSource2Case(BaseModel):
    company_name: str
    company_name_norm: str
    violation_type: str | None
    scheme_type: str | None
    violation_year: int | None
    beneish_components: list[str]
    forensic_signals: list[str]
    sanction_summary: str
    enrichment_status: str   # "ok" | "metadata_only" | "fallback"
    audit_years: str
    listed_status: str


# ─── Tool definition ──────────────────────────────────────────────────────────

ENRICHMENT_TOOL = {
    "name": "extract_company_metadata",
    "description": "Extract forensic accounting classification from an FSS Source 2 company enforcement case.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name_norm": {
                "type": "string",
                "description": "Company name with corporate form prefixes removed (주식회사, ㈜, etc.).",
            },
            "violation_type": {
                "type": ["string", "null"],
                "enum": FSS_VIOLATION_CATEGORIES + [None],
            },
            "scheme_type": {
                "type": ["string", "null"],
                "enum": SCHEME_TYPES + [None],
            },
            "violation_year": {
                "type": ["integer", "null"],
                "description": "Primary fiscal year of the violation (4-digit integer). Earliest year if multi-year audit.",
            },
            "beneish_components": {
                "type": "array",
                "items": {"type": "string", "enum": BENEISH_COMPONENTS},
            },
            "forensic_signals": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(SIGNAL_SEED_VOCABULARY)},
            },
            "sanction_summary": {
                "type": "string",
                "description": "One sentence describing the regulatory action taken, in English.",
            },
        },
        "required": [
            "company_name_norm", "violation_type", "scheme_type",
            "violation_year", "beneish_components", "forensic_signals", "sanction_summary",
        ],
    },
}


# ─── Fallback constructor ─────────────────────────────────────────────────────

def _build_fallback(
    company_name: str,
    audit_years: str = "",
    listed_status: str = "",
    status: str = "fallback",
) -> EnrichedSource2Case:
    return EnrichedSource2Case(
        company_name=company_name,
        company_name_norm=company_name,
        violation_type=None,
        scheme_type=None,
        violation_year=None,
        beneish_components=[],
        forensic_signals=[],
        sanction_summary="",
        enrichment_status=status,
        audit_years=audit_years,
        listed_status=listed_status,
    )


# ─── Prompt builders ──────────────────────────────────────────────────────────

def _build_full_text_prompt(company_name: str, audit_years: str, listed_status: str, full_text: str) -> str:
    return (
        f"Company: {company_name}\n"
        f"Audit years: {audit_years}\n"
        f"Listed status: {listed_status}\n\n"
        f"Case text:\n{full_text[:4000]}"
    )


def _build_metadata_prompt(company_name: str, audit_years: str, listed_status: str) -> str:
    return (
        f"Company: {company_name}\n"
        f"Audit years: {audit_years}\n"
        f"Listed status: {listed_status}\n\n"
        f"Note: Full case text not available. Classify based on company context and audit years."
    )


# ─── Single enrichment ────────────────────────────────────────────────────────

def _parse_tool_response(
    parsed: dict,
    company_name: str,
    audit_years: str,
    listed_status: str,
    status: str,
) -> EnrichedSource2Case:
    return EnrichedSource2Case(
        company_name=company_name,
        company_name_norm=parsed.get("company_name_norm") or company_name,
        violation_type=parsed.get("violation_type"),
        scheme_type=parsed.get("scheme_type"),
        violation_year=parsed.get("violation_year"),
        beneish_components=parsed.get("beneish_components") or [],
        forensic_signals=parsed.get("forensic_signals") or [],
        sanction_summary=parsed.get("sanction_summary") or "",
        enrichment_status=status,
        audit_years=audit_years,
        listed_status=listed_status,
    )


def _enrich_one(
    client,
    company_name: str,
    audit_years: str,
    listed_status: str,
    full_text: str | None,
    model: str,
) -> EnrichedSource2Case:
    """Enrich a single company. Returns fallback on error."""
    if full_text:
        prompt = _build_full_text_prompt(company_name, audit_years, listed_status, full_text)
        status = "ok"
    else:
        prompt = _build_metadata_prompt(company_name, audit_years, listed_status)
        status = "metadata_only"
        # Metadata-only always uses Haiku (sparse signal, cost savings justified)
        model = HAIKU_MODEL

    try:
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=SOURCE2_ENRICHMENT_SYSTEM_PROMPT,
            tools=[ENRICHMENT_TOOL],
            tool_choice={"type": "tool", "name": "extract_company_metadata"},
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = response.content[0].input
        return _parse_tool_response(parsed, company_name, audit_years, listed_status, status)
    except (AttributeError, KeyError, ValueError, IndexError, Exception) as e:
        log.warning("  Enrichment failed for %s: %s", company_name, e)
        return _build_fallback(company_name, audit_years, listed_status)


# ─── Batch mode ───────────────────────────────────────────────────────────────

def _build_batch_request(
    position: int,
    company_name: str,
    audit_years: str,
    listed_status: str,
    full_text: str | None,
    model: str,
) -> dict:
    if full_text:
        prompt = _build_full_text_prompt(company_name, audit_years, listed_status, full_text)
        actual_model = model
    else:
        prompt = _build_metadata_prompt(company_name, audit_years, listed_status)
        actual_model = HAIKU_MODEL  # metadata-only always uses Haiku

    return {
        "custom_id": str(position),
        "params": {
            "model": actual_model,
            "max_tokens": 512,
            "system": SOURCE2_ENRICHMENT_SYSTEM_PROMPT,
            "tools": [ENRICHMENT_TOOL],
            "tool_choice": {"type": "tool", "name": "extract_company_metadata"},
            "messages": [{"role": "user", "content": prompt}],
        },
    }


def _parse_batch_result(
    result,
    company_name: str,
    audit_years: str,
    listed_status: str,
    has_text: bool,
) -> EnrichedSource2Case:
    try:
        if result.type != "succeeded":
            return _build_fallback(company_name, audit_years, listed_status)
        parsed = result.message.content[0].input
        status = "ok" if has_text else "metadata_only"
        return _parse_tool_response(parsed, company_name, audit_years, listed_status, status)
    except (AttributeError, KeyError, ValueError, IndexError):
        return _build_fallback(company_name, audit_years, listed_status)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich FSS Source 2 named company cases via Sonnet/Haiku"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max companies to enrich (for dev validation).",
    )
    parser.add_argument(
        "--batch", action="store_true",
        help="Use Anthropic Batch API (production).",
    )
    parser.add_argument(
        "--poll-interval", type=int, default=30,
        help="Batch poll interval in seconds (default: 30).",
    )
    parser.add_argument(
        "--metadata-only", action="store_true",
        help="Skip HWP text; classify from index metadata only.",
    )
    parser.add_argument(
        "--model", default=SONNET_MODEL,
        choices=[HAIKU_MODEL, SONNET_MODEL],
        help=(
            f"Model for full-text enrichment (default: {SONNET_MODEL}). "
            "Metadata-only always uses Haiku regardless of this flag."
        ),
    )
    args = parser.parse_args()

    import anthropic
    from dotenv import load_dotenv
    load_dotenv()
    client = anthropic.Anthropic()

    # Load index
    if not SOURCE2_INDEX.exists():
        log.error("fss_source2_index.csv not found. Run scrape_fss_source2 first.")
        sys.exit(1)

    with open(SOURCE2_INDEX, encoding="utf-8-sig", newline="") as f:
        index_rows = list(csv.DictReader(f))
    log.info("Loaded %d rows from fss_source2_index.csv", len(index_rows))

    # Load HWP extracted text (if available and not metadata-only mode)
    extracted_map: dict[str, str] = {}  # company_name → full_text
    if not args.metadata_only and SOURCE2_EXTRACTED_JSON.exists():
        with open(SOURCE2_EXTRACTED_JSON, encoding="utf-8") as f:
            for entry in json.load(f):
                if entry.get("extract_status") == "ok" and entry.get("full_text"):
                    extracted_map[entry["company_name"]] = entry["full_text"]
        log.info("Loaded HWP text for %d companies", len(extracted_map))

    # Load existing enriched results
    existing: dict[str, dict] = {}
    if SOURCE2_ENRICHED_JSON.exists():
        with open(SOURCE2_ENRICHED_JSON, encoding="utf-8") as f:
            for entry in json.load(f):
                existing[entry["company_name"]] = entry

    # Filter: skip already-ok or pinned cases
    to_enrich = [
        r for r in index_rows
        if existing.get(r["company_name"], {}).get("enrichment_status") not in ("ok", "pinned")
    ]
    if args.metadata_only:
        # In metadata-only mode, also skip metadata_only (already done)
        to_enrich = [
            r for r in to_enrich
            if existing.get(r["company_name"], {}).get("enrichment_status") != "metadata_only"
        ]

    log.info(
        "Skipping %d already-enriched; processing %d remaining",
        len(index_rows) - len(to_enrich), len(to_enrich),
    )

    if args.limit is not None:
        to_enrich = to_enrich[:args.limit]

    if not to_enrich:
        log.info("Nothing to enrich.")
        return

    mode = "batch" if args.batch else "sequential"
    log.info("Enriching %d companies via %s (%s) ...", len(to_enrich), args.model, mode)

    new_results: list[EnrichedSource2Case] = []

    if not args.batch:
        for i, row in enumerate(to_enrich, 1):
            company_name  = row["company_name"]
            audit_years   = row.get("audit_years", "")
            listed_status = row.get("listed_status", "")
            full_text     = None if args.metadata_only else extracted_map.get(company_name)

            log.info("[%d/%d] %s (%s)", i, len(to_enrich), company_name, audit_years)
            result = _enrich_one(
                client, company_name, audit_years, listed_status, full_text, args.model
            )
            new_results.append(result)

    else:
        # Batch mode
        requests_payload = []
        for i, row in enumerate(to_enrich):
            company_name  = row["company_name"]
            audit_years   = row.get("audit_years", "")
            listed_status = row.get("listed_status", "")
            full_text     = None if args.metadata_only else extracted_map.get(company_name)
            requests_payload.append(
                _build_batch_request(i, company_name, audit_years, listed_status, full_text, args.model)
            )

        batch_job = client.messages.batches.create(requests=requests_payload)
        log.info("Batch %s submitted. Polling every %ds ...", batch_job.id, args.poll_interval)

        while batch_job.processing_status != "ended":
            time.sleep(args.poll_interval)
            batch_job = client.messages.batches.retrieve(batch_job.id)
            log.info("  Status: %s", batch_job.processing_status)

        result_map: dict[int, EnrichedSource2Case] = {}
        for item in client.messages.batches.results(batch_job.id):
            pos = int(item.custom_id)
            row = to_enrich[pos]
            has_text = not args.metadata_only and row["company_name"] in extracted_map
            result_map[pos] = _parse_batch_result(
                item.result,
                row["company_name"],
                row.get("audit_years", ""),
                row.get("listed_status", ""),
                has_text,
            )

        new_results = [
            result_map.get(i, _build_fallback(r["company_name"], r.get("audit_years", ""), r.get("listed_status", "")))
            for i, r in enumerate(to_enrich)
        ]

    # Merge into existing
    merged = dict(existing)
    for e in new_results:
        key = e.company_name
        existing_status = existing.get(key, {}).get("enrichment_status")
        if existing_status == "pinned":
            continue
        if e.enrichment_status not in ("ok", "metadata_only") and existing_status in ("ok", "metadata_only", "pinned"):
            continue  # never downgrade
        merged[key] = e.model_dump()

    merged_list = list(merged.values())
    SOURCE2_ENRICHED_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCE2_ENRICHED_JSON, "w", encoding="utf-8") as f:
        json.dump(merged_list, f, ensure_ascii=False, indent=2)

    ok_count   = sum(1 for v in merged_list if v["enrichment_status"] == "ok")
    meta_count = sum(1 for v in merged_list if v["enrichment_status"] == "metadata_only")
    log.info("Wrote %d companies -> %s", len(merged_list), SOURCE2_ENRICHED_JSON)
    log.info("  ok: %d | metadata_only: %d | other: %d", ok_count, meta_count, len(merged_list) - ok_count - meta_count)


if __name__ == "__main__":
    main()
