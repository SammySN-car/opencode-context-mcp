"""Terminal noise-gate and stream sanitization engine.

Strips ANSI escape sequences (CSI, OSC, standard ESC), normalizes carriage returns,
suppresses package manager progress bars and spinners, and applies
saliency-preserving head/tail truncation.
"""

from __future__ import annotations

import re
import subprocess
from typing import Optional, Tuple

# Comprehensive regex matching ANSI escape sequences (CSI, standard ESC codes)
ANSI_ESCAPE_RE = re.compile(
    r'(?:\x1B[@-Z\\-_]|[\x80-\x9A\x9C-\x9F]|(?:\x1B\[|\x9B)[0-?]*[ -/]*[@-~])'
)

# OSC (Operating System Command) sequences, e.g. terminal titles, hyperlinks: \x1b]0;Title\x07
OSC_ESCAPE_RE = re.compile(
    r'\x1B\][0-9]+;[^\x07\x1B]*?(?:\x07|\x1B\\)'
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
    """Remove all ANSI color codes, OSC sequences, and terminal control characters."""
    if not text:
        return ""
    # Strip OSC sequences first (titles, links)
    no_osc = OSC_ESCAPE_RE.sub("", text)
    # Strip CSI and standard ANSI control sequences
    return ANSI_ESCAPE_RE.sub("", no_osc)


def collapse_carriage_returns(text: str) -> str:
    """Resolve in-place line overwrites caused by \\r (carriage return).

    Normalizes Windows \\r\\n to \\n first, then resolves any remaining in-place
    overwrites (e.g. '10%\\r20%\\rDone') to their final displayed state.
    """
    if not text:
        return ""

    # Normalize Windows CRLF first so trailing \r does not confuse overwrite logic
    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")
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
    if not text:
        return ""
    filtered = PACKAGE_NOISE_RE.sub("", text)
    # Remove excessive blank lines left behind by stripped lines
    filtered = re.sub(r'\n{3,}', '\n\n', filtered)
    return filtered.strip()


def truncate_head_tail(text: str, max_lines: int = 60, head_ratio: float = 0.3) -> str:
    """Perform saliency-preserving head/tail truncation on large outputs.

    Preserves top lines (command invocation, flags, setup) and bottom lines
    (final summary, return status, or stack traces) while omitting the middle spam.
    """
    if not text:
        return ""

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

    1. Normalize line endings and strip ANSI/OSC escape sequences
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
    """Execute a shell command with strict UTF-8 decoding and noise-gate filtering.

    On Windows, executes via PowerShell (-NoProfile -Command) to natively support
    PowerShell cmdlets, scripts, and environment variable expansions. On Unix,
    defaults to bash/sh.

    Returns:
        (sanitized_output, is_error)
    """
    import os
    try:
        if os.name == "nt":
            args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
            proc = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                timeout=timeout
            )
        else:
            bash_path = "/bin/bash" if os.path.exists("/bin/bash") else None
            proc = subprocess.run(
                command,
                shell=True,
                executable=bash_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
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
