# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for InvocationsHostServer with a real Foundry endpoint.

These tests exercise the full HTTP pipeline using httpx.AsyncClient with
ASGITransport — no real server process is started. The agent talks to a real
Foundry project endpoint so every test requires valid credentials.

The invocations protocol is intentionally simple: a request is a JSON body with
a ``message`` field (and an optional ``stream`` flag). Non-streaming responses
return the agent's answer as plain text; streaming responses return the answer
as a ``text/event-stream`` of text chunks. Session continuity is keyed off the
``agent_session_id`` query parameter.

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT - The Azure AI Foundry project endpoint URL.
    FOUNDRY_MODEL            - The model deployment name (e.g. gpt-4o).
"""

from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
import pytest
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

from agent_framework_foundry_hosting import InvocationsHostServer

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
def server() -> InvocationsHostServer:
    """Create an InvocationsHostServer backed by a real Foundry agent."""
    client = FoundryChatClient(credential=AzureCliCredential())  # pyrefly: ignore[bad-argument-type]

    agent = Agent(
        client=client,  # ty: ignore[invalid-argument-type]
        instructions="You are a concise assistant. Keep answers very short (one or two sentences).",
        default_options={"store": False},  # pyrefly: ignore[bad-argument-type]
    )

    return InvocationsHostServer(agent)


@tool
async def get_weather(location: Annotated[str, "The city name"]) -> str:
    """Get the current weather in a given location."""
    return f"The weather in {location} is 72°F and sunny."


@pytest.fixture
def server_with_tools() -> InvocationsHostServer:
    """Create an InvocationsHostServer whose agent has a tool."""
    client = FoundryChatClient(credential=AzureCliCredential())  # pyrefly: ignore[bad-argument-type]

    agent = Agent(
        client=client,  # ty: ignore[invalid-argument-type]
        instructions="You are a concise assistant. Use the provided tools when appropriate. Keep answers very short.",
        tools=[get_weather],
        default_options={"store": False},  # pyrefly: ignore[bad-argument-type]
    )

    return InvocationsHostServer(agent)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


async def _post_invocation(
    server: InvocationsHostServer,
    *,
    message: str,
    stream: bool = False,
    session_id: str | None = None,
) -> httpx.Response:
    """Send a POST /invocations request with the given message.

    When ``session_id`` is provided it is forwarded as the ``agent_session_id``
    query parameter so the server reuses the same conversation session.
    """
    payload: dict[str, Any] = {"message": message, "stream": stream}
    params = {"agent_session_id": session_id} if session_id is not None else None
    transport = httpx.ASGITransport(app=server)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/invocations", json=payload, params=params, timeout=120)


# ---------------------------------------------------------------------------
# Tests — basic text input
# ---------------------------------------------------------------------------


class TestBasicText:
    """Simple text-in / text-out round trips."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_simple_text_non_streaming(self, server: InvocationsHostServer) -> None:
        """Non-streaming: send a message and get the agent's text answer."""
        resp = await _post_invocation(server, message="Say hello in exactly three words.", stream=False)

        assert resp.status_code == 200
        assert len(resp.text) > 0

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_simple_text_streaming(self, server: InvocationsHostServer) -> None:
        """Streaming: send a message and receive text chunks as an event stream."""
        resp = await _post_invocation(server, message="Say hello in exactly three words.", stream=True)

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert len(resp.text) > 0

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_missing_message_returns_400(self, server: InvocationsHostServer) -> None:
        """A request without a ``message`` field is rejected with a 400."""
        transport = httpx.ASGITransport(app=server)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/invocations", json={"stream": False}, timeout=120)

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests — multi-turn conversations
# ---------------------------------------------------------------------------


class TestMultiTurn:
    """Multi-round conversations using a shared agent_session_id."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_two_turn_conversation(self, server: InvocationsHostServer) -> None:
        """Turn 1 establishes context; turn 2 recalls it via the same session."""
        session_id = "int-test-session-two-turn"

        resp1 = await _post_invocation(
            server,
            message="My favorite color is blue. Remember that.",
            stream=False,
            session_id=session_id,
        )
        assert resp1.status_code == 200

        resp2 = await _post_invocation(
            server,
            message="What is my favorite color? Answer with a single word.",
            stream=False,
            session_id=session_id,
        )
        assert resp2.status_code == 200
        assert "blue" in resp2.text.lower()

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_multi_turn_streaming(self, server: InvocationsHostServer) -> None:
        """Multi-turn conversation with streaming on the second turn."""
        session_id = "int-test-session-stream"

        resp1 = await _post_invocation(
            server,
            message="My favorite number is 42.",
            stream=False,
            session_id=session_id,
        )
        assert resp1.status_code == 200

        resp2 = await _post_invocation(
            server,
            message="What is my favorite number?",
            stream=True,
            session_id=session_id,
        )
        assert resp2.status_code == 200
        assert "text/event-stream" in resp2.headers["content-type"]
        assert "42" in resp2.text


# ---------------------------------------------------------------------------
# Tests — tool calling
# ---------------------------------------------------------------------------


class TestToolCalling:
    """Tests that verify function-tool round trips through the hosting layer."""

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_tool_call_non_streaming(self, server_with_tools: InvocationsHostServer) -> None:
        """Agent invokes a tool and returns a final answer (non-streaming)."""
        resp = await _post_invocation(
            server_with_tools,
            message="What is the weather in Seattle?",
            stream=False,
        )

        assert resp.status_code == 200
        assert "72" in resp.text

    @pytest.mark.flaky
    @pytest.mark.integration
    @skip_if_foundry_hosting_integration_tests_disabled
    async def test_tool_call_streaming(self, server_with_tools: InvocationsHostServer) -> None:
        """Agent invokes a tool and streams a final answer."""
        resp = await _post_invocation(
            server_with_tools,
            message="What is the weather in Seattle?",
            stream=True,
        )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "72" in resp.text
