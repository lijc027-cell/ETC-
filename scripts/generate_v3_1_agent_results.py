#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etf_agent import semantic_query_v3
from etf_agent.capability_registry import all_v3_1_allowed_fields

OUT_MD = ROOT / "answer" / "test3.1-agent-results.md"
OUT_JSON = ROOT / "answer" / "raw" / "test3.1-agent-results.json"

AGENT_CASES: dict[str, dict[str, Any]] = {
    "帮我找沪深300相关的ETF": {"group": "standard", "route": ("search", "search"), "must_contain": ["基金代码"]},
    "找规模大于10亿的ETF": {"group": "standard", "route": ("filter", "filter"), "must_contain": ["基金规模"]},
    "哪些ETF管理费率最低": {"group": "standard", "route": ("filter", "filter"), "must_contain": ["管理费率"]},
    "对比510300、510500和159919": {"group": "standard", "route": ("compare", "compare"), "must_contain": ["510300", "510500", "159919"]},
    "股票型ETF里今年收益最高的5只是哪些？对比一下": {"group": "standard", "route": ("composite", "filter_to_compare"), "must_contain": ["今年以来收益率"]},
    "低成本的沪深300产品都有哪些": {"group": "paraphrase", "routes": [("filter", "filter"), ("search", "search")], "must_contain": ["管理费率"]},
    "便宜一点的沪深300产品": {"group": "paraphrase", "routes": [("filter", "filter"), ("search", "search")]},
    "科创板50相关产品": {"group": "paraphrase", "routes": [("search", "search"), ("filter", "filter")], "must_contain": ["科创50"]},
    "偏债的场内基金有哪些": {"group": "paraphrase", "route": ("filter", "filter"), "must_contain": ["债"]},
    "510300 510500 159919放一起看看": {"group": "paraphrase", "route": ("compare", "compare"), "must_contain": ["510300", "510500", "159919"]},
    "512880和510300谁费用更省": {"group": "paraphrase", "route": ("compare", "compare"), "must_contain": ["管理费率"]},
    "沪深300产品里回报靠前的": {"group": "paraphrase", "route": ("filter", "filter"), "must_contain": ["收益率"]},
    "规模不小于100亿的产品": {"group": "paraphrase", "route": ("filter", "filter"), "must_contain": ["基金规模"]},
    "510300近半年和同类比怎么样": {"group": "boundary", "route": ("unsupported", None)},
    "沪深300里面哪只更值得买": {"group": "boundary", "route": ("deny", None)},
    "2024年成立的ETF有哪些": {"group": "boundary", "route": ("unsupported", None)},
}

ALLOWED_FIELDS = all_v3_1_allowed_fields()


def main() -> int:
    rows = []
    for question in AGENT_CASES:
        result = semantic_query_v3(question, root=ROOT, no_llm=False, dry_run=False)
        status, reason = evaluate_agent_result(question, result)
        rows.append({"question": question, "status": status, "reason": reason, "result": _compact_result(result)})

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(_markdown(rows), encoding="utf-8")
    print(OUT_MD)
    print(OUT_JSON)
    return 1 if any(row["status"] == "FAIL" for row in rows) else 0


def evaluate_agent_result(question: str, result: dict[str, Any]) -> tuple[str, str]:
    expected = AGENT_CASES.get(question, {})
    route = (result["v3"].get("recognized_query_mode"), result["v3"].get("intent"))
    expected_routes = expected.get("routes") or [expected.get("route")]
    if expected_routes and route not in expected_routes:
        return "FAIL", f"route mismatch: {route}"

    plan = result.get("query_plan")
    forbidden = _forbidden_fields(plan)
    if forbidden:
        return "FAIL", f"forbidden field: {forbidden[0]}"

    if route[0] not in {"deny", "unsupported", "clarify"}:
        if str(result.get("answer", "")).startswith("远端查询失败"):
            return "FAIL", "remote query failed"
        if not _has_result_data(result.get("result")):
            return "FAIL", "empty result"

    for text in expected.get("must_contain", []):
        if text not in str(result.get("answer", "")):
            return "FAIL", f"answer missing: {text}"
    return "PASS", ""


def _forbidden_fields(plan: Any) -> list[str]:
    if not isinstance(plan, dict):
        return []
    plans = plan.get("steps") if "steps" in plan else [plan]
    fields: list[str] = []
    for item in plans:
        fields.extend(str(field) for field in item.get("projection", []))
        fields.extend(str(field) for field in item.get("filter", {}).keys() if field != "__search_text__")
        fields.extend(str(field) for field, _direction in item.get("sort", []))
    return [field for field in fields if field not in ALLOWED_FIELDS]


def _has_result_data(result: Any) -> bool:
    if isinstance(result, dict) and "steps" in result:
        return all(_has_result_data(step) for step in result["steps"])
    if not isinstance(result, dict):
        return False
    data = result.get("data")
    return bool(data)


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": [result["v3"].get("recognized_query_mode"), result["v3"].get("intent")],
        "llm_ast_status": result["v3"].get("llm_ast_status"),
        "answer": result.get("answer", ""),
        "query_plan": result.get("query_plan"),
    }


def _markdown(rows: list[dict[str, Any]]) -> str:
    pass_count = sum(1 for row in rows if row["status"] == "PASS")
    fail_count = sum(1 for row in rows if row["status"] == "FAIL")
    lines = [
        "# v3.1 Agent E2E Results",
        "",
        f"测试时间：{date.today().isoformat()}",
        "",
        f"- PASS：{pass_count}",
        f"- FAIL：{fail_count}",
        f"- LLM AST generated：{sum(1 for row in rows if row['result'].get('llm_ast_status') == 'generated')}",
        f"- LLM AST fallback：{sum(1 for row in rows if row['result'].get('llm_ast_status') == 'fallback_to_deterministic')}",
        f"- LLM AST skipped：{sum(1 for row in rows if row['result'].get('llm_ast_status') == 'skipped')}",
        "",
        "| 问句 | 路由 | 判定 | 原因 |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        route = " / ".join(str(item) for item in row["result"]["route"])
        lines.append(f"| {row['question']} | `{route}` | {row['status']} | {row['reason']} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
