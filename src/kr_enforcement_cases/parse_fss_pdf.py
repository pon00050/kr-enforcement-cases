"""
parse_fss_pdf.py — Deterministic PDF extraction for FSS enforcement cases.

Extracts full text, section splits (s1–s5), and header metadata from PDFs using
pdfplumber. Never raises — returns extract_status='failed' on error.

Output: data/curated/fss_extracted.json — list of ExtractedCase dicts.

Usage:
  uv run python -m kr_enforcement_cases.parse_fss_pdf
  uv run python -m kr_enforcement_cases.parse_fss_pdf --force
  uv run python -m kr_enforcement_cases.parse_fss_pdf --tier 2
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import (
    CURATED_DIR,
    EXTRACTED_JSON,
    RAW_DIR,
    SCORED_INDEX,
    INDEX_PATH,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)

# ─── Section header patterns ───────────────────────────────────────────────────

# Each tuple: (section_key, list of Korean header strings to match)
_SECTION_HEADERS: list[tuple[str, list[str]]] = [
    ("s1", ["회사의 회계처리"]),
    ("s2", ["위반 지적", "위반내용", "지적사항"]),
    ("s3", ["판단 근거", "판단근거"]),
    ("s4", ["감사절차 미흡", "감사절차미흡"]),
    ("s5", ["시사점"]),
]

# PDF header metadata patterns
_RE_결정일 = re.compile(r"결정일\s*[:\uff1a]\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2})")
_RE_회계결산일 = re.compile(r"회계결산일\s*[:\uff1a]\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2})")


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class ExtractedCase:
    공개번호: str
    pdf_path: str                  # stored as string for JSON serialisation
    extract_status: str            # "ok" | "partial" | "image_pdf" | "failed" | "not_found"
    full_text: str
    sections: dict[str, str]       # s1..s5 if detectable; empty if not
    결정일: str                     # from PDF header regex; empty if not found
    회계결산일: str                   # from PDF header regex; empty if not found


# ─── Core extraction ──────────────────────────────────────────────────────────

def _split_sections(text: str) -> dict[str, str]:
    """Split full_text into s1..s5 by FSS section headers. Best-effort."""
    # Find positions of known headers
    hits: list[tuple[int, str]] = []
    for key, patterns in _SECTION_HEADERS:
        for pat in patterns:
            idx = text.find(pat)
            if idx != -1:
                hits.append((idx, key))
                break  # first matching pattern wins for this section

    if not hits:
        return {}

    hits.sort()
    sections: dict[str, str] = {}
    for i, (start, key) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        sections[key] = text[start:end].strip()

    return sections


def _extract_header_dates(text: str) -> tuple[str, str]:
    """Extract 결정일 and 회계결산일 from PDF header block. Returns ('', '') if not found."""
    m1 = _RE_결정일.search(text[:2000])   # limit search to header area
    m2 = _RE_회계결산일.search(text[:2000])
    return (m1.group(1) if m1 else ""), (m2.group(1) if m2 else "")


def extract_pdf(path: Path) -> ExtractedCase:
    """Extract text and metadata from a single PDF. Never raises."""
    try:
        import pdfplumber
    except ImportError:
        return ExtractedCase(
            공개번호=path.stem,
            pdf_path=str(path),
            extract_status="failed",
            full_text="",
            sections={},
            결정일="",
            회계결산일="",
        )

    # Derive 공개번호 from filename: FSS2505_06.pdf → FSS/2505-06
    stem = path.stem  # e.g. FSS2512_10
    m = re.match(r"FSS(\d{4})_(\d+)", stem)
    공개번호 = f"FSS/{m.group(1)}-{m.group(2)}" if m else stem

    try:
        with pdfplumber.open(path) as pdf:
            pages_text = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
            full_text = "\n".join(pages_text).strip()
    except Exception as exc:
        log.warning("pdfplumber failed for %s: %s — trying pypdfium2...", path.name, exc)
        try:
            import pypdfium2 as pdfium  # type: ignore[import]
            doc = pdfium.PdfDocument(str(path))
            pages_text = []
            for i in range(len(doc)):
                textpage = doc[i].get_textpage()
                t = textpage.get_text_range()
                if t:
                    pages_text.append(t)
            full_text = "\n".join(pages_text).strip()
        except Exception as exc2:
            log.warning("pypdfium2 also failed for %s: %s", path.name, exc2)
            return ExtractedCase(
                공개번호=공개번호,
                pdf_path=str(path),
                extract_status="failed",
                full_text="",
                sections={},
                결정일="",
                회계결산일="",
            )

    if len(full_text) < 50:
        return ExtractedCase(
            공개번호=공개번호,
            pdf_path=str(path),
            extract_status="image_pdf",
            full_text=full_text,
            sections={},
            결정일="",
            회계결산일="",
        )

    sections = _split_sections(full_text)
    결정일, 회계결산일 = _extract_header_dates(full_text)
    status = "ok" if sections else "partial"

    return ExtractedCase(
        공개번호=공개번호,
        pdf_path=str(path),
        extract_status=status,
        full_text=full_text,
        sections=sections,
        결정일=결정일,
        회계결산일=회계결산일,
    )


# ─── Batch extraction ─────────────────────────────────────────────────────────

def _load_tier_filenames(scored_index: Path, tier_max: int) -> set[str]:
    """Return set of pdf_filenames for cases at or above the given tier."""
    if not scored_index.exists():
        return set()
    with open(scored_index, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return {r["pdf_filename"] for r in rows if int(r.get("tier", 3)) <= tier_max}


def extract_all(
    raw_dir: Path | None = None,
    scored_index: Path | None = None,
    tier_max: int = 1,
) -> list[ExtractedCase]:
    """
    Extract all downloaded PDFs at or above tier_max.
    Falls back to extracting ALL PDFs in raw_dir if scored_index is absent.
    """
    src_dir = raw_dir or RAW_DIR
    si_path = scored_index or SCORED_INDEX

    allowed = _load_tier_filenames(si_path, tier_max)
    pdfs = sorted(src_dir.glob("*.pdf"))

    if allowed:
        pdfs = [p for p in pdfs if p.name in allowed]

    log.info("Extracting %d PDFs (tier <= %d) ...", len(pdfs), tier_max)
    results: list[ExtractedCase] = []
    for i, pdf in enumerate(pdfs, 1):
        log.info("[%d/%d] %s", i, len(pdfs), pdf.name)
        results.append(extract_pdf(pdf))

    return results


# ─── Persistence ──────────────────────────────────────────────────────────────

def save_extracted(cases: list[ExtractedCase], path: Path | None = None) -> Path:
    p = path or EXTRACTED_JSON
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump([asdict(c) for c in cases], f, ensure_ascii=False, indent=2)
    return p


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic PDF extraction for FSS enforcement cases"
    )
    parser.add_argument(
        "--tier", type=int, default=1, choices=[1, 2, 3],
        help="Extract PDFs up to this tier (default: 1).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing fss_extracted.json.",
    )
    args = parser.parse_args()

    out_path = EXTRACTED_JSON
    if out_path.exists() and not args.force:
        log.info("fss_extracted.json already exists. Use --force to overwrite.")
        sys.exit(0)

    cases = extract_all(tier_max=args.tier)
    out = save_extracted(cases)

    status_counts: dict[str, int] = {}
    for c in cases:
        status_counts[c.extract_status] = status_counts.get(c.extract_status, 0) + 1

    log.info("Extracted %d cases -> %s", len(cases), out)
    for status, count in sorted(status_counts.items()):
        log.info("  %s: %d", status, count)


if __name__ == "__main__":
    main()
