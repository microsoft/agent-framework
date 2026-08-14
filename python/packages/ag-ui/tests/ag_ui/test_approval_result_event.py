# Copyright (c) Microsoft. All rights reserved.

"""Public event-stream tests for approval result projection."""

from __future__ import annotations

import json
from typing import Any

from ag_ui.core import ToolCallResultEvent
from agent_framework import AgentResponseUpdate, Content, FunctionTool
from agent_framework.exceptions import UserInputRequiredException
from conftest import StubAgent  # pyrefly: ignore[missing-import] # pyright: ignore[reportMissingImports]

from agent_framework_ag_ui._agent import AgentConfig
from agent_framework_ag_ui._agent_run import run_agent_stream
from agent_framework_ag_ui._approval_lifecycle import ApprovalExecutionOwner
from agent_framework_ag_ui._approval_state import InMemoryAGUIApprovalStateStore


def _weather_tool(executions: list[str]) -> FunctionTool:
    def get_weather(city: str) -> str:
        executions.append(city)
        return f"Sunny in {city}"

    return FunctionTool(
        name="get_weather",
        description="Get the weather for a city",
        func=get_weather,
        approval_mode="always_require",
    )


async def _run_resume(
    *,
    thread_id: str,
    calls: list[tuple[str, str]],
    decisions: list[tuple[str, bool]],
    executions: list[str],
) -> list[Any]:
    tool = _weather_tool(executions)
    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="Done.")], role="assistant")],
        default_options={"tools": [tool]},
    )
    store = InMemoryAGUIApprovalStateStore()
    for call_id, city in calls:
        store.register(
            owner=ApprovalExecutionOwner.LOCAL,
            thread_ids=[thread_id],
            name="get_weather",
            arguments=json.dumps({"city": city}, sort_keys=True, separators=(",", ":")),
            request_id=call_id,
            interrupt_id=call_id,
        )

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Check the weather"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": json.dumps({"city": city})},
                }
                for call_id, city in calls
            ],
        },
    ]
    events: list[Any] = []
    async for event in run_agent_stream(
        {
            "thread_id": thread_id,
            "run_id": "resume-run",
            "messages": messages,
            "resume": [
                {"interruptId": call_id, "status": "resolved", "payload": {"accepted": accepted}}
                for call_id, accepted in decisions
            ],
        },
        agent,
        AgentConfig(),
        approval_state_store=store,
    ):
        events.append(event)
    return events


async def _run_custom_approval(tool: FunctionTool) -> tuple[list[Any], StubAgent]:
    agent = StubAgent(
        updates=[AgentResponseUpdate(contents=[Content.from_text(text="Done.")], role="assistant")],
        default_options={"tools": [tool]},
    )
    store = InMemoryAGUIApprovalStateStore()
    store.register(
        owner=ApprovalExecutionOwner.LOCAL,
        thread_ids=["thread-custom"],
        name=tool.name,
        arguments="{}",
        request_id="approval-custom",
        interrupt_id="call-custom",
    )
    events = [
        event
        async for event in run_agent_stream(
            {
                "thread_id": "thread-custom",
                "run_id": "resume-custom",
                "messages": [{"role": "user", "content": "Continue"}],
                "resume": [{"interruptId": "call-custom", "status": "resolved", "payload": {"approved": True}}],
            },
            agent,
            AgentConfig(),
            approval_state_store=store,
        )
    ]
    return events, agent


async def test_approved_call_emits_one_live_result_under_original_identity() -> None:
    executions: list[str] = []

    events = await _run_resume(
        thread_id="thread-approved",
        calls=[("call-weather", "Seattle")],
        decisions=[("call-weather", True)],
        executions=executions,
    )

    results = [event for event in events if isinstance(event, ToolCallResultEvent)]
    assert executions == ["Seattle"]
    assert [(event.tool_call_id, event.content) for event in results] == [("call-weather", "Sunny in Seattle")]


async def test_rejected_call_does_not_execute_or_emit_live_result() -> None:
    executions: list[str] = []

    events = await _run_resume(
        thread_id="thread-rejected",
        calls=[("call-weather", "Seattle")],
        decisions=[("call-weather", False)],
        executions=executions,
    )

    assert executions == []
    assert not [event for event in events if getattr(event, "type", None) == "TOOL_CALL_RESULT"]


async def test_mixed_batch_preserves_approved_result_identity_and_order() -> None:
    executions: list[str] = []

    events = await _run_resume(
        thread_id="thread-mixed",
        calls=[("call-seattle", "Seattle"), ("call-portland", "Portland")],
        decisions=[("call-seattle", True), ("call-portland", False)],
        executions=executions,
    )

    results = [event for event in events if isinstance(event, ToolCallResultEvent)]
    assert executions == ["Seattle"]
    assert [(event.tool_call_id, event.content) for event in results] == [("call-seattle", "Sunny in Seattle")]


async def test_approval_follow_up_group_remains_in_history_without_live_tool_result() -> None:
    """Approval-time user-input requests remain grouped without becoming terminal tool results."""

    def request_consent() -> str:
        raise UserInputRequiredException(
            contents=[
                Content.from_oauth_consent_request(consent_link="https://example.com/first"),
                Content.from_oauth_consent_request(consent_link="https://example.com/second"),
            ]
        )

    events, agent = await _run_custom_approval(
        FunctionTool(name="request_consent", description="Request consent", func=request_consent)
    )

    assert not [event for event in events if getattr(event, "type", None) == "TOOL_CALL_RESULT"]
    requests = [
        content
        for message in agent.messages_received
        for content in message.contents
        if isinstance(content, Content) and content.user_input_request
    ]
    assert [request.consent_link for request in requests] == [
        "https://example.com/first",
        "https://example.com/second",
    ]


async def test_approval_execution_failure_emits_one_terminal_error_result() -> None:
    """An approved tool failure produces one deterministic terminal result."""

    def fail() -> str:
        raise RuntimeError("secret failure detail")

    events, _ = await _run_custom_approval(FunctionTool(name="fail", description="Fail", func=fail))

    results = [event for event in events if isinstance(event, ToolCallResultEvent)]
    assert [(event.tool_call_id, event.content) for event in results] == [("call-custom", "Error: Function failed.")]


async def test_no_approval_path_emits_no_approval_specific_duplicate_result() -> None:
    """An ordinary provider tool result is projected once without approval bookkeeping."""
    agent = StubAgent(
        updates=[
            AgentResponseUpdate(
                contents=[Content.from_function_result(call_id="call-ordinary", result="ordinary result")],
                role="tool",
            )
        ]
    )

    events = [
        event
        async for event in run_agent_stream(
            {
                "thread_id": "thread-ordinary",
                "run_id": "run-ordinary",
                "messages": [{"role": "user", "content": "Run it"}],
            },
            agent,
            AgentConfig(),
        )
    ]

    results = [event for event in events if isinstance(event, ToolCallResultEvent)]
    assert [(event.tool_call_id, event.content) for event in results] == [("call-ordinary", "ordinary result")]
