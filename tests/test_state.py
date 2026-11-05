"""Unit tests for token ledger, attention zone monitor, and tombstone tracker."""

import pytest
from occe.state.ledger import TokenLedger, AttentionZone, estimate_tokens
from occe.state.tombstone import TombstoneTracker


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello world") == 2
    code_snippet = "def calculate_loss(y_true: float, y_pred: float) -> float:\n    return (y_true - y_pred) ** 2"
    tokens = estimate_tokens(code_snippet)
    assert 15 <= tokens <= 35


def test_token_ledger_attention_zones():
    ledger = TokenLedger()
    assert ledger.current_zone == AttentionZone.GREEN

    # Add 20,000 tokens (Still Green)
    ledger.record_turn(input_tokens=20_000, output_tokens=1_000)
    assert ledger.current_zone == AttentionZone.GREEN

    # Cross 25,000 into Yellow Zone
    ledger.record_turn(input_tokens=8_000, output_tokens=500)
    assert ledger.total_context_tokens == 29_500
    assert ledger.current_zone == AttentionZone.YELLOW

    # Cross 40,000 into Red Zone
    ledger.record_turn(input_tokens=15_000, output_tokens=500)
    assert ledger.total_context_tokens == 45_000
    assert ledger.current_zone == AttentionZone.RED


def test_token_ledger_record_savings():
    ledger = TokenLedger()
    saved = ledger.record_savings("code_skeleton", raw_tokens=3_500, optimized_tokens=250)
    assert saved == 3_250
    assert ledger.tokens_saved_cumulative == 3_250
    assert ledger.tool_invocations["code_skeleton"] == 1

    summary = ledger.get_summary()
    assert summary["tokens_saved_cumulative"] == 3_250

    report = ledger.format_status_report()
    assert "OCCE Token Ledger" in report
    assert "code_skeleton" in report


def test_tombstone_tracker():
    tracker = TombstoneTracker()

    # Turn 1: Read auth.py (3,500 tokens)
    r1 = tracker.record_read(turn=1, filepath="src/auth.py", token_count=3_500)
    assert not r1.is_tombstoned

    # Turn 2: Read db.py (2,000 tokens)
    r2 = tracker.record_read(turn=2, filepath="src/db.py", token_count=2_000)

    # Active reads: 5,500 tokens
    active = tracker.get_active_reads()
    assert active["src/auth.py"] == 3_500
    assert active["src/db.py"] == 2_000

    # Turn 4: Edit auth.py
    tombstones = tracker.record_edit(turn=4, filepath="src/auth.py")
    assert len(tombstones) == 1
    assert "superseded by edit at Turn 4" in tombstones[0]
    assert r1.is_tombstoned
    assert tracker.tokens_reclaimed == (3_500 - 15)

    # db.py is still active, auth.py is inactive
    active_after = tracker.get_active_reads()
    assert "src/auth.py" not in active_after
    assert active_after["src/db.py"] == 2_000
