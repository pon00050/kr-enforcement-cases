"""
cohort_comparison.py — A1 internal cross-validation.

Compares Beneish-by-violation-type distributions between the 'ok' cohort (full PDF
enrichment) and the 'metadata_only' cohort. Tests whether separability findings are
consistent across enrichment quality levels or inflated by prompt scaffolding.

Output: reports/cohort-comparison.md

Usage:
  uv run python -m kr_enforcement_cases.cohort_comparison
"""

from __future__ import annotations

import csv
import logging
import sys
from collections import defaultdict
from pathlib import Path

from .paths import REPORTS_DIR, VIOLATIONS_CSV

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
log = logging.getLogger(__name__)

BENEISH = ["DSRI", "GMI", "AQI", "SGI", "DEPI", "LVGI", "TATA"]
COHORTS = ["ok", "metadata_only"]
DIVERGENCE_THRESHOLD = 15  # percentage points


def _pct(count: int, total: int) -> float:
    return 100 * count / total if total else 0.0


def analyse(violations_csv: Path | None = None) -> str:
    """Run cohort comparison and return a markdown report string."""
    path = violations_csv or VIOLATIONS_CSV

    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    # Filter to classified cases in ok / metadata_only cohorts
    cases = [
        r for r in rows
        if r.get("enrichment_status") in COHORTS and r.get("violation_type")
    ]
    log.info(
        "Loaded %d total rows; %d classified cases in ok/metadata_only cohorts",
        len(rows), len(cases),
    )

    # counts[cohort][violation_type][component] = case_count_with_component
    counts: dict[str, dict[str, dict[str, int]]] = {
        c: defaultdict(lambda: defaultdict(int)) for c in COHORTS
    }
    totals: dict[str, dict[str, int]] = {c: defaultdict(int) for c in COHORTS}

    for row in cases:
        cohort = row["enrichment_status"]
        vtype = row["violation_type"]
        comps = {c.strip() for c in row["beneish_components"].split(",") if c.strip()}
        totals[cohort][vtype] += 1
        for comp in comps:
            if comp in BENEISH:
                counts[cohort][vtype][comp] += 1

    all_vtypes = sorted({vt for c in COHORTS for vt in counts[c]})
    n_ok_total = sum(totals["ok"].values())
    n_meta_total = sum(totals["metadata_only"].values())

    lines = [
        "# Cohort Comparison: ok vs metadata_only",
        "",
        "Internal cross-validation of Beneish-by-violation-type distributions.",
        "Tests whether component–violation separability is consistent across enrichment quality levels,",
        "or whether it is inflated by the `FSS_ENRICHMENT_SYSTEM_PROMPT` Beneish description scaffold.",
        "",
        f"- **ok** cohort (full PDF + Haiku, rich signal): **{n_ok_total}** classified cases",
        f"- **metadata_only** cohort (index fields only): **{n_meta_total}** classified cases",
        "",
        f"Divergence flag threshold: **{DIVERGENCE_THRESHOLD} percentage points**",
        "",
    ]

    flagged_pairs: list[tuple[str, str, float, float, float]] = []

    for vtype in all_vtypes:
        n_ok = totals["ok"].get(vtype, 0)
        n_meta = totals["metadata_only"].get(vtype, 0)
        lines.append(f"## {vtype}")
        lines.append(f"n = {n_ok} (ok) | {n_meta} (metadata_only)")
        lines.append("")
        lines.append("| Component | ok % | metadata_only % | Δ (pp) | Flag |")
        lines.append("|-----------|-----:|----------------:|-------:|------|")
        for comp in BENEISH:
            pct_ok = _pct(counts["ok"][vtype].get(comp, 0), n_ok)
            pct_meta = _pct(counts["metadata_only"][vtype].get(comp, 0), n_meta)
            diff = abs(pct_ok - pct_meta)
            flag = "⚠️" if diff >= DIVERGENCE_THRESHOLD else ""
            lines.append(
                f"| {comp} | {pct_ok:.0f}% | {pct_meta:.0f}% | {diff:.0f} | {flag} |"
            )
            if diff >= DIVERGENCE_THRESHOLD:
                flagged_pairs.append((vtype, comp, pct_ok, pct_meta, diff))
        lines.append("")

    lines.append("## Summary")
    lines.append("")

    if not flagged_pairs:
        lines.append(
            "**No divergence ≥ 15pp detected.** Beneish-by-violation separability is "
            "consistent across ok and metadata_only cohorts. The confirmation bias concern "
            "is marginal — the finding is unlikely to be purely prompt-scaffolded."
        )
    else:
        lines.append(
            f"**{len(flagged_pairs)} component/violation pair(s) show divergence ≥ {DIVERGENCE_THRESHOLD}pp.** "
            "The metadata_only cohort may be inflating separability through prompt scaffolding. "
            "Report ok-cohort numbers only for any defensible finding."
        )
        lines.append("")
        lines.append("| violation_type | component | ok % | metadata_only % | Δ (pp) |")
        lines.append("|----------------|-----------|-----:|----------------:|-------:|")
        for vtype, comp, pct_ok, pct_meta, diff in sorted(flagged_pairs, key=lambda x: -x[4]):
            lines.append(
                f"| {vtype} | {comp} | {pct_ok:.0f}% | {pct_meta:.0f}% | {diff:.0f} |"
            )

    lines.append("")
    lines.append("### Interpretation guide")
    lines.append("")
    lines.append(
        "- **Same pattern in both cohorts** → separability is real; prompt scaffold is not the driver."
    )
    lines.append(
        "- **metadata_only more extreme (e.g. 100% vs 85%)** → numbers are prompt-inflated; "
        "use ok-cohort figures only."
    )
    lines.append(
        "- **ok shows weaker or no separability** → original finding was spurious; "
        "revisit taxonomy claims."
    )
    lines.append("")
    lines.append("---")
    lines.append("*Generated by `cohort_comparison.py` (Phase A1 cross-validation)*")

    return "\n".join(lines)


def main() -> None:
    report = analyse()
    out = REPORTS_DIR / "cohort-comparison.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    log.info("Wrote %s", out)
    sys.stdout.buffer.write(report.encode("utf-8", errors="replace") + b"\n")


if __name__ == "__main__":
    main()
