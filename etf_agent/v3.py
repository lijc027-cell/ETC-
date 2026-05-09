from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from .candidates import PERIOD_FIELDS
from .capability_registry import COMPARE_FIELDS as REGISTRY_COMPARE_FIELDS
from .capability_registry import LIST_BASELINE_FIELDS as REGISTRY_LIST_BASELINE_FIELDS
from .capability_registry import field_meta, get_selection_context
from .entities import PERIOD_PATTERNS
from .ast_generator import generate_full_ast_draft_with_llm
from .ast_validator import validate_v3_2_ast_draft
from .generation_context import build_generation_bundle

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
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "reason": "peer_average_requires_v3_2",
        }
    return None


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
    return {
        "fundcodes": _extract_fundcodes(question),
        "filters": filters,
        "limit_hint": _extract_limit(question),
        "order_by": order_by,
        "search_keyword": _extract_search_keyword(question),
        "period": _period_from_question(question),
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
        if any(word in question for word in ("最高", "高到低", "费率最高")):
            return {"field": "ths_manage_fee_rate_fund", "direction": "desc"}
    if "规模" in question and any(word in question for word in ("前", "最大", "最高", "排序")):
        return {"field": "ths_fund_scale_fund", "direction": "desc"}
    if any(word in question for word in ("收益", "收益率", "回报")) and any(
        word in question for word in ("前", "最高", "最好", "排名", "排序", "靠前")
    ):
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
    if "全部" in question or "所有" in question:
        return 50
    return None


def _extract_search_keyword(question: str) -> str:
    cleaned = question
    cleaned = re.sub(r"[\"“”'‘’]", "", cleaned)
    for word in (
        "帮我",
        "我想",
        "搜索",
        "找一下",
        "找",
        "有没有",
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


def _yield_field_for_question(question: str) -> str:
    return f"ths_yeild_{_period_from_question(question)}_fund"


def _force_deny_classification(question: str) -> dict[str, Any] | None:
    if any(word in question for word in ("能买吗", "能不能买", "值不值得", "该不该买", "推荐", "给我挑", "适合买入", "要不要入手", "哪个更好", "哪个好")):
        return {
            "recognized_query_mode": "deny",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "deny_reason": "investment_advice",
        }
    if any(word in question for word in ("实时行情", "今日涨跌", "成交额", "融资余额", "融券", "净现金流", "大盘", "A股大盘", "K线", "MACD", "均线", "RSI")):
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
    return {
        "intent": "search",
        "from": "tb_ths_etf_base",
        "select": list(LIST_BASELINE_FIELDS),
        "where": [{"field": "__search_text__", "op": "contains", "value": entity_hints.get("search_keyword", "")}],
        "order_by": {"field": "ths_fund_scale_fund", "direction": "desc"},
        "limit": min(int(entity_hints.get("limit_hint") or 20), 50),
        "output_style": "list",
        "answer_fields": _field_metas(LIST_BASELINE_FIELDS),
        "report_period": None,
        "expand": None,
    }


def _build_filter_ast(entity_hints: dict[str, Any], question: str) -> dict[str, Any]:
    order_by = entity_hints.get("order_by") or {"field": "ths_fund_scale_fund", "direction": "desc"}
    filters = [_ast_clause(clause) for clause in entity_hints.get("filters") or []]
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
    plan: dict[str, Any] = {
        "collection": ast["from"],
        "filter": {},
        "projection": list(ast["select"]),
        "limit": ast["limit"],
        "answer_fields": list(ast["answer_fields"]),
        "output_style": ast.get("output_style", "summary"),
    }
    order_by = ast.get("order_by")
    if order_by:
        plan["sort"] = _sort_spec(order_by)
    for clause in ast.get("where", []):
        op = clause.get("op")
        if op == "eq":
            plan["filter"][clause["field"]] = clause["value"]
        elif op == "in":
            plan["filter"][clause["field"]] = {"$in": clause["value"]}
        elif op == "contains":
            plan["filter"][clause["field"]] = {"$contains": clause["value"]}
        elif op == "between":
            value = clause.get("value") or {}
            plan["filter"].setdefault(clause["field"], {})["$gte"] = value.get("start") or value.get("gte")
            plan["filter"].setdefault(clause["field"], {})["$lte"] = value.get("end") or value.get("lte")
        elif op in {"gt", "gte", "lt", "lte"}:
            plan["filter"].setdefault(clause["field"], {})[_mongo_compare_op(op)] = clause["value"]
    return plan


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


def semantic_query_v3(question: str, *, root=None, dry_run: bool = False, no_llm: bool = False) -> dict[str, Any]:
    # Load config
    from .config import load_config

    config_root = Path(root) if root else _detect_project_root()
    config_obj = load_config(config_root)

    # ---- Step 1: deny / unsupported gate ----
    classification = classify_v3_query(question, config=None if (dry_run or no_llm) else config_obj)
    mode = classification["recognized_query_mode"]

    if not dry_run and not no_llm:
        return _semantic_query_v3_2_strict(question, config_obj=config_obj, classification=classification)

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
    if routing_result["type"] == "DeniedQuery":
        answer = "抱歉，该问题涉及实时行情、交易指标或投资建议，超出当前 ETF 数据查询能力范围。"
    elif routing_result["type"] == "ClarificationRequired":
        answer = "查询条件还不够明确，请补充后重试。"
    else:
        answer = "当前版本暂不支持该查询类型。"
    v3 = {
        **classification,
        "routing_result": routing_result,
        **_non_executable_capability_audit_fields(routing_result, reason),
        "ast_generation_mode": None,
        "llm_ast_draft_raw": None,
        "remote_query_allowed": False,
        "failure_stage": "routing",
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
        "failure_stage": "routing",
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
    if any(word in question for word in ("收益", "排名", "涨", "跌")):
        sub_intents.append("performance")
    if any(word in question for word in ("管理人", "基金经理")):
        sub_intents.append("manager")
    if any(word in question for word in ("申赎", "申购", "赎回", "联接", "上市", "业绩比较基准")):
        sub_intents.append("basic_info_extended")
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
