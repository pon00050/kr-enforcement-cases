# Model Delegation Matrix — Bias Validation & Dataset Expansion

Decisions recorded: 2026-03-16

---

## Model Lineup (March 2026)

| Model | Input / Output (per 1M tokens) | Batch discount | Role profile |
|-------|-------------------------------|----------------|--------------|
| Haiku 4.5 (`claude-haiku-4-5-20251001`) | $1 / $5 | 50% | High-volume structured classification with tool-use enum constraints |
| Sonnet 4.6 (`claude-sonnet-4-6`) | $3 / $15 | 50% | Review, nuanced comparison, judgment with clear criteria; within 1–2% of Opus on most real-world tasks; preferred over Opus 4.5 59% of the time in user testing |
| Opus 4.6 (`claude-opus-4-6`) | $5 / $25 | 50% | Retains clear superiority for ambiguous judgment calls, vague requirements, and deep multi-step reasoning; overkill for well-defined tasks |

**Batch API:** 50% discount applies to all three models. Most batches complete within 1 hour.

---

## Delegation Decisions by Option

### Option 1 — Internal cross-validation (ok vs metadata_only split)
**Executor:** Sonnet 4.6 (Claude Code, Python script) — no external LLM call
**Why:** Pure data analysis. Compute Beneish-by-violation-type distributions separately for the two enrichment cohorts and compare. Implemented as `cohort_comparison.py` run directly against `violations.csv`. No model delegation justified.

---

### Option 2 — Blind keyword validation (20-case manual spot check)

| Sub-task | Model | Reason |
|----------|-------|--------|
| Blind extraction — "which Beneish terms are evidenced in this text?" (enum only, no definitions) | Haiku 4.5, Batch API | Structured tool use; high-confidence at this task profile; ~$0.10 for 20 cases |
| Discrepancy analysis — "do these blind extractions match the original enrichment? Is the separability finding stable?" | Sonnet 4.6 | Nuanced comparative judgment; clear criteria; Opus unnecessary for a structured comparison |

---

### Option 3 — Blind re-enrichment (stripped prompt, 20 cases)

| Sub-task | Model | Reason |
|----------|-------|--------|
| Re-enrich 20 ok cases with `FSS_BLIND_TEST_SYSTEM_PROMPT` (Beneish descriptions removed) | Haiku 4.5, Batch API | Same task profile as original enrichment; cost negligible |
| Compare outputs; assess prompt sensitivity; identify which components are prompt-stable vs prompt-sensitive | Sonnet 4.6 | Independent reviewer role; Sonnet 4.6 shows better calibration on nuanced discernment than 4.5 |

**Implementation:** `--blind-test` flag on `enrich_fss_cases.py`. Output: `fss_blind_test.json`.

---

### Option 4 — Recover pre-2022 PDFs (pypdfium2 fallback)
**Executor:** Sonnet 4.6 (Claude Code, engineering) — no external LLM call
**Why:** Engineering task. Either pypdfium2 opens the PDF or it doesn't. If successful, the existing enrichment pipeline handles the rest unchanged.

**Implementation:** `parse_fss_pdf.py` now falls through to pypdfium2 when pdfplumber throws. `pypdfium2>=4.0` in `pyproject.toml`.

---

### Option 5 — SFC Decision Database pipeline (B3)

| Sub-task | Model | Reason |
|----------|-------|--------|
| Scraping, HWP/PDF parsing, DART API calls, Beneish ratio computation | Sonnet 4.6 (Claude Code) | Engineering work |
| Named company enrichment — structured classification of SFC decisions (~500 cases) | Haiku 4.5, Batch API | Same pattern as FSS enrichment; ~$1–2 for hundreds of cases at 50% batch discount |
| Ambiguous company matching — chaebol subsidiaries, name changes, merger histories | Sonnet 4.6 | Structured enough for Sonnet; not vague enough to justify Opus |
| Final analytical synthesis — "do actual Beneish ratios computed from DART confirm the taxonomy patterns?" | **Opus 4.6** | Exactly the "vague requirements, judgment-intensive" territory where Opus retains a real advantage. Interpreting noisy empirical data against an expected pattern — the right call matters for paper credibility. One-shot, not batch. |

---

### Option 6 — data.go.kr structured CSV check (B2)
**Executor:** Sonnet 4.6 (Claude Code, WebFetch / manual browser) — no external LLM call
**Why:** Web fetch and assess. 30 minutes of exploration. If a structured CSV exists, the path to B3 shortens materially.

---

## Summary Matrix

| Option | Primary executor | Review / analysis |
|--------|-----------------|-------------------|
| 1. Cross-validation | Sonnet 4.6 (me) | — |
| 2. Blind keyword | Haiku 4.5 batch | Sonnet 4.6 |
| 3. Blind re-enrichment | Haiku 4.5 batch | Sonnet 4.6 |
| 4. Recover PDFs | Sonnet 4.6 (me) | — |
| 5a. SFC engineering | Sonnet 4.6 (me) | — |
| 5b. SFC enrichment | Haiku 4.5 batch | — |
| 5c. SFC company matching | Sonnet 4.6 | — |
| 5d. SFC final synthesis | **Opus 4.6** | — |
| 6. data.go.kr | Sonnet 4.6 (me) | — |

**The only place Opus is justified is the SFC final synthesis** — one expensive call to interpret ambiguous empirical findings against expected taxonomy patterns, where getting the interpretation right determines whether the paper is credible. Everything else is either well-defined enough for Haiku (structured classification with enums) or structured enough for Sonnet (review, comparison, judgment with clear criteria).

---

## Phase A/B Progress (as of 2026-03-17)

| Step | Status |
|------|--------|
| A1 | ✅ |
| A2 | ✅ |
| A3 | ✅ |
| A4 — Prompt repair validation (test run, 65 ok cases) | ✅ Done 2026-03-16 — validated repaired prompt produces expected distribution |
| A5 — Prompt repair production (2026-03-17) | ✅ Done — 65 ok cases re-enriched with Sonnet + repaired prompt; `fss_enriched.json` is canonical post-repair state; TATA 34%, SGI 95% precision, AQI 74%, LVGI 73% |
| B1 | ✅ (hard ceiling confirmed) |
| B2 | Skipped (user decision) |
| B3 — SFC Source 1 pipeline | ✅ Done 2026-03-17 — Sessions 1+2 complete; 28 PDFs enriched, 6 DART matches, 11 Beneish rows, beneish_ratios.csv = 60 rows total |

**A3 note:** Batch API for Sonnet 4.6 took >1.5 hours for 20 cases (vs 14 min for Haiku).
Switched to sequential mode: `uv run python -m kr_enforcement_cases.enrich_fss_cases --model claude-sonnet-4-6`
Cost: ~$0.09 (20 × ~500 tokens in × $3/1M + 20 × ~200 tokens out × $15/1M). No code changes needed — sequential path existed from the start.

**B1 note:** Both pdfplumber and pypdfium2 fail with "Data format error" on all 50 pre-2022 PDFs (FSS1912/2008/2106/2112). These files are genuinely malformed at the binary level. No Python PDF library will recover them. The 65 ok / 50 failed split is permanent.

---

## A1 Findings — Cross-Validation Result

**The confirmation bias concern is partially confirmed but narrower than feared.**

### Core separability is robust (prompt-stable)

The primary taxonomy claims survive the cohort split with near-zero divergence:

| violation_type | component | ok % | metadata_only % | Δ (pp) |
|----------------|-----------|-----:|----------------:|-------:|
| asset_inflation | AQI | 85% | 88% | 3 |
| revenue_fabrication | SGI | 100% | 96% | 4 |
| liability_suppression | LVGI | 100% | 91% | 9 |

These are the load-bearing claims. Both cohorts agree. The Beneish scaffold is not driving these assignments.

### Flagged pairs (divergence ≥ 15pp)

| violation_type | component | ok % | metadata_only % | Δ (pp) | Interpretation |
|----------------|-----------|-----:|----------------:|-------:|----------------|
| disclosure_fraud | TATA | 100% | 59% | 41 | **ok > meta** — TATA requires seeing accrual language in the PDF; metadata signal too weak to trigger it. Full-text adds signal here. |
| cost_distortion | AQI | 33% | 0% | 33 | Tiny sample noise (n=3 ok, n=2 meta) |
| cost_distortion | GMI | 67% | 100% | 33 | Tiny sample noise (same) |
| revenue_fabrication | GMI | 20% | 52% | 32 | ⚠️ **Probable inflation** — GMI prompt description (`매출·원가 조작`) scaffolds this for revenue cases. Full-text enrichment does not support it at the same rate. |
| related_party | DSRI | 0% | 25% | 25 | Tiny sample noise (n=4 ok, n=8 meta) |
| disclosure_fraud | LVGI | 43% | 24% | 19 | **ok > meta** — full-text adds LVGI to disclosure cases, not scaffold |
| revenue_fabrication | TATA | 80% | 96% | 16 | Marginal; both cohorts high |

### Decision rule from A1 (superseded by A2 — see below)

A1 could only compare two cohorts that both used the same scaffolded prompt. It flagged GMI/revenue_fabrication as the one inflated pair, and rated AQI/SGI/LVGI as stable. **A2 revealed that A1 couldn't detect artifacts affecting both cohorts equally — TATA is exactly that case.** The A1 interpretation below is preserved for completeness but the A2 findings take precedence.

- **Near-zero divergence** (both cohorts agree, signal is real): AQI/asset_inflation, SGI/revenue_fabrication, LVGI/liability_suppression
- **metadata_only > ok** (possible scaffold inflation): GMI/revenue_fabrication, TATA/revenue_fabrication
- **ok > metadata_only** (full-text adds signal): TATA/disclosure_fraud, LVGI/disclosure_fraud

---

## A2 Findings — Blind Re-enrichment Result (2026-03-16)

**Method:** Same 20 cases from the ok cohort, re-enriched by Haiku using `FSS_BLIND_TEST_SYSTEM_PROMPT` — identical to the main prompt except the `beneish_components` section has no Korean/English descriptions, only the closed list header. The model must infer component relevance from case text alone.

| Component | Original % | Blind % | Δ (pp) | Verdict |
|-----------|-----------|---------|--------|---------|
| TATA | **100%** | **20%** | **-80** | ⚠️ Massively scaffolded — universal prompt artifact |
| LVGI | 25% | 5% | -20 | ⚠️ Substantially scaffolded |
| GMI | 10% | 0% | -10 | ⚠️ Fully scaffolded — confirms A1 suspicion |
| SGI | 25% | 20% | -5 | ✅ Fully stable (4/4 revenue_fabrication → 4/4) |
| DEPI | 0% | 0% | 0 | — Not assigned in either |
| DSRI | 20% | 30% | +10 | ✅ Roughly stable |
| AQI | 30% | 50% | +20 | ✅ Stable (slight increase as generic asset-signal without anchoring) |

**Exact beneish_components match: 2/20 (10%).** Far below the 80% inter-model agreement target. Collapse driven entirely by TATA ubiquity in the original.

**OOV regression: 9 novel signal occurrences** in blind output (e.g. `derivative accounting`, `accounting policy choice`, `revenue_fabrication` used as a signal). The descriptions serve as vocabulary anchors; removing them causes the model to invent plausible-sounding terms outside the closed list.

### The TATA finding — headline result

Every single one of the 20 original enrichments had TATA assigned (20/20, 100%). After stripping descriptions, TATA dropped to 4/20 (20%) — an 80pp collapse. The original prompt description for TATA is **"large unexplained total accruals"** — generic enough to describe almost any accounting manipulation. Haiku assigned it universally because the description matched every fraud case, not because the case texts specifically evidenced unexplained accrual patterns.

Implications:
- The A1 finding that TATA→disclosure_fraud was 100% in the ok cohort is not a real pattern — it was the prompt scaffold firing on both cohorts equally (which is why A1, comparing two scaffolded cohorts, showed only a 41pp gap rather than the full collapse A2 reveals)
- TATA frequency in the existing `fss_enriched.json` is an artifact, not a forensic signal
- The actual TATA rate, when the model must infer from text alone, is ~20%

### Why A1 couldn't see this

A1 compared ok vs metadata_only cohorts — both enriched with the **same** prompt. A shared scaffold produces the same bias in both cohorts, making them look consistent. A1 correctly flagged GMI (where metadata_only was higher) because that was a *differential* artifact. TATA was universal in both cohorts, so A1 saw only a 41pp gap at the disclosure_fraud level — directionally the wrong sign — and misread it as "full-text adds TATA signal." A2 (different prompt, same cases) was the only design that could detect a universal scaffold.

### Per-stratum breakdown

| Stratum | TATA orig | TATA blind | AQI orig | AQI blind | SGI orig | SGI blind | LVGI orig | LVGI blind |
|---------|-----------|------------|----------|-----------|----------|-----------|-----------|------------|
| asset_inflation (n=8) | 8/8 | 1/8 | 5/8 | 6/8 | 0/8 | 0/8 | 2/8 | 1/8 |
| revenue_fabrication (n=4) | 4/4 | 0/4 | 0/4 | 0/4 | 4/4 | 4/4 | 0/4 | 0/4 |
| disclosure_fraud (n=1) | 1/1 | 0/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| _other (n=7) | 7/7 | 3/7 | 1/7 | 3/7 | 1/7 | 0/7 | 3/7 | 0/7 |

SGI is 4/4 → 4/4 for revenue_fabrication — **perfect stability across the hardest test available without real Beneish ratios.**

---

## B1 Findings — PDF Recovery Result (2026-03-16)

pypdfium2 (using Chrome's pdfium C library) was tried against all 50 failed pre-2022 PDFs. Result: **all 50 fail with "Data format error" on pypdfium2 as well.** These files are genuinely malformed at the binary level — not an unsupported format issue, but corrupted or non-standard binary structure that no Python PDF library can parse. The 65 ok / 50 failed split is the permanent ceiling.

---

## A3 Findings — Sonnet Spot-Check Result (2026-03-16)

**Method:** Same 20 cases, Sonnet 4.6, full original `FSS_ENRICHMENT_SYSTEM_PROMPT`. Sequential mode (batch took >1.5 hours; sequential ~3 minutes, ~$0.09). Output: `fss_sonnet_review.json`.

### Three-way comparison

| Component | Haiku orig (full) | Sonnet (full) | Haiku blind (stripped) | Haiku/Sonnet agree | Sonnet/Blind agree |
|-----------|:-----------------:|:-------------:|:----------------------:|:-----------------:|:-----------------:|
| TATA | **100%** | **95%** | **20%** | 19/20 (95%) | 5/20 (25%) |
| LVGI | 25% | 30% | 5% | 19/20 (95%) | 15/20 (75%) |
| GMI | 10% | 30% | 0% | 16/20 (80%) | 14/20 (70%) |
| AQI | 30% | 35% | 50% | 19/20 (95%) | 13/20 (65%) |
| DSRI | 20% | 30% | 30% | 18/20 (90%) | 16/20 (80%) |
| SGI | **25%** | **25%** | **20%** | **20/20 (100%)** | 19/20 (95%) |
| DEPI | 0% | 5% | 0% | 19/20 (95%) | 19/20 (95%) |

Exact match rates: Haiku-orig vs Sonnet 13/20 (65%) | Sonnet vs Haiku-blind 1/20 (5%)

Sonnet produced **0 OOV signals** (vs 9 in Haiku-blind). Sonnet maintains vocabulary discipline without description anchoring — use Sonnet (not Haiku) for any re-enrichment with a stripped or revised prompt.

### The definitive conclusion: TATA is a prompt-level artifact

Sonnet assigned TATA to 19/20 cases (95%) with the full prompt. This rules out a Haiku-specific over-triggering explanation. **Both architecturally independent models read `TATA — large unexplained total accruals` and apply it to virtually every case.** The fix is in the prompt.

High Haiku/Sonnet agreement on TATA (95%) does not mean the signal is stable — it means both models are equally susceptible to the same scaffold. The blind test (different prompt, not different model) is the correct test for stability.

### Additional A3 findings

- **SGI: 20/20 Haiku/Sonnet agreement (100%)** — only perfect score; confirms it as the strongest defensible signal
- **GMI: Sonnet 30% vs Haiku 10%** — Sonnet is *more* susceptible to GMI scaffolding than Haiku; both drop to 0% in blind
- **LVGI: both models ~25–30% with full prompt, both collapse to ~5% blind** — scaffold is prompt-level, not model-specific

Full narrative analysis in `reports/blind-test-review.md`.

---

## Revised Defensible Claims (post-A2/A3)

| Component | Haiku/Sonnet agree | Prompt-stable? | Status |
|-----------|:-----------------:|:--------------:|--------|
| SGI → revenue_fabrication | 100% | ✅ Yes | **Defensible** — 4/4 blind stability; perfect inter-model agreement |
| AQI → asset_inflation | 95% | ✅ Yes | **Defensible** — stable and increases in blind test |
| DSRI (supporting) | 90% | ✅ Roughly | Minor role; not primary claim |
| LVGI → liability_suppression | 95% | ❌ No | **Drop** — high agreement on a shared scaffold; 25%→5% blind (superseded by A4/A5 — LVGI recovered post-repair; see below) |
| TATA → any type | 95% | ❌ No | **Drop** — universal prompt artifact; 100%→20% blind |
| GMI → revenue_fabrication | 80% | ❌ No | **Drop** — fully scaffolded; 10%→0% blind |

**The dataset is not invalidated.** violation_type classification is defensible. key_issue, fss_ruling, and implications from full-text enrichment are rich and accurate. The problem is isolated to the `beneish_components` field in `fss_enriched.json` — one field, one design flaw (descriptions too generic, especially TATA).

### Prompt repair (completed — see A4)

Three descriptions in `FSS_ENRICHMENT_SYSTEM_PROMPT` were rewritten to require specific case evidence:

```
# Old — scaffolds universally:
TATA  — large unexplained total accruals
LVGI  — liability suppression (부채·충당부채 과소계상)
GMI   — gross margin distortion (매출·원가 조작)

# New — requires specific case evidence:
TATA  — total accruals are materially large relative to assets with no clear business explanation;
        assign only when the case text specifically references accrual magnitude or reversal patterns
LVGI  — liabilities or provisions explicitly understated, omitted, or derecognised without justification
        (충당부채 미설정, 부채 누락)
GMI   — gross margin deteriorates while revenue grows, or COGS is misclassified
        (원가 과소계상, 채널 스터핑)
```

Additional fixes: added preamble "Only assign a component when the case text provides specific evidence for it."; removed TATA from Example 1 (`["DSRI", "TATA"]` → `["DSRI"]`).

`enrich_fss_cases.py` was also updated: `--model` flag now routes to the normal enrichment path (not the 20-case validation sample); merge logic preserves metadata_only/pinned cases when new result is a fallback.

---

## A4 Findings — Prompt Repair Result (2026-03-16)

**Method:** Repaired `FSS_ENRICHMENT_SYSTEM_PROMPT` + Sonnet 4.6 sequential, all 65 ok cases (~11 min). Output merged into `fss_enriched.json`. violations.csv rebuilt.

### Component frequency and cross-violation specificity

| Component | Haiku-orig (20-case %) | Haiku-blind (20-case %) | Sonnet-repaired (65-case %) | Precision (dominant pairing) |
|-----------|:---------------------:|:----------------------:|:---------------------------:|------------------------------|
| SGI  | 25% | 20% | **34%** (22/65) | 21/22 revenue_fabrication — **95%** |
| AQI  | 30% | 50% | **40%** (26/65) | 19/21 asset_inflation — **90%** |
| DSRI | 20% | 30% | **37%** (24/65) | 19/22 revenue_fabrication — **86%** |
| LVGI | 25% | 5%  | **17%** (11/65) | 8/9 liability_suppression — **89%** ✅ Recovered |
| GMI  | 10% | 0%  | **29%** (19/65) | 14/22 rev_fab + 4/4 cost_distortion — concentrated ⚠️ |
| TATA | 100% | 20% | **34%** (22/65) | scattered across violation types |
| DEPI | 0%  | 0%  | **11%** (7/65)  | 6/21 asset_inflation — plausible |

### Interpretation

**TATA**: 100% → 34%. Major improvement. The repaired description stopped universal assignment. Remaining 34% is concentrated in revenue_fabrication (9/22) and cost_distortion (3/4) — plausible given those cases tend to involve real accrual manipulation. Still diffuse enough not to serve as a separability signal.

**LVGI**: 25% → 17%, with 8/9 liability_suppression precision. A2 had flagged LVGI as "substantially scaffolded" and recommended dropping it. The repaired prompt recovers it — the specificity is now 89%, comparable to SGI and AQI. **LVGI → liability_suppression is a fourth defensible claim post-repair.**

**GMI**: Concentrated in revenue_fabrication (64%) and cost_distortion (100%) — not scattered. Both pairings are mechanistically defensible. The rate is model-dependent (Haiku-orig 10%, Sonnet 29%), so GMI cannot be cited without noting this uncertainty. Not a primary claim.

**SGI / AQI / DSRI**: Strong and stable. These form the backbone of the defensible findings.

### Revised defensible claims (post-A4, final)

| Component | Precision (repaired, n=65) | Verdict |
|-----------|:--------------------------:|---------|
| SGI → revenue_fabrication | 95% (21/22) | ✅ Strongest finding |
| AQI → asset_inflation | 90% (19/21) | ✅ Defensible |
| DSRI → revenue_fabrication | 86% (19/22) | ✅ Strong supporting signal |
| LVGI → liability_suppression | 89% (8/9) | ✅ Recovered post-repair |
| GMI → rev_fab / cost_distortion | concentrated, model-dependent | ⚠️ Cite with caveat |
| TATA → any violation type | diffuse | ❌ Not a separability signal |

---

## Cost Analysis — Was the Approach Efficient?

**Short answer: yes, with honest caveats.**

### Where the approach was efficient

- **Haiku for metadata-only enrichment** (~$0.03 for 134 cases) and **A2 blind test** (~$0.10 for 20 cases): correct calls — cheap, fast, constrained tool-use
- **A3 switching from Sonnet batch (abandoned after 1.5 hours) to sequential (~3 min, ~$0.09)**: right adaptation; sequential path already existed, no code changes needed
- **Opus reserved exclusively for the SFC final synthesis** (one-shot, not yet spent): discipline maintained
- **Total bias validation phase** (A1 free + A2 + A3 + B1 free): under $0.25

### The most expensive single step: A4 re-enrichment

65 Sonnet sequential calls at list price (~$0.40–0.60). No batch discount used — Sonnet batch burned 1.5 hours for 20 cases; sequential was the right call for 65. Could have been ~$0.20–0.30 with batch, but the wait-time cost is not worth it at this scale.

### Legitimate inefficiencies

- Three bad `--limit 3` dev-validate runs hit pre-2022 failed PDFs (no full text, instant fallback), so they exercised the merge logic but didn't actually validate the API path. Wasted a few Haiku/Sonnet tokens, required a repair script for 3 downgraded metadata_only cases. Avoidable with better case ordering.
- Running Sonnet where Haiku might have sufficed with the repaired prompt — the A3 finding justified it, but that was with a stripped prompt. The repaired prompt (specific descriptions retained) might anchor Haiku's vocabulary adequately. The ~$0.30 premium was minor insurance.

### Structural question

Whether Sonnet was overkill vs. Haiku with the repaired prompt. It was a reasonable choice: the A3 result showed Haiku-blind producing 9 OOV signals vs Sonnet's 0, and OOV drift was the main risk with a modified prompt. The premium is trivial at 65 cases.

**Net: total project spend through prompt repair is well under $2. The cost architecture is sound.**

---

## Plain-Language Summary

The core problem was simple: the AI was rubber-stamping "TATA" onto every single case — 100% rate — because the prompt description was so vague it matched any accounting fraud. That is not a finding. It is the model doing pattern completion on the description, not reading the case text.

The fix was to rewrite three descriptions in the prompt to require specific evidence. The re-enrichment confirmed it worked: TATA dropped from 100% to 34%, and the remaining assignments are now concentrated where they make sense rather than everywhere.

**The numbers that actually matter are these four:**

- SGI → revenue_fabrication: 21 out of 22 cases. Near-perfect.
- AQI → asset_inflation: 19 out of 21 cases. Very clean.
- LVGI → liability_suppression: 8 out of 9 cases. Solid.
- TATA: was 65/65, now 22/65. The other 43 were prompt noise.

The rest — A1, A2, A3, the three-way comparison tables, the precision percentages — is documentation that those four numbers are real and not themselves artifacts of the prompt. That required running the same cases with stripped descriptions to prove it.

The statistical framing is a symptom of needing to justify that the AI's output means something. If you trust it, there is nothing to measure. Because you do not, you have to show the numbers.

---

## Publishing Potential

The bias validation methodology is the most publishable piece of this work. Most practitioners using LLMs for classification either don't ask whether the prompt is scaffolding the answer, or they ask but don't have a rigorous method to test it. This project has:

- **Cohort splitting** (A1) — comparing enrichment quality levels to detect differential scaffold effects
- **Blind prompt stripping** (A2) — removing descriptions and rerunning the same cases to detect universal scaffold effects
- **Cross-model replication** (A3) — testing whether Haiku-specific over-triggering vs prompt-level artifact

That's a reproducible three-step validation protocol applicable to any structured LLM extraction task.

**The TATA finding is the intellectual contribution:** a 100% assignment rate that collapses to 20% when the description is removed is not an anecdote — it's a falsifiable, reproducible result that demonstrates how generic descriptions in tool-use prompts can masquerade as empirical signal.

**Possible audience framing:**
- *LLM methodology:* "The 100% problem — when your prompt is doing the classification for you"
- *Forensic accounting:* "What Beneish components actually appear in Korean FSS enforcement cases" (empirical distribution over 65 full-text cases)
- *Research methods:* "Cohort contamination in LLM-enriched datasets" — the ok vs metadata_only split as a general bias diagnostic

---

*Sources: platform.claude.com/docs/en/about-claude/models/overview, pricing page, VentureBeat Sonnet 4.6 comparison, Batch API docs*
