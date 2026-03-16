"""
enrich_fss_cases.py — Haiku enrichment of FSS enforcement cases.

Reads fss_extracted.json, calls Haiku to classify each case, writes fss_enriched.json.
Mirrors the sequential/batch dual-mode pattern from jfia-forensic/enrichment.py.

Usage:
  uv run python -m kr_enforcement_cases.enrich_fss_cases --limit 3
  uv run python -m kr_enforcement_cases.enrich_fss_cases --batch
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from pydantic import BaseModel

from .constants import (
    BENEISH_COMPONENTS,
    FSS_BLIND_TEST_SYSTEM_PROMPT,
    FSS_ENRICHMENT_SYSTEM_PROMPT,
    FSS_VIOLATION_CATEGORIES,
    HAIKU_MODEL,
    SCHEME_TYPES,
    SIGNAL_SEED_VOCABULARY,
    SONNET_MODEL,
)
from .paths import (
    BLIND_TEST_JSON,
    CURATED_DIR,
    ENRICHED_JSON,
    EXTRACTED_JSON,
    SCORED_INDEX,
    SONNET_REVIEW_JSON,
)

MANUAL_PATCHES = CURATED_DIR / "manual_patches.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── Output model ─────────────────────────────────────────────────────────────

class EnrichedCase(BaseModel):
    공개번호: str
    violation_type: str | None
    scheme_type: str | None
    beneish_components: list[str]
    forensic_signals: list[str]
    key_issue: str
    fss_ruling: str
    implications: str
    enrichment_status: str   # "ok" | "fallback" | "image_pdf" | "not_downloaded"


# ─── Tool definition ──────────────────────────────────────────────────────────

ENRICHMENT_TOOL = {
    "name": "extract_case_metadata",
    "description": "Extract forensic accounting classification from an FSS enforcement case.",
    "input_schema": {
        "type": "object",
        "properties": {
            "violation_type": {
                "type": ["string", "null"],
                "enum": FSS_VIOLATION_CATEGORIES + [None],
            },
            "scheme_type": {
                "type": ["string", "null"],
                "enum": SCHEME_TYPES + [None],
            },
            "beneish_components": {
                "type": "array",
                "items": {"type": "string", "enum": BENEISH_COMPONENTS},
            },
            "forensic_signals": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(SIGNAL_SEED_VOCABULARY)},
            },
            "key_issue": {"type": "string"},
            "fss_ruling": {"type": "string"},
            "implications": {"type": "string"},
        },
        "required": [
            "violation_type", "scheme_type", "beneish_components",
            "forensic_signals", "key_issue", "fss_ruling", "implications",
        ],
    },
}


METADATA_ENRICHMENT_TOOL = {
    "name": "extract_case_metadata",
    "description": "Classify an FSS enforcement case from index metadata.",
    "input_schema": {
        "type": "object",
        "properties": {
            "violation_type": {
                "type": ["string", "null"],
                "enum": FSS_VIOLATION_CATEGORIES + [None],
            },
            "scheme_type": {
                "type": ["string", "null"],
                "enum": SCHEME_TYPES + [None],
            },
            "beneish_components": {
                "type": "array",
                "items": {"type": "string", "enum": BENEISH_COMPONENTS},
            },
            "forensic_signals": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(SIGNAL_SEED_VOCABULARY)},
            },
        },
        "required": ["violation_type", "scheme_type", "beneish_components", "forensic_signals"],
    },
}


# ─── Fallback constructor ─────────────────────────────────────────────────────

def _build_fallback(공개번호: str, status: str = "fallback") -> EnrichedCase:
    return EnrichedCase(
        공개번호=공개번호,
        violation_type=None,
        scheme_type=None,
        beneish_components=[],
        forensic_signals=[],
        key_issue="",
        fss_ruling="",
        implications="",
        enrichment_status=status,
    )


# ─── Input builder ────────────────────────────────────────────────────────────

def _build_prompt(case: dict) -> str:
    """Build the user prompt for a single case. Uses section-condensed text if available."""
    sections = case.get("sections", {})
    if sections:
        # s1 = company treatment, s3 = FSS reasoning, s5 = implications
        content = "\n\n".join(
            v for k, v in sections.items()
            if k in ("s1", "s3", "s5") and v
        )
        if not content:
            content = case.get("full_text", "")
    else:
        content = case.get("full_text", "")

    return f"Case ID: {case['공개번호']}\n\n{content}"


# ─── Sequential mode ──────────────────────────────────────────────────────────

def _enrich_one(
    client,
    case: dict,
    model: str = HAIKU_MODEL,
    system: str = FSS_ENRICHMENT_SYSTEM_PROMPT,
) -> EnrichedCase:
    """Enrich a single case. Returns fallback on per-item error."""
    status = case.get("extract_status", "failed")
    if status == "image_pdf":
        return _build_fallback(case["공개번호"], "image_pdf")
    if status in ("failed", "not_found"):
        return _build_fallback(case["공개번호"], "not_downloaded")
    if not case.get("full_text"):
        return _build_fallback(case["공개번호"], "fallback")

    prompt = _build_prompt(case)

    response = client.messages.create(
        model=model,
        max_tokens=768,
        system=system,
        tools=[ENRICHMENT_TOOL],
        tool_choice={"type": "tool", "name": "extract_case_metadata"},
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        parsed = response.content[0].input
        return EnrichedCase(
            공개번호=case["공개번호"],
            violation_type=parsed.get("violation_type"),
            scheme_type=parsed.get("scheme_type"),
            beneish_components=parsed.get("beneish_components") or [],
            forensic_signals=parsed.get("forensic_signals") or [],
            key_issue=parsed.get("key_issue") or "",
            fss_ruling=parsed.get("fss_ruling") or "",
            implications=parsed.get("implications") or "",
            enrichment_status="ok",
        )
    except (AttributeError, KeyError, ValueError, IndexError):
        return _build_fallback(case["공개번호"])


# ─── Batch mode ───────────────────────────────────────────────────────────────

def _build_batch_request(
    position: int,
    case: dict,
    model: str = HAIKU_MODEL,
    system: str = FSS_ENRICHMENT_SYSTEM_PROMPT,
) -> dict:
    return {
        "custom_id": str(position),
        "params": {
            "model": model,
            "max_tokens": 768,
            "system": system,
            "tools": [ENRICHMENT_TOOL],
            "tool_choice": {"type": "tool", "name": "extract_case_metadata"},
            "messages": [{"role": "user", "content": _build_prompt(case)}],
        },
    }


def _parse_batch_result(result, case: dict) -> EnrichedCase:
    try:
        if result.type != "succeeded":
            return _build_fallback(case["공개번호"])
        parsed = result.message.content[0].input
        return EnrichedCase(
            공개번호=case["공개번호"],
            violation_type=parsed.get("violation_type"),
            scheme_type=parsed.get("scheme_type"),
            beneish_components=parsed.get("beneish_components") or [],
            forensic_signals=parsed.get("forensic_signals") or [],
            key_issue=parsed.get("key_issue") or "",
            fss_ruling=parsed.get("fss_ruling") or "",
            implications=parsed.get("implications") or "",
            enrichment_status="ok",
        )
    except (AttributeError, KeyError, ValueError, IndexError):
        return _build_fallback(case["공개번호"])


# ─── Metadata-only mode ───────────────────────────────────────────────────────

def _build_metadata_prompt(row: dict) -> str:
    return (
        f"Case: {row['공개번호']}\n"
        f"Title: {row['제목']}\n"
        f"Dispute area: {row['쟁점_분야']}\n"
        f"K-IFRS ref: {row['관련_기준서']}\n"
        f"Year: {row['결정년도']}"
    )


def _enrich_one_metadata(client, row: dict) -> EnrichedCase:
    """Enrich a single case from index metadata only. Returns fallback for annual summaries."""
    if str(row.get("공개번호", "")).startswith("FSS/BATCH-"):
        return _build_fallback(row["공개번호"], "fallback")

    prompt = _build_metadata_prompt(row)
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=256,
        system=FSS_ENRICHMENT_SYSTEM_PROMPT,
        tools=[METADATA_ENRICHMENT_TOOL],
        tool_choice={"type": "tool", "name": "extract_case_metadata"},
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        parsed = response.content[0].input
        return EnrichedCase(
            공개번호=row["공개번호"],
            violation_type=parsed.get("violation_type"),
            scheme_type=parsed.get("scheme_type"),
            beneish_components=parsed.get("beneish_components") or [],
            forensic_signals=parsed.get("forensic_signals") or [],
            key_issue="",
            fss_ruling="",
            implications="",
            enrichment_status="metadata_only",
        )
    except (AttributeError, KeyError, ValueError, IndexError):
        return _build_fallback(row["공개번호"])


def _build_metadata_batch_request(position: int, row: dict) -> dict:
    return {
        "custom_id": str(position),
        "params": {
            "model": HAIKU_MODEL,
            "max_tokens": 256,
            "system": FSS_ENRICHMENT_SYSTEM_PROMPT,
            "tools": [METADATA_ENRICHMENT_TOOL],
            "tool_choice": {"type": "tool", "name": "extract_case_metadata"},
            "messages": [{"role": "user", "content": _build_metadata_prompt(row)}],
        },
    }


def _parse_metadata_batch_result(result, row: dict) -> EnrichedCase:
    try:
        if result.type != "succeeded":
            return _build_fallback(row["공개번호"])
        parsed = result.message.content[0].input
        return EnrichedCase(
            공개번호=row["공개번호"],
            violation_type=parsed.get("violation_type"),
            scheme_type=parsed.get("scheme_type"),
            beneish_components=parsed.get("beneish_components") or [],
            forensic_signals=parsed.get("forensic_signals") or [],
            key_issue="",
            fss_ruling="",
            implications="",
            enrichment_status="metadata_only",
        )
    except (AttributeError, KeyError, ValueError, IndexError):
        return _build_fallback(row["공개번호"])


def enrich_cases_metadata(
    rows: list[dict],
    client,
    limit: int | None = None,
    batch: bool = False,
    poll_interval: int = 30,
) -> list[EnrichedCase]:
    """
    Enrich FSS cases from scored_index.csv metadata only (no PDF text).

    Skips annual summary rows (공개번호 starts with FSS/BATCH-).
    batch=False: sequential. batch=True: Anthropic Batch API.
    """
    eligible = [r for r in rows if not str(r.get("공개번호", "")).startswith("FSS/BATCH-")]
    if limit is not None:
        eligible = eligible[:limit]

    log.info("Metadata-only enrichment: %d eligible rows", len(eligible))

    if not batch:
        results = []
        for i, row in enumerate(eligible, 1):
            enriched = _enrich_one_metadata(client, row)
            results.append(enriched)
            if i % 20 == 0:
                log.info("  Enriched %d/%d...", i, len(eligible))
        return results

    # Batch path
    requests_payload = [_build_metadata_batch_request(i, r) for i, r in enumerate(eligible)]
    batch_job = client.messages.batches.create(requests=requests_payload)
    log.info("Batch %s submitted. Polling every %ds...", batch_job.id, poll_interval)

    while batch_job.processing_status != "ended":
        time.sleep(poll_interval)
        batch_job = client.messages.batches.retrieve(batch_job.id)
        log.info("  Status: %s", batch_job.processing_status)

    result_map: dict[int, EnrichedCase] = {}
    for item in client.messages.batches.results(batch_job.id):
        pos = int(item.custom_id)
        result_map[pos] = _parse_metadata_batch_result(item.result, eligible[pos])

    return [
        result_map.get(i, _build_fallback(r["공개번호"]))
        for i, r in enumerate(eligible)
    ]


# ─── Main enrichment function ─────────────────────────────────────────────────

def enrich_cases(
    cases: list[dict],
    client,
    limit: int | None = None,
    batch: bool = False,
    poll_interval: int = 30,
    model: str = HAIKU_MODEL,
    system: str = FSS_ENRICHMENT_SYSTEM_PROMPT,
) -> list[EnrichedCase]:
    """
    Enrich FSS cases using the given model and system prompt.

    batch=False: sequential, one API call per case.
    batch=True: Anthropic Batch API; polls every poll_interval seconds.
    limit: truncates case list before processing.
    model: override the default Haiku model (e.g. SONNET_MODEL for A3).
    system: override the system prompt (e.g. FSS_BLIND_TEST_SYSTEM_PROMPT for A2).
    """
    if limit is not None:
        cases = cases[:limit]

    if not batch:
        results = []
        for i, case in enumerate(cases, 1):
            enriched = _enrich_one(client, case, model=model, system=system)
            results.append(enriched)
            if i % 20 == 0:
                log.info("  Enriched %d/%d...", i, len(cases))
        return results

    # Batch path — only submit cases that have extractable text
    eligible = [
        (i, c) for i, c in enumerate(cases)
        if c.get("extract_status") not in ("image_pdf", "failed", "not_found")
        and c.get("full_text")
    ]
    log.info(
        "Submitting %d/%d cases to Batch API...", len(eligible), len(cases)
    )

    requests_payload = [_build_batch_request(i, c, model=model, system=system) for i, c in eligible]
    batch_job = client.messages.batches.create(requests=requests_payload)
    log.info("Batch %s submitted. Polling every %ds...", batch_job.id, poll_interval)

    while batch_job.processing_status != "ended":
        time.sleep(poll_interval)
        batch_job = client.messages.batches.retrieve(batch_job.id)
        log.info("  Status: %s", batch_job.processing_status)

    result_map: dict[int, EnrichedCase] = {}
    for item in client.messages.batches.results(batch_job.id):
        pos = int(item.custom_id)
        result_map[pos] = _parse_batch_result(item.result, cases[pos])

    return [
        result_map.get(i, _build_fallback(c["공개번호"]))
        for i, c in enumerate(cases)
    ]


# ─── Manual patches ───────────────────────────────────────────────────────────

def _apply_manual_patches(cases: list[dict]) -> list[dict]:
    """Apply manual_patches.json overrides. Patches merge field-by-field, not replace."""
    if not MANUAL_PATCHES.exists():
        return cases
    with open(MANUAL_PATCHES, encoding="utf-8") as f:
        patches = {p["공개번호"]: p for p in json.load(f)}
    if not patches:
        return cases
    result = []
    for c in cases:
        pid = c["공개번호"]
        if pid in patches:
            c = {**c, **patches[pid]}
            log.info("  Patch applied: %s", pid)
        result.append(c)
    return result


# ─── Validation sample selection (A2 / A3) ────────────────────────────────────

def _select_validation_sample(
    enriched_json: Path,
    extracted_json: Path,
    n_per_stratum: int = 5,
) -> list[dict]:
    """
    Return a stratified sample of ok cases for blind-test / model-comparison runs.

    Strata: asset_inflation, revenue_fabrication, disclosure_fraud, _other.
    Returns up to n_per_stratum cases per stratum, merged with extracted full text.
    """
    with open(enriched_json, encoding="utf-8") as f:
        enriched = {e["공개번호"]: e for e in json.load(f)}
    with open(extracted_json, encoding="utf-8") as f:
        extracted = {e["공개번호"]: e for e in json.load(f)}

    strata: dict[str, list[dict]] = {
        "asset_inflation": [],
        "revenue_fabrication": [],
        "disclosure_fraud": [],
        "_other": [],
    }
    for cid, e in enriched.items():
        if e.get("enrichment_status") != "ok":
            continue
        ext = extracted.get(cid)
        if not ext or not ext.get("full_text"):
            continue
        merged = {**ext, **e}  # extracted base + enriched metadata
        vtype = e.get("violation_type") or ""
        key = vtype if vtype in strata else "_other"
        strata[key].append(merged)

    selected = []
    for stratum_cases in strata.values():
        selected.extend(stratum_cases[:n_per_stratum])

    log.info(
        "Validation sample: %d cases (%s)",
        len(selected),
        ", ".join(f"{k}={len(v[:n_per_stratum])}" for k, v in strata.items()),
    )
    return selected


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    import csv
    import anthropic
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Enrich FSS enforcement cases via Haiku"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max cases to enrich (for dev validation).",
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
        help="Read scored_index.csv, skip already-enriched cases, merge into fss_enriched.json.",
    )
    parser.add_argument(
        "--blind-test", action="store_true",
        help=(
            "A2: Re-enrich 20 stratified ok cases with stripped Beneish prompt "
            "(FSS_BLIND_TEST_SYSTEM_PROMPT). Output: fss_blind_test.json."
        ),
    )
    parser.add_argument(
        "--model", default=HAIKU_MODEL,
        choices=[HAIKU_MODEL, SONNET_MODEL],
        help=(
            f"Model to use (default: {HAIKU_MODEL}). "
            f"Use '{SONNET_MODEL}' for A3 independent spot-check."
        ),
    )
    args = parser.parse_args()

    client = anthropic.Anthropic()
    mode = "batch" if args.batch else "sequential"

    # ── Validation modes: A2 (blind-test) ────────────────────────────────────
    if args.blind_test:
        if not ENRICHED_JSON.exists():
            log.error("fss_enriched.json not found — run enrich_fss_cases first.")
            sys.exit(1)
        if not EXTRACTED_JSON.exists():
            log.error("fss_extracted.json not found — run parse_fss_pdf first.")
            sys.exit(1)

        cases = _select_validation_sample(ENRICHED_JSON, EXTRACTED_JSON)

        if args.blind_test:
            system_prompt = FSS_BLIND_TEST_SYSTEM_PROMPT
            out_path = BLIND_TEST_JSON
            label = "blind-test"
        else:
            system_prompt = FSS_ENRICHMENT_SYSTEM_PROMPT
            out_path = SONNET_REVIEW_JSON
            label = "sonnet-review"

        log.info(
            "Validation enrichment (%s): %d cases, model=%s, mode=%s",
            label, len(cases), args.model, mode,
        )

        validated = enrich_cases(
            cases, client,
            batch=args.batch,
            poll_interval=args.poll_interval,
            model=args.model,
            system=system_prompt,
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump([e.model_dump() for e in validated], f, ensure_ascii=False, indent=2)
        log.info("Wrote %d validation cases -> %s", len(validated), out_path)
        return

    if args.metadata_only:
        if not SCORED_INDEX.exists():
            log.error(
                "scored_index.csv not found. "
                "Run: uv run python -m kr_enforcement_cases.score_cases"
            )
            sys.exit(1)

        with open(SCORED_INDEX, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        log.info("Loaded %d rows from scored_index.csv", len(rows))

        # Load existing enriched results (if any)
        existing: dict[str, dict] = {}
        if ENRICHED_JSON.exists():
            with open(ENRICHED_JSON, encoding="utf-8") as f:
                for entry in json.load(f):
                    existing[entry["공개번호"]] = entry

        # Skip cases already fully enriched or manually pinned
        to_enrich = [
            r for r in rows
            if existing.get(r["공개번호"], {}).get("enrichment_status") not in ("ok", "pinned")
        ]
        log.info(
            "Skipping %d already-ok cases; enriching %d remaining",
            len(rows) - len(to_enrich), len(to_enrich),
        )
        log.info("Enriching via %s (%s, metadata-only)...", HAIKU_MODEL, mode)

        new_results = enrich_cases_metadata(
            to_enrich, client,
            limit=args.limit,
            batch=args.batch,
            poll_interval=args.poll_interval,
        )

        # Merge: existing takes precedence for "ok" entries; new results overwrite others
        merged = dict(existing)
        for e in new_results:
            merged[e.공개번호] = e.model_dump()

        merged_list = _apply_manual_patches(list(merged.values()))
        ENRICHED_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(ENRICHED_JSON, "w", encoding="utf-8") as f:
            json.dump(merged_list, f, ensure_ascii=False, indent=2)

        ok = sum(1 for v in merged_list if v["enrichment_status"] == "ok")
        meta = sum(1 for v in merged_list if v["enrichment_status"] == "metadata_only")
        log.info("Wrote %d total cases -> %s", len(merged_list), ENRICHED_JSON)
        log.info("  ok: %d | metadata_only: %d | other: %d", ok, meta, len(merged_list) - ok - meta)
        return

    if not EXTRACTED_JSON.exists():
        log.error(
            "fss_extracted.json not found. "
            "Run: uv run python -m kr_enforcement_cases.parse_fss_pdf"
        )
        sys.exit(1)

    with open(EXTRACTED_JSON, encoding="utf-8") as f:
        cases = json.load(f)
    log.info("Loaded %d extracted cases", len(cases))

    log.info("Enriching via %s (%s)...", args.model, mode)

    enriched = enrich_cases(
        cases, client,
        limit=args.limit,
        batch=args.batch,
        poll_interval=args.poll_interval,
        model=args.model,
    )

    # Merge: preserve existing metadata_only / pinned cases; new results overwrite ok/fallback
    existing: dict[str, dict] = {}
    if ENRICHED_JSON.exists():
        with open(ENRICHED_JSON, encoding="utf-8") as f:
            for entry in json.load(f):
                existing[entry["공개번호"]] = entry

    merged = dict(existing)
    for e in enriched:
        pid = e.공개번호
        existing_status = existing.get(pid, {}).get("enrichment_status")
        if existing_status == "pinned":
            continue  # never overwrite manual pins
        if e.enrichment_status != "ok" and existing_status in ("ok", "metadata_only", "pinned"):
            continue  # never downgrade a good result with a fallback
        merged[pid] = e.model_dump()

    merged_list = _apply_manual_patches(list(merged.values()))
    ENRICHED_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(ENRICHED_JSON, "w", encoding="utf-8") as f:
        json.dump(merged_list, f, ensure_ascii=False, indent=2)

    ok = sum(1 for e in merged_list if e["enrichment_status"] == "ok")
    meta = sum(1 for e in merged_list if e["enrichment_status"] == "metadata_only")
    log.info("Wrote %d total cases -> %s", len(merged_list), ENRICHED_JSON)
    log.info("  ok: %d | metadata_only: %d | other: %d", ok, meta, len(merged_list) - ok - meta)


if __name__ == "__main__":
    main()
