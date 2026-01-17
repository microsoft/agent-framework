# Copyright (c) Microsoft. All rights reserved.

import json
import os
from typing import Annotated

import pytest
from pydantic import BaseModel

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    ChatAgent,
    HostedCodeInterpreterTool,
    HostedImageGenerationTool,
    HostedMCPTool,
    MCPStreamableHTTPTool,
    ai_function,
)
from agent_framework.openai import OpenAIResponsesClient

skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


@ai_function
async def get_weather(location: Annotated[str, "The location as a city name"]) -> str:
    """Get the current weather in a given location."""
    # Implementation of the tool to get weather
    return f"The current weather in {location} is sunny."


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_basic_run_streaming():
    """Test OpenAI Responses Client agent basic streaming functionality with OpenAIResponsesClient."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
    ) as agent:
        # Test streaming run
        full_text = ""
        async for chunk in agent.run_stream("Please respond with exactly: 'This is a streaming response test.'"):
            assert isinstance(chunk, AgentResponseUpdate)
            if chunk.text:
                full_text += chunk.text

        assert len(full_text) > 0
        assert "streaming response test" in full_text.lower()


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_thread_persistence():
    """Test OpenAI Responses Client agent thread persistence across runs with OpenAIResponsesClient."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant with good memory.",
    ) as agent:
        # Create a new thread that will be reused
        thread = agent.get_new_thread()

        # First interaction
        first_response = await agent.run("My favorite programming language is Python. Remember this.", thread=thread)

        assert isinstance(first_response, AgentResponse)
        assert first_response.text is not None

        # Second interaction - test memory
        second_response = await agent.run("What is my favorite programming language?", thread=thread)

        assert isinstance(second_response, AgentResponse)
        assert second_response.text is not None


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_thread_storage_with_store_true():
    """Test OpenAI Responses Client agent with store=True to verify service_thread_id is returned."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant.",
    ) as agent:
        # Create a new thread
        thread = AgentThread()

        # Initially, service_thread_id should be None
        assert thread.service_thread_id is None

        # Run with store=True to store messages on OpenAI side
        response = await agent.run(
            "Hello! Please remember that my name is Alex.",
            thread=thread,
            options={"store": True},
        )

        # Validate response
        assert isinstance(response, AgentResponse)
        assert response.text is not None
        assert len(response.text) > 0

        # After store=True, service_thread_id should be populated
        assert thread.service_thread_id is not None
        assert isinstance(thread.service_thread_id, str)
        assert len(thread.service_thread_id) > 0


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_existing_thread():
    """Test OpenAI Responses Client agent with existing thread to continue conversations across agent instances."""
    # First conversation - capture the thread
    preserved_thread = None

    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant with good memory.",
    ) as first_agent:
        # Start a conversation and capture the thread
        thread = first_agent.get_new_thread()
        first_response = await first_agent.run("My hobby is photography. Remember this.", thread=thread)

        assert isinstance(first_response, AgentResponse)
        assert first_response.text is not None

        # Preserve the thread for reuse
        preserved_thread = thread

    # Second conversation - reuse the thread in a new agent instance
    if preserved_thread:
        async with ChatAgent(
            chat_client=OpenAIResponsesClient(),
            instructions="You are a helpful assistant with good memory.",
        ) as second_agent:
            # Reuse the preserved thread
            second_response = await second_agent.run("What is my hobby?", thread=preserved_thread)

            assert isinstance(second_response, AgentResponse)
            assert second_response.text is not None
            assert "photography" in second_response.text.lower()


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_hosted_code_interpreter_tool():
    """Test OpenAI Responses Client agent with HostedCodeInterpreterTool through OpenAIResponsesClient."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that can execute Python code.",
        tools=[HostedCodeInterpreterTool()],
    ) as agent:
        # Test code interpreter functionality
        response = await agent.run("Calculate the sum of numbers from 1 to 10 using Python code.")

        assert isinstance(response, AgentResponse)
        assert response.text is not None
        assert len(response.text) > 0
        # Should contain calculation result (sum of 1-10 = 55) or code execution content
        contains_relevant_content = any(
            term in response.text.lower() for term in ["55", "sum", "code", "python", "calculate", "10"]
        )
        assert contains_relevant_content or len(response.text.strip()) > 10


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_image_generation_tool():
    """Test OpenAI Responses Client agent with raw image_generation tool through OpenAIResponsesClient."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that can generate images.",
        tools=HostedImageGenerationTool(options={"image_size": "1024x1024", "media_type": "png"}),
    ) as agent:
        # Test image generation functionality
        response = await agent.run("Generate an image of a cute red panda sitting on a tree branch in a forest.")

        assert isinstance(response, AgentResponse)
        assert response.messages

        # Verify we got image content - look for ImageGenerationToolResultContent
        image_content_found = False
        for message in response.messages:
            for content in message.contents:
                if content.type == "image_generation_tool_result" and content.outputs:
                    image_content_found = True
                    break
            if image_content_found:
                break

        # The test passes if we got image content
        assert image_content_found, "Expected to find image content in response"


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_level_tool_persistence():
    """Test that agent-level tools persist across multiple runs with OpenAI Responses Client."""

    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that uses available tools.",
        tools=[get_weather],  # Agent-level tool
    ) as agent:
        # First run - agent-level tool should be available
        first_response = await agent.run("What's the weather like in Chicago?")

        assert isinstance(first_response, AgentResponse)
        assert first_response.text is not None
        # Should use the agent-level weather tool
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "72"])

        # Second run - agent-level tool should still be available (persistence test)
        second_response = await agent.run("What's the weather in Miami?")

        assert isinstance(second_response, AgentResponse)
        assert second_response.text is not None
        # Should use the agent-level weather tool again
        assert any(term in second_response.text.lower() for term in ["miami", "sunny", "72"])


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_run_level_tool_isolation():
    """Test that run-level tools are isolated to specific runs and don't persist with OpenAI Responses Client."""
    # Counter to track how many times the weather tool is called
    call_count = 0

    @ai_function
    async def get_weather_with_counter(
        location: Annotated[str, "The location as a city name"],
    ) -> str:
        """Get the current weather in a given location."""
        nonlocal call_count
        call_count += 1
        return f"The weather in {location} is sunny and 72°F."

    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant.",
    ) as agent:
        # First run - use run-level tool
        first_response = await agent.run(
            "What's the weather like in Chicago?",
            tools=[get_weather_with_counter],  # Run-level tool
        )

        assert isinstance(first_response, AgentResponse)
        assert first_response.text is not None
        # Should use the run-level weather tool (call count should be 1)
        assert call_count == 1
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "72"])

        # Second run - run-level tool should NOT persist (key isolation test)
        second_response = await agent.run("What's the weather like in Miami?")

        assert isinstance(second_response, AgentResponse)
        assert second_response.text is not None
        # Should NOT use the weather tool since it was only run-level in previous call
        # Call count should still be 1 (no additional calls)
        assert call_count == 1


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_chat_options_agent_level() -> None:
    """Integration test for comprehensive ChatOptions parameter coverage with OpenAI Response Agent."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant.",
        tools=[get_weather],
        default_options={
            "max_tokens": 100,
            "temperature": 0.7,
            "top_p": 0.9,
            "seed": 123,
            "user": "comprehensive-test-user",
            "tool_choice": "auto",
        },
    ) as agent:
        response = await agent.run(
            "Provide a brief, helpful response.",
        )

        assert isinstance(response, AgentResponse)
        assert response.text is not None
        assert len(response.text) > 0


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_hosted_mcp_tool() -> None:
    """Integration test for HostedMCPTool with OpenAI Response Agent using Microsoft Learn MCP."""

    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=HostedMCPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
            description="A Microsoft Learn MCP server for documentation questions",
            approval_mode="never_require",
        ),
    ) as agent:
        response = await agent.run(
            "How to create an Azure storage account using az cli?",
            # this needs to be high enough to handle the full MCP tool response.
            options={"max_tokens": 5000},
        )

        assert isinstance(response, AgentResponse)
        assert response.text
        # Should contain Azure-related content since it's asking about Azure CLI
        assert any(term in response.text.lower() for term in ["azure", "storage", "account", "cli"])


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_local_mcp_tool() -> None:
    """Integration test for MCPStreamableHTTPTool with OpenAI Response Agent using Microsoft Learn MCP."""

    mcp_tool = MCPStreamableHTTPTool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
    )

    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=[mcp_tool],
    ) as agent:
        response = await agent.run(
            "How to create an Azure storage account using az cli?",
            options={"max_tokens": 200},
        )

        assert isinstance(response, AgentResponse)
        assert response.text is not None
        assert len(response.text) > 0
        # Should contain Azure-related content since it's asking about Azure CLI
        assert any(term in response.text.lower() for term in ["azure", "storage", "account", "cli"])


class ReleaseBrief(BaseModel):
    """Structured output model for release brief testing."""

    title: str
    summary: str
    highlights: list[str]
    model_config = {"extra": "forbid"}


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_with_response_format_pydantic() -> None:
    """Integration test for response_format with Pydantic model using OpenAI Responses Client."""
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="You are a helpful assistant that returns structured JSON responses.",
    ) as agent:
        response = await agent.run(
            "Summarize the following release notes into a ReleaseBrief:\n\n"
            "Version 2.0 Release Notes:\n"
            "- Added new streaming API for real-time responses\n"
            "- Improved error handling with detailed messages\n"
            "- Performance boost of 50% in batch processing\n"
            "- Fixed memory leak in connection pooling",
            options={
                "response_format": ReleaseBrief,
            },
        )

        # Validate response
        assert isinstance(response, AgentResponse)
        assert response.value is not None
        assert isinstance(response.value, ReleaseBrief)

        # Validate structured output fields
        brief = response.value
        assert len(brief.title) > 0
        assert len(brief.summary) > 0
        assert len(brief.highlights) > 0


@pytest.mark.flaky
@skip_if_openai_integration_tests_disabled
async def test_openai_responses_client_agent_with_runtime_json_schema() -> None:
    """Integration test for response_format with runtime JSON schema using OpenAI Responses Client."""
    runtime_schema = {
        "title": "WeatherDigest",
        "type": "object",
        "properties": {
            "location": {"type": "string"},
            "conditions": {"type": "string"},
            "temperature_c": {"type": "number"},
            "advisory": {"type": "string"},
        },
        "required": ["location", "conditions", "temperature_c", "advisory"],
        "additionalProperties": False,
    }

    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        instructions="Return only JSON that matches the provided schema. Do not add commentary.",
    ) as agent:
        response = await agent.run(
            "Give a brief weather digest for Seattle.",
            options={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": runtime_schema["title"],
                        "strict": True,
                        "schema": runtime_schema,
                    },
                },
            },
        )

        # Validate response
        assert isinstance(response, AgentResponse)
        assert response.text is not None

        # Parse JSON and validate structure
        parsed = json.loads(response.text)
        assert "location" in parsed
        assert "conditions" in parsed
        assert "temperature_c" in parsed
        assert "advisory" in parsed
