"""OCCE Model Context Protocol (MCP) JSON-RPC 2.0 stdio server.

Provides the 6 context optimization tools over standard input/output (stdio),
enforcing strict protocol framing, stderr logging isolation, and session state tracking.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import sys
import urllib.parse
from typing import Any, Dict, List, Optional

from occe.protocol import PROTOCOL_VERSION, SERVER_NAME, SERVER_VERSION, TOOL_DEFINITIONS
from occe.parsers.ast_skeleton import generate_python_skeleton, extract_symbol
from occe.parsers.file_slice import slice_file_lines
from occe.parsers.noise_gate import execute_shell_command
from occe.parsers.test_reducers import run_test_suite
from occe.parsers.diff_engine import generate_compact_diff
from occe.state.ledger import TokenLedger, AttentionZone, estimate_tokens
from occe.state.tombstone import TombstoneTracker

# Logging strictly to stderr to keep stdout clean for JSON-RPC messages
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [OCCE-MCP] %(levelname)s: %(message)s"
)
logger = logging.getLogger("occe.server")


def _list_available_symbols(source_code: str) -> List[str]:
    """Helper to list top-level symbols in a Python file for agent self-healing."""
    try:
        tree = ast.parse(source_code)
        symbols: List[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.append(node.name)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                symbols.append(node.target.id)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        symbols.append(t.id)
        return symbols[:15]
    except Exception:
        return []


class MCPServer:
    """Zero-dependency Model Context Protocol server communicating via stdio."""

    def __init__(self):
        self.ledger = TokenLedger()
        self.tombstones = TombstoneTracker()
        self.workspace_root: Optional[str] = None
        self.running = True

    def _resolve_path(self, raw_path: str) -> Optional[str]:
        """Resiliently resolve relative or absolute file paths across OS and workspace roots."""
        cleaned = str(raw_path).strip().strip("'\"")
        if not cleaned:
            return None
        if os.path.exists(cleaned):
            return os.path.abspath(cleaned)
        if self.workspace_root:
            cand = os.path.join(self.workspace_root, cleaned)
            if os.path.exists(cand):
                return os.path.abspath(cand)
        norm = os.path.normpath(cleaned)
        if os.path.exists(norm):
            return os.path.abspath(norm)
        return None

    def _format_tool_response(self, text: str, is_error: bool = False) -> Dict[str, Any]:
        """Wrap output in standard MCP tools/call content structure."""
        zone = self.ledger.current_zone
        final_text = text

        # Non-intrusive budget guidance appended when context crosses thresholds
        if zone == AttentionZone.YELLOW:
            final_text += (
                f"\n\n[OCCE Notice: Session context in YELLOW ZONE (~{self.ledger.total_context_tokens:,} tokens). "
                f"Attention fading. Prefer code_skeleton & test_compress over raw reads.]"
            )
        elif zone == AttentionZone.RED:
            final_text += (
                f"\n\n[OCCE ALERT: Session context in RED ZONE (~{self.ledger.total_context_tokens:,} tokens). "
                f"High risk of Zen rate limit lockout & hallucinated edits! Run /compact or restart session.]"
            )

        return {
            "content": [
                {
                    "type": "text",
                    "text": final_text
                }
            ],
            "isError": is_error
        }

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one of the registered OCCE tools."""
        try:
            if name == "code_skeleton":
                raw_path = str(arguments.get("path", "")).strip().strip("'\"")
                if not raw_path:
                    return self._format_tool_response("[OCCE Error: Parameter 'path' is required]", is_error=True)

                resolved_path = self._resolve_path(raw_path)
                if not resolved_path:
                    abs_p = os.path.abspath(raw_path)
                    return self._format_tool_response(f"[OCCE Error: File '{raw_path}' not found at '{abs_p}']", is_error=True)

                with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                depth = arguments.get("depth", 3)
                skeleton = generate_python_skeleton(content, max_depth=depth)

                raw_tok = estimate_tokens(content)
                opt_tok = estimate_tokens(skeleton)
                self.ledger.record_savings("code_skeleton", raw_tok, opt_tok)
                self.ledger.record_turn(input_tokens=opt_tok)
                self.tombstones.record_read(turn=self.ledger.turn_count, filepath=resolved_path, token_count=opt_tok)

                reduction = ((raw_tok - opt_tok) / raw_tok) * 100 if raw_tok > 0 else 0
                header = f"# [OCCE AST Skeleton: {os.path.basename(resolved_path)} | ~{raw_tok} -> ~{opt_tok} tokens ({reduction:.1f}% saved)]\n"
                return self._format_tool_response(header + skeleton)

            elif name == "symbol_slice":
                raw_path = str(arguments.get("path", "")).strip().strip("'\"")
                symbol = str(arguments.get("symbol", "")).strip()

                if not raw_path:
                    return self._format_tool_response("[OCCE Error: Parameter 'path' is required]", is_error=True)
                if not symbol:
                    return self._format_tool_response("[OCCE Error: Parameter 'symbol' is required]", is_error=True)

                resolved_path = self._resolve_path(raw_path)
                if not resolved_path:
                    abs_p = os.path.abspath(raw_path)
                    return self._format_tool_response(f"[OCCE Error: File '{raw_path}' not found at '{abs_p}']", is_error=True)

                with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                slice_code = extract_symbol(content, symbol)
                if slice_code is None:
                    avail = _list_available_symbols(content)
                    avail_str = f" Available symbols: {', '.join(avail)}" if avail else ""
                    return self._format_tool_response(
                        f"[OCCE Error: Symbol '{symbol}' not found in '{raw_path}'.{avail_str}]",
                        is_error=True
                    )

                raw_tok = estimate_tokens(content)
                opt_tok = estimate_tokens(slice_code)
                self.ledger.record_savings("symbol_slice", raw_tok, opt_tok)
                self.ledger.record_turn(input_tokens=opt_tok)

                header = f"# [OCCE Symbol Slice: '{symbol}' in {os.path.basename(raw_path)} | ~{opt_tok} tokens]\n"
                return self._format_tool_response(header + slice_code)

            elif name == "smart_exec":
                command = arguments.get("command")
                if not command:
                    return self._format_tool_response("[OCCE Error: Parameter 'command' is required]", is_error=True)

                max_lines = arguments.get("max_lines", 60)
                output, is_error = execute_shell_command(command, max_lines=max_lines)

                raw_tok = estimate_tokens(command) * 2 + 100
                opt_tok = estimate_tokens(output)
                self.ledger.record_savings("smart_exec", raw_tok, opt_tok)
                self.ledger.record_turn(input_tokens=opt_tok)

                return self._format_tool_response(output, is_error=is_error)

            elif name == "test_compress":
                command = arguments.get("command")
                if not command:
                    return self._format_tool_response("[OCCE Error: Parameter 'command' is required]", is_error=True)

                report, is_error = run_test_suite(command)
                opt_tok = estimate_tokens(report)
                self.ledger.record_savings("test_compress", raw_tokens=opt_tok * 4, optimized_tokens=opt_tok)
                self.ledger.record_turn(input_tokens=opt_tok)

                return self._format_tool_response(report, is_error=is_error)

            elif name == "diff_compact":
                filepath = arguments.get("filepath")
                staged = arguments.get("staged", False)
                diff_text, is_error = generate_compact_diff(
                    filepath=filepath,
                    staged=staged,
                    cwd=self.workspace_root
                )

                opt_tok = estimate_tokens(diff_text)
                self.ledger.record_savings("diff_compact", raw_tokens=opt_tok * 3, optimized_tokens=opt_tok)
                self.ledger.record_turn(input_tokens=opt_tok)

                return self._format_tool_response(diff_text, is_error=is_error)

            elif name == "file_slice":
                raw_path = str(arguments.get("path", "")).strip().strip("'\"")
                if not raw_path:
                    return self._format_tool_response("[OCCE Error: Parameter 'path' is required]", is_error=True)

                resolved_path = self._resolve_path(raw_path)
                if not resolved_path:
                    abs_p = os.path.abspath(raw_path)
                    return self._format_tool_response(f"[OCCE Error: File '{raw_path}' not found at '{abs_p}']", is_error=True)

                start_line = arguments.get("start_line", 1)
                end_line = arguments.get("end_line")
                max_lines = arguments.get("max_lines", 60)

                slice_text, is_error = slice_file_lines(
                    filepath=resolved_path,
                    start_line=start_line,
                    end_line=end_line,
                    max_lines=max_lines
                )

                opt_tok = estimate_tokens(slice_text)
                self.ledger.record_savings("file_slice", raw_tokens=opt_tok * 5, optimized_tokens=opt_tok)
                self.ledger.record_turn(input_tokens=opt_tok)
                return self._format_tool_response(slice_text, is_error=is_error)

            elif name == "token_ledger":
                report = self.ledger.format_status_report()
                return self._format_tool_response(report)

            else:
                return self._format_tool_response(f"[OCCE Error: Tool '{name}' not found]", is_error=True)

        except Exception as e:
            logger.exception("Error executing tool %s: %s", name, e)
            return self._format_tool_response(f"[OCCE Unexpected Error: {str(e)}]", is_error=True)

    def handle_message(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single incoming JSON-RPC request or notification."""
        method = request.get("method", "")
        msg_id = request.get("id")

        logger.debug("Received method: %s, id: %s", method, msg_id)

        # 1. Initialization Handshake
        if method == "initialize":
            params = request.get("params", {})
            root_path = params.get("rootPath")
            root_uri = params.get("rootUri")
            if root_path and os.path.isdir(str(root_path)):
                self.workspace_root = os.path.abspath(str(root_path))
            elif root_uri and str(root_uri).startswith("file://"):
                parsed = urllib.parse.unquote(str(root_uri)[7:])
                if sys.platform == "win32" and parsed.startswith("/") and len(parsed) > 2 and parsed[2] == ":":
                    parsed = parsed[1:]
                if os.path.isdir(parsed):
                    self.workspace_root = os.path.abspath(parsed)

            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False}
                    },
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION
                    }
                }
            }

        # 2. Client notifications (must never return a response)
        elif method.startswith("notifications/"):
            logger.debug("Handled client notification: %s", method)
            return None

        # 3. List available tools
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": TOOL_DEFINITIONS
                }
            }

        # 4. Call a tool
        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = self.execute_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": result
            }

        # 5. Ping
        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {}
            }

        # 6. Unknown method
        else:
            if msg_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found"
                    }
                }
            return None

    def run_stdio_loop(self) -> None:
        """Run standard I/O (stdio) event loop reading and writing JSON-RPC messages."""
        logger.info("%s v%s running on stdio transport", SERVER_NAME, SERVER_VERSION)
        while self.running:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue

                request = json.loads(line)
                response = self.handle_message(request)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()

            except json.JSONDecodeError as e:
                logger.error("JSON decode error: %s", e)
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error: Invalid JSON"}
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
            except Exception as e:
                logger.exception("Unexpected error in stdio loop: %s", e)


def main():
    """Main entrypoint for the OCCE MCP server CLI."""
    server = MCPServer()
    server.run_stdio_loop()


if __name__ == "__main__":
    main()
