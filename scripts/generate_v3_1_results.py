#!/usr/bin/env python3
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etf_agent import semantic_query_v3
from etf_agent.v3 import extract_v3_test_questions

SOURCE = ROOT / "etf-query-test-questions.md"
OUT = ROOT / "answer" / "test3.1-results.md"
OUT_JSON = ROOT / "answer" / "test3.1-results.json"

EXPECTED = {
    "近1年收益率超过20%的ETF": {
        "route": ("filter", "filter"),
        "must_not_contain": ["未找到符合条件的 ETF"],
        "must_contain": ["近1年收益率"],
    },
    "我想找跟踪科创50的ETF": {
        "route": ("filter", "filter"),
        "must_not_contain": ["未找到符合条件的 ETF"],
        "must_contain": ["科创50"],
    },
}


def main() -> int:
    items = [item for item in extract_v3_test_questions(SOURCE) if item["phase"] in {"v3.0", "v3.1"}]
    passed = 0
    failed = 0
    records = []
    lines = [
        "# v3.0 + v3.1 抽取问题测试结果",
        "",
        f"测试来源：[`etf-query-test-questions.md`](../{SOURCE.name})",
        "",
        "运行方式：`.venv/bin/python scripts/generate_v3_1_results.py`",
        "",
        f"测试时间：{date.today().isoformat()}",
        "",
        "说明：",
        "",
        "- 本轮从总问题集中抽取 `v3.0` 与 `v3.1` 范围内的问题。",
        "- 使用 `semantic_query_v3(..., no_llm=True)`，跳过 LLM，但连接远端真实 MongoDB 执行查询。",
        "- 本文件是远端真实 MongoDB 查询结果，不是 dry-run 示例数据。",
        "- `v3.1` 覆盖 search / filter / sort / compare，以及 filter -> compare 派生演示。",
        "",
    ]
    for phase in ("v3.0", "v3.1"):
        phase_items = [item for item in items if item["phase"] == phase]
        lines.extend(
            [
                f"## {phase} 问题",
                "",
            ]
        )
        for index, item in enumerate(phase_items, start=1):
            result = semantic_query_v3(item["question"], root=ROOT, no_llm=True)
            route = f"{result['v3'].get('recognized_query_mode')} / {result['v3'].get('intent')}"
            status, reason = evaluate_result(item["question"], result)
            if status == "PASS":
                passed += 1
            else:
                failed += 1
            records.append(_record(item, result, route, status, reason))
            lines.extend(_question_section(index, item, result, route, status, reason))
        lines.append("")

    v3_0_count = sum(1 for item in items if item["phase"] == "v3.0")
    v3_1_count = sum(1 for item in items if item["phase"] == "v3.1")
    lines.extend(
        [
            "## 汇总",
            "",
            f"- v3.0 抽取题数：{v3_0_count}",
            f"- v3.1 抽取题数：{v3_1_count}",
            f"- 总题数：{len(items)}",
            f"- PASS：{passed}",
            f"- FAIL：{failed}",
            "",
            "本文件可直接作为 v3.1 demo 展示材料：先展示 v3.0 单只基金能力，再展示 v3.1 搜索、筛选、排序和对比能力。",
            "",
        ]
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    print(OUT_JSON)
    return 1 if failed else 0


def evaluate_result(question: str, result: dict) -> tuple[str, str]:
    expected = EXPECTED.get(question)
    if not expected:
        if str(result.get("answer", "")).startswith("远端查询失败"):
            return "FAIL", "远端查询失败"
        return "PASS", ""

    route = (result["v3"].get("recognized_query_mode"), result["v3"].get("intent"))
    expected_route = expected.get("route")
    if expected_route and route != expected_route:
        return "FAIL", f"路由不匹配：实际 {route[0]} / {route[1]}"

    answer = str(result.get("answer", ""))
    for text in expected.get("must_not_contain", []):
        if text in answer:
            return "FAIL", f"不应包含：{text}"
    for text in expected.get("must_contain", []):
        if text not in answer:
            return "FAIL", f"缺少关键内容：{text}"
    return "PASS", ""


def _question_section(index: int, item: dict, result: dict, route: str, status: str, reason: str) -> list[str]:
    lines = [
        f"### Q{index} {item['question']}",
        "",
        f"- 来源章节：{item['section']}",
        f"- v3 路由：`{route}`",
        f"- 判定：{status}" + (f"（{reason}）" if reason else ""),
        "",
        "**实际回答**",
        "",
        result["answer"],
        "",
    ]
    if result.get("query_plan"):
        lines.extend(
            [
                "**查询计划**",
                "",
                "```json",
                json.dumps(result["query_plan"], ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    lines.extend(["---", ""])
    return lines


def _record(item: dict, result: dict, route: str, status: str, reason: str) -> dict:
    return {
        "phase": item["phase"],
        "section": item["section"],
        "question": item["question"],
        "route": route,
        "status": status,
        "reason": reason,
        "answer": result.get("answer", ""),
        "v3": result.get("v3"),
        "v3_ast": result.get("v3_ast"),
        "query_plan": result.get("query_plan"),
        "result": result.get("result"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
