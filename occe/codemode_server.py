"""OCCE v3 Code-Mode MCP Server (`execute_occe_ts`).

Exposes a single typed TypeScript execution tool backed by a locked-down
Node.js V8 vm sandbox (`ts-sdk/sandbox_runner.mjs`) and the localhost
`HostRPCBridge` forwarding calls to the Python OCCE engine.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

from occe.protocol import PROTOCOL_VERSION, SERVER_NAME
from occe.rpc_bridge import HostRPCBridge
from occe.server import MCPServer

logger = logging.getLogger("occe.codemode")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DTS_PATH = os.path.join(_REPO_ROOT, "ts-sdk", "occe.d.ts")
_RUNNER_PATH = os.path.join(_REPO_ROOT, "ts-sdk", "sandbox_runner.mjs")


def _load_dts() -> str:
    try:
        with open(_DTS_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "declare namespace occe { /* see ts-sdk/occe.d.ts */ }"


def build_codemode_tool_definitions() -> List[Dict[str, Any]]:
    dts = _load_dts()
    return [
        {
            "name": "execute_occe_ts",
            "description": (
                "PREFER THIS FOR MULTI-STEP WORKFLOWS. Execute an async TypeScript snippet "
                "inside a sandboxed V8 isolate with no filesystem or internet access, using the "
                "typed `occe` API below (`Promise.all`, loops, filtering). Intermediate data stays "
                "inside the isolate; only your `return` value enters context.\n\n"
                f"```ts\n{dts}\n```"
            ),
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "Async TypeScript function body using `occe.*` and ending with `return ...`."
                        ),
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Execution timeout in milliseconds (default: 30000, max: 120000).",
                        "default": 30000,
                    },
                },
                "required": ["code"],
            },
        }
    ]


class CodeModeMCPServer:
    """Single-tool Code-Mode MCP server wrapping MCPServer + HostRPCBridge."""

    def __init__(self, node_bin: Optional[str] = None) -> None:
        self.base_server = MCPServer()
        self.bridge = HostRPCBridge(self.base_server)
        self.node_bin = node_bin or shutil.which("node") or "node"
        self.running = True
        self._bridge_started = False

    def start_bridge(self) -> str:
        if not self._bridge_started:
            url = self.bridge.start()
            self._bridge_started = True
            return url
        return self.bridge.url

    def stop(self) -> None:
        if self._bridge_started:
            self.bridge.stop()
            self._bridge_started = False

    def execute_ts(self, code: str, timeout_ms: int = 30_000) -> Dict[str, Any]:
        rpc_url = self.start_bridge()
        req_payload = json.dumps(
            {
                "code": code,
                "rpcUrl": rpc_url,
                "token": self.bridge.token,
                "timeoutMs": timeout_ms,
            }
        )
        timeout_sec = max(5.0, min(float(timeout_ms) / 1000.0 + 5.0, 125.0))
        try:
            proc = subprocess.run(
                [self.node_bin, "--no-warnings", _RUNNER_PATH],
                input=req_payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                cwd=self.base_server.workspace_root or _REPO_ROOT,
            )
        except FileNotFoundError:
            return self.base_server._format_tool_response(
                "[OCCE CodeMode Error: Node.js executable not found on PATH]",
                is_error=True,
            )
        except subprocess.TimeoutExpired:
            return self.base_server._format_tool_response(
                f"[OCCE CodeMode Error: Sandbox timed out after {timeout_ms}ms]",
                is_error=True,
            )

        stdout = proc.stdout.strip()
        if not stdout:
            err = proc.stderr.strip() or f"Sandbox exited with code {proc.returncode}"
            return self.base_server._format_tool_response(
                f"[OCCE CodeMode Error: {err}]",
                is_error=True,
            )

        try:
            parsed = json.loads(stdout)
            is_err = not bool(parsed.get("ok", False))
            formatted = json.dumps(parsed, indent=2)
            return self.base_server._format_tool_response(formatted, is_error=is_err)
        except json.JSONDecodeError:
            return self.base_server._format_tool_response(stdout, is_error=proc.returncode != 0)

    def handle_message(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = request.get("method", "")
        msg_id = request.get("id")

        if method == "initialize":
            resp = self.base_server.handle_message(request)
            if resp and "result" in resp:
                resp["result"]["serverInfo"] = {
                    "name": f"{SERVER_NAME}-codemode",
                    "version": "0.3.0",
                }
                resp["result"]["protocolVersion"] = PROTOCOL_VERSION
            return resp

        if method.startswith("notifications/"):
            return None

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": build_codemode_tool_definitions()},
            }

        if method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            if tool_name != "execute_occe_ts":
                res = self.base_server._format_tool_response(
                    f"[OCCE CodeMode Error: Unknown tool '{tool_name}'. Use 'execute_occe_ts'.]",
                    is_error=True,
                )
            else:
                code = str(arguments.get("code", ""))
                timeout_ms = int(arguments.get("timeout_ms", 30_000))
                res = self.execute_ts(code, timeout_ms=timeout_ms)
            return {"jsonrpc": "2.0", "id": msg_id, "result": res}

        return self.base_server.handle_message(request)

    def run_stdio_loop(self) -> None:
        logger.info("%s-codemode v0.3.0 running on stdio transport", SERVER_NAME)
        self.start_bridge()
        try:
            while self.running:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line)
                    response = self.handle_message(request)
                    if response is not None:
                        sys.stdout.write(json.dumps(response) + "\n")
                        sys.stdout.flush()
                except json.JSONDecodeError as e:
                    err_resp = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {e}"},
                    }
                    sys.stdout.write(json.dumps(err_resp) + "\n")
                    sys.stdout.flush()
        finally:
            self.stop()


def main() -> None:
    server = CodeModeMCPServer()
    server.run_stdio_loop()


if __name__ == "__main__":
    main()
