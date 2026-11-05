"""OCCE Model Context Protocol (MCP) JSON-RPC 2.0 stdio server.

Provides the 6 context optimization tools over standard input/output (stdio),
enforcing strict protocol framing, stderr logging isolation, and session state tracking.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, Optional, Tuple

from occe.protocol import PROTOCOL_VERSION, SERVER_NAME, SERVER_VERSION, TOOL_DEFINITIONS
from occe.parsers.ast_skeleton import generate_python_skeleton, extract_symbol
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


class MCPServer:
    """Zero-dependency Model Context Protocol server communicating via stdio."""

    def __init__(self):
        self.ledger = TokenLedger()
        self.tombstones = TombstoneTracker()
        self.running = True

    def _format_tool_response(self, text: str, is_error: bool = False) -> Dict[str, Any]:
        """Wrap output in standard MCP tools/call content structure."""
        # Append degradation alert if in Yellow or Red zones
        zone = self.ledger.current_zone
        final_text = text
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
                path = arguments.get("path")
                if not path or not os.path.exists(path):
                    return self._format_tool_response(f"[OCCE Error: File '{path}' not found]", is_error=True)

                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                depth = arguments.get("depth", 3)
                skeleton = generate_python_skeleton(content, max_depth=depth)

                raw_tok = estimate_tokens(content)
                opt_tok = estimate_tokens(skeleton)
                self.ledger.record_savings("code_skeleton", raw_tok, opt_tok)
                self.ledger.record_turn(input_tokens=opt_tok)
                self.tombstones.record_read(turn=self.ledger.turn_count, filepath=path, token_count=opt_tok)

                reduction = ((raw_tok - opt_tok) / raw_tok) * 100 if raw_tok > 0 else 0
                header = f"# [OCCE AST Skeleton: {os.path.basename(path)} | ~{raw_tok} -> ~{opt_tok} tokens ({reduction:.1f}% saved)]\n"
                return self._format_tool_response(header + skeleton)

            elif name == "symbol_slice":
                path = arguments.get("path")
                symbol = arguments.get("symbol")
                if not path or not os.path.exists(path):
                    return self._format_tool_response(f"[OCCE Error: File '{path}' not found]", is_error=True)
                if not symbol:
                    return self._format_tool_response("[OCCE Error: Parameter 'symbol' is required]", is_error=True)

                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                slice_code = extract_symbol(content, symbol)
                if slice_code is None:
                    return self._format_tool_response(f"[OCCE Error: Symbol '{symbol}' not found in '{path}']", is_error=True)

                raw_tok = estimate_tokens(content)
                opt_tok = estimate_tokens(slice_code)
                self.ledger.record_savings("symbol_slice", raw_tok, opt_tok)
                self.ledger.record_turn(input_tokens=opt_tok)

                header = f"# [OCCE Symbol Slice: '{symbol}' in {os.path.basename(path)} | ~{opt_tok} tokens]\n"
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
                diff_text, is_error = generate_compact_diff(filepath=filepath, staged=staged)

                opt_tok = estimate_tokens(diff_text)
                self.ledger.record_savings("diff_compact", raw_tokens=opt_tok * 3, optimized_tokens=opt_tok)
                self.ledger.record_turn(input_tokens=opt_tok)

                return self._format_tool_response(diff_text, is_error=is_error)

            elif name == "token_ledger":
                report = self.ledger.format_status_report()
                return self._format_tool_response(report)

            else:
                return self._format_tool_response(f"[OCCE Error: Tool '{name}' not found]", is_error=True)

        except Exception as e:
            logger.exception("Error executing tool %s: %s", name, e)
            return self._format_tool_response(f"[OCCE Unexpected Error: {str(e)}]", is_error=True)

    def handle_message(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single incoming JSON-RPC request/notification."""
        method = request.get("method")
        msg_id = request.get("id")

        logger.debug("Received method: %s, id: %s", method, msg_id)

        # 1. Initialization Handshake
        if method == "initialize":
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

        # 2. Initialized notification
        elif method == "notifications/initialized":
            logger.info("Client handshake successfully completed.")
            return None

        # 3. List tools
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": TOOL_DEFINITIONS
                }
            }

        # 4. Call tool
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

        # Unknown method
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
