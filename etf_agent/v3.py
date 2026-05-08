from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from .candidates import PERIOD_FIELDS

SUPPORTED_INTENTS = {
    "basic_info",
    "fund_scale",
    "tracking_index",
    "performance",
    "fee",
    "manager",
    "fee_and_manager",
    "dividend",
}

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
        "个股分析", "大盘", "A股", "上证", "深证",
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

    forced = _force_v3_0_single_classification(question, entities)
    if forced is not None:
        return forced

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


def _force_deny_classification(question: str) -> dict[str, Any] | None:
    if any(word in question for word in ("能买吗", "能买吗", "能不能买", "值不值得", "该不该买", "推荐", "给我挑", "适合买入", "要不要入手")):
        return {
            "recognized_query_mode": "deny",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "deny_reason": "investment_advice",
        }
    if any(word in question for word in ("实时行情", "实时", "今日涨跌", "成交额", "融资余额", "融券", "K线", "MACD", "均线", "RSI")):
        return {
            "recognized_query_mode": "deny",
            "intent": None,
            "intent_candidates": [],
            "from_candidates": [],
            "deny_reason": "v3_unsupported_domain",
        }
    return None


def _force_v3_0_single_classification(question: str, entities: dict[str, str]) -> dict[str, Any] | None:
    has_fund_identity = bool(entities.get("fundcode")) or bool(re.search(r"(?<!\d)\d{6}(?!\d)", question))
    if not has_fund_identity:
        return None

    real_time_markers = ("实时", "盘中", "当前", "现在", "今天", "今日", "估值")
    if "净值" in question and not any(marker in question for marker in real_time_markers):
        return _single_classification("fund_scale", entities)
    if "ETF排" in question or "ETF 排" in question:
        return _single_classification("performance", entities)
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


def _compile_ast_to_plan(ast: dict[str, Any]) -> dict[str, Any]:
    """Compile v3 AST into a plan dict compatible with execute_remote_query + format_answer."""
    plan: dict[str, Any] = {
        "collection": ast["from"],
        "filter": {},
        "projection": list(ast["select"]),
        "limit": ast["limit"],
        "answer_fields": list(ast["answer_fields"]),
    }
    # Convert AST where clauses to simple filter dict (v3.0 only supports eq on fundcode)
    for clause in ast.get("where", []):
        if clause.get("op") == "eq":
            plan["filter"][clause["field"]] = clause["value"]
    return plan


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

    if mode == "deny":
        return {
            "question": question,
            "answer": "抱歉，该问题涉及实时行情、交易指标或投资建议，超出当前 ETF 数据查询能力范围。",
            "v3": classification,
        }
    if mode == "unsupported":
        return {
            "question": question,
            "answer": "当前版本暂不支持该查询类型。",
            "v3": classification,
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
                "v3": classification,
            }
    entities["question"] = question

    # ---- Step 3: build v3 AST (no re-classification) ----
    intent = classification["intent"]
    ast = build_v3_ast(intent, entities)
    plan = _compile_ast_to_plan(ast)

    # ---- Step 4: execute query ----
    if dry_run or no_llm:
        from .remote import fake_result

        result = fake_result(plan)
    else:
        from .remote import execute_remote_query

        try:
            result = execute_remote_query(plan, config_obj)
        except RuntimeError as exc:
            return {
                "question": question,
                "answer": f"远端查询失败：{exc}",
                "v3": classification,
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
        "v3": classification,
        "v3_ast": ast,
        "entities": entities,
        "query_plan": plan,
        "result": result,
    }


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
