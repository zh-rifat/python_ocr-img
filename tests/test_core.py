"""Pure logic tests - no filesystem, no engine."""

from __future__ import annotations

from ocr_img.core import OcrResult, clean, normalize, summarize, summarize_cleaned


def test_normalize_collapses_inline_whitespace():
    assert normalize("a   b\t\tc") == "a b c"


def test_normalize_collapses_paragraph_gaps():
    assert normalize("a\n\n\n\n\nb") == "a\n\nb"


def test_normalize_strips_leading_blank_lines():
    assert normalize("\n\n\ntext\n") == "text\n"


def test_normalize_is_idempotent():
    once = normalize("a  b\n\n\n\nc")
    assert normalize(once) == once


def test_normalize_handles_empty_input():
    assert normalize("") == ""


def test_clean_counts():
    # raw splitlines() -> ["a  b", "", "", "", "", "c"] = 6 lines
    # cleaned          -> ["a b", "", "c"]               = 3 lines
    raw = OcrResult(text="a  b\n\n\n\n\nc", lines=6, chars=0, language="eng")
    out = clean(raw)
    assert out.text == "a b\n\nc"
    assert out.lines == 3
    assert out.words == 3
    assert out.removed_lines == 3


def test_clean_reports_removed_blank_lines():
    raw = OcrResult(text="x\n\n\n\n\ny", lines=5, chars=0, language="eng")
    assert clean(raw).removed_lines > 0


def test_summaries_are_strings():
    raw = OcrResult(text="x", lines=1, chars=1, language="eng")
    assert "lang=eng" in summarize(raw)
    assert "words" in summarize_cleaned(clean(raw))
