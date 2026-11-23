"""Pure layout reconstruction: tesseract `tsv` in, markdown out.

Same TSV in -> same markdown out. No I/O, no clock, no printing.

The point is a markdown document that *reads* like the page it came from:
wrapped lines join back into single paragraphs, isolated short lines become
headings, and bulleted or numbered lines stay lists instead of being flattened
into a wall of text.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from statistics import median

# Glyphs tesseract emits for a bullet. Deliberately excludes "o" and "0" —
# too easily a real word or a real number.
_BULLET_RE = re.compile(r"^(?:[-•·*–—‣∙»+])\s*")  # noqa: RUF001 - real bullet glyphs
_ORDERED_RE = re.compile(r"^(\d{1,3})[.)]\s*")
_MARKER_PREFIX_RE = re.compile(r"^(?:\d{1,3}[.)]|[-•·*–—‣∙»+])\s")  # noqa: RUF001
_TSV_HEADER_CELL = "level"

# A heading does not end like the start of a sentence continuation.
_SENTENCE_ENDINGS = (".", ",", ";", "…")

# Characters that would otherwise be read as inline markdown syntax.
_INLINE_ESCAPE_RE = re.compile(r"([\\`*_\[\]<>|])")
_LINE_START_ESCAPE_RE = re.compile(r"^([-+#>]|\d{1,3}[.)])")

MAX_HEADING_WORDS = 8
MAX_HEADING_CHARS = 72
# A paragraph this much taller than body type is display type (a heading).
HEADING_HEIGHT_RATIO = 1.3
# Height buckets are ~4 pt wide, so a scale that differs by a pixel still counts
# as the same type size.
HEIGHT_BUCKET = 4
# A line this much taller than body type is display type, even when tesseract
# filed it in the same paragraph as the body text.
TYPE_CHANGE_RATIO = 1.3
MAX_LIST_DEPTH = 3


@dataclass(frozen=True)
class Word:
    """One recognized word with its box, as tesseract reports it."""

    text: str
    page: int
    block: int
    paragraph: int
    line: int
    left: int
    top: int
    width: int
    height: int
    conf: float

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@dataclass(frozen=True)
class Line:
    """The words sharing one tesseract line id, left to right."""

    words: tuple[Word, ...]

    @property
    def key(self) -> tuple[int, int, int]:
        first = self.words[0]
        return (first.page, first.block, first.paragraph)

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words).strip()

    @property
    def left(self) -> int:
        return min(word.left for word in self.words)

    @property
    def right(self) -> int:
        return max(word.right for word in self.words)

    @property
    def top(self) -> int:
        return min(word.top for word in self.words)

    @property
    def bottom(self) -> int:
        return max(word.bottom for word in self.words)

    @property
    def height(self) -> int:
        return max(word.height for word in self.words)


@dataclass(frozen=True)
class Paragraph:
    """The lines sharing one tesseract paragraph id, top to bottom."""

    lines: tuple[Line, ...]

    @property
    def text(self) -> str:
        return _join_lines(self.lines)

    @property
    def height(self) -> int:
        return max(line.height for line in self.lines)

    @property
    def left(self) -> int:
        return min(line.left for line in self.lines)


@dataclass(frozen=True)
class Document:
    """A parsed page plus the metrics the heuristics are relative to."""

    lines: tuple[Line, ...]
    paragraphs: tuple[Paragraph, ...]
    body_height: int
    char_width: float
    left_margin: int


@dataclass(frozen=True)
class MarkdownDoc:
    """The rendered markdown and the counts worth reporting to the user."""

    text: str
    blocks: int
    headings: int
    lists: int
    lines: int


def parse_tsv(tsv: str) -> list[Word]:
    """Parse tesseract `tsv` output into word records; every other row is skipped."""
    rows = [row for row in tsv.splitlines() if row.strip()]
    if rows and rows[0].split("\t", 1)[0].strip() == _TSV_HEADER_CELL:
        rows = rows[1:]

    words: list[Word] = []
    for row in rows:
        cells = row.split("\t")
        if len(cells) < 12:
            continue
        try:
            level = int(cells[0])
        except ValueError:
            continue
        if level != 5:  # 1=page 2=block 3=paragraph 4=line 5=word
            continue
        text = " ".join(cells[11:]).strip()
        if not text:
            continue
        try:
            words.append(
                Word(
                    text=text,
                    page=int(cells[1]),
                    block=int(cells[2]),
                    paragraph=int(cells[3]),
                    line=int(cells[4]),
                    left=int(cells[6]),
                    top=int(cells[7]),
                    width=int(cells[8]),
                    height=int(cells[9]),
                    conf=_confidence(cells[10]),
                )
            )
        except ValueError:
            continue
    return words


def build_document(words: list[Word]) -> Document:
    """Group words into lines and paragraphs, and derive the page metrics.

    `body_height` is the median *word* height, not the median line height: body
    text outnumbers headings word-for-word, so a page with a big title still
    measures body type correctly.
    """
    lines = _build_lines(words)
    body_height = _body_height(words)
    paragraphs = _split_by_type(_group_paragraphs(lines), body_height)
    widths = [word.width / len(word.text) for word in words if len(word.text) >= 2]
    char_width = max(median(widths) if widths else body_height / 2.0, 1.0)
    left_margin = min((line.left for line in lines), default=0)
    return Document(
        lines=tuple(lines),
        paragraphs=tuple(paragraphs),
        body_height=body_height,
        char_width=char_width,
        left_margin=left_margin,
    )


def to_markdown(document: Document) -> MarkdownDoc:
    """Render a parsed page as markdown, one blank line between blocks."""
    blocks: list[str] = []
    headings = 0
    lists = 0
    top_heading: int | None = None

    for paragraph in document.paragraphs:
        text = paragraph.text
        if not text:
            continue

        rendered_list = _render_list(paragraph, document)
        if rendered_list is not None:
            blocks.append(rendered_list)
            lists += 1
            continue

        level, top_heading = _heading_level(paragraph, document, top_heading)
        if level:
            blocks.append("#" * level + " " + _escape(text))
            headings += 1
            continue

        blocks.append(_escape(text))

    body = "\n\n".join(blocks)
    if body:
        body += "\n"
    return MarkdownDoc(
        text=body,
        blocks=len(blocks),
        headings=headings,
        lists=lists,
        lines=len(body.splitlines()) if body else 0,
    )


def markdown_from_tsv(tsv: str) -> MarkdownDoc:
    """Convenience: tesseract `tsv` text straight to a markdown document."""
    return to_markdown(build_document(parse_tsv(tsv)))


def summarize_markdown(document: MarkdownDoc) -> str:
    """Human one-liner for a rendered markdown document."""
    return (
        f"markdown · {document.blocks} blocks · {document.headings} headings · "
        f"{document.lists} lists · {document.lines} lines"
    )


def _confidence(cell: str) -> float:
    try:
        return float(cell)
    except ValueError:
        return -1.0


def _build_lines(words: list[Word]) -> list[Line]:
    grouped: dict[tuple[int, int, int, int], list[Word]] = {}
    for word in words:
        grouped.setdefault((word.page, word.block, word.paragraph, word.line), []).append(word)
    return [
        Line(words=tuple(sorted(grouped[key], key=lambda word: word.left)))
        for key in sorted(grouped)
    ]


def _group_paragraphs(lines: list[Line]) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    bucket: list[Line] = []
    current: tuple[int, int, int] | None = None

    for line in lines:
        if current is not None and line.key != current and bucket:
            paragraphs.append(Paragraph(lines=tuple(bucket)))
            bucket = []
        current = line.key
        bucket.append(line)

    if bucket:
        paragraphs.append(Paragraph(lines=tuple(bucket)))
    return paragraphs


def _split_by_type(paragraphs: list[Paragraph], body_height: int) -> list[Paragraph]:
    """Split paragraphs where the type size changes.

    Tesseract's paragraph ids are geometric, so a title and the body text right
    under it often share one id. Breaking on a type-size change keeps the title
    a heading instead of gluing it to the paragraph below.
    """
    threshold = body_height * TYPE_CHANGE_RATIO
    result: list[Paragraph] = []

    for paragraph in paragraphs:
        bucket: list[Line] = []
        in_display = False
        for line in paragraph.lines:
            display = line.height >= threshold
            if bucket and display != in_display:
                result.append(Paragraph(lines=tuple(bucket)))
                bucket = []
            in_display = display
            bucket.append(line)
        if bucket:
            result.append(Paragraph(lines=tuple(bucket)))

    return result


def _body_height(words: list[Word]) -> int:
    """The page's body type size, as the *modal* word height.

    Body text dominates a page word-for-word, so the most common height bucket
    is body type. A median is the wrong statistic here: it lands between body
    and heading sizes and then misreads both, and the bucket is taken around the
    mode so a font that spans a couple of pixels still measures as one size.
    """
    heights = [word.height for word in words if word.height > 0]
    if not heights:
        return 1
    buckets = Counter(height // HEIGHT_BUCKET for height in heights)
    most_common = buckets.most_common(1)[0][0]
    inside = [height for height in heights if height // HEIGHT_BUCKET == most_common]
    return max(int(median(inside)), 1)


def _is_marker_line(line: Line) -> bool:
    """True when a line opens with a list marker."""
    return bool(_MARKER_PREFIX_RE.match(line.text.strip()))


def _join_lines(lines: tuple[Line, ...]) -> str:
    """Join wrapped lines, undoing hyphenation at the wrap point."""
    joined = ""
    for line in lines:
        piece = line.text.strip()
        if not piece:
            continue
        if not joined:
            joined = piece
        elif joined.endswith("-") and len(joined) > 1 and piece[:1].islower():
            joined = joined[:-1] + piece
        else:
            joined = joined + " " + piece
    return joined


def _heading_level(
    paragraph: Paragraph, document: Document, top_heading: int | None
) -> tuple[int, int | None]:
    """Classify a paragraph as a heading.

    Returns `(level, new_top_heading)`, where level 0 means body text.

    Two signals: the paragraph's type is much larger than body type (display
    type), or it is a lone short line that does not read like a sentence (a
    section title on its own line). Depth is *relative* — the largest heading on
    the page is `#` and any meaningfully smaller one is `##` — because an image
    carries no absolute heading level.
    """
    text = paragraph.text.strip()
    if not text:
        return 0, top_heading

    display = paragraph.height / document.body_height >= HEADING_HEIGHT_RATIO
    lone_short_line = len(paragraph.lines) == 1 and _looks_like_heading(text)
    if not display and not lone_short_line:
        return 0, top_heading

    # Depth is a class comparison, not a ratio: two headings in the same height
    # bucket are the same level, a smaller bucket is a sub-heading. Reusing the
    # body-type bucket keeps one source of tolerance for the whole module.
    bucket = paragraph.height // HEIGHT_BUCKET
    if top_heading is None:
        return 1, bucket
    if bucket >= top_heading:
        return 1, max(bucket, top_heading)
    return 2, top_heading


def _looks_like_heading(text: str) -> bool:
    words = text.split()
    if not words or len(words) > MAX_HEADING_WORDS or len(text) > MAX_HEADING_CHARS:
        return False
    return not text.endswith(_SENTENCE_ENDINGS)


def _render_list(paragraph: Paragraph, document: Document) -> str | None:
    """Render a paragraph as a markdown list, or return None when it is prose."""
    items: list[tuple[int, str, str | None]] = []
    levels = _nesting_levels(paragraph, document)

    for index, line in enumerate(paragraph.lines):
        text = line.text.strip()
        if not text:
            continue
        level = levels[index]
        ordered = _ORDERED_RE.match(text)
        bullet = _BULLET_RE.match(text)
        if ordered:
            items.append((level, text[ordered.end() :].strip(), ordered.group(1)))
        elif bullet:
            items.append((level, text[bullet.end() :].strip(), None))
        elif items:
            level, body, number = items[-1]
            items[-1] = (level, f"{body} {text}".strip(), number)
        else:
            return None

    bodies = [body for _, body, _ in items if body]
    if not items or not bodies:
        return None

    numbered = all(number is not None for _, _, number in items)
    rendered: list[str] = []
    for level, body, number in items:
        if not body:
            continue
        marker = f"{number}." if numbered and number else "-"
        rendered.append("  " * level + marker + " " + _escape(body))
    return "\n".join(rendered)


def _nesting_levels(paragraph: Paragraph, document: Document) -> list[int]:
    """Nesting level per line, from the marker positions in this paragraph.

    Clustering is per-paragraph on purpose. A page-wide frame of reference reads
    two unrelated lists that happen to start a few pixels apart as one nested
    list; inside a single paragraph, distinct marker positions really are nesting
    levels. `char_width` sets the tolerance, so markers a hair apart stay level.
    """
    lefts = [line.left if _is_marker_line(line) else None for line in paragraph.lines]
    present = sorted({left for left in lefts if left is not None})
    tolerance = max(document.char_width, 1.0)

    clusters: list[float] = []
    for left in present:
        if clusters and left - clusters[-1] <= tolerance:
            continue
        clusters.append(left)

    levels: list[int] = []
    for left in lefts:
        if left is None:
            levels.append(levels[-1] if levels else 0)
            continue
        index = max(i for i, edge in enumerate(clusters) if left >= edge - tolerance)
        levels.append(min(index, MAX_LIST_DEPTH))
    return levels


def _escape(text: str) -> str:
    """Neutralize characters markdown would otherwise interpret as syntax."""
    escaped = _INLINE_ESCAPE_RE.sub(r"\\\1", text)
    return _LINE_START_ESCAPE_RE.sub(r"\\\1", escaped)


__all__ = [
    "Document",
    "Line",
    "MarkdownDoc",
    "Paragraph",
    "Word",
    "build_document",
    "markdown_from_tsv",
    "parse_tsv",
    "summarize_markdown",
    "to_markdown",
]
