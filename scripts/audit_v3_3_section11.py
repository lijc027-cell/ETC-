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


OUT_JSON = ROOT / "result" / "audit-v3.3-section11-compare-real.json"
OUT_MD = ROOT / "result" / "audit-v3.3-section11-compare-real.md"
OUT_HTML = ROOT / "result" / "audit-v3.3-section11-compare-real.html"


CASES = [
    {"question_id": "十一.1", "question": "510300最近成交额多少"},
    {"question_id": "十一.2", "question": "510300的净现金流是正还是负"},
    {"question_id": "十一.3", "question": "510300的融资余额是多少"},
    {"question_id": "十一.4", "question": "510300的融券卖出量多少"},
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
    checks = _checks(result, actual_answer)
    passed = all(item["pass"] for item in checks)
    return {
        "question_id": case["question_id"],
        "question": case["question"],
        "pm_bucket": "交易类指标（新增字段）",
        "release_scope": "v3_3_required",
        "release_bucket": "v3_3_trading_metric",
        "expected_outcome": "v3_3_trading_metric_snapshot",
        "actual_outcome": f"{(v3.get('routing_result') or {}).get('type', 'ExecutableQuery')}({v3.get('recognized_query_mode')}/{v3.get('intent')})",
        "expected_answer": case["expected_answer"],
        "actual_answer": actual_answer,
        "answer_match": case["expected_answer"] in _compact(actual_answer),
        "pass_fail": "PASS" if passed else "FAIL",
        "recognized_query_mode": v3.get("recognized_query_mode"),
        "intent": v3.get("intent"),
        "ast_schema_version": result.get("validated_ast", {}).get("ast_schema_version"),
        "ast_generation_mode": v3.get("ast_generation_mode"),
        "failure_stage": result.get("failure_stage") or v3.get("failure_stage"),
        "failure_reason": result.get("failure_reason") or v3.get("failure_reason"),
        "query_summary": json.dumps(result.get("query_plan") or {}, ensure_ascii=False, sort_keys=True),
        "llm_total_tokens": llm_total_tokens(result),
        "user_visible_answer": actual_answer,
        "checks": checks,
        "reason": "; ".join(item["name"] for item in checks if not item["pass"]),
    }


def _checks(result: dict[str, Any], actual_answer: str) -> list[dict[str, Any]]:
    v3 = result.get("v3") or {}
    return [
        {"name": "recognized_query_mode is single", "pass": v3.get("recognized_query_mode") == "single"},
        {"name": "intent is trading_metric", "pass": v3.get("intent") == "trading_metric"},
        {"name": "ast generation mode is llm_ast_draft", "pass": v3.get("ast_generation_mode") == "llm_ast_draft"},
        {"name": "answer is non-empty", "pass": bool(actual_answer.strip())},
        {"name": "runtime footers removed", "pass": all(token not in actual_answer for token in ("查询起始时间", "查询结束时间"))},
        {
            "name": "answer has real metric date or no-data wording",
            "pass": ("2026-05-11" in actual_answer) or ("暂无可用" in actual_answer) or ("暂无数据" in actual_answer),
        },
    ]


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
    in_section11 = False
    for line in lines:
        if line.startswith("## 十一、"):
            in_section11 = True
            continue
        if in_section11 and line.startswith("## 十二、"):
            break
        if not in_section11:
            continue
        if line.startswith("### 十一."):
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
        raise RuntimeError(f"missing Section 11 expected answers in {path}: {missing}")
    return expected


def _compact(text: str) -> str:
    return "".join(str(text).split())


def _markdown(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# v3.3 Section 11 Expected Compare",
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
<title>v3.3 Section 11 Expected Compare</title>
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
      <h1>v3.3 Section 11 Expected Compare</h1>
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
