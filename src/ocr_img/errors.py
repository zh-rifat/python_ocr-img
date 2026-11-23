"""Typed exception hierarchy. The only place exit codes are defined.

Exit-code contract (mirrors .ai-agent/architecture.md):

    0    success
    1    runtime failure / invariant drift
    2    usage error (argument shape) - argparse raises most of these itself
    3    guard refused - a precondition about the world said no
    130  interrupted
"""

from __future__ import annotations


class ToolError(Exception):
    """Base for every expected failure. Carries the process exit code."""

    exit_code: int = 1


class UsageError(ToolError):
    """Argument-shape failure the parser could not catch itself.

    Example: --json and --output together, when both cannot be honoured.
    Preconditions about the world are GuardError, not UsageError.
    """

    exit_code = 2


class GuardError(ToolError):
    """A precondition or safety check refused to proceed.

    Examples: input image missing, unsupported file type, target file exists
    and --overwrite was not passed.
    """

    exit_code = 3


class InputError(ToolError):
    """The input was unreadable, not an image, or malformed."""

    exit_code = 1


class OcrError(ToolError):
    """The OCR engine failed, or is not installed or configured."""

    exit_code = 1


__all__ = [
    "GuardError",
    "InputError",
    "OcrError",
    "ToolError",
    "UsageError",
]
