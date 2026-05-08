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
from etf_agent.config import load_config
from etf_agent.remote import execute_remote_query

OUT_JSON = ROOT / "answer" / "audit-v3.1-results.json"
OUT_MD = ROOT / "answer" / "audit-v3.1-results.md"

AUDIT_CASES: dict[str, dict[str, Any]] = {
    "510300是什么": {
        "route": ("single", "basic_info"),
        "reference": {"filter": {"fundcode": "510300"}, "projection": ["fundcode", "ths_fund_extended_inner_short_name_fund"], "limit": 1},
        "top_match": False,
        "must_contain": ["沪深300ETF"],
    },
    "工银沪深300ETF的费率和基金经理是什么": {
        "route": ("single", "fee_and_manager"),
        "reference": {"filter": {"fundcode": "510350"}, "projection": ["fundcode", "ths_manage_fee_rate_fund"], "limit": 1},
        "top_match": False,
        "must_contain": ["管理费率"],
    },
    "510300今年的收益率是多少": {
        "route": ("single", "performance"),
        "reference": {"filter": {"fundcode": "510300"}, "projection": ["fundcode", "ths_yeild_ytd_fund"], "limit": 1},
        "top_match": False,
        "must_contain": ["今年以来收益率"],
    },
    "近1年收益率超过20%的ETF": {
        "route": ("filter", "filter"),
        "filter": {"ths_yeild_1y_fund": {"$gt": 20}},
        "reference": {
            "filter": {"ths_yeild_1y_fund": {"$gt": 20}},
            "projection": ["fundcode", "ths_yeild_1y_fund", "ths_fund_scale_fund"],
            "sort": [["ths_fund_scale_fund", -1], ["fundcode", 1]],
            "limit": 10,
        },
        "top_match": True,
        "must_contain": ["近1年收益率"],
    },
    "找规模大于10亿的ETF": {
        "route": ("filter", "filter"),
        "filter": {"ths_fund_scale_fund": {"$gt": 1000000000}},
        "reference": {
            "filter": {"ths_fund_scale_fund": {"$gt": 1000000000}},
            "projection": ["fundcode", "ths_fund_scale_fund"],
            "sort": [["ths_fund_scale_fund", -1], ["fundcode", 1]],
            "limit": 10,
        },
        "top_match": True,
    },
    "哪些ETF管理费率最低": {
        "route": ("filter", "filter"),
        "sort": [["ths_manage_fee_rate_fund", 1], ["ths_fund_scale_fund", -1], ["fundcode", 1]],
        "reference": {
            "filter": {},
            "projection": ["fundcode", "ths_manage_fee_rate_fund", "ths_fund_scale_fund"],
            "sort": [["ths_manage_fee_rate_fund", 1], ["ths_fund_scale_fund", -1], ["fundcode", 1]],
            "limit": 10,
        },
        "top_match": True,
    },
    "我想找跟踪科创50的ETF": {
        "route": ("filter", "filter"),
        "filter": {"ths_name_of_tracking_index_fund": "上证科创板50成份指数"},
        "reference": {
            "filter": {"ths_name_of_tracking_index_fund": "上证科创板50成份指数"},
            "projection": ["fundcode", "ths_name_of_tracking_index_fund", "ths_fund_scale_fund"],
            "sort": [["ths_fund_scale_fund", -1], ["fundcode", 1]],
            "limit": 10,
        },
        "top_match": True,
        "must_contain": ["科创50"],
    },
    "帮我找沪深300相关的ETF": {
        "route": ("search", "search"),
        "reference": {
            "filter": {"__search_text__": {"$contains": "沪深300"}},
            "projection": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_name_of_tracking_index_fund", "ths_fund_scale_fund"],
            "sort": [["ths_fund_scale_fund", -1], ["fundcode", 1]],
            "limit": 20,
        },
        "review": "search 子串匹配可能有合理差异",
    },
    "对比510300、510500和159919": {
        "route": ("compare", "compare"),
        "filter": {"fundcode": {"$in": ["510300", "510500", "159919"]}},
        "reference": {
            "filter": {"fundcode": {"$in": ["510300", "510500", "159919"]}},
            "projection": ["fundcode", "ths_fund_extended_inner_short_name_fund", "ths_fund_scale_fund"],
            "limit": 10,
        },
        "top_match": False,
    },
    "对比510300和000000": {
        "route": ("compare", "compare"),
        "reference": {"filter": {"fundcode": {"$in": ["510300", "000000"]}}, "projection": ["fundcode"], "limit": 10},
        "top_match": False,
        "must_contain": ["缺失代码：000000"],
    },
    "股票型ETF里今年收益最高的5只是哪些？对比一下": {
        "route": ("composite", "filter_to_compare"),
        "reference": {
            "filter": {"ths_fund_invest_type_fund": "股票型"},
            "projection": ["fundcode", "ths_fund_invest_type_fund", "ths_yeild_ytd_fund"],
            "sort": [["ths_yeild_ytd_fund", -1], ["ths_fund_scale_fund", -1], ["fundcode", 1]],
            "limit": 5,
        },
        "top_match": False,
        "must_contain": ["今年以来收益率"],
    },
    "帮我查510300的实时行情": {
        "route": ("deny", None),
        "reference": None,
        "must_contain": ["超出当前 ETF 数据查询能力范围"],
    },
}


def main() -> int:
    config = load_config(ROOT)
    rows = []
    for question, expected in AUDIT_CASES.items():
        model = semantic_query_v3(question, root=ROOT, no_llm=True)
        reference = _run_reference(expected.get("reference"), config)
        rows.append(compare_audit_case(question=question, expected=expected, model=model, reference=reference))

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(_markdown(rows), encoding="utf-8")
    print(OUT_JSON)
    print(OUT_MD)
    return 1 if any(row["status"] == "FAIL" for row in rows) else 0


def compare_audit_case(question: str, expected: dict[str, Any], model: dict[str, Any], reference: dict[str, Any] | None) -> dict[str, Any]:
    model_route = [model["v3"].get("recognized_query_mode"), model["v3"].get("intent")]
    expected_route = list(expected.get("route", []))
    model_plan = _first_plan(model.get("query_plan") or {})
    model_data = _first_result_data(model.get("result"))
    reference_data = [] if reference is None else _rows(reference.get("data"))

    status = "PASS"
    reason = ""
    if expected_route and model_route != expected_route:
        status, reason = "FAIL", f"route mismatch: expected {expected_route}, got {model_route}"
    elif expected.get("filter") is not None and model_plan.get("filter") != expected["filter"]:
        status, reason = "FAIL", "filter mismatch"
    elif expected.get("sort") is not None and model_plan.get("sort") != expected["sort"]:
        status, reason = "FAIL", "sort mismatch"
    elif reference is not None and bool(model_data) != bool(reference_data):
        status = "FAIL"
        reason = "model returned empty but reference query found matching ETF" if reference_data else "model returned data but reference query is empty"
    elif expected.get("top_match") and _fundcodes(model_data)[: len(_fundcodes(reference_data))] != _fundcodes(reference_data):
        status, reason = "FAIL", "top fundcode mismatch"
    else:
        for text in expected.get("must_contain", []):
            if text not in str(model.get("answer", "")):
                status, reason = "FAIL", f"answer missing: {text}"
                break

    if status == "PASS" and expected.get("review"):
        status, reason = "REVIEW", expected["review"]

    return {
        "question": question,
        "expected_route": expected_route,
        "model_route": model_route,
        "model_filter": model_plan.get("filter"),
        "model_sort": model_plan.get("sort"),
        "reference_filter": None if expected.get("reference") is None else expected["reference"].get("filter"),
        "model_count": len(model_data),
        "reference_count": len(reference_data),
        "model_top_fundcodes": _fundcodes(model_data),
        "reference_top_fundcodes": _fundcodes(reference_data),
        "status": status,
        "reason": reason,
    }


def _run_reference(spec: dict[str, Any] | None, config) -> dict[str, Any] | None:
    if spec is None:
        return None
    plan = {
        "collection": "tb_ths_etf_base",
        "filter": spec.get("filter", {}),
        "projection": spec.get("projection", ["fundcode"]),
        "sort": spec.get("sort", []),
        "limit": spec.get("limit", 10),
    }
    return execute_remote_query(plan, config)


def _first_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if "steps" in plan:
        return plan["steps"][0]
    return plan


def _first_result_data(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict) and "steps" in result:
        return _rows(result["steps"][0].get("data"))
    if isinstance(result, dict):
        return _rows(result.get("data"))
    return []


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _fundcodes(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row.get("fundcode")) for row in rows if row.get("fundcode")]


def _markdown(rows: list[dict[str, Any]]) -> str:
    pass_count = sum(1 for row in rows if row["status"] == "PASS")
    fail_count = sum(1 for row in rows if row["status"] == "FAIL")
    review_count = sum(1 for row in rows if row["status"] == "REVIEW")
    lines = [
        "# v3.1 Reference Audit",
        "",
        f"测试时间：{date.today().isoformat()}",
        "",
        f"- PASS：{pass_count}",
        f"- FAIL：{fail_count}",
        f"- REVIEW：{review_count}",
        "",
        "| 问句 | 模型路由 | 模型数量 | 参考数量 | 判定 | 原因 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        route = " / ".join(str(item) for item in row["model_route"])
        lines.append(f"| {row['question']} | `{route}` | {row['model_count']} | {row['reference_count']} | {row['status']} | {row['reason']} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
