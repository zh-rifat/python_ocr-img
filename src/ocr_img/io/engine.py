"""OCR engine adapter — the one module that talks to Tesseract."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import Config
from ..core import OcrResult
from ..errors import OcrError
from ..io import files

# Second positional arg to tesseract: the output config ("stdout" writes the
# recognized text to stdout). The trailing token selects the renderer.
_TSV_CONFIG = "tsv"


class Engine:
    """Thin wrapper around the tesseract binary via stdin/stdout."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._cmd = config.tesseract_cmd or "tesseract"

    def available(self) -> bool:
        import shutil

        return bool(shutil.which(self._cmd)) if self._cmd == "tesseract" else self._cmd is not None

    def extract(self, path: Path, lang: str | None = None, dpi: int | None = None) -> OcrResult:
        """Run tesseract on `path` and return the recognized text as a pure result."""
        text = self._run(path, lang=lang, dpi=dpi, renderer=None)
        lines = len(text.splitlines())
        return OcrResult(text=text, lines=lines, chars=len(text), language=lang or self.config.lang)

    def extract_tsv(self, path: Path, lang: str | None = None, dpi: int | None = None) -> str:
        """Run tesseract on `path` and return its TSV word boxes verbatim."""
        return self._run(path, lang=lang, dpi=dpi, renderer=_TSV_CONFIG)

    def _run(self, path: Path, *, lang: str | None, dpi: int | None, renderer: str | None) -> str:
        """Invoke tesseract once and return its stdout, or raise a typed error."""
        files.validate_image(path)

        if self._cmd is None:
            raise OcrError("tesseract binary not found; install tesseract-ocr")

        lang = lang or self.config.lang
        dpi = dpi or self.config.dpi

        cmd = [self._cmd, str(path), "stdout", "-l", lang, "--dpi", str(dpi)]
        if renderer:
            cmd.append(renderer)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except FileNotFoundError as exc:
            raise OcrError(f"tesseract binary not found: {self._cmd}") from exc
        except subprocess.SubprocessError as exc:
            raise OcrError(f"tesseract invocation failed: {exc}") from exc

        if proc.returncode != 0:
            detail = (proc.stderr or "").strip() or proc.stdout or ""
            raise OcrError(f"tesseract failed (exit {proc.returncode}): {detail}")

        return proc.stdout or ""
