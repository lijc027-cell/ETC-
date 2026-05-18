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
        "phase": "v3.4",
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


def test_audit_test2_tool_runs_v3_4_script(monkeypatch):
    import etf_mcp_server

    calls = []

    def fake_run(args, cwd, capture_output, text, timeout):
        calls.append(args)

        class Result:
            returncode = 0
            stdout = "passed=44 failed=0 total=44"
            stderr = ""

        return Result()

    monkeypatch.setattr(etf_mcp_server.subprocess, "run", fake_run)

    response = etf_mcp_server.audit_test2_tool()

    assert response["ok"] is True
    assert calls[0][-1] == "scripts/audit_test2.py"
    assert response["stdout"] == "passed=44 failed=0 total=44"


def test_project_status_reports_v3_4_p2_progress():
    import etf_mcp_server

    response = etf_mcp_server.get_project_status_tool()

    assert response["ok"] is True
    assert response["default_phase"] == "v3.4"
    assert response["current_progress"]["p2_status"] == "local_uncommitted"
    assert "nav_trend" in response["current_progress"]["enabled_intents"]
    assert "scale_share_trend" in response["current_progress"]["enabled_intents"]
    assert "v3.4" in response["supported_phases"]
    assert "audit_test2" in response["tools"]
