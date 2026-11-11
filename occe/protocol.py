"""Model Context Protocol (MCP) constants, tools schema, and specification definitions.

Adheres to MCP Protocol version 2024-11-05 over JSON-RPC 2.0.
"""

from __future__ import annotations

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "opencode-context-engine"
SERVER_VERSION = "0.1.0"

TOOL_DEFINITIONS = [
    {
        "name": "code_skeleton",
        "description": (
            "Extract an AST outline of classes, functions, signatures, argument type hints, "
            "and docstrings from a source file, replacing bodies with '...'. "
            "Consumes 80-94% fewer tokens than raw file reading."
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
                "path": {
                    "type": "string",
                    "description": "Path to the source file (relative or absolute)."
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum nesting depth to inspect (default: 3).",
                    "default": 3
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "symbol_slice",
        "description": (
            "Extract the exact implementation of a single class or function by symbol name "
            "(e.g., 'PaymentGateway' or 'PaymentGateway.charge' or 'charge'), avoiding the need "
            "to read the entire file."
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
                "path": {
                    "type": "string",
                    "description": "Path to the source file."
                },
                "symbol": {
                    "type": "string",
                    "description": "Name of the class, method, or function to extract."
                }
            },
            "required": ["path", "symbol"]
        }
    },
    {
        "name": "smart_exec",
        "description": (
            "Execute a shell command with real-time ANSI escape stripping, carriage-return collapse, "
            "package manager progress bar & spinner suppression, and intelligent head/tail truncation."
        ),
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command line to execute."
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum output lines before head/tail truncation (default: 60).",
                    "default": 60
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "test_compress",
        "description": (
            "Run test suites (pytest, cargo test, go test, jest/vitest) and output only failing tests, "
            "assertion errors, and clean stack frames, collapsing passed tests into a 1-line summary."
        ),
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Test command to execute (e.g., 'pytest tests/', 'cargo test', 'go test ./...')."
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "diff_compact",
        "description": (
            "Generate a zero-context (-U0) git diff of uncommitted changes or specific files, "
            "eliminating unchanged surrounding context lines and git index boilerplate."
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
                "filepath": {
                    "type": "string",
                    "description": "Optional specific file path to diff."
                },
                "staged": {
                    "type": "boolean",
                    "description": "Whether to inspect staged changes only.",
                    "default": False
                }
            }
        }
    },
    {
        "name": "token_ledger",
        "description": (
            "Check current session token usage, cumulative savings achieved by OCCE, "
            "and free-model attention health zone (GREEN / YELLOW / RED alert)."
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
            "properties": {}
        }
    }
]
