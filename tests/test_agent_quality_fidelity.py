"""Comprehensive Agent Quality & Fidelity Verification Suite for OCCE.

Verifies that context compression does NOT reduce the information quality,
edit accuracy, or debugging capability of autonomous coding agents.
"""

import ast
import json
import pytest
from occe.parsers.ast_skeleton import generate_python_skeleton, extract_symbol
from occe.parsers.file_slice import slice_file_lines
from occe.parsers.test_reducers import compress_pytest_output
from occe.parsers.noise_gate import execute_shell_command
from occe.parsers.diff_engine import compute_text_diff_u0


# -------------------------------------------------------------
# Pillar 1: Edit & Search-Replace Fidelity (symbol_slice & file_slice)
# -------------------------------------------------------------
COMPLEX_SERVICE_CODE = '''import os
from typing import Dict, Any, Optional

class PaymentProcessor:
    """Processes customer payments via external gateway."""

    def __init__(self, api_key: str, timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout
        self.retry_count = 3

    def charge(self, user_id: str, amount_cents: int, currency: str = "USD") -> Dict[str, Any]:
        """Charge the user and return a transaction receipt."""
        if amount_cents <= 0:
            raise ValueError("Amount must be positive")
        # Critical business logic
        transaction_id = f"tx_{user_id}_{amount_cents}"
        status = "succeeded" if amount_cents < 1000000 else "requires_review"
        return {"id": transaction_id, "status": status, "currency": currency}

    def refund(self, transaction_id: str) -> bool:
        """Issue a full refund for a previous transaction."""
        return True
'''

def test_symbol_slice_fidelity_for_exact_code_edits():
    """Verify extracted symbol preserves complete implementation and class context."""
    extracted = extract_symbol(COMPLEX_SERVICE_CODE, "PaymentProcessor.charge")
    assert extracted is not None

    # Verify class context and method signature
    assert "class PaymentProcessor:" in extracted
    assert "def charge" in extracted
    assert "user_id: str" in extracted
    assert "amount_cents: int" in extracted
    assert "currency: str" in extracted
    assert "Dict[str, Any]" in extracted
    assert '"""Charge the user and return a transaction receipt."""' in extracted
    assert "transaction_id = f'tx_{user_id}_{amount_cents}'" in extracted
    assert "if amount_cents <= 0:" in extracted
    assert "return {'id': transaction_id, 'status': status, 'currency': currency}" in extracted

    # Verify extracted slice parses cleanly as valid Python AST
    parsed = ast.parse(extracted)
    assert parsed is not None


def test_file_slice_fidelity_line_anchors(tmp_path):
    """Verify file_slice delivers exact line numbers and accurate text bounds."""
    f = tmp_path / "service.py"
    f.write_text(COMPLEX_SERVICE_CODE, encoding="utf-8")

    # Lines 12-18 correspond to def charge and its body
    out, is_err = slice_file_lines(str(f), start_line=12, end_line=18)
    assert not is_err

    # Verify line anchors match real line numbers in the original file
    original_lines = COMPLEX_SERVICE_CODE.splitlines()
    assert "def charge" in out
    assert "if amount_cents <= 0:" in out
    assert original_lines[11].strip() in out  # 0-indexed line 11 = line 12
    assert original_lines[17].strip() in out  # 0-indexed line 17 = line 18


# -------------------------------------------------------------
# Pillar 2: Debugging & Failure Diagnosis Fidelity (test_compress)
# -------------------------------------------------------------
REALISTIC_PYTEST_FAILURE = '''============================= test session starts =============================
platform win32 -- Python 3.13.0
rootdir: C:/Users/samar/project
collected 50 items

tests/unit/test_payment.py .........................F................ [100%]

=================================== FAILURES ===================================
_________________________ test_charge_negative_amount __________________________

    def test_charge_negative_amount():
        processor = PaymentProcessor("key_123")
>       processor.charge("user_99", -50)

tests/unit/test_payment.py:48: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

user_id = 'user_99', amount_cents = -50, currency = 'USD'

    def charge(self, user_id: str, amount_cents: int, currency: str = "USD"):
        if amount_cents <= 0:
>           raise ValueError("Amount must be positive")
E           ValueError: Amount must be positive

backend/app/payment.py:16: ValueError
=========================== short test summary info ===========================
FAILED tests/unit/test_payment.py::test_charge_negative_amount - ValueError: Amount must be positive
========================= 1 failed, 49 passed in 1.82s =========================
'''

def test_test_compress_preserves_100_percent_of_failure_diagnostic_data():
    """Verify that when tests fail, zero actionable debugging info is lost."""
    compressed = compress_pytest_output(REALISTIC_PYTEST_FAILURE)

    # 1. Summary line with test counts and timing
    assert "1 failed, 49 passed in 1.82s" in compressed

    # 2. Test function name
    assert "test_charge_negative_amount" in compressed

    # 3. Exact source file and line numbers
    assert "tests/unit/test_payment.py:48" in compressed
    assert "backend/app/payment.py:16" in compressed

    # 4. Exact Exception type and message
    assert "ValueError: Amount must be positive" in compressed

    # 5. Only the noisy progress dots are stripped
    assert ".........................F................" not in compressed


# -------------------------------------------------------------
# Pillar 3: API Contract & Type Understanding (code_skeleton)
# -------------------------------------------------------------
def test_code_skeleton_preserves_complete_type_hierarchy_and_docs():
    """Verify an agent reading code_skeleton understands the complete public interface."""
    skeleton = generate_python_skeleton(COMPLEX_SERVICE_CODE)

    # Verify all classes, methods, and signatures are preserved
    assert "class PaymentProcessor:" in skeleton
    assert "def __init__" in skeleton
    assert "api_key: str" in skeleton
    assert "timeout: int" in skeleton
    assert "def charge" in skeleton
    assert "user_id: str" in skeleton
    assert "amount_cents: int" in skeleton
    assert "currency: str" in skeleton
    assert "Dict[str, Any]" in skeleton
    assert "def refund" in skeleton

    # Verify first-line docstrings are preserved for semantic intent
    assert "Processes customer payments via external gateway." in skeleton
    assert "Charge the user and return a transaction receipt." in skeleton

    # Verify line anchors steer the agent to use symbol_slice
    assert "lines omitted" in skeleton
    assert "..." in skeleton


# -------------------------------------------------------------
# Pillar 4: Shell Execution & Error Propagation Fidelity (smart_exec)
# -------------------------------------------------------------
def test_smart_exec_preserves_error_status_and_tracebacks():
    """Verify smart_exec returns is_error=True and complete stderr when commands fail."""
    cmd = "python -c \"import sys; sys.stderr.write('CRITICAL DATABASE ERROR\\n'); sys.exit(2)\""
    out, is_err = execute_shell_command(cmd)

    assert is_err is True
    assert "CRITICAL DATABASE ERROR" in out


# -------------------------------------------------------------
# Pillar 5: Zero-Context Diff Precision (diff_compact)
# -------------------------------------------------------------
def test_diff_compact_preserves_exact_hunk_changes():
    """Verify diff_compact produces clean, syntactically exact patches."""
    old = "def add(a, b):\n    return a - b\n"
    new = "def add(a, b):\n    return a + b\n"
    diff = compute_text_diff_u0(old, new)

    assert "-    return a - b" in diff
    assert "+    return a + b" in diff
    assert "@@" in diff
