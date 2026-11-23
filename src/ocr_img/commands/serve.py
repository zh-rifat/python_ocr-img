"""The `serve` command: launch a Gradio web UI for OCR over HTTP."""

from __future__ import annotations

import argparse

from ..config import Config
from ..output import warn


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("serve", help="Run the Gradio web UI for OCR.")
    p.add_argument("--host", type=str, default=None, help="Bind host (default 127.0.0.1).")
    p.add_argument("--port", type=int, default=None, help="Bind port (default 7861).")
    p.set_defaults(run=run)
    return p


def run(args: argparse.Namespace, config: Config) -> int:
    from ..ui.app import build_app

    host = args.host or config.host
    port = args.port or config.port

    app = build_app(config)
    warn(f"serving Gradio UI on http://{host}:{port}")
    app.launch(server_name=host, server_port=port, show_error=True)
    return 0


__all__ = ["add_parser", "run"]
