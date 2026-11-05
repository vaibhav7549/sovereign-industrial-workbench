"""Task 1: /agent/query end to end with a fake LLM (encryption off, so TenSEAL is not needed).

Checks that the response keeps its old shape plus tool_calls, that the agent really calls a tool,
and that the air-gapped fallback still works when the LLM is offline.
Needs fastapi + langchain (skipped otherwise; all present in the backend container).
"""

import importlib

import pytest

from conftest import MockAtomic

pytest.importorskip("fastapi")
pytest.importorskip("langchain_core")
pytest.importorskip("langchain_openai")

from fake_llm import ScriptedChatModel, answer, tool_call  # noqa: E402

OLD_KEYS = {"user", "query", "agent_response", "agent_thinking", "scholar_results"}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_ENABLED", "false")
    monkeypatch.setenv("ENCRYPTION_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SERPAPI_KEY", "")
    import main

    main = importlib.reload(main)
    atomic = MockAtomic()
    monkeypatch.setattr(main, "call_mcp_tool", atomic)

    async def no_init():
        return None

    async def no_scholar(kw):
        return []

    monkeypatch.setattr(main, "mcp_initialize", no_init)
    monkeypatch.setattr(main, "search_scholar", no_scholar)
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        c.main, c.atomic = main, atomic
        c.token = c.post("/login", params={"username": "operator.test"}).json()["token"]
        yield c


def use_llm(app, monkeypatch, llm):
    monkeypatch.setattr(app.main, "_build_llm", lambda *a, **k: llm)


def test_agent_calls_tool_and_reports_it(app, monkeypatch):
    llm = ScriptedChatModel(script=[
        tool_call("search_mcp", {"query": "pump seal leak"}),
        answer("Replace the mechanical seal."),
        answer("mechanical seal, centrifugal pump"),       # keyword extraction (plain LLM call)
    ])
    use_llm(app, monkeypatch, llm)
    r = app.post("/agent/query", params={"query": "Why does the pump seal leak?", "token": app.token}).json()

    assert OLD_KEYS <= set(r)
    assert r["agent_response"] == "Replace the mechanical seal."
    assert [c["name"] for c in r["tool_calls"]] == ["search_mcp"]
    assert r["tool_calls"][0]["args"] == {"query": "pump seal leak"}
    assert ("semantic_search", {"query": "pump seal leak"}) in app.atomic.received
    assert "search_mcp" in r["agent_thinking"]
    assert llm.bound_tool_names[0] == "search_mcp" and "search_knowledge" not in llm.bound_tool_names
    assert llm.calls == 3      # two agent turns + one keyword call; keywords did not re-run tools


def test_agent_without_tool_use_has_empty_tool_calls(app, monkeypatch):
    use_llm(app, monkeypatch, ScriptedChatModel(script=[answer("Hello."), answer("greeting")]))
    r = app.post("/agent/query", params={"query": "hi", "token": app.token}).json()
    assert r["agent_response"] == "Hello." and r["tool_calls"] == []


def test_llm_offline_fallback_still_works(app, monkeypatch):
    use_llm(app, monkeypatch, ScriptedChatModel(script=[answer("unused")], fail_with="connection refused"))
    r = app.post("/agent/query", params={"query": "compressor surge control", "token": app.token}).json()
    assert OLD_KEYS <= set(r)
    assert "Air-Gapped Fallback" in r["agent_response"]
    assert r["tool_calls"] == []


def test_ingest_tool_through_api_uses_inbox(app, monkeypatch, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    import pypdf

    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    with open(inbox / "blank.pdf", "wb") as f:
        w.write(f)
    llm = ScriptedChatModel(script=[tool_call("ingest_pdf", {"filename": "blank.pdf"}), answer("ingested"),
                                    answer("pdf")])
    use_llm(app, monkeypatch, llm)
    r = app.post("/agent/query", params={"query": "ingest blank.pdf", "token": app.token}).json()
    assert r["tool_calls"][0]["name"] == "ingest_pdf" and r["tool_calls"][0]["status"] == "success"
    assert any(tool == "create_atom" for tool, _ in app.atomic.received)


def test_summarize_tool_redirect_to_loopback_refused_end_to_end(app, monkeypatch):
    """Operator pastes a public link; it redirects to the backend's own loopback port.

    Goes through main._summarize_paper_impl. The refusal reaches the model as an error, the
    loopback URL is never requested, and nothing is cached for the URL.
    """
    import tools.core as core
    from test_agent_tools import FakeResp, FakeWeb

    public = "http://93.184.216.34/paper"          # IP literal: no DNS needed in the test
    web = FakeWeb({public: FakeResp(302, location="http://127.0.0.1:8000/agent/verify-encryption")})
    monkeypatch.setattr(core, "_default_http_get", web)
    llm = ScriptedChatModel(script=[tool_call("summarize_url", {"url": public}), answer("could not fetch"),
                                    answer("none")])
    use_llm(app, monkeypatch, llm)
    r = app.post("/agent/query", params={"query": f"summarize {public}", "token": app.token}).json()

    call = r["tool_calls"][0]
    assert call["name"] == "summarize_url"
    assert "refused" in call["result_preview"] and "127.0.0.1" in call["result_preview"]
    assert [u for u, _ in web.requested] == [public]
    assert public not in app.main.summary_cache


# ----------------------------------------------------------------------------- /agent/summarize
PAPER = "http://93.184.216.34/paper"   # IP literal, so the policy needs no DNS in tests


@pytest.fixture
def web(monkeypatch):
    """Replace the real HTTP client used by fetch_html_checked; records every outbound request."""
    import tools.core as core
    from test_agent_tools import FakeResp, FakeWeb

    w = FakeWeb({PAPER: FakeResp(302, location="http://127.0.0.1:8000/agent/verify-encryption")})
    w.FakeResp = FakeResp
    monkeypatch.setattr(core, "_default_http_get", w)
    return w


def summarize(app, token=None, url=PAPER):
    params = {"url": url, "title": "Paper"}
    if token is not None:
        params["token"] = token
    return app.post("/agent/summarize", params=params)


def test_summarize_without_token_is_401(app, web):
    app.main._remember_paper_url(PAPER)
    r = summarize(app)
    assert r.status_code == 401
    assert web.requested == []          # rejected before any outbound request


def test_summarize_with_invalid_token_is_401(app, web):
    app.main._remember_paper_url(PAPER)
    for bad in ("", "not-a-session", "00000000-0000-0000-0000-000000000000"):
        assert summarize(app, token=bad).status_code == 401
    assert web.requested == []


def test_summarize_redirect_to_loopback_is_refused(app, web):
    """Valid session, Scholar link, but the page 302s to the backend's own loopback port."""
    app.main._remember_paper_url(PAPER)
    r = summarize(app, token=app.token)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "refused"
    assert "hop 1 (http://127.0.0.1:8000/" in body["full_summary"][0]   # refused: not on the allow-list
    assert [u for u, _ in web.requested] == [PAPER]          # the loopback hop was never requested
    assert PAPER not in app.main.summary_cache               # refusals are not cached

    # Even if the loopback URL were on the allow-list, the address check still refuses it.
    app.main._remember_paper_url("http://127.0.0.1:8000/agent/verify-encryption")
    body = summarize(app, token=app.token).json()
    assert body["status"] == "refused" and "internal or private" in body["full_summary"][0]
    assert [u for u, _ in web.requested] == [PAPER, PAPER]   # still never the loopback hop


def test_summarize_link_not_from_scholar_is_refused(app, web):
    r = summarize(app, token=app.token, url="http://93.184.216.35/elsewhere")
    assert r.json()["status"] == "refused"
    assert web.requested == []


def test_summarize_allowed_link_is_fetched_once_without_auto_redirects(app, web):
    page = "<html><body>" + "<p>Anti-surge control protects centrifugal compressors from surge.</p>" * 20 + "</body></html>"
    web.routes[PAPER] = web.FakeResp(200, text=page)
    app.main._remember_paper_url(PAPER)
    r = summarize(app, token=app.token)
    assert r.status_code == 200 and r.json()["status"] in ("ok", "fallback")
    assert len(web.requested) == 1 and web.requested[0][1]["allow_redirects"] is False


# ----------------------------------------------------------------------------- /ingest/pdf OCR (Task 2)
def test_plain_ingest_pdf_reports_ocr_and_survives_page_failure(app, monkeypatch):
    """Encryption off: /ingest/pdf -> _ingest_plain_document -> pdf_text OCR fallback."""
    import io

    import pdf_text
    from test_pdf_ocr import LONG_TEXT, fake_ocr, make_text_pdf

    monkeypatch.setattr(pdf_text, "ocr_available", lambda: (True, ""))
    monkeypatch.setattr(pdf_text, "ocr_page_image",
                        fake_ocr({2: RuntimeError("boom"), 3: "Scanned flange torque table for page three"}))
    pdf = make_text_pdf([LONG_TEXT, "", ""])
    r = app.post("/ingest/pdf", params={"token": app.token},
                 files={"file": ("scan.pdf", io.BytesIO(pdf), "application/pdf")}).json()

    assert r["status"] == "success"
    assert r["ocr_pages"] == 1 and r["ocr_page_numbers"] == [3]
    assert r["ocr_warnings"] == ["page 2: OCR failed (RuntimeError: boom); kept pypdf text"]
    content = [a for t, a in app.atomic.received if t == "create_atom"][0]["content"]
    assert content.startswith("## Page 1\n") and "## Page 3\nScanned flange torque table" in content
    assert "## Page 2" not in content                    # failed page kept its (empty) pypdf text


# ----------------------------------------------------------------------------- /dummy_tool sandbox health (Task 3)
def test_dummy_tool_is_a_sandbox_health_check(app, monkeypatch):
    calls = []

    async def fake_run(code, timeout=5.0):
        calls.append((code, timeout))
        return {"exit_code": 0, "stdout": "2\n", "stderr": "", "timed_out": False, "truncated": False,
                "oom_killed": False, "duration_ms": 640}

    monkeypatch.setattr(app.main.sandbox_client, "run_code", fake_run)
    r = app.post("/dummy_tool", params={"input_val": "rm -rf /", "token": app.token}).json()
    assert calls == [("print(1+1)", 5)]                # fixed probe; input_val is never executed
    assert r["status"] == "success" and "print(1+1) -> 2" in r["message"] and r["sandbox"]["stdout"] == "2\n"


def test_dummy_tool_reports_sandbox_down(app, monkeypatch):
    async def down(code, timeout=5.0):
        return {"error": "sandbox-runner socket /ipc/runner.sock not found", "status": 503}

    monkeypatch.setattr(app.main.sandbox_client, "run_code", down)
    r = app.post("/dummy_tool", params={"input_val": "x", "token": app.token}).json()
    assert r["status"] == "error" and "not found" in r["message"]


def test_dummy_tool_still_requires_token(app):
    assert app.post("/dummy_tool", params={"input_val": "x", "token": "bogus"}).status_code == 401


# ----------------------------------------------------------------------------- router (Task 4)
def test_coding_query_gets_sandbox_only_agent(app, monkeypatch):
    runs = []

    async def fake_run(code, timeout=5.0):
        runs.append(code)
        return {"exit_code": 0, "stdout": "42\n", "stderr": "", "timed_out": False, "truncated": False,
                "oom_killed": False, "duration_ms": 500}

    monkeypatch.setattr(app.main.sandbox_client, "run_code", fake_run)
    llm = ScriptedChatModel(script=[tool_call("run_python_sandboxed", {"code": "print(6*7)"}),
                                    answer("The result is 42."), answer("python")])
    use_llm(app, monkeypatch, llm)
    r = app.post("/agent/query", params={"query": "write a python script that prints 6*7", "token": app.token}).json()

    assert llm.bound_tool_names == ["run_python_sandboxed"]          # nothing else is offered
    assert runs == ["print(6*7)"]
    assert r["route"]["label"] == "coding" and r["route"]["method"] == "keywords"
    assert r["agent_thinking"].splitlines()[0].startswith("🧭 Router: 'coding'")
    assert [c["name"] for c in r["tool_calls"]] == ["run_python_sandboxed"]
    assert OLD_KEYS | {"tool_calls", "route"} == set(r)               # shape: only 'route' added


def test_knowledge_query_keeps_current_agent(app, monkeypatch):
    llm = ScriptedChatModel(script=[answer("See SOP-12."), answer("pumps")])
    use_llm(app, monkeypatch, llm)
    r = app.post("/agent/query", params={"query": "what do my SOPs say about pumps", "token": app.token}).json()
    from tools import select_tool_names

    assert r["route"]["label"] == "knowledge"
    assert llm.bound_tool_names == select_tool_names(False)          # unchanged tool set
    assert "run_python_sandboxed" not in llm.bound_tool_names


def test_document_query_has_ingest_tools(app, monkeypatch):
    llm = ScriptedChatModel(script=[answer("ok"), answer("pdf")])
    use_llm(app, monkeypatch, llm)
    r = app.post("/agent/query", params={"query": "ingest pump_manual.pdf from the inbox", "token": app.token}).json()
    assert r["route"]["label"] == "document" and "ingest_pdf" in llm.bound_tool_names


def test_route_logged_in_fallback_trace(app, monkeypatch):
    use_llm(app, monkeypatch, ScriptedChatModel(script=[answer("x")], fail_with="connection refused"))
    r = app.post("/agent/query", params={"query": "write a python function to read a PDF", "token": app.token}).json()
    assert "Air-Gapped Fallback" in r["agent_response"]
    assert r["route"]["label"] == "coding" and r["agent_thinking"].startswith("🧭 Router: 'coding'")


# ----------------------------------------------------------------------------- vision in /ingest/pdf (Task 5)
def test_plain_ingest_pdf_stores_vision_description_under_heading(app, monkeypatch):
    import io

    import pdf_vision
    from test_pdf_ocr import HAVE_PIL_FONT, make_scanned_pdf

    if not HAVE_PIL_FONT:
        pytest.skip("Pillow with FreeType needed")
    monkeypatch.setenv("PDF_VISION_ENABLED", "true")
    monkeypatch.setenv("PDF_OCR_MIN_CHARS", "0")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(pdf_vision, "describe_page", lambda data, page, settings: "P&ID: pump P-101 to tank T-4.")
    r = app.post("/ingest/pdf", params={"token": app.token},
                 files={"file": ("pid.pdf", io.BytesIO(make_scanned_pdf()), "application/pdf")}).json()
    assert r["status"] == "success" and r["vision_pages"] == 1 and r["vision_warnings"] == []
    content = [a for t, a in app.atomic.received if t == "create_atom"][0]["content"]
    assert "## Page 1\n### Image description (vision model, page 1)\nP&ID: pump P-101 to tank T-4." in content


def test_plain_ingest_pdf_vision_unreachable_still_ingests(app, monkeypatch):
    import io

    import pdf_vision
    from test_pdf_ocr import LONG_TEXT, HAVE_PIL_FONT, concat_pdfs, make_scanned_pdf, make_text_pdf

    if not HAVE_PIL_FONT:
        pytest.skip("Pillow with FreeType needed")
    monkeypatch.setenv("PDF_VISION_ENABLED", "true")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")      # nothing listens on port 9

    def unreachable(data, page, settings):
        raise pdf_vision.VisionUnreachable("cannot connect to http://127.0.0.1:9/v1")

    monkeypatch.setattr(pdf_vision, "describe_page", unreachable)
    pdf = concat_pdfs(make_text_pdf([LONG_TEXT]), make_scanned_pdf())
    r = app.post("/ingest/pdf", params={"token": app.token},
                 files={"file": ("mixed.pdf", io.BytesIO(pdf), "application/pdf")}).json()
    assert r["status"] == "success" and r["vision_pages"] == 0
    assert "unreachable" in r["vision_warnings"][0]
