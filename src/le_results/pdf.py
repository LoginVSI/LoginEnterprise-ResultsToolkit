"""Optional reproducible PDF of an already built HTML report.

The page content, arithmetic and provenance labels come from the existing HTML report; this
module only prints it with a user-local Chromium-family browser (Edge, Chrome or Chromium) and
verifies the result. It needs no pip dependency and no administrator rights. This is distinct from
`download-pdf`, which retrieves an existing native Application PDF.
"""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import zlib
from datetime import UTC, datetime
from html import escape as html_escape
from html import unescape
from pathlib import Path
from typing import Any

from .errors import ToolkitError
from .evidence import write_json

BROWSER_ENV = "LE_RESULTS_BROWSER"
PATH_NAMES = (
    "msedge",
    "chrome",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
)
KNOWN_LOCATIONS = (
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
PRINT_CSS = (
    "<style>@page{size:A4 landscape;margin:8mm}"
    "html{zoom:.72}body{background:#fff}"
    "html,body{-webkit-print-color-adjust:exact;print-color-adjust:exact}"
    "tr,svg,figure,.card,.panel,.warning,h2{break-inside:avoid}h2{break-after:avoid}"
    "thead{display:table-header-group}details{break-before:page;overflow:visible}"
    "table{width:100%;table-layout:auto}td,th{overflow-wrap:break-word}summary{list-style:none}"
    "</style>"
)
MAX_HTML_BYTES = 32 * 1024 * 1024
MIN_CONTENT_BYTES = 1500


def find_browser(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    explicit = env.get(BROWSER_ENV)
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ToolkitError(
                f"{BROWSER_ENV} does not point to a file. Set it to a user-local msedge, chrome or chromium executable.",
                code="pdf_renderer_missing",
            )
        return path
    for name in PATH_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    for template in KNOWN_LOCATIONS:
        candidate = Path(os.path.expandvars(template))
        if candidate.is_file():
            return candidate
    raise ToolkitError(
        "No Chromium-family browser found for PDF printing. Use the HTML report as is, or install "
        "Microsoft Edge or Google Chrome for your user, or unzip a portable Chromium into a folder "
        f"you own and set {BROWSER_ENV} to its executable. No administrator rights or pip packages are needed.",
        code="pdf_renderer_missing",
    )


def _streams(data: bytes) -> list[bytes]:
    out = []
    for match in re.finditer(rb"stream\r?\n", data):
        end = data.find(b"endstream", match.end())
        if end < 0:
            continue
        chunk = data[match.end() : end]
        try:
            out.append(zlib.decompress(chunk))
        except zlib.error:
            out.append(chunk)
    return out


def inspect_pdf(path: Path, forbidden: list[str], expected_text: list[str]) -> dict[str, Any]:
    """Structural verification plus optional text markers; failure is explicit, never silent."""
    data = path.read_bytes()
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
        raise ToolkitError("Rendered file is not a complete PDF.", code="pdf_invalid")
    pages = len(re.findall(rb"/Type\s*/Page(?![s\w])", data))
    if pages < 1:
        raise ToolkitError("Rendered PDF has no countable pages.", code="pdf_invalid")
    streams = _streams(data)
    if sum(len(s) for s in streams) < MIN_CONTENT_BYTES:
        raise ToolkitError("Rendered PDF appears blank.", code="pdf_blank")
    haystack = data + b"\n".join(streams)
    for item in forbidden:
        if item and item.encode("utf-8", "ignore") in haystack:
            raise ToolkitError(
                "Rendered PDF contains a local path or private marker; output discarded.",
                code="pdf_leak",
            )
    verification = "structural"
    text_checked: list[str] = []
    if expected_text or forbidden:
        reader_class = _pdf_reader()
        if reader_class is None:
            reader = None
        else:
            try:
                reader = reader_class(str(path))
                parsed_pages = len(reader.pages)
                text = " ".join(page.extract_text() or "" for page in reader.pages)
            except Exception:  # noqa: BLE001 - any parser failure means the PDF is unusable
                raise ToolkitError(
                    "Rendered PDF could not be parsed; output discarded.", code="pdf_invalid"
                ) from None
        if reader is not None:
            if parsed_pages != pages:
                raise ToolkitError("PDF page count is inconsistent.", code="pdf_invalid")
            squashed = _norm(text)
            if any(_norm(item) and _norm(item) in squashed for item in forbidden if len(item) > 6):
                raise ToolkitError(
                    "Rendered PDF text contains a local path or private marker; output discarded.",
                    code="pdf_leak",
                )
            missing = [m for m in expected_text if _norm(m) not in squashed]
            if missing:
                raise ToolkitError(
                    "Rendered PDF is incomplete: expected report text is missing: "
                    + ", ".join(missing),
                    code="pdf_incomplete",
                )
            verification = "structural+text"
            text_checked = expected_text
    return {
        "pages": pages,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "verification": verification,
        "text_markers_checked": text_checked,
    }


def _wait_for_output(path: Path, deadline: float) -> bool:
    """Chromium launchers can return before the PDF is written; wait for a stable file."""
    last = -1
    while time.monotonic() < deadline:
        size = path.stat().st_size if path.is_file() else 0
        if size and size == last:
            return True
        last = size
        time.sleep(0.4)
    return False


def _cleanup(path: Path) -> None:
    for _ in range(10):  # the browser may still be releasing its profile on Windows
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.3)


def _with_print_css(html: str) -> str:
    """The standard layout has no explicit head; insert after the root element instead."""
    if "<head>" in html:
        return html.replace("<head>", "<head>" + PRINT_CSS, 1)
    return re.sub(r"(<html[^>]*>)", lambda m: m.group(1) + PRINT_CSS, html, count=1)


def _pdf_reader() -> Any:
    """pypdf is optional; without it only structural checks run."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    return PdfReader


def _norm(text: str) -> str:
    """Compare text across extraction differences: case, spacing and punctuation."""
    return re.sub(r"[^0-9a-z]+", " ", text.lower()).strip()


def _path_variants(path: str) -> set[str]:
    """Spellings of a local path that can appear in HTML or JSON text."""
    return {
        v
        for v in (
            path,
            path.replace("\\", "/"),
            path.replace("\\", "\\\\"),
            html_escape(path),
        )
        if len(v) > 6
    }


def _local_markers() -> list[str]:
    values = [
        str(Path.home()),
        tempfile.gettempdir(),
        os.environ.get("USERPROFILE", ""),
        os.environ.get("TEMP", ""),
    ]
    return [v for value in values if value for v in _path_variants(value)]


def _markers(html: str) -> list[str]:
    """Title and section headings that must survive printing (unescaped; normalized on compare)."""
    markers: list[str] = []
    for match in re.finditer(r"<h([12])[^>]*>(.*?)</h\1>", html, re.S):
        text = unescape(re.sub(r"<[^>]+>", "", match.group(2)))
        text = re.sub(r"\s+", " ", text).strip()
        if text and text[:60] not in markers:
            markers.append(text[:60])
    return markers[:12]


def print_report(
    report_dir: Path,
    out: Path,
    *,
    replace: bool = False,
    browser: Path | None = None,
    timeout: float = 90,
) -> dict[str, Any]:
    source = report_dir / "report.html"
    if not source.is_file():
        raise ToolkitError("Report directory has no report.html; build a report first.")
    if out.exists() and not replace:
        raise ToolkitError("PDF destination exists; use --replace to swap it only after success.")
    if source.stat().st_size > MAX_HTML_BYTES:
        raise ToolkitError("Report HTML exceeds the PDF size bound.")
    html = source.read_text(encoding="utf-8")
    if "<head>" not in html and not re.search(r"<html[^>]*>", html):
        raise ToolkitError("Report HTML has no root element to print from.", code="pdf_invalid")
    searchable = html.lower()
    local = [str(report_dir.resolve()), *_local_markers()]
    if any(v.lower() in searchable for item in local for v in _path_variants(item)):
        raise ToolkitError(
            "Report HTML shows a local path; rebuild it without paths before printing.",
            code="pdf_leak",
        )
    renderer = browser or find_browser()
    out.parent.mkdir(parents=True, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="le-pdf-")
    try:
        work = Path(scratch)
        page = work / "report.html"
        # Print copy only: expose collapsed evidence; the report on disk is unchanged.
        printable = re.sub(r"<details(?=[\s>])(?![^>]*\sopen(?=[\s=>/]))", "<details open", html)
        page.write_text(_with_print_css(printable), encoding="utf-8")
        printed = work / "printed.pdf"
        command = [
            str(renderer),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--disable-extensions",
            "--disable-background-networking",
            "--host-resolver-rules=MAP * ~NOTFOUND",
            "--proxy-server=http://127.0.0.1:9",  # IP-literal URLs cannot reach a network either
            "--no-pdf-header-footer",
            f"--user-data-dir={work / 'profile'}",
            f"--print-to-pdf={printed}",
            page.as_uri(),
        ]
        deadline = time.monotonic() + timeout
        try:
            subprocess.run(command, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise ToolkitError(
                "PDF renderer timed out; the HTML report is unchanged and no PDF was written.",
                code="pdf_timeout",
            ) from None
        except OSError:
            raise ToolkitError(
                "PDF renderer could not start; check the executable and user permissions.",
                code="pdf_renderer_missing",
            ) from None
        if not _wait_for_output(printed, deadline):
            raise ToolkitError(
                "PDF renderer produced no output. Close other profiles of that browser or set "
                f"{BROWSER_ENV} to another Chromium executable.",
                code="pdf_failed",
            )
        forbidden = [str(work), scratch, str(Path.home()), str(report_dir.resolve()), "file:///"]
        details = inspect_pdf(printed, forbidden, _markers(html))
        staged = out.with_name(out.name + ".partial")
        receipt_path = out.with_name(out.name + ".receipt.json")
        try:
            shutil.copyfile(printed, staged)
            receipt_path.unlink(missing_ok=True)  # an old receipt must never describe a new PDF
            os.replace(staged, out)  # Prior good PDF survives every earlier failure.
        finally:
            staged.unlink(missing_ok=True)
    finally:
        _cleanup(Path(scratch))
    receipt = {
        "schema_version": "pdf-receipt/1",
        "generated_at": datetime.now(UTC).isoformat(),
        "renderer": renderer.stem,
        "source_html_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "synthetic": "SYNTHETIC" in html.upper(),
        "scope": "Print of the existing HTML report; no recalculation and not a native Application PDF.",
        **details,
    }
    write_json(receipt_path, receipt)
    return {
        "out": str(out),
        **{k: receipt[k] for k in ("pages", "bytes", "sha256", "verification")},
    }
