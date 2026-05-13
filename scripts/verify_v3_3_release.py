#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
import argparse
import html
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etf_agent import semantic_query_v3
from scripts.audit_answer_format import format_audit_answer, llm_total_tokens


DEFAULT_COVERAGE = ROOT / "docs" / "v3-coverage-matrix.md"
DEFAULT_OUT_MD = ROOT / "result" / "audit-v3.3-results.md"
DEFAULT_OUT_JSON = ROOT / "result" / "audit-v3.3-results.json"
DEFAULT_OUT_HTML = ROOT / "result" / "audit-v3.3-results.html"
PHASE = "v3.3"
BASELINE_SCOPE = "v3_2_required"
NEW_SCOPE = "v3_3_required"
RELEASE_SCOPES = {BASELINE_SCOPE, NEW_SCOPE}
PROTOCOL_SCHEMA_VERSIONS = {"v3_2_base_ast", "v3_3_structured_query"}
REQUIRED_NEW_FRAGMENT_BUCKETS = ("report", "timeseries", "derived_performance", "composite")


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

    @property
    def bucket(self) -> str:
        return self.values["PM bucket"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the v3.3 release against the coverage matrix.")
    parser.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-html", type=Path, default=DEFAULT_OUT_HTML)
    parser.add_argument("--skip-fragment-gate", action="store_true")
    parser.add_argument("--execute-all-scopes", action="store_true")
    args = parser.parse_args(argv)

    rows = load_coverage_rows(args.coverage)
    records = []
    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{len(rows)}] {row.question_id} {row.question}", flush=True)
        if row["release_scope"] not in RELEASE_SCOPES:
            if args.execute_all_scopes:
                try:
                    result = semantic_query_v3(row.question, root=ROOT, phase=PHASE)
                except Exception as exc:
                    result = _runtime_exception_result(row.question, exc)
            else:
                result = _static_out_of_scope_result(row)
        else:
            try:
                result = semantic_query_v3(row.question, root=ROOT, phase=PHASE)
            except Exception as exc:
                result = _runtime_exception_result(row.question, exc)
        records.append(evaluate_row(row, result, executed=row["release_scope"] in RELEASE_SCOPES or args.execute_all_scopes))

    summary = summarize(records, skip_fragment_gate=args.skip_fragment_gate)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_html.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "records": records}
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out_md.write_text(render_markdown(records, summary, args.coverage, args.out_json), encoding="utf-8")
    args.out_html.write_text(render_html(records, summary, args.coverage, args.out_json), encoding="utf-8")
    print(args.out_json)
    print(args.out_md)
    print(args.out_html)
    print(f"overall_release_pass={str(summary['overall_release_pass']).lower()}")
    return 0 if summary["overall_release_pass"] else 1


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


def evaluate_row(row: CoverageRow, result: dict[str, Any], *, executed: bool = True) -> dict[str, Any]:
    v3 = result.get("v3") or {}
    release_scope = row["release_scope"]
    in_release_scope = release_scope in RELEASE_SCOPES
    expected_type = row["routing_result.type"]
    expected_mode = _none_if_null(row["recognized_query_mode"])
    expected_intent = _none_if_null(row["expected_intent_or_profile"])
    expected_ast_mode = _none_if_null(row["ast_generation_mode"])
    expected_remote = _bool(row["remote_query_allowed"])
    expected_reason = _expected_reason(row)

    actual_type = (v3.get("routing_result") or {}).get("type") or _legacy_type(v3)
    actual_mode = v3.get("recognized_query_mode")
    actual_intent = v3.get("intent")
    actual_ast_mode = v3.get("ast_generation_mode")
    actual_remote = bool(v3.get("remote_query_allowed"))
    ast_schema_version = _ast_schema_version(result)
    failure_stage = result.get("failure_stage") or v3.get("failure_stage")
    failure_reason = result.get("failure_reason") or v3.get("failure_reason") or (v3.get("routing_result") or {}).get("reason")
    remote_status = _remote_status(result.get("result"), expected_remote) if in_release_scope else "SKIPPED"
    formatter_status = _formatter_status(result) if in_release_scope else "SKIPPED"
    text2sql_strict_pass, text2sql_failures = _text2sql_strict_pass(result, row)
    answer_value_success = _answer_value_success(result, expected_type, formatter_status, failure_reason)

    failures: list[str] = []
    if in_release_scope:
        if actual_type != expected_type:
            failures.append(f"routing type expected {expected_type}, got {actual_type}")
        if expected_mode is not None and actual_mode != expected_mode:
            failures.append(f"mode expected {expected_mode}, got {actual_mode}")
        if expected_intent not in {None, "-"} and expected_type == "ExecutableQuery" and actual_intent != expected_intent:
            failures.append(f"intent/profile expected {expected_intent}, got {actual_intent}")
        if expected_ast_mode != actual_ast_mode:
            failures.append(f"ast_generation_mode expected {expected_ast_mode}, got {actual_ast_mode}")
        if expected_remote != actual_remote:
            failures.append(f"remote_query_allowed expected {expected_remote}, got {actual_remote}")
        if expected_reason not in {None, "-"} and expected_type != "ExecutableQuery" and failure_reason != expected_reason:
            failures.append(f"failure_reason expected {expected_reason}, got {failure_reason}")
        if expected_type == "ExecutableQuery":
            if not text2sql_strict_pass:
                failures.extend(text2sql_failures)
            if expected_remote and remote_status != "PASS":
                failures.append(remote_status)
            if formatter_status != "PASS":
                failures.append(formatter_status)
            if not answer_value_success and failure_reason != "data_not_available":
                failures.append("answer_value_success is false")
        else:
            failures.extend(_check_non_executable_contract(result))
            if text2sql_strict_pass:
                failures.append("non-executable must not be text2sql_strict_pass")
            if answer_value_success:
                failures.append("non-executable must not be answer_value_success")
    else:
        text2sql_strict_pass = False
        answer_value_success = False

    status = "SKIP" if not in_release_scope else ("FAIL" if failures else "PASS")
    release_bucket = _release_bucket(row)
    fragment_buckets = _fragment_buckets(row)
    actual_outcome = _actual_outcome(
        actual_type=actual_type,
        actual_mode=actual_mode,
        actual_intent=actual_intent,
        failure_stage=failure_stage,
        failure_reason=failure_reason,
        result=result,
    )
    user_visible_answer = format_audit_answer(str(result.get("answer") or ""), result=result) if executed else "不在 v3.3 release denominator"
    total_tokens = llm_total_tokens(result) if executed else None
    return {
        "question_id": row.question_id,
        "question": row.question,
        "pm_bucket": row.bucket,
        "release_scope": release_scope,
        "release_bucket": release_bucket,
        "fragment_buckets": fragment_buckets,
        "expected_outcome": row["expected_outcome"],
        "actual_outcome": actual_outcome,
        "expected_routing_type": expected_type,
        "actual_routing_type": actual_type,
        "expected_recognized_query_mode": expected_mode,
        "recognized_query_mode": actual_mode,
        "expected_intent_or_profile": expected_intent,
        "actual_intent_or_profile": actual_intent,
        "ast_schema_version": ast_schema_version,
        "ast_generation_mode": actual_ast_mode,
        "text2sql_strict_pass": text2sql_strict_pass,
        "answer_value_success": answer_value_success,
        "pass/fail": status,
        "failure_stage": failure_stage,
        "failure_reason": failure_reason,
        "remote_query_allowed": actual_remote,
        "remote_status": remote_status,
        "formatter_status": formatter_status,
        "query_summary": _query_summary(result.get("query_plan")),
        "llm_total_tokens": total_tokens,
        "user_visible_answer": user_visible_answer,
        "reason": "; ".join(_dedupe(failures)),
    }


def summarize(records: list[dict[str, Any]], *, skip_fragment_gate: bool = False) -> dict[str, Any]:
    total = len(records)
    scoped_records = [record for record in records if record["release_scope"] in RELEASE_SCOPES]
    passed = sum(1 for record in scoped_records if record["pass/fail"] == "PASS")
    failed = sum(1 for record in scoped_records if record["pass/fail"] == "FAIL")
    baseline = _scope_stats(records, BASELINE_SCOPE)
    new = _scope_stats(records, NEW_SCOPE)
    pm_buckets = _pm_bucket_stats(records)
    release_buckets = _release_bucket_stats(records)
    fragment_buckets = _fragment_bucket_stats(records)
    missing_required_fragments = [
        name for name in REQUIRED_NEW_FRAGMENT_BUCKETS if fragment_buckets.get(name, {}).get("total", 0) == 0
    ]
    failed_required_fragments = [
        name for name in REQUIRED_NEW_FRAGMENT_BUCKETS if fragment_buckets.get(name, {}).get("failed", 0) > 0
    ]
    overall_release_pass = failed == 0 and (skip_fragment_gate or (not missing_required_fragments and not failed_required_fragments))
    failure_by_stage = Counter(
        str(record["failure_stage"])
        for record in scoped_records
        if record["pass/fail"] == "FAIL" and record.get("failure_stage")
    )

    return {
        "total_cases": total,
        "scoped_cases": len(scoped_records),
        "passed": passed,
        "failed": failed,
        "v3_2_compatibility_baseline": baseline,
        "v3_3_new_fragments": new,
        "report": fragment_buckets.get("report", _empty_stats()),
        "timeseries": fragment_buckets.get("timeseries", _empty_stats()),
        "derived_performance": fragment_buckets.get("derived_performance", _empty_stats()),
        "composite": fragment_buckets.get("composite", _empty_stats()),
        "manager_detail": fragment_buckets.get("manager_detail", _empty_stats()),
        "trading_metric": fragment_buckets.get("trading_metric", _empty_stats()),
        "blocked_by_verification_total": _reason_count(scoped_records, "blocked_by_verification"),
        "data_not_available_total": _reason_count(scoped_records, "data_not_available"),
        "denied_total": sum(1 for record in scoped_records if record["actual_routing_type"] == "DeniedQuery"),
        "clarification_required_total": sum(1 for record in scoped_records if record["actual_routing_type"] == "ClarificationRequired"),
        "llm_ast_draft_total": sum(1 for record in scoped_records if record["ast_generation_mode"] == "llm_ast_draft"),
        "llm_ast_draft_passed": sum(
            1 for record in scoped_records if record["ast_generation_mode"] == "llm_ast_draft" and record["text2sql_strict_pass"]
        ),
        "llm_ast_draft_failed_total": sum(1 for record in scoped_records if record["ast_generation_mode"] == "llm_ast_draft_failed"),
        "llm_ast_draft_failure_by_stage": dict(sorted(failure_by_stage.items())),
        "remote_execution_passed": sum(1 for record in scoped_records if record["remote_status"] == "PASS"),
        "formatter_passed": sum(1 for record in scoped_records if record["formatter_status"] == "PASS"),
        "strict_semantic_provenance_passed": sum(1 for record in scoped_records if record["text2sql_strict_pass"]),
        "validator_semantic_addition_failed": sum(
            1 for record in scoped_records if "semantic_additions" in str(record.get("reason") or "")
        ),
        "deterministic_legacy_total": sum(1 for record in scoped_records if record["ast_generation_mode"] == "deterministic_legacy"),
        "deterministic_legacy_debug_fallback_total": sum(
            1
            for record in scoped_records
            if record["ast_generation_mode"] == "llm_ast_draft_failed" and "deterministic" in str(record.get("actual_outcome") or "")
        ),
        "poisoned_legacy_signal_passed": 0,
        "llm_total_tokens": sum(
            record["llm_total_tokens"] for record in scoped_records if isinstance(record.get("llm_total_tokens"), int)
        ),
        "missing_required_fragments": missing_required_fragments,
        "failed_required_fragments": failed_required_fragments,
        "overall_release_pass": overall_release_pass,
        "pm_bucket_stats": pm_buckets,
        "release_bucket_stats": release_buckets,
        "fragment_bucket_stats": fragment_buckets,
    }


def _text2sql_strict_pass(result: dict[str, Any], row: CoverageRow) -> tuple[bool, list[str]]:
    failures: list[str] = []
    v3 = result.get("v3") or {}
    if row["routing_result.type"] != "ExecutableQuery":
        return False, []
    if _bool(row["llm_ast_draft_required"]) and v3.get("ast_generation_mode") != "llm_ast_draft":
        failures.append("covered executable did not use llm_ast_draft")
    if v3.get("ast_generation_mode") == "deterministic_legacy":
        failures.append("deterministic_legacy appeared in executable pass path")
    if not v3.get("llm_ast_draft_raw"):
        failures.append("missing v3.llm_ast_draft_raw")
    for key in ("v3_ast", "validated_ast", "query_plan", "mongo_params"):
        if result.get(key) is None or result.get(key) == {}:
            failures.append(f"missing {key}")
    if v3.get("capability_status") != "executable":
        failures.append(f"capability_status expected executable, got {v3.get('capability_status')}")
    if v3.get("gate_status") not in {"passed", "not_applicable"}:
        failures.append(f"gate_status expected passed/not_applicable, got {v3.get('gate_status')}")
    schema_version = _ast_schema_version(result)
    if schema_version not in PROTOCOL_SCHEMA_VERSIONS:
        failures.append(f"unsupported ast_schema_version: {schema_version}")
    failures.extend(_provenance_failures(v3.get("provenance_diff")))
    failure_reason = result.get("failure_reason") or v3.get("failure_reason")
    failure_stage = result.get("failure_stage") or v3.get("failure_stage")
    if failure_reason in {"blocked_by_verification"} or failure_stage in {"routing", "llm_ast_draft", "validator", "compiler"}:
        failures.append(f"pre-execution failure cannot be strict pass: {failure_stage}/{failure_reason}")
    return not failures, _dedupe(failures)


def _provenance_failures(diff: Any) -> list[str]:
    if isinstance(diff, list):
        failures: list[str] = []
        if not diff:
            return ["missing provenance_diff"]
        for index, item in enumerate(diff, start=1):
            for failure in _provenance_failures(item):
                failures.append(f"child {index}: {failure}")
        return failures
    if not isinstance(diff, dict):
        return ["missing provenance_diff"]
    failures = []
    if diff.get("strict_pass") is not True:
        failures.append("provenance_diff.strict_pass is not true")
    if diff.get("semantic_additions"):
        failures.append("semantic_additions is not empty")
    if diff.get("semantic_overrides"):
        failures.append("semantic_overrides is not empty")
    semantic_defaults = (diff.get("validator_additions_by_kind") or {}).get("semantic") or []
    if semantic_defaults:
        failures.append("validator_additions_by_kind.semantic is not empty")
    schema_version = diff.get("ast_schema_version")
    if schema_version is not None and schema_version not in PROTOCOL_SCHEMA_VERSIONS:
        failures.append(f"provenance_diff has unsupported ast_schema_version: {schema_version}")
    return failures


def _check_non_executable_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if result.get("v3_ast") is not None:
        failures.append("non-executable generated v3_ast")
    if result.get("validated_ast") is not None:
        failures.append("non-executable generated validated_ast")
    if result.get("query_plan") is not None:
        failures.append("non-executable generated query_plan")
    if result.get("v3", {}).get("remote_query_allowed"):
        failures.append("non-executable allowed remote query")
    return failures


def _answer_value_success(
    result: dict[str, Any],
    expected_type: str,
    formatter_status: str,
    failure_reason: str | None,
) -> bool:
    if expected_type != "ExecutableQuery":
        return False
    if failure_reason == "data_not_available":
        return False
    if formatter_status != "PASS":
        return False
    remote_result = result.get("result")
    if not isinstance(remote_result, dict) or remote_result.get("success") is not True:
        return False
    return True


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
    if "steps" in result:
        steps = result.get("steps") or []
        if all(isinstance(item, dict) and item.get("success") is True for item in steps):
            return "PASS"
        return "remote failed: step failure"
    if result.get("success") is not True:
        return f"remote failed: {result.get('error')}"
    return "PASS"


def _formatter_status(result: dict[str, Any]) -> str:
    answer = str(result.get("answer") or "")
    if not answer:
        return "formatter missing answer"
    if answer.startswith(("v3.2 查询失败", "v3.3 查询失败")) or "查询失败" in answer:
        return "formatter received failed runtime result"
    return "PASS"


def _actual_outcome(
    *,
    actual_type: str | None,
    actual_mode: str | None,
    actual_intent: str | None,
    failure_stage: str | None,
    failure_reason: str | None,
    result: dict[str, Any],
) -> str:
    reason = failure_reason or (result.get("v3") or {}).get("reason")
    if actual_type in {"DeniedQuery", "UnsupportedQuery", "ClarificationRequired"}:
        return f"{actual_type}({reason or '-'})"
    if failure_stage:
        return f"ExecutableQueryFailed({failure_stage}:{reason or '-'})"
    if actual_type == "ExecutableQuery":
        return f"ExecutableQuery({actual_mode or '-'}/{actual_intent or '-'})"
    return str(actual_type or "unknown")


def _ast_schema_version(result: dict[str, Any]) -> str | None:
    v3 = result.get("v3") or {}
    if v3.get("ast_schema_version"):
        return v3.get("ast_schema_version")
    ast = result.get("validated_ast") or result.get("v3_ast")
    if isinstance(ast, dict):
        if ast.get("ast_schema_version"):
            return ast.get("ast_schema_version")
        steps = ast.get("steps")
        if isinstance(steps, list):
            versions = [
                step.get("ast_schema_version")
                for step in steps
                if isinstance(step, dict) and step.get("ast_schema_version")
            ]
            if versions:
                unique = sorted(set(versions))
                return unique[0] if len(unique) == 1 else ",".join(unique)
    return None


def _expected_reason(row: CoverageRow) -> str | None:
    raw = row["expected_outcome"]
    if "(" not in raw or not raw.endswith(")"):
        return _none_if_null(row["expected_fallback_or_blocked_reason"])
    return raw.split("(", 1)[1][:-1] or None


def _release_bucket(row: CoverageRow) -> str:
    if row["release_scope"] == BASELINE_SCOPE:
        return "v3_2_compatibility_baseline"
    if row["release_scope"] == NEW_SCOPE:
        return "v3_3_new_fragments"
    return "out_of_release_scope"


def _fragment_buckets(row: CoverageRow) -> list[str]:
    if row["release_scope"] != NEW_SCOPE:
        return []
    question = row.question
    expected_intent = _none_if_null(row["expected_intent_or_profile"]) or ""
    expected_mode = _none_if_null(row["recognized_query_mode"]) or ""
    expected_outcome = row["expected_outcome"]
    tags: list[str] = []
    if expected_mode == "report" or expected_intent.startswith("report_") or expected_intent in {
        "institution_holding",
        "report_style",
        "report_nav_change",
    }:
        tags.append("report")
    if "timeseries" in expected_outcome or expected_intent == "trading_metric":
        tags.append("timeseries")
    if "收益" in question or "收益率" in question or expected_intent in {"performance", "unsupported_peer_average"}:
        tags.append("derived_performance")
    if expected_mode == "composite" or expected_intent in {"composite_single", "two_step_composite"} or row.bucket == "复合意图":
        tags.append("composite")
    if expected_intent == "manager_detail":
        tags.append("manager_detail")
    if expected_intent == "trading_metric":
        tags.append("trading_metric")
    if not tags:
        tags.append("other")
    return list(dict.fromkeys(tags))


def _scope_stats(records: list[dict[str, Any]], scope: str) -> dict[str, int | bool]:
    scoped = [record for record in records if record["release_scope"] == scope]
    failed = sum(1 for record in scoped if record["pass/fail"] == "FAIL")
    return {
        "total": len(scoped),
        "passed": sum(1 for record in scoped if record["pass/fail"] == "PASS"),
        "failed": failed,
        "pass": failed == 0 and bool(scoped),
    }


def _pm_bucket_stats(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = defaultdict(lambda: Counter({"total": 0, "scoped": 0, "passed": 0, "failed": 0, "skipped": 0}))  # type: ignore[assignment]
    for record in records:
        bucket = record["pm_bucket"]
        stats[bucket]["total"] += 1
        if record["release_scope"] in RELEASE_SCOPES:
            stats[bucket]["scoped"] += 1
            if record["pass/fail"] == "PASS":
                stats[bucket]["passed"] += 1
            elif record["pass/fail"] == "FAIL":
                stats[bucket]["failed"] += 1
        else:
            stats[bucket]["skipped"] += 1
    return {bucket: dict(values) for bucket, values in sorted(stats.items())}


def _release_bucket_stats(records: list[dict[str, Any]]) -> dict[str, dict[str, int | bool]]:
    stats: dict[str, dict[str, int]] = defaultdict(lambda: Counter({"total": 0, "passed": 0, "failed": 0, "skipped": 0}))  # type: ignore[assignment]
    for record in records:
        bucket = record["release_bucket"]
        stats[bucket]["total"] += 1
        status = record["pass/fail"]
        if status == "PASS":
            stats[bucket]["passed"] += 1
        elif status == "FAIL":
            stats[bucket]["failed"] += 1
        else:
            stats[bucket]["skipped"] += 1
    return {
        bucket: {**dict(values), "pass": values["failed"] == 0 and values["passed"] > 0}
        for bucket, values in sorted(stats.items())
    }


def _fragment_bucket_stats(records: list[dict[str, Any]]) -> dict[str, dict[str, int | bool]]:
    stats: dict[str, dict[str, int]] = defaultdict(lambda: Counter({"total": 0, "passed": 0, "failed": 0}))  # type: ignore[assignment]
    for record in records:
        if record["release_scope"] != NEW_SCOPE:
            continue
        for bucket in record["fragment_buckets"]:
            stats[bucket]["total"] += 1
            if record["pass/fail"] == "PASS":
                stats[bucket]["passed"] += 1
            elif record["pass/fail"] == "FAIL":
                stats[bucket]["failed"] += 1
    return {
        bucket: {**dict(values), "pass": values["failed"] == 0 and values["total"] > 0}
        for bucket, values in sorted(stats.items())
    }


def _empty_stats() -> dict[str, int | bool]:
    return {"total": 0, "passed": 0, "failed": 0, "pass": False}


def _reason_count(records: list[dict[str, Any]], reason: str) -> int:
    return sum(
        1
        for record in records
        if record.get("failure_reason") == reason
        or record.get("failure_stage") == reason
        or str(record.get("actual_outcome") or "").endswith(f"({reason})")
    )


def render_markdown(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    coverage_path: Path,
    out_json: Path,
) -> str:
    lines = [
        "# v3.3 Release Audit",
        "",
        "## Summary",
        "",
        f"- test_date: `{date.today().isoformat()}`",
        f"- coverage_matrix: [`{_relative_path(coverage_path)}`]({_relative_path(coverage_path)})",
        f"- raw_json: `{_relative_path(out_json)}`",
        f"- total_cases: `{summary['total_cases']}`",
        f"- scoped_cases: `{summary['scoped_cases']}`",
        f"- passed: `{summary['passed']}`",
        f"- failed: `{summary['failed']}`",
        f"- blocked_by_verification_total: `{summary['blocked_by_verification_total']}`",
        f"- data_not_available_total: `{summary['data_not_available_total']}`",
        f"- denied_total: `{summary['denied_total']}`",
        f"- clarification_required_total: `{summary['clarification_required_total']}`",
        f"- llm_total_tokens: `{summary['llm_total_tokens']}`",
        f"- overall_release_pass: `{str(summary['overall_release_pass']).lower()}`",
        "",
        "## Release Bucket Stats",
        "",
        "| bucket | total | passed | failed | skipped | pass |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for bucket, stats in summary["release_bucket_stats"].items():
        lines.append(
            f"| {bucket} | {stats.get('total', 0)} | {stats.get('passed', 0)} | {stats.get('failed', 0)} | {stats.get('skipped', 0)} | {str(stats.get('pass', False)).lower()} |"
        )

    lines.extend(
        [
            "",
            "## v3.3 Fragment Stats",
            "",
            "| fragment | total | passed | failed | pass |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for bucket in sorted(summary["fragment_bucket_stats"]):
        stats = summary["fragment_bucket_stats"][bucket]
        lines.append(
            f"| {bucket} | {stats.get('total', 0)} | {stats.get('passed', 0)} | {stats.get('failed', 0)} | {str(stats.get('pass', False)).lower()} |"
        )

    lines.extend(
        [
            "",
            "## PM Bucket Stats",
            "",
            "| PM bucket | total | scoped | passed | failed | skipped |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for bucket, stats in summary["pm_bucket_stats"].items():
        lines.append(
            f"| {bucket} | {stats.get('total', 0)} | {stats.get('scoped', 0)} | {stats.get('passed', 0)} | {stats.get('failed', 0)} | {stats.get('skipped', 0)} |"
        )

    lines.extend(
        [
            "",
            "## Per-Question Summary",
            "",
            "| question_id | question | release_scope | expected_outcome | actual_outcome | recognized_query_mode | expected_intent_or_profile | actual_intent_or_profile | ast_schema_version | ast_generation_mode | text2sql_strict_pass | answer_value_success | pass/fail | failure_stage | failure_reason |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in records:
        cells = _record_cells(record)
        lines.append(
            "| {question_id} | {question} | {release_scope} | {expected_outcome} | {actual_outcome} | {recognized_query_mode} | {expected_intent_or_profile} | {actual_intent_or_profile} | {ast_schema_version} | {ast_generation_mode} | {text2sql_strict_pass} | {answer_value_success} | {pass/fail} | {failure_stage} | {failure_reason} |".format(
                **cells
            )
        )

    lines.extend(
        [
            "",
            "## Per-Question Details",
            "",
            "| question_id | question | release_bucket | fragment_buckets | remote_status | formatter_status | query_summary | reason | user_visible_answer |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in records:
        cells = _record_cells(record)
        lines.append(
            "| {question_id} | {question} | {release_bucket} | {fragment_buckets} | {remote_status} | {formatter_status} | {query_summary} | {reason} | {user_visible_answer} |".format(
                **cells
            )
        )

    lines.extend(
        [
            "",
            "## Failure Totals",
            "",
            "| metric | value |",
            "| --- | ---: |",
            f"| llm_ast_draft_failed_total | {summary['llm_ast_draft_failed_total']} |",
            f"| deterministic_legacy_total | {summary['deterministic_legacy_total']} |",
            f"| deterministic_legacy_debug_fallback_total | {summary['deterministic_legacy_debug_fallback_total']} |",
            f"| remote_execution_passed | {summary['remote_execution_passed']} |",
            f"| formatter_passed | {summary['formatter_passed']} |",
            f"| strict_semantic_provenance_passed | {summary['strict_semantic_provenance_passed']} |",
            f"| validator_semantic_addition_failed | {summary['validator_semantic_addition_failed']} |",
            f"| poisoned_legacy_signal_passed | {summary['poisoned_legacy_signal_passed']} |",
            "",
            "## Notes",
            "",
            "- Denominator is declared before runtime by `release_scope in {v3_2_required, v3_3_required}`.",
            "- All denominator rows are executed through `semantic_query_v3(..., phase=\"v3.3\")`.",
            "- `user_visible_answer` contains only the final natural-language/table answer text.",
        ]
    )
    return "\n".join(lines)


def render_html(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    coverage_path: Path,
    out_json: Path,
) -> str:
    expected_answers = _load_expected_answers_for_html()
    cards = "\n".join(_case_html(record, expected_answers) for record in records)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>v3.3 Full Release Audit</title>
<style>
  :root {{ --bg: #f4f0e6; --paper: #fffaf0; --ink: #2f2418; --muted: #6e5c45; --line: #d7c8b2; --pass: #2f6f4e; --fail: #9f2f2f; --skip: #70655b; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: Georgia, serif; }}
  .wrap {{ max-width: 1320px; margin: 0 auto; padding: 28px 22px 48px; }}
  .hero {{ padding: 10px 0 18px; border-bottom: 1px solid var(--line); margin-bottom: 18px; }}
  h1 {{ margin: 0 0 8px; font-size: 32px; }}
  .sub {{ color: var(--muted); font-size: 14px; line-height: 1.5; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0 24px; }}
  .stat {{ background: var(--paper); border: 1px solid var(--line); padding: 14px 16px; border-radius: 6px; }}
  .stat .k {{ color: var(--muted); font-size: 12px; }}
  .stat .v {{ margin-top: 6px; font-size: 26px; }}
  .cases {{ display: grid; gap: 16px; }}
  .card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 6px; padding: 18px; }}
  .head {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 10px; }}
  .qid {{ font-size: 20px; line-height: 1.35; }}
  .badge {{ font-size: 12px; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--line); white-space: nowrap; }}
  .pass {{ color: var(--pass); }}
  .fail {{ color: var(--fail); }}
  .skip {{ color: var(--skip); }}
  .meta {{ color: var(--muted); font-size: 13px; margin-bottom: 14px; line-height: 1.5; }}
  .cols {{ display: grid; grid-template-columns: 0.85fr 1.15fr; gap: 14px; }}
  .panel {{ border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }}
  .panel h3 {{ margin: 0; padding: 10px 12px; font-size: 14px; background: rgba(0,0,0,0.03); }}
  .panel pre {{ margin: 0; padding: 12px; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; line-height: 1.5; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ border-top: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }}
  th {{ background: rgba(0,0,0,0.035); }}
  @media (max-width: 900px) {{ .cols {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>v3.3 Full Release Audit</h1>
      <div class="sub">{html.escape(str(_relative_path(out_json)))} · coverage {html.escape(str(_relative_path(coverage_path)))} · {summary['passed']} pass · {summary['failed']} fail · LLM 总 token 数：{html.escape(str(summary['llm_total_tokens']))}</div>
    </div>
    <div class="grid">
      <div class="stat"><div class="k">Total Cases</div><div class="v">{summary['total_cases']}</div></div>
      <div class="stat"><div class="k">Scoped Cases</div><div class="v">{summary['scoped_cases']}</div></div>
      <div class="stat"><div class="k">Passed</div><div class="v">{summary['passed']}</div></div>
      <div class="stat"><div class="k">Failed</div><div class="v">{summary['failed']}</div></div>
      <div class="stat"><div class="k">LLM Tokens</div><div class="v">{html.escape(str(summary['llm_total_tokens']))}</div></div>
    </div>
    <div class="cases">{cards}</div>
  </div>
</body>
</html>
"""


def _case_html(record: dict[str, Any], expected_answers: dict[str, str]) -> str:
    status = str(record["pass/fail"]).lower()
    badge_class = "pass" if status == "pass" else "fail" if status == "fail" else "skip"
    meta = (
        f"scope={record['release_scope']} · bucket={record['release_bucket']} · "
        f"expected={record['expected_outcome']} · actual={record['actual_outcome']} · "
        f"tokens={record.get('llm_total_tokens') if record.get('llm_total_tokens') is not None else '未记录'}"
    )
    expected_answer = expected_answers.get(record["question_id"], "未在 codex-etf-query-answers.md 中找到 expected 答案。")
    return f"""
    <section class="card">
      <div class="head">
        <div class="qid">{html.escape(record['question_id'])} {html.escape(record['question'])}</div>
        <div class="badge {badge_class}">{html.escape(record['pass/fail'])}</div>
      </div>
      <div class="meta">{html.escape(meta)}</div>
      <div class="cols">
        <div class="panel">
          <h3>Expected</h3>
          {_render_markdownish(expected_answer)}
        </div>
        <div class="panel">
          <h3>Answer</h3>
          {_render_markdownish(record.get('user_visible_answer') or '')}
        </div>
      </div>
    </section>
"""


def _load_expected_answers_for_html() -> dict[str, str]:
    path = ROOT / "result" / "codex-etf-query-answers.md"
    expected: dict[str, str] = {}
    current_id: str | None = None
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            if current_id:
                expected[current_id] = "\n".join(current).strip()
            parts = line.split(maxsplit=2)
            current_id = parts[1] if len(parts) >= 2 else None
            current = []
            continue
        if line.startswith("## "):
            continue
        if current_id:
            current.append(line)
    if current_id:
        expected[current_id] = "\n".join(current).strip()
    return expected


def _render_markdownish(text: str) -> str:
    blocks = []
    lines = str(text).splitlines()
    index = 0
    while index < len(lines):
        if _is_table_start(lines, index):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            blocks.append(_render_table(table_lines))
            continue
        paragraph = []
        while index < len(lines) and not _is_table_start(lines, index):
            paragraph.append(lines[index])
            index += 1
        content = "\n".join(paragraph).strip()
        if content:
            blocks.append(f"<pre>{html.escape(content)}</pre>")
    return "\n".join(blocks) if blocks else "<pre></pre>"


def _is_table_start(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and lines[index].strip().startswith("|")
        and set(lines[index + 1].replace("|", "").strip()) <= {"-", " ", ":"}
    )


def _render_table(lines: list[str]) -> str:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) < 2:
        return f"<pre>{html.escape(chr(10).join(lines))}</pre>"
    header = rows[0]
    body = rows[2:]
    head_html = "".join(f"<th>{html.escape(cell)}</th>" for cell in header)
    body_html = "\n".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in body
    )
    return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"


def _record_cells(record: dict[str, Any]) -> dict[str, str]:
    return {key: _escape_cell(_display_value(value)) for key, value in record.items()}


def _display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _escape_cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", "<br>")


def _relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _brief_user_answer(answer: str, *, max_chars: int = 320) -> str:
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
    if "mongo_phase" in plan:
        mongo_phase = plan.get("mongo_phase") or {}
        return json.dumps(
            {
                "collection": mongo_phase.get("collection"),
                "filter": mongo_phase.get("filter"),
                "projection": mongo_phase.get("projection"),
                "derived_metrics": [item.get("alias") for item in (plan.get("derived_phase") or {}).get("metrics", [])],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
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


def _static_out_of_scope_result(row: CoverageRow) -> dict[str, Any]:
    return {
        "question": row.question,
        "answer": "不在 v3.3 release denominator",
        "v3": {
            "routing_result": {"type": row["routing_result.type"], "reason": "out_of_v3_3_release_denominator"},
            "recognized_query_mode": _none_if_null(row["recognized_query_mode"]),
            "intent": _none_if_null(row["expected_intent_or_profile"]),
            "ast_generation_mode": _none_if_null(row["ast_generation_mode"]),
            "remote_query_allowed": False,
            "failure_stage": None,
            "failure_reason": "out_of_v3_3_release_denominator",
            "capability_id": f"v3.3:skip:{row['release_scope']}",
            "capability_status": "out_of_scope",
            "gate_status": "skipped",
            "capability_status_reason": "out_of_v3_3_release_denominator",
        },
        "v3_ast": None,
        "validated_ast": None,
        "query_plan": None,
        "mongo_params": None,
        "result": None,
        "failure_stage": None,
        "failure_reason": "out_of_v3_3_release_denominator",
    }


def _runtime_exception_result(question: str, exc: Exception) -> dict[str, Any]:
    return {
        "question": question,
        "answer": f"v3.3 查询失败：runtime_exception - {exc}",
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


def _bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _none_if_null(value: str) -> str | None:
    return None if value in {"null", ""} else value


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


if __name__ == "__main__":
    raise SystemExit(main())
