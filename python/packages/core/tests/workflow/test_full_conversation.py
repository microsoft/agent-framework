# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable
from typing import Any

from pydantic import PrivateAttr
from typing_extensions import Never

from agent_framework import (
    AgentExecutor,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Role,
    SequentialBuilder,
    TextContent,
    WorkflowBuilder,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)
from agent_framework._workflow._executor import AgentExecutorResponse, Executor
from agent_framework._workflow._workflow_context import WorkflowContext


class _SimpleAgent(BaseAgent):
    """Agent that returns a single assistant message (non-streaming path)."""

    def __init__(self, *, reply_text: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._reply_text = reply_text

    async def run(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text=self._reply_text)])

    async def run_stream(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        # This agent does not support streaming; yield a single complete response
        yield AgentRunResponseUpdate(contents=[TextContent(text=self._reply_text)])


class _CaptureFullConversation(Executor):
    """Captures AgentExecutorResponse.full_conversation and completes the workflow."""

    @handler
    async def capture(self, response: AgentExecutorResponse, ctx: WorkflowContext[Never, dict]) -> None:
        full = response.full_conversation
        # The AgentExecutor contract guarantees full_conversation is populated.
        assert full is not None
        payload = {
            "length": len(full),
            "roles": [m.role for m in full],
            "texts": [m.text for m in full],
        }
        await ctx.yield_output(payload)
        pass


async def test_agent_executor_populates_full_conversation_non_streaming() -> None:
    # Arrange: non-streaming AgentExecutor for deterministic response composition
    agent = _SimpleAgent(id="agent1", name="A", reply_text="agent-reply")
    agent_exec = AgentExecutor(agent, streaming=False, id="agent1-exec")
    capturer = _CaptureFullConversation(id="capture")

    wf = WorkflowBuilder().set_start_executor(agent_exec).add_edge(agent_exec, capturer).build()

    # Act: run with a simple user prompt
    completed = False
    output: dict | None = None
    async for ev in wf.run_stream("hello world"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = ev.data  # type: ignore[assignment]
        if completed and output is not None:
            break

    # Assert: full_conversation contains [user("hello world"), assistant("agent-reply")]
    assert completed
    assert output is not None
    payload = output
    assert isinstance(payload, dict)
    assert payload["length"] == 2
    assert payload["roles"][0] == Role.USER and "hello world" in (payload["texts"][0] or "")
    assert payload["roles"][1] == Role.ASSISTANT and "agent-reply" in (payload["texts"][1] or "")


class _CaptureAgent(BaseAgent):
    """Streaming-capable agent that records the messages it received."""

    _last_messages: list[ChatMessage] = PrivateAttr(default_factory=list)  # type: ignore

    def __init__(self, *, reply_text: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._reply_text = reply_text

    async def run(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        # Normalize and record messages for verification when running non-streaming
        norm: list[ChatMessage] = []
        if messages:
            for m in messages:  # type: ignore[iteration-over-optional]
                if isinstance(m, ChatMessage):
                    norm.append(m)
                elif isinstance(m, str):
                    norm.append(ChatMessage(role=Role.USER, text=m))
        self._last_messages = norm
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text=self._reply_text)])

    async def run_stream(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        # Normalize and record messages for verification when running streaming
        norm: list[ChatMessage] = []
        if messages:
            for m in messages:  # type: ignore[iteration-over-optional]
                if isinstance(m, ChatMessage):
                    norm.append(m)
                elif isinstance(m, str):
                    norm.append(ChatMessage(role=Role.USER, text=m))
        self._last_messages = norm
        yield AgentRunResponseUpdate(contents=[TextContent(text=self._reply_text)])


async def test_sequential_adapter_uses_full_conversation() -> None:
    # Arrange: two streaming agents; the second records what it receives
    a1 = _CaptureAgent(id="agent1", name="A1", reply_text="A1 reply")
    a2 = _CaptureAgent(id="agent2", name="A2", reply_text="A2 reply")

    wf = SequentialBuilder().participants([a1, a2]).build()

    # Act
    async for ev in wf.run_stream("hello seq"):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            break

    # Assert: second agent should have seen the user prompt and A1's assistant reply
    seen = a2._last_messages  # pyright: ignore[reportPrivateUsage]
    assert len(seen) == 2
    assert seen[0].role == Role.USER and "hello seq" in (seen[0].text or "")
    assert seen[1].role == Role.ASSISTANT and "A1 reply" in (seen[1].text or "")
