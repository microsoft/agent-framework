# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import (
    Agent,
    BaseContextProvider,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ResponseStream,
    WorkflowEvent,
    resolve_agent_id,
)
from agent_framework._clients import BaseChatClient
from agent_framework._middleware import ChatMiddlewareLayer, FunctionInvocationContext, MiddlewareTermination
from agent_framework._tools import FunctionInvocationLayer, FunctionTool, tool
from agent_framework.orchestrations import HandoffAgentUserRequest, HandoffBuilder

from agent_framework_orchestrations._handoff import (
    HANDOFF_FUNCTION_RESULT_KEY,
    HandoffConfiguration,
    _AutoHandoffMiddleware,  # pyright: ignore[reportPrivateUsage]
    get_handoff_tool_name,
)


class MockChatClient(ChatMiddlewareLayer[Any], FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """Mock chat client for testing handoff workflows."""

    def __init__(
        self,
        *,
        name: str = "",
        handoff_to: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the mock chat client.

        Args:
            name: The name of the agent using this chat client.
            handoff_to: The name of the agent to hand off to, or None for no handoff.
                This is hardcoded for testing purposes so that the agent always attempts to hand off.
        """
        ChatMiddlewareLayer.__init__(self)
        FunctionInvocationLayer.__init__(self)
        BaseChatClient.__init__(self)
        self._name = name
        self._handoff_to = handoff_to
        self._call_index = 0

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        if stream:
            return self._build_streaming_response(options=dict(options))

        async def _get() -> ChatResponse:
            contents = _build_reply_contents(self._name, self._handoff_to, self._next_call_id())
            reply = Message(
                role="assistant",
                contents=contents,
            )
            return ChatResponse(messages=reply, response_id="mock_response")

        return _get()

    def _build_streaming_response(self, *, options: dict[str, Any]) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            contents = _build_reply_contents(self._name, self._handoff_to, self._next_call_id())
            yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

        def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            response_format = options.get("response_format")
            output_format_type = response_format if isinstance(response_format, type) else None
            return ChatResponse.from_updates(updates, output_format_type=output_format_type)

        return ResponseStream(_stream(), finalizer=_finalize)

    def _next_call_id(self) -> str | None:
        if not self._handoff_to:
            return None
        call_id = f"{self._name}-handoff-{self._call_index}"
        self._call_index += 1
        return call_id


def _build_reply_contents(
    agent_name: str,
    handoff_to: str | None,
    call_id: str | None,
) -> list[Content]:
    contents: list[Content] = []
    if handoff_to and call_id:
        contents.append(
            Content.from_function_call(
                call_id=call_id, name=f"handoff_to_{handoff_to}", arguments={"handoff_to": handoff_to}
            )
        )
    text = f"{agent_name} reply"
    contents.append(Content.from_text(text=text))
    return contents


class MockHandoffAgent(Agent):
    """Mock agent that can hand off to another agent."""

    def __init__(
        self,
        *,
        name: str,
        handoff_to: str | None = None,
    ) -> None:
        """Initialize the mock handoff agent.

        Args:
            name: The name of the agent.
            handoff_to: The name of the agent to hand off to, or None for no handoff.
                This is hardcoded for testing purposes so that the agent always attempts to hand off.
        """
        super().__init__(client=MockChatClient(name=name, handoff_to=handoff_to), name=name, id=name)


async def _drain(stream: AsyncIterable[WorkflowEvent]) -> list[WorkflowEvent]:
    return [event async for event in stream]


async def test_handoff():
    """Test that agents can hand off to each other."""

    # `triage` hands off to `specialist`, who then hands off to `escalation`.
    # `escalation` has no handoff, so the workflow should request user input to continue.
    triage = MockHandoffAgent(name="triage", handoff_to="specialist")
    specialist = MockHandoffAgent(name="specialist", handoff_to="escalation")
    escalation = MockHandoffAgent(name="escalation")

    # Without explicitly defining handoffs, the builder will create connections
    # between all agents.
    workflow = (
        HandoffBuilder(
            participants=[triage, specialist, escalation],
            termination_condition=lambda conv: sum(1 for m in conv if m.role == "user") >= 2,
        )
        .with_start_agent(triage)
        .build()
    )

    # Start conversation - triage hands off to specialist then escalation
    # escalation won't trigger a handoff, so the response from it will become
    # a request for user input because autonomous mode is not enabled by default.
    events = await _drain(workflow.run("Need technical support", stream=True))
    requests = [ev for ev in events if ev.type == "request_info"]

    assert requests
    assert len(requests) == 1

    request = requests[0]
    assert isinstance(request.data, HandoffAgentUserRequest)
    assert request.source_executor_id == escalation.name


async def test_autonomous_mode_yields_output_without_user_request():
    """Ensure autonomous interaction mode yields output without requesting user input."""
    triage = MockHandoffAgent(name="triage", handoff_to="specialist")
    specialist = MockHandoffAgent(name="specialist")

    workflow = (
        HandoffBuilder(
            participants=[triage, specialist],
            # This termination condition ensures the workflow runs through both agents.
            # First message is the user message to triage, second is triage's response, which
            # is a handoff to specialist, third is specialist's response that should not request
            # user input due to autonomous mode. Fourth message will come from the specialist
            # again and will trigger termination.
            termination_condition=lambda conv: len(conv) >= 4,
        )
        .with_start_agent(triage)
        # Since specialist has no handoff, the specialist will be generating normal responses.
        # With autonomous mode, this should continue until the termination condition is met.
        .with_autonomous_mode(
            agents=[specialist],
            turn_limits={resolve_agent_id(specialist): 1},
        )
        .build()
    )

    events = await _drain(workflow.run("Package arrived broken", stream=True))
    requests = [ev for ev in events if ev.type == "request_info"]
    assert not requests, "Autonomous mode should not request additional user input"

    outputs = [ev for ev in events if ev.type == "output"]
    assert outputs, "Autonomous mode should yield a workflow output"

    final_conversation = outputs[-1].data
    assert isinstance(final_conversation, list)
    conversation_list = cast(list[Message], final_conversation)
    assert any(msg.role == "assistant" and (msg.text or "").startswith("specialist reply") for msg in conversation_list)


async def test_autonomous_mode_resumes_user_input_on_turn_limit():
    """Autonomous mode should resume user input request when turn limit is reached."""
    triage = MockHandoffAgent(name="triage", handoff_to="worker")
    worker = MockHandoffAgent(name="worker")

    workflow = (
        HandoffBuilder(participants=[triage, worker], termination_condition=lambda conv: False)
        .with_start_agent(triage)
        .with_autonomous_mode(agents=[worker], turn_limits={resolve_agent_id(worker): 2})
        .build()
    )

    events = await _drain(workflow.run("Start", stream=True))
    requests = [ev for ev in events if ev.type == "request_info"]
    assert requests and len(requests) == 1, "Turn limit should force a user input request"
    assert requests[0].source_executor_id == worker.name


def test_build_fails_without_start_agent():
    """Verify that build() raises ValueError when with_start_agent() was not called."""
    triage = MockHandoffAgent(name="triage")
    specialist = MockHandoffAgent(name="specialist")

    with pytest.raises(ValueError, match=r"Must call with_start_agent\(...\) before building the workflow."):
        HandoffBuilder(participants=[triage, specialist]).build()


def test_build_fails_without_participants():
    """Verify that build() raises ValueError when no participants are provided."""
    with pytest.raises(ValueError):
        HandoffBuilder(participants=[]).build()


async def test_handoff_async_termination_condition() -> None:
    """Test that async termination conditions work correctly."""
    termination_call_count = 0

    async def async_termination(conv: list[Message]) -> bool:
        nonlocal termination_call_count
        termination_call_count += 1
        user_count = sum(1 for msg in conv if msg.role == "user")
        return user_count >= 2

    coordinator = MockHandoffAgent(name="coordinator", handoff_to="worker")
    worker = MockHandoffAgent(name="worker")

    workflow = (
        HandoffBuilder(participants=[coordinator, worker], termination_condition=async_termination)
        .with_start_agent(coordinator)
        .build()
    )

    events = await _drain(workflow.run("First user message", stream=True))
    requests = [ev for ev in events if ev.type == "request_info"]
    assert requests

    events = await _drain(
        workflow.run(
            stream=True, responses={requests[-1].request_id: [Message(role="user", text="Second user message")]}
        )
    )
    outputs = [ev for ev in events if ev.type == "output"]
    assert len(outputs) == 1

    final_conversation = outputs[0].data
    assert isinstance(final_conversation, list)
    final_conv_list = cast(list[Message], final_conversation)
    user_messages = [msg for msg in final_conv_list if msg.role == "user"]
    assert len(user_messages) == 2
    assert termination_call_count > 0


async def test_tool_choice_preserved_from_agent_config():
    """Verify that agent-level tool_choice configuration is preserved and not overridden."""
    # Create a mock chat client that records the tool_choice used
    recorded_tool_choices: list[Any] = []

    async def mock_get_response(messages: Any, options: dict[str, Any] | None = None, **kwargs: Any) -> ChatResponse:
        if options:
            recorded_tool_choices.append(options.get("tool_choice"))
        return ChatResponse(
            messages=[Message(role="assistant", text="Response")],
            response_id="test_response",
        )

    mock_client = MagicMock()
    mock_client.get_response = AsyncMock(side_effect=mock_get_response)

    # Create agent with specific tool_choice configuration via default_options
    agent = Agent(
        client=mock_client,
        name="test_agent",
        default_options={"tool_choice": {"mode": "required"}},  # type: ignore
    )

    # Run the agent
    await agent.run("Test message")

    # Verify tool_choice was preserved
    assert len(recorded_tool_choices) > 0, "No tool_choice recorded"
    last_tool_choice = recorded_tool_choices[-1]
    assert last_tool_choice is not None, "tool_choice should not be None"
    assert last_tool_choice == {"mode": "required"}, f"Expected 'required', got {last_tool_choice}"


async def test_context_provider_preserved_during_handoff():
    """Verify that context_providers are preserved when cloning agents in handoff workflows."""
    # Track whether context provider methods were called
    provider_calls: list[str] = []

    class TestContextProvider(BaseContextProvider):
        """A test context provider that tracks its invocations."""

        def __init__(self) -> None:
            super().__init__("test")

        async def before_run(self, **kwargs: Any) -> None:
            provider_calls.append("before_run")

    # Create context provider
    context_provider = TestContextProvider()

    # Create a mock chat client
    mock_client = MockChatClient(name="test_agent")

    # Create agent with context provider using proper constructor
    agent = Agent(
        client=mock_client,
        name="test_agent",
        id="test_agent",
        context_providers=[context_provider],
    )

    # Verify the original agent has the context provider
    assert context_provider in agent.context_providers, "Original agent should have context provider"

    # Build handoff workflow - this should clone the agent and preserve context_providers
    workflow = HandoffBuilder(participants=[agent]).with_start_agent(agent).build()

    # Run workflow with a simple message to trigger context provider
    await _drain(workflow.run("Test message", stream=True))

    # Verify context provider was invoked during the workflow execution
    assert len(provider_calls) > 0, (
        "Context provider should be called during workflow execution, "
        "indicating it was properly preserved during agent cloning"
    )


def test_handoff_builder_accepts_all_instances_in_add_handoff():
    """Test that add_handoff accepts all instances when using participants."""
    triage = MockHandoffAgent(name="triage", handoff_to="specialist_a")
    specialist_a = MockHandoffAgent(name="specialist_a")
    specialist_b = MockHandoffAgent(name="specialist_b")

    # This should work - all instances with participants
    builder = (
        HandoffBuilder(participants=[triage, specialist_a, specialist_b])
        .with_start_agent(triage)
        .add_handoff(triage, [specialist_a, specialist_b])
    )

    workflow = builder.build()
    assert "triage" in workflow.executors
    assert "specialist_a" in workflow.executors
    assert "specialist_b" in workflow.executors


async def test_auto_handoff_middleware_intercepts_handoff_tool_call() -> None:
    """Middleware should short-circuit matching handoff tool calls with a synthetic result."""
    target_id = "specialist"
    middleware = _AutoHandoffMiddleware([HandoffConfiguration(target=target_id)])

    @tool(name=get_handoff_tool_name(target_id), approval_mode="never_require")
    def handoff_tool() -> str:
        return "unreachable"

    context = FunctionInvocationContext(function=handoff_tool, arguments={})
    call_next = AsyncMock()

    with pytest.raises(MiddlewareTermination) as exc_info:
        await middleware.process(context, call_next)

    call_next.assert_not_awaited()
    expected_result = FunctionTool.parse_result({HANDOFF_FUNCTION_RESULT_KEY: target_id})
    assert context.result == expected_result
    assert exc_info.value.result == expected_result


async def test_auto_handoff_middleware_calls_next_for_non_handoff_tool() -> None:
    """Middleware should pass through when the function name is not a configured handoff tool."""
    middleware = _AutoHandoffMiddleware([HandoffConfiguration(target="specialist")])

    @tool(name="regular_tool", approval_mode="never_require")
    def regular_tool() -> str:
        return "ok"

    context = FunctionInvocationContext(function=regular_tool, arguments={})
    call_next = AsyncMock()

    await middleware.process(context, call_next)

    call_next.assert_awaited_once()
    assert context.result is None
