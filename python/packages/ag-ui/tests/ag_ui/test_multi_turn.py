# Copyright (c) Microsoft. All rights reserved.

"""Multi-turn conversation tests: POST → collect events → extract snapshot → POST again.

These tests catch round-trip fidelity bugs: if MessagesSnapshotEvent produces a
malformed message list, the second turn will fail during normalize_agui_input_messages()
or produce incorrect behavior.
"""

from __future__ import annotations

import json
from typing import Any

from agent_framework import AgentResponseUpdate, Content
from conftest import StubAgent
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sse_helpers import parse_sse_response, parse_sse_to_event_stream

from agent_framework_ag_ui import AgentFrameworkAgent, add_agent_framework_fastapi_endpoint


def _build_app_with_agent(updates: list[AgentResponseUpdate], **kwargs: Any) -> FastAPI:
    stub = StubAgent(updates=updates)
    agent = AgentFrameworkAgent(agent=stub, **kwargs)
    app = FastAPI()
    add_agent_framework_fastapi_endpoint(app, agent)
    return app


def _extract_snapshot_messages(response_content: bytes) -> list[dict[str, Any]]:
    """Extract the latest MessagesSnapshotEvent.messages from SSE response bytes."""
    raw_events = parse_sse_response(response_content)
    snapshot_msgs: list[dict[str, Any]] | None = None
    for event in raw_events:
        if event.get("type") == "MESSAGES_SNAPSHOT":
            snapshot_msgs = event.get("messages", [])
    assert snapshot_msgs is not None, "No MESSAGES_SNAPSHOT event found"
    return snapshot_msgs


# ── Basic multi-turn chat ──


def test_basic_multi_turn_chat() -> None:
    """Turn 1: user→assistant. Turn 2: user→assistant with prior history from snapshot."""
    app = _build_app_with_agent(
        [
            AgentResponseUpdate(contents=[Content.from_text(text="Hello! How can I help?")], role="assistant"),
        ]
    )
    client = TestClient(app)

    # Turn 1
    resp1 = client.post(
        "/",
        json={
            "messages": [{"role": "user", "content": "Hi there"}],
            "threadId": "thread-multi",
            "runId": "run-1",
        },
    )
    assert resp1.status_code == 200
    stream1 = parse_sse_to_event_stream(resp1.content)
    stream1.assert_bookends()
    stream1.assert_text_messages_balanced()

    # Extract snapshot messages from turn 1
    snapshot_messages = _extract_snapshot_messages(resp1.content)

    # Turn 2: send snapshot messages + new user message
    turn2_messages = list(snapshot_messages) + [{"role": "user", "content": "Tell me more"}]
    resp2 = client.post(
        "/",
        json={
            "messages": turn2_messages,
            "threadId": "thread-multi",
            "runId": "run-2",
        },
    )
    assert resp2.status_code == 200
    stream2 = parse_sse_to_event_stream(resp2.content)
    stream2.assert_bookends()
    stream2.assert_text_messages_balanced()
    stream2.assert_no_run_error()


# ── Tool call history round-trip ──


def test_tool_call_history_round_trips() -> None:
    """Turn 1: tool call + result. Turn 2: snapshot messages correctly reconstruct tool history."""
    app = _build_app_with_agent(
        [
            AgentResponseUpdate(
                contents=[Content.from_function_call(name="get_weather", call_id="call-1", arguments='{"city": "SF"}')],
                role="assistant",
            ),
            AgentResponseUpdate(
                contents=[Content.from_function_result(call_id="call-1", result="72°F")],
                role="assistant",
            ),
            AgentResponseUpdate(
                contents=[Content.from_text(text="It's warm!")],
                role="assistant",
            ),
        ]
    )
    client = TestClient(app)

    # Turn 1
    resp1 = client.post(
        "/",
        json={
            "messages": [{"role": "user", "content": "What's the weather?"}],
            "threadId": "thread-tool-multi",
            "runId": "run-1",
        },
    )
    assert resp1.status_code == 200
    stream1 = parse_sse_to_event_stream(resp1.content)
    stream1.assert_tool_calls_balanced()

    # Extract snapshot and verify it has tool history
    snapshot_messages = _extract_snapshot_messages(resp1.content)
    roles = [m.get("role") for m in snapshot_messages]
    assert "tool" in roles or "assistant" in roles, f"Expected tool/assistant messages in snapshot, got: {roles}"

    # Turn 2: send snapshot + new question
    turn2_messages = list(snapshot_messages) + [{"role": "user", "content": "What about tomorrow?"}]
    resp2 = client.post(
        "/",
        json={
            "messages": turn2_messages,
            "threadId": "thread-tool-multi",
            "runId": "run-2",
        },
    )
    assert resp2.status_code == 200
    stream2 = parse_sse_to_event_stream(resp2.content)
    stream2.assert_bookends()
    stream2.assert_no_run_error()


# ── Approval interrupt/resume round-trip ──


async def test_approval_interrupt_resume_round_trip() -> None:
    """Turn 1: approval request → interrupt with confirm_changes. Turn 2: confirm_changes result → confirmation text.

    The confirm_changes flow uses a specific message format that bypasses the agent
    and directly emits a confirmation text message.
    """
    from event_stream import EventStream

    steps = [{"description": "Execute task", "status": "enabled"}]

    # Build agent with predictive state and confirmation
    stub = StubAgent(
        updates=[
            AgentResponseUpdate(
                contents=[
                    Content.from_function_call(
                        name="generate_task_steps",
                        call_id="call-steps",
                        arguments=json.dumps({"steps": steps}),
                    )
                ],
                role="assistant",
            ),
        ]
    )
    agent = AgentFrameworkAgent(
        agent=stub,
        state_schema={"tasks": {"type": "array"}},
        predict_state_config={"tasks": {"tool": "generate_task_steps", "tool_argument": "steps"}},
        require_confirmation=True,
    )

    # Turn 1
    events1 = [
        e
        async for e in agent.run(
            {
                "thread_id": "thread-approval-multi",
                "run_id": "run-1",
                "messages": [{"role": "user", "content": "Plan my tasks"}],
                "state": {"tasks": []},
            }
        )
    ]
    stream1 = EventStream(events1)
    stream1.assert_bookends()
    stream1.assert_tool_calls_balanced()

    # Should have interrupt with function_approval_request
    finished1 = stream1.last("RUN_FINISHED")
    interrupt1 = finished1.model_dump().get("interrupt")
    assert interrupt1, "Expected interrupt in RUN_FINISHED"

    # Verify confirm_changes tool call was emitted
    tool_starts = stream1.get("TOOL_CALL_START")
    tool_names = [getattr(s, "tool_call_name", None) for s in tool_starts]
    assert "confirm_changes" in tool_names, f"Expected confirm_changes in tool calls, got {tool_names}"

    # Turn 2: Direct confirm_changes response (the way CopilotKit sends it)
    # Construct the messages as CopilotKit would - with the confirm_changes tool call
    # and a tool result
    confirm_tool = [s for s in tool_starts if getattr(s, "tool_call_name", None) == "confirm_changes"][0]
    confirm_id = confirm_tool.tool_call_id
    confirm_args = None
    for e in stream1.get("TOOL_CALL_ARGS"):
        if e.tool_call_id == confirm_id:
            confirm_args = e.delta
            break

    turn2_messages = [
        {"role": "user", "content": "Plan my tasks"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": confirm_id,
                    "type": "function",
                    "function": {"name": "confirm_changes", "arguments": confirm_args or "{}"},
                },
            ],
        },
        {
            "role": "tool",
            "toolCallId": confirm_id,
            "content": json.dumps({"accepted": True, "steps": steps}),
        },
    ]

    events2 = [
        e
        async for e in agent.run(
            {
                "thread_id": "thread-approval-multi",
                "run_id": "run-2",
                "messages": turn2_messages,
                "state": {"tasks": []},
            }
        )
    ]
    stream2 = EventStream(events2)
    stream2.assert_bookends()
    stream2.assert_text_messages_balanced()
    stream2.assert_no_run_error()

    # Turn 2 should have confirmation text (the approval handler generates it)
    text_events = stream2.get("TEXT_MESSAGE_CONTENT")
    assert text_events, "Expected confirmation text message in turn 2"

    # Turn 2 should NOT have interrupt (approval completed)
    finished2 = stream2.last("RUN_FINISHED")
    interrupt2 = finished2.model_dump().get("interrupt")
    assert not interrupt2, f"Expected no interrupt after approval, got {interrupt2}"


# ── Workflow interrupt/resume round-trip ──
# Note: Workflow tests use async agent.run() directly instead of HTTP TestClient
# because the sync TestClient runs in a different event loop, which conflicts
# with the workflow's asyncio Queue.


async def test_workflow_interrupt_resume_round_trip() -> None:
    """Turn 1: workflow request_info → interrupt. Turn 2: resume → completion."""
    from event_stream import EventStream

    from agent_framework_ag_ui_examples.agents.subgraphs_agent import subgraphs_agent

    agent = subgraphs_agent()

    # Turn 1: initial request → flight interrupt
    events1 = [
        event
        async for event in agent.run(
            {
                "messages": [{"role": "user", "content": "Plan a trip to SF"}],
                "thread_id": "thread-wf-multi",
                "run_id": "run-1",
            }
        )
    ]
    stream1 = EventStream(events1)
    stream1.assert_bookends()
    stream1.assert_no_run_error()

    finished1 = stream1.last("RUN_FINISHED")
    interrupt1 = finished1.model_dump().get("interrupt")
    assert interrupt1, "Expected flight interrupt"
    assert interrupt1[0]["value"]["agent"] == "flights"

    # Turn 2: resume with flight selection
    events2 = [
        event
        async for event in agent.run(
            {
                "messages": [],
                "thread_id": "thread-wf-multi",
                "run_id": "run-2",
                "resume": {
                    "interrupts": [
                        {
                            "id": interrupt1[0]["id"],
                            "value": json.dumps(
                                {
                                    "airline": "United",
                                    "departure": "Amsterdam (AMS)",
                                    "arrival": "San Francisco (SFO)",
                                    "price": "$720",
                                    "duration": "12h 15m",
                                }
                            ),
                        }
                    ],
                },
            }
        )
    ]
    stream2 = EventStream(events2)
    stream2.assert_bookends()
    stream2.assert_no_run_error()

    # Should now have hotel interrupt
    finished2 = stream2.last("RUN_FINISHED")
    interrupt2 = finished2.model_dump().get("interrupt")
    assert interrupt2, "Expected hotel interrupt"
    assert interrupt2[0]["value"]["agent"] == "hotels"
