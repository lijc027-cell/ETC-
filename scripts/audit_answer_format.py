from __future__ import annotations

from typing import Any


TOKEN_PREFIX = "LLM token："
RUNTIME_PREFIXES = ("查询起始时间：", "查询结束时间：")
CUTOFF_PREFIXES = ("数据截至 ", "截止时间：", "数据结束日：", "数据区间：")


def format_audit_answer(answer: str, *, result: dict[str, Any] | None = None, total_tokens: int | None = None) -> str:
    lines = [line for line in str(answer or "").splitlines() if not line.startswith(RUNTIME_PREFIXES)]
    existing_token = _pop_existing_token(lines)
    _collapse_blank_runs(lines)
    token = existing_token or _format_token(total_tokens if total_tokens is not None else llm_total_tokens(result or {}))
    if token:
        _insert_token_after_cutoff(lines, token)
    return "\n".join(lines).strip()


def llm_total_tokens(result: dict[str, Any]) -> int | None:
    values: list[int] = []
    _collect_usage_records(result.get("llm_usage"), values)
    _collect_usage_records((result.get("v3") or {}).get("llm_usage"), values)
    _collect_usage_records(result.get("result"), values)
    return sum(values) if values else 0


def _collect_usage_records(value: Any, values: list[int]) -> None:
    if isinstance(value, dict):
        if isinstance(value.get("total_tokens"), int):
            values.append(value["total_tokens"])
            return
        for item in value.values():
            _collect_usage_records(item, values)
    elif isinstance(value, list):
        for item in value:
            _collect_usage_records(item, values)


def _pop_existing_token(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        if line.startswith(TOKEN_PREFIX):
            return lines.pop(index)
    return None


def _collapse_blank_runs(lines: list[str]) -> None:
    index = len(lines) - 1
    while index > 0:
        if not lines[index].strip() and not lines[index - 1].strip():
            lines.pop(index)
        index -= 1


def _format_token(total_tokens: int | None) -> str | None:
    if total_tokens is None:
        return None
    return f"{TOKEN_PREFIX}{total_tokens}"


def _insert_token_after_cutoff(lines: list[str], token: str) -> None:
    insert_at = _last_cutoff_line_index(lines)
    if insert_at is None:
        if lines and lines[-1].strip():
            lines.extend(["", token])
        else:
            lines.append(token)
        return
    lines.insert(insert_at + 1, token)


def _last_cutoff_line_index(lines: list[str]) -> int | None:
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].startswith(CUTOFF_PREFIXES):
            return index
    return None
