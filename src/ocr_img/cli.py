"""Entry point - parses args, dispatches commands, returns exit codes."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .commands import extract as extract_cmd
from .commands import serve as serve_cmd
from .config import load_config
from .errors import ToolError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ocr-img",
        description="Extract plain text from images with Tesseract.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log progress to stderr.")
    sub = parser.add_subparsers(dest="command", required=True)
    extract_cmd.add_parser(sub)
    serve_cmd.add_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args)
    try:
        return args.run(args, config)
    except ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
