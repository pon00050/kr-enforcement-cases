# kr-enforcement-cases

Korean FSS/SFC enforcement case dataset for forensic accounting model training.

## Install & Run

```bash
uv sync
uv run pytest tests/ -v
```

## Full Pipeline (run in order)

```bash
# 1. Scrape FSS index + download PDFs
uv run python -m kr_enforcement_cases.scrape_fss_cases --index-only   # metadata only
uv run python -m kr_enforcement_cases.scrape_fss_cases                 # full download

# 2. Score and prioritise cases for download
uv run python -m kr_enforcement_cases.score_cases
# → reports/scored_index.csv

# 3. Download prioritised PDFs (Tier 1 & 2 only)
uv run python -m kr_enforcement_cases.download_prioritised

# 4. Extract text from downloaded PDFs
uv run python -m kr_enforcement_cases.parse_fss_pdf --tier 2   # Tier 1+2 (default: tier 1 only)
# → data/curated/fss_extracted.json

# 5a. Enrich with full PDF text (for downloaded cases)
uv run python -m kr_enforcement_cases.enrich_fss_cases --limit 3       # dev validation
uv run python -m kr_enforcement_cases.enrich_fss_cases --batch          # production

# 5b. Enrich all 229 cases from index metadata only (no PDFs needed)
uv run python -m kr_enforcement_cases.enrich_fss_cases --metadata-only --limit 3  # dev
uv run python -m kr_enforcement_cases.enrich_fss_cases --metadata-only             # production
# → data/curated/fss_enriched.json (merges in-place; skips enrichment_status="ok")

# 6. Validate vocabulary / strip OOV values
uv run python -m kr_enforcement_cases.normalise_fss --strict
# → rewrites fss_enriched.json in-place

# 7. Build violations.csv
uv run python -m kr_enforcement_cases.build_violation_db
# → reports/violations.csv
```

## Source 2 Pipeline — FSS 회계감리결과제재 (71 named companies)

Produces `beneish_ratios.csv` for empirical validation of the FSS taxonomy.
Prerequisite: `DART_API_KEY` in `.env` (register free at https://opendart.fss.or.kr/).

```bash
# S2-1. Scrape Source 2 index + download HWP files
uv run python -m kr_enforcement_cases.scrape_fss_source2 --pages 1-2 --index-only  # dev test
uv run python -m kr_enforcement_cases.scrape_fss_source2 --index-only               # full index
uv run python -m kr_enforcement_cases.scrape_fss_source2                             # + downloads
# → data/processed/fss_source2_index.csv, data/raw/fss_source2/*.hwp

# S2-2. Extract text from HWP/HWPX files (best-effort; binary .hwp will fail)
uv run python -m kr_enforcement_cases.extract_hwp --limit 3   # dev test
uv run python -m kr_enforcement_cases.extract_hwp             # full extraction
# → data/curated/fss_source2_extracted.json (gitignored)

# S2-3. Enrich with Sonnet (full text where available, Haiku metadata-only fallback)
uv run python -m kr_enforcement_cases.enrich_source2 --limit 3 --model haiku  # dev test
uv run python -m kr_enforcement_cases.enrich_source2                           # production (sequential — 71 cases in ~4 min)
# Note: --batch is NOT recommended for ≤100 cases; Batch API took 90+ min for 71 cases
# → data/curated/fss_source2_enriched.json (gitignored)

# S2-4. Match companies to DART corp_codes (requires DART_API_KEY)
uv run python -m kr_enforcement_cases.match_dart_companies --limit 10  # dev test
uv run python -m kr_enforcement_cases.match_dart_companies             # production
# → data/curated/dart_matches.csv (committed)

# S2-5. Compute Beneish ratios from DART financials (t, t-1, t-2 per company)
uv run python -m kr_enforcement_cases.compute_beneish --limit 5  # dev test
uv run python -m kr_enforcement_cases.compute_beneish            # production
# → reports/beneish_ratios.csv (committed)
```

## Source 1 Pipeline — SFC 증선위의결정보 (accounting audit decisions)

Source: fsc.go.kr/no020102 — 503 "의사록" meeting records (POST search).
Attachment availability: ZIPs exist only for 2025–2026 (26 records); 2015–2024 have minutes PDFs only.

```bash
# S1-1. Index all 503 records (no downloads)
uv run python -m kr_enforcement_cases.scrape_sfc_source1 --pages 1-3 --index-only  # dev
uv run python -m kr_enforcement_cases.scrape_sfc_source1 --index-only               # all 51 pages
# → data/processed/sfc_source1_index.csv

# S1-2. Download minutes PDFs + scan for accounting keywords (pre-filter for large backlogs)
# NOTE: Only worthwhile if many ZIPs are available (hundreds+). For 26 ZIPs, skip to S1-3.
uv run python -m kr_enforcement_cases.scrape_sfc_source1 --minutes --limit 10  # dev
uv run python -m kr_enforcement_cases.scrape_sfc_source1 --minutes              # full scan
# → data/raw/SFC Source 1/minutes/*.pdf, updates has_accounting in sfc_source1_index.csv

# S1-3. Download ZIPs + extract accounting (의결서) PDFs
uv run python -m kr_enforcement_cases.scrape_sfc_source1 --download --limit 3  # dev
uv run python -m kr_enforcement_cases.scrape_sfc_source1 --download             # production
# → data/raw/SFC Source 1/{meeting_title}/(의결서)*.pdf
```

**Accounting PDF filter:** filename must start with `(의결서)` AND contain one of:
`조사감리결과` | `위탁감리결과` | `회계감리결과` | `감사보고서`

**Key structural finding (confirmed 2026-03-17):** Decision letter ZIPs were introduced in
2025. Pre-2025 records have minutes PDFs only. Backfilling pre-2025 would require parsing
minutes PDFs to identify accounting items — a separate effort.

## Architecture

```
src/kr_enforcement_cases/
  scrape_fss_cases.py      — Scrapes FSS 심사·감리지적사례; 229 anonymized PDFs + index
  score_cases.py           — Scores cases by Beneish/forensic signal relevance
                             Tier 1 (high) / Tier 2 (medium) / Tier 3 (low)
                             Output: reports/scored_index.csv
  download_prioritised.py  — Downloads Tier 1 & 2 PDFs from scored_index.csv
  parse_fss_pdf.py         — Extracts structured text from PDFs
                             Output: data/curated/fss_extracted.json
  enrich_fss_cases.py      — Sonnet enrichment (full text, repaired prompt) + Haiku (metadata-only fallback):
                               Full text mode: reads fss_extracted.json
                               --metadata-only: reads scored_index.csv directly
                             Output: data/curated/fss_enriched.json
                             enrichment_status: "ok" | "metadata_only" | "fallback" | ...
  normalise_fss.py         — Validates all fields against closed enumerations
                             --strict strips OOV forensic_signals from output
  build_violation_db.py    — Flattens fss_enriched.json → violations.csv
  constants.py             — Shared vocabulary (SCHEME_TYPES, FSS_VIOLATION_CATEGORIES,
                             SIGNAL_SEED_VOCABULARY, FSS_ENRICHMENT_SYSTEM_PROMPT,
                             SOURCE2_NAME_STRIP, DART_ACCOUNT_MAP,
                             SOURCE2_ENRICHMENT_SYSTEM_PROMPT)
  paths.py                 — Canonical paths (PROJECT_ROOT, SCORED_INDEX, ENRICHED_JSON,
                             SOURCE2_*, DART_MATCHES_CSV, BENEISH_RATIOS_CSV, ...)

  [Source 2 — FSS 회계감리결과제재]
  scrape_fss_source2.py    — Scrapes 71 named companies; downloads HWP files
                             Output: data/processed/fss_source2_index.csv
  extract_hwp.py           — Extracts text from HWP/HWPX files (best-effort)
                             .hwpx: python-hwpx + zipfile+XML fallback
                             binary .hwp: extract_status="failed" (no Python 3.13 lib)
                             Output: data/curated/fss_source2_extracted.json
  enrich_source2.py        — Sonnet enrichment (full text) + Haiku (metadata-only fallback)
                             Adds company_name_norm, violation_year, sanction_summary
                             Default model: Sonnet (better calibration for labeled data)
                             Output: data/curated/fss_source2_enriched.json
  match_dart_companies.py  — Two-stage DART corp_code matching:
                               Stage 1: opendartreader exact + fuzzy (automated)
                               Stage 2: Sonnet review for ambiguous (cap 20 calls)
                             Output: data/curated/dart_matches.csv (committed)
  compute_beneish.py       — 7 Beneish components × 3 years per company from DART finstate
                             Formulas: DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA + M-Score
                             Output: reports/beneish_ratios.csv (committed)

  [Source 1 — SFC 증선위의결정보]
  scrape_sfc_source1.py    — Three-phase scraper for SFC accounting audit decisions
                             Phase 1 (--index-only): POST search "의사록" → 503 records, 51 pages
                             Phase 2 (--minutes): download minutes PDFs, scan for accounting keywords
                             Phase 3 (--download): download ZIPs, extract (의결서) accounting PDFs
                             Output: data/processed/sfc_source1_index.csv
                                     data/raw/SFC Source 1/{meeting_title}/(의결서)*.pdf
  parse_sfc1_pdfs.py       — Walks SFC1_RAW_DIR, filters/deduplicates accounting PDFs,
                             extracts full text via pdfplumber (pypdfium2 fallback)
                             Dedup key: (decision_number, meeting_year)
                             Output: data/curated/sfc_source1_extracted.json (gitignored)
  enrich_sfc1_cases.py     — Sonnet enrichment; extracts company_name from body text
                             (not from filename — OOO filenames are common)
                             Sequential only — no --batch (28 cases, ~3 min)
                             Output: data/curated/sfc_source1_enriched.json (gitignored)

data/
  raw/fss_enforcement/     — Downloaded PDFs (gitignored)
  raw/fss_source2/         — Downloaded HWP files (gitignored)
  raw/SFC Source 1/        — Accounting decision PDFs + minutes (gitignored)
    minutes/               — Minutes PDFs (kept for audit; used as keyword pre-filter)
    {meeting_title}/       — Per-meeting folder; contains (의결서)*.pdf accounting decisions
  processed/               — fss_enforcement_index.csv, fss_source2_index.csv,
                             sfc_source1_index.csv (gitignored)
  curated/
    fss_extracted.json          — PDF text extraction output (gitignored)
    fss_enriched.json           — Sonnet classification output (A5 repaired prompt; gitignored)
    fss_source2_extracted.json  — HWP text extraction output (gitignored)
    fss_source2_enriched.json   — Sonnet classification output (gitignored)
    sfc_source1_extracted.json  — SFC1 PDF text extraction output (gitignored)
    sfc_source1_enriched.json   — SFC1 Sonnet classification output (gitignored)
    dart_matches.csv            — DART corp_code matches for all sources (committed)
                                  source column: "fss_source2" | "sfc_source1"
    manual_patches.json         — Committed manual overrides applied after every enrichment write

reports/
  scored_index.csv         — 229 cases with tier, Beneish scores
  violations.csv           — Final output: one row per violation per case
  beneish_ratios.csv       — 7 Beneish components × 3 years × N companies (committed)
                             source column added (2026-03-17): "fss_source2" | "sfc_source1"
  beneish-validation.md    — Opus: empirical Beneish findings (Session 2)
  research-journey.md      — Opus: full project narrative (Session 2)
  cohort-comparison.md     — A1: ok vs metadata_only Beneish distribution (2026-03-16)
  blind-test-review.md     — A2/A3: blind prompt + Sonnet spot-check review (2026-03-16)
  sfc-source1-session1.md  — Session 1 journey: extraction + enrichment results,
                             OOO redaction findings, cross-regulator taxonomy check (2026-03-17)

docs/
  data_sources.md          — All 8 identified enforcement data sources ranked by priority
  model_delegation_matrix.md — Model delegation decisions + full bias validation journey
```

## Current Dataset State

### Source 3 (FSS anonymized PDFs)

| File | Rows | Notes |
|------|------|-------|
| scored_index.csv | 229 | All FSS cases scored and tiered |
| fss_enriched.json | 200 | 65 ok (full PDF) + 134 metadata_only + 1 pinned |
| violations.csv | 240 | 199 classified + 41 unclassified (FSS/BATCH-* annual summaries) |

The 39 FSS/BATCH-* rows are annual summary documents (not individual cases) — no
classification signal, correctly skipped by `--metadata-only`.

### Source 2 (FSS 회계감리결과제재 — named companies, Sessions 1+2 complete 2026-03-17)

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

### Source 1 (SFC 증선위의결정보 — Sessions 1+2 complete 2026-03-17)

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
세진, 신기테크, 모델솔루션, 라온홀딩스 were skipped at DART matching (already in dart_matches.csv
from Source 2 — same companies sanctioned by both regulators).

**Violation type distribution (enriched.json):**
asset_inflation:10, revenue_fabrication:9, liability_suppression:7, related_party:1, disclosure_fraud:1

**Cross-regulator taxonomy finding:** FSS violation_type closed list applied cleanly to SFC
decisions without modification. Zero null violation_type (vs 52/71 null in Source 2 metadata-only).
The taxonomy generalizes across FSS and SFC regulatory contexts.

**Beneish empirical additions (SFC1):**
- asset_inflation (코오롱생명과학, 일정실업, 세코닉스): M-scores predominantly below -1.78 threshold,
  continuing Source 2 AQI contradiction. Exception: 일정실업 t-2 (2022) M=-1.27 above threshold
  (early-period anomaly; violation year is 2024).
- 에스디엠 (revenue_fabrication, violation_year=2025) and 파인켐텍 (liability_suppression,
  violation_year=2025): zero DART rows — FY2025 annual statements not yet filed.

See `reports/sfc-source1-session1.md` for full journey documentation.

### violation_type distribution (violations.csv)
| Type | Count |
|------|-------|
| asset_inflation | 76 |
| revenue_fabrication | 45 |
| disclosure_fraud | 44 |
| liability_suppression | 16 |
| related_party | 13 |
| cost_distortion | 5 |
| (unclassified) | 41 |

## Data Sources (Priority Order)

See `docs/data_sources.md` for full details. Sources 1-3 = v1.0 (complete). Sources 4-8 = v2.0 (planned).

| # | Source | Status |
|---|--------|--------|
| 3 | FSS 심사·감리지적사례 (229 anonymized PDFs) | **v1.0 Complete** — violations.csv populated |
| 1 | SFC Decision Database (증선위/금융위 의결) | **v1.0 Complete** — 28 PDFs enriched, 6 DART matches, 11 Beneish rows; beneish_ratios.csv = 60 rows total |
| 2 | FSS 회계감리결과제재 (71 named companies, HWP) | **v1.0 Complete** — dart_matches.csv + beneish_ratios.csv + beneish-validation.md + research-journey.md all written |
| 4 | data.go.kr 증선위 의결정보 (potential CSV shortcut) | v2.0 — not started |
| 5–8 | CaseNote, auditor findings, audit firm reports, FSC press releases | v2.0 — not started |

## Vocabulary

All closed-list values live in `constants.py`. Never hardcode strings in pipeline code.

**FSS_VIOLATION_CATEGORIES**: revenue_fabrication, cost_distortion, asset_inflation,
liability_suppression, related_party, disclosure_fraud

**SCHEME_TYPES**: earnings_manipulation, revenue_fabrication, asset_inflation,
liability_suppression, disclosure_fraud, insider_network, cb_bw_manipulation, timing_anomaly

**BENEISH_COMPONENTS**: DSRI, GMI, AQI, SGI, DEPI, LVGI, TATA

**SIGNAL_SEED_VOCABULARY**: ~45 forensic signals (see constants.py).
Key entries: Beneish components, accrual measures, transaction patterns, audit quality
signals, fraud theory terms, disclosure_fraud, earnings_smoothing, timing_anomaly.

### OOV management
- `normalise_fss --strict` strips any OOV forensic_signals before build
- Persistent OOV indicates a prompt drift issue — fix in `FSS_ENRICHMENT_SYSTEM_PROMPT`
- Manually patched cases should be added to `data/curated/manual_patches.json`
  with `enrichment_status="pinned"` — this survives every enrichment run

## Enrichment Status Values

| Status | Meaning |
|--------|---------|
| `ok` | Full PDF text enriched via Sonnet (repaired prompt, A5) — rich signals, key_issue/fss_ruling/implications populated |
| `metadata_only` | Classified from scored_index.csv fields only — violation/scheme reliable, signals inferred |
| `pinned` | Manually corrected — skipped by both `--metadata-only` and future re-enrichment |
| `fallback` | No classification signal (FSS/BATCH-* annual summaries) |
| `image_pdf` | PDF is scanned image, no extractable text |
| `not_downloaded` | PDF not downloaded yet |

## Conventions

- All string literals → `constants.py`; all paths → `paths.py`
- `enrich_fss_cases --metadata-only` is idempotent and skips `enrichment_status="ok"` cases
- Dev-validate with `--limit 3` before full runs
- `normalise_fss --strict` is the production default; non-strict is for inspection only
- `fss_enriched.json` is the single source of truth; violations.csv is a derived output

## Ecosystem

Part of the forensic-accounting-toolkit ecosystem. Produces enforcement labels
that feed into kr-forensic-finance's supervised model training pipeline, and
case precedents for the MCP forensic search tool (tool #12).

Hub: `../forensic-accounting-toolkit/`
