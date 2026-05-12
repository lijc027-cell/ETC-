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


OUT_JSON = ROOT / "result" / "audit-v3.3-section8-compare-real.json"
OUT_MD = ROOT / "result" / "audit-v3.3-section8-compare-real.md"
OUT_HTML = ROOT / "result" / "audit-v3.3-section8-compare-real.html"


CASES = [
    ("八.1", "帮我筛选所有股票型ETF", "covered_filter"),
    ("八.2", "找上交所规模前10的ETF", "covered_filter"),
    ("八.3", "哪些ETF管理费率最低", "covered_filter_lowest_fee_bucket"),
    ("八.4", "筛选跟踪沪深300指数的ETF，按收益率排序", "covered_filter"),
    ("八.5", "找规模大于10亿的ETF", "covered_filter"),
    ("八.6", "筛选深交所的债券型ETF", "covered_filter"),
    ("八.7", "今年以来收益排名前10的ETF", "covered_filter"),
    ("八.8", "管理费率低于0.2%的ETF有哪些", "covered_filter_fee_threshold"),
    ("八.9", "2024年成立的ETF有哪些", "v3_2_filter_date_between"),
    ("八.10", "近1年收益率超过20%的ETF", "covered_filter"),
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
    plan = result.get("query_plan") or {}
    query_result = result.get("result") or {}
    actual_answer = _strip_llm_token(str(result.get("answer") or ""))
    checks = _checks(question_id, result, actual_answer)
    passed = all(item["pass"] for item in checks)
    answer_match = expected_answer in _compact(actual_answer)
    return {
        "question_id": question_id,
        "question": question,
        "pm_bucket": "条件筛选",
        "release_scope": "v3_2_required",
        "release_bucket": "v3_2_compatibility_baseline",
        "expected_outcome": expected_outcome,
        "actual_outcome": f"{(v3.get('routing_result') or {}).get('type', 'ExecutableQuery')}({v3.get('recognized_query_mode')}/{v3.get('intent')})",
        "expected_answer": expected_answer,
        "actual_answer": actual_answer,
        "answer_match": answer_match,
        "pass_fail": "PASS" if passed else "FAIL",
        "recognized_query_mode": v3.get("recognized_query_mode"),
        "intent": v3.get("intent"),
        "total_count": query_result.get("total_count"),
        "returned_count": query_result.get("returned_count"),
        "has_more": query_result.get("has_more"),
        "ast_schema_version": result.get("validated_ast", {}).get("ast_schema_version"),
        "ast_generation_mode": v3.get("ast_generation_mode"),
        "failure_stage": result.get("failure_stage") or v3.get("failure_stage"),
        "failure_reason": result.get("failure_reason") or v3.get("failure_reason"),
        "remote_status": "PASS" if query_result.get("success") else "FAIL",
        "formatter_status": "PASS" if actual_answer else "FAIL",
        "query_summary": json.dumps(
            {
                "collection": plan.get("collection"),
                "filter": plan.get("filter"),
                "limit": plan.get("limit"),
                "projection": plan.get("projection"),
                "sort": plan.get("sort"),
                "answer_fields": [item.get("field") for item in plan.get("answer_fields") or []],
                "total_count": query_result.get("total_count"),
                "returned_count": query_result.get("returned_count"),
                "has_more": query_result.get("has_more"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        "user_visible_answer": actual_answer,
        "checks": checks,
        "reason": "; ".join(item["name"] for item in checks if not item["pass"]),
    }


def _checks(question_id: str, result: dict[str, Any], actual_answer: str) -> list[dict[str, Any]]:
    v3 = result.get("v3") or {}
    plan = result.get("query_plan") or {}
    query_result = result.get("result") or {}
    checks = [
        {"name": "route is filter/filter", "pass": v3.get("recognized_query_mode") == "filter" and v3.get("intent") == "filter"},
        {"name": "result exposes total_count", "pass": isinstance(query_result.get("total_count"), int)},
        {"name": "result exposes returned_count", "pass": isinstance(query_result.get("returned_count"), int)},
        {"name": "result exposes has_more", "pass": isinstance(query_result.get("has_more"), bool)},
        {"name": "answer contains markdown table", "pass": "| 基金代码 |" in actual_answer},
    ]
    if question_id == "八.3":
        checks.extend(_lowest_fee_checks(plan, actual_answer))
    if question_id == "八.8":
        checks.extend(_fee_threshold_checks(plan, actual_answer))
    if question_id == "八.9":
        checks.extend(_date_filter_checks(plan, actual_answer))
    return checks


def _lowest_fee_checks(plan: dict[str, Any], actual_answer: str) -> list[dict[str, Any]]:
    return [
        {"name": "lowest fee bucket filter is eq 0.15", "pass": (plan.get("filter") or {}).get("ths_manage_fee_rate_fund") == 0.15},
        {"name": "fee sort uses fee scale fundcode", "pass": plan.get("sort") == [["ths_manage_fee_rate_fund", 1], ["ths_fund_scale_fund", -1], ["fundcode", 1]]},
        {"name": "projection includes scale", "pass": "ths_fund_scale_fund" in (plan.get("projection") or [])},
        {"name": "answer_fields includes scale", "pass": _answer_has(plan, "ths_fund_scale_fund")},
        {"name": "answer explains lowest fee bucket", "pass": actual_answer.startswith("当前库里最低管理费率为 0.15%，共有 ")},
        {"name": "answer shows scale column", "pass": "| 基金代码 | 基金简称 | 管理费率 | 基金规模 |" in actual_answer},
        {"name": "top rows are scale ordered", "pass": all(code in actual_answer for code in ("510300", "510310", "511360", "510330", "159919"))},
    ]


def _fee_threshold_checks(plan: dict[str, Any], actual_answer: str) -> list[dict[str, Any]]:
    return [
        {"name": "fee threshold filter stays lt 0.2", "pass": (plan.get("filter") or {}).get("ths_manage_fee_rate_fund") == {"$lt": 0.2}},
        {"name": "fee sort uses fee scale fundcode", "pass": plan.get("sort") == [["ths_manage_fee_rate_fund", 1], ["ths_fund_scale_fund", -1], ["fundcode", 1]]},
        {"name": "projection includes scale", "pass": "ths_fund_scale_fund" in (plan.get("projection") or [])},
        {"name": "answer_fields includes scale", "pass": _answer_has(plan, "ths_fund_scale_fund")},
        {"name": "answer shows scale column", "pass": "| 基金代码 | 基金简称 | 管理费率 | 基金规模 |" in actual_answer},
        {"name": "threshold result is scale ordered", "pass": all(code in actual_answer for code in ("510300", "510310", "511360", "510330", "159919"))},
    ]


def _date_filter_checks(plan: dict[str, Any], actual_answer: str) -> list[dict[str, Any]]:
    return [
        {"name": "date sort is establishment asc", "pass": plan.get("sort") == [["ths_fund_establishment_date_fund", 1], ["fundcode", 1]]},
        {"name": "projection includes establishment date", "pass": "ths_fund_establishment_date_fund" in (plan.get("projection") or [])},
        {"name": "answer_fields includes establishment date", "pass": _answer_has(plan, "ths_fund_establishment_date_fund")},
        {"name": "answer explains date sort", "pass": actual_answer.startswith("2024 年成立的 ETF 共 ")},
        {"name": "answer shows establishment date column", "pass": "成立日期" in actual_answer},
        {"name": "earliest 2024 rows appear", "pass": all(code in actual_answer for code in ("159567", "159530", "159562"))},
    ]


def _answer_has(plan: dict[str, Any], field: str) -> bool:
    return any(item.get("field") == field for item in plan.get("answer_fields") or [])


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
    in_section8 = False
    for line in lines:
        if line.startswith("## 八、"):
            in_section8 = True
            continue
        if in_section8 and line.startswith("## 九、"):
            break
        if not in_section8:
            continue
        if line.startswith("### 八."):
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
        raise RuntimeError(f"missing Section 8 expected answers in {path}: {missing}")
    return expected


def _markdown(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# v3.3 Section 8 Expected Compare",
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
                f"- total_count: `{record['total_count']}`",
                f"- returned_count: `{record['returned_count']}`",
                f"- has_more: `{str(record['has_more']).lower()}`",
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
<title>v3.3 Section 8 Expected Compare</title>
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
  .detail-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px 18px; margin-top: 14px; font-size: 13px; }}
  .detail-grid span {{ display: block; color: var(--muted); margin-bottom: 4px; }}
  .detail-grid strong {{ font-weight: 400; }}
  @media (max-width: 900px) {{ .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .case-head, .compare {{ grid-template-columns: 1fr; display: grid; }} .badges {{ justify-content: flex-start; }} .detail-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>v3.3 Section 8 Expected Compare</h1>
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
        <div><span>total / returned / has_more</span><strong>{record['total_count']} / {record['returned_count']} / {str(record['has_more']).lower()}</strong></div>
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

    chunks: list[str] = []
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


def _strip_llm_token(answer: str) -> str:
    marker = "\n\nLLM token："
    if marker in answer:
        return answer.split(marker, 1)[0]
    return answer


def _compact(text: str) -> str:
    return " ".join(text.split()).replace("。 ", "。")


if __name__ == "__main__":
    raise SystemExit(main())
