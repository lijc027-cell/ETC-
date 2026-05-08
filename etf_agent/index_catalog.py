from __future__ import annotations

import re
from typing import Any


INDEX_FIELDS = [
    "ths_name_of_tracking_index_fund",
    "ths_tracking_index_code_fund",
]

MOCK_INDEX_CATALOG = [
    {
        "ths_name_of_tracking_index_fund": "沪深300指数",
        "ths_tracking_index_code_fund": "000300",
    },
    {
        "ths_name_of_tracking_index_fund": "中证小盘500指数",
        "ths_tracking_index_code_fund": "000905",
    },
    {
        "ths_name_of_tracking_index_fund": "上证科创板50成份指数",
        "ths_tracking_index_code_fund": "000688",
    },
]

INDEX_ALIASES = {
    "科创50": "上证科创板50成份指数",
    "沪深300": "沪深300指数",
    "中证500": "中证小盘500指数",
}


def resolve_index_name(keyword: str, config=None, *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run or config is None:
        return resolve_index_name_from_catalog(keyword, MOCK_INDEX_CATALOG)

    from .remote import fetch_etf_name_catalog

    return resolve_index_name_from_catalog(keyword, fetch_etf_name_catalog(config))


def resolve_index_name_from_catalog(keyword: str, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    entries = _unique_index_entries(catalog)
    normalized_keyword = _normalize(keyword)
    if not normalized_keyword:
        return {"status": "not_found", "matches": []}

    code_matches = [entry for entry in entries if normalized_keyword == _normalize(entry["code"])]
    if code_matches:
        return _matched(code_matches[0], code_matches)

    exact_matches = [entry for entry in entries if normalized_keyword == _normalize(entry["name"])]
    if exact_matches:
        return _matched(exact_matches[0], exact_matches)

    alias = INDEX_ALIASES.get(re.sub(r"\s+", "", keyword))
    if alias:
        alias_matches = [entry for entry in entries if _normalize(entry["name"]) == _normalize(alias)]
        if alias_matches:
            return _matched(alias_matches[0], alias_matches)

    substring_matches = [
        entry
        for entry in entries
        if normalized_keyword in _normalize(entry["name"]) or _normalize(entry["name"]) in normalized_keyword
    ]
    if len(substring_matches) == 1:
        return _matched(substring_matches[0], substring_matches)
    if len(substring_matches) > 1:
        return {"status": "ambiguous", "matches": substring_matches[:10]}
    return {"status": "not_found", "matches": []}


def _unique_index_entries(catalog: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    entries: list[dict[str, str]] = []
    for row in catalog:
        name = str(row.get("ths_name_of_tracking_index_fund") or "").strip()
        code = str(row.get("ths_tracking_index_code_fund") or "").strip()
        if not name:
            continue
        key = (name, code)
        if key in seen:
            continue
        seen.add(key)
        entries.append({"name": name, "code": code})
    return entries


def _matched(entry: dict[str, str], matches: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "status": "matched",
        "value": entry["name"],
        "matches": matches[:10],
    }


def _normalize(value: str) -> str:
    return re.sub(r"[\s（）()]", "", value).upper()
