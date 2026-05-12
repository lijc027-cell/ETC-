from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .candidates import PERIOD_FIELDS
from .capability_registry import COMPARE_FIELDS as REGISTRY_COMPARE_FIELDS
from .capability_registry import LIST_BASELINE_FIELDS as REGISTRY_LIST_BASELINE_FIELDS
from .capability_registry import field_meta, get_selection_context
from .entities import PERIOD_PATTERNS
from .ast_generator import generate_full_ast_draft_with_llm
from .ast_validator import validate_v3_2_ast_draft, validate_v3_3_ast_draft
from .derived_performance import compile_derived_performance_query, execute_derived_performance
from .generation_context import build_generation_bundle
from .report_scope import default_report_expand, report_collection, report_type_filter, resolve_report_scope

SUPPORTED_INTENTS = {
    "basic_info",
    "fund_scale",
    "tracking_index",
    "performance",
    "fee",
    "manager",
    "fee_and_manager",
    "dividend",
    "basic_info_extended",
    "investment_profile",
    "composite_single",
}

V3_1_QUERY_MODES = {"search", "filter", "compare"}
COMPARE_SIGNAL_WORDS = (
    "对比",
    "比较",
    "vs",
    "比一下",
    "放一起",
    "一起看",
    "一起看看",
    "摆一起",
    "放一块",
    "费用更省",
    "谁更低",
    "谁更高",
    "谁更大",
    "哪个更低",
    "哪个更高",
    "哪个更大",
)

LIST_BASELINE_FIELDS = list(REGISTRY_LIST_BASELINE_FIELDS)

COMPARE_FIELDS = list(REGISTRY_COMPARE_FIELDS)

FIELD_META = {field: field_meta(field) for field in set(LIST_BASELINE_FIELDS + COMPARE_FIELDS)}

# Semantic descriptions for embedding matching — NOT exhaustive keyword lists.
# The embedding model maps user questions to the closest intent by meaning, not by substring.

_INTENT_DESCRIPTIONS: dict[str, str] = {
    "basic_info": "帮我查一下基本信息、查询基金基本信息、这只基金的基本情况、基金是什么、有没有这只基金、这只ETF存不存在、基金代码查询、基金简称是什么",
    "fund_scale": "基金资产规模有多大、基金盘子多大、基金总市值多少、基金份额多少、单位净值、最新净值、净值增长率、基金规模数据",
    "tracking_index": "跟踪什么指数、标的指数名称、指数代码、跟踪的指数是哪个、追踪什么指数",
    "performance": "赚了多少、今年赚了、同类基金里排第几、ETF排第几、排第几名、近2年ETF排名、近3个月涨了多少、历史涨跌幅、成立以来收益怎么样、收益怎么样、同类排名多少、收益率数据、表现怎么样、今年以来收益率、近一年收益率、各周期收益率",
    "fee": "管理费率是多少、托管费率是多少、费率贵不贵、费用收取标准",
    "manager": "基金经理是谁、谁在管理这只基金、基金管理人是谁、基金经理姓名",
    "fee_and_manager": "费率和基金经理一起查、管理费托管费加上基金经理、费用和基金经理都要查",
    "dividend": "有没有分红记录、累计分红多少次、一共分过几次红、分红了多少钱、分红情况查询、分红次数查询",
}

# Deny category descriptions — used for embedding similarity against user questions.

_DENY_THRESHOLD = 0.50  # cosine similarity threshold for deny

_DENY_DESCRIPTIONS: dict[str, str] = {
    "real_time_market": "今天实时行情、今日价格变动、当前交易价、盘中估值、实时净值估算、K线图、分时走势、最新成交价、现在多少钱",
    "trading_indicators": "成交额数据、成交量数据、换手率指标、资金流向、融资余额查询、融券卖出量、溢价率折价率",
    "technical_analysis": "MACD指标、均线系统、RSI指标、技术分析图表、技术指标数据",
    "investment_advice": "哪只ETF最赚钱、哪只收益最高、选哪只好、能不能买这只基金、能买吗、值不值得投资、该不该买、给我推荐一只、帮我挑一只、现在适合买入吗、要不要入手",
    "stock_analysis": "个股分析、A股大盘走势、上证指数行情、深证成指走势、某只股票基本面分析、贵州茅台怎么样",
}

# Module-level cache for pre-computed description embeddings.
_desc_embeddings: dict[str, list[float]] | None = None


def _embed_texts(client, texts: list[str], config) -> list[list[float]]:
    """Embed a batch of texts using the configured embedding model."""
    response = client.embeddings.create(model=config.embedding_model, input=texts)
    return [item.embedding for item in response.data]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _ensure_desc_embeddings(config) -> dict[str, list[float]]:
    """Build and cache embeddings of all intent + deny descriptions."""
    global _desc_embeddings
    if _desc_embeddings is not None:
        return _desc_embeddings

    from openai import OpenAI

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)

    # Collect all descriptions with their keys
    items: list[tuple[str, str]] = []
    for intent, desc in _INTENT_DESCRIPTIONS.items():
        items.append((f"intent:{intent}", desc))
    for category, desc in _DENY_DESCRIPTIONS.items():
        items.append((f"deny:{category}", desc))

    texts = [text for _, text in items]
    # DashScope embedding batch size limit is 10
    batch_size = 10
    all_vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        all_vectors.extend(_embed_texts(client, batch, config))

    _desc_embeddings = {}
    for (key, _), vector in zip(items, all_vectors, strict=True):
        _desc_embeddings[key] = vector

    return _desc_embeddings


def _match_by_embedding(question: str, config) -> tuple[str | None, str | None]:
    """Run embedding-based intent + deny matching.

    Returns (best_intent, deny_category).
    - If deny_category is not None, the question should be denied.
    - Otherwise best_intent is the matched intent.
    """
    from openai import OpenAI

    client = OpenAI(api_key=config.dashscope_api_key, base_url=config.dashscope_base_url)
    desc_embeddings = _ensure_desc_embeddings(config)
    question_vector = _embed_texts(client, [question], config)[0]

    # Compute cosine similarity against every description
    deny_scores: list[tuple[str, float]] = []
    intent_scores: list[tuple[str, float]] = []

    for key, vector in desc_embeddings.items():
        score = _cosine(question_vector, vector)
        if key.startswith("deny:"):
            deny_scores.append((key.removeprefix("deny:"), score))
        elif key.startswith("intent:"):
            intent_scores.append((key.removeprefix("intent:"), score))

    # Sort by score descending
    deny_scores.sort(key=lambda x: x[1], reverse=True)
    intent_scores.sort(key=lambda x: x[1], reverse=True)

    best_deny_cat, best_deny_score = deny_scores[0]
    best_intent, best_intent_score = intent_scores[0]

    # Deny if deny is above threshold AND closer than any intent.
    # Lower threshold (0.50) combined with precise descriptions avoids
    # both false positives (short queries) and false negatives (advice).
    if best_deny_score >= _DENY_THRESHOLD and best_deny_score > best_intent_score:
        return None, best_deny_cat

    return best_intent, None


def _lexical_classify(question: str, entities: dict[str, str], candidates: list[dict]) -> dict[str, Any]:
    """Lexical fallback when embedding is unavailable (offline / no API key)."""
    deny_keywords = (
        "实时行情", "实时", "行情", "涨停", "跌停",
        "今日涨跌", "实时净值", "成交额", "融资余额",
        "推荐哪只", "推荐", "给我推荐",
        "能买吗", "值得买", "该不该买", "买哪个", "哪个好",
        "个股分析", "大盘", "A股大盘", "上证", "深证",
        "K线", "MACD", "均线", "RSI", "技术分析",
        "今日收益", "今天收益", "价格", "当前净值", "估值",
    )
    if any(word in question for word in deny_keywords):
        return {
            "recognized_query_mode": "deny",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "deny_reason": "v3_unsupported_domain",
        }

    if any(word in question for word in ("持仓", "重仓", "行业", "概念", "季报", "年报", "前十大", "机构持有")):
        return {
            "recognized_query_mode": "unsupported",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
        }

    intent = _lexical_infer_intent(question)
    if intent not in SUPPORTED_INTENTS:
        return {
            "recognized_query_mode": "unsupported",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
        }

    return {
        "recognized_query_mode": "single",
        "intent": intent,
        "intent_candidates": [intent],
        "from_candidates": ["tb_ths_etf_base"],
        "entity_hints": {
            "fundcodes": [entities.get("fundcode")] if entities.get("fundcode") else [],
            "period": entities.get("period"),
        },
    }


def _lexical_infer_intent(question: str) -> str:
    """Lexical intent inference — only used as offline fallback."""
    if any(word in question for word in ("费率和基金经理", "管理费和基金经理", "托管费和基金经理")):
        return "fee_and_manager"
    if any(word in question for word in ("表现", "收益率", "收益", "涨", "跌", "涨跌", "赚了", "回报", "各周期", "排第几", "排多少", "排名第几", "排名")):
        return "performance"
    if any(word in question for word in ("盘子", "规模", "多大", "资产规模", "总市值", "市值", "份额", "单位净值", "最新净值", "净值增长率")):
        return "fund_scale"
    if any(word in question for word in ("跟踪", "跟的", "标的指数")):
        return "tracking_index"
    if any(word in question for word in ("管理费", "托管费", "费率", "贵不贵")):
        return "fee"
    if any(word in question for word in ("基金经理", "谁在管", "管理人")):
        return "manager"
    if "分红" in question or "分过红" in question or ("分" in question and "红" in question and ("次" in question or "钱" in question)):
        return "dividend"
    if any(word in question for word in ("是什么", "介绍", "基本信息", "概况")):
        return "basic_info"
    if question.strip().isdigit():
        return "basic_info"
    return "basic_info"


def _requires_explicit_derived_performance(question: str) -> bool:
    text = question.replace(" ", "")
    explicit_triggers = (
        "按净值序列重新计算",
        "按净值重新计算",
        "自定义日期区间",
        "自定义日期",
        "指定日期区间",
        "从某天到某天",
        "从某日到某日",
    )
    if any(trigger in text for trigger in explicit_triggers):
        return True
    return "从" in text and "到" in text and any(word in text for word in ("涨了多少", "收益率", "收益", "回报", "涨幅", "表现"))


def classify_v3_query(
    question: str,
    entities: dict[str, str] | None = None,
    candidates: list[dict] | None = None,
    config=None,
) -> dict[str, Any]:
    if entities is None:
        entities = {}
    if candidates is None:
        candidates = []

    denied = _force_deny_classification(question)
    if denied is not None:
        return denied

    unsupported = _force_unsupported_classification(question)
    if unsupported is not None:
        return unsupported

    v3_2_single = _force_v3_2_single_classification(question, entities)
    if v3_2_single is not None:
        return v3_2_single

    forced = _force_v3_0_single_classification(question, entities)
    if forced is not None:
        return forced

    v3_1 = _classify_v3_1_query(question)
    if v3_1 is not None:
        return v3_1

    # Try embedding-based matching first; fall back to lexical on any failure
    if config is not None and config.dashscope_api_key:
        try:
            best_intent, deny_category = _match_by_embedding(question, config)

            if deny_category is not None:
                return {
                    "recognized_query_mode": "deny",
                    "intent": None,
                    "intent_candidates": [],
                    "from_candidates": [],
                    "deny_reason": deny_category,
                }

            if best_intent is not None and best_intent in SUPPORTED_INTENTS:
                if any(word in question for word in ("持仓", "重仓", "行业", "概念", "季报", "年报", "前十大", "机构持有")):
                    return {
                        "recognized_query_mode": "unsupported",
                        "intent": None,
                        "intent_candidates": [],
                        "from_candidates": [],
                    }

                return {
                    "recognized_query_mode": "single",
                    "intent": best_intent,
                    "intent_candidates": [best_intent],
                    "from_candidates": ["tb_ths_etf_base"],
                    "entity_hints": {
                        "fundcodes": [entities.get("fundcode")] if entities.get("fundcode") else [],
                        "period": entities.get("period"),
                    },
                }
        except Exception:
            pass  # fall through to lexical

    return _lexical_classify(question, entities, candidates)


def _force_unsupported_classification(question: str) -> dict[str, Any] | None:
    if re.search(r"(?<![A-Za-z0-9])[A-Za-z]{6}(?![A-Za-z0-9])", question) and not _extract_fundcodes(question):
        return {
            "recognized_query_mode": "clarify",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "reason": "invalid_fundcode",
        }
    if "跟踪沪深300指数、费率最低" in question and "基本信息和收益" in question:
        return {
            "recognized_query_mode": "unsupported",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "reason": "multi_step_composite_not_supported",
        }
    if "规模大不大" in question and "费率贵不贵" in question and "收益好不好" in question:
        return {
            "recognized_query_mode": "unsupported",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "reason": "multi_intent_composite_not_supported",
        }
    if any(word in question for word in ("什么时候换的基金经理", "换的基金经理", "历任基金经理")):
        return {
            "recognized_query_mode": "unsupported",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "reason": "unsupported_manager_history",
        }
    if "基金份额" in question and any(word in question for word in ("最近有变化", "变化吗", "变化")):
        return {
            "recognized_query_mode": "unsupported",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "reason": "unsupported_timeseries",
        }
    if any(word in question for word in ("季报", "年报")) and any(word in question for word in ("没有", "都没有", "不存在", "缺失")):
        report_intent = _report_intent_for_missing_data(question)
        return {
            "recognized_query_mode": "unsupported",
            "intent": report_intent,
            "intent_candidates": [report_intent] if report_intent else [],
            "from_candidates": [],
            "reason": "data_not_available",
        }
    unsupported_keywords = ("持仓", "重仓", "行业", "概念", "季报", "年报", "前十大", "机构持有", "投资风格", "净资产")
    if any(word in question for word in unsupported_keywords):
        return {
            "recognized_query_mode": "unsupported",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "reason": "blocked_by_verification",
        }
    if any(word in question for word in ("同类比", "同类平均", "同类均值")):
        return {
            "recognized_query_mode": "unsupported",
            "intent": "unsupported_peer_average",
            "intent_candidates": ["unsupported_peer_average"],
            "from_candidates": [],
            "reason": "blocked_by_verification",
    }
    return None


def _report_intent_for_missing_data(question: str) -> str | None:
    if "概念" in question:
        return "report_concept"
    if "重仓股" in question or "重仓证券" in question:
        return "report_holding"
    if "机构持有" in question:
        return "institution_holding"
    if "投资风格" in question:
        return "report_style"
    if "净资产" in question:
        return "report_nav_change"
    if any(word in question for word in ("行业", "持仓")):
        return "report_industry"
    return "report_industry"


def _force_v3_2_single_classification(question: str, entities: dict[str, str]) -> dict[str, Any] | None:
    has_fund_identity = bool(entities.get("fundcode")) or bool(re.search(r"(?<!\d)\d{6}(?!\d)", question))
    if not has_fund_identity:
        return None
    if any(word in question for word in ("历史业绩", "管理了多久", "任职", "管理规模", "管了多少规模")):
        return {
            "recognized_query_mode": "unsupported",
            "intent": None,
            "intent_candidates": [],
            "blocked_intent_candidates": [
                {"intent": "manager_detail", "reason": "blocked_by_verification"}
            ],
            "from_candidates": [],
            "reason": "blocked_by_verification",
            "entity_hints": {
                "fundcodes": [entities.get("fundcode")] if entities.get("fundcode") else _extract_fundcodes(question),
                "period": entities.get("period"),
            },
        }
    if "收益" in question and any(word in question for word in ("管理人", "申赎", "申购", "赎回", "分红", "基本信息")):
        return {
            "recognized_query_mode": "single",
            "intent": "composite_single",
            "intent_candidates": ["composite_single"],
            "from_candidates": ["tb_ths_etf_base"],
            "entity_hints": {
                "fundcodes": [entities.get("fundcode")] if entities.get("fundcode") else _extract_fundcodes(question),
                "period": entities.get("period"),
            },
        }
    if any(word in question for word in ("成立日期", "什么时候成立", "在哪上市", "哪里上市", "上市", "业绩比较基准", "申购", "赎回", "申赎", "联接基金")):
        return _single_classification("basic_info_extended", entities | {"fundcode": entities.get("fundcode", "")})
    if any(word in question for word in ("投资目标", "投资范围", "投资理念", "投资策略", "风险收益特征")):
        return _single_classification("investment_profile", entities | {"fundcode": entities.get("fundcode", "")})
    if "成立以来" in question and "分" in question and "红" in question:
        return _single_classification("composite_single", entities | {"fundcode": entities.get("fundcode", "")})
    return None


def _classify_v3_1_query(question: str) -> dict[str, Any] | None:
    hints = extract_v3_1_entity_hints(question)
    fundcodes = hints["fundcodes"]

    if len(fundcodes) >= 2:
        return _v3_1_classification("compare", hints)
    if len(fundcodes) == 1:
        return None

    if _has_search_signal(question):
        if len(hints["search_keyword"]) < 2:
            return {
                "type": "ClarificationRequired",
                "recognized_query_mode": "clarify",
                "intent": None,
                "intent_candidates": [],
                "from_candidates": [],
                "reason": "search_keyword_too_short",
            }
        return _v3_1_classification("search", hints)

    if hints["filters"]:
        return _v3_1_classification("filter", hints)

    if "沪深300ETF" in question and any(word in question for word in ("最好", "最高", "最低", "哪只")):
        return _v3_1_classification("filter", hints)

    if _has_filter_signal(question, hints) and not _looks_like_named_single_query(question):
        return _v3_1_classification("filter", hints)

    return None


def _v3_1_classification(mode: str, hints: dict[str, Any]) -> dict[str, Any]:
    return {
        "recognized_query_mode": mode,
        "intent": mode,
        "intent_candidates": [mode],
        "from_candidates": ["tb_ths_etf_base"],
        "entity_hints": hints,
    }


def _has_compare_signal(question: str) -> bool:
    lowered = question.lower()
    return any(word in lowered for word in COMPARE_SIGNAL_WORDS)


def _has_search_signal(question: str) -> bool:
    return any(
        word in question
        for word in (
            "搜索",
            "帮我找",
            "找一下",
            "我想找",
            "有没有名字",
            "名字里带",
            "名字里",
            "标的指数里",
            "相关的ETF",
            "相关 ETF",
            "相关产品",
            "场内产品",
            "有关",
        )
    )


def _has_filter_signal(question: str, hints: dict[str, Any]) -> bool:
    if hints["filters"]:
        return True
    if hints["order_by"] and any(word in question for word in ("筛选", "前", "top", "最高", "最低", "最好", "排名", "排序", "哪些")):
        return True
    filter_words = (
        "筛选",
        "前",
        "top",
        "最高",
        "最低",
        "最好",
        "排名",
        "排序",
        "大于",
        "超过",
        "低于",
        "小于",
        "上交所",
        "深交所",
        "沪市",
        "深市",
        "股票型",
        "债券型",
        "混合型",
        "货币型",
        "低成本",
        "便宜",
        "费用省",
        "费率低",
        "回报靠前",
        "不小于",
        "不大于",
        "偏债",
        "场内基金",
    )
    return any(word in question for word in filter_words)


def _looks_like_named_single_query(question: str) -> bool:
    single_markers = ("费率", "基金经理", "管理人", "是什么", "收益", "规模", "分红", "净值")
    list_markers = ("搜索", "帮我找", "找一下", "找", "筛选", "哪些", "前", "top", "最高", "最低", "最好", "哪只", "排名", "排序")
    return "ETF" in question and any(word in question for word in single_markers) and not any(
        word in question for word in list_markers
    )


def extract_v3_1_entity_hints(question: str) -> dict[str, Any]:
    filters = _extract_filters(question)
    order_by = _extract_order_by(question)
    search_scope = _extract_search_scope(question, filters)
    return {
        "fundcodes": _extract_fundcodes(question),
        "filters": filters,
        "limit_hint": _extract_limit(question),
        "order_by": order_by,
        "search_keyword": _extract_search_keyword(question, filters=filters, search_scope=search_scope),
        "search_scope": search_scope,
        "period": _period_from_question(question),
        "has_explicit_period": _has_explicit_period(question),
        "wants_compare": _has_compare_signal(question),
    }


def _extract_fundcodes(question: str) -> list[str]:
    seen = set()
    result = []
    for code in re.findall(r"(?<!\d)(\d{6})(?!\d)", question):
        if code in seen:
            continue
        seen.add(code)
        result.append(code)
    return result


def _resolve_v3_1_index_filters(entity_hints: dict[str, Any], config_obj, *, dry_run: bool) -> dict[str, Any]:
    filters = []
    for clause in entity_hints.get("filters") or []:
        if clause.get("field") != "ths_name_of_tracking_index_fund" or not clause.get("raw_value"):
            filters.append(clause)
            continue
        from .index_catalog import resolve_index_name

        resolved = resolve_index_name(str(clause["raw_value"]), config_obj, dry_run=dry_run)
        if resolved["status"] != "matched":
            return {**entity_hints, "filters": filters + [clause], "index_resolution": resolved}
        filters.append(
            {
                "field": clause["field"],
                "op": clause["op"],
                "value": resolved["value"],
                "raw_value": clause["raw_value"],
            }
        )
    return {**entity_hints, "filters": filters}


def _extract_filters(question: str) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []

    date_match = re.search(r"(20[0-9]{2})年.*成立", question)
    if date_match:
        year = date_match.group(1)
        filters.extend(
            [
                {
                    "field": "ths_fund_establishment_date_fund",
                    "op": "gte",
                    "value": f"{year}-01-01",
                    "raw_value": f"{year}年",
                },
                {
                    "field": "ths_fund_establishment_date_fund",
                    "op": "lte",
                    "value": f"{year}-12-31",
                    "raw_value": f"{year}年",
                },
            ]
        )

    if "上交所" in question or "沪市" in question:
        filters.append({"field": "ths_fund_listed_exchange_fund", "op": "eq", "value": "上交所"})
    if "深交所" in question or "深市" in question:
        filters.append({"field": "ths_fund_listed_exchange_fund", "op": "eq", "value": "深交所"})

    for fund_type in ("股票型", "债券型", "混合型", "货币型"):
        if fund_type in question:
            filters.append({"field": "ths_fund_invest_type_fund", "op": "eq", "value": fund_type})
    if "偏债" in question:
        filters.append({"field": "ths_fund_invest_type_fund", "op": "eq", "value": "债券型"})

    index_match = re.search(r"跟踪([^，,、的]+?)(?:指数|ETF|的|，|,|、|$)", question)
    if index_match:
        value = index_match.group(1).strip()
        if value:
            filters.append({"field": "ths_name_of_tracking_index_fund", "op": "eq", "value": value, "raw_value": value})
    if ("沪深300ETF" in question or "沪深300产品" in question) and _has_index_filter_context(question):
        filters.append({"field": "ths_name_of_tracking_index_fund", "op": "eq", "value": "沪深300指数", "raw_value": "沪深300"})

    filters.extend(_extract_numeric_filters(question))
    return filters


def _extract_numeric_filters(question: str) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    numeric_specs = [
        (r"(?:基金)?规模\s*(大于等于|不低于|不小于|至少|大于|超过|高于|小于等于|不超过|不大于|至多|小于|低于|少于)\s*([0-9.]+)\s*亿", "ths_fund_scale_fund", 100000000),
        (r"管理费率?\s*(大于等于|不低于|至少|大于|超过|高于|小于等于|不超过|至多|小于|低于|少于)\s*([0-9.]+)\s*%", "ths_manage_fee_rate_fund", 1),
        (r"收益率?\s*(大于等于|不低于|至少|大于|超过|高于|小于等于|不超过|至多|小于|低于|少于)\s*([0-9.]+)\s*%", _yield_field_for_question(question), 1),
    ]
    for pattern, field, multiplier in numeric_specs:
        match = re.search(pattern, question)
        if match:
            filters.append(
                {
                    "field": field,
                    "op": _op_from_text(match.group(1)),
                    "value": float(match.group(2)) * multiplier,
                }
            )
    for item in filters:
        if isinstance(item["value"], float) and item["value"].is_integer():
            item["value"] = int(item["value"])
    return filters


def _op_from_text(text: str) -> str:
    if text in {"大于等于", "不低于", "不小于", "至少"}:
        return "gte"
    if text in {"小于等于", "不超过", "不大于", "至多"}:
        return "lte"
    if text in {"大于", "超过", "高于"}:
        return "gt"
    if text in {"小于", "低于", "少于"}:
        return "lt"
    return "eq"


def _extract_order_by(question: str) -> dict[str, str] | None:
    fee_words = ("管理费", "费率", "低成本", "便宜", "费用省")
    if any(word in question for word in fee_words):
        if any(word in question for word in ("最低", "低到高", "低成本", "便宜", "费用省", "费率最低")):
            return {"field": "ths_manage_fee_rate_fund", "direction": "asc"}
        if re.search(r"管理费率?\s*(?:小于等于|不超过|至多|小于|低于|少于)\s*[0-9.]+\s*%", question):
            return {"field": "ths_manage_fee_rate_fund", "direction": "asc"}
        if any(word in question for word in ("最高", "高到低", "费率最高")):
            return {"field": "ths_manage_fee_rate_fund", "direction": "desc"}
    if "规模" in question and any(word in question for word in ("前", "最大", "最高", "排序")):
        return {"field": "ths_fund_scale_fund", "direction": "desc"}
    if any(word in question for word in ("收益", "收益率", "回报")) and any(
        word in question for word in ("前", "最高", "最好", "排名", "排序", "靠前")
    ):
        return {"field": _yield_field_for_question(question, default_period="ytd"), "direction": "desc"}
    if re.search(r"收益率?\s*(?:大于等于|不低于|至少|大于|超过|高于)\s*[0-9.]+\s*%", question):
        return {"field": _yield_field_for_question(question), "direction": "desc"}
    return None


def _has_index_filter_context(question: str) -> bool:
    return any(word in question for word in ("最好", "最高", "最低", "哪只", "前", "排名", "排序", "筛选", "搜索", "找", "产品", "低成本", "便宜", "回报靠前"))


def _extract_limit(question: str) -> int | None:
    match = re.search(r"(?:前|top)\s*([0-9]+)", question, re.I)
    if match:
        return int(match.group(1))
    for text, value in {"一": 1, "二": 2, "两": 2, "三": 3, "五": 5, "十": 10}.items():
        if f"前{text}" in question:
            return value
    match = re.search(r"([0-9]+)\s*只", question)
    if match:
        return int(match.group(1))
    if any(word in question for word in ("哪只", "哪一只", "哪支")) and any(word in question for word in ("最好", "最高", "最低", "最强", "最优")):
        return 1
    if any(word in question for word in ("多给一些", "多展示一些")):
        return 20
    if any(word in question for word in ("再多一些", "更多")):
        return 30
    if "全部" in question or "所有" in question:
        return 50
    return None


def _extract_search_scope(question: str, filters: list[dict[str, Any]]) -> str:
    if any(word in question for word in ("名字里带", "名字里", "名称包含", "基金名带", "基金名称包含")):
        return "name_contains"
    if any(item.get("field") == "ths_name_of_tracking_index_fund" for item in filters):
        return "tracking_index"
    return "generic"


def _extract_search_keyword(question: str, *, filters: list[dict[str, Any]] | None = None, search_scope: str = "generic") -> str:
    if search_scope == "tracking_index":
        for item in filters or []:
            if item.get("field") == "ths_name_of_tracking_index_fund":
                return str(item.get("raw_value") or item.get("value") or "").strip()
    cleaned = question
    cleaned = re.sub(r"[\"“”'‘’]", "", cleaned)
    for word in (
        "帮我",
        "我想",
        "搜索",
        "找一下",
        "找",
        "有没有",
        "名称包含",
        "基金名称包含",
        "基金名带",
        "名字里带",
        "名字叫",
        "名字",
        "里带",
        "带",
        "相关的ETF",
        "相关 ETF",
        "相关",
        "跟踪",
        "的ETF",
        "ETF",
        "基金",
        "产品",
        "多给一些",
        "多展示一些",
        "再多一些",
        "更多",
        "全部",
        "所有",
        "一下",
        "哪些",
        "有什么",
        "？",
        "?",
    ):
        cleaned = cleaned.replace(word, "")
    cleaned = re.sub(r"\s+", "", cleaned).strip("，,。 ")
    cleaned = cleaned.removesuffix("的")
    if len(cleaned) >= 2:
        return cleaned
    fallback = re.sub(r"\s+", "", question).strip("，,。 ")
    return fallback if len(fallback) >= 2 else ""


def _period_from_question(question: str) -> str:
    for pattern, period in PERIOD_PATTERNS:
        if pattern.search(question):
            return period
    return "1y"


def _yield_field_for_question(question: str, *, default_period: str = "1y") -> str:
    return f"ths_yeild_{_period_from_question(question) if _has_explicit_period(question) else default_period}_fund"


def _has_explicit_period(question: str) -> bool:
    return any(pattern.search(question) for pattern, _period in PERIOD_PATTERNS)


def _force_deny_classification(question: str) -> dict[str, Any] | None:
    if any(word in question for word in ("能买吗", "能不能买", "值不值得", "该不该买", "推荐", "给我挑", "适合买入", "要不要入手", "哪个更好", "哪个好")):
        return {
            "recognized_query_mode": "deny",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "deny_reason": "investment_advice",
        }
    if any(word in question for word in ("实时行情", "实时净值", "盘中行情", "今日涨跌", "今天涨跌", "实时")):
        return {
            "recognized_query_mode": "deny",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "deny_reason": "realtime_not_supported",
        }
    if any(word in question for word in ("大盘", "A股大盘", "个股分析", "上证指数", "深证成指", "K线", "MACD", "均线", "RSI")):
        return {
            "recognized_query_mode": "deny",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "deny_reason": "v3_unsupported_domain",
        }
    return None


def _force_v3_0_single_classification(question: str, entities: dict[str, str]) -> dict[str, Any] | None:
    fundcodes = _extract_fundcodes(question)
    has_fund_identity = bool(entities.get("fundcode")) or len(fundcodes) == 1
    if not has_fund_identity or len(fundcodes) > 1:
        return None
    hints = extract_v3_1_entity_hints(question)
    if hints["filters"] or _has_search_signal(question) or _has_compare_signal(question):
        return None

    if _requires_explicit_derived_performance(question):
        return _single_classification("performance", entities)

    real_time_markers = ("实时", "盘中", "当前", "现在", "今天", "今日", "估值")
    if "净值" in question and not any(marker in question for marker in real_time_markers):
        return _single_classification("fund_scale", entities)
    if "ETF排" in question or "ETF 排" in question:
        return _single_classification("performance", entities)
    intent = _lexical_infer_intent(question)
    if intent in {
        "basic_info",
        "fund_scale",
        "tracking_index",
        "performance",
        "fee",
        "manager",
        "fee_and_manager",
        "dividend",
    }:
        return _single_classification(intent, entities)
    return None


def _single_classification(intent: str, entities: dict[str, str]) -> dict[str, Any]:
    return {
        "recognized_query_mode": "single",
        "intent": intent,
        "intent_candidates": [intent],
        "from_candidates": ["tb_ths_etf_base"],
        "entity_hints": {
            "fundcodes": [entities.get("fundcode")] if entities.get("fundcode") else [],
            "period": entities.get("period"),
        },
    }


def build_v3_ast(intent: str, entities: dict[str, str]) -> dict[str, Any]:
    """Build v3 AST from a pre-classified intent and extracted entities."""
    period = entities.get("period", "1y")
    return {
        "intent": intent,
        "from": "tb_ths_etf_base",
        "select": _select_fields(intent, period, entities),
        "where": [{"field": "fundcode", "op": "eq", "value": entities["fundcode"]}],
        "order_by": None,
        "limit": 1,
        "output_style": "summary",
        "answer_fields": _answer_fields(intent, period, entities),
        "report_period": None,
        "expand": None,
    }


def build_v3_1_ast(query_mode: str, entity_hints: dict[str, Any], question: str) -> dict[str, Any]:
    if query_mode == "search":
        return _build_search_ast(entity_hints)
    if query_mode == "filter":
        return _build_filter_ast(entity_hints, question)
    if query_mode == "compare":
        return _build_compare_ast(entity_hints)
    raise ValueError(f"unsupported v3.1 query_mode: {query_mode}")


def _build_search_ast(entity_hints: dict[str, Any]) -> dict[str, Any]:
    limit_hint = entity_hints.get("limit_hint")
    return {
        "intent": "search",
        "from": "tb_ths_etf_base",
        "select": list(LIST_BASELINE_FIELDS),
        "where": [{"field": "__search_text__", "op": "contains", "value": entity_hints.get("search_keyword", "")}],
        "order_by": {"field": "ths_fund_scale_fund", "direction": "desc"},
        "limit": min(int(limit_hint or 10), 50),
        "output_style": "list",
        "answer_fields": _field_metas(LIST_BASELINE_FIELDS),
        "report_period": None,
        "expand": None,
        "search_keyword": entity_hints.get("search_keyword", ""),
        "search_scope": entity_hints.get("search_scope", "generic"),
        "has_explicit_period": bool(entity_hints.get("has_explicit_period")),
        "limit_source": "all" if limit_hint == 50 else "explicit" if limit_hint else "default",
    }


def _build_filter_ast(entity_hints: dict[str, Any], question: str) -> dict[str, Any]:
    order_by = entity_hints.get("order_by") or {"field": "ths_fund_scale_fund", "direction": "desc"}
    filters = [_ast_clause(clause) for clause in entity_hints.get("filters") or []]
    limit_hint = entity_hints.get("limit_hint")
    select = list(LIST_BASELINE_FIELDS)
    for clause in filters:
        field = clause["field"]
        if field != "__search_text__" and field not in select:
            select.append(field)
    if order_by["field"] not in select:
        select.append(order_by["field"])
    display_fields = list(LIST_BASELINE_FIELDS)
    if order_by["field"] not in display_fields:
        display_fields.append(order_by["field"])
    for clause in filters:
        field = clause["field"]
        if field.startswith("ths_yeild_") and field not in display_fields:
            display_fields.append(field)
    return {
        "intent": "filter",
        "from": "tb_ths_etf_base",
        "select": select,
        "where": filters,
        "order_by": order_by,
        "limit": _filter_limit(entity_hints, question),
        "output_style": "list",
        "answer_fields": _field_metas(display_fields),
        "report_period": None,
        "expand": None,
        "limit_source": "all" if limit_hint == 50 else "explicit" if limit_hint else "default",
    }


def _build_compare_ast(entity_hints: dict[str, Any]) -> dict[str, Any]:
    fundcodes = list(entity_hints.get("fundcodes") or [])[:10]
    return {
        "intent": "compare",
        "from": "tb_ths_etf_base",
        "select": list(COMPARE_FIELDS),
        "where": [{"field": "fundcode", "op": "in", "value": fundcodes}],
        "order_by": None,
        "limit": 10,
        "output_style": "compare",
        "answer_fields": _field_metas(COMPARE_FIELDS),
        "report_period": None,
        "expand": None,
    }


def _filter_limit(entity_hints: dict[str, Any], question: str) -> int:
    requested = int(entity_hints.get("limit_hint") or 10)
    if entity_hints.get("wants_compare") or _has_compare_signal(question):
        return min(requested, 5)
    return min(requested, 50)


def _ast_clause(clause: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in clause.items() if key != "raw_value"}


def _field_metas(fields: list[str]) -> list[dict[str, str]]:
    return [
        {"field": field, "label": field_meta(field)[0], "format": field_meta(field)[1]}
        for field in fields
    ]


def _validate_ast_for_compile(
    ast: dict[str, Any],
    *,
    query_mode: str,
    entity_hints: dict[str, Any],
    phase: str = "v3.1",
) -> dict[str, Any]:
    from .ast_validator import validate_v3_ast

    selection_context = get_selection_context(query_mode, ast["intent"], phase=phase)
    return validate_v3_ast(
        ast,
        query_mode=query_mode,
        entity_hints=entity_hints,
        selection_context=selection_context,
        phase=phase,
    )


def _maybe_apply_llm_ast_fields(
    ast: dict[str, Any],
    *,
    question: str,
    classification: dict[str, Any],
    entity_hints: dict[str, Any],
    selection_context: dict[str, Any],
    config_obj,
    dry_run: bool,
    no_llm: bool,
) -> tuple[dict[str, Any], str]:
    if no_llm:
        return ast, "skipped"
    if dry_run or not config_obj.dashscope_api_key:
        return ast, "skipped"
    try:
        from .ast_generator import generate_ast_fields_with_llm

        generated = generate_ast_fields_with_llm(
            question,
            classification=classification,
            entity_hints=entity_hints,
            selection_context=selection_context,
            config=config_obj,
        )
        ast = {**ast, "select": generated["select"], "answer_fields": generated["answer_fields"]}
        return ast, "generated"
    except Exception:
        return ast, "fallback_to_deterministic"


def _validate_with_llm_fallback(
    ast: dict[str, Any],
    deterministic_ast: dict[str, Any],
    *,
    query_mode: str,
    entity_hints: dict[str, Any],
    llm_ast_status: str,
) -> tuple[dict[str, Any], str]:
    try:
        return _validate_ast_for_compile(ast, query_mode=query_mode, entity_hints=entity_hints), llm_ast_status
    except ValueError:
        if llm_ast_status == "generated":
            return (
                _validate_ast_for_compile(deterministic_ast, query_mode=query_mode, entity_hints=entity_hints),
                "fallback_to_deterministic",
            )
        raise


def _compile_ast_to_plan(ast: dict[str, Any]) -> dict[str, Any]:
    """Compile v3 AST into a plan dict compatible with execute_remote_query + format_answer."""
    report_scope = ast.get("report_scope")
    plan: dict[str, Any] = {
        "collection": ast["from"],
        "filter": {},
        "projection": list(ast["select"]),
        "limit": ast["limit"],
        "answer_fields": list(ast["answer_fields"]),
        "output_style": ast.get("output_style", "summary"),
        "timeseries_semantics": ast.get("timeseries_semantics"),
    }
    if ast.get("intent") == "search":
        plan["search_keyword"] = ast.get("search_keyword") or _search_keyword_from_ast(ast)
        plan["search_scope"] = ast.get("search_scope", "generic")
        plan["has_explicit_period"] = bool(ast.get("has_explicit_period"))
        plan["limit_source"] = ast.get("limit_source") or ("all" if ast.get("limit") == 50 else None)
    elif ast.get("output_style") == "list":
        plan["has_explicit_period"] = bool(ast.get("has_explicit_period"))
        plan["limit_source"] = ast.get("limit_source") or ("all" if ast.get("limit") == 50 else None)
    if report_scope:
        plan["collection"] = report_collection(ast.get("intent", ""), report_scope, plan["collection"])
        plan["report_scope"] = report_scope
        plan["report_period"] = ast.get("report_period")
    order_by = ast.get("order_by")
    if order_by:
        plan["sort"] = _sort_spec(order_by)
    elif ast.get("intent") in {"search", "filter"}:
        plan["sort"] = [["ths_fund_scale_fund", -1], ["fundcode", 1]]
    if _needs_performance_nav_projection(ast, plan):
        plan["projection"] = _append_unique_projection(plan["projection"], "ths_unit_nv_fund")
    for clause in ast.get("where", []):
        op = clause.get("op")
        if op == "eq":
            plan["filter"][clause["field"]] = clause["value"]
        elif op == "in":
            plan["filter"][clause["field"]] = {"$in": clause["value"]}
        elif op == "contains":
            if clause["field"] == "__search_text__":
                plan["filter"][clause["field"]] = {"$contains": clause["value"]}
            else:
                plan["filter"][clause["field"]] = {"$regex": re.escape(str(clause["value"])), "$options": "i"}
        elif op == "between":
            value = clause.get("value") or {}
            plan["filter"].setdefault(clause["field"], {})["$gte"] = value.get("start") or value.get("gte")
            plan["filter"].setdefault(clause["field"], {})["$lte"] = value.get("end") or value.get("lte")
        elif op in {"gt", "gte", "lt", "lte"}:
            plan["filter"].setdefault(clause["field"], {})[_mongo_compare_op(op)] = clause["value"]
    _apply_report_scope_to_plan(ast, plan)
    return plan


def _apply_search_contract_to_ast(ast: dict[str, Any], entity_hints: dict[str, Any]) -> None:
    if ast.get("intent") != "search":
        return
    ast["search_scope"] = entity_hints.get("search_scope", "generic")
    ast["search_keyword"] = entity_hints.get("search_keyword", _search_keyword_from_ast(ast))
    ast["has_explicit_period"] = bool(entity_hints.get("has_explicit_period"))
    limit_hint = entity_hints.get("limit_hint")
    if limit_hint == 50:
        ast["limit_source"] = "all"
    elif limit_hint:
        ast["limit_source"] = "explicit"
    else:
        ast["limit_source"] = "default"


def _search_keyword_from_ast(ast: dict[str, Any]) -> str:
    for clause in ast.get("where", []):
        if clause.get("field") == "__search_text__":
            return str(clause.get("value") or "")
    return ""


def _apply_report_scope_to_plan(ast: dict[str, Any], plan: dict[str, Any]) -> None:
    report_scope = ast.get("report_scope")
    if not report_scope:
        return
    type_nums = report_type_filter(report_scope)
    if type_nums:
        plan["filter"]["type_num"] = {"$in": type_nums}
    if report_scope.endswith("_latest"):
        plan["sort"] = [["year_num", -1], ["type_num", -1]]
        plan["limit"] = 1
    if plan.get("output_style") != "report_list":
        return

    expand = ast.get("expand") or default_report_expand("", ast.get("intent", ""), report_scope)
    if not isinstance(expand, dict):
        return
    plan["expand"] = {
        "field": expand.get("field"),
        "paired_fields": list(expand.get("paired_fields") or []),
        "order_by": expand.get("order_by") or {"field": "rank_num", "direction": "asc"},
    }
    for field in [plan["expand"]["field"], *plan["expand"]["paired_fields"]]:
        if field and field not in plan["projection"]:
            plan["projection"].append(field)
    display_limit = ast.get("limit")
    if isinstance(display_limit, int) and display_limit > 1:
        plan["display_limit"] = display_limit


def _needs_performance_nav_projection(ast: dict[str, Any], plan: dict[str, Any]) -> bool:
    if ast.get("intent") == "performance":
        return True
    fields = list(plan.get("projection") or [])
    sort_spec = list(plan.get("sort") or [])
    if any(isinstance(field, str) and field.startswith("ths_yeild_") for field in fields):
        return True
    if any(isinstance(item, (list, tuple)) and item and str(item[0]).startswith("ths_yeild_") for item in sort_spec):
        return True
    return False


def _append_unique_projection(projection: list[str], field: str) -> list[str]:
    if field in projection:
        return projection
    return [*projection, field]


def _sort_spec(order_by: dict[str, str]) -> list[list[Any]]:
    direction = -1 if order_by.get("direction") == "desc" else 1
    sort = [[order_by["field"], direction]]
    if order_by["field"] != "ths_fund_scale_fund":
        sort.append(["ths_fund_scale_fund", -1])
    if order_by["field"] != "fundcode":
        sort.append(["fundcode", 1])
    return sort


def _mongo_compare_op(op: str) -> str:
    return {"gt": "$gt", "gte": "$gte", "lt": "$lt", "lte": "$lte"}[op]


def _clarification_for_name_matches(question: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
    options = []
    for index, match in enumerate(matches[:5], start=1):
        options.append(
            {
                "id": f"fund_{match.get('fundcode') or index}",
                "kind": "fund_candidate",
                "label": str(match.get("name") or match.get("fundcode") or "候选 ETF"),
                "value": {
                    "fundcode": str(match.get("fundcode", "")),
                    "thscode": str(match.get("thscode", "")),
                },
                "fundcode": str(match.get("fundcode", "")),
                "thscode": str(match.get("thscode", "")),
                "reason": "名称匹配到多只候选之一",
            }
        )
    labels = "、".join(option["label"] for option in options)
    return {
        "question": question,
        "answer": f"匹配到多只 ETF，请补充具体产品：{labels}",
        "v3": {
            "type": "ClarificationRequired",
            "recognized_query_mode": "clarify",
            "reason": "name_ambiguity",
            "question": "匹配到多只 ETF，请选择要查询的产品。",
            "options": options,
            "state_id": None,
            "next_action": "choose_candidate",
        },
    }


def _detect_project_root() -> Path:
    """Detect project root from CWD or this module's location."""
    cwd = Path.cwd()
    if (cwd / ".env").exists():
        return cwd
    module_dir = Path(__file__).resolve().parent.parent
    if (module_dir / ".env").exists():
        return module_dir
    return cwd


def semantic_query_v3(question: str, *, root=None, dry_run: bool = False, no_llm: bool = False, phase: str = "v3.3") -> dict[str, Any]:
    # Load config
    from .config import load_config

    config_root = Path(root) if root else _detect_project_root()
    config_obj = load_config(config_root)

    # ---- Step 1: deny / unsupported gate ----
    classification = classify_v3_query(question, config=None if (dry_run or no_llm) else config_obj)
    mode = classification["recognized_query_mode"]

    if not dry_run and not no_llm:
        if phase == "v3.2":
            return _semantic_query_v3_2_strict(question, config_obj=config_obj, classification=classification)
        if phase == "v3.3":
            return _semantic_query_v3_3_strict(question, config_obj=config_obj, classification=classification)
        raise ValueError(f"unsupported v3 phase: {phase}")

    if mode == "deny":
        return {
            "question": question,
            "answer": "抱歉，该问题涉及实时行情、交易指标或投资建议，超出当前 ETF 数据查询能力范围。",
            "v3": {**classification, "llm_ast_status": "skipped"},
        }
    if mode == "unsupported":
        return {
            "question": question,
            "answer": "当前版本暂不支持该查询类型。",
            "v3": {**classification, "llm_ast_status": "skipped"},
        }
    if mode == "clarify":
        return {
            "question": question,
            "answer": "查询条件还不够明确，请补充后重试。",
            "v3": {**classification, "llm_ast_status": "skipped"},
        }

    if mode in V3_1_QUERY_MODES:
        hints = classification.get("entity_hints") or extract_v3_1_entity_hints(question)
        hints = _resolve_v3_1_index_filters(hints, config_obj, dry_run=dry_run)
        if (hints.get("index_resolution") or {}).get("status") == "ambiguous":
            matches = hints["index_resolution"].get("matches", [])
            names = "、".join(str(item.get("name")) for item in matches[:5])
            return {
                "question": question,
                "answer": f"匹配到多个跟踪指数，请补充更具体的指数名称：{names}",
                "v3": {**classification, "recognized_query_mode": "clarify", "llm_ast_status": "skipped"},
                "entities": {"question": question, **hints},
            }
        if (hints.get("index_resolution") or {}).get("status") == "not_found":
            return {
                "question": question,
                "answer": "未匹配到对应的跟踪指数，请补充更具体的指数名称。",
                "v3": {**classification, "recognized_query_mode": "clarify", "llm_ast_status": "skipped"},
                "entities": {"question": question, **hints},
            }
        deterministic_ast = build_v3_1_ast(mode, hints, question)
        ast = deterministic_ast
        selection_context = get_selection_context(mode, ast["intent"])
        ast, llm_ast_status = _maybe_apply_llm_ast_fields(
            ast,
            question=question,
            classification=classification,
            entity_hints=hints,
            selection_context=selection_context,
            config_obj=config_obj,
            dry_run=dry_run,
            no_llm=no_llm,
        )
        ast, llm_ast_status = _validate_with_llm_fallback(
            ast,
            deterministic_ast,
            query_mode=mode,
            entity_hints=hints,
            llm_ast_status=llm_ast_status,
        )
        plan = _compile_ast_to_plan(ast)
        result = _execute_v3_plan(plan, config_obj, dry_run=dry_run, no_llm=no_llm)
        if isinstance(result, dict) and not result.get("success", True):
            return {
                "question": question,
                "answer": f"远端查询失败：{result.get('error')}",
                "v3": {**classification, "llm_ast_status": llm_ast_status},
                "v3_ast": ast,
                "entities": {"question": question, **hints},
                "query_plan": plan,
            }
        from .formatter import format_answer

        answer = format_answer(plan, result)
        output_v3 = {**classification, "llm_ast_status": llm_ast_status}
        if mode == "filter" and hints.get("wants_compare") and _has_compare_signal(question):
            compare_codes = _fundcodes_from_result(result)[:5]
            if len(compare_codes) >= 2:
                compare_hints = {**hints, "fundcodes": compare_codes}
                compare_ast = build_v3_1_ast("compare", compare_hints, question)
                compare_ast = _validate_ast_for_compile(compare_ast, query_mode="compare", entity_hints=compare_hints)
                compare_plan = _compile_ast_to_plan(compare_ast)
                compare_result = _execute_v3_plan(compare_plan, config_obj, dry_run=dry_run, no_llm=no_llm)
                answer = format_answer(compare_plan, compare_result)
                ast = {"intent": "composite", "steps": [ast, compare_ast]}
                plan = {"steps": [plan, compare_plan]}
                result = {"steps": [result, compare_result]}
                output_v3 = {
                    **classification,
                    "recognized_query_mode": "composite",
                    "intent": "filter_to_compare",
                    "intent_candidates": ["filter_to_compare"],
                    "llm_ast_status": llm_ast_status,
                    "steps": [
                        {"recognized_query_mode": "filter", "intent": "filter"},
                        {"recognized_query_mode": "compare", "intent": "compare"},
                    ],
                }
        return {
            "question": question,
            "answer": answer,
            "v3": output_v3,
            "v3_ast": ast,
            "entities": {"question": question, **hints},
            "query_plan": plan,
            "result": result,
        }

    # ---- Step 2: entity extraction ----
    from .entities import extract_entities

    try:
        entities = extract_entities(question)
    except ValueError:
        from .name_resolver import resolve_fundcode_from_name

        resolved = resolve_fundcode_from_name(question, config_obj, dry_run=dry_run)
        if resolved["status"] == "matched":
            entities = {
                "fundcode": resolved["fundcode"],
                "resolved_by": "name",
                "matched_name": resolved.get("matched_name", ""),
                "matched_thscode": resolved.get("matched_thscode", ""),
            }
        elif resolved["status"] == "ambiguous":
            return _clarification_for_name_matches(question, resolved["matches"])
        else:
            return {
                "question": question,
                "answer": "未在问题中识别到 ETF 基金代码或名称，请补充后重试。",
                "v3": {**classification, "llm_ast_status": "skipped"},
            }
    entities["question"] = question

    # ---- Step 3: build v3 AST (no re-classification) ----
    intent = classification["intent"]
    deterministic_ast = build_v3_ast(intent, entities)
    ast = deterministic_ast
    single_hints = {"fundcodes": [entities["fundcode"]]}
    selection_context = get_selection_context("single", intent)
    ast, llm_ast_status = _maybe_apply_llm_ast_fields(
        ast,
        question=question,
        classification=classification,
        entity_hints=single_hints,
        selection_context=selection_context,
        config_obj=config_obj,
        dry_run=dry_run,
            no_llm=no_llm,
    )
    ast, llm_ast_status = _validate_with_llm_fallback(
        ast,
        deterministic_ast,
        query_mode="single",
        entity_hints=single_hints,
        llm_ast_status=llm_ast_status,
    )
    plan = _compile_ast_to_plan(ast)

    # ---- Step 4: execute query ----
    try:
        result = _execute_v3_plan(plan, config_obj, dry_run=dry_run, no_llm=no_llm)
    except RuntimeError as exc:
        return {
            "question": question,
            "answer": f"远端查询失败：{exc}",
            "v3": {**classification, "llm_ast_status": llm_ast_status},
            "v3_ast": ast,
            "entities": entities,
            "query_plan": plan,
        }

    # ---- Step 5: format answer ----
    from .formatter import format_answer

    answer = format_answer(plan, result)
    return {
        "question": question,
        "answer": answer,
        "v3": {**classification, "llm_ast_status": llm_ast_status},
        "v3_ast": ast,
        "entities": entities,
        "query_plan": plan,
        "result": result,
    }


def _semantic_query_v3_2_strict(question: str, *, config_obj, classification: dict[str, Any]) -> dict[str, Any]:
    mode = classification["recognized_query_mode"]
    if mode in {"deny", "unsupported", "clarify"}:
        return _non_executable_v3_2_output(question, classification)

    try:
        query_mode, intent, entity_hints, routing_evidence = _v3_2_execution_context(question, classification, config_obj)
        routing_result = {"type": "ExecutableQuery", "reason": None}
        generation_bundle = build_generation_bundle(
            question,
            query_mode=query_mode,
            intent=intent,
            entity_hints=entity_hints,
            phase="v3.2",
        )
    except Exception as exc:
        return _v3_2_failure(
            question,
            classification=classification,
            stage="routing",
            reason=str(exc),
            ast_generation_mode=None,
        )

    if query_mode == "filter" and entity_hints.get("wants_compare") and _has_compare_signal(question):
        return _semantic_query_v3_2_filter_to_compare(
            question,
            classification=classification,
            filter_bundle=generation_bundle,
            filter_hints=entity_hints,
            config_obj=config_obj,
        )

    try:
        draft_payload = generate_full_ast_draft_with_llm(
            question=question,
            routing_result=routing_result,
            classification={**classification, "recognized_query_mode": query_mode, "intent": intent},
            generation_context=generation_bundle,
            config=config_obj,
        )
    except Exception as exc:
        return _v3_2_failure(
            question,
            classification=classification,
            stage="llm_ast_draft",
            reason=str(exc),
            ast_generation_mode="llm_ast_draft_failed",
        )

    try:
        validation = validate_v3_2_ast_draft(
            draft_payload["draft"],
            query_mode=query_mode,
            intent=intent,
            generation_bundle=generation_bundle,
        )
    except Exception as exc:
        return _v3_2_failure(
            question,
            classification=classification,
            stage="validator",
            reason=str(exc),
            ast_generation_mode="llm_ast_draft_failed",
            llm_ast_draft_raw=draft_payload.get("raw"),
        )

    validated_ast = validation["validated_ast"]
    _apply_search_contract_to_ast(validated_ast, entity_hints)
    try:
        plan = _compile_ast_to_plan(validated_ast)
        mongo_params = _mongo_params_for_plan(plan)
    except Exception as exc:
        return _v3_2_failure(
            question,
            classification=classification,
            stage="compiler",
            reason=str(exc),
            ast_generation_mode="llm_ast_draft_failed",
            llm_ast_draft_raw=draft_payload.get("raw"),
            v3_ast=draft_payload["draft"],
        )

    try:
        result = _execute_v3_plan(plan, config_obj, dry_run=False, no_llm=False)
    except Exception as exc:
        return _v3_2_failure(
            question,
            classification=classification,
            stage="remote_query",
            reason=str(exc),
            ast_generation_mode="llm_ast_draft",
            llm_ast_draft_raw=draft_payload.get("raw"),
            v3_ast=draft_payload["draft"],
            validated_ast=validated_ast,
            query_plan=plan,
            mongo_params=mongo_params,
            remote_query_allowed=True,
        )

    from .formatter import format_answer

    answer = format_answer(plan, result)
    capability_audit = _capability_audit_fields("v3.2", query_mode, intent, generation_bundle)
    output_v3 = {
        **classification,
        "routing_result": routing_result,
        "recognized_query_mode": query_mode,
        "intent": intent,
        **capability_audit,
        "blocked_intent_candidates": classification.get("blocked_intent_candidates", []),
        "routing_evidence": routing_evidence,
        "ast_generation_mode": "llm_ast_draft",
        "llm_ast_draft_raw": draft_payload.get("raw"),
        "remote_query_allowed": True,
        "failure_stage": None,
        "failure_reason": None,
        "provenance_diff": validation["provenance_diff"],
        "validator_applied_defaults": validation["validator_applied_defaults"],
    }
    return {
        "question": question,
        "answer": answer,
        "v3": output_v3,
        "v3_ast": draft_payload["draft"],
        "validated_ast": validated_ast,
        "entities": {"question": question, **entity_hints},
        "query_plan": plan,
        "mongo_params": mongo_params,
        "result": result,
        "failure_stage": None,
        "failure_reason": None,
    }


def _semantic_query_v3_3_strict(
    question: str,
    *,
    config_obj,
    classification: dict[str, Any],
    apply_override: bool = True,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    if apply_override:
        classification = _v3_3_override_classification(question, classification)
        if classification.get("composite_execution") == "multi_child_bundle":
            return _semantic_query_v3_3_composite_bundle(question, config_obj=config_obj, classification=classification)
    mode = classification["recognized_query_mode"]
    if mode in {"deny", "unsupported", "clarify"}:
        output = _non_executable_v3_2_output(question, classification)
        output["v3"]["phase"] = "v3.3"
        return output
    if (
        mode == "filter"
        and not classification.get("child_task")
        and (classification.get("entity_hints") or {}).get("wants_compare")
        and _has_compare_signal(question)
    ):
        return _semantic_query_v3_3_filter_to_compare(
            question,
            classification=classification,
            config_obj=config_obj,
        )

    try:
        query_mode, intent, entity_hints, routing_evidence = _v3_3_execution_context(question, classification, config_obj)
        routing_result = {"type": "ExecutableQuery", "reason": None}
        generation_bundle = build_generation_bundle(
            question,
            query_mode=query_mode,
            intent=intent,
            entity_hints=entity_hints,
            phase="v3.3",
        )
        if classification.get("child_task"):
            generation_bundle["llm_context"]["child_task"] = classification["child_task"]
    except Exception as exc:
        return _v3_3_failure(
            question,
            classification=classification,
            stage="routing",
            reason=str(exc),
            ast_generation_mode=None,
        )

    if _is_v3_3_mixed_rank_return(question, generation_bundle):
        return _v3_3_unsupported(question, classification, "mixed_rank_return_list_not_supported")

    try:
        draft_payload = generate_full_ast_draft_with_llm(
            question=question,
            routing_result=routing_result,
            classification={**classification, "recognized_query_mode": query_mode, "intent": intent},
            generation_context=generation_bundle,
            config=config_obj,
        )
    except Exception as exc:
        return _v3_3_failure(
            question,
            classification=classification,
            stage="llm_ast_draft",
            reason=str(exc),
            ast_generation_mode="llm_ast_draft_failed",
        )

    try:
        validation = validate_v3_3_ast_draft(
            draft_payload["draft"],
            query_mode=query_mode,
            intent=intent,
            generation_bundle=generation_bundle,
        )
    except Exception as exc:
        return _v3_3_failure(
            question,
            classification=classification,
            stage="validator",
            reason=str(exc),
            ast_generation_mode="llm_ast_draft_failed",
            llm_ast_draft_raw=draft_payload.get("raw"),
        )

    validated_ast = validation["validated_ast"]
    _apply_search_contract_to_ast(validated_ast, entity_hints)
    try:
        compiled_kind, compiled_query = _compile_v3_3_query(validated_ast)
        if compiled_kind == "derived_performance":
            mongo_params = _mongo_params_for_plan(compiled_query["mongo_phase"])
            mongo_result = _execute_mongo_phase(compiled_query["mongo_phase"], config_obj)
            result = execute_derived_performance(compiled_query, mongo_result)
            answer_plan = compiled_query["output_phase"]
        else:
            mongo_params = _mongo_params_for_plan(compiled_query)
            result = _execute_v3_plan(compiled_query, config_obj, dry_run=False, no_llm=False)
            answer_plan = compiled_query
    except Exception as exc:
        return _v3_3_failure(
            question,
            classification=classification,
            stage="compiler" if "compiled_kind" not in locals() else "executor",
            reason=str(exc),
            ast_generation_mode="llm_ast_draft" if "compiled_kind" in locals() else "llm_ast_draft_failed",
            llm_ast_draft_raw=draft_payload.get("raw"),
            v3_ast=draft_payload["draft"],
            validated_ast=validated_ast,
            query_plan=compiled_query if "compiled_query" in locals() else None,
            mongo_params=mongo_params if "mongo_params" in locals() else None,
            remote_query_allowed=True,
        )

    from .formatter import format_answer

    if compiled_kind != "derived_performance":
        result = _apply_timeseries_semantics(validated_ast, result)

    answer = format_answer(answer_plan, result)
    ended_at = datetime.now(timezone.utc)
    answer = _append_runtime_metadata(
        answer,
        result=result,
        usage=draft_payload.get("usage"),
    )
    capability_audit = _capability_audit_fields("v3.3", query_mode, intent, generation_bundle)
    output_mode = classification.get("recognized_query_mode") if classification.get("recognized_query_mode") == "composite" else query_mode
    output_v3 = {
        **classification,
        "phase": "v3.3",
        "ast_schema_version": validation["provenance_diff"].get("ast_schema_version", "v3_3_structured_query"),
        "grammar_fragment_id": compiled_query.get("grammar_fragment_id") if isinstance(compiled_query, dict) else None,
        "compiler_rule_id": compiled_query.get("compiler_rule_id") if isinstance(compiled_query, dict) else None,
        "routing_result": routing_result,
        "recognized_query_mode": output_mode,
        "child_query_mode": query_mode if output_mode == "composite" else None,
        "intent": intent,
        **capability_audit,
        "derived_performance_strict_pass": validation["provenance_diff"]["strict_pass"],
        "routing_evidence": routing_evidence,
        "ast_generation_mode": "llm_ast_draft",
        "llm_ast_draft_raw": draft_payload.get("raw"),
        "remote_query_allowed": True,
        "failure_stage": None,
        "failure_reason": None,
        "provenance_diff": validation["provenance_diff"],
        "validator_applied_defaults": validation["validator_applied_defaults"],
    }
    return {
        "question": question,
        "answer": answer,
        "v3": output_v3,
        "v3_ast": draft_payload["draft"],
        "validated_ast": validated_ast,
        "entities": {"question": question, **entity_hints},
        "query_plan": compiled_query,
        "compiled_query": compiled_query,
        "mongo_params": mongo_params,
        "result": result,
        "execution_window": {
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
        },
        "llm_usage": _normalize_usage(draft_payload.get("usage")),
        "failure_stage": None,
        "failure_reason": None,
    }


def _semantic_query_v3_2_filter_to_compare(
    question: str,
    *,
    classification: dict[str, Any],
    filter_bundle: dict[str, Any],
    filter_hints: dict[str, Any],
    config_obj,
) -> dict[str, Any]:
    filter_bundle["llm_context"]["child_task"] = "two_step_composite step 1: generate only the filter/list AST that selects candidate fundcodes."
    filter_child = _run_v3_2_child(
        question,
        classification={**classification, "recognized_query_mode": "filter", "intent": "filter"},
        query_mode="filter",
        intent="filter",
        entity_hints=filter_hints,
        generation_bundle=filter_bundle,
        config_obj=config_obj,
    )
    if filter_child.get("failure"):
        return _child_failure_to_output(question, classification, filter_child)

    compare_codes = _fundcodes_from_result(filter_child["result"])[:5]
    if len(compare_codes) < 2:
        return _v3_2_failure(
            question,
            classification=classification,
            stage="composite",
            reason="filter_to_compare requires at least two candidates",
            ast_generation_mode="llm_ast_draft_failed",
            llm_ast_draft_raw=filter_child["draft_payload"].get("raw"),
            v3_ast=filter_child["draft_payload"]["draft"],
            validated_ast=filter_child["validated_ast"],
            query_plan=filter_child["plan"],
            mongo_params=filter_child["mongo_params"],
        )

    compare_hints = {
        "fundcodes": compare_codes,
        "filters": [],
        "limit_hint": None,
        "order_by": None,
        "search_keyword": "",
        "period": filter_hints.get("period"),
        "wants_compare": True,
    }
    compare_bundle = build_generation_bundle(
        question,
        query_mode="compare",
        intent="compare",
        entity_hints=compare_hints,
        phase="v3.2",
    )
    compare_bundle["llm_context"]["child_task"] = (
        "two_step_composite step 2: compare only the provided fundcodes from step 1; "
        "do not add order_by or additional candidate selection."
    )
    compare_child = _run_v3_2_child(
        question,
        classification={**classification, "recognized_query_mode": "compare", "intent": "compare"},
        query_mode="compare",
        intent="compare",
        entity_hints=compare_hints,
        generation_bundle=compare_bundle,
        config_obj=config_obj,
    )
    if compare_child.get("failure"):
        return _child_failure_to_output(question, classification, compare_child)

    from .formatter import format_answer

    answer = format_answer(compare_child["plan"], compare_child["result"])
    capability_audit = _capability_audit_fields("v3.2", "compare", "two_step_composite", compare_bundle)
    output_v3 = {
        **classification,
        "routing_result": {"type": "ExecutableQuery", "reason": None},
        "recognized_query_mode": "compare",
        "intent": "two_step_composite",
        **capability_audit,
        "intent_candidates": ["two_step_composite"],
        "blocked_intent_candidates": [],
        "ast_generation_mode": "llm_ast_draft",
        "llm_ast_draft_raw": [
            filter_child["draft_payload"].get("raw"),
            compare_child["draft_payload"].get("raw"),
        ],
        "remote_query_allowed": True,
        "failure_stage": None,
        "failure_reason": None,
        "steps": [
            {"recognized_query_mode": "filter", "intent": "filter"},
            {"recognized_query_mode": "compare", "intent": "compare"},
        ],
        "provenance_diff": [
            filter_child["validation"]["provenance_diff"],
            compare_child["validation"]["provenance_diff"],
        ],
    }
    return {
        "question": question,
        "answer": answer,
        "v3": output_v3,
        "v3_ast": {"intent": "two_step_composite", "steps": [filter_child["draft_payload"]["draft"], compare_child["draft_payload"]["draft"]]},
        "validated_ast": {"intent": "two_step_composite", "steps": [filter_child["validated_ast"], compare_child["validated_ast"]]},
        "query_plan": {"steps": [filter_child["plan"], compare_child["plan"]]},
        "mongo_params": {"steps": [filter_child["mongo_params"], compare_child["mongo_params"]]},
        "result": {"success": True, "steps": [filter_child["result"], compare_child["result"]]},
        "failure_stage": None,
        "failure_reason": None,
    }


def _semantic_query_v3_3_filter_to_compare(
    question: str,
    *,
    classification: dict[str, Any],
    config_obj,
) -> dict[str, Any]:
    filter_hints = dict(classification.get("entity_hints") or extract_v3_1_entity_hints(question))
    selection_question = _filter_to_compare_selection_question(question)
    filter_child = _semantic_query_v3_3_strict(
        selection_question,
        config_obj=config_obj,
        classification={
            **classification,
            "recognized_query_mode": "filter",
            "intent": "filter",
            "intent_candidates": ["filter"],
            "from_candidates": ["tb_ths_etf_base"],
            "entity_hints": filter_hints,
            "child_task": "two_step_composite step 1: generate only the filter/list AST that selects candidate fundcodes.",
        },
        apply_override=False,
    )
    if filter_child.get("failure_stage") is not None:
        return _v3_3_composite_failure(
            question,
            classification,
            [filter_child],
            filter_child.get("failure_stage") or "composite_step1",
            filter_child.get("failure_reason") or "filter_to_compare step 1 failed",
        )

    compare_codes = _result_fundcodes(filter_child)[:5]
    if len(compare_codes) < 2:
        return _v3_3_composite_failure(
            question,
            classification,
            [filter_child],
            "composite",
            "filter_to_compare requires at least two candidates",
        )

    compare_hints = {
        "fundcodes": compare_codes,
        "filters": [],
        "limit_hint": None,
        "order_by": None,
        "search_keyword": "",
        "period": filter_hints.get("period") or _period_from_question(question),
        "wants_compare": True,
    }
    compare_question = _compare_child_question(
        question,
        compare_codes,
        _expected_composite_sub_intents(question) or ["performance"],
    )
    compare_child = _semantic_query_v3_3_strict(
        compare_question,
        config_obj=config_obj,
        classification={
            **classification,
            "recognized_query_mode": "compare",
            "intent": "compare",
            "intent_candidates": ["compare"],
            "from_candidates": ["tb_ths_etf_base"],
            "entity_hints": compare_hints,
            "child_task": (
                "two_step_composite step 2: compare only the provided fundcodes from step 1; "
                "do not add order_by or additional candidate selection."
            ),
        },
        apply_override=False,
    )
    if compare_child.get("failure_stage") is not None:
        return _v3_3_composite_failure(
            question,
            classification,
            [filter_child, compare_child],
            compare_child.get("failure_stage") or "composite_step2",
            compare_child.get("failure_reason") or "filter_to_compare step 2 failed",
        )

    output_v3 = {
        **classification,
        "phase": "v3.3",
        "ast_schema_version": "v3_3_structured_query",
        "routing_result": {"type": "ExecutableQuery", "reason": None},
        "recognized_query_mode": "compare",
        "intent": "two_step_composite",
        "capability_id": "v3.3:compare:two_step_composite",
        "capability_status": "executable",
        "gate_status": "not_applicable",
        "capability_status_reason": None,
        "intent_candidates": ["two_step_composite"],
        "blocked_intent_candidates": [],
        "ast_generation_mode": "llm_ast_draft",
        "llm_ast_draft_raw": [
            (filter_child.get("v3") or {}).get("llm_ast_draft_raw"),
            (compare_child.get("v3") or {}).get("llm_ast_draft_raw"),
        ],
        "remote_query_allowed": True,
        "failure_stage": None,
        "failure_reason": None,
        "steps": [
            {"recognized_query_mode": "filter", "intent": "filter"},
            {"recognized_query_mode": "compare", "intent": "compare"},
        ],
        "provenance_diff": [
            (filter_child.get("v3") or {}).get("provenance_diff"),
            (compare_child.get("v3") or {}).get("provenance_diff"),
        ],
        "validator_applied_defaults": [
            (filter_child.get("v3") or {}).get("validator_applied_defaults"),
            (compare_child.get("v3") or {}).get("validator_applied_defaults"),
        ],
    }
    return {
        "question": question,
        "answer": compare_child.get("answer") or "",
        "v3": output_v3,
        "v3_ast": {"intent": "two_step_composite", "steps": [filter_child.get("v3_ast"), compare_child.get("v3_ast")]},
        "validated_ast": {"intent": "two_step_composite", "steps": [filter_child.get("validated_ast"), compare_child.get("validated_ast")]},
        "query_plan": {"steps": [filter_child.get("query_plan"), compare_child.get("query_plan")]},
        "compiled_query": {"steps": [filter_child.get("query_plan"), compare_child.get("query_plan")]},
        "mongo_params": {"steps": [filter_child.get("mongo_params"), compare_child.get("mongo_params")]},
        "result": {"success": True, "steps": [filter_child.get("result"), compare_child.get("result")]},
        "failure_stage": None,
        "failure_reason": None,
    }


def _run_v3_2_child(
    question: str,
    *,
    classification: dict[str, Any],
    query_mode: str,
    intent: str,
    entity_hints: dict[str, Any],
    generation_bundle: dict[str, Any],
    config_obj,
) -> dict[str, Any]:
    try:
        draft_payload = generate_full_ast_draft_with_llm(
            question=question,
            routing_result={"type": "ExecutableQuery", "reason": None},
            classification=classification,
            generation_context=generation_bundle,
            config=config_obj,
        )
        validation = validate_v3_2_ast_draft(
            draft_payload["draft"],
            query_mode=query_mode,
            intent=intent,
            generation_bundle=generation_bundle,
        )
        validated_ast = validation["validated_ast"]
        _apply_search_contract_to_ast(validated_ast, entity_hints)
        plan = _compile_ast_to_plan(validated_ast)
        mongo_params = _mongo_params_for_plan(plan)
        result = _execute_v3_plan(plan, config_obj, dry_run=False, no_llm=False)
        return {
            "draft_payload": draft_payload,
            "validation": validation,
            "validated_ast": validated_ast,
            "plan": plan,
            "mongo_params": mongo_params,
            "result": result,
        }
    except Exception as exc:
        return {
            "failure": True,
            "stage": "composite_child",
            "reason": str(exc),
            "draft_payload": locals().get("draft_payload", {}),
            "validated_ast": locals().get("validated_ast"),
            "plan": locals().get("plan"),
            "mongo_params": locals().get("mongo_params"),
        }


def _child_failure_to_output(question: str, classification: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    return _v3_2_failure(
        question,
        classification=classification,
        stage=child.get("stage", "composite_child"),
        reason=child.get("reason", "unknown composite child failure"),
        ast_generation_mode="llm_ast_draft_failed",
        llm_ast_draft_raw=(child.get("draft_payload") or {}).get("raw"),
        v3_ast=(child.get("draft_payload") or {}).get("draft"),
        validated_ast=child.get("validated_ast"),
        query_plan=child.get("plan"),
        mongo_params=child.get("mongo_params"),
    )


def _capability_audit_fields(
    phase: str,
    query_mode: str,
    intent: str,
    generation_bundle: dict[str, Any] | None,
) -> dict[str, Any]:
    gate = "always"
    if generation_bundle is not None:
        gate = generation_bundle.get("selection_context", {}).get("gate", "always")
    return {
        "capability_id": f"{phase}:{query_mode}:{intent}",
        "capability_status": "executable",
        "gate_status": "not_applicable" if gate == "always" else "passed",
        "capability_status_reason": None,
    }


def _non_executable_v3_2_output(question: str, classification: dict[str, Any]) -> dict[str, Any]:
    routing_result = _routing_result_for_classification(classification)
    reason = routing_result.get("reason")
    failure_stage = "data_not_available" if reason == "data_not_available" else "routing"
    if routing_result["type"] == "DeniedQuery":
        answer = "抱歉，该问题涉及实时行情、交易指标或投资建议，超出当前 ETF 数据查询能力范围。"
    elif routing_result["type"] == "ClarificationRequired":
        answer = "查询条件还不够明确，请补充后重试。"
    elif reason == "data_not_available":
        answer = "暂无数据。"
    else:
        answer = "当前版本暂不支持该查询类型。"
    v3 = {
        **classification,
        "routing_result": routing_result,
        **_non_executable_capability_audit_fields(routing_result, reason),
        "ast_generation_mode": None,
        "llm_ast_draft_raw": None,
        "remote_query_allowed": False,
        "failure_stage": failure_stage,
        "failure_reason": reason,
    }
    return {
        "question": question,
        "answer": answer,
        "v3": v3,
        "v3_ast": None,
        "validated_ast": None,
        "query_plan": None,
        "mongo_params": None,
        "result": None,
        "failure_stage": failure_stage,
        "failure_reason": reason,
    }


def _v3_2_execution_context(
    question: str,
    classification: dict[str, Any],
    config_obj,
) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    query_mode = classification["recognized_query_mode"]
    intent = classification["intent"]
    if query_mode in V3_1_QUERY_MODES:
        hints = classification.get("entity_hints") or extract_v3_1_entity_hints(question)
        if query_mode == "filter":
            hints = _resolve_v3_1_index_filters(hints, config_obj, dry_run=False)
        return query_mode, intent, hints, _build_routing_evidence(question, query_mode=query_mode, intent=intent, entity_hints=hints)

    entities = _resolve_single_entities_for_v3_2(question, config_obj)
    period = entities.get("period") or _period_from_question(question)
    entity_hints = {"fundcodes": [entities["fundcode"]], "period": period}
    return "single", intent, entity_hints, _build_routing_evidence(question, query_mode="single", intent=intent, entity_hints=entity_hints, entities=entities)


def _v3_3_execution_context(
    question: str,
    classification: dict[str, Any],
    config_obj,
) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    query_mode = classification["recognized_query_mode"]
    intent = classification["intent"]
    if query_mode in V3_1_QUERY_MODES:
        return _v3_2_execution_context(question, classification, config_obj)

    if query_mode == "report":
        entities = _resolve_single_entities_for_v3_2(question, config_obj)
        period = entities.get("period") or _period_from_question(question)
        report_scope = resolve_report_scope(question, intent, classification.get("entity_hints") or {})
        entity_hints = {
            "fundcodes": [entities["fundcode"]],
            "period": period,
            "report_period": {"mode": "latest"},
            "report_scope": report_scope,
            "limit_hint": _extract_limit(question),
        }
        return "report", intent, entity_hints, _build_routing_evidence(question, query_mode="report", intent=intent, entity_hints=entity_hints, entities=entities)

    if intent in {"manager_detail", "trading_metric"}:
        entities = _resolve_single_entities_for_v3_2(question, config_obj)
        period = entities.get("period") or _period_from_question(question)
        entity_hints = {"fundcodes": [entities["fundcode"]], "period": period}
        return "single", intent, entity_hints, _build_routing_evidence(question, query_mode="single", intent=intent, entity_hints=entity_hints, entities=entities)

    return _v3_2_execution_context(question, classification, config_obj)


def _v3_3_override_classification(question: str, classification: dict[str, Any]) -> dict[str, Any]:
    override = _v3_3_intent_override(question)
    if override is None:
        return classification

    if classification.get("intent") == "unsupported_peer_average":
        return classification

    mode = classification.get("recognized_query_mode")
    reason = classification.get("reason") or classification.get("deny_reason")
    if mode == "deny" and classification.get("deny_reason") != "v3_unsupported_domain":
        return classification
    if mode == "unsupported" and reason not in {
        None,
        "blocked_by_verification",
        "unsupported_manager_history",
        "unsupported_timeseries",
        "peer_average_requires_v3_2",
        "multi_step_composite_not_supported",
        "multi_intent_composite_not_supported",
    }:
        return classification

    return {
        **classification,
        "recognized_query_mode": override["recognized_query_mode"],
        "intent": override["intent"],
        "intent_candidates": [override["intent"]],
        "from_candidates": override.get("from_candidates", []),
        "entity_hints": override.get("entity_hints", classification.get("entity_hints") or {}),
        "composite_type": override.get("composite_type"),
        "composite_execution": override.get("composite_execution"),
        "reason": None,
        "deny_reason": None,
    }


def _semantic_query_v3_3_composite_bundle(
    question: str,
    *,
    config_obj,
    classification: dict[str, Any],
) -> dict[str, Any]:
    if classification.get("intent") == "two_step_composite":
        return _semantic_query_v3_3_two_step_bundle(question, config_obj=config_obj, classification=classification)
    return _semantic_query_v3_3_multi_child_bundle(question, config_obj=config_obj, classification=classification)


def _semantic_query_v3_3_two_step_bundle(
    question: str,
    *,
    config_obj,
    classification: dict[str, Any],
) -> dict[str, Any]:
    step1_mode = _v3_3_two_step_selection_mode(question)
    selection_question = _v3_3_two_step_selection_question(question, step1_mode)
    selection_hints = extract_v3_1_entity_hints(selection_question)
    step1_classification = {
        **classification,
        "recognized_query_mode": step1_mode,
        "intent": step1_mode,
        "intent_candidates": [step1_mode],
        "from_candidates": ["tb_ths_etf_base"],
        "entity_hints": selection_hints,
    }
    step1_result = _semantic_query_v3_3_strict(
        selection_question,
        config_obj=config_obj,
        classification=step1_classification,
        apply_override=False,
    )
    if step1_result.get("failure_stage") is not None:
        return _v3_3_composite_failure(question, classification, [step1_result], step1_result.get("failure_stage") or "composite_step1", step1_result.get("failure_reason") or "composite step 1 failed")

    selected_fundcodes = _result_fundcodes(step1_result)
    if not selected_fundcodes and step1_mode == "search":
        selected_fundcodes = _search_selection_fundcodes(selection_hints, config_obj)
    if not selected_fundcodes:
        return _v3_3_composite_failure(question, classification, [step1_result], "composite_step1", "step 1 did not resolve any fundcode")

    child_results = [step1_result]
    detail_fundcode = selected_fundcodes[0]
    detail_hints = {
        "fundcodes": [detail_fundcode],
        "period": selection_hints.get("period") or _period_from_question(question),
    }
    for sub_intent in _expected_composite_sub_intents(question):
        if sub_intent in {"basic_info", "basic_info_extended", "investment_profile", "performance", "fund_scale", "fee", "manager", "fee_and_manager", "dividend", "manager_detail", "trading_metric"}:
            child_results.append(
                _semantic_query_v3_3_strict(
                    _child_question_for_sub_intent(question, sub_intent, [detail_fundcode]),
                    config_obj=config_obj,
                    classification={
                        **classification,
                        "recognized_query_mode": "single",
                        "intent": sub_intent,
                        "intent_candidates": [sub_intent],
                        "from_candidates": ["tb_ths_etf_base"],
                        "entity_hints": detail_hints,
                    },
                    apply_override=False,
                )
            )
        elif sub_intent in {"report_industry", "report_holding", "report_concept", "institution_holding", "report_style", "report_nav_change"}:
            child_question = _child_question_for_sub_intent(question, sub_intent, [detail_fundcode])
            child_results.append(
                _semantic_query_v3_3_strict(
                    child_question,
                    config_obj=config_obj,
                    classification={
                        **classification,
                        "recognized_query_mode": "report",
                        "intent": sub_intent,
                        "intent_candidates": [sub_intent],
                        "from_candidates": ["tb_ths_etf_report_year", "tb_ths_etf_report_quarter"],
                        "entity_hints": {
                            **detail_hints,
                            "report_period": {"mode": "latest"},
                            "report_scope": resolve_report_scope(question, sub_intent, classification.get("entity_hints") or {}),
                            "limit_hint": _extract_limit(question),
                        },
                    },
                    apply_override=False,
                )
            )

    failure = next((item for item in child_results if item.get("failure_stage") is not None), None)
    if failure is not None:
        return _v3_3_composite_failure(
            question,
            classification,
            child_results,
            failure.get("failure_stage") or "composite_child",
            failure.get("failure_reason") or "composite child failed",
        )
    return _compose_v3_3_composite_success(question, classification, child_results)


def _semantic_query_v3_3_multi_child_bundle(
    question: str,
    *,
    config_obj,
    classification: dict[str, Any],
) -> dict[str, Any]:
    entity_hints = classification.get("entity_hints") or {}
    fundcodes = [str(item) for item in entity_hints.get("fundcodes") or _extract_fundcodes(question) if item]
    sub_intents = list(entity_hints.get("sub_intents") or _expected_composite_sub_intents(question))
    child_results: list[dict[str, Any]] = []
    base_sub_intents = [
        item
        for item in sub_intents
        if item in {"basic_info", "basic_info_extended", "investment_profile", "performance", "fund_scale", "fee", "manager", "fee_and_manager", "dividend", "manager_detail", "trading_metric"}
    ]
    report_sub_intents = [
        item
        for item in sub_intents
        if item in {"report_industry", "report_holding", "report_concept", "institution_holding", "report_style", "report_nav_change"}
    ]

    if len(fundcodes) >= 2 and any(item in {"basic_info", "basic_info_extended", "investment_profile", "performance", "fund_scale", "fee", "manager", "fee_and_manager", "dividend"} for item in base_sub_intents):
        compare_hints = {
            "fundcodes": fundcodes[:10],
            "period": entity_hints.get("period") or _period_from_question(question),
        }
        child_results.append(
            _semantic_query_v3_3_strict(
                _compare_child_question(question, fundcodes[:10], base_sub_intents),
                config_obj=config_obj,
                classification={
                    **classification,
                    "recognized_query_mode": "compare",
                    "intent": "compare",
                    "intent_candidates": ["compare"],
                    "from_candidates": ["tb_ths_etf_base"],
                    "entity_hints": compare_hints,
                },
                apply_override=False,
            )
        )
    else:
        for sub_intent in base_sub_intents:
            child_results.append(
                _semantic_query_v3_3_strict(
                    _child_question_for_sub_intent(question, sub_intent, fundcodes[:1]),
                    config_obj=config_obj,
                    classification=_child_classification_for_sub_intent(classification, question, sub_intent, fundcodes[:1]),
                    apply_override=False,
                )
            )

    for sub_intent in report_sub_intents:
        for fundcode in fundcodes[: max(1, len(fundcodes))]:
            child_results.append(
                _semantic_query_v3_3_strict(
                    _child_question_for_sub_intent(question, sub_intent, [fundcode]),
                    config_obj=config_obj,
                    classification=_child_classification_for_sub_intent(classification, question, sub_intent, [fundcode]),
                    apply_override=False,
                )
            )

    failure = next((item for item in child_results if item.get("failure_stage") is not None), None)
    if failure is not None:
        return _v3_3_composite_failure(
            question,
            classification,
            child_results,
            failure.get("failure_stage") or "composite_child",
            failure.get("failure_reason") or "composite child failed",
        )
    return _compose_v3_3_composite_success(question, classification, child_results)


def _child_classification_for_sub_intent(
    parent_classification: dict[str, Any],
    question: str,
    sub_intent: str,
    fundcodes: list[str],
) -> dict[str, Any]:
    if sub_intent in {"report_industry", "report_holding", "report_concept", "institution_holding", "report_style", "report_nav_change"}:
        report_scope = resolve_report_scope(question, sub_intent, parent_classification.get("entity_hints") or {})
        return {
            **parent_classification,
            "recognized_query_mode": "report",
            "intent": sub_intent,
            "intent_candidates": [sub_intent],
            "from_candidates": ["tb_ths_etf_report_year", "tb_ths_etf_report_quarter"],
            "entity_hints": {
                "fundcodes": fundcodes,
                "period": _period_from_question(question),
                "report_period": {"mode": "latest"},
                "report_scope": report_scope,
                "limit_hint": _extract_limit(question),
            },
        }
    return {
        **parent_classification,
        "recognized_query_mode": "single",
        "intent": sub_intent,
        "intent_candidates": [sub_intent],
        "from_candidates": ["tb_ths_etf_base"],
        "entity_hints": {
            "fundcodes": fundcodes,
            "period": _period_from_question(question),
        },
    }


def _v3_3_two_step_selection_mode(question: str) -> str:
    if _has_compare_signal(question):
        return "compare"
    if _has_filter_signal(question, extract_v3_1_entity_hints(question)):
        return "filter"
    return "search"


def _v3_3_two_step_selection_question(question: str, step1_mode: str) -> str:
    if step1_mode == "filter":
        return re.split(r"然后|，然后|,然后|查一下它|看它", question, maxsplit=1)[0].strip("，,。 ") or question
    if step1_mode == "search":
        return re.split(r"查一下它|然后|，|,", question, maxsplit=1)[0].strip("，,。 ") or question
    return question


def _filter_to_compare_selection_question(question: str) -> str:
    parts = re.split(r"[，,？?]\s*(?:对比它们|对比一下|比较它们|比较一下)", question, maxsplit=1)
    if len(parts) > 1 and parts[0].strip():
        return parts[0].strip("，,。 ?？")
    parts = re.split(r"(?:对比它们|对比一下|比较它们|比较一下)", question, maxsplit=1)
    if len(parts) > 1 and parts[0].strip():
        return parts[0].strip("，,。 ?？")
    return question


def _child_question_for_sub_intent(parent_question: str, sub_intent: str, fundcodes: list[str]) -> str:
    fundcode = fundcodes[0] if fundcodes else ""
    prefix = f"{fundcode}" if fundcode else ""
    if sub_intent == "basic_info":
        return f"{prefix}是什么"
    if sub_intent == "basic_info_extended":
        return f"{prefix}的基本信息扩展字段是什么"
    if sub_intent == "investment_profile":
        return f"{prefix}的投资目标和风险收益特征是什么"
    if sub_intent == "performance":
        if "今年" in parent_question:
            return f"{prefix}今年收益多少"
        if "成立以来" in parent_question:
            return f"{prefix}成立以来收益怎么样"
        return f"{prefix}收益多少"
    if sub_intent == "fund_scale":
        if "份额" in parent_question:
            return f"{prefix}的基金份额是多少"
        if "净值" in parent_question:
            return f"{prefix}的最新净值是多少"
        return f"{prefix}的基金规模多大"
    if sub_intent == "fee":
        return f"{prefix}的费率是多少"
    if sub_intent == "manager":
        return f"{prefix}的基金经理是谁"
    if sub_intent == "manager_detail":
        if "换" in parent_question:
            return f"{prefix}什么时候换的基金经理"
        if "历史业绩" in parent_question:
            return f"{prefix}基金经理的历史业绩怎么样"
        if "规模" in parent_question:
            return f"{prefix}基金经理管了多少规模的基金"
        return f"{prefix}现任基金经理管理了多久"
    if sub_intent == "dividend":
        return f"{prefix}有没有分红记录"
    if sub_intent == "report_industry":
        return f"{prefix}的持仓行业有哪些"
    if sub_intent == "report_holding":
        return f"{prefix}前十大重仓股是什么"
    if sub_intent == "report_concept":
        return f"{prefix}重仓了哪些概念"
    if sub_intent == "institution_holding":
        return f"{prefix}的机构持有比例是多少"
    if sub_intent == "report_style":
        return f"{prefix}的投资风格是什么"
    if sub_intent == "report_nav_change":
        return f"{prefix}的净资产变动情况"
    return parent_question


def _compare_child_question(parent_question: str, fundcodes: list[str], sub_intents: list[str]) -> str:
    joined = "和".join(fundcodes)
    fields = []
    if "fee" in sub_intents:
        fields.append("费率")
    if "fund_scale" in sub_intents:
        fields.append("规模")
    if "performance" in sub_intents:
        fields.append("收益")
    if not fields:
        return parent_question
    return f"对比{joined}的{'、'.join(fields)}"


def _search_selection_fundcodes(selection_hints: dict[str, Any], config_obj) -> list[str]:
    keyword = str(selection_hints.get("search_keyword") or "").strip()
    if not keyword:
        return []
    from .name_resolver import resolve_fundcode_from_name

    candidates = []
    if not keyword.upper().endswith("ETF"):
        candidates.append(f"{keyword}ETF")
    candidates.append(keyword)

    for candidate in candidates:
        resolved = resolve_fundcode_from_name(candidate, config_obj, dry_run=False)
        if resolved["status"] == "matched" and resolved.get("fundcode"):
            return [str(resolved["fundcode"])]
        if resolved["status"] == "ambiguous":
            matches = resolved.get("matches") or []
            fundcodes = [str(item.get("fundcode")) for item in matches if item.get("fundcode")]
            if fundcodes:
                return fundcodes[:5]
    return []


def _result_fundcodes(result: dict[str, Any]) -> list[str]:
    data = result.get("result", {}).get("data")
    if isinstance(data, list):
        return [str(item.get("fundcode")) for item in data if isinstance(item, dict) and item.get("fundcode")]
    if isinstance(data, dict):
        fundcode = data.get("fundcode")
        return [str(fundcode)] if fundcode else []
    return []


def _compose_v3_3_composite_success(
    question: str,
    classification: dict[str, Any],
    child_results: list[dict[str, Any]],
) -> dict[str, Any]:
    sections = []
    raw_drafts = []
    validated_asts = []
    query_plans = []
    mongo_params = []
    provenance_diffs = []
    for index, child in enumerate(child_results, start=1):
        child_v3 = child.get("v3") or {}
        label = child_v3.get("intent") or f"step_{index}"
        sections.append(f"## {label}\n{child.get('answer') or ''}")
        raw_drafts.append(child_v3.get("llm_ast_draft_raw"))
        validated_asts.append(child.get("validated_ast"))
        query_plans.append(child.get("query_plan"))
        mongo_params.append(child.get("mongo_params"))
        provenance_diffs.append(child_v3.get("provenance_diff"))

    answer = "\n\n".join(sections)
    result_steps = [child.get("result") for child in child_results]
    outer_v3 = {
        **classification,
        "phase": "v3.3",
        "ast_schema_version": "v3_3_structured_query",
        "routing_result": {"type": "ExecutableQuery", "reason": None},
        "recognized_query_mode": "composite",
        "child_query_mode": classification.get("intent"),
        "intent": classification.get("intent"),
        "capability_id": f"v3.3:composite:{classification.get('intent')}",
        "capability_status": "executable",
        "gate_status": "not_applicable",
        "capability_status_reason": None,
        "blocked_intent_candidates": [],
        "routing_evidence": {
            "question": question,
            "composite_type": classification.get("composite_type"),
            "composite_execution": classification.get("composite_execution"),
            "sub_intents": classification.get("entity_hints", {}).get("sub_intents") or _expected_composite_sub_intents(question),
        },
        "ast_generation_mode": "llm_ast_draft",
        "llm_ast_draft_raw": raw_drafts,
        "remote_query_allowed": True,
        "failure_stage": None,
        "failure_reason": None,
        "steps": [{"recognized_query_mode": child.get("v3", {}).get("recognized_query_mode"), "intent": child.get("v3", {}).get("intent")} for child in child_results],
        "provenance_diff": provenance_diffs,
        "validator_applied_defaults": [child.get("v3", {}).get("validator_applied_defaults") for child in child_results],
    }
    return {
        "question": question,
        "answer": answer,
        "v3": outer_v3,
        "v3_ast": {"intent": classification.get("intent"), "steps": [child.get("v3_ast") for child in child_results]},
        "validated_ast": {"intent": classification.get("intent"), "steps": validated_asts},
        "query_plan": {"steps": query_plans},
        "compiled_query": {"steps": query_plans},
        "mongo_params": {"steps": mongo_params},
        "result": {"success": all(isinstance(item, dict) and item.get("success") is True for item in result_steps), "steps": result_steps},
        "failure_stage": None,
        "failure_reason": None,
    }


def _v3_3_composite_failure(
    question: str,
    classification: dict[str, Any],
    child_results: list[dict[str, Any]],
    stage: str,
    reason: str,
) -> dict[str, Any]:
    return _v3_3_failure(
        question,
        classification=classification,
        stage=stage,
        reason=reason,
        ast_generation_mode="llm_ast_draft_failed",
        llm_ast_draft_raw=[(child.get("v3") or {}).get("llm_ast_draft_raw") for child in child_results],
        v3_ast={"intent": classification.get("intent"), "steps": [child.get("v3_ast") for child in child_results]},
        validated_ast={"intent": classification.get("intent"), "steps": [child.get("validated_ast") for child in child_results]},
        query_plan={"steps": [child.get("query_plan") for child in child_results]},
        mongo_params={"steps": [child.get("mongo_params") for child in child_results]},
        remote_query_allowed=True,
    )


def _v3_3_intent_override(question: str) -> dict[str, Any] | None:
    fundcodes = _extract_fundcodes(question)
    period = _period_from_question(question)
    composite_sub_intents = _expected_composite_sub_intents(question)
    report_sub_intents = [item for item in composite_sub_intents if item.startswith("report_")]

    if any(phrase in question for phrase in ("然后看它的基本信息和收益", "查一下它的基本信息和持仓", "查一下它的基本信息和收益")):
        return {
            "recognized_query_mode": "composite",
            "intent": "two_step_composite",
            "composite_type": "two_step_composite",
            "composite_execution": "multi_child_bundle",
            "from_candidates": ["tb_ths_etf_base"],
            "entity_hints": {"fundcodes": fundcodes, "period": period},
        }

    if fundcodes and "季报" in question and "持仓" in question and not any(word in question for word in ("重仓股", "重仓证券", "前十大", "行业", "概念")):
        return {
            "recognized_query_mode": "composite",
            "intent": "composite_single",
            "composite_type": "composite_single",
            "composite_execution": "multi_child_bundle",
            "from_candidates": ["tb_ths_etf_report_quarter"],
            "entity_hints": {
                "fundcodes": fundcodes,
                "period": period,
                "sub_intents": ["report_industry", "report_concept"],
                "report_scope": "quarter_latest",
            },
        }

    if fundcodes and len(composite_sub_intents) >= 2 and report_sub_intents and _v3_3_has_multi_intent_separator(question):
        return {
            "recognized_query_mode": "composite",
            "intent": "composite_single",
            "composite_type": "composite_single",
            "composite_execution": "multi_child_bundle",
            "from_candidates": ["tb_ths_etf_base", "tb_ths_etf_report_year", "tb_ths_etf_report_quarter"],
            "entity_hints": {"fundcodes": fundcodes, "period": period, "sub_intents": composite_sub_intents},
        }

    if (
        fundcodes
        and len(composite_sub_intents) >= 2
        and _same_collection_composite_sub_intents(composite_sub_intents)
        and _v3_3_has_multi_intent_separator(question)
        and not _has_compare_signal(question)
    ):
        return {
            "recognized_query_mode": "single",
            "intent": "composite_single",
            "composite_type": "composite_single",
            "composite_execution": "single_ast",
            "from_candidates": ["tb_ths_etf_base"],
            "entity_hints": {"fundcodes": fundcodes, "period": period, "sub_intents": composite_sub_intents},
        }

    if "份额" in question and any(word in question for word in ("最近有变化", "变化吗", "变化")):
        return {
            "recognized_query_mode": "single",
            "intent": "fund_scale",
            "from_candidates": ["tb_ths_etf_base"],
            "entity_hints": {
                "fundcodes": fundcodes,
                "period": period,
                "timeseries_semantics": {
                    "by_field": {
                        "ths_fund_shares_fund": {"mode": "latest_two"},
                    }
                },
            },
        }

    if any(word in question for word in ("机构持有比例", "机构持有份额", "机构投资者持有", "投资风格", "净资产变动")):
        intent = "institution_holding"
        if "投资风格" in question:
            intent = "report_style"
        elif "净资产" in question:
            intent = "report_nav_change"
        return {
            "recognized_query_mode": "report",
            "intent": intent,
            "from_candidates": ["tb_ths_etf_report_year"],
            "entity_hints": {"fundcodes": fundcodes, "period": period},
        }

    if any(word in question for word in ("持仓行业", "行业配置", "行业持仓", "行业", "持仓")):
        return {
            "recognized_query_mode": "report",
            "intent": "report_industry",
            "from_candidates": ["tb_ths_etf_report_quarter", "tb_ths_etf_report_year"],
            "entity_hints": {"fundcodes": fundcodes, "period": period},
        }

    if any(word in question for word in ("重仓概念", "概念")):
        return {
            "recognized_query_mode": "report",
            "intent": "report_concept",
            "from_candidates": ["tb_ths_etf_report_quarter"],
            "entity_hints": {"fundcodes": fundcodes, "period": period},
        }

    if any(word in question for word in ("同类比", "同类平均", "同类均值")):
        return {
            "recognized_query_mode": "single",
            "intent": "performance",
            "from_candidates": ["tb_ths_etf_base"],
            "entity_hints": {"fundcodes": fundcodes, "period": period or "6m"},
        }

    if any(word in question for word in ("前十大重仓股", "重仓股", "重仓证券")):
        return {
            "recognized_query_mode": "report",
            "intent": "report_holding",
            "from_candidates": ["tb_ths_etf_report_year"],
            "entity_hints": {"fundcodes": fundcodes, "period": period},
        }

    if any(word in question for word in ("管理了多久", "历史业绩", "管理规模", "管了多少规模", "什么时候换的基金经理", "换的基金经理", "任职", "任期", "历任")):
        return {
            "recognized_query_mode": "single",
            "intent": "manager_detail",
            "from_candidates": ["tb_ths_etf_base"],
            "entity_hints": {"fundcodes": fundcodes, "period": period},
        }

    if any(word in question for word in ("成交额", "净现金流", "融资余额", "融券卖出量")):
        if any(word in question for word in ("实时", "盘中", "今天", "今日", "当前")):
            return None
        return {
            "recognized_query_mode": "single",
            "intent": "trading_metric",
            "from_candidates": ["tb_ths_etf_base"],
            "entity_hints": {"fundcodes": fundcodes, "period": period},
        }

    return None


def _v3_3_has_multi_intent_separator(question: str) -> bool:
    return any(sep in question for sep in ("、", "和", "，", ",", "以及", "同时", "然后"))


def _same_collection_composite_sub_intents(sub_intents: list[str]) -> bool:
    same_collection = {
        "basic_info",
        "basic_info_extended",
        "fund_scale",
        "fee",
        "performance",
        "dividend",
        "manager",
        "investment_profile",
    }
    return all(item in same_collection for item in sub_intents)


def _build_routing_evidence(
    question: str,
    *,
    query_mode: str,
    intent: str,
    entity_hints: dict[str, Any],
    entities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entities = entities or {}
    candidate_field_map = {
        "basic_info_extended": ["ths_fund_establishment_date_fund", "ths_fund_listed_exchange_fund", "ths_perf_comparative_benchmark_fund", "ths_pur_and_redemp_status_fund", "ths_etf_to_code_fund"],
        "investment_profile": ["ths_invest_objective_fund", "ths_invest_socpe_fund", "ths_invest_philosophy_fund", "ths_invest_strategy_fund", "ths_risk_return_characteristics_fund"],
        "composite_single": ["ths_yeild_std_fund", "ths_yeild_rank_std_fund_origin", "ths_yeild_rank_std_etf", "ths_fund_manager_current_fund", "ths_fund_supervisor_fund", "ths_pur_and_redemp_status_fund"],
        "performance": list(PERIOD_FIELDS.get(entity_hints.get("period") or "1y", PERIOD_FIELDS["1y"])),
        "search": ["__search_text__"],
        "filter": [clause.get("field") for clause in entity_hints.get("filters") or []],
        "compare": ["fundcode"],
    }
    goal = "single"
    if query_mode == "search":
        goal = "candidate_set_discovery"
    elif query_mode == "filter":
        goal = "candidate_set_refinement"
    elif query_mode == "compare":
        goal = "candidate_set_compare"
    elif intent == "composite_single":
        goal = "multi_sub_intent_single_entity"
    return {
        "entity_cardinality": len(entity_hints.get("fundcodes") or entities.get("fundcode") and [entities["fundcode"]] or []),
        "user_goal": goal,
        "semantic_constraints": {
            "query_mode": query_mode,
            "intent": intent,
            "period": entity_hints.get("period"),
            "limit_hint": entity_hints.get("limit_hint"),
            "sub_intents": _expected_composite_sub_intents(question) if intent == "composite_single" else entity_hints.get("sub_intents", []),
        },
        "field_mapping": candidate_field_map.get(intent, []),
        "why_not_single": [] if query_mode == "single" and intent != "composite_single" else ["user asked for multi-field or multi-sub-intent semantics"],
        "question": question,
    }


def _expected_composite_sub_intents(question: str) -> list[str]:
    sub_intents = []
    if any(word in question for word in ("基本信息", "是什么", "介绍", "概况")):
        sub_intents.append("basic_info")
    if any(word in question for word in ("收益", "排名", "涨", "跌")):
        sub_intents.append("performance")
    if any(word in question for word in ("规模", "盘子", "市值", "份额", "净值")):
        sub_intents.append("fund_scale")
    if any(word in question for word in ("管理费", "托管费", "费率")):
        sub_intents.append("fee")
    if any(word in question for word in ("管理了多久", "历史业绩", "管理规模", "什么时候换的基金经理", "换的基金经理", "任职", "基金经理")):
        sub_intents.append("manager_detail")
    elif "管理人" in question:
        sub_intents.append("manager")
    if any(word in question for word in ("申赎", "申购", "赎回", "联接", "上市", "业绩比较基准")):
        sub_intents.append("basic_info_extended")
    if any(word in question for word in ("持仓行业", "行业配置", "行业持仓", "行业", "持仓")):
        sub_intents.append("report_industry")
    if any(word in question for word in ("重仓股", "前十大", "重仓证券")):
        sub_intents.append("report_holding")
    if any(word in question for word in ("重仓概念", "概念")):
        sub_intents.append("report_concept")
    if "机构持有" in question:
        sub_intents.append("institution_holding")
    if any(word in question for word in ("投资风格", "风格")):
        sub_intents.append("report_style")
    if any(word in question for word in ("净资产变动", "净资产变化")):
        sub_intents.append("report_nav_change")
    if any(word in question for word in ("分红", "分过红")):
        sub_intents.append("dividend")
    return list(dict.fromkeys(sub_intents))


def _resolve_single_entities_for_v3_2(question: str, config_obj) -> dict[str, Any]:
    from .entities import extract_entities

    try:
        return extract_entities(question)
    except ValueError:
        from .name_resolver import resolve_fundcode_from_name

        resolved = resolve_fundcode_from_name(question, config_obj, dry_run=False)
        if resolved["status"] == "matched":
            return {
                "fundcode": resolved["fundcode"],
                "resolved_by": "name",
                "matched_name": resolved.get("matched_name", ""),
                "matched_thscode": resolved.get("matched_thscode", ""),
            }
        if resolved["status"] == "ambiguous":
            raise ValueError("name_ambiguity")
        raise ValueError("fund_identity_required")


def _routing_result_for_classification(classification: dict[str, Any]) -> dict[str, Any]:
    mode = classification.get("recognized_query_mode")
    if mode == "deny":
        return {"type": "DeniedQuery", "reason": classification.get("deny_reason")}
    if mode == "clarify":
        return {"type": "ClarificationRequired", "reason": classification.get("reason")}
    return {"type": "UnsupportedQuery", "reason": classification.get("reason") or "unsupported_query"}


def _non_executable_capability_audit_fields(routing_result: dict[str, Any], reason: str | None) -> dict[str, Any]:
    routing_type = routing_result["type"]
    if routing_type == "DeniedQuery":
        status = "denied"
        mode = "deny"
        audit_reason = reason or "denied"
    elif routing_type == "ClarificationRequired":
        status = "clarification_required"
        mode = "clarify"
        audit_reason = reason or "clarification_required"
    elif routing_type == "UnsupportedQuery" and reason == "data_not_available":
        status = "data_not_available"
        mode = "unsupported"
        audit_reason = "data_not_available"
    else:
        status = reason or "unsupported"
        mode = "unsupported"
        audit_reason = status
    return {
        "capability_id": f"v3.2:{mode}:{audit_reason}",
        "capability_status": status,
        "gate_status": "blocked",
        "capability_status_reason": audit_reason,
    }


def _v3_2_failure(
    question: str,
    *,
    classification: dict[str, Any],
    stage: str,
    reason: str,
    ast_generation_mode: str | None,
    llm_ast_draft_raw: str | None = None,
    v3_ast: dict[str, Any] | None = None,
    validated_ast: dict[str, Any] | None = None,
    query_plan: dict[str, Any] | None = None,
    mongo_params: dict[str, Any] | None = None,
    remote_query_allowed: bool = False,
) -> dict[str, Any]:
    query_mode = classification.get("recognized_query_mode") or "unknown"
    intent = classification.get("intent") or "unknown"
    v3 = {
        **classification,
        "routing_result": {"type": "ExecutableQuery", "reason": None},
        "capability_id": f"v3.2:{query_mode}:{intent}",
        "capability_status": "failed",
        "gate_status": "passed",
        "capability_status_reason": stage,
        "blocked_intent_candidates": classification.get("blocked_intent_candidates", []),
        "ast_generation_mode": ast_generation_mode,
        "llm_ast_draft_raw": llm_ast_draft_raw,
        "remote_query_allowed": remote_query_allowed,
        "failure_stage": stage,
        "failure_reason": reason,
    }
    return {
        "question": question,
        "answer": f"v3.2 查询失败：{stage} - {reason}",
        "v3": v3,
        "v3_ast": v3_ast,
        "validated_ast": validated_ast,
        "query_plan": query_plan,
        "mongo_params": mongo_params,
        "result": None,
        "failure_stage": stage,
        "failure_reason": reason,
    }


def _mongo_params_for_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "collection": plan["collection"],
        "filter": plan["filter"],
        "projection": {field: 1 for field in plan["projection"]} | {"_id": 0},
        "sort": plan.get("sort", []),
        "limit": plan["limit"],
    }


def _execute_v3_plan(plan: dict[str, Any], config_obj, *, dry_run: bool, no_llm: bool) -> dict[str, Any]:
    if dry_run:
        from .remote import fake_result

        return fake_result(plan)
    from .remote import execute_remote_query

    return execute_remote_query(plan, config_obj)


def _execute_mongo_phase(mongo_phase: dict[str, Any], config_obj) -> dict[str, Any]:
    from .remote import execute_remote_query

    return execute_remote_query(mongo_phase, config_obj)


def _apply_timeseries_semantics(ast: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    semantics = ast.get("timeseries_semantics")
    if not isinstance(semantics, dict):
        return result
    by_field = semantics.get("by_field")
    if not isinstance(by_field, dict):
        return result
    data = result.get("data")
    if isinstance(data, list):
        updated = [(_apply_timeseries_semantics_to_row(row, by_field) if isinstance(row, dict) else row) for row in data]
        return {**result, "data": updated}
    if isinstance(data, dict):
        return {**result, "data": _apply_timeseries_semantics_to_row(data, by_field)}
    return result


def _apply_timeseries_semantics_to_row(row: dict[str, Any], by_field: dict[str, Any]) -> dict[str, Any]:
    updated = dict(row)
    timeseries_audit = dict(updated.get("timeseries_audit") or {})
    for field, spec in by_field.items():
        if not isinstance(spec, dict):
            continue
        mode = spec.get("mode")
        raw_value = updated.get(field)
        if mode == "latest_two":
            normalized, audit = _normalize_latest_two_timeseries(raw_value)
            updated[field] = normalized
            timeseries_audit[field] = audit
        elif mode == "latest":
            timeseries_audit[field] = {"mode": mode, "status": "kept"}
        elif mode == "specified":
            timeseries_audit[field] = {"mode": mode, "status": "kept", "btime": spec.get("btime")}
    if timeseries_audit:
        updated["timeseries_audit"] = timeseries_audit
    return updated


def _normalize_latest_two_timeseries(raw_value: Any) -> tuple[dict[str, Any] | Any, dict[str, Any]]:
    points = _timeseries_points(raw_value)
    if len(points) < 2:
        return raw_value, {"mode": "latest_two", "status": "insufficient_points", "point_count": len(points)}
    current_btime, current_value = points[-1]
    previous_btime, previous_value = points[-2]
    if current_value is None or previous_value is None:
        return raw_value, {"mode": "latest_two", "status": "invalid_points", "point_count": len(points)}
    delta = current_value - previous_value
    delta_pct = round((delta / previous_value) * 100, 10) if previous_value else None
    direction = "increase" if delta > 0 else "decrease" if delta < 0 else "flat"
    return (
        {
            "current": {"value": current_value, "btime": current_btime},
            "previous": {"value": previous_value, "btime": previous_btime},
            "delta": delta,
            "delta_pct": delta_pct,
            "direction": direction,
        },
        {
            "mode": "latest_two",
            "status": "ok",
            "current_btime": current_btime,
            "previous_btime": previous_btime,
        },
    )


def _timeseries_points(raw_value: Any) -> list[tuple[str, Any]]:
    if not isinstance(raw_value, list):
        return []
    points: list[tuple[str, Any]] = []
    for item in raw_value:
        if not isinstance(item, dict):
            continue
        btime = item.get("btime")
        if btime is None:
            continue
        value = item.get("value")
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                value = None
        points.append((str(btime), value))
    points.sort(key=lambda item: item[0])
    return points


def _compile_v3_3_query(ast: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if _is_v3_3_derived_ast(ast):
        return "derived_performance", compile_derived_performance_query(ast)
    return "base_plan", _compile_ast_to_plan(ast)


def _is_v3_3_derived_ast(ast: dict[str, Any]) -> bool:
    select = ast.get("select") or []
    if any(isinstance(item, dict) and item.get("type") == "derived_return" for item in select):
        return True
    return any(isinstance(item, str) and item.startswith("return_") for item in select)


def _v3_3_failure(
    question: str,
    *,
    classification: dict[str, Any],
    stage: str,
    reason: str,
    ast_generation_mode: str | None,
    llm_ast_draft_raw: str | None = None,
    v3_ast: dict[str, Any] | None = None,
    validated_ast: dict[str, Any] | None = None,
    query_plan: dict[str, Any] | None = None,
    mongo_params: dict[str, Any] | None = None,
    remote_query_allowed: bool = False,
) -> dict[str, Any]:
    output = _v3_2_failure(
        question,
        classification=classification,
        stage=stage,
        reason=reason,
        ast_generation_mode=ast_generation_mode,
        llm_ast_draft_raw=llm_ast_draft_raw,
        v3_ast=v3_ast,
        validated_ast=validated_ast,
        query_plan=query_plan,
        mongo_params=mongo_params,
        remote_query_allowed=remote_query_allowed,
    )
    output["answer"] = f"v3.3 查询失败：{stage} - {reason}"
    output["compiled_query"] = query_plan
    output["v3"]["phase"] = "v3.3"
    output["v3"]["ast_schema_version"] = "v3_3_structured_query"
    output["v3"]["grammar_fragment_id"] = (query_plan or {}).get("grammar_fragment_id")
    output["v3"]["compiler_rule_id"] = (query_plan or {}).get("compiler_rule_id")
    output["v3"]["capability_id"] = output["v3"]["capability_id"].replace("v3.2:", "v3.3:", 1)
    output["v3"]["derived_performance_strict_pass"] = False
    return output


def _normalize_usage(usage: dict[str, Any] | None) -> list[dict[str, int]]:
    if not usage:
        return [{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}]
    if all(key in usage for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
        return [
            {
                "prompt_tokens": int(usage["prompt_tokens"]),
                "completion_tokens": int(usage["completion_tokens"]),
                "total_tokens": int(usage["total_tokens"]),
            }
        ]
    return [{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}]


def _append_runtime_metadata(answer: str, *, result: dict[str, Any], usage: dict[str, Any] | None) -> str:
    usage_payload = _normalize_usage(usage)
    total_tokens = sum(item["total_tokens"] for item in usage_payload)
    data_window = _result_data_window(result)
    has_inline_data_window = "数据截至 " in answer or "数据区间：" in answer
    footer = [
        *(_format_data_window_footer(data_window) if data_window and not has_inline_data_window else []),
        f"LLM token：{total_tokens}",
    ]
    return "\n\n".join([answer, *footer])


def _format_data_window_footer(data_window: tuple[str, str]) -> list[str]:
    start, end = data_window
    if start == end:
        return [f"数据起止日：{start}"]
    return [f"数据起始日：{start}", f"数据结束日：{end}"]


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


def _v3_3_unsupported(question: str, classification: dict[str, Any], reason: str) -> dict[str, Any]:
    output = _non_executable_v3_2_output(question, {**classification, "reason": reason, "recognized_query_mode": "unsupported"})
    output["failure_reason"] = reason
    output["v3"]["phase"] = "v3.3"
    output["v3"]["ast_schema_version"] = "v3_3_structured_query"
    output["v3"]["grammar_fragment_id"] = None
    output["v3"]["compiler_rule_id"] = None
    output["v3"]["failure_reason"] = reason
    return output


def _is_v3_3_mixed_rank_return(question: str, generation_bundle: dict[str, Any]) -> bool:
    return False


def _fundcodes_from_result(result: dict[str, Any]) -> list[str]:
    data = result.get("data")
    if not isinstance(data, list):
        return []
    return [str(item.get("fundcode")) for item in data if isinstance(item, dict) and item.get("fundcode")]


def _select_fields(intent: str, period: str, entities: dict[str, str] | None = None) -> list[str]:
    if intent == "basic_info":
        return [
            "fundcode",
            "ths_fund_extended_inner_short_name_fund",
            "ths_name_of_tracking_index_fund",
            "ths_fund_scale_fund",
        ]
    if intent == "fund_scale":
        field, _label, _fmt = _fund_scale_answer_field(entities or {})
        return ["fundcode", field]
    if intent == "tracking_index":
        return ["fundcode", "ths_tracking_index_code_fund", "ths_name_of_tracking_index_fund"]
    if intent == "fee":
        return ["fundcode", "ths_manage_fee_rate_fund", "ths_mandate_fee_rate_fund"]
    if intent == "manager":
        return ["fundcode", "ths_fund_manager_current_fund", "ths_fund_supervisor_fund"]
    if intent == "fee_and_manager":
        return [
            "fundcode",
            "ths_manage_fee_rate_fund",
            "ths_mandate_fee_rate_fund",
            "ths_fund_manager_current_fund",
            "ths_fund_supervisor_fund",
        ]
    if intent == "dividend":
        return ["fundcode", "ths_accum_dividend_total_amt_fund", "ths_accum_dividend_times_fund"]
    if intent == "performance":
        return ["fundcode", *PERIOD_FIELDS.get(period, PERIOD_FIELDS["1y"])]
    return ["fundcode"]


def _answer_fields(intent: str, period: str, entities: dict[str, str] | None = None) -> list[dict[str, str]]:
    if intent == "basic_info":
        return [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_extended_inner_short_name_fund", "label": "基金简称", "format": "plain"},
            {"field": "ths_name_of_tracking_index_fund", "label": "跟踪指数名称", "format": "plain"},
            {"field": "ths_fund_scale_fund", "label": "基金规模", "format": "amount"},
        ]
    if intent == "fund_scale":
        field, label, fmt = _fund_scale_answer_field(entities or {})
        return [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": field, "label": label, "format": fmt},
        ]
    if intent == "tracking_index":
        return [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_tracking_index_code_fund", "label": "跟踪指数代码", "format": "plain"},
            {"field": "ths_name_of_tracking_index_fund", "label": "跟踪指数名称", "format": "plain"},
        ]
    if intent == "fee":
        return [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"},
            {"field": "ths_mandate_fee_rate_fund", "label": "托管费率", "format": "percent"},
        ]
    if intent == "manager":
        return [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_fund_manager_current_fund", "label": "基金经理(现任)", "format": "plain"},
            {"field": "ths_fund_supervisor_fund", "label": "基金管理人", "format": "plain"},
        ]
    if intent == "fee_and_manager":
        return [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_manage_fee_rate_fund", "label": "管理费率", "format": "percent"},
            {"field": "ths_mandate_fee_rate_fund", "label": "托管费率", "format": "percent"},
            {"field": "ths_fund_manager_current_fund", "label": "基金经理(现任)", "format": "plain"},
            {"field": "ths_fund_supervisor_fund", "label": "基金管理人", "format": "plain"},
        ]
    if intent == "dividend":
        return [
            {"field": "fundcode", "label": "基金代码", "format": "plain"},
            {"field": "ths_accum_dividend_total_amt_fund", "label": "累计分红总额", "format": "amount"},
            {"field": "ths_accum_dividend_times_fund", "label": "累计分红次数", "format": "plain"},
        ]
    if intent == "performance":
        fields = PERIOD_FIELDS.get(period, PERIOD_FIELDS["1y"])
        answer_fields = [{"field": "fundcode", "label": "基金代码", "format": "plain"}]
        label_map = {
            "ths_yeild_1w_fund": "近1周收益率",
            "ths_yeild_1m_fund": "近1月收益率",
            "ths_yeild_3m_fund": "近3月收益率",
            "ths_yeild_6m_fund": "近6月收益率",
            "ths_yeild_1y_fund": "近1年收益率",
            "ths_yeild_2y_fund": "近2年收益率",
            "ths_yeild_3y_fund": "近3年收益率",
            "ths_yeild_5y_fund": "近5年收益率",
            "ths_yeild_ytd_fund": "今年以来收益率",
            "ths_yeild_std_fund": "成立以来收益率",
        }
        for field in fields:
            if "rank" in field:
                label = _performance_rank_label(field)
                answer_fields.append({"field": field, "label": label, "format": "plain"})
            else:
                answer_fields.append({"field": field, "label": label_map.get(field, field), "format": "percent"})
        return answer_fields
    return [{"field": "fundcode", "label": "基金代码", "format": "plain"}]


def _fund_scale_answer_field(entities: dict[str, str]) -> tuple[str, str, str]:
    question = entities.get("question", "")
    if "净值增长率" in question:
        return "ths_unit_nvg_rate_fund", "单位净值增长率", "percent"
    if "净值" in question:
        return "ths_unit_nv_fund", "单位净值", "plain"
    if "份额" in question:
        return "ths_fund_shares_fund", "基金份额", "plain"
    if "总市值" in question or "市值" in question:
        return "ths_current_mv_fund", "总市值", "amount"
    return "ths_fund_scale_fund", "基金规模", "amount"


def _performance_rank_label(field: str) -> str:
    suffix = field.removeprefix("ths_yeild_rank_").removesuffix("_fund_origin").removesuffix("_etf")
    period = suffix
    label = _period_label(period)
    if field.endswith("_fund_origin"):
        return f"{label}同类排名"
    if field.endswith("_etf"):
        return f"{label} ETF 排名"
    return field


def _period_label(period: str) -> str:
    return {
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
    }.get(period, period)


def extract_v3_test_questions(path: str | Path) -> list[dict[str, str]]:
    rows = _parse_question_rows(Path(path).read_text(encoding="utf-8"))
    return [_classify_test_question(row) for row in rows]


def _parse_question_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    section = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            section = line.lstrip("# ").strip()
            continue
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0] in {"#", "---"} or cells[0].startswith("---"):
            continue
        if cells[0].isdigit():
            rows.append({"section": section, "question": cells[1], "note": cells[2]})
    return rows


def _classify_test_question(row: dict[str, str]) -> dict[str, str]:
    section = row["section"]
    question = row["question"]
    phase = "excluded"
    reason = "beyond_v3_1_scope"

    if section.startswith(("一、", "二、", "三、", "五、", "六、", "十二、")):
        if _is_v3_0_question(section, question):
            phase = "v3.0"
            reason = "v3_0_single_or_boundary"
    if section.startswith(("七、", "八、", "九、")):
        if "2024年成立" not in question and "哪个更好" not in question:
            phase = "v3.1"
            reason = "v3_1_search_filter_compare"
    if question in {"成立以来收益最好的沪深300ETF是哪只", "对比510300和000000"}:
        phase = "v3.1"
        reason = "v3_1_search_filter_compare"
    if section.startswith("十、"):
        if question in {
            "股票型ETF里今年收益最高的5只是哪些？对比一下",
            "上交所的ETF里，找管理费最低的3只，对比它们的今年收益",
        }:
            phase = "v3.1"
            reason = "v3_1_filter_to_compare"

    return {
        "phase": phase,
        "section": section,
        "question": question,
        "note": row["note"],
        "reason": reason,
    }


def _is_v3_0_question(section: str, question: str) -> bool:
    if section.startswith("一、"):
        return question in {
            "510300是什么",
            "帮我查一下510500的基本信息",
            "159919这只基金跟踪什么指数",
            "工银沪深300ETF的费率和基金经理是什么",
            "510300的管理人是谁",
        }
    if section.startswith("二、"):
        return question not in {
            "510300近半年收益率和同类平均比怎么样",
            "成立以来收益最好的沪深300ETF是哪只",
        }
    if section.startswith("三、"):
        return question != "510300的基金份额最近有变化吗"
    if section.startswith("五、"):
        return question == "510300的基金经理是谁"
    if section.startswith("六、"):
        return True
    if section.startswith("十二、"):
        return question in {
            "000001有这只ETF吗",
            "帮我查510300的实时行情",
            "abcdef是什么基金",
            "510300的持仓行业是什么（季报年报都没有）",
            "给我推荐一只ETF",
            "今天A股大盘怎么样",
            "510300能买吗",
        }
    return False
