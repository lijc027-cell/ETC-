from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .candidates import PERIOD_FIELDS


ALLOWED_FORMATS = ("plain", "amount", "percent", "date", "yuan_to_100m", "long_text")
BASE_COLLECTION = "tb_ths_etf_base"


@dataclass(frozen=True)
class FieldSpec:
    field: str
    label: str
    format: str
    selectable: bool = True
    filterable: bool = False
    sortable: bool = False
    filter_operators: tuple[str, ...] = ()
    value_schema: str = "any"
    normalizer: str | None = None
    gate: str = "always"
    semantic_role: str = "semantic"


@dataclass(frozen=True)
class Capability:
    phase: str
    query_mode: str
    intent: str
    collection: str
    output_style: str
    field_profile: str
    fields: tuple[FieldSpec, ...]
    baseline_answer_fields: tuple[str, ...]
    gate: str = "always"


FIELD_SPECS: dict[str, FieldSpec] = {
    "fundcode": FieldSpec("fundcode", "基金代码", "plain", filterable=True, sortable=True, filter_operators=("eq", "in"), semantic_role="identity"),
    "ths_fund_extended_inner_short_name_fund": FieldSpec("ths_fund_extended_inner_short_name_fund", "基金简称", "plain", semantic_role="context"),
    "ths_fund_scale_fund": FieldSpec("ths_fund_scale_fund", "基金规模", "amount", filterable=True, sortable=True, filter_operators=("eq", "gt", "gte", "lt", "lte"), value_schema="amount"),
    "ths_manage_fee_rate_fund": FieldSpec("ths_manage_fee_rate_fund", "管理费率", "percent", filterable=True, sortable=True, filter_operators=("eq", "gt", "gte", "lt", "lte"), value_schema="percent"),
    "ths_mandate_fee_rate_fund": FieldSpec("ths_mandate_fee_rate_fund", "托管费率", "percent", sortable=True),
    "ths_yeild_1w_fund": FieldSpec("ths_yeild_1w_fund", "近1周收益率", "percent", filterable=True, sortable=True, filter_operators=("eq", "gt", "gte", "lt", "lte"), value_schema="percent"),
    "ths_yeild_1m_fund": FieldSpec("ths_yeild_1m_fund", "近1月收益率", "percent", filterable=True, sortable=True, filter_operators=("eq", "gt", "gte", "lt", "lte"), value_schema="percent"),
    "ths_yeild_3m_fund": FieldSpec("ths_yeild_3m_fund", "近3月收益率", "percent", filterable=True, sortable=True, filter_operators=("eq", "gt", "gte", "lt", "lte"), value_schema="percent"),
    "ths_yeild_6m_fund": FieldSpec("ths_yeild_6m_fund", "近6月收益率", "percent", filterable=True, sortable=True, filter_operators=("eq", "gt", "gte", "lt", "lte"), value_schema="percent"),
    "ths_yeild_1y_fund": FieldSpec("ths_yeild_1y_fund", "近1年收益率", "percent", filterable=True, sortable=True, filter_operators=("eq", "gt", "gte", "lt", "lte"), value_schema="percent"),
    "ths_yeild_2y_fund": FieldSpec("ths_yeild_2y_fund", "近2年收益率", "percent", sortable=True),
    "ths_yeild_3y_fund": FieldSpec("ths_yeild_3y_fund", "近3年收益率", "percent", sortable=True),
    "ths_yeild_5y_fund": FieldSpec("ths_yeild_5y_fund", "近5年收益率", "percent", sortable=True),
    "ths_yeild_ytd_fund": FieldSpec("ths_yeild_ytd_fund", "今年以来收益率", "percent", filterable=True, sortable=True, filter_operators=("eq", "gt", "gte", "lt", "lte"), value_schema="percent"),
    "ths_yeild_std_fund": FieldSpec("ths_yeild_std_fund", "成立以来收益率", "percent", filterable=True, sortable=True, filter_operators=("eq", "gt", "gte", "lt", "lte"), value_schema="percent"),
    "ths_yeild_rank_1w_fund_origin": FieldSpec("ths_yeild_rank_1w_fund_origin", "近1周同类排名", "plain"),
    "ths_yeild_rank_1m_fund_origin": FieldSpec("ths_yeild_rank_1m_fund_origin", "近1月同类排名", "plain"),
    "ths_yeild_rank_3m_fund_origin": FieldSpec("ths_yeild_rank_3m_fund_origin", "近3月同类排名", "plain"),
    "ths_yeild_rank_6m_fund_origin": FieldSpec("ths_yeild_rank_6m_fund_origin", "近半年同类排名", "plain"),
    "ths_yeild_rank_1y_fund_origin": FieldSpec("ths_yeild_rank_1y_fund_origin", "近1年同类排名", "plain"),
    "ths_yeild_rank_2y_fund_origin": FieldSpec("ths_yeild_rank_2y_fund_origin", "近2年同类排名", "plain"),
    "ths_yeild_rank_3y_fund_origin": FieldSpec("ths_yeild_rank_3y_fund_origin", "近3年同类排名", "plain"),
    "ths_yeild_rank_5y_fund_origin": FieldSpec("ths_yeild_rank_5y_fund_origin", "近5年同类排名", "plain"),
    "ths_yeild_rank_ytd_fund_origin": FieldSpec("ths_yeild_rank_ytd_fund_origin", "今年以来同类排名", "plain"),
    "ths_yeild_rank_std_fund_origin": FieldSpec("ths_yeild_rank_std_fund_origin", "成立以来同类排名", "plain"),
    "ths_yeild_rank_1w_etf": FieldSpec("ths_yeild_rank_1w_etf", "近1周 ETF 排名", "plain"),
    "ths_yeild_rank_1m_etf": FieldSpec("ths_yeild_rank_1m_etf", "近1月 ETF 排名", "plain"),
    "ths_yeild_rank_3m_etf": FieldSpec("ths_yeild_rank_3m_etf", "近3月 ETF 排名", "plain"),
    "ths_yeild_rank_6m_etf": FieldSpec("ths_yeild_rank_6m_etf", "近半年 ETF 排名", "plain"),
    "ths_yeild_rank_1y_etf": FieldSpec("ths_yeild_rank_1y_etf", "近1年 ETF 排名", "plain"),
    "ths_yeild_rank_2y_etf": FieldSpec("ths_yeild_rank_2y_etf", "近2年 ETF 排名", "plain"),
    "ths_yeild_rank_3y_etf": FieldSpec("ths_yeild_rank_3y_etf", "近3年 ETF 排名", "plain"),
    "ths_yeild_rank_5y_etf": FieldSpec("ths_yeild_rank_5y_etf", "近5年 ETF 排名", "plain"),
    "ths_yeild_rank_ytd_etf": FieldSpec("ths_yeild_rank_ytd_etf", "今年以来 ETF 排名", "plain"),
    "ths_yeild_rank_std_etf": FieldSpec("ths_yeild_rank_std_etf", "成立以来 ETF 排名", "plain"),
    "ths_name_of_tracking_index_fund": FieldSpec("ths_name_of_tracking_index_fund", "跟踪指数名称", "plain", filterable=True, filter_operators=("eq",), value_schema="string"),
    "ths_tracking_index_code_fund": FieldSpec("ths_tracking_index_code_fund", "跟踪指数代码", "plain"),
    "ths_fund_listed_exchange_fund": FieldSpec("ths_fund_listed_exchange_fund", "上市地点", "plain", filterable=True, filter_operators=("eq",), value_schema="enum"),
    "ths_fund_invest_type_fund": FieldSpec("ths_fund_invest_type_fund", "基金投资类型", "plain", filterable=True, filter_operators=("eq",), value_schema="enum"),
    "ths_fund_manager_current_fund": FieldSpec("ths_fund_manager_current_fund", "基金经理(现任)", "plain"),
    "ths_fund_supervisor_fund": FieldSpec("ths_fund_supervisor_fund", "基金管理人", "plain"),
    "ths_accum_dividend_total_amt_fund": FieldSpec("ths_accum_dividend_total_amt_fund", "累计分红总额", "amount", sortable=True),
    "ths_accum_dividend_times_fund": FieldSpec("ths_accum_dividend_times_fund", "累计分红次数", "plain", sortable=True),
    "ths_current_mv_fund": FieldSpec("ths_current_mv_fund", "总市值", "amount", sortable=True),
    "ths_unit_nv_fund": FieldSpec("ths_unit_nv_fund", "单位净值", "plain"),
    "ths_unit_nvg_rate_fund": FieldSpec("ths_unit_nvg_rate_fund", "单位净值增长率", "percent", sortable=True),
    "ths_fund_shares_fund": FieldSpec("ths_fund_shares_fund", "基金份额", "plain", sortable=True),
    "ths_fund_establishment_date_fund": FieldSpec("ths_fund_establishment_date_fund", "成立日期", "date", filterable=True, sortable=True, filter_operators=("eq", "gte", "lte", "between"), value_schema="date", normalizer="date"),
    "ths_perf_comparative_benchmark_fund": FieldSpec("ths_perf_comparative_benchmark_fund", "业绩比较基准", "plain"),
    "ths_pur_and_redemp_status_fund": FieldSpec("ths_pur_and_redemp_status_fund", "申购赎回状态", "plain"),
    "ths_etf_to_code_fund": FieldSpec("ths_etf_to_code_fund", "ETF关联联接基金代码", "plain"),
    "ths_manager": FieldSpec("ths_manager", "基金经理详情", "plain", selectable=False, gate="blocked"),
    "ths_invest_objective_fund": FieldSpec("ths_invest_objective_fund", "投资目标", "long_text"),
    "ths_invest_socpe_fund": FieldSpec("ths_invest_socpe_fund", "投资范围", "long_text"),
    "ths_invest_philosophy_fund": FieldSpec("ths_invest_philosophy_fund", "投资理念", "long_text"),
    "ths_invest_strategy_fund": FieldSpec("ths_invest_strategy_fund", "投资策略", "long_text"),
    "ths_risk_return_characteristics_fund": FieldSpec("ths_risk_return_characteristics_fund", "风险收益特征", "long_text"),
    "__search_text__": FieldSpec("__search_text__", "全文搜索", "plain", selectable=False, filterable=True, filter_operators=("contains",), value_schema="text", semantic_role="semantic"),
}

BLOCKED_V3_2_FIELDS = {
    "ths_fund_establishment_date_fund",
    "ths_perf_comparative_benchmark_fund",
    "ths_pur_and_redemp_status_fund",
    "ths_etf_to_code_fund",
    "ths_manager",
    "ths_invest_objective_fund",
    "ths_invest_socpe_fund",
    "ths_invest_philosophy_fund",
    "ths_invest_strategy_fund",
    "ths_risk_return_characteristics_fund",
}

LIST_BASELINE_FIELDS = (
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
)

COMPARE_FIELDS = (
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_scale_fund",
    "ths_manage_fee_rate_fund",
    "ths_mandate_fee_rate_fund",
    "ths_yeild_ytd_fund",
    "ths_yeild_1y_fund",
    "ths_name_of_tracking_index_fund",
)

FILTER_FIELDS = (
    *LIST_BASELINE_FIELDS,
    "ths_fund_listed_exchange_fund",
    "ths_fund_invest_type_fund",
    "ths_name_of_tracking_index_fund",
    "ths_yeild_1m_fund",
    "ths_yeild_3m_fund",
    "ths_yeild_6m_fund",
    "ths_yeild_1y_fund",
    "ths_yeild_ytd_fund",
    "ths_yeild_std_fund",
)

BASIC_INFO_EXTENDED_FIELDS = (
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_fund_establishment_date_fund",
    "ths_fund_listed_exchange_fund",
    "ths_perf_comparative_benchmark_fund",
    "ths_pur_and_redemp_status_fund",
    "ths_etf_to_code_fund",
)

INVESTMENT_PROFILE_FIELDS = (
    "fundcode",
    "ths_fund_extended_inner_short_name_fund",
    "ths_invest_objective_fund",
    "ths_invest_socpe_fund",
    "ths_invest_philosophy_fund",
    "ths_invest_strategy_fund",
    "ths_risk_return_characteristics_fund",
)

FILTER_FIELDS_V3_2 = (
    *FILTER_FIELDS,
    "ths_fund_establishment_date_fund",
)

COMPOSITE_SINGLE_FIELDS = tuple(
    dict.fromkeys(
        (
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_fund_manager_current_fund",
            "ths_fund_supervisor_fund",
            "ths_fund_establishment_date_fund",
            "ths_fund_listed_exchange_fund",
            "ths_perf_comparative_benchmark_fund",
            "ths_pur_and_redemp_status_fund",
            "ths_etf_to_code_fund",
            "ths_invest_objective_fund",
            "ths_invest_socpe_fund",
            "ths_invest_philosophy_fund",
            "ths_invest_strategy_fund",
            "ths_risk_return_characteristics_fund",
            *PERIOD_FIELDS["std"],
            "ths_accum_dividend_total_amt_fund",
            "ths_accum_dividend_times_fund",
        )
    )
)


def get_capability(query_mode: str, intent: str, phase: str = "v3.1") -> Capability:
    key = (phase, query_mode, intent)
    if key not in _CAPABILITIES:
        raise KeyError(f"unsupported capability: {phase} {query_mode}/{intent}")
    return _CAPABILITIES[key]


def get_selection_context(query_mode: str, intent: str, phase: str = "v3.1") -> dict[str, Any]:
    capability = get_capability(query_mode, intent, phase)
    field_operators = {
        field.field: list(_field_operators(field))
        for field in capability.fields
        if field.filterable or field.filter_operators
    }
    return {
        "field_profile": capability.field_profile,
        "collection": capability.collection,
        "output_style": capability.output_style,
        "gate": capability.gate,
        "selectable_fields": [field.field for field in capability.fields if field.selectable],
        "filterable_fields": [field.field for field in capability.fields if field.filterable],
        "sortable_fields": [field.field for field in capability.fields if field.sortable],
        "field_operators": field_operators,
        "value_schemas": {field.field: field.value_schema for field in capability.fields},
        "normalizers": {field.field: field.normalizer for field in capability.fields if field.normalizer},
        "gates": {field.field: field.gate for field in capability.fields},
        "semantic_roles": {field.field: field.semantic_role for field in capability.fields},
        "allowed_formats": list(ALLOWED_FORMATS),
        "baseline_answer_fields": list(capability.baseline_answer_fields),
        "field_metas": {field.field: {"label": field.label, "format": field.format} for field in capability.fields},
    }


def field_meta(field: str) -> tuple[str, str]:
    spec = FIELD_SPECS.get(field)
    if spec is None:
        return field, "plain"
    return spec.label, spec.format


def all_v3_1_allowed_fields() -> set[str]:
    return all_allowed_fields(phase="v3.1")


def all_v3_2_allowed_fields() -> set[str]:
    return all_allowed_fields(phase="v3.2")


def all_allowed_fields(phase: str) -> set[str]:
    fields: set[str] = {"__search_text__"}
    for key, capability in _CAPABILITIES.items():
        if key[0] != phase:
            continue
        fields.update(field.field for field in capability.fields)
    return fields


def _field_operators(field: FieldSpec) -> tuple[str, ...]:
    if field.filter_operators:
        return field.filter_operators
    if field.filterable:
        return ("eq",)
    return ()


def _fields(names: tuple[str, ...] | list[str]) -> tuple[FieldSpec, ...]:
    return tuple(FIELD_SPECS[name] for name in names)


def _single_capability(
    intent: str,
    fields: tuple[str, ...],
    baseline: tuple[str, ...] | None = None,
    *,
    phase: str = "v3.1",
    gate: str = "always",
) -> Capability:
    return Capability(
        phase=phase,
        query_mode="single",
        intent=intent,
        collection=BASE_COLLECTION,
        output_style="summary",
        field_profile=intent,
        fields=_fields(fields),
        baseline_answer_fields=baseline or fields,
        gate=gate,
    )


def _performance_fields() -> tuple[str, ...]:
    fields = ["fundcode"]
    for period_fields in PERIOD_FIELDS.values():
        fields.extend(period_fields)
    return tuple(dict.fromkeys(fields))


_CAPABILITIES: dict[tuple[str, str, str], Capability] = {
    ("v3.1", "search", "search"): Capability(
        phase="v3.1",
        query_mode="search",
        intent="search",
        collection=BASE_COLLECTION,
        output_style="list",
        field_profile="search_list",
        fields=_fields((*LIST_BASELINE_FIELDS, "__search_text__")),
        baseline_answer_fields=LIST_BASELINE_FIELDS,
    ),
    ("v3.1", "filter", "filter"): Capability(
        phase="v3.1",
        query_mode="filter",
        intent="filter",
        collection=BASE_COLLECTION,
        output_style="list",
        field_profile="filter_list",
        fields=_fields(FILTER_FIELDS),
        baseline_answer_fields=LIST_BASELINE_FIELDS,
    ),
    ("v3.1", "compare", "compare"): Capability(
        phase="v3.1",
        query_mode="compare",
        intent="compare",
        collection=BASE_COLLECTION,
        output_style="compare",
        field_profile="compare_fixed",
        fields=_fields(COMPARE_FIELDS),
        baseline_answer_fields=COMPARE_FIELDS,
    ),
    ("v3.1", "single", "basic_info"): _single_capability(
        "basic_info",
        (
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_name_of_tracking_index_fund",
            "ths_fund_scale_fund",
        ),
    ),
    ("v3.1", "single", "fund_scale"): _single_capability(
        "fund_scale",
        (
            "fundcode",
            "ths_fund_scale_fund",
            "ths_current_mv_fund",
            "ths_unit_nv_fund",
            "ths_unit_nvg_rate_fund",
            "ths_fund_shares_fund",
        ),
        baseline=("fundcode",),
    ),
    ("v3.1", "single", "tracking_index"): _single_capability(
        "tracking_index",
        ("fundcode", "ths_tracking_index_code_fund", "ths_name_of_tracking_index_fund"),
    ),
    ("v3.1", "single", "performance"): _single_capability(
        "performance",
        _performance_fields(),
        baseline=("fundcode",),
    ),
    ("v3.1", "single", "fee"): _single_capability(
        "fee",
        ("fundcode", "ths_manage_fee_rate_fund", "ths_mandate_fee_rate_fund"),
    ),
    ("v3.1", "single", "manager"): _single_capability(
        "manager",
        ("fundcode", "ths_fund_manager_current_fund", "ths_fund_supervisor_fund"),
    ),
    ("v3.1", "single", "fee_and_manager"): _single_capability(
        "fee_and_manager",
        (
            "fundcode",
            "ths_manage_fee_rate_fund",
            "ths_mandate_fee_rate_fund",
            "ths_fund_manager_current_fund",
            "ths_fund_supervisor_fund",
        ),
    ),
    ("v3.1", "single", "dividend"): _single_capability(
        "dividend",
        ("fundcode", "ths_accum_dividend_total_amt_fund", "ths_accum_dividend_times_fund"),
    ),
}

for (phase, query_mode, intent), capability in list(_CAPABILITIES.items()):
    if phase == "v3.1":
        _CAPABILITIES[("v3.2", query_mode, intent)] = replace(capability, phase="v3.2")

_CAPABILITIES[("v3.2", "filter", "filter")] = Capability(
    phase="v3.2",
    query_mode="filter",
    intent="filter",
    collection=BASE_COLLECTION,
    output_style="list",
    field_profile="filter_list",
    fields=_fields(FILTER_FIELDS_V3_2),
    baseline_answer_fields=LIST_BASELINE_FIELDS,
)

_CAPABILITIES[("v3.2", "single", "basic_info_extended")] = _single_capability(
    "basic_info_extended",
    BASIC_INFO_EXTENDED_FIELDS,
    baseline=("fundcode", "ths_fund_extended_inner_short_name_fund"),
    phase="v3.2",
)

_CAPABILITIES[("v3.2", "single", "investment_profile")] = _single_capability(
    "investment_profile",
    INVESTMENT_PROFILE_FIELDS,
    baseline=("fundcode", "ths_fund_extended_inner_short_name_fund"),
    phase="v3.2",
)

_CAPABILITIES[("v3.2", "single", "composite_single")] = _single_capability(
    "composite_single",
    COMPOSITE_SINGLE_FIELDS,
    baseline=("fundcode", "ths_fund_extended_inner_short_name_fund"),
    phase="v3.2",
)

_CAPABILITIES[("v3.2", "single", "manager_detail")] = _single_capability(
    "manager_detail",
    ("fundcode", "ths_fund_extended_inner_short_name_fund", "ths_fund_manager_current_fund", "ths_fund_supervisor_fund"),
    baseline=("fundcode", "ths_fund_extended_inner_short_name_fund"),
    phase="v3.2",
    gate="blocked",
)
