# SFC Source 1 — Relevance to Earlier Pipeline Phases

> **Status (2026-03-17):** All work described below has been completed. See reports/sfc-source1-session1.md for execution results.

The 28 SFC Source 1 PDFs connect to the earlier work in three ways:

**1. They extend the Beneish validation dataset (the core gap)**

Source 2 gave you only n=4 revenue_fabrication and n=2 asset_inflation companies with Beneish data — too small for any statistical claim. The SFC PDFs are another source of *named companies* with specific violation types. Extract company names → DART match → compute Beneish ratios → add rows to `beneish_ratios.csv`. The entire pipeline (match_dart_companies.py, compute_beneish.py) is already built and reusable.

**2. The taxonomy built from Source 3 can be tested here**

Source 3 (229 anonymized FSS PDFs) produced the violation taxonomy (revenue_fabrication, asset_inflation, etc.) and calibrated the enrichment prompts. The A2/A3 bias validation showed only SGI and AQI are defensible separability signals. The SFC PDFs are a different regulator's decisions on the same underlying violations — they're an independent test of whether the taxonomy labels hold across institutions.

**3. PDF extraction will work better here than Source 2 did**

Source 2's Achilles heel was binary HWP files — 54/71 cases returned `extract_status="failed"`, forcing metadata-only enrichment with no full text. These SFC files are PDFs. pdfplumber already handles the FSS PDFs reliably. You should get near-100% text extraction, which means Sonnet gets real case text to classify from rather than guessing from company name alone.

**Practical implication:** The natural next step is to run these 28 PDFs through the same enrich → DART match → Beneish pipeline that Source 2 went through. The 모델솔루션㈜ cross-source hit is a preview of what you'll find — some of these companies also appear in Source 2, which is independent confirmation of the same violation.
