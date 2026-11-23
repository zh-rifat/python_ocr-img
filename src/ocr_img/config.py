"""Configuration resolution. The only module that reads os.environ.

Resolution order, applied once: CLI flag -> environment variable -> default.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

ENV_PREFIX = "OCR_IMG_"

# Documents scanned below this lose small glyphs; above it the engine slows
# down with no accuracy gain.
DEFAULT_DPI = 300
DEFAULT_LANG = "eng"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7861

# Languages offered in the web UI and accepted by --lang. Ordered by likely use.
SUPPORTED_LANGS: tuple[tuple[str, str], ...] = (
    ("eng", "English"),
    ("ben", "Bengali"),
    ("ara", "Arabic"),
    ("hin", "Hindi"),
    ("chi_sim", "Chinese (Simplified)"),
    ("jpn", "Japanese"),
    ("kor", "Korean"),
    ("rus", "Russian"),
    ("spa", "Spanish"),
    ("fra", "French"),
    ("deu", "German"),
)


@dataclass(frozen=True)
class Config:
    """Resolved settings, passed down explicitly. Never re-read from the source."""

    lang: str = DEFAULT_LANG
    dpi: int = DEFAULT_DPI
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    verbose: bool = False
    tesseract_cmd: str | None = None


def _env(name: str) -> str | None:
    """Read one prefixed environment variable, or None when unset or empty."""
    value = os.environ.get(f"{ENV_PREFIX}{name}", "").strip()
    return value or None


def find_tesseract() -> str | None:
    """Absolute path to the tesseract binary, or None when it is not installed."""
    override = _env("TESSERACT_CMD")
    if override:
        return override
    import shutil

    return shutil.which("tesseract")


def load_config(args: object | None = None) -> Config:
    """Resolve configuration: CLI flag -> env var -> default.

    `args` is an argparse.Namespace; any missing attribute falls through to the
    environment and then the default, so the web UI can call this with None.
    """

    def pick(field: str, env_name: str, default):
        value = getattr(args, field, None) if args is not None else None
        if value is not None and value != "":
            return value
        env_value = _env(env_name)
        if env_value is not None:
            return env_value
        return default

    return Config(
        lang=str(pick("lang", "LANG", DEFAULT_LANG)),
        dpi=int(pick("dpi", "DPI", DEFAULT_DPI)),
        host=str(pick("host", "HOST", DEFAULT_HOST)),
        port=int(pick("port", "PORT", DEFAULT_PORT)),
        verbose=bool(getattr(args, "verbose", False) if args is not None else False),
        tesseract_cmd=find_tesseract(),
    )


def available_langs() -> list[str]:
    """Language codes the engine actually has installed, or [] when unavailable."""
    cmd = find_tesseract()
    if not cmd:
        return []
    try:
        proc = subprocess.run(
            [cmd, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    lines = (proc.stdout or "").splitlines()
    # First line is the header ("List of available languages ...").
    return [line.strip() for line in lines[1:] if line.strip()]


def project_root() -> Path:
    """The repository root, derived from this file's location."""
    return Path(__file__).resolve().parent.parent.parent


__all__ = [
    "DEFAULT_DPI",
    "DEFAULT_HOST",
    "DEFAULT_LANG",
    "DEFAULT_PORT",
    "ENV_PREFIX",
    "SUPPORTED_LANGS",
    "Config",
    "available_langs",
    "find_tesseract",
    "load_config",
    "project_root",
]
