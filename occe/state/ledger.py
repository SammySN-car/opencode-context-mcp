"""Token estimation, session ledger, and free-model attention degradation monitor.

Tracks token consumption across agentic turns, computes net savings achieved by
OCCE tools, and enforces a 3-tier attention health monitor tuned for OpenCode Zen
free models (Big Pickle, MiMo) to prevent sliding-window rate limit lockouts.
"""

from __future__ import annotations

import enum
import math
import re
from typing import Dict, Any


class AttentionZone(str, enum.Enum):
    GREEN = "GREEN"      # < 25,000 tokens: High attention fidelity
    YELLOW = "YELLOW"    # 25,000 - 40,000 tokens: Warning, attention fading
    RED = "RED"          # > 40,000 tokens: Critical degradation, rate limit risk


def estimate_tokens(text: str) -> int:
    """Fast local token estimation for code and prose without external dependencies.

    Uses a calibrated subword heuristic conforming to standard BPE tokenizers
    (cl100k_base, Qwen, DeepSeek):
    - Common words up to 6 characters are single tokens.
    - Long words/identifiers are split at ~4 characters per subword token.
    - Punctuation symbols are single tokens.
    - Single spaces are absorbed into words (standard BPE whitespace prefixing).
    - Extra whitespace/indentation adds 1 token per 4 spaces.
    """
    if not text:
        return 0

    # Pattern matching words, numbers, punctuation symbols, or multi-space/newline blocks
    pattern = re.compile(r'\w+|[^\w\s]|\s+')
    matches = pattern.findall(text)

    count = 0
    for match in matches:
        if match.isspace():
            # A single space is absorbed into the following token in BPE;
            # multiple spaces (like 4-space indentation) or newlines add tokens
            if len(match) > 1:
                count += max(1, len(match) // 4)
        elif len(match) <= 6:
            count += 1
        else:
            # Long identifiers or compound words get split into ~4-character subwords
            count += math.ceil(len(match) / 4.0)

    return max(1, count)


class TokenLedger:
    """Session ledger tracking token usage, cumulative savings, and attention health."""

    # Thresholds calibrated for OpenCode Zen free models
    YELLOW_THRESHOLD = 25_000
    RED_THRESHOLD = 40_000

    def __init__(self):
        self.session_tokens_sent: int = 0
        self.session_tokens_received: int = 0
        self.tokens_saved_cumulative: int = 0
        self.turn_count: int = 0
        self.tool_invocations: Dict[str, int] = {
            "code_skeleton": 0,
            "symbol_slice": 0,
            "smart_exec": 0,
            "test_compress": 0,
            "diff_compact": 0,
            "token_ledger": 0,
        }

    def record_turn(self, input_tokens: int, output_tokens: int = 0) -> None:
        """Record an agent interaction turn."""
        self.turn_count += 1
        self.session_tokens_sent += input_tokens
        self.session_tokens_received += output_tokens

    def record_savings(self, tool_name: str, raw_tokens: int, optimized_tokens: int) -> int:
        """Record tokens saved by an OCCE optimization tool.

        Returns:
            The net tokens saved for this call.
        """
        saved = max(0, raw_tokens - optimized_tokens)
        self.tokens_saved_cumulative += saved
        if tool_name in self.tool_invocations:
            self.tool_invocations[tool_name] += 1
        else:
            self.tool_invocations[tool_name] = 1
        return saved

    @property
    def total_context_tokens(self) -> int:
        """Approximate cumulative context tokens currently in session."""
        return self.session_tokens_sent + self.session_tokens_received

    @property
    def net_savings_percentage(self) -> float:
        """Calculate overall percentage reduction achieved by OCCE."""
        baseline = self.session_tokens_sent + self.tokens_saved_cumulative
        if baseline <= 0:
            return 0.0
        return (self.tokens_saved_cumulative / baseline) * 100

    @property
    def current_zone(self) -> AttentionZone:
        """Determine model attention degradation zone."""
        tokens = self.total_context_tokens
        if tokens < self.YELLOW_THRESHOLD:
            return AttentionZone.GREEN
        elif tokens < self.RED_THRESHOLD:
            return AttentionZone.YELLOW
        else:
            return AttentionZone.RED

    def get_summary(self) -> Dict[str, Any]:
        """Return a structured dictionary summary of ledger state."""
        return {
            "turn_count": self.turn_count,
            "total_context_tokens": self.total_context_tokens,
            "tokens_saved_cumulative": self.tokens_saved_cumulative,
            "net_savings_percentage": round(self.net_savings_percentage, 1),
            "attention_zone": self.current_zone.value,
            "tool_invocations": self.tool_invocations.copy(),
        }

    def format_status_report(self) -> str:
        """Format a human-readable and agent-friendly status report."""
        zone = self.current_zone
        total = self.total_context_tokens
        saved = self.tokens_saved_cumulative
        pct = self.net_savings_percentage

        if zone == AttentionZone.GREEN:
            status_desc = "[OK] Green Zone (<25k): High attention fidelity. Free models perform accurately."
        elif zone == AttentionZone.YELLOW:
            status_desc = "[WARN] Yellow Zone (25k-40k): Attention fading. Use code_skeleton & test_compress."
        else:
            status_desc = "[ALERT] Red Zone (>40k): High degradation & rate limit risk! Consider /compact or restart."

        lines = [
            "==================== OCCE Token Ledger ====================",
            f"Active Context:      ~{total:,} tokens",
            f"Cumulative Saved:    ~{saved:,} tokens ({pct:.1f}% net reduction)",
            f"Turns Recorded:      {self.turn_count}",
            f"Attention Health:    {zone.value} ({status_desc})",
            "----------------- Tool Invocations -----------------",
        ]
        for tool, count in self.tool_invocations.items():
            if count > 0:
                lines.append(f"  • {tool:<18}: {count} calls")
        lines.append("==========================================================")
        return "\n".join(lines)
