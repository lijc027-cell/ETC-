from __future__ import annotations

import json
import shlex
import uuid
from typing import Any

from .name_resolver import CATALOG_FIELDS


RUNNER = r'''
import json
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

        if plan["limit"] == 1:
            result = collection.find_one(plan["filter"], projection)
        else:
            result = list(collection.find(plan["filter"], projection).limit(plan["limit"]))

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
    values = {"fundcode": plan["filter"].get("fundcode")}
    for field in plan["projection"]:
        if field == "fundcode":
            values[field] = plan["filter"].get("fundcode")
        elif field == "ths_fund_scale_fund":
            values[field] = 12345678900
        elif field == "ths_current_mv_fund":
            values[field] = 12100000000
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
        elif "dividend" in field:
            values[field] = 3
        else:
            values[field] = "示例值"
    return {"success": True, "data": values}


def _write_remote_json(sftp, path: str, payload: dict[str, Any]) -> None:
    with sftp.open(path, "w") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))


def _write_remote_text(sftp, path: str, payload: str) -> None:
    with sftp.open(path, "w") as handle:
        handle.write(payload)
