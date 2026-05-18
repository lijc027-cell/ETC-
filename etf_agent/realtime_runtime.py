from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any
from urllib import request

from .name_resolver import resolve_fundcode_from_name
from .realtime_planner import generate_realtime_plan_with_llm
from .realtime_registry import get_realtime_registry, validate_realtime_registry


def run_realtime_query(
    question: str,
    *,
    config_obj: Any,
    dry_run: bool = False,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = deepcopy(registry or get_realtime_registry())
    validate_realtime_registry(registry)

    alias_output = _normalize_aliases(question, registry)
    terminal_outcome = _highest_priority(alias_output["emitted_terminal_outcomes"])
    if terminal_outcome:
        return _unsupported_output(question, terminal_outcome["canonical_id"], alias_output)

    fund_resolution = _resolve_funds(question, config_obj, dry_run=dry_run)
    alias_output["fund_resolution"] = fund_resolution
    if fund_resolution["status"] == "ambiguous":
        return _unsupported_output(question, registry["terminal_outcome_matrix"]["fund_identity_ambiguous"], alias_output)
    fundcodes = [item["fundcode"] for item in fund_resolution.get("funds") or []]
    thscodes = [item["thscode"] for item in fund_resolution.get("funds") or []]
    if not fundcodes:
        return _unsupported_output(question, registry["terminal_outcome_matrix"]["fund_identity_required"], alias_output)

    if dry_run:
        plan_payload = _deterministic_realtime_plan(question, alias_output, fundcodes, registry)
    else:
        plan_payload = _llm_realtime_plan(question, fund_resolution, registry, config_obj)
        if not plan_payload["ok"]:
            if len(fundcodes) >= 2 and _has_compare_signal(question):
                plan_payload = _deterministic_realtime_plan(question, alias_output, fundcodes, registry)
            else:
                return _unsupported_output(question, plan_payload["reason"], alias_output, llm_usage=plan_payload.get("llm_usage"))
        alias_output["realtime_plan"] = {
            "raw": plan_payload.get("raw_plan"),
            "validated": plan_payload.get("validated_plan"),
        }
    scenarios = plan_payload["scenarios"]
    explicit_fields = plan_payload["explicit_fields"]
    scenarios = _apply_compare_overview(question, fundcodes, scenarios, explicit_fields)
    if scenarios == ["compare_overview"] and not _has_explicit_compare_metric_terms(question):
        explicit_fields = []
    if not scenarios:
        return _unsupported_output(question, registry["terminal_outcome_matrix"]["no_scenario_match"], alias_output)

    fields, support_error = _expand_fields(scenarios, explicit_fields, registry)
    if support_error:
        return _unsupported_output(question, support_error, alias_output)
    if not fields:
        return _unsupported_output(question, registry["terminal_outcome_matrix"]["explicit_field_without_supported_scenario"], alias_output)

    plan = _build_plan(
        fundcodes,
        thscodes,
        fund_resolution,
        scenarios,
        fields,
        registry,
        asked_fields=plan_payload.get("asked_fields") or [],
        field_origin=plan_payload.get("field_origin") or ("explicit_user_request" if explicit_fields else "scenario_default"),
    )
    result = fake_realtime_result(plan) if dry_run else execute_realtime_plan(plan)
    answer = format_realtime_answer(plan, result)
    clarification = _clarification_prompt(scenarios, registry)
    if clarification:
        answer = f"{answer}\n{clarification}"
    llm_usage = plan_payload.get("llm_usage") or []
    ast_generation_mode = "registry_realtime" if dry_run else "realtime_llm_plan"
    failure_stage = result.get("failure_stage") if result.get("success") is False else None
    failure_reason = result.get("failure_reason") if result.get("success") is False else None
    return {
        "question": question,
        "answer": answer,
        "v3": {
            "phase": "v3.5",
            "recognized_query_mode": "realtime",
            "intent": "realtime_quote",
            "intent_candidates": scenarios,
            "routing_result": {"type": "ExecutableQuery", "reason": None},
            "routing_evidence": alias_output,
            "capability_id": "v3.5:realtime:realtime_quote",
            "capability_status": "executable",
            "gate_status": "not_applicable",
            "capability_status_reason": None,
            "ast_generation_mode": ast_generation_mode,
            "remote_query_allowed": True,
            "failure_stage": failure_stage,
            "failure_reason": failure_reason,
            "llm_usage": llm_usage,
        },
        "v3_ast": {
            "intent": "realtime_quote",
            "scenarios": scenarios,
            "fields": fields,
            "fundcodes": fundcodes,
            "thscodes": thscodes,
        },
        "validated_ast": {
            "intent": "realtime_quote",
            "scenarios": scenarios,
            "fields": fields,
            "fundcodes": fundcodes,
            "thscodes": thscodes,
        },
        "query_plan": plan,
        "result": result,
        "llm_usage": llm_usage,
        "failure_stage": failure_stage,
        "failure_reason": failure_reason,
    }


def execute_realtime_plan(plan: dict[str, Any]) -> dict[str, Any]:
    endpoint = os.getenv("ETF_REALTIME_API_URL", "").strip()
    if not endpoint:
        return _null_realtime_result(plan, source_status="not_configured", failure_stage="remote_not_configured")

    body = json.dumps({"codes": plan["thscodes"]}, ensure_ascii=False).encode("utf-8")
    req = request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return _null_realtime_result(plan, source_status="source_error", failure_stage="remote_request", failure_reason=str(exc))
    return _normalize_realtime_payload(payload, plan)


def fake_realtime_result(plan: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for fundcode, thscode in zip(plan["fundcodes"], plan["thscodes"], strict=False):
        row = {"fundcode": fundcode, "thscode": thscode, "name": plan.get("matched_names", {}).get(fundcode) or _fake_name(fundcode)}
        for field in plan["fields"]:
            row[field] = _fake_value(field)
        rows.append(row)
    return {"success": True, "data": rows, "source_status": "dry_run"}


def format_realtime_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    rows = result.get("data") or []
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        return "暂无实时行情数据。"
    if result.get("success") is False and result.get("source_status") in {"not_configured", "source_error", "empty"}:
        if result.get("source_status") == "empty":
            return "实时行情接口返回空数据。"
        return "实时行情接口异常，暂时无法获取数据。"

    fields = plan["fields"]
    display = plan["field_display_matrix"]
    if len(rows) > 1:
        table = _format_realtime_table(rows, fields, display)
        if "compare_overview" in plan.get("scenarios", []):
            return f"{_compare_summary(rows, display)}\n{table}"
        return table

    row = rows[0]
    parts = [f"{display[field]['label']}：{_format_realtime_value(row.get(field), display[field])}" for field in fields]
    if "buyVolume" in fields and "sellVolume" in fields:
        parts.append(f"外内盘比：{_format_flow_ratio(row.get('buyVolume'), row.get('sellVolume'))}")
    prefix = ""
    if result.get("success") is False and result.get("source_status") == "missing_fields":
        prefix = "实时行情接口返回字段不完整，以下为已返回字段：\n"
    if plan.get("output_mode") == "direct_fields":
        return prefix + _compose_direct_realtime_answer(row, fields, display)
    summary = _compose_overview_realtime_answer(row, fields, display)
    if plan.get("output_mode") == "overview_card":
        return prefix + summary
    title = _fund_title(row)
    return prefix + f"{summary}\n{title}实时行情：\n" + "\n".join(parts)


def _normalize_aliases(question: str, registry: dict[str, Any]) -> dict[str, Any]:
    emitted_scenarios = []
    emitted_fields = []
    emitted_terminal_outcomes = []
    for rule in registry["alias_rules"].get("rules") or []:
        if not _rule_matches(question, rule):
            continue
        target = {
            "canonical_id": rule["canonical_id"],
            "pattern": rule["pattern"],
            "priority": int(rule.get("priority") or 0),
        }
        if rule["emit_mode"] == "single":
            emitted_scenarios.append(target)
        elif rule["emit_mode"] == "field":
            emitted_fields.append(target)
        elif rule["emit_mode"] == "terminal_outcome":
            emitted_terminal_outcomes.append(target)
    return {
        "normalized_text": question,
        "emitted_scenarios": emitted_scenarios,
        "emitted_fields": emitted_fields,
        "emitted_terminal_outcomes": emitted_terminal_outcomes,
    }


def _rule_matches(text: str, rule: dict[str, Any]) -> bool:
    pattern = str(rule.get("pattern") or "")
    if rule.get("match_kind") == "exact_phrase":
        return text == pattern
    return pattern in text


def _classify_scenarios(text: str, registry: dict[str, Any]) -> list[str]:
    matched = []
    for scenario, row in registry["intent_to_scenario_matrix"].items():
        if not row.get("enabled", False):
            continue
        if any(phrase and phrase in text for phrase in row.get("forbid") or []):
            continue
        if not all(phrase in text for phrase in row.get("must_have") or []):
            continue
        any_of = row.get("any_of") or []
        if any_of and not any(phrase in text for phrase in any_of):
            continue
        matched.append((scenario, int(row.get("priority") or 0)))
    matched.extend((item["canonical_id"], int(item.get("priority") or 0)) for item in _normalize_aliases(text, registry)["emitted_scenarios"])
    matched.sort(key=lambda item: (-item[1], item[0]))
    return _dedupe([scenario for scenario, _priority in matched])


def _has_compare_signal(question: str) -> bool:
    lowered = question.lower()
    return any(signal in lowered for signal in ("对比", "比较", "vs", "比一下"))


def _asked_fields_from_question(question: str) -> list[str]:
    rules: list[tuple[tuple[str, ...], list[str]]] = [
        (("成交额",), ["amount"]),
        (("成交量",), ["volume"]),
        (("现手",), ["latestVolume"]),
        (("涨了吗", "涨了没", "跌了多少"), ["change", "changeRatio"]),
        (("涨跌幅",), ["changeRatio"]),
        (("现在什么价", "什么价", "价格多少", "价格", "报多少", "多少钱"), ["latest"]),
        (("溢价率", "折价率", "折溢价率", "溢价", "折价", "折溢价"), ["premium"]),
        (("IOPV", "iopv"), ["iopv"]),
        (("盘口", "挂单"), ["bid1", "ask1", "bidSize1", "askSize1"]),
        (("买一", "买1"), ["bid1", "bidSize1"]),
        (("卖一", "卖1"), ["ask1", "askSize1"]),
        (("内外盘",), ["sellVolume", "buyVolume"]),
        (("外盘",), ["buyVolume"]),
        (("内盘",), ["sellVolume"]),
        (("振幅",), ["swing"]),
    ]
    fields: list[str] = []
    for phrases, emitted in rules:
        if any(phrase in question for phrase in phrases):
            fields.extend(emitted)
    if "涨跌" in question and "涨跌幅" not in question:
        fields.extend(["change", "changeRatio"])
    return _dedupe(fields)


def _append_trade_time_for_explicit_fields(fields: list[str]) -> list[str]:
    if fields and "tradeTime" not in fields:
        return [*fields, "tradeTime"]
    return fields


def _inject_explicit_field_scenarios(scenarios: list[str], explicit_fields: list[str], registry: dict[str, Any]) -> list[str]:
    result = list(scenarios)
    for field in explicit_fields:
        if field == "tradeTime":
            continue
        if any(field in (registry["scenario_field_support_matrix"].get(scenario) or {}).get("explicitly_allowed_fields", []) for scenario in result):
            continue
        rule = registry["explicit_field_injection_rules"].get(field) or {}
        for scenario in rule.get("default_scenarios") or []:
            if scenario not in result:
                result.append(scenario)
    scenario_priority = registry["intent_to_scenario_matrix"]
    result.sort(key=lambda scenario: -int(scenario_priority[scenario].get("priority") or 0))
    return result


def _deterministic_realtime_plan(
    question: str,
    alias_output: dict[str, Any],
    fundcodes: list[str],
    registry: dict[str, Any],
) -> dict[str, Any]:
    scenarios = _classify_scenarios(alias_output["normalized_text"], registry)
    if len(fundcodes) >= 2 and _has_compare_signal(question) and not scenarios:
        scenarios = ["overview"]
    asked_fields = _asked_fields_from_question(question)
    explicit_fields = _dedupe([item["canonical_id"] for item in alias_output["emitted_fields"]] + asked_fields)
    scenarios = _inject_explicit_field_scenarios(scenarios, explicit_fields, registry)
    scenarios = _apply_default_overview(scenarios, explicit_fields, registry)
    scenarios = _apply_compare_overview(question, fundcodes, scenarios, explicit_fields)
    if scenarios == ["compare_overview"] and not _has_explicit_compare_metric_terms(question):
        explicit_fields = []
    explicit_fields = _append_trade_time_for_explicit_fields(explicit_fields)
    return {
        "ok": True,
        "scenarios": scenarios,
        "explicit_fields": explicit_fields,
        "asked_fields": asked_fields,
        "field_origin": "explicit_user_request" if asked_fields else "scenario_default",
        "llm_usage": [],
    }


def _llm_realtime_plan(
    question: str,
    fund_resolution: dict[str, Any],
    registry: dict[str, Any],
    config_obj: Any,
) -> dict[str, Any]:
    try:
        payload = generate_realtime_plan_with_llm(
            question=question,
            fund_resolution=fund_resolution,
            registry=registry,
            config=config_obj,
        )
        scenarios, explicit_fields = _validate_realtime_llm_plan(payload["draft"], registry)
    except Exception as exc:
        return {
            "ok": False,
            "reason": "realtime_plan_failed",
            "llm_usage": [],
            "error": str(exc),
        }
    asked_fields = _asked_fields_from_question(question)
    if asked_fields:
        explicit_fields = _append_trade_time_for_explicit_fields(asked_fields)
        local_scenarios = _classify_scenarios(question, registry)
        if local_scenarios:
            scenarios = local_scenarios
        scenarios = _inject_explicit_field_scenarios(scenarios, explicit_fields, registry)
    scenarios = _apply_default_overview(scenarios, explicit_fields if asked_fields else [], registry)
    usage = _normalize_usage(payload.get("usage"))
    return {
        "ok": True,
        "scenarios": scenarios,
        "explicit_fields": explicit_fields,
        "asked_fields": asked_fields,
        "field_origin": "explicit_user_request" if asked_fields else "llm_metrics",
        "raw_plan": payload.get("raw"),
        "validated_plan": payload.get("draft"),
        "llm_usage": usage,
    }


def _validate_realtime_llm_plan(draft: dict[str, Any], registry: dict[str, Any]) -> tuple[list[str], list[str]]:
    if draft.get("type") != "executable_query":
        raise ValueError("realtime plan type must be executable_query")
    subqueries = draft.get("subqueries")
    if not isinstance(subqueries, list) or not subqueries:
        raise ValueError("realtime plan subqueries must be a non-empty list")
    scenarios: list[str] = []
    explicit_fields: list[str] = []
    for subquery in subqueries:
        if not isinstance(subquery, dict):
            raise ValueError("realtime plan subqueries must contain objects")
        time_scope = subquery.get("time_scope")
        if not isinstance(time_scope, dict) or time_scope.get("kind") != "realtime":
            raise ValueError("realtime plan only supports realtime time_scope")
        scenario = _intent_profile_to_scenario(str(subquery.get("intent_profile") or ""))
        if scenario not in registry["intent_to_scenario_matrix"]:
            raise ValueError(f"unknown realtime intent_profile: {subquery.get('intent_profile')}")
        if scenario not in scenarios:
            scenarios.append(scenario)
        metrics = subquery.get("metrics")
        if metrics is None:
            continue
        if not isinstance(metrics, list):
            raise ValueError("realtime plan metrics must be a list")
        allowed = set((registry["scenario_field_support_matrix"].get(scenario) or {}).get("explicitly_allowed_fields") or [])
        for metric in metrics:
            if not isinstance(metric, dict):
                raise ValueError("realtime plan metric entries must be objects")
            field = metric.get("field")
            if not isinstance(field, str) or field not in registry["field_metadata"]:
                raise ValueError(f"unknown realtime metric field: {field}")
            if field not in allowed:
                raise ValueError(f"metric {field} is not allowed for scenario {scenario}")
            if field not in explicit_fields:
                explicit_fields.append(field)
    if not explicit_fields:
        explicit_fields = []
    if explicit_fields and "tradeTime" not in explicit_fields:
        explicit_fields.append("tradeTime")
    return scenarios, explicit_fields


def _intent_profile_to_scenario(intent_profile: str) -> str:
    return {
        "quote": "price_change",
        "overview": "default_overview",
        "trading": "trading",
        "valuation": "valuation",
        "order_book": "order_book",
        "trade_flow": "trade_flow",
        "technical": "overview",
    }.get(intent_profile, intent_profile)


def _normalize_usage(usage: Any) -> list[dict[str, int]]:
    if not isinstance(usage, dict):
        return [{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}]
    return [
        {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }
    ]


def _expand_fields(scenarios: list[str], explicit_fields: list[str], registry: dict[str, Any]) -> tuple[list[str], str | None]:
    fields = []
    explicit = bool(explicit_fields)
    if not explicit:
        for scenario in scenarios:
            fields.extend(registry["scenario_to_fields_matrix"].get(scenario) or [])
    fields.extend(explicit_fields)

    allowed = set()
    denied = set()
    for scenario in scenarios:
        support = registry["scenario_field_support_matrix"].get(scenario) or {}
        allowed.update(support.get("explicitly_allowed_fields") or [])
        denied.update(support.get("explicitly_denied_fields") or [])

    for field in fields:
        if field in denied or field not in allowed:
            return [], registry["unsupported_field_policy"]["default_error_code"]

    order = registry["composition_rules"]["global_field_order"]
    ordered = [field for field in order if field in set(fields)]
    return ordered, None


def _build_plan(
    fundcodes: list[str],
    thscodes: list[str],
    fund_resolution: dict[str, Any],
    scenarios: list[str],
    fields: list[str],
    registry: dict[str, Any],
    *,
    asked_fields: list[str] | None = None,
    field_origin: str = "scenario_default",
) -> dict[str, Any]:
    matched_names = {item["fundcode"]: item.get("matched_name", "") for item in fund_resolution.get("funds") or []}
    output_mode = "overview_card" if "default_overview" in scenarios else "direct_fields"
    if "compare_overview" in scenarios or len(fundcodes) > 1:
        output_mode = "comparison_table"
    return {
        "output_style": "realtime_card",
        "output_mode": output_mode,
        "asked_fields": asked_fields or [],
        "field_origin": field_origin,
        "fundcodes": fundcodes,
        "thscodes": thscodes,
        "matched_names": matched_names,
        "scenarios": scenarios,
        "fields": fields,
        "field_display_matrix": {field: registry["field_display_matrix"][field] for field in fields},
        "source_field_mappings": {field: registry["source_field_mappings"][field] for field in fields},
        "normalization_rules": registry["normalization_rules"],
    }


def _resolve_funds(question: str, config_obj: Any, *, dry_run: bool) -> dict[str, Any]:
    fundcodes = re.findall(r"(?<!\d)(?:1|5)\d{5}(?!\d)", question)
    if fundcodes:
        funds = [
            {
                "fundcode": fundcode,
                "thscode": _fundcode_to_thscode(fundcode),
                "matched_name": _fake_name(fundcode),
            }
            for fundcode in _dedupe(fundcodes)
        ]
        return {"status": "matched", "funds": funds, "matches": funds}
    resolved = resolve_fundcode_from_name(question, config_obj, dry_run=dry_run)
    if resolved.get("status") == "matched" and resolved.get("fundcode"):
        fundcode = str(resolved["fundcode"])
        thscode = str(resolved.get("thscode") or resolved.get("matched_thscode") or _fundcode_to_thscode(fundcode))
        fund = {"fundcode": fundcode, "thscode": thscode, "matched_name": str(resolved.get("matched_name") or "")}
        return {"status": "matched", "funds": [fund], "matches": resolved.get("matches") or [fund]}
    if resolved.get("status") == "ambiguous":
        return {"status": "ambiguous", "funds": [], "matches": resolved.get("matches") or []}
    return {"status": "not_found", "funds": [], "matches": []}


def _normalize_realtime_payload(payload: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        rows = [data]
    elif isinstance(data, list):
        rows = [row for row in data if isinstance(row, dict)]
    else:
        rows = []
    if not rows:
        return _null_realtime_result(plan, source_status="empty", failure_stage="remote_response_empty")
    fundcode_by_thscode = dict(zip(plan["thscodes"], plan["fundcodes"], strict=False))
    name_by_fundcode = plan.get("matched_names") or {}
    normalized = []
    missing_fields: dict[str, list[str]] = {}
    for source_row in rows:
        thscode = str(source_row.get("thscode") or "")
        fundcode = str(source_row.get("fundcode") or fundcode_by_thscode.get(thscode) or _fundcode_from_thscode(thscode))
        row = {
            "fundcode": fundcode,
            "thscode": thscode,
            "name": str(source_row.get("name") or name_by_fundcode.get(fundcode) or ""),
        }
        for field in plan["fields"]:
            row[field] = source_row.get(field)
            if field not in source_row:
                missing_fields.setdefault(thscode or fundcode, []).append(field)
        normalized.append(row)
    if missing_fields:
        return {
            "success": False,
            "data": normalized,
            "source_status": "missing_fields",
            "failure_stage": "remote_response_missing_fields",
            "failure_reason": "remote response missing requested fields",
            "missing_fields": missing_fields,
        }
    return {"success": True, "data": normalized, "source_status": payload.get("source_status") or "remote"}


def _null_realtime_result(
    plan: dict[str, Any],
    *,
    source_status: str,
    failure_stage: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    rows = []
    for fundcode, thscode in zip(plan["fundcodes"], plan.get("thscodes") or [], strict=False):
        row = {"fundcode": fundcode, "thscode": thscode, "name": plan.get("matched_names", {}).get(fundcode) or _fake_name(fundcode)}
        for field in plan["fields"]:
            row[field] = None
        rows.append(row)
    return {
        "success": False,
        "data": rows,
        "source_status": source_status,
        "failure_stage": failure_stage,
        "failure_reason": failure_reason or source_status,
    }


def _format_realtime_table(rows: list[dict[str, Any]], fields: list[str], display: dict[str, Any]) -> str:
    headers = ["指标", *[_fund_title(row) for row in rows]]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for field in fields:
        rule = display[field]
        values = [_format_realtime_value(row.get(field), rule) for row in rows]
        lines.append("| " + " | ".join([rule["label"], *values]) + " |")
    if "buyVolume" in fields and "sellVolume" in fields:
        ratio_values = [_format_flow_ratio(row.get("buyVolume"), row.get("sellVolume")) for row in rows]
        lines.append("| " + " | ".join(["外内盘比", *ratio_values]) + " |")
    return "\n".join(lines)


def _compose_direct_realtime_answer(row: dict[str, Any], fields: list[str], display: dict[str, Any]) -> str:
    title = _fund_title(row)
    time_text = _data_time_suffix(row, display) if "tradeTime" in fields else ""
    value_fields = [field for field in fields if field != "tradeTime"]

    if set(value_fields) == {"bid1", "ask1", "bidSize1", "askSize1"}:
        bid = _format_realtime_value(row.get("bid1"), display["bid1"])
        ask = _format_realtime_value(row.get("ask1"), display["ask1"])
        bid_size = _format_realtime_value(row.get("bidSize1"), display["bidSize1"])
        ask_size = _format_realtime_value(row.get("askSize1"), display["askSize1"])
        return f"{title}盘口上，买一价 {bid}、卖一价 {ask}；买一量 {bid_size}、卖一量 {ask_size}。{_data_time_sentence(row, display)}"

    if len(value_fields) == 1:
        field = value_fields[0]
        value = _format_realtime_value(row.get(field), display[field])
        return f"{title}当前{display[field]['label']}为 {value}{time_text}"

    if "change" in value_fields and "changeRatio" in value_fields and len(value_fields) == 2:
        direction = _direction_word(row.get("changeRatio"))
        change = _format_realtime_value(row.get("change"), display["change"])
        ratio = _format_realtime_value(row.get("changeRatio"), display["changeRatio"])
        return f"{title}当前{direction}，涨跌为 {change}，涨跌幅为 {ratio}{time_text}"

    if "buyVolume" in value_fields and "sellVolume" in value_fields and len(value_fields) == 2:
        buy = _format_realtime_value(row.get("buyVolume"), display["buyVolume"])
        sell = _format_realtime_value(row.get("sellVolume"), display["sellVolume"])
        ratio = _format_flow_ratio(row.get("buyVolume"), row.get("sellVolume"))
        return f"{title}当前外盘 {buy}、内盘 {sell}，外内盘比 {ratio}{time_text}"

    first = value_fields[0]
    rest = value_fields[1:]
    first_value = _format_realtime_value(row.get(first), display[first])
    first_clause = f"{title}当前{display[first]['label']}为 {first_value}"
    rest_clause = "，".join(_format_metric_phrase(row, field, display) for field in rest)
    if rest_clause:
        return f"{first_clause}；{rest_clause}。{_data_time_sentence(row, display)}"
    return f"{first_clause}{time_text}"


def _compose_overview_realtime_answer(row: dict[str, Any], fields: list[str], display: dict[str, Any]) -> str:
    title = _fund_title(row)
    metric_fields = [field for field in fields if field != "tradeTime"]
    phrases = [_format_metric_phrase(row, field, display) for field in metric_fields]
    time_text = _data_time_suffix(row, display) if "tradeTime" in fields else "。"
    return f"先看核心实时情况：{title}" + "，".join(phrases) + time_text


def _format_metric_phrase(row: dict[str, Any], field: str, display: dict[str, Any]) -> str:
    return f"{display[field]['label']} {_format_realtime_value(row.get(field), display[field])}"


def _data_time_suffix(row: dict[str, Any], display: dict[str, Any]) -> str:
    return f"，数据时间 {_format_realtime_value(row.get('tradeTime'), display['tradeTime'])}。"


def _data_time_sentence(row: dict[str, Any], display: dict[str, Any]) -> str:
    return f"数据时间 {_format_realtime_value(row.get('tradeTime'), display['tradeTime'])}。"


def _single_realtime_summary(row: dict[str, Any], fields: list[str], display: dict[str, Any]) -> str:
    title = _fund_title(row)
    if "latest" in fields:
        latest = _format_realtime_value(row.get("latest"), display["latest"])
        if "changeRatio" in fields:
            ratio = _format_realtime_value(row.get("changeRatio"), display["changeRatio"])
            direction = _direction_word(row.get("changeRatio"))
            ratio_text = ratio.lstrip("+-") if direction in {"上涨", "下跌"} else ratio
            return f"{title}当前最新价为 {latest}，{direction}，涨跌幅为 {ratio_text}。"
        return f"{title}当前最新价为 {latest}。"
    if "amount" in fields:
        return f"{title}当前成交额：{_format_realtime_value(row.get('amount'), display['amount'])}。"
    if "changeRatio" in fields:
        ratio = _format_realtime_value(row.get("changeRatio"), display["changeRatio"])
        direction = _direction_word(row.get("changeRatio"))
        if "change" in fields:
            change = _format_realtime_value(row.get("change"), display["change"])
            return f"{title}当前{direction}，涨跌为 {change}，涨跌幅为 {ratio}。"
        return f"{title}当前涨跌幅为 {ratio}。"
    if "volume" in fields:
        return f"{title}当前成交量为 {_format_realtime_value(row.get('volume'), display['volume'])}。"
    if "latestVolume" in fields:
        return f"{title}当前现手为 {_format_realtime_value(row.get('latestVolume'), display['latestVolume'])}。"
    if "premium" in fields:
        return f"{title}当前折溢价率：{_format_realtime_value(row.get('premium'), display['premium'])}。"
    if "bid1" in fields and "ask1" in fields:
        return f"{title}当前买一价 {_format_realtime_value(row.get('bid1'), display['bid1'])}，卖一价 {_format_realtime_value(row.get('ask1'), display['ask1'])}。"
    if "buyVolume" in fields and "sellVolume" in fields:
        return f"{title}当前外内盘比为 {_format_flow_ratio(row.get('buyVolume'), row.get('sellVolume'))}。"
    if "swing" in fields:
        return f"{title}当前振幅为 {_format_realtime_value(row.get('swing'), display['swing'])}。"
    return f"{title}当前实时行情如下。"


def _single_summary_covered_fields(fields: list[str]) -> set[str]:
    if "latest" in fields:
        covered = {"latest"}
        if "changeRatio" in fields:
            covered.add("changeRatio")
        return covered
    if "amount" in fields:
        return {"amount"}
    if "changeRatio" in fields:
        covered = {"changeRatio"}
        if "change" in fields:
            covered.add("change")
        return covered
    if "volume" in fields:
        return {"volume"}
    if "latestVolume" in fields:
        return {"latestVolume"}
    if "premium" in fields:
        return {"premium"}
    if "bid1" in fields and "ask1" in fields:
        return {"bid1", "ask1"}
    if "buyVolume" in fields and "sellVolume" in fields:
        return set()
    if "swing" in fields:
        return {"swing"}
    return set()


def _compare_summary(rows: list[dict[str, Any]], display: dict[str, Any]) -> str:
    ranked = _rank_rows_by_number(rows, "changeRatio")
    if not ranked:
        return "对比来看，下面是这几只ETF的实时核心指标。"
    leader = ranked[0]
    ratio = _format_realtime_value(leader.get("changeRatio"), display["changeRatio"])
    return f"对比来看，{_fund_title(leader)}当前涨跌幅相对更高，为 {ratio}。"


def _rank_rows_by_number(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    numeric_rows = []
    for row in rows:
        try:
            numeric_rows.append((float(row.get(field)), row))
        except Exception:
            continue
    return [row for _value, row in sorted(numeric_rows, key=lambda item: item[0], reverse=True)]


def _direction_word(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "涨跌幅"
    if number > 0:
        return "上涨"
    if number < 0:
        return "下跌"
    return "涨跌幅"


def _format_realtime_value(value: Any, rule: dict[str, Any]) -> str:
    if value is None or value == "":
        return "暂无数据"
    if rule["format_kind"] == "plain_text":
        return str(value)
    number = float(value)
    if rule["scale_policy"] == "divide":
        number = number / float(rule.get("scale_value") or 1)
    elif rule["scale_policy"] == "ratio_to_percent":
        number = number * 100 if abs(number) <= 1 else number
    text = _format_number(number, rule)
    if rule["sign_policy"] == "always" and number > 0:
        text = f"+{text}"
    if rule["unit_policy"] == "suffix_percent":
        return f"{text}%"
    if rule["unit_policy"] == "literal":
        return f"{text}{rule.get('unit_value') or ''}"
    return text


def _format_number(value: float, rule: dict[str, Any]) -> str:
    precision = int(rule.get("precision_value") or 0)
    if rule["precision_mode"] == "none":
        return str(int(value))
    text = f"{value:.{precision}f}"
    if rule["precision_mode"] == "max_fraction_digits":
        return text.rstrip("0").rstrip(".")
    return text


def _format_flow_ratio(buy_volume: Any, sell_volume: Any) -> str:
    try:
        buy = float(buy_volume)
        sell = float(sell_volume)
    except Exception:
        return "暂无数据"
    if sell == 0:
        return "暂无数据"
    return f"{buy / sell:.2f}"


def _highest_priority(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return sorted(items, key=lambda item: -int(item.get("priority") or 0))[0]


def _unsupported_output(question: str, reason: str, alias_output: dict[str, Any], *, llm_usage: list[dict[str, int]] | None = None) -> dict[str, Any]:
    usage = llm_usage or []
    return {
        "question": question,
        "answer": _unsupported_message(question, reason, alias_output),
        "v3": {
            "phase": "v3.5",
            "recognized_query_mode": "unsupported",
            "intent": None,
            "routing_result": {"type": "UnsupportedQuery", "reason": reason},
            "routing_evidence": alias_output,
            "capability_id": f"v3.5:unsupported:{reason}",
            "capability_status": reason,
            "gate_status": "blocked",
            "capability_status_reason": reason,
            "remote_query_allowed": False,
            "failure_stage": "routing",
            "failure_reason": reason,
            "llm_usage": usage,
        },
        "v3_ast": None,
        "validated_ast": None,
        "query_plan": None,
        "result": None,
        "llm_usage": usage,
        "failure_stage": "routing",
        "failure_reason": reason,
    }


def _unsupported_message(question: str, reason: str, alias_output: dict[str, Any] | None = None) -> str:
    if reason == "fund_identity_required":
        if "盘口" in question or "内外盘" in question:
            return "请先提供ETF代码或名称。"
        if "规模" in question:
            return "暂无数据。实时行情能力不返回基金规模；如需规模数据，请提供具体ETF并使用基金资料类能力查询。"
        if "历史走势" in question:
            return "暂无数据。当前实时能力聚焦最新盘口与当日行情，不返回历史走势。"
        return "请先提供ETF代码或名称。"
    if reason == "fund_identity_ambiguous":
        return _ambiguous_fund_message(alias_output or {})
    if reason == "unsupported_domain":
        return "暂无数据。当前实时问句能力仅支持ETF，不支持该标的。"
    if reason == "field_not_supported":
        return "暂无数据。当前实时能力不支持该字段。"

    if any(word in question for word in ("持仓", "重仓", "持有")):
        return "暂无实时数据。该问题属于基金持仓信息，建议使用基金资料或持仓类能力查询最新定期报告数据。"
    if any(word in question for word in ("基金经理", "管理人")):
        return "暂无实时数据。该问题属于基金基础资料，建议使用基金资料类能力查询。"
    if any(word in question for word in ("跟踪什么指数", "跟踪哪个指数", "跟踪")):
        return "暂无实时数据。该问题属于基金基础资料，建议使用基金资料类能力查询。"
    if any(word in question for word in ("费率",)):
        return "暂无实时数据。该问题属于基金费率资料，建议使用基金资料类能力查询。"
    if "历史走势" in question:
        return "暂无数据。当前实时能力聚焦最新盘口与当日行情，不返回历史走势。"
    return "暂无实时数据。该问题不在当前实时行情能力范围内。"


def _fake_name(fundcode: str) -> str:
    return {
        "510050": "上证50ETF",
        "510300": "沪深300ETF",
        "159915": "创业板ETF",
        "588000": "科创50ETF华夏",
    }.get(fundcode, "")


def _ambiguous_fund_message(alias_output: dict[str, Any]) -> str:
    matches = ((alias_output.get("fund_resolution") or {}).get("matches") or [])[:3]
    if not matches:
        return "匹配到多只ETF，请补充基金公司或基金代码后再查。"
    lines = ["我查到几只可能匹配的 ETF，先列出来供你确认："]
    for match in matches:
        name = match.get("matched_name") or match.get("name") or ""
        fundcode = match.get("fundcode") or ""
        manager = match.get("manager") or "基金公司待确认"
        tracking_index = match.get("tracking_index") or "跟踪指数待确认"
        lines.append(f"- {name}（{fundcode}）：{manager}，跟踪 {tracking_index}")
    lines.append("你可以直接回基金代码，我再继续查实时数据。")
    return "\n".join(lines)


def _apply_compare_overview(
    question: str,
    fundcodes: list[str],
    scenarios: list[str],
    explicit_fields: list[str],
) -> list[str]:
    if len(fundcodes) < 2 or not _has_compare_signal(question):
        return scenarios
    if explicit_fields and _has_explicit_compare_metric_terms(question):
        return scenarios
    if scenarios in (["overview"], ["default_overview"]):
        return ["compare_overview"]
    return scenarios


def _has_explicit_compare_metric_terms(question: str) -> bool:
    return any(
        term in question
        for term in (
            "价格",
            "涨跌",
            "涨跌幅",
            "成交",
            "溢价",
            "折价",
            "折溢价",
            "盘口",
            "买一",
            "卖一",
            "内外盘",
            "外盘",
            "内盘",
            "振幅",
        )
    )


def _apply_default_overview(scenarios: list[str], explicit_fields: list[str], registry: dict[str, Any]) -> list[str]:
    config = registry.get("default_overview") or {}
    scenario = config.get("scenario")
    if explicit_fields or not scenario:
        return scenarios
    if scenarios == ["overview"]:
        return [scenario]
    return scenarios


def _clarification_prompt(scenarios: list[str], registry: dict[str, Any]) -> str:
    config = registry.get("default_overview") or {}
    if config.get("scenario") in scenarios:
        return str(config.get("clarification_prompt") or "")
    return ""


def _fundcode_to_thscode(fundcode: str) -> str:
    suffix = "SZ" if fundcode.startswith("1") else "SH"
    return f"{fundcode}.{suffix}"


def _fundcode_from_thscode(thscode: str) -> str:
    return thscode.split(".", 1)[0] if thscode else ""


def _fake_value(field: str) -> Any:
    return {
        "tradeDate": "2026-05-17",
        "tradeTime": "14:56:03",
        "preClose": 2.5,
        "open": 2.501,
        "high": 2.536,
        "low": 2.488,
        "latest": 2.5123,
        "change": 0.0123,
        "changeRatio": 0.0049,
        "swing": 0.0192,
        "amount": 1_250_000_000,
        "volume": 1_234_560,
        "latestVolume": 800,
        "sellVolume": 520_000,
        "buyVolume": 610_000,
        "iopv": 2.514,
        "premium": -0.0017,
        "bid1": 2.512,
        "ask1": 2.513,
        "bidSize1": 18_000,
        "askSize1": 21_000,
    }.get(field)


def _fund_title(row: dict[str, Any]) -> str:
    fundcode = str(row.get("fundcode") or "")
    name = str(row.get("name") or "")
    return f"{name}（{fundcode}）" if name and fundcode else fundcode or name or "该ETF"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
