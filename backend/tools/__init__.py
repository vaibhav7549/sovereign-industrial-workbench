"""LangChain tools for the /agent/query agent.

    from tools import ToolDeps, build_tools, select_tool_names
    tools = build_tools(deps, select_tool_names(encrypted_mode))

The logic lives in tools/core.py (no LangChain needed); this module only wraps it.
LangChain is imported lazily so the rest of the backend and the pure tests do not need it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .core import (  # noqa: F401  (re-exported)
    ToolDeps,
    check_url_allowed,
    extract_tool_calls,
    select_tool_names,
    urls_in_text,
)
from . import core


def build_tools(deps: ToolDeps, names: Optional[Sequence[str]] = None) -> List[Any]:
    """Return LangChain tools bound to `deps`, in the order of `names` (default: all)."""
    from langchain_core.tools import tool

    @tool
    async def search_knowledge(query: str) -> str:
        """Search the ENCRYPTED industrial knowledge base (uploaded plant documents, SOPs, manuals).
        The search runs on homomorphically encrypted embeddings; only the best matches are decrypted.
        Input: a short search query. Returns JSON list of {atom_id, title, page, score, text}."""
        return await core.search_knowledge_impl(deps, query)

    @tool
    async def search_mcp(query: str) -> str:
        """Semantic search over the Atomic knowledge graph (MCP semantic_search).
        Input: a short search query. Returns the graph's matching chunks as JSON."""
        return await core.search_mcp_impl(deps, query)

    @tool
    async def get_wiki_tool(tag: str) -> str:
        """Returns a synthesized wiki overview for a tag (a topic name such as "hydrocracking") from the knowledge graph with citations. Input is the tag name."""
        return await core.get_wiki_impl(deps, tag)

    @tool
    async def summarize_url(url: str, title: str = "") -> str:
        """Fetch a web page or paper and return an extractive (LexRank) summary.
        Only works for links the operator gave in the question or that came from the paper search.
        Input: the exact URL, optional title."""
        return await core.summarize_url_impl(deps, url, title)

    @tool
    async def ingest_pdf(filename: str) -> str:
        """Ingest a document from the server's ingest inbox into the knowledge base
        (encrypted when encryption is enabled). Input: the plain file name, e.g. "pump_manual.pdf".
        If the name is wrong, the reply lists the files that are available."""
        return await core.ingest_pdf_impl(deps, filename)

    @tool
    async def run_python_sandboxed(code: str, timeout_s: float = 5.0) -> str:
        """Run Python 3.11 code in an isolated sandbox and return its output.
        The sandbox has no network, a read-only filesystem except /work (32 MB), 256 MB RAM,
        half a CPU, at most 10 s, and only the standard library. Print what you need to see.
        Returns JSON {exit_code, stdout, stderr, timed_out, truncated, oom_killed, duration_ms}."""
        return await core.run_python_sandboxed_impl(deps, code, timeout_s)

    @tool
    def generate_word_report_tool(executive_summary: str, math_output: str) -> str:
        """Combines the LLM executive summary and the verified math output into a styled Word document."""
        return core.write_word_report(executive_summary, math_output)

    available: Dict[str, Any] = {t.name: t for t in (
        search_knowledge, search_mcp, get_wiki_tool, summarize_url, ingest_pdf, generate_word_report_tool,
        run_python_sandboxed)}
    wanted = list(names) if names is not None else list(available)
    unknown = [n for n in wanted if n not in available]
    if unknown:
        raise ValueError(f"unknown tool(s): {unknown}")
    return [available[n] for n in wanted]
