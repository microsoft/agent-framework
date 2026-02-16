# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable, Sequence
from typing import Any

from pydantic import PrivateAttr
from typing_extensions import Never

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    Executor,
    Message,
    ResponseStream,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowRunState,
    handler,
)
from agent_framework.orchestrations import SequentialBuilder


class _SimpleAgent(BaseAgent):
    """Agent that returns a single assistant message."""

    def __init__(self, *, reply_text: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._reply_text = reply_text

    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=[Content.from_text(text=self._reply_text)])

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", [self._reply_text])])

        return _run()


class _CaptureFullConversation(Executor):
    """Captures AgentExecutorResponse.full_conversation and completes the workflow."""

    @handler
    async def capture(self, response: AgentExecutorResponse, ctx: WorkflowContext[Never, dict[str, Any]]) -> None:
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
    # Arrange: AgentExecutor will be non-streaming when using workflow.run()
    agent = _SimpleAgent(id="agent1", name="A", reply_text="agent-reply")
    agent_exec = AgentExecutor(agent, id="agent1-exec")
    capturer = _CaptureFullConversation(id="capture")

    wf = WorkflowBuilder(start_executor=agent_exec, output_executors=[capturer]).add_edge(agent_exec, capturer).build()

    # Act: use run() to test non-streaming mode
    result = await wf.run("hello world")

    # Extract output from run result
    outputs = result.get_outputs()
    assert len(outputs) == 1
    payload = outputs[0]

    # Assert: full_conversation contains [user("hello world"), assistant("agent-reply")]
    assert isinstance(payload, dict)
    assert payload["length"] == 2
    assert payload["roles"][0] == "user" and "hello world" in (payload["texts"][0] or "")
    assert payload["roles"][1] == "assistant" and "agent-reply" in (payload["texts"][1] or "")


class _CaptureAgent(BaseAgent):
    """Streaming-capable agent that records the messages it received."""

    _last_messages: list[Message] = PrivateAttr(default_factory=list)  # type: ignore

    def __init__(self, *, reply_text: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._reply_text = reply_text

    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        # Normalize and record messages for verification
        norm: list[Message] = []
        if messages:
            for m in messages:  # type: ignore[iteration-over-optional]
                if isinstance(m, Message):
                    norm.append(m)
                elif isinstance(m, str):
                    norm.append(Message("user", [m]))
        self._last_messages = norm

        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=[Content.from_text(text=self._reply_text)])

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", [self._reply_text])])

        return _run()


async def test_sequential_adapter_uses_full_conversation() -> None:
    # Arrange: two streaming agents; the second records what it receives
    a1 = _CaptureAgent(id="agent1", name="A1", reply_text="A1 reply")
    a2 = _CaptureAgent(id="agent2", name="A2", reply_text="A2 reply")

    wf = SequentialBuilder(participants=[a1, a2]).build()

    # Act
    async for ev in wf.run("hello seq", stream=True):
        if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
            break

    # Assert: second agent should have seen the user prompt and A1's assistant reply
    seen = a2._last_messages  # pyright: ignore[reportPrivateUsage]
    assert len(seen) == 2
    assert seen[0].role == "user" and "hello seq" in (seen[0].text or "")
    assert seen[1].role == "assistant" and "A1 reply" in (seen[1].text or "")


class _RoundTripCoordinator(Executor):
    """Loops once back to the same agent with full conversation + feedback."""

    def __init__(self, *, target_agent_id: str, id: str = "round_trip_coordinator") -> None:
        super().__init__(id=id)
        self._target_agent_id = target_agent_id
        self._seen = 0

    @handler
    async def handle_response(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[Never, dict[str, Any]],
    ) -> None:
        self._seen += 1
        if self._seen == 1:
            assert response.full_conversation is not None
            await ctx.send_message(
                AgentExecutorRequest(
                    messages=list(response.full_conversation) + [Message(role="user", text="apply feedback")],
                    should_respond=True,
                ),
                target_id=self._target_agent_id,
            )
            return

        assert response.full_conversation is not None
        await ctx.yield_output({
            "roles": [m.role for m in response.full_conversation],
            "texts": [m.text for m in response.full_conversation],
        })


async def test_agent_executor_full_conversation_round_trip_does_not_duplicate_history() -> None:
    """When full history is replayed, AgentExecutor should not duplicate prior turns."""
    agent = _SimpleAgent(id="writer_agent", name="Writer", reply_text="draft reply")
    agent_exec = AgentExecutor(agent, id="writer_agent")
    coordinator = _RoundTripCoordinator(target_agent_id="writer_agent")

    wf = (
        WorkflowBuilder(start_executor=agent_exec, output_executors=[coordinator])
        .add_edge(agent_exec, coordinator)
        .add_edge(coordinator, agent_exec)
        .build()
    )

    result = await wf.run("initial prompt")
    outputs = result.get_outputs()
    assert len(outputs) == 1
    payload = outputs[0]
    assert isinstance(payload, dict)

    # Expected conversation after one loop:
    # user(initial), assistant(first reply), user(feedback), assistant(second reply)
    assert payload["roles"] == ["user", "assistant", "user", "assistant"]
    assert payload["texts"][0] == "initial prompt"
    assert payload["texts"][1] == "draft reply"
    assert payload["texts"][2] == "apply feedback"
    assert payload["texts"][3] == "draft reply"
