"""Optional vision descriptions for PDF pages that contain images (Task 5). Off by default.

PDF_VISION_ENABLED=true: each page with an embedded image is rendered (pdf2image) and sent to the
vision model (VISION_MODEL, default qwen2.5vl:3b) at LLM_BASE_URL's OpenAI-compatible
/chat/completions endpoint. The answer is appended to that page's text under its own heading, so it
is stored with the atom (and encrypted with it when encryption is on).

Images go to LLM_BASE_URL only, and only if it is a loopback address (localhost, 127.0.0.0/8, ::1),
unless VISION_ALLOW_REMOTE=true. The client uses no proxy settings from the environment
(trust_env=False), follows no redirects and does not retry.

Vision never fails ingestion: if the endpoint is refused, unreachable or times out, the page keeps
its text and a warning is recorded. After an unreachable endpoint or a timeout, the remaining pages
are skipped (one warning), so a dead endpoint costs at most one timeout per document.
"""

from __future__ import annotations

import base64
import io
import ipaddress
import os
import socket
from typing import List, Optional, Tuple
from urllib.parse import urlparse

VISION_HEADING = "### Image description (vision model, page {page})"
VISION_PROMPT = (
    "You are indexing an industrial engineering document. Describe the images on this page for search: "
    "diagram type (P&ID, schematic, chart, photo, table), equipment and instrument tags, labels, units and any "
    "text inside the images. Be factual and concise; do not guess values you cannot read."
)
VISION_DPI = 150
VISION_MAX_WIDTH = 1280
VISION_MAX_TOKENS = 400


class VisionTimeout(Exception):
    pass


class VisionUnreachable(Exception):
    pass


def _flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def vision_enabled() -> bool:
    return _flag("PDF_VISION_ENABLED")


def vision_settings() -> dict:
    return {
        "base_url": os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"),
        "api_key": os.getenv("LLM_API_KEY", "ollama"),
        "model": os.getenv("VISION_MODEL", "qwen2.5vl:3b"),
        "timeout_s": float(os.getenv("VISION_TIMEOUT_S", "60")),
    }


def check_vision_endpoint(base_url: str, allow_remote: Optional[bool] = None) -> Tuple[bool, str]:
    """(ok, reason). ok only for loopback endpoints unless VISION_ALLOW_REMOTE=true."""
    allow_remote = _flag("VISION_ALLOW_REMOTE") if allow_remote is None else allow_remote
    parsed = urlparse(base_url or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False, f"vision disabled: LLM_BASE_URL {base_url!r} is not an http(s) URL"
    if allow_remote:
        return True, ""
    host = parsed.hostname
    try:
        addrs = [host] if _is_ip(host) else sorted({i[4][0] for i in socket.getaddrinfo(host, None)})
    except OSError:
        return False, f"vision disabled: cannot resolve LLM_BASE_URL host {host!r}"
    if addrs and all(ipaddress.ip_address(a.split("%", 1)[0]).is_loopback for a in addrs):
        return True, ""
    return False, (f"vision disabled: LLM_BASE_URL host {host!r} is not a local (loopback) address; "
                   "set VISION_ALLOW_REMOTE=true to allow it")


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def page_has_images(page, _depth: int = 0) -> bool:
    """True if the page's resources contain an image XObject (also inside form XObjects)."""
    try:
        resources = page.get("/Resources")
        resources = resources.get_object() if resources is not None else None
        xobjects = resources.get("/XObject") if resources else None
        if xobjects is None:
            return False
        for ref in xobjects.get_object().values():
            obj = ref.get_object()
            subtype = obj.get("/Subtype")
            if subtype == "/Image":
                return True
            if subtype == "/Form" and _depth < 3 and page_has_images(obj, _depth + 1):
                return True
    except Exception:
        return False
    return False


def render_page_png(pdf_bytes: bytes, page_number: int) -> bytes:
    from pdf2image import convert_from_bytes

    images = convert_from_bytes(pdf_bytes, dpi=VISION_DPI, first_page=page_number, last_page=page_number,
                                size=(VISION_MAX_WIDTH, None), timeout=120)
    if not images:
        raise RuntimeError("page did not render")
    buf = io.BytesIO()
    try:
        images[0].save(buf, "PNG")
    finally:
        for im in images:
            im.close()
    return buf.getvalue()


def describe_image(png: bytes, settings: dict) -> str:
    """One OpenAI-compatible chat completion with the page image. Raises VisionTimeout/VisionUnreachable."""
    import httpx
    import openai

    client = openai.OpenAI(
        base_url=settings["base_url"], api_key=settings["api_key"], max_retries=0,
        timeout=settings["timeout_s"],
        http_client=httpx.Client(trust_env=False, follow_redirects=False, timeout=settings["timeout_s"]),
    )
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    try:
        resp = client.chat.completions.create(
            model=settings["model"], temperature=0, max_tokens=VISION_MAX_TOKENS,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
        )
    except openai.APITimeoutError as e:            # subclass of APIConnectionError: check first
        raise VisionTimeout(f"no answer within {settings['timeout_s']:g}s") from e
    except openai.APIConnectionError as e:
        raise VisionUnreachable(f"cannot connect to {settings['base_url']}") from e
    finally:
        client.close()
    return (resp.choices[0].message.content or "").strip()


def describe_page(pdf_bytes: bytes, page_number: int, settings: dict) -> str:
    return describe_image(render_page_png(pdf_bytes, page_number), settings)


def add_vision_descriptions(pdf_bytes: bytes, reader, texts: List[str], report) -> None:
    """Append descriptions to `texts` (in place) and fill report.vision_* fields. Never raises."""
    report.vision_enabled = True
    settings = vision_settings()
    ok, reason = check_vision_endpoint(settings["base_url"])
    if not ok:
        report.vision_warnings.append(reason)
        return
    try:
        pages = [i + 1 for i, page in enumerate(reader.pages) if page_has_images(page)]
    except Exception as e:
        report.vision_warnings.append(f"vision skipped: could not inspect pages ({type(e).__name__})")
        return
    for n, page in enumerate(pages):
        try:
            desc = describe_page(pdf_bytes, page, settings)
        except (VisionTimeout, VisionUnreachable) as e:
            left = len(pages) - n - 1
            more = f"; {left} more page(s) with images ingested text-only" if left else ""
            kind = "timed out" if isinstance(e, VisionTimeout) else "unreachable"
            report.vision_warnings.append(f"page {page}: vision endpoint {kind} ({e}); text only{more}")
            return
        except Exception as e:
            report.vision_warnings.append(f"page {page}: vision failed ({type(e).__name__}); text only")
            continue
        if desc:
            texts[page - 1] = (texts[page - 1].rstrip() + "\n\n" + VISION_HEADING.format(page=page)
                               + "\n" + desc).lstrip()
            report.vision_pages.append(page)
