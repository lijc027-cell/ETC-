#!/usr/bin/env python3
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ANSWERS = ROOT / "result" / "codex-etf-query-answers.md"

TARGETS = [
    {
        "section_title": "八、条件筛选",
        "next_section_title": "九、多只对比",
        "question_prefix": "八.",
        "label": "Section 8",
        "json": ROOT / "result" / "audit-v3.3-section8-compare-real.json",
        "md": ROOT / "result" / "audit-v3.3-section8-compare-real.md",
        "html": ROOT / "result" / "audit-v3.3-section8-compare-real.html",
    },
    {
        "section_title": "九、多只对比",
        "next_section_title": "十、复合意图",
        "question_prefix": "九.",
        "label": "Section 9",
        "json": ROOT / "result" / "audit-v3.3-section9-compare-real.json",
        "md": ROOT / "result" / "audit-v3.3-section9-compare-real.md",
        "html": ROOT / "result" / "audit-v3.3-section9-compare-real.html",
    },
]


def main() -> int:
    source_lines = ANSWERS.read_text(encoding="utf-8").splitlines()
    for target in TARGETS:
        expected = load_expected_answers(
            source_lines,
            target["section_title"],
            target["next_section_title"],
            target["question_prefix"],
        )
        payload = json.loads(target["json"].read_text(encoding="utf-8"))
        records = payload["records"]
        for record in records:
            question_id = record["question_id"]
            expected_answer = expected[question_id]
            record["expected_answer"] = expected_answer
            record["answer_match"] = compact(expected_answer) in compact(record.get("actual_answer", ""))
        payload["summary"] = summarize(records)
        target["json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        target["md"].write_text(render_markdown(target["label"], payload["summary"], records), encoding="utf-8")
        target["html"].write_text(render_html(target, payload["summary"], records), encoding="utf-8")
        print(target["json"])
        print(target["md"])
        print(target["html"])
    return 0


def load_expected_answers(
    lines: list[str],
    section_title: str,
    next_section_title: str,
    question_prefix: str,
) -> dict[str, str]:
    expected: dict[str, str] = {}
    current_id: str | None = None
    current: list[str] = []
    in_section = False
    section_header = f"## {section_title}"
    next_section_header = f"## {next_section_title}"
    question_header = f"### {question_prefix}"
    for line in lines:
        if line.startswith(section_header):
            in_section = True
            continue
        if in_section and line.startswith(next_section_header):
            break
        if not in_section:
            continue
        if line.startswith(question_header):
            if current_id is not None:
                expected[current_id] = "\n".join(current).strip()
            current_id = line.split()[1]
            current = []
            continue
        if current_id is not None:
            current.append(line)
    if current_id is not None:
        expected[current_id] = "\n".join(current).strip()
    return expected


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    passed = sum(1 for record in records if record.get("pass_fail") == "PASS")
    matched = sum(1 for record in records if record.get("answer_match"))
    return {
        "total_cases": total,
        "scoped_cases": total,
        "passed": passed,
        "failed": total - passed,
        "expected_answer_match_total": matched,
        "expected_answer_mismatch_total": total - matched,
    }


def render_markdown(section_label: str, summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        f"# v3.3 {section_label} Expected Compare",
        "",
        "## Summary",
        "",
        f"- total_cases: `{summary['total_cases']}`",
        f"- scoped_cases: `{summary['scoped_cases']}`",
        f"- passed: `{summary['passed']}`",
        f"- failed: `{summary['failed']}`",
        f"- expected_answer_match_total: `{summary['expected_answer_match_total']}`",
        f"- expected_answer_mismatch_total: `{summary['expected_answer_mismatch_total']}`",
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
                record.get("expected_answer") or "—",
                "",
                "**Actual**",
                "",
                record.get("actual_answer") or "—",
                "",
            ]
        )
    return "\n".join(lines)


def render_html(target: dict[str, Any], summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    cards = "\n".join(render_case_html(record) for record in records)
    title = f"v3.3 {target['label']} Expected Compare"
    sub = (
        f"{target['json']} · {summary['passed']} pass · {summary['failed']} fail · "
        f"expected match {summary['expected_answer_match_total']}/{summary['total_cases']}"
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
  :root {{ --bg: #f4f0e6; --paper: #fffaf0; --ink: #2f2418; --muted: #6e5c45; --line: #d7c8b2; --pass: #2f6f4e; --fail: #9f2f2f; --match: #2f6f4e; --mismatch: #8a5a1f; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: Georgia, serif; }}
  .wrap {{ max-width: 1240px; margin: 0 auto; padding: 28px 22px 48px; }}
  .hero {{ padding: 10px 0 18px; border-bottom: 1px solid var(--line); margin-bottom: 18px; }}
  h1 {{ margin: 0 0 8px; font-size: 32px; }}
  .sub {{ color: var(--muted); font-size: 14px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 18px 0 24px; }}
  .stat {{ background: var(--paper); border: 1px solid var(--line); padding: 14px 16px; border-radius: 6px; }}
  .stat .k {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0; }}
  .stat .v {{ margin-top: 6px; font-size: 28px; }}
  .cases {{ display: grid; gap: 16px; }}
  .card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 6px; padding: 18px; }}
  .head {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 10px; }}
  .qid {{ font-size: 22px; }}
  .badge {{ font-size: 12px; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--line); }}
  .pass {{ color: var(--pass); border-color: color-mix(in srgb, var(--pass) 35%, var(--line)); }}
  .fail {{ color: var(--fail); border-color: color-mix(in srgb, var(--fail) 35%, var(--line)); }}
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
      <h1>{escape(title)}</h1>
      <div class="sub">{escape(sub)}</div>
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


def render_case_html(record: dict[str, Any]) -> str:
    badge_class = "pass" if record.get("pass_fail") == "PASS" else "fail"
    expected = record.get("expected_answer") or "—"
    actual = record.get("actual_answer") or "—"
    meta = (
        f"answer_match={str(record.get('answer_match')).lower()} · "
        f"expected_outcome={record.get('expected_outcome')} · "
        f"actual_outcome={record.get('actual_outcome')}"
    )
    return f"""
    <section class="card">
      <div class="head">
        <div class="qid">{escape(record.get('question_id', ''))} {escape(record.get('question', ''))}</div>
        <div class="badge {badge_class}">{escape(record.get('pass_fail', ''))}</div>
      </div>
      <div class="meta">{escape(meta)}</div>
      <div class="cols">
        <div class="panel">
          <h3>Expected</h3>
          <pre>{escape(expected)}</pre>
        </div>
        <div class="panel">
          <h3>Actual</h3>
          <pre>{escape(actual)}</pre>
        </div>
      </div>
    </section>
"""


def compact(text: str) -> str:
    return "".join(str(text).split())


def escape(text: str) -> str:
    return html.escape(str(text))


if __name__ == "__main__":
    raise SystemExit(main())
