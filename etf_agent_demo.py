#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from etf_agent import semantic_query, semantic_query_v3


def main() -> int:
    parser = argparse.ArgumentParser(description="ETF 语义查询本地 demo")
    parser.add_argument("question", help="自然语言 ETF 问题，例如：510300 盘子有多大")
    parser.add_argument("--dry-run", action="store_true", help="不调用 Qwen/SSH，使用确定性计划和示例远端结果演示链路")
    parser.add_argument("--no-llm", action="store_true", help="跳过 Qwen，仍执行真实 SSH 查询")
    parser.add_argument("--v3", action="store_true", help="使用 v3.0 路由和 AST 预览")
    parser.add_argument("--verbose", action="store_true", help="打印完整调试链路和远端原始 JSON")
    parser.add_argument("--answer-only", action="store_true", help="只打印最终人话回答")
    args = parser.parse_args()

    if args.v3:
        output = semantic_query_v3(
            args.question,
            root=Path(__file__).resolve().parent,
            dry_run=args.dry_run,
            no_llm=args.no_llm,
        )
    else:
        output = semantic_query(
            args.question,
            root=Path(__file__).resolve().parent,
            dry_run=args.dry_run,
            no_llm=args.no_llm,
        )
    print_report(output, verbose=args.verbose, answer_only=args.answer_only)
    return 1 if "error" in output else 0


def print_report(output: dict, *, verbose: bool = False, answer_only: bool = False) -> None:
    if answer_only and "answer" in output:
        print(output["answer"])
        return

    print("用户问题")
    print(output["question"])
    print()

    if "error" in output:
        print(output["error"])
        if output.get("matches"):
            print()
            print("候选 ETF")
            for item in output["matches"]:
                print(f"- {item.get('fundcode')} {item.get('name')} {item.get('thscode', '')}".rstrip())
        print()
        print("调试过程")
        print(json.dumps(output["debug"], ensure_ascii=False, indent=2))
        return

    print("最终简短回答")
    print(output["answer"])
    print()

    if not verbose:
        print("提示：需要 AST、查询计划和远端原始 JSON 时，加 --verbose。")
        return

    print("关键查询信息")
    if output.get("entities"):
        print(f"基金代码: {output['entities'].get('fundcode', '暂无数据')}")
    if output.get("query_plan"):
        print_query_plan_summary(output["query_plan"])
    if output.get("v3"):
        print(f"v3 路由: {output['v3'].get('recognized_query_mode')} / {output['v3'].get('intent')}")
    if output.get("v3_ast"):
        print("v3 AST")
        print(json.dumps(output["v3_ast"], ensure_ascii=False, indent=2))
    print()

    if output.get("v3"):
        print("查询计划")
        print(json.dumps(output.get("query_plan"), ensure_ascii=False, indent=2))
        print()

        print("远端数据库结果")
        print(json.dumps(output.get("result"), ensure_ascii=False, indent=2))
        return

    print("实体识别结果")
    print(json.dumps(output["entities"], ensure_ascii=False, indent=2))
    print()

    print("向量召回候选")
    print(json.dumps(output["retrieved_mappings"], ensure_ascii=False, indent=2))
    print()

    print("Qwen 查询计划")
    print(json.dumps(output["query_plan"], ensure_ascii=False, indent=2))
    print()

    print("SQL-like 展示语句")
    print(output["sql_like"])
    print()

    print("Mongo 查询参数")
    print(json.dumps(output["mongo_params"], ensure_ascii=False, indent=2))
    print()

    print("远端数据库结果")
    print(json.dumps(output["result"], ensure_ascii=False, indent=2))
    print()

    print("字段中文名映射")
    print(json.dumps(output["field_labels"], ensure_ascii=False, indent=2))
    print()

    print("调试过程")
    print(json.dumps(output["debug"], ensure_ascii=False, indent=2))


def print_query_plan_summary(query_plan: dict) -> None:
    if "steps" in query_plan:
        for index, step in enumerate(query_plan["steps"], start=1):
            print(f"查询步骤 {index}")
            print(f"集合: {step['collection']}")
            print(f"字段: {', '.join(step['projection'])}")
        return
    print(f"集合: {query_plan['collection']}")
    print(f"字段: {', '.join(query_plan['projection'])}")


if __name__ == "__main__":
    raise SystemExit(main())
