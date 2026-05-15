from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .v3 import semantic_query_v3


API_VERSION = "temp-v3.4"
DEFAULT_PHASE = "v3.3"
SUPPORTED_PHASES = {"v3.2", "v3.3", "v3.4"}


def run_query(payload: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    question = _required_question(payload)
    phase = str(payload.get("phase") or DEFAULT_PHASE)
    if phase not in SUPPORTED_PHASES:
        raise ValueError("phase must be v3.2, v3.3, or v3.4")

    raw = semantic_query_v3(
        question,
        root=root or _project_root(),
        dry_run=bool(payload.get("dry_run", False)),
        no_llm=bool(payload.get("no_llm", False)),
        phase=phase,
    )
    return _public_response(raw, phase=phase, include_debug=bool(payload.get("include_debug", False)))


def openapi_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "ETF Query Temporary API",
            "version": API_VERSION,
            "description": "临时 ETF 查数接口：输入自然语言问题，返回当前 v3 查询回答。",
        },
        "servers": [{"url": "http://localhost:8090", "description": "local temporary server"}],
        "paths": {
            "/health": {
                "get": {
                    "summary": "健康检查",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/v1/query": {
                "post": {
                    "summary": "ETF 自然语言查数",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/QueryRequest"},
                                "example": {"question": "510500近一年净值走势", "phase": "v3.4"},
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "查询成功",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/QueryResponse"}
                                }
                            },
                        },
                        "400": {"description": "请求参数错误"},
                        "500": {"description": "服务端查询失败"},
                    },
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "OpenAPI 文档",
                    "responses": {"200": {"description": "OpenAPI JSON"}},
                }
            },
        },
        "components": {
            "schemas": {
                "QueryRequest": {
                    "type": "object",
                    "required": ["question"],
                    "properties": {
                        "question": {"type": "string", "description": "自然语言 ETF 查询问题"},
                        "phase": {"type": "string", "enum": sorted(SUPPORTED_PHASES), "default": DEFAULT_PHASE},
                        "dry_run": {"type": "boolean", "default": False},
                        "no_llm": {"type": "boolean", "default": False},
                        "include_debug": {"type": "boolean", "default": False},
                    },
                },
                "QueryResponse": {
                    "type": "object",
                    "required": ["ok", "question", "answer", "phase"],
                    "properties": {
                        "ok": {"type": "boolean"},
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                        "phase": {"type": "string"},
                        "mode": {"type": "string"},
                        "intent": {"type": "string"},
                        "matches": {"type": "array", "items": {"type": "object"}},
                        "query_plan": {"type": "object"},
                        "result": {"type": "object"},
                    },
                },
            }
        },
    }


def serve(*, host: str = "127.0.0.1", port: int = 8090, root: Path | None = None) -> None:
    handler = _handler(root or _project_root())
    server = ThreadingHTTPServer((host, port), handler)
    print(f"ETF Query API listening on http://{host}:{port}")
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ETF Query temporary HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port)
    return 0


def _handler(root: Path) -> type[BaseHTTPRequestHandler]:
    class ETFQueryHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self._write_json({"status": "ok", "service": "etf-query-api", "version": API_VERSION})
                return
            if self.path == "/openapi.json":
                self._write_json(openapi_spec())
                return
            self._write_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            if self.path != "/v1/query":
                self._write_json({"error": "not found"}, status=404)
                return
            try:
                payload = self._read_json()
                self._write_json(run_query(payload, root=root))
            except ValueError as exc:
                self._write_json({"ok": False, "error": str(exc)}, status=400)
            except Exception as exc:
                self._write_json({"ok": False, "error": str(exc)}, status=500)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                raise ValueError("request body is required")
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("request body must be valid JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _write_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ETFQueryHandler


def _public_response(raw: dict[str, Any], *, phase: str, include_debug: bool) -> dict[str, Any]:
    v3 = raw.get("v3") if isinstance(raw.get("v3"), dict) else {}
    response: dict[str, Any] = {
        "ok": "error" not in raw,
        "question": str(raw.get("question") or ""),
        "answer": str(raw.get("answer") or raw.get("error") or ""),
        "phase": phase,
        "mode": v3.get("recognized_query_mode"),
        "intent": v3.get("intent"),
    }
    if raw.get("matches"):
        response["matches"] = raw["matches"]
    if include_debug:
        for key in ("v3", "entities", "query_plan", "result", "debug"):
            if key in raw:
                response[key] = raw[key]
    return response


def _required_question(payload: dict[str, Any]) -> str:
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")
    return question.strip()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]
