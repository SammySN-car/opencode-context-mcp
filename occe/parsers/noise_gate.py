"""Terminal noise-gate and stream sanitization engine.

Strips ANSI escape sequences, normalizes carriage returns, suppresses package
manager progress bars, and applies saliency-preserving head/tail truncation.
"""

from __future__ import annotations

import re
import subprocess
from typing import Optional, Tuple

# Comprehensive regex matching ANSI escape sequences (CSI, OSC, standard ESC codes)
ANSI_ESCAPE_RE = re.compile(
    r'(?:\x1B[@-Z\\-_]|[\x80-\x9A\x9C-\x9F]|(?:\x1B\[|\x9B)[0-?]*[ -/]*[@-~])'
)

# Regex matching dynamic progress bars, spinners, and package manager download streams
PACKAGE_NOISE_RE = re.compile(
    r'(?:\r|^)[^\n]*?(?:'
    r'\[=+>?\s*\]|'                       # Progress bars: [===>   ]
    r'\|[█\s]+\|\s*\d+/\d+|'              # Pip Unicode bars: |████   | 4/10
    r'\d+%\s*\|\s*[\d/]+|'                # Percentage counters: 45% | 12/25
    r'⸨[░▒▓█\s]+⸩|'                       # NPM progress glyphs: ⸨░░░░░░⸩
    r'⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏|'              # Braille spinners
    r'Compiling\s+[\w\-]+\s+v\d+|'        # Cargo intermediate compilation lines
    r'Fetching\s+package\s+|'             # Yarn fetching lines
    r'Downloading\s+[\w\.\-]+|'           # Pip download lines
    r'Extracting\s+[\w\.\-]+'             # Archive extraction lines
    r')[^\n]*',
    re.MULTILINE | re.IGNORECASE
)


def strip_ansi(text: str) -> str:
    """Remove all ANSI color codes and terminal control sequences."""
    return ANSI_ESCAPE_RE.sub("", text)


def collapse_carriage_returns(text: str) -> str:
    """Resolve in-place line overwrites caused by \\r (carriage return).

    When a progress counter or spinner emits 'Step 1\\rStep 2\\rDone',
    this resolves each line to its final displayed state.
    """
    lines = text.split("\n")
    resolved_lines = []
    for line in lines:
        if "\r" in line:
            parts = [p for p in line.split("\r") if p.strip()]
            resolved_lines.append(parts[-1] if parts else "")
        else:
            resolved_lines.append(line)
    return "\n".join(resolved_lines)


def filter_package_noise(text: str) -> str:
    """Filter out progress bars, spinner frames, and intermediate build spam."""
    filtered = PACKAGE_NOISE_RE.sub("", text)
    # Remove multiple consecutive blank lines left by filtered output
    filtered = re.sub(r'\n{3,}', '\n\n', filtered)
    return filtered.strip()


def truncate_head_tail(text: str, max_lines: int = 60, head_ratio: float = 0.3) -> str:
    """Perform saliency-preserving head/tail truncation on large outputs.

    Preserves the top lines (command invocation, flags, setup) and bottom lines
    (final summary, return status, or stack traces) while omitting the middle spam.
    """
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text

    head_count = max(int(max_lines * head_ratio), 5)
    tail_count = max(max_lines - head_count, 10)
    omitted = len(lines) - (head_count + tail_count)

    if omitted <= 0:
        return text

    return (
        "\n".join(lines[:head_count])
        + f"\n\n[... OCCE Noise-Gate: {omitted} lines of verbose log omitted ...]\n\n"
        + "\n".join(lines[-tail_count:])
    )


def sanitize_terminal_output(raw_text: str, max_lines: int = 60) -> str:
    """Execute the full 4-stage noise-gate sanitization pipeline.

    1. Strip ANSI escape sequences
    2. Normalize in-place carriage returns
    3. Filter progress bars and spinners
    4. Saliency-preserving head/tail truncation
    """
    if not raw_text:
        return ""

    step1 = strip_ansi(raw_text)
    step2 = collapse_carriage_returns(step1)
    step3 = filter_package_noise(step2)
    step4 = truncate_head_tail(step3, max_lines=max_lines)
    return step4


def execute_shell_command(
    command: str,
    max_lines: int = 60,
    cwd: Optional[str] = None,
    timeout: float = 60.0
) -> Tuple[str, bool]:
    """Execute a shell command and pass its combined output through the noise gate.

    Returns:
        (sanitized_output, is_error)
    """
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout
        )
        combined_output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        sanitized = sanitize_terminal_output(combined_output, max_lines=max_lines)
        is_error = proc.returncode != 0
        return sanitized, is_error
    except subprocess.TimeoutExpired:
        return f"[OCCE Error: Command timed out after {timeout} seconds]", True
    except Exception as e:
        return f"[OCCE Execution Error: {str(e)}]", True
