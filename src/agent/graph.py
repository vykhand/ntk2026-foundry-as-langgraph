"""The NTK asistent graph — plain LangGraph, model injected, nothing Foundry-specific.

    START → assistant ─┬─(tool calls)→ tools ────────────→ assistant …
                       └─(answer)────→ guard ─┬─(bad)────→ assistant
                                              └─(ok)─────→ END

State is ``MessagesState`` (a ``messages`` channel with the add-messages reducer),
which is the contract the hosting layer relies on: it feeds the conversation in
as messages and reads this turn's new messages back out.

``guard`` is optional (``enforce_constraints``) and off by default, so versions 1–3 keep the
two-node shape. It re-reads the agenda the model just wrote and sends it back when it breaks a
constraint — see ``agent.guard`` for why that is a node and not a sentence in the prompt.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from agent import guard
from agent.prompt import load_system_prompt
from agent.tools import default_tools

log = logging.getLogger("ntk.guard")


def build_graph(
    model: BaseChatModel,
    *,
    system_prompt: str | None = None,
    tools: Sequence[BaseTool] | None = None,
    enforce_constraints: bool = False,
) -> CompiledStateGraph:
    """Compile the agent graph around any LangChain chat model that supports tool calling."""
    toolset = list(tools) if tools is not None else default_tools()
    prompt = system_prompt if system_prompt is not None else load_system_prompt()
    model_with_tools = model.bind_tools(toolset)

    async def assistant(state: MessagesState) -> dict:
        response = await model_with_tools.ainvoke([SystemMessage(content=prompt), *state["messages"]])
        return {"messages": [response]}

    def guard_node(state: MessagesState) -> dict:
        """Score the answer the model just wrote; hand the violations back, or pass.

        Every decision is logged, including the passes: an approval and a guard that never ran
        look identical from the outside, which is how the residual failures in S-08b went
        unexplained for a day. ``attendee_source`` is the field that earns its keep.

        ``RemoveMessage`` drops the rejected answer from state, and **that does not un-send it**
        (S-08e). The Foundry hosting layer always drives the graph with ``astream`` and converts
        node updates to Responses events as they happen, so every assistant turn is already on
        the wire by the time the guard forms an opinion about it. The removal still keeps the
        conversation clean for later turns; the caller sees the draft *and* the repair, which is
        why ``contract.extract_agenda`` takes the last agenda and not the first.
        """
        attempt = guard.corrections_so_far(state["messages"]) + 1
        question = guard.asked(state["messages"])[:64]
        verdict = guard.inspect_state(state)
        problems = verdict["problems"]
        if attempt > guard.MAX_CORRECTIONS:
            log.info(guard.format_verdict(verdict, decision="give-up", q=question, attempt=attempt))
            return {"messages": []}
        if not verdict.get("agenda"):
            log.info(guard.format_verdict(verdict, decision="no-agenda", q=question, attempt=attempt))
            return {"messages": []}
        if not problems:
            log.info(guard.format_verdict(verdict, decision="pass", q=question, attempt=attempt))
            return {"messages": []}
        log.info(guard.format_verdict(verdict, decision="reject", q=question, attempt=attempt))
        rejected = state["messages"][-1]
        out: list = []
        if getattr(rejected, "id", None):
            out.append(RemoveMessage(id=rejected.id))
        out.append(HumanMessage(content=guard.correction_message(problems)))
        return {"messages": out}

    def after_guard(state: MessagesState) -> str:
        last = state["messages"][-1]
        content = last.content if isinstance(last.content, str) else ""
        return "assistant" if guard.CORRECTION_MARKER in content else END

    def route(state: MessagesState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return "guard" if enforce_constraints else END

    builder = StateGraph(MessagesState)
    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode(toolset))
    builder.add_edge(START, "assistant")
    builder.add_edge("tools", "assistant")
    if enforce_constraints:
        builder.add_node("guard", guard_node)
        builder.add_conditional_edges("assistant", route, {"tools": "tools", "guard": "guard"})
        builder.add_conditional_edges("guard", after_guard, {"assistant": "assistant", END: END})
    else:
        builder.add_conditional_edges("assistant", route, {"tools": "tools", END: END})
    return builder.compile()


__all__ = ["build_graph"]
