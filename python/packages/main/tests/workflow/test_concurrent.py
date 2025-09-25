# Copyright (c) Microsoft. All rights reserved.

from typing import Any, cast

import pytest

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
    ChatMessage,
    ConcurrentBuilder,
    Executor,
    Role,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)


class _FakeAgentExec(Executor):
    """Test executor that mimics an agent by emitting an AgentExecutorResponse.

    It takes the incoming AgentExecutorRequest, produces a single assistant message
    with the configured reply text, and sends an AgentExecutorResponse that includes
    full_conversation (the original user prompt followed by the assistant message).
    """

    def __init__(self, id: str, reply_text: str) -> None:
        super().__init__(id)
        self._reply_text = reply_text

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        response = AgentRunResponse(messages=ChatMessage(Role.ASSISTANT, text=self._reply_text))
        full_conversation = list(request.messages) + list(response.messages)
        await ctx.send_message(AgentExecutorResponse(self.id, response, full_conversation=full_conversation))


def test_concurrent_builder_rejects_empty_participants() -> None:
    with pytest.raises(ValueError):
        ConcurrentBuilder().participants([])


def test_concurrent_builder_rejects_duplicate_executors() -> None:
    a = _FakeAgentExec("dup", "A")
    b = _FakeAgentExec("dup", "B")  # same executor id
    with pytest.raises(ValueError):
        ConcurrentBuilder().participants([a, b])


async def test_concurrent_default_aggregator_emits_single_user_and_assistants() -> None:
    # Three synthetic agent executors
    e1 = _FakeAgentExec("agentA", "Alpha")
    e2 = _FakeAgentExec("agentB", "Beta")
    e3 = _FakeAgentExec("agentC", "Gamma")

    wf = ConcurrentBuilder().participants([e1, e2, e3]).build()

    completed = False
    output: list[ChatMessage] | None = None
    async for ev in wf.run_stream("prompt: hello world"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = cast(list[ChatMessage], ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    messages: list[ChatMessage] = output

    # Expect one user message + one assistant message per participant
    assert len(messages) == 1 + 3
    assert messages[0].role == Role.USER
    assert "hello world" in messages[0].text

    assistant_texts = {m.text for m in messages[1:]}
    assert assistant_texts == {"Alpha", "Beta", "Gamma"}
    assert all(m.role == Role.ASSISTANT for m in messages[1:])


async def test_concurrent_custom_aggregator_callback_is_used() -> None:
    # Two synthetic agent executors for brevity
    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    async def summarize(results: list[AgentExecutorResponse]) -> str:
        texts: list[str] = []
        for r in results:
            msgs: list[ChatMessage] = r.agent_run_response.messages
            texts.append(msgs[-1].text if msgs else "")
        return " | ".join(sorted(texts))

    wf = ConcurrentBuilder().participants([e1, e2]).with_aggregator(summarize).build()

    completed = False
    output: str | None = None
    async for ev in wf.run_stream("prompt: custom"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = cast(str, ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    # Custom aggregator returns a string payload
    assert isinstance(output, str)
    assert output == "One | Two"


async def test_concurrent_custom_aggregator_sync_callback_is_used() -> None:
    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    # Sync callback with ctx parameter (should run via asyncio.to_thread)
    def summarize_sync(results: list[AgentExecutorResponse], _ctx: WorkflowContext[Any]) -> str:  # type: ignore[unused-argument]
        texts: list[str] = []
        for r in results:
            msgs: list[ChatMessage] = r.agent_run_response.messages
            texts.append(msgs[-1].text if msgs else "")
        return " | ".join(sorted(texts))

    wf = ConcurrentBuilder().participants([e1, e2]).with_aggregator(summarize_sync).build()

    completed = False
    output: str | None = None
    async for ev in wf.run_stream("prompt: custom sync"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = cast(str, ev.data)
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    assert isinstance(output, str)
    assert output == "One | Two"


def test_concurrent_custom_aggregator_uses_callback_name_for_id() -> None:
    e1 = _FakeAgentExec("agentA", "One")
    e2 = _FakeAgentExec("agentB", "Two")

    def summarize(results: list[AgentExecutorResponse]) -> str:  # type: ignore[override]
        return str(len(results))

    wf = ConcurrentBuilder().participants([e1, e2]).with_aggregator(summarize).build()

    assert "summarize" in wf.executors
    aggregator = wf.executors["summarize"]
    assert aggregator.id == "summarize"
