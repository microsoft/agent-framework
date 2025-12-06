# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Annotated

import pytest
from azure.identity import AzureCliCredential
from pydantic import BaseModel

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedMCPTool,
    HostedVectorStoreContent,
    TextContent,
    ai_function,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.exceptions import ServiceInitializationError

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


async def create_vector_store(client: AzureOpenAIResponsesClient) -> tuple[str, HostedVectorStoreContent]:
    """Create a vector store with sample documents for testing."""
    file = await client.client.files.create(
        file=("todays_weather.txt", b"The weather today is sunny with a high of 75F."), purpose="assistants"
    )
    vector_store = await client.client.vector_stores.create(
        name="knowledge_base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )
    result = await client.client.vector_stores.files.create_and_poll(vector_store_id=vector_store.id, file_id=file.id)
    if result.last_error is not None:
        raise Exception(f"Vector store file processing failed with status: {result.last_error.message}")

    return file.id, HostedVectorStoreContent(vector_store_id=vector_store.id)


async def delete_vector_store(client: AzureOpenAIResponsesClient, file_id: str, vector_store_id: str) -> None:
    """Delete the vector store after tests."""

    await client.client.vector_stores.delete(vector_store_id=vector_store_id)
    await client.client.files.delete(file_id=file_id)


def test_init(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    azure_responses_client = AzureOpenAIResponsesClient()

    assert azure_responses_client.model_id == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(azure_responses_client, ChatClientProtocol)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        AzureOpenAIResponsesClient(api_key="34523", deployment_name={"test": "dict"})  # type: ignore


def test_init_model_id_constructor(azure_openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    model_id = "test_model_id"
    azure_responses_client = AzureOpenAIResponsesClient(deployment_name=model_id)

    assert azure_responses_client.model_id == model_id
    assert isinstance(azure_responses_client, ChatClientProtocol)


def test_init_with_default_header(azure_openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    azure_responses_client = AzureOpenAIResponsesClient(
        default_headers=default_headers,
    )

    assert azure_responses_client.model_id == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert isinstance(azure_responses_client, ChatClientProtocol)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in azure_responses_client.client.default_headers
        assert azure_responses_client.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]], indirect=True)
def test_init_with_empty_model_id(azure_openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        AzureOpenAIResponsesClient(
            env_file_path="test.env",
        )


def test_serialize(azure_openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "deployment_name": azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        "api_key": azure_openai_unit_test_env["AZURE_OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    azure_responses_client = AzureOpenAIResponsesClient.from_dict(settings)
    dumped_settings = azure_responses_client.to_dict()
    assert dumped_settings["deployment_name"] == azure_openai_unit_test_env["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]
    assert "api_key" not in dumped_settings
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_response() -> None:
    """Test azure responses client responses."""
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    assert isinstance(azure_responses_client, ChatClientProtocol)

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


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_response_tools() -> None:
    """Test azure responses client tools."""
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    assert isinstance(azure_responses_client, ChatClientProtocol)

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


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_streaming() -> None:
    """Test Azure azure responses client streaming responses."""
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    assert isinstance(azure_responses_client, ChatClientProtocol)

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


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_streaming_tools() -> None:
    """Test azure responses client streaming tools."""
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    assert isinstance(azure_responses_client, ChatClientProtocol)

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


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_basic_run():
    """Test Azure Responses Client agent basic run functionality with AzureOpenAIResponsesClient."""
    agent = AzureOpenAIResponsesClient(credential=AzureCliCredential()).create_agent(
        instructions="You are a helpful assistant.",
    )

    # Test basic run
    response = await agent.run("Hello! Please respond with 'Hello World' exactly.")

    assert isinstance(response, AgentRunResponse)
    assert response.text is not None
    assert len(response.text) > 0
    assert "hello world" in response.text.lower()


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_basic_run_streaming():
    """Test Azure Responses Client agent basic streaming functionality with AzureOpenAIResponsesClient."""
    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
    ) as agent:
        # Test streaming run
        full_text = ""
        async for chunk in agent.run_stream("Please respond with exactly: 'This is a streaming response test.'"):
            assert isinstance(chunk, AgentRunResponseUpdate)
            if chunk.text:
                full_text += chunk.text

        assert len(full_text) > 0
        assert "streaming response test" in full_text.lower()


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_thread_persistence():
    """Test Azure Responses Client agent thread persistence across runs with AzureOpenAIResponsesClient."""
    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
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


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_thread_storage_with_store_true():
    """Test Azure Responses Client agent with store=True to verify service_thread_id is returned."""
    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
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


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_existing_thread():
    """Test Azure Responses Client agent with existing thread to continue conversations across agent instances."""
    # First conversation - capture the thread
    preserved_thread = None

    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
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
        async with ChatAgent(
            chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
            instructions="You are a helpful assistant with good memory.",
        ) as second_agent:
            # Reuse the preserved thread
            second_response = await second_agent.run("What is my hobby?", thread=preserved_thread)

            assert isinstance(second_response, AgentRunResponse)
            assert second_response.text is not None
            assert "photography" in second_response.text.lower()


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_hosted_code_interpreter_tool():
    """Test Azure Responses Client agent with HostedCodeInterpreterTool through AzureOpenAIResponsesClient."""
    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
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


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_level_tool_persistence():
    """Test that agent-level tools persist across multiple runs with Azure Responses Client."""

    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
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


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_chat_options_run_level() -> None:
    """Integration test for comprehensive ChatOptions parameter coverage with Azure Response Agent."""
    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
    ) as agent:
        response = await agent.run(
            "Provide a brief, helpful response.",
            max_tokens=100,
            temperature=0.7,
            top_p=0.9,
            seed=123,
            user="comprehensive-test-user",
            tools=[get_weather],
            tool_choice="auto",
        )

        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_chat_options_agent_level() -> None:
    """Integration test for comprehensive ChatOptions parameter coverage with Azure Response Agent."""
    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant.",
        max_tokens=100,
        temperature=0.7,
        top_p=0.9,
        seed=123,
        user="comprehensive-test-user",
        tools=[get_weather],
        tool_choice="auto",
    ) as agent:
        response = await agent.run(
            "Provide a brief, helpful response.",
        )

        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_agent_hosted_mcp_tool() -> None:
    """Integration test for HostedMCPTool with Azure Response Agent using Microsoft Learn MCP."""

    mcp_tool = HostedMCPTool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
        description="A Microsoft Learn MCP server for documentation questions",
        approval_mode="never_require",
    )

    async with ChatAgent(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=[mcp_tool],
    ) as agent:
        response = await agent.run(
            "How to create an Azure storage account using az cli?",
            max_tokens=200,
        )

        assert isinstance(response, AgentRunResponse)
        assert response.text is not None
        assert len(response.text) > 0
        # Should contain Azure-related content since it's asking about Azure CLI
        assert any(term in response.text.lower() for term in ["azure", "storage", "account", "cli"])


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_file_search() -> None:
    """Test Azure responses client with file search tool."""
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    assert isinstance(azure_responses_client, ChatClientProtocol)

    file_id, vector_store = await create_vector_store(azure_responses_client)
    # Test that the client will use the file search tool
    response = await azure_responses_client.get_response(
        messages=[
            ChatMessage(
                role="user",
                text="What is the weather today? Do a file search to find the answer.",
            )
        ],
        tools=[HostedFileSearchTool(inputs=vector_store)],
        tool_choice="auto",
    )

    await delete_vector_store(azure_responses_client, file_id, vector_store.vector_store_id)
    assert "sunny" in response.text.lower()
    assert "75" in response.text


@pytest.mark.flaky
@skip_if_azure_integration_tests_disabled
async def test_azure_responses_client_file_search_streaming() -> None:
    """Test Azure responses client with file search tool and streaming."""
    azure_responses_client = AzureOpenAIResponsesClient(credential=AzureCliCredential())

    assert isinstance(azure_responses_client, ChatClientProtocol)

    file_id, vector_store = await create_vector_store(azure_responses_client)
    # Test that the client will use the file search tool
    response = azure_responses_client.get_streaming_response(
        messages=[
            ChatMessage(
                role="user",
                text="What is the weather today? Do a file search to find the answer.",
            )
        ],
        tools=[HostedFileSearchTool(inputs=vector_store)],
        tool_choice="auto",
    )

    assert response is not None
    full_message: str = ""
    async for chunk in response:
        assert chunk is not None
        assert isinstance(chunk, ChatResponseUpdate)
        for content in chunk.contents:
            if isinstance(content, TextContent) and content.text:
                full_message += content.text

    await delete_vector_store(azure_responses_client, file_id, vector_store.vector_store_id)

    assert "sunny" in full_message.lower()
    assert "75" in full_message
