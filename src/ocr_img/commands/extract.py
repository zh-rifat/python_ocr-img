"""The `extract` command: read an image, OCR it, print/return text or markdown."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..config import Config
from ..core import (
    clean,
    markdown_from_tsv,
    summarize,
    summarize_cleaned,
    summarize_markdown,
)
from ..errors import GuardError, UsageError
from ..io import engine as engine_module
from ..io import files
from ..output import emit, warn


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("extract", help="OCR an image and print the recognized text.")
    p.add_argument("image", type=str, help="Path to an image file.")
    p.add_argument("--lang", type=str, default=None, help="OCR language code (default eng).")
    p.add_argument(
        "--dpi", type=int, default=None, help="Rendering DPI passed to tesseract (default 300)."
    )
    p.add_argument(
        "-o", "--output", type=str, default=None, help="Write text to this file instead of stdout."
    )
    p.add_argument("--json", action="store_true", help="Emit one JSON document to stdout.")
    p.add_argument(
        "--raw", action="store_true", help="Skip text cleaning; print raw engine output."
    )
    p.add_argument(
        "--markdown",
        action="store_true",
        help="Rebuild the page layout as markdown (paragraphs, headings, lists).",
    )
    p.add_argument(
        "--overwrite", action="store_true", help="Allow overwriting an existing --output file."
    )
    p.set_defaults(run=run)
    return p


def run(args: argparse.Namespace, config: Config) -> int:
    image = Path(args.image)

    # Preconditions the parser cannot express — fail before any work.
    if not image.exists():
        raise GuardError(f"image not found: {image}")
    if image.suffix.lower() not in files.SUPPORTED_IMAGE_SUFFIXES:
        raise GuardError(f"unsupported image type {image.suffix!r}: {image}")
    if args.markdown and args.raw:
        raise UsageError("--markdown and --raw cannot be combined")
    if args.json and args.output:
        # stdout is the JSON channel; -o would be silently ignored otherwise.
        raise UsageError("--json and --output cannot be combined")

    eng = engine_module.Engine(config)

    if args.markdown:
        return _run_markdown(args, eng, image)

    result = eng.extract(image, lang=args.lang, dpi=args.dpi)
    cleaned = clean(result) if not args.raw else None

    if args.json:
        payload = {
            "image": str(image),
            "language": result.language,
            "lines": result.lines,
            "chars": result.chars,
            "text": result.text,
        }
        if cleaned is not None:
            payload["cleaned"] = {
                "text": cleaned.text,
                "lines": cleaned.lines,
                "chars": cleaned.chars,
                "words": cleaned.words,
                "removed_lines": cleaned.removed_lines,
            }
        emit(payload, as_json=True, human="")
        return 0

    human = summarize_cleaned(cleaned) if cleaned is not None else summarize(result)

    if args.output:
        out = Path(args.output)
        if out.exists() and not args.overwrite:
            raise GuardError(f"output file exists (use --overwrite to replace): {out}")
        text = cleaned.text if cleaned is not None else result.text
        files.write_text(out, text)
        warn(f"wrote {out}")
        print(human)
        return 0

    print(cleaned.text if cleaned is not None else result.text, end="")
    return 0


def _run_markdown(args: argparse.Namespace, eng: engine_module.Engine, image: Path) -> int:
    """The `--markdown` branch: TSV in, reconstructed markdown out."""
    tsv = eng.extract_tsv(image, lang=args.lang, dpi=args.dpi)
    document = markdown_from_tsv(tsv)

    if args.json:
        emit(
            {
                "image": str(image),
                "format": "markdown",
                "blocks": document.blocks,
                "headings": document.headings,
                "lists": document.lists,
                "lines": document.lines,
                "markdown": document.text,
            },
            as_json=True,
            human="",
        )
        return 0

    if args.output:
        out = Path(args.output)
        if out.exists() and not args.overwrite:
            raise GuardError(f"output file exists (use --overwrite to replace): {out}")
        files.write_text(out, document.text)
        warn(f"wrote {out}")
        print(summarize_markdown(document))
        return 0

    print(document.text, end="")
    return 0
