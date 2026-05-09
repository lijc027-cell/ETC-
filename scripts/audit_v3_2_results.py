#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etf_agent import semantic_query_v3


COVERAGE = ROOT / "docs" / "v3-coverage-matrix.md"
OUT_MD = ROOT / "answer" / "audit-v3.2-results.md"
OUT_JSON = ROOT / "answer" / "raw" / "audit-v3.2-results.json"


@dataclass(frozen=True)
class CoverageRow:
    values: dict[str, str]

    def __getitem__(self, key: str) -> str:
        return self.values[key]

    @property
    def question(self) -> str:
        return self.values["question"]

    @property
    def question_id(self) -> str:
        return self.values["question_id"]


def main() -> int:
    rows = load_coverage_rows(COVERAGE)
    records = []
    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{len(rows)}] {row.question_id} {row.question}", flush=True)
        if row["release_scope"] != "v3_2_required":
            result = _static_out_of_scope_result(row)
        else:
            try:
                result = semantic_query_v3(row.question, root=ROOT)
            except Exception as exc:
                result = _runtime_exception_result(row.question, exc)
        records.append(evaluate_row(row, result))

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(_markdown(records), encoding="utf-8")
    print(OUT_JSON)
    print(OUT_MD)
    return 1 if any(record["status"] == "FAIL" and record["release_scope"] == "v3_2_required" for record in records) else 0


def _runtime_exception_result(question: str, exc: Exception) -> dict[str, Any]:
    return {
        "question": question,
        "answer": f"v3.2 查询失败：runtime_exception - {exc}",
        "v3": {
            "routing_result": {"type": "ExecutableQuery", "reason": None},
            "recognized_query_mode": None,
            "intent": None,
            "ast_generation_mode": "llm_ast_draft_failed",
            "remote_query_allowed": False,
            "failure_stage": "runtime_exception",
            "failure_reason": str(exc),
        },
        "v3_ast": None,
        "validated_ast": None,
        "query_plan": None,
        "mongo_params": None,
        "result": None,
        "failure_stage": "runtime_exception",
        "failure_reason": str(exc),
    }


def _static_out_of_scope_result(row: CoverageRow) -> dict[str, Any]:
    return {
        "question": row.question,
        "answer": "不在 v3.2 能力范围",
        "v3": {
            "routing_result": {"type": row["routing_result.type"], "reason": "out_of_v3_2_scope"},
            "recognized_query_mode": _none_if_null(row["recognized_query_mode"]),
            "intent": _none_if_null(row["expected_intent_or_profile"]),
            "ast_generation_mode": _none_if_null(row["ast_generation_mode"]),
            "remote_query_allowed": False,
            "failure_stage": None,
            "failure_reason": "out_of_v3_2_scope",
            "capability_id": f"v3.2:skip:{row['release_scope']}",
            "capability_status": "out_of_scope",
            "gate_status": "skipped",
            "capability_status_reason": "out_of_v3_2_scope",
        },
        "v3_ast": None,
        "validated_ast": None,
        "query_plan": None,
        "mongo_params": None,
        "result": None,
        "failure_stage": None,
        "failure_reason": "out_of_v3_2_scope",
    }


def load_coverage_rows(path: Path) -> list[CoverageRow]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header: list[str] | None = None
    rows: list[CoverageRow] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0] == "question_id":
            header = cells
            continue
        if header is None or not cells or cells[0].startswith("---"):
            continue
        if len(cells) != len(header):
            continue
        rows.append(CoverageRow(dict(zip(header, cells, strict=True))))
    return rows


def evaluate_row(row: CoverageRow, result: dict[str, Any]) -> dict[str, Any]:
    v3 = result.get("v3") or {}
    release_scope = row["release_scope"]
    in_scope = release_scope == "v3_2_required"
    expected_type = row["routing_result.type"]
    expected_mode = _none_if_null(row["recognized_query_mode"])
    expected_intent = _none_if_null(row["expected_intent_or_profile"])
    expected_ast_mode = _none_if_null(row["ast_generation_mode"])
    expected_remote = _bool(row["remote_query_allowed"])
    actual_type = (v3.get("routing_result") or {}).get("type") or _legacy_type(v3)
    actual_mode = v3.get("recognized_query_mode")
    actual_intent = v3.get("intent")
    actual_ast_mode = v3.get("ast_generation_mode")
    actual_remote = bool(v3.get("remote_query_allowed"))
    plan = result.get("query_plan")
    remote_result = result.get("result")
    answer = str(result.get("answer") or "")
    display_answer = _brief_user_answer(answer) if in_scope else "不在 v3.2 能力范围"

    failures = []
    if in_scope:
        if actual_type != expected_type:
            failures.append(f"routing type expected {expected_type}, got {actual_type}")
        if expected_mode is not None and actual_mode != expected_mode:
            failures.append(f"mode expected {expected_mode}, got {actual_mode}")
        if expected_intent not in {None, "-"} and _is_executable_type(expected_type) and actual_intent != expected_intent:
            failures.append(f"intent expected {expected_intent}, got {actual_intent}")
        if expected_ast_mode != actual_ast_mode:
            failures.append(f"ast_generation_mode expected {expected_ast_mode}, got {actual_ast_mode}")
        if expected_remote != actual_remote:
            failures.append(f"remote_query_allowed expected {expected_remote}, got {actual_remote}")

        if _is_executable_type(expected_type):
            failures.extend(_check_executable_contract(result, row))
        else:
            failures.extend(_check_non_executable_contract(result))

        remote_status = _remote_status(remote_result, expected_remote)
        formatter_status = _formatter_status(result)
        if expected_remote and remote_status != "PASS":
            failures.append(remote_status)
        if _is_executable_type(expected_type) and formatter_status != "PASS":
            failures.append(formatter_status)
    else:
        remote_status = "SKIPPED"
        formatter_status = "SKIPPED"

    return {
        "question_id": row.question_id,
        "question": row.question,
        "release_scope": release_scope,
        "expected_type": expected_type,
        "actual_type": actual_type,
        "expected_mode": expected_mode,
        "actual_mode": actual_mode,
        "expected_intent": expected_intent,
        "actual_intent": actual_intent,
        "ast_generation_mode": actual_ast_mode,
        "remote_query_allowed": actual_remote,
        "remote_status": remote_status,
        "formatter_status": formatter_status,
        "failure_stage": result.get("failure_stage") or v3.get("failure_stage"),
        "failure_reason": result.get("failure_reason") or v3.get("failure_reason"),
        "query_summary": _query_summary(plan),
        "answer": answer,
        "display_answer": display_answer,
        "status": "SKIP" if not in_scope else ("FAIL" if failures else "PASS"),
        "reason": "; ".join(failures),
    }


def _check_executable_contract(result: dict[str, Any], row: CoverageRow) -> list[str]:
    failures = []
    v3 = result.get("v3") or {}
    if _bool(row["llm_ast_draft_required"]) and v3.get("ast_generation_mode") != "llm_ast_draft":
        failures.append("covered executable did not use llm_ast_draft")
    for key in ("llm_ast_draft_raw",):
        if not v3.get(key):
            failures.append(f"missing v3.{key}")
    for key in ("v3_ast", "validated_ast", "query_plan", "mongo_params"):
        if result.get(key) is None or result.get(key) == {}:
            failures.append(f"missing {key}")
    if v3.get("ast_generation_mode") == "deterministic_legacy":
        failures.append("deterministic_legacy appeared in executable pass path")
    if v3.get("capability_status") != "executable":
        failures.append(f"capability_status expected executable, got {v3.get('capability_status')}")
    if v3.get("gate_status") not in {"passed", "not_applicable"}:
        failures.append(f"gate_status expected passed/not_applicable, got {v3.get('gate_status')}")
    diff = v3.get("provenance_diff")
    if isinstance(diff, list):
        strict_pass = all(item.get("strict_pass") is True for item in diff if isinstance(item, dict))
        semantic_additions = [item for item in diff if isinstance(item, dict) and item.get("semantic_additions")]
        semantic_overrides = [item for item in diff if isinstance(item, dict) and item.get("semantic_overrides")]
        semantic_defaults = [
            item for item in diff
            if isinstance(item, dict) and (item.get("validator_additions_by_kind") or {}).get("semantic")
        ]
    elif isinstance(diff, dict):
        strict_pass = diff.get("strict_pass") is True
        semantic_additions = diff.get("semantic_additions") or []
        semantic_overrides = diff.get("semantic_overrides") or []
        semantic_defaults = (diff.get("validator_additions_by_kind") or {}).get("semantic") or []
    else:
        strict_pass = False
        semantic_additions = ["missing provenance_diff"]
        semantic_overrides = []
        semantic_defaults = []
    if not strict_pass:
        failures.append("provenance_diff.strict_pass is not true")
    if semantic_additions:
        failures.append("semantic_additions is not empty")
    if semantic_overrides:
        failures.append("semantic_overrides is not empty")
    if semantic_defaults:
        failures.append("validator_additions_by_kind.semantic is not empty")
    return failures


def _check_non_executable_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("v3_ast") is not None:
        failures.append("non-executable generated v3_ast")
    if result.get("validated_ast") is not None:
        failures.append("non-executable generated validated_ast")
    if result.get("query_plan") is not None:
        failures.append("non-executable generated query_plan")
    if result.get("v3", {}).get("remote_query_allowed"):
        failures.append("non-executable allowed remote query")
    return failures


def _legacy_type(v3: dict[str, Any]) -> str | None:
    mode = v3.get("recognized_query_mode")
    if mode == "deny":
        return "DeniedQuery"
    if mode == "clarify":
        return "ClarificationRequired"
    if mode == "unsupported":
        return "UnsupportedQuery"
    if mode:
        return "ExecutableQuery"
    return None


def _remote_status(result: Any, expected_remote: bool) -> str:
    if not expected_remote:
        return "SKIPPED"
    if not isinstance(result, dict):
        return "remote result missing"
    if result.get("success") is not True:
        return f"remote failed: {result.get('error')}"
    return "PASS"


def _formatter_status(result: dict[str, Any]) -> str:
    answer = str(result.get("answer") or "")
    if not answer:
        return "formatter missing answer"
    if answer.startswith("v3.2 查询失败"):
        return "formatter received failed runtime result"
    return "PASS"


def _brief_user_answer(answer: str, *, max_chars: int = 160) -> str:
    if _looks_like_markdown_table(answer):
        return _brief_markdown_table(answer)
    cleaned = " ".join(str(answer or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip("，,。；; ") + "..."


def _looks_like_markdown_table(answer: str) -> bool:
    lines = [line.strip() for line in str(answer or "").splitlines() if line.strip()]
    return len(lines) >= 2 and lines[0].startswith("|") and lines[1].startswith("|") and "---" in lines[1]


def _brief_markdown_table(answer: str, *, max_rows: int = 5) -> str:
    rows = []
    for line in str(answer or "").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and all(set(cell) <= {"-"} for cell in cells):
            continue
        rows.append(cells)
        if len(rows) >= max_rows + 1:
            break
    if not rows:
        return ""
    widths = [0] * max(len(row) for row in rows)
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    rendered = []
    for row in rows:
        padded = row + [""] * (len(widths) - len(row))
        rendered.append(" | ".join(cell.ljust(widths[index]) for index, cell in enumerate(padded)))
    if len([line for line in str(answer or "").splitlines() if line.strip().startswith("|")]) > max_rows + 2:
        rendered.append("...")
    return "\n".join(rendered)


def _query_summary(plan: Any) -> str:
    if not isinstance(plan, dict):
        return ""
    if "steps" in plan:
        return f"steps={len(plan['steps'])}"
    return json.dumps(
        {
            "collection": plan.get("collection"),
            "filter": plan.get("filter"),
            "projection": plan.get("projection"),
            "sort": plan.get("sort", []),
            "limit": plan.get("limit"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _markdown(records: list[dict[str, Any]]) -> str:
    total = len(records)
    scoped = sum(1 for record in records if record["release_scope"] == "v3_2_required")
    skipped = total - scoped
    passed = sum(1 for record in records if record["release_scope"] == "v3_2_required" and record["status"] == "PASS")
    failed = sum(1 for record in records if record["release_scope"] == "v3_2_required" and record["status"] == "FAIL")
    llm_passed = sum(1 for record in records if record["release_scope"] == "v3_2_required" and record["ast_generation_mode"] == "llm_ast_draft" and record["status"] == "PASS")
    llm_failed = sum(1 for record in records if record["ast_generation_mode"] == "llm_ast_draft_failed")
    deterministic = sum(1 for record in records if record["ast_generation_mode"] == "deterministic_legacy")
    blocked = sum(1 for record in records if record["release_scope"] == "v3_2_required" and record["expected_type"] in {"DeniedQuery", "UnsupportedQuery", "ClarificationRequired"})
    remote_passed = sum(1 for record in records if record["release_scope"] == "v3_2_required" and record["remote_status"] == "PASS")
    remote_failed = sum(1 for record in records if str(record["remote_status"]).startswith("remote failed"))
    formatter_passed = sum(1 for record in records if record["release_scope"] == "v3_2_required" and record["formatter_status"] == "PASS")
    formatter_failed = sum(1 for record in records if record["formatter_status"] != "PASS")
    covered = sum(1 for record in records if record["release_scope"] == "v3_2_required" and record["expected_type"] == "ExecutableQuery")

    table_rows = []
    for record in records:
        expected = f"{record['expected_type']} / {record['expected_mode']} / {record['expected_intent']}"
        answer = str(record.get("display_answer") or record.get("answer") or "")
        payload = expected if not answer else f"{expected}\n{answer}"
        table_rows.append(
            [
                record["question_id"],
                record["question"],
                payload,
            ]
        )

    widths = [0, 0, 0]
    for row in table_rows:
        for idx, cell in enumerate(row):
            for part in str(cell).split("\n"):
                widths[idx] = max(widths[idx], len(part))

    lines = [
        "# v3.2 Reference Audit",
        "",
        f"测试时间：{date.today().isoformat()}",
        "",
        "远端数据库：通过项目 `.env` 中的 SSH/Mongo 配置由 `semantic_query_v3` 正式运行时执行；报告不记录密钥。",
        "",
        f"- 总用例数：{total}",
        f"- v3.2 应覆盖用例数：{scoped}",
        f"- v3.2 PASS：{passed}",
        f"- v3.2 FAIL：{failed}",
        f"- 不在 v3.2 范围：{skipped}",
        f"- llm_ast_draft passed：{llm_passed}",
        f"- llm_ast_draft failed：{llm_failed}",
        f"- deterministic_legacy：{deterministic}",
        f"- blocked/unsupported/clarification：{blocked}",
        f"- remote execution passed：{remote_passed}",
        f"- remote execution failed：{remote_failed}",
        f"- formatter passed：{formatter_passed}",
        f"- formatter failed：{formatter_failed}",
        f"- v3.2 pass rate：{passed}/{scoped}" if scoped else "- v3.2 pass rate：0/0",
        "",
        "```text",
        _render_fixed_width_header(widths),
    ]
    for row in table_rows:
        lines.extend(_render_fixed_width_row(row, widths))
    lines.append("```")
    mismatches = [record for record in records if record["status"] == "FAIL"]
    lines.extend(["", "## 与 Coverage Matrix 不一致", ""])
    if mismatches:
        for record in mismatches:
            lines.append(f"- {record['question_id']} {record['question']}：{record['reason']}")
    else:
        lines.append("- 无")
    lines.extend(["", "## 未完成项和阻塞项", ""])
    if mismatches:
        lines.append("- 详见上方 FAIL 列表。")
    else:
        lines.append("- 无。")
    lines.append("")
    return "\n".join(lines)


def _bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _none_if_null(value: str) -> str | None:
    return None if value in {"null", ""} else value


def _is_executable_type(value: str) -> bool:
    return value == "ExecutableQuery"


def _render_fixed_width_header(widths: list[int]) -> str:
    labels = ["ID", "问句", "预期 + 真实回答"]
    return " | ".join(label.ljust(widths[idx]) for idx, label in enumerate(labels))


def _render_fixed_width_row(row: list[str], widths: list[int]) -> list[str]:
    parts = [str(cell).split("\n") for cell in row]
    height = max(len(part) for part in parts)
    normalized = []
    for idx, part in enumerate(parts):
        padded = part + [""] * (height - len(part))
        normalized.append([line.ljust(widths[idx]) for line in padded])
    lines: list[str] = []
    for i in range(height):
        lines.append(" | ".join(col[i] for col in normalized))
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
