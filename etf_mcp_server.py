from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Any

from etf_agent.api import API_VERSION, SUPPORTED_PHASES, run_query

ROOT = Path(__file__).resolve().parent
DEFAULT_PHASE = "v3.4"


def query_etf_tool(
    question: str,
    phase: str = DEFAULT_PHASE,
    dry_run: bool = False,
    no_llm: bool = False,
    include_debug: bool = False,
) -> dict[str, Any]:
    if not isinstance(question, str) or not question.strip():
        return {"ok": False, "error": "question is required"}
    try:
        return run_query(
            {
                "question": question.strip(),
                "phase": phase,
                "dry_run": dry_run,
                "no_llm": no_llm,
                "include_debug": include_debug,
            },
            root=ROOT,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def audit_section10_tool() -> dict[str, Any]:
    return _run_audit("scripts/audit_v3_3_section10.py")


def audit_section12_tool() -> dict[str, Any]:
    return _run_audit("scripts/audit_v3_3_section12.py")


def get_project_status_tool() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "etf-query-mcp",
        "api_version": API_VERSION,
        "default_phase": DEFAULT_PHASE,
        "supported_phases": sorted(SUPPORTED_PHASES),
        "current_progress": {
            "p2_status": "local_uncommitted",
            "enabled_intents": ["nav_trend", "scale_share_trend"],
        },
        "tools": ["query_etf", "audit_section10", "audit_section12", "get_project_status"],
        "notes": [
            "Queries use the local ETF Text2SQL v3 runtime.",
            "Runtime credentials are loaded from environment variables or .env.",
            "The MCP server does not expose write operations.",
        ],
    }


def _run_audit(script: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [sys.executable, script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except Exception as exc:
        return {"ok": False, "script": script, "error": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "script": script,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _build_mcp_server():
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("etf-query")
    mcp.tool(name="query_etf")(query_etf_tool)
    mcp.tool(name="audit_section10")(audit_section10_tool)
    mcp.tool(name="audit_section12")(audit_section12_tool)
    mcp.tool(name="get_project_status")(get_project_status_tool)
    return mcp


def main() -> None:
    _build_mcp_server().run()


if __name__ == "__main__":
    main()
