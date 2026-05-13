from __future__ import annotations

import re
from typing import Any


def compose_composite_answer(question: str, facts: list[dict[str, Any]], *, report_policy: dict[str, Any] | None = None) -> str:
    report_policy = report_policy or {}
    if "重仓股" in question and len(_fundcodes(facts)) >= 2:
        return _compose_compare_holding(question, facts, report_policy)
    if "持仓" in question or any(_first_fund_fact(fact, "report_industry.top") for fact in facts):
        return _compose_holding_summary(facts)
    return _compose_default(facts, report_policy)


def compose_candidate_clarification(keyword: str, options: list[dict[str, Any]]) -> str:
    lines = [
        f"我找到多只与“{keyword}”相关的 ETF，请先确认要查哪一只：",
        "",
        "| 基金代码 | 基金简称 | 跟踪指数 | 基金规模 | 匹配原因 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for option in options[:5]:
        lines.append(
            "| {fundcode} | {label} | {tracking_index} | {scale} | {match_reason} |".format(
                fundcode=option.get("fundcode", ""),
                label=option.get("label", ""),
                tracking_index=option.get("tracking_index", ""),
                scale=option.get("scale", ""),
                match_reason=option.get("match_reason", ""),
            )
        )
    lines.extend(["", "确认具体基金后，我可以继续查基本信息和持仓。"])
    return "\n".join(lines)


def _compose_default(facts: list[dict[str, Any]], report_policy: dict[str, Any]) -> str:
    parts: list[str] = []
    for fact in facts:
        if fact.get("intent") in {"search", "filter"} and len(facts) > 1:
            continue
        answer = _strip_runtime_footers(str(fact.get("answer") or ""))
        answer = _strip_data_as_of(answer)
        if answer:
            parts.append(answer)
    answer = "\n\n".join(parts)
    note = _holding_note(report_policy)
    data_as_of = _common_data_as_of(facts)
    tail = [item for item in (note, f"数据截至 {data_as_of}。" if data_as_of else "") if item]
    if tail:
        answer = f"{answer}\n\n{' '.join(tail)}".strip()
    return answer


def _compose_holding_summary(facts: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for fact in facts:
        if fact.get("intent") in {"search", "filter"}:
            continue
        if fact.get("intent") in {"report_industry", "report_concept"}:
            continue
        answer = _strip_data_as_of(_strip_runtime_footers(str(fact.get("answer") or "")))
        if answer:
            parts.append(answer)

    industries = _first_fact_value(facts, "report_industry.top") or []
    concepts = _first_fact_value(facts, "report_concept.top") or []
    period = _first_metadata(facts, "report_period")
    if industries or concepts:
        holding = "持仓方面"
        if period:
            holding += f"，{period}显示"
        clauses = []
        if industries:
            clauses.append(f"主要行业包括{_join_cn(industries)}")
        if concepts:
            clauses.append(f"重仓概念包括{_join_cn(concepts)}")
        holding += "，" + "；".join(clauses) + "。"
        parts.append(holding)

    data_as_of = _common_data_as_of(facts)
    if data_as_of:
        parts.append(f"数据截至 {data_as_of}。")
    return "\n\n".join(parts)


def _compose_compare_holding(question: str, facts: list[dict[str, Any]], report_policy: dict[str, Any]) -> str:
    fundcodes = _ordered_fundcodes(question, facts)
    rows = [
        ["指标", *fundcodes],
        ["---", *("---" for _ in fundcodes)],
    ]
    for label, key in (
        ("基金简称", "fund.name"),
        ("基金规模", "scale.latest"),
        ("管理费率", "fee.manage"),
        ("托管费率", "fee.custody"),
        ("前十大重仓股", "report_holding.top_codes"),
    ):
        row = [label]
        for fundcode in fundcodes:
            value = _fact_for_fund(facts, fundcode, key)
            if isinstance(value, list):
                value = "、".join(value)
            row.append(str(value or "暂无数据"))
        rows.append(row)
    table = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    note = _holding_note(report_policy) or "重仓股当前按最新年报口径展示。"
    data_as_of = _common_data_as_of(facts)
    if data_as_of:
        note = f"{note} 数据截至 {data_as_of}。"
    return f"{table}\n\n{note}"


def _fundcodes(facts: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for fact in facts:
        for fund in fact.get("funds") or []:
            fundcode = fund.get("fundcode")
            if fundcode and fundcode not in result:
                result.append(str(fundcode))
    return result


def _ordered_fundcodes(question: str, facts: list[dict[str, Any]]) -> list[str]:
    available = _fundcodes(facts)
    requested = [code for code in re.findall(r"(?<!\d)\d{6}(?!\d)", question) if code in available]
    return list(dict.fromkeys(requested + available))


def _fact_for_fund(facts: list[dict[str, Any]], fundcode: str, key: str) -> Any:
    for fact in facts:
        for fund in fact.get("funds") or []:
            if str(fund.get("fundcode") or "") != fundcode:
                continue
            value = (fund.get("facts") or {}).get(key)
            if value not in (None, "", []):
                return value
    return None


def _first_fact_value(facts: list[dict[str, Any]], key: str) -> Any:
    for fact in facts:
        for fund in fact.get("funds") or []:
            value = (fund.get("facts") or {}).get(key)
            if value not in (None, "", []):
                return value
    return None


def _first_fund_fact(fact: dict[str, Any], key: str) -> Any:
    for fund in fact.get("funds") or []:
        value = (fund.get("facts") or {}).get(key)
        if value not in (None, "", []):
            return value
    return None


def _first_metadata(facts: list[dict[str, Any]], key: str) -> str:
    for fact in facts:
        value = (fact.get("metadata") or {}).get(key)
        if value:
            return str(value)
        for fund in fact.get("funds") or []:
            value = (fund.get("metadata") or {}).get(key)
            if value:
                return str(value)
    return ""


def _common_data_as_of(facts: list[dict[str, Any]]) -> str:
    dates = []
    for fact in facts:
        value = (fact.get("metadata") or {}).get("data_as_of")
        if value:
            dates.append(str(value))
        for fund in fact.get("funds") or []:
            value = (fund.get("metadata") or {}).get("data_as_of")
            if value:
                dates.append(str(value))
    unique = sorted(set(dates))
    return unique[-1] if unique else ""


def _holding_note(report_policy: dict[str, Any]) -> str:
    policy = report_policy.get("report_holding") if isinstance(report_policy, dict) else None
    if isinstance(policy, dict) and policy.get("user_note"):
        return str(policy["user_note"]) + "。"
    return ""


def _join_cn(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return "、".join(items[:-1]) + "和" + items[-1]


def _strip_runtime_footers(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        if line.startswith("查询起始时间："):
            continue
        if line.startswith("查询结束时间："):
            continue
        if line.startswith("LLM token："):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _strip_data_as_of(text: str) -> str:
    return re.sub(r"\n*数据截至 \d{4}-\d{2}-\d{2}。\n*", "\n", text).strip()
