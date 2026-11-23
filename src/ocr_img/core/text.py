"""Pure OCR text normalization.

Same inputs -> same outputs, no I/O, no clock, no printing. This is where the
tests point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Multiple whitespace runs inside a line collapse to a single space; paragraph
# gaps (one or more blank lines) collapse to a single blank line.
_WS_INLINE = re.compile(r"[ \t\u00a0\u2009\u200a\u3000]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


@dataclass(frozen=True)
class OcrResult:
    text: str
    lines: int
    chars: int
    language: str


@dataclass(frozen=True)
class CleanedResult:
    text: str
    lines: int
    chars: int
    words: int
    removed_lines: int


def normalize(text: str) -> str:
    """Collapse internal whitespace and paragraph gaps; strip leading/trailing blanks."""
    text = _WS_INLINE.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip("\n") + ("\n" if text.endswith("\n") else "")


def clean(result: OcrResult) -> CleanedResult:
    """Normalize an OcrResult without any side effects."""
    raw_lines = result.text.splitlines()
    cleaned = normalize(result.text)
    cleaned_lines = cleaned.splitlines()
    return CleanedResult(
        text=cleaned,
        lines=len(cleaned_lines),
        chars=len(cleaned),
        words=len(cleaned.split()),
        removed_lines=len(raw_lines) - len(cleaned_lines),
    )


def summarize(result: OcrResult) -> str:
    """Human one-liner for a raw OCR result."""
    return f"{result.lines} lines · {result.chars} chars · lang={result.language}"


def summarize_cleaned(result: CleanedResult) -> str:
    """Human one-liner for a cleaned result."""
    return (
        f"{result.lines} lines · {result.chars} chars · "
        f"{result.words} words · {result.removed_lines} blank lines removed"
    )


__all__ = [
    "CleanedResult",
    "OcrResult",
    "clean",
    "normalize",
    "summarize",
    "summarize_cleaned",
]
