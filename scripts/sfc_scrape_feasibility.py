"""
sfc_scrape_feasibility.py — One-time script for SFC Source 1 scraping feasibility.

Tests:
  1. POST search form → parse 2 pages of "의사록" results (post_id, title, date, file list)
  2. Verify ZIP and minutes PDF attachment parsing
  3. Download 1 minutes PDF → confirm download URL pattern works
  4. Parse minutes PDF for accounting keywords (조사감리결과, 감리결과, 감사보고서)
     to assess whether minutes can serve as a pre-filter before downloading ZIPs

Run: uv run python test_sfc_scrape.py
"""
from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")

import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import pdfplumber

BASE_URL   = "https://fsc.go.kr"
SEARCH_URL = f"{BASE_URL}/no020102"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer":         SEARCH_URL,
}
ACCOUNTING_KEYWORDS = ["조사감리결과", "감리결과", "감사보고서", "회계감리", "조사·감리"]

OUT_DIR = Path("data/raw/sfc_test")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── Parsing ──────────────────────────────────────────────────────────────────

def parse_records(soup: BeautifulSoup) -> list[dict]:
    records = []
    for li in soup.select("div.board-list-wrap ul li"):
        count_div   = li.select_one("div.count")
        subject_a   = li.select_one("div.subject a")
        day_div     = li.select_one("div.day")
        file_lists  = li.select("div.file-list")
        if not subject_a:
            continue

        # Extract post_id from href like /no020102/86410?...
        post_id = None
        for part in subject_a.get("href", "").split("/"):
            candidate = part.split("?")[0]
            if candidate.isdigit():
                post_id = int(candidate)
                break

        files = []
        for fl in file_lists:
            a = fl.select_one("a[href*='getFile']")
            spans = fl.select("span.name")
            if a:
                files.append({
                    "name": a.get("title", ""),
                    "url":  BASE_URL + a["href"],
                    "size": spans[1].text.strip() if len(spans) > 1 else "",
                })

        records.append({
            "count":   count_div.text.strip() if count_div else "",
            "post_id": post_id,
            "title":   subject_a.get("title", "").strip(),
            "date":    day_div.text.strip() if day_div else "",
            "files":   files,
        })
    return records


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    session = requests.Session()

    # ── Step 1: POST search form (page 1) ─────────────────────────────────────
    print("=== Step 1: POST search form — page 1 ===")
    post_data = {
        "srchCtgry":  "",
        "srchKey":    "sj",
        "srchText":   "의사록",
        "curPage":    "1",
    }
    resp = session.post(SEARCH_URL, data=post_data, headers=HEADERS, timeout=30)
    print(f"  POST status={resp.status_code}, body_len={len(resp.text)}")

    soup = BeautifulSoup(resp.text, "html.parser")

    total_el = soup.select_one("div.board-total-wrap strong")
    if total_el:
        print(f"  Total records reported: {total_el.text}")
    else:
        print("  WARNING: could not find total count element")

    records_p1 = parse_records(soup)
    print(f"  Parsed {len(records_p1)} records from page 1")
    for r in records_p1:
        zips = [f for f in r["files"] if f["name"].endswith(".zip")]
        pdfs = [f for f in r["files"] if f["name"].endswith(".pdf")]
        print(f"    [{r['count']:>4}] {r['date']}  {r['title'][:55]}")
        for f in r["files"]:
            tag = "ZIP" if f["name"].endswith(".zip") else "PDF"
            print(f"           [{tag}] {f['name'][:60]}  {f['size']}")

    time.sleep(1.5)

    # ── Step 2: GET page 2 (session-cookie pagination) ────────────────────────
    print("\n=== Step 2: GET page 2 via ?curPage=2 ===")
    resp2 = session.get(f"{SEARCH_URL}?curPage=2", headers=HEADERS, timeout=30)
    print(f"  GET status={resp2.status_code}")
    soup2 = BeautifulSoup(resp2.text, "html.parser")
    records_p2 = parse_records(soup2)
    print(f"  Parsed {len(records_p2)} records from page 2")
    for r in records_p2:
        print(f"    [{r['count']:>4}] {r['date']}  {r['title'][:55]}")

    # Check if page 2 results are the same as page 1 (would mean session not maintained)
    if records_p2 and records_p1:
        if records_p2[0]["post_id"] == records_p1[0]["post_id"]:
            print("  WARNING: page 2 returned same results as page 1 — session state lost.")
            print("  Will retry page 2 with full POST params.")
            post_data["curPage"] = "2"
            resp2 = session.post(SEARCH_URL, data=post_data, headers=HEADERS, timeout=30)
            soup2 = BeautifulSoup(resp2.text, "html.parser")
            records_p2 = parse_records(soup2)
            print(f"  POST retry: parsed {len(records_p2)} records")
            for r in records_p2:
                print(f"    [{r['count']:>4}] {r['date']}  {r['title'][:55]}")

    time.sleep(1.5)

    # ── Step 3: Download 1 minutes PDF ────────────────────────────────────────
    print("\n=== Step 3: Download 1 minutes PDF ===")
    all_records = records_p1 + records_p2
    minutes_file = None
    parent_record = None
    for r in all_records:
        for f in r["files"]:
            if "의사록" in f["name"] and f["name"].endswith(".pdf"):
                minutes_file = f
                parent_record = r
                break
        if minutes_file:
            break

    if not minutes_file:
        print("  No minutes PDF found — cannot test download")
        return

    print(f"  Target: {minutes_file['name']}  {minutes_file['size']}")
    print(f"  URL:    {minutes_file['url']}")
    resp3 = session.get(minutes_file["url"], headers=HEADERS, timeout=60)
    print(f"  Status: {resp3.status_code}, Content-Type: {resp3.headers.get('Content-Type', '?')}")
    print(f"  Downloaded bytes: {len(resp3.content)}")

    if resp3.status_code != 200 or resp3.content[:4] != b"%PDF":
        print("  FAIL: response is not a valid PDF")
        (OUT_DIR / "debug_response.html").write_bytes(resp3.content[:5000])
        print("  Saved first 5KB to data/raw/sfc_test/debug_response.html for inspection")
        return

    out_path = OUT_DIR / "test_minutes.pdf"
    out_path.write_bytes(resp3.content)
    print(f"  Saved: {out_path}")

    # ── Step 4: Scan minutes PDF for accounting keywords ──────────────────────
    print("\n=== Step 4: Scan minutes PDF for accounting keywords ===")
    with pdfplumber.open(out_path) as pdf:
        print(f"  Pages: {len(pdf.pages)}")
        full_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        print(f"  Total chars extracted: {len(full_text)}")

        found_any = False
        for kw in ACCOUNTING_KEYWORDS:
            count = full_text.count(kw)
            if count:
                print(f"  '{kw}': {count} occurrence(s)")
                found_any = True

        if not found_any:
            print("  No accounting keywords found in this minutes PDF.")
            print("  (This meeting may have had no accounting audit items, or keywords differ.)")
        else:
            # Show context around first hit
            for kw in ACCOUNTING_KEYWORDS:
                idx = full_text.find(kw)
                if idx >= 0:
                    snippet = full_text[max(0, idx - 60):idx + 120].replace("\n", " ")
                    print(f"\n  Context for '{kw}':\n    ...{snippet}...")
                    break

    print(f"\n=== Summary ===")
    total_parsed = len(all_records)
    has_zip = sum(1 for r in all_records if any(f["name"].endswith(".zip") for f in r["files"]))
    has_minutes = sum(1 for r in all_records if any("의사록" in f["name"] and f["name"].endswith(".pdf") for f in r["files"]))
    print(f"  Records parsed: {total_parsed}")
    print(f"  Records with ZIP: {has_zip}")
    print(f"  Records with minutes PDF: {has_minutes}")
    print(f"  Accounting keywords in test minutes: {'YES' if found_any else 'NO'}")


if __name__ == "__main__":
    main()
