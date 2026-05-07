from __future__ import annotations

import re


PERIOD_PATTERNS = [
    (re.compile(r"各周期"), "all"),
    (re.compile(r"近一周|近1周"), "1w"),
    (re.compile(r"近一月|近1月"), "1m"),
    (re.compile(r"近三月|近3月"), "3m"),
    (re.compile(r"近六月|近6月"), "6m"),
    (re.compile(r"近一年|近1年|最近一年"), "1y"),
    (re.compile(r"近二年|近2年"), "2y"),
    (re.compile(r"近三年|近3年"), "3y"),
    (re.compile(r"近五年|近5年"), "5y"),
    (re.compile(r"今年以来|今年"), "ytd"),
    (re.compile(r"成立以来"), "std"),
]


def extract_entities(question: str) -> dict[str, str]:
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", question)
    if not match:
        raise ValueError("实体抽取失败：未识别到 6 位 ETF 基金代码。")

    entities = {"fundcode": match.group(1)}
    for pattern, period in PERIOD_PATTERNS:
        if pattern.search(question):
            entities["period"] = period
            break
    return entities
