# ETF Query MCP Usage

This project exposes the ETF Text2SQL v3 runtime as a local stdio MCP server for Claude Code. The current local default is the uncommitted v3.4 P2 branch for time-series trend queries.

## Install

```bash
cd etf-query
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with the runtime credentials:

```env
DASHSCOPE_API_KEY=...
ETF_SSH_PASSWORD=...
```

## Register In Claude Code

From the project root:

```bash
claude mcp add etf-query --scope project -- .venv/bin/python etf_mcp_server.py
```

Then start Claude Code and run `/mcp` to confirm `etf-query` is connected.

## Tools

- `query_etf(question, phase="v3.4", dry_run=false, no_llm=false, include_debug=false)`
- `audit_section10()`
- `audit_section12()`
- `audit_test2()`
- `get_project_status()`

Example prompts:

```text
Use etf-query to query 510500近一年净值走势
Use etf-query to query 159919份额变化趋势
Use etf-query to audit Test2
Use etf-query to audit Section 10
Use etf-query to show project status
```

## Current Progress

- Default phase: `v3.4`.
- P2 status: local uncommitted implementation.
- Newly enabled intents: `nav_trend`, `scale_share_trend`.
- Covered fields: `ths_unit_nv_fund`, `ths_fund_scale_fund`, `ths_fund_shares_fund`.
- Reference answers: `result/codex-etf-query-answers-test2.md`.
- Audit command: `.venv/bin/python scripts/audit_test2.py`.

## Notes

- The server runs locally over stdio; it does not open an HTTP port.
- Runtime config is loaded from environment variables or `.env`.
- Do not commit real API keys or SSH passwords.
