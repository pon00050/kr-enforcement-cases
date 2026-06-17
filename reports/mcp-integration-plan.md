# MCP Integration Plan — kr-enforcement-cases

## What MCP enables

MCP (Model Context Protocol) lets Claude (or any MCP client) directly query the
enforcement dataset as a tool during conversation. No copy-pasting, no intermediate
API layers.

| MCP capability | What it means for this project |
|---|---|
| **Tools** | Claude calls `search_violations(query="revenue fabrication", sector="manufacturing")` mid-conversation and gets structured results back |
| **Resources** | Claude can read `violations.csv`, `beneish_ratios.csv`, or `fss_enriched.json` on demand |
| **Prompts** | Pre-built prompt templates like "analyze this company against known enforcement patterns" that users can invoke |

This is **tool #12** in the forensic-accounting-toolkit ecosystem. Core use case: a user
asks Claude "what enforcement precedents exist for this pattern?" and Claude queries the
dataset live.

## Why skip CLI (Typer) and API (FastAPI)

1. **The consumer is an LLM, not a human.** A Typer CLI or FastAPI server would be
   intermediate layers that nobody calls directly — Claude is the end user. MCP is
   the native interface for that.

2. **MCP servers are trivially simple.** A basic MCP server is ~50-80 lines of Python
   using the `mcp` SDK. Less code than a FastAPI app with equivalent functionality.

3. **The data layer already exists.** `paths.py`, `constants.py`, and the curated
   JSON/CSV files are the backend. The MCP server is just a thin query layer on top.

4. **CLI/API only add value if humans or non-LLM systems consume the data.** The only
   downstream consumers are Claude (in Claude Code or the desktop app) and
   kr-forensic-finance's training pipeline (which reads files directly). There is no
   user for a REST API.

**When FastAPI would become relevant:** if a web UI or external system integration is
needed later. But for tool #12, MCP is the direct path.

## Proposed MCP server

```
src/kr_enforcement_cases/mcp_server.py
```

### Tools to expose

| Tool | Input | Output | Data source |
|---|---|---|---|
| `search_cases` | violation_type, sector, keyword, tier | Matching rows with case metadata | violations.csv |
| `get_case_detail` | case_id | Full enriched record (key_issue, fss_ruling, implications, signals) | fss_enriched.json |
| `search_beneish` | company, m_score_threshold, component | Beneish ratios with M-Score flag | beneish_ratios.csv |
| `get_precedents` | scheme_type, forensic_signals | Semantically matched cases ranked by signal overlap | fss_enriched.json + sfc_source1_enriched.json |

### Resources to expose

| Resource | URI pattern | Description |
|---|---|---|
| Violation taxonomy | `enforcement://taxonomy` | FSS_VIOLATION_CATEGORIES + SCHEME_TYPES from constants.py |
| Signal vocabulary | `enforcement://signals` | SIGNAL_SEED_VOCABULARY — closed list of forensic signals |
| Dataset summary | `enforcement://stats` | Row counts, source coverage, enrichment status distribution |

### Prompt templates

| Prompt | Purpose |
|---|---|
| `analyze-pattern` | Given a suspected scheme type, retrieve matching precedents and Beneish benchmarks |
| `company-risk-profile` | Given a company name, pull DART matches + Beneish ratios + any enforcement history |

## Dependencies

- `mcp` Python SDK (add to pyproject.toml)
- Existing: `paths.py`, `constants.py`, pandas/polars for CSV/JSON reads

## Open questions

- **Hosting model:** stdio (Claude Code local) vs SSE (remote, e.g. for Claude desktop app)?
  Both are supported by the MCP SDK. stdio is simplest for local dev.
- **Cross-source merge:** `get_precedents` needs to query across Source 1, 2, and 3
  enriched JSONs. Worth building a unified view (DuckDB?) or keep separate reads?
- **Auth:** Not needed for local stdio. If SSE is added later, token-based auth required.
