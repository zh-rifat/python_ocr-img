"""End-to-end tests: real images, the real tesseract binary, the real HTTP surface.

Everything here crosses a process boundary on purpose — these are the tests that
answer "does the tool actually work when a user runs it?", as opposed to the unit
and command tests, which call `main([...])` in-process and stub the engine away.

Covered surfaces:

    CLI     `python -m ocr_img extract IMAGE` — text, --raw, --json, --markdown,
            -o/--overwrite, every documented exit code, env-var precedence
    Web     `python -m ocr_img serve` + the Gradio API — text and markdown modes,
            download artifacts, the language dropdown, the error path

Anything requiring a browser is out of scope here; the Gradio HTTP API is the
contract the UI is built on, so that is what is exercised.

Run only these:   pytest -m e2e
Skip these:       pytest -m "not e2e"
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ocr_img import __version__
from ocr_img.config import available_langs, find_tesseract

SRC = Path(__file__).resolve().parent.parent / "src"
PROJECT_ROOT = SRC.parent

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(find_tesseract() is None, reason="tesseract binary not installed"),
]

# The page the fixtures render, as it must come back out.
TITLE = "Chapter One"
PARAGRAPH = "This paragraph wraps onto a second line of text."
FIRST_BULLET = "- first item"


# --------------------------------------------------------------------------- helpers


def _env(**overrides: str) -> dict[str, str]:
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    for key in list(env):
        if key.startswith("OCR_IMG_"):
            env.pop(key)
    env.update(overrides)
    return env


def run_cli(*args: str, env: dict[str, str] | None = None, timeout: int = 180):
    """Run the CLI in a real subprocess and return the completed process."""
    return subprocess.run(
        [sys.executable, "-m", "ocr_img", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env or _env(),
        cwd=str(PROJECT_ROOT),
    )


def _console_script() -> str | None:
    """The `ocr-img` console script, looked up beside the running interpreter too.

    Tests are usually run as `<env>/bin/python -m pytest`, and that directory is
    not necessarily on PATH, so `which` alone would skip the check for no reason.
    """
    found = shutil.which("ocr-img")
    if found:
        return found
    candidate = Path(sys.executable).parent / "ocr-img"
    return str(candidate) if candidate.is_file() else None


def test_runs_are_deterministic(doc_image: Path):
    """Same image, same flags, same bytes — OCR is the only variable and it is stable."""
    first = run_cli("extract", str(doc_image), "--markdown")
    second = run_cli("extract", str(doc_image), "--markdown")
    assert (first.returncode, first.stdout) == (second.returncode, second.stdout)


# --------------------------------------------------------------------------- CLI: entry surface


def test_version_matches_package():
    result = run_cli("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"ocr-img {__version__}"


def test_help_lists_both_commands():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "extract" in result.stdout
    assert "serve" in result.stdout


def test_extract_help_documents_every_flag():
    result = run_cli("extract", "--help")
    assert result.returncode == 0
    for flag in ("--lang", "--dpi", "-o", "--json", "--raw", "--markdown", "--overwrite"):
        assert flag in result.stdout


def test_console_script_and_module_agree(doc_image: Path):
    """The installed `ocr-img` entry point and `python -m ocr_img` share one code path."""
    script = _console_script()
    if script is None:
        pytest.skip("console script not installed in this environment")

    via_module = run_cli("extract", str(doc_image), "--markdown")
    via_script = subprocess.run(
        [script, "extract", str(doc_image), "--markdown"],
        capture_output=True,
        text=True,
        timeout=180,
        env=_env(),
        cwd=str(PROJECT_ROOT),
    )
    assert via_script.returncode == via_module.returncode
    assert via_script.stdout == via_module.stdout


# --------------------------------------------------------------------------- CLI: plain text


def test_text_mode_prints_the_page(doc_image: Path):
    result = run_cli("extract", str(doc_image))
    assert result.returncode == 0
    assert TITLE in result.stdout
    assert "This paragraph wraps onto" in result.stdout
    assert "a second line of text." in result.stdout
    assert FIRST_BULLET in result.stdout
    # No wrapped-line joining in plain text — that is the markdown renderer's job.
    assert PARAGRAPH not in result.stdout
    assert result.stderr == ""


def test_raw_mode_matches_the_engine_output(doc_image: Path):
    """`--raw` is the uncleaned engine text: still the page, minus normalization."""
    result = run_cli("extract", str(doc_image), "--raw")
    assert result.returncode == 0
    assert TITLE in result.stdout
    assert result.stdout.endswith("\n")


def test_blank_image_is_empty_success(tmp_path: Path):
    """No text is not an error for a pipe: empty stdout, exit 0, in both modes."""
    from PIL import Image

    blank = tmp_path / "blank.png"
    Image.new("RGB", (80, 30), "white").save(blank)

    for flags in ((), ("--markdown",)):
        result = run_cli("extract", str(blank), *flags)
        assert result.returncode == 0
        assert result.stdout == ""


@pytest.mark.parametrize(
    ("suffix", "pillow_format"),
    [
        (".png", "PNG"),
        (".jpg", "JPEG"),
        (".jpeg", "JPEG"),
        (".bmp", "BMP"),
        (".tif", "TIFF"),
        (".tiff", "TIFF"),
        (".webp", "WEBP"),
    ],
)
def test_every_advertised_image_format(
    doc_image: Path, tmp_path: Path, suffix: str, pillow_format: str
):
    """The suffix allow-list in `io/files.py` and the README are not lying."""
    from PIL import Image

    converted = tmp_path / f"page{suffix}"
    with Image.open(doc_image) as image:
        image.save(converted, pillow_format)

    result = run_cli("extract", str(converted), "--markdown")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(f"# {TITLE}")


# --------------------------------------------------------------------------- CLI: JSON


def test_json_document_schema(doc_image: Path):
    result = run_cli("extract", str(doc_image), "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)  # stdout is pure JSON, nothing else
    assert payload["image"] == str(doc_image)
    assert payload["language"] == "eng"
    assert payload["lines"] >= 1
    assert payload["chars"] == len(payload["text"])
    assert TITLE in payload["text"]
    cleaned = payload["cleaned"]
    assert {"text", "lines", "chars", "words", "removed_lines"} == set(cleaned)
    assert cleaned["words"] > 0


def test_markdown_json_document_schema(doc_image: Path):
    result = run_cli("extract", str(doc_image), "--markdown", "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["format"] == "markdown"
    assert payload["image"] == str(doc_image)
    assert payload["headings"] >= 1
    assert payload["lists"] >= 2
    assert payload["blocks"] == len(payload["markdown"].strip().split("\n\n"))
    assert payload["markdown"].startswith(f"# {TITLE}")


def test_json_leaves_stdout_clean(doc_image: Path):
    result = run_cli("extract", str(doc_image), "--json")
    assert result.returncode == 0
    json.loads(result.stdout)
    assert "warning" not in result.stdout
    assert result.stderr == ""


# --------------------------------------------------------------------------- CLI: markdown


def test_markdown_reconstructs_the_page(doc_image: Path):
    result = run_cli("extract", str(doc_image), "--markdown")
    assert result.returncode == 0
    lines = result.stdout.splitlines()

    # Display type becomes a top-level heading.
    assert lines[0] == f"# {TITLE}"
    # Wrapped lines rejoin into one paragraph instead of staying fragmented.
    assert PARAGRAPH in result.stdout
    # Bullets and numbers survive as markdown lists, numbers preserved.
    assert "- first item" in lines
    assert "- second item" in lines
    assert "1. step one" in lines
    assert "2. step two" in lines
    # Blocks are separated by exactly one blank line.
    assert result.stdout.endswith("\n")
    assert "\n\n\n" not in result.stdout


def test_markdown_is_a_single_pass_from_one_ocr_run(doc_image: Path):
    """The renderer sees the same page the text path sees — no second pipeline."""
    text = run_cli("extract", str(doc_image))
    markdown = run_cli("extract", str(doc_image), "--markdown")
    assert text.returncode == markdown.returncode == 0
    for word in (TITLE, "first item", "step two"):
        assert word in text.stdout
        assert word in markdown.stdout


# --------------------------------------------------------------------------- CLI: -o / --overwrite


def test_text_output_file(doc_image: Path, tmp_path: Path):
    out = tmp_path / "page.txt"
    result = run_cli("extract", str(doc_image), "-o", str(out))
    assert result.returncode == 0
    assert out.read_text(encoding="utf-8") == run_cli("extract", str(doc_image)).stdout
    # Summary on stdout, the written path on stderr.
    assert "lines" in result.stdout
    assert f"warning: wrote {out}" in result.stderr


def test_markdown_output_file(doc_image: Path, tmp_path: Path):
    out = tmp_path / "page.md"
    result = run_cli("extract", str(doc_image), "--markdown", "-o", str(out))
    assert result.returncode == 0
    assert out.read_text(encoding="utf-8").startswith(f"# {TITLE}")
    assert "markdown" in result.stdout
    assert f"warning: wrote {out}" in result.stderr


def test_output_file_guard_and_overwrite(doc_image: Path, tmp_path: Path):
    out = tmp_path / "page.md"
    out.write_text("previous", encoding="utf-8")

    refused = run_cli("extract", str(doc_image), "--markdown", "-o", str(out))
    assert refused.returncode == 3
    assert "already exists" not in refused.stdout
    assert out.read_text(encoding="utf-8") == "previous"

    replaced = run_cli("extract", str(doc_image), "--markdown", "-o", str(out), "--overwrite")
    assert replaced.returncode == 0
    assert out.read_text(encoding="utf-8").startswith(f"# {TITLE}")


# --------------------------------------------------------------------------- CLI: exit codes


def test_missing_image_is_guard(tmp_path: Path):
    result = run_cli("extract", str(tmp_path / "nope.png"))
    assert result.returncode == 3
    assert result.stdout == ""
    assert "image not found" in result.stderr


def test_unsupported_suffix_is_guard(tmp_path: Path):
    bad = tmp_path / "note.txt"
    bad.write_text("hi", encoding="utf-8")
    assert run_cli("extract", str(bad)).returncode == 3


def test_directory_is_guard(tmp_path: Path):
    result = run_cli("extract", str(tmp_path))
    assert result.returncode == 3
    assert result.stdout == ""


def test_corrupt_image_is_runtime_failure(tmp_path: Path):
    bad = tmp_path / "broken.png"
    bad.write_text("not an image", encoding="utf-8")
    result = run_cli("extract", str(bad))
    assert result.returncode == 1
    assert "error:" in result.stderr


def test_unknown_language_is_runtime_failure(doc_image: Path):
    result = run_cli("extract", str(doc_image), "--lang", "zzz_not_a_lang")
    assert result.returncode == 1
    assert "tesseract failed" in result.stderr


def test_bad_dpi_is_usage_error(doc_image: Path):
    assert run_cli("extract", str(doc_image), "--dpi", "abc").returncode == 2


def test_unknown_flag_is_usage_error(doc_image: Path):
    assert run_cli("extract", str(doc_image), "--nope").returncode == 2


def test_missing_subcommand_is_usage_error():
    assert run_cli().returncode == 2


def test_markdown_with_raw_is_usage_error(doc_image: Path):
    result = run_cli("extract", str(doc_image), "--markdown", "--raw")
    assert result.returncode == 2
    assert "--markdown" in result.stderr and "--raw" in result.stderr
    assert result.stdout == ""


def test_json_with_output_is_usage_error(doc_image: Path, tmp_path: Path):
    """Two output destinations is a usage error, not a silently dropped -o."""
    out = tmp_path / "ignored.json"
    result = run_cli("extract", str(doc_image), "--json", "-o", str(out))
    assert result.returncode == 2
    assert "--json" in result.stderr and "--output" in result.stderr
    assert result.stdout == ""
    assert not out.exists()


# --------------------------------------------------------------------------- CLI: config


def test_env_language_is_overridden_by_the_flag(doc_image: Path):
    broken_env = _env(OCR_IMG_LANG="zzz_not_a_lang")
    assert run_cli("extract", str(doc_image), env=broken_env).returncode == 1

    overridden = run_cli("extract", str(doc_image), "--lang", "eng", env=broken_env)
    assert overridden.returncode == 0
    assert TITLE in overridden.stdout


def test_env_dpi_is_honoured(doc_image: Path):
    result = run_cli("extract", str(doc_image), "--markdown", env=_env(OCR_IMG_DPI="150"))
    assert result.returncode == 0
    assert result.stdout.startswith(f"# {TITLE}")


def test_multi_language_flag(doc_image: Path):
    installed = set(available_langs())
    if "ben" not in installed:
        pytest.skip("bengali language data not installed")
    result = run_cli("extract", str(doc_image), "--lang", "eng+ben")
    assert result.returncode == 0
    assert TITLE in result.stdout


# --------------------------------------------------------------------------- Web UI: fixture


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get_json(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_for_server(url: str, proc: subprocess.Popen, log: Path, deadline: float = 120.0) -> None:
    """Poll /config until the app answers, or fail with whatever the server said."""
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise AssertionError(f"serve exited early ({proc.returncode}):\n{log.read_text()}")
        try:
            _get_json(f"{url}/config")
            return
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            time.sleep(0.5)
    raise AssertionError(
        f"serve did not answer on {url} within {deadline:.0f}s:\n{log.read_text()}"
    )


@pytest.fixture(scope="module")
def serve(tmp_path_factory: pytest.TempPathFactory):
    """A real `ocr-img serve` process, plus a gradio_client pointed at it."""
    gradio_client = pytest.importorskip("gradio_client")

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    log = tmp_path_factory.mktemp("serve") / "serve.log"

    with log.open("w", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            [sys.executable, "-m", "ocr_img", "serve", "--port", str(port)],
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=_env(),
            cwd=str(PROJECT_ROOT),
        )
        try:
            _wait_for_server(url, proc, log)
            yield {
                "url": url,
                "client": gradio_client.Client(url, verbose=False),
                "handle_file": gradio_client.handle_file,
                "config": _get_json(f"{url}/config"),
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:  # pragma: no cover - stubborn shutdown
                proc.kill()
                proc.wait(timeout=10)


# --------------------------------------------------------------------------- Web UI: surface


def test_ui_component_surface(serve):
    """The controls the README promises are actually on the page."""
    components = serve["config"]["components"]
    by_type: dict[str, list[dict]] = {}
    for component in components:
        by_type.setdefault(component["type"], []).append(component["props"])

    image = by_type["image"][0]
    assert image["label"] == "Image"

    dropdown = by_type["dropdown"][0]
    codes = [code for _, code in dropdown["choices"]]
    assert dropdown["label"] == "Language"
    assert dropdown["value"] == "eng"
    assert set(codes) <= set(available_langs())

    checkbox = by_type["checkbox"][0]
    assert checkbox["label"] == "Markdown output"
    assert checkbox["value"] is False

    textbox = by_type["textbox"][0]
    assert textbox["label"] == "Recognized text"
    assert textbox["interactive"] is False

    download = by_type["downloadbutton"][0]
    assert download["visible"] is False


def test_ui_endpoint_inventory(serve):
    endpoints = _get_json(f"{serve['url']}/gradio_api/info")["named_endpoints"]
    assert "/ocr" in endpoints
    params = [param["parameter_name"] for param in endpoints["/ocr"]["parameters"]]
    assert params == ["image_path", "lang_code", "as_markdown"]
    returns = [ret["component"].lower() for ret in endpoints["/ocr"]["returns"]]
    assert returns == ["textbox", "downloadbutton"]


# --------------------------------------------------------------------------- Web UI: OCR


def test_ui_text_mode_and_download(serve, doc_image: Path):
    text, download = serve["client"].predict(
        serve["handle_file"](str(doc_image)), "eng", False, api_name="/ocr"
    )

    assert TITLE in text
    assert FIRST_BULLET in text
    assert PARAGRAPH not in text  # plain text keeps the wrapped lines

    assert download["label"] == "Download text"
    assert download["visible"] is True
    artifact = Path(download["value"])
    assert artifact.suffix == ".txt"
    assert artifact.read_text(encoding="utf-8") == text


def test_ui_markdown_mode_and_download(serve, doc_image: Path):
    markdown, download = serve["client"].predict(
        serve["handle_file"](str(doc_image)), "eng", True, api_name="/ocr"
    )

    assert markdown.startswith(f"# {TITLE}")
    assert PARAGRAPH in markdown
    assert "1. step one" in markdown

    assert download["label"] == "Download markdown"
    assert download["visible"] is True
    artifact = Path(download["value"])
    assert artifact.suffix == ".md"
    assert artifact.read_text(encoding="utf-8") == markdown


def test_ui_cli_and_web_agree(serve, doc_image: Path):
    """Both surfaces run the same Engine and the same renderer, so they must match."""
    cli_text = run_cli("extract", str(doc_image)).stdout
    cli_markdown = run_cli("extract", str(doc_image), "--markdown").stdout

    ui_text, _ = serve["client"].predict(
        serve["handle_file"](str(doc_image)), "eng", False, api_name="/ocr"
    )
    ui_markdown, _ = serve["client"].predict(
        serve["handle_file"](str(doc_image)), "eng", True, api_name="/ocr"
    )

    assert ui_text == cli_text
    assert ui_markdown == cli_markdown


def test_ui_download_url_is_served(serve, doc_image: Path):
    """The file behind the download button is actually reachable over HTTP."""
    _, download = serve["client"].predict(
        serve["handle_file"](str(doc_image)), "eng", True, api_name="/ocr"
    )
    # gradio_client hands back a cache path; the browser gets the /gradio_api/file= URL.
    file_url = f"{serve['url']}/gradio_api/file={download['value']}"
    with urllib.request.urlopen(file_url, timeout=10) as response:
        assert response.status == 200
        body = response.read().decode("utf-8")
    assert body.startswith(f"# {TITLE}")


def test_ui_missing_image_is_a_visible_error(serve):
    gradio_client = pytest.importorskip("gradio_client")
    with pytest.raises(gradio_client.exceptions.AppError) as exc:
        serve["client"].predict(None, "eng", False, api_name="/ocr")
    assert "upload an image first" in str(exc.value)
