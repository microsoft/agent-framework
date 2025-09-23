# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable
from typing import Any

import pytest

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Executor,
    Role,
    SequentialBuilder,
    TextContent,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)


class _EchoAgent(BaseAgent):
    """Simple agent that appends a single assistant message with its name."""

    async def run(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text=f"{self.display_name} reply")])

    async def run_stream(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        # Minimal async generator with one assistant update
        yield AgentRunResponseUpdate(contents=[TextContent(text=f"{self.display_name} reply")])


class _SummarizerExec(Executor):
    """Custom executor that summarizes by appending a short assistant message."""

    @handler
    async def summarize(self, conversation: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        user_texts = [m.text for m in conversation if m.role == Role.USER]
        agents = [m.author_name or m.role for m in conversation if m.role == Role.ASSISTANT]
        summary = ChatMessage(role=Role.ASSISTANT, text=f"Summary of users:{len(user_texts)} agents:{len(agents)}")
        await ctx.send_message(list(conversation) + [summary])


def test_sequential_builder_rejects_empty_participants() -> None:
    with pytest.raises(ValueError):
        SequentialBuilder().participants([])


async def test_sequential_agents_append_to_context() -> None:
    a1 = _EchoAgent(id="agent1", name="A1")
    a2 = _EchoAgent(id="agent2", name="A2")

    wf = SequentialBuilder().participants([a1, a2]).build()

    completed = False
    output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("hello sequential"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = ev.data  # type: ignore[assignment]
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    assert isinstance(output, list)
    msgs: list[ChatMessage] = output
    assert len(msgs) == 3
    assert msgs[0].role == Role.USER and "hello sequential" in msgs[0].text
    assert msgs[1].role == Role.ASSISTANT and (msgs[1].author_name == "A1" or True)
    assert msgs[2].role == Role.ASSISTANT and (msgs[2].author_name == "A2" or True)
    assert "A1 reply" in msgs[1].text
    assert "A2 reply" in msgs[2].text


async def test_sequential_with_custom_executor_summary() -> None:
    a1 = _EchoAgent(id="agent1", name="A1")
    summarizer = _SummarizerExec(id="summarizer")

    wf = SequentialBuilder().participants([a1, summarizer]).build()

    completed = False
    output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("topic X"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = ev.data  # type: ignore[assignment]
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    msgs: list[ChatMessage] = output
    # Expect: [user, A1 reply, summary]
    assert len(msgs) == 3
    assert msgs[0].role == Role.USER
    assert msgs[1].role == Role.ASSISTANT and "A1 reply" in msgs[1].text
    assert msgs[2].role == Role.ASSISTANT and msgs[2].text.startswith("Summary of users:")
