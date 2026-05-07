from __future__ import annotations

import re
from typing import Any


CATALOG_FIELDS = [
    "fundcode",
    "thscode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_supervisor_fund",
    "ths_name_of_tracking_index_fund",
    "ths_tracking_index_code_fund",
]


MOCK_CATALOG = [
    {
        "fundcode": "510350",
        "thscode": "510350.SH",
        "ths_fund_extended_inner_short_name_fund": "沪深300ETF工银",
        "ths_fund_supervisor_fund": "工银瑞信基金",
        "ths_name_of_tracking_index_fund": "沪深300指数",
        "ths_tracking_index_code_fund": "000300",
    },
    {
        "fundcode": "510330",
        "thscode": "510330.SH",
        "ths_fund_extended_inner_short_name_fund": "沪深300ETF华夏",
        "ths_fund_supervisor_fund": "华夏基金",
        "ths_name_of_tracking_index_fund": "沪深300指数",
        "ths_tracking_index_code_fund": "000300",
    },
    {
        "fundcode": "159919",
        "thscode": "159919.SZ",
        "ths_fund_extended_inner_short_name_fund": "沪深300ETF",
        "ths_fund_supervisor_fund": "嘉实基金",
        "ths_name_of_tracking_index_fund": "沪深300指数",
        "ths_tracking_index_code_fund": "000300",
    },
]


def resolve_fundcode_from_name(question: str, config, *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return resolve_fundcode_from_catalog(question, MOCK_CATALOG)

    from .remote import fetch_etf_name_catalog

    return resolve_fundcode_from_catalog(question, fetch_etf_name_catalog(config))


def resolve_fundcode_from_catalog(question: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    matches = _rank_matches(question, catalog)
    if not matches:
        return {"status": "not_found", "matches": []}
    if len(matches) == 1:
        match = matches[0]
        return {
            "status": "matched",
            "fundcode": match["fundcode"],
            "matched_name": match["name"],
            "matched_thscode": match.get("thscode", ""),
            "matches": matches,
        }
    return {"status": "ambiguous", "matches": matches}


def _rank_matches(question: str, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query = _normalize(question)
    index_tokens = _index_tokens(query)
    manager_tokens = _manager_tokens(query)
    scored = []

    for index, row in enumerate(catalog):
        name = str(row.get("ths_fund_extended_inner_short_name_fund") or "")
        manager = str(row.get("ths_fund_supervisor_fund") or "")
        index_name = str(row.get("ths_name_of_tracking_index_fund") or "")
        haystack = _normalize(f"{name} {manager} {index_name}")
        normalized_name = _normalize(name)

        score = 0
        if normalized_name and normalized_name in query:
            score += 100
        if index_tokens and all(token in haystack for token in index_tokens):
            score += 30
        if manager_tokens and any(token in haystack for token in manager_tokens):
            score += 40
        if "ETF" in question.upper() and "ETF" in name.upper():
            score += 5
        if not manager_tokens and index_tokens and all(token in normalized_name for token in index_tokens):
            score += 20

        if score > 0 and _has_required_signal(index_tokens, manager_tokens, haystack):
            scored.append((_match(row), score, index))

    if not scored:
        return []
    scored.sort(key=lambda item: (-item[1], item[2]))
    best = scored[0][1]
    if manager_tokens and best >= 70:
        return [scored[0][0]]
    return [match for match, _score, _index in scored[:10]]


def _match(row: dict[str, Any]) -> dict[str, str]:
    return {
        "fundcode": str(row.get("fundcode", "")),
        "thscode": str(row.get("thscode", "")),
        "name": str(row.get("ths_fund_extended_inner_short_name_fund", "")),
        "manager": str(row.get("ths_fund_supervisor_fund", "")),
        "tracking_index": str(row.get("ths_name_of_tracking_index_fund", "")),
    }


def _has_required_signal(index_tokens: list[str], manager_tokens: list[str], haystack: str) -> bool:
    if manager_tokens:
        return bool(index_tokens) and any(token in haystack for token in manager_tokens)
    return bool(index_tokens)


def _index_tokens(query: str) -> list[str]:
    tokens = []
    for pattern in (r"沪深\s*300", r"中证\s*500", r"中证\s*1000", r"创业板", r"科创\s*50"):
        match = re.search(pattern, query, re.I)
        if match:
            tokens.append(re.sub(r"\s+", "", match.group(0)).upper())
    return tokens


def _manager_tokens(query: str) -> list[str]:
    managers = ["工银", "华夏", "嘉实", "易方达", "华泰柏瑞", "南方", "广发", "招商", "富国", "博时"]
    return [manager.upper() for manager in managers if manager.upper() in query]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()
