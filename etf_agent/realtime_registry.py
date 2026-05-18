from __future__ import annotations

from copy import deepcopy
from typing import Any


REQUIRED_TOP_LEVEL_KEYS = {
    "intent_to_scenario_matrix",
    "scenario_to_fields_matrix",
    "field_display_matrix",
    "scenario_metadata",
    "field_metadata",
    "unsupported_field_policy",
    "alias_rules",
    "role_rules",
    "scenario_field_support_matrix",
    "explicit_field_injection_rules",
    "terminal_outcome_matrix",
    "composition_rules",
    "default_overview",
    "source_field_mappings",
    "source_capabilities",
    "derivation_rules",
    "normalization_rules",
}

FORMAT_KINDS = {"plain_text", "plain_number", "percent", "scaled_number"}
PRECISION_MODES = {"none", "fixed_fraction_digits", "max_fraction_digits"}
SIGN_POLICIES = {"auto", "always", "never"}
SCALE_POLICIES = {"none", "divide", "ratio_to_percent"}
UNIT_POLICIES = {"none", "literal", "suffix_percent"}
NULL_POLICIES = {"display_placeholder"}
ZERO_POLICIES = {"allow"}
MATCH_KINDS = {"exact_phrase", "contains_phrase"}
EMIT_MODES = {"single", "field", "terminal_outcome"}


def get_realtime_registry() -> dict[str, Any]:
    return deepcopy(REALTIME_REGISTRY)


def validate_realtime_registry(registry: dict[str, Any]) -> None:
    missing = REQUIRED_TOP_LEVEL_KEYS - set(registry)
    if missing:
        raise ValueError(f"realtime_registry missing top-level keys: {sorted(missing)}")

    scenarios = set(registry["intent_to_scenario_matrix"])
    fields = set(registry["field_metadata"])
    outcomes = set(registry["terminal_outcome_matrix"].values())

    for scenario, row in registry["intent_to_scenario_matrix"].items():
        if row.get("match_mode") != "rule_based":
            raise ValueError(f"unsupported match_mode for scenario {scenario}: {row.get('match_mode')}")
        unknown = set(row.get("allowed_cooccurrence") or []) - scenarios
        if unknown:
            raise ValueError(f"scenario {scenario} references unknown cooccurrence scenarios: {sorted(unknown)}")

    for scenario, scenario_fields in registry["scenario_to_fields_matrix"].items():
        _require_known_scenario(scenario, scenarios)
        _require_known_fields(scenario_fields, fields, f"scenario_to_fields_matrix.{scenario}")

    for scenario, support in registry["scenario_field_support_matrix"].items():
        _require_known_scenario(scenario, scenarios)
        _require_known_fields(support.get("explicitly_allowed_fields") or [], fields, f"scenario_field_support_matrix.{scenario}")
        _require_known_fields(support.get("explicitly_denied_fields") or [], fields, f"scenario_field_support_matrix.{scenario}")

    for field, rule in registry["explicit_field_injection_rules"].items():
        _require_known_field(field, fields)
        unknown = set(rule.get("default_scenarios") or []) - scenarios
        if unknown:
            raise ValueError(f"field {field} references unknown default scenarios: {sorted(unknown)}")

    for field in fields:
        if field not in registry["field_display_matrix"]:
            raise ValueError(f"field {field} has no display rule")
        if field not in registry["source_field_mappings"]:
            raise ValueError(f"field {field} has no source mapping")
        _validate_display_rule(field, registry["field_display_matrix"][field])

    normalization_ids = {rule["rule_id"] for rule in registry["normalization_rules"].get("rules") or []}
    for field, meta in registry["field_metadata"].items():
        if meta.get("normalization_rule_id") not in normalization_ids:
            raise ValueError(f"field {field} references unknown normalization rule")

    for rule in registry["alias_rules"].get("rules") or []:
        if rule.get("match_kind") not in MATCH_KINDS:
            raise ValueError(f"unknown alias match_kind: {rule.get('match_kind')}")
        if rule.get("emit_mode") not in EMIT_MODES:
            raise ValueError(f"unknown alias emit_mode: {rule.get('emit_mode')}")
        canonical_id = rule.get("canonical_id")
        if rule["emit_mode"] == "single":
            _require_known_scenario(canonical_id, scenarios)
        elif rule["emit_mode"] == "field":
            _require_known_field(canonical_id, fields)
        elif canonical_id not in outcomes:
            raise ValueError(f"alias references unknown terminal outcome: {canonical_id}")


def _validate_display_rule(field: str, rule: dict[str, Any]) -> None:
    required = {
        "label",
        "format_kind",
        "precision_mode",
        "precision_value",
        "sign_policy",
        "scale_policy",
        "unit_policy",
        "null_policy",
        "zero_policy",
    }
    missing = required - set(rule)
    if missing:
        raise ValueError(f"display rule for {field} missing keys: {sorted(missing)}")
    _require_enum(rule, "format_kind", FORMAT_KINDS)
    _require_enum(rule, "precision_mode", PRECISION_MODES)
    _require_enum(rule, "sign_policy", SIGN_POLICIES)
    _require_enum(rule, "scale_policy", SCALE_POLICIES)
    _require_enum(rule, "unit_policy", UNIT_POLICIES)
    _require_enum(rule, "null_policy", NULL_POLICIES)
    _require_enum(rule, "zero_policy", ZERO_POLICIES)


def _require_enum(row: dict[str, Any], key: str, allowed: set[str]) -> None:
    value = row.get(key)
    if value not in allowed:
        raise ValueError(f"unknown {key}: {value}")


def _require_known_scenario(scenario: str, scenarios: set[str]) -> None:
    if scenario not in scenarios:
        raise ValueError(f"unknown scenario: {scenario}")


def _require_known_field(field: str, fields: set[str]) -> None:
    if field not in fields:
        raise ValueError(f"unknown field: {field}")


def _require_known_fields(values: list[str], fields: set[str], path: str) -> None:
    unknown = set(values) - fields
    if unknown:
        raise ValueError(f"{path} references unknown fields: {sorted(unknown)}")


def _display(
    label: str,
    *,
    format_kind: str = "plain_number",
    precision_mode: str = "max_fraction_digits",
    precision_value: int = 4,
    sign_policy: str = "auto",
    scale_policy: str = "none",
    scale_value: float | None = None,
    unit_policy: str = "none",
    unit_value: str | None = None,
) -> dict[str, Any]:
    row = {
        "label": label,
        "format_kind": format_kind,
        "precision_mode": precision_mode,
        "precision_value": precision_value,
        "sign_policy": sign_policy,
        "scale_policy": scale_policy,
        "unit_policy": unit_policy,
        "null_policy": "display_placeholder",
        "zero_policy": "allow",
    }
    if scale_value is not None:
        row["scale_value"] = scale_value
    if unit_value is not None:
        row["unit_value"] = unit_value
    return row


def _field(label: str, value_type: str, source_mapping_id: str) -> dict[str, Any]:
    return {
        "exposed": True,
        "value_type": value_type,
        "canonical_unit": "raw",
        "source_mapping_id": source_mapping_id,
        "normalization_rule_id": "default_numeric_passthrough",
        "derivation_rule_id": None,
        "freshness_policy": "accept_latest_available",
    }


REALTIME_FIELDS = (
    "tradeDate",
    "tradeTime",
    "preClose",
    "open",
    "high",
    "low",
    "latest",
    "change",
    "changeRatio",
    "swing",
    "amount",
    "volume",
    "latestVolume",
    "sellVolume",
    "buyVolume",
    "iopv",
    "premium",
    "bid1",
    "ask1",
    "bidSize1",
    "askSize1",
)


REALTIME_REGISTRY: dict[str, Any] = {
    "intent_to_scenario_matrix": {
        "overview": {
            "enabled": True,
            "match_mode": "rule_based",
            "must_have": [],
            "any_of": ["实时行情", "现在行情", "现在什么情况", "今天表现如何", "怎么样"],
            "forbid": [],
            "priority": 100,
            "multi_match_policy": "merge",
            "allowed_cooccurrence": ["default_overview", "price_change", "trading", "valuation", "order_book", "trade_flow"],
        },
        "default_overview": {
            "enabled": False,
            "match_mode": "rule_based",
            "must_have": [],
            "any_of": [],
            "forbid": [],
            "priority": 95,
            "multi_match_policy": "merge",
            "allowed_cooccurrence": ["overview", "compare_overview", "price_change", "trading", "valuation", "order_book", "trade_flow"],
        },
        "compare_overview": {
            "enabled": False,
            "match_mode": "rule_based",
            "must_have": [],
            "any_of": [],
            "forbid": [],
            "priority": 94,
            "multi_match_policy": "merge",
            "allowed_cooccurrence": ["overview", "default_overview", "price_change", "trading", "valuation", "order_book", "trade_flow"],
        },
        "price_change": {
            "enabled": True,
            "match_mode": "rule_based",
            "must_have": [],
            "any_of": ["现在什么价", "什么价", "价格多少", "价格", "报多少", "多少钱", "涨了吗", "涨了没", "跌了多少", "涨跌幅"],
            "forbid": [],
            "priority": 90,
            "multi_match_policy": "merge",
            "allowed_cooccurrence": ["overview", "default_overview", "trading", "valuation", "order_book", "trade_flow"],
        },
        "trading": {
            "enabled": True,
            "match_mode": "rule_based",
            "must_have": [],
            "any_of": ["成交额", "成交量", "现手"],
            "forbid": [],
            "priority": 80,
            "multi_match_policy": "merge",
            "allowed_cooccurrence": ["overview", "default_overview", "price_change", "valuation", "order_book", "trade_flow"],
        },
        "valuation": {
            "enabled": True,
            "match_mode": "rule_based",
            "must_have": [],
            "any_of": ["溢价", "折价", "折溢价", "IOPV", "iopv"],
            "forbid": [],
            "priority": 70,
            "multi_match_policy": "merge",
            "allowed_cooccurrence": ["overview", "default_overview", "price_change", "trading", "order_book", "trade_flow"],
        },
        "order_book": {
            "enabled": True,
            "match_mode": "rule_based",
            "must_have": [],
            "any_of": ["盘口", "买一", "卖一", "买1", "卖1", "挂单"],
            "forbid": [],
            "priority": 60,
            "multi_match_policy": "merge",
            "allowed_cooccurrence": ["overview", "default_overview", "price_change", "trading", "valuation", "trade_flow"],
        },
        "trade_flow": {
            "enabled": True,
            "match_mode": "rule_based",
            "must_have": [],
            "any_of": ["内外盘", "外盘", "内盘"],
            "forbid": [],
            "priority": 50,
            "multi_match_policy": "merge",
            "allowed_cooccurrence": ["overview", "default_overview", "price_change", "trading", "valuation", "order_book"],
        },
    },
    "scenario_to_fields_matrix": {
        "overview": ["preClose", "latest", "change", "changeRatio", "open", "high", "low", "amount", "volume", "iopv", "premium", "tradeTime"],
        "default_overview": ["latest", "change", "changeRatio", "amount", "tradeTime"],
        "compare_overview": ["latest", "changeRatio", "amount", "premium", "tradeTime"],
        "price_change": ["latest", "change", "changeRatio", "tradeTime"],
        "trading": ["amount", "volume", "latestVolume", "tradeTime"],
        "valuation": ["latest", "iopv", "premium", "tradeTime"],
        "order_book": ["bid1", "ask1", "bidSize1", "askSize1", "tradeTime"],
        "trade_flow": ["sellVolume", "buyVolume", "latestVolume", "tradeTime"],
    },
    "field_display_matrix": {
        "tradeDate": _display("交易日期", format_kind="plain_text", precision_mode="none", precision_value=0, sign_policy="never"),
        "tradeTime": _display("交易时间", format_kind="plain_text", precision_mode="none", precision_value=0, sign_policy="never"),
        "preClose": _display("前收盘价"),
        "open": _display("开盘价"),
        "high": _display("最高价"),
        "low": _display("最低价"),
        "latest": _display("最新价"),
        "change": _display("涨跌", sign_policy="always"),
        "changeRatio": _display("涨跌幅", format_kind="percent", precision_mode="fixed_fraction_digits", precision_value=2, sign_policy="always", scale_policy="ratio_to_percent", unit_policy="suffix_percent"),
        "swing": _display("振幅", format_kind="percent", precision_mode="fixed_fraction_digits", precision_value=2, scale_policy="ratio_to_percent", unit_policy="suffix_percent"),
        "amount": _display("成交额", format_kind="scaled_number", precision_mode="fixed_fraction_digits", precision_value=2, scale_policy="divide", scale_value=100000000, unit_policy="literal", unit_value="亿元"),
        "volume": _display("成交量", format_kind="scaled_number", precision_mode="fixed_fraction_digits", precision_value=2, scale_policy="divide", scale_value=10000, unit_policy="literal", unit_value="万手"),
        "latestVolume": _display("现手", precision_mode="none", precision_value=0),
        "sellVolume": _display("内盘", format_kind="scaled_number", precision_mode="fixed_fraction_digits", precision_value=2, scale_policy="divide", scale_value=10000, unit_policy="literal", unit_value="万手"),
        "buyVolume": _display("外盘", format_kind="scaled_number", precision_mode="fixed_fraction_digits", precision_value=2, scale_policy="divide", scale_value=10000, unit_policy="literal", unit_value="万手"),
        "iopv": _display("IOPV"),
        "premium": _display("折溢价率", format_kind="percent", precision_mode="fixed_fraction_digits", precision_value=2, sign_policy="always", scale_policy="ratio_to_percent", unit_policy="suffix_percent"),
        "bid1": _display("买一价"),
        "ask1": _display("卖一价"),
        "bidSize1": _display("买一量", precision_mode="none", precision_value=0),
        "askSize1": _display("卖一量", precision_mode="none", precision_value=0),
    },
    "scenario_metadata": {
        "overview": {"card_group": "overview"},
        "default_overview": {"card_group": "overview"},
        "compare_overview": {"card_group": "compare"},
        "price_change": {"card_group": "price_change"},
        "trading": {"card_group": "trading"},
        "valuation": {"card_group": "valuation"},
        "order_book": {"card_group": "order_book"},
        "trade_flow": {"card_group": "trade_flow"},
    },
    "field_metadata": {field: _field(field, "text" if field in {"tradeDate", "tradeTime"} else "number", field) for field in REALTIME_FIELDS},
    "unsupported_field_policy": {
        "default_action_by_origin": {"default": "drop_field", "explicit": "reject_request", "derived": "reject_request"},
        "default_error_code": "field_not_supported",
    },
    "alias_rules": {
        "rules": [
            {"scope": "terminal", "match_kind": "contains_phrase", "pattern": "五档盘口", "canonical_id": "field_not_supported", "priority": 300, "rewrite_mode": "none", "emit_mode": "terminal_outcome", "collision_policy": "highest_priority_wins"},
            {"scope": "terminal", "match_kind": "contains_phrase", "pattern": "贵州茅台", "canonical_id": "unsupported_domain", "priority": 300, "rewrite_mode": "none", "emit_mode": "terminal_outcome", "collision_policy": "highest_priority_wins"},
            {"scope": "terminal", "match_kind": "contains_phrase", "pattern": "上证指数", "canonical_id": "unsupported_domain", "priority": 300, "rewrite_mode": "none", "emit_mode": "terminal_outcome", "collision_policy": "highest_priority_wins"},
            {"scope": "terminal", "match_kind": "contains_phrase", "pattern": "深证成指", "canonical_id": "unsupported_domain", "priority": 300, "rewrite_mode": "none", "emit_mode": "terminal_outcome", "collision_policy": "highest_priority_wins"},
            {"scope": "field", "match_kind": "contains_phrase", "pattern": "振幅", "canonical_id": "swing", "priority": 120, "rewrite_mode": "none", "emit_mode": "field", "collision_policy": "highest_priority_wins"},
        ],
        "normalized_output_contract": {
            "fields": ["normalized_text", "emitted_scenarios", "emitted_fields", "emitted_terminal_outcomes"],
            "overlap_policy": "highest_priority_wins",
        },
    },
    "role_rules": {},
    "scenario_field_support_matrix": {
        scenario: {
            "explicitly_allowed_fields": list(dict.fromkeys(fields + (["swing"] if scenario == "overview" else []))),
            "explicitly_denied_fields": [],
            "unsupported_error_code": "field_not_supported",
        }
        for scenario, fields in {
            "overview": ["preClose", "latest", "change", "changeRatio", "open", "high", "low", "amount", "volume", "iopv", "premium", "tradeTime"],
            "default_overview": ["latest", "change", "changeRatio", "amount", "tradeTime"],
            "compare_overview": ["latest", "changeRatio", "amount", "premium", "tradeTime"],
            "price_change": ["latest", "change", "changeRatio", "tradeTime"],
            "trading": ["amount", "volume", "latestVolume", "tradeTime"],
            "valuation": ["latest", "iopv", "premium", "tradeTime"],
            "order_book": ["bid1", "ask1", "bidSize1", "askSize1", "tradeTime"],
            "trade_flow": ["sellVolume", "buyVolume", "latestVolume", "tradeTime"],
        }.items()
    },
    "explicit_field_injection_rules": {
        "latest": {"default_scenarios": ["price_change", "overview"]},
        "swing": {"default_scenarios": ["overview"]},
    },
    "terminal_outcome_matrix": {
        "no_scenario_match": "unsupported_query",
        "explicit_field_without_supported_scenario": "field_not_supported",
        "fund_identity_required": "fund_identity_required",
        "fund_identity_ambiguous": "fund_identity_ambiguous",
        "unsupported_domain": "unsupported_domain",
        "field_not_supported": "field_not_supported",
    },
    "composition_rules": {
        "merge_stages": ["collect_scenarios", "expand_defaults", "apply_explicit_fields", "apply_role_filters", "apply_support_policy", "dedupe", "order"],
        "explicit_field_precedence": "explicit_over_default",
        "scenario_conflict_policy": "higher_priority_wins",
        "global_field_order": [
            "latest",
            "change",
            "changeRatio",
            "open",
            "high",
            "low",
            "amount",
            "volume",
            "sellVolume",
            "buyVolume",
            "latestVolume",
            "iopv",
            "premium",
            "bid1",
            "ask1",
            "bidSize1",
            "askSize1",
            "swing",
            "preClose",
            "tradeDate",
            "tradeTime",
        ],
        "field_conflict_policy": "first_by_global_order",
    },
    "default_overview": {
        "trigger_phrases": ["实时行情", "现在行情", "现在什么情况", "今天表现如何", "怎么样"],
        "scenario": "default_overview",
        "fields": ["latest", "change", "changeRatio", "amount", "tradeTime"],
        "clarification_prompt": "你还可以继续问价格涨跌、成交活跃、折溢价、盘口或内外盘。",
    },
    "source_field_mappings": {
        field: {
            "sources": [{"source_id": "primary_quote", "source_field": field, "priority": 100, "capability_gate": None, "input_unit": "raw"}],
            "priority_policy": "highest_priority_available",
            "freshness_policy": "accept_latest_available",
            "failure_policy": "return_null",
        }
        for field in REALTIME_FIELDS
    },
    "source_capabilities": {},
    "derivation_rules": {},
    "normalization_rules": {
        "rules": [
            {
                "rule_id": "default_numeric_passthrough",
                "null_policy": "preserve_null",
                "zero_policy": "preserve_zero",
                "normalization_steps": ["type_coerce_number"],
            }
        ]
    },
}
