"""Unit tests for AST skeleton and symbol extraction."""

import pytest
from occe.parsers.ast_skeleton import generate_python_skeleton, extract_symbol

SAMPLE_PYTHON_FILE = '''"""Module docstring explaining payment processing."""

import os
from typing import Optional, List, Dict
from dataclasses import dataclass

MAX_RETRIES = 5
DEFAULT_TIMEOUT = 30.0

@dataclass
class TransactionResult:
    """Represents a transaction outcome."""
    success: bool
    transaction_id: str
    error_message: Optional[str] = None
    retry_count: int = 0


class PaymentGateway:
    """Processes credit card and crypto transactions across multiple providers."""

    SANDBOX_URL: str = "https://sandbox.payment.io"
    LIVE_URL: str = "https://api.payment.io"

    def __init__(self, api_key: str, sandbox: bool = False, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Initialize gateway connection."""
        self.api_key = api_key
        self.sandbox = sandbox
        self.timeout = timeout
        self.session = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Internal helper to configure HTTP session."""
        print("Configuring HTTP pool with 20 workers...")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        # Many lines of internal setup logic
        self.session = "dummy_session"

    def charge(self, amount_cents: int, currency: str, token: str) -> TransactionResult:
        """Execute a customer charge.
        
        Args:
            amount_cents: The charge amount in smallest currency unit.
            currency: Three-letter ISO currency code.
            token: Payment card or token identifier.
        """
        if amount_cents <= 0:
            raise ValueError("Amount must be strictly positive")
        
        # Heavy implementation with validation, HMAC signing, HTTP retries
        for attempt in range(MAX_RETRIES):
            try:
                # 30 lines of request building and error handling
                return TransactionResult(success=True, transaction_id=f"tx_{attempt}")
            except Exception as e:
                pass
        return TransactionResult(success=False, transaction_id="", error_message="Exhausted retries")

    async def refund(self, transaction_id: str, amount_cents: Optional[int] = None) -> bool:
        """Asynchronously issue a refund."""
        # 25 lines of async HTTP call and signature validation
        return True


def helper_calculate_fee(amount_cents: int, rate: float = 0.029) -> int:
    """Calculate processing fee in cents."""
    fixed_fee_cents = 30
    return int(amount_cents * rate) + fixed_fee_cents
'''


def test_skeleton_preserves_signatures_and_strips_bodies():
    skeleton = generate_python_skeleton(SAMPLE_PYTHON_FILE)

    # 1. Implementation details must be gone
    assert 'print("Configuring HTTP pool with 20 workers...")' not in skeleton
    assert 'raise ValueError("Amount must be strictly positive")' not in skeleton
    assert 'fixed_fee_cents = 30' not in skeleton

    # 2. Structural signatures must be preserved
    assert "class PaymentGateway:" in skeleton
    assert "def __init__(self, api_key: str, sandbox: bool=False, timeout: float=DEFAULT_TIMEOUT) -> None:" in skeleton
    assert "def charge(self, amount_cents: int, currency: str, token: str) -> TransactionResult:" in skeleton
    assert "async def refund(self, transaction_id: str, amount_cents: Optional[int]=None) -> bool:" in skeleton
    assert "def helper_calculate_fee(amount_cents: int, rate: float=0.029) -> int:" in skeleton

    # 3. Docstrings must be preserved (first line)
    assert "Processes credit card and crypto transactions across multiple providers." in skeleton
    assert "Execute a customer charge." in skeleton

    # 4. Imports and constants must be preserved
    assert "from typing import Optional, List, Dict" in skeleton
    assert "MAX_RETRIES = 5" in skeleton

    # 5. Measure token/character reduction ratio
    orig_chars = len(SAMPLE_PYTHON_FILE)
    skel_chars = len(skeleton)
    reduction_ratio = (orig_chars - skel_chars) / orig_chars
    print(f"\nOriginal: {orig_chars} chars, Skeleton: {skel_chars} chars, Reduction: {reduction_ratio:.1%}")
    assert reduction_ratio > 0.45  # Significant reduction


def test_extract_symbol_top_level_function():
    code = extract_symbol(SAMPLE_PYTHON_FILE, "helper_calculate_fee")
    assert code is not None
    assert "def helper_calculate_fee(amount_cents: int, rate: float=0.029) -> int:" in code
    assert "fixed_fee_cents = 30" in code
    assert "return int(amount_cents * rate) + fixed_fee_cents" in code


def test_extract_symbol_class():
    code = extract_symbol(SAMPLE_PYTHON_FILE, "PaymentGateway")
    assert code is not None
    assert "class PaymentGateway:" in code
    assert "def charge" in code
    assert "def refund" in code


def test_extract_symbol_class_method_qualified():
    code = extract_symbol(SAMPLE_PYTHON_FILE, "PaymentGateway.charge")
    assert code is not None
    assert "class PaymentGateway:" in code
    assert "def charge(self, amount_cents: int, currency: str, token: str) -> TransactionResult:" in code
    assert "raise ValueError" in code
    # Internal _initialize_client should NOT be in this slice
    assert "def _initialize_client" not in code


def test_extract_symbol_class_method_unqualified():
    code = extract_symbol(SAMPLE_PYTHON_FILE, "refund")
    assert code is not None
    assert "class PaymentGateway:" in code
    assert "async def refund(self, transaction_id: str, amount_cents: Optional[int]=None) -> bool:" in code


def test_extract_nonexistent_symbol():
    code = extract_symbol(SAMPLE_PYTHON_FILE, "non_existent_func")
    assert code is None


def test_extract_symbol_constant_assignment():
    code = extract_symbol(SAMPLE_PYTHON_FILE, "MAX_RETRIES")
    assert code is not None
    assert "MAX_RETRIES = 5" in code


def test_extract_symbol_class_attribute():
    code = extract_symbol(SAMPLE_PYTHON_FILE, "PaymentGateway.SANDBOX_URL")
    assert code is not None
    assert "class PaymentGateway:" in code
    assert "SANDBOX_URL: str = 'https://sandbox.payment.io'" in code or "SANDBOX_URL" in code


def test_fallback_typescript_skeleton():
    ts_code = """
    export interface UserProfile {
        id: string;
        email: string;
    }

    export class AuthService {
        private secret: string;

        constructor(secret: string) {
            this.secret = secret;
            console.log("Setting up auth...");
        }

        async login(user: string, pass: string): Promise<boolean> {
            // 40 lines of hashing and JWT signing
            return true;
        }
    }
    """
    skeleton = generate_python_skeleton(ts_code)
    assert "interface UserProfile" in skeleton
    assert "class AuthService" in skeleton
    assert "async login(user: string, pass: string): Promise<boolean>" in skeleton
    assert 'console.log("Setting up auth...")' not in skeleton


def test_fallback_heuristic_on_syntax_error():
    broken_code = """
    def valid_func(a: int) -> int:
        return a * 2
    this is broken syntax !!! @@@
    class AnotherClass:
        def method_one(self): pass
    """
    skeleton = generate_python_skeleton(broken_code)
    assert "def valid_func" in skeleton or "class AnotherClass" in skeleton
