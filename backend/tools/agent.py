"""Build a tool-calling agent with whichever LangChain API is installed.

langchain >= 1.0:  langchain.agents.create_agent(model=..., tools=..., system_prompt=...)
older:             langgraph.prebuilt.create_react_agent(model, tools, prompt=...)

The two take the system prompt under different keyword names. Passing system_prompt= to
create_react_agent raises TypeError, which /agent/query used to report as "LLM offline".
"""

from __future__ import annotations

from typing import Any, Sequence


def create_tool_agent(llm: Any, tools: Sequence[Any], system_prompt: str) -> Any:
    try:
        from langchain.agents import create_agent
    except ImportError:
        create_agent = None
    if create_agent is not None:
        return create_agent(model=llm, tools=list(tools), system_prompt=system_prompt)

    from langgraph.prebuilt import create_react_agent

    return create_react_agent(llm, list(tools), prompt=system_prompt)
