#!/usr/bin/env python3
from __future__ import annotations

import html
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etf_agent import semantic_query_v3
from scripts.audit_answer_format import format_audit_answer, llm_total_tokens


OUT_JSON = ROOT / "result" / "audit-v3.3-section12-compare-real.json"
OUT_MD = ROOT / "result" / "audit-v3.3-section12-compare-real.md"
OUT_HTML = ROOT / "result" / "audit-v3.3-section12-compare-real.html"


CASES = [
    {
        "question_id": "十二.1",
        "question": "000001有这只ETF吗",
        "routing_type": "ExecutableQuery",
        "recognized_query_mode": "single",
        "intent": "basic_info",
        "expected_outcome": "executable_empty_result_not_found",
        "release_scope": "v3_2_required",
    },
    {
        "question_id": "十二.2",
        "question": "帮我查510300的实时行情",
        "routing_type": "DeniedQuery",
        "recognized_query_mode": None,
        "intent": "realtime_not_supported",
        "expected_outcome": "DeniedQuery(realtime_not_supported)",
        "release_scope": "boundary",
    },
    {
        "question_id": "十二.3",
        "question": "abcdef是什么基金",
        "routing_type": "ClarificationRequired",
        "recognized_query_mode": None,
        "intent": "invalid_fundcode",
        "expected_outcome": "ClarificationRequired(invalid_fundcode)",
        "release_scope": "boundary",
    },
    {
        "question_id": "十二.4",
        "question": "510300的持仓行业是什么（季报年报都没有）",
        "routing_type": "ExecutableQuery",
        "recognized_query_mode": "report",
        "intent": "report_industry",
        "expected_outcome": "ExecutableQuery(report_industry)+premise_correction",
        "release_scope": "v3_3_required",
    },
    {
        "question_id": "十二.5",
        "question": "对比510300和000000",
        "routing_type": "ExecutableQuery",
        "recognized_query_mode": "compare",
        "intent": "compare",
        "expected_outcome": "compare_partial_found",
        "release_scope": "v3_2_required",
    },
    {
        "question_id": "十二.6",
        "question": "给我推荐一只ETF",
        "routing_type": "DeniedQuery",
        "recognized_query_mode": "deny",
        "intent": "investment_advice",
        "expected_outcome": "DeniedQuery(investment_advice)",
        "release_scope": "boundary",
    },
    {
        "question_id": "十二.7",
        "question": "今天A股大盘怎么样",
        "routing_type": "DeniedQuery",
        "recognized_query_mode": "deny",
        "intent": "unsupported_domain",
        "expected_outcome": "DeniedQuery(unsupported_domain)",
        "release_scope": "boundary",
    },
    {
        "question_id": "十二.8",
        "question": "510300能买吗",
        "routing_type": "DeniedQuery",
        "recognized_query_mode": "deny",
        "intent": "investment_advice",
        "expected_outcome": "DeniedQuery(investment_advice)",
        "release_scope": "boundary",
    },
]


def main() -> int:
    expected_answers = _load_expected_answers()
    records = []
    for case in CASES:
        print(f"{case['question_id']} {case['question']}", flush=True)
        result = semantic_query_v3(case["question"], root=ROOT, phase="v3.3")
        records.append(_record({**case, "expected_answer": expected_answers[case["question_id"]]}, result))

    summary = _summary(records)
    payload = {"summary": summary, "records": records}
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(_markdown(summary, records), encoding="utf-8")
    OUT_HTML.write_text(_html(summary, records), encoding="utf-8")
    print(OUT_JSON)
    print(OUT_MD)
    print(OUT_HTML)
    return 0 if summary["failed"] == 0 else 1


def _record(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    v3 = result.get("v3") or {}
    routing = v3.get("routing_result") or {}
    validated_ast = result.get("validated_ast") or {}
    actual_answer = format_audit_answer(str(result.get("answer") or ""), result=result)
    checks = _checks(case, result, actual_answer)
    passed = all(item["pass"] for item in checks)
    actual_type = routing.get("type") or _fallback_type(v3, result)
    actual_mode = v3.get("recognized_query_mode")
    actual_intent = (routing.get("reason") if actual_type != "ExecutableQuery" else v3.get("intent")) or result.get("failure_reason")
    return {
        "question_id": case["question_id"],
        "question": case["question"],
        "pm_bucket": "边界/异常场景",
        "release_scope": case["release_scope"],
        "release_bucket": "v3_3_boundary",
        "expected_outcome": case["expected_outcome"],
        "actual_outcome": f"{actual_type}({actual_mode}/{actual_intent})",
        "expected_answer": case["expected_answer"],
        "actual_answer": actual_answer,
        "answer_match": case["expected_answer"] in _compact(actual_answer),
        "pass_fail": "PASS" if passed else "FAIL",
        "routing_type": actual_type,
        "recognized_query_mode": actual_mode,
        "intent": actual_intent,
        "ast_schema_version": validated_ast.get("ast_schema_version"),
        "ast_generation_mode": v3.get("ast_generation_mode"),
        "failure_stage": result.get("failure_stage") or v3.get("failure_stage"),
        "failure_reason": result.get("failure_reason") or v3.get("failure_reason"),
        "query_summary": json.dumps(result.get("query_plan") or {}, ensure_ascii=False, sort_keys=True),
        "llm_total_tokens": llm_total_tokens(result),
        "user_visible_answer": actual_answer,
        "checks": checks,
        "business_checks": _business_checks(case, result, actual_answer),
        "reason": "; ".join(item["name"] for item in checks if not item["pass"]),
    }


def _checks(case: dict[str, Any], result: dict[str, Any], actual_answer: str) -> list[dict[str, Any]]:
    v3 = result.get("v3") or {}
    routing = v3.get("routing_result") or {}
    actual_type = routing.get("type") or _fallback_type(v3, result)
    actual_mode = v3.get("recognized_query_mode")
    actual_intent = (routing.get("reason") if actual_type != "ExecutableQuery" else v3.get("intent")) or result.get("failure_reason")
    return [
        {"name": "routing type matches", "pass": actual_type == case["routing_type"]},
        {"name": "recognized_query_mode matches", "pass": _mode_matches(case["recognized_query_mode"], actual_mode, actual_type)},
        {"name": "intent/failure reason matches", "pass": actual_intent == case["intent"]},
        {"name": "answer is non-empty", "pass": bool(actual_answer.strip())},
        {"name": "runtime footers removed", "pass": all(token not in actual_answer for token in ("查询起始时间", "查询结束时间"))},
        {"name": "business checks pass", "pass": all(_business_checks(case, result, actual_answer).values())},
    ]


def _business_checks(case: dict[str, Any], result: dict[str, Any], actual_answer: str) -> dict[str, bool]:
    qid = case["question_id"]
    normalized = actual_answer.replace(" ", "")
    failure_stage = (result.get("failure_stage") or "").replace("router", "routing")
    return {
        "12_2_realtime_and_snapshot": qid != "十二.2" or ("不提供实时行情" in actual_answer and "最新净值" in actual_answer),
        "12_3_invalid_code_specific_copy": qid != "十二.3" or ("不是有效" in actual_answer or "无效代码" in actual_answer),
        "12_4_premise_correction_with_industry": qid != "十二.4" or ("一季报" in actual_answer and "食品饮料" in actual_answer and "银行" in actual_answer and "暂无数据" not in actual_answer),
        "12_5_missing_code_first": qid != "十二.5" or actual_answer.splitlines()[0].startswith("510300 能查到，000000 未查到"),
        "12_6_12_8_investment_advice_copy": qid not in {"十二.6", "十二.8"} or "投资建议" in actual_answer,
        "12_7_unsupported_domain_copy": qid != "十二.7" or ("ETF 数据库" in actual_answer or "大盘" in actual_answer),
        "failure_stage_normalized": qid not in {"十二.2", "十二.3", "十二.6", "十二.7", "十二.8"} or failure_stage in {"", "routing"},
        "unsupported_domain_reason_normalized": qid != "十二.7" or (((result.get("v3") or {}).get("routing_result") or {}).get("reason") == "unsupported_domain"),
    }


def _mode_matches(expected_mode: str | None, actual_mode: str | None, actual_type: str) -> bool:
    if expected_mode is None:
        if actual_type == "DeniedQuery":
            return actual_mode in {None, "deny"}
        if actual_type == "ClarificationRequired":
            return actual_mode in {None, "clarify"}
        return True
    return actual_mode == expected_mode


def _fallback_type(v3: dict[str, Any], result: dict[str, Any]) -> str:
    mode = v3.get("recognized_query_mode")
    if mode == "deny":
        return "DeniedQuery"
    if result.get("failure_stage") in {"router", "routing"} and result.get("failure_reason") == "invalid_fundcode":
        return "ClarificationRequired"
    if result.get("failure_stage") in {"router", "routing"} and result.get("failure_reason"):
        return "UnsupportedQuery"
    return "ExecutableQuery"


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in records if item["pass_fail"] == "PASS")
    failed = sum(1 for item in records if item["pass_fail"] == "FAIL")
    matches = sum(1 for item in records if item["answer_match"])
    return {
        "total_cases": len(records),
        "scoped_cases": len(records),
        "passed": passed,
        "failed": failed,
        "expected_answer_match_total": matches,
        "expected_answer_mismatch_total": len(records) - matches,
        "release_pass": failed == 0,
    }


def _load_expected_answers() -> dict[str, str]:
    path = ROOT / "result" / "codex-etf-query-answers.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    expected: dict[str, str] = {}
    current_id: str | None = None
    current: list[str] = []
    in_section12 = False
    for line in lines:
        if line.startswith("## 十二、"):
            in_section12 = True
            continue
        if not in_section12:
            continue
        if line.startswith("### 十二."):
            if current_id is not None:
                expected[current_id] = "\n".join(current).strip()
            current_id = line.split()[1]
            current = []
            continue
        if current_id is not None:
            current.append(line)
    if current_id is not None:
        expected[current_id] = "\n".join(current).strip()
    missing = [case["question_id"] for case in CASES if case["question_id"] not in expected or not expected[case["question_id"]]]
    if missing:
        raise RuntimeError(f"missing Section 12 expected answers in {path}: {missing}")
    return expected


def _compact(text: str) -> str:
    return "".join(str(text).split())


def _markdown(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# v3.3 Section 12 Expected Compare",
        "",
        "## Summary",
        "",
        f"- total_cases: `{summary['total_cases']}`",
        f"- scoped_cases: `{summary['scoped_cases']}`",
        f"- passed: `{summary['passed']}`",
        f"- failed: `{summary['failed']}`",
        f"- expected_answer_match_total: `{summary['expected_answer_match_total']}`",
        f"- expected_answer_mismatch_total: `{summary['expected_answer_mismatch_total']}`",
        f"- release_pass: `{str(summary['release_pass']).lower()}`",
        "",
        "## Cases",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"### {record['question_id']} {record['question']}",
                "",
                f"- pass/fail: `{record['pass_fail']}`",
                f"- answer_match: `{str(record['answer_match']).lower()}`",
                f"- expected_outcome: `{record['expected_outcome']}`",
                f"- actual_outcome: `{record['actual_outcome']}`",
                f"- routing_type: `{record['routing_type']}`",
                f"- recognized_query_mode: `{record['recognized_query_mode']}`",
                f"- intent: `{record['intent']}`",
                "",
                "**Expected**",
                "",
                record["expected_answer"],
                "",
                "**Actual**",
                "",
                record["actual_answer"],
                "",
            ]
        )
    return "\n".join(lines)


def _html(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    cards = "\n".join(_case_html(record) for record in records)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>v3.3 Section 12 Expected Compare</title>
<style>
  :root {{ --bg: #f4f0e6; --paper: #fffaf0; --ink: #2f2418; --muted: #6e5c45; --line: #d7c8b2; --pass: #2f6f4e; --fail: #9f2f2f; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: Georgia, serif; }}
  .wrap {{ max-width: 1240px; margin: 0 auto; padding: 28px 22px 48px; }}
  .hero {{ padding: 10px 0 18px; border-bottom: 1px solid var(--line); margin-bottom: 18px; }}
  h1 {{ margin: 0 0 8px; font-size: 32px; }}
  .sub {{ color: var(--muted); font-size: 14px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 18px 0 24px; }}
  .stat {{ background: var(--paper); border: 1px solid var(--line); padding: 14px 16px; border-radius: 6px; }}
  .stat .k {{ color: var(--muted); font-size: 12px; }}
  .stat .v {{ margin-top: 6px; font-size: 28px; }}
  .cases {{ display: grid; gap: 16px; }}
  .card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 6px; padding: 18px; }}
  .head {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 10px; }}
  .qid {{ font-size: 22px; }}
  .badge {{ font-size: 12px; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--line); }}
  .pass {{ color: var(--pass); }}
  .fail {{ color: var(--fail); }}
  .meta {{ color: var(--muted); font-size: 13px; margin-bottom: 14px; }}
  .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  .panel {{ border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }}
  .panel h3 {{ margin: 0; padding: 10px 12px; font-size: 14px; background: rgba(0,0,0,0.03); }}
  .panel pre {{ margin: 0; padding: 12px; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; line-height: 1.5; }}
  @media (max-width: 900px) {{ .cols {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>v3.3 Section 12 Expected Compare</h1>
      <div class="sub">{html.escape(str(OUT_JSON))} · {summary['passed']} pass · {summary['failed']} fail · expected match {summary['expected_answer_match_total']}/{summary['total_cases']}</div>
    </div>
    <div class="grid">
      <div class="stat"><div class="k">Total Cases</div><div class="v">{summary['total_cases']}</div></div>
      <div class="stat"><div class="k">Passed</div><div class="v">{summary['passed']}</div></div>
      <div class="stat"><div class="k">Failed</div><div class="v">{summary['failed']}</div></div>
      <div class="stat"><div class="k">Expected Match</div><div class="v">{summary['expected_answer_match_total']}/{summary['total_cases']}</div></div>
    </div>
    <div class="cases">{cards}</div>
  </div>
</body>
</html>
"""


def _case_html(record: dict[str, Any]) -> str:
    badge_class = "pass" if record["pass_fail"] == "PASS" else "fail"
    meta = (
        f"answer_match={str(record['answer_match']).lower()} · "
        f"expected_outcome={record['expected_outcome']} · "
        f"actual_outcome={record['actual_outcome']}"
    )
    return f"""
    <section class="card">
      <div class="head">
        <div class="qid">{html.escape(record['question_id'])} {html.escape(record['question'])}</div>
        <div class="badge {badge_class}">{html.escape(record['pass_fail'])}</div>
      </div>
      <div class="meta">{html.escape(meta)}</div>
      <div class="cols">
        <div class="panel">
          <h3>Expected</h3>
          <pre>{html.escape(record['expected_answer'])}</pre>
        </div>
        <div class="panel">
          <h3>Actual</h3>
          <pre>{html.escape(record['actual_answer'])}</pre>
        </div>
      </div>
    </section>
"""


if __name__ == "__main__":
    raise SystemExit(main())
