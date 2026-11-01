"""Task 2: OCR fallback for scanned PDF pages (pdf_text.py) in both ingestion paths.

Real-OCR tests need pytesseract + pdf2image, the tesseract and poppler binaries, the 'eng'
language and Pillow; they skip with the exact reason when anything is missing. The rest mock the
OCR function and run anywhere.
"""

import asyncio
import io
import json
from unittest import mock

import pytest

import pdf_text
from encryption.envelope import extract_pages, extract_pages_with_ocr
from pdf_text import extract_pdf_pages

OCR_OK, OCR_REASON = pdf_text.ocr_available()
requires_ocr = pytest.mark.skipif(not OCR_OK, reason=OCR_REASON or "OCR unavailable")

try:
    from PIL import Image, ImageDraw, ImageFont, features
    HAVE_PIL_FONT = features.check("freetype2")
except ImportError:
    HAVE_PIL_FONT = False
requires_pil = pytest.mark.skipif(not HAVE_PIL_FONT, reason="Pillow with FreeType needed to draw the test scan")

LONG_TEXT = ("Centrifugal compressor surge control uses an anti-surge valve and a recycle line. "
             "Operators verify the valve stroke weekly.")
SCAN_LINES = ["ANTI SURGE VALVE", "COMPRESSOR RECYCLE LINE", "INSPECT WEEKLY"]


# ----------------------------------------------------------------------------- PDF builders
def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_text_pdf(pages):
    """Minimal PDF with a real text layer (Helvetica). An empty string gives a page with no text."""
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objs[2] = f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(pages)} >>".encode()
    for pid, text in zip(page_ids, pages):
        shows = " ".join(f"({_esc(line)}) Tj T*" for line in text.split("\n") if line)
        stream = f"BT /F1 11 Tf 72 720 Td 14 TL {shows} ET".encode()
        objs[pid] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                     f"/Resources << /Font << /F1 3 0 R >> >> /Contents {pid + 1} 0 R >>").encode()
        objs[pid + 1] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    out, offsets = b"%PDF-1.4\n", {}
    for oid in sorted(objs):
        offsets[oid] = len(out)
        out += f"{oid} 0 obj\n".encode() + objs[oid] + b"\nendobj\n"
    xref, size = len(out), max(objs) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offsets[i]:010d} 00000 n \n".encode() for i in range(1, size))
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def make_scanned_pdf(lines=SCAN_LINES):
    """Image-only PDF: text drawn into a bitmap, no text layer at all."""
    img = Image.new("L", (1700, 700), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=64)
    for i, line in enumerate(lines):
        draw.text((80, 80 + i * 170), line, fill=0, font=font)
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=200)
    return buf.getvalue()


def concat_pdfs(*docs):
    import pypdf

    w = pypdf.PdfWriter()
    for d in docs:
        w.append(pypdf.PdfReader(io.BytesIO(d)))
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def fake_ocr(by_page):
    """OCR stand-in: page -> text, or an Exception instance to raise."""
    calls = []

    def ocr(data, page):
        calls.append(page)
        result = by_page.get(page, "")
        if isinstance(result, Exception):
            raise result
        return result

    ocr.calls = calls
    return ocr


def page_text(pages, n):
    return dict(pages)[n]


@pytest.fixture(autouse=True)
def default_ocr_env(monkeypatch):
    monkeypatch.delenv("PDF_OCR_MIN_CHARS", raising=False)
    monkeypatch.delenv("PDF_OCR_MAX_PAGES", raising=False)


# ----------------------------------------------------------------------------- real OCR
@requires_ocr
@requires_pil
def test_image_only_pdf_is_ocrd():
    scan = make_scanned_pdf()
    pages, report = extract_pdf_pages(scan)
    text = page_text(pages, 1).upper()
    for line in SCAN_LINES:
        assert line in text, f"{line!r} not in OCR output {text!r}"
    assert report.ocr_pages == [1] and report.warnings == []


@requires_ocr
@requires_pil
def test_mixed_pdf_only_scanned_page_is_ocrd():
    pdf = concat_pdfs(make_text_pdf([LONG_TEXT]), make_scanned_pdf())
    pages, report = extract_pdf_pages(pdf)
    assert report.attempted == [2] and report.ocr_pages == [2]
    assert "anti-surge valve" in page_text(pages, 1)          # pypdf text kept for page 1
    assert "COMPRESSOR RECYCLE LINE" in page_text(pages, 2).upper()


@requires_ocr
@requires_pil
def test_extract_pages_signature_unchanged_and_ocrs():
    """extract_pages(filename, data) -> [(page, text)] is what the encrypted pipeline used before."""
    pages = extract_pages("scan.pdf", make_scanned_pdf())
    assert len(pages) == 1 and pages[0][0] == 1 and "ANTI SURGE VALVE" in pages[0][1].upper()


# ----------------------------------------------------------------------------- no OCR for text PDFs
def test_text_pdf_does_not_call_ocr(monkeypatch):
    ocr = mock.Mock(side_effect=AssertionError("OCR must not run for a text PDF"))
    available = mock.Mock(return_value=(True, ""))
    monkeypatch.setattr(pdf_text, "ocr_page_image", ocr)
    monkeypatch.setattr(pdf_text, "ocr_available", available)

    pdf = make_text_pdf([LONG_TEXT, LONG_TEXT])
    pages, report = extract_pdf_pages(pdf)                 # default path, as ingestion calls it
    assert "anti-surge valve" in page_text(pages, 1) and "anti-surge valve" in page_text(pages, 2)
    assert extract_pages("manual.pdf", pdf)                # encrypted-path entry point too
    ocr.assert_not_called()
    available.assert_not_called()                          # not even the availability probe
    assert report.attempted == [] and report.summary()["ocr_pages"] == 0


# ----------------------------------------------------------------------------- failures and limits
def test_ocr_failure_on_one_page_keeps_going_with_warning():
    pdf = make_text_pdf([LONG_TEXT, "", ""])
    ocr = fake_ocr({2: RuntimeError("tesseract crashed"), 3: "Recovered pump maintenance text from page three"})
    pages, report = extract_pdf_pages(pdf, ocr=ocr)
    assert ocr.calls == [2, 3]
    assert page_text(pages, 2) == ""                        # pypdf result kept
    assert page_text(pages, 3).startswith("Recovered pump")
    assert report.ocr_pages == [3]
    assert report.warnings == ["page 2: OCR failed (RuntimeError: tesseract crashed); kept pypdf text"]


def test_ocr_unavailable_gives_one_warning_and_pypdf_text(monkeypatch):
    monkeypatch.setattr(pdf_text, "ocr_available", lambda: (False, "OCR unavailable: tesseract not usable (X)"))
    monkeypatch.setattr(pdf_text, "ocr_page_image", mock.Mock(side_effect=AssertionError("not reached")))
    pages, report = extract_pdf_pages(make_text_pdf(["", "", ""]))
    assert [t for _, t in pages] == ["", "", ""]
    assert len(report.warnings) == 1 and "3 page(s) kept with pypdf text only" in report.warnings[0]


def test_max_pages_limit(monkeypatch):
    monkeypatch.setenv("PDF_OCR_MAX_PAGES", "1")
    ocr = fake_ocr({1: "first scanned page text here", 2: "x" * 80, 3: "y" * 80})
    _, report = extract_pdf_pages(make_text_pdf(["", "", ""]), ocr=ocr)
    assert ocr.calls == [1] and report.ocr_pages == [1]
    assert "PDF_OCR_MAX_PAGES=1: 2 page(s) not OCR'd (pages 2-3)" in report.warnings[0]


def test_max_pages_zero_means_no_limit():
    ocr = fake_ocr({n: "scanned text " * 5 for n in range(1, 6)})
    _, report = extract_pdf_pages(make_text_pdf([""] * 5), max_pages=0, ocr=ocr)
    assert ocr.calls == [1, 2, 3, 4, 5]


def test_min_chars_threshold(monkeypatch):
    short = "Pump P-101"                                        # 8 non-space chars
    ocr = fake_ocr({1: "Pump P-101 discharge pressure 12 bar, seal flush plan 11"})
    _, report = extract_pdf_pages(make_text_pdf([short]), ocr=ocr)
    assert ocr.calls == [1] and report.ocr_pages == [1]

    monkeypatch.setenv("PDF_OCR_MIN_CHARS", "5")
    ocr = fake_ocr({})
    extract_pdf_pages(make_text_pdf([short]), ocr=ocr)
    assert ocr.calls == []


def test_min_chars_zero_disables_ocr(monkeypatch):
    monkeypatch.setenv("PDF_OCR_MIN_CHARS", "0")
    ocr = fake_ocr({})
    _, report = extract_pdf_pages(make_text_pdf(["", ""]), ocr=ocr)
    assert ocr.calls == [] and report.attempted == []


@pytest.mark.parametrize("name,value", [("PDF_OCR_MIN_CHARS", "abc"), ("PDF_OCR_MIN_CHARS", "-1"),
                                        ("PDF_OCR_MAX_PAGES", "1.5")])
def test_bad_settings_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        extract_pdf_pages(make_text_pdf([LONG_TEXT]))


def test_ocr_result_with_less_text_is_ignored():
    pdf = make_text_pdf(["Valve V-7"])
    pages, report = extract_pdf_pages(pdf, ocr=fake_ocr({1: "  "}))
    assert "Valve V-7" in page_text(pages, 1)
    assert report.attempted == [1] and report.ocr_pages == []


def test_text_files_have_no_ocr_report():
    pages, report = extract_pages_with_ocr("notes.txt", b"plain text notes")
    assert pages == [(None, "plain text notes")] and report is None


# ----------------------------------------------------------------------------- encrypted path
def _pipeline(tmp_path, keys, fake_embedder, mock_atomic):
    from test_pipeline import make_pipeline

    return make_pipeline(tmp_path, keys, fake_embedder, mock_atomic)


def test_encrypted_ingest_reports_ocr_and_survives_page_failure(tmp_path, keys, fake_embedder, mock_atomic,
                                                                monkeypatch):
    recovered = "Recovered pump maintenance text from page three: replace the mechanical seal."
    monkeypatch.setattr(pdf_text, "ocr_available", lambda: (True, ""))
    monkeypatch.setattr(pdf_text, "ocr_page_image", fake_ocr({2: OSError("pdftoppm died"), 3: recovered}))
    p = _pipeline(tmp_path, keys, fake_embedder, mock_atomic)

    res = asyncio.run(p.ingest("scan.pdf", make_text_pdf([LONG_TEXT, "", ""]), actor="op"))
    assert res["status"] == "ingested_encrypted" and res["chunks"] >= 2
    assert res["ocr_pages"] == 1 and res["ocr_page_numbers"] == [3]
    assert res["ocr_warnings"] == ["page 2: OCR failed (OSError: pdftoppm died); kept pypdf text"]
    assert "Recovered pump" not in mock_atomic.everything_seen()     # OCR text is encrypted like any other

    hits = asyncio.run(p.search("replace the mechanical seal", actor="op"))["results"]
    assert hits[0]["page"] == 3 and hits[0]["text"].startswith("Recovered pump")

    with open(tmp_path / "audit.jsonl") as f:
        entry = [json.loads(line) for line in f if '"ingest_encrypted"' in line][-1]
    assert entry["ocr_pages"] == 1 and entry["ocr_warning_count"] == 1
    assert "Recovered" not in json.dumps(entry)


def test_encrypted_ingest_all_ocr_failed_explains_why(tmp_path, keys, fake_embedder, mock_atomic, monkeypatch):
    monkeypatch.setattr(pdf_text, "ocr_available", lambda: (False, "OCR unavailable: pdftoppm not found"))
    p = _pipeline(tmp_path, keys, fake_embedder, mock_atomic)
    with pytest.raises(ValueError, match="no extractable text in document .OCR: OCR unavailable: pdftoppm"):
        asyncio.run(p.ingest("scan.pdf", make_text_pdf(["", ""]), actor="op"))


@requires_ocr
@requires_pil
def test_encrypted_ingest_of_real_scan_is_searchable(tmp_path, keys, fake_embedder, mock_atomic):
    """The demo path, no mocks in OCR: scanned PDF -> Tesseract -> encrypted chunks -> encrypted search."""
    p = _pipeline(tmp_path, keys, fake_embedder, mock_atomic)
    res = asyncio.run(p.ingest("scan.pdf", make_scanned_pdf(), actor="op"))
    assert res["status"] == "ingested_encrypted" and res["ocr_pages"] == 1 and res["ocr_warnings"] == []
    assert "RECYCLE" not in mock_atomic.everything_seen().upper()
    hits = asyncio.run(p.search("compressor recycle line", actor="op"))["results"]
    assert hits and "COMPRESSOR RECYCLE LINE" in hits[0]["text"].upper()
