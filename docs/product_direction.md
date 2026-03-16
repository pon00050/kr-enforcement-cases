# Product Direction — Korean Forensic Accounting Intelligence Platform

> Strategic positioning memo. Written 2026-03-17 after Sources 1, 2, and 3 were complete.
> v1.0 is now public on GitHub. This document exists to force a direction decision before
> v2.0 source integration begins, because each direction requires meaningfully different
> things to be built on top of what is already here.

---

## What This Project Has Become

By the time all identified data sources are integrated, this project is a **Korean forensic
accounting intelligence platform**: a continuously-updatable dataset of named enforcement
cases with financial signal validation, auditor quality linkage, and cross-regulator
coverage (FSS and SFC independently classifying the same companies), backed by a
bias-tested extraction methodology. It is the empirical infrastructure for whatever
research question about Korean accounting fraud one wants to ask next.

What it is not, and will not become without a specific decision to make it so, is a
generalizable framework. Everything here is tuned to the Korean regulatory context — the
FSS taxonomy, the DART API, the SFC decision letter format, the K-IFRS account names in
the Beneish mapping. The methodology generalizes; the pipeline does not. Porting it to
SEC enforcement actions or ESMA decisions would require rebuilding most of the
source-specific layers.

---

## The Commercial Ceiling on the Dataset Itself

With that much work on collecting and cleaning data, it had better be something people
actually find useful — to the extent that they would feel comfortable paying for the
completed version.

The dataset itself is unlikely to be the sellable thing. Raw enforcement case data — even
well-structured, taxonomy-tagged, Beneish-enriched — faces a ceiling: the underlying FSS
and SFC decisions are public, and a sufficiently motivated buyer could reconstruct the
dataset themselves. "We did the engineering work so you don't have to" is a service pitch,
not a product pitch. It is also a pitch that gets weaker over time as LLM-assisted data
pipelines become more accessible.

---

## Three Directions Worth Paying For

What would be genuinely worth paying for is what the dataset enables, rather than the
dataset itself.

### 1. The Forensic Screening Tool

A practitioner — an auditor, a short-seller research desk, a compliance officer at a
Korean brokerage — who can query "which listed KOSDAQ companies currently show the same
financial signature as the 11 SFC-sanctioned asset_inflation cases from this dataset" is
paying for a decision-support tool, not a dataset. The dataset is the training ground; the
tool is the product. That is a recurring subscription, not a one-time data sale.

What needs to be built on top of what exists: a scoring model that applies the
violation-type-specific Beneish signatures to current DART filings across the listed
universe, a query interface, and an output format practitioners can act on.

### 2. The Audit and Due Diligence Workflow

M&A advisors and PE firms doing Korean target diligence currently have no systematic way
to check whether a company's financial profile resembles enforcement case precedents. A
report that says "this company's AQI, SGI, and LVGI pattern over the past three years sits
in the 90th percentile of pre-enforcement companies in our dataset" is something a deal
team would pay for per-engagement.

What needs to be built on top of what exists: a report template, a per-company scoring
function that places a target company in the empirical distribution of the enforcement
dataset, and a delivery mechanism (PDF report or API endpoint) suitable for deal workflows.

### 3. The Methodology, Licensed to Institutions

Regulators, exchanges, and large audit firms have their own data and their own teams but
often lack the methodology — the bias-validated taxonomy, the LLM extraction pipeline, the
cross-regulator confirmation framework. Licensing the approach rather than the output is a
different commercial model entirely.

What needs to be built on top of what exists: documentation rigorous enough to be audited,
a reproducibility package, and a licensing structure. The A2/A3 bias validation work and
the cross-regulator taxonomy confirmation are the most defensible components to license
because they represent intellectual contributions that are not simply re-engineerable from
public data.

---

## The Gap Risk

The honest risk is that the project lands in a gap: too rigorous and expensive to build to
give away, but not packaged into a workflow product that a buyer can point to and say "that
saves me X hours" or "that catches Y risk." The data collection work is necessary but not
sufficient.

The three directions above are not mutually exclusive in the long run, but they require
different near-term build priorities:

- **Screening tool** requires a live scoring pipeline against current DART data and a
  query interface — engineering-forward.
- **Due diligence workflow** requires a client-facing report format and per-engagement
  delivery — go-to-market forward.
- **Methodology license** requires documentation and reproducibility packaging —
  academic/institutional forward.

Building all three simultaneously without a primary commitment produces none of them well.

---

## The Decision

Someone needs to decide, before v2.0 source integration begins, which of those three
directions the project is heading. The v1.0 dataset is public — but the design choices
made in the remaining source integration steps (which features to compute, how to structure
the output schema, what to publish vs. keep proprietary) look different depending on the
answer.
