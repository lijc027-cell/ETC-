#!/usr/bin/env python3
"""Audit script for test_questions2.md against v3.4 spec.

Runs each question through semantic_query_v3 and produces an HTML report.
Expected answers come from result/codex-etf-query-answers-test2.md.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etf_agent import semantic_query_v3
from scripts.audit_answer_format import format_audit_answer, llm_total_tokens

DEFAULT_OUT_HTML = ROOT / "result" / "audit-test2-results.html"
DEFAULT_OUT_JSON = ROOT / "result" / "audit-test2-results.json"

# Questions that are in v3.3/v3.4 scope and should be executed.
# Questions NOT in this set are out-of-scope and should be skipped.
IN_SCOPE_SECTIONS = {
    "一", "二", "三", "四", "六", "七", "八", "九",
    "十", "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九",
}

# Expected status for each question (based on spec analysis).
# "executable" = should return a real answer
# "data_not_available" = field exists in spec but no data in DB
# "unsupported" = spec explicitly rejects this query type
EXPECTED_STATUS: dict[str, str] = {
    "一.1": "executable",
    "一.2": "executable",
    "二.1": "executable",
    "二.2": "executable",
    "二.3": "executable",
    "三.1": "executable",
    "三.2": "executable",
    "三.3": "executable",
    "四.1": "executable",
    "四.2": "executable",
    "四.3": "executable",
    "六.1": "executable",
    "六.2": "executable",
    "七.1": "executable",
    "七.2": "executable",
    "七.3": "executable",
    "八.1": "data_not_available",
    "八.2": "executable",
    "八.3": "executable",
    "九.1": "executable",
    "九.2": "executable",
    "十.1": "data_not_available",
    "十.2": "data_not_available",
    "十.3": "data_not_available",
    "十一.1": "data_not_available",
    "十一.2": "data_not_available",
    "十一.3": "data_not_available",
    "十二.1": "executable",
    "十二.2": "executable",
    "十二.3": "executable",
    "十三.1": "data_not_available",
    "十三.2": "data_not_available",
    "十四.1": "data_not_available",
    "十四.2": "data_not_available",
    "十五.1": "unsupported",
    "十五.2": "unsupported",
    "十六.1": "executable",
    "十六.2": "executable",
    "十七.1": "data_not_available",
    "十七.2": "data_not_available",
    "十八.1": "executable",
    "十八.2": "executable",
    "十九.1": "unsupported",
    "十九.2": "unsupported",
}

# Phase to use for each question.
QUESTION_PHASE: dict[str, str] = {
    "六.1": "v3.4",
    "六.2": "v3.4",
    "九.1": "v3.4",
    "九.2": "v3.4",
    "十八.1": "v3.4",
    "十八.2": "v3.4",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit test_questions2.md against v3.4 spec.")
    parser.add_argument("--out-html", type=Path, default=DEFAULT_OUT_HTML)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--dry-run", action="store_true", help="Skip remote queries")
    args = parser.parse_args(argv)

    questions = load_questions(ROOT / "test_questions2.md")
    expected_answers = load_expected_answers(ROOT / "result" / "codex-etf-query-answers-test2.md")

    records = []
    for index, q in enumerate(questions, start=1):
        qid = q["id"]
        question = q["question"]
        phase = QUESTION_PHASE.get(qid, "v3.3")
        print(f"[{index}/{len(questions)}] {qid} {question} (phase={phase})", flush=True)
        try:
            result = semantic_query_v3(question, root=ROOT, phase=phase)
        except Exception as exc:
            result = _runtime_exception_result(question, exc)
        records.append(build_record(qid, question, result, expected_answers))

    summary = summarize(records)
    args.out_html.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "records": records}
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out_html.write_text(render_html(records, summary, expected_answers), encoding="utf-8")
    print(args.out_json)
    print(args.out_html)
    print(f"passed={summary['passed']} failed={summary['failed']} total={summary['total']}")
    return 0 if summary["failed"] == 0 else 1


def load_questions(path: Path) -> list[dict[str, str]]:
    questions = []
    current_section = ""
    section_counter: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("## "):
            current_section = line[3:].strip().split("、", 1)[0]
            section_counter[current_section] = 0
        elif line.startswith("- ") and current_section:
            section_counter[current_section] = section_counter.get(current_section, 0) + 1
            count = section_counter[current_section]
            qid = f"{current_section}.{count}"
            questions.append({"id": qid, "question": line[2:].strip(), "section": current_section})
    return questions


def load_expected_answers(path: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    current_id: str | None = None
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            if current_id:
                expected[current_id] = "\n".join(current).strip()
            parts = line[4:].strip().split(" ", 1)
            current_id = parts[0] if parts else None
            current = []
            continue
        if line.startswith("## "):
            continue
        if current_id:
            current.append(line)
    if current_id:
        expected[current_id] = "\n".join(current).strip()
    return expected


def build_record(
    qid: str,
    question: str,
    result: dict[str, Any],
    expected_answers: dict[str, str],
) -> dict[str, Any]:
    v3 = result.get("v3") or {}
    expected_status = EXPECTED_STATUS.get(qid, "unknown")
    actual_answer = format_audit_answer(str(result.get("answer") or ""), result=result)
    tokens = llm_total_tokens(result)

    routing_result = v3.get("routing_result") or {}
    if isinstance(routing_result, dict):
        actual_type = routing_result.get("type") or _legacy_type(v3)
    else:
        actual_type = _legacy_type(v3)

    failure_reason = v3.get("failure_reason") or result.get("failure_reason")
    failure_stage = v3.get("failure_stage") or result.get("failure_stage")
    intent = v3.get("intent")
    mode = v3.get("recognized_query_mode")
    phase = v3.get("phase", "v3.3")

    actual_status = _derive_actual_status(actual_type, failure_reason, actual_answer)
    structural_failures = _series_assertion_failures(result, actual_answer)
    pass_fail = _evaluate_pass_fail(qid, expected_status, actual_status, actual_answer, failure_reason)
    if pass_fail == "PASS" and structural_failures:
        pass_fail = "FAIL"

    return {
        "id": qid,
        "question": question,
        "expected_status": expected_status,
        "actual_status": actual_status,
        "pass/fail": pass_fail,
        "phase": phase,
        "intent": intent,
        "mode": mode,
        "failure_stage": failure_stage,
        "failure_reason": failure_reason,
        "actual_answer": actual_answer,
        "expected_answer": expected_answers.get(qid, ""),
        "structural_failures": structural_failures,
        "llm_total_tokens": tokens,
    }


def _series_assertion_failures(result: dict[str, Any], answer: str) -> list[str]:
    v3 = result.get("v3") or {}
    if v3.get("intent") not in {"nav_trend", "scale_share_trend"}:
        return []
    failures: list[str] = []
    data = (result.get("result") or {}).get("data")
    if not isinstance(data, dict):
        return ["result.data must be a dict"]
    series = data.get("series")
    if not isinstance(series, list) or not series:
        return ["result.data.series must be a non-empty list"]
    valid_periods = {"1m", "3m", "6m", "1y", "3y", "5y", "std", "business_days"}
    for item in series:
        if not isinstance(item, dict):
            failures.append("series item must be a dict")
            continue
        field = item.get("field")
        points = item.get("points")
        period = item.get("period")
        if period not in valid_periods:
            failures.append(f"{field}.period is invalid: {period}")
        if period == "business_days":
            count = item.get("count")
            if not isinstance(count, int) or not 1 <= count <= 250:
                failures.append(f"{field}.count is invalid: {count}")
        if not isinstance(points, list) or not points:
            failures.append(f"{field}.points must be non-empty")
            continue
        for point in points:
            if not isinstance(point, dict) or "btime" not in point or "value" not in point:
                failures.append(f"{field}.points must contain btime/value")
                break
        if field == "ths_fund_scale_fund":
            if item.get("format") != "yuan_to_100m":
                failures.append("ths_fund_scale_fund.format must be yuan_to_100m")
            _assert_unscaled_points(field, points, failures)
        if field == "ths_fund_shares_fund":
            if item.get("format") != "shares_to_100m":
                failures.append("ths_fund_shares_fund.format must be shares_to_100m")
            _assert_unscaled_points(field, points, failures)
    if len(re.findall(r"\d{4}-\d{2}-\d{2}[：:]", answer)) > 12:
        failures.append("answer expands too many dated points")
    if re.search(r"[+-]\d+(?:\.\d+)?%", answer):
        failures.append("answer contains derived percentage")
    for word in ("上涨", "下跌", "涨幅", "跌幅", "变动率"):
        if word in answer:
            failures.append(f"answer contains derived metric word: {word}")
    return failures


def _assert_unscaled_points(field: str, points: list[Any], failures: list[str]) -> None:
    numeric_values = [
        point.get("value")
        for point in points
        if isinstance(point, dict) and isinstance(point.get("value"), (int, float)) and point.get("value") not in (0, None)
    ]
    if numeric_values and max(abs(value) for value in numeric_values) < 1_000_000:
        failures.append(f"{field}.points values look divided by 1e8")


def _derive_actual_status(actual_type: str | None, failure_reason: str | None, answer: str) -> str:
    if actual_type in {"DeniedQuery", "UnsupportedQuery"}:
        return "unsupported"
    if failure_reason == "data_not_available":
        return "data_not_available"
    if actual_type == "ClarificationRequired":
        return "clarify"
    if "暂无" in answer or "没有返回" in answer or "无数据" in answer:
        return "data_not_available"
    if actual_type == "ExecutableQuery" or (answer and "查询失败" not in answer):
        return "executable"
    return "unknown"


def _evaluate_pass_fail(
    qid: str,
    expected_status: str,
    actual_status: str,
    actual_answer: str,
    failure_reason: str | None,
) -> str:
    if expected_status == "unknown":
        return "SKIP"
    if expected_status == "executable":
        if actual_status == "executable" and actual_answer and "查询失败" not in actual_answer:
            return "PASS"
        return "FAIL"
    if expected_status == "data_not_available":
        if actual_status in {"data_not_available", "unsupported"}:
            return "PASS"
        return "FAIL"
    if expected_status == "unsupported":
        if actual_status in {"unsupported", "data_not_available"}:
            return "PASS"
        return "FAIL"
    return "SKIP"


def _legacy_type(v3: dict[str, Any]) -> str | None:
    mode = v3.get("recognized_query_mode")
    if mode == "deny":
        return "DeniedQuery"
    if mode == "clarify":
        return "ClarificationRequired"
    if mode == "unsupported":
        return "UnsupportedQuery"
    if mode:
        return "ExecutableQuery"
    return None


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    passed = sum(1 for r in records if r["pass/fail"] == "PASS")
    failed = sum(1 for r in records if r["pass/fail"] == "FAIL")
    skipped = sum(1 for r in records if r["pass/fail"] == "SKIP")
    tokens = sum(r["llm_total_tokens"] for r in records if isinstance(r.get("llm_total_tokens"), int))
    by_section: dict[str, dict[str, int]] = {}
    for r in records:
        section = r["id"].rsplit(".", 1)[0]
        stats = by_section.setdefault(section, {"total": 0, "passed": 0, "failed": 0})
        stats["total"] += 1
        if r["pass/fail"] == "PASS":
            stats["passed"] += 1
        elif r["pass/fail"] == "FAIL":
            stats["failed"] += 1
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "llm_total_tokens": tokens,
        "by_section": by_section,
        "overall_pass": failed == 0,
    }


def render_html(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    expected_answers: dict[str, str],
) -> str:
    cards = "\n".join(_case_html(r) for r in records)
    section_rows = "\n".join(
        f"<tr><td>{html.escape(sec)}</td><td>{stats['total']}</td>"
        f"<td class='pass'>{stats['passed']}</td><td class='fail'>{stats['failed']}</td></tr>"
        for sec, stats in summary["by_section"].items()
    )
    overall_class = "pass" if summary["overall_pass"] else "fail"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>v3.4 Test2 Audit</title>
<style>
  :root {{ --bg: #f4f0e6; --paper: #fffaf0; --ink: #2f2418; --muted: #6e5c45; --line: #d7c8b2; --pass: #2f6f4e; --fail: #9f2f2f; --skip: #70655b; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: Georgia, serif; }}
  .wrap {{ max-width: 1320px; margin: 0 auto; padding: 28px 22px 48px; }}
  .hero {{ padding: 10px 0 18px; border-bottom: 1px solid var(--line); margin-bottom: 18px; }}
  h1 {{ margin: 0 0 8px; font-size: 32px; }}
  .sub {{ color: var(--muted); font-size: 14px; line-height: 1.5; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0 24px; }}
  .stat {{ background: var(--paper); border: 1px solid var(--line); padding: 14px 16px; border-radius: 6px; }}
  .stat .k {{ color: var(--muted); font-size: 12px; }}
  .stat .v {{ margin-top: 6px; font-size: 26px; }}
  .section-table {{ background: var(--paper); border: 1px solid var(--line); border-radius: 6px; margin-bottom: 24px; overflow: hidden; }}
  .section-table table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .section-table th, .section-table td {{ border-top: 1px solid var(--line); padding: 8px 12px; text-align: left; }}
  .section-table th {{ background: rgba(0,0,0,0.035); }}
  .cases {{ display: grid; gap: 16px; }}
  .card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 6px; padding: 18px; }}
  .head {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 10px; }}
  .qid {{ font-size: 20px; line-height: 1.35; }}
  .badge {{ font-size: 12px; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--line); white-space: nowrap; }}
  .pass {{ color: var(--pass); }}
  .fail {{ color: var(--fail); }}
  .skip {{ color: var(--skip); }}
  .meta {{ color: var(--muted); font-size: 13px; margin-bottom: 14px; line-height: 1.5; }}
  .cols {{ display: grid; grid-template-columns: 0.85fr 1.15fr; gap: 14px; }}
  .panel {{ border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }}
  .panel h3 {{ margin: 0; padding: 10px 12px; font-size: 14px; background: rgba(0,0,0,0.03); }}
  .panel pre {{ margin: 0; padding: 12px; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; line-height: 1.5; }}
  @media (max-width: 900px) {{ .cols {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>v3.4 Test2 Audit</h1>
      <div class="sub">test_date: {date.today().isoformat()} · {summary['passed']} pass · {summary['failed']} fail · {summary['skipped']} skip · LLM 总 token 数：{summary['llm_total_tokens']}</div>
    </div>
    <div class="grid">
      <div class="stat"><div class="k">Total</div><div class="v">{summary['total']}</div></div>
      <div class="stat"><div class="k">Passed</div><div class="v {overall_class}">{summary['passed']}</div></div>
      <div class="stat"><div class="k">Failed</div><div class="v {'fail' if summary['failed'] > 0 else ''}">{summary['failed']}</div></div>
      <div class="stat"><div class="k">Skipped</div><div class="v">{summary['skipped']}</div></div>
      <div class="stat"><div class="k">LLM Tokens</div><div class="v">{summary['llm_total_tokens']}</div></div>
    </div>
    <div class="section-table">
      <table>
        <thead><tr><th>Section</th><th>Total</th><th>Passed</th><th>Failed</th></tr></thead>
        <tbody>{section_rows}</tbody>
      </table>
    </div>
    <div class="cases">{cards}</div>
  </div>
</body>
</html>
"""


def _case_html(record: dict[str, Any]) -> str:
    status = str(record["pass/fail"]).lower()
    badge_class = "pass" if status == "pass" else "fail" if status == "fail" else "skip"
    meta_parts = [
        f"expected={record['expected_status']}",
        f"actual={record['actual_status']}",
        f"phase={record['phase']}",
        f"intent={record['intent'] or '-'}",
        f"mode={record['mode'] or '-'}",
        f"tokens={record['llm_total_tokens'] if record['llm_total_tokens'] is not None else '未记录'}",
    ]
    if record.get("failure_reason"):
        meta_parts.append(f"failure_reason={record['failure_reason']}")
    meta = " · ".join(meta_parts)
    expected_text = record.get("expected_answer") or "（无 expected 答案）"
    actual_text = record.get("actual_answer") or "（无答案）"
    return f"""
    <section class="card">
      <div class="head">
        <div class="qid">{html.escape(record['id'])} {html.escape(record['question'])}</div>
        <div class="badge {badge_class}">{html.escape(record['pass/fail'])}</div>
      </div>
      <div class="meta">{html.escape(meta)}</div>
      <div class="cols">
        <div class="panel">
          <h3>Expected</h3>
          <pre>{html.escape(expected_text)}</pre>
        </div>
        <div class="panel">
          <h3>Answer</h3>
          <pre>{html.escape(actual_text)}</pre>
        </div>
      </div>
    </section>
"""


def _runtime_exception_result(question: str, exc: Exception) -> dict[str, Any]:
    return {
        "question": question,
        "answer": f"运行时异常：{exc}",
        "v3": {
            "recognized_query_mode": None,
            "intent": None,
            "failure_stage": "runtime_exception",
            "failure_reason": str(exc),
            "phase": "v3.3",
        },
    }


if __name__ == "__main__":
    sys.exit(main())
