"""File I/O helpers. Readers never mutate; writers never decide policy."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def write_atomic(path: Path, text: str) -> None:
    """Write text so a crash cannot leave a truncated file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def read_text(path: Path) -> str:
    """Read a text file with explicit UTF-8 encoding."""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """Overwrite a file atomically."""
    write_atomic(path, text)


def exists(path: Path) -> bool:
    return path.exists()


def validate_image(path: Path) -> None:
    """Raise InputError when the path is not a readable supported image."""
    import importlib

    from ..errors import InputError

    if not path.is_file():
        raise InputError(f"image not found: {path}")
    if path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise InputError(f"unsupported image type {path.suffix!r}: {path}")
    try:
        importlib.import_module("PIL.Image")
    except ImportError as exc:  # pragma: no cover - pillow is a hard dep
        raise InputError("Pillow is required but not installed") from exc
    try:
        from PIL import Image

        with Image.open(path) as im:
            im.verify()
    except Exception as exc:
        raise InputError(f"cannot read image {path}: {exc}") from exc


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


__all__ = [
    "SUPPORTED_IMAGE_SUFFIXES",
    "exists",
    "project_root",
    "read_text",
    "validate_image",
    "write_atomic",
    "write_text",
]
