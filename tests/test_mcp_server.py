from __future__ import annotations


def test_query_etf_tool_uses_public_api_response(monkeypatch):
    import etf_mcp_server

    def fake_run_query(payload, *, root):
        return {
            "ok": True,
            "question": payload["question"],
            "answer": "answer",
            "phase": payload["phase"],
            "mode": "single",
            "intent": "basic_info",
        }

    monkeypatch.setattr(etf_mcp_server, "run_query", fake_run_query)

    response = etf_mcp_server.query_etf_tool("510300是什么", include_debug=True)

    assert response == {
        "ok": True,
        "question": "510300是什么",
        "answer": "answer",
        "phase": "v3.3",
        "mode": "single",
        "intent": "basic_info",
    }


def test_query_etf_tool_rejects_blank_question():
    import etf_mcp_server

    response = etf_mcp_server.query_etf_tool(" ")

    assert response["ok"] is False
    assert response["error"] == "question is required"


def test_audit_section_tool_runs_script(monkeypatch):
    import etf_mcp_server

    calls = []

    def fake_run(args, cwd, capture_output, text, timeout):
        calls.append(args)

        class Result:
            returncode = 0
            stdout = "overall ok"
            stderr = ""

        return Result()

    monkeypatch.setattr(etf_mcp_server.subprocess, "run", fake_run)

    response = etf_mcp_server.audit_section10_tool()

    assert response["ok"] is True
    assert calls[0][-1] == "scripts/audit_v3_3_section10.py"
    assert response["stdout"] == "overall ok"
