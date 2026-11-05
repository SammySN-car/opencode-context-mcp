"""Multi-framework test output compressor and noise reducer.

Parses test outputs for Pytest, Cargo test, Go test, and Jest/Vitest.
Collapses 100% passing suites into a single status line, while isolating
exact failure tracebacks, assertion messages, collection errors, and line numbers.
"""

from __future__ import annotations

import re
import subprocess
from typing import Optional, Tuple

from occe.parsers.noise_gate import strip_ansi, sanitize_terminal_output


def compress_pytest_output(raw_output: str) -> str:
    """Compress Pytest output by collapsing passes and isolating failures/errors."""
    clean = strip_ansi(raw_output)

    pass_match = re.search(r'(?:=+\s*)?(\d+)\s+passed[^\n]*in\s+([\d\.]+)s(?:\s*=+)?', clean)
    fail_match = re.search(r'(?:=+\s*)?(\d+)\s+failed(?:,\s*(\d+)\s+passed)?[^\n]*in\s+([\d\.]+)s(?:\s*=+)?', clean)
    error_match = re.search(r'(?:=+\s*)?(\d+)\s+error[s]?[^\n]*(?:in\s+([\d\.]+)s)?(?:\s*=+)?', clean)

    # 1. Complete success without failures or errors
    if pass_match and not fail_match and not error_match:
        return f"[OCCE Pytest: ALL {pass_match.group(1)} TESTS PASSED in {pass_match.group(2)}s]"

    # 2. Collection or runtime ERRORS present (e.g., import errors or broken syntax)
    if "==================================== ERRORS ====================================" in clean or "=== ERRORS ===" in clean:
        parts = re.split(r'=+\s*ERRORS\s*=+', clean)
        if len(parts) > 1:
            err_body = parts[1]
            if "=== short test summary info ===" in err_body:
                err_body = err_body.split("=== short test summary info ===")[0]
            elif "====" in err_body:
                idx = err_body.rfind("====")
                if idx != -1:
                    err_body = err_body[:idx]
            return f"[OCCE Pytest Collection/Runtime Error]\n\n{err_body.strip()}"

    # 3. Test assertion FAILURES present
    if "FAILURES" in clean:
        parts = re.split(r'=+\s*FAILURES\s*=+', clean)
        if len(parts) > 1:
            failure_body = parts[1]
            if "=== short test summary info ===" in failure_body:
                failure_body = failure_body.split("=== short test summary info ===")[0]
            elif "====" in failure_body:
                banner_idx = failure_body.rfind("====")
                if banner_idx != -1:
                    failure_body = failure_body[:banner_idx]

            summary_line = fail_match.group(0).strip("= ") if fail_match else "Test suite failed"
            return f"[OCCE Pytest Report: {summary_line}]\n\n{failure_body.strip()}"

    # 4. Fallback to general truncation
    return sanitize_terminal_output(clean, max_lines=45)


def compress_cargo_test(raw_output: str) -> str:
    """Compress Rust (cargo test) output by collapsing passes and isolating failures."""
    clean = strip_ansi(raw_output)

    # Check for overall success: test result: ok. 15 passed; 0 failed
    ok_match = re.search(r'test result:\s+ok\.\s+(\d+)\s+passed;\s+0\s+failed', clean)
    if ok_match:
        return f"[OCCE Cargo Test: ALL {ok_match.group(1)} TESTS PASSED]"

    # Extract failed test symbols
    failed_tests = re.findall(r'^test\s+([\w::]+)\s+\.\.\.\s+FAILED', clean, re.MULTILINE)

    if "failures:" in clean:
        parts = clean.split("failures:\n")
        if len(parts) > 1:
            details = parts[1].split("test result:")[0]
            fail_count = len(failed_tests) if failed_tests else 1
            names_summary = f": {', '.join(failed_tests)}" if failed_tests else ""
            return f"[OCCE Cargo Test: FAILED ({fail_count} failed{names_summary})]\n\n{details.strip()}"

    return sanitize_terminal_output(clean, max_lines=45)


def compress_go_test(raw_output: str) -> str:
    """Compress Go (go test) output by collapsing passes and isolating failures."""
    clean = strip_ansi(raw_output)
    lines = clean.splitlines()

    # Check if any failure exists
    has_failure = any(line.startswith("FAIL") or "--- FAIL:" in line for line in lines)

    if not has_failure:
        ok_count = sum(1 for line in lines if line.startswith("ok  \t"))
        if ok_count == 0:
            ok_count = 1 if any(line.strip() == "PASS" for line in lines) else 0
        return f"[OCCE Go Test: ALL {max(ok_count, 1)} PACKAGES PASSED]"

    # Isolate failure blocks
    failure_blocks: list[str] = []
    current_block: list[str] = []
    recording = False

    for line in lines:
        if line.startswith("--- FAIL:"):
            if current_block:
                failure_blocks.append("\n".join(current_block))
                current_block = []
            recording = True
            current_block.append(line)
        elif recording:
            if line.startswith("--- PASS:") or line.startswith("PASS") or line.startswith("ok  \t"):
                recording = False
            else:
                current_block.append(line)

    if current_block:
        failure_blocks.append("\n".join(current_block))

    summary_lines = [line for line in lines if line.startswith("FAIL\t") or line.startswith("FAIL:")]
    summary_str = " | ".join(summary_lines[:2]) if summary_lines else "Go tests failed"

    return f"[OCCE Go Test Report: {summary_str}]\n\n" + "\n\n".join(failure_blocks)


def compress_jest_output(raw_output: str) -> str:
    """Compress Jest / Vitest output by collapsing passes and isolating failures."""
    clean = strip_ansi(raw_output)

    # Check for all passed: Tests: 42 passed, 42 total
    pass_match = re.search(r'Tests:\s+(\d+)\s+passed,\s+\1\s+total', clean)
    if not pass_match:
        # Vitest format: Tests  10 passed (10)
        pass_match = re.search(r'Tests\s+(\d+)\s+passed\s+\(\1\)', clean)

    if pass_match and "FAIL " not in clean and "FAIL" not in clean.splitlines()[-3:]:
        return f"[OCCE Jest/Vitest: ALL {pass_match.group(1)} TESTS PASSED]"

    lines = clean.splitlines()
    isolated_lines: list[str] = []
    capture = False

    for line in lines:
        if line.startswith("FAIL ") or "● " in line or line.strip().startswith("Error:"):
            capture = True
        elif line.startswith("Test Suites:") or line.startswith("Tests:") or line.startswith("Test Files"):
            isolated_lines.append(line)
            capture = False

        if capture:
            if not line.strip().startswith("console.log"):
                isolated_lines.append(line)

    if isolated_lines:
        return "[OCCE Jest/Vitest Test Report]\n\n" + "\n".join(isolated_lines[:50])

    return sanitize_terminal_output(clean, max_lines=45)


def compress_test_output(raw_output: str, command_hint: Optional[str] = None) -> str:
    """Auto-detect test runner framework and return compressed test output."""
    hint = (command_hint or "").lower()

    if "pytest" in hint or "test_" in hint or "=== FAILURES ===" in raw_output or "passed in " in raw_output:
        return compress_pytest_output(raw_output)
    elif "cargo test" in hint or "test result:" in raw_output:
        return compress_cargo_test(raw_output)
    elif "go test" in hint or "--- FAIL:" in raw_output or "\tok  \t" in raw_output:
        return compress_go_test(raw_output)
    elif "jest" in hint or "vitest" in hint or "npm test" in hint or "● " in raw_output or "FAIL " in raw_output:
        return compress_jest_output(raw_output)

    # Default fallback
    return sanitize_terminal_output(raw_output, max_lines=50)


def run_test_suite(
    command: str,
    cwd: Optional[str] = None,
    timeout: float = 120.0
) -> Tuple[str, bool]:
    """Execute a test command with strict UTF-8 decoding and noise-gate compression.

    Returns:
        (compressed_report, is_error)
    """
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            timeout=timeout
        )
        combined_output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        compressed = compress_test_output(combined_output, command_hint=command)
        is_error = proc.returncode != 0
        return compressed, is_error
    except subprocess.TimeoutExpired:
        return f"[OCCE Test Error: Test command timed out after {timeout}s]", True
    except Exception as e:
        return f"[OCCE Test Execution Error: {str(e)}]", True
