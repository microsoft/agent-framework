# Copyright (c) Microsoft. All rights reserved.

import datetime
import os
from typing import Annotated

import pytest
from pydantic import BaseModel

from agent_framework import ChatClient, ChatMessage, ChatResponse, ai_function
from agent_framework.openai import OpenAIResponsesClient

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


class OutputStruct(BaseModel):
    """A structured output for testing purposes."""

    location: str
    weather: str


@ai_function
async def get_weather(location: Annotated[str, "The location as a city name"]) -> str:
    """Get the current weather in a given location."""
    # Implementation of the tool to get weather
    return f"The current weather in {location} is sunny."


async def test_openai_responses_client_response() -> None:
    """Test OpenAI chat completion responses."""
    openai_responses_client = OpenAIResponsesClient(ai_model_id="gpt-4.1-mini")

    assert isinstance(openai_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="The weather in New York is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    start = datetime.datetime.now()
    print("Starting test at:", start)  # noqa
    # Test that the client can be used to get a response
    response = await openai_responses_client.get_response(
        background=True,
        store=True,
        messages=messages,
        response_format=OutputStruct,
    )
    response_time = datetime.datetime.now()
    print("Response received at:", response_time)  # noqa

    assert response is not None
    assert isinstance(response, ChatResponse)
    final_response = await openai_responses_client.get_response(
        messages="",  # messages are meaningless here.. do something about that
        long_running_message_id=response.response_id,
        # Uncomment this lines if you want to poll
        # background=True,
        response_format=OutputStruct,
    )
    print(final_response)
    end = datetime.datetime.now()
    print("response received at: ", end)  # noqa
    print("Time taken for processing:", end - response_time)  # noqa
    output = OutputStruct.model_validate_json(final_response.messages[0].text)
    assert "New York" in output.location
    assert "sunny" in output.weather
