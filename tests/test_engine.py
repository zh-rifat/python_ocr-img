"""Engine adapter tests - against the real binary, skipped when absent."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ocr_img.config import Config
from ocr_img.errors import InputError, OcrError
from ocr_img.io import engine as engine_module
from ocr_img.io import files

requires_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not installed"
)


def test_validate_image_rejects_missing(tmp_path: Path):
    with pytest.raises(InputError):
        files.validate_image(tmp_path / "nope.png")


def test_validate_image_rejects_wrong_suffix(tmp_path: Path):
    bad = tmp_path / "x.txt"
    bad.write_text("hi", encoding="utf-8")
    with pytest.raises(InputError):
        files.validate_image(bad)


def test_validate_image_accepts_real_png(sample_image: Path):
    files.validate_image(sample_image)  # must not raise


def test_write_atomic_leaves_no_tmp(sample_image: Path, tmp_path: Path):
    target = tmp_path / "out.txt"
    files.write_atomic(target, "body")
    assert target.read_text(encoding="utf-8") == "body"
    assert not list(tmp_path.glob("*.tmp"))


@requires_tesseract
def test_engine_returns_result(sample_image: Path):
    eng = engine_module.Engine(Config())
    result = eng.extract(sample_image, lang="eng")
    assert isinstance(result.text, str)
    assert result.language == "eng"


@requires_tesseract
def test_engine_rejects_bad_language(sample_image: Path):
    eng = engine_module.Engine(Config())
    with pytest.raises(OcrError):
        eng.extract(sample_image, lang="zzz_not_a_lang")


def test_engine_missing_binary_raises(sample_image: Path):
    eng = engine_module.Engine(Config(tesseract_cmd="/nonexistent/tesseract"))
    with pytest.raises(OcrError):
        eng.extract(sample_image, lang="eng")
