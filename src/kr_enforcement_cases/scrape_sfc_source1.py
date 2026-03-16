"""
scrape_sfc_source1.py — Index and selectively download SFC 증선위의결정보 accounting audit PDFs.

Source: https://fsc.go.kr/no020102
Records: 503 "의사록" meetings (POST search), each with a minutes PDF + ZIP of decision letters.

Three-phase approach (run in order):
  Phase 1 --index-only   : Scrape all 503 records → sfc_source1_index.csv (no downloads)
  Phase 2 --minutes      : Download minutes PDFs, scan for accounting keywords, flag meetings
  Phase 3 --download     : Download ZIPs only for flagged meetings, extract accounting PDFs

Accounting filter (PDF filename must start with "(의결서)" AND contain one of):
  조사감리결과 | 위탁감리결과 | 감사보고서.*감리 | 회계감리결과

Output layout:
  data/processed/sfc_source1_index.csv          — meeting index with has_accounting flag
  data/raw/SFC Source 1/minutes/                — minutes PDFs (scanning use; kept for audit)
  data/raw/SFC Source 1/{meeting_title}/        — accounting decision PDFs (의결서 only)

Usage:
  uv run python -m kr_enforcement_cases.scrape_sfc_source1 --index-only
  uv run python -m kr_enforcement_cases.scrape_sfc_source1 --minutes
  uv run python -m kr_enforcement_cases.scrape_sfc_source1 --download
  uv run python -m kr_enforcement_cases.scrape_sfc_source1 --pages 1-3 --index-only  # dev
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
import time
import zipfile
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import pdfplumber

from .paths import SFC1_INDEX, SFC1_MINUTES_DIR, SFC1_RAW_DIR, PROCESSED_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

BASE_URL   = "https://fsc.go.kr"
SEARCH_URL = f"{BASE_URL}/no020102"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer":         SEARCH_URL,
}
DEFAULT_SLEEP = 1.5

# Keywords that identify accounting audit items in minutes PDF text
MINUTES_KEYWORDS = ["조사감리결과", "위탁감리결과", "회계감리결과", "감사보고서"]

# Filename patterns for target PDFs inside ZIPs:
#   must start with "(의결서)" AND contain one of these substrings
DECISION_FILE_KEYWORDS = ["조사감리결과", "위탁감리결과", "회계감리결과", "감사보고서"]

INDEX_FIELDS = [
    "post_id", "title", "date",
    "minutes_filename", "minutes_url",
    "zip_filename", "zip_url", "zip_size_kb",
    "has_accounting",      # "" | "yes" | "no"
    "accounting_pdfs",     # semicolon-separated filenames extracted from ZIP
]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    s = requests.Session()
    s.get(SEARCH_URL, headers=HEADERS, timeout=30)  # seed session cookie
    return s


def _fetch_search_page(session: requests.Session, page: int) -> BeautifulSoup:
    resp = session.post(
        SEARCH_URL,
        data={"srchCtgry": "", "srchKey": "sj", "srchText": "의사록", "curPage": str(page)},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _parse_records(soup: BeautifulSoup) -> list[dict]:
    records = []
    for li in soup.select("div.board-list-wrap ul li"):
        subject_a = li.select_one("div.subject a")
        day_div   = li.select_one("div.day")
        if not subject_a:
            continue

        post_id = None
        for part in subject_a.get("href", "").split("/"):
            candidate = part.split("?")[0]
            if candidate.isdigit():
                post_id = int(candidate)
                break

        minutes_filename = minutes_url = ""
        zip_filename = zip_url = zip_size_kb = ""

        for fl in li.select("div.file-list"):
            a     = fl.select_one("a[href*='getFile']")
            spans = fl.select("span.name")
            if not a:
                continue
            fname = a.get("title", "")
            url   = BASE_URL + a["href"]
            size  = spans[1].text.strip() if len(spans) > 1 else ""

            if fname.endswith(".zip"):
                zip_filename = fname
                zip_url      = url
                zip_size_kb  = size
            elif fname.endswith(".pdf") and "의사록" in fname:
                minutes_filename = fname
                minutes_url      = url

        if post_id is None:
            continue

        records.append({
            "post_id":          post_id,
            "title":            subject_a.get("title", "").strip(),
            "date":             day_div.text.strip() if day_div else "",
            "minutes_filename": minutes_filename,
            "minutes_url":      minutes_url,
            "zip_filename":     zip_filename,
            "zip_url":          zip_url,
            "zip_size_kb":      zip_size_kb,
            "has_accounting":   "",
            "accounting_pdfs":  "",
        })
    return records


def _safe_dirname(title: str) -> str:
    """Sanitize meeting title for use as a directory name."""
    return re.sub(r'[<>:"/\\|?*]', "_", title).strip()


def _is_accounting_pdf(filename: str) -> bool:
    """Return True if this ZIP member is an accounting audit decision letter."""
    if not filename.startswith("(의결서)"):
        return False
    return any(kw in filename for kw in DECISION_FILE_KEYWORDS)


def _minutes_has_accounting(pdf_bytes: bytes) -> bool:
    """Return True if the minutes PDF mentions accounting audit keywords."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if any(kw in text for kw in MINUTES_KEYWORDS):
                    return True
    except Exception as e:
        log.warning("  pdfplumber failed on minutes: %s", e)
    return False


def _load_index() -> dict[int, dict]:
    """Load existing index CSV keyed by post_id."""
    existing: dict[int, dict] = {}
    if SFC1_INDEX.exists():
        with open(SFC1_INDEX, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                try:
                    existing[int(row["post_id"])] = row
                except (KeyError, ValueError):
                    pass
    return existing


def _save_index(records: list[dict]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(SFC1_INDEX, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    log.info("Saved %d records → %s", len(records), SFC1_INDEX)


# ─── Phase 1: Index ───────────────────────────────────────────────────────────

def phase_index(page_range: tuple[int, int], sleep: float) -> None:
    """Scrape all 의사록 search results and write sfc_source1_index.csv."""
    existing = _load_index()
    session  = _make_session()

    # Probe total pages
    soup0  = _fetch_search_page(session, 1)
    total_el = soup0.select_one("div.board-total-wrap strong")
    total_str = total_el.text if total_el else "?"
    log.info("Total 의사록 records: %s", total_str)

    start_page, end_page = page_range
    all_records: dict[int, dict] = dict(existing)

    for page in range(start_page, end_page + 1):
        log.info("Fetching page %d/%d ...", page, end_page)
        soup    = _fetch_search_page(session, page) if page > 1 else soup0
        records = _parse_records(soup)
        log.info("  Parsed %d records", len(records))
        for r in records:
            pid = r["post_id"]
            if pid in existing:
                # Preserve has_accounting / accounting_pdfs from existing
                r["has_accounting"] = existing[pid].get("has_accounting", "")
                r["accounting_pdfs"] = existing[pid].get("accounting_pdfs", "")
            all_records[pid] = r
        time.sleep(sleep)

    merged = sorted(all_records.values(), key=lambda r: r["post_id"], reverse=True)
    _save_index(merged)

    has_zip  = sum(1 for r in merged if r["zip_url"])
    no_zip   = sum(1 for r in merged if not r["zip_url"])
    log.info("Records with ZIP: %d | without ZIP: %d", has_zip, no_zip)


# ─── Phase 2: Minutes scan ────────────────────────────────────────────────────

def phase_minutes(limit: int | None, sleep: float) -> None:
    """Download minutes PDFs, scan for accounting keywords, update has_accounting."""
    existing = _load_index()
    if not existing:
        log.error("No index found. Run --index-only first.")
        sys.exit(1)

    SFC1_MINUTES_DIR.mkdir(parents=True, exist_ok=True)
    session = _make_session()

    to_scan = [
        r for r in existing.values()
        if r.get("minutes_url") and r.get("has_accounting") == ""
    ]
    if limit is not None:
        to_scan = to_scan[:limit]

    log.info("Minutes to scan: %d (already flagged: %d)",
             len(to_scan),
             sum(1 for r in existing.values() if r.get("has_accounting") != ""))

    for i, r in enumerate(to_scan, 1):
        pid   = int(r["post_id"])
        fname = r["minutes_filename"] or f"{pid}_minutes.pdf"
        out   = SFC1_MINUTES_DIR / fname
        log.info("[%d/%d] %s", i, len(to_scan), r["title"][:60])

        # Download if not cached
        if not out.exists():
            try:
                resp = session.get(r["minutes_url"], headers=HEADERS, timeout=60)
                resp.raise_for_status()
                out.write_bytes(resp.content)
                log.info("  Downloaded %d KB", len(resp.content) // 1024)
            except Exception as e:
                log.warning("  Download failed: %s", e)
                time.sleep(sleep)
                continue
            time.sleep(sleep)

        # Scan
        pdf_bytes = out.read_bytes()
        found = _minutes_has_accounting(pdf_bytes)
        existing[pid]["has_accounting"] = "yes" if found else "no"
        log.info("  has_accounting = %s", existing[pid]["has_accounting"])

    merged = sorted(existing.values(), key=lambda r: int(r["post_id"]), reverse=True)
    _save_index(merged)

    yes = sum(1 for r in existing.values() if r.get("has_accounting") == "yes")
    no  = sum(1 for r in existing.values() if r.get("has_accounting") == "no")
    log.info("=== Minutes scan complete: yes=%d | no=%d | pending=%d ===",
             yes, no, len(existing) - yes - no)


# ─── Phase 3: ZIP download + extract ─────────────────────────────────────────

def phase_download(limit: int | None, sleep: float) -> None:
    """Download ZIPs for has_accounting=yes meetings, extract matching PDFs."""
    existing = _load_index()
    if not existing:
        log.error("No index found. Run --index-only and --minutes first.")
        sys.exit(1)

    session = _make_session()

    to_download = [
        r for r in existing.values()
        if r.get("has_accounting") == "yes"
        and r.get("zip_url")
        and not r.get("accounting_pdfs")   # skip if already extracted
    ]
    if limit is not None:
        to_download = to_download[:limit]

    log.info("Meetings to download: %d", len(to_download))

    for i, r in enumerate(to_download, 1):
        pid        = int(r["post_id"])
        meeting_dir = SFC1_RAW_DIR / _safe_dirname(r["title"])
        log.info("[%d/%d] %s", i, len(to_download), r["title"][:60])
        log.info("  ZIP: %s  %s", r["zip_filename"], r["zip_size_kb"])

        try:
            resp = session.get(r["zip_url"], headers=HEADERS, timeout=120)
            resp.raise_for_status()
            log.info("  Downloaded %d KB", len(resp.content) // 1024)
        except Exception as e:
            log.warning("  ZIP download failed: %s", e)
            time.sleep(sleep)
            continue

        # Extract matching PDFs from ZIP
        accounting_files: list[str] = []
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                all_names = zf.namelist()
                log.info("  ZIP contains %d files", len(all_names))
                for name in all_names:
                    basename = Path(name).name
                    if _is_accounting_pdf(basename):
                        meeting_dir.mkdir(parents=True, exist_ok=True)
                        out_path = meeting_dir / basename
                        out_path.write_bytes(zf.read(name))
                        accounting_files.append(basename)
                        log.info("  Extracted: %s", basename)
        except zipfile.BadZipFile as e:
            log.warning("  Bad ZIP: %s", e)
            time.sleep(sleep)
            continue

        if not accounting_files:
            log.info("  No matching PDFs found — updating has_accounting=no")
            existing[pid]["has_accounting"] = "no"
        else:
            existing[pid]["accounting_pdfs"] = ";".join(accounting_files)
            log.info("  Extracted %d accounting PDF(s)", len(accounting_files))

        time.sleep(sleep)

    merged = sorted(existing.values(), key=lambda r: int(r["post_id"]), reverse=True)
    _save_index(merged)

    extracted = sum(1 for r in existing.values() if r.get("accounting_pdfs"))
    total_pdfs = sum(
        len(r["accounting_pdfs"].split(";"))
        for r in existing.values()
        if r.get("accounting_pdfs")
    )
    log.info("=== Download complete: %d meetings | %d accounting PDFs ===",
             extracted, total_pdfs)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index and download SFC 증선위의결정보 accounting audit PDFs"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--index-only", action="store_true",
                       help="Phase 1: scrape index only (no downloads)")
    group.add_argument("--minutes", action="store_true",
                       help="Phase 2: download minutes PDFs and flag meetings")
    group.add_argument("--download", action="store_true",
                       help="Phase 3: download ZIPs and extract accounting PDFs")

    parser.add_argument("--pages", default=None,
                        help="Page range for --index-only, e.g. 1-5 (default: all 51)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max records to process (dev testing)")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP,
                        help=f"Seconds between requests (default {DEFAULT_SLEEP})")
    args = parser.parse_args()

    if args.index_only:
        # Determine page range
        if args.pages:
            m = re.match(r"(\d+)(?:-(\d+))?", args.pages)
            start = int(m.group(1))
            end   = int(m.group(2)) if m.group(2) else start
        else:
            start, end = 1, 51
        if args.limit:
            # Approximate: 10 records/page
            end = min(end, start + (args.limit - 1) // 10)
        phase_index((start, end), args.sleep)

    elif args.minutes:
        phase_minutes(args.limit, args.sleep)

    elif args.download:
        phase_download(args.limit, args.sleep)


if __name__ == "__main__":
    main()
