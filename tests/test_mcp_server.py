"""Unit and integration tests for the OCCE MCP Server and JSON-RPC 2.0 protocol."""

import json
import pytest
from occe.server import MCPServer
from occe.protocol import PROTOCOL_VERSION, SERVER_NAME, TOOL_DEFINITIONS


@pytest.fixture
def server():
    return MCPServer()


def test_mcp_initialize(server):
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "opencode-test", "version": "1.0.0"}
        }
    }
    resp = server.handle_message(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert resp["result"]["serverInfo"]["name"] == SERVER_NAME
    assert "tools" in resp["result"]["capabilities"]


def test_mcp_notifications_initialized(server):
    req = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }
    resp = server.handle_message(req)
    assert resp is None


def test_mcp_tools_list(server):
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    resp = server.handle_message(req)
    assert resp["id"] == 2
    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "code_skeleton" in tool_names
    assert "symbol_slice" in tool_names
    assert "smart_exec" in tool_names
    assert "test_compress" in tool_names
    assert "diff_compact" in tool_names
    assert "token_ledger" in tool_names


def test_mcp_call_code_skeleton(server, tmp_path):
    py_file = tmp_path / "sample.py"
    py_file.write_text(
        "def compute_hash(val: str) -> str:\n"
        "    # 50 lines of complex hashing\n"
        "    return 'hashed_' + val\n",
        encoding="utf-8"
    )

    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "code_skeleton",
            "arguments": {"path": str(py_file)}
        }
    }
    resp = server.handle_message(req)
    assert resp["id"] == 3
    assert not resp["result"]["isError"]
    content_text = resp["result"]["content"][0]["text"]
    assert "def compute_hash(val: str) -> str:" in content_text
    assert "..." in content_text
    assert "50 lines of complex hashing" not in content_text


def test_mcp_call_symbol_slice(server, tmp_path):
    py_file = tmp_path / "sample.py"
    py_file.write_text(
        "class OrderService:\n"
        "    def create_order(self, item_id: str) -> str:\n"
        "        return 'order_123'\n"
        "    def cancel_order(self, order_id: str) -> bool:\n"
        "        return True\n",
        encoding="utf-8"
    )

    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "symbol_slice",
            "arguments": {"path": str(py_file), "symbol": "create_order"}
        }
    }
    resp = server.handle_message(req)
    assert not resp["result"]["isError"]
    content_text = resp["result"]["content"][0]["text"]
    assert "create_order" in content_text
    assert "cancel_order" not in content_text


def test_mcp_call_smart_exec(server):
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "smart_exec",
            "arguments": {"command": "python -c \"print('Hello from MCP smart_exec')\""}
        }
    }
    resp = server.handle_message(req)
    assert not resp["result"]["isError"]
    assert "Hello from MCP smart_exec" in resp["result"]["content"][0]["text"]


def test_mcp_call_token_ledger(server):
    req = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "token_ledger",
            "arguments": {}
        }
    }
    resp = server.handle_message(req)
    assert not resp["result"]["isError"]
    text = resp["result"]["content"][0]["text"]
    assert "OCCE Token Ledger" in text
    assert "Attention Health" in text


def test_mcp_call_symbol_slice_missing_symbol_shows_available(server, tmp_path):
    py_file = tmp_path / "sample.py"
    py_file.write_text(
        "class OrderService:\n"
        "    pass\n"
        "def create_order(): pass\n"
        "def cancel_order(): pass\n",
        encoding="utf-8"
    )

    req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "symbol_slice",
            "arguments": {"path": str(py_file), "symbol": "non_existent_fn"}
        }
    }
    resp = server.handle_message(req)
    assert resp["result"]["isError"]
    err_text = resp["result"]["content"][0]["text"]
    assert "Symbol 'non_existent_fn' not found" in err_text
    assert "Available symbols:" in err_text
    assert "OrderService" in err_text
    assert "create_order" in err_text


def test_mcp_client_notifications_ignored_cleanly(server):
    req_cancelled = {
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": 42}
    }
    assert server.handle_message(req_cancelled) is None

    req_progress = {
        "jsonrpc": "2.0",
        "method": "notifications/progress",
        "params": {"progress": 50}
    }
    assert server.handle_message(req_progress) is None


def test_mcp_call_test_compress(server):
    req = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "test_compress",
            "arguments": {"command": "python -c \"print('================ 5 passed in 0.20s ================')\""}
        }
    }
    resp = server.handle_message(req)
    assert not resp["result"]["isError"]
    assert "ALL 5 TESTS PASSED" in resp["result"]["content"][0]["text"]


def test_mcp_call_diff_compact(server):
    req = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "tools/call",
        "params": {
            "name": "diff_compact",
            "arguments": {"staged": False}
        }
    }
    resp = server.handle_message(req)
    assert not resp["result"]["isError"]
    text = resp["result"]["content"][0]["text"]
    assert "diff --git" in text or "OCCE" in text


def test_mcp_call_error_validation_branches(server):
    # Missing path in code_skeleton
    resp = server.handle_message({"jsonrpc": "2.0", "id": 13, "method": "tools/call", "params": {"name": "code_skeleton", "arguments": {}}})
    assert resp["result"]["isError"]

    # Nonexistent path
    resp = server.handle_message({"jsonrpc": "2.0", "id": 14, "method": "tools/call", "params": {"name": "code_skeleton", "arguments": {"path": "invalid_p.py"}}})
    assert resp["result"]["isError"]

    # Missing command in smart_exec
    resp = server.handle_message({"jsonrpc": "2.0", "id": 15, "method": "tools/call", "params": {"name": "smart_exec", "arguments": {}}})
    assert resp["result"]["isError"]

    # Missing command in test_compress
    resp = server.handle_message({"jsonrpc": "2.0", "id": 16, "method": "tools/call", "params": {"name": "test_compress", "arguments": {}}})
    assert resp["result"]["isError"]


def test_mcp_yellow_and_red_zone_alerts(server):
    # Simulate yellow zone
    server.ledger.session_tokens_sent = 30_000
    resp_yellow = server.execute_tool("token_ledger", {})
    assert "YELLOW ZONE" in resp_yellow["content"][0]["text"]

    # Simulate red zone
    server.ledger.session_tokens_sent = 50_000
    resp_red = server.execute_tool("token_ledger", {})
    assert "RED ZONE" in resp_red["content"][0]["text"]


def test_mcp_stdio_loop_execution(server, monkeypatch):
    import io
    import sys

    # Feed initialize followed by EOF
    mock_input = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 99, "method": "ping"}) + "\n"
    )
    mock_output = io.StringIO()

    monkeypatch.setattr(sys, "stdin", mock_input)
    monkeypatch.setattr(sys, "stdout", mock_output)

    server.run_stdio_loop()

    out = mock_output.getvalue().strip()
    resp = json.loads(out)
    assert resp["id"] == 99
    assert resp["result"] == {}


def test_mcp_unknown_method(server):
    req = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "non_existent_method"
    }
    resp = server.handle_message(req)
    assert resp["error"]["code"] == -32601


def test_mcp_ping(server):
    req = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "ping"
    }
    resp = server.handle_message(req)
    assert resp["result"] == {}
