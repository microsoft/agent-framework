# Copyright (c) Microsoft. All rights reserved.

import os
from typing import Annotated, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types.beta.assistant import Assistant
from pydantic import BaseModel, Field

from agent_framework import ChatAgent, HostedCodeInterpreterTool, HostedFileSearchTool, normalize_tools, tool
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.openai import OpenAIAssistantProvider
from agent_framework.openai._shared import from_assistant_tools, to_assistant_tools

# region Test Helpers


def create_mock_assistant(
    assistant_id: str = "asst_test123",
    name: str = "TestAssistant",
    model: str = "gpt-4",
    instructions: str | None = "You are a helpful assistant.",
    description: str | None = None,
    tools: list[Any] | None = None,
) -> Assistant:
    """Create a mock Assistant object."""
    mock = MagicMock(spec=Assistant)
    mock.id = assistant_id
    mock.name = name
    mock.model = model
    mock.instructions = instructions
    mock.description = description
    mock.tools = tools or []
    return mock


def create_function_tool(name: str, description: str = "A test function") -> MagicMock:
    """Create a mock FunctionTool."""
    mock = MagicMock()
    mock.type = "function"
    mock.function = MagicMock()
    mock.function.name = name
    mock.function.description = description
    return mock


def create_code_interpreter_tool() -> MagicMock:
    """Create a mock CodeInterpreterTool."""
    mock = MagicMock()
    mock.type = "code_interpreter"
    return mock


def create_file_search_tool() -> MagicMock:
    """Create a mock FileSearchTool."""
    mock = MagicMock()
    mock.type = "file_search"
    return mock


@pytest.fixture
def mock_async_openai() -> MagicMock:
    """Mock AsyncOpenAI client."""
    mock_client = MagicMock()

    # Mock beta.assistants
    mock_client.beta.assistants.create = AsyncMock(
        return_value=create_mock_assistant(assistant_id="asst_created123", name="CreatedAssistant")
    )
    mock_client.beta.assistants.retrieve = AsyncMock(
        return_value=create_mock_assistant(assistant_id="asst_retrieved123", name="RetrievedAssistant")
    )
    mock_client.beta.assistants.delete = AsyncMock()

    # Mock close method
    mock_client.close = AsyncMock()

    return mock_client


# Test function for tool validation
def get_weather(location: Annotated[str, Field(description="The location")]) -> str:
    """Get the weather for a location."""
    return f"Weather in {location}: sunny"


def search_database(query: Annotated[str, Field(description="Search query")]) -> str:
    """Search the database."""
    return f"Results for: {query}"


# Pydantic model for structured output tests
class WeatherResponse(BaseModel):
    location: str
    temperature: float
    conditions: str


# endregion


# region Initialization Tests


class TestOpenAIAssistantProviderInit:
    """Tests for provider initialization."""

    def test_init_with_client(self, mock_async_openai: MagicMock) -> None:
        """Test initialization with existing AsyncOpenAI client."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        assert provider._client is mock_async_openai  # type: ignore[reportPrivateUsage]
        assert provider._should_close_client is False  # type: ignore[reportPrivateUsage]

    def test_init_without_client_creates_one(self, openai_unit_test_env: dict[str, str]) -> None:
        """Test initialization creates client from settings."""
        provider = OpenAIAssistantProvider()

        assert provider._client is not None  # type: ignore[reportPrivateUsage]
        assert provider._should_close_client is True  # type: ignore[reportPrivateUsage]

    def test_init_with_api_key(self) -> None:
        """Test initialization with explicit API key."""
        provider = OpenAIAssistantProvider(api_key="sk-test-key")

        assert provider._client is not None  # type: ignore[reportPrivateUsage]
        assert provider._should_close_client is True  # type: ignore[reportPrivateUsage]

    def test_init_fails_without_api_key(self) -> None:
        """Test initialization fails without API key when settings return None."""
        from unittest.mock import patch

        # Mock OpenAISettings to return None for api_key
        with patch("agent_framework.openai._assistant_provider.OpenAISettings") as mock_settings:
            mock_settings.return_value.api_key = None

            with pytest.raises(ServiceInitializationError) as exc_info:
                OpenAIAssistantProvider()

            assert "API key is required" in str(exc_info.value)

    def test_init_with_org_id_and_base_url(self) -> None:
        """Test initialization with organization ID and base URL."""
        provider = OpenAIAssistantProvider(
            api_key="sk-test-key",
            org_id="org-123",
            base_url="https://custom.openai.com",
        )

        assert provider._client is not None  # type: ignore[reportPrivateUsage]


class TestOpenAIAssistantProviderContextManager:
    """Tests for async context manager."""

    async def test_context_manager_enter_exit(self, mock_async_openai: MagicMock) -> None:
        """Test async context manager entry and exit."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        async with provider as p:
            assert p is provider

    async def test_context_manager_closes_owned_client(self, openai_unit_test_env: dict[str, str]) -> None:
        """Test that owned client is closed on exit."""
        provider = OpenAIAssistantProvider()
        client = provider._client  # type: ignore[reportPrivateUsage]
        assert client is not None
        client.close = AsyncMock()

        async with provider:
            pass

        client.close.assert_called_once()

    async def test_context_manager_does_not_close_external_client(self, mock_async_openai: MagicMock) -> None:
        """Test that external client is not closed on exit."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        async with provider:
            pass

        mock_async_openai.close.assert_not_called()


# endregion


# region create_agent Tests


class TestOpenAIAssistantProviderCreateAgent:
    """Tests for create_agent method."""

    async def test_create_agent_basic(self, mock_async_openai: MagicMock) -> None:
        """Test basic assistant creation."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        agent = await provider.create_agent(
            name="TestAgent",
            model="gpt-4",
            instructions="You are helpful.",
        )

        assert isinstance(agent, ChatAgent)
        assert agent.name == "CreatedAssistant"
        mock_async_openai.beta.assistants.create.assert_called_once()

        # Verify create was called with correct parameters
        call_kwargs = mock_async_openai.beta.assistants.create.call_args.kwargs
        assert call_kwargs["name"] == "TestAgent"
        assert call_kwargs["model"] == "gpt-4"
        assert call_kwargs["instructions"] == "You are helpful."

    async def test_create_agent_with_description(self, mock_async_openai: MagicMock) -> None:
        """Test assistant creation with description."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        await provider.create_agent(
            name="TestAgent",
            model="gpt-4",
            description="A test agent description",
        )

        call_kwargs = mock_async_openai.beta.assistants.create.call_args.kwargs
        assert call_kwargs["description"] == "A test agent description"

    async def test_create_agent_with_function_tools(self, mock_async_openai: MagicMock) -> None:
        """Test assistant creation with function tools."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        agent = await provider.create_agent(
            name="WeatherAgent",
            model="gpt-4",
            tools=[get_weather],
        )

        assert isinstance(agent, ChatAgent)

        # Verify tools were passed to create
        call_kwargs = mock_async_openai.beta.assistants.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["type"] == "function"
        assert call_kwargs["tools"][0]["function"]["name"] == "get_weather"

    async def test_create_agent_with_tool(self, mock_async_openai: MagicMock) -> None:
        """Test assistant creation with FunctionTool."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        @tool
        def my_function(x: int) -> int:
            """Double a number."""
            return x * 2

        await provider.create_agent(
            name="TestAgent",
            model="gpt-4",
            tools=[my_function],
        )

        call_kwargs = mock_async_openai.beta.assistants.create.call_args.kwargs
        assert call_kwargs["tools"][0]["function"]["name"] == "my_function"

    async def test_create_agent_with_code_interpreter(self, mock_async_openai: MagicMock) -> None:
        """Test assistant creation with code interpreter."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        await provider.create_agent(
            name="CodeAgent",
            model="gpt-4",
            tools=[HostedCodeInterpreterTool()],
        )

        call_kwargs = mock_async_openai.beta.assistants.create.call_args.kwargs
        assert {"type": "code_interpreter"} in call_kwargs["tools"]

    async def test_create_agent_with_file_search(self, mock_async_openai: MagicMock) -> None:
        """Test assistant creation with file search."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        await provider.create_agent(
            name="SearchAgent",
            model="gpt-4",
            tools=[HostedFileSearchTool()],
        )

        call_kwargs = mock_async_openai.beta.assistants.create.call_args.kwargs
        assert any(t["type"] == "file_search" for t in call_kwargs["tools"])

    async def test_create_agent_with_file_search_max_results(self, mock_async_openai: MagicMock) -> None:
        """Test assistant creation with file search and max_results."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        await provider.create_agent(
            name="SearchAgent",
            model="gpt-4",
            tools=[HostedFileSearchTool(max_results=10)],
        )

        call_kwargs = mock_async_openai.beta.assistants.create.call_args.kwargs
        file_search_tool = next(t for t in call_kwargs["tools"] if t["type"] == "file_search")
        assert file_search_tool.get("file_search", {}).get("max_num_results") == 10

    async def test_create_agent_with_mixed_tools(self, mock_async_openai: MagicMock) -> None:
        """Test assistant creation with multiple tool types."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        await provider.create_agent(
            name="MultiToolAgent",
            model="gpt-4",
            tools=[get_weather, HostedCodeInterpreterTool(), HostedFileSearchTool()],
        )

        call_kwargs = mock_async_openai.beta.assistants.create.call_args.kwargs
        assert len(call_kwargs["tools"]) == 3

    async def test_create_agent_with_metadata(self, mock_async_openai: MagicMock) -> None:
        """Test assistant creation with metadata."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        await provider.create_agent(
            name="TestAgent",
            model="gpt-4",
            metadata={"env": "test", "version": "1.0"},
        )

        call_kwargs = mock_async_openai.beta.assistants.create.call_args.kwargs
        assert call_kwargs["metadata"] == {"env": "test", "version": "1.0"}

    async def test_create_agent_with_response_format_pydantic(self, mock_async_openai: MagicMock) -> None:
        """Test assistant creation with Pydantic response format via default_options."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        await provider.create_agent(
            name="StructuredAgent",
            model="gpt-4",
            default_options={"response_format": WeatherResponse},
        )

        call_kwargs = mock_async_openai.beta.assistants.create.call_args.kwargs
        assert call_kwargs["response_format"]["type"] == "json_schema"
        assert call_kwargs["response_format"]["json_schema"]["name"] == "WeatherResponse"

    async def test_create_agent_returns_chat_agent(self, mock_async_openai: MagicMock) -> None:
        """Test that create_agent returns a ChatAgent instance."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        agent = await provider.create_agent(
            name="TestAgent",
            model="gpt-4",
        )

        assert isinstance(agent, ChatAgent)


# endregion


# region get_agent Tests


class TestOpenAIAssistantProviderGetAgent:
    """Tests for get_agent method."""

    async def test_get_agent_basic(self, mock_async_openai: MagicMock) -> None:
        """Test retrieving an existing assistant."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        agent = await provider.get_agent(assistant_id="asst_123")

        assert isinstance(agent, ChatAgent)
        mock_async_openai.beta.assistants.retrieve.assert_called_once_with("asst_123")

    async def test_get_agent_with_instructions_override(self, mock_async_openai: MagicMock) -> None:
        """Test retrieving assistant with instruction override."""
        provider = OpenAIAssistantProvider(mock_async_openai)

        agent = await provider.get_agent(
            assistant_id="asst_123",
            instructions="Custom instructions",
        )

        # Agent should be created successfully with the custom instructions
        assert isinstance(agent, ChatAgent)
        assert agent.id == "asst_retrieved123"

    async def test_get_agent_with_function_tools(self, mock_async_openai: MagicMock) -> None:
        """Test retrieving assistant with function tools provided."""
        # Setup assistant with function tool
        assistant = create_mock_assistant(tools=[create_function_tool("get_weather")])
        mock_async_openai.beta.assistants.retrieve = AsyncMock(return_value=assistant)

        provider = OpenAIAssistantProvider(mock_async_openai)

        agent = await provider.get_agent(
            assistant_id="asst_123",
            tools=[get_weather],
        )

        assert isinstance(agent, ChatAgent)

    async def test_get_agent_validates_missing_function_tools(self, mock_async_openai: MagicMock) -> None:
        """Test that missing function tools raise ValueError."""
        # Setup assistant with function tool
        assistant = create_mock_assistant(tools=[create_function_tool("get_weather")])
        mock_async_openai.beta.assistants.retrieve = AsyncMock(return_value=assistant)

        provider = OpenAIAssistantProvider(mock_async_openai)

        with pytest.raises(ValueError) as exc_info:
            await provider.get_agent(assistant_id="asst_123")

        assert "get_weather" in str(exc_info.value)
        assert "no implementation was provided" in str(exc_info.value)

    async def test_get_agent_validates_multiple_missing_function_tools(self, mock_async_openai: MagicMock) -> None:
        """Test validation with multiple missing function tools."""
        assistant = create_mock_assistant(
            tools=[create_function_tool("get_weather"), create_function_tool("search_database")]
        )
        mock_async_openai.beta.assistants.retrieve = AsyncMock(return_value=assistant)

        provider = OpenAIAssistantProvider(mock_async_openai)

        with pytest.raises(ValueError) as exc_info:
            await provider.get_agent(assistant_id="asst_123")

        error_msg = str(exc_info.value)
        assert "get_weather" in error_msg or "search_database" in error_msg

    async def test_get_agent_merges_hosted_tools(self, mock_async_openai: MagicMock) -> None:
        """Test that hosted tools are automatically included."""
        assistant = create_mock_assistant(tools=[create_code_interpreter_tool(), create_file_search_tool()])
        mock_async_openai.beta.assistants.retrieve = AsyncMock(return_value=assistant)

        provider = OpenAIAssistantProvider(mock_async_openai)

        agent = await provider.get_agent(assistant_id="asst_123")

        # Hosted tools should be merged automatically
        assert isinstance(agent, ChatAgent)


# endregion


# region as_agent Tests


class TestOpenAIAssistantProviderAsAgent:
    """Tests for as_agent method."""

    def test_as_agent_no_http_call(self, mock_async_openai: MagicMock) -> None:
        """Test that as_agent doesn't make HTTP calls."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant = create_mock_assistant()

        agent = provider.as_agent(assistant)

        assert isinstance(agent, ChatAgent)
        # Verify no HTTP calls were made
        mock_async_openai.beta.assistants.create.assert_not_called()
        mock_async_openai.beta.assistants.retrieve.assert_not_called()

    def test_as_agent_wraps_assistant(self, mock_async_openai: MagicMock) -> None:
        """Test wrapping an SDK Assistant object."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant = create_mock_assistant(
            assistant_id="asst_wrap123",
            name="WrappedAssistant",
            instructions="Original instructions",
        )

        agent = provider.as_agent(assistant)

        assert agent.id == "asst_wrap123"
        assert agent.name == "WrappedAssistant"
        # Instructions are passed to ChatOptions, not exposed as attribute
        assert isinstance(agent, ChatAgent)

    def test_as_agent_with_instructions_override(self, mock_async_openai: MagicMock) -> None:
        """Test as_agent with instruction override."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant = create_mock_assistant(instructions="Original")

        agent = provider.as_agent(assistant, instructions="Override")

        # Agent should be created successfully with override instructions
        assert isinstance(agent, ChatAgent)

    def test_as_agent_validates_function_tools(self, mock_async_openai: MagicMock) -> None:
        """Test that missing function tools raise ValueError."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant = create_mock_assistant(tools=[create_function_tool("get_weather")])

        with pytest.raises(ValueError) as exc_info:
            provider.as_agent(assistant)

        assert "get_weather" in str(exc_info.value)

    def test_as_agent_with_function_tools_provided(self, mock_async_openai: MagicMock) -> None:
        """Test as_agent with function tools provided."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant = create_mock_assistant(tools=[create_function_tool("get_weather")])

        agent = provider.as_agent(assistant, tools=[get_weather])

        assert isinstance(agent, ChatAgent)

    def test_as_agent_merges_hosted_tools(self, mock_async_openai: MagicMock) -> None:
        """Test that hosted tools are merged automatically."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant = create_mock_assistant(tools=[create_code_interpreter_tool()])

        agent = provider.as_agent(assistant)

        assert isinstance(agent, ChatAgent)

    def test_as_agent_hosted_tools_not_required(self, mock_async_openai: MagicMock) -> None:
        """Test that hosted tools don't require user implementations."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant = create_mock_assistant(tools=[create_code_interpreter_tool(), create_file_search_tool()])

        # Should not raise - hosted tools don't need implementations
        agent = provider.as_agent(assistant)

        assert isinstance(agent, ChatAgent)


# endregion


# region Tool Conversion Tests


class TestToolConversion:
    """Tests for tool conversion utilities (shared functions)."""

    def test_to_assistant_tools_tool(self) -> None:
        """Test FunctionTool conversion to API format."""

        @tool
        def test_func(x: int) -> int:
            """Test function."""
            return x

        # Normalize tools first, then convert
        normalized = normalize_tools([test_func])
        api_tools = to_assistant_tools(normalized)

        assert len(api_tools) == 1
        assert api_tools[0]["type"] == "function"
        assert api_tools[0]["function"]["name"] == "test_func"

    def test_to_assistant_tools_callable(self) -> None:
        """Test raw callable conversion via normalize_tools."""
        # normalize_tools converts callables to FunctionTool
        normalized = normalize_tools([get_weather])
        api_tools = to_assistant_tools(normalized)

        assert len(api_tools) == 1
        assert api_tools[0]["type"] == "function"
        assert api_tools[0]["function"]["name"] == "get_weather"

    def test_to_assistant_tools_code_interpreter(self) -> None:
        """Test HostedCodeInterpreterTool conversion."""
        api_tools = to_assistant_tools([HostedCodeInterpreterTool()])

        assert len(api_tools) == 1
        assert api_tools[0] == {"type": "code_interpreter"}

    def test_to_assistant_tools_file_search(self) -> None:
        """Test HostedFileSearchTool conversion."""
        api_tools = to_assistant_tools([HostedFileSearchTool()])

        assert len(api_tools) == 1
        assert api_tools[0]["type"] == "file_search"

    def test_to_assistant_tools_file_search_with_max_results(self) -> None:
        """Test HostedFileSearchTool with max_results conversion."""
        api_tools = to_assistant_tools([HostedFileSearchTool(max_results=5)])

        assert api_tools[0]["file_search"]["max_num_results"] == 5

    def test_to_assistant_tools_dict(self) -> None:
        """Test raw dict tool passthrough."""
        raw_tool = {"type": "function", "function": {"name": "custom", "description": "Custom tool"}}

        api_tools = to_assistant_tools([raw_tool])

        assert len(api_tools) == 1
        assert api_tools[0] == raw_tool

    def test_to_assistant_tools_empty(self) -> None:
        """Test conversion with no tools."""
        api_tools = to_assistant_tools(None)

        assert api_tools == []

    def test_from_assistant_tools_code_interpreter(self) -> None:
        """Test converting code_interpreter tool from OpenAI format."""
        assistant_tools = [create_code_interpreter_tool()]

        tools = from_assistant_tools(assistant_tools)

        assert len(tools) == 1
        assert isinstance(tools[0], HostedCodeInterpreterTool)

    def test_from_assistant_tools_file_search(self) -> None:
        """Test converting file_search tool from OpenAI format."""
        assistant_tools = [create_file_search_tool()]

        tools = from_assistant_tools(assistant_tools)

        assert len(tools) == 1
        assert isinstance(tools[0], HostedFileSearchTool)

    def test_from_assistant_tools_function_skipped(self) -> None:
        """Test that function tools are skipped (no implementations)."""
        assistant_tools = [create_function_tool("test_func")]

        tools = from_assistant_tools(assistant_tools)

        assert len(tools) == 0  # Function tools are skipped

    def test_from_assistant_tools_empty(self) -> None:
        """Test conversion with no tools."""
        tools = from_assistant_tools(None)

        assert tools == []


# endregion


# region Tool Validation Tests


class TestToolValidation:
    """Tests for tool validation."""

    def test_validate_missing_function_tool_raises(self, mock_async_openai: MagicMock) -> None:
        """Test that missing function tools raise ValueError."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant_tools = [create_function_tool("my_function")]

        with pytest.raises(ValueError) as exc_info:
            provider._validate_function_tools(assistant_tools, None)  # type: ignore[reportPrivateUsage]

        assert "my_function" in str(exc_info.value)

    def test_validate_all_tools_provided_passes(self, mock_async_openai: MagicMock) -> None:
        """Test that validation passes when all tools provided."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant_tools = [create_function_tool("get_weather")]

        # Should not raise
        provider._validate_function_tools(assistant_tools, [get_weather])  # type: ignore[reportPrivateUsage]

    def test_validate_hosted_tools_not_required(self, mock_async_openai: MagicMock) -> None:
        """Test that hosted tools don't require implementations."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant_tools = [create_code_interpreter_tool(), create_file_search_tool()]

        # Should not raise
        provider._validate_function_tools(assistant_tools, None)  # type: ignore[reportPrivateUsage]

    def test_validate_with_tool(self, mock_async_openai: MagicMock) -> None:
        """Test validation with FunctionTool."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant_tools = [create_function_tool("get_weather")]

        wrapped = tool(get_weather)

        # Should not raise
        provider._validate_function_tools(assistant_tools, [wrapped])  # type: ignore[reportPrivateUsage]

    def test_validate_partial_tools_raises(self, mock_async_openai: MagicMock) -> None:
        """Test that partial tool provision raises error."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant_tools = [
            create_function_tool("get_weather"),
            create_function_tool("search_database"),
        ]

        with pytest.raises(ValueError) as exc_info:
            provider._validate_function_tools(assistant_tools, [get_weather])  # type: ignore[reportPrivateUsage]

        assert "search_database" in str(exc_info.value)


# endregion


# region Tool Merging Tests


class TestToolMerging:
    """Tests for tool merging."""

    def test_merge_code_interpreter(self, mock_async_openai: MagicMock) -> None:
        """Test merging code interpreter tool."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant_tools = [create_code_interpreter_tool()]

        merged = provider._merge_tools(assistant_tools, None)  # type: ignore[reportPrivateUsage]

        assert len(merged) == 1
        assert isinstance(merged[0], HostedCodeInterpreterTool)

    def test_merge_file_search(self, mock_async_openai: MagicMock) -> None:
        """Test merging file search tool."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant_tools = [create_file_search_tool()]

        merged = provider._merge_tools(assistant_tools, None)  # type: ignore[reportPrivateUsage]

        assert len(merged) == 1
        assert isinstance(merged[0], HostedFileSearchTool)

    def test_merge_with_user_tools(self, mock_async_openai: MagicMock) -> None:
        """Test merging hosted and user tools."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant_tools = [create_code_interpreter_tool()]

        merged = provider._merge_tools(assistant_tools, [get_weather])  # type: ignore[reportPrivateUsage]

        assert len(merged) == 2
        assert isinstance(merged[0], HostedCodeInterpreterTool)

    def test_merge_multiple_hosted_tools(self, mock_async_openai: MagicMock) -> None:
        """Test merging multiple hosted tools."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant_tools = [create_code_interpreter_tool(), create_file_search_tool()]

        merged = provider._merge_tools(assistant_tools, None)  # type: ignore[reportPrivateUsage]

        assert len(merged) == 2

    def test_merge_single_user_tool(self, mock_async_openai: MagicMock) -> None:
        """Test merging with single user tool (not list)."""
        provider = OpenAIAssistantProvider(mock_async_openai)
        assistant_tools: list[Any] = []

        merged = provider._merge_tools(assistant_tools, get_weather)  # type: ignore[reportPrivateUsage]

        assert len(merged) == 1


# endregion


# region Integration Tests


skip_if_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "false").lower() != "true"
    or os.getenv("OPENAI_API_KEY", "") in ("", "test-dummy-key"),
    reason="No real OPENAI_API_KEY provided; skipping integration tests."
    if os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    else "Integration tests are disabled.",
)


@skip_if_openai_integration_tests_disabled
class TestOpenAIAssistantProviderIntegration:
    """Integration tests requiring real OpenAI API."""

    async def test_create_and_run_agent(self) -> None:
        """End-to-end test of creating and running an agent."""
        provider = OpenAIAssistantProvider()

        agent = await provider.create_agent(
            name="IntegrationTestAgent",
            model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            instructions="You are a helpful assistant. Respond briefly.",
        )

        try:
            result = await agent.run("Say 'hello' and nothing else.")
            result_text = str(result)
            assert "hello" in result_text.lower()
        finally:
            # Clean up the assistant
            await provider._client.beta.assistants.delete(agent.id)  # type: ignore[reportPrivateUsage, union-attr]

    async def test_create_agent_with_function_tools_integration(self) -> None:
        """Integration test with function tools."""
        provider = OpenAIAssistantProvider()

        @tool(approval_mode="never_require")
        def get_current_time() -> str:
            """Get the current time."""
            from datetime import datetime

            return datetime.now().strftime("%H:%M")

        agent = await provider.create_agent(
            name="TimeAgent",
            model=os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4"),
            instructions="You are a helpful assistant.",
            tools=[get_current_time],
        )

        try:
            result = await agent.run("What time is it? Use the get_current_time function.")
            result_text = str(result)
            # The response should contain time information
            assert ":" in result_text or "time" in result_text.lower()
        finally:
            await provider._client.beta.assistants.delete(agent.id)  # type: ignore[reportPrivateUsage, union-attr]


# endregion
