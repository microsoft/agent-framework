# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

import pytest

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    BaseAgent,
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


async def test_handoff_routes_to_specialist_and_requests_user_input():
    triage = _RecordingAgent(name="triage", handoff_to="specialist")
    specialist = _RecordingAgent(name="specialist")

    workflow = HandoffBuilder(participants=[triage, specialist]).set_coordinator("triage").build()

    events = await _drain(workflow.run_stream("Need help with a refund"))

    assert triage.calls, "Starting agent should receive initial conversation"
    assert specialist.calls, "Specialist should be invoked after handoff"
    assert len(specialist.calls[0]) == 2  # user + triage reply

    requests = [ev for ev in events if isinstance(ev, RequestInfoEvent)]
    assert requests, "Workflow should request additional user input"
    request_payload = requests[-1].data
    assert isinstance(request_payload, HandoffUserInputRequest)
    assert len(request_payload.conversation) == 4  # user, triage tool call, tool ack, specialist
    assert request_payload.conversation[2].role == Role.TOOL
    assert request_payload.conversation[3].role == Role.ASSISTANT
    assert "specialist reply" in request_payload.conversation[3].text

    follow_up = await _drain(workflow.send_responses_streaming({requests[-1].request_id: "Thanks"}))
    assert any(isinstance(ev, RequestInfoEvent) for ev in follow_up)


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
