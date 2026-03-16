"""
scrape_fss_cases.py — Download FSS 심사·감리지적사례 enforcement case PDFs.

Source: https://fss.or.kr/fss/bbs/B0000135/list.do?menuNo=200448
Records: 229 anonymized enforcement cases across 23 pages (10 per page).
Format: PDF attachments with consistent 5-section structure:
  - Metadata: case number (FSS/YYMM-NN), 쟁점 분야, K-IFRS ref, 결정일, 회계결산일
  - §1 회사의 회계처리, §2 위반 지적, §3 판단 근거, §4 감사절차 미흡, §5 시사점

Page structure (server-side rendered HTML):
  - List: GET /fss/bbs/B0000135/list.do?menuNo=200448&pageIndex={1..N}
  - Detail: GET /fss/bbs/B0000135/view.do?nttId={id}&menuNo=200448
  - PDF: GET /fss/cmmn/file/fileDown.do?menuNo=200448&atchFileId={uuid}&fileSn=1&bbsId=

Output:
  data/raw/fss_enforcement/              — downloaded PDFs
  data/processed/fss_enforcement_index.csv — case metadata index

Usage:
  python -m kr_enforcement_cases.scrape_fss_cases
  python -m kr_enforcement_cases.scrape_fss_cases --pages 1-3      # first 3 pages only
  python -m kr_enforcement_cases.scrape_fss_cases --index-only      # scrape metadata, skip PDFs
  python -m kr_enforcement_cases.scrape_fss_cases --sleep 2.0       # seconds between requests
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
from pathlib import Path
from typing import NamedTuple

import requests
from bs4 import BeautifulSoup

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "fss_enforcement"
INDEX_PATH = PROJECT_ROOT / "data" / "processed" / "fss_enforcement_index.csv"

# ─── Constants ────────────────────────────────────────────────────────────────
BASE_URL = "https://fss.or.kr"
LIST_URL = f"{BASE_URL}/fss/bbs/B0000135/list.do"
DETAIL_URL = f"{BASE_URL}/fss/bbs/B0000135/view.do"
FILE_DOWN_URL = f"{BASE_URL}/fss/cmmn/file/fileDown.do"
MENU_NO = "200448"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://fss.or.kr/",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── Data model ───────────────────────────────────────────────────────────────
class CaseEntry(NamedTuple):
    """One row from the FSS enforcement case listing."""
    번호: int               # sequential number (229 down to 1)
    공개번호: str            # e.g. FSS/2512-10
    제목: str               # case title
    쟁점_분야: str           # dispute category
    관련_기준서: str          # K-IFRS reference
    결정년도: str            # decision year
    ntt_id: str             # bulletin board post ID
    atch_file_id: str       # attachment file UUID for PDF download
    pdf_filename: str       # e.g. FSS2512_10.pdf


# ─── Scraping ─────────────────────────────────────────────────────────────────

def fetch_page(session: requests.Session, page_index: int) -> str:
    """Fetch one page of the enforcement case listing."""
    params = {"menuNo": MENU_NO, "pageIndex": str(page_index)}
    resp = session.get(LIST_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_list_page(html: str) -> list[CaseEntry]:
    """Parse the table rows from one page of the listing.

    The FSS page uses a standard <table class="tb_list"> with columns:
    번호 | 공개번호 | 제목 | 쟁점 분야 | 관련 기준서 | 결정년도 | 첨부파일 | 조회수
    """
    soup = BeautifulSoup(html, "html.parser")
    entries: list[CaseEntry] = []

    # Find the main data table — it has class "tb_list"
    table = soup.find("table", class_="tb_list")
    if not table:
        # Fallback: try any table with enough columns
        tables = soup.find_all("table")
        for t in tables:
            if t.find("th") and len(t.find_all("th")) >= 6:
                table = t
                break
    if not table:
        log.warning("Could not find data table in page HTML")
        return entries

    tbody = table.find("tbody")
    if not tbody:
        tbody = table

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 7:
            continue

        번호_text = tds[0].get_text(strip=True)
        if not 번호_text.isdigit():
            continue

        번호 = int(번호_text)
        공개번호 = tds[1].get_text(strip=True)
        제목 = tds[2].get_text(strip=True)
        쟁점_분야 = tds[3].get_text(strip=True)
        관련_기준서 = tds[4].get_text(strip=True)
        결정년도 = tds[5].get_text(strip=True)

        # Extract nttId from the title link
        link = tds[2].find("a")
        ntt_id = ""
        if link:
            href = link.get("href", "")
            # Pattern: /fss/bbs/B0000135/view.do?nttId=207883&menuNo=200448
            m = re.search(r"nttId=(\d+)", href)
            if m:
                ntt_id = m.group(1)
            else:
                # Sometimes onclick with fn_detail('207883') or similar
                onclick = link.get("onclick", "")
                m = re.search(r"(\d{5,})", onclick)
                if m:
                    ntt_id = m.group(1)

        # Extract atchFileId from the attachment column
        atch_file_id = ""
        pdf_filename = ""
        attach_cell = tds[6]

        # Look for download link/button
        attach_link = attach_cell.find("a")
        if attach_link:
            href = attach_link.get("href", "")
            onclick = attach_link.get("onclick", "")
            # Pattern: fileDown.do?...atchFileId=e478b8ae48124a60bb6fcecb186623ed
            for text in [href, onclick]:
                m = re.search(r"atchFileId=([a-f0-9]{20,})", text)
                if m:
                    atch_file_id = m.group(1)
                    break

            # Try to get PDF filename from link text or title
            link_text = attach_link.get_text(strip=True)
            if link_text.endswith(".pdf"):
                pdf_filename = link_text
            title_attr = attach_link.get("title", "")
            if title_attr.endswith(".pdf"):
                pdf_filename = title_attr

        # If no atchFileId found in link, check for img with onclick or
        # any element with the file ID pattern
        if not atch_file_id:
            for elem in attach_cell.find_all(True):
                for attr_val in elem.attrs.values():
                    if isinstance(attr_val, str):
                        m = re.search(r"atchFileId=([a-f0-9]{20,})", attr_val)
                        if m:
                            atch_file_id = m.group(1)
                            break
                    elif isinstance(attr_val, list):
                        for v in attr_val:
                            if isinstance(v, str):
                                m = re.search(r"atchFileId=([a-f0-9]{20,})", v)
                                if m:
                                    atch_file_id = m.group(1)
                                    break
                if atch_file_id:
                    break

        # Generate PDF filename from 공개번호 if not found
        if not pdf_filename and 공개번호:
            # FSS/2512-10 → FSS2512_10.pdf
            pdf_filename = 공개번호.replace("/", "").replace("-", "_") + ".pdf"

        entries.append(CaseEntry(
            번호=번호,
            공개번호=공개번호,
            제목=제목,
            쟁점_분야=쟁점_분야,
            관련_기준서=관련_기준서,
            결정년도=결정년도,
            ntt_id=ntt_id,
            atch_file_id=atch_file_id,
            pdf_filename=pdf_filename,
        ))

    return entries


def fetch_atch_file_id_from_detail(
    session: requests.Session, ntt_id: str, sleep: float
) -> str:
    """Fallback: fetch the detail page to find atchFileId if list page didn't have it."""
    params = {"nttId": ntt_id, "menuNo": MENU_NO}
    time.sleep(sleep)
    resp = session.get(DETAIL_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    m = re.search(r"atchFileId=([a-f0-9]{20,})", resp.text)
    return m.group(1) if m else ""


def download_pdf(
    session: requests.Session,
    atch_file_id: str,
    dest_path: Path,
    sleep: float,
) -> bool:
    """Download a single PDF from FSS file download endpoint."""
    if dest_path.exists() and dest_path.stat().st_size > 1000:
        log.info("  Already downloaded: %s", dest_path.name)
        return True

    params = {
        "menuNo": MENU_NO,
        "atchFileId": atch_file_id,
        "fileSn": "1",
        "bbsId": "",
    }
    time.sleep(sleep)
    resp = session.get(FILE_DOWN_URL, params=params, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "pdf" not in content_type.lower() and len(resp.content) < 5000:
        log.warning("  Unexpected response for %s (Content-Type: %s, size: %d)",
                     dest_path.name, content_type, len(resp.content))
        return False

    dest_path.write_bytes(resp.content)
    log.info("  Downloaded: %s (%d bytes)", dest_path.name, len(resp.content))
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

def scrape_index(
    session: requests.Session,
    page_start: int,
    page_end: int,
    sleep: float,
) -> list[CaseEntry]:
    """Scrape case metadata from all specified pages."""
    all_entries: list[CaseEntry] = []

    for page in range(page_start, page_end + 1):
        log.info("Fetching page %d ...", page)
        html = fetch_page(session, page)
        entries = parse_list_page(html)

        if not entries:
            log.warning("No entries found on page %d — may have reached the end", page)
            break

        log.info("  Found %d entries on page %d", len(entries), page)
        all_entries.extend(entries)

        if page < page_end:
            time.sleep(sleep)

    return all_entries


def save_index(entries: list[CaseEntry], path: Path) -> None:
    """Write case index to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(CaseEntry._fields)
        for e in entries:
            writer.writerow(e)
    log.info("Index saved: %s (%d entries)", path, len(entries))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download FSS enforcement case PDFs (심사·감리지적사례)"
    )
    parser.add_argument(
        "--pages", default=None,
        help="Page range to scrape, e.g. '1-3' or '5'. Default: all pages.",
    )
    parser.add_argument(
        "--index-only", action="store_true",
        help="Scrape metadata index only, skip PDF downloads.",
    )
    parser.add_argument(
        "--sleep", type=float, default=1.5,
        help="Seconds to wait between requests (default: 1.5).",
    )
    parser.add_argument(
        "--max-pages", type=int, default=25,
        help="Maximum pages to scan if total is unknown (default: 25).",
    )
    args = parser.parse_args()

    # Parse page range
    if args.pages:
        if "-" in args.pages:
            parts = args.pages.split("-")
            page_start, page_end = int(parts[0]), int(parts[1])
        else:
            page_start = page_end = int(args.pages)
    else:
        page_start, page_end = 1, args.max_pages

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()

    # Phase 1: Scrape index
    log.info("=== Phase 1: Scraping case index (pages %d–%d) ===", page_start, page_end)
    entries = scrape_index(session, page_start, page_end, args.sleep)

    if not entries:
        log.error("No entries found. The FSS page structure may have changed.")
        sys.exit(1)

    # Fill in missing atchFileIds from detail pages
    missing_atch = [e for e in entries if not e.atch_file_id]
    if missing_atch:
        log.info("Fetching atchFileId from detail pages for %d entries...", len(missing_atch))
        updated: list[CaseEntry] = []
        for e in entries:
            if not e.atch_file_id and e.ntt_id:
                atch = fetch_atch_file_id_from_detail(session, e.ntt_id, args.sleep)
                if atch:
                    e = e._replace(atch_file_id=atch)
                    log.info("  Found atchFileId for %s via detail page", e.공개번호)
                else:
                    log.warning("  Could not find atchFileId for %s", e.공개번호)
            updated.append(e)
        entries = updated

    save_index(entries, INDEX_PATH)

    log.info("=== Index summary ===")
    log.info("  Total cases: %d", len(entries))
    log.info("  With atchFileId: %d", sum(1 for e in entries if e.atch_file_id))
    log.info("  Missing atchFileId: %d", sum(1 for e in entries if not e.atch_file_id))

    if args.index_only:
        log.info("--index-only specified, skipping PDF downloads.")
        return

    # Phase 2: Download PDFs
    downloadable = [e for e in entries if e.atch_file_id]
    log.info("=== Phase 2: Downloading %d PDFs ===", len(downloadable))

    success = 0
    fail = 0
    for i, entry in enumerate(downloadable, 1):
        dest = RAW_DIR / entry.pdf_filename
        log.info("[%d/%d] %s — %s", i, len(downloadable), entry.공개번호, entry.제목)
        ok = download_pdf(session, entry.atch_file_id, dest, args.sleep)
        if ok:
            success += 1
        else:
            fail += 1

    log.info("=== Done ===")
    log.info("  Downloaded: %d | Failed: %d | Skipped (no atchFileId): %d",
             success, fail, len(entries) - len(downloadable))


if __name__ == "__main__":
    main()
