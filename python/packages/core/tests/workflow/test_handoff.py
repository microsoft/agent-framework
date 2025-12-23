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
from agent_framework._workflows import AgentRunEvent
from agent_framework._workflows import _handoff as handoff_module  # type: ignore
from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value
from agent_framework._workflows._handoff import (
    _clone_chat_agent,  # type: ignore[reportPrivateUsage]
    _ConversationWithUserInput,
    _UserInputGateway,
)
from agent_framework._workflows._workflow_builder import WorkflowBuilder


class _CountingWorkflowBuilder(WorkflowBuilder):
    created: list["_CountingWorkflowBuilder"] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.start_calls = 0
        _CountingWorkflowBuilder.created.append(self)

    def set_start_executor(self, executor: Any) -> "_CountingWorkflowBuilder":  # type: ignore[override]
        self.start_calls += 1
        return cast("_CountingWorkflowBuilder", super().set_start_executor(executor))


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
        .set_coordinator(triage)
        .with_termination_condition(lambda conv: sum(1 for msg in conv if msg.role == Role.USER) >= 2)
        .build()
    )

    # Initial run should preserve complex metadata in the triage response
    events = await _drain(workflow.run_stream("Need help with a return"))
    agent_events = [ev for ev in events if isinstance(ev, AgentRunEvent)]
    if agent_events:
        first_agent_event = agent_events[0]
        first_agent_event_data = first_agent_event.data
        if first_agent_event_data and first_agent_event_data.messages:
            first_agent_message = first_agent_event_data.messages[0]
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

    workflow = HandoffBuilder(participants=[triage, specialist]).set_coordinator(triage).build()

    await _drain(workflow.run_stream("Package arrived broken"))

    assert specialist.calls, "Specialist should be invoked using handoff tool call"
    assert len(specialist.calls[0]) >= 2


async def test_autonomous_interaction_mode_yields_output_without_user_request():
    """Ensure autonomous interaction mode yields output without requesting user input."""
    triage = _RecordingAgent(name="triage", handoff_to="specialist")
    specialist = _RecordingAgent(name="specialist")

    workflow = (
        HandoffBuilder(participants=[triage, specialist])
        .set_coordinator(triage)
        .with_interaction_mode("autonomous", autonomous_turn_limit=1)
        .build()
    )

    events = await _drain(workflow.run_stream("Package arrived broken"))
    assert len(triage.calls) == 1
    assert len(specialist.calls) == 1
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert not requests, "Autonomous mode should not request additional user input"

    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "Autonomous mode should yield a workflow output"

    final_conversation = outputs[-1].data
    assert isinstance(final_conversation, list)
    conversation_list = cast(list[ChatMessage], final_conversation)
    assert any(
        msg.role == Role.ASSISTANT and (msg.text or "").startswith("specialist reply") for msg in conversation_list
    )


async def test_autonomous_continues_without_handoff_until_termination():
    """Autonomous mode should keep invoking the same agent when no handoff occurs."""
    worker = _RecordingAgent(name="worker")

    workflow = (
        HandoffBuilder(participants=[worker])
        .set_coordinator(worker)
        .with_interaction_mode("autonomous", autonomous_turn_limit=3)
        .with_termination_condition(lambda conv: False)
        .build()
    )

    events = await _drain(workflow.run_stream("Start"))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "Autonomous mode should yield output after termination condition"
    assert len(worker.calls) == 3, "Worker should be invoked multiple times without user input"
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert not requests, "Autonomous mode should not request user input"


async def test_autonomous_turn_limit_stops_loop():
    """Autonomous mode should stop when the configured turn limit is reached."""
    worker = _RecordingAgent(name="worker")

    workflow = (
        HandoffBuilder(participants=[worker])
        .set_coordinator(worker)
        .with_interaction_mode("autonomous", autonomous_turn_limit=2)
        .with_termination_condition(lambda conv: False)
        .build()
    )

    events = await _drain(workflow.run_stream("Start"))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "Turn limit should force a workflow output"
    assert len(worker.calls) == 2, "Worker should stop after reaching the turn limit"
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert not requests, "Autonomous mode should not request user input"


async def test_autonomous_routes_back_to_coordinator_when_specialist_stops():
    """Specialist without handoff should route back to coordinator in autonomous mode."""
    triage = _RecordingAgent(name="triage", handoff_to="specialist")
    specialist = _RecordingAgent(name="specialist")

    workflow = (
        HandoffBuilder(participants=[triage, specialist])
        .set_coordinator(triage)
        .add_handoff(triage, specialist)
        .with_interaction_mode("autonomous", autonomous_turn_limit=3)
        .with_termination_condition(lambda conv: len(conv) >= 4)
        .build()
    )

    events = await _drain(workflow.run_stream("Issue"))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "Workflow should complete without user input"
    assert len(specialist.calls) >= 1, "Specialist should run without handoff"


async def test_autonomous_mode_with_inline_turn_limit():
    """Autonomous mode should respect turn limit passed via with_interaction_mode."""
    worker = _RecordingAgent(name="worker")

    workflow = (
        HandoffBuilder(participants=[worker])
        .set_coordinator(worker)
        .with_interaction_mode("autonomous", autonomous_turn_limit=2)
        .with_termination_condition(lambda conv: False)
        .build()
    )

    events = await _drain(workflow.run_stream("Start"))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "Turn limit should force a workflow output"
    assert len(worker.calls) == 2, "Worker should stop after reaching the inline turn limit"


def test_autonomous_turn_limit_ignored_in_human_in_loop_mode(caplog):
    """Verify that autonomous_turn_limit logs a warning when mode is human_in_loop."""
    worker = _RecordingAgent(name="worker")

    # Should not raise, but should log a warning
    HandoffBuilder(participants=[worker]).set_coordinator(worker).with_interaction_mode(
        "human_in_loop", autonomous_turn_limit=10
    )

    assert "autonomous_turn_limit=10 was provided but interaction_mode is 'human_in_loop'; ignoring." in caplog.text


def test_autonomous_turn_limit_must_be_positive():
    """Verify that autonomous_turn_limit raises an error when <= 0."""
    worker = _RecordingAgent(name="worker")

    with pytest.raises(ValueError, match="autonomous_turn_limit must be positive"):
        HandoffBuilder(participants=[worker]).set_coordinator(worker).with_interaction_mode(
            "autonomous", autonomous_turn_limit=0
        )

    with pytest.raises(ValueError, match="autonomous_turn_limit must be positive"):
        HandoffBuilder(participants=[worker]).set_coordinator(worker).with_interaction_mode(
            "autonomous", autonomous_turn_limit=-5
        )


def test_build_fails_without_coordinator():
    """Verify that build() raises ValueError when set_coordinator() was not called."""
    triage = _RecordingAgent(name="triage")
    specialist = _RecordingAgent(name="specialist")

    with pytest.raises(ValueError, match=r"Must call set_coordinator\(...\) before building the workflow."):
        HandoffBuilder(participants=[triage, specialist]).build()


def test_build_fails_without_participants():
    """Verify that build() raises ValueError when no participants are provided."""
    with pytest.raises(ValueError, match="No participants or participant_factories have been configured."):
        HandoffBuilder().build()


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
        .set_coordinator(triage)
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


def test_handoff_builder_sets_start_executor_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure HandoffBuilder.build sets the start executor only once when assembling the workflow."""
    _CountingWorkflowBuilder.created.clear()
    monkeypatch.setattr(handoff_module, "WorkflowBuilder", _CountingWorkflowBuilder)

    coordinator = _RecordingAgent(name="coordinator")
    specialist = _RecordingAgent(name="specialist")

    workflow = (
        HandoffBuilder(participants=[coordinator, specialist])
        .set_coordinator(coordinator)
        .with_termination_condition(lambda conv: len(conv) > 0)
        .build()
    )

    assert workflow is not None
    assert _CountingWorkflowBuilder.created, "Expected CountingWorkflowBuilder to be instantiated"
    builder = _CountingWorkflowBuilder.created[-1]
    assert builder.start_calls == 1, "set_start_executor should be invoked exactly once"


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


async def test_handoff_builder_with_request_info():
    """Test that HandoffBuilder supports request info via with_request_info()."""
    from agent_framework import AgentInputRequest, RequestInfoEvent

    # Create test agents
    coordinator = _RecordingAgent(name="coordinator")
    specialist = _RecordingAgent(name="specialist")

    # Build workflow with request info enabled
    workflow = (
        HandoffBuilder(participants=[coordinator, specialist])
        .set_coordinator(coordinator)
        .with_termination_condition(lambda conv: len([m for m in conv if m.role == Role.USER]) >= 1)
        .with_request_info()
        .build()
    )

    # Run workflow until it pauses for request info
    request_event: RequestInfoEvent | None = None
    async for event in workflow.run_stream("Hello"):
        if isinstance(event, RequestInfoEvent) and isinstance(event.data, AgentInputRequest):
            request_event = event

    # Verify request info was emitted
    assert request_event is not None, "Request info should have been emitted"
    assert isinstance(request_event.data, AgentInputRequest)

    # Provide response and continue
    output_events: list[WorkflowOutputEvent] = []
    async for event in workflow.send_responses_streaming({request_event.request_id: "approved"}):
        if isinstance(event, WorkflowOutputEvent):
            output_events.append(event)

    # Verify we got output events
    assert len(output_events) > 0, "Should produce output events after response"


async def test_handoff_builder_with_request_info_method_chaining():
    """Test that with_request_info returns self for method chaining."""
    coordinator = _RecordingAgent(name="coordinator")

    builder = HandoffBuilder(participants=[coordinator])
    result = builder.with_request_info()

    assert result is builder, "with_request_info should return self for chaining"
    assert builder._request_info_enabled is True  # type: ignore


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
    state = await coordinator.on_checkpoint_save()

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
    await coordinator2.on_checkpoint_restore(state)

    # Verify current_agent_id was restored
    assert coordinator2._current_agent_id == "specialist_a", "Current agent should be restored from checkpoint"  # type: ignore[reportPrivateUsage]


# region Participant Factory Tests


def test_handoff_builder_rejects_empty_participant_factories():
    """Test that HandoffBuilder rejects empty participant_factories dictionary."""
    # Empty factories are rejected immediately when calling participant_factories()
    with pytest.raises(ValueError, match=r"participant_factories cannot be empty"):
        HandoffBuilder().participant_factories({})

    with pytest.raises(ValueError, match=r"No participants or participant_factories have been configured"):
        HandoffBuilder(participant_factories={}).build()


def test_handoff_builder_rejects_mixing_participants_and_factories():
    """Test that mixing participants and participant_factories in __init__ raises an error."""
    triage = _RecordingAgent(name="triage")
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder(participants=[triage], participant_factories={"triage": lambda: triage})


def test_handoff_builder_rejects_mixing_participants_and_participant_factories_methods():
    """Test that mixing .participants() and .participant_factories() raises an error."""
    triage = _RecordingAgent(name="triage")

    # Case 1: participants first, then participant_factories
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder(participants=[triage]).participant_factories({
            "specialist": lambda: _RecordingAgent(name="specialist")
        })

    # Case 2: participant_factories first, then participants
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder(participant_factories={"triage": lambda: triage}).participants([
            _RecordingAgent(name="specialist")
        ])

    # Case 3: participants(), then participant_factories()
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder().participants([triage]).participant_factories({
            "specialist": lambda: _RecordingAgent(name="specialist")
        })

    # Case 4: participant_factories(), then participants()
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder().participant_factories({"triage": lambda: triage}).participants([
            _RecordingAgent(name="specialist")
        ])

    # Case 5: mix during initialization
    with pytest.raises(ValueError, match="Cannot mix .participants"):
        HandoffBuilder(
            participants=[triage], participant_factories={"specialist": lambda: _RecordingAgent(name="specialist")}
        )


def test_handoff_builder_rejects_multiple_calls_to_participant_factories():
    """Test that multiple calls to .participant_factories() raises an error."""
    with pytest.raises(ValueError, match=r"participant_factories\(\) has already been called"):
        (
            HandoffBuilder()
            .participant_factories({"agent1": lambda: _RecordingAgent(name="agent1")})
            .participant_factories({"agent2": lambda: _RecordingAgent(name="agent2")})
        )


def test_handoff_builder_rejects_multiple_calls_to_participants():
    """Test that multiple calls to .participants() raises an error."""
    with pytest.raises(ValueError, match="participants have already been assigned"):
        (HandoffBuilder().participants([_RecordingAgent(name="agent1")]).participants([_RecordingAgent(name="agent2")]))


def test_handoff_builder_rejects_duplicate_factories():
    """Test that multiple calls to participant_factories are rejected."""
    factories = {
        "triage": lambda: _RecordingAgent(name="triage"),
        "specialist": lambda: _RecordingAgent(name="specialist"),
    }

    # Multiple calls to participant_factories should fail
    builder = HandoffBuilder(participant_factories=factories)
    with pytest.raises(ValueError, match=r"participant_factories\(\) has already been called"):
        builder.participant_factories({"triage": lambda: _RecordingAgent(name="triage2")})


def test_handoff_builder_rejects_instance_coordinator_with_factories():
    """Test that using an agent instance for set_coordinator when using factories raises an error."""

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage")

    def create_specialist() -> _RecordingAgent:
        return _RecordingAgent(name="specialist")

    # Create an agent instance
    coordinator_instance = _RecordingAgent(name="coordinator")

    with pytest.raises(ValueError, match=r"Call participants\(\.\.\.\) before coordinator\(\.\.\.\)"):
        (
            HandoffBuilder(
                participant_factories={"triage": create_triage, "specialist": create_specialist}
            ).set_coordinator(coordinator_instance)  # Instance, not factory name
        )


def test_handoff_builder_rejects_factory_name_coordinator_with_instances():
    """Test that using a factory name for set_coordinator when using instances raises an error."""
    triage = _RecordingAgent(name="triage")
    specialist = _RecordingAgent(name="specialist")

    with pytest.raises(
        ValueError, match="coordinator factory name 'triage' is not part of the participant_factories list"
    ):
        (
            HandoffBuilder(participants=[triage, specialist]).set_coordinator(
                "triage"
            )  # String factory name, not instance
        )


def test_handoff_builder_rejects_mixed_types_in_add_handoff_source():
    """Test that add_handoff rejects factory name source with instance-based participants."""
    triage = _RecordingAgent(name="triage")
    specialist = _RecordingAgent(name="specialist")

    with pytest.raises(TypeError, match="Cannot mix factory names \\(str\\) and AgentProtocol/Executor instances"):
        (
            HandoffBuilder(participants=[triage, specialist])
            .set_coordinator(triage)
            .add_handoff("triage", specialist)  # String source with instance participants
        )


def test_handoff_builder_accepts_all_factory_names_in_add_handoff():
    """Test that add_handoff accepts all factory names when using participant_factories."""

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage")

    def create_specialist_a() -> _RecordingAgent:
        return _RecordingAgent(name="specialist_a")

    def create_specialist_b() -> _RecordingAgent:
        return _RecordingAgent(name="specialist_b")

    # This should work - all strings with participant_factories
    builder = (
        HandoffBuilder(
            participant_factories={
                "triage": create_triage,
                "specialist_a": create_specialist_a,
                "specialist_b": create_specialist_b,
            }
        )
        .set_coordinator("triage")
        .add_handoff("triage", ["specialist_a", "specialist_b"])
    )

    workflow = builder.build()
    assert "triage" in workflow.executors
    assert "specialist_a" in workflow.executors
    assert "specialist_b" in workflow.executors


def test_handoff_builder_accepts_all_instances_in_add_handoff():
    """Test that add_handoff accepts all instances when using participants."""
    triage = _RecordingAgent(name="triage", handoff_to="specialist_a")
    specialist_a = _RecordingAgent(name="specialist_a")
    specialist_b = _RecordingAgent(name="specialist_b")

    # This should work - all instances with participants
    builder = (
        HandoffBuilder(participants=[triage, specialist_a, specialist_b])
        .set_coordinator(triage)
        .add_handoff(triage, [specialist_a, specialist_b])
    )

    workflow = builder.build()
    assert "triage" in workflow.executors
    assert "specialist_a" in workflow.executors
    assert "specialist_b" in workflow.executors


async def test_handoff_with_participant_factories():
    """Test workflow creation using participant_factories."""
    call_count = 0

    def create_triage() -> _RecordingAgent:
        nonlocal call_count
        call_count += 1
        return _RecordingAgent(name="triage", handoff_to="specialist")

    def create_specialist() -> _RecordingAgent:
        nonlocal call_count
        call_count += 1
        return _RecordingAgent(name="specialist")

    workflow = (
        HandoffBuilder(participant_factories={"triage": create_triage, "specialist": create_specialist})
        .set_coordinator("triage")
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 2)
        .build()
    )

    # Factories should be called during build
    assert call_count == 2

    events = await _drain(workflow.run_stream("Need help"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Follow-up message
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "More details"}))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs


async def test_handoff_participant_factories_reusable_builder():
    """Test that the builder can be reused to build multiple workflows with factories."""
    call_count = 0

    def create_triage() -> _RecordingAgent:
        nonlocal call_count
        call_count += 1
        return _RecordingAgent(name="triage", handoff_to="specialist")

    def create_specialist() -> _RecordingAgent:
        nonlocal call_count
        call_count += 1
        return _RecordingAgent(name="specialist")

    builder = HandoffBuilder(
        participant_factories={"triage": create_triage, "specialist": create_specialist}
    ).set_coordinator("triage")

    # Build first workflow
    wf1 = builder.build()
    assert call_count == 2

    # Build second workflow
    wf2 = builder.build()
    assert call_count == 4

    # Verify that the two workflows have different agent instances
    assert wf1.executors["triage"] is not wf2.executors["triage"]
    assert wf1.executors["specialist"] is not wf2.executors["specialist"]


async def test_handoff_with_participant_factories_and_add_handoff():
    """Test that .add_handoff() works correctly with participant_factories."""

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage", handoff_to="specialist_a")

    def create_specialist_a() -> _RecordingAgent:
        return _RecordingAgent(name="specialist_a", handoff_to="specialist_b")

    def create_specialist_b() -> _RecordingAgent:
        return _RecordingAgent(name="specialist_b")

    workflow = (
        HandoffBuilder(
            participant_factories={
                "triage": create_triage,
                "specialist_a": create_specialist_a,
                "specialist_b": create_specialist_b,
            }
        )
        .set_coordinator("triage")
        .add_handoff("triage", ["specialist_a", "specialist_b"])
        .add_handoff("specialist_a", "specialist_b")
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 3)
        .build()
    )

    # Start conversation - triage hands off to specialist_a
    events = await _drain(workflow.run_stream("Initial request"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Verify specialist_a executor exists and was called
    assert "specialist_a" in workflow.executors

    # Second user message - specialist_a hands off to specialist_b
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Need escalation"}))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Verify specialist_b executor exists
    assert "specialist_b" in workflow.executors


async def test_handoff_participant_factories_with_checkpointing():
    """Test checkpointing with participant_factories."""
    from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage

    storage = InMemoryCheckpointStorage()

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage", handoff_to="specialist")

    def create_specialist() -> _RecordingAgent:
        return _RecordingAgent(name="specialist")

    workflow = (
        HandoffBuilder(participant_factories={"triage": create_triage, "specialist": create_specialist})
        .set_coordinator("triage")
        .with_checkpointing(storage)
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 2)
        .build()
    )

    # Run workflow and capture output
    events = await _drain(workflow.run_stream("checkpoint test"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "follow up"}))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "Should have workflow output after termination condition is met"

    # List checkpoints - just verify they were created
    checkpoints = await storage.list_checkpoints()
    assert checkpoints, "Checkpoints should be created during workflow execution"


def test_handoff_set_coordinator_with_factory_name():
    """Test that set_coordinator accepts factory name as string."""

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage")

    def create_specialist() -> _RecordingAgent:
        return _RecordingAgent(name="specialist")

    builder = HandoffBuilder(
        participant_factories={"triage": create_triage, "specialist": create_specialist}
    ).set_coordinator("triage")

    workflow = builder.build()
    assert "triage" in workflow.executors


def test_handoff_add_handoff_with_factory_names():
    """Test that add_handoff accepts factory names as strings."""

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage", handoff_to="specialist_a")

    def create_specialist_a() -> _RecordingAgent:
        return _RecordingAgent(name="specialist_a")

    def create_specialist_b() -> _RecordingAgent:
        return _RecordingAgent(name="specialist_b")

    builder = (
        HandoffBuilder(
            participant_factories={
                "triage": create_triage,
                "specialist_a": create_specialist_a,
                "specialist_b": create_specialist_b,
            }
        )
        .set_coordinator("triage")
        .add_handoff("triage", ["specialist_a", "specialist_b"])
    )

    workflow = builder.build()
    assert "triage" in workflow.executors
    assert "specialist_a" in workflow.executors
    assert "specialist_b" in workflow.executors


async def test_handoff_participant_factories_autonomous_mode():
    """Test autonomous mode with participant_factories."""

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage", handoff_to="specialist")

    def create_specialist() -> _RecordingAgent:
        return _RecordingAgent(name="specialist")

    workflow = (
        HandoffBuilder(participant_factories={"triage": create_triage, "specialist": create_specialist})
        .set_coordinator("triage")
        .with_interaction_mode("autonomous", autonomous_turn_limit=2)
        .build()
    )

    events = await _drain(workflow.run_stream("Issue"))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs, "Autonomous mode should yield output"
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert not requests, "Autonomous mode should not request user input"


async def test_handoff_participant_factories_with_request_info():
    """Test that .with_request_info() works with participant_factories."""

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage")

    def create_specialist() -> _RecordingAgent:
        return _RecordingAgent(name="specialist")

    builder = (
        HandoffBuilder(participant_factories={"triage": create_triage, "specialist": create_specialist})
        .set_coordinator("triage")
        .with_request_info(agents=["triage"])
    )

    workflow = builder.build()
    assert "triage" in workflow.executors


def test_handoff_participant_factories_invalid_coordinator_name():
    """Test that set_coordinator raises error for non-existent factory name."""

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage")

    with pytest.raises(
        ValueError, match="coordinator factory name 'nonexistent' is not part of the participant_factories list"
    ):
        (HandoffBuilder(participant_factories={"triage": create_triage}).set_coordinator("nonexistent").build())


def test_handoff_participant_factories_invalid_handoff_target():
    """Test that add_handoff raises error for non-existent target factory name."""

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage")

    def create_specialist() -> _RecordingAgent:
        return _RecordingAgent(name="specialist")

    with pytest.raises(ValueError, match="Target factory name 'nonexistent' is not in the participant_factories list"):
        (
            HandoffBuilder(participant_factories={"triage": create_triage, "specialist": create_specialist})
            .set_coordinator("triage")
            .add_handoff("triage", "nonexistent")
            .build()
        )


async def test_handoff_participant_factories_enable_return_to_previous():
    """Test return_to_previous works with participant_factories."""

    def create_triage() -> _RecordingAgent:
        return _RecordingAgent(name="triage", handoff_to="specialist_a")

    def create_specialist_a() -> _RecordingAgent:
        return _RecordingAgent(name="specialist_a", handoff_to="specialist_b")

    def create_specialist_b() -> _RecordingAgent:
        return _RecordingAgent(name="specialist_b")

    workflow = (
        HandoffBuilder(
            participant_factories={
                "triage": create_triage,
                "specialist_a": create_specialist_a,
                "specialist_b": create_specialist_b,
            }
        )
        .set_coordinator("triage")
        .add_handoff("triage", ["specialist_a", "specialist_b"])
        .add_handoff("specialist_a", "specialist_b")
        .enable_return_to_previous(True)
        .with_termination_condition(lambda conv: sum(1 for m in conv if m.role == Role.USER) >= 3)
        .build()
    )

    # Start conversation - triage hands off to specialist_a
    events = await _drain(workflow.run_stream("Initial request"))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Second user message - specialist_a hands off to specialist_b
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Need escalation"}))
    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests

    # Third user message - should route back to specialist_b (return to previous)
    events = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Follow up"}))
    outputs = [ev for ev in events if isinstance(ev, WorkflowOutputEvent)]
    assert outputs or [ev for ev in events if isinstance(ev, RequestInfoEvent)]


# endregion Participant Factory Tests


async def test_handoff_user_input_request_checkpoint_excludes_conversation():
    """Test that HandoffUserInputRequest serialization excludes conversation to prevent duplication.

    Issue #2667: When checkpointing a workflow with a pending HandoffUserInputRequest,
    the conversation field gets serialized twice: once in the RequestInfoEvent's data
    and once in the coordinator's conversation state. On restore, this causes duplicate
    messages.

    The fix is to exclude the conversation field during checkpoint serialization since
    the conversation is already preserved in the coordinator's state.
    """
    # Create a conversation history
    conversation = [
        ChatMessage(role=Role.USER, text="Hello"),
        ChatMessage(role=Role.ASSISTANT, text="Hi there!"),
        ChatMessage(role=Role.USER, text="Help me"),
    ]

    # Create a HandoffUserInputRequest with the conversation
    request = HandoffUserInputRequest(
        conversation=conversation,
        awaiting_agent_id="specialist_agent",
        prompt="Please provide your input",
        source_executor_id="gateway",
    )

    # Encode the request (simulating checkpoint save)
    encoded = encode_checkpoint_value(request)

    # Verify conversation is NOT in the encoded output
    # The fix should exclude conversation from serialization
    assert isinstance(encoded, dict)

    # If using MODEL_MARKER strategy (to_dict/from_dict)
    if "__af_model__" in encoded or "__af_dataclass__" in encoded:
        value = encoded.get("value", {})
        assert "conversation" not in value, "conversation should be excluded from checkpoint serialization"

    # Decode the request (simulating checkpoint restore)
    decoded = decode_checkpoint_value(encoded)

    # Verify the decoded request is a HandoffUserInputRequest
    assert isinstance(decoded, HandoffUserInputRequest)

    # Verify other fields are preserved
    assert decoded.awaiting_agent_id == "specialist_agent"
    assert decoded.prompt == "Please provide your input"
    assert decoded.source_executor_id == "gateway"

    # Conversation should be an empty list after deserialization
    # (will be reconstructed from coordinator state on restore)
    assert decoded.conversation == []


async def test_handoff_user_input_request_roundtrip_preserves_metadata():
    """Test that non-conversation fields survive checkpoint roundtrip."""
    request = HandoffUserInputRequest(
        conversation=[ChatMessage(role=Role.USER, text="test")],
        awaiting_agent_id="test_agent",
        prompt="Enter your response",
        source_executor_id="test_gateway",
    )

    # Roundtrip through checkpoint encoding
    encoded = encode_checkpoint_value(request)
    decoded = decode_checkpoint_value(encoded)

    assert isinstance(decoded, HandoffUserInputRequest)
    assert decoded.awaiting_agent_id == request.awaiting_agent_id
    assert decoded.prompt == request.prompt
    assert decoded.source_executor_id == request.source_executor_id


async def test_request_info_event_with_handoff_user_input_request():
    """Test RequestInfoEvent serialization with HandoffUserInputRequest data."""
    conversation = [
        ChatMessage(role=Role.USER, text="Hello"),
        ChatMessage(role=Role.ASSISTANT, text="How can I help?"),
    ]

    request = HandoffUserInputRequest(
        conversation=conversation,
        awaiting_agent_id="specialist",
        prompt="Provide input",
        source_executor_id="gateway",
    )

    # Create a RequestInfoEvent wrapping the request
    event = RequestInfoEvent(
        request_id="test-request-123",
        source_executor_id="gateway",
        request_data=request,
        response_type=object,
    )

    # Serialize the event
    event_dict = event.to_dict()

    # Verify the data field doesn't contain conversation
    data_encoded = event_dict["data"]
    if isinstance(data_encoded, dict) and ("__af_model__" in data_encoded or "__af_dataclass__" in data_encoded):
        value = data_encoded.get("value", {})
        assert "conversation" not in value

    # Deserialize and verify
    restored_event = RequestInfoEvent.from_dict(event_dict)
    assert isinstance(restored_event.data, HandoffUserInputRequest)
    assert restored_event.data.awaiting_agent_id == "specialist"
    assert restored_event.data.conversation == []


async def test_handoff_user_input_request_to_dict_excludes_conversation():
    """Test that to_dict() method excludes conversation field."""
    conversation = [
        ChatMessage(role=Role.USER, text="Hello"),
        ChatMessage(role=Role.ASSISTANT, text="Hi!"),
    ]

    request = HandoffUserInputRequest(
        conversation=conversation,
        awaiting_agent_id="agent1",
        prompt="Enter input",
        source_executor_id="gateway",
    )

    # Call to_dict directly
    data = request.to_dict()

    # Verify conversation is excluded
    assert "conversation" not in data
    assert data["awaiting_agent_id"] == "agent1"
    assert data["prompt"] == "Enter input"
    assert data["source_executor_id"] == "gateway"


async def test_handoff_user_input_request_from_dict_creates_empty_conversation():
    """Test that from_dict() creates an instance with empty conversation."""
    data = {
        "awaiting_agent_id": "agent1",
        "prompt": "Enter input",
        "source_executor_id": "gateway",
    }

    request = HandoffUserInputRequest.from_dict(data)

    assert request.conversation == []
    assert request.awaiting_agent_id == "agent1"
    assert request.prompt == "Enter input"
    assert request.source_executor_id == "gateway"


async def test_user_input_gateway_resume_handles_empty_conversation():
    """Test that _UserInputGateway.resume_from_user handles post-restore scenario.

    After checkpoint restore, the HandoffUserInputRequest will have an empty
    conversation. The gateway should handle this by sending only the new user
    messages to the coordinator.
    """
    from unittest.mock import AsyncMock

    # Create a gateway
    gateway = _UserInputGateway(
        starting_agent_id="coordinator",
        prompt="Enter input",
        id="test-gateway",
    )

    # Simulate post-restore: request with empty conversation
    restored_request = HandoffUserInputRequest(
        conversation=[],  # Empty after restore
        awaiting_agent_id="specialist",
        prompt="Enter input",
        source_executor_id="test-gateway",
    )

    # Create mock context
    mock_ctx = MagicMock()
    mock_ctx.send_message = AsyncMock()

    # Call resume_from_user with a user response
    await gateway.resume_from_user(restored_request, "New user message", mock_ctx)

    # Verify send_message was called
    mock_ctx.send_message.assert_called_once()

    # Get the message that was sent
    call_args = mock_ctx.send_message.call_args
    sent_message = call_args[0][0]

    # Verify it's a _ConversationWithUserInput
    assert isinstance(sent_message, _ConversationWithUserInput)

    # Verify it contains only the new user message (not any history)
    assert len(sent_message.full_conversation) == 1
    assert sent_message.full_conversation[0].role == Role.USER
    assert sent_message.full_conversation[0].text == "New user message"


async def test_user_input_gateway_resume_with_full_conversation():
    """Test that _UserInputGateway.resume_from_user handles normal flow correctly.

    In normal flow (no checkpoint restore), the HandoffUserInputRequest has
    the full conversation. The gateway should send the full conversation
    plus the new user messages.
    """
    from unittest.mock import AsyncMock

    # Create a gateway
    gateway = _UserInputGateway(
        starting_agent_id="coordinator",
        prompt="Enter input",
        id="test-gateway",
    )

    # Normal flow: request with full conversation
    normal_request = HandoffUserInputRequest(
        conversation=[
            ChatMessage(role=Role.USER, text="Hello"),
            ChatMessage(role=Role.ASSISTANT, text="Hi!"),
        ],
        awaiting_agent_id="specialist",
        prompt="Enter input",
        source_executor_id="test-gateway",
    )

    # Create mock context
    mock_ctx = MagicMock()
    mock_ctx.send_message = AsyncMock()

    # Call resume_from_user with a user response
    await gateway.resume_from_user(normal_request, "Follow up message", mock_ctx)

    # Verify send_message was called
    mock_ctx.send_message.assert_called_once()

    # Get the message that was sent
    call_args = mock_ctx.send_message.call_args
    sent_message = call_args[0][0]

    # Verify it's a _ConversationWithUserInput
    assert isinstance(sent_message, _ConversationWithUserInput)

    # Verify it contains the full conversation plus new user message
    assert len(sent_message.full_conversation) == 3
    assert sent_message.full_conversation[0].text == "Hello"
    assert sent_message.full_conversation[1].text == "Hi!"
    assert sent_message.full_conversation[2].text == "Follow up message"


async def test_coordinator_handle_user_input_post_restore():
    """Test that _HandoffCoordinator.handle_user_input handles post-restore correctly.

    After checkpoint restore, the coordinator has its conversation restored,
    and the gateway sends only the new user messages. The coordinator should
    append these to its existing conversation rather than replacing.
    """
    from unittest.mock import AsyncMock

    from agent_framework._workflows._handoff import _HandoffCoordinator

    # Create a coordinator with pre-existing conversation (simulating restored state)
    coordinator = _HandoffCoordinator(
        starting_agent_id="triage",
        specialist_ids={"specialist_a": "specialist_a"},
        input_gateway_id="gateway",
        termination_condition=lambda conv: False,
        id="test-coordinator",
    )

    # Simulate restored conversation
    coordinator._conversation = [
        ChatMessage(role=Role.USER, text="Hello"),
        ChatMessage(role=Role.ASSISTANT, text="Hi there!"),
        ChatMessage(role=Role.USER, text="Help me"),
        ChatMessage(role=Role.ASSISTANT, text="Sure, what do you need?"),
    ]

    # Create mock context
    mock_ctx = MagicMock()
    mock_ctx.send_message = AsyncMock()

    # Simulate post-restore: only new user message with explicit flag
    incoming = _ConversationWithUserInput(
        full_conversation=[ChatMessage(role=Role.USER, text="I need shipping help")],
        is_post_restore=True,
    )

    # Handle the user input
    await coordinator.handle_user_input(incoming, mock_ctx)

    # Verify conversation was appended, not replaced
    assert len(coordinator._conversation) == 5
    assert coordinator._conversation[0].text == "Hello"
    assert coordinator._conversation[1].text == "Hi there!"
    assert coordinator._conversation[2].text == "Help me"
    assert coordinator._conversation[3].text == "Sure, what do you need?"
    assert coordinator._conversation[4].text == "I need shipping help"


async def test_coordinator_handle_user_input_normal_flow():
    """Test that _HandoffCoordinator.handle_user_input handles normal flow correctly.

    In normal flow (no restore), the gateway sends the full conversation.
    The coordinator should replace its conversation with the incoming one.
    """
    from unittest.mock import AsyncMock

    from agent_framework._workflows._handoff import _HandoffCoordinator

    # Create a coordinator
    coordinator = _HandoffCoordinator(
        starting_agent_id="triage",
        specialist_ids={"specialist_a": "specialist_a"},
        input_gateway_id="gateway",
        termination_condition=lambda conv: False,
        id="test-coordinator",
    )

    # Set some initial conversation
    coordinator._conversation = [
        ChatMessage(role=Role.USER, text="Old message"),
    ]

    # Create mock context
    mock_ctx = MagicMock()
    mock_ctx.send_message = AsyncMock()

    # Normal flow: full conversation including new user message (is_post_restore=False by default)
    incoming = _ConversationWithUserInput(
        full_conversation=[
            ChatMessage(role=Role.USER, text="Hello"),
            ChatMessage(role=Role.ASSISTANT, text="Hi!"),
            ChatMessage(role=Role.USER, text="New message"),
        ],
        is_post_restore=False,
    )

    # Handle the user input
    await coordinator.handle_user_input(incoming, mock_ctx)

    # Verify conversation was replaced (normal flow with full history)
    assert len(coordinator._conversation) == 3
    assert coordinator._conversation[0].text == "Hello"
    assert coordinator._conversation[1].text == "Hi!"
    assert coordinator._conversation[2].text == "New message"


async def test_coordinator_handle_user_input_multiple_consecutive_user_messages():
    """Test that multiple consecutive USER messages in normal flow are handled correctly.

    This is a regression test for the edge case where a user submits multiple consecutive
    USER messages. The explicit is_post_restore flag ensures this doesn't get incorrectly
    detected as a post-restore scenario.
    """
    from unittest.mock import AsyncMock

    from agent_framework._workflows._handoff import _HandoffCoordinator

    # Create a coordinator with existing conversation
    coordinator = _HandoffCoordinator(
        starting_agent_id="triage",
        specialist_ids={"specialist_a": "specialist_a"},
        input_gateway_id="gateway",
        termination_condition=lambda conv: False,
        id="test-coordinator",
    )

    # Set existing conversation with 4 messages
    coordinator._conversation = [
        ChatMessage(role=Role.USER, text="Original message 1"),
        ChatMessage(role=Role.ASSISTANT, text="Response 1"),
        ChatMessage(role=Role.USER, text="Original message 2"),
        ChatMessage(role=Role.ASSISTANT, text="Response 2"),
    ]

    # Create mock context
    mock_ctx = MagicMock()
    mock_ctx.send_message = AsyncMock()

    # Normal flow: User sends multiple consecutive USER messages
    # This should REPLACE the conversation, not append to it
    incoming = _ConversationWithUserInput(
        full_conversation=[
            ChatMessage(role=Role.USER, text="New user message 1"),
            ChatMessage(role=Role.USER, text="New user message 2"),
        ],
        is_post_restore=False,  # Explicit flag - this is normal flow
    )

    # Handle the user input
    await coordinator.handle_user_input(incoming, mock_ctx)

    # Verify conversation was REPLACED (not appended)
    # Without the explicit flag, the old heuristic might incorrectly append
    assert len(coordinator._conversation) == 2
    assert coordinator._conversation[0].text == "New user message 1"
    assert coordinator._conversation[1].text == "New user message 2"
