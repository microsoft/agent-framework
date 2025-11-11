# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    BaseAgent,
    ChatAgent,
    ChatMessage,
    FunctionCallContent,
    HandoffBuilder,
    HandoffUserInputRequest,
    RequestInfoEvent,
    Role,
    TextContent,
    WorkflowEvent,
    WorkflowOutputEvent,
)
from agent_framework._mcp import MCPTool
from agent_framework._workflows._handoff import _clone_chat_agent  # type: ignore[reportPrivateUsage]


@dataclass
class _ComplexMetadata:
    reason: str
    payload: dict[str, str]


@pytest.fixture
def complex_metadata() -> _ComplexMetadata:
    return _ComplexMetadata(reason="route", payload={"code": "X1"})


def _metadata_from_conversation(conversation: list[ChatMessage], key: str) -> list[object]:
    return [msg.additional_properties[key] for msg in conversation if key in msg.additional_properties]


def _conversation_debug(conversation: list[ChatMessage]) -> list[tuple[str, str | None, str]]:
    return [
        (msg.role.value if hasattr(msg.role, "value") else str(msg.role), msg.author_name, msg.text)
        for msg in conversation
    ]


class _RecordingAgent(BaseAgent):
    def __init__(
        self,
        *,
        name: str,
        handoff_to: str | None = None,
        text_handoff: bool = False,
        extra_properties: dict[str, object] | None = None,
    ) -> None:
        super().__init__(id=name, name=name, display_name=name)
        self._agent_name = name
        self.handoff_to = handoff_to
        self.calls: list[list[ChatMessage]] = []
        self._text_handoff = text_handoff
        self._extra_properties = dict(extra_properties or {})
        self._call_index = 0

    async def run(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: Any = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        conversation = _normalise(messages)
        self.calls.append(conversation)
        additional_properties = _merge_additional_properties(
            self.handoff_to, self._text_handoff, self._extra_properties
        )
        contents = _build_reply_contents(self._agent_name, self.handoff_to, self._text_handoff, self._next_call_id())
        reply = ChatMessage(
            role=Role.ASSISTANT,
            contents=contents,
            author_name=self.display_name,
            additional_properties=additional_properties,
        )
        return AgentRunResponse(messages=[reply])

    async def run_stream(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[AgentRunResponseUpdate]:
        conversation = _normalise(messages)
        self.calls.append(conversation)
        additional_props = _merge_additional_properties(self.handoff_to, self._text_handoff, self._extra_properties)
        contents = _build_reply_contents(self._agent_name, self.handoff_to, self._text_handoff, self._next_call_id())
        yield AgentRunResponseUpdate(
            contents=contents,
            role=Role.ASSISTANT,
            additional_properties=additional_props,
        )

    def _next_call_id(self) -> str | None:
        if not self.handoff_to:
            return None
        call_id = f"{self.id}-handoff-{self._call_index}"
        self._call_index += 1
        return call_id


def _merge_additional_properties(
    handoff_to: str | None, use_text_hint: bool, extras: dict[str, object]
) -> dict[str, object]:
    additional_properties: dict[str, object] = {}
    if handoff_to and not use_text_hint:
        additional_properties["handoff_to"] = handoff_to
    additional_properties.update(extras)
    return additional_properties


def _build_reply_contents(
    agent_name: str,
    handoff_to: str | None,
    use_text_hint: bool,
    call_id: str | None,
) -> list[TextContent | FunctionCallContent]:
    contents: list[TextContent | FunctionCallContent] = []
    if handoff_to and call_id:
        contents.append(
            FunctionCallContent(call_id=call_id, name=f"handoff_to_{handoff_to}", arguments={"handoff_to": handoff_to})
        )
    text = f"{agent_name} reply"
    if use_text_hint and handoff_to:
        text += f"\nHANDOFF_TO: {handoff_to}"
    contents.append(TextContent(text=text))
    return contents


def _normalise(messages: str | ChatMessage | list[str] | list[ChatMessage] | None) -> list[ChatMessage]:
    if isinstance(messages, list):
        result: list[ChatMessage] = []
        for msg in messages:
            if isinstance(msg, ChatMessage):
                result.append(msg)
            elif isinstance(msg, str):
                result.append(ChatMessage(Role.USER, text=msg))
        return result
    if isinstance(messages, ChatMessage):
        return [messages]
    if isinstance(messages, str):
        return [ChatMessage(Role.USER, text=messages)]
    return []


async def _drain(stream: AsyncIterable[WorkflowEvent]) -> list[WorkflowEvent]:
    return [event async for event in stream]


async def test_specialist_to_specialist_handoff():
    """Test that specialists can hand off to other specialists via .add_handoff() configuration."""
    triage = _RecordingAgent(name="triage", handoff_to="specialist")
    specialist = _RecordingAgent(name="specialist", handoff_to="escalation")
    escalation = _RecordingAgent(name="escalation")

    workflow = (
        HandoffBuilder(participants=[triage, specialist, escalation])
        .set_coordinator(triage)
        .add_handoff(triage, [specialist, escalation])
        .add_handoff(specialist, escalation)
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 2)
        .build()
    )

    # Start conversation - triage hands off to specialist
    events = await _drain(workflow.run_stream("Need technical support"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Specialist should have been called
    assert len(specialist.calls) > 0

    # Second user message - specialist hands off to escalation
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "This is complex"}))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs

    # Escalation should have been called
    assert len(escalation.calls) > 0


async def test_handoff_preserves_complex_additional_properties(complex_metadata: _ComplexMetadata):
    triage = _RecordingAgent(name="triage", handoff_to="specialist", extra_properties={"complex": complex_metadata})
    specialist = _RecordingAgent(name="specialist")

    # Sanity check: agent response contains complex metadata before entering workflow
    triage_response = await triage.run([ChatMessage(role=Role.USER, text="Need help with a return")])
    assert triage_response.messages
    assert "complex" in triage_response.messages[0].additional_properties

    workflow = (
        HandoffBuilder(participants=[triage, specialist])
        .set_coordinator("triage")
        .with_termination_condition(lambda conv: sum(1 for msg in conv if msg.role == Role.USER) >= 2)
        .build()
    )

    # Initial run should preserve complex metadata in the triage response
    events = await _drain(workflow.run_stream("Need help with a return"))
    agent_events = [ev for ev in events if hasattr(ev, "data") and hasattr(ev.data, "messages")]
    if agent_events:
        first_agent_event = agent_events[0]
        first_agent_event_data = first_agent_event.data
        if first_agent_event_data and hasattr(first_agent_event_data, "messages"):
            first_agent_message = first_agent_event_data.messages[0]  # type: ignore[attr-defined]
            assert "complex" in first_agent_message.additional_properties, "Agent event lost complex metadata"
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests, "Workflow should request additional user input"

    request_data = requests[-1].data
    assert isinstance(request_data, HandoffUserInputRequest)
    conversation_snapshot = request_data.conversation
    metadata_values = _metadata_from_conversation(conversation_snapshot, "complex")
    assert metadata_values, (
        "Expected triage message in conversation, found "
        f"additional_properties={[msg.additional_properties for msg in conversation_snapshot]},"
        f" messages={_conversation_debug(conversation_snapshot)}"
    )
    assert any(isinstance(value, _ComplexMetadata) for value in metadata_values), (
        "Complex metadata lost after first hop"
    )
    restored_meta = next(value for value in metadata_values if isinstance(value, _ComplexMetadata))
    assert restored_meta.payload["code"] == "X1"

    # Respond and ensure metadata survives subsequent cycles
    follow_up_events = await _drain(
        workflow.send_responses_streaming({requests[-1].request_id: "Here are more details"})
    )
    follow_up_requests = [ev for ev in follow_up_events if isinstance(ev, RequestInfoEvent)]
    outputs = [ev for ev in follow_up_events if isinstance(ev, WorkflowOutputEvent)]

    follow_up_conversation: list[ChatMessage]
    if follow_up_requests:
        follow_up_request_data = follow_up_requests[-1].data
        assert isinstance(follow_up_request_data, HandoffUserInputRequest)
        follow_up_conversation = follow_up_request_data.conversation
    else:
        assert outputs, "Workflow produced neither follow-up request nor output"
        output_data = outputs[-1].data
        follow_up_conversation = cast(list[ChatMessage], output_data) if isinstance(output_data, list) else []

    metadata_values_after = _metadata_from_conversation(follow_up_conversation, "complex")
    assert metadata_values_after, "Expected triage message after follow-up"
    assert any(isinstance(value, _ComplexMetadata) for value in metadata_values_after), (
        "Complex metadata lost after restore"
    )

    restored_meta_after = next(value for value in metadata_values_after if isinstance(value, _ComplexMetadata))
    assert restored_meta_after.payload["code"] == "X1"


async def test_tool_call_handoff_detection_with_text_hint():
    triage = _RecordingAgent(name="triage", handoff_to="specialist", text_handoff=True)
    specialist = _RecordingAgent(name="specialist")

    workflow = HandoffBuilder(participants=[triage, specialist]).set_coordinator("triage").build()

    await _drain(workflow.run_stream("Package arrived broken"))

    assert specialist.calls, "Specialist should be invoked using handoff tool call"
    assert len(specialist.calls[0]) >= 2


def test_build_fails_without_coordinator():
    """Verify that build() raises ValueError when set_coordinator() was not called."""
    triage = _RecordingAgent(name="triage")
    specialist = _RecordingAgent(name="specialist")

    with pytest.raises(ValueError, match="coordinator must be defined before build"):
        HandoffBuilder(participants=[triage, specialist]).build()


def test_build_fails_without_participants():
    """Verify that build() raises ValueError when no participants are provided."""
    with pytest.raises(ValueError, match="No participants provided"):
        HandoffBuilder().build()


async def test_multiple_runs_dont_leak_conversation():
    """Verify that running the same workflow multiple times doesn't leak conversation history."""
    triage = _RecordingAgent(name="triage", handoff_to="specialist")
    specialist = _RecordingAgent(name="specialist")

    workflow = (
        HandoffBuilder(participants=[triage, specialist])
        .set_coordinator("triage")
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 2)
        .build()
    )

    # First run
    events = await _drain(workflow.run_stream("First run message"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Second message"}))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "First run should emit output"

    first_run_conversation = outputs[-1].data
    assert isinstance(first_run_conversation, list)
    first_run_conv_list = cast(list[ChatMessage], first_run_conversation)
    first_run_user_messages = [msg for msg in first_run_conv_list if msg.role == Role.USER]
    assert len(first_run_user_messages) == 2
    assert any("First run message" in msg.text for msg in first_run_user_messages if msg.text)

    # Second run - should start fresh, not include first run's messages
    triage.calls.clear()
    specialist.calls.clear()

    events = await _drain(workflow.run_stream("Second run different message"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Another message"}))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "Second run should emit output"

    second_run_conversation = outputs[-1].data
    assert isinstance(second_run_conversation, list)
    second_run_conv_list = cast(list[ChatMessage], second_run_conversation)
    second_run_user_messages = [msg for msg in second_run_conv_list if msg.role == Role.USER]
    assert len(second_run_user_messages) == 2, (
        "Second run should have exactly 2 user messages, not accumulate first run"
    )
    assert any("Second run different message" in msg.text for msg in second_run_user_messages if msg.text)
    assert not any("First run message" in msg.text for msg in second_run_user_messages if msg.text), (
        "Second run should NOT contain first run's messages"
    )


async def test_handoff_async_termination_condition() -> None:
    """Test that async termination conditions work correctly."""
    termination_call_count = 0

    async def async_termination(conv: list[ChatMessage]) -> bool:
        nonlocal termination_call_count
        termination_call_count += 1
        user_count = sum(1 for msg in conv if msg.role == Role.USER)
        return user_count >= 2

    coordinator = _RecordingAgent(name="coordinator")

    workflow = (
        HandoffBuilder(participants=[coordinator])
        .set_coordinator(coordinator)
        .with_termination_condition(async_termination)
        .build()
    )

    events = await _drain(workflow.run_stream("First user message"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Second user message"}))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert len(outputs) == 1

    final_conversation = outputs[0].data
    assert isinstance(final_conversation, list)
    final_conv_list = cast(list[ChatMessage], final_conversation)
    user_messages = [msg for msg in final_conv_list if msg.role == Role.USER]
    assert len(user_messages) == 2
    assert termination_call_count > 0


async def test_clone_chat_agent_preserves_mcp_tools() -> None:
    """Test that _clone_chat_agent preserves MCP tools when cloning an agent."""
    mock_chat_client = MagicMock()

    mock_mcp_tool = MagicMock(spec=MCPTool)
    mock_mcp_tool.name = "test_mcp_tool"

    def sample_function() -> str:
        return "test"

    original_agent = ChatAgent(
        chat_client=mock_chat_client,
        name="TestAgent",
        instructions="Test instructions",
        tools=[mock_mcp_tool, sample_function],
    )

    assert hasattr(original_agent, "_local_mcp_tools")
    assert len(original_agent._local_mcp_tools) == 1  # type: ignore[reportPrivateUsage]
    assert original_agent._local_mcp_tools[0] == mock_mcp_tool  # type: ignore[reportPrivateUsage]

    cloned_agent = _clone_chat_agent(original_agent)

    assert hasattr(cloned_agent, "_local_mcp_tools")
    assert len(cloned_agent._local_mcp_tools) == 1  # type: ignore[reportPrivateUsage]
    assert cloned_agent._local_mcp_tools[0] == mock_mcp_tool  # type: ignore[reportPrivateUsage]
    assert cloned_agent.chat_options.tools is not None
    assert len(cloned_agent.chat_options.tools) == 1


async def test_return_to_previous_routing():
    """Test that return-to-previous routes back to the current specialist handling the conversation."""
    triage = _RecordingAgent(name="triage", handoff_to="specialist_a")
    specialist_a = _RecordingAgent(name="specialist_a", handoff_to="specialist_b")
    specialist_b = _RecordingAgent(name="specialist_b")

    workflow = (
        HandoffBuilder(participants=[triage, specialist_a, specialist_b])
        .set_coordinator(triage)
        .add_handoff(triage, [specialist_a, specialist_b])
        .add_handoff(specialist_a, specialist_b)
        .enable_return_to_previous(True)
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 4)
        .build()
    )

    # Start conversation - triage hands off to specialist_a
    events = await _drain(workflow.run_stream("Initial request"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests
    assert len(specialist_a.calls) > 0

    # Specialist_a should have been called with initial request
    initial_specialist_a_calls = len(specialist_a.calls)

    # Second user message - specialist_a hands off to specialist_b
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Need more help"}))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Specialist_b should have been called
    assert len(specialist_b.calls) > 0
    initial_specialist_b_calls = len(specialist_b.calls)

    # Third user message - with return_to_previous, should route back to specialist_b (current agent)
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Follow up question"}))
    third_requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]

    # Specialist_b should have been called again (return-to-previous routes to current agent)
    assert len(specialist_b.calls) > initial_specialist_b_calls, (
        "Specialist B should be called again due to return-to-previous routing to current agent"
    )

    # Specialist_a should NOT be called again (it's no longer the current agent)
    assert len(specialist_a.calls) == initial_specialist_a_calls, (
        "Specialist A should not be called again - specialist_b is the current agent"
    )

    # Triage should only have been called once at the start
    assert len(triage.calls) == 1, "Triage should only be called once (initial routing)"

    # Verify awaiting_agent_id is set to specialist_b (the agent that just responded)
    if third_requests:
        user_input_req = third_requests[-1].data
        assert isinstance(user_input_req, HandoffUserInputRequest)
        assert user_input_req.awaiting_agent_id == "specialist_b", (
            f"Expected awaiting_agent_id 'specialist_b' but got '{user_input_req.awaiting_agent_id}'"
        )


async def test_return_to_previous_disabled_routes_to_coordinator():
    """Test that with return-to-previous disabled, routing goes back to coordinator."""
    triage = _RecordingAgent(name="triage", handoff_to="specialist_a")
    specialist_a = _RecordingAgent(name="specialist_a", handoff_to="specialist_b")
    specialist_b = _RecordingAgent(name="specialist_b")

    workflow = (
        HandoffBuilder(participants=[triage, specialist_a, specialist_b])
        .set_coordinator(triage)
        .add_handoff(triage, [specialist_a, specialist_b])
        .add_handoff(specialist_a, specialist_b)
        .enable_return_to_previous(False)
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 3)
        .build()
    )

    # Start conversation - triage hands off to specialist_a
    events = await _drain(workflow.run_stream("Initial request"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests
    assert len(triage.calls) == 1

    # Second user message - specialist_a hands off to specialist_b
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Need more help"}))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Third user message - without return_to_previous, should route back to triage
    await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Follow up question"}))

    # Triage should have been called twice total: initial + after specialist_b responds
    assert len(triage.calls) == 2, "Triage should be called twice (initial + default routing to coordinator)"


async def test_return_to_previous_enabled():
    """Verify that enable_return_to_previous() keeps control with the current specialist."""
    triage = _RecordingAgent(name="triage", handoff_to="specialist_a")
    specialist_a = _RecordingAgent(name="specialist_a")
    specialist_b = _RecordingAgent(name="specialist_b")

    workflow = (
        HandoffBuilder(participants=[triage, specialist_a, specialist_b])
        .set_coordinator("triage")
        .enable_return_to_previous(True)
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 3)
        .build()
    )

    # Start conversation - triage hands off to specialist_a
    events = await _drain(workflow.run_stream("Initial request"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests
    assert len(triage.calls) == 1
    assert len(specialist_a.calls) == 1

    # Second user message - with return_to_previous, should route to specialist_a (not triage)
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Follow up question"}))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Triage should only have been called once (initial) - specialist_a handles follow-up
    assert len(triage.calls) == 1, "Triage should only be called once (initial)"
    assert len(specialist_a.calls) == 2, "Specialist A should handle follow-up with return_to_previous enabled"


async def test_tool_choice_preserved_from_agent_config():
    """Verify that agent-level tool_choice configuration is preserved and not overridden."""
    from unittest.mock import AsyncMock

    from agent_framework import ChatResponse, ToolMode

    # Create a mock chat client that records the tool_choice used
    recorded_tool_choices: list[Any] = []

    async def mock_get_response(messages: Any, **kwargs: Any) -> ChatResponse:
        chat_options = kwargs.get("chat_options")
        if chat_options:
            recorded_tool_choices.append(chat_options.tool_choice)
        return ChatResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, text="Response")],
            response_id="test_response",
        )

    mock_client = MagicMock()
    mock_client.get_response = AsyncMock(side_effect=mock_get_response)

    # Create agent with specific tool_choice configuration
    agent = ChatAgent(
        chat_client=mock_client,
        name="test_agent",
        tool_choice=ToolMode(mode="required"),  # type: ignore[arg-type]
    )

    # Run the agent
    await agent.run("Test message")

    # Verify tool_choice was preserved
    assert len(recorded_tool_choices) > 0, "No tool_choice recorded"
    last_tool_choice = recorded_tool_choices[-1]
    assert last_tool_choice is not None, "tool_choice should not be None"
    assert str(last_tool_choice) == "required", f"Expected 'required', got {last_tool_choice}"


async def test_return_to_previous_state_serialization():
    """Test that return_to_previous state is properly serialized/deserialized for checkpointing."""
    from agent_framework._workflows._handoff import _HandoffCoordinator  # type: ignore[reportPrivateUsage]

    # Create a coordinator with return_to_previous enabled
    coordinator = _HandoffCoordinator(
        starting_agent_id="triage",
        specialist_ids={"specialist_a": "specialist_a", "specialist_b": "specialist_b"},
        input_gateway_id="gateway",
        termination_condition=lambda conv: False,
        id="test-coordinator",
        return_to_previous=True,
    )

    # Set the current agent (simulating a handoff scenario)
    coordinator._current_agent_id = "specialist_a"  # type: ignore[reportPrivateUsage]

    # Snapshot the state
    state = coordinator.snapshot_state()

    # Verify pattern metadata includes current_agent_id
    assert "metadata" in state
    assert "current_agent_id" in state["metadata"]
    assert state["metadata"]["current_agent_id"] == "specialist_a"

    # Create a new coordinator and restore state
    coordinator2 = _HandoffCoordinator(
        starting_agent_id="triage",
        specialist_ids={"specialist_a": "specialist_a", "specialist_b": "specialist_b"},
        input_gateway_id="gateway",
        termination_condition=lambda conv: False,
        id="test-coordinator",
        return_to_previous=True,
    )

    # Restore state
    coordinator2.restore_state(state)

    # Verify current_agent_id was restored
    assert coordinator2._current_agent_id == "specialist_a", "Current agent should be restored from checkpoint"  # type: ignore[reportPrivateUsage]
