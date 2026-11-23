"""Gradio web application for OCR."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import gradio as gr

from ..config import SUPPORTED_LANGS, Config, available_langs
from ..core import clean, markdown_from_tsv
from ..errors import GuardError
from ..io import engine as engine_module
from ..io import files


def _language_choices() -> list[tuple[str, str]]:
    """(label, code) pairs this project offers, filtered to what tesseract has."""
    installed = set(available_langs())
    choices = [(label, code) for code, label in SUPPORTED_LANGS if code in installed]
    # Fall back to English so the UI still builds when the engine is missing.
    return choices or [("English", "eng")]


def build_app(config: Config) -> gr.Blocks:
    """Build the Blocks app so `serve` can launch it and tests can inspect it."""
    choices = _language_choices()
    default_lang = "eng" if any(code == "eng" for _, code in choices) else choices[0][1]

    with gr.Blocks(title="ocr-img") as demo:
        gr.Markdown("# ocr-img")
        gr.Markdown("Upload an image, choose a language, then extract its text.")

        with gr.Row():
            with gr.Column(scale=1):
                image = gr.Image(type="filepath", label="Image")
                lang = gr.Dropdown(choices=choices, value=default_lang, label="Language")
                markdown_mode = gr.Checkbox(
                    label="Markdown output",
                    value=False,
                    info="Rebuild the page layout: paragraphs, headings, and lists.",
                )
                with gr.Row():
                    run_btn = gr.Button("Extract text", variant="primary")
                    clear_btn = gr.Button("Clear")
            with gr.Column(scale=1):
                text_out = gr.Textbox(
                    label="Recognized text",
                    lines=14,
                    interactive=False,
                    buttons=["copy"],
                )
                download = gr.DownloadButton(label="Download text", visible=False)

        def ocr(image_path: str | None, lang_code: str, as_markdown: bool):
            if not image_path:
                raise GuardError("upload an image first")
            path = Path(image_path)
            files.validate_image(path)

            eng = engine_module.Engine(config)

            if as_markdown:
                tsv = eng.extract_tsv(path, lang=lang_code)
                document = markdown_from_tsv(tsv)
                if not document.text.strip():
                    raise GuardError("no text recognized in the uploaded image")
                body, suffix, label = document.text, ".md", "Download markdown"
            else:
                cleaned = clean(eng.extract(path, lang=lang_code))
                body, suffix, label = cleaned.text, ".txt", "Download text"

            # DownloadButton needs a file, so persist the body to a temp file.
            fd, tmp_name = tempfile.mkstemp(suffix=suffix, text=True)
            os.close(fd)
            tmp = Path(tmp_name)
            files.write_text(tmp, body)

            return body, gr.DownloadButton(label=label, value=str(tmp), visible=True)

        def reset():
            return None, ""

        run_btn.click(
            fn=ocr,
            inputs=[image, lang, markdown_mode],
            outputs=[text_out, download],
            show_progress="full",
        )
        clear_btn.click(fn=reset, inputs=[], outputs=[image, text_out], show_progress="hidden")

    return demo


__all__ = ["build_app"]
