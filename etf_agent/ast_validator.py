from __future__ import annotations

from copy import deepcopy
from typing import Any

from .capability_registry import BASE_COLLECTION, BLOCKED_V3_2_FIELDS


ALLOWED_OPERATORS = {"eq", "in", "contains", "gt", "gte", "lt", "lte"}
ALLOWED_QUERY_INTENTS = {
    ("single", "basic_info"),
    ("single", "fund_scale"),
    ("single", "tracking_index"),
    ("single", "performance"),
    ("single", "fee"),
    ("single", "manager"),
    ("single", "fee_and_manager"),
    ("single", "dividend"),
    ("search", "search"),
    ("filter", "filter"),
    ("compare", "compare"),
}


def validate_v3_ast(
    ast: dict[str, Any],
    *,
    query_mode: str,
    entity_hints: dict[str, Any],
    selection_context: dict[str, Any],
    phase: str = "v3.1",
) -> dict[str, Any]:
    normalized = deepcopy(ast)
    _validate_collection(normalized)
    _validate_intent(query_mode, normalized)
    _validate_limit(query_mode, normalized)
    _validate_where(query_mode, normalized, entity_hints, selection_context)
    _validate_order_by(normalized, selection_context)
    _validate_select(normalized, selection_context, phase)
    _validate_answer_fields(normalized, selection_context)
    _ensure_baseline_answer_fields(normalized, selection_context)
    return normalized


def _validate_collection(ast: dict[str, Any]) -> None:
    if ast.get("from") != BASE_COLLECTION:
        raise ValueError(f"unsupported collection: {ast.get('from')}")


def _validate_intent(query_mode: str, ast: dict[str, Any]) -> None:
    intent = ast.get("intent")
    if (query_mode, intent) not in ALLOWED_QUERY_INTENTS:
        raise ValueError(f"unsupported query mode or intent: {query_mode}/{intent}")


def _validate_limit(query_mode: str, ast: dict[str, Any]) -> None:
    limit = ast.get("limit")
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    if query_mode == "compare" and limit > 10:
        raise ValueError("compare limit must be <= 10")


def _validate_where(
    query_mode: str,
    ast: dict[str, Any],
    entity_hints: dict[str, Any],
    selection_context: dict[str, Any],
) -> None:
    where = ast.get("where")
    if not isinstance(where, list):
        raise ValueError("where must be a list")
    for clause in where:
        if not isinstance(clause, dict):
            raise ValueError("where clause must be an object")
        op = clause.get("op")
        if op not in ALLOWED_OPERATORS:
            raise ValueError(f"unsupported operator: {op}")
    if query_mode == "single":
        _validate_single_where(where, entity_hints)
    elif query_mode == "search":
        _validate_search_where(where, entity_hints, selection_context)
    elif query_mode == "filter":
        _validate_filter_where(where, entity_hints, selection_context)
    elif query_mode == "compare":
        _validate_compare_where(where, entity_hints)


def _validate_single_where(where: list[dict[str, Any]], entity_hints: dict[str, Any]) -> None:
    fundcodes = [str(item) for item in entity_hints.get("fundcodes") or [] if item]
    if len(where) != 1 or where[0].get("field") != "fundcode" or where[0].get("op") != "eq":
        raise ValueError("single query requires fundcode eq where")
    if fundcodes and str(where[0].get("value")) != fundcodes[0]:
        raise ValueError("single where must match entity_hints fundcode")


def _validate_search_where(
    where: list[dict[str, Any]],
    entity_hints: dict[str, Any],
    selection_context: dict[str, Any],
) -> None:
    keyword = str(entity_hints.get("search_keyword") or "")
    if len(where) != 1 or where[0] != {"field": "__search_text__", "op": "contains", "value": keyword}:
        raise ValueError("search where must match entity_hints search_keyword")
    if "__search_text__" not in selection_context["filterable_fields"]:
        raise ValueError("search field is not filterable")


def _validate_filter_where(
    where: list[dict[str, Any]],
    entity_hints: dict[str, Any],
    selection_context: dict[str, Any],
) -> None:
    expected = [_strip_raw_value(item) for item in entity_hints.get("filters") or []]
    if where != expected:
        raise ValueError("filter where must match entity_hints filters")
    filterable = set(selection_context["filterable_fields"])
    for clause in where:
        if clause.get("field") not in filterable:
            raise ValueError(f"where contains non-filterable field: {clause.get('field')}")


def _validate_compare_where(where: list[dict[str, Any]], entity_hints: dict[str, Any]) -> None:
    fundcodes = [str(item) for item in entity_hints.get("fundcodes") or [] if item]
    if len(fundcodes) < 2:
        raise ValueError("compare requires at least two fundcodes")
    if len(where) != 1 or where[0].get("field") != "fundcode" or where[0].get("op") != "in":
        raise ValueError("compare query requires fundcode in where")
    if [str(item) for item in where[0].get("value") or []] != fundcodes[:10]:
        raise ValueError("compare where must match entity_hints fundcodes")


def _validate_order_by(ast: dict[str, Any], selection_context: dict[str, Any]) -> None:
    order_by = ast.get("order_by")
    if order_by is None:
        return
    if not isinstance(order_by, dict):
        raise ValueError("order_by must be an object or null")
    if order_by.get("direction") not in {"asc", "desc"}:
        raise ValueError("order_by direction must be asc or desc")
    if order_by.get("field") not in selection_context["sortable_fields"]:
        raise ValueError(f"order_by contains non-sortable field: {order_by.get('field')}")


def _validate_select(ast: dict[str, Any], selection_context: dict[str, Any], phase: str) -> None:
    select = ast.get("select")
    if not isinstance(select, list) or not all(isinstance(field, str) for field in select):
        raise ValueError("select must be a list of field names")
    unsupported = [field for field in select if field not in selection_context["selectable_fields"]]
    blocked = [field for field in unsupported if field in BLOCKED_V3_2_FIELDS]
    if blocked and phase == "v3.1":
        raise ValueError(f"field blocked in v3.1: {blocked[0]}")
    if unsupported:
        raise ValueError(f"select contains unsupported field: {unsupported[0]}")


def _validate_answer_fields(ast: dict[str, Any], selection_context: dict[str, Any]) -> None:
    answer_fields = ast.get("answer_fields")
    if not isinstance(answer_fields, list):
        raise ValueError("answer_fields must be a list")
    selected = set(ast.get("select") or [])
    allowed_formats = set(selection_context["allowed_formats"])
    metas = selection_context["field_metas"]
    for item in answer_fields:
        if not isinstance(item, dict):
            raise ValueError("answer_fields item must be an object")
        field = item.get("field")
        if field not in selected:
            raise ValueError(f"answer field is not selected: {field}")
        meta = metas.get(field, {"label": field, "format": "plain"})
        item.setdefault("label", meta["label"])
        item.setdefault("format", meta["format"])
        if item.get("format", "plain") not in allowed_formats:
            raise ValueError(f"unsupported answer format: {item.get('format')}")


def _ensure_baseline_answer_fields(ast: dict[str, Any], selection_context: dict[str, Any]) -> None:
    selected = set(ast.get("select") or [])
    existing = {item.get("field") for item in ast.get("answer_fields") or [] if isinstance(item, dict)}
    metas = selection_context["field_metas"]
    for field in selection_context["baseline_answer_fields"]:
        if field not in selected:
            ast["select"].append(field)
            selected.add(field)
        if field not in existing:
            meta = metas.get(field, {"label": field, "format": "plain"})
            ast["answer_fields"].append({"field": field, "label": meta["label"], "format": meta["format"]})
            existing.add(field)


def _strip_raw_value(clause: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in clause.items() if key != "raw_value"}
