# Dataset State — 2026-03-17

Extracted from CLAUDE.md during 2026-03-31 documentation audit. Represents the
dataset snapshot after Sessions 1+2 (Source 1, 2, 3 all v1.0 complete).

---

## Source 3 (FSS anonymized PDFs)

| File | Rows | Notes |
|------|------|-------|
| scored_index.csv | 229 | All FSS cases scored and tiered |
| fss_enriched.json | 200 | 65 ok (full PDF) + 134 metadata_only + 1 pinned |
| violations.csv | 240 | 199 classified + 41 unclassified (FSS/BATCH-* annual summaries) |

The 39 FSS/BATCH-* rows are annual summary documents (not individual cases) — no
classification signal, correctly skipped by `--metadata-only`.

---

## Source 2 (FSS 회계감리결과제재 — named companies, Sessions 1+2 complete 2026-03-17)

| File | Rows | Notes |
|------|------|-------|
| fss_source2_index.csv | 71 | All companies indexed; atch_file_id populated for all 71 |
| data/raw/fss_source2/ | 71 HWP files | 17 HWPX (extractable), 54 binary HWP 5.0 |
| fss_source2_extracted.json | 71 | 17 ok (HWPX, avg ~720 chars), 54 failed (binary HWP) |
| fss_source2_enriched.json | 71 | 17 ok (Sonnet + full text), 54 metadata_only (Haiku) |
| dart_matches.csv | 71 | 64 high-confidence, 7 unresolved (90% match rate) |
| beneish_ratios.csv | 49 | 18 companies × ~3 years; 46/49 with M-Score |

**Session 2 API bugs discovered and fixed (2026-03-17):**
1. `find_corp_code()` returns a plain string (8-digit corp_code), not a DataFrame. `len("00131799") == 8 > 1` was flagging every company "ambiguous". Fixed: `isinstance(result, str) and len(result) == 8`.
2. `finstate` (summary, ~14 rows) vs `finstate_all` (detailed, ~159 rows). Switched to `finstate_all` — gives receivables, COGS, PPE, operating CF. Income statement uses `sj_div='CIS'`, sales field is `수익(매출액)`.
3. `DEPI` and `SGAI` unavailable in DART main statements (notes-only disclosure). Made both optional in M-Score — core 6 components (DSRI, GMI, AQI, SGI, LVGI, TATA) are required; DEPI/SGAI included if available.
4. `company_by_name()` returns a list, not a DataFrame — handled in Stage 2 candidate fetch.

**Beneish empirical findings (reports/beneish-validation.md):**
- revenue_fabrication (n=4): SGI directionally elevated (median ~1.2); 1 case clearly anomalous (아크솔루션스 SGI=2.48). Weakly supports taxonomy.
- asset_inflation (n=2): Both cases show AQI < 1.0 — contradicts taxonomy prediction.
- liability_suppression (n=2): LVGI not elevated — consistent with A2/A3 scaffold finding.
- 22% of violation-year companies above M-Score threshold (-1.78). Directional but anecdotal at n=2–4 per category.
- 18/42 companies produced Beneish data (others: unlisted companies don't file standardized DART statements, or violation_year < 2016).

**beneish_components field (repaired 2026-03-17):** Original Haiku enrichment had TATA as a
prompt artifact (100% assignment). A4 validated a repaired prompt; A5 re-enriched all 65 ok
cases with Sonnet using the repaired prompt. Production distribution: TATA 34% (diffuse),
SGI 95% precision→revenue_fabrication, AQI 74% precision→asset_inflation,
LVGI 73% precision→liability_suppression. The field is now usable for downstream applications.
See `reports/blind-test-review.md` for full A2–A5 validation chain.

**manual_patches.json pattern**: Any manually corrected case should be added to
`data/curated/manual_patches.json` with `enrichment_status="pinned"`. This file is committed
and applied by `_apply_manual_patches()` after every enrichment write, preventing overwrites.

---

## Source 1 (SFC 증선위의결정보 — Sessions 1+2 complete 2026-03-17)

| Metric | Value | Notes |
|--------|-------|-------|
| sfc_source1_index.csv | 503 records | All "의사록" meetings 2008–2026 |
| Records with ZIPs | 26 | 2025–2026 only; pre-2025 ZIPs not available |
| Records with minutes PDF only | 333 | 2015–2024 |
| Records with no attachments | 144 | 2008–2014 |
| Meetings with accounting items | 15 of 26 | 11 had no accounting audit items |
| Accounting PDFs extracted | 28 | From 15 meetings; 100% pdfplumber extraction |
| sfc_source1_extracted.json | 28 | 28 ok, 0 failed — all 2025–2026 modern PDFs |
| sfc_source1_enriched.json | 28 | 28 ok, 0 null violation_type |
| dart_matches.csv (sfc_source1 rows) | 6 new | 5 high + 1 medium; 웨이브일렉트로닉스 unresolved |
| beneish_ratios.csv (sfc_source1 rows) | 11 new | 3 companies × ~3 years; 8/11 with M-Score |
| beneish_ratios.csv (combined total) | 60 rows | 49 fss_source2 + 11 sfc_source1; 54/60 with M-Score |

**OOO redaction depth (confirmed 2026-03-17):** 15/28 PDFs are fully redacted in both
filename AND body text. The SFC anonymization goes end-to-end, not just the filename.
11 named companies were extractable (세진, 신기테크, 모델솔루션, 에스디엠, 숲, 코오롱생명과학,
웨이브일렉트로닉스, 일정실업, 파인켐텍, 라온홀딩스, 세코닉스).

**Violation type distribution (enriched.json):**
asset_inflation:10, revenue_fabrication:9, liability_suppression:7, related_party:1, disclosure_fraud:1

**Cross-regulator taxonomy finding:** FSS violation_type closed list applied cleanly to SFC
decisions without modification. Zero null violation_type (vs 52/71 null in Source 2 metadata-only).
The taxonomy generalizes across FSS and SFC regulatory contexts.

**Beneish empirical additions (SFC1):**
- asset_inflation (코오롱생명과학, 일정실업, 세코닉스): M-scores predominantly below -1.78 threshold,
  continuing Source 2 AQI contradiction.
- 에스디엠 (revenue_fabrication, violation_year=2025) and 파인켐텍 (liability_suppression,
  violation_year=2025): zero DART rows — FY2025 annual statements not yet filed.

See `reports/sfc-source1-session1.md` for full journey documentation.

---

## violation_type distribution (violations.csv as of 2026-03-17)

| Type | Count |
|------|-------|
| asset_inflation | 76 |
| revenue_fabrication | 45 |
| disclosure_fraud | 44 |
| liability_suppression | 16 |
| related_party | 13 |
| cost_distortion | 5 |
| (unclassified) | 41 |
