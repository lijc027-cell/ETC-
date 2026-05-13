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


OUT_JSON = ROOT / "result" / "audit-v3.3-section10-compare-real.json"
OUT_MD = ROOT / "result" / "audit-v3.3-section10-compare-real.md"
OUT_HTML = ROOT / "result" / "audit-v3.3-section10-compare-real.html"


CASES = [
    {
        "question_id": "十.1",
        "question": "帮我找跟踪沪深300指数、费率最低的ETF，然后看它的基本信息和收益",
        "recognized_query_mode": "composite",
        "intent": "two_step_composite",
        "expected_outcome": "v3_3_two_step_filter_composite_single",
        "release_scope": "v3_3_required",
    },
    {
        "question_id": "十.2",
        "question": "股票型ETF里今年收益最高的5只是哪些？对比一下",
        "recognized_query_mode": "compare",
        "intent": "two_step_composite",
        "expected_outcome": "two_step_composite_filter_compare",
        "release_scope": "v3_2_required",
    },
    {
        "question_id": "十.3",
        "question": "搜索中证红利，查一下它的基本信息和持仓",
        "recognized_query_mode": "composite",
        "intent": "two_step_composite",
        "expected_outcome": "ClarificationRequired(multiple_candidates)",
        "release_scope": "v3_3_required",
    },
    {
        "question_id": "十.4",
        "question": "510300今年收益多少，持仓了哪些行业，基金经理是谁",
        "recognized_query_mode": "composite",
        "intent": "composite_single",
        "expected_outcome": "v3_3_composite_cross_collection",
        "release_scope": "v3_3_required",
    },
    {
        "question_id": "十.5",
        "question": "帮我看看510500的规模大不大，费率贵不贵，收益好不好",
        "recognized_query_mode": "single",
        "intent": "composite_single",
        "expected_outcome": "v3_3_composite_single_scale_fee_performance",
        "release_scope": "v3_3_required",
    },
    {
        "question_id": "十.6",
        "question": "上交所的ETF里，找管理费最低的3只，对比它们的今年收益",
        "recognized_query_mode": "compare",
        "intent": "two_step_composite",
        "expected_outcome": "two_step_composite_filter_compare",
        "release_scope": "v3_2_required",
    },
    {
        "question_id": "十.7",
        "question": "510300成立以来收益怎么样，分过红吗",
        "recognized_query_mode": "single",
        "intent": "composite_single",
        "expected_outcome": "composite_single_performance_dividend",
        "release_scope": "v3_2_required",
    },
    {
        "question_id": "十.8",
        "question": "对比510300和510500的费率、规模和重仓股",
        "recognized_query_mode": "composite",
        "intent": "composite_single",
        "expected_outcome": "v3_3_composite_compare_plus_report",
        "release_scope": "v3_3_required",
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
    actual_answer = format_audit_answer(str(result.get("answer") or ""), result=result)
    checks = _checks(case, result, actual_answer)
    business_checks = _business_checks(case, result, actual_answer)
    passed = all(item["pass"] for item in checks) and all(business_checks.values())
    answer_match = case["expected_answer"] in _compact(actual_answer)
    return {
        "question_id": case["question_id"],
        "question": case["question"],
        "pm_bucket": "复合意图",
        "release_scope": case["release_scope"],
        "release_bucket": "v3_3_composite",
        "expected_outcome": case["expected_outcome"],
        "actual_outcome": f"{(v3.get('routing_result') or {}).get('type', 'ExecutableQuery')}({v3.get('recognized_query_mode')}/{v3.get('intent')})",
        "expected_answer": case["expected_answer"],
        "actual_answer": actual_answer,
        "answer_match": answer_match,
        "pass_fail": "PASS" if passed else "FAIL",
        "recognized_query_mode": v3.get("recognized_query_mode"),
        "intent": v3.get("intent"),
        "ast_schema_version": (result.get("validated_ast") or {}).get("ast_schema_version"),
        "ast_generation_mode": v3.get("ast_generation_mode"),
        "failure_stage": result.get("failure_stage") or v3.get("failure_stage"),
        "failure_reason": result.get("failure_reason") or v3.get("failure_reason"),
        "query_summary": _query_summary(result),
        "llm_total_tokens": llm_total_tokens(result),
        "user_visible_answer": actual_answer,
        "checks": checks,
        "business_checks": business_checks,
        "reason": "; ".join(item["name"] for item in checks if not item["pass"]),
    }


def _checks(case: dict[str, Any], result: dict[str, Any], actual_answer: str) -> list[dict[str, Any]]:
    v3 = result.get("v3") or {}
    query_plan = result.get("query_plan")
    requires_clarification = (v3.get("routing_result") or {}).get("type") == "ClarificationRequired" or v3.get("requires_clarification") is True
    return [
        {"name": "recognized_query_mode matches", "pass": v3.get("recognized_query_mode") == case["recognized_query_mode"]},
        {"name": "intent matches", "pass": v3.get("intent") == case["intent"]},
        {"name": "ast generation mode is llm_ast_draft", "pass": v3.get("ast_generation_mode") == "llm_ast_draft"},
        {"name": "answer is non-empty", "pass": bool(actual_answer.strip())},
        {"name": "runtime footers removed", "pass": all(token not in actual_answer for token in ("查询起始时间", "查询结束时间"))},
        {
            "name": "keeps real data dates when present",
            "pass": requires_clarification or ("数据截至" in actual_answer) or ("数据起始日" in actual_answer) or ("数据结束日" in actual_answer) or ("最新" in actual_answer) or ("当前" in actual_answer),
        },
        {"name": "query structure exists", "pass": bool(query_plan) or case["intent"] == "composite_single"},
    ]


def _business_checks(case: dict[str, Any], result: dict[str, Any], actual_answer: str) -> dict[str, bool]:
    question_id = case["question_id"]
    v3 = result.get("v3") or {}
    routing_type = (v3.get("routing_result") or {}).get("type")
    return {
        "deduped_data_date": _data_as_of_count(actual_answer) <= 1,
        "no_debug_sections": "## performance" not in actual_answer and "## report_holding" not in actual_answer,
        "holding_summary_not_raw_report": _holding_summary_not_raw_report(question_id, actual_answer),
        "requires_clarification_when_multiple_candidates": (
            question_id != "十.3"
            or (
                routing_type == "ClarificationRequired"
                or v3.get("requires_clarification") is True
            )
            and all(token in actual_answer for token in ("请先确认", "多只", "基金代码"))
        ),
        "merged_compare_and_holding_table": (
            question_id != "十.8"
            or (
                _markdown_table_count(actual_answer) == 1
                and "前十大重仓股" in actual_answer
                and "最新年报口径" in actual_answer
            )
        ),
    }


def _data_as_of_count(text: str) -> int:
    return text.count("数据截至")


def _holding_summary_not_raw_report(question_id: str, text: str) -> bool:
    if question_id == "十.3":
        return "请先确认" in text
    if question_id not in {"十.4"}:
        return True
    blocked = ("报告数据如下", "| 排名 |", "前N大行业名称", "前N大概念名称")
    return "持仓方面" in text and not any(token in text for token in blocked)


def _markdown_table_count(text: str) -> int:
    lines = text.splitlines()
    count = 0
    index = 0
    while index < len(lines):
        if _is_table_start(lines, index):
            count += 1
            index += 1
            while index < len(lines) and lines[index].strip().startswith("|"):
                index += 1
            continue
        index += 1
    return count


def _query_summary(result: dict[str, Any]) -> str:
    query_plan = result.get("query_plan")
    if query_plan:
        return json.dumps(query_plan, ensure_ascii=False, sort_keys=True)
    plan_steps = result.get("plan_steps") or result.get("composite_steps") or result.get("debug_steps")
    if plan_steps:
        return json.dumps(plan_steps, ensure_ascii=False, sort_keys=True)
    return ""


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in records if item["pass_fail"] == "PASS")
    failed = sum(1 for item in records if item["pass_fail"] == "FAIL")
    matches = sum(1 for item in records if item["answer_match"])
    token_values = [item.get("llm_total_tokens") for item in records if isinstance(item.get("llm_total_tokens"), int)]
    return {
        "total_cases": len(records),
        "scoped_cases": len(records),
        "passed": passed,
        "failed": failed,
        "expected_answer_match_total": matches,
        "expected_answer_mismatch_total": len(records) - matches,
        "release_pass": failed == 0,
        "llm_total_tokens": sum(token_values) if token_values else None,
    }


def _load_expected_answers() -> dict[str, str]:
    path = ROOT / "result" / "codex-etf-query-answers.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    expected: dict[str, str] = {}
    current_id: str | None = None
    current: list[str] = []
    in_section10 = False
    for line in lines:
        if line.startswith("## 十、"):
            in_section10 = True
            continue
        if in_section10 and line.startswith("## 十一、"):
            break
        if not in_section10:
            continue
        if line.startswith("### 十."):
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
        raise RuntimeError(f"missing Section 10 expected answers in {path}: {missing}")
    return expected


def _compact(text: str) -> str:
    return "".join(str(text).split())


def _markdown(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# v3.3 Section 10 Expected Compare",
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
        f"- llm_total_tokens: `{summary['llm_total_tokens'] if summary['llm_total_tokens'] is not None else '未记录'}`",
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
                f"- recognized_query_mode: `{record['recognized_query_mode']}`",
                f"- intent: `{record['intent']}`",
                f"- business_checks: `{json.dumps(record['business_checks'], ensure_ascii=False)}`",
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
<title>v3.3 Section 10 Expected Compare</title>
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
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ border-top: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }}
  th {{ background: rgba(0,0,0,0.035); }}
  @media (max-width: 900px) {{ .cols {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>v3.3 Section 10 Expected Compare</h1>
      <div class="sub">{html.escape(str(OUT_JSON))} · {summary['passed']} pass · {summary['failed']} fail · expected match {summary['expected_answer_match_total']}/{summary['total_cases']} · LLM 总 token 数：{html.escape(str(summary['llm_total_tokens'] if summary['llm_total_tokens'] is not None else '未记录'))}</div>
    </div>
    <div class="grid">
      <div class="stat"><div class="k">Total Cases</div><div class="v">{summary['total_cases']}</div></div>
      <div class="stat"><div class="k">Passed</div><div class="v">{summary['passed']}</div></div>
      <div class="stat"><div class="k">Failed</div><div class="v">{summary['failed']}</div></div>
      <div class="stat"><div class="k">Expected Match</div><div class="v">{summary['expected_answer_match_total']}/{summary['total_cases']}</div></div>
      <div class="stat"><div class="k">LLM Tokens</div><div class="v">{html.escape(str(summary['llm_total_tokens'] if summary['llm_total_tokens'] is not None else '未记录'))}</div></div>
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
        f"actual_outcome={record['actual_outcome']} · "
        f"business_checks={json.dumps(record['business_checks'], ensure_ascii=False)}"
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
          {_render_markdownish(record['expected_answer'])}
        </div>
        <div class="panel">
          <h3>Actual</h3>
          {_render_markdownish(record['actual_answer'])}
        </div>
      </div>
    </section>
"""


def _render_markdownish(text: str) -> str:
    blocks = []
    lines = str(text).splitlines()
    index = 0
    while index < len(lines):
        if _is_table_start(lines, index):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            blocks.append(_render_table(table_lines))
            continue
        paragraph = []
        while index < len(lines) and not _is_table_start(lines, index):
            paragraph.append(lines[index])
            index += 1
        content = "\n".join(paragraph).strip()
        if content:
            blocks.append(f"<pre>{html.escape(content)}</pre>")
    return "\n".join(blocks) if blocks else "<pre></pre>"


def _is_table_start(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and lines[index].strip().startswith("|")
        and set(lines[index + 1].replace("|", "").strip()) <= {"-", " ", ":"}
    )


def _render_table(lines: list[str]) -> str:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) < 2:
        return f"<pre>{html.escape(chr(10).join(lines))}</pre>"
    header = rows[0]
    body = rows[2:]
    head_html = "".join(f"<th>{html.escape(cell)}</th>" for cell in header)
    body_html = "\n".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in body
    )
    return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"


if __name__ == "__main__":
    raise SystemExit(main())
