# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for ResponsesHostServer with a real Foundry endpoint.

These tests exercise the full HTTP pipeline using httpx.AsyncClient with
ASGITransport — no real server process is started. The agent talks to a real
Foundry project endpoint so every test requires valid credentials.

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT - The Azure AI Foundry project endpoint URL.
    FOUNDRY_MODEL            - The model deployment name (e.g. gpt-4o).
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Annotated, Any

import httpx
import pytest
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.ai.agentserver.responses import InMemoryResponseProvider
from azure.identity import AzureCliCredential

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
    client = FoundryChatClient(credential=AzureCliCredential())

    agent = Agent(
        client=client,
        instructions="You are a concise assistant. Keep answers very short (one or two sentences).",
        default_options={"store": False},
    )

    return ResponsesHostServer(agent, store=InMemoryResponseProvider())


@tool
async def get_weather(location: Annotated[str, "The city name"]) -> str:
    """Get the current weather in a given location."""
    return f"The weather in {location} is 72°F and sunny."


@pytest.fixture
def server_with_tools() -> ResponsesHostServer:
    """Create a ResponsesHostServer whose agent has a tool."""
    client = FoundryChatClient(credential=AzureCliCredential())

    agent = Agent(
        client=client,
        instructions="You are a concise assistant. Use the provided tools when appropriate. Keep answers very short.",
        tools=[get_weather],
        default_options={"store": False},
    )

    return ResponsesHostServer(agent, store=InMemoryResponseProvider())


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
    async def test_two_turn_conversation(self, server: ResponsesHostServer) -> None:
        """Turn 1: introduce context. Turn 2: ask about it using previous_response_id."""
        # Turn 1
        resp1 = await _post_json(
            server,
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
            server,
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
    async def test_three_turn_conversation(self, server: ResponsesHostServer) -> None:
        """Three sequential turns to verify history accumulates correctly."""
        # Turn 1
        resp1 = await _post_json(
            server,
            {
                "input": "I have a pet dog named Max.",
                "stream": False,
            },
        )
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        # Turn 2
        resp2 = await _post_json(
            server,
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
            server,
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
    async def test_multi_turn_streaming(self, server: ResponsesHostServer) -> None:
        """Multi-turn conversation with streaming on the second turn."""
        # Turn 1 — non-streaming
        resp1 = await _post_json(
            server,
            {
                "input": "My favorite number is 42.",
                "stream": False,
            },
        )
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        # Turn 2 — streaming
        resp2 = await _post_json(
            server,
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


# ---------------------------------------------------------------------------
# Tests — tool calling
# ---------------------------------------------------------------------------


class TestToolCalling:
    """Tests that verify function-tool round trips through the hosting layer."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_tool_call_non_streaming(self, server_with_tools: ResponsesHostServer) -> None:
        """Agent invokes a tool and returns a final answer (non-streaming)."""
        resp = await _post_json(
            server_with_tools,
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
    async def test_tool_call_streaming(self, server_with_tools: ResponsesHostServer) -> None:
        """Agent invokes a tool and returns a final answer (streaming)."""
        resp = await _post_json(
            server_with_tools,
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
        """Set temperature and max_output_tokens and verify the response succeeds."""
        resp = await _post_json(
            server,
            {
                "input": "Say hello briefly.",
                "stream": False,
                "max_output_tokens": 50,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        output_messages = [o for o in body["output"] if o["type"] == "message"]
        assert len(output_messages) == 1
        output_text = output_messages[0]["content"][0]["text"]
        assert len(output_text) > 0
