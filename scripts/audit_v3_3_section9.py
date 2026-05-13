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
from scripts.audit_answer_format import format_audit_answer


OUT_JSON = ROOT / "result" / "audit-v3.3-section9-compare-real.json"
OUT_MD = ROOT / "result" / "audit-v3.3-section9-compare-real.md"
OUT_HTML = ROOT / "result" / "audit-v3.3-section9-compare-real.html"


CASES = [
    ("九.1", "对比510300、510500和159919", "covered_compare"),
    ("九.2", "512880和510300哪个更好", "DeniedQuery(investment_advice)"),
    ("九.3", "对比所有跟踪沪深300的前5只ETF，看收益和费率", "two_step_composite_filter_compare"),
    ("九.4", "510300和510500比一下规模和费率", "covered_compare"),
    ("九.5", "对比一下510300和159919的收益率", "covered_compare"),
]


def main() -> int:
    expected_answers = _load_expected_answers()
    records = []
    for question_id, question, expected_outcome in CASES:
        print(f"{question_id} {question}", flush=True)
        result = semantic_query_v3(question, root=ROOT, phase="v3.3")
        records.append(_record(question_id, question, expected_outcome, expected_answers[question_id], result))

    summary = _summary(records)
    payload = {"summary": summary, "records": records}
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(_markdown(summary, records), encoding="utf-8")
    OUT_HTML.write_text(_html(summary, records), encoding="utf-8")
    print(OUT_JSON)
    print(OUT_MD)
    print(OUT_HTML)
    return 0 if summary["failed"] == 0 else 1


def _record(question_id: str, question: str, expected_outcome: str, expected_answer: str, result: dict[str, Any]) -> dict[str, Any]:
    v3 = result.get("v3") or {}
    actual_answer = format_audit_answer(str(result.get("answer") or ""), result=result)
    checks = _checks(question_id, result, actual_answer)
    passed = all(item["pass"] for item in checks)
    answer_match = expected_answer in _compact(actual_answer)
    return {
        "question_id": question_id,
        "question": question,
        "pm_bucket": "多只对比",
        "release_scope": "v3_2_required",
        "release_bucket": "v3_2_compatibility_baseline",
        "expected_outcome": expected_outcome,
        "actual_outcome": _actual_outcome(v3),
        "expected_answer": expected_answer,
        "actual_answer": actual_answer,
        "answer_match": answer_match,
        "pass_fail": "PASS" if passed else "FAIL",
        "recognized_query_mode": v3.get("recognized_query_mode"),
        "intent": v3.get("intent"),
        "ast_schema_version": _ast_schema_version(result),
        "ast_generation_mode": v3.get("ast_generation_mode"),
        "failure_stage": result.get("failure_stage") or v3.get("failure_stage"),
        "failure_reason": result.get("failure_reason") or v3.get("failure_reason") or (v3.get("routing_result") or {}).get("reason"),
        "remote_status": _remote_status(result),
        "formatter_status": "PASS" if actual_answer else "FAIL",
        "query_summary": json.dumps(_query_summary(result), ensure_ascii=False, sort_keys=True),
        "user_visible_answer": actual_answer,
        "checks": checks,
        "reason": "; ".join(item["name"] for item in checks if not item["pass"]),
    }


def _checks(question_id: str, result: dict[str, Any], actual_answer: str) -> list[dict[str, Any]]:
    if question_id == "九.2":
        return [
            {"name": "route is denied", "pass": ((result.get("v3") or {}).get("routing_result") or {}).get("type") == "DeniedQuery"},
            {"name": "answer exists", "pass": bool(actual_answer)},
        ]
    checks = [
        {"name": "answer exists", "pass": bool(actual_answer)},
        {"name": "answer contains compare table or guidance", "pass": "| 指标 |" in actual_answer or question_id == "九.2"},
    ]
    if question_id == "九.3":
        checks.extend(_case_9_3_checks(result, actual_answer))
    return checks


def _case_9_3_checks(result: dict[str, Any], actual_answer: str) -> list[dict[str, Any]]:
    plans = (result.get("query_plan") or {}).get("steps") or []
    filter_plan = plans[0] if len(plans) > 0 and isinstance(plans[0], dict) else {}
    compare_plan = plans[1] if len(plans) > 1 and isinstance(plans[1], dict) else {}
    compare_codes = ((compare_plan.get("filter") or {}).get("fundcode") or {}).get("$in") or []
    return [
        {"name": "route is compare/two_step_composite", "pass": (result.get("v3") or {}).get("recognized_query_mode") == "compare" and (result.get("v3") or {}).get("intent") == "two_step_composite"},
        {"name": "step1 sorts by one year yield", "pass": (filter_plan.get("sort") or [])[:1] == [["ths_yeild_1y_fund", -1]]},
        {"name": "step1 projection includes one year yield", "pass": "ths_yeild_1y_fund" in (filter_plan.get("projection") or [])},
        {"name": "compare candidates exclude empty yield fund", "pass": "159238" not in compare_codes and "159238" not in actual_answer},
        {"name": "compare candidates are one-year-yield ordered", "pass": compare_codes == ["515360", "159393", "561930", "159300", "515130"]},
        {"name": "answer explains candidate selection", "pass": actual_answer.startswith("这里按近1年收益率从高到低选取前5只跟踪沪深300相关 ETF，再对比它们的收益和费率。")},
        {"name": "answer states sort evidence", "pass": "排序依据：近1年收益率。" in actual_answer},
        {"name": "answer keeps one year yield row", "pass": "| 近1年收益率 | 35.58% | 35.17% | 34.86% | 33.80% | 33.48% |" in actual_answer},
        {"name": "answer has no empty one-year yield", "pass": "暂无数据" not in actual_answer},
    ]


def _actual_outcome(v3: dict[str, Any]) -> str:
    route_type = (v3.get("routing_result") or {}).get("type", "ExecutableQuery")
    if route_type != "ExecutableQuery":
        reason = (v3.get("routing_result") or {}).get("reason") or v3.get("failure_reason")
        return f"{route_type}({reason})"
    return f"{route_type}({v3.get('recognized_query_mode')}/{v3.get('intent')})"


def _remote_status(result: dict[str, Any]) -> str:
    if ((result.get("v3") or {}).get("routing_result") or {}).get("type") == "DeniedQuery":
        return "SKIPPED"
    remote = result.get("result") or {}
    return "PASS" if remote.get("success") else "FAIL"


def _ast_schema_version(result: dict[str, Any]) -> str | None:
    ast = result.get("validated_ast")
    if isinstance(ast, dict) and isinstance(ast.get("steps"), list):
        versions = []
        for step in ast["steps"]:
            if isinstance(step, dict) and step.get("ast_schema_version"):
                versions.append(step["ast_schema_version"])
        return ",".join(versions)
    if isinstance(ast, dict):
        return ast.get("ast_schema_version")
    return None


def _query_summary(result: dict[str, Any]) -> dict[str, Any]:
    plan = result.get("query_plan")
    if isinstance(plan, dict) and isinstance(plan.get("steps"), list):
        return {"steps": [_plan_summary(item) for item in plan["steps"] if isinstance(item, dict)]}
    if isinstance(plan, dict):
        return _plan_summary(plan)
    return {}


def _plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "collection": plan.get("collection"),
        "filter": plan.get("filter"),
        "limit": plan.get("limit"),
        "projection": plan.get("projection"),
        "sort": plan.get("sort"),
        "answer_fields": [item.get("field") for item in plan.get("answer_fields") or []],
    }


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
    in_section9 = False
    for line in lines:
        if line.startswith("## 九、"):
            in_section9 = True
            continue
        if in_section9 and line.startswith("## 十、"):
            break
        if not in_section9:
            continue
        if line.startswith("### 九."):
            if current_id is not None:
                expected[current_id] = "\n".join(current).strip()
            current_id = line.split()[1]
            current = []
            continue
        if current_id is not None:
            current.append(line)
    if current_id is not None:
        expected[current_id] = "\n".join(current).strip()
    missing = [case[0] for case in CASES if case[0] not in expected or not expected[case[0]]]
    if missing:
        raise RuntimeError(f"missing Section 9 expected answers in {path}: {missing}")
    return expected


def _markdown(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# v3.3 Section 9 Expected Compare",
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
<title>v3.3 Section 9 Expected Compare</title>
<style>
  :root {{ --bg: #f4f0e6; --paper: #fffaf0; --ink: #2f2418; --muted: #6e5c45; --line: #d7c8b2; --pass: #2f6f4e; --fail: #9f2f2f; --match: #2f6f4e; --mismatch: #8a5a1f; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: Georgia, serif; }}
  .wrap {{ max-width: 1240px; margin: 0 auto; padding: 28px 22px 48px; }}
  .hero {{ padding: 10px 0 18px; border-bottom: 1px solid var(--line); margin-bottom: 18px; }}
  h1 {{ margin: 0 0 8px; font-size: 32px; }}
  .sub {{ color: var(--muted); font-size: 14px; }}
  .metrics {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 18px 0 24px; }}
  .metric {{ background: var(--paper); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; box-shadow: 0 2px 0 rgba(60, 45, 25, .04); }}
  .metric-label {{ color: var(--muted); font-size: 13px; margin-bottom: 6px; }}
  .metric-value {{ font-size: 28px; line-height: 1.1; }}
  .cases {{ display: grid; gap: 14px; }}
  .case {{ background: var(--paper); border: 1px solid var(--line); border-radius: 12px; padding: 16px; box-shadow: 0 2px 0 rgba(60, 45, 25, .04); }}
  .case-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }}
  .case-id {{ font-size: 13px; color: var(--muted); margin-bottom: 4px; }}
  .case-question {{ font-size: 20px; line-height: 1.3; }}
  .badges {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
  .pill {{ padding: 6px 10px; border-radius: 999px; font-size: 12px; border: 1px solid transparent; white-space: nowrap; }}
  .pill.pass, .pill.match {{ background: #e8f3ec; color: var(--match); border-color: #c7e0d0; }}
  .pill.fail {{ background: #f9e5e2; color: var(--fail); border-color: #ecc2bb; }}
  .pill.mismatch {{ background: #fbedd8; color: var(--mismatch); border-color: #ebd0a9; }}
  .meta {{ margin-top: 10px; color: var(--muted); font-size: 13px; }}
  .compare {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 14px; }}
  .compare-col {{ border: 1px solid var(--line); border-radius: 10px; background: #fffdf7; padding: 12px 14px; overflow: auto; }}
  .compare-col .label {{ color: var(--muted); font-size: 13px; margin-bottom: 8px; }}
  .body {{ line-height: 1.7; font-size: 15px; }}
  .body p {{ margin: 0 0 10px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 14px; }}
  th, td {{ border: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }}
  th {{ background: #f6ecd8; }}
  .detail-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 18px; margin-top: 14px; font-size: 13px; }}
  .detail-grid span {{ display: block; color: var(--muted); margin-bottom: 4px; }}
  .detail-grid strong {{ font-weight: 400; }}
  @media (max-width: 900px) {{ .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .case-head, .compare {{ grid-template-columns: 1fr; display: grid; }} .badges {{ justify-content: flex-start; }} .detail-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>v3.3 Section 9 Expected Compare</h1>
      <div class="sub">{OUT_JSON.name} · {summary['passed']} pass · {summary['failed']} fail · expected match {summary['expected_answer_match_total']}/{summary['total_cases']} · release pass {str(summary['release_pass']).lower()}</div>
    </div>
    <div class="metrics">
      <div class="metric"><div class="metric-label">Cases</div><div class="metric-value">{summary['total_cases']}</div></div>
      <div class="metric"><div class="metric-label">Pass</div><div class="metric-value">{summary['passed']}</div></div>
      <div class="metric"><div class="metric-label">Fail</div><div class="metric-value">{summary['failed']}</div></div>
      <div class="metric"><div class="metric-label">Expected match</div><div class="metric-value">{summary['expected_answer_match_total']}</div></div>
      <div class="metric"><div class="metric-label">Release pass</div><div class="metric-value">{str(summary['release_pass']).lower()}</div></div>
    </div>
    <div class="cases">
{cards}
    </div>
  </div>
</body>
</html>
"""


def _case_html(record: dict[str, Any]) -> str:
    status_class = "pass" if record["pass_fail"] == "PASS" else "fail"
    match_class = "match" if record["answer_match"] else "mismatch"
    match_text = "MATCH" if record["answer_match"] else "MISMATCH"
    return f"""    <section class="case {status_class}">
      <div class="case-head">
        <div>
          <div class="case-id">{html.escape(record['question_id'])}</div>
          <div class="case-question">{html.escape(record['question'])}</div>
        </div>
        <div class="badges">
          <div class="pill {status_class}">{record['pass_fail']}</div>
          <div class="pill {match_class}">{match_text}</div>
        </div>
      </div>
      <div class="meta">{html.escape(record['release_scope'])} · {html.escape(record['expected_outcome'])} · {html.escape(record['actual_outcome'])}</div>
      <div class="compare">
        <div class="compare-col"><div class="label">Expected</div><div class="body">{_render_markdownish(record['expected_answer'])}</div></div>
        <div class="compare-col"><div class="label">Actual</div><div class="body">{_render_markdownish(record['actual_answer'])}</div></div>
      </div>
      <div class="detail-grid">
        <div><span>Query summary</span><strong>{html.escape(record['query_summary'])}</strong></div>
        <div><span>Reason</span><strong>{html.escape(record['reason'] or '-')}</strong></div>
      </div>
    </section>"""


def _render_markdownish(text: str) -> str:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    chunks = []
    for block in blocks:
        if len(block) >= 2 and block[0].strip().startswith("|") and block[1].strip().startswith("|") and "---" in block[1]:
            chunks.append(_table_html(block))
        else:
            chunks.append("<p>" + "<br>".join(html.escape(item.strip()) for item in block) + "</p>")
    return "\n".join(chunks)


def _table_html(lines: list[str]) -> str:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) < 2:
        return ""
    head = rows[0]
    body = rows[2:]
    head_html = "".join(f"<th>{html.escape(cell)}</th>" for cell in head)
    body_html = "\n".join("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>" for row in body)
    return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"


def _compact(text: str) -> str:
    return " ".join(text.split()).replace("。 ", "。")


if __name__ == "__main__":
    raise SystemExit(main())
