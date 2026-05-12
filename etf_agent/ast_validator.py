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
V3_3_REQUIRED_KEYS = V3_2_REQUIRED_KEYS | {"ast_schema_version"}
V3_3_OPTIONAL_KEYS = {
    "grammar_fragment_id",
    "compiler_rule_id",
    "profile",
    "performance_rows",
    "timeseries_semantics",
    "report_scope",
    "search_scope",
    "search_keyword",
    "has_explicit_period",
    "limit_source",
}
V3_3_SCHEMA_VERSIONS = {"v3_2_base_ast", "v3_3_structured_query"}
V3_3_PROFILES = {"derived_performance_table", "derived_return_list", "composite_single"}
DERIVED_ALIAS_LABELS = {
    "1w": "近1周收益率",
    "1m": "近1月收益率",
    "3m": "近3月收益率",
    "6m": "近半年收益率",
    "1y": "近1年收益率",
    "2y": "近2年收益率",
    "3y": "近3年收益率",
    "5y": "近5年收益率",
    "ytd": "今年以来收益率",
    "std": "成立以来收益率",
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
    _normalize_report_array_order_by(normalized, expectations)
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


def validate_v3_3_ast_draft(
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

    ast_schema_version = _validate_v3_3_ast_schema_version(normalized)
    has_derived_return_select = any(
        (isinstance(item, dict) and item.get("type") == "derived_return")
        or (isinstance(item, str) and item.startswith("return_"))
        for item in normalized.get("select") or []
    )
    if (
        "profile" not in normalized
        and "performance_rows" not in normalized
        and normalized.get("timeseries_semantics") is None
        and not has_derived_return_select
    ):
        base_draft = {
            key: value
            for key, value in normalized.items()
            if key
            not in {"ast_schema_version", "grammar_fragment_id", "compiler_rule_id", "timeseries_semantics", "report_scope"}
        }
        validation = validate_v3_2_ast_draft(
            base_draft,
            query_mode=query_mode,
            intent=intent,
            generation_bundle=generation_bundle,
        )
        validated_ast = validation["validated_ast"]
        validated_ast["ast_schema_version"] = ast_schema_version
        _apply_v3_3_report_contract(validated_ast, expectations)
        if "timeseries_semantics" in normalized:
            validated_ast["timeseries_semantics"] = normalized["timeseries_semantics"]
        if "grammar_fragment_id" in normalized:
            validated_ast["grammar_fragment_id"] = normalized["grammar_fragment_id"]
        if "compiler_rule_id" in normalized:
            validated_ast["compiler_rule_id"] = normalized["compiler_rule_id"]
        provenance_diff = validation["provenance_diff"]
        provenance_diff["ast_schema_version"] = ast_schema_version
        return {
            "validated_ast": validated_ast,
            "provenance_diff": provenance_diff,
            "validator_applied_defaults": validation["validator_applied_defaults"],
        }

    ast_schema_version, alias_map = _validate_v3_3_shape(normalized)
    if "performance_rows" in normalized and "profile" not in normalized:
        raise ValueError("profile must be present when performance_rows is provided")

    _validate_v3_3_profile(normalized, expectations)
    _validate_v3_3_timeseries_semantics(normalized, selection_context, expectations)
    if normalized.get("profile") == "derived_performance_table" and "performance_rows" not in normalized:
        raise ValueError("performance_rows must be a list")
    _validate_v3_2_capability(normalized, query_mode=query_mode, intent=intent, selection_context=selection_context)
    defaults = _apply_v3_2_defaults(normalized, selection_context, generation_bundle, intent)
    _validate_v3_2_limit(normalized, expectations, generation_bundle["llm_context"]["limit_policy"])
    _validate_v3_3_select(normalized, alias_map, selection_context, expectations)
    _normalize_v3_2_answer_fields(normalized, alias_map)
    _validate_v3_3_answer_fields(normalized, alias_map, selection_context, expectations)
    _validate_v3_2_where(normalized, selection_context, expectations, generation_bundle)
    _normalize_report_array_order_by(normalized, expectations)
    _validate_v3_3_order_by(normalized, selection_context, expectations)
    _validate_v3_2_sub_intents(normalized, expectations)
    if "performance_rows" in normalized:
        _validate_v3_3_performance_rows(normalized, alias_map, expectations)
    _apply_v3_3_report_contract(normalized, expectations)
    provenance_diff = _build_v3_2_provenance_diff(
        draft_before_validation,
        normalized,
        baseline_fields_added=defaults,
        semantic_roles=selection_context["semantic_roles"],
    )
    provenance_diff["ast_schema_version"] = ast_schema_version

    return {
        "validated_ast": normalized,
        "provenance_diff": provenance_diff,
        "validator_applied_defaults": {"baseline_fields_added": defaults},
    }


def _apply_v3_3_report_contract(ast: dict[str, Any], expectations: dict[str, Any]) -> None:
    report_scope = expectations.get("report_scope")
    if not report_scope:
        return
    ast["report_scope"] = report_scope
    expected_expand = expectations.get("expected_expand")
    if expected_expand is not None:
        ast["expand"] = deepcopy(expected_expand)


def _normalize_report_array_order_by(ast: dict[str, Any], expectations: dict[str, Any]) -> None:
    expected_expand = expectations.get("expected_expand")
    if not isinstance(expected_expand, dict):
        return
    order_by = ast.get("order_by")
    expected_order_by = expected_expand.get("order_by")
    if isinstance(order_by, dict) and isinstance(expected_order_by, dict) and order_by == expected_order_by:
        ast["order_by"] = None


def _validate_v3_3_shape(ast: dict[str, Any]) -> tuple[str, dict[str, str]]:
    if not isinstance(ast, dict):
        raise ValueError("LLM Draft AST must be an object")
    missing = V3_3_REQUIRED_KEYS - set(ast)
    if missing:
        raise ValueError(f"LLM Draft AST missing keys: {sorted(missing)}")
    extra = set(ast) - (V3_3_REQUIRED_KEYS | V3_3_OPTIONAL_KEYS)
    if extra:
        raise ValueError(f"LLM Draft AST contains forbidden keys: {sorted(extra)}")
    schema_version = ast.get("ast_schema_version")
    if schema_version not in V3_3_SCHEMA_VERSIONS:
        raise ValueError(f"ast_schema_version must be one of {sorted(V3_3_SCHEMA_VERSIONS)}")
    if schema_version == "v3_2_base_ast" and ({"profile", "performance_rows"} & set(ast)):
        raise ValueError("v3_2_base_ast cannot include v3.3 fragment fields")
    if not isinstance(ast["sub_intents"], list):
        raise ValueError("sub_intents must be a list")
    alias_map = _normalize_v3_3_select(ast)
    if not isinstance(ast["where"], list):
        raise ValueError("where must be a list")
    if not isinstance(ast["answer_fields"], list):
        raise ValueError("answer_fields must be a list")
    if "performance_rows" in ast and not isinstance(ast["performance_rows"], list):
        raise ValueError("performance_rows must be a list")
    if "profile" in ast and ast["profile"] not in V3_3_PROFILES:
        raise ValueError(f"unsupported v3.3 profile: {ast.get('profile')}")
    return schema_version, alias_map


def _validate_v3_3_ast_schema_version(ast: dict[str, Any]) -> str:
    if not isinstance(ast, dict):
        raise ValueError("LLM Draft AST must be an object")
    schema_version = ast.get("ast_schema_version")
    if schema_version not in V3_3_SCHEMA_VERSIONS:
        raise ValueError(f"ast_schema_version must be one of {sorted(V3_3_SCHEMA_VERSIONS)}")
    return schema_version


def _normalize_v3_3_select(ast: dict[str, Any]) -> dict[str, str]:
    raw_select = ast.get("select")
    if not isinstance(raw_select, list):
        raise ValueError("select must be a list")

    normalized: list[str] = []
    alias_map: dict[str, str] = {}
    for item in raw_select:
        if isinstance(item, str):
            _reject_legacy_yield_field(item)
            normalized.append(item)
            continue
        if isinstance(item, dict):
            alias = item.get("alias")
            item_type = item.get("type")
            period = item.get("period")
            if item_type != "derived_return" or not isinstance(alias, str) or not alias:
                raise ValueError("v3.3 derived select items must declare alias/type/period")
            if not isinstance(period, str) or not period:
                raise ValueError("v3.3 derived select item missing period")
            alias_map[alias] = alias
            normalized.append(alias)
            continue
        raise ValueError("select must contain field names or derived alias objects")

    ast["select"] = list(dict.fromkeys(normalized))
    return alias_map


def _validate_v3_3_profile(ast: dict[str, Any], expectations: dict[str, Any]) -> None:
    if "profile" not in ast:
        return
    allowed = set((expectations.get("v3_3") or {}).get("allowed_profiles") or [])
    if allowed and ast["profile"] not in allowed:
        raise ValueError(f"profile not allowed for user evidence: {ast['profile']}")


def _validate_v3_3_select(
    ast: dict[str, Any],
    alias_map: dict[str, str],
    selection_context: dict[str, Any],
    expectations: dict[str, Any],
) -> None:
    allowed = set(selection_context["selectable_fields"]) | set(alias_map)
    for field in ast["select"]:
        _reject_legacy_yield_field(field)
        if field not in allowed:
            raise ValueError(f"select contains unsupported field: {field}")
    labels = expectations.get("semantic_field_labels") or {}
    for field in expectations.get("required_select_fields") or []:
        if field not in ast["select"]:
            label = labels.get(field, field)
            raise ValueError(f"missing requested semantic field: {label}")
    required_aliases = (expectations.get("v3_3") or {}).get("required_derived_aliases") or []
    for alias in required_aliases:
        if alias not in alias_map and alias not in ast["select"]:
            raise ValueError(f"missing requested derived alias: {alias}")


def _validate_v3_3_answer_fields(
    ast: dict[str, Any],
    alias_map: dict[str, str],
    selection_context: dict[str, Any],
    expectations: dict[str, Any],
) -> None:
    selected = set(ast["select"])
    allowed_formats = set(selection_context["allowed_formats"])
    field_metas = selection_context["field_metas"]
    answer_field_names = set()
    for item in ast["answer_fields"]:
        if not isinstance(item, dict):
            raise ValueError("answer_fields item must be an object")
        field = item.get("field")
        _reject_legacy_yield_field(field)
        if field not in selected:
            raise ValueError(f"answer field is not selected: {field}")
        if field in alias_map:
            item.setdefault("label", _derived_alias_label(field))
            item.setdefault("format", "percent")
            if item.get("source") != "derived":
                raise ValueError(f"derived answer field must use source=derived: {field}")
        else:
            item.setdefault("label", field_metas.get(field, {"label": field})["label"])
            item.setdefault("format", field_metas.get(field, {"format": "plain"})["format"])
            if item.get("source") == "derived":
                raise ValueError(f"non-derived answer field cannot use source=derived: {field}")
        if item.get("format") not in allowed_formats:
            raise ValueError(f"unsupported answer format: {item.get('format')}")
        answer_field_names.add(field)
    required_answer_fields = expectations.get("required_answer_fields") or expectations.get("required_select_fields") or []
    for field in required_answer_fields:
        if field not in answer_field_names:
            label = (expectations.get("semantic_field_labels") or {}).get(field, field)
            raise ValueError(f"missing requested semantic answer field: {label}")


def _derived_alias_label(alias: str) -> str:
    if not isinstance(alias, str) or not alias.startswith("return_"):
        return alias
    period = alias.removeprefix("return_")
    return DERIVED_ALIAS_LABELS.get(period, alias)


def _validate_v3_3_order_by(ast: dict[str, Any], selection_context: dict[str, Any], expectations: dict[str, Any]) -> None:
    order_by = ast.get("order_by")
    if isinstance(order_by, list) and len(order_by) == 1 and isinstance(order_by[0], dict):
        order_by = order_by[0]
        ast["order_by"] = order_by
    if order_by is None:
        return
    if not isinstance(order_by, dict):
        raise ValueError("order_by must be an object or null")
    field = order_by.get("field")
    _reject_legacy_yield_field(field)
    if order_by.get("direction") not in {"asc", "desc"}:
        raise ValueError("order_by direction must be asc or desc")
    if field not in set(selection_context["sortable_fields"]) | set((expectations.get("v3_3") or {}).get("required_derived_aliases") or []):
        raise ValueError(f"order_by contains non-sortable field: {field}")


def _validate_v3_3_performance_rows(ast: dict[str, Any], alias_map: dict[str, str], expectations: dict[str, Any]) -> None:
    aliases = set(alias_map)
    row_aliases = []
    for row in ast["performance_rows"]:
        if not isinstance(row, dict):
            raise ValueError("performance_rows item must be an object")
        alias = row.get("alias")
        if alias not in aliases:
            raise ValueError(f"performance row alias is not declared: {alias}")
        row_aliases.append(alias)
    required_rows = (expectations.get("v3_3") or {}).get("required_performance_rows") or []
    for alias in required_rows:
        if alias not in row_aliases:
            raise ValueError(f"missing requested performance row: {alias}")


def _validate_v3_3_timeseries_semantics(
    ast: dict[str, Any],
    selection_context: dict[str, Any],
    expectations: dict[str, Any],
) -> None:
    expected = expectations.get("expected_timeseries_modes") or {}
    timeseries = ast.get("timeseries_semantics")
    if timeseries is None:
        if expected:
            raise ValueError("missing requested timeseries_semantics")
        return
    if not isinstance(timeseries, dict):
        raise ValueError("timeseries_semantics must be an object or null")
    by_field = timeseries.get("by_field")
    if not isinstance(by_field, dict):
        raise ValueError("timeseries_semantics.by_field must be an object")
    allowed_fields = set(selection_context["selectable_fields"]) | set(selection_context["sortable_fields"])
    normalized_by_field: dict[str, dict[str, Any]] = {}
    for field, spec in by_field.items():
        if field not in allowed_fields:
            raise ValueError(f"timeseries_semantics contains unsupported field: {field}")
        if isinstance(spec, str):
            spec = {"mode": spec}
        if not isinstance(spec, dict):
            raise ValueError("timeseries_semantics entries must be objects")
        normalized_spec = dict(spec)
        mode = normalized_spec.get("mode")
        if mode not in {"latest", "latest_two", "specified"}:
            raise ValueError(f"unsupported timeseries mode: {mode}")
        if mode == "specified" and not isinstance(normalized_spec.get("btime"), str):
            raise ValueError("specified timeseries mode requires btime")
        expected_spec = expected.get(field)
        if expected_spec is not None:
            if mode != expected_spec.get("mode"):
                raise ValueError(f"timeseries mode mismatch for {field}")
            if expected_spec.get("mode") == "specified" and spec.get("btime") != expected_spec.get("btime"):
                raise ValueError(f"timeseries btime mismatch for {field}")
        normalized_by_field[field] = normalized_spec
    for field, expected_spec in expected.items():
        if field not in by_field:
            raise ValueError(f"missing requested timeseries field: {field}")
    timeseries["by_field"] = normalized_by_field


def _reject_legacy_yield_field(field: Any) -> None:
    if isinstance(field, str) and field.startswith("ths_yeild_") and "_rank_" not in field:
        raise ValueError(f"legacy yield field is not allowed in v3.3 derived performance: {field}")


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
        "timeseries_semantics": ast.get("timeseries_semantics"),
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
        if isinstance(field, str) and field.startswith("return_"):
            continue
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
