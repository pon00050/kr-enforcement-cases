# kr-enforcement-cases

Structured dataset of Korean financial enforcement cases from FSS and SFC regulators, with LLM-enriched violation taxonomy, DART-linked Beneish ratios, and a bias-validated extraction methodology.

Built for forensic accounting research, supervised model training, and regulatory pattern analysis.

## What This Produces

| Output | Rows | Description |
|--------|------|-------------|
| `reports/violations.csv` | 240 | One row per violation per case — violation type, scheme type, forensic signals, Beneish components |
| `reports/beneish_ratios.csv` | 60 | 7 Beneish components + M-Score per company-year, computed from DART financials |
| `reports/scored_index.csv` | 229 | All FSS cases scored by forensic relevance (Tier 1/2/3) |
| `data/curated/dart_matches.csv` | 77 | Named companies matched to DART corp_codes (90% match rate) |

## Data Sources (v1.0)

Three Korean regulatory enforcement data sources, fully integrated:

| Source | Regulator | Cases | Named? | Status |
|--------|-----------|-------|--------|--------|
| FSS 심사·감리지적사례 | FSS | 229 | Anonymized | 200 enriched, 65 with full PDF text |
| FSS 회계감리결과제재 | FSS | 71 | Named | 64 DART-matched, 49 Beneish rows |
| SFC 증선위의결정보 | SFC | 28 | Mixed (15 redacted, 13 named) | 28 enriched, 6 DART-matched, 11 Beneish rows |

Five additional sources have been identified for v2.0 (see `docs/data_sources.md`).

## Violation Taxonomy

Six violation types, applied consistently across both FSS and SFC decisions:

| Type | Count (violations.csv) |
|------|------------------------|
| `asset_inflation` | 76 |
| `revenue_fabrication` | 45 |
| `disclosure_fraud` | 44 |
| `liability_suppression` | 16 |
| `related_party` | 13 |
| `cost_distortion` | 5 |

## Beneish Component Validation

Each violation type maps to specific Beneish M-Score components. The mapping was bias-tested using a three-step protocol (cohort splitting, blind prompt stripping, cross-model replication) documented in `docs/model_delegation_matrix.md`.

Defensible mappings (post-repair):

| Component | Violation type | Precision |
|-----------|---------------|-----------|
| SGI | revenue_fabrication | 95% |
| AQI | asset_inflation | 74% |
| LVGI | liability_suppression | 73% |
| DSRI | revenue_fabrication | 86% (supporting) |

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

For DART API access (Source 2 and Beneish computation), register at https://opendart.fss.or.kr/ and add to `.env`:

```
DART_API_KEY=your_key_here
```

## Pipeline

The full pipeline runs in stages. Each stage is idempotent and can be re-run independently.

### Source 3 — FSS anonymized case PDFs (229 cases)

```bash
uv run python -m kr_enforcement_cases.scrape_fss_cases      # scrape index + download PDFs
uv run python -m kr_enforcement_cases.score_cases            # score and tier cases
uv run python -m kr_enforcement_cases.download_prioritised   # download Tier 1+2 PDFs
uv run python -m kr_enforcement_cases.parse_fss_pdf          # extract text from PDFs
uv run python -m kr_enforcement_cases.enrich_fss_cases       # LLM enrichment (full text)
uv run python -m kr_enforcement_cases.enrich_fss_cases --metadata-only  # enrich remaining from metadata
uv run python -m kr_enforcement_cases.normalise_fss --strict # validate vocabulary
uv run python -m kr_enforcement_cases.build_violation_db     # build violations.csv
```

### Source 2 — FSS named company sanctions (71 companies)

```bash
uv run python -m kr_enforcement_cases.scrape_fss_source2     # scrape index + download HWP
uv run python -m kr_enforcement_cases.extract_hwp            # extract text from HWP/HWPX
uv run python -m kr_enforcement_cases.enrich_source2         # LLM enrichment
uv run python -m kr_enforcement_cases.match_dart_companies   # match to DART corp_codes
uv run python -m kr_enforcement_cases.compute_beneish        # compute Beneish ratios
```

### Source 1 — SFC accounting decisions (28 PDFs)

```bash
uv run python -m kr_enforcement_cases.scrape_sfc_source1 --index-only  # index 503 meetings
uv run python -m kr_enforcement_cases.scrape_sfc_source1 --download    # download ZIPs + extract PDFs
uv run python -m kr_enforcement_cases.parse_sfc1_pdfs      # extract text from PDFs
uv run python -m kr_enforcement_cases.enrich_sfc1_cases    # LLM enrichment
```

Use `--limit 3` on any enrichment step for dev validation before full runs.

## Tests

```bash
uv run pytest tests/ -v
```

## Project Structure

```
src/kr_enforcement_cases/
  constants.py             — Closed vocabulary lists (violation types, scheme types, Beneish components)
  paths.py                 — Canonical file paths
  scrape_fss_cases.py      — Source 3 scraper
  score_cases.py           — Forensic relevance scoring
  download_prioritised.py  — Tiered PDF downloader
  parse_fss_pdf.py         — PDF text extraction (pdfplumber + pypdfium2 fallback)
  enrich_fss_cases.py      — LLM enrichment (Sonnet full text + Haiku metadata-only)
  normalise_fss.py         — Vocabulary validation
  build_violation_db.py    — violations.csv builder
  scrape_fss_source2.py    — Source 2 scraper
  extract_hwp.py           — HWP/HWPX text extraction
  enrich_source2.py        — Source 2 LLM enrichment
  scrape_sfc_source1.py    — Source 1 three-phase scraper
  parse_sfc1_pdfs.py       — Source 1 PDF extraction
  enrich_sfc1_cases.py     — Source 1 LLM enrichment
  match_dart_companies.py  — DART corp_code matching (exact + fuzzy + LLM review)
  compute_beneish.py       — Beneish M-Score computation from DART financials

reports/                   — Pipeline outputs (committed)
data/curated/              — Enriched JSON (gitignored), dart_matches.csv (committed)
docs/                      — Data source catalogue, methodology documentation
```

## Key Design Decisions

- **Enrichment model**: Sonnet for full-text cases (repaired prompt, A5); Haiku for metadata-only fallback. The prompt was bias-validated through A1-A5 phases.
- **Beneish formula**: Core 6 components required (DSRI, GMI, AQI, SGI, LVGI, TATA); DEPI/SGAI optional (notes-only disclosure in DART).
- **Manual patches**: `data/curated/manual_patches.json` stores corrected cases with `enrichment_status="pinned"`, applied after every enrichment write.
- **All string literals** live in `constants.py`; all paths in `paths.py`.

## Ecosystem

Part of the forensic-accounting-toolkit ecosystem. Produces:
- Enforcement labels for supervised model training (kr-forensic-finance)
- Case precedents for the MCP forensic search tool

## Documentation

| File | Contents |
|------|----------|
| `docs/data_sources.md` | All 8 identified enforcement data sources with status |
| `docs/model_delegation_matrix.md` | Model delegation decisions + full bias validation journey (A1-A5, B1-B3) |
| `reports/beneish-validation.md` | Empirical Beneish findings against DART financials |
| `reports/blind-test-review.md` | A2/A3 blind prompt validation + Sonnet spot-check |
| `reports/research-journey.md` | Full project narrative |
| `reports/sfc-source1-session1.md` | SFC Source 1 extraction + enrichment results |

## Roadmap

**v1.0** (current): Sources 1-3 complete. 328 cases across two regulators, 60 Beneish company-year rows, bias-validated taxonomy.

**v2.0** (planned): Integrate Sources 4-8 — data.go.kr structured CSV, CaseNote third-party database, auditor-side findings, audit firm context, FSC press releases. See `docs/data_sources.md` for details.

## License

MIT — see [LICENSE](LICENSE).
