from __future__ import annotations

import re


PERIOD_PATTERNS = [
    (re.compile(r"各周期"), "all"),
    (re.compile(r"近一周|近1周|最近一周|这一周|这周"), "1w"),
    (re.compile(r"近一[月個个]月?|近1[月個个]月?|最近一[月個个]月?|这一[月個个]月?|这[月個个]月?"), "1m"),
    (re.compile(r"近三[月個个]月?|近3[月個个]月?|这三[月個个]月?|这3[月個个]月?"), "3m"),
    (re.compile(r"近六[月個个]月?|近6[月個个]月?|这六[月個个]月?|这6[月個个]月?|近半年|这半年"), "6m"),
    (re.compile(r"近一[年個个]年?|近1[年個个]年?|最近一[年個个]年?|这一[年個个]年?|这[年個个]年?"), "1y"),
    (re.compile(r"近二[年個个]年?|近2[年個个]年?|这二[年個个]年?|这2[年個个]年?"), "2y"),
    (re.compile(r"近三[年個个]年?|近3[年個个]年?|这三[年個个]年?|这3[年個个]年?"), "3y"),
    (re.compile(r"近五[年個个]年?|近5[年個个]年?|这五[年個个]年?|这5[年個个]年?"), "5y"),
    (re.compile(r"(?:两|2)年期"), "2y"),
    (re.compile(r"今年以来|今年"), "ytd"),
    (re.compile(r"成立以来|成立到现在|成立至今"), "std"),
]


_CURRENT_YEAR = 2026


def extract_specified_date(question: str) -> str | None:
    # 2026年5月11日 / 2026年3月15日
    m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})[日号]?", question)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 2026-05-11 / 2026/05/11
    m = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", question)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 5月11日
    m = re.search(r"(\d{1,2})月(\d{1,2})[日号]?", question)
    if m:
        return f"{_CURRENT_YEAR}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    # 3.15净值 / 3/15净值（仅在净值上下文中）
    m = re.search(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?=净值|的净值|单位净值)", question)
    if m:
        return f"{_CURRENT_YEAR}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


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
