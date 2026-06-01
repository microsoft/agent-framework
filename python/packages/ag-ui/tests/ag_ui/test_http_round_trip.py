# Copyright (c) Microsoft. All rights reserved.

"""HTTP round-trip tests: POST → SSE bytes → parse → validate event sequence.

These tests exercise the full HTTP pipeline using FastAPI TestClient,
parsing the raw SSE byte stream and validating through EventStream assertions.
"""

from __future__ import annotations

from typing import Any

from agent_framework import AgentResponseUpdate, Content, WorkflowBuilder, WorkflowContext, executor
from conftest import StubAgent
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sse_helpers import parse_sse_response, parse_sse_to_event_stream
from typing_extensions import Never

from agent_framework_ag_ui import AgentFrameworkAgent, AgentFrameworkWorkflow, add_agent_framework_fastapi_endpoint


def _build_app_with_agent(updates: list[AgentResponseUpdate], **kwargs: Any) -> FastAPI:
    stub = StubAgent(updates=updates)
    agent = AgentFrameworkAgent(agent=stub, **kwargs)
    app = FastAPI()
    add_agent_framework_fastapi_endpoint(app, agent)
    return app


def _build_app_with_workflow(workflow_builder: WorkflowBuilder) -> FastAPI:
    workflow = workflow_builder.build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    app = FastAPI()
    add_agent_framework_fastapi_endpoint(app, wrapper)
    return app


USER_PAYLOAD: dict[str, Any] = {
    "messages": [{"role": "user", "content": "Hello"}],
    "threadId": "thread-http",
    "runId": "run-http",
}


# ── Agentic chat SSE round-trip ──


def test_agentic_chat_sse_round_trip() -> None:
    """Full HTTP round-trip: POST → SSE bytes → parse → validate event sequence."""
    app = _build_app_with_agent(
        [
            AgentResponseUpdate(contents=[Content.from_text(text="Hi there!")], role="assistant"),
        ]
    )
    client = TestClient(app)
    response = client.post("/", json=USER_PAYLOAD)

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    stream = parse_sse_to_event_stream(response.content)
    stream.assert_bookends()
    stream.assert_text_messages_balanced()
    stream.assert_no_run_error()
    stream.assert_ordered_types(
        [
            "RUN_STARTED",
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_END",
            "MESSAGES_SNAPSHOT",
            "RUN_FINISHED",
        ]
    )


# ── Tool call SSE round-trip ──


def test_tool_call_sse_round_trip() -> None:
    """Tool call events survive SSE encoding/parsing round-trip."""
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
    response = client.post("/", json=USER_PAYLOAD)

    stream = parse_sse_to_event_stream(response.content)
    stream.assert_bookends()
    stream.assert_tool_calls_balanced()
    stream.assert_text_messages_balanced()

    # Verify tool call details survive SSE encoding
    start = stream.first("TOOL_CALL_START")
    assert start.tool_call_name == "get_weather"
    assert start.tool_call_id == "call-1"


# ── SSE encoding fidelity ──


def test_sse_event_encoding_fidelity() -> None:
    """Every event from agent.run() produces a valid SSE data: line that round-trips."""
    app = _build_app_with_agent(
        [
            AgentResponseUpdate(contents=[Content.from_text(text="Hello world")], role="assistant"),
        ]
    )
    client = TestClient(app)
    response = client.post("/", json=USER_PAYLOAD)

    raw_events = parse_sse_response(response.content)
    assert len(raw_events) > 0, "No SSE events parsed"

    # Every event should have a 'type' field
    for event in raw_events:
        assert "type" in event, f"Event missing 'type': {event}"

    # Event types should include the expected ones
    event_types = [e["type"] for e in raw_events]
    assert "RUN_STARTED" in event_types
    assert "RUN_FINISHED" in event_types


# ── camelCase request field acceptance ──


def test_camel_case_request_fields_accepted() -> None:
    """Request with camelCase fields (runId, threadId) is correctly parsed."""
    app = _build_app_with_agent(
        [
            AgentResponseUpdate(contents=[Content.from_text(text="ok")], role="assistant"),
        ]
    )
    client = TestClient(app)
    response = client.post(
        "/",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "runId": "camel-run",
            "threadId": "camel-thread",
        },
    )
    assert response.status_code == 200

    stream = parse_sse_to_event_stream(response.content)
    stream.assert_bookends()


# ── Workflow SSE round-trip ──


def test_workflow_sse_round_trip() -> None:
    """Workflow events survive SSE encoding/parsing."""

    @executor(id="greeter")
    async def greeter(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("Hello from workflow!")

    app = _build_app_with_workflow(WorkflowBuilder(start_executor=greeter))
    client = TestClient(app)
    response = client.post("/", json=USER_PAYLOAD)

    assert response.status_code == 200
    stream = parse_sse_to_event_stream(response.content)
    stream.assert_bookends()
    stream.assert_no_run_error()
    stream.assert_text_messages_balanced()
    stream.assert_has_type("STEP_STARTED")


# ── Error handling ──


def test_empty_messages_returns_valid_sse() -> None:
    """Empty messages list still returns a valid SSE stream with bookends."""
    app = _build_app_with_agent(
        [
            AgentResponseUpdate(contents=[Content.from_text(text="ok")], role="assistant"),
        ]
    )
    client = TestClient(app)
    response = client.post("/", json={"messages": []})

    assert response.status_code == 200
    stream = parse_sse_to_event_stream(response.content)
    stream.assert_bookends()


def test_sse_response_headers() -> None:
    """SSE response has correct headers for event streaming."""
    app = _build_app_with_agent(
        [
            AgentResponseUpdate(contents=[Content.from_text(text="ok")], role="assistant"),
        ]
    )
    client = TestClient(app)
    response = client.post("/", json=USER_PAYLOAD)

    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert response.headers.get("cache-control") == "no-cache"


# ── MCP tool call SSE round-trip ──


def test_mcp_tool_call_sse_round_trip() -> None:
    """MCP tool call + result events survive SSE encoding/parsing round-trip."""
    app = _build_app_with_agent(
        [
            AgentResponseUpdate(
                contents=[
                    Content.from_mcp_server_tool_call(
                        call_id="mcp-1",
                        tool_name="search",
                        server_name="brave",
                        arguments={"query": "weather"},
                    )
                ],
                role="assistant",
            ),
            AgentResponseUpdate(
                contents=[
                    Content.from_mcp_server_tool_result(
                        call_id="mcp-1",
                        output={"results": ["sunny"]},
                    )
                ],
                role="assistant",
            ),
            AgentResponseUpdate(
                contents=[Content.from_text(text="It's sunny!")],
                role="assistant",
            ),
        ]
    )
    client = TestClient(app)
    response = client.post("/", json=USER_PAYLOAD)

    assert response.status_code == 200
    stream = parse_sse_to_event_stream(response.content)
    stream.assert_bookends()
    stream.assert_tool_calls_balanced()
    stream.assert_text_messages_balanced()
    stream.assert_no_run_error()

    # Verify MCP tool call details survive SSE encoding
    start = stream.first("TOOL_CALL_START")
    assert start.tool_call_name == "search"
    assert start.tool_call_id == "mcp-1"

    # Verify the result came through
    result = stream.first("TOOL_CALL_RESULT")
    assert "sunny" in result.content


# ── Text reasoning SSE round-trip ──


def test_text_reasoning_sse_round_trip() -> None:
    """Text reasoning events survive SSE encoding/parsing round-trip."""
    app = _build_app_with_agent(
        [
            AgentResponseUpdate(
                contents=[
                    Content.from_text_reasoning(
                        id="reason-1",
                        text="The user wants weather info, I should use a tool.",
                    )
                ],
                role="assistant",
            ),
            AgentResponseUpdate(
                contents=[Content.from_text(text="Let me check the weather.")],
                role="assistant",
            ),
        ]
    )
    client = TestClient(app)
    response = client.post("/", json=USER_PAYLOAD)

    assert response.status_code == 200
    stream = parse_sse_to_event_stream(response.content)
    stream.assert_bookends()
    stream.assert_text_messages_balanced()
    stream.assert_no_run_error()
    stream.assert_has_type("REASONING_START")
    stream.assert_has_type("REASONING_MESSAGE_CONTENT")
    stream.assert_has_type("REASONING_END")

    # Verify reasoning content survives SSE encoding
    raw_events = parse_sse_response(response.content)
    reasoning_content = [e for e in raw_events if e["type"] == "REASONING_MESSAGE_CONTENT"]
    assert len(reasoning_content) == 1
    assert "weather" in reasoning_content[0]["delta"]


def test_text_reasoning_with_encrypted_value_sse_round_trip() -> None:
    """Reasoning with protected_data emits ReasoningEncryptedValue through SSE."""
    app = _build_app_with_agent(
        [
            AgentResponseUpdate(
                contents=[
                    Content.from_text_reasoning(
                        id="reason-enc",
                        text="visible reasoning",
                        protected_data="encrypted-payload-abc123",
                    )
                ],
                role="assistant",
            ),
            AgentResponseUpdate(
                contents=[Content.from_text(text="Done.")],
                role="assistant",
            ),
        ]
    )
    client = TestClient(app)
    response = client.post("/", json=USER_PAYLOAD)

    assert response.status_code == 200
    stream = parse_sse_to_event_stream(response.content)
    stream.assert_bookends()
    stream.assert_no_run_error()
    stream.assert_has_type("REASONING_ENCRYPTED_VALUE")

    raw_events = parse_sse_response(response.content)
    encrypted = [e for e in raw_events if e["type"] == "REASONING_ENCRYPTED_VALUE"]
    assert len(encrypted) == 1
    assert encrypted[0]["encryptedValue"] == "encrypted-payload-abc123"
    assert encrypted[0]["entityId"] == "reason-enc"
    assert encrypted[0]["subtype"] == "message"
