"""Unit tests for the terminal noise-gate and sanitization pipeline."""

import pytest
from occe.parsers.noise_gate import (
    strip_ansi,
    collapse_carriage_returns,
    filter_package_noise,
    truncate_head_tail,
    sanitize_terminal_output,
    execute_shell_command,
)


def test_strip_ansi_colors_and_controls():
    raw_with_ansi = (
        "\x1b[1m\x1b[32mPASS\x1b[39m\x1b[22m src/auth.test.ts\n"
        "\x1b[36m[\x1b[39m\x1b[36mINFO\x1b[39m\x1b[36m]\x1b[39m Connecting to database...\n"
        "\x1b[2K\r\x1b[1A\x1b[31mFAIL\x1b[39m test failed"
    )
    cleaned = strip_ansi(raw_with_ansi)
    assert "\x1b" not in cleaned
    assert "PASS src/auth.test.ts" in cleaned
    assert "Connecting to database..." in cleaned
    assert "FAIL test failed" in cleaned


def test_collapse_carriage_returns():
    overwrites = "Downloading 10%\rDownloading 50%\rDownloading 100%\nDone!"
    collapsed = collapse_carriage_returns(overwrites)
    assert "Downloading 10%" not in collapsed
    assert "Downloading 50%" not in collapsed
    assert "Downloading 100%" in collapsed
    assert "Done!" in collapsed


def test_filter_package_manager_noise():
    noisy_output = (
        "Running build...\n"
        "Downloading package-a-1.0.0.tar.gz (45.2 MB) |████████████████| 100%\n"
        "⠋ Resolving dependencies...\n"
        "⸨░░░░░░░░░░░░░░░░░░⸩ reify:timing\n"
        "Compiling serde v1.0.197\n"
        "Compiling tokio v1.37.0\n"
        "Successfully installed package-a\n"
        "Build completed successfully in 3.42s"
    )
    filtered = filter_package_noise(noisy_output)
    # Intermediate noise removed
    assert "|████████████████|" not in filtered
    assert "⠋" not in filtered
    assert "⸨░░░░░░░░░░░░░░░░░░⸩" not in filtered
    assert "Compiling serde" not in filtered
    assert "Compiling tokio" not in filtered
    # Final important lines preserved
    assert "Running build..." in filtered
    assert "Successfully installed package-a" in filtered
    assert "Build completed successfully in 3.42s" in filtered


def test_truncate_head_tail():
    long_log = "\n".join(f"Log line {i}: processing item {i*7}" for i in range(120))
    truncated = truncate_head_tail(long_log, max_lines=40)
    lines = truncated.splitlines()

    # Total lines should be close to 40 + banner lines
    assert len(lines) < 50
    assert "Log line 0: processing item 0" in truncated  # Head preserved
    assert "Log line 119: processing item 833" in truncated  # Tail preserved
    assert "OCCE Noise-Gate:" in truncated
    assert "lines of verbose log omitted" in truncated


def test_full_sanitization_pipeline():
    complex_stream = (
        "\x1b[33mSetting up environment...\x1b[0m\n"
        "Progress: 10%\rProgress: 80%\rProgress: 100%\n"
        "⠙ Downloading wheels...\n"
        "|████████| 45/45 packages\n"
        "All packages installed!\n"
    )
    result = sanitize_terminal_output(complex_stream)
    assert "\x1b" not in result
    assert "Progress: 10%" not in result
    assert "⠙" not in result
    assert "|████████|" not in result
    assert "Setting up environment..." in result
    assert "All packages installed!" in result


def test_execute_shell_command_success():
    output, is_error = execute_shell_command("python -c \"print('Hello OCCE Noise Gate')\"")
    assert not is_error
    assert "Hello OCCE Noise Gate" in output


def test_execute_shell_command_error():
    output, is_error = execute_shell_command("python -c \"import sys; sys.exit(42)\"")
    assert is_error
