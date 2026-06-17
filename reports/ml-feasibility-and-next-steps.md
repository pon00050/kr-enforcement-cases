# ML Feasibility Assessment & Next Steps

> Date: 2026-03-17
> Context: Post-v1.0.0 review of what the kr-enforcement-cases dataset can and cannot support, with a roadmap for closing the gaps.

---

## 1. Project Positioning

This project is best classified as **Tier 3: Research Dataset Infrastructure** — not a fraud prediction system, not a screening tool, and not the Korean equivalent of SEC's Accounting Quality Model (AQM). AQM ingests thousands of filings automatically with real-time data feeds integrated into enforcement workflow. This is a research pipeline that produces structured data from regulatory documents.

The precise description:

> A reproducible pipeline that converts Korean financial enforcement documents into structured forensic accounting data with LLM-assisted violation taxonomy and linked financial indicators.

That's a harder tier to build correctly than ML systems, which can be assembled from existing models. The pipeline, taxonomy design, and bias validation here are the durable contributions — not the label counts.

---

## 2. What the Dataset Actually Is Today

### Current data inventory

| Asset | Rows | Notes |
|-------|------|-------|
| `violations.csv` | 240 | 65 full-text enriched, 134 title-inferred, 1 manual, 40 unclassified |
| `beneish_ratios.csv` | 60 | Enforcement companies only (49 Source 2 + 11 Source 1) |
| `dart_matches.csv` | 86 | 90% match rate across Source 2 + Source 1 |

### Label quality tiers

| Status | Count | Evidence strength |
|--------|-------|-------------------|
| `ok` | 65 | Full PDF text → LLM extraction (defensible for research) |
| `metadata_only` | 134 | Title/metadata → LLM inference (weaker, use with caution) |
| `pinned` | 1 | Manual correction |
| unclassified | 40 | FSS/BATCH annual summaries, no violation type assigned |

**Label leakage risk:** The 134 `metadata_only` labels were inferred from case titles using the same text signal a model would use as an input feature. Any model trained on these cases with text features is potentially circular. The 65 `ok` cases (full-text enriched) are the defensible core for research use.

---

## 3. Why ML Is Not Feasible Today

The central constraint is structural, not a matter of sample size alone. Three problems block a classifier:

### Problem 1: The dataset is positive-class only

Every row in `violations.csv` is an enforcement case. A binary classifier requires:

```
fraud (positive):      ~200 cases  ← you have this
non-fraud (negative):  ~2,000+ company-years  ← you don't
```

Without a denominator of non-enforced companies, you cannot estimate `P(enforcement | financial features)`. You can only describe `P(features | enforcement)`, which is a very different question and not useful for prediction.

This is the single most common error in fraud ML. It is not a data volume problem — it is a sampling design problem.

### Problem 2: Beneish ratios exist only for enforcement targets

`beneish_ratios.csv` has 60 rows, all enforcement companies. A model needs the same ratios computed for the comparison group over the same time window. Computing those ratios requires DART API calls at scale for thousands of company-years — feasible via kr-beneish, but not yet done.

### Problem 3: Temporal leakage

Korean enforcement lag is typically 3-7+ years between the fraud year and the enforcement decision. A model cannot legitimately see financial data from the years between fraud and enforcement — that window contains information that would not be available at prediction time. Handling this correctly requires a precise time-indexed feature construction approach, not just a train/test split.

---

## 4. What IS Feasible Today (No New Data Required)

The following analyses can be run now with what exists in `violations.csv` and `beneish_ratios.csv`:

| Analysis | Source | Publishable? |
|----------|--------|--------------|
| Enforcement pattern descriptive statistics | violations.csv (200 labeled cases) | Yes |
| Violation type distribution over time | `결정년도` column | Yes |
| Beneish component association with violation types | beneish_ratios.csv — correlation table, not regression | Yes, with caveats |
| **Regulatory detection lag analysis** | `회계결산일` vs `결정년도` | **Yes — high value, zero new data** |
| Case similarity / forensic precedent search | violations.csv + enrichment fields | Yes — retrieval, not prediction |

### Detection lag as the priority first analysis

The detection lag analysis is the highest-ROI immediate step. It requires no new data, no new code, and answers a policy-relevant question with direct practical implications:

> "How long does it take Korean regulators to detect and sanction accounting fraud?"

**Proposed output schema:**

```
case_id
financial_year      ← 회계결산일 (year the fraud occurred)
enforcement_year    ← 결정년도 (year of enforcement decision)
lag                 ← enforcement_year - financial_year
violation_type
regulator           ← FSS vs SFC
source              ← Source 1 / 2 / 3
```

**Analyses within reach:**

- Distribution of lag (median, IQR, range)
- Lag by violation type — does revenue fabrication get caught faster than disclosure fraud?
- Lag by regulator — does SFC act faster than FSS?
- Trend over time — is detection improving?

**International context:** Korean findings can be benchmarked against published enforcement lag estimates from the SEC (approximately 3-4 years for accounting fraud), ESMA, and PCAOB audit enforcement. That comparison alone has publication value.

---

## 5. The Path to ML: What Would Actually Be Required

ML becomes viable when three conditions are met. These are research design decisions, not engineering tasks — the choices made here determine study validity.

### Step 1: Define the control group (the critical unlock)

Construct a set of company-years not subject to enforcement, matched to your enforcement cases. Options:

- **Full universe:** All KOSPI/KOSDAQ listed companies in kr-company-registry (3,949) over the enforcement window — maximum n, but highly imbalanced (~1:50 fraud ratio)
- **Industry-matched:** Match each enforcement company to 3-5 non-enforced companies in the same GICS sector and size decile — better comparability, harder to construct
- **Propensity-matched:** Match on pre-fraud Beneish ratios — most rigorous but requires Step 2 to be complete first

The choice is a research judgment call with trade-offs between statistical power and comparability.

**Important:** A control group alone does not make ML "possible." It makes it _designed_. The matching assumptions, time windows, and survivorship bias handling all determine whether any resulting model is valid.

### Step 2: Compute Beneish ratios for the control group

kr-beneish already has the computation logic. It needs to run at scale against DART financial statements for the control group companies and years. This requires significant DART API calls (potentially thousands of filings) but is technically straightforward.

### Step 3: Define a clear, leakage-free prediction target

- Binary: enforced / not enforced (simplest, most interpretable)
- Multi-class: violation type (uses the taxonomy, but small n per class at current scale)
- The feature cutoff date must be the financial year end — no features from after the fraud year

### Step 4: Address class imbalance explicitly

At likely ratios of 1:20 to 1:50 (fraud to non-fraud), standard classifiers will default to predicting no fraud. Require explicit strategy: oversampling (SMOTE), undersampling, or cost-sensitive learning.

---

## 6. The Audit Report Opportunity (KAM + Audit Opinions)

### The core insight

The dataset is currently retrospective: it describes the state *after* enforcement. Adding auditor signals creates a temporal structure:

```
BEFORE: audit opinion + KAM flags + going concern warnings  (pre-enforcement)
  ↓
AFTER:  enforcement action or no enforcement action
```

This enables the research question: **"Do auditor disclosures predict future enforcement?"**

### What's actually available via DART

| Signal | Extraction difficulty | Coverage | Recommended |
|--------|----------------------|----------|-------------|
| Audit opinion (적정/한정/부적정/의견거절) | **Low** — structured field via DART API | All listed companies, all years | Yes, Phase 1 |
| Going concern flag (계속기업 불확실성) | **Low** — structured in DART filings | All listed companies | Yes, Phase 1 |
| KAM text (핵심감사사항) | **High** — HTML sub-document parsing | Post-2017 (large cos); post-2020 (all listed) | Phase 2 only |
| Emphasis of matter (강조사항) | Medium — semi-structured | Varies by year | Phase 2 |

### Critical caveat: audit opinions need a denominator too

Pulling audit opinions for the 86 matched enforcement companies alone is not sufficient for any comparative analysis. To test whether non-clean audit opinions predict enforcement, you need audit opinions for the comparison group as well. This means audit opinion extraction must be paired with control group construction (Step 1 above) — not done independently.

### KAM-specific constraints

- **KAM only exists from fiscal year 2017** (large companies) / **2020** (all listed). Most of your enforcement cases — especially FSS Source 3 (anonymized) — predate this window.
- KAM text is frequently boilerplate. Whether it carries genuine predictive signal for fraud is an open empirical question, not a settled fact. Build the extraction first; validate signal second.
- DART stores audit reports as structured HTML sub-documents with filing-year-dependent structure. This is a non-trivial parsing project, best scoped as a separate module or separate repo.

---

## 7. Recommended Execution Order

| Phase | Task | Effort | Dependency | Expected value |
|-------|------|--------|-----------|----------------|
| **Now** | Detection lag analysis (violations.csv only) | ~1 day | None | High — publishable, policy-relevant |
| **Next** | Extract audit opinions + going concern flags for 86 matched companies AND a control universe | Low-medium | Control group design decision | High — enables auditor behavior analysis |
| **Later** | Construct non-fraud control group from kr-company-registry | Medium | Research design decision on matching | Critical — unlocks all comparative analysis |
| **Later** | Compute Beneish ratios for control group at scale via kr-beneish | Medium | Control group list | Critical — enables feature parity |
| **Future** | KAM text extraction pipeline (HTML sub-document parsing) | High | Sources 4-8 to improve post-2017 coverage | Medium — open research question on signal value |
| **Future** | Supervised ML training | High | All of the above | Possible only after control group + ratio parity |

---

## 8. Honest Framing

### What the project is

> A well-engineered forensic accounting research dataset pipeline with partial enforcement labeling, covering 240 Korean FSS/SFC cases with a 6-type violation taxonomy, Beneish component linkage, and bias-tested LLM enrichment.

### What it is not (yet)

- A fraud prediction system
- A screening tool comparable to SEC's AQM
- Ready for supervised ML training without a matched control group

### What makes it valuable despite those limits

1. **The pipeline** — reproducible extraction from 3 regulatory sources, scalable to Sources 4-8
2. **The taxonomy** — 6 violation types with controlled vocabulary, bias-tested across 3 LLM models
3. **The Beneish linkage** — enforcement signals mapped to financial indicator components, empirically validated
4. **The rarity** — almost no open datasets combine regulatory enforcement + structured violation types + financial ratios for Korea
5. **The discipline** — the pipeline explicitly tracks label quality tiers; it does not claim more than the data supports

### The actual gap

The gap between here and ML is **research design**, not engineering. The scraping, parsing, enrichment, and normalization infrastructure is complete. What's missing are methodological decisions: how to define a control group, what the matching criteria are, and how to handle temporal structure. Those decisions require judgment about causal inference, not more code.
