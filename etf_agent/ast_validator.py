from __future__ import annotations

from copy import deepcopy
from typing import Any

from .capability_registry import BASE_COLLECTION, BLOCKED_V3_2_FIELDS


ALLOWED_OPERATORS = {"eq", "in", "contains", "gt", "gte", "lt", "lte"}
V3_2_REQUIRED_KEYS = {
    "intent",
    "sub_intents",
    "from",
    "select",
    "where",
    "order_by",
    "limit",
    "output_style",
    "answer_fields",
    "report_period",
    "expand",
}
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


def validate_v3_2_ast_draft(
    draft_ast: dict[str, Any],
    *,
    query_mode: str,
    intent: str,
    generation_bundle: dict[str, Any],
) -> dict[str, Any]:
    selection_context = generation_bundle["selection_context"]
    expectations = generation_bundle["validator_expectations"]
    draft_before_validation = deepcopy(draft_ast)
    normalized = deepcopy(draft_ast)

    alias_map = _validate_v3_2_shape(normalized)
    _validate_v3_2_capability(normalized, query_mode=query_mode, intent=intent, selection_context=selection_context)
    defaults = _apply_v3_2_defaults(normalized, selection_context, generation_bundle, intent)
    _validate_v3_2_limit(normalized, expectations, generation_bundle["llm_context"]["limit_policy"])
    _validate_v3_2_select(normalized, selection_context, expectations)
    _normalize_v3_2_answer_fields(normalized, alias_map)
    _validate_v3_2_answer_fields(normalized, selection_context, expectations)
    _validate_v3_2_where(normalized, selection_context, expectations, generation_bundle)
    _validate_v3_2_order_by(normalized, selection_context, expectations)
    _validate_v3_2_sub_intents(normalized, expectations)
    provenance_diff = _build_v3_2_provenance_diff(
        draft_before_validation,
        normalized,
        baseline_fields_added=defaults,
        semantic_roles=selection_context["semantic_roles"],
    )

    return {
        "validated_ast": normalized,
        "provenance_diff": provenance_diff,
        "validator_applied_defaults": {"baseline_fields_added": defaults},
    }


def _build_v3_2_provenance_diff(
    draft_ast: dict[str, Any],
    validated_ast: dict[str, Any],
    *,
    baseline_fields_added: list[str],
    semantic_roles: dict[str, str],
) -> dict[str, Any]:
    validator_additions_by_kind = {"identity": [], "context": [], "display": [], "semantic": []}
    for field in baseline_fields_added:
        role = semantic_roles.get(field, "semantic")
        if role not in validator_additions_by_kind:
            role = "semantic"
        validator_additions_by_kind[role].append(field)

    semantic_additions = [
        {"kind": "select", "field": field}
        for field in validator_additions_by_kind["semantic"]
    ]
    semantic_overrides: list[dict[str, Any]] = []
    return {
        "draft_semantics": _v3_2_semantic_fingerprint(draft_ast),
        "validated_semantics": _v3_2_semantic_fingerprint(validated_ast),
        "compiler_expansions": [],
        "validator_additions_by_kind": validator_additions_by_kind,
        "semantic_additions": semantic_additions,
        "semantic_overrides": semantic_overrides,
        "strict_pass": not semantic_additions and not semantic_overrides,
    }


def _v3_2_semantic_fingerprint(ast: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent": ast.get("intent"),
        "sub_intents": ast.get("sub_intents"),
        "from": ast.get("from"),
        "select": ast.get("select"),
        "where": ast.get("where"),
        "order_by": ast.get("order_by"),
        "limit": ast.get("limit"),
        "answer_fields": [item.get("field") for item in ast.get("answer_fields") or [] if isinstance(item, dict)],
        "report_period": ast.get("report_period"),
        "expand": ast.get("expand"),
    }


def _validate_v3_2_shape(ast: dict[str, Any]) -> dict[str, str]:
    if not isinstance(ast, dict):
        raise ValueError("LLM Draft AST must be an object")
    missing = V3_2_REQUIRED_KEYS - set(ast)
    if missing:
        raise ValueError(f"LLM Draft AST missing keys: {sorted(missing)}")
    extra = set(ast) - V3_2_REQUIRED_KEYS
    if extra:
        raise ValueError(f"LLM Draft AST contains forbidden keys: {sorted(extra)}")
    if not isinstance(ast["sub_intents"], list):
        raise ValueError("sub_intents must be a list")
    alias_map = _normalize_v3_2_select(ast)
    if not isinstance(ast["where"], list):
        raise ValueError("where must be a list")
    if not isinstance(ast["answer_fields"], list):
        raise ValueError("answer_fields must be a list")
    return alias_map


def _validate_v3_2_capability(
    ast: dict[str, Any],
    *,
    query_mode: str,
    intent: str,
    selection_context: dict[str, Any],
) -> None:
    if ast["intent"] != intent:
        raise ValueError(f"LLM Draft intent mismatch: expected {intent}, got {ast['intent']}")
    if ast["from"] != selection_context["collection"]:
        raise ValueError(f"unsupported collection: {ast['from']}")
    if ast["output_style"] != selection_context["output_style"]:
        raise ValueError(f"output_style mismatch for {query_mode}/{intent}")


def _validate_v3_2_limit(ast: dict[str, Any], expectations: dict[str, Any], limit_policy: dict[str, int]) -> None:
    limit = ast.get("limit")
    expected = expectations.get("expected_limit")
    if limit is None and expected is None:
        ast["limit"] = int(limit_policy["default"])
        return
    if not isinstance(limit, int) or not 1 <= limit <= int(limit_policy["max"]):
        raise ValueError(f"limit must be between 1 and {limit_policy['max']}")
    if expected is not None:
        expected_limit = min(int(expected), int(limit_policy["max"]))
        if expected_limit == int(limit_policy["max"]) and limit <= expected_limit:
            ast["limit"] = expected_limit
            return
        if limit != expected_limit:
            raise ValueError("user requested limit is not preserved in LLM Draft AST")


def _validate_v3_2_select(ast: dict[str, Any], selection_context: dict[str, Any], expectations: dict[str, Any]) -> None:
    allowed = set(selection_context["selectable_fields"])
    selected = set(ast["select"])
    unsupported = [field for field in ast["select"] if field not in allowed]
    if unsupported:
        raise ValueError(f"select contains unsupported field: {unsupported[0]}")
    labels = expectations.get("semantic_field_labels") or {}
    for field in expectations.get("required_select_fields") or []:
        if field not in selected:
            label = labels.get(field, field)
            raise ValueError(f"missing requested semantic field: {label}")


def _normalize_v3_2_select(ast: dict[str, Any]) -> dict[str, str]:
    raw_select = ast.get("select")
    if not isinstance(raw_select, list):
        raise ValueError("select must be a field-name list")

    normalized: list[str] = []
    alias_map: dict[str, str] = {}
    for item in raw_select:
        if isinstance(item, str):
            normalized.append(item)
            continue
        if isinstance(item, dict):
            field = item.get("field")
            if not isinstance(field, str) or not field:
                raise ValueError("select must be a field-name list")
            normalized.append(field)
            alias = item.get("alias")
            if isinstance(alias, str) and alias:
                alias_map[alias] = field
            continue
        raise ValueError("select must be a field-name list")

    ast["select"] = list(dict.fromkeys(normalized))
    return alias_map


def _normalize_v3_2_answer_fields(ast: dict[str, Any], alias_map: dict[str, str]) -> None:
    normalized: list[dict[str, Any]] = []
    for item in ast["answer_fields"]:
        if isinstance(item, str):
            item = {"field": item}
        if not isinstance(item, dict):
            raise ValueError("answer_fields item must be an object")
        field = item.get("field")
        if isinstance(field, str) and field in alias_map:
            item = {**item, "field": alias_map[field]}
        normalized.append(item)
    ast["answer_fields"] = normalized


def _validate_v3_2_answer_fields(ast: dict[str, Any], selection_context: dict[str, Any], expectations: dict[str, Any]) -> None:
    selected = set(ast["select"])
    allowed_formats = set(selection_context["allowed_formats"])
    field_metas = selection_context["field_metas"]
    answer_field_names = set()
    for item in ast["answer_fields"]:
        if not isinstance(item, dict):
            raise ValueError("answer_fields item must be an object")
        field = item.get("field")
        if field not in selected:
            raise ValueError(f"answer field is not selected: {field}")
        item.setdefault("label", field_metas.get(field, {"label": field})["label"])
        item.setdefault("format", field_metas.get(field, {"format": "plain"})["format"])
        if item.get("format") not in allowed_formats:
            raise ValueError(f"unsupported answer format: {item.get('format')}")
        answer_field_names.add(field)
    labels = expectations.get("semantic_field_labels") or {}
    for field in expectations.get("required_select_fields") or []:
        if field not in answer_field_names:
            label = labels.get(field, field)
            raise ValueError(f"missing requested semantic answer field: {label}")


def _validate_v3_2_where(
    ast: dict[str, Any],
    selection_context: dict[str, Any],
    expectations: dict[str, Any],
    generation_bundle: dict[str, Any],
) -> None:
    field_operators = selection_context["field_operators"]
    expected = [deepcopy(clause) for clause in expectations.get("expected_where") or []]
    normalized_where = _normalize_v3_2_where(ast["where"], expected, generation_bundle)
    for clause in normalized_where:
        field = clause.get("field")
        op = clause.get("op")
        if field not in field_operators:
            raise ValueError(f"where contains non-filterable field: {field}")
        if op not in field_operators[field]:
            raise ValueError(f"unsupported operator for {field}: {op}")
    if expected and normalized_where != expected:
        raise ValueError("LLM Draft where does not match extracted user evidence")
    if not expected and normalized_where:
        raise ValueError("LLM Draft where is not supported by user evidence")
    ast["where"] = normalized_where


def _validate_v3_2_order_by(ast: dict[str, Any], selection_context: dict[str, Any], expectations: dict[str, Any]) -> None:
    order_by = ast.get("order_by")
    if isinstance(order_by, list) and len(order_by) == 1 and isinstance(order_by[0], dict):
        order_by = order_by[0]
        ast["order_by"] = order_by
    expected = expectations.get("expected_order_by")
    if order_by is None:
        if expected is not None:
            raise ValueError("missing requested order_by in LLM Draft AST")
        return
    if not isinstance(order_by, dict):
        raise ValueError("order_by must be an object or null")
    if order_by.get("direction") not in {"asc", "desc"}:
        raise ValueError("order_by direction must be asc or desc")
    if order_by.get("field") not in selection_context["sortable_fields"]:
        raise ValueError(f"order_by contains non-sortable field: {order_by.get('field')}")
    if expected is None:
        raise ValueError("LLM Draft order_by is not supported by user evidence")
    if order_by != expected:
        raise ValueError("LLM Draft order_by does not match user evidence")


def _validate_v3_2_sub_intents(ast: dict[str, Any], expectations: dict[str, Any]) -> None:
    expected = expectations.get("expected_sub_intents") or []
    if not expected:
        return
    sub_intents = ast.get("sub_intents")
    if not isinstance(sub_intents, list):
        raise ValueError("sub_intents must be a list")
    if not sub_intents:
        raise ValueError("missing requested sub_intents in LLM Draft AST")
    if list(dict.fromkeys(sub_intents)) != list(dict.fromkeys(expected)):
        raise ValueError("LLM Draft sub_intents does not match user evidence")


def _apply_identity_context_defaults(ast: dict[str, Any], selection_context: dict[str, Any]) -> list[str]:
    return _apply_v3_2_defaults(ast, selection_context, {"llm_context": {"llm_draft_evidence": {}}}, ast.get("intent", ""))


def _apply_v3_2_defaults(
    ast: dict[str, Any],
    selection_context: dict[str, Any],
    generation_bundle: dict[str, Any],
    intent: str,
) -> list[str]:
    added: list[str] = []
    selected = set(ast["select"])
    answer_field_names = {item.get("field") for item in ast["answer_fields"] if isinstance(item, dict)}
    metas = selection_context["field_metas"]
    required_default_fields = list(dict.fromkeys(selection_context["baseline_answer_fields"]))
    required_default_fields.extend(generation_bundle.get("validator_expectations", {}).get("display_default_fields", []))
    required_default_fields = list(dict.fromkeys(required_default_fields))
    for field in required_default_fields:
        if selection_context["semantic_roles"].get(field, "semantic") == "semantic":
            continue
        if field not in selection_context["selectable_fields"]:
            continue
        if field not in selected:
            ast["select"].append(field)
            selected.add(field)
            added.append(field)
        if field not in answer_field_names:
            meta = metas.get(field, {"label": field, "format": "plain"})
            ast["answer_fields"].append({"field": field, "label": meta["label"], "format": meta["format"]})
            answer_field_names.add(field)
    for field in ast["select"]:
        if field not in answer_field_names:
            meta = metas.get(field, {"label": field, "format": "plain"})
            ast["answer_fields"].append({"field": field, "label": meta["label"], "format": meta["format"]})
            answer_field_names.add(field)
    return added


def _normalize_where_clause(clause: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(clause, dict):
        raise ValueError("where clause must be an object")
    return dict(clause)


def _normalize_v3_2_where(
    actual_where: list[dict[str, Any]],
    expected_where: list[dict[str, Any]],
    generation_bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    expected_index = 0
    date_evidence = generation_bundle["llm_context"].get("llm_draft_evidence", {}).get("date_evidence") or []
    date_raw_value = date_evidence[0]["raw"] if date_evidence else None

    for clause in actual_where:
        clause = _normalize_where_clause(clause)
        expected = expected_where[expected_index] if expected_index < len(expected_where) else None

        if clause.get("op") == "between":
            normalized.extend(_expand_between_where_clause(clause, expected, date_raw_value))
            if expected is not None and expected.get("field") == clause.get("field"):
                if (
                    expected_index + 1 < len(expected_where)
                    and expected_where[expected_index + 1].get("field") == clause.get("field")
                ):
                    expected_index += 2
                else:
                    expected_index += 1
            else:
                expected_index += 1
            continue

        if expected is not None:
            clause = _normalize_clause_against_expected(clause, expected)
            expected_index += 1

        normalized.append(clause)

    return normalized


def _expand_between_where_clause(
    clause: dict[str, Any],
    expected: dict[str, Any] | None,
    date_raw_value: str | None,
) -> list[dict[str, Any]]:
    value = clause.get("value")
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("between operator requires a two-item value list")

    raw_value = None
    if expected is not None:
        raw_value = expected.get("raw_value")
    if raw_value is None:
        raw_value = date_raw_value

    normalized = [
        {"field": clause["field"], "op": "gte", "value": value[0]},
        {"field": clause["field"], "op": "lte", "value": value[1]},
    ]
    if raw_value is not None:
        normalized[0]["raw_value"] = raw_value
        normalized[1]["raw_value"] = raw_value
    return normalized


def _normalize_clause_against_expected(
    clause: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(clause)
    expected_raw = expected.get("raw_value")
    if expected_raw is not None:
        if normalized.get("value") == expected_raw:
            normalized["value"] = expected["value"]
            normalized["raw_value"] = expected_raw
        elif normalized.get("value") == expected.get("value"):
            normalized["raw_value"] = expected_raw
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
