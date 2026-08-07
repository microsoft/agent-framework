# Copyright (c) Microsoft. All rights reserved.

"""Tests for TOOL_CALL_RESULT event emission on approval resume flows."""

from __future__ import annotations

import json
from typing import Any

from agent_framework import AgentResponseUpdate, Content, FunctionTool
from conftest import StubAgent  # pyrefly: ignore[missing-import] # pyright: ignore[reportMissingImports]

from agent_framework_ag_ui._agent import AgentConfig
from agent_framework_ag_ui._agent_run import PendingApprovalEntry, PendingApprovalKey, run_agent_stream


def _make_weather_tool() -> FunctionTool:
    """Create a real executable weather tool with approval_mode='always_require'."""

    def get_weather(city: str) -> str:
        return f"Sunny in {city}"

    return FunctionTool(
        name="get_weather",
        description="Get the weather for a city",
        func=get_weather,
        approval_mode="always_require",
    )


async def test_approval_resume_emits_tool_call_result() -> None:
    """After approving a tool call, the resume stream should contain a TOOL_CALL_RESULT event.

    The message format follows the AG-UI approval pattern:
    - assistant message with tool_calls
    - tool message with {"accepted": true} content and toolCallId
    """
    tool_name = "get_weather"
    call_id = "call_abc123"
    weather_tool = _make_weather_tool()

    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="The weather is sunny.")], role="assistant")],
        default_options={"tools": [weather_tool]},
    )
    config = AgentConfig()

    # Build resume messages: user query, assistant tool call, approval response
    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "What's the weather in Seattle?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps({"city": "Seattle"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": True}),
            "toolCallId": call_id,
        },
    ]

    input_data: dict[str, Any] = {
        "thread_id": "thread-approval-result",
        "run_id": "run-resume",
        "messages": resume_messages,
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    event_types = [getattr(e, "type", None) for e in events]

    assert "RUN_STARTED" in event_types, f"Expected RUN_STARTED, got types: {event_types}"
    assert "RUN_FINISHED" in event_types, f"Expected RUN_FINISHED, got types: {event_types}"

    # TOOL_CALL_RESULT must be present for the approved tool
    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]

    assert len(tool_result_events) > 0, (
        f"Expected at least one TOOL_CALL_RESULT event for the approved tool, "
        f"but found none. Event types in stream: {event_types}"
    )

    result_event = tool_result_events[0]
    assert result_event.tool_call_id == call_id, (
        f"Expected TOOL_CALL_RESULT with tool_call_id={call_id}, got tool_call_id={result_event.tool_call_id}"
    )
    # Verify the result contains the actual tool execution output
    assert result_event.content == "Sunny in Seattle"


async def test_approval_resume_result_has_content() -> None:
    """TOOL_CALL_RESULT event from an approved tool should contain the execution result."""
    tool_name = "get_weather"
    call_id = "call_content_check"
    weather_tool = _make_weather_tool()

    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="Done.")], role="assistant")],
        default_options={"tools": [weather_tool]},
    )
    config = AgentConfig()

    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Check the weather"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps({"city": "Portland"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": True}),
            "toolCallId": call_id,
        },
    ]

    input_data: dict[str, Any] = {
        "thread_id": "thread-result-content",
        "run_id": "run-resume-2",
        "messages": resume_messages,
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]
    assert len(tool_result_events) == 1

    result_event = tool_result_events[0]
    assert result_event.tool_call_id == call_id
    assert result_event.role == "tool"
    # Verify the result contains the actual tool execution output (string returned directly)
    assert result_event.content == "Sunny in Portland"


async def test_approval_resume_snapshot_replaces_approval_payload_with_tool_result() -> None:
    """Approved HITL tools persist their executed result in MESSAGES_SNAPSHOT for replay."""
    from agent_framework_ag_ui._message_adapters import normalize_agui_input_messages

    call_id = "call_snapshot_replay"
    weather_tool = _make_weather_tool()
    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="The weather is sunny.")], role="assistant")],
        default_options={"tools": [weather_tool]},
    )
    config = AgentConfig()
    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "What's the weather in Seattle?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"city": "Seattle"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": True}),
            "toolCallId": call_id,
        },
    ]

    events: list[Any] = []
    async for event in run_agent_stream(
        {
            "thread_id": "thread-snapshot-replay",
            "run_id": "run-snapshot-replay",
            "messages": resume_messages,
        },
        agent,
        config,
    ):
        events.append(event)

    snapshots = [event.messages for event in events if getattr(event, "type", None) == "MESSAGES_SNAPSHOT"]
    assert snapshots
    snapshot_messages = [
        message.model_dump(by_alias=True, exclude_none=True) if hasattr(message, "model_dump") else message
        for message in snapshots[-1]
    ]
    tool_messages = [message for message in snapshot_messages if message.get("role") == "tool"]
    assert any(
        message.get("toolCallId") == call_id and message.get("content") == "Sunny in Seattle"
        for message in tool_messages
    )
    assert not any(message.get("content") == json.dumps({"accepted": True}) for message in tool_messages)

    replay_messages = snapshot_messages + [{"role": "user", "content": "What is the weather now?"}]
    provider_messages, _ = normalize_agui_input_messages(replay_messages)

    assert not any(
        content.type == "function_approval_response"
        for message in provider_messages
        for content in message.contents or []
    )
    assert any(
        content.type == "function_result" and content.call_id == call_id and content.result == "Sunny in Seattle"
        for message in provider_messages
        for content in message.contents or []
    )


async def test_no_approval_no_extra_tool_result() -> None:
    """When no approval response is present, no extra TOOL_CALL_RESULT events should be emitted."""
    agent = StubAgent(updates=[AgentResponseUpdate(contents=[Content.from_text(text="Hello.")], role="assistant")])
    config = AgentConfig()

    input_data: dict[str, Any] = {
        "thread_id": "thread-no-approval",
        "run_id": "run-normal",
        "messages": [{"role": "user", "content": "Hi"}],
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]
    assert len(tool_result_events) == 0, f"Unexpected TOOL_CALL_RESULT events: {tool_result_events}"


async def test_rejection_does_not_emit_tool_call_result() -> None:
    """Rejected tool calls should not produce TOOL_CALL_RESULT events."""
    tool_name = "get_weather"
    call_id = "call_rejected"
    weather_tool = _make_weather_tool()

    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="OK, I won't check.")], role="assistant")],
        default_options={"tools": [weather_tool]},
    )
    config = AgentConfig()

    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "What's the weather?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps({"city": "Denver"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": False}),
            "toolCallId": call_id,
        },
    ]

    input_data: dict[str, Any] = {
        "thread_id": "thread-rejection",
        "run_id": "run-rejected",
        "messages": resume_messages,
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]
    assert len(tool_result_events) == 0, (
        f"Expected no TOOL_CALL_RESULT for rejected tool, got {len(tool_result_events)}"
    )


def _make_temperature_tool() -> FunctionTool:
    """Create a real executable temperature tool with approval_mode='always_require'."""

    def get_temperature(city: str) -> str:
        return f"72F in {city}"

    return FunctionTool(
        name="get_temperature",
        description="Get the temperature for a city",
        func=get_temperature,
        approval_mode="always_require",
    )


async def test_mixed_approve_reject_emits_only_approved_tool_result() -> None:
    """When one tool call is approved and another rejected, only the approved one produces a TOOL_CALL_RESULT event."""
    weather_tool = _make_weather_tool()
    temperature_tool = _make_temperature_tool()
    approved_call_id = "call_approved"
    rejected_call_id = "call_rejected"

    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="Here are the results.")], role="assistant")],
        default_options={"tools": [weather_tool, temperature_tool]},
    )
    config = AgentConfig()

    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Weather and temperature in Seattle?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": approved_call_id,
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"city": "Seattle"}),
                    },
                },
                {
                    "id": rejected_call_id,
                    "type": "function",
                    "function": {
                        "name": "get_temperature",
                        "arguments": json.dumps({"city": "Seattle"}),
                    },
                },
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": True}),
            "toolCallId": approved_call_id,
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": False}),
            "toolCallId": rejected_call_id,
        },
    ]

    input_data: dict[str, Any] = {
        "thread_id": "thread-mixed",
        "run_id": "run-mixed",
        "messages": resume_messages,
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]

    # Only the approved tool call should produce a TOOL_CALL_RESULT event
    assert len(tool_result_events) == 1, (
        f"Expected exactly 1 TOOL_CALL_RESULT (approved only), got {len(tool_result_events)}"
    )
    assert tool_result_events[0].tool_call_id == approved_call_id
    assert tool_result_events[0].content == "Sunny in Seattle"


async def test_approval_resume_zero_updates_emits_tool_result() -> None:
    """When the agent produces zero updates, TOOL_CALL_RESULT events should still be emitted via the fallback path."""
    tool_name = "get_weather"
    call_id = "call_zero_updates"
    weather_tool = _make_weather_tool()

    agent = StubAgent(
        updates=[],
        default_options={"tools": [weather_tool]},
    )
    config = AgentConfig()

    resume_messages: list[dict[str, Any]] = [
        {"role": "user", "content": "What's the weather?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps({"city": "Boston"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": json.dumps({"accepted": True}),
            "toolCallId": call_id,
        },
    ]

    input_data: dict[str, Any] = {
        "thread_id": "thread-zero-updates",
        "run_id": "run-zero-updates",
        "messages": resume_messages,
    }

    events: list[Any] = []
    async for event in run_agent_stream(input_data, agent, config):
        events.append(event)

    event_types = [getattr(e, "type", None) for e in events]
    assert "RUN_STARTED" in event_types

    tool_result_events = [e for e in events if getattr(e, "type", None) == "TOOL_CALL_RESULT"]
    assert len(tool_result_events) == 1, (
        f"Expected 1 TOOL_CALL_RESULT in zero-updates fallback path, got {len(tool_result_events)}"
    )
    assert tool_result_events[0].tool_call_id == call_id
    assert tool_result_events[0].content == "Sunny in Boston"


async def test_resolve_approval_responses_returns_only_approved() -> None:
    """_resolve_approval_responses should return only approved results; rejection results go into messages only."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import _resolve_approval_responses

    weather_tool = _make_weather_tool()
    temperature_tool = _make_temperature_tool()
    approved_call_id = "call_a"
    rejected_call_id = "call_r"

    messages: list[Any] = [
        Message(role="user", contents=[Content.from_text(text="Hi")]),
        Message(
            role="assistant",
            contents=[
                Content(
                    type="function_approval_request",
                    id=approved_call_id,
                    function_call=Content(
                        type="function_call",
                        name="get_weather",
                        call_id=approved_call_id,
                        arguments='{"city": "NYC"}',
                    ),
                ),
                Content(
                    type="function_approval_request",
                    id=rejected_call_id,
                    function_call=Content(
                        type="function_call",
                        name="get_temperature",
                        call_id=rejected_call_id,
                        arguments='{"city": "NYC"}',
                    ),
                ),
            ],
        ),
        Message(
            role="user",
            contents=[
                Content(
                    type="function_approval_response",
                    id=approved_call_id,
                    approved=True,
                    function_call=Content(
                        type="function_call",
                        name="get_weather",
                        call_id=approved_call_id,
                        arguments='{"city": "NYC"}',
                    ),
                ),
                Content(
                    type="function_approval_response",
                    id=rejected_call_id,
                    approved=False,
                    function_call=Content(
                        type="function_call",
                        name="get_temperature",
                        call_id=rejected_call_id,
                        arguments='{"city": "NYC"}',
                    ),
                ),
            ],
        ),
    ]

    agent = StubAgent(
        updates=[],
        default_options={"tools": [weather_tool, temperature_tool]},
    )

    results = await _resolve_approval_responses(messages, [weather_tool, temperature_tool], agent, {})

    # Return value should only contain approved results
    assert len(results) == 1
    assert results[0].call_id == approved_call_id
    assert results[0].type == "function_result"

    # Rejection result should be written into messages (by _replace_approval_contents_with_results)
    all_contents = [c for msg in messages for c in msg.contents]
    rejection_results = [c for c in all_contents if c.type == "function_result" and c.call_id == rejected_call_id]
    assert len(rejection_results) == 1
    assert "rejected" in str(rejection_results[0].result).lower()


async def test_resolve_approval_responses_preserves_follow_up_user_input_group() -> None:
    """Approval-time follow-up requests stay grouped and do not emit a synthetic tool result."""
    from agent_framework import Message
    from agent_framework.exceptions import UserInputRequiredException

    from agent_framework_ag_ui._agent_run import _resolve_approval_responses

    def request_consent() -> str:
        raise UserInputRequiredException(
            contents=[
                Content.from_oauth_consent_request(consent_link="https://example.com/consent-1"),
                Content.from_oauth_consent_request(consent_link="https://example.com/consent-2"),
            ]
        )

    consent_tool = FunctionTool(
        name="request_consent",
        description="Request two consent steps",
        func=request_consent,
        approval_mode="always_require",
    )
    function_call = Content.from_function_call(call_id="call_consent", name="request_consent", arguments="{}")
    approval_request = Content.from_function_approval_request(id="approval_consent", function_call=function_call)
    messages: list[Any] = [
        Message(role="assistant", contents=[approval_request]),
        Message(role="user", contents=[approval_request.to_function_approval_response(approved=True)]),
    ]
    agent = StubAgent(updates=[], default_options={"tools": [consent_tool]})

    results = await _resolve_approval_responses(messages, [consent_tool], agent, {})

    follow_up_requests = [content for message in messages for content in message.contents if content.user_input_request]
    assert results == []
    assert [request.consent_link for request in follow_up_requests] == [
        "https://example.com/consent-1",
        "https://example.com/consent-2",
    ]
    assert not [content for message in messages for content in message.contents if content.type == "function_result"]
    assert any(message.role == "assistant" and message.contents == follow_up_requests for message in messages)


async def test_resolve_approval_responses_returns_failure_when_grouped_execution_raises(
    monkeypatch: Any,
) -> None:
    """A grouped-execution failure produces one deterministic result for the approved call."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import _resolve_approval_responses

    async def fail_grouped_execution(**kwargs: Any) -> tuple[list[list[Content]], bool]:
        del kwargs
        raise RuntimeError("execution failed")

    monkeypatch.setattr(
        "agent_framework_ag_ui._agent_run._try_execute_function_call_groups",
        fail_grouped_execution,
    )
    weather_tool = _make_weather_tool()
    function_call = Content.from_function_call(
        call_id="call_execution_failure",
        name="get_weather",
        arguments='{"city": "Seattle"}',
    )
    approval_request = Content.from_function_approval_request(
        id="approval_execution_failure",
        function_call=function_call,
    )
    messages: list[Any] = [
        Message(role="assistant", contents=[approval_request]),
        Message(role="user", contents=[approval_request.to_function_approval_response(approved=True)]),
    ]
    agent = StubAgent(updates=[], default_options={"tools": [weather_tool]})

    results = await _resolve_approval_responses(messages, [weather_tool], agent, {})

    assert len(results) == 1
    assert results[0].type == "function_result"
    assert results[0].call_id == "call_execution_failure"
    assert results[0].result == "Error: Tool call invocation failed."
    assert [
        content.result for message in messages for content in message.contents if content.type == "function_result"
    ] == ["Error: Tool call invocation failed."]


async def test_resolve_approval_responses_keeps_fresh_occurrence_when_canonical_id_is_reused() -> None:
    """A completed occurrence cannot consume a later approval that reuses its canonical call id."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import (
        _make_pending_approval_entry,
        _pending_approval_key,
        _resolve_approval_responses,
    )

    executions: list[str] = []

    def guarded_write(value: str) -> str:
        executions.append(value)
        return f"wrote:{value}"

    tool = FunctionTool(
        name="guarded_write",
        description="Write a value",
        func=guarded_write,
        approval_mode="always_require",
    )
    call_id = "call_reused"
    first_call = Content.from_function_call(call_id=call_id, name="guarded_write", arguments={"value": "same"})
    second_call = Content.from_function_call(call_id=call_id, name="guarded_write", arguments={"value": "same"})
    messages = [
        Message(role="assistant", contents=[first_call]),
        Message(role="tool", contents=[Content.from_function_result(call_id=call_id, result="already wrote")]),
        Message(
            role="user",
            contents=[Content.from_function_approval_response(approved=True, id=call_id, function_call=first_call)],
        ),
        Message(role="assistant", contents=[second_call]),
        Message(
            role="user",
            contents=[Content.from_function_approval_response(approved=True, id=call_id, function_call=second_call)],
        ),
    ]
    thread_id = "thread-reused"
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] = {
        _pending_approval_key(thread_id, call_id): _make_pending_approval_entry(
            "guarded_write",
            '{"value":"same"}',
            request_id=call_id,
            interrupt_id=call_id,
        )
    }
    agent = StubAgent(updates=[], default_options={"tools": [tool]})

    results = await _resolve_approval_responses(
        messages,
        [tool],
        agent,
        {},
        pending_approvals,
        thread_id,
    )

    assert executions == ["same"]
    assert [result.result for result in results] == ["wrote:same"]
    assert pending_approvals == {}
    assert not [
        content for message in messages for content in message.contents if content.type == "function_approval_response"
    ]


async def test_resolve_approval_responses_uses_fresh_decision_when_canonical_id_is_reused() -> None:
    """A historical approval does not conflict with a fresh rejection for a reused call id."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import (
        _make_pending_approval_entry,
        _pending_approval_key,
        _resolve_approval_responses,
    )

    executions: list[str] = []

    def guarded_write(value: str) -> str:
        executions.append(value)
        return f"wrote:{value}"

    tool = FunctionTool(
        name="guarded_write",
        description="Write a value",
        func=guarded_write,
        approval_mode="always_require",
    )
    call_id = "call_reused_decision"
    first_call = Content.from_function_call(call_id=call_id, name="guarded_write", arguments={"value": "same"})
    second_call = Content.from_function_call(call_id=call_id, name="guarded_write", arguments={"value": "same"})
    messages = [
        Message(role="assistant", contents=[first_call]),
        Message(role="tool", contents=[Content.from_function_result(call_id=call_id, result="already wrote")]),
        Message(
            role="user",
            contents=[Content.from_function_approval_response(approved=True, id=call_id, function_call=first_call)],
        ),
        Message(role="assistant", contents=[second_call]),
        Message(
            role="user",
            contents=[Content.from_function_approval_response(approved=False, id=call_id, function_call=second_call)],
        ),
    ]
    thread_id = "thread-reused-decision"
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] = {
        _pending_approval_key(thread_id, call_id): _make_pending_approval_entry(
            "guarded_write",
            '{"value":"same"}',
            request_id=call_id,
            interrupt_id=call_id,
        )
    }
    agent = StubAgent(updates=[], default_options={"tools": [tool]})

    results = await _resolve_approval_responses(
        messages,
        [tool],
        agent,
        {},
        pending_approvals,
        thread_id,
    )

    assert executions == []
    assert results == []
    assert pending_approvals == {}
    assert [
        content.result for message in messages for content in message.contents if content.type == "function_result"
    ] == ["already wrote", "Error: Tool call invocation was rejected by user."]
    assert not [
        content for message in messages for content in message.contents if content.type == "function_approval_response"
    ]


async def test_resolve_approval_responses_does_not_fall_back_when_fresh_reused_response_is_invalid() -> None:
    """An invalid fresh response cannot consume pending state through a valid historical response."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import (
        _make_pending_approval_entry,
        _pending_approval_key,
        _resolve_approval_responses,
    )

    executions: list[str] = []

    def guarded_write(value: str) -> str:
        executions.append(value)
        return f"wrote:{value}"

    tool = FunctionTool(
        name="guarded_write",
        description="Write a value",
        func=guarded_write,
        approval_mode="always_require",
    )
    call_id = "call_reused_invalid"
    first_call = Content.from_function_call(call_id=call_id, name="guarded_write", arguments={"value": "same"})
    edited_second_call = Content.from_function_call(
        call_id=call_id,
        name="guarded_write",
        arguments={"value": "tampered"},
    )
    messages = [
        Message(role="assistant", contents=[first_call]),
        Message(role="tool", contents=[Content.from_function_result(call_id=call_id, result="already wrote")]),
        Message(
            role="user",
            contents=[Content.from_function_approval_response(approved=True, id=call_id, function_call=first_call)],
        ),
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id=call_id,
                    name="guarded_write",
                    arguments={"value": "same"},
                )
            ],
        ),
        Message(
            role="user",
            contents=[
                Content.from_function_approval_response(
                    approved=True,
                    id=call_id,
                    function_call=edited_second_call,
                )
            ],
        ),
    ]
    thread_id = "thread-reused-invalid"
    pending_entry = _make_pending_approval_entry(
        "guarded_write",
        '{"value":"same"}',
        request_id=call_id,
        interrupt_id=call_id,
    )
    pending_key = _pending_approval_key(thread_id, call_id)
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] = {pending_key: pending_entry}
    agent = StubAgent(updates=[], default_options={"tools": [tool]})

    results = await _resolve_approval_responses(
        messages,
        [tool],
        agent,
        {},
        pending_approvals,
        thread_id,
    )

    assert executions == []
    assert results == []
    assert pending_approvals == {pending_key: pending_entry}
    assert not [
        content for message in messages for content in message.contents if content.type == "function_approval_response"
    ]


async def test_resolve_approval_responses_consumes_trusted_hosted_pending_entry() -> None:
    """A server-collected hosted response remains provider-bound but cannot be replayed."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import (
        _make_pending_approval_entry,
        _pending_approval_key,
        _resolve_approval_responses,
    )

    call_id = "mcpr_hosted"
    server_label = "hosted-mcp"
    hosted_call = Content.from_function_call(
        call_id=call_id,
        name="hosted_write",
        arguments={"value": "same"},
        additional_properties={"server_label": server_label},
    )
    hosted_response = Content.from_function_approval_response(
        approved=True,
        id=call_id,
        function_call=hosted_call,
    )
    messages = [Message(role="user", contents=[hosted_response])]
    thread_id = "thread-hosted-collected"
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] = {
        _pending_approval_key(thread_id, call_id): _make_pending_approval_entry(
            "hosted_write",
            '{"value":"same"}',
            request_id=call_id,
            interrupt_id=call_id,
            server_label=server_label,
        )
    }

    results = await _resolve_approval_responses(
        messages,
        [],
        StubAgent(updates=[]),
        {},
        pending_approvals,
        thread_id,
    )

    assert results == []
    assert pending_approvals == {}
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].contents == [hosted_response]


async def test_resolve_approval_responses_uses_fresh_response_across_pending_aliases() -> None:
    """The interrupt-id response wins over historical replay under the request-id alias."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import (
        _make_pending_approval_entry,
        _pending_approval_key,
        _resolve_approval_responses,
    )

    executions: list[str] = []

    def guarded_write(value: str) -> str:
        executions.append(value)
        return f"wrote:{value}"

    tool = FunctionTool(name="guarded_write", description="Write a value", func=guarded_write)
    request_id = "approval_alias"
    interrupt_id = "call_alias"
    function_call = Content.from_function_call(
        call_id=interrupt_id,
        name="guarded_write",
        arguments={"value": "same"},
    )
    messages = [
        Message(role="assistant", contents=[function_call]),
        Message(
            role="user",
            contents=[
                Content.from_function_approval_response(
                    approved=True,
                    id=request_id,
                    function_call=function_call,
                )
            ],
        ),
        Message(
            role="user",
            contents=[
                Content.from_function_approval_response(
                    approved=False,
                    id=interrupt_id,
                    function_call=function_call,
                )
            ],
        ),
    ]
    thread_id = "thread-alias"
    pending_entry = _make_pending_approval_entry(
        "guarded_write",
        '{"value":"same"}',
        request_id=request_id,
        interrupt_id=interrupt_id,
    )
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] = {
        _pending_approval_key(thread_id, request_id): pending_entry,
        _pending_approval_key(thread_id, interrupt_id): pending_entry,
    }

    results = await _resolve_approval_responses(
        messages,
        [tool],
        StubAgent(updates=[], default_options={"tools": [tool]}),
        {},
        pending_approvals,
        thread_id,
    )

    assert executions == []
    assert results == []
    assert pending_approvals == {}
    assert [
        content.result for message in messages for content in message.contents if content.type == "function_result"
    ] == ["Error: Tool call invocation was rejected by user."]


async def test_resolve_approval_responses_rejects_fresh_unknown_alias_without_historical_fallback() -> None:
    """An unknown fresh response id cannot consume pending state through a trusted historical alias."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import (
        _make_pending_approval_entry,
        _pending_approval_key,
        _resolve_approval_responses,
    )

    executions: list[str] = []

    def guarded_write(value: str) -> str:
        executions.append(value)
        return f"wrote:{value}"

    tool = FunctionTool(name="guarded_write", description="Write a value", func=guarded_write)
    request_id = "approval_known"
    interrupt_id = "call_known"
    function_call = Content.from_function_call(
        call_id=interrupt_id,
        name="guarded_write",
        arguments={"value": "same"},
    )
    messages = [
        Message(role="assistant", contents=[function_call]),
        Message(
            role="user",
            contents=[
                Content.from_function_approval_response(
                    approved=True,
                    id=request_id,
                    function_call=function_call,
                ),
                Content.from_function_approval_response(
                    approved=True,
                    id="approval_unknown",
                    function_call=function_call,
                ),
            ],
        ),
    ]
    thread_id = "thread-unknown-alias"
    pending_entry = _make_pending_approval_entry(
        "guarded_write",
        '{"value":"same"}',
        request_id=request_id,
        interrupt_id=interrupt_id,
    )
    request_key = _pending_approval_key(thread_id, request_id)
    interrupt_key = _pending_approval_key(thread_id, interrupt_id)
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] = {
        request_key: pending_entry,
        interrupt_key: pending_entry,
    }

    results = await _resolve_approval_responses(
        messages,
        [tool],
        StubAgent(updates=[], default_options={"tools": [tool]}),
        {},
        pending_approvals,
        thread_id,
    )

    assert executions == []
    assert results == []
    assert pending_approvals == {request_key: pending_entry, interrupt_key: pending_entry}
    assert not [
        content for message in messages for content in message.contents if content.type == "function_approval_response"
    ]


async def test_resolve_approval_responses_rejects_forged_call_id_for_valid_response_alias() -> None:
    """A trusted response id cannot authorize a result under an unknown function-call id."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import (
        _make_pending_approval_entry,
        _pending_approval_key,
        _resolve_approval_responses,
    )

    executions: list[str] = []

    def guarded_write(value: str) -> str:
        executions.append(value)
        return f"wrote:{value}"

    tool = FunctionTool(name="guarded_write", description="Write a value", func=guarded_write)
    request_id = "approval_valid"
    interrupt_id = "call_valid"
    actual_call = Content.from_function_call(
        call_id=interrupt_id,
        name="guarded_write",
        arguments={"value": "same"},
    )
    forged_call = Content.from_function_call(
        call_id="call_forged",
        name="guarded_write",
        arguments={"value": "same"},
    )
    messages = [
        Message(role="assistant", contents=[actual_call]),
        Message(
            role="user",
            contents=[
                Content.from_function_approval_response(
                    approved=True,
                    id=request_id,
                    function_call=forged_call,
                )
            ],
        ),
    ]
    thread_id = "thread-forged-call"
    pending_entry = _make_pending_approval_entry(
        "guarded_write",
        '{"value":"same"}',
        request_id=request_id,
        interrupt_id=interrupt_id,
    )
    request_key = _pending_approval_key(thread_id, request_id)
    interrupt_key = _pending_approval_key(thread_id, interrupt_id)
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] = {
        request_key: pending_entry,
        interrupt_key: pending_entry,
    }

    results = await _resolve_approval_responses(
        messages,
        [tool],
        StubAgent(updates=[], default_options={"tools": [tool]}),
        {},
        pending_approvals,
        thread_id,
    )

    assert executions == []
    assert results == []
    assert pending_approvals == {request_key: pending_entry, interrupt_key: pending_entry}
    assert not [
        content
        for message in messages
        for content in message.contents
        if content.type in {"function_approval_response", "function_result"}
    ]


async def test_resolve_approval_responses_rejects_call_id_from_different_pending_entry() -> None:
    """A response id from one approval cannot be paired with another approval's call id."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import (
        _make_pending_approval_entry,
        _pending_approval_key,
        _resolve_approval_responses,
    )

    executions: list[str] = []

    def guarded_write(value: str) -> str:
        executions.append(value)
        return f"wrote:{value}"

    tool = FunctionTool(name="guarded_write", description="Write a value", func=guarded_write)
    request_a = "approval_a"
    call_a = Content.from_function_call(
        call_id="call_a",
        name="guarded_write",
        arguments={"value": "same"},
    )
    request_b = "approval_b"
    call_b = Content.from_function_call(
        call_id="call_b",
        name="guarded_write",
        arguments={"value": "same"},
    )
    messages = [
        Message(role="assistant", contents=[call_a]),
        Message(
            role="user",
            contents=[
                Content.from_function_approval_response(approved=True, id=request_a, function_call=call_a),
                Content.from_function_approval_response(approved=False, id=request_a, function_call=call_b),
            ],
        ),
    ]
    thread_id = "thread-crossed-aliases"
    pending_a = _make_pending_approval_entry(
        "guarded_write",
        '{"value":"same"}',
        request_id=request_a,
        interrupt_id="call_a",
    )
    pending_b = _make_pending_approval_entry(
        "guarded_write",
        '{"value":"same"}',
        request_id=request_b,
        interrupt_id="call_b",
    )
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] = {
        _pending_approval_key(thread_id, request_a): pending_a,
        _pending_approval_key(thread_id, "call_a"): pending_a,
        _pending_approval_key(thread_id, request_b): pending_b,
        _pending_approval_key(thread_id, "call_b"): pending_b,
    }
    expected_pending = dict(pending_approvals)

    results = await _resolve_approval_responses(
        messages,
        [tool],
        StubAgent(updates=[], default_options={"tools": [tool]}),
        {},
        pending_approvals,
        thread_id,
    )

    assert executions == []
    assert results == []
    assert pending_approvals == expected_pending
    assert not [
        content
        for message in messages
        for content in message.contents
        if content.type in {"function_approval_response", "function_result"}
    ]


async def test_resolve_approval_responses_without_registry_uses_latest_duplicate_decision() -> None:
    """The optional no-registry path preserves the established last-response-wins behavior."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import _resolve_approval_responses

    executions: list[str] = []

    def guarded_write(value: str) -> str:
        executions.append(value)
        return f"wrote:{value}"

    tool = FunctionTool(name="guarded_write", description="Write a value", func=guarded_write)
    call_id = "call_no_registry"
    function_call = Content.from_function_call(
        call_id=call_id,
        name="guarded_write",
        arguments={"value": "same"},
    )
    messages = [
        Message(role="assistant", contents=[function_call]),
        Message(
            role="user",
            contents=[
                Content.from_function_approval_response(approved=True, id=call_id, function_call=function_call),
                Content.from_function_approval_response(approved=False, id=call_id, function_call=function_call),
            ],
        ),
    ]

    results = await _resolve_approval_responses(
        messages,
        [tool],
        StubAgent(updates=[], default_options={"tools": [tool]}),
        {},
    )

    assert executions == []
    assert results == []
    assert [
        content.result for message in messages for content in message.contents if content.type == "function_result"
    ] == ["Error: Tool call invocation was rejected by user."]


async def test_resolve_approval_responses_legacy_registry_uses_latest_duplicate_decision() -> None:
    """Legacy string entries group duplicate decisions by their matched response id."""
    from agent_framework import Message

    from agent_framework_ag_ui._agent_run import _pending_approval_key, _resolve_approval_responses

    executions: list[str] = []

    def guarded_write(value: str) -> str:
        executions.append(value)
        return f"wrote:{value}"

    tool = FunctionTool(name="guarded_write", description="Write a value", func=guarded_write)
    approval_id = "approval_legacy"
    first_call = Content.from_function_call(
        call_id="call_legacy_old",
        name="guarded_write",
        arguments={"value": "same"},
    )
    latest_call = Content.from_function_call(
        call_id="call_legacy_new",
        name="guarded_write",
        arguments={"value": "same"},
    )
    messages = [
        Message(
            role="user",
            contents=[
                Content.from_function_approval_response(
                    approved=True,
                    id=approval_id,
                    function_call=first_call,
                ),
                Content.from_function_approval_response(
                    approved=False,
                    id=approval_id,
                    function_call=latest_call,
                ),
            ],
        )
    ]
    thread_id = "thread-legacy"
    pending_approvals: dict[PendingApprovalKey, PendingApprovalEntry] = {
        _pending_approval_key(thread_id, approval_id): "guarded_write"
    }

    results = await _resolve_approval_responses(
        messages,
        [tool],
        StubAgent(updates=[], default_options={"tools": [tool]}),
        {},
        pending_approvals,
        thread_id,
    )

    assert executions == []
    assert results == []
    assert pending_approvals == {}
    assert [
        content.result for message in messages for content in message.contents if content.type == "function_result"
    ] == ["Error: Tool call invocation was rejected by user."]


class TestApprovalToolResultDisplayChannel:
    """Approved tools using ``state_update(..., tool_result=...)`` must route the
    display payload to the UI event while ``flow.tool_results`` still receives
    the LLM-bound text. The HITL approval emitter is separate from the standard
    streaming emitter, so it gets its own coverage.
    """

    def test_approval_emits_display_payload_when_marker_present(self) -> None:
        from agent_framework_ag_ui import state_update
        from agent_framework_ag_ui._agent_run import _make_approval_tool_result_events

        display_payload = {"city": "Seattle", "temp": 14, "conditions": "foggy"}
        inner = state_update(text="14°C, foggy", tool_result=display_payload)
        resolved = Content.from_function_result(call_id="call_disp", result=[inner])

        events = _make_approval_tool_result_events([resolved])

        assert len(events) == 1
        # UI event must carry the serialized display payload, NOT the LLM text.
        assert json.loads(events[0].content) == display_payload
        assert events[0].content != "14°C, foggy"

    def test_approval_falls_back_to_text_when_no_marker(self) -> None:
        """Backward compat: without a display marker, behaviour is unchanged."""
        from agent_framework_ag_ui._agent_run import _make_approval_tool_result_events

        resolved = Content.from_function_result(call_id="call_plain", result="Sunny in Seattle")

        events = _make_approval_tool_result_events([resolved])

        assert len(events) == 1
        assert events[0].content == "Sunny in Seattle"
