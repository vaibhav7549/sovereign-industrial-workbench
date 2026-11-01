"""A scripted chat model for agent tests (needs langchain_core).

Each call to the model returns the next scripted reply; replies may contain tool calls.
bind_tools() records which tools the agent bound, which is what the binding tests assert on.
"""

from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def tool_call(name: str, args: Dict[str, Any], call_id: str = "call_1") -> Dict[str, Any]:
    return {"content": "", "tool_calls": [{"name": name, "args": args, "id": call_id, "type": "tool_call"}]}


def answer(text: str) -> Dict[str, Any]:
    return {"content": text}


class ScriptedChatModel(BaseChatModel):
    script: List[Dict[str, Any]]
    calls: int = 0
    bound_tool_names: List[str] = []
    fail_with: Optional[str] = None   # raise ConnectionError(fail_with) on every call (LLM offline)

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        names = []
        for t in tools:
            if isinstance(t, dict):
                names.append(t.get("name") or t.get("function", {}).get("name"))
            else:
                names.append(getattr(t, "name", None))
        self.bound_tool_names = names
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self.fail_with:
            raise ConnectionError(self.fail_with)
        step = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        msg = AIMessage(content=step.get("content", ""), tool_calls=step.get("tool_calls", []))
        return ChatResult(generations=[ChatGeneration(message=msg)])
