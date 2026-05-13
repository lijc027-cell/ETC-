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


OUT_JSON = ROOT / "result" / "audit-v3.3-section7-compare-real.json"
OUT_MD = ROOT / "result" / "audit-v3.3-section7-compare-real.md"
OUT_HTML = ROOT / "result" / "audit-v3.3-section7-compare-real.html"


CASES = [
    {
        "question_id": "七.1",
        "question": "帮我找沪深300相关的ETF",
        "scope": "generic",
        "keyword": "沪深300",
    },
    {
        "question_id": "七.2",
        "question": "搜索中证500",
        "scope": "generic",
        "keyword": "中证500",
    },
    {
        "question_id": "七.3",
        "question": "找一下创业板ETF",
        "scope": "generic",
        "keyword": "创业板",
    },
    {
        "question_id": "七.4",
        "question": "搜索MSCI中国A股",
        "scope": "generic",
        "keyword": "MSCI中国A股",
    },
    {
        "question_id": "七.5",
        "question": "有没有名字里带医药的ETF",
        "scope": "name_contains",
        "keyword": "医药",
    },
    {
        "question_id": "七.6",
        "question": "有没有ETF名字里带\"红利\"的",
        "scope": "name_contains",
        "keyword": "红利",
    },
    {
        "question_id": "七.7",
        "question": "我想找跟踪科创50的ETF",
        "scope": "tracking_index",
        "keyword": "科创50",
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
    plan = result.get("query_plan") or {}
    query_result = result.get("result") or {}
    actual_answer = format_audit_answer(str(result.get("answer") or ""), result=result)
    checks = _checks(case, result, actual_answer)
    passed = all(item["pass"] for item in checks)
    answer_match = case["expected_answer"] in _compact(actual_answer)
    return {
        "question_id": case["question_id"],
        "question": case["question"],
        "pm_bucket": "搜索ETF",
        "release_scope": "v3_2_required",
        "release_bucket": "v3_2_compatibility_baseline",
        "expected_outcome": "covered_search",
        "actual_outcome": f"{(v3.get('routing_result') or {}).get('type', 'ExecutableQuery')}({v3.get('recognized_query_mode')}/{v3.get('intent')})",
        "expected_answer": case["expected_answer"],
        "actual_answer": actual_answer,
        "answer_match": answer_match,
        "pass_fail": "PASS" if passed else "FAIL",
        "recognized_query_mode": v3.get("recognized_query_mode"),
        "intent": v3.get("intent"),
        "search_scope": plan.get("search_scope"),
        "search_keyword": plan.get("search_keyword"),
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
                "search_scope": plan.get("search_scope"),
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


def _checks(case: dict[str, Any], result: dict[str, Any], actual_answer: str) -> list[dict[str, Any]]:
    v3 = result.get("v3") or {}
    plan = result.get("query_plan") or {}
    query_result = result.get("result") or {}
    return [
        {"name": "route is search/search", "pass": v3.get("recognized_query_mode") == "search" and v3.get("intent") == "search"},
        {"name": "default limit is 10", "pass": plan.get("limit") == 10},
        {"name": "search_scope matches", "pass": plan.get("search_scope") == case["scope"]},
        {"name": "search_keyword matches", "pass": plan.get("search_keyword") == case["keyword"]},
        {"name": "result exposes total_count", "pass": isinstance(query_result.get("total_count"), int)},
        {"name": "result exposes returned_count", "pass": isinstance(query_result.get("returned_count"), int)},
        {"name": "result exposes has_more", "pass": isinstance(query_result.get("has_more"), bool)},
        {"name": "answer contains required summary", "pass": _required_summary(case, query_result) in _compact(actual_answer)},
        {"name": "answer contains markdown table", "pass": "| 基金代码 | 基金简称 | 基金规模 | 管理费率 |" in actual_answer},
        {"name": "answer uses cutoff date footer", "pass": "数据截至 2026-05-11。" in actual_answer and "数据起始日" not in actual_answer},
    ]


def _required_summary(case: dict[str, Any], query_result: dict[str, Any]) -> str:
    total = query_result.get("total_count")
    keyword = case["keyword"]
    if case["scope"] == "name_contains":
        first = f"共找到 {total} 只基金名称包含“{keyword}”的 ETF，默认按基金规模从高到低展示前 10 只。"
    elif case["scope"] == "tracking_index":
        first = f"共找到 {total} 只跟踪指数匹配或相关于“{keyword}”的 ETF，默认按基金规模从高到低展示前 10 只。"
    else:
        first = f"共找到 {total} 只名称、跟踪指数或指数代码与“{keyword}”相关的 ETF，默认按基金规模从高到低展示前 10 只。"
    if query_result.get("has_more"):
        first += "还有更多结果，可缩小条件或指定展示数量。"
    return first


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for item in records if item["pass_fail"] == "PASS")
    failed = sum(1 for item in records if item["pass_fail"] == "FAIL")
    matches = sum(1 for item in records if item["answer_match"])
    tokens = 0
    return {
        "total_cases": len(records),
        "scoped_cases": len(records),
        "passed": passed,
        "failed": failed,
        "expected_answer_match_total": matches,
        "expected_answer_mismatch_total": len(records) - matches,
        "llm_token_total": tokens,
        "release_pass": failed == 0,
    }


def _load_expected_answers() -> dict[str, str]:
    path = ROOT / "result" / "codex-etf-query-answers.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    expected: dict[str, str] = {}
    current_id: str | None = None
    current: list[str] = []
    in_section7 = False
    for line in lines:
        if line.startswith("## 七、"):
            in_section7 = True
            continue
        if in_section7 and line.startswith("## 八、"):
            break
        if not in_section7:
            continue
        if line.startswith("### 七."):
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
        raise RuntimeError(f"missing Section 7 expected answers in {path}: {missing}")
    return expected


def _markdown(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# v3.3 Section 7 Expected Compare",
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
                f"- search_scope: `{record['search_scope']}`",
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
<title>v3.3 Section 7 Expected Compare</title>
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
      <h1>v3.3 Section 7 Expected Compare</h1>
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
        <div><span>search_scope</span><strong>{html.escape(str(record['search_scope']))}</strong></div>
        <div><span>total / returned / has_more</span><strong>{record['total_count']} / {record['returned_count']} / {str(record['has_more']).lower()}</strong></div>
        <div><span>Reason</span><strong>{html.escape(record['reason'] or '—')}</strong></div>
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


def _is_table_start(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and lines[index].strip().startswith("|")
        and lines[index + 1].strip().startswith("|")
        and "---" in lines[index + 1]
    )


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
