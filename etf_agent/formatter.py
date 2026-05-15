from __future__ import annotations

import re
from typing import Any


PERIOD_LABELS = {
    "1w": "近1周",
    "1m": "近1月",
    "3m": "近3月",
    "6m": "近半年",
    "1y": "近1年",
    "2y": "近2年",
    "3y": "近3年",
    "5y": "近5年",
    "ytd": "今年以来",
    "std": "成立以来",
}


def format_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    if plan.get("output_style") == "timeseries_series":
        return _format_timeseries_series_answer(plan, result)
    if plan.get("output_style") == "performance_table":
        return _format_performance_table_answer(plan, result)
    if plan.get("output_style") == "report_list":
        return _format_report_list_answer(plan, result)
    if plan.get("output_style") == "manager_detail":
        return _format_manager_detail_answer(plan, result)
    if plan.get("output_style") == "list":
        return _format_list_answer(plan, result)
    if plan.get("output_style") == "compare":
        return _format_compare_answer(plan, result)
    return _format_summary_answer(plan, result)


def _format_timeseries_series_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    data = result.get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        return "查询结果为空。"

    series = _ensure_result_series(data, plan)
    data["series"] = series
    fundcode = str(data.get("fundcode") or (plan.get("filter") or {}).get("fundcode") or "")
    name = str(data.get("ths_fund_extended_inner_short_name_fund") or "")
    fund_label = f"{name}（{fundcode}）" if name and fundcode else fundcode or name or "该基金"
    if not series:
        return f"{fund_label} 暂无走势数据。"
    first = series[0]
    label = first.get("label") or first.get("field") or "指标"
    period = first.get("period") or "1y"
    point_count = sum(len(item.get("points") or []) for item in series if isinstance(item, dict))
    date_range = _series_date_range_text(series)
    period_text = _series_period_text(first)
    if len(series) == 1:
        summary = f"{fund_label}{period_text}{label}走势已查询到，共 {point_count} 个数据点{date_range}。"
        return _with_series_samples(summary, series)
    labels = "、".join(str(item.get("label") or item.get("field")) for item in series)
    summary = f"{fund_label}{period_text}{labels}走势已查询到，共 {point_count} 个数据点{date_range}。"
    return _with_series_samples(summary, series)


def _series_date_range_text(series: list[dict[str, Any]]) -> str:
    dates = [
        str(point.get("btime") or "")[:10]
        for item in series
        if isinstance(item, dict)
        for point in (item.get("points") or [])
        if isinstance(point, dict) and point.get("btime")
    ]
    if not dates:
        return ""
    return f"，覆盖 {min(dates)} 至 {max(dates)}"


def _series_period_text(item: dict[str, Any]) -> str:
    period = item.get("period")
    if period == "business_days" and isinstance(item.get("count"), int):
        return f"近{item['count']}个交易日"
    return {
        "1m": "近一个月",
        "3m": "近三个月",
        "6m": "近半年",
        "1y": "近一年",
        "3y": "近三年",
        "5y": "近五年",
        "std": "成立以来",
    }.get(str(period or ""), "")


def _with_series_samples(summary: str, series: list[dict[str, Any]]) -> str:
    lines = [summary, "部分数据点："]
    for item in series:
        sample_text = _series_sample_line(item)
        if sample_text:
            lines.append(sample_text)
    return "\n".join(lines)


def _series_sample_line(item: dict[str, Any]) -> str:
    points = [point for point in (item.get("points") or []) if isinstance(point, dict)]
    if not points:
        return ""
    sampled = _sample_series_points(points)
    parts = []
    for point in sampled:
        if point == "...":
            parts.append("...")
            continue
        parts.append(f"{point.get('btime')}：{_format_series_point_value(point.get('value'), item)}")
    label = item.get("label") or item.get("field") or "指标"
    return f"{label}：" + "；".join(parts)


def _sample_series_points(points: list[dict[str, Any]]) -> list[dict[str, Any] | str]:
    if len(points) <= 6:
        return points
    return [*points[:3], "...", *points[-3:]]


def _format_series_point_value(value: Any, item: dict[str, Any]) -> str:
    field = str(item.get("field") or "")
    fmt = str(item.get("format") or "plain")
    if value is None or value == "":
        return "暂无数据"
    if field == "ths_unit_nv_fund":
        return _format_scalar(value, "plain", field=field)
    if fmt in {"yuan_to_100m", "shares_to_100m", "shares", "amount"}:
        return _format_scalar(value, fmt, field=field)
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _ensure_result_series(data: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    existing = data.get("series")
    if isinstance(existing, list):
        return existing
    by_field = ((plan.get("timeseries_semantics") or {}).get("by_field") or {})
    answer_formats = {item.get("field"): item.get("format", "plain") for item in plan.get("answer_fields") or [] if isinstance(item, dict)}
    series = []
    for field, spec in by_field.items():
        if not isinstance(spec, dict):
            continue
        points = data.get(field)
        if not isinstance(points, list):
            points = []
        block = {
            "field": field,
            "label": _field_label(plan, field),
            "format": _series_format(field, answer_formats.get(field, "plain")),
            "period": spec.get("period") or "1y",
            "points": points,
        }
        if spec.get("period") == "business_days" and isinstance(spec.get("count"), int):
            block["count"] = spec["count"]
        series.append(block)
    return series


def _series_format(field: str, fmt: str) -> str:
    if field == "ths_fund_scale_fund":
        return "yuan_to_100m"
    if field == "ths_fund_shares_fund":
        return "shares_to_100m"
    return fmt or "plain"


def _format_summary_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    fundcode = plan.get("filter", {}).get("fundcode", "该 ETF")
    data = result.get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if not data:
        return f"未在 ETF 数据库中找到代码 {fundcode} 对应的 ETF。"

    report_prefix = _report_period_prefix(data)
    parts = []
    for field in plan["answer_fields"]:
        name = field["field"]
        if name in {"fundcode", "year_num", "type_num"}:
            continue
        parts.append(f"{field['label']}为 {_format_value(data.get(name), field.get('format', 'plain'), field=name)}")

    if not parts:
        return f"{fundcode} 暂无可展示字段。"
    if report_prefix:
        return f"{fundcode} 的{report_prefix}{'，'.join(parts)}。"
    return f"{fundcode} 的{'，'.join(parts)}。"


def chinese_mapping(plan: dict[str, Any]) -> dict[str, str]:
    return {item["field"]: item["label"] for item in plan["answer_fields"]}


def _format_value(value: Any, fmt: str, *, field: str | None = None) -> str:
    if isinstance(value, dict) and {"current", "previous", "delta", "delta_pct", "direction"} <= set(value):
        return _format_timeseries_delta(value, fmt, field=field)
    value, as_of = _latest_value(value)
    if value is None or value == "":
        return "暂无数据"
    suffix = f"（{as_of}）" if as_of else ""
    if field in {"ths_fund_shares_fund", "ths_org_investor_total_held_shares_fund"} or fmt in {"shares", "shares_to_100m"}:
        return f"{float(value) / 100000000:.2f}亿份{suffix}"
    if fmt in {"yuan_to_100m", "amount"}:
        return f"{float(value) / 100000000:.2f} 亿元{suffix}"
    if fmt == "percent":
        return f"{float(value):.2f}%{suffix}"
    if field == "ths_unit_nv_fund":
        return f"{float(value):.4f}".rstrip("0").rstrip(".") + suffix
    if isinstance(value, float):
        return f"{value:.4g}{suffix}"
    return f"{value}{suffix}"


def _format_timeseries_delta(value: dict[str, Any], fmt: str, *, field: str | None = None) -> str:
    current = value.get("current") or {}
    previous = value.get("previous") or {}
    direction = value.get("direction") or "flat"
    delta = value.get("delta")
    delta_pct = value.get("delta_pct")

    current_text = _format_scalar(current.get("value"), fmt, field=field)
    previous_text = _format_scalar(previous.get("value"), fmt, field=field)
    current_as_of = str(current.get("btime") or "")
    previous_as_of = str(previous.get("btime") or "")
    direction_text = {"increase": "增加", "decrease": "减少"}.get(direction, "持平")
    delta_text = _format_scalar(delta, fmt, field=field) if delta is not None else "暂无数据"
    pct_text = f"{float(delta_pct):.2f}%" if isinstance(delta_pct, (int, float)) else "暂无数据"
    return (
        f"{current_text}（{current_as_of}），较前一期 {previous_text}（{previous_as_of}）"
        f"{direction_text} {delta_text}（{pct_text}）"
    )


def _format_scalar(value: Any, fmt: str, *, field: str | None = None) -> str:
    if value is None or value == "":
        return "暂无数据"
    if field in {"ths_fund_shares_fund", "ths_org_investor_total_held_shares_fund"} or fmt in {"shares", "shares_to_100m"}:
        return f"{float(value) / 100000000:.2f}亿份"
    if fmt in {"yuan_to_100m", "amount"}:
        return f"{float(value) / 100000000:.2f} 亿元"
    if fmt == "percent":
        return f"{float(value):.2f}%"
    if field == "ths_unit_nv_fund":
        return f"{float(value):.4f}".rstrip("0").rstrip(".")
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _format_list_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    rows = result.get("data") or []
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or not rows:
        return "未找到符合条件的 ETF。"

    if len(rows) == 1 and int(plan.get("limit") or 0) == 1:
        top1 = _format_top1_performance_answer(plan, rows[0])
        if top1 is not None:
            return top1

    fields = _list_fields(plan)
    labels = chinese_mapping({"answer_fields": plan["answer_fields"]})
    lines = [
        "| " + " | ".join(labels.get(field, field) for field in fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_format_value(row.get(field), _field_format(plan, field), field=field) for field in fields) + " |")
    body = "\n".join(lines)
    prefix = _list_summary(plan, result)
    footer = _list_date_footer(plan, result)
    parts = [item for item in (prefix, body, footer) if item]
    return "\n\n".join(parts)


def _list_summary(plan: dict[str, Any], result: dict[str, Any]) -> str:
    if "__search_text__" not in (plan.get("filter") or {}):
        return _filter_list_summary(plan, result)

    limit = int(plan.get("limit") or result.get("returned_count") or 0)
    keyword = str(plan.get("search_keyword") or _search_keyword_from_filter(plan) or "")
    total = result.get("total_count")
    has_more = bool(result.get("has_more"))
    limit_text = f"最多展示 {limit} 只" if plan.get("limit_source") == "all" else f"默认按基金规模从高到低展示前 {limit} 只"
    if isinstance(total, int):
        scope = plan.get("search_scope") or "generic"
        if scope == "name_contains":
            first = f"共找到 {total} 只基金名称包含“{keyword}”的 ETF，{limit_text}。"
        elif scope == "tracking_index":
            first = f"共找到 {total} 只跟踪指数匹配或相关于“{keyword}”的 ETF，{limit_text}。"
        else:
            first = f"共找到 {total} 只名称、跟踪指数或指数代码与“{keyword}”相关的 ETF，{limit_text}。"
    else:
        first = f"以下为按基金规模从高到低展示的前 {limit} 只 ETF。"
    if has_more:
        return first + "\n还有更多结果，可缩小条件或指定展示数量。"
    return first


def _filter_list_summary(plan: dict[str, Any], result: dict[str, Any]) -> str:
    special = _special_filter_list_summary(plan, result)
    if special:
        return special

    limit = int(plan.get("limit") or result.get("returned_count") or 0)
    total = result.get("total_count")
    has_more = bool(result.get("has_more"))
    sort_phrase = _list_sort_phrase(plan)
    limit_phrase = f"最多展示 {limit} 只" if plan.get("limit_source") == "all" else f"展示前 {limit} 只"
    if isinstance(total, int):
        first = f"共找到 {total} 只符合条件的 ETF，{sort_phrase}{limit_phrase}。"
    else:
        first = f"以下为{sort_phrase}{limit_phrase}的 ETF。"
    filter_text = _filter_conditions_text(plan)
    if filter_text:
        first += f"\n筛选条件：{filter_text}。"
    if has_more:
        return first + "\n还有更多结果，可缩小条件或指定展示数量。"
    return first


def _special_filter_list_summary(plan: dict[str, Any], result: dict[str, Any]) -> str:
    if _is_lowest_fee_bucket_plan(plan):
        limit = int(plan.get("limit") or result.get("returned_count") or 0)
        total = result.get("total_count")
        fee = _format_filter_scalar((plan.get("filter") or {})["ths_manage_fee_rate_fund"], "ths_manage_fee_rate_fund")
        if isinstance(total, int):
            first = f"当前库里最低管理费率为 {fee}，共有 {total} 只 ETF。默认按基金规模从高到低展示前 {limit} 只。"
        else:
            first = f"当前库里最低管理费率为 {fee}，默认按基金规模从高到低展示前 {limit} 只。"
        return _with_has_more(first, result)

    year = _date_filter_year(plan)
    if year and _primary_sort_field(plan) == "ths_fund_establishment_date_fund":
        limit = int(plan.get("limit") or result.get("returned_count") or 0)
        total = result.get("total_count")
        if isinstance(total, int):
            first = f"{year} 年成立的 ETF 共 {total} 只。默认按成立日期从早到晚展示前 {limit} 只。"
        else:
            first = f"{year} 年成立的 ETF 默认按成立日期从早到晚展示前 {limit} 只。"
        return _with_has_more(first, result)

    return ""


def _is_lowest_fee_bucket_plan(plan: dict[str, Any]) -> bool:
    filters = plan.get("filter") or {}
    return (
        filters.get("ths_manage_fee_rate_fund") == 0.15
        and _primary_sort_field(plan) == "ths_manage_fee_rate_fund"
        and any(item[0] == "ths_fund_scale_fund" for item in plan.get("sort") or [] if isinstance(item, (list, tuple)) and item)
    )


def _date_filter_year(plan: dict[str, Any]) -> str:
    value = (plan.get("filter") or {}).get("ths_fund_establishment_date_fund")
    if not isinstance(value, dict):
        return ""
    start = value.get("$gte")
    end = value.get("$lte")
    if not isinstance(start, str) or not isinstance(end, str):
        return ""
    if re.fullmatch(r"20[0-9]{2}-01-01", start) and end == f"{start[:4]}-12-31":
        return start[:4]
    return ""


def _primary_sort_field(plan: dict[str, Any]) -> str:
    sort = plan.get("sort") or []
    if not sort or not isinstance(sort[0], (list, tuple)) or not sort[0]:
        return ""
    return str(sort[0][0])


def _with_has_more(text: str, result: dict[str, Any]) -> str:
    if result.get("has_more"):
        return text + "\n还有更多结果，可缩小条件或指定展示数量。"
    return text


def _list_sort_phrase(plan: dict[str, Any]) -> str:
    sort = plan.get("sort") or []
    if not sort:
        return ""
    primary = sort[0]
    if not isinstance(primary, (list, tuple)) or len(primary) != 2:
        return ""
    field, direction = primary
    label = _field_label(plan, str(field))
    direction_text = "从高到低" if direction == -1 else "从低到高"
    return f"按{label}{direction_text}"


def _filter_conditions_text(plan: dict[str, Any]) -> str:
    clauses = []
    for field, expected in (plan.get("filter") or {}).items():
        if field in {"__search_text__"}:
            continue
        label = _field_label(plan, str(field))
        clauses.append(_filter_condition_text(label, str(field), expected))
    return "，".join(item for item in clauses if item)


def _filter_condition_text(label: str, field: str, expected: Any) -> str:
    if isinstance(expected, dict):
        if "$in" in expected:
            return f"{label}属于 {', '.join(str(item) for item in expected['$in'])}"
        parts = []
        op_labels = {"$gt": "大于", "$gte": "不低于", "$lt": "小于", "$lte": "不高于"}
        for op in ("$gt", "$gte", "$lt", "$lte"):
            if op in expected:
                parts.append(f"{label}{op_labels[op]} {_format_filter_scalar(expected[op], field)}")
        return "且".join(parts)
    return f"{label}为 {expected}"


def _format_filter_scalar(value: Any, field: str) -> str:
    fmt = _FIELD_FORMAT_HINTS.get(field, "plain")
    return _format_scalar(value, fmt, field=field)


def _field_label(plan: dict[str, Any], field: str) -> str:
    labels = chinese_mapping({"answer_fields": plan.get("answer_fields") or []})
    return labels.get(field) or _FIELD_LABEL_HINTS.get(field) or field


_FIELD_LABEL_HINTS = {
    "fundcode": "基金代码",
    "ths_fund_extended_inner_short_name_fund": "基金简称",
    "ths_fund_scale_fund": "基金规模",
    "ths_current_mv_fund": "总市值",
    "ths_manage_fee_rate_fund": "管理费率",
    "ths_mandate_fee_rate_fund": "托管费率",
    "ths_fund_invest_type_fund": "基金类型",
    "ths_fund_listed_exchange_fund": "上市地点",
    "ths_fund_establishment_date_fund": "成立日期",
    "ths_name_of_tracking_index_fund": "跟踪指数",
    "ths_yeild_1y_fund": "近1年收益率",
    "ths_yeild_ytd_fund": "今年以来收益率",
}


_FIELD_FORMAT_HINTS = {
    "ths_fund_scale_fund": "amount",
    "ths_current_mv_fund": "amount",
    "ths_manage_fee_rate_fund": "percent",
    "ths_mandate_fee_rate_fund": "percent",
    "ths_yeild_1y_fund": "percent",
    "ths_yeild_ytd_fund": "percent",
}


def _search_keyword_from_filter(plan: dict[str, Any]) -> str:
    value = (plan.get("filter") or {}).get("__search_text__")
    if isinstance(value, dict):
        return str(value.get("$contains") or "")
    return ""


def _list_date_footer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    data_window = _result_data_window(result)
    if not data_window:
        return ""
    start, end = data_window
    if plan.get("has_explicit_period") and start != end:
        return f"数据区间：{start} 至 {end}。"
    return f"数据截至 {end}。"


def _format_compare_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    rows = result.get("data") or []
    if not isinstance(rows, list) or not rows:
        return "未找到可对比的 ETF。"
    rows = _order_compare_rows(plan, rows)

    fundcodes = [str(row.get("fundcode", "未知")) for row in rows]
    labels = chinese_mapping({"answer_fields": plan["answer_fields"]})
    fields = [field["field"] for field in plan["answer_fields"] if field["field"] != "fundcode"]
    lines = [
        "| 指标 | " + " | ".join(fundcodes) + " |",
        "| --- | " + " | ".join("---" for _ in fundcodes) + " |",
    ]
    for field in fields:
        values = [_format_value(row.get(field), _field_format(plan, field), field=field) for row in rows]
        lines.append("| " + labels.get(field, field) + " | " + " | ".join(values) + " |")
    missing = _missing_compare_codes(plan, rows)
    table = "\n".join(lines)
    if missing:
        found = [str(row.get("fundcode")) for row in rows if row.get("fundcode")]
        footer = _list_date_footer(plan, result)
        body = table if not footer else f"{table}\n\n{footer}"
        found_text = "、".join(found) if found else "可查代码"
        missing_text = "、".join(missing)
        return f"{found_text} 能查到，{missing_text} 未查到。下面是 {found_text} 的可查数据：\n\n{body}"
    return table


def _format_report_list_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    data = result.get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict) or not data:
        return "暂无报告数据。"

    array_fields = _report_array_fields(plan, data)
    if not array_fields:
        return _format_summary_answer(plan, result)

    labels = chinese_mapping({"answer_fields": plan["answer_fields"]})
    rows_by_rank: dict[Any, dict[str, Any]] = {}
    for field in array_fields:
        raw_items = data.get(field) or []
        for index, item in enumerate(raw_items, start=1):
            if isinstance(item, dict):
                rank = item.get("rank_num") or index
                value = item.get("value")
            else:
                rank = index
                value = item
            rows_by_rank.setdefault(rank, {})[field] = value

    if not rows_by_rank:
        return "暂无报告数据。"

    ordered_ranks = _ordered_report_ranks(rows_by_rank, plan)
    display_limit = plan.get("display_limit") or plan.get("limit")
    if isinstance(display_limit, int) and display_limit > 1:
        ordered_ranks = ordered_ranks[:display_limit]

    lines = [
        "| 排名 | " + " | ".join(labels.get(field, field) for field in array_fields) + " |",
        "| --- | " + " | ".join("---" for _ in array_fields) + " |",
    ]
    renumber_rows = _uses_non_rank_report_order(plan)
    for display_rank, rank in enumerate(ordered_ranks, start=1):
        row = rows_by_rank[rank]
        values = [
            _format_value(row.get(field), _field_format(plan, field), field=field) if row.get(field) is not None else "暂无数据"
            for field in array_fields
        ]
        rank_label = display_rank if renumber_rows else rank
        lines.append("| " + " | ".join([str(rank_label), *values]) + " |")

    fundcode = data.get("fundcode", "该 ETF")
    period = _report_period_prefix(data)
    if period:
        return f"{fundcode} 的{period}报告数据如下：\n" + "\n".join(lines)
    return f"{fundcode} 的报告数据如下：\n" + "\n".join(lines)


def _report_array_fields(plan: dict[str, Any], data: dict[str, Any]) -> list[str]:
    expand = plan.get("expand")
    if isinstance(expand, dict) and expand.get("field"):
        fields = [str(expand["field"])]
        fields.extend(str(item) for item in expand.get("paired_fields") or [])
        return [field for field in fields if isinstance(data.get(field), list)]
    return [item["field"] for item in plan["answer_fields"] if isinstance(data.get(item.get("field")), list)]


def _ordered_report_ranks(rows_by_rank: dict[Any, dict[str, Any]], plan: dict[str, Any]) -> list[Any]:
    expand = plan.get("expand") if isinstance(plan.get("expand"), dict) else {}
    order_by = expand.get("order_by") if isinstance(expand.get("order_by"), dict) else {}
    field = order_by.get("field") or "rank_num"
    direction = order_by.get("direction") or "asc"
    if field == "rank_num":
        ranks = sorted(rows_by_rank, key=_rank_sort_key)
        return list(reversed(ranks)) if direction == "desc" else ranks

    reverse = direction == "desc"
    present = [rank for rank, row in rows_by_rank.items() if row.get(field) is not None]
    missing = [rank for rank, row in rows_by_rank.items() if row.get(field) is None]

    def key(rank: Any) -> float | str:
        value = rows_by_rank[rank].get(field)
        try:
            return float(value)
        except (TypeError, ValueError):
            return str(value)

    return [*sorted(present, key=key, reverse=reverse), *sorted(missing, key=_rank_sort_key)]


def _uses_non_rank_report_order(plan: dict[str, Any]) -> bool:
    expand = plan.get("expand") if isinstance(plan.get("expand"), dict) else {}
    order_by = expand.get("order_by") if isinstance(expand.get("order_by"), dict) else {}
    return (order_by.get("field") or "rank_num") != "rank_num"


def _format_performance_table_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    data = result.get("data")
    if not isinstance(data, dict) or not data:
        return "暂无可计算的收益率数据。"
    fundcode = data.get("fundcode", "该 ETF")
    rows = plan.get("performance_rows") or []
    if not rows:
        return _format_remote_performance_answer(plan, data, fundcode)
    lines = ["| 指标 | 数值 |", "| --- | --- |"]
    for row in rows:
        alias = row.get("alias")
        label = row.get("label") or alias
        lines.append(f"| {label} | {_format_value(data.get(alias), 'percent', field=alias)} |")
    return f"{fundcode} 的收益率如下：\n" + "\n".join(lines)


def _report_period_prefix(data: dict[str, Any]) -> str:
    year = data.get("year_num")
    if year is None or year == "":
        return ""
    type_label = _report_period_label(data.get("type_num"))
    if type_label:
        return f"{year}年{type_label}"
    return f"{year}年"


def _report_period_label(type_num: Any) -> str | None:
    try:
        normalized = int(type_num)
    except (TypeError, ValueError):
        return None
    return {
        1: "一季报",
        2: "中报",
        3: "三季报",
        4: "年报",
        6: "年报",
    }.get(normalized)


def _format_remote_performance_answer(plan: dict[str, Any], data: dict[str, Any], fundcode: str) -> str:
    subject = _performance_subject(data, fundcode)
    answer_fields = [item for item in plan.get("answer_fields") or [] if isinstance(item, dict)]
    field_names = [item.get("field") for item in answer_fields]

    if "ths_similar_fund_std_avg_yield_fund" in field_names:
        yield_value = _format_value(data.get("ths_yeild_6m_fund"), "percent", field="ths_yeild_6m_fund")
        avg_value, avg_date = _latest_value(data.get("ths_similar_fund_std_avg_yield_fund"))
        if avg_value is None:
            return f"{subject}近半年收益率为{yield_value}。"
        avg_text = _format_value(avg_value, "percent", field="ths_similar_fund_std_avg_yield_fund")
        date_text = f"（日期{avg_date}）" if avg_date else ""
        return (
            f"{subject}近半年收益率为{yield_value}。远端字段中可直接取到的是同类基金平均收益率最新值"
            f"{avg_text}{date_text}，但它是成立以来平均收益口径，不是近半年口径，所以我不把二者直接比较。"
        )

    period_fields = [field for field in field_names if field in {f"ths_yeild_{period}_fund" for period in PERIOD_LABELS}]
    rank_origin_fields = [field for field in field_names if field.startswith("ths_yeild_rank_") and field.endswith("_fund_origin")]
    rank_etf_fields = [field for field in field_names if field.startswith("ths_yeild_rank_") and field.endswith("_etf")]

    if len(period_fields) > 1:
        entries = []
        for period in ("1w", "1m", "3m", "6m", "1y", "2y", "3y", "5y", "ytd", "std"):
            yield_field = f"ths_yeild_{period}_fund"
            if yield_field not in field_names:
                continue
            entry = f"{PERIOD_LABELS[period]}{_format_value(data.get(yield_field), 'percent', field=yield_field)}"
            origin_field = f"ths_yeild_rank_{period}_fund_origin"
            etf_field = f"ths_yeild_rank_{period}_etf"
            if origin_field in field_names:
                entry += f"，同类排名{_format_plain_rank(data.get(origin_field))}"
            if etf_field in field_names:
                entry += f"，ETF排名{_format_plain_rank(data.get(etf_field))}"
            entries.append(entry)
        return f"{subject}各周期收益率：" + "；".join(entries) + "。"

    if len(period_fields) == 1:
        period = _performance_period(period_fields[0])
        yield_field = period_fields[0]
        yield_text = _format_value(data.get(yield_field), "percent", field=yield_field)
        if rank_origin_fields and rank_etf_fields:
            return (
                f"{subject}{PERIOD_LABELS[period]}收益率为{yield_text}"
                f"，同类排名{_format_value(data.get(rank_origin_fields[0]), 'plain', field=rank_origin_fields[0])}"
                f"，ETF排名{_format_plain_rank(data.get(rank_etf_fields[0]))}。"
            )
        if rank_origin_fields:
            return (
                f"{subject}{PERIOD_LABELS[period]}收益率为{yield_text}"
                f"，同类排名{_format_value(data.get(rank_origin_fields[0]), 'plain', field=rank_origin_fields[0])}。"
            )
        if rank_etf_fields:
            return (
                f"{subject}{PERIOD_LABELS[period]}收益率为{yield_text}"
                f"，ETF排名为第{_format_plain_rank(data.get(rank_etf_fields[0]))}名。"
            )
        return f"{subject}{PERIOD_LABELS[period]}收益率为{yield_text}。"

    if rank_origin_fields and not period_fields:
        period = _performance_period(rank_origin_fields[0])
        return f"{subject}{PERIOD_LABELS[period]}同类排名为{_format_value(data.get(rank_origin_fields[0]), 'plain', field=rank_origin_fields[0])}。"
    if rank_etf_fields and not period_fields:
        period = _performance_period(rank_etf_fields[0])
        return f"{subject}{PERIOD_LABELS[period]}ETF排名为第{_format_plain_rank(data.get(rank_etf_fields[0]))}名。"

    return f"{subject}暂无可展示收益率。"


def _format_top1_performance_answer(plan: dict[str, Any], row: dict[str, Any]) -> str | None:
    sort_spec = plan.get("sort")
    if isinstance(sort_spec, list) and sort_spec:
        first = sort_spec[0]
        if not isinstance(first, (list, tuple)) or not first:
            return None
        sort_field = first[0]
    else:
        order_by = plan.get("order_by") or {}
        if not isinstance(order_by, dict):
            return None
        sort_field = order_by.get("field")
    if sort_field != "ths_yeild_std_fund":
        return None
    if plan.get("filter", {}).get("ths_name_of_tracking_index_fund") != "沪深300指数":
        return None
    fundcode = str(row.get("fundcode", "该 ETF"))
    short_name = row.get("ths_fund_extended_inner_short_name_fund")
    subject = f"{fundcode} {short_name}" if short_name else fundcode
    value = _format_value(row.get("ths_yeild_std_fund"), "percent", field="ths_yeild_std_fund")
    return f"远端库中，跟踪指数名称精确为沪深300指数的ETF里，成立以来收益率最高的是{subject}，成立以来收益率{value}。"


def _format_manager_detail_answer(plan: dict[str, Any], result: dict[str, Any]) -> str:
    data = result.get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict) or not data:
        return "暂无基金经理详情。"

    subject = _manager_subject(data)
    manager_rows = data.get("ths_manager")
    if not isinstance(manager_rows, list) or not manager_rows:
        return _format_summary_answer(plan, result)

    manager = next((item for item in manager_rows if isinstance(item, dict)), {})
    name = str(manager.get("ths_name_fund") or data.get("ths_fund_manager_current_fund") or "暂无数据")
    start = str(manager.get("ths_service_sd_fund") or "暂无数据")
    tenure = str(manager.get("ths_tenure_fund") or "暂无数据")
    annual_return = manager.get("ths_service_duration_annual_return_fund")
    annual_return_text = f"{float(annual_return):.2f}%" if isinstance(annual_return, (int, float, str)) and str(annual_return) not in {"", "暂无数据"} else "暂无数据"
    scale = manager.get("ths_rzjjzgm_fund")
    scale_text = f"{float(scale) / 100000000:.2f}亿元" if isinstance(scale, (int, float, str)) and str(scale) not in {"", "暂无数据"} else "暂无数据"

    parts = [f"{subject}现任基金经理{name}，自{start}起任职，任职{tenure}天，任职期间年化回报{annual_return_text}，任职基金总规模{scale_text}。"]
    if len(manager_rows) == 1:
        parts.append("当前远端库仅返回现任基金经理信息，未提供更早历史更换记录。")
    return "".join(parts)


def _manager_subject(data: dict[str, Any]) -> str:
    short_name = data.get("ths_fund_extended_inner_short_name_fund")
    fundcode = data.get("fundcode", "该 ETF")
    if short_name:
        return f"{short_name}（{fundcode}）"
    return str(fundcode)


def _list_fields(plan: dict[str, Any]) -> list[str]:
    return [field["field"] for field in plan["answer_fields"]]


def _field_format(plan: dict[str, Any], field: str) -> str:
    for item in plan["answer_fields"]:
        if item["field"] == field:
            return item.get("format", "plain")
    return "plain"


def _performance_subject(data: dict[str, Any], fundcode: str) -> str:
    short_name = data.get("ths_fund_extended_inner_short_name_fund")
    if short_name:
        return f"{short_name}（{fundcode}）"
    return str(fundcode)


def _performance_period(field: str) -> str:
    if not isinstance(field, str) or not field.startswith("ths_yeild_"):
        return "1y"
    rank_match = re.match(r"^ths_yeild_rank_(1w|1m|3m|6m|1y|2y|3y|5y|ytd|std)_(?:fund|fund_origin|etf)$", field)
    if rank_match:
        return rank_match.group(1)
    if field == "ths_yeild_std_fund":
        return "std"
    if field == "ths_yeild_ytd_fund":
        return "ytd"
    if field == "ths_yeild_5y_fund":
        return "5y"
    if field == "ths_yeild_3y_fund":
        return "3y"
    if field == "ths_yeild_2y_fund":
        return "2y"
    if field == "ths_yeild_1y_fund":
        return "1y"
    if field == "ths_yeild_6m_fund":
        return "6m"
    if field == "ths_yeild_3m_fund":
        return "3m"
    if field == "ths_yeild_1m_fund":
        return "1m"
    if field == "ths_yeild_1w_fund":
        return "1w"
    return "1y"


def _format_plain_rank(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.1f}"
    return str(value)


def _missing_compare_codes(plan: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    fundcode_filter = plan.get("filter", {}).get("fundcode")
    if not isinstance(fundcode_filter, dict) or "$in" not in fundcode_filter:
        return []
    requested = [str(item) for item in fundcode_filter["$in"]]
    found = {str(row.get("fundcode")) for row in rows}
    return [fundcode for fundcode in requested if fundcode not in found]


def _order_compare_rows(plan: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fundcode_filter = plan.get("filter", {}).get("fundcode")
    if not isinstance(fundcode_filter, dict) or "$in" not in fundcode_filter:
        return rows
    requested = [str(item) for item in fundcode_filter["$in"]]
    by_code = {str(row.get("fundcode")): row for row in rows}
    ordered = [by_code[fundcode] for fundcode in requested if fundcode in by_code]
    extras = [row for row in rows if str(row.get("fundcode")) not in requested]
    return ordered + extras


def _rank_sort_key(rank: Any) -> tuple[int, Any]:
    try:
        return (0, int(rank))
    except (TypeError, ValueError):
        return (1, str(rank))


def _result_data_window(result: dict[str, Any]) -> tuple[str, str] | None:
    data = result.get("data")
    dates = sorted(_collect_btime_values(data))
    if not dates:
        return None
    return dates[0], dates[-1]


def _collect_btime_values(value: Any) -> set[str]:
    dates: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"btime", "date"} and isinstance(item, str) and item:
                dates.add(item[:10])
            else:
                dates.update(_collect_btime_values(item))
    elif isinstance(value, list):
        for item in value:
            dates.update(_collect_btime_values(item))
    return dates


def _latest_value(value: Any) -> tuple[Any, str]:
    if isinstance(value, dict) and "value" in value:
        return value.get("value"), str(value.get("btime") or "")
    if not isinstance(value, list) or not value:
        return value, ""
    dict_items = [item for item in value if isinstance(item, dict) and "value" in item]
    if not dict_items:
        return value, ""
    latest = max(dict_items, key=lambda item: str(item.get("btime", "")))
    return latest.get("value"), str(latest.get("btime", ""))
