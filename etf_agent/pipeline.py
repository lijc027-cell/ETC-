from __future__ import annotations

from pathlib import Path
from typing import Any

from .candidates import enhance_candidates
from .config import load_config, require_runtime_config, require_ssh_config
from .dictionary import parse_data_dictionary
from .entities import extract_entities
from .formatter import chinese_mapping, format_answer
from .llm import deterministic_plan, generate_query_plan, is_plan_schema_like
from .name_resolver import resolve_fundcode_from_name
from .plan import build_sql_like, mongo_params, validate_query_plan
from .remote import execute_remote_query, fake_result
from .retrieval import retrieve_mappings


def semantic_query(question: str, *, root: Path | str | None = None, dry_run: bool = False, no_llm: bool = False) -> dict[str, Any]:
    root_path = Path(root) if root else Path(__file__).resolve().parents[1]
    config = load_config(root_path)
    dictionary_path = root_path / "references" / "data-dictionary.md"
    debug = {"stages": []}

    try:
        if not dry_run:
            require_ssh_config(config) if no_llm else require_runtime_config(config)
        mappings = parse_data_dictionary(dictionary_path)
        debug["stages"].append({"name": "dictionary_parse", "status": "ok", "detail": {"fields": len(mappings)}})

        entities = _extract_or_resolve_entities(question, config, dry_run)
        debug["stages"].append({"name": "entity_extraction", "status": "ok", "detail": entities})

        vector_results = retrieve_mappings(question, mappings, dictionary_path, config, offline=dry_run or no_llm)
        if not vector_results:
            raise RuntimeError("阶段：向量召回\n错误：向量召回结果为空")
        candidates = enhance_candidates(question, entities, mappings, vector_results)
        candidate_ids = [candidate["id"] for candidate in candidates]
        debug["stages"].append({"name": "retrieval", "status": "ok", "detail": {"count": len(candidates)}})

        raw_plan = deterministic_plan(question, entities, candidates) if (dry_run or no_llm) else generate_query_plan(question, entities, candidates, config)
        if not dry_run and not no_llm and not is_plan_schema_like(raw_plan):
            debug["stages"].append({"name": "query_plan_generation", "status": "fallback", "detail": raw_plan})
            raw_plan = deterministic_plan(question, entities, candidates)
        else:
            debug["stages"].append({"name": "query_plan_generation", "status": "ok", "detail": raw_plan})

        plan = validate_query_plan(raw_plan, mappings, entities, candidate_ids)
        sql_like = build_sql_like(plan)
        params = mongo_params(plan)
        debug["stages"].append({"name": "query_plan_validation", "status": "ok", "detail": {"sql_like": sql_like}})

        result = fake_result(plan) if dry_run else execute_remote_query(plan, config)
        debug["stages"].append({"name": "remote_query", "status": "ok", "detail": {"success": result.get("success")}})

        answer = format_answer(plan, result)
        return {
            "question": question,
            "entities": entities,
            "retrieved_mappings": candidates,
            "query_plan": plan,
            "sql_like": sql_like,
            "mongo_params": params,
            "result": result,
            "field_labels": chinese_mapping(plan),
            "answer": answer,
            "debug": debug,
        }
    except Exception as exc:
        debug["stages"].append({"name": "error", "status": "failed", "detail": str(exc)})
        payload = {"question": question, "error": str(exc), "debug": debug}
        if hasattr(exc, "matches"):
            payload["matches"] = exc.matches
        return payload


class NameResolutionError(RuntimeError):
    def __init__(self, message: str, matches: list[dict] | None = None):
        super().__init__(message)
        self.matches = matches or []


def _extract_or_resolve_entities(question: str, config, dry_run: bool) -> dict[str, str]:
    try:
        return extract_entities(question)
    except ValueError:
        resolved = resolve_fundcode_from_name(question, config, dry_run=dry_run)
        if resolved["status"] == "matched":
            return {
                "fundcode": resolved["fundcode"],
                "resolved_by": "name",
                "matched_name": resolved["matched_name"],
                "matched_thscode": resolved.get("matched_thscode", ""),
            }
        if resolved["status"] == "ambiguous":
            raise NameResolutionError(
                "阶段：ETF 名称解析\n错误：匹配到多只 ETF，请补充具体产品",
                resolved["matches"],
            )
        raise NameResolutionError("阶段：ETF 名称解析\n错误：未找到匹配的 ETF 产品")
