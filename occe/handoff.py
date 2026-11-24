"""Single-call deterministic session handoff snapshot for quota/agent transitions."""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List, Optional

from occe.parsers.diff_engine import find_git_root, generate_compact_diff
from occe.state.ledger import TokenLedger


def _git_out(args: List[str], cwd: Optional[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


def build_session_handoff(
    ledger: TokenLedger,
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a compact structured handoff snapshot in one deterministic host call."""
    git_root = find_git_root(workspace_root)
    branch = _git_out(["rev-parse", "--abbrev-ref", "HEAD"], git_root) or "unknown"
    head_sha = _git_out(["rev-parse", "--short", "HEAD"], git_root) or "unknown"
    status = _git_out(["status", "-sb"], git_root) or "clean"
    log_raw = _git_out(["log", "-n", "5", "--oneline"], git_root)
    recent_commits = [line for line in log_raw.splitlines() if line.strip()] if log_raw else []
    compact_diff, _ = generate_compact_diff(cwd=git_root, exclude_generated=True)
    if len(compact_diff) > 3500:
        compact_diff = compact_diff[:3500] + "\n... [OCCE Handoff: diff truncated]"

    return {
        "branch": branch,
        "headSha": head_sha,
        "status": status,
        "recentCommits": recent_commits,
        "compactDiff": compact_diff,
        "ledger": ledger.get_summary(),
    }
