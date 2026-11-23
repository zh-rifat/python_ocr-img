"""Output layer — every user-facing print in the project lives here.

Three channels, never mixed:

    stdout   — the command's result (text, JSON, nothing else)
    stderr   — progress, warnings, error messages
    exit code — machine-readable outcome (handled by cli.py)
"""

from __future__ import annotations

import json
import sys
from typing import Any


def emit(payload: Any, *, as_json: bool, human: str) -> None:
    """Print exactly one thing to stdout: a JSON document, or a human summary."""
    if as_json:
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return
    print(human)


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def progress(done: int, total: int) -> None:
    print(f"\r{done}/{total}", end="", file=sys.stderr, flush=True)
