"""Targeted file line-range slicing engine for Markdown, JSON, YAML, and code.

Extracts a bounded window of lines with line-number anchors, eliminating the need
for agents to write ad-hoc PowerShell or Python scripts to read partial files.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple


def slice_file_lines(
    filepath: str,
    start_line: int = 1,
    end_line: Optional[int] = None,
    max_lines: int = 60
) -> Tuple[str, bool]:
    """Extract a window of lines from a file with line-number anchors.

    Returns:
        (sliced_text, is_error)
    """
    if not filepath:
        return "[OCCE Error: Parameter 'filepath' is required]", True

    if not os.path.exists(filepath):
        return f"[OCCE Error: File '{filepath}' not found]", True

    if not os.path.isfile(filepath):
        return f"[OCCE Error: Path '{filepath}' is not a file]", True

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return f"[OCCE Error reading file '{filepath}': {str(e)}]", True

    total_lines = len(lines)
    if total_lines == 0:
        return f"# [OCCE File Slice: {os.path.basename(filepath)} | Empty file (0 lines)]\n", False

    start = max(1, start_line)
    if start > total_lines:
        return (
            f"[OCCE Error: start_line {start} exceeds total file lines ({total_lines})]",
            True
        )

    if end_line is not None and end_line >= start:
        effective_end = min(total_lines, end_line)
    else:
        effective_end = min(total_lines, start + max_lines - 1)

    # Enforce max_lines ceiling if user requested an excessively huge range
    if (effective_end - start + 1) > max_lines:
        effective_end = start + max_lines - 1

    selected_lines = lines[start - 1 : effective_end]

    # Format output with line anchors
    fname = os.path.basename(filepath)
    header = (
        f"# [OCCE File Slice: {fname} (L{start}-L{effective_end} of {total_lines} lines)]\n"
    )

    formatted = []
    for idx, line in enumerate(selected_lines, start=start):
        formatted.append(f"{idx:4d} | {line.rstrip()}")

    footer = ""
    if effective_end < total_lines:
        remaining = total_lines - effective_end
        footer = f"\n# [... {remaining} remaining lines omitted. Use start_line={effective_end + 1} to continue ...]"

    return header + "\n".join(formatted) + footer, False
