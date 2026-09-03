# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for ResponsesHostServer with a real Foundry endpoint.

These tests exercise the full HTTP pipeline using httpx.AsyncClient with
ASGITransport — no real server process is started. Most tests talk to a real
Foundry project endpoint. Deterministic cross-package regressions replace only
the external Responses HTTP boundary.

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT - The Microsoft Foundry project endpoint URL.
    FOUNDRY_MODEL            - The model deployment name (e.g. gpt-4o).
"""

from __future__ import annotations

import asyncio
import base64
import json
import multiprocessing
import multiprocessing.process
import os
import re
import socket
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import MagicMock

import httpx
import pytest
from agent_framework import (
    Agent,
    Content,
    Executor,
    InMemoryHistoryProvider,
    Message,
    SlidingWindowStrategy,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from azure.ai.agentserver.responses import InMemoryResponseProvider, ResponsesServerOptions
from azure.identity import AzureCliCredential
from openai import AsyncOpenAI
from typing_extensions import Never

from agent_framework_foundry_hosting import ResponsesHostServer

# ---------------------------------------------------------------------------
# Skip / marker helpers
# ---------------------------------------------------------------------------

skip_if_foundry_hosting_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("FOUNDRY_PROJECT_ENDPOINT", "") in ("", "https://test-project.services.ai.azure.com/")
    or os.getenv("FOUNDRY_MODEL", "") == "",
    reason="No real FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL provided; skipping integration tests.",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def server() -> ResponsesHostServer:
    """Create a ResponsesHostServer backed by a real Foundry agent."""
    client = FoundryChatClient(credential=AzureCliCredential())  # pyrefly: ignore[bad-argument-type]

    agent = Agent(
        client=client,  # ty: ignore[invalid-argument-type]
        instructions="You are a concise assistant. Keep answers very short (one or two sentences).",
    )

    return ResponsesHostServer(agent, store=InMemoryResponseProvider())


@tool
async def get_weather(location: Annotated[str, "The city name"]) -> str:
    """Get the current weather in a given location."""
    return f"The weather in {location} is 72°F and sunny."


@pytest.fixture(params=["agent_server", "agent"], ids=["agent-server-history", "agent-history"])
def history_server(request: pytest.FixtureRequest) -> ResponsesHostServer:
    """Create a real Foundry server for each model-history source."""
    client = FoundryChatClient(credential=AzureCliCredential())  # pyrefly: ignore[bad-argument-type]
    agent = Agent(
        client=client,  # ty: ignore[invalid-argument-type]
        instructions="You are a concise assistant. Keep answers very short (one or two sentences).",
        default_options={"store": True},  # pyrefly: ignore[bad-argument-type]
    )
    return ResponsesHostServer(
        agent,
        store=InMemoryResponseProvider(),
        history_source=request.param,
    )


@pytest.fixture(params=["agent_server", "agent"], ids=["agent-server-history", "agent-history"])
def history_server_with_tools(request: pytest.FixtureRequest) -> ResponsesHostServer:
    """Create a real Foundry tool-calling server for each model-history source."""
    client = FoundryChatClient(credential=AzureCliCredential())  # pyrefly: ignore[bad-argument-type]
    agent = Agent(
        client=client,  # ty: ignore[invalid-argument-type]
        instructions="You are a concise assistant. Use the provided tools when appropriate. Keep answers very short.",
        tools=[get_weather],
        default_options={"store": True},  # pyrefly: ignore[bad-argument-type]
    )
    return ResponsesHostServer(
        agent,
        store=InMemoryResponseProvider(),
        history_source=request.param,
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


async def _post_json(
    server: ResponsesHostServer,
    payload: dict[str, Any],
) -> httpx.Response:
    """Send a POST /responses request with a raw JSON payload."""
    transport = httpx.ASGITransport(app=server)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/responses", json=payload, timeout=120)


def _parse_sse_events(body: str) -> list[dict[str, Any]]:
    """Parse SSE text into a list of event dicts with 'event' and 'data' keys."""
    events: list[dict[str, Any]] = []
    current_event: str | None = None
    current_data_lines: list[str] = []

    for line in body.split("\n"):
        if line.startswith("event: "):
            current_event = line[len("event: ") :]
        elif line.startswith("data: "):
            current_data_lines.append(line[len("data: ") :])
        elif line.strip() == "" and current_event is not None:
            data_str = "\n".join(current_data_lines)
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = data_str
            events.append({"event": current_event, "data": data})
            current_event = None
            current_data_lines = []

    return events


def _sse_event_types(events: list[dict[str, Any]]) -> list[str]:
    """Extract event type strings from parsed SSE events."""
    return [e["event"] for e in events]


# ---------------------------------------------------------------------------
# Tests — basic text input
# ---------------------------------------------------------------------------


class TestBasicText:
    """Simple text-in / text-out round trips."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_simple_text_non_streaming(self, server: ResponsesHostServer) -> None:
        """Non-streaming: send a text prompt and get a completed response."""
        resp = await _post_json(
            server,
            {
                "input": "Say hello in exactly three words.",
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        # There should be exactly one output item with text
        output_messages = [o for o in body["output"] if o["type"] == "message"]
        assert len(output_messages) == 1
        text_parts = [c for c in output_messages[0]["content"] if c["type"] == "output_text"]
        assert len(text_parts) >= 1
        assert len(text_parts[0]["text"]) > 0

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_simple_text_streaming(self, server: ResponsesHostServer) -> None:
        """Streaming: send a text prompt and verify SSE lifecycle events."""
        resp = await _post_json(
            server,
            {
                "input": "Say hello in exactly three words.",
                "stream": True,
            },
        )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        assert types[0] == "response.created"
        assert types[1] == "response.in_progress"
        assert types[-1] == "response.completed"
        assert "response.output_text.delta" in types
        assert "response.output_text.done" in types

        # The done event should have accumulated text
        done_events = [e for e in events if e["event"] == "response.output_text.done"]
        assert len(done_events) >= 1
        assert len(done_events[0]["data"]["text"]) > 0


# ---------------------------------------------------------------------------
# Tests — structured content input
# ---------------------------------------------------------------------------


class TestStructuredContentInput:
    """Structured content arrays: text + images, text + files."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_text_array_input(self, server: ResponsesHostServer) -> None:
        """Multiple input_text parts in one message."""
        resp = await _post_json(
            server,
            {
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "My name is Alice."},
                            {"type": "input_text", "text": "What is my name?"},
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        # The response should mention Alice
        output_messages = [o for o in body["output"] if o["type"] == "message"]
        assert len(output_messages) == 1
        output_text = output_messages[0]["content"][0]["text"]
        assert "alice" in output_text.lower()

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_input_image_url(self, server: ResponsesHostServer) -> None:
        """Send an image via URL and ask the model about it."""
        resp = await _post_json(
            server,
            {
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "What animal is in this image? Reply in one word."},
                            {
                                "type": "input_image",
                                "image_url": "https://cdn.pixabay.com/photo/2024/02/28/07/42/european-shorthair-8601492_640.jpg",
                            },
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        output_messages = [o for o in body["output"] if o["type"] == "message"]
        assert len(output_messages) == 1
        output_text = output_messages[0]["content"][0]["text"].lower()
        assert "cat" in output_text

    @pytest.mark.xfail(
        reason=(
            "Foundry Responses API rejects inline base64 data URIs in image_url with "
            "'invalid_payload: ... is not a valid absolute URI'. It requires an absolute "
            "http(s) URI or an uploaded file_id. Re-enable if Foundry adds data-URI support."
        ),
        strict=False,
    )
    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_input_image_file_data(self, server: ResponsesHostServer) -> None:
        """Send a local image file as inline base64 data URI."""
        image_path = Path(__file__).resolve().parent / "test_assets" / "sample_image.jpg"  # noqa: ASYNC240
        image_bytes = image_path.read_bytes()
        b64 = base64.b64encode(image_bytes).decode()
        data_uri = f"data:image/jpeg;base64,{b64}"

        resp = await _post_json(
            server,
            {
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "What animal is in this image? Reply in one word."},
                            {"type": "input_image", "image_url": data_uri},
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        output_messages = [o for o in body["output"] if o["type"] == "message"]
        assert len(output_messages) == 1
        output_text = output_messages[0]["content"][0]["text"].lower()
        assert "cat" in output_text

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_input_file_data(self, server: ResponsesHostServer) -> None:
        """Send a small text file as inline file_data (base64 data URI)."""
        text_content = "The capital of France is Paris."
        b64 = base64.b64encode(text_content.encode()).decode()
        data_uri = f"data:text/plain;base64,{b64}"

        resp = await _post_json(
            server,
            {
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "What is the capital mentioned in the attached file?"},
                            {"type": "input_file", "file_data": data_uri, "filename": "info.txt"},
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        output_messages = [o for o in body["output"] if o["type"] == "message"]
        assert len(output_messages) == 1
        output_text = output_messages[0]["content"][0]["text"].lower()
        assert "paris" in output_text

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_input_pdf_file_data(self, server: ResponsesHostServer) -> None:
        """Send a real PDF file as inline file_data (base64 data URI)."""
        pdf_path = Path(__file__).resolve().parent / "test_assets" / "sample.pdf"  # noqa: ASYNC240
        pdf_bytes = pdf_path.read_bytes()
        b64 = base64.b64encode(pdf_bytes).decode()
        data_uri = f"data:application/pdf;base64,{b64}"

        resp = await _post_json(
            server,
            {
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Summarize this PDF in one sentence."},
                            {"type": "input_file", "file_data": data_uri, "filename": "sample.pdf"},
                        ],
                    }
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        output_messages = [o for o in body["output"] if o["type"] == "message"]
        assert len(output_messages) == 1
        output_text = output_messages[0]["content"][0]["text"]
        assert "microsoft" in output_text.lower()


# ---------------------------------------------------------------------------
# Tests — multi-turn conversations
# ---------------------------------------------------------------------------


class TestMultiTurn:
    """Multi-round conversations using previous_response_id."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_explicit_agent_framework_message_conversation(self) -> None:
        """Agent Framework Message and Content primitives preserve explicit conversation history."""
        agent = Agent(
            client=FoundryChatClient(credential=AzureCliCredential()),  # ty: ignore[invalid-argument-type]
            instructions="You are a concise assistant. Keep answers very short.",
        )

        response = await agent.run([
            Message(role="user", contents=[Content.from_text("My favorite color is blue.")]),
            Message(role="assistant", contents=[Content.from_text("Your favorite color is blue.")]),
            Message(role="user", contents=[Content.from_text("What is my favorite color?")]),
        ])

        assert response.text is not None
        assert "blue" in response.text.lower()

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_explicit_user_assistant_user_conversation(self, server: ResponsesHostServer) -> None:
        """Explicit user, assistant, and follow-up user messages form one conversation."""
        resp = await _post_json(
            server,
            {
                "input": [
                    {"type": "message", "role": "user", "content": "My favorite color is blue."},
                    {"type": "message", "role": "assistant", "content": "Your favorite color is blue."},
                    {"type": "message", "role": "user", "content": "What is my favorite color?"},
                ],
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        output_messages = [item for item in body["output"] if item["type"] == "message"]
        assert len(output_messages) == 1
        assert "blue" in output_messages[0]["content"][0]["text"].lower()

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_two_turn_conversation(self, history_server: ResponsesHostServer) -> None:
        """Turn 1: introduce context. Turn 2: ask about it using previous_response_id."""
        # Turn 1
        resp1 = await _post_json(
            history_server,
            {
                "input": "My favorite color is blue. Remember that.",
                "stream": False,
            },
        )

        assert resp1.status_code == 200
        body1 = resp1.json()
        assert body1["status"] == "completed"
        response_id_1 = body1["id"]

        # Turn 2 — references turn 1
        resp2 = await _post_json(
            history_server,
            {
                "input": "What is my favorite color?",
                "stream": False,
                "previous_response_id": response_id_1,
            },
        )

        assert resp2.status_code == 200
        body2 = resp2.json()
        assert body2["status"] == "completed"
        output_messages = [o for o in body2["output"] if o["type"] == "message"]
        assert len(output_messages) == 1
        output_text = output_messages[0]["content"][0]["text"].lower()
        assert "blue" in output_text

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_three_turn_conversation(self, history_server: ResponsesHostServer) -> None:
        """Three sequential turns to verify history accumulates correctly."""
        # Turn 1
        resp1 = await _post_json(
            history_server,
            {
                "input": "I have a pet dog named Max.",
                "stream": False,
            },
        )
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        # Turn 2
        resp2 = await _post_json(
            history_server,
            {
                "input": "I also have a cat named Luna.",
                "stream": False,
                "previous_response_id": id1,
            },
        )
        assert resp2.status_code == 200
        id2 = resp2.json()["id"]

        # Turn 3 — should remember both pets
        resp3 = await _post_json(
            history_server,
            {
                "input": "What are my pets' names?",
                "stream": False,
                "previous_response_id": id2,
            },
        )
        assert resp3.status_code == 200
        body3 = resp3.json()
        output_messages = [o for o in body3["output"] if o["type"] == "message"]
        assert len(output_messages) == 1
        output_text = output_messages[0]["content"][0]["text"].lower()
        assert "max" in output_text
        assert "luna" in output_text

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_multi_turn_streaming(self, history_server: ResponsesHostServer) -> None:
        """Multi-turn conversation with streaming on the second turn."""
        # Turn 1 — non-streaming
        resp1 = await _post_json(
            history_server,
            {
                "input": "My favorite number is 42.",
                "stream": False,
            },
        )
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        # Turn 2 — streaming
        resp2 = await _post_json(
            history_server,
            {
                "input": "What is my favorite number?",
                "stream": True,
                "previous_response_id": id1,
            },
        )
        assert resp2.status_code == 200
        assert "text/event-stream" in resp2.headers["content-type"]

        events = _parse_sse_events(resp2.text)
        types = _sse_event_types(events)

        assert types[0] == "response.created"
        assert types[-1] == "response.completed"
        assert "response.output_text.done" in types

        done_events = [e for e in events if e["event"] == "response.output_text.done"]
        assert "42" in done_events[0]["data"]["text"]

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_agent_history_with_in_memory_provider(self) -> None:
        """Regular agent mode can persist in-session history while the model service stays stateless."""
        agent = Agent(
            client=FoundryChatClient(credential=AzureCliCredential()),  # ty: ignore[invalid-argument-type]
            instructions="Answer questions using the supplied conversation history. Keep answers very short.",
            context_providers=[InMemoryHistoryProvider()],
            default_options={"store": False},  # pyrefly: ignore[bad-argument-type]
        )
        server = ResponsesHostServer(
            agent,
            store=InMemoryResponseProvider(),
            history_source="agent",
        )

        first = await _post_json(
            server,
            {
                "input": "My favorite city is Lisbon. Remember that.",
                "stream": False,
            },
        )
        assert first.status_code == 200

        second = await _post_json(
            server,
            {
                "input": "What is my favorite city?",
                "stream": False,
                "previous_response_id": first.json()["id"],
            },
        )

        assert second.status_code == 200
        output_messages = [item for item in second.json()["output"] if item["type"] == "message"]
        assert len(output_messages) == 1
        assert "lisbon" in output_messages[0]["content"][0]["text"].lower()


class TestReasoningHostedMcpReplay:
    """Regression coverage for stateless reasoning + hosted MCP replay."""

    async def test_second_turn_replays_mcp_call_with_encrypted_reasoning(self) -> None:
        """A hosted agent replays an encrypted reasoning and MCP pair when store is disabled."""
        call_count = 0
        reasoning_id = "rs_576d207b35d96b3200pkcXkMwXAij920Wcv7WhRXiMPiLdOA63"
        provider_payloads: list[dict[str, Any]] = []

        def _message(message_id: str) -> dict[str, Any]:
            return {
                "id": message_id,
                "content": [{"annotations": [], "text": "Microsoft Agent Framework", "type": "output_text"}],
                "role": "assistant",
                "status": "completed",
                "type": "message",
            }

        def _response(response_id: str, output: list[dict[str, Any]]) -> dict[str, Any]:
            return {
                "id": response_id,
                "created_at": 0,
                "model": "gpt-5.4",
                "object": "response",
                "output": output,
                "parallel_tool_calls": True,
                "tool_choice": "auto",
                "tools": [],
                "status": "completed",
            }

        def _streaming_response(response_id: str, output: list[dict[str, Any]]) -> httpx.Response:
            response = _response(response_id, output)
            events: list[dict[str, Any]] = []
            for output_index, item in enumerate(output):
                events.extend([
                    {
                        "type": "response.output_item.added",
                        "output_index": output_index,
                        "item": {**item, "status": "in_progress"},
                        "sequence_number": len(events),
                    },
                    {
                        "type": "response.output_item.done",
                        "output_index": output_index,
                        "item": item,
                        "sequence_number": len(events) + 1,
                    },
                ])
            events.append({
                "type": "response.completed",
                "response": response,
                "sequence_number": len(events),
            })
            body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

        async def foundry_responses_boundary(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            payload = json.loads(request.content)
            provider_payloads.append(payload)
            if call_count == 1:
                return _streaming_response(
                    "resp_first",
                    [
                        {
                            "encrypted_content": "encrypted-reasoning",
                            "id": reasoning_id,
                            "summary": [{"text": "The MCP server has the answer.", "type": "summary_text"}],
                            "type": "reasoning",
                        },
                        {
                            "id": "mcp_paired",
                            "arguments": '{"query":"Agent Framework overview"}',
                            "name": "microsoft_docs_search",
                            "server_label": "Microsoft_Learn",
                            "type": "mcp_call",
                            "output": "Microsoft Agent Framework",
                            "status": "completed",
                        },
                        _message("msg_first"),
                    ],
                )

            input_items = payload["input"]
            reasoning_items = [item for item in input_items if item.get("type") == "reasoning"]
            mcp_calls = [item for item in input_items if item.get("type") == "mcp_call"]
            if (
                len(reasoning_items) != 1
                or reasoning_items[0].get("encrypted_content") != "encrypted-reasoning"
                or len(mcp_calls) != 1
                or mcp_calls[0].get("output") != "Microsoft Agent Framework"
            ):
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": (
                                "The stateless request did not replay the complete encrypted "
                                "reasoning and hosted MCP call/result group."
                            ),
                            "type": "invalid_request_error",
                            "code": "invalid_request_error",
                        }
                    },
                )

            return _streaming_response("resp_second", [_message("msg_second")])

        transport = httpx.MockTransport(foundry_responses_boundary)
        responses_client = AsyncOpenAI(
            api_key="test-key",
            http_client=httpx.AsyncClient(transport=transport),
            max_retries=0,
        )
        project_client = MagicMock()
        project_client.get_openai_client.return_value = responses_client
        client = FoundryChatClient(
            project_client=project_client,
            model="gpt-5.4",
            compaction_strategy=SlidingWindowStrategy(keep_last_groups=4),
        )
        learn_mcp = client.get_mcp_tool(
            name="Microsoft Learn",
            url="https://learn.microsoft.com/api/mcp",
            allowed_tools=["microsoft_docs_search"],
            approval_mode="never_require",
        )
        agent = Agent(
            client=client,  # ty: ignore[invalid-argument-type]
            instructions=(
                "Always use the Microsoft Learn MCP tool to answer documentation questions. "
                "Keep the final answer to one short sentence."
            ),
            tools=[learn_mcp],
            default_options={  # pyrefly: ignore[bad-argument-type]
                "store": False,
                "reasoning": {"effort": "low", "summary": "auto"},
                "include": ["reasoning.encrypted_content"],
            },
        )
        server = ResponsesHostServer(agent, store=InMemoryResponseProvider())

        first = await _post_json(
            server,
            {
                "input": "Use Microsoft Learn MCP to find the official Agent Framework overview and state its title.",
                "stream": False,
            },
        )

        assert first.status_code == 200
        first_body = first.json()
        assert first_body["status"] == "completed", first_body.get("error")
        first_output_types = {item["type"] for item in first_body["output"]}
        assert {"reasoning", "mcp_call"} <= first_output_types
        first_reasoning = next(item for item in first_body["output"] if item["type"] == "reasoning")
        assert first_reasoning["id"] == reasoning_id
        assert first_reasoning["encrypted_content"] == "encrypted-reasoning"
        assert "reasoning.encrypted_content" in provider_payloads[0]["include"]

        second = await _post_json(
            server,
            {
                "input": "Which Microsoft framework did you just look up? Reply with only its name.",
                "stream": False,
                "previous_response_id": first_body["id"],
            },
        )

        assert second.status_code == 200
        second_body = second.json()
        assert second_body["status"] == "completed", second_body.get("error")
        assert call_count == 2

        second_input = provider_payloads[1]["input"]
        reasoning_items = [item for item in second_input if item.get("type") == "reasoning"]
        mcp_calls = [item for item in second_input if item.get("type") == "mcp_call"]
        assert len(reasoning_items) == 1
        assert reasoning_items[0]["id"] == reasoning_id
        assert reasoning_items[0]["encrypted_content"] == "encrypted-reasoning"
        assert len(mcp_calls) == 1
        assert mcp_calls[0]["id"] == "mcp_paired"
        assert mcp_calls[0]["output"] == "Microsoft Agent Framework"


# ---------------------------------------------------------------------------
# Tests — tool calling
# ---------------------------------------------------------------------------


class TestToolCalling:
    """Tests that verify function-tool round trips through the hosting layer."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_tool_call_non_streaming(self, history_server_with_tools: ResponsesHostServer) -> None:
        """Agent invokes a tool and returns a final answer (non-streaming)."""
        resp = await _post_json(
            history_server_with_tools,
            {
                "input": "What is the weather in Seattle?",
                "stream": False,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"

        # The output should contain the final text referencing the weather
        output_messages = [o for o in body["output"] if o["type"] == "message"]
        assert len(output_messages) == 1
        final_text = output_messages[0]["content"][0]["text"].lower()
        assert "72" in final_text or "sunny" in final_text or "seattle" in final_text

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_tool_call_streaming(self, history_server_with_tools: ResponsesHostServer) -> None:
        """Agent invokes a tool and returns a final answer (streaming)."""
        resp = await _post_json(
            history_server_with_tools,
            {
                "input": "What is the weather in Seattle?",
                "stream": True,
            },
        )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse_events(resp.text)
        types = _sse_event_types(events)

        assert types[0] == "response.created"
        assert types[-1] == "response.completed"

        # Should have text output with the weather info
        done_events = [e for e in events if e["event"] == "response.output_text.done"]
        assert len(done_events) >= 1
        final_text = done_events[-1]["data"]["text"].lower()
        assert "72" in final_text or "sunny" in final_text or "seattle" in final_text


# ---------------------------------------------------------------------------
# Tests — options passthrough
# ---------------------------------------------------------------------------


class TestOptions:
    """Verify chat options are passed through to the model."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_temperature_and_max_tokens(self, server: ResponsesHostServer) -> None:
        """Set max_output_tokens and verify the response succeeds."""
        resp = await _post_json(
            server,
            {
                "input": "Say hello briefly.",
                "stream": False,
                "max_output_tokens": 200,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert len(body["output"]) > 0


# ---------------------------------------------------------------------------
# Tests — real crash/recovery for resilient-background workflows
#
# A real ResponsesHostServer is force-killed mid-workflow, then a freshly
# started process pointed at the same on-disk state recovers and completes the same response.
# The workflow is deterministic and model-free so the test needs no credentials.
# ---------------------------------------------------------------------------


class _CountdownStartExecutor(Executor):
    """Extract the countdown target from the input text without calling a model."""

    def __init__(self, id: str = "start") -> None:
        super().__init__(id=id)

    @handler
    async def extract_target(self, messages: list[Message], ctx: WorkflowContext[int, str]) -> None:
        match = re.search(r"\d+", " ".join(m.text for m in messages))
        if not match:
            await ctx.yield_output("The message must contain a positive integer counter target.")
            return
        await ctx.send_message(int(match.group()))


class _CountdownExecutor(Executor):
    """Decrement the target through a self-loop, then signal completion."""

    def __init__(self, sleep_seconds: float, id: str = "countdown") -> None:
        super().__init__(id=id)
        self._sleep_seconds = sleep_seconds

    @handler
    async def countdown(self, target: int, ctx: WorkflowContext[int | str, str]) -> None:
        if target <= 0:
            await ctx.send_message("Countdown complete.", target_id="complete")
            return

        await asyncio.sleep(self._sleep_seconds)  # Simulate a long-running operation
        await ctx.yield_output(str(target))
        await ctx.send_message(target - 1, target_id=self.id)


class _PairedYieldExecutor(Executor):
    """Yield two separate, already-complete output items in a single superstep, then self-loop.

    Exercises the case the single-item-per-superstep countdown workflow can't: a superstep whose
    checkpoint only becomes visible after *both* items have been pulled from the stream, so the
    second item is still the tracker's dangling "active" item at the moment the checkpoint for
    this superstep is (or isn't yet) safe to pin and persist.
    """

    def __init__(self, sleep_seconds: float, id: str = "paired") -> None:
        super().__init__(id=id)
        self._sleep_seconds = sleep_seconds

    @handler
    async def step(self, target: int, ctx: WorkflowContext[int | str, str]) -> None:
        if target <= 0:
            await ctx.send_message("Countdown complete.", target_id="complete")
            return

        await asyncio.sleep(self._sleep_seconds)  # Simulate a long-running operation
        await ctx.yield_output(f"first-{target}")
        await ctx.yield_output(f"second-{target}")
        await ctx.send_message(target - 1, target_id=self.id)


class _ToolCallExecutor(Executor):
    """Emit a deterministic function-call/result pair, then a final message, without a real model.

    Exercises the function-call accumulation path in ``_OutputItemTracker`` (a distinct code path
    from plain text) under a real crash/recovery cycle: the result must not be re-invoked or
    duplicated after recovery.
    """

    def __init__(self, sleep_seconds: float, id: str = "tool_call") -> None:
        super().__init__(id=id)
        self._sleep_seconds = sleep_seconds

    @handler
    async def call_tool(self, target: int, ctx: WorkflowContext[str, Content | str]) -> None:
        call_id = f"call_{target}"
        await asyncio.sleep(self._sleep_seconds)  # Simulate a long-running operation
        await ctx.yield_output(
            Content.from_function_call(call_id, "get_number_fact", arguments=json.dumps({"number": target}))
        )
        await ctx.yield_output(Content.from_function_result(call_id, result=f"{target} is a deterministic number."))
        await ctx.yield_output(f"The number is {target}.")
        await ctx.send_message("Countdown complete.", target_id="complete")


@executor(id="complete")
async def _countdown_complete(message: str, ctx: WorkflowContext[Never, str]) -> None:  # zuban: ignore
    """Yield the workflow's completion output."""
    await ctx.yield_output(message)


def _build_countdown_workflow(sleep_seconds: float):
    """Build the target extraction, countdown, and completion workflow."""
    start = _CountdownStartExecutor()
    countdown = _CountdownExecutor(sleep_seconds)

    return (
        WorkflowBuilder(start_executor=start, output_from="all")
        .add_edge(start, countdown)
        .add_edge(countdown, countdown)
        .add_edge(countdown, _countdown_complete)
        .build()
    )


def _build_paired_yield_workflow(sleep_seconds: float):
    """Build a workflow whose self-looping executor yields two output items per superstep."""
    start = _CountdownStartExecutor()
    paired = _PairedYieldExecutor(sleep_seconds)

    return (
        WorkflowBuilder(start_executor=start, output_from="all")
        .add_edge(start, paired)
        .add_edge(paired, paired)
        .add_edge(paired, _countdown_complete)
        .build()
    )


def _build_tool_call_workflow(sleep_seconds: float):
    """Build a workflow that emits a function-call/result pair, then text, then a second superstep."""
    start = _CountdownStartExecutor()
    tool_call = _ToolCallExecutor(sleep_seconds)

    return (
        WorkflowBuilder(start_executor=start, output_from="all")
        .add_edge(start, tool_call)
        .add_edge(tool_call, _countdown_complete)
        .build()
    )


def _run_resilient_server(
    *,
    port: int,
    state_root: str,
    sleep_seconds: float,
    log_path: str,
    build_workflow: Callable[[float], Any],
) -> None:
    """Multiprocessing target: hosts the given workflow as a real, killable server process."""
    log_file = open(log_path, "a", buffering=1)  # noqa: SIM115
    os.dup2(log_file.fileno(), 1)
    os.dup2(log_file.fileno(), 2)
    os.environ["AGENTSERVER_STATE_ROOT"] = state_root

    workflow_agent = build_workflow(sleep_seconds).as_agent(name="resilient-workflow")
    server = ResponsesHostServer(workflow_agent, options=ResponsesServerOptions(resilient_background=True))
    server.run(host="127.0.0.1", port=port)


def _free_port() -> int:
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_resilient_server(
    *, port: int, state_root: Path, log_path: Path, build_workflow: Callable[[float], Any] = _build_countdown_workflow
) -> multiprocessing.process.BaseProcess:
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(
        target=_run_resilient_server,
        kwargs={
            "port": port,
            "state_root": str(state_root),
            "sleep_seconds": 0.05,
            "log_path": str(log_path),
            "build_workflow": build_workflow,
        },
    )
    proc.start()
    return proc


async def _wait_for_ready(base_url: str, *, timeout: float = 30.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                resp = await client.get(f"{base_url}/readiness", timeout=2.0)
                if resp.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.2)
    raise RuntimeError("Server did not become ready in time.")


def _kill(proc: multiprocessing.process.BaseProcess) -> None:
    # kill() sends SIGKILL on POSIX and calls TerminateProcess on Windows -- an ungraceful hard
    # kill, just like a real crash.
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=10)


def _clear_stale_stream_lock(state_root: Path, response_id: str) -> None:
    # On Windows, the local stream store falls back to a plain lock *file* (no fcntl), which isn't
    # cleaned up when the process is force-killed. Retry briefly since the killed process's file
    # handle may not be released immediately.
    lock_path = state_root / "streams" / f"{response_id}.jsonl.lock"
    if not lock_path.exists():
        return
    for attempt in range(10):
        try:
            lock_path.unlink()
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.5)


def _output_texts(output_items: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for item in output_items:
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                texts.append(part["text"])
    return texts


async def _run_until_nth_output_item_then_crash(
    *, base_url: str, server: multiprocessing.process.BaseProcess, input_text: str, crash_after_count: int
) -> str:
    """POST a real streaming background response, force-kill the server after ``crash_after_count``
    ``response.output_item.done`` events, and return the response id.
    """
    response_id: str | None = None
    count = 0
    async with (
        httpx.AsyncClient(timeout=30) as client,
        client.stream(
            "POST",
            f"{base_url}/responses",
            json={"input": input_text, "store": True, "background": True, "stream": True},
        ) as resp,
    ):
        assert resp.status_code == 200
        current_event: str | None = None
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                current_event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
                if current_event == "response.created" and response_id is None:
                    response_id = data["response"]["id"]
                elif current_event == "response.output_item.done":
                    count += 1
                    if count >= crash_after_count:
                        break
    assert response_id is not None
    assert count >= crash_after_count
    return response_id


async def _wait_for_recovery_completion(*, base_url: str, response_id: str) -> dict[str, Any]:
    """Replay the response's SSE stream to completion after a restart, then return the final body."""
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("GET", f"{base_url}/responses/{response_id}", params={"stream": "true"}) as resp:
            assert resp.status_code == 200
            current_event: str | None = None
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                elif line.startswith("data:") and current_event in (
                    "response.completed",
                    "response.failed",
                    "response.incomplete",
                ):
                    break

        final = await client.get(f"{base_url}/responses/{response_id}")
    return final.json()


async def _crash_and_recover(
    *,
    build_workflow: Callable[[float], Any],
    input_text: str,
    crash_after_count: int,
    tmp_path: Path,
) -> dict[str, Any]:
    """Force-kill a real server after ``crash_after_count`` output items, restart it against the
    same on-disk state, and return the recovered response's final body.
    """
    state_root = tmp_path / "state"
    log_path = tmp_path / "server.log"
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    server = _start_resilient_server(port=port, state_root=state_root, log_path=log_path, build_workflow=build_workflow)
    try:
        await _wait_for_ready(base_url)
        response_id = await _run_until_nth_output_item_then_crash(
            base_url=base_url, server=server, input_text=input_text, crash_after_count=crash_after_count
        )
    finally:
        _kill(server)

    _clear_stale_stream_lock(state_root, response_id)

    server = _start_resilient_server(port=port, state_root=state_root, log_path=log_path, build_workflow=build_workflow)
    try:
        await _wait_for_ready(base_url)
        body = await _wait_for_recovery_completion(base_url=base_url, response_id=response_id)
    finally:
        _kill(server)

    assert body["status"] == "completed", log_path.read_text(errors="replace")
    return body


@pytest.mark.xfail(
    reason=("Known gap: 1. 'RuntimeError: Server did not become ready in time.' consistenly in CI. 2. #7809"),
    strict=False,
)
class TestWorkflowResilientRecoveryRealCrash:
    """Force-kill a real ResponsesHostServer process mid-workflow and verify a freshly started
    process, pointed at the same on-disk state, recovers and completes the response with no
    lost or duplicated output.

    Crash points are parametrized across each workflow's item boundaries rather than a single
    fixed point, since the checkpoint pin/persist ordering being tested depends on exactly where,
    relative to a superstep boundary, the crash lands.
    """

    @pytest.mark.integration
    @pytest.mark.parametrize("crash_after_count", [1, 3, 6])
    async def test_countdown_workflow_crash_and_recover(self, tmp_path: Path, crash_after_count: int) -> None:
        """One output item per superstep: a baseline where the tracker's active item always
        auto-closes via a fresh message_id before the next checkpoint check runs.
        """
        target = 6
        expected_texts = [str(n) for n in range(target, 0, -1)] + ["Countdown complete."]

        body = await _crash_and_recover(
            build_workflow=_build_countdown_workflow,
            input_text=f"Count down from {target}",
            crash_after_count=crash_after_count,
            tmp_path=tmp_path,
        )
        assert _output_texts(body["output"]) == expected_texts

    @pytest.mark.integration
    @pytest.mark.parametrize("crash_after_count", [1, 2, 6])
    async def test_paired_yield_workflow_crash_and_recover(self, tmp_path: Path, crash_after_count: int) -> None:
        """Two output items per superstep: the second item is still the tracker's dangling
        "active" item at the exact moment the checkpoint for that superstep would be pinned and
        persisted.
        """
        target = 6
        expected_texts = [text for n in range(target, 0, -1) for text in (f"first-{n}", f"second-{n}")] + [
            "Countdown complete."
        ]

        body = await _crash_and_recover(
            build_workflow=_build_paired_yield_workflow,
            input_text=f"Count down from {target}",
            crash_after_count=crash_after_count,
            tmp_path=tmp_path,
        )
        assert _output_texts(body["output"]) == expected_texts

    @pytest.mark.integration
    @pytest.mark.parametrize("crash_after_count", [1, 3])
    async def test_tool_call_workflow_crash_and_recover(self, tmp_path: Path, crash_after_count: int) -> None:
        """Function-call/result accumulation is a distinct ``_OutputItemTracker`` code path from
        plain text. Crashing right at the boundary into the next superstep (after the call/result/
        text superstep completes) must resume without re-emitting the call.
        """
        body = await _crash_and_recover(
            build_workflow=_build_tool_call_workflow,
            input_text="Look up a fact about 7",
            crash_after_count=crash_after_count,
            tmp_path=tmp_path,
        )
        function_calls = [item for item in body["output"] if item.get("type") == "function_call"]
        function_call_outputs = [item for item in body["output"] if item.get("type") == "function_call_output"]
        assert len(function_calls) == 1
        assert function_calls[0]["call_id"] == "call_7"
        assert len(function_call_outputs) == 1
        assert function_call_outputs[0]["call_id"] == "call_7"
        assert _output_texts(body["output"]) == ["The number is 7.", "Countdown complete."]
