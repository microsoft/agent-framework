# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any, Literal, overload

import pytest
from pydantic import PrivateAttr
from typing_extensions import Never

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    BaseAgent,
    Content,
    Executor,
    Message,
    ResponseStream,
    ServiceSessionId,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowRunState,
    executor,
    handler,
)


class _SimpleAgent(BaseAgent):
    """Agent that returns a single assistant message."""

    def __init__(self, *, reply_text: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._reply_text = reply_text

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...
    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[True],
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(contents=[Content.from_text(text=self._reply_text)])

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", [self._reply_text])])

        return _run()


class _ToolHistoryAgent(BaseAgent):
    """Agent that emits tool-call internals plus a final assistant summary."""

    def __init__(self, *, summary_text: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._summary_text = summary_text

    def _messages(self) -> list[Message]:
        return [
            Message(
                role="assistant",
                contents=[
                    Content.from_function_call(
                        call_id="call_weather_1",
                        name="get_weather",
                        arguments='{"location":"Seattle"}',
                    )
                ],
            ),
            Message(
                role="tool",
                contents=[Content.from_function_result(call_id="call_weather_1", result="Sunny, 72F")],
            ),
            Message(role="assistant", contents=[Content.from_text(text=self._summary_text)]),
        ]

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...
    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[True],
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(
                    contents=[
                        Content.from_function_call(
                            call_id="call_weather_1",
                            name="get_weather",
                            arguments='{"location":"Seattle"}',
                        )
                    ],
                    role="assistant",
                )
                yield AgentResponseUpdate(
                    contents=[Content.from_function_result(call_id="call_weather_1", result="Sunny, 72F")],
                    role="tool",
                )
                yield AgentResponseUpdate(contents=[Content.from_text(text=self._summary_text)], role="assistant")

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=self._messages())

        return _run()


class _CaptureFullConversation(Executor):
    """Captures AgentExecutorResponse.full_conversation and completes the workflow."""

    @handler
    async def capture(self, response: AgentExecutorResponse, ctx: WorkflowContext[Never, dict[str, Any]]) -> None:  # type: ignore[valid-type]
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

    wf = WorkflowBuilder(start_executor=agent_exec, output_from=[capturer]).add_edge(agent_exec, capturer).build()

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

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...
    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[True],
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        # Normalize and record messages for verification
        norm: list[Message] = []
        if messages:
            for m in messages:  # type: ignore[iteration-over-optional, union-attr]  # ty: ignore[not-iterable]
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
    pytest.importorskip("agent_framework_orchestrations")
    from agent_framework.orchestrations import SequentialBuilder

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


async def test_sequential_handoff_preserves_function_call_for_non_reasoning_model() -> None:
    pytest.importorskip("agent_framework_orchestrations")
    from agent_framework.orchestrations import SequentialBuilder

    # Arrange: non-reasoning agent emits function_call + function_result + summary
    first = _ToolHistoryAgent(
        id="tool_history_agent",
        name="ToolHistory",
        summary_text="The weather in Seattle is sunny and 72F.",
    )
    second = _CaptureAgent(id="capture_agent", name="Capture", reply_text="Captured")
    wf = SequentialBuilder(participants=[first, second]).build()

    # Act
    result = await wf.run("Check weather and continue")

    # Assert workflow completed
    outputs = result.get_outputs()
    assert outputs

    # For non-reasoning models (no text_reasoning), function_call and function_result are
    # both kept so the receiving agent has the full call/result pair as context.
    seen = second._last_messages  # pyright: ignore[reportPrivateUsage]
    assert len(seen) == 4  # user, assistant(function_call), tool(function_result), assistant(summary)
    assert seen[0].role == "user"
    assert "Check weather and continue" in (seen[0].text or "")
    assert seen[1].role == "assistant"
    assert any(content.type == "function_call" for content in seen[1].contents)
    assert seen[2].role == "tool"
    assert any(content.type == "function_result" for content in seen[2].contents)
    assert seen[3].role == "assistant"
    assert "Seattle is sunny" in (seen[3].text or "")
    # No text_reasoning should appear (non-reasoning model)
    assert all(content.type != "text_reasoning" for msg in seen for content in msg.contents)


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
        ctx: WorkflowContext[AgentExecutorRequest, dict[str, Any]],
    ) -> None:
        self._seen += 1
        if self._seen == 1:
            assert response.full_conversation is not None
            await ctx.send_message(
                AgentExecutorRequest(
                    messages=list(response.full_conversation) + [Message(role="user", contents=["apply feedback"])],
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
        WorkflowBuilder(start_executor=agent_exec, output_from=[coordinator])
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


class _SessionIdCapturingAgent(BaseAgent):
    """Records service_session_id of the session at run() time."""

    _captured_service_session_id: str | ServiceSessionId | None = PrivateAttr(default="NOT_CAPTURED")

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...
    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[True],
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        self._captured_service_session_id = session.service_session_id if session else None

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", ["done"])])

        return _run()


class _FullHistoryReplayCoordinator(Executor):
    """Coordinator that pre-sets service_session_id on a target executor then sends it
    an AgentExecutorRequest carrying either the full conversation (including function
    calls) or just a new user turn."""

    def __init__(self, *, target_exec: AgentExecutor, include_history: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._target_exec = target_exec
        self._include_history = include_history

    @handler
    async def handle(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[AgentExecutorRequest, Any],
    ) -> None:
        if self._include_history:
            full_conv = list(response.full_conversation or response.agent_response.messages)
        else:
            full_conv = []
        full_conv.append(Message(role="user", contents=["follow-up"]))
        # Simulate a prior run: the target executor has a stored previous_response_id.
        self._target_exec._session.service_session_id = "resp_PREVIOUS_RUN"  # pyright: ignore[reportPrivateUsage]
        await ctx.send_message(
            AgentExecutorRequest(messages=full_conv, should_respond=True),
            target_id=self._target_exec.id,
        )


class _PayloadReplayCoordinator(Executor):
    """Coordinator that pre-sets service_session_id on a target executor and sends it
    a payload derived from the upstream response. The payload type selects the
    executor's input handler (from_messages, from_message, from_str, or run)."""

    def __init__(
        self,
        *,
        target_exec: AgentExecutor,
        payload_factory: Callable[[AgentExecutorResponse], Any],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._target_exec = target_exec
        self._payload_factory = payload_factory

    @handler
    async def handle(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[str | Message | list[Message], Any],
    ) -> None:
        self._target_exec._session.service_session_id = "resp_PREVIOUS_RUN"  # pyright: ignore[reportPrivateUsage]
        await ctx.send_message(self._payload_factory(response), target_id=self._target_exec.id)


async def test_run_request_with_full_history_clears_service_session_id() -> None:
    """Replaying a full conversation (including function calls) via AgentExecutorRequest must
    clear service_session_id so the API does not receive both previous_response_id and the
    same function-call items in input — which would cause a 'Duplicate item' API error."""
    tool_agent = _ToolHistoryAgent(id="tool_agent", name="ToolAgent", summary_text="Done.")
    tool_exec = AgentExecutor(tool_agent, id="tool_agent")

    spy_agent = _SessionIdCapturingAgent(id="spy_agent", name="SpyAgent")
    spy_exec = AgentExecutor(spy_agent, id="spy_agent")

    coordinator = _FullHistoryReplayCoordinator(id="coord", target_exec=spy_exec)

    wf = (
        WorkflowBuilder(start_executor=tool_exec, output_from=[coordinator])
        .add_edge(tool_exec, coordinator)
        .add_edge(coordinator, spy_exec)
        .build()
    )

    result = await wf.run("initial prompt")
    assert result.get_outputs() is not None

    # The spy agent must have seen service_session_id=None (cleared before run).
    # Without the fix, it would see "resp_PREVIOUS_RUN" and the API would raise
    # "Duplicate item found" because the same function-call IDs appear in both
    # previous_response_id (server-stored) and the explicit input messages.
    assert spy_agent._captured_service_session_id is None  # pyright: ignore[reportPrivateUsage]


async def test_run_request_with_new_turn_preserves_service_session_id() -> None:
    """A new user turn (no replayed history) must keep service_session_id so the provider
    can continue the conversation via previous_response_id."""
    tool_agent = _ToolHistoryAgent(id="tool_agent_new_turn", name="ToolAgent", summary_text="Done.")
    tool_exec = AgentExecutor(tool_agent, id="tool_agent_new_turn")

    spy_agent = _SessionIdCapturingAgent(id="spy_agent_new_turn", name="SpyAgent")
    spy_exec = AgentExecutor(spy_agent, id="spy_agent_new_turn")

    coordinator = _FullHistoryReplayCoordinator(id="coord_new_turn", target_exec=spy_exec, include_history=False)

    wf = (
        WorkflowBuilder(start_executor=tool_exec, output_from=[coordinator])
        .add_edge(tool_exec, coordinator)
        .add_edge(coordinator, spy_exec)
        .build()
    )

    result = await wf.run("initial prompt")
    assert result.get_outputs() is not None

    # The spy agent must still see the stored pointer: only a full-history replay clears it.
    assert spy_agent._captured_service_session_id == "resp_PREVIOUS_RUN"  # pyright: ignore[reportPrivateUsage]


async def test_from_messages_with_full_history_clears_service_session_id() -> None:
    """from_messages with a full-history list must clear service_session_id."""
    tool_agent = _ToolHistoryAgent(id="tool_agent_fm", name="ToolAgent", summary_text="Done.")
    tool_exec = AgentExecutor(tool_agent, id="tool_agent_fm")

    spy_agent = _SessionIdCapturingAgent(id="spy_agent_fm", name="SpyAgent")
    spy_exec = AgentExecutor(spy_agent, id="spy_agent_fm")

    coordinator = _PayloadReplayCoordinator(
        id="coord_fm",
        target_exec=spy_exec,
        payload_factory=lambda response: list(response.full_conversation or response.agent_response.messages),
    )

    wf = (
        WorkflowBuilder(start_executor=tool_exec, output_from=[coordinator])
        .add_edge(tool_exec, coordinator)
        .add_edge(coordinator, spy_exec)
        .build()
    )

    result = await wf.run("initial prompt")
    assert result.get_outputs() is not None
    assert spy_agent._captured_service_session_id is None  # pyright: ignore[reportPrivateUsage]


async def test_from_messages_with_new_turn_preserves_service_session_id() -> None:
    """from_messages with only a user turn must keep service_session_id."""
    tool_agent = _ToolHistoryAgent(id="tool_agent_fm2", name="ToolAgent", summary_text="Done.")
    tool_exec = AgentExecutor(tool_agent, id="tool_agent_fm2")

    spy_agent = _SessionIdCapturingAgent(id="spy_agent_fm2", name="SpyAgent")
    spy_exec = AgentExecutor(spy_agent, id="spy_agent_fm2")

    coordinator = _PayloadReplayCoordinator(
        id="coord_fm2",
        target_exec=spy_exec,
        payload_factory=lambda _: [Message(role="user", contents=["follow-up"])],
    )

    wf = (
        WorkflowBuilder(start_executor=tool_exec, output_from=[coordinator])
        .add_edge(tool_exec, coordinator)
        .add_edge(coordinator, spy_exec)
        .build()
    )

    result = await wf.run("initial prompt")
    assert result.get_outputs() is not None
    assert spy_agent._captured_service_session_id == "resp_PREVIOUS_RUN"  # pyright: ignore[reportPrivateUsage]


async def test_from_message_replays_prior_turn_clears_service_session_id() -> None:
    """A single replayed assistant message via from_message must clear service_session_id."""
    tool_agent = _ToolHistoryAgent(id="tool_agent_msg", name="ToolAgent", summary_text="Done.")
    tool_exec = AgentExecutor(tool_agent, id="tool_agent_msg")

    spy_agent = _SessionIdCapturingAgent(id="spy_agent_msg", name="SpyAgent")
    spy_exec = AgentExecutor(spy_agent, id="spy_agent_msg")

    coordinator = _PayloadReplayCoordinator(
        id="coord_msg",
        target_exec=spy_exec,
        payload_factory=lambda response: list(response.full_conversation or response.agent_response.messages)[-1],
    )

    wf = (
        WorkflowBuilder(start_executor=tool_exec, output_from=[coordinator])
        .add_edge(tool_exec, coordinator)
        .add_edge(coordinator, spy_exec)
        .build()
    )

    result = await wf.run("initial prompt")
    assert result.get_outputs() is not None
    assert spy_agent._captured_service_session_id is None  # pyright: ignore[reportPrivateUsage]


async def test_from_str_with_user_prompt_preserves_service_session_id() -> None:
    """from_str (a plain user prompt) must keep service_session_id."""
    tool_agent = _ToolHistoryAgent(id="tool_agent_str", name="ToolAgent", summary_text="Done.")
    tool_exec = AgentExecutor(tool_agent, id="tool_agent_str")

    spy_agent = _SessionIdCapturingAgent(id="spy_agent_str", name="SpyAgent")
    spy_exec = AgentExecutor(spy_agent, id="spy_agent_str")

    coordinator = _PayloadReplayCoordinator(
        id="coord_str",
        target_exec=spy_exec,
        payload_factory=lambda _: "follow-up",
    )

    wf = (
        WorkflowBuilder(start_executor=tool_exec, output_from=[coordinator])
        .add_edge(tool_exec, coordinator)
        .add_edge(coordinator, spy_exec)
        .build()
    )

    result = await wf.run("initial prompt")
    assert result.get_outputs() is not None
    assert spy_agent._captured_service_session_id == "resp_PREVIOUS_RUN"  # pyright: ignore[reportPrivateUsage]


async def test_from_response_preserves_service_session_id() -> None:
    """from_response hands off a prior agent's full conversation to the next executor.
    The receiving executor's service_session_id is preserved so the API can continue
    the conversation using previous_response_id."""
    tool_agent = _ToolHistoryAgent(id="tool_agent2", name="ToolAgent", summary_text="Done.")
    tool_exec = AgentExecutor(tool_agent, id="tool_agent2")

    spy_agent = _SessionIdCapturingAgent(id="spy_agent2", name="SpyAgent")
    spy_exec = AgentExecutor(spy_agent, id="spy_agent2")
    # Simulate a prior run on the spy executor.
    spy_exec._session.service_session_id = "resp_PREVIOUS_RUN"  # pyright: ignore[reportPrivateUsage]

    wf = WorkflowBuilder(start_executor=tool_exec, output_from=[spy_exec]).add_edge(tool_exec, spy_exec).build()

    result = await wf.run("start")
    assert result.get_outputs() is not None

    assert spy_agent._captured_service_session_id == "resp_PREVIOUS_RUN"  # pyright: ignore[reportPrivateUsage]


@executor(
    id="upper_case_executor",
    input=AgentExecutorResponse,
    output=AgentExecutorResponse,
    workflow_output=str,
)
async def _upper_case_executor(
    response: AgentExecutorResponse,
    ctx: WorkflowContext[AgentExecutorResponse, str],
) -> None:
    upper_text = response.agent_response.text.upper()
    await ctx.send_message(response.with_text(upper_text))
    await ctx.yield_output(upper_text)


async def test_with_text_preserves_full_conversation_through_custom_executor() -> None:
    """Custom executor using with_text must preserve the full conversation chain."""
    # Mirrors the reproduction from issue #5246:
    # agent1 ("User likes sky red") -> agent2 ("User likes sky blue") -> upper_case -> agent3 ("User likes sky green")
    agent1 = AgentExecutor(
        _SimpleAgent(id="agent1", name="ContextAgent1", reply_text="User likes sky red"), id="agent1"
    )
    agent2 = AgentExecutor(
        _SimpleAgent(id="agent2", name="ContextAgent2", reply_text="User likes sky blue"), id="agent2"
    )
    agent3 = AgentExecutor(
        _SimpleAgent(id="agent3", name="ContextAgent3", reply_text="User likes sky green"), id="agent3"
    )
    capturer = _CaptureFullConversation(id="capture")

    wf = (
        WorkflowBuilder(start_executor=agent1, output_from=[capturer])
        .add_chain([agent1, agent2, _upper_case_executor, agent3, capturer])
        .build()
    )

    result = await wf.run("")
    payload = next(o for o in result.get_outputs() if isinstance(o, dict))

    # The final agent must see the full conversation: user, agent1, UPPER(agent2), agent3
    assert payload["roles"] == ["user", "assistant", "assistant", "assistant"]
    assert payload["texts"][1] == "User likes sky red"
    assert payload["texts"][2] == "USER LIKES SKY BLUE"
    assert payload["texts"][3] == "User likes sky green"


async def test_with_text_does_not_mutate_original() -> None:
    """with_text returns a new instance; the original must be unmodified."""
    original = AgentExecutorResponse(
        executor_id="test_exec",
        agent_response=AgentResponse(messages=[Message("assistant", ["original reply"])]),
        full_conversation=[Message("user", ["prompt"]), Message("assistant", ["original reply"])],
    )

    new = original.with_text("transformed reply")

    assert new is not original
    assert new.agent_response.text == "transformed reply"
    assert new.full_conversation[-1].text == "transformed reply"
    assert new.full_conversation[-1].role == "assistant"
    # Original unchanged
    assert original.agent_response.text == "original reply"
    assert original.full_conversation[-1].text == "original reply"


async def test_with_text_strips_multi_message_agent_turn() -> None:
    """When the agent turn has multiple messages (tool calls), with_text strips all of them."""
    tool_call = Message("assistant", ["<tool_call>"])
    tool_result = Message("tool", ["<result>"])
    final_reply = Message("assistant", ["actual answer"])
    user_msg = Message("user", ["question"])

    original = AgentExecutorResponse(
        executor_id="exec",
        agent_response=AgentResponse(messages=[tool_call, tool_result, final_reply]),
        full_conversation=[user_msg, tool_call, tool_result, final_reply],
    )

    new = original.with_text("summarised answer")

    # Only the pre-agent-turn messages should remain, plus the replacement
    assert len(new.full_conversation) == 2
    assert new.full_conversation[0].text == "question"
    assert new.full_conversation[1].text == "summarised answer"
    assert new.agent_response.text == "summarised answer"
