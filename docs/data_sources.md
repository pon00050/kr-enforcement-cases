# Enforcement Case Data Sources

> All identified Korean financial enforcement data sources, ranked by priority.
> Sources 1-3 are complete (v1.0). Sources 4-8 are planned for v2.0.
> Last updated: 2026-03-17

---

## Why This Matters

FSS enforcement data is the highest-quality source of confirmed fraud labels for supervised model training. Systematic enforcement data collection has produced 328 cases across two regulators (v1.0) with potential to expand to 500–1,000+ cases from the remaining five sources (v2.0).

Annual run rate (2022–2024): ~70 sanctions/year, ~7 prosecutor referrals/year. 2025 plan: ~160 companies targeted for review.

---

## Sources (ranked by priority)

### Priority 1: SFC Decision Database (증선위/금융위 의결)

| Field | Value |
|-------|-------|
| URL (증선위) | `https://fsc.go.kr/no020102` |
| URL (금융위) | `https://fsc.go.kr/no020101` |
| Records | 1,292 (증선위) + 1,411 (금융위) |
| Format | PDF and ZIP attachments (full 의결서) |
| Companies | **Named** — with violations, fine amounts, sanction details |
| Coverage | All SFC/FSC business (not just accounting — needs filtering) |
| Known examples | SK에코플랜트 (₩54억), 카카오모빌리티 (₩41.4억), STX, 모델솔루션, 지란지교시큐리티 |
| Note | Likely the single most comprehensive source of named enforcement decisions |

### Priority 2: FSS 회계감리결과제재 (named company sanctions)

| Field | Value |
|-------|-------|
| URL | `https://fss.or.kr/fss/job/accnutAdtorInfo/list.do?acntnWrkCode=02&menuNo=200617` |
| Records | 71 named companies |
| Format | HWP attachments |
| Fields | Company name, market, industry, numbered violations with amounts, sanctions (과징금/감사인지정/해임권고/검찰통보), 증선위 의결 date |
| Sample | ㈜동성화인텍 — 5 violations, 과징금 + 감사인지정 3년 + 검찰통보 |
| Parsing | `python-hwp`, LibreOffice conversion, or `pyhwp`/`hwp5` |
| Note | Curated subset of Priority 1 — accounting-specific only |

### Priority 3: FSS 심사·감리지적사례 (anonymized case PDFs)

| Field | Value |
|-------|-------|
| URL | `https://fss.or.kr/fss/bbs/B0000135/list.do?menuNo=200448` |
| Records | 229 cases across 23 pages |
| Format | **PDF** — consistent 5-section structure |
| Sections | Metadata (case FSS/YYMM-NN, 쟁점 분야, K-IFRS ref, 결정일, 회계결산일), §1 회사의 회계처리, §2 위반 지적, §3 판단 근거, §4 감사절차 미흡, §5 시사점 |
| Companies | **Anonymized** (A사, B사) — violation mechanics and K-IFRS taxonomy |
| Violation breakdown (2024 H1) | Investment securities 30%, revenue/COGS 15%, inventory/fixed assets 15%, embezzlement concealment 15% |
| Cross-reference | Can de-anonymize by matching violation details against named sanctions in Priority 1–2 |
| Note | Easiest to parse (PDF, consistent structure). Good for building K-IFRS violation taxonomy. |

### Priority 4: data.go.kr 증선위 의결정보 (potential structured shortcut)

| Field | Value |
|-------|-------|
| URL | `https://data.go.kr/data/3036480/fileData.do` |
| Records | Unknown |
| Format | Possibly CSV/Excel (file data download) |
| Note | **If this has structured tabular data, it shortcuts all PDF/HWP parsing.** Needs manual verification. |

### Priority 5: CaseNote 금융감독원 제재 (third-party database)

| Field | Value |
|-------|-------|
| URL | `https://casenote.kr/금융감독원/제재/` |
| Records | 4,805 total FSS sanctions (all sectors) |
| Format | Already structured: institution name, date, industry, sanction details, targets |
| Note | Needs filtering for accounting-specific sanctions. Third-party — may save significant scraping effort. |

### Priority 6: 감사인 감리결과 개선권고사항 (auditor-side)

| Field | Value |
|-------|-------|
| URL | `https://fss.or.kr/fss/bbs/B0000291/list.do?menuNo=200620` |
| Records | Most recent: 14 firms reviewed |
| Format | Published for 3 years from issuance |
| Note | When a company gets sanctioned, the auditor often gets a parallel finding. Links auditor quality to enforcement. |

### Priority 7: 회계법인사업보고서 (audit firm context)

| Field | Value |
|-------|-------|
| URL | `https://fss.or.kr/fss/bbs/B0000137/list.do?menuNo=200450` |
| Records | 254 registered accounting firms |
| Note | Average audit fee declining to ₩46.8M — FSS flagged as quality risk. Enables analysis: do certain audit firms' clients get sanctioned disproportionately? |

### Priority 8: FSC 보도자료 (press releases)

| Field | Value |
|-------|-------|
| URL | `https://fsc.go.kr/no010101` |
| Records | Estimated 50–100 named cases (only notable ones get press releases) |
| Filter | "회계처리기준 위반" |

### Other Sources (low priority)

| Source | URL suffix (fss.or.kr) | Notes |
|--------|----------------------|-------|
| 회계감리업무절차 | `menuNo=200446` | Process description, not data |
| 회계법인품질관리매뉴얼 | `menuNo=200449` | Auditor standards |
| 회계현안설명회 | (FSS annual briefings) | Trend statistics, violation category charts |

---

## Build Order

**Completed (v1.0):** Priority 3 → Priority 2 → Priority 1. Executed in reverse priority order because Priority 3 (anonymized PDFs) was easiest to parse and established the taxonomy, Priority 2 (named companies) enabled DART-linked Beneish validation, and Priority 1 (SFC decisions) provided cross-regulator confirmation.

**Planned (v2.0):**
1. Check data.go.kr (Priority 4) — if structured CSV exists, may shortcut remaining scraping
2. Evaluate CaseNote (Priority 5) — 4,805 records, possibly already structured
3. Auditor-side findings (Priority 6) — links audit firm quality to enforcement
4. Press releases (Priority 8) — supplementary named cases

---

## Current Status (as of 2026-03-17)

- **Source 3** (Priority 3 — FSS 심사·감리지적사례): **Complete.** 229 cases scored and tiered, 200 enriched (65 ok + 134 metadata_only + 1 pinned), violations.csv = 240 rows.
- **Source 2** (Priority 2 — FSS 회계감리결과제재): **Complete.** 71 companies indexed, 71 enriched, 64 DART matches, beneish_ratios.csv = 49 rows (18 companies × ~3 years).
- **Source 1** (Priority 1 — SFC 증선위의결정보): **Complete.** 28 accounting PDFs extracted and enriched, 6 DART matches, 11 Beneish rows; beneish_ratios.csv combined total = 60 rows.
- **Source 4** (data.go.kr): Not started (skipped by user decision).
- **Sources 5–8**: Not started.
