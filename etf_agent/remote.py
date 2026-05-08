from __future__ import annotations

import json
import re
import shlex
import uuid
from typing import Any

from .name_resolver import CATALOG_FIELDS


RUNNER = r'''
import json
import re
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient


def to_jsonable(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return value


def compile_filter(raw_filter):
    clauses = []
    query = {}
    post_filters = []
    for field, value in raw_filter.items():
        if field == "__search_text__" and isinstance(value, dict) and "$contains" in value:
            keyword = re.escape(str(value["$contains"]))
            clauses.append({
                "$or": [
                    {"ths_fund_extended_inner_short_name_fund": {"$regex": keyword, "$options": "i"}},
                    {"ths_name_of_tracking_index_fund": {"$regex": keyword, "$options": "i"}},
                    {"ths_tracking_index_code_fund": {"$regex": keyword, "$options": "i"}},
                ]
            })
        elif isinstance(value, dict) and any(op in value for op in ("$gt", "$gte", "$lt", "$lte")):
            post_filters.append((field, value))
        else:
            query[field] = value
    if clauses and query:
        return {"$and": [query, *clauses]}, post_filters
    if clauses:
        return clauses[0], post_filters
    return query, post_filters


def latest_value(value):
    if not isinstance(value, list) or not value:
        return value
    dict_items = [item for item in value if isinstance(item, dict) and "value" in item]
    if not dict_items:
        return value
    latest = max(dict_items, key=lambda item: str(item.get("btime", "")))
    return latest.get("value")


def sort_documents(documents, sort_spec):
    if not sort_spec:
        return documents

    sorted_documents = documents
    for field, direction in reversed(sort_spec):
        reverse = direction == -1

        def key(document, field=field, direction=direction):
            value = latest_value(document.get(field))
            if value is None:
                return float("-inf") if direction == -1 else float("inf")
            return value

        sorted_documents = sorted(sorted_documents, key=key, reverse=reverse)
    return sorted_documents


def apply_post_filters(documents, post_filters):
    if not post_filters:
        return documents
    return [document for document in documents if all(match_compare(document.get(field), ops) for field, ops in post_filters)]


def match_compare(raw_value, ops):
    value = latest_value(raw_value)
    if value is None:
        return False
    for op, threshold in ops.items():
        if op == "$gt" and not value > threshold:
            return False
        if op == "$gte" and not value >= threshold:
            return False
        if op == "$lt" and not value < threshold:
            return False
        if op == "$lte" and not value <= threshold:
            return False
    return True


def main():
    query_plan_path = sys.argv[1]
    result_path = sys.argv[2]
    mongo_uri = sys.argv[3]
    db_name = sys.argv[4]

    try:
        with open(query_plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        collection = db[plan["collection"]]
        projection = {field: 1 for field in plan["projection"]}
        projection["_id"] = 0
        query_filter, post_filters = compile_filter(plan["filter"])
        sort_spec = plan.get("sort", [])

        if sort_spec or post_filters:
            documents = list(collection.find(query_filter, projection))
            documents = apply_post_filters(documents, post_filters)
            documents = sort_documents(documents, sort_spec)
            if plan["limit"] == 1:
                result = documents[0] if documents else None
            else:
                result = documents[:plan["limit"]]
        elif plan["limit"] == 1:
            result = collection.find_one(query_filter, projection)
        else:
            result = list(collection.find(query_filter, projection).limit(plan["limit"]))

        out = {"success": True, "data": to_jsonable(result)}
    except Exception as exc:
        out = {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=5),
        }
    Path(result_path).write_text(json.dumps(out, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
'''


def execute_remote_query(plan: dict[str, Any], config) -> dict[str, Any]:
    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError("阶段：远端 Mongo 查询\n错误：缺少 paramiko 依赖，请先 pip install -r requirements.txt") from exc

    token = uuid.uuid4().hex
    remote_plan = f"/tmp/etf_query_plan_{token}.json"
    remote_runner = f"/tmp/etf_query_runner_{token}.py"
    remote_result = f"/tmp/etf_query_result_{token}.json"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            config.ssh_host,
            config.ssh_port,
            config.ssh_user,
            config.ssh_password,
            timeout=5,
        )
        sftp = ssh.open_sftp()
        _write_remote_json(sftp, remote_plan, plan)
        _write_remote_text(sftp, remote_runner, RUNNER)
        command = " ".join(
            [
                shlex.quote(config.remote_python),
                shlex.quote(remote_runner),
                shlex.quote(remote_plan),
                shlex.quote(remote_result),
                shlex.quote(config.remote_mongo_uri),
                shlex.quote(config.remote_db),
            ]
        )
        stdin, stdout, stderr = ssh.exec_command(command, timeout=15)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            err = stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"阶段：远端 Mongo 查询\n错误：远端执行失败：{err}")
        with sftp.open(remote_result, "rb") as handle:
            result = json.loads(handle.read().decode("utf-8"))
        if not result.get("success"):
            raise RuntimeError(f"阶段：远端 Mongo 查询\n错误：远端 Mongo 查询失败：{result.get('error')}")
        return result
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"阶段：远端 Mongo 查询\n错误：SSH 连接失败或查询失败：{exc}") from exc
    finally:
        try:
            _stdin, stdout, stderr = ssh.exec_command(
                f"rm -f {shlex.quote(remote_plan)} {shlex.quote(remote_runner)} {shlex.quote(remote_result)}"
            )
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                warning = stderr.read().decode("utf-8", errors="replace")
                print(f"warning: remote temp cleanup failed: {warning}")
        except Exception:
            print("warning: remote temp cleanup failed")
        try:
            ssh.close()
        except Exception:
            pass


def fetch_etf_name_catalog(config) -> list[dict[str, Any]]:
    plan = {
        "collection": "tb_ths_etf_base",
        "filter": {},
        "projection": CATALOG_FIELDS,
        "limit": 5000,
    }
    result = execute_remote_query(plan, config)
    data = result.get("data") or []
    return data if isinstance(data, list) else [data]


def fake_result(plan: dict[str, Any]) -> dict[str, Any]:
    if plan["filter"].get("fundcode") == "000001":
        return {"success": True, "data": None}
    if plan.get("output_style") in {"list", "compare"} or plan["limit"] > 1:
        return {"success": True, "data": _fake_rows(plan)}
    values = {"fundcode": plan["filter"].get("fundcode")}
    for field in plan["projection"]:
        if field == "fundcode":
            values[field] = plan["filter"].get("fundcode")
        elif field == "ths_fund_scale_fund":
            values[field] = 12345678900
        elif field == "ths_current_mv_fund":
            values[field] = 12100000000
        elif field == "ths_unit_nv_fund":
            values[field] = 5.1234
        elif field == "ths_unit_nvg_rate_fund":
            values[field] = 0.56
        elif field == "ths_fund_shares_fund":
            values[field] = 2345678900
        elif field == "ths_tracking_index_code_fund":
            values[field] = "000300"
        elif field == "ths_name_of_tracking_index_fund":
            values[field] = "沪深300指数"
        elif field == "ths_fund_extended_inner_short_name_fund":
            values[field] = "沪深300ETF"
        elif field == "ths_manage_fee_rate_fund":
            values[field] = 0.5
        elif field == "ths_mandate_fee_rate_fund":
            values[field] = 0.1
        elif "yeild_rank" in field and field.endswith("_etf"):
            values[field] = 12
        elif "yeild_rank" in field:
            values[field] = "100/500"
        elif "yeild" in field:
            values[field] = 8.88
        elif field == "ths_accum_dividend_total_amt_fund":
            values[field] = 2639000000
        elif field == "ths_accum_dividend_times_fund":
            values[field] = 3
        else:
            values[field] = "示例值"
    return {"success": True, "data": values}


def _fake_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    fundcodes = _fundcodes_for_fake_rows(plan)
    rows = []
    for index, fundcode in enumerate(fundcodes, start=1):
        if fundcode in {"000000", "000001"}:
            continue
        row = {"fundcode": fundcode}
        for field in plan["projection"]:
            if field == "fundcode":
                row[field] = fundcode
            elif field == "ths_fund_extended_inner_short_name_fund":
                row[field] = _fake_name(fundcode, index)
            elif field == "ths_fund_scale_fund":
                row[field] = (120 - index * 7) * 100000000
            elif field == "ths_manage_fee_rate_fund":
                row[field] = round(0.12 + index * 0.03, 2)
            elif field == "ths_mandate_fee_rate_fund":
                row[field] = 0.05
            elif field == "ths_yeild_ytd_fund":
                row[field] = round(6.5 - index * 0.3, 2)
            elif field == "ths_yeild_1y_fund":
                row[field] = round(20.0 + index * 1.1, 2)
            elif field == "ths_yeild_std_fund":
                row[field] = round(80.0 + index * 3.5, 2)
            elif field == "ths_name_of_tracking_index_fund":
                row[field] = "沪深300指数" if fundcode in {"510300", "159919"} else "中证小盘500指数"
            elif field == "ths_fund_listed_exchange_fund":
                row[field] = "上交所"
            elif field == "ths_fund_invest_type_fund":
                row[field] = "股票型"
            else:
                row[field] = "示例值"
        rows.append(row)
    return rows[: plan["limit"]]


def _fundcodes_for_fake_rows(plan: dict[str, Any]) -> list[str]:
    fundcode_filter = plan["filter"].get("fundcode")
    if isinstance(fundcode_filter, dict) and "$in" in fundcode_filter:
        return [str(item) for item in fundcode_filter["$in"]]
    if isinstance(fundcode_filter, str):
        return [fundcode_filter]
    return ["510300", "510500", "159919", "510350", "512880", "588000", "159915", "515180", "512010", "510330"]


def _fake_name(fundcode: str, index: int) -> str:
    names = {
        "510300": "沪深300ETF",
        "510500": "中证500ETF",
        "159919": "沪深300ETF深市",
        "510350": "沪深300ETF工银",
        "512880": "证券ETF",
    }
    return names.get(fundcode, f"示例ETF{index}")


def _write_remote_json(sftp, path: str, payload: dict[str, Any]) -> None:
    with sftp.open(path, "w") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))


def _write_remote_text(sftp, path: str, payload: str) -> None:
    with sftp.open(path, "w") as handle:
        handle.write(payload)
