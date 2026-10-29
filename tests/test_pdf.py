import json
import os
import zlib
from pathlib import Path

import pytest

from le_results import pdf
from le_results.compare import compare
from le_results.errors import ToolkitError
from le_results.report import build_report
from le_results.synthetic import demo


def make_pdf(content: bytes = b"BT /F1 12 Tf (report) Tj ET\n" * 120, tail: bytes = b"%%EOF\n"):
    body = zlib.compress(content)
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Pages/Kids[2 0 R]/Count 1>>endobj\n"
        b"2 0 obj<</Type/Page/Parent 1 0 R/Contents 3 0 R>>endobj\n"
        b"3 0 obj<</Filter/FlateDecode/Length "
        + str(len(body)).encode()
        + b">>\nstream\n"
        + body
        + b"\nendstream endobj\ntrailer<</Root 1 0 R>>\n"
        + tail
    )


def write(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "x.pdf"
    path.write_bytes(data)
    return path


def test_valid_structure_counts_pages_and_hashes(tmp_path):
    result = pdf.inspect_pdf(write(tmp_path, make_pdf()), [], [])
    assert result["pages"] == 1 and result["verification"] == "structural"
    assert len(result["sha256"]) == 64


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"not a pdf at all", "pdf_invalid"),
        (make_pdf(tail=b""), "pdf_invalid"),  # truncated: no EOF marker
        (make_pdf(content=b"q Q\n"), "pdf_blank"),
        (make_pdf().replace(b"/Type/Page/", b"/Type/Other/"), "pdf_invalid"),
    ],
)
def test_corrupt_blank_or_incomplete_output_is_rejected(tmp_path, data, code):
    with pytest.raises(ToolkitError) as caught:
        pdf.inspect_pdf(write(tmp_path, data), [], [])
    assert caught.value.code == code


def test_private_path_in_content_or_metadata_is_rejected(tmp_path):
    secret = "C:\\Users\\someone\\private"
    leaky = make_pdf(content=(b"BT (" + secret.encode() + b") Tj ET\n") * 120)
    with pytest.raises(ToolkitError) as caught:
        pdf.inspect_pdf(write(tmp_path, leaky), [secret], [])
    assert caught.value.code == "pdf_leak"


def test_renderer_diagnostics_are_actionable(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf.shutil, "which", lambda name: None)
    monkeypatch.setattr(pdf, "KNOWN_LOCATIONS", ())
    with pytest.raises(ToolkitError, match="administrator rights") as caught:
        pdf.find_browser({})
    assert caught.value.code == "pdf_renderer_missing"
    assert pdf.BROWSER_ENV in str(caught.value)
    with pytest.raises(ToolkitError, match="does not point to a file"):
        pdf.find_browser({pdf.BROWSER_ENV: str(tmp_path / "missing.exe")})
    exe = tmp_path / "chromium.exe"
    exe.write_bytes(b"")
    assert pdf.find_browser({pdf.BROWSER_ENV: str(exe)}) == exe


@pytest.fixture
def report_dir(tmp_path):
    demo(tmp_path / "d", "windows-review")
    d = tmp_path / "d"
    config = json.loads((d / "compare.json").read_text())
    comparison = compare(d / "baseline", d / "candidate", config)
    out = tmp_path / "report"
    build_report(
        comparison,
        out,
        {
            "schema_version": "report/1",
            "title": "Windows image application review",
            "layout": "review",
            "visuals": ["comparison_table", "change_chart", "coverage_table", "source_table"],
        },
    )
    return out


def fake_renderer(monkeypatch, behavior):
    seen = {}

    def run(command, **kwargs):
        target = next(c for c in command if c.startswith("--print-to-pdf="))
        seen["command"] = command
        seen["page"] = Path(command[-1].removeprefix("file:///").replace("/", os.sep))
        behavior(Path(target.split("=", 1)[1]), seen)

    monkeypatch.setattr(pdf.subprocess, "run", run)
    monkeypatch.setattr(pdf.time, "sleep", lambda s: None)
    return seen


def test_print_uses_existing_html_exposes_details_and_writes_receipt(
    tmp_path, report_dir, monkeypatch
):
    tool = tmp_path / "chrome.exe"
    tool.write_bytes(b"")
    captured = {}

    def good(target, seen):
        captured["html"] = seen["page"].read_text(encoding="utf-8")
        target.write_bytes(make_pdf())

    fake_renderer(monkeypatch, good)
    monkeypatch.setattr(pdf, "_markers", lambda html: [])  # synthetic bytes are not parseable
    before = (report_dir / "report.html").read_bytes()
    out = tmp_path / "out" / "r.pdf"
    result = pdf.print_report(report_dir, out, browser=tool)
    assert result["pages"] == 1 and out.is_file()
    assert "<details open" in captured["html"] and "@page" in captured["html"]
    assert (report_dir / "report.html").read_bytes() == before  # source report untouched
    receipt = json.loads(Path(str(out) + ".receipt.json").read_text())
    assert receipt["synthetic"] is True and receipt["renderer"] == "chrome"
    assert "recalculation" in receipt["scope"]
    assert str(tmp_path) not in json.dumps(receipt)  # no private paths in the receipt


def test_unparseable_pdf_with_expected_text_is_rejected(tmp_path):
    pytest.importorskip("pypdf")
    with pytest.raises(ToolkitError) as caught:
        pdf.inspect_pdf(write(tmp_path, make_pdf()), [], ["Report title"])
    assert caught.value.code == "pdf_invalid"


def test_failed_render_preserves_prior_good_pdf(tmp_path, report_dir, monkeypatch):
    tool = tmp_path / "chrome.exe"
    tool.write_bytes(b"")
    out = tmp_path / "r.pdf"
    out.write_bytes(make_pdf())
    prior = out.read_bytes()
    fake_renderer(monkeypatch, lambda target, seen: target.write_bytes(b"%PDF-1.4 broken"))
    with pytest.raises(ToolkitError):
        pdf.print_report(report_dir, out, replace=True, browser=tool, timeout=0.5)
    assert out.read_bytes() == prior and not Path(str(out) + ".partial").exists()


def test_no_output_and_existing_destination_are_explicit(tmp_path, report_dir, monkeypatch):
    tool = tmp_path / "chrome.exe"
    tool.write_bytes(b"")
    fake_renderer(monkeypatch, lambda target, seen: None)
    clock = iter(range(0, 1000, 50))
    monkeypatch.setattr(pdf.time, "monotonic", lambda: next(clock))
    with pytest.raises(ToolkitError) as caught:
        pdf.print_report(report_dir, tmp_path / "none.pdf", browser=tool, timeout=60)
    assert caught.value.code == "pdf_failed"
    existing = tmp_path / "e.pdf"
    existing.write_bytes(b"keep")
    with pytest.raises(ToolkitError, match="--replace"):
        pdf.print_report(report_dir, existing, browser=tool)
    assert existing.read_bytes() == b"keep"


def test_missing_report_html_is_explicit(tmp_path):
    with pytest.raises(ToolkitError, match="no report.html"):
        pdf.print_report(tmp_path, tmp_path / "x.pdf", browser=tmp_path / "b.exe")


@pytest.mark.skipif(
    os.environ.get("LE_RESULTS_TEST_BROWSER") != "1",
    reason="Set LE_RESULTS_TEST_BROWSER=1 to print with a real local Chromium-family browser.",
)
def test_real_browser_prints_synthetic_review(tmp_path, report_dir):
    out = tmp_path / "real.pdf"
    result = pdf.print_report(report_dir, out)
    assert result["pages"] >= 2 and result["verification"] in ("structural", "structural+text")
    pytest.importorskip("pypdf")
    from pypdf import PdfReader

    text = " ".join(p.extract_text() for p in PdfReader(str(out)).pages)
    assert "SYNTHETIC" in text and "Evidence, sample counts and limitations" in text
    assert "Selection and source" in text  # collapsed evidence is printed
