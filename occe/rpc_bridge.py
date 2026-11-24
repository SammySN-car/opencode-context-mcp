"""Localhost-only authenticated RPC bridge for OCCE Code-Mode sandboxes."""

from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from occe.handoff import build_session_handoff


class HostRPCBridge:
    """Thread-safe 127.0.0.1 HTTP-JSON bridge forwarding sandbox calls to MCPServer."""

    def __init__(self, mcp_server: Any) -> None:
        self.mcp_server = mcp_server
        self.token = secrets.token_urlsafe(24)
        self._lock = threading.Lock()
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        if self._httpd is None:
            raise RuntimeError("HostRPCBridge has not been started")
        host, port = self._httpd.server_address
        return f"http://{host}:{port}/rpc"

    def start(self) -> str:
        bridge = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/rpc":
                    self.send_error(404, "Not Found")
                    return

                auth = self.headers.get("X-OCCE-Token", "")
                if not secrets.compare_digest(auth, bridge.token):
                    self.send_error(401, "Unauthorized")
                    return

                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length)
                try:
                    req = json.loads(raw_body.decode("utf-8"))
                except Exception:
                    self.send_error(400, "Invalid JSON")
                    return

                method = str(req.get("method", ""))
                args: Dict[str, Any] = req.get("arguments") or {}

                with bridge._lock:
                    if method == "session_handoff":
                        payload: Any = build_session_handoff(
                            bridge.mcp_server.ledger,
                            workspace_root=bridge.mcp_server.workspace_root,
                        )
                    else:
                        res = bridge.mcp_server.execute_tool(method, args)
                        content = res.get("content", [])
                        text = content[0].get("text", "") if content else ""
                        payload = {
                            "text": text,
                            "isError": bool(res.get("isError", False)),
                        }

                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.url

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
