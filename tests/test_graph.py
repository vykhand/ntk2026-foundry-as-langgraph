"""Graph wiring test with a scripted fake model — no network, no Foundry."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import MessagesState

from agent.contract import extract_agenda, resolve_items
from agent.graph import build_graph
from agent.metrics import evaluate_agenda
from agent.program import load_program

ACT1_QUESTION = "Sestavi mi urnik za torek — zanima me AI in Azure, nič pred deveto, pusti mi luknjo za kavo."


class ScriptedToolModel(BaseChatModel):
    """Replays a fixed list of AI messages; records what it was asked."""

    script: list[AIMessage]
    calls: list[list[BaseMessage]] = []
    bound_tools: list[Any] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):  # type: ignore[override]
        self.bound_tools = list(tools)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        message = self.script.pop(0)
        return ChatResult(generations=[ChatGeneration(message=message)])


def _tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


async def test_graph_runs_the_react_loop_and_honours_the_output_contract():
    program = load_program()
    tuesday_ai = program.search(track="AI", day="torek", limit=80)
    pick = [t for t in tuesday_ai if t["start"] >= "2026-09-22T09:00"][:3]
    ids = [t["id"] for t in pick]
    final_text = (
        "Tukaj je urnik.\n```json\n"
        + json.dumps({"day": "2026-09-22", "attendee": "maja", "items": [{"id": i} for i in ids]})
        + "\n```\nDopoldne so tri predavanja o umetni inteligenci."
    )
    model = ScriptedToolModel(
        script=[
            _tool_call("preferences", {}, "c1"),
            _tool_call("program_search", {"track": "AI", "day": "torek", "limit": 80}, "c2"),
            _tool_call("clash_checker", {"talk_ids": ids}, "c3"),
            AIMessage(content=final_text),
        ]
    )
    graph = build_graph(model, system_prompt="TEST PROMPT")

    result = await graph.ainvoke({"messages": [HumanMessage(content=ACT1_QUESTION)]})
    messages = result["messages"]

    # MessagesState contract: the hosting layer reads this turn's messages back out.
    assert graph.builder.state_schema is MessagesState
    assert isinstance(messages[-1], AIMessage) and messages[-1].content == final_text
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    assert [m.name for m in tool_messages] == ["preferences", "program_search", "clash_checker"]

    # Tools ran for real against the fixtures.
    prefs = json.loads(tool_messages[0].content)
    assert prefs["id"] == "maja"
    clash = json.loads(tool_messages[2].content)
    assert clash["unknown_ids"] == [] and "clash_count" in clash

    # The system prompt is prepended on every model call but never stored in state.
    for call in model.calls:
        assert isinstance(call[0], SystemMessage) and call[0].content == "TEST PROMPT"
    assert not any(isinstance(m, SystemMessage) for m in messages)
    assert {t.name for t in model.bound_tools} == {"program_search", "clash_checker", "preferences"}

    # Evals can score the structured output using program-authoritative times.
    agenda = extract_agenda(messages[-1].content)
    assert agenda is not None
    resolved = resolve_items(agenda, program.get)
    assert resolved["unknown_ids"] == []
    report = evaluate_agenda(resolved["items"], {"constraints": {"earliest_start": "09:00"}})
    assert report["items"] == 3
    assert report["clash_count"] == clash["clash_count"]


async def test_graph_without_tool_calls_ends_after_one_model_turn():
    model = ScriptedToolModel(script=[AIMessage(content="Živjo! Kako ti lahko pomagam?")])
    graph = build_graph(model, system_prompt="TEST PROMPT")
    result = await graph.ainvoke({"messages": [HumanMessage(content="Živjo")]})
    assert len(result["messages"]) == 2
    assert len(model.calls) == 1
