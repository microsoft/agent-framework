# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os

import pytest
from agent_framework import Content, FunctionTool, Message
from pydantic import BaseModel

from agent_framework_gemini import GeminiChatClient, GeminiChatOptions, ThinkingConfig

skip_if_no_api_key = pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set; skipping integration tests.",
)

_MODEL = "gemini-2.5-flash"


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_basic_chat() -> None:
    """Basic request/response round-trip returns a non-empty text reply."""
    client = GeminiChatClient(model_id=_MODEL)
    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Reply with the single word: hello")])]
    )

    assert response.messages
    assert response.messages[0].text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_streaming() -> None:
    """Streaming yields multiple chunks that together form a non-empty response."""
    client = GeminiChatClient(model_id=_MODEL)
    stream = client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("Count from 1 to 5.")])],
        stream=True,
    )

    chunks = [update async for update in stream]
    assert len(chunks) > 0
    full_text = "".join(u.text or "" for u in chunks)
    assert full_text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_tool_calling() -> None:
    """Model invokes the registered tool when asked a question that requires it."""

    def get_temperature(city: str) -> str:
        """Return the current temperature for a city."""
        return f"22°C in {city}"

    tool = FunctionTool(name="get_temperature", func=get_temperature)
    client = GeminiChatClient(model_id=_MODEL)

    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("What is the temperature in Berlin?")])],
        options={"tools": [tool], "tool_choice": "required"},
    )

    function_calls = [c for c in response.messages[0].contents if c.type == "function_call"]
    assert len(function_calls) >= 1
    assert function_calls[0].name == "get_temperature"


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_thinking_config() -> None:
    """Model accepts a thinking budget and returns a non-empty text reply."""
    options: GeminiChatOptions = {"thinking_config": ThinkingConfig(thinking_budget=512)}
    client = GeminiChatClient(model_id=_MODEL)

    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("What is 17 * 34?")])],
        options=options,
    )

    assert response.messages
    assert response.messages[0].text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_google_search_grounding() -> None:
    """Google Search grounding returns a non-empty response for a current-events question."""
    options: GeminiChatOptions = {"google_search_grounding": True}
    client = GeminiChatClient(model_id=_MODEL)

    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("What is the latest stable version of Python?")])],
        options=options,
    )

    assert response.messages
    assert response.messages[0].text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_code_execution() -> None:
    """Code execution tool produces a non-empty response for a computation request."""
    options: GeminiChatOptions = {"code_execution": True}
    client = GeminiChatClient(model_id=_MODEL)

    response = await client.get_response(
        messages=[
            Message(
                role="user",
                contents=[Content.from_text("Compute the sum of the first 100 natural numbers using code.")],
            )
        ],
        options=options,
    )

    assert response.messages
    assert response.messages[0].text


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_structured_output() -> None:
    """Structured output with a Pydantic response_format returns a parsed value via response.value."""

    class Answer(BaseModel):
        answer: str

    client = GeminiChatClient(model_id=_MODEL)

    response = await client.get_response(
        messages=[Message(role="user", contents=[Content.from_text("What is the capital of Germany?")])],
        options={"response_format": Answer},
    )

    assert response.value is not None
    assert isinstance(response.value, Answer)
    assert response.value.answer


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_no_api_key
async def test_integration_google_maps_grounding() -> None:
    """Google Maps grounding returns a non-empty response for a location-based question."""
    options: GeminiChatOptions = {"google_maps_grounding": True}
    client = GeminiChatClient(model_id=_MODEL)

    response = await client.get_response(
        messages=[
            Message(
                role="user",
                contents=[Content.from_text("What are some highly rated restaurants in Karlsruhe city center?")],
            )
        ],
        options=options,
    )

    assert response.messages
    assert response.messages[0].text
