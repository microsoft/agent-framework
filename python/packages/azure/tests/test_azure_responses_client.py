# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Annotated

import pytest
from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    ChatClient,
    ChatClientAgent,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    HostedCodeInterpreterTool,
    TextContent,
    ai_function,
)
from agent_framework.azure import AzureResponsesClient
from agent_framework.exceptions import ServiceInitializationError
from azure.identity import AzureCliCredential
from pydantic import BaseModel

skip_if_azure_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("AZURE_OPENAI_ENDPOINT", "") in ("", "https://test-endpoint.com"),
    reason="No real AZURE_OPENAI_ENDPOINT provided; skipping integration tests."
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
    return f"The weather in {location} is sunny and 72°F."


def test_init(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    azure_responses_client = AzureResponsesClient()

    assert azure_responses_client.ai_model_id == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(azure_responses_client, ChatClient)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        AzureResponsesClient(api_key="34523", deployment_name={"test": "dict"})  # type: ignore


def test_init_ai_model_id_constructor(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    ai_model_id = "test_model_id"
    azure_responses_client = AzureResponsesClient(deployment_name=ai_model_id)

    assert azure_responses_client.ai_model_id == ai_model_id
    assert isinstance(azure_responses_client, ChatClient)


def test_init_with_default_header(azure_openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    azure_responses_client = AzureResponsesClient(
        default_headers=default_headers,
    )

    assert azure_responses_client.ai_model_id == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(azure_responses_client, ChatClient)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in azure_responses_client.client.default_headers
        assert azure_responses_client.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]], indirect=True)
def test_init_with_empty_model_id(azure_openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        AzureResponsesClient(
            env_file_path="test.env",
        )


def test_serialize(azure_openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "ai_model_id": azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        "api_key": azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    azure_responses_client = AzureResponsesClient.from_dict(settings)
    dumped_settings = azure_responses_client.to_dict()
    assert dumped_settings["ai_model_id"] == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert dumped_settings["api_key"] == azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"]
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_response() -> None:
    """Test azure responses client responses."""
    azure_responses_client = AzureResponsesClient(credential=AzureCliCredential())

    assert isinstance(azure_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(
        ChatMessage(
            role="user",
            text="Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
            "Bonded by their love for the natural world and shared curiosity, they uncovered a "
            "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
            "of climate change.",
        )
    )
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = await azure_responses_client.get_response(messages=messages)

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "scientists" in response.text

    messages.clear()
    messages.append(ChatMessage(role="user", text="The weather in New York is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a structured response
    structured_response = await azure_responses_client.get_response(  # type: ignore[reportAssignmentType]
        messages=messages,
        response_format=OutputStruct,
    )

    assert structured_response is not None
    assert isinstance(structured_response, ChatResponse)
    assert isinstance(structured_response.value, OutputStruct)
    assert structured_response.value.location == "New York"
    assert "sunny" in structured_response.value.weather.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_response_tools() -> None:
    """Test azure responses client tools."""
    azure_responses_client = AzureResponsesClient(credential=AzureCliCredential())

    assert isinstance(azure_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(ChatMessage(role="user", text="What is the weather in New York?"))

    # Test that the client can be used to get a response
    response = await azure_responses_client.get_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
    )

    assert response is not None
    assert isinstance(response, ChatResponse)
    assert "sunny" in response.text

    messages.clear()
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    # Test that the client can be used to get a response
    structured_response: ChatResponse = await azure_responses_client.get_response(  # type: ignore[reportAssignmentType]
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
        response_format=OutputStruct,
    )

    assert structured_response is not None
    assert isinstance(structured_response, ChatResponse)
    assert isinstance(structured_response.value, OutputStruct)
    assert "Seattle" in structured_response.value.location
    assert "sunny" in structured_response.value.weather.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_streaming() -> None:
    """Test Azure azure responses client streaming responses."""
    azure_responses_client = AzureResponsesClient(credential=AzureCliCredential())

    assert isinstance(azure_responses_client, ChatClient)

    messages: list[ChatMessage] = []
    messages.append(
        ChatMessage(
            role="user",
            text="Emily and David, two passionate scientists, met during a research expedition to Antarctica. "
            "Bonded by their love for the natural world and shared curiosity, they uncovered a "
            "groundbreaking phenomenon in glaciology that could potentially reshape our understanding "
            "of climate change.",
        )
    )
    messages.append(ChatMessage(role="user", text="who are Emily and David?"))

    # Test that the client can be used to get a response
    response = azure_responses_client.get_streaming_response(messages=messages)

    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    assert "scientists" in full_message

    messages.clear()
    messages.append(ChatMessage(role="user", text="The weather in Seattle is sunny"))
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    structured_response = await ChatResponse.from_chat_response_generator(
        azure_responses_client.get_streaming_response(
            messages=messages,
            response_format=OutputStruct,
        ),
        output_format_type=OutputStruct,
    )
    assert structured_response is not None
    assert isinstance(structured_response, ChatResponse)
    assert isinstance(structured_response.value, OutputStruct)
    assert "Seattle" in structured_response.value.location
    assert "sunny" in structured_response.value.weather.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_streaming_tools() -> None:
    """Test azure responses client streaming tools."""
    azure_responses_client = AzureResponsesClient(credential=AzureCliCredential())

    assert isinstance(azure_responses_client, ChatClient)

    messages: list[ChatMessage] = [ChatMessage(role="user", text="What is the weather in Seattle?")]

    # Test that the client can be used to get a response
    response = azure_responses_client.get_streaming_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
    )
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    assert "sunny" in full_message

    messages.clear()
    messages.append(ChatMessage(role="user", text="What is the weather in Seattle?"))

    structured_response = azure_responses_client.get_streaming_response(
        messages=messages,
        tools=[get_weather],
        tool_choice="auto",
        response_format=OutputStruct,
    )
    full_message = ""
    async for chunk in structured_response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    output = OutputStruct.model_validate_json(full_message)
    assert "Seattle" in output.location
    assert "sunny" in output.weather.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_basic_run():
    """Test Azure Responses Client agent basic run functionality with AzureResponsesClient."""
    agent = AzureResponsesClient(credential=AzureCliCredential()).create_agent(
        instructions="You are a helpful assistant.",
    )

    # Test basic run
    response = await agent.run("Hello! Please respond with 'Hello World' exactly.")

    assert isinstance(response, AgentRunResponse)
    assert response.text is not None
    assert len(response.text) > 0
    assert "hello world" in response.text.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_basic_run_streaming():
    """Test Azure Responses Client agent basic streaming functionality with AzureResponsesClient."""
    async with ChatClientAgent(
        chat_client=AzureResponsesClient(credential=AzureCliCredential()),
    ) as agent:
        # Test streaming run
        full_text = ""
        async for chunk in agent.run_streaming("Please respond with exactly: 'This is a streaming response test.'"):
            assert isinstance(chunk, AgentRunResponseUpdate)
            if chunk.text:
                full_text += chunk.text

        assert len(full_text) > 0
        assert "streaming response test" in full_text.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_thread_persistence():
    """Test Azure Responses Client agent thread persistence across runs with AzureResponsesClient."""
    async with ChatClientAgent(
        chat_client=AzureResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant with good memory.",
    ) as agent:
        # Create a new thread that will be reused
        thread = agent.get_new_thread()

        # First interaction
        first_response = await agent.run("My favorite programming language is Python. Remember this.", thread=thread)

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None

        # Second interaction - test memory
        second_response = await agent.run("What is my favorite programming language?", thread=thread)

        assert isinstance(second_response, AgentRunResponse)
        assert second_response.text is not None


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_thread_storage_with_store_true():
    """Test Azure Responses Client agent with store=True to verify service_thread_id is returned."""
    async with ChatClientAgent(
        chat_client=AzureResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
    ) as agent:
        # Create a new thread
        thread = AgentThread()

        # Initially, service_thread_id should be None
        assert thread.service_thread_id is None

        # Run with store=True to store messages on Azure/OpenAI side
        response = await agent.run(
            "Hello! Please remember that my name is Alex.",
            thread=thread,
            store=True,
        )

        # Validate response
        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0

        # After store=True, service_thread_id should be populated
        assert thread.service_thread_id is not None
        assert isinstance(thread.service_thread_id, str)
        assert len(thread.service_thread_id) > 0


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_existing_thread():
    """Test Azure Responses Client agent with existing thread to continue conversations across agent instances."""
    # First conversation - capture the thread
    preserved_thread = None

    async with ChatClientAgent(
        chat_client=AzureResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant with good memory.",
    ) as first_agent:
        # Start a conversation and capture the thread
        thread = first_agent.get_new_thread()
        first_response = await first_agent.run("My hobby is photography. Remember this.", thread=thread)

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None

        # Preserve the thread for reuse
        preserved_thread = thread

    # Second conversation - reuse the thread in a new agent instance
    if preserved_thread:
        async with ChatClientAgent(
            chat_client=AzureResponsesClient(credential=AzureCliCredential()),
            instructions="You are a helpful assistant with good memory.",
        ) as second_agent:
            # Reuse the preserved thread
            second_response = await second_agent.run("What is my hobby?", thread=preserved_thread)

            assert isinstance(second_response, AgentRunResponse)
            assert second_response.text is not None
            assert "photography" in second_response.text.lower()


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_hosted_code_interpreter_tool():
    """Test Azure Responses Client agent with HostedCodeInterpreterTool through AzureResponsesClient."""
    async with ChatClientAgent(
        chat_client=AzureResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that can execute Python code.",
        tools=[HostedCodeInterpreterTool()],
    ) as agent:
        # Test code interpreter functionality
        response = await agent.run("Calculate the sum of numbers from 1 to 10 using Python code.")

        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0
        # Should contain calculation result (sum of 1-10 = 55) or code execution content
        contains_relevant_content = any(
            term in response.text.lower() for term in ["55", "sum", "code", "python", "calculate", "10"]
        )
        assert contains_relevant_content or len(response.text.strip()) > 10


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_level_tool_persistence():
    """Test that agent-level tools persist across multiple runs with Azure Responses Client."""

    async with ChatClientAgent(
        chat_client=AzureResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that uses available tools.",
        tools=[get_weather],  # Agent-level tool
    ) as agent:
        # First run - agent-level tool should be available
        first_response = await agent.run("What's the weather like in Chicago?")

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None
        # Should use the agent-level weather tool
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "72"])

        # Second run - agent-level tool should still be available (persistence test)
        second_response = await agent.run("What's the weather in Miami?")

        assert isinstance(second_response, AgentRunResponse)
        assert second_response.text is not None
        # Should use the agent-level weather tool again
        assert any(term in second_response.text.lower() for term in ["miami", "sunny", "72"])


@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_run_level_tool_isolation():
    """Test that run-level tools are isolated to specific runs and don't persist with Azure Responses Client."""
    # Counter to track how many times the weather tool is called
    call_count = 0

    @ai_function
    async def get_weather_with_counter(location: Annotated[str, "The location as a city name"]) -> str:
        """Get the current weather in a given location."""
        nonlocal call_count
        call_count += 1
        return f"The weather in {location} is sunny and 72°F."

    async with ChatClientAgent(
        chat_client=AzureResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
    ) as agent:
        # First run - use run-level tool
        first_response = await agent.run(
            "What's the weather like in Chicago?",
            tools=[get_weather_with_counter],  # Run-level tool
        )

        assert isinstance(first_response, AgentRunResponse)
        assert first_response.text is not None
        # Should use the run-level weather tool (call count should be 1)
        assert call_count == 1
        assert any(term in first_response.text.lower() for term in ["chicago", "sunny", "72"])

        # Second run - run-level tool should NOT persist (key isolation test)
        second_response = await agent.run("What's the weather like in Miami?")

        assert isinstance(second_response, AgentRunResponse)
        assert second_response.text is not None
        # Should NOT use the weather tool since it was only run-level in previous call
        # Call count should still be 1 (no additional calls)
        assert call_count == 1
