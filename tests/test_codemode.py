"""End-to-end tests for OCCE v3 TypeScript Code-Mode runtime, RPC bridge, and sandbox."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from occe.codemode_server import CodeModeMCPServer
from occe.parsers.diff_engine import summarize_generated_sections


def test_summarize_generated_sections_collapses_lockfiles_and_openapi():
    sample = (
        "diff --git a/app/users.py b/app/users.py\n"
        "--- a/app/users.py\n"
        "+++ b/app/users.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/docs/openapi.yaml b/docs/openapi.yaml\n"
        "--- a/docs/openapi.yaml\n"
        "+++ b/docs/openapi.yaml\n"
        "@@ -10,0 +11,2 @@\n"
        "+paths:\n"
        "+  /health:\n"
        "diff --git a/uv.lock b/uv.lock\n"
        "--- a/uv.lock\n"
        "+++ b/uv.lock\n"
        "@@ -1 +1 @@\n"
        "-v1\n"
        "+v2"
    )
    out = summarize_generated_sections(sample)
    assert "+new" in out
    assert "[OCCE Diff Summary: docs/openapi.yaml (+2 / -0 lines omitted" in out
    assert "[OCCE Diff Summary: uv.lock (+1 / -1 lines omitted" in out
    assert "/health:" not in out


def test_rpc_bridge_rejects_missing_or_wrong_token():
    srv = CodeModeMCPServer()
    url = srv.start_bridge()
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"method": "token_ledger", "arguments": {}}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-OCCE-Token": "wrong-token"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req)
            raise AssertionError("Expected 401 Unauthorized")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
    finally:
        srv.stop()


def test_codemode_mcp_initialize_and_tools_list():
    srv = CodeModeMCPServer()
    try:
        init_resp = srv.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"rootPath": "."},
            }
        )
        assert init_resp is not None
        assert init_resp["result"]["serverInfo"]["name"].endswith("-codemode")

        list_resp = srv.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert list_resp is not None
        tools = list_resp["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "execute_occe_ts"
        assert "codeSkeleton" in tools[0]["description"]
        assert "sessionHandoff" in tools[0]["description"]
    finally:
        srv.stop()


def test_codemode_executes_typescript_and_composes_parallel_calls():
    srv = CodeModeMCPServer()
    try:
        srv.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            }
        )
        ts_code = """
        interface Summary {
          hasServer: boolean;
          ledgerSaved: boolean;
          branch: string;
        }
        const [skel, slice, handoff, ledger] = await Promise.all([
          occe.codeSkeleton({ path: "occe/server.py", depth: 2 }),
          occe.fileSlice({ path: "occe/protocol.py", start_line: 1, end_line: 12 }),
          occe.sessionHandoff(),
          occe.tokenLedger(),
        ]);
        const out: Summary = {
          hasServer: !skel.isError && skel.text.includes("MCPServer") && slice.text.includes("PROTOCOL_VERSION"),
          ledgerSaved: !ledger.isError && ledger.text.includes("OCCE Token Ledger"),
          branch: handoff.branch,
        };
        return out;
        """
        resp = srv.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "execute_occe_ts", "arguments": {"code": ts_code}},
            }
        )
        assert resp is not None
        result = resp["result"]
        assert result["isError"] is False
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["ok"] is True
        assert parsed["result"]["hasServer"] is True
        assert parsed["result"]["ledgerSaved"] is True
        assert isinstance(parsed["result"]["branch"], str)
    finally:
        srv.stop()


def test_codemode_sandbox_blocks_fs_process_and_fetch():
    srv = CodeModeMCPServer()
    try:
        for snippet in [
            "return require('fs').readFileSync('pyproject.toml', 'utf8');",
            "return process.env;",
            "return await fetch('https://example.com');",
        ]:
            res = srv.execute_ts(snippet)
            assert res["isError"] is True
            parsed = json.loads(res["content"][0]["text"])
            assert parsed["ok"] is False
    finally:
        srv.stop()
