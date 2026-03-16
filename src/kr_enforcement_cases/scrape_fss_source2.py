"""
scrape_fss_source2.py — Download FSS 회계감리결과제재 enforcement case HWP files.

Source: https://fss.or.kr/fss/job/accnutAdtorInfo/list.do?acntnWrkCode=02&menuNo=200617
Records: 71 named companies with HWP attachments (enforcement sanction details).
Format: HWP/HWPX attachments, one per company row.

Page structure (server-side rendered HTML):
  - List: GET /fss/job/accnutAdtorInfo/list.do?acntnWrkCode=02&menuNo=200617&curPage={N}
  - File: GET /fss/cmmn/file/fileDown.do?menuNo=200617&atchFileId={uuid}&fileSn=1&bbsId=

Columns per row: 번호, 회사명, 감리대상연도, 조치일, 상장여부, 조치내역 (HWP), 조회수

Output:
  data/processed/fss_source2_index.csv    — company metadata index
  data/raw/fss_source2/                   — downloaded HWP files

Usage:
  uv run python -m kr_enforcement_cases.scrape_fss_source2 --index-only
  uv run python -m kr_enforcement_cases.scrape_fss_source2 --pages 1-2
  uv run python -m kr_enforcement_cases.scrape_fss_source2 --sleep 2.0
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

from .paths import PROCESSED_DIR, SOURCE2_INDEX, SOURCE2_RAW_DIR

# ─── Constants ────────────────────────────────────────────────────────────────

BASE_URL     = "https://fss.or.kr"
LIST_URL     = f"{BASE_URL}/fss/job/accnutAdtorInfo/list.do"
FILE_DOWN_URL = f"{BASE_URL}/fss/cmmn/file/fileDown.do"
MENU_NO      = "200617"
ACN_WRK_CODE = "02"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://fss.or.kr/",
}

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)


# ─── Data model ───────────────────────────────────────────────────────────────

class Source2Entry(NamedTuple):
    """One row from the FSS Source 2 listing."""
    seq_no: int           # row number from table (번호)
    company_name: str     # 회사명 (raw, with corporate form prefix)
    audit_years: str      # 감리대상연도 (e.g. "2022~2023" or "2021")
    action_date: str      # 조치일 (YYYY.MM.DD as displayed)
    listed_status: str    # 상장여부 (상장/비상장/코스닥 etc.)
    atch_file_id: str     # UUID from download URL
    file_name: str        # original HWP filename
    downloaded: bool      # updated to True after download


# ─── Scraping ─────────────────────────────────────────────────────────────────

def _init_session() -> requests.Session:
    """Create a session and warm it up with the main page to get any cookies."""
    session = requests.Session()
    try:
        session.get(BASE_URL, headers=HEADERS, timeout=15)
    except Exception:
        pass  # warm-up failure is non-fatal
    return session


def fetch_page(session: requests.Session, page_index: int) -> str:
    """Fetch one page of the Source 2 listing."""
    params = {
        "acntnWrkCode": ACN_WRK_CODE,
        "menuNo": MENU_NO,
        "pageIndex": str(page_index),
    }
    resp = session.get(LIST_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_list_page(html: str) -> list[Source2Entry]:
    """Parse the table rows from one page of the Source 2 listing."""
    soup = BeautifulSoup(html, "html.parser")
    entries: list[Source2Entry] = []

    # Find the main data table
    table = soup.find("table", class_="tb_list")
    if not table:
        tables = soup.find_all("table")
        for t in tables:
            ths = t.find_all("th")
            if len(ths) >= 5:
                table = t
                break
    if not table:
        log.warning("Could not find data table in page HTML")
        return entries

    tbody = table.find("tbody") or table

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue

        seq_text = tds[0].get_text(strip=True)
        if not seq_text.isdigit():
            continue

        seq_no       = int(seq_text)
        company_name = tds[1].get_text(strip=True)
        audit_years  = tds[2].get_text(strip=True)
        action_date  = tds[3].get_text(strip=True)
        listed_status = tds[4].get_text(strip=True)

        # Attachment cell — column index 5
        attach_cell = tds[5]
        atch_file_id = ""
        file_name    = ""

        # Search all elements in attach cell for atchFileId
        for elem in attach_cell.find_all(True):
            for attr_name, attr_val in elem.attrs.items():
                if isinstance(attr_val, str):
                    m = re.search(r"atchFileId=([a-f0-9A-F\-]{20,})", attr_val)
                    if m:
                        atch_file_id = m.group(1)
                elif isinstance(attr_val, list):
                    for v in attr_val:
                        if isinstance(v, str):
                            m = re.search(r"atchFileId=([a-f0-9A-F\-]{20,})", v)
                            if m:
                                atch_file_id = m.group(1)

            # Also check href/onclick
            for attr in ("href", "onclick"):
                val = elem.get(attr, "")
                if isinstance(val, str):
                    m = re.search(r"atchFileId=([a-f0-9A-F\-]{20,})", val)
                    if m and not atch_file_id:
                        atch_file_id = m.group(1)

            if atch_file_id:
                # Try to extract filename from link text or title
                text = elem.get_text(strip=True)
                title = elem.get("title", "")
                for candidate in [title, text]:
                    if candidate.lower().endswith(".hwp") or candidate.lower().endswith(".hwpx"):
                        file_name = candidate
                        break
                break

        # Generate filename from company name if not found
        if not file_name and company_name:
            safe = re.sub(r'[\\/:*?"<>|]', "_", company_name)
            file_name = f"{safe}.hwp"
        elif not file_name:
            file_name = f"source2_{seq_no}.hwp"

        entries.append(Source2Entry(
            seq_no=seq_no,
            company_name=company_name,
            audit_years=audit_years,
            action_date=action_date,
            listed_status=listed_status,
            atch_file_id=atch_file_id,
            file_name=file_name,
            downloaded=False,
        ))

    return entries


def download_hwp(
    session: requests.Session,
    atch_file_id: str,
    dest_path: Path,
    sleep: float,
    company_name: str = "",
) -> bool:
    """Download a single HWP file from the FSS file download endpoint."""
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
    size = len(resp.content)
    if size < 2000 and "html" in content_type.lower():
        log.warning("  HTML response (likely error) for %s (size: %d)", company_name or dest_path.name, size)
        return False

    # Detect actual file extension from content
    actual_path = dest_path
    if resp.content[:4] == b'PK\x03\x04':
        # ZIP-based — could be HWPX
        actual_path = dest_path.with_suffix(".hwpx")
    elif resp.content[:4] == b'\xd0\xcf\x11\xe0':
        # OLE2 compound document — binary HWP
        actual_path = dest_path.with_suffix(".hwp")

    # Try to get filename from Content-Disposition
    cd = resp.headers.get("Content-Disposition", "")
    if cd:
        m = re.search(r'filename[^;=\n]*=([^;\n]*)', cd)
        if m:
            fn = m.group(1).strip().strip('"\'')
            if fn:
                # Decode percent-encoded filename
                try:
                    from urllib.parse import unquote
                    fn = unquote(fn)
                except Exception:
                    pass
                safe = re.sub(r'[\\/:*?"<>|]', "_", fn)
                actual_path = dest_path.parent / safe

    actual_path.write_bytes(resp.content)
    log.info("  Downloaded: %s (%d bytes)", actual_path.name, size)
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

def scrape_index(
    session: requests.Session,
    page_start: int,
    page_end: int,
    sleep: float,
) -> list[Source2Entry]:
    """Scrape company metadata from all specified pages."""
    all_entries: list[Source2Entry] = []

    for page in range(page_start, page_end + 1):
        log.info("Fetching page %d ...", page)
        html = fetch_page(session, page)
        entries = parse_list_page(html)

        if not entries:
            log.warning("No entries on page %d — may have reached end", page)
            break

        log.info("  Found %d entries on page %d", len(entries), page)
        all_entries.extend(entries)

        if page < page_end:
            time.sleep(sleep)

    return all_entries


def save_index(entries: list[Source2Entry], path: Path) -> None:
    """Write company index to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(Source2Entry._fields)
        for e in entries:
            writer.writerow(e)
    log.info("Index saved: %s (%d entries)", path, len(entries))


def load_index(path: Path) -> list[Source2Entry]:
    """Load existing index CSV, returning list of Source2Entry."""
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        entries = []
        for row in reader:
            entries.append(Source2Entry(
                seq_no=int(row["seq_no"]),
                company_name=row["company_name"],
                audit_years=row["audit_years"],
                action_date=row["action_date"],
                listed_status=row["listed_status"],
                atch_file_id=row["atch_file_id"],
                file_name=row["file_name"],
                downloaded=row["downloaded"].lower() == "true",
            ))
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape FSS Source 2 (회계감리결과제재) company list and HWP files"
    )
    parser.add_argument(
        "--pages", default=None,
        help="Page range to scrape, e.g. '1-3' or '5'. Default: all pages.",
    )
    parser.add_argument(
        "--index-only", action="store_true",
        help="Scrape metadata index only, skip HWP downloads.",
    )
    parser.add_argument(
        "--sleep", type=float, default=1.5,
        help="Seconds to wait between requests (default: 1.5).",
    )
    parser.add_argument(
        "--max-pages", type=int, default=10,
        help="Maximum pages to scan if total is unknown (default: 10).",
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

    SOURCE2_RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    session = _init_session()

    # Phase 1: Scrape index
    log.info("=== Phase 1: Scraping Source 2 index (pages %d–%d) ===", page_start, page_end)
    entries = scrape_index(session, page_start, page_end, args.sleep)

    if not entries:
        log.error("No entries found. The FSS Source 2 page structure may have changed.")
        sys.exit(1)

    save_index(entries, SOURCE2_INDEX)

    log.info("=== Index summary ===")
    log.info("  Total companies: %d", len(entries))
    log.info("  With atchFileId: %d", sum(1 for e in entries if e.atch_file_id))
    log.info("  Missing atchFileId: %d", sum(1 for e in entries if not e.atch_file_id))

    if args.index_only:
        log.info("--index-only specified, skipping HWP downloads.")
        return

    # Phase 2: Download HWP files
    downloadable = [e for e in entries if e.atch_file_id]
    log.info("=== Phase 2: Downloading %d HWP files ===", len(downloadable))

    success = 0
    fail = 0
    updated: list[Source2Entry] = []

    for i, entry in enumerate(entries, 1):
        if not entry.atch_file_id:
            updated.append(entry)
            continue

        safe_name = re.sub(r'[\\/:*?"<>|]', "_", entry.file_name)
        dest = SOURCE2_RAW_DIR / safe_name
        log.info("[%d/%d] %s (%s)", i, len(downloadable), entry.company_name, entry.audit_years)
        ok = download_hwp(session, entry.atch_file_id, dest, args.sleep, entry.company_name)
        updated.append(entry._replace(downloaded=ok))
        if ok:
            success += 1
        else:
            fail += 1

    save_index(updated, SOURCE2_INDEX)

    log.info("=== Done ===")
    log.info(
        "  Downloaded: %d | Failed: %d | No atchFileId: %d",
        success, fail, len(entries) - len(downloadable),
    )


if __name__ == "__main__":
    main()
