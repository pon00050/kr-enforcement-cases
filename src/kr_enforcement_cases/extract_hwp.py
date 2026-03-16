"""
extract_hwp.py — Extract text from HWP/HWPX files downloaded from FSS Source 2.

HWP format situation:
  - Binary .hwp (HWP 5.0): no compatible library for Python 3.13.
    Returns extract_status="failed" immediately.
  - .hwpx (ZIP+XML, OWPML standard): python-hwpx primary, zipfile+XML fallback.

Never raises — mirrors the extract_status pattern from parse_fss_pdf.py.

Output: data/curated/fss_source2_extracted.json

Usage:
  uv run python -m kr_enforcement_cases.extract_hwp
  uv run python -m kr_enforcement_cases.extract_hwp --force
  uv run python -m kr_enforcement_cases.extract_hwp --limit 5
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import SOURCE2_EXTRACTED_JSON, SOURCE2_INDEX, SOURCE2_RAW_DIR

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class ExtractedHwpCase:
    company_name: str      # from index
    file_path: str         # relative path for portability
    extract_status: str    # "ok" | "failed" | "image_hwp" | "not_found"
    full_text: str
    file_format: str       # "hwpx" | "hwp5" | "unknown"
    char_count: int


# ─── HWPX extraction ──────────────────────────────────────────────────────────

def _extract_hwpx_via_library(path: Path) -> str | None:
    """Try python-hwpx library. Returns text or None on any failure."""
    try:
        from hwpx import HwpxDocument  # type: ignore[import]
        doc = HwpxDocument(str(path))
        text = doc.to_text()
        return text if text else None
    except Exception:
        return None


def _extract_hwpx_via_zipfile(path: Path) -> str | None:
    """
    Manual HWPX extraction via zipfile + XML.

    HWPX is a ZIP archive (OWPML, KS X 6101). Text content lives in
    <hp:t> elements inside Contents/section*.xml files.
    """
    try:
        texts: list[str] = []
        with zipfile.ZipFile(path, "r") as zf:
            section_files = sorted(
                [n for n in zf.namelist() if n.startswith("Contents/section") and n.endswith(".xml")]
            )
            if not section_files:
                # Some HWPX layouts use a different path
                section_files = sorted(
                    [n for n in zf.namelist() if "section" in n.lower() and n.endswith(".xml")]
                )

            for section_name in section_files:
                raw = zf.read(section_name)
                try:
                    root = ET.fromstring(raw)
                except ET.ParseError:
                    continue

                # <hp:t> elements contain text runs
                # Namespace URIs vary; search all namespaces
                for elem in root.iter():
                    local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if local == "t" and elem.text:
                        texts.append(elem.text)

        result = " ".join(texts).strip()
        return result if len(result) > 50 else None
    except Exception:
        return None


def _is_ole2(path: Path) -> bool:
    """Return True if the file is a binary OLE2 document (HWP 5.0)."""
    try:
        with open(path, "rb") as f:
            magic = f.read(8)
        return magic[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
    except Exception:
        return False


def _is_zip(path: Path) -> bool:
    """Return True if the file is a ZIP archive (potential HWPX)."""
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
        return magic == b'PK\x03\x04'
    except Exception:
        return False


# ─── Core extraction ──────────────────────────────────────────────────────────

def extract_file(path: Path, company_name: str = "") -> ExtractedHwpCase:
    """
    Extract text from a single HWP/HWPX file.
    Never raises — returns extract_status describing the outcome.
    """
    if not path.exists():
        return ExtractedHwpCase(
            company_name=company_name,
            file_path=str(path),
            extract_status="not_found",
            full_text="",
            file_format="unknown",
            char_count=0,
        )

    ext = path.suffix.lower()

    # Detect format by magic bytes (more reliable than extension)
    if _is_ole2(path):
        # Binary HWP 5.0 — no compatible Python 3.13 library
        log.debug("  Binary HWP 5.0 (OLE2): %s — extraction not supported on Python 3.13", path.name)
        return ExtractedHwpCase(
            company_name=company_name,
            file_path=str(path),
            extract_status="failed",
            full_text="",
            file_format="hwp5",
            char_count=0,
        )

    if _is_zip(path) or ext == ".hwpx":
        # HWPX — try library first, then manual ZIP+XML
        text = _extract_hwpx_via_library(path)
        if not text:
            text = _extract_hwpx_via_zipfile(path)

        if text and len(text) > 50:
            log.info("  Extracted %s: %d chars", path.name, len(text))
            return ExtractedHwpCase(
                company_name=company_name,
                file_path=str(path),
                extract_status="ok",
                full_text=text,
                file_format="hwpx",
                char_count=len(text),
            )
        else:
            log.warning("  HWPX parse yielded no text: %s", path.name)
            return ExtractedHwpCase(
                company_name=company_name,
                file_path=str(path),
                extract_status="failed",
                full_text="",
                file_format="hwpx",
                char_count=0,
            )

    # Unknown format
    log.warning("  Unknown file format: %s (ext=%s)", path.name, ext)
    return ExtractedHwpCase(
        company_name=company_name,
        file_path=str(path),
        extract_status="failed",
        full_text="",
        file_format="unknown",
        char_count=0,
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract text from FSS Source 2 HWP/HWPX files"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max files to process (for dev validation).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-extract all files even if output already exists.",
    )
    parser.add_argument(
        "--file", default=None,
        help="Extract a single specific file path (for testing).",
    )
    args = parser.parse_args()

    # Single file mode
    if args.file:
        p = Path(args.file)
        result = extract_file(p, company_name=p.stem)
        log.info(
            "Result: status=%s format=%s chars=%d",
            result.extract_status, result.file_format, result.char_count,
        )
        if result.full_text:
            preview = result.full_text[:300]
            log.info("Text preview: %s", preview)
        return

    # Load index to get company names
    company_map: dict[str, str] = {}  # filename stem → company_name
    if SOURCE2_INDEX.exists():
        with open(SOURCE2_INDEX, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                file_name = row.get("file_name", "")
                company = row.get("company_name", "")
                if file_name:
                    company_map[Path(file_name).stem] = company

    # Find all HWP/HWPX files in raw dir
    if not SOURCE2_RAW_DIR.exists():
        log.error("Source 2 raw dir not found: %s", SOURCE2_RAW_DIR)
        log.error("Run: uv run python -m kr_enforcement_cases.scrape_fss_source2 first.")
        sys.exit(1)

    hwp_files = sorted(
        SOURCE2_RAW_DIR.glob("*.hwp")
    ) + sorted(SOURCE2_RAW_DIR.glob("*.hwpx"))

    if not hwp_files:
        log.error("No HWP/HWPX files found in %s", SOURCE2_RAW_DIR)
        sys.exit(1)

    log.info("Found %d HWP/HWPX files in %s", len(hwp_files), SOURCE2_RAW_DIR)

    # Load existing extracted results
    existing: dict[str, dict] = {}
    if SOURCE2_EXTRACTED_JSON.exists() and not args.force:
        with open(SOURCE2_EXTRACTED_JSON, encoding="utf-8") as f:
            for entry in json.load(f):
                existing[entry["file_path"]] = entry

    to_process = hwp_files
    if args.limit is not None:
        to_process = to_process[:args.limit]

    results: list[ExtractedHwpCase] = []
    ok_count = fail_count = skip_count = 0

    for i, path in enumerate(to_process, 1):
        key = str(path)
        company_name = company_map.get(path.stem, path.stem)

        if key in existing and not args.force:
            log.info("[%d/%d] Skip (cached): %s", i, len(to_process), path.name)
            results.append(ExtractedHwpCase(**existing[key]))
            skip_count += 1
            continue

        log.info("[%d/%d] Extracting: %s (%s)", i, len(to_process), path.name, company_name)
        result = extract_file(path, company_name=company_name)
        results.append(result)

        if result.extract_status == "ok":
            ok_count += 1
        else:
            fail_count += 1

    # Merge with existing (all files, not just processed)
    all_results = dict(existing)
    for r in results:
        all_results[r.file_path] = asdict(r)

    SOURCE2_EXTRACTED_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCE2_EXTRACTED_JSON, "w", encoding="utf-8") as f:
        json.dump(list(all_results.values()), f, ensure_ascii=False, indent=2)

    log.info("=== Extraction summary ===")
    log.info("  ok: %d | failed: %d | skipped: %d", ok_count, fail_count, skip_count)
    log.info("  Total in output: %d", len(all_results))
    log.info("  Written: %s", SOURCE2_EXTRACTED_JSON)

    if ok_count == 0 and fail_count > 0:
        log.warning(
            "All files failed to extract. Most files are likely binary HWP 5.0. "
            "Proceeding with metadata-only enrichment for all 71 cases is required. "
            "Run: uv run python -m kr_enforcement_cases.enrich_source2 --metadata-only"
        )


if __name__ == "__main__":
    main()
