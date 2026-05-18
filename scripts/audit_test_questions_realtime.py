#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from datetime import date
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etf_agent import semantic_query_v3
from scripts.audit_answer_format import format_audit_answer, llm_total_tokens


OUT_JSON = ROOT / "result" / "audit-v3.5-realtime.json"
OUT_MD = ROOT / "result" / "audit-v3.5-realtime.md"
OUT_HTML = ROOT / "result" / "audit-v3.5-realtime.html"
REAL_OUT_JSON = ROOT / "result" / "audit-v3.5-realtime-real.json"
REAL_OUT_MD = ROOT / "result" / "audit-v3.5-realtime-real.md"
REAL_OUT_HTML = ROOT / "result" / "audit-v3.5-realtime-real.html"
DEFAULT_EXPECTED = ROOT / "result" / "codex-realtime-direct-answers.md"


QUESTION_STATUS: dict[str, str] = {
    "510050现在什么价": "executable",
    "科创50ETF报多少": "ambiguous_fund_identity",
    "510050涨了吗": "executable",
    "科创50ETF跌了多少": "ambiguous_fund_identity",
    "510050成交额多少": "executable",
    "510050盘口": "executable",
    "科创50ETF买一多少": "ambiguous_fund_identity",
    "510050溢价多少": "executable",
    "科创50ETF是折价还是溢价": "ambiguous_fund_identity",
    "510050内外盘": "executable",
    "科创50ETF外盘多少": "ambiguous_fund_identity",
    "510050振幅多大": "executable",
    "对比510050和510300": "capability_ambiguous",
    "510050涨了没，成交额多少": "executable",
    "科创50ETF怎么样，折价了吗": "ambiguous_fund_identity",
    "159915价格多少，买一卖一挂了多少": "executable",
    "对比510050和510300的涨跌幅和溢价": "executable",
    "这只ETF盘口什么情况，内外盘怎么样": "needs_fund_identity",
    "510050价格、涨跌幅、成交额、溢价率": "executable",
    "510300现在行情，有没有折价，外盘强还是内盘强": "executable",
    "510050持仓哪些股票": "executable",
    "510300基金经理是谁": "executable",
    "科创50ETF跟踪什么指数": "ambiguous_fund_identity",
    "这只ETF规模多大": "needs_fund_identity",
    "510050费率多少": "executable",
    "贵州茅台现在什么价": "unsupported_domain",
    "上证指数多少点": "unsupported_domain",
    "510050五档盘口": "field_not_supported",
    "这只ETF历史走势": "needs_fund_identity",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit realtime test questions against v3.5 dry-run runtime.")
    parser.add_argument("--real", action="store_true", help="Run against the configured realtime source instead of dry-run fixtures.")
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--out-html", type=Path)
    parser.add_argument("--start", type=int, default=1, help="1-based question index to start from.")
    parser.add_argument("--limit", type=int, help="Maximum number of questions to run.")
    args = parser.parse_args(argv)
    out_json = args.out_json or (REAL_OUT_JSON if args.real else OUT_JSON)
    out_md = args.out_md or (REAL_OUT_MD if args.real else OUT_MD)
    out_html = args.out_html or (REAL_OUT_HTML if args.real else OUT_HTML)

    questions = slice_questions(load_questions(ROOT / "test-questions-realtime.md"), start=args.start, limit=args.limit)
    expected = load_expected_answers(args.expected)

    records = []
    for item in questions:
        result = semantic_query_v3(item["question"], root=ROOT, dry_run=not args.real, phase="v3.5")
        records.append(build_record(item, result, expected.get(item["question"], "")))

    summary = summarize(records)
    payload = {"summary": summary, "records": records}

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_md(records, summary), encoding="utf-8")
    out_html.write_text(render_html(records, summary), encoding="utf-8")
    print(out_json)
    print(out_md)
    print(out_html)
    print(f"passed={summary['passed']} failed={summary['failed']} total={summary['total_cases']}")
    return 0 if summary["failed"] == 0 else 1


def load_questions(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current_section = ""
    section_index: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            current_section = line[3:].strip()
            section_index[current_section] = 0
            continue
        if line.startswith("- ") and current_section:
            section_index[current_section] += 1
            rows.append(
                {
                    "question_id": f"{current_section}.{section_index[current_section]}",
                    "section": current_section,
                    "question": line[2:].strip(),
                }
            )
    return rows


def slice_questions(rows: list[dict[str, str]], *, start: int, limit: int | None) -> list[dict[str, str]]:
    start_index = max(start, 1) - 1
    if limit is None:
        return rows[start_index:]
    return rows[start_index : start_index + max(limit, 0)]


def load_expected_answers(path: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    current_question: str | None = None
    buffer: list[str] = []
    in_question_answers = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("## 逐题整理"):
            in_question_answers = True
            continue
        if raw.startswith("## ") and not raw.startswith("## 逐题整理"):
            in_question_answers = False
            continue
        if in_question_answers and raw.startswith("#### "):
            if current_question is not None:
                expected[current_question] = "\n".join(buffer).strip()
            current_question = raw[5:].strip()
            buffer = []
            continue
        if raw.startswith("#"):
            continue
        if in_question_answers and current_question is not None:
            buffer.append(raw)
    if current_question is not None:
        expected[current_question] = "\n".join(buffer).strip()
    return expected


def build_record(item: dict[str, str], result: dict[str, Any], expected_answer: str) -> dict[str, Any]:
    v3 = result.get("v3") or {}
    routing = v3.get("routing_result") or {}
    actual_type = str(routing.get("type") or "Unknown")
    reason = routing.get("reason")
    actual_outcome = f"{actual_type}({reason})" if reason else actual_type
    expected_status = QUESTION_STATUS.get(item["question"], "unknown")
    pass_fail = evaluate(expected_status, actual_type, reason)
    return {
        "question_id": item["question_id"],
        "question": item["question"],
        "section": item["section"],
        "phase": "v3.5",
        "expected_status": expected_status,
        "expected_answer": expected_answer,
        "user_visible_answer": format_audit_answer(str(result.get("answer") or ""), result=result),
        "pass/fail": pass_fail,
        "actual_outcome": actual_outcome,
        "failure_stage": v3.get("failure_stage") or result.get("failure_stage"),
        "failure_reason": v3.get("failure_reason") or result.get("failure_reason"),
        "llm_total_tokens": llm_total_tokens(result),
        "raw_result": result,
    }


def evaluate(expected_status: str, actual_type: str, reason: str | None) -> str:
    if expected_status == "executable":
        return "PASS" if actual_type == "ExecutableQuery" else "FAIL"
    if expected_status == "needs_fund_identity":
        return "PASS" if actual_type == "UnsupportedQuery" and reason == "fund_identity_required" else "FAIL"
    if expected_status == "ambiguous_fund_identity":
        return "PASS" if actual_type == "UnsupportedQuery" and reason == "fund_identity_ambiguous" else "FAIL"
    if expected_status == "capability_ambiguous":
        return "PASS" if actual_type == "ClarificationRequired" and reason == "capability_ambiguous" else "FAIL"
    if expected_status == "unsupported_domain":
        return "PASS" if actual_type == "UnsupportedQuery" and reason == "unsupported_domain" else "FAIL"
    if expected_status == "field_not_supported":
        return "PASS" if actual_type == "UnsupportedQuery" and reason == "field_not_supported" else "FAIL"
    if expected_status == "unsupported_info":
        return "PASS" if actual_type == "UnsupportedQuery" else "FAIL"
    return "FAIL"


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_cases": len(records),
        "passed": sum(1 for item in records if item["pass/fail"] == "PASS"),
        "failed": sum(1 for item in records if item["pass/fail"] == "FAIL"),
        "llm_total_tokens": sum(int(item.get("llm_total_tokens") or 0) for item in records),
        "test_date": str(date.today()),
    }


def render_md(records: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        "# v3.5 Realtime Audit",
        "",
        f"- total: {summary['total_cases']}",
        f"- passed: {summary['passed']}",
        f"- failed: {summary['failed']}",
        "",
        "| ID | Status | Question | Actual |",
        "| --- | --- | --- | --- |",
    ]
    for item in records:
        actual = item["actual_outcome"]
        lines.append(f"| {item['question_id']} | {item['pass/fail']} | {item['question']} | {actual} |")
    return "\n".join(lines) + "\n"


def render_html(records: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    cards: list[str] = []
    for item in records:
        status_class = "pass" if item["pass/fail"] == "PASS" else "fail"
        cards.append(
            f"""<section class="card"><div class="head"><div class="qid">{html.escape(item['question_id'])} {html.escape(item['question'])}</div><div class="badge {status_class}">{item['pass/fail']}</div></div><div class="meta">phase={html.escape(item['phase'])} · actual={html.escape(item['actual_outcome'])} · tokens={item['llm_total_tokens']}</div><div class="cols"><div class="panel"><h3>Expected</h3><pre>{html.escape(item['expected_answer'])}</pre></div><div class="panel"><h3>Answer</h3><pre>{html.escape(item['user_visible_answer'])}</pre></div></div></section>"""
        )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>v3.5 Realtime Audit</title><style>:root{{--bg:#f4f0e6;--paper:#fffaf0;--ink:#2f2418;--muted:#6e5c45;--line:#d7c8b2;--pass:#2f6f4e;--fail:#9f2f2f;}}*{{box-sizing:border-box;}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Georgia,serif;}}.wrap{{max-width:1320px;margin:0 auto;padding:28px 22px 48px;}}.hero{{padding:10px 0 18px;border-bottom:1px solid var(--line);margin-bottom:18px;}}h1{{margin:0 0 8px;font-size:32px;}}.sub{{color:var(--muted);font-size:14px;line-height:1.5;}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:18px 0 24px;}}.stat{{background:var(--paper);border:1px solid var(--line);padding:14px 16px;border-radius:6px;}}.stat .k{{color:var(--muted);font-size:12px;}}.stat .v{{margin-top:6px;font-size:26px;}}.cases{{display:grid;gap:16px;}}.card{{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:18px;}}.head{{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin-bottom:10px;}}.qid{{font-size:20px;line-height:1.35;}}.badge{{font-size:12px;padding:3px 8px;border-radius:999px;border:1px solid var(--line);white-space:nowrap;}}.pass{{color:var(--pass);}}.fail{{color:var(--fail);}}.meta{{color:var(--muted);font-size:13px;margin-bottom:14px;line-height:1.5;}}.cols{{display:grid;grid-template-columns:.85fr 1.15fr;gap:14px;}}.panel{{border:1px solid var(--line);border-radius:6px;overflow:hidden;}}.panel h3{{margin:0;padding:10px 12px;font-size:14px;background:rgba(0,0,0,.03);}}.panel pre{{margin:0;padding:12px;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;line-height:1.5;}}@media(max-width:900px){{.cols{{grid-template-columns:1fr;}}}}</style></head><body><div class="wrap"><div class="hero"><h1>v3.5 Realtime Audit</h1><div class="sub">expected from result/codex-realtime-direct-answers.md · {summary['passed']} pass · {summary['failed']} fail · LLM 总 token 数：{summary['llm_total_tokens']}</div></div><div class="grid"><div class="stat"><div class="k">Total Cases</div><div class="v">{summary['total_cases']}</div></div><div class="stat"><div class="k">Passed</div><div class="v">{summary['passed']}</div></div><div class="stat"><div class="k">Failed</div><div class="v">{summary['failed']}</div></div><div class="stat"><div class="k">LLM Tokens</div><div class="v">{summary['llm_total_tokens']}</div></div></div><div class="cases">{''.join(cards)}</div></div></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
