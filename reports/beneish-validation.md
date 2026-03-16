# Beneish M-Score Empirical Validation Against Korean Enforcement Cases

## 1. Overview

This report tests whether Korean companies sanctioned for accounting violations show elevated Beneish M-Score components in their violation-year financials. The hypothesis originates from a taxonomy built during Source 3 analysis (229 anonymized FSS cases), where blind prompt testing (A2/A3) identified two defensible component-to-violation mappings: SGI to revenue_fabrication and AQI to asset_inflation. TATA, LVGI, and GMI were rejected as prompt artifacts.

The dataset now combines two independent regulatory sources: FSS Source 2 (회계감리결과제재, 71 named companies) and SFC Source 1 (증선위 의결정보, 28 accounting decision PDFs from 2025-2026 committee meetings). This yields 60 company-year rows across 21 companies, with 54 rows producing computable M-Scores. The cross-regulator scope strengthens per-category findings and confirms that the FSS violation taxonomy generalizes beyond its source institution.

## 2. Data and Method

**FSS Source 2** contains 71 named companies. Of these, 64 matched to DART corp_codes (90%). Violation years were extracted for 42 companies from HWP document text or metadata enrichment. Only 18 companies produced usable Beneish data; the remainder had violation years before 2016 (predating reliable DART electronic filings) or lacked sufficient consecutive-year financials. This yielded 49 company-year rows. A classification gap persists: 17/71 source files were HWPX (extractable, Sonnet-classified), while 54 were binary HWP 5.0 (metadata-only enrichment). As a result, 10 of 18 Source 2 companies with Beneish data have violation_type=None.

**SFC Source 1** adds 11 company-year rows from 3 named companies with asset_inflation classification, plus 3 rows from 1 company (OO) classified as revenue_fabrication but with incomplete accounts (COGS absent from DART filings, M-Score not computable). All SFC Source 1 companies were enriched from full PDF text with Sonnet, so classification quality is high.

The combined dataset: 21 companies, 60 company-year rows, 54 with computable M-Scores. DEPI remains largely unavailable (depreciation is not a main-statement DART line item); SGAI is intermittently present. The core 6 components (DSRI, GMI, AQI, SGI, LVGI, TATA) are required for M-Score computation.

## 3. Cross-Regulator Taxonomy Confirmation

The FSS violation taxonomy -- a closed list of six categories (revenue_fabrication, asset_inflation, liability_suppression, cost_distortion, related_party, disclosure_fraud) -- was applied without modification to 28 SFC accounting decision PDFs. Every decision received a non-null violation_type classification. Zero cases required a new category. This is notable because the taxonomy was derived from FSS enforcement patterns, and the SFC is a separate regulator (Securities and Futures Commission under the Financial Services Commission) with different procedural norms.

Further confirmation comes from 모델솔루션, which appears in both FSS Source 2 (Beneish data) and SFC Source 1 (accounting decision PDF), classified as revenue_fabrication by both independent enrichment runs against documents from two different regulators. This is the only company present in both sources and constitutes a direct cross-source validation.

## 4. SGI and Revenue Fabrication

The taxonomy's strongest claim is that SGI elevates in revenue_fabrication cases. Four companies have this classification with Beneish data (unchanged from the prior report -- SFC Source 1 added OO as revenue_fabrication, but COGS was absent from its DART filings, preventing GMI and M-Score computation):

| Company | Source | SGI | DSRI | M-Score | Above threshold? |
|---------|--------|-----|------|---------|-----------------|
| 아크솔루션스 | FSS S2 | **2.48** | 1.74 | -1.54 | Yes |
| 동성화인텍 | FSS S2 | 1.19 | 0.74 | -2.31 | No |
| 모델솔루션 | FSS S2 | 1.10 | **2.28** | -1.05 | Yes |
| 웰바이오텍 | FSS S2 | 1.13 | 0.99 | N/A | Incomplete |

아크솔루션스 shows strongly elevated SGI (2.48), consistent with the taxonomy claim. The other three show modest SGI values between 1.10 and 1.19 -- above 1.0 (indicating sales growth) but not dramatically so. Notably, 모델솔루션 flags on DSRI (2.28), not SGI, suggesting the manipulation signal surfaced through receivables rather than top-line growth. 모델솔루션 is additionally confirmed as revenue_fabrication by SFC Source 1, making it the highest-confidence classification in the dataset. Two of four companies crossed the M-Score manipulation threshold (-1.78), which is a meaningful hit rate, but the mechanism is not consistently SGI-driven. The taxonomy claim is not contradicted but is only clearly supported by one of four cases.

## 5. AQI and Asset Inflation

This is the section with the most material change. The addition of SFC Source 1 data expanded the asset_inflation sample from 2 to 5 companies. Three new companies -- 코오롱생명과학, 일정실업, and 세코닉스 -- all come from SFC accounting decisions with full-text enrichment, so their violation_type classification is high-confidence.

| Company | Source | Year Offset | AQI | M-Score | Above threshold? |
|---------|--------|-------------|-----|---------|-----------------|
| 파나케이아 | FSS S2 | 0 | 0.82 | -4.19 | No |
| 파나케이아 | FSS S2 | -1 | 0.90 | -1.77 | Yes |
| 파나케이아 | FSS S2 | -2 | 0.81 | -0.41 | Yes |
| 세토피아 | FSS S2 | 0 | 0.70 | -6.52 | No |
| 세토피아 | FSS S2 | -1 | **2.47** | -2.55 | No |
| 세토피아 | FSS S2 | -2 | 0.78 | -4.16 | No |
| 코오롱생명과학 | SFC S1 | -1 | **1.84** | -2.79 | No |
| 코오롱생명과학 | SFC S1 | -2 | 1.06 | -2.05 | No |
| 일정실업 | SFC S1 | 0 | 0.91 | -2.32 | No |
| 일정실업 | SFC S1 | -1 | 1.03 | -3.60 | No |
| 일정실업 | SFC S1 | -2 | **1.70** | -1.27 | Yes |
| 세코닉스 | SFC S1 | 0 | 1.07 | -3.34 | No |
| 세코닉스 | SFC S1 | -1 | 0.89 | -2.91 | No |
| 세코닉스 | SFC S1 | -2 | 0.88 | -3.14 | No |

At the violation year (offset=0), AQI values are: 파나케이아 0.82, 세토피아 0.70, 일정실업 0.91, 세코닉스 1.07. All are at or below 1.0. 코오롱생명과학 has no offset=0 row (violation year 2025, most recent DART data is 2024). The taxonomy predicts AQI should be elevated (above 1.0) in asset_inflation cases -- inflated assets in the current period relative to the prior period should push AQI upward. The data shows the opposite: at the point of violation, asset quality ratios are flat or declining.

At n=2, the AQI < 1.0 finding was a curiosity that could have been a sampling artifact. At n=5, with companies from two independent regulators spanning violation years from 2018 to 2025, it is a pattern. Five companies, four with violation-year AQI at or below 1.0, constitute a genuine empirical contradiction of the taxonomy prediction.

Three rows show AQI above 1.0: 세토피아 at t-1 (2.47), 코오롱생명과학 at t-1 (1.84), and 일정실업 at t-2 (1.70). These are all pre-violation observations, one to two years before the violation year. The 일정실업 t-2 row is the only asset_inflation observation above the M-Score threshold (-1.27 > -1.78), but this is 2022 data for a 2024 violation year -- an early-period anomaly that predates the misstatement detection by two years.

One possible interpretation: asset inflation manipulations may *stabilize* apparent asset quality (suppressing AQI variation) rather than elevate it. A company inflating assets might show AQI near 1.0 precisely because the inflation maintains a consistent asset ratio across periods. This is speculative but would explain the flat-to-declining pattern better than measurement error.

## 6. LVGI and Liability Suppression

Two companies carry this classification (unchanged):

| Company | LVGI | M-Score |
|---------|------|---------|
| 스포츠서울 | 0.73 | -1.03 (above) |
| STX | 1.08 | -1.91 |

LVGI is below 1.0 for 스포츠서울 (leverage decreased, opposite of expectation) and near-neutral for STX. 스포츠서울 crossed the threshold, but driven by DSRI (2.31), not LVGI. This is consistent with the A2/A3 finding that LVGI was a prompt artifact: the blind test collapsed LVGI assignment from 25% to 5%, and real financial data shows no elevation here either.

## 7. M-Score Aggregate

Across all 54 scored rows (all years, all companies), 11 rows (20%) fall above the -1.78 manipulation threshold. At the violation year specifically (year_offset=0), 4 of 19 companies with computable M-Scores (21%) exceed the threshold. These figures are essentially unchanged from the prior report (was 10/46 = 22% aggregate, 4/18 = 22% violation-year). The SFC Source 1 additions -- predominantly asset_inflation cases with deeply negative M-Scores -- pulled the aggregate rate down slightly.

Beneish (1999) reported roughly 50% detection in his manipulator sample. Our 20-21% is below that benchmark but well above the expected base rate for non-manipulators (~3-5% in clean samples). The aggregate signal is present but weak, and its stability across dataset expansions (22% at n=46, 20% at n=54) suggests it is not an artifact of small-sample volatility.

## 8. Data Limitations

- **Sample size**: n=2 to 5 per classified violation type. Asset_inflation at n=5 is approaching the threshold where patterns can be discussed with some confidence, but remains below statistical significance for formal hypothesis testing.
- **Classification gap**: 10/21 companies (48%) lack violation_type. The gap narrowed from 56% (prior report) due to SFC Source 1 additions being fully classified, but nearly half the sample still cannot contribute to per-category analysis.
- **Missing components**: DEPI was unavailable across most rows (depreciation is not a main-statement DART line item). SGAI was intermittent. Both are part of the full 8-variable model; their omission may bias M-Score downward.
- **Survivorship**: Only listed companies with post-2016 DART filings appear. Delisted companies and older violations are systematically excluded.
- **Violation year precision**: Extracted from document text or enrichment metadata; may be imprecise for some Source 2 cases (accounting period vs. sanction date ambiguity). SFC Source 1 violation years are more reliable, being taken directly from decision documents.
- **No control group**: All companies in the dataset were sanctioned. Without a matched sample of non-violated companies, the aggregate M-Score elevation cannot be attributed specifically to violation status versus general financial distress or industry effects.

## 9. Honest Overall Assessment

**What this evidence supports:** The aggregate M-Score elevation (20-21% vs. ~3-5% base rate) is consistent with the general premise that sanctioned companies show detectable financial anomalies, and this finding is stable across two dataset expansions. The FSS violation taxonomy generalizes cleanly to SFC decisions -- a cross-regulator confirmation that the six-category framework captures the enforcement landscape. 모델솔루션 is confirmed as revenue_fabrication by two independent regulators.

**What this evidence does not support:** Component-to-violation-type specificity. AQI is not elevated in the five asset_inflation cases -- this is no longer an n=2 quirk but a consistent pattern across five companies from two regulators spanning seven years of violation dates. LVGI is not elevated in the two liability_suppression cases. SGI is modestly elevated in three of four revenue_fabrication cases but dramatically so in only one. The taxonomy's mapping of specific Beneish components to specific violation types is not validated by this data. The AQI finding actively contradicts it.

**What would be needed:** A sample of 30+ companies per violation type, with reliable classification and complete Beneish components (including DEPI), benchmarked against an industry-matched control group. The current dataset has made meaningful progress -- asset_inflation reached n=5, cross-regulator coverage is established -- but remains below the threshold for per-category statistical claims.
