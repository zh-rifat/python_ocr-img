"""Pure domain logic: no I/O, no clock, no printing.

Two modules, one public surface:

    text.py    — whitespace normalization of raw engine output
    layout.py  — reconstruct lines/paragraphs from word boxes, render markdown
"""

from __future__ import annotations

from .layout import (
    Document,
    Line,
    MarkdownDoc,
    Paragraph,
    Word,
    build_document,
    markdown_from_tsv,
    parse_tsv,
    summarize_markdown,
    to_markdown,
)
from .text import (
    CleanedResult,
    OcrResult,
    clean,
    normalize,
    summarize,
    summarize_cleaned,
)

__all__ = [
    "CleanedResult",
    "Document",
    "Line",
    "MarkdownDoc",
    "OcrResult",
    "Paragraph",
    "Word",
    "build_document",
    "clean",
    "markdown_from_tsv",
    "normalize",
    "parse_tsv",
    "summarize",
    "summarize_cleaned",
    "summarize_markdown",
    "to_markdown",
]
