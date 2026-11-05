"""Unit tests for multi-framework test reducers."""

import pytest
from occe.parsers.test_reducers import (
    compress_pytest_output,
    compress_cargo_test,
    compress_go_test,
    compress_jest_output,
    compress_test_output,
)


def test_compress_pytest_all_passed():
    raw = (
        "============================= test session starts =============================\n"
        "rootdir: /path/to/project\n"
        "collected 42 items\n\n"
        "tests/test_auth.py .......................................... [100%]\n\n"
        "============================== 42 passed in 1.45s ==============================\n"
    )
    result = compress_pytest_output(raw)
    assert "[OCCE Pytest: ALL 42 TESTS PASSED in 1.45s]" in result
    assert "tests/test_auth.py" not in result


def test_compress_pytest_with_failure():
    raw = (
        "============================= test session starts =============================\n"
        "collected 10 items\n"
        "tests/test_api.py .........F [100%]\n\n"
        "=================================== FAILURES ===================================\n"
        "________________________________ test_token_auth _______________________________\n"
        "tests/test_api.py:42: in test_token_auth\n"
        "    assert response.status_code == 200\n"
        "E   AssertionError: assert 401 == 200\n"
        "=========================== short test summary info ===========================\n"
        "FAILED tests/test_api.py::test_token_auth - AssertionError: assert 401 == 200\n"
        "========================= 1 failed, 9 passed in 0.85s =========================\n"
    )
    result = compress_pytest_output(raw)
    assert "[OCCE Pytest Report: 1 failed, 9 passed in 0.85s]" in result
    assert "test_token_auth" in result
    assert "assert response.status_code == 200" in result
    assert "AssertionError: assert 401 == 200" in result
    # Progress dots stripped
    assert "tests/test_api.py .........F" not in result


def test_compress_cargo_test_all_passed():
    raw = (
        "   Compiling my_crate v0.1.0\n"
        "    Finished test [unoptimized + debuginfo] target(s) in 2.34s\n"
        "     Running unittests src/lib.rs (target/debug/deps/my_crate-abc)\n\n"
        "running 18 tests\n"
        "test auth::tests::test_create_token ... ok\n"
        "test auth::tests::test_verify_token ... ok\n\n"
        "test result: ok. 18 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out\n"
    )
    result = compress_cargo_test(raw)
    assert "[OCCE Cargo Test: ALL 18 TESTS PASSED]" in result
    assert "test auth::tests::test_create_token" not in result


def test_compress_cargo_test_with_failure():
    raw = (
        "running 5 tests\n"
        "test tests::test_pass ... ok\n"
        "test tests::test_fail ... FAILED\n\n"
        "failures:\n"
        "---- tests::test_fail stdout ----\n"
        "thread 'tests::test_fail' panicked at src/lib.rs:88:9:\n"
        "assertion `left == right` failed\n"
        "  left: 401\n"
        " right: 200\n\n"
        "failures:\n"
        "    tests::test_fail\n\n"
        "test result: FAILED. 4 passed; 1 failed; 0 ignored\n"
    )
    result = compress_cargo_test(raw)
    assert "OCCE Cargo Test: FAILED (1 failed: tests::test_fail)" in result
    assert "thread 'tests::test_fail' panicked at src/lib.rs:88:9" in result
    assert "assertion `left == right` failed" in result


def test_compress_go_test_all_passed():
    raw = (
        "=== RUN   TestCreateUser\n"
        "--- PASS: TestCreateUser (0.01s)\n"
        "=== RUN   TestVerifyUser\n"
        "--- PASS: TestVerifyUser (0.00s)\n"
        "PASS\n"
        "ok  \tgithub.com/user/project/pkg/auth\t0.024s\n"
    )
    result = compress_go_test(raw)
    assert "[OCCE Go Test: ALL 1 PACKAGES PASSED]" in result
    assert "=== RUN   TestCreateUser" not in result


def test_compress_go_test_with_failure():
    raw = (
        "=== RUN   TestLogin\n"
        "--- FAIL: TestLogin (0.02s)\n"
        "    login_test.go:45: Expected token to be valid, got expired error\n"
        "FAIL\n"
        "FAIL\tgithub.com/user/project/pkg/auth\t0.031s\n"
        "FAIL\n"
    )
    result = compress_go_test(raw)
    assert "OCCE Go Test Report:" in result
    assert "--- FAIL: TestLogin" in result
    assert "login_test.go:45: Expected token to be valid" in result


def test_compress_jest_all_passed():
    raw = (
        "PASS src/auth.test.ts\n"
        "PASS src/crypto.test.ts\n\n"
        "Test Suites: 2 passed, 2 total\n"
        "Tests:       35 passed, 35 total\n"
        "Snapshots:   0 total\n"
        "Time:        1.854 s\n"
    )
    result = compress_jest_output(raw)
    assert "[OCCE Jest/Vitest: ALL 35 TESTS PASSED]" in result


def test_compress_jest_with_failure():
    raw = (
        "FAIL src/api.test.ts\n"
        "  ● API Authentication › should reject invalid tokens\n\n"
        "    expect(received).toBe(expected) // Object.is equality\n\n"
        "    Expected: 401\n"
        "    Received: 500\n\n"
        "      42 |     const res = await request(app).get('/secure');\n"
        "    > 43 |     expect(res.status).toBe(401);\n\n"
        "Test Suites: 1 failed, 1 total\n"
        "Tests:       1 failed, 10 passed, 11 total\n"
    )
    result = compress_jest_output(raw)
    assert "[OCCE Jest Test Report]" in result
    assert "FAIL src/api.test.ts" in result
    assert "● API Authentication › should reject invalid tokens" in result
    assert "Expected: 401" in result


def test_compress_test_output_auto_detection():
    # Pytest auto-detect
    pytest_raw = "42 passed in 1.25s"
    assert "OCCE Pytest:" in compress_test_output(pytest_raw, command_hint="pytest tests/")

    # Cargo auto-detect
    cargo_raw = "test result: ok. 15 passed; 0 failed"
    assert "OCCE Cargo Test:" in compress_test_output(cargo_raw, command_hint="cargo test")
