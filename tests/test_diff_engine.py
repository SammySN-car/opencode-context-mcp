"""Unit tests for zero-context diff generator and compressor."""

import difflib
import pytest
from occe.parsers.diff_engine import (
    compute_text_diff_u0,
    filter_diff_headers,
    generate_compact_diff,
)

SAMPLE_OLD = """def calculate_total(items, tax_rate):
    subtotal = 0.0
    for item in items:
        subtotal += item.price * item.quantity
    
    # Calculate tax
    tax = subtotal * tax_rate
    total = subtotal + tax
    return total

def print_receipt(total):
    print("====================")
    print(f"Total: ${total:.2f}")
    print("====================")
"""

SAMPLE_NEW = """def calculate_total(items, tax_rate):
    subtotal = 0.0
    for item in items:
        subtotal += item.price * item.quantity
    
    # Calculate tax with discount support
    discount = 0.10 if subtotal > 100.0 else 0.0
    subtotal -= subtotal * discount
    tax = subtotal * tax_rate
    total = subtotal + tax
    return total

def print_receipt(total):
    print("====================")
    print(f"Total: ${total:.2f}")
    print("====================")
"""


def test_compute_text_diff_u0_zero_context():
    # Generate -U0 diff
    diff_u0 = compute_text_diff_u0(SAMPLE_OLD, SAMPLE_NEW)

    # 1. New modifications must be present
    assert "+    discount = 0.10 if subtotal > 100.0 else 0.0" in diff_u0
    assert "+    subtotal -= subtotal * discount" in diff_u0

    # 2. Unchanged context lines must NOT be present (zero context)
    assert "print_receipt" not in diff_u0
    assert "for item in items:" not in diff_u0
    assert "subtotal += item.price * item.quantity" not in diff_u0

    # 3. Compare with standard -U3 diff size
    diff_u3 = "".join(
        difflib.unified_diff(
            SAMPLE_OLD.splitlines(keepends=True),
            SAMPLE_NEW.splitlines(keepends=True),
            n=3
        )
    )
    assert len(diff_u0) < len(diff_u3)
    reduction = (len(diff_u3) - len(diff_u0)) / len(diff_u3)
    print(f"\nU3 Diff: {len(diff_u3)} chars, U0 Diff: {len(diff_u0)} chars, Reduction: {reduction:.1%}")
    assert reduction > 0.35


def test_compute_text_diff_u0_no_changes():
    diff = compute_text_diff_u0(SAMPLE_OLD, SAMPLE_OLD)
    assert "[OCCE: No changes detected]" in diff


def test_filter_diff_headers():
    raw_git_diff = (
        "diff --git a/src/auth.py b/src/auth.py\n"
        "index 8a3f12c..5b9e01d 100644\n"
        "new file mode 100644\n"
        "--- a/src/auth.py\n"
        "+++ b/src/auth.py\n"
        "@@ -10 +10,2 @@\n"
        "-old_call()\n"
        "+new_call_step1()\n"
        "+new_call_step2()\n"
    )
    cleaned = filter_diff_headers(raw_git_diff)
    assert "index 8a3f12c..5b9e01d 100644" not in cleaned
    assert "new file mode 100644" not in cleaned
    assert "--- a/src/auth.py" in cleaned
    assert "+new_call_step1()" in cleaned


def test_generate_compact_diff_with_local_changes(tmp_path):
    # Create a hermetic git repository in tmp_path
    import subprocess
    repo = str(tmp_path)
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, capture_output=True, check=True)

    test_file = tmp_path / "hello.py"
    test_file.write_text("print('version 1')\n", encoding="utf-8")
    subprocess.run(["git", "add", "hello.py"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True, check=True)

    # Clean check
    clean_diff, err = generate_compact_diff(cwd=repo)
    assert not err
    assert "[OCCE: Working directory clean" in clean_diff

    # Modify file
    test_file.write_text("print('version 2 - modified')\n", encoding="utf-8")

    # Dirty check
    dirty_diff, err = generate_compact_diff(cwd=repo)
    assert not err
    assert "--- a/hello.py" in dirty_diff
    assert "+print('version 2 - modified')" in dirty_diff
