"""Task 5: optional vision descriptions for PDF pages with images (pdf_vision.py).

Flow tests mock describe_page() and run anywhere. The client tests talk to a local stub
OpenAI-compatible server (success, timeout, unreachable, proxy env ignored) and need openai, httpx,
pdf2image/poppler and Pillow; they skip otherwise. All of these are in the backend image.
"""

import asyncio
import json
import os
import shutil
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import pdf_text
import pdf_vision
from pdf_text import extract_pdf_pages
from test_pdf_ocr import HAVE_PIL_FONT, LONG_TEXT, concat_pdfs, make_scanned_pdf, make_text_pdf

requires_pil = pytest.mark.skipif(not HAVE_PIL_FONT, reason="Pillow with FreeType needed to build image PDFs")


@pytest.fixture(autouse=True)
def vision_env(monkeypatch):
    for name in ("PDF_VISION_ENABLED", "VISION_ALLOW_REMOTE", "VISION_MODEL", "VISION_TIMEOUT_S"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("PDF_OCR_MIN_CHARS", "0")          # isolate vision from OCR


class FakeDescribe:
    def __init__(self, results):
        self.results, self.calls = results, []

    def __call__(self, data, page, settings):
        self.calls.append(page)
        r = self.results.get(page, "")
        if isinstance(r, Exception):
            raise r
        return r


def enable(monkeypatch, describe=None):
    monkeypatch.setenv("PDF_VISION_ENABLED", "true")
    if describe is not None:
        monkeypatch.setattr(pdf_vision, "describe_page", describe)


# ----------------------------------------------------------------------------- default off
@requires_pil
def test_vision_off_by_default(monkeypatch):
    fake = FakeDescribe({1: "should not be called"})
    monkeypatch.setattr(pdf_vision, "describe_page", fake)
    _, report = extract_pdf_pages(make_scanned_pdf())
    assert fake.calls == [] and "vision_pages" not in report.summary()


# ----------------------------------------------------------------------------- flow (mocked)
@requires_pil
def test_success_appends_description_under_its_own_heading(monkeypatch):
    enable(monkeypatch, FakeDescribe({2: "P&ID: pump P-101 discharging to vessel V-3 through FCV-12."}))
    pdf = concat_pdfs(make_text_pdf([LONG_TEXT]), make_scanned_pdf())
    pages, report = extract_pdf_pages(pdf)
    text2 = dict(pages)[2]
    assert text2.startswith("### Image description (vision model, page 2)\nP&ID: pump P-101")
    assert "Image description" not in dict(pages)[1]      # page 1 has no images: not sent
    s = report.summary()
    assert s["vision_pages"] == 1 and s["vision_page_numbers"] == [2] and s["vision_warnings"] == []


@requires_pil
def test_timeout_keeps_text_and_skips_remaining_pages(monkeypatch):
    fake = FakeDescribe({1: pdf_vision.VisionTimeout("no answer within 60s"), 2: "never"})
    enable(monkeypatch, fake)
    pages, report = extract_pdf_pages(concat_pdfs(make_scanned_pdf(), make_scanned_pdf()))
    assert fake.calls == [1]                               # one timeout per document at most
    assert all("Image description" not in t for _, t in pages)
    assert report.vision_warnings == [
        "page 1: vision endpoint timed out (no answer within 60s); text only; 1 more page(s) with images ingested text-only"]


@requires_pil
def test_unreachable_keeps_text_with_warning(monkeypatch):
    enable(monkeypatch, FakeDescribe({1: pdf_vision.VisionUnreachable("cannot connect to http://127.0.0.1:11434/v1")}))
    pages, report = extract_pdf_pages(make_scanned_pdf())
    assert "Image description" not in dict(pages)[1]
    assert report.vision_warnings[0].startswith("page 1: vision endpoint unreachable (cannot connect")
    assert report.summary()["vision_pages"] == 0


@requires_pil
def test_other_page_error_continues_with_next_page(monkeypatch):
    fake = FakeDescribe({1: ValueError("bad response"), 2: "Bar chart of monthly vibration."})
    enable(monkeypatch, fake)
    pages, report = extract_pdf_pages(concat_pdfs(make_scanned_pdf(), make_scanned_pdf()))
    assert fake.calls == [1, 2] and report.vision_pages == [2]
    assert report.vision_warnings == ["page 1: vision failed (ValueError); text only"]


@requires_pil
def test_non_local_endpoint_is_refused_unless_allowed(monkeypatch):
    fake = FakeDescribe({1: "desc"})
    enable(monkeypatch, fake)
    monkeypatch.setenv("LLM_BASE_URL", "http://192.168.1.50:11434/v1")
    _, report = extract_pdf_pages(make_scanned_pdf())
    assert fake.calls == [] and "not a local (loopback) address" in report.vision_warnings[0]

    monkeypatch.setenv("VISION_ALLOW_REMOTE", "true")
    _, report = extract_pdf_pages(make_scanned_pdf())
    assert fake.calls == [1] and report.vision_pages == [1]


@pytest.mark.parametrize("url,ok", [
    ("http://127.0.0.1:11434/v1", True), ("http://localhost:11434/v1", True), ("http://[::1]:11434/v1", True),
    ("http://127.1.2.3:8000/v1", True), ("http://10.0.0.5:11434/v1", False), ("http://192.168.1.50/v1", False),
    ("http://172.17.0.1:11434/v1", False), ("https://8.8.8.8/v1", False), ("ftp://127.0.0.1/v1", False), ("", False),
])
def test_endpoint_locality(url, ok):
    assert pdf_vision.check_vision_endpoint(url, allow_remote=False)[0] is ok


def test_allow_remote_still_requires_http_url():
    assert pdf_vision.check_vision_endpoint("http://203.0.113.9/v1", allow_remote=True)[0] is True
    assert pdf_vision.check_vision_endpoint("file:///etc/passwd", allow_remote=True)[0] is False


@requires_pil
def test_page_has_images():
    import io

    import pypdf

    assert pdf_vision.page_has_images(pypdf.PdfReader(io.BytesIO(make_scanned_pdf())).pages[0])
    assert not pdf_vision.page_has_images(pypdf.PdfReader(io.BytesIO(make_text_pdf([LONG_TEXT]))).pages[0])


@requires_pil
def test_encrypted_pipeline_stores_description_encrypted(tmp_path, keys, fake_embedder, mock_atomic, monkeypatch):
    from test_pipeline import make_pipeline

    enable(monkeypatch, FakeDescribe({1: "Schematic of anti-surge loop with valve FV-201."}))
    p = make_pipeline(tmp_path, keys, fake_embedder, mock_atomic)
    res = asyncio.run(p.ingest("pid.pdf", make_scanned_pdf(), actor="op"))
    assert res["status"] == "ingested_encrypted" and res["vision_pages"] == 1 and res["vision_warnings"] == []
    assert "FV-201" not in mock_atomic.everything_seen()     # encrypted like any other text
    hit = asyncio.run(p.search("anti-surge valve FV-201 schematic", actor="op"))["results"][0]
    assert "### Image description (vision model, page 1)" in hit["text"]


# ----------------------------------------------------------------------------- real client vs stub server
def _client_ready():
    try:
        import httpx  # noqa: F401
        import openai  # noqa: F401
        import pdf2image  # noqa: F401
    except ImportError as e:
        return False, f"{e.name} not installed"
    if not shutil.which("pdftoppm"):
        return False, "pdftoppm (poppler) not installed"
    if not HAVE_PIL_FONT:
        return False, "Pillow with FreeType not available"
    return True, ""


CLIENT_OK, CLIENT_WHY = _client_ready()
requires_client = pytest.mark.skipif(not CLIENT_OK, reason=CLIENT_WHY or "vision client deps missing")


class StubVision(BaseHTTPRequestHandler):
    delay = 0.0
    requests = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append((self.path, body))
        time.sleep(type(self).delay)
        reply = {"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                 "choices": [{"index": 0, "finish_reason": "stop",
                              "message": {"role": "assistant", "content": "Diagram of pump P-101 and valve V-7."}}],
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        data = json.dumps(reply).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *a):
        pass


@pytest.fixture
def stub(monkeypatch):
    StubVision.delay, StubVision.requests = 0.0, []
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubVision)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}/v1")
    yield StubVision
    server.shutdown()


@requires_client
def test_client_success_against_stub(stub, monkeypatch):
    enable(monkeypatch)
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(var, "http://10.255.255.1:9")   # dead proxy: the client must ignore it
    monkeypatch.setenv("NO_PROXY", "")
    pages, report = extract_pdf_pages(make_scanned_pdf())
    assert report.vision_pages == [1], report.vision_warnings
    assert "Diagram of pump P-101" in dict(pages)[1]
    path, body = stub.requests[0]
    assert path == "/v1/chat/completions" and body["model"] == "qwen2.5vl:3b"
    image = body["messages"][0]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")


@requires_client
def test_client_timeout_against_stub(stub, monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv("VISION_TIMEOUT_S", "1")
    stub.delay = 3.0
    t = time.monotonic()
    pages, report = extract_pdf_pages(make_scanned_pdf())
    assert time.monotonic() - t < 6
    assert "timed out" in report.vision_warnings[0] and report.vision_pages == []


@requires_client
def test_client_unreachable(monkeypatch):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                               # nothing listens here now
    enable(monkeypatch)
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{port}/v1")
    pages, report = extract_pdf_pages(make_scanned_pdf())
    assert "unreachable" in report.vision_warnings[0] and report.vision_pages == []
