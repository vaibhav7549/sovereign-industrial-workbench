"""Task 1: agent tools without LangChain (tools/core.py).

Covers tool selection per mode, the summarize_url URL policy (prompt-injection exfiltration and
SSRF), the ingest inbox path policy, each tool body with fake dependencies, and trace parsing.
"""

import asyncio
import json
import os
from types import SimpleNamespace

import pytest

from tools import core
from tools.core import (ToolDeps, check_url_allowed, extract_tool_calls, resolve_inbox_file,
                        select_tool_names, urls_in_text)


def run(coro):
    return asyncio.run(coro)


async def public_dns(host):
    return ["93.184.216.34"]


class Recorder:
    def __init__(self, result=None, exc=None):
        self.calls, self.result, self.exc = [], result, exc

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.exc:
            raise self.exc
        return self.result


class FakePipeline:
    def __init__(self, results=None, exc=None):
        self.queries, self.results, self.exc = [], results or [], exc

    async def search(self, query, actor):
        self.queries.append((query, actor))
        if self.exc:
            raise self.exc
        return {"results": self.results}


def make_deps(tmp_path=None, **kw):
    base = dict(actor="op.test", mcp_call=Recorder({"ok": True}), summarize=Recorder({"title": "T", "status": "ok"}),
                ingest_bytes=Recorder({"status": "ingested_encrypted", "atom_id": "a1", "chunks": 2, "text": "x"}),
                inbox_dir=str(tmp_path) if tmp_path else "/nonexistent", resolve_host=public_dns)
    base.update(kw)
    return ToolDeps(**base)


# ----------------------------------------------------------------------------- selection
def test_encrypted_mode_never_offers_plaintext_atomic_tools():
    names = select_tool_names(encrypted_mode=True)
    assert "search_knowledge" in names
    assert "search_mcp" not in names and "get_wiki_tool" not in names
    assert {"summarize_url", "ingest_pdf"} <= set(names)


def test_plain_mode_uses_mcp_search():
    names = select_tool_names(encrypted_mode=False)
    assert names[0] == "search_mcp"
    assert "search_knowledge" not in names
    assert {"summarize_url", "ingest_pdf", "get_wiki_tool", "generate_word_report_tool"} <= set(names)


# ----------------------------------------------------------------------------- URL policy
def test_urls_in_text_strips_punctuation():
    assert urls_in_text("see https://arxiv.org/abs/1234.5678, and (http://x.org/a).") == {
        "https://arxiv.org/abs/1234.5678", "http://x.org/a"}


def test_allowed_url_passes():
    assert run(check_url_allowed("https://arxiv.org/abs/1", {"https://arxiv.org/abs/1/"}, public_dns)) is None


def test_url_not_from_operator_or_scholar_refused():
    """The prompt-injection case: a document tells the model to fetch an attacker URL."""
    reason = run(check_url_allowed("https://attacker.example/?d=SECRET", {"https://arxiv.org/abs/1"}, public_dns))
    assert reason and "not provided" in reason


@pytest.mark.parametrize("url", ["ftp://arxiv.org/x", "file:///etc/passwd", "https://user:pw@arxiv.org/x"])
def test_bad_scheme_or_credentials_refused_even_if_allowlisted(url):
    assert run(check_url_allowed(url, {url}, public_dns)) is not None


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/", "http://10.0.0.5/", "http://169.254.169.254/latest",
                                 "http://localhost:8080/mcp", "http://[::1]/", "http://printer.local/"])
def test_internal_targets_refused_even_if_allowlisted(url):
    assert run(check_url_allowed(url, {url}, public_dns)) is not None


def test_hostname_resolving_to_private_ip_refused():
    async def rebind(host):
        return ["10.1.2.3"]
    assert "private" in run(check_url_allowed("https://evil.example/", {"https://evil.example/"}, rebind))


def test_summarize_refusal_never_fetches():
    deps = make_deps(allowed_urls=set())
    out = json.loads(run(core.summarize_url_impl(deps, "https://attacker.example/?d=secret")))
    assert "refused" in out["error"]
    assert deps.summarize.calls == []


def test_summarize_allowed_fetches():
    deps = make_deps(allowed_urls={"https://arxiv.org/abs/1"})
    out = json.loads(run(core.summarize_url_impl(deps, "https://arxiv.org/abs/1", "Paper")))
    assert out["status"] == "ok"
    assert deps.summarize.calls[0][0][:2] == ("https://arxiv.org/abs/1", "Paper")


# ----------------------------------------------------------------------------- redirects (SSRF)
class FakeResp:
    def __init__(self, status=200, text="", location=None):
        self.status_code, self.text = status, text
        self.headers = {"Location": location} if location else {}
        self.closed = False

    def close(self):
        self.closed = True


class FakeWeb:
    """requests.get stand-in: a fixed map url -> response, recording every request made."""

    def __init__(self, routes):
        self.routes, self.requested = routes, []

    def __call__(self, url, **kwargs):
        self.requested.append((url, kwargs))
        if url not in self.routes:
            raise AssertionError(f"unexpected request to {url}")
        return self.routes[url]


PUBLIC = "https://papers.example/abs/1"


def test_redirect_to_loopback_is_refused_and_never_requested():
    """An allowed public URL answers 302 -> http://127.0.0.1:8080/mcp. The second hop must not run."""
    web = FakeWeb({PUBLIC: FakeResp(302, location="http://127.0.0.1:8080/mcp")})
    with pytest.raises(core.FetchRefused, match="internal or private"):
        # Loopback target is even allow-listed here, to show the address check holds on its own.
        run(core.fetch_html_checked(PUBLIC, {PUBLIC, "http://127.0.0.1:8080/mcp"}, public_dns, web))
    assert [u for u, _ in web.requested] == [PUBLIC]
    assert web.requested[0][1]["allow_redirects"] is False


def test_summarize_tool_refuses_redirect_to_loopback():
    """Same attack through the tool: summarize() gets a fetch that refuses the hop; nothing is fetched."""
    web = FakeWeb({PUBLIC: FakeResp(302, location="http://127.0.0.1/")})

    async def summarize_like_main(url, title, fetch):   # mirrors main._summarize_paper_impl's use of fetch
        return {"title": title, "status": "ok", "html": await fetch(url)}

    deps = make_deps(allowed_urls={PUBLIC}, summarize=summarize_like_main, http_get=web)
    out = json.loads(run(core.summarize_url_impl(deps, PUBLIC)))
    assert "refused" in out["error"] and "127.0.0.1" in out["error"]
    assert [u for u, _ in web.requested] == [PUBLIC]


def test_redirect_to_public_host_not_on_allow_list_is_refused():
    web = FakeWeb({PUBLIC: FakeResp(301, location="https://elsewhere.example/landing")})
    with pytest.raises(core.FetchRefused, match="not provided"):
        run(core.fetch_html_checked(PUBLIC, {PUBLIC}, public_dns, web))
    assert len(web.requested) == 1


def test_redirect_to_hostname_resolving_private_is_refused():
    target = "https://intranet.example/"

    async def split_dns(host):
        return ["10.0.0.7"] if host == "intranet.example" else ["93.184.216.34"]

    web = FakeWeb({PUBLIC: FakeResp(307, location=target)})
    with pytest.raises(core.FetchRefused, match="internal or private"):
        run(core.fetch_html_checked(PUBLIC, {PUBLIC, target}, split_dns, web))
    assert len(web.requested) == 1


def test_relative_redirect_within_allow_list_is_followed():
    final = "https://papers.example/abs/1v2"
    web = FakeWeb({PUBLIC: FakeResp(302, location="/abs/1v2"), final: FakeResp(200, text="<html>ok</html>")})
    assert run(core.fetch_html_checked(PUBLIC, {PUBLIC, final}, public_dns, web)) == "<html>ok</html>"
    assert [u for u, _ in web.requested] == [PUBLIC, final]
    assert all(kw["allow_redirects"] is False for _, kw in web.requested)
    assert all(r.closed for r in web.routes.values())


def test_redirect_loop_is_cut_off():
    a, b = "https://papers.example/a", "https://papers.example/b"
    web = FakeWeb({a: FakeResp(302, location=b), b: FakeResp(302, location=a)})
    with pytest.raises(core.FetchRefused, match="redirects"):
        run(core.fetch_html_checked(a, {a, b}, public_dns, web, max_redirects=3))
    assert len(web.requested) == 4   # first request + 3 redirects, then stop


def test_non_200_is_ordinary_failure_not_refusal():
    web = FakeWeb({PUBLIC: FakeResp(403)})
    with pytest.raises(Exception, match="HTTP 403") as e:
        run(core.fetch_html_checked(PUBLIC, {PUBLIC}, public_dns, web))
    assert not isinstance(e.value, core.FetchRefused)


# ----------------------------------------------------------------------------- inbox policy
@pytest.fixture
def inbox(tmp_path):
    box = tmp_path / "inbox"
    box.mkdir()
    (box / "pump_manual.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "secret.pdf").write_bytes(b"outside")
    (box / "link.pdf").symlink_to(tmp_path / "secret.pdf")
    return box


@pytest.mark.parametrize("name", ["../secret.pdf", "/etc/passwd", "sub/x.pdf", "..", "", "notes.exe", "link.pdf"])
def test_inbox_rejects_paths_symlinks_and_types(inbox, name):
    with pytest.raises((ValueError, FileNotFoundError)):
        resolve_inbox_file(str(inbox), name)


def test_inbox_accepts_plain_name(inbox):
    assert resolve_inbox_file(str(inbox), "pump_manual.pdf") == os.path.realpath(inbox / "pump_manual.pdf")


def test_ingest_tool_reads_inbox_file_and_trims_result(inbox):
    deps = make_deps(inbox)
    out = json.loads(run(core.ingest_pdf_impl(deps, "pump_manual.pdf")))
    assert out == {"status": "ingested_encrypted", "atom_id": "a1", "chunks": 2}   # no other fields leak
    (name, data, actor), _ = deps.ingest_bytes.calls[0]
    assert (name, data, actor) == ("pump_manual.pdf", b"%PDF-1.4 fake", "op.test")


def test_ingest_tool_unknown_file_lists_available(inbox):
    out = json.loads(run(core.ingest_pdf_impl(make_deps(inbox), "missing.pdf")))
    assert "pump_manual.pdf" in out["available"]


def test_ingest_tool_traversal_refused_without_reading(inbox):
    deps = make_deps(inbox)
    out = json.loads(run(core.ingest_pdf_impl(deps, "../secret.pdf")))
    assert "error" in out and deps.ingest_bytes.calls == []


def test_ingest_tool_size_limit(inbox):
    deps = make_deps(inbox, max_upload_bytes=4)
    assert "limit" in json.loads(run(core.ingest_pdf_impl(deps, "pump_manual.pdf")))["error"]
    assert deps.ingest_bytes.calls == []


# ----------------------------------------------------------------------------- search tools
def test_search_knowledge_without_pipeline():
    assert "not enabled" in json.loads(run(core.search_knowledge_impl(make_deps(), "q")))["error"]


def test_search_knowledge_returns_trimmed_results():
    pipe = FakePipeline([{"atom_id": "a", "title": "t.pdf", "page": 2, "score": 0.9, "text": "x" * 5000,
                          "doc_id": "d", "chunk_index": 0}])
    out = json.loads(run(core.search_knowledge_impl(make_deps(pipeline=pipe), "surge")))
    assert out[0]["title"] == "t.pdf" and len(out[0]["text"]) == core.KNOWLEDGE_TEXT_CHARS
    assert set(out[0]) == {"atom_id", "title", "page", "score", "text"}
    assert pipe.queries == [("surge", "op.test")]


def test_search_knowledge_error_hides_details():
    pipe = FakePipeline(exc=RuntimeError("key material: deadbeef"))
    out = run(core.search_knowledge_impl(make_deps(pipeline=pipe), "q"))
    assert "RuntimeError" in out and "deadbeef" not in out


def test_search_mcp_calls_semantic_search():
    deps = make_deps()
    run(core.search_mcp_impl(deps, "valve"))
    assert deps.mcp_call.calls[0][0] == ("semantic_search", {"query": "valve"})


# ----------------------------------------------------------------------------- trace
def test_extract_tool_calls_pairs_results():
    msgs = [
        SimpleNamespace(content="q"),
        SimpleNamespace(content="", tool_calls=[{"name": "search_mcp", "args": {"query": "v"}, "id": "c1"},
                                                 {"name": "ingest_pdf", "args": {"filename": "a.pdf"}, "id": "c2"}]),
        SimpleNamespace(content="r" * 500, tool_call_id="c1", name="search_mcp", status="success"),
        SimpleNamespace(content="final answer"),
    ]
    calls = extract_tool_calls(msgs)
    assert [c["name"] for c in calls] == ["search_mcp", "ingest_pdf"]
    assert calls[0]["status"] == "success" and calls[0]["result_preview"].endswith("...")
    assert len(calls[0]["result_preview"]) == core.RESULT_PREVIEW_CHARS + 3
    assert calls[1]["status"] == "no_result" and calls[1]["result_preview"] is None


def test_extract_tool_calls_no_tools():
    assert extract_tool_calls([SimpleNamespace(content="hi"), SimpleNamespace(content="answer")]) == []
