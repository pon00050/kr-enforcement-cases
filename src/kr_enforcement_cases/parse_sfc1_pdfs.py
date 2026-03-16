"""
parse_sfc1_pdfs.py — Extract text from SFC Source 1 accounting audit PDFs.

Walks data/raw/SFC Source 1/, filters to accounting audit PDFs by filename,
deduplicates by decision number + meeting year, and extracts full text via
pdfplumber (pypdfium2 fallback).

Output: data/curated/sfc_source1_extracted.json

Usage:
  uv run python -m kr_enforcement_cases.parse_sfc1_pdfs
  uv run python -m kr_enforcement_cases.parse_sfc1_pdfs --force
  uv run python -m kr_enforcement_cases.parse_sfc1_pdfs --limit 5
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from .paths import SFC1_EXTRACTED_JSON, SFC1_MINUTES_DIR, SFC1_RAW_DIR

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)

# Filename keywords that identify accounting audit PDFs
ACCOUNTING_KEYWORDS = [
    "감리결과",
    "조사감리",
    "조사·감리",
    "조사ㆍ감리",
    "위탁감리결과",
]

# Regex to extract decision number from filename
_RE_DECISION = re.compile(r'의결\s*(\d+(?:\(\d+\))?)', re.UNICODE)

# Regex to extract 4-digit year from folder name
_RE_YEAR = re.compile(r'(\d{4})')


def _is_accounting_pdf(filename: str) -> bool:
    """Return True if filename indicates an accounting audit PDF."""
    if not filename.startswith("(의결서)"):
        return False
    return any(kw in filename for kw in ACCOUNTING_KEYWORDS)


def _parse_decision_number(filename: str) -> str:
    """Extract decision number from filename, e.g. '의결174' → '174'."""
    m = _RE_DECISION.search(filename)
    return m.group(1) if m else ""


def _folder_year(folder_name: str) -> str:
    """Extract the first 4-digit year from a folder name."""
    m = _RE_YEAR.search(folder_name)
    return m.group(1) if m else ""


def _folder_score(path: Path) -> int:
    """
    Score a PDF path for deduplication preference. Lower = better.
    Prefer non-의사록 folders; prefer (의결서) prefix over (공개용).
    """
    score = 0
    if "의사록" in path.parent.name:
        score += 10
    if path.name.startswith("(공개용)"):
        score += 1
    return score


def _extract_text(path: Path) -> tuple[str, str]:
    """
    Extract full text from a PDF. Returns (full_text, extract_status).
    extract_status: "ok" | "image_pdf" | "failed". Never raises.
    """
    try:
        import pdfplumber
    except ImportError:
        return "", "failed"

    try:
        with pdfplumber.open(path) as pdf:
            pages: list[str] = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
            full_text = "\n".join(pages).strip()
    except Exception as exc:
        log.warning("pdfplumber failed for %s: %s — trying pypdfium2...", path.name, exc)
        try:
            import pypdfium2 as pdfium  # type: ignore[import]
            doc = pdfium.PdfDocument(str(path))
            pages = []
            for i in range(len(doc)):
                textpage = doc[i].get_textpage()
                t = textpage.get_text_range()
                if t:
                    pages.append(t)
            full_text = "\n".join(pages).strip()
        except Exception as exc2:
            log.warning("pypdfium2 also failed for %s: %s", path.name, exc2)
            return "", "failed"

    if len(full_text) < 50:
        return full_text, "image_pdf"
    return full_text, "ok"


def collect_pdfs(raw_dir: Path) -> list[Path]:
    """
    Walk raw_dir recursively, collect accounting audit PDFs, and deduplicate.

    Deduplication key: (decision_number, meeting_year).
    When the same decision appears in both a '의사록' folder and a dedicated
    '안건 및 제재안건 의결서' folder, prefer the non-의사록 folder.
    For '(공개용)' vs '(의결서)' prefix variants, prefer '(의결서)'.
    """
    candidates: list[Path] = []
    for p in raw_dir.rglob("*.pdf"):
        # Skip minutes directory
        try:
            p.relative_to(SFC1_MINUTES_DIR)
            continue  # path is inside minutes dir — skip
        except ValueError:
            pass
        if _is_accounting_pdf(p.name):
            candidates.append(p)

    # Deduplicate: for each (decision_number, year) key keep the best-scored path
    seen: dict[tuple[str, str], tuple[Path, int]] = {}
    for p in candidates:
        dec_num = _parse_decision_number(p.name)
        year = _folder_year(p.parent.name)
        key = (dec_num, year)
        score = _folder_score(p)
        if key not in seen or score < seen[key][1]:
            seen[key] = (p, score)

    return sorted(p for p, _ in seen.values())


def extract_all(raw_dir: Path | None = None, limit: int | None = None) -> list[dict]:
    """Extract text from all accounting audit PDFs. Returns list of entry dicts."""
    src_dir = raw_dir or SFC1_RAW_DIR
    pdfs = collect_pdfs(src_dir)
    log.info("Found %d unique accounting audit PDFs after deduplication", len(pdfs))

    if limit is not None:
        pdfs = pdfs[:limit]

    results: list[dict] = []
    for i, pdf in enumerate(pdfs, 1):
        log.info("[%d/%d] %s / %s", i, len(pdfs), pdf.parent.name, pdf.name)
        decision_number = _parse_decision_number(pdf.name)
        full_text, status = _extract_text(pdf)
        results.append({
            "meeting_folder": pdf.parent.name,
            "pdf_filename": pdf.name,
            "pdf_path": str(pdf),
            "decision_number": decision_number,
            "extract_status": status,
            "full_text": full_text,
            "char_count": len(full_text),
        })
        log.info("  → status=%s chars=%d", status, len(full_text))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract text from SFC Source 1 accounting audit PDFs"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing sfc_source1_extracted.json.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max PDFs to extract (for dev validation).",
    )
    args = parser.parse_args()

    if SFC1_EXTRACTED_JSON.exists() and not args.force:
        log.info("sfc_source1_extracted.json already exists. Use --force to overwrite.")
        sys.exit(0)

    results = extract_all(limit=args.limit)

    SFC1_EXTRACTED_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(SFC1_EXTRACTED_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    status_counts: dict[str, int] = {}
    for r in results:
        status_counts[r["extract_status"]] = status_counts.get(r["extract_status"], 0) + 1

    log.info("Extracted %d PDFs → %s", len(results), SFC1_EXTRACTED_JSON)
    for status, count in sorted(status_counts.items()):
        log.info("  %s: %d", status, count)


if __name__ == "__main__":
    main()
