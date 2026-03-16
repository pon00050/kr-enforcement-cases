# Research Journey: From FSS Enforcement Cases to Cross-Regulator Beneish Validation

**Abstract.** We set out to build a forensic accounting taxonomy from 229 anonymized Korean FSS enforcement cases, using LLM classification to tag violation types and Beneish M-Score components. Bias validation revealed that most Beneish component assignments were prompt artifacts -- only SGI and AQI survived blind re-enrichment. We then pivoted to empirical validation using named companies from two additional sources: FSS Source 2 (71 named companies with HWP attachments) and SFC Source 1 (28 accounting decision PDFs from 2025-2026 committee meetings). The combined dataset (21 companies, 60 firm-years, 54 with M-Scores) spans two independent regulators and provides the first cross-regulator test of the taxonomy. The most consequential finding is negative: AQI is not elevated in asset_inflation cases. At n=5 across both regulators, this is a pattern, not a quirk. This document records the full methodological arc: what we built, what broke, what surprised us, and what the findings actually warrant.

---

## 1. Starting Point: Building a Forensic Taxonomy from FSS Cases

The Korean Financial Supervisory Service publishes a collection of 229 anonymized enforcement PDFs under its 심사·감리지적사례 (audit inspection case) archive. Each document describes an accounting violation -- fabricated revenue, inflated assets, suppressed liabilities -- but strips the company name. We saw an opportunity: classify each case by violation type and tag the Beneish M-Score components that the violation pattern would theoretically elevate, producing a taxonomy that maps enforcement categories to quantitative forensic signals.

We built a five-stage pipeline. A scraper collected the 229 case index records and downloaded PDFs. A scoring module ranked cases by forensic relevance using keyword matching against Beneish-related terms in Korean (with a compound noun containment rule -- 매출채권 scores once for the compound, not separately for 매출 and 채권). Cases were tiered: 58 Tier 1, 57 Tier 2, 114 Tier 3. Anthropic's Haiku model classified each case into six violation categories (revenue_fabrication, asset_inflation, liability_suppression, cost_distortion, related_party, disclosure_fraud) and tagged expected Beneish components. The output was `fss_enriched.json` with 200 classified cases and `violations.csv` with 240 rows.

This looked like a clean result. It was not.

## 2. Phase A: Bias Validation

We ran four validation experiments, labeled A1 through A4. Each one eroded confidence in the Beneish component assignments while leaving the violation type taxonomy intact.

**A1 (Cohort Comparison)** compared the 65 cases enriched from full PDF text against the 134 enriched from index metadata alone. The violation type distributions were statistically comparable -- no systematic bias from the two enrichment modes. But GMI appeared inflated in revenue_fabrication cases, which prompted deeper investigation.

**A2 (Blind Prompt Test)** was the headline finding. We re-ran Haiku enrichment with a stripped prompt that removed the explicit mapping between violation types and Beneish components. TATA -- "large unexplained total accruals" -- collapsed from 100% assignment to 20%. The description is generic enough to apply to virtually any accounting irregularity; the model had been parroting the prompt's implicit suggestion rather than reasoning from case facts. LVGI dropped from 25% to 5%. GMI went to zero for revenue_fabrication cases.

**A3 (Sonnet Spot-Check)** confirmed this was a prompt-level artifact, not a Haiku-specific weakness. Sonnet with the full prompt assigned TATA at 95%. The problem was in what we asked, not in who we asked.

The surviving signals were SGI (Sales Growth Index, stable at 100% inter-model agreement for revenue_fabrication) and AQI (Asset Quality Index, stable for asset_inflation). Everything else in the beneish_components field was scaffolded by the prompt and must not be treated as ground truth.

## 3. Decision Point: Why Empirical Validation Was Needed

The taxonomy, even after pruning, encodes what language models believe about the relationship between violation types and financial indicators. It does not encode what the data shows. To test whether SGI is actually elevated in revenue_fabrication cases requires computing SGI from real financial statements of companies that committed revenue fabrication. Anonymous cases cannot be matched to financial data. We needed named companies.

## 4. Phase B: FSS Source 2

We evaluated two sources initially. SFC Source 1 (증선위 의결정보) offered ~2,700 committee records but each was a ZIP bundle containing minutes, vote records, and procedural documents with no consistent structure. Accounting decisions were buried two to three levels deep. We chose FSS Source 2 first.

FSS Source 2 (회계감리결과제재) offered 71 named companies in a clean HTML table with one HWP attachment per row. Company name and audit year were visible in the HTML itself.

Implementation surfaced a series of problems, each instructive:

**Pagination bug.** The FSS page uses a `pageIndex` parameter, not `curPage`. Our scraper silently returned page 1 twelve times, producing 120 rows of duplicates. We discovered this only through row count inspection -- the data looked plausible row by row.

**HWP format.** The pyhwp library requires Python 3.8 or below. libhwp has no Python 3.13 wheel. We used python-hwpx for the newer .hwpx format and accepted failure for binary .hwp files. Result: 17 of 71 files extracted (24%), with 54 binary HWP files unreadable.

**OpenDartReader API.** The `find_corp_code()` function returns a string for a single match, not a DataFrame. Our code assumed a DataFrame, causing all 71 companies to be flagged as ambiguous in the first run. A straightforward type-handling fix resolved this.

**DART financial statement coverage.** The summary `finstate` API returns only 14 high-level line items -- no receivables, COGS, PPE, or depreciation. We switched to `finstate_all`, which returns 159 rows with full statements. Income statement data required `sj_div='CIS'`, not `'IS'`. Even after these fixes, only 18 of 42 companies with a known violation year produced usable Beneish data. Most 기타 (unlisted) companies do not file standardized consolidated statements.

**Batch API.** The Anthropic Batch API took over 90 minutes for 71 cases with no completion signal. Sequential Sonnet calls finished in four minutes. For datasets under 100 cases, sequential wins.

## 5. Phase C: SFC Source 1

After FSS Source 2 was complete, we returned to SFC Source 1. The initial assessment -- that the document structure was too nested to parse reliably -- turned out to be partially wrong. The SFC introduced ZIP attachments for committee meeting records starting in 2025. Pre-2025 records have only minutes PDFs, and pre-2015 records have no attachments at all. But the 2025-2026 subset was navigable.

We built a three-phase scraper. Phase 1 indexed all 503 "의사록" (minutes) records via POST search across 51 pages. Phase 2 optionally downloaded minutes PDFs and scanned them for accounting keywords as a pre-filter. Phase 3 downloaded ZIPs and extracted accounting decision PDFs, filtering by filename: the PDF must start with `(의결서)` and contain one of four accounting audit keywords (조사감리결과, 위탁감리결과, 회계감리결과, 감사보고서).

Of 26 meetings with ZIP attachments, 15 contained accounting audit items. This yielded 28 accounting decision PDFs. All 28 were successfully enriched using Sonnet with full text -- 100% extraction and classification rate, a marked improvement over the 24% extraction rate for FSS Source 2's binary HWP files.

A structural discovery: the SFC anonymizes deeply. Fifteen of the 28 PDFs used OOO placeholders not only in filenames but throughout the body text. Only 13 PDFs contained identifiable company names. Of these, 11 were distinct named companies. Six matched to DART corp_codes (5 high-confidence, 1 medium). Three of these -- 코오롱생명과학, 일정실업, and 세코닉스 -- produced Beneish data, all classified as asset_inflation. This was exactly the violation category where the prior report had the weakest sample (n=2).

A fourth SFC Source 1 company, OO, was classified as revenue_fabrication but lacked COGS in its DART filings, making GMI and M-Score computation impossible. The net effect on revenue_fabrication Beneish analysis was zero -- the sample remained at n=4.

**Cross-regulator taxonomy confirmation.** The FSS violation taxonomy -- six categories derived entirely from FSS enforcement patterns -- was applied to the 28 SFC decisions without modification. Every case received a non-null violation_type. Zero cases required a new category. The taxonomy generalizes across regulators.

**Cross-source company confirmation.** 모델솔루션 appears in both FSS Source 2 (with Beneish ratio data) and SFC Source 1 (as an accounting decision PDF), classified as revenue_fabrication in both cases by independent enrichment runs against documents from two different regulators. This is the only company present in both sources.

## 6. Results

The combined dataset contains 21 companies across 60 firm-years, with 54 producing a calculable M-Score. By source: FSS Source 2 contributed 18 companies and 49 rows; SFC Source 1 contributed 3 companies and 11 rows (plus OO with 3 rows but no M-Score).

### Revenue Fabrication (n=4, unchanged)

SGI showed a median around 1.2 at the violation year -- directionally elevated, but only one case (아크솔루션스, SGI = 2.48) was clearly anomalous. 모델솔루션 flagged on DSRI (2.28) rather than SGI. Two of four companies crossed the M-Score manipulation threshold (-1.78). The taxonomy claim is not contradicted but is only clearly supported by one of four cases.

### Asset Inflation (n=5, expanded from n=2)

This is where the dataset expansion made a material difference. At n=2, the finding that AQI was below 1.0 in both asset_inflation cases was a curiosity. At n=5, it is a pattern. All five companies -- 파나케이아, 세토피아 (FSS Source 2), 코오롱생명과학, 일정실업, 세코닉스 (SFC Source 1) -- show AQI at or below 1.0 at the violation year. The taxonomy predicted the opposite: inflated assets should push AQI above 1.0. The data contradicts this across two regulators and seven years of violation dates (2018-2025).

One exception exists: 일정실업 at t-2 (2022, two years before its 2024 violation year) shows M-Score of -1.27, above the manipulation threshold. But this is an early-period anomaly, and even in that row, AQI is 1.70 -- elevated but in a pre-violation year. The overall M-Score profile of the asset_inflation cohort is deeply negative (median well below -2.5), showing no aggregate manipulation signal.

### Liability Suppression (n=2, unchanged)

LVGI was not elevated in either case. Consistent with the A2/A3 finding that LVGI was a prompt artifact.

### M-Score Aggregate

Across all 54 scored rows, 11 (20%) fall above the -1.78 manipulation threshold. At the violation year specifically, 4 of 19 companies (21%) exceed the threshold. This is stable relative to the prior report (was 22% at n=46). The rate is above the expected non-manipulator base rate (~3-5%) but below Beneish's original 50% detection rate.

## 7. Limitations

We cannot draw statistical conclusions from samples of two to five per violation type. Forty-eight percent of companies with Beneish data lack a violation type classification (down from 56% in the prior report, thanks to SFC Source 1's full-text enrichment). DEPI (Depreciation Index) was unavailable across most rows. We have no control group of non-violated companies. The SFC Source 1 contribution is limited to 2025-2026 meeting records; pre-2025 ZIPs do not exist.

The AQI finding -- below 1.0 across five asset_inflation companies -- is the strongest per-category result in the dataset, but n=5 remains well below the threshold for formal hypothesis testing. It could reflect a genuine flaw in the taxonomy mapping, a structural feature of how Korean asset inflation manifests in financial statements, or a systematic bias in the sample (e.g., companies caught for asset inflation may be those whose ratios did not flag, precisely because the inflation was designed to keep ratios stable).

## 8. What This Means for the Forensic Toolkit

The prompt-derived taxonomy works as an organizational framework. Its six violation categories applied cleanly to SFC decisions without modification -- a genuine cross-regulator confirmation. The infrastructure built across Phases B and C -- scrapers for two regulatory sources, DART matching, Beneish computation -- is operational and extensible.

The taxonomy's quantitative claims -- that specific Beneish components should be elevated for specific violation types -- are not supported by the data. The AQI contradiction in asset_inflation is the clearest negative finding: five companies, two regulators, zero showing the predicted elevation at the violation year. This is not a data insufficiency problem; it is a directional contradiction. The taxonomy mapping of AQI to asset_inflation needs revision or abandonment.

The aggregate M-Score signal (20-21% above threshold vs. 3-5% base rate) is directionally consistent with violation-year anomalies and has been stable across two dataset expansions. But it cannot distinguish violation-specific signal from general financial distress, and without a control group, the attribution remains uncertain.

The honest summary: we built a classification pipeline, discovered through rigorous self-testing that most of its Beneish component assignments were prompt artifacts, pivoted to empirical validation across two regulatory sources, and found that the taxonomy's organizational structure generalizes but its quantitative predictions do not hold. The AQI-to-asset_inflation mapping is empirically contradicted. The SGI-to-revenue_fabrication mapping is directionally supported but only clearly so in one of four cases. The aggregate detection rate is real but weak. The taxonomy stands as a classification framework. Its component-level claims need rethinking.
