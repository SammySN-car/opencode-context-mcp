"""Unit tests for the targeted file line slicing engine."""

import pytest
from occe.parsers.file_slice import slice_file_lines


def test_slice_file_lines_basic(tmp_path):
    sample = tmp_path / "sample.md"
    sample.write_text("\n".join(f"Line {i}" for i in range(1, 101)), encoding="utf-8")

    out, is_err = slice_file_lines(str(sample), start_line=10, end_line=15)
    assert not is_err
    assert "Line 10" in out
    assert "Line 15" in out
    assert "Line 9" not in out
    assert "Line 16" not in out
    assert "L10-L15 of 100 lines" in out


def test_slice_file_lines_max_lines_limit(tmp_path):
    sample = tmp_path / "sample.json"
    sample.write_text("\n".join(f'{{"row": {i}}}' for i in range(1, 200)), encoding="utf-8")

    out, is_err = slice_file_lines(str(sample), start_line=1, max_lines=20)
    assert not is_err
    assert "L1-L20 of 199 lines" in out
    assert "179 remaining lines omitted" in out


def test_slice_file_lines_file_not_found():
    out, is_err = slice_file_lines("non_existent_file.txt")
    assert is_err
    assert "not found" in out


def test_slice_file_lines_start_exceeds():
    import tempfile
    with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
        f.write("Line 1\nLine 2\n")
        fname = f.name
    out, is_err = slice_file_lines(fname, start_line=50)
    assert is_err
    assert "exceeds total file lines" in out
