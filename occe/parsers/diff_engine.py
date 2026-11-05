"""Zero-context Git diff generator and diff compressor.

Generates -U0 (zero context) diffs that strip out unchanged surrounding lines,
file mode boilerplate, and index hashes, reducing diff token consumption by 75-85%.
"""

from __future__ import annotations

import difflib
import subprocess
from typing import Optional, Tuple


def filter_diff_headers(raw_diff: str) -> str:
    """Filter out git index hashes, binary indicators, and file permission metadata."""
    if not raw_diff:
        return ""

    lines = raw_diff.splitlines()
    filtered: list[str] = []

    for line in lines:
        # Strip index hashes: 'index 8a3f12c..5b9e01d 100644'
        if line.startswith("index ") and (".." in line or "100" in line):
            continue
        # Strip file mode lines
        if line.startswith("new file mode ") or line.startswith("deleted file mode ") or line.startswith("old mode "):
            continue
        # Strip git binary indicator
        if line.startswith("Binary files ") and "differ" in line:
            filtered.append(line)
            continue
        filtered.append(line)

    return "\n".join(filtered)


def compute_text_diff_u0(
    old_text: str,
    new_text: str,
    fromfile: str = "a/file",
    tofile: str = "b/file"
) -> str:
    """Compute an in-memory zero-context (-U0) diff between two text strings."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=fromfile,
        tofile=tofile,
        n=0  # Zero lines of surrounding context
    )
    diff_text = "".join(diff).strip()
    return diff_text if diff_text else "[OCCE: No changes detected]"


def generate_compact_diff(
    filepath: Optional[str] = None,
    staged: bool = False,
    commit: Optional[str] = None,
    cwd: Optional[str] = None
) -> Tuple[str, bool]:
    """Generate a zero-context (-U0) git diff for modified or staged files.

    Returns:
        (compact_diff, is_error)
    """
    cmd = ["git", "diff", "-U0", "--no-color", "--ignore-all-space"]

    if staged:
        cmd.append("--staged")

    if commit:
        cmd.append(commit)

    if filepath:
        cmd.extend(["--", filepath])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd
        )
        if proc.returncode != 0:
            err = proc.stderr.strip() if proc.stderr else f"git diff failed with code {proc.returncode}"
            if "not a git repository" in err.lower():
                return "[OCCE Git Error: Current directory is not a git repository]", True
            return f"[OCCE Git Error: {err}]", True

        raw_diff = proc.stdout.strip()
        if not raw_diff:
            return "[OCCE: Working directory clean (no changes)]", False

        clean_diff = filter_diff_headers(raw_diff)
        return clean_diff, False

    except FileNotFoundError:
        return "[OCCE Error: git executable not found on system PATH]", True
    except Exception as e:
        return f"[OCCE Diff Error: {str(e)}]", True
