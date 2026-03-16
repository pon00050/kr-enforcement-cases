"""
enrich_sfc1_cases.py — Sonnet enrichment of SFC Source 1 accounting audit PDFs.

Reads sfc_source1_extracted.json. Calls Sonnet to extract the company name from
the PDF body text and classify the violation. Writes sfc_source1_enriched.json.

Key difference from enrich_source2.py: company_name is extracted from the PDF
body text, not from a pre-labelled index. Some PDF filenames use OOO placeholders
— the actual company name must be found in the body text.

No --batch flag: 29 cases is well within the range where sequential (~1 min)
is faster than Batch API (minimum 4-5 min queue overhead).

Usage:
  uv run python -m kr_enforcement_cases.enrich_sfc1_cases --limit 3       # dev
  uv run python -m kr_enforcement_cases.enrich_sfc1_cases                  # production
  uv run python -m kr_enforcement_cases.enrich_sfc1_cases --model haiku    # cost test
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from pydantic import BaseModel

from .constants import (
    BENEISH_COMPONENTS,
    FSS_VIOLATION_CATEGORIES,
    HAIKU_MODEL,
    SFC1_ENRICHMENT_SYSTEM_PROMPT,
    SCHEME_TYPES,
    SIGNAL_SEED_VOCABULARY,
    SONNET_MODEL,
)
from .paths import SFC1_ENRICHED_JSON, SFC1_EXTRACTED_JSON

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── Output model ─────────────────────────────────────────────────────────────

class EnrichedSFC1Case(BaseModel):
    meeting_folder: str
    pdf_filename: str
    decision_number: str
    company_name: str
    company_name_norm: str
    violation_type: str | None
    scheme_type: str | None
    violation_year: int | None
    beneish_components: list[str]
    forensic_signals: list[str]
    sanction_summary: str
    enrichment_status: str   # "ok" | "fallback"
    audit_years: str
    listed_status: str


# ─── Tool definition ──────────────────────────────────────────────────────────

ENRICHMENT_TOOL = {
    "name": "extract_company_metadata",
    "description": "Extract company name and forensic accounting classification from an SFC Source 1 decision letter PDF.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": (
                    "Raw company name as found in the PDF body text, including any ㈜/(주) prefix. "
                    "Look for the subject of the enforcement action, typically preceded by '피심인', '회사', "
                    "or appearing in the opening paragraphs with ㈜/주식회사 prefix. "
                    "Do NOT copy the PDF filename — read the body text."
                ),
            },
            "company_name_norm": {
                "type": "string",
                "description": "Company name with corporate form prefixes removed (주식회사, ㈜, (주), etc.).",
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
                "description": "One sentence describing the SFC's regulatory action (in English).",
            },
            "audit_years": {
                "type": "string",
                "description": "Fiscal years covered by the audit, e.g. '2021' or '2020~2022'. Empty string if not stated.",
            },
            "listed_status": {
                "type": "string",
                "description": "KOSPI, KOSDAQ, unlisted, or empty string if unknown.",
            },
        },
        "required": [
            "company_name", "company_name_norm", "violation_type", "scheme_type",
            "violation_year", "beneish_components", "forensic_signals", "sanction_summary",
        ],
    },
}


# ─── Fallback constructor ─────────────────────────────────────────────────────

def _build_fallback(entry: dict) -> EnrichedSFC1Case:
    return EnrichedSFC1Case(
        meeting_folder=entry.get("meeting_folder", ""),
        pdf_filename=entry.get("pdf_filename", ""),
        decision_number=entry.get("decision_number", ""),
        company_name="",
        company_name_norm="",
        violation_type=None,
        scheme_type=None,
        violation_year=None,
        beneish_components=[],
        forensic_signals=[],
        sanction_summary="",
        enrichment_status="fallback",
        audit_years="",
        listed_status="",
    )


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _build_prompt(entry: dict) -> str:
    return (
        f"Meeting: {entry['meeting_folder']}\n"
        f"PDF: {entry['pdf_filename']}\n"
        f"Decision: {entry.get('decision_number', '')}\n\n"
        f"Case text:\n{entry['full_text'][:5000]}"
    )


# ─── Single enrichment ────────────────────────────────────────────────────────

def _enrich_one(client, entry: dict, model: str) -> EnrichedSFC1Case:
    """Enrich a single PDF entry. Returns fallback on error."""
    prompt = _build_prompt(entry)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=SFC1_ENRICHMENT_SYSTEM_PROMPT,
            tools=[ENRICHMENT_TOOL],
            tool_choice={"type": "tool", "name": "extract_company_metadata"},
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = response.content[0].input
        return EnrichedSFC1Case(
            meeting_folder=entry.get("meeting_folder", ""),
            pdf_filename=entry.get("pdf_filename", ""),
            decision_number=entry.get("decision_number", ""),
            company_name=parsed.get("company_name") or "",
            company_name_norm=parsed.get("company_name_norm") or "",
            violation_type=parsed.get("violation_type"),
            scheme_type=parsed.get("scheme_type"),
            violation_year=parsed.get("violation_year"),
            beneish_components=parsed.get("beneish_components") or [],
            forensic_signals=parsed.get("forensic_signals") or [],
            sanction_summary=parsed.get("sanction_summary") or "",
            enrichment_status="ok",
            audit_years=parsed.get("audit_years") or "",
            listed_status=parsed.get("listed_status") or "",
        )
    except Exception as e:
        log.warning("  Enrichment failed for %s: %s", entry.get("pdf_filename"), e)
        return _build_fallback(entry)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich SFC Source 1 accounting audit PDFs via Sonnet"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max PDFs to enrich (for dev validation).",
    )
    parser.add_argument(
        "--model", default=SONNET_MODEL,
        choices=[HAIKU_MODEL, SONNET_MODEL],
        help=f"Model to use (default: {SONNET_MODEL}).",
    )
    args = parser.parse_args()

    import anthropic
    from dotenv import load_dotenv
    load_dotenv()
    client = anthropic.Anthropic()

    if not SFC1_EXTRACTED_JSON.exists():
        log.error("sfc_source1_extracted.json not found. Run parse_sfc1_pdfs first.")
        sys.exit(1)

    with open(SFC1_EXTRACTED_JSON, encoding="utf-8") as f:
        extracted = json.load(f)
    log.info("Loaded %d entries from sfc_source1_extracted.json", len(extracted))

    # Load existing enriched results (idempotent — keyed by pdf_filename)
    existing: dict[str, dict] = {}
    if SFC1_ENRICHED_JSON.exists():
        with open(SFC1_ENRICHED_JSON, encoding="utf-8") as f:
            for entry in json.load(f):
                existing[entry["pdf_filename"]] = entry
        log.info("Loaded %d existing entries from sfc_source1_enriched.json", len(existing))

    # Only process PDFs with extractable text that haven't been enriched yet
    to_enrich = [
        e for e in extracted
        if existing.get(e["pdf_filename"], {}).get("enrichment_status") not in ("ok", "pinned")
        and e.get("extract_status") == "ok"
    ]
    log.info(
        "Skipping %d already-enriched; processing %d remaining",
        len(extracted) - len(to_enrich), len(to_enrich),
    )

    if args.limit is not None:
        to_enrich = to_enrich[:args.limit]

    if not to_enrich:
        log.info("Nothing to enrich.")
        return

    log.info("Enriching %d PDFs via %s (sequential) ...", len(to_enrich), args.model)

    new_results: list[EnrichedSFC1Case] = []
    for i, entry in enumerate(to_enrich, 1):
        log.info(
            "[%d/%d] %s / %s",
            i, len(to_enrich), entry.get("meeting_folder", ""), entry.get("pdf_filename", ""),
        )
        result = _enrich_one(client, entry, args.model)
        log.info(
            "  → company=%s violation_type=%s year=%s",
            result.company_name, result.violation_type, result.violation_year,
        )
        new_results.append(result)

    # Merge into existing (never downgrade pinned entries)
    merged = dict(existing)
    for e in new_results:
        key = e.pdf_filename
        if existing.get(key, {}).get("enrichment_status") == "pinned":
            continue
        merged[key] = e.model_dump()

    merged_list = list(merged.values())
    SFC1_ENRICHED_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(SFC1_ENRICHED_JSON, "w", encoding="utf-8") as f:
        json.dump(merged_list, f, ensure_ascii=False, indent=2)

    ok_count = sum(1 for v in merged_list if v["enrichment_status"] == "ok")
    log.info("Wrote %d entries → %s", len(merged_list), SFC1_ENRICHED_JSON)
    log.info("  ok: %d | other: %d", ok_count, len(merged_list) - ok_count)


if __name__ == "__main__":
    main()
