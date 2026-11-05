"""PDF text extraction with an OCR fallback for scanned pages (Task 2).

pypdf runs first on every page. Pages whose pypdf text has fewer than PDF_OCR_MIN_CHARS
non-whitespace characters are rendered with pdf2image (poppler's pdftoppm) and read with
pytesseract (Tesseract, lang="eng"). Only those pages are rendered.

Failure never aborts ingestion: if OCR is unavailable or fails on a page, that page keeps its
pypdf text and a warning is recorded. Everything runs locally; nothing leaves the machine.
Rendering and Tesseract write short-lived temp files to /tmp, which docker-compose mounts as
tmpfs (RAM) for the backend.

Settings (environment):
  PDF_OCR_MIN_CHARS  default 50. 0 disables OCR.
  PDF_OCR_MAX_PAGES  default 0 = no limit. Otherwise at most this many pages are OCR'd per PDF.
"""

from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

OCR_LANG = "eng"
OCR_DPI = 300
OCR_PAGE_TIMEOUT_S = 120      # per page, for both rendering and Tesseract
_WARNING_MAX_CHARS = 200


@dataclass
class OcrReport:
    pages_total: int = 0
    attempted: List[int] = field(default_factory=list)   # 1-based pages sent to OCR
    ocr_pages: List[int] = field(default_factory=list)   # pages whose text now comes from OCR
    warnings: List[str] = field(default_factory=list)
    # Vision (pdf_vision.py, Task 5): only reported when PDF_VISION_ENABLED=true.
    vision_enabled: bool = False
    vision_pages: List[int] = field(default_factory=list)
    vision_warnings: List[str] = field(default_factory=list)

    def summary(self) -> dict:
        """Fields added to ingestion responses."""
        out = {"ocr_pages": len(self.ocr_pages), "ocr_page_numbers": list(self.ocr_pages),
               "ocr_warnings": list(self.warnings)}
        if self.vision_enabled:
            out.update({"vision_pages": len(self.vision_pages), "vision_page_numbers": list(self.vision_pages),
                        "vision_warnings": list(self.vision_warnings)})
        return out


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value


def ocr_settings() -> Tuple[int, int]:
    """(min_chars, max_pages) from PDF_OCR_MIN_CHARS / PDF_OCR_MAX_PAGES."""
    return _env_int("PDF_OCR_MIN_CHARS", 50), _env_int("PDF_OCR_MAX_PAGES", 0)


def ocr_available() -> Tuple[bool, str]:
    """Check once per document that the wrappers and the binaries are present."""
    try:
        import pdf2image  # noqa: F401
        import pytesseract
    except ImportError as e:
        return False, f"OCR unavailable: Python package missing ({e.name})"
    for binary in ("pdftoppm", "pdfinfo"):
        if shutil.which(binary) is None:
            return False, f"OCR unavailable: {binary} not found (install poppler-utils)"
    try:
        langs = pytesseract.get_languages(config="")
    except Exception as e:  # TesseractNotFoundError and friends
        return False, f"OCR unavailable: tesseract not usable ({type(e).__name__})"
    if OCR_LANG not in langs:
        return False, f"OCR unavailable: Tesseract language '{OCR_LANG}' not installed (tesseract-ocr-eng)"
    return True, ""


def ocr_page_image(pdf_bytes: bytes, page_number: int) -> str:
    """Render one page (1-based) and OCR it. Raises on any failure."""
    from pdf2image import convert_from_bytes
    import pytesseract

    images = convert_from_bytes(pdf_bytes, dpi=OCR_DPI, first_page=page_number, last_page=page_number,
                                timeout=OCR_PAGE_TIMEOUT_S)
    if not images:
        raise RuntimeError("page did not render")
    try:
        return pytesseract.image_to_string(images[0], lang=OCR_LANG, timeout=OCR_PAGE_TIMEOUT_S)
    finally:
        for im in images:
            im.close()


def _short(e: BaseException) -> str:
    msg = f"{type(e).__name__}: {e}".strip()
    return msg if len(msg) <= _WARNING_MAX_CHARS else msg[:_WARNING_MAX_CHARS] + "..."


def extract_pdf_pages(data: bytes, min_chars: Optional[int] = None, max_pages: Optional[int] = None,
                      ocr: Optional[Callable[[bytes, int], str]] = None) -> Tuple[List[Tuple[int, str]], OcrReport]:
    """Return ([(page_number, text), ...] for every page, OcrReport).

    Pages are 1-based and include empty ones; callers drop those as before. `ocr` is injectable
    for tests; by default ocr_page_image() is used after an ocr_available() check.
    """
    import pypdf

    env_min, env_max = ocr_settings()
    min_chars = env_min if min_chars is None else min_chars
    max_pages = env_max if max_pages is None else max_pages

    reader = pypdf.PdfReader(io.BytesIO(data))
    texts = [page.extract_text() or "" for page in reader.pages]
    report = OcrReport(pages_total=len(texts))

    _ocr_pass(data, texts, report, min_chars, max_pages, ocr)

    import pdf_vision   # Task 5: off unless PDF_VISION_ENABLED=true; never raises

    if pdf_vision.vision_enabled():
        pdf_vision.add_vision_descriptions(data, reader, texts, report)
    return list(enumerate(texts, start=1)), report


def _ocr_pass(data: bytes, texts: List[str], report: OcrReport, min_chars: int, max_pages: int,
              ocr: Optional[Callable[[bytes, int], str]]) -> None:
    """OCR the pages whose pypdf text is too short, updating `texts` and `report` in place."""

    def too_short(t: str) -> bool:
        return len("".join(t.split())) < min_chars

    candidates = [i + 1 for i, t in enumerate(texts) if too_short(t)]
    if not candidates:
        return

    if ocr is None:
        ok, reason = ocr_available()
        if not ok:
            report.warnings.append(f"{reason}; {len(candidates)} page(s) kept with pypdf text only")
            return
        ocr = ocr_page_image

    if max_pages and len(candidates) > max_pages:
        skipped = candidates[max_pages:]
        candidates = candidates[:max_pages]
        report.warnings.append(f"PDF_OCR_MAX_PAGES={max_pages}: {len(skipped)} page(s) not OCR'd "
                               f"(pages {skipped[0]}-{skipped[-1]})")

    for page in candidates:
        report.attempted.append(page)
        try:
            text = ocr(data, page) or ""
        except Exception as e:
            report.warnings.append(f"page {page}: OCR failed ({_short(e)}); kept pypdf text")
            continue
        # Use OCR only if it found more than pypdf did (an empty scan stays empty, a sparse text page stays as is).
        if len("".join(text.split())) > len("".join(texts[page - 1].split())):
            texts[page - 1] = text
            report.ocr_pages.append(page)
