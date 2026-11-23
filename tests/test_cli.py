"""Command tests through main([...]) - asserts on exit codes and filesystem state."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ocr_img.cli import main


def test_missing_image_returns_guard_code(tmp_path: Path):
    assert main(["extract", str(tmp_path / "nope.png")]) == 3


def test_unsupported_suffix_returns_guard_code(tmp_path: Path):
    bad = tmp_path / "note.txt"
    bad.write_text("hi", encoding="utf-8")
    assert main(["extract", str(bad)]) == 3


def test_corrupt_image_returns_runtime_failure(tmp_path: Path):
    bad = tmp_path / "broken.png"
    bad.write_text("not an image", encoding="utf-8")
    assert main(["extract", str(bad)]) == 1


def test_no_subcommand_is_usage_error():
    # argparse raises SystemExit(2) itself for usage errors - that is the contract,
    # so main() never returns here.
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_missing_required_arg_is_usage_error():
    with pytest.raises(SystemExit) as exc:
        main(["extract"])
    assert exc.value.code == 2


def test_extract_json_is_parseable(sample_image: Path, capsys):
    code = main(["extract", str(sample_image), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["image"] == str(sample_image)
    assert "text" in payload
    assert "cleaned" in payload


def test_json_goes_to_stdout_and_diagnostics_to_stderr(sample_image: Path, capsys):
    main(["extract", str(sample_image), "--json"])
    captured = capsys.readouterr()
    json.loads(captured.out)  # stdout is pure JSON
    assert "warning" not in captured.out


def test_output_file_written(sample_image: Path, tmp_path: Path):
    out = tmp_path / "result.txt"
    assert main(["extract", str(sample_image), "-o", str(out)]) == 0
    assert out.exists()


def test_existing_output_without_overwrite_is_guard(sample_image: Path, tmp_path: Path):
    out = tmp_path / "result.txt"
    out.write_text("previous", encoding="utf-8")
    assert main(["extract", str(sample_image), "-o", str(out)]) == 3


def test_existing_output_with_overwrite_succeeds(sample_image: Path, tmp_path: Path):
    out = tmp_path / "result.txt"
    out.write_text("previous", encoding="utf-8")
    assert main(["extract", str(sample_image), "-o", str(out), "--overwrite"]) == 0


def test_rerun_is_stable(sample_image: Path):
    assert main(["extract", str(sample_image), "--json"]) == 0
    assert main(["extract", str(sample_image), "--json"]) == 0


# --- markdown output -------------------------------------------------------


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_markdown_goes_to_stdout(text_image: Path, capsys):
    assert main(["extract", str(text_image), "--markdown"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("# Chapter One\n")
    assert "paragraphed" not in captured.out  # wrapped lines are joined, not fragmented
    assert "- first item" in captured.out
    assert "warning" not in captured.out


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_markdown_json_is_parseable(text_image: Path, capsys):
    assert main(["extract", str(text_image), "--markdown", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["format"] == "markdown"
    assert set(payload) == {
        "image",
        "format",
        "blocks",
        "headings",
        "lists",
        "lines",
        "markdown",
    }
    assert isinstance(payload["markdown"], str)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_markdown_output_file_written(text_image: Path, tmp_path: Path):
    out = tmp_path / "result.md"
    assert main(["extract", str(text_image), "--markdown", "-o", str(out)]) == 0
    assert out.exists()


def test_markdown_with_raw_is_usage_error(sample_image: Path):
    assert main(["extract", str(sample_image), "--markdown", "--raw"]) == 2


def test_json_with_output_is_usage_error(sample_image: Path, tmp_path: Path):
    """Two output destinations is a usage error; -o must not be silently dropped."""
    out = tmp_path / "ignored.json"
    assert main(["extract", str(sample_image), "--json", "-o", str(out)]) == 2
    assert not out.exists()


def test_markdown_existing_output_without_overwrite_is_guard(sample_image: Path, tmp_path: Path):
    out = tmp_path / "result.md"
    out.write_text("previous", encoding="utf-8")
    assert main(["extract", str(sample_image), "--markdown", "-o", str(out)]) == 3


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_markdown_existing_output_with_overwrite_succeeds(text_image: Path, tmp_path: Path):
    out = tmp_path / "result.md"
    out.write_text("previous", encoding="utf-8")
    assert main(["extract", str(text_image), "--markdown", "-o", str(out), "--overwrite"]) == 0
