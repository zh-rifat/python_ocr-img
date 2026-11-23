"""Shared fixtures: real PNGs on disk, and a fake engine so tests never need tesseract."""

from __future__ import annotations

from pathlib import Path

import pytest

# TrueType fonts ship with most Linux desktops; Pillow's bitmap default is the fallback.
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def load_font(size: int):
    """A real scalable font when the system has one, else Pillow's built-in default."""
    from PIL import ImageFont

    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """A small but real PNG on disk."""
    from PIL import Image

    path = tmp_path / "sample.png"
    Image.new("RGB", (120, 40), "white").save(path)
    return path


@pytest.fixture
def text_image(tmp_path: Path) -> Path:
    """A real PNG with recognizable text, headings and a bulleted list."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    title, body = load_font(40), load_font(24)
    draw.text((30, 20), "Chapter One", fill="black", font=title)
    draw.text((30, 110), "This paragraph wraps onto", fill="black", font=body)
    draw.text((30, 145), "a second line of text.", fill="black", font=body)
    draw.text((30, 200), "- first item", fill="black", font=body)
    draw.text((30, 235), "- second item", fill="black", font=body)

    path = tmp_path / "text.png"
    image.save(path)
    return path


@pytest.fixture
def doc_image(tmp_path: Path) -> Path:
    """A page-shaped PNG: title, one wrapped paragraph, a bullet list, a numbered list.

    Deliberately laid out the way a real page reads, so the end-to-end tests can
    assert that the markdown renderer recovers structure instead of flattening it.
    """
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (1000, 520), "white")
    draw = ImageDraw.Draw(image)
    title, body = load_font(44), load_font(26)
    draw.text((40, 30), "Chapter One", fill="black", font=title)
    draw.text((40, 130), "This paragraph wraps onto", fill="black", font=body)
    draw.text((40, 170), "a second line of text.", fill="black", font=body)
    draw.text((40, 240), "- first item", fill="black", font=body)
    draw.text((40, 280), "- second item", fill="black", font=body)
    draw.text((40, 350), "1. step one", fill="black", font=body)
    draw.text((40, 390), "2. step two", fill="black", font=body)

    path = tmp_path / "doc.png"
    image.save(path)
    return path
