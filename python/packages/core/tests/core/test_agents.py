# Copyright (c) Microsoft. All rights reserved.

import contextlib
from collections.abc import AsyncIterable, MutableSequence, Sequence
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pytest import raises

from agent_framework import (
    AgentProtocol,
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatMessageStore,
    ChatOptions,
    ChatResponse,
    Content,
    Context,
    ContextProvider,
    HostedCodeInterpreterTool,
    Role,
    ToolProtocol,
    tool,
)
from agent_framework._agents import _merge_options, _sanitize_agent_name
from agent_framework._mcp import MCPTool
from agent_framework.exceptions import AgentExecutionException, AgentInitializationError


def test_agent_thread_type(agent_thread: AgentThread) -> None:
    assert isinstance(agent_thread, AgentThread)


def test_agent_type(agent: AgentProtocol) -> None:
    assert isinstance(agent, AgentProtocol)


async def test_agent_run(agent: AgentProtocol) -> None:
    response = await agent.run("test")
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[0].text == "Response"


async def test_agent_run_streaming(agent: AgentProtocol) -> None:
    async def collect_updates(updates: AsyncIterable[AgentResponseUpdate]) -> list[AgentResponseUpdate]:
        return [u async for u in updates]

    updates = await collect_updates(agent.run_stream(messages="test"))
    assert len(updates) == 1
    assert updates[0].text == "Response"


def test_chat_client_agent_type(chat_client: ChatClientProtocol) -> None:
    chat_client_agent = ChatAgent(chat_client=chat_client)
    assert isinstance(chat_client_agent, AgentProtocol)


async def test_chat_client_agent_init(chat_client: ChatClientProtocol) -> None:
    agent_id = str(uuid4())
    agent = ChatAgent(chat_client=chat_client, id=agent_id, description="Test")

    assert agent.id == agent_id
    assert agent.name is None
    assert agent.description == "Test"


async def test_chat_client_agent_init_with_name(chat_client: ChatClientProtocol) -> None:
    agent_id = str(uuid4())
    agent = ChatAgent(chat_client=chat_client, id=agent_id, name="Test Agent", description="Test")

    assert agent.id == agent_id
    assert agent.name == "Test Agent"
    assert agent.description == "Test"


async def test_chat_client_agent_run(chat_client: ChatClientProtocol) -> None:
    agent = ChatAgent(chat_client=chat_client)

    result = await agent.run("Hello")

    assert result.text == "test response"


async def test_chat_client_agent_run_streaming(chat_client: ChatClientProtocol) -> None:
    agent = ChatAgent(chat_client=chat_client)

    result = await AgentResponse.from_agent_response_generator(agent.run_stream("Hello"))

    assert result.text == "test streaming response another update"


async def test_chat_client_agent_get_new_thread(chat_client: ChatClientProtocol) -> None:
    agent = ChatAgent(chat_client=chat_client)
    thread = agent.get_new_thread()

    assert isinstance(thread, AgentThread)


async def test_chat_client_agent_prepare_thread_and_messages(chat_client: ChatClientProtocol) -> None:
    agent = ChatAgent(chat_client=chat_client)
    message = ChatMessage(role=Role.USER, text="Hello")
    thread = AgentThread(message_store=ChatMessageStore(messages=[message]))

    _, _, result_messages = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=thread,
        input_messages=[ChatMessage(role=Role.USER, text="Test")],
    )

    assert len(result_messages) == 2
    assert result_messages[0] == message
    assert result_messages[1].text == "Test"


async def test_prepare_thread_does_not_mutate_agent_chat_options(chat_client: ChatClientProtocol) -> None:
    tool = HostedCodeInterpreterTool()
    agent = ChatAgent(chat_client=chat_client, tools=[tool])

    assert agent.default_options.get("tools") is not None
    base_tools = agent.default_options["tools"]
    thread = agent.get_new_thread()

    _, prepared_chat_options, _ = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=thread,
        input_messages=[ChatMessage(role=Role.USER, text="Test")],
    )

    assert prepared_chat_options.get("tools") is not None
    assert base_tools is not prepared_chat_options["tools"]

    prepared_chat_options["tools"].append(HostedCodeInterpreterTool())  # type: ignore[arg-type]
    assert len(agent.default_options["tools"]) == 1


async def test_chat_client_agent_update_thread_id(chat_client_base: ChatClientProtocol) -> None:
    mock_response = ChatResponse(
        messages=[ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text("test response")])],
        conversation_id="123",
    )
    chat_client_base.run_responses = [mock_response]
    agent = ChatAgent(
        chat_client=chat_client_base,
        tools=HostedCodeInterpreterTool(),
    )
    thread = agent.get_new_thread()

    result = await agent.run("Hello", thread=thread)
    assert result.text == "test response"

    assert thread.service_thread_id == "123"


async def test_chat_client_agent_update_thread_messages(chat_client: ChatClientProtocol) -> None:
    agent = ChatAgent(chat_client=chat_client)
    thread = agent.get_new_thread()

    result = await agent.run("Hello", thread=thread)
    assert result.text == "test response"

    assert thread.service_thread_id is None
    assert thread.message_store is not None

    chat_messages: list[ChatMessage] = await thread.message_store.list_messages()

    assert chat_messages is not None
    assert len(chat_messages) == 2
    assert chat_messages[0].text == "Hello"
    assert chat_messages[1].text == "test response"


async def test_chat_client_agent_update_thread_conversation_id_missing(chat_client: ChatClientProtocol) -> None:
    agent = ChatAgent(chat_client=chat_client)
    thread = AgentThread(service_thread_id="123")

    with raises(AgentExecutionException, match="Service did not return a valid conversation id"):
        await agent._update_thread_with_type_and_conversation_id(thread, None)  # type: ignore[reportPrivateUsage]


async def test_chat_client_agent_default_author_name(chat_client: ChatClientProtocol) -> None:
    # Name is not specified here, so default name should be used
    agent = ChatAgent(chat_client=chat_client)

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "UnnamedAgent"


async def test_chat_client_agent_author_name_as_agent_name(chat_client: ChatClientProtocol) -> None:
    # Name is specified here, so it should be used as author name
    agent = ChatAgent(chat_client=chat_client, name="TestAgent")

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "TestAgent"


async def test_chat_client_agent_author_name_is_used_from_response(chat_client_base: ChatClientProtocol) -> None:
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[
                ChatMessage(
                    role=Role.ASSISTANT, contents=[Content.from_text("test response")], author_name="TestAuthor"
                )
            ]
        )
    ]

    agent = ChatAgent(chat_client=chat_client_base, tools=HostedCodeInterpreterTool())

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "TestAuthor"


# Mock context provider for testing
class MockContextProvider(ContextProvider):
    def __init__(self, messages: list[ChatMessage] | None = None) -> None:
        self.context_messages = messages
        self.thread_created_called = False
        self.invoked_called = False
        self.invoking_called = False
        self.thread_created_thread_id = None
        self.invoked_thread_id = None
        self.new_messages: list[ChatMessage] = []

    async def thread_created(self, thread_id: str | None) -> None:
        self.thread_created_called = True
        self.thread_created_thread_id = thread_id

    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Any = None,
        **kwargs: Any,
    ) -> None:
        self.invoked_called = True
        if isinstance(request_messages, ChatMessage):
            self.new_messages.append(request_messages)
        else:
            self.new_messages.extend(request_messages)
        if isinstance(response_messages, ChatMessage):
            self.new_messages.append(response_messages)
        else:
            self.new_messages.extend(response_messages)

    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        self.invoking_called = True
        return Context(messages=self.context_messages)


async def test_chat_agent_context_providers_model_invoking(chat_client: ChatClientProtocol) -> None:
    """Test that context providers' invoking is called during agent run."""
    mock_provider = MockContextProvider(messages=[ChatMessage(role=Role.SYSTEM, text="Test context instructions")])
    agent = ChatAgent(chat_client=chat_client, context_provider=mock_provider)

    await agent.run("Hello")

    assert mock_provider.invoking_called


async def test_chat_agent_context_providers_thread_created(chat_client_base: ChatClientProtocol) -> None:
    """Test that context providers' thread_created is called during agent run."""
    mock_provider = MockContextProvider()
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text("test response")])],
            conversation_id="test-thread-id",
        )
    ]

    agent = ChatAgent(chat_client=chat_client_base, context_provider=mock_provider)

    await agent.run("Hello")

    assert mock_provider.thread_created_called
    assert mock_provider.thread_created_thread_id == "test-thread-id"


async def test_chat_agent_context_providers_messages_adding(chat_client: ChatClientProtocol) -> None:
    """Test that context providers' invoked is called during agent run."""
    mock_provider = MockContextProvider()
    agent = ChatAgent(chat_client=chat_client, context_provider=mock_provider)

    await agent.run("Hello")

    assert mock_provider.invoked_called
    # Should be called with both input and response messages
    assert len(mock_provider.new_messages) >= 2


async def test_chat_agent_context_instructions_in_messages(chat_client: ChatClientProtocol) -> None:
    """Test that AI context instructions are included in messages."""
    mock_provider = MockContextProvider(messages=[ChatMessage(role="system", text="Context-specific instructions")])
    agent = ChatAgent(chat_client=chat_client, instructions="Agent instructions", context_provider=mock_provider)

    # We need to test the _prepare_thread_and_messages method directly
    _, _, messages = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=None, input_messages=[ChatMessage(role=Role.USER, text="Hello")]
    )

    # Should have context instructions, and user message
    assert len(messages) == 2
    assert messages[0].role == Role.SYSTEM
    assert messages[0].text == "Context-specific instructions"
    assert messages[1].role == Role.USER
    assert messages[1].text == "Hello"
    # instructions system message is added by a chat_client


async def test_chat_agent_no_context_instructions(chat_client: ChatClientProtocol) -> None:
    """Test behavior when AI context has no instructions."""
    mock_provider = MockContextProvider()
    agent = ChatAgent(chat_client=chat_client, instructions="Agent instructions", context_provider=mock_provider)

    _, _, messages = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=None, input_messages=[ChatMessage(role=Role.USER, text="Hello")]
    )

    # Should have agent instructions and user message only
    assert len(messages) == 1
    assert messages[0].role == Role.USER
    assert messages[0].text == "Hello"


async def test_chat_agent_run_stream_context_providers(chat_client: ChatClientProtocol) -> None:
    """Test that context providers work with run_stream method."""
    mock_provider = MockContextProvider(messages=[ChatMessage(role=Role.SYSTEM, text="Stream context instructions")])
    agent = ChatAgent(chat_client=chat_client, context_provider=mock_provider)

    # Collect all stream updates
    updates: list[AgentResponseUpdate] = []
    async for update in agent.run_stream("Hello"):
        updates.append(update)

    # Verify context provider was called
    assert mock_provider.invoking_called
    # no conversation id is created, so no need to thread_create to be called.
    assert not mock_provider.thread_created_called
    assert mock_provider.invoked_called


async def test_chat_agent_context_providers_with_thread_service_id(chat_client_base: ChatClientProtocol) -> None:
    """Test context providers with service-managed thread."""
    mock_provider = MockContextProvider()
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, contents=[Content.from_text("test response")])],
            conversation_id="service-thread-123",
        )
    ]

    agent = ChatAgent(chat_client=chat_client_base, context_provider=mock_provider)

    # Use existing service-managed thread
    thread = agent.get_new_thread(service_thread_id="existing-thread-id")
    await agent.run("Hello", thread=thread)

    # invoked should be called with the service thread ID from response
    assert mock_provider.invoked_called


# Tests for as_tool method
async def test_chat_agent_as_tool_basic(chat_client: ChatClientProtocol) -> None:
    """Test basic as_tool functionality."""
    agent = ChatAgent(chat_client=chat_client, name="TestAgent", description="Test agent for as_tool")

    tool = agent.as_tool()

    assert tool.name == "TestAgent"
    assert tool.description == "Test agent for as_tool"
    assert hasattr(tool, "func")
    assert hasattr(tool, "input_model")


async def test_chat_agent_as_tool_custom_parameters(chat_client: ChatClientProtocol) -> None:
    """Test as_tool with custom parameters."""
    agent = ChatAgent(chat_client=chat_client, name="TestAgent", description="Original description")

    tool = agent.as_tool(
        name="CustomTool",
        description="Custom description",
        arg_name="query",
        arg_description="Custom input description",
    )

    assert tool.name == "CustomTool"
    assert tool.description == "Custom description"

    # Check that the input model has the custom field name
    schema = tool.input_model.model_json_schema()
    assert "query" in schema["properties"]
    assert schema["properties"]["query"]["description"] == "Custom input description"


async def test_chat_agent_as_tool_defaults(chat_client: ChatClientProtocol) -> None:
    """Test as_tool with default parameters."""
    agent = ChatAgent(
        chat_client=chat_client,
        name="TestAgent",
        # No description provided
    )

    tool = agent.as_tool()

    assert tool.name == "TestAgent"
    assert tool.description == ""  # Should default to empty string

    # Check default input field
    schema = tool.input_model.model_json_schema()
    assert "task" in schema["properties"]
    assert "Task for TestAgent" in schema["properties"]["task"]["description"]


async def test_chat_agent_as_tool_no_name(chat_client: ChatClientProtocol) -> None:
    """Test as_tool when agent has no name (should raise ValueError)."""
    agent = ChatAgent(chat_client=chat_client)  # No name provided

    # Should raise ValueError since agent has no name
    with raises(ValueError, match="Agent tool name cannot be None"):
        agent.as_tool()


async def test_chat_agent_as_tool_function_execution(chat_client: ChatClientProtocol) -> None:
    """Test that the generated FunctionTool can be executed."""
    agent = ChatAgent(chat_client=chat_client, name="TestAgent", description="Test agent")

    tool = agent.as_tool()

    # Test function execution
    result = await tool.invoke(arguments=tool.input_model(task="Hello"))

    # Should return the agent's response text
    assert isinstance(result, str)
    assert result == "test response"  # From mock chat client


async def test_chat_agent_as_tool_with_stream_callback(chat_client: ChatClientProtocol) -> None:
    """Test as_tool with stream callback functionality."""
    agent = ChatAgent(chat_client=chat_client, name="StreamingAgent")

    # Collect streaming updates
    collected_updates: list[AgentResponseUpdate] = []

    def stream_callback(update: AgentResponseUpdate) -> None:
        collected_updates.append(update)

    tool = agent.as_tool(stream_callback=stream_callback)

    # Execute the tool
    result = await tool.invoke(arguments=tool.input_model(task="Hello"))

    # Should have collected streaming updates
    assert len(collected_updates) > 0
    assert isinstance(result, str)
    # Result should be concatenation of all streaming updates
    expected_text = "".join(update.text for update in collected_updates)
    assert result == expected_text


async def test_chat_agent_as_tool_with_custom_arg_name(chat_client: ChatClientProtocol) -> None:
    """Test as_tool with custom argument name."""
    agent = ChatAgent(chat_client=chat_client, name="CustomArgAgent")

    tool = agent.as_tool(arg_name="prompt", arg_description="Custom prompt input")

    # Test that the custom argument name works
    result = await tool.invoke(arguments=tool.input_model(prompt="Test prompt"))
    assert result == "test response"


async def test_chat_agent_as_tool_with_async_stream_callback(chat_client: ChatClientProtocol) -> None:
    """Test as_tool with async stream callback functionality."""
    agent = ChatAgent(chat_client=chat_client, name="AsyncStreamingAgent")

    # Collect streaming updates using an async callback
    collected_updates: list[AgentResponseUpdate] = []

    async def async_stream_callback(update: AgentResponseUpdate) -> None:
        collected_updates.append(update)

    tool = agent.as_tool(stream_callback=async_stream_callback)

    # Execute the tool
    result = await tool.invoke(arguments=tool.input_model(task="Hello"))

    # Should have collected streaming updates
    assert len(collected_updates) > 0
    assert isinstance(result, str)
    # Result should be concatenation of all streaming updates
    expected_text = "".join(update.text for update in collected_updates)
    assert result == expected_text


async def test_chat_agent_as_tool_name_sanitization(chat_client: ChatClientProtocol) -> None:
    """Test as_tool name sanitization."""
    test_cases = [
        ("Invoice & Billing Agent", "Invoice_Billing_Agent"),
        ("Travel & Logistics Agent", "Travel_Logistics_Agent"),
        ("Agent@Company.com", "Agent_Company_com"),
        ("Agent___Multiple___Underscores", "Agent_Multiple_Underscores"),
        ("123Agent", "_123Agent"),  # Test digit prefix handling
        ("9to5Helper", "_9to5Helper"),  # Another digit prefix case
        ("@@@", "agent"),  # Test empty sanitization fallback
    ]

    for agent_name, expected_tool_name in test_cases:
        agent = ChatAgent(chat_client=chat_client, name=agent_name, description="Test agent")
        tool = agent.as_tool()
        assert tool.name == expected_tool_name, f"Expected {expected_tool_name}, got {tool.name} for input {agent_name}"


async def test_chat_agent_as_mcp_server_basic(chat_client: ChatClientProtocol) -> None:
    """Test basic as_mcp_server functionality."""
    agent = ChatAgent(chat_client=chat_client, name="TestAgent", description="Test agent for MCP")

    # Create MCP server with default parameters
    server = agent.as_mcp_server()

    # Verify server is created
    assert server is not None
    assert hasattr(server, "name")
    assert hasattr(server, "version")


async def test_chat_agent_run_with_mcp_tools(chat_client: ChatClientProtocol) -> None:
    """Test run method with MCP tools to cover MCP tool handling code."""
    agent = ChatAgent(chat_client=chat_client, name="TestAgent", description="Test agent")

    # Create a mock MCP tool
    mock_mcp_tool = MagicMock(spec=MCPTool)
    mock_mcp_tool.is_connected = False
    mock_mcp_tool.functions = [MagicMock()]

    # Mock the async context manager entry
    mock_mcp_tool.__aenter__ = AsyncMock(return_value=mock_mcp_tool)
    mock_mcp_tool.__aexit__ = AsyncMock(return_value=None)

    # Test run with MCP tools - this should hit the MCP tool handling code
    with contextlib.suppress(Exception):
        # We expect this to fail since we're using mocks, but we want to exercise the code path
        await agent.run(messages="Test message", tools=[mock_mcp_tool])


async def test_chat_agent_with_local_mcp_tools(chat_client: ChatClientProtocol) -> None:
    """Test agent initialization with local MCP tools."""
    # Create a mock MCP tool
    mock_mcp_tool = MagicMock(spec=MCPTool)
    mock_mcp_tool.is_connected = False
    mock_mcp_tool.__aenter__ = AsyncMock(return_value=mock_mcp_tool)
    mock_mcp_tool.__aexit__ = AsyncMock(return_value=None)

    # Test agent with MCP tools in constructor
    with contextlib.suppress(Exception):
        agent = ChatAgent(chat_client=chat_client, name="TestAgent", description="Test agent", tools=[mock_mcp_tool])
        # Test async context manager with MCP tools
        async with agent:
            pass


async def test_agent_tool_receives_thread_in_kwargs(chat_client_base: Any) -> None:
    """Verify tool execution receives 'thread' inside **kwargs when function is called by client."""

    captured: dict[str, Any] = {}

    @tool(name="echo_thread_info", approval_mode="never_require")
    def echo_thread_info(text: str, **kwargs: Any) -> str:  # type: ignore[reportUnknownParameterType]
        thread = kwargs.get("thread")
        captured["has_thread"] = thread is not None
        captured["has_message_store"] = thread.message_store is not None if isinstance(thread, AgentThread) else False
        return f"echo: {text}"

    # Make the base client emit a function call for our tool
    chat_client_base.run_responses = [
        ChatResponse(
            messages=ChatMessage(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="1", name="echo_thread_info", arguments='{"text": "hello"}')
                ],
            )
        ),
        ChatResponse(messages=ChatMessage(role="assistant", text="done")),
    ]

    agent = ChatAgent(
        chat_client=chat_client_base, tools=[echo_thread_info], chat_message_store_factory=ChatMessageStore
    )
    thread = agent.get_new_thread()

    result = await agent.run("hello", thread=thread)

    assert result.text == "done"
    assert captured.get("has_thread") is True
    assert captured.get("has_message_store") is True


async def test_chat_agent_tool_choice_run_level_overrides_agent_level(chat_client_base: Any, tool_tool: Any) -> None:
    """Verify that tool_choice passed to run() overrides agent-level tool_choice."""

    captured_options: list[dict[str, Any]] = []

    # Store the original inner method
    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[ChatMessage], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(options)
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    # Create agent with agent-level tool_choice="auto" and a tool (tools required for tool_choice to be meaningful)
    agent = ChatAgent(
        chat_client=chat_client_base,
        tools=[tool_tool],
        options={"tool_choice": "auto"},
    )

    # Run with run-level tool_choice="required"
    await agent.run("Hello", options={"tool_choice": "required"})

    # Verify the client received tool_choice="required", not "auto"
    assert len(captured_options) >= 1
    assert captured_options[0]["tool_choice"] == "required"


async def test_chat_agent_tool_choice_agent_level_used_when_run_level_not_specified(
    chat_client_base: Any, tool_tool: Any
) -> None:
    """Verify that agent-level tool_choice is used when run() doesn't specify one."""
    captured_options: list[ChatOptions] = []

    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[ChatMessage], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(options)
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    # Create agent with agent-level tool_choice="required" and a tool
    agent = ChatAgent(
        chat_client=chat_client_base,
        tools=[tool_tool],
        default_options={"tool_choice": "required"},
    )

    # Run without specifying tool_choice
    await agent.run("Hello")

    # Verify the client received tool_choice="required" from agent-level
    assert len(captured_options) >= 1
    assert captured_options[0]["tool_choice"] == "required"
    # older code compared to ToolMode constants; ensure value is 'required'
    assert captured_options[0]["tool_choice"] == "required"


async def test_chat_agent_tool_choice_none_at_run_preserves_agent_level(chat_client_base: Any, tool_tool: Any) -> None:
    """Verify that tool_choice=None at run() uses agent-level default."""
    captured_options: list[ChatOptions] = []

    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[ChatMessage], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(options)
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    # Create agent with agent-level tool_choice="auto" and a tool
    agent = ChatAgent(
        chat_client=chat_client_base,
        tools=[tool_tool],
        default_options={"tool_choice": "auto"},
    )

    # Run with explicitly passing None (same as not specifying)
    await agent.run("Hello", options={"tool_choice": None})

    # Verify the client received tool_choice="auto" from agent-level
    assert len(captured_options) >= 1
    assert captured_options[0]["tool_choice"] == "auto"


# region Test _merge_options


def test_merge_options_basic():
    """Test _merge_options merges two dicts with override precedence."""
    base = {"key1": "value1", "key2": "value2"}
    override = {"key2": "new_value2", "key3": "value3"}

    result = _merge_options(base, override)

    assert result["key1"] == "value1"
    assert result["key2"] == "new_value2"
    assert result["key3"] == "value3"


def test_merge_options_none_values_ignored():
    """Test _merge_options ignores None values in override."""
    base = {"key1": "value1"}
    override = {"key1": None, "key2": "value2"}

    result = _merge_options(base, override)

    assert result["key1"] == "value1"  # None didn't override
    assert result["key2"] == "value2"


def test_merge_options_tools_combined():
    """Test _merge_options combines tool lists without duplicates."""

    class MockTool:
        def __init__(self, name):
            self.name = name

    tool1 = MockTool("tool1")
    tool2 = MockTool("tool2")
    tool3 = MockTool("tool1")  # Duplicate name

    base = {"tools": [tool1]}
    override = {"tools": [tool2, tool3]}

    result = _merge_options(base, override)

    # Should have tool1 and tool2, but not duplicate tool3
    assert len(result["tools"]) == 2
    tool_names = [t.name for t in result["tools"]]
    assert "tool1" in tool_names
    assert "tool2" in tool_names


def test_merge_options_logit_bias_merged():
    """Test _merge_options merges logit_bias dicts."""
    base = {"logit_bias": {"token1": 1.0}}
    override = {"logit_bias": {"token2": 2.0}}

    result = _merge_options(base, override)

    assert result["logit_bias"]["token1"] == 1.0
    assert result["logit_bias"]["token2"] == 2.0


def test_merge_options_metadata_merged():
    """Test _merge_options merges metadata dicts."""
    base = {"metadata": {"key1": "value1"}}
    override = {"metadata": {"key2": "value2"}}

    result = _merge_options(base, override)

    assert result["metadata"]["key1"] == "value1"
    assert result["metadata"]["key2"] == "value2"


def test_merge_options_instructions_concatenated():
    """Test _merge_options concatenates instructions."""
    base = {"instructions": "First instruction."}
    override = {"instructions": "Second instruction."}

    result = _merge_options(base, override)

    assert "First instruction." in result["instructions"]
    assert "Second instruction." in result["instructions"]
    assert "\n" in result["instructions"]


# endregion


# region Test _sanitize_agent_name


def test_sanitize_agent_name_none():
    """Test _sanitize_agent_name returns None for None input."""
    assert _sanitize_agent_name(None) is None


def test_sanitize_agent_name_valid():
    """Test _sanitize_agent_name returns valid names unchanged."""
    assert _sanitize_agent_name("valid_name") == "valid_name"
    assert _sanitize_agent_name("ValidName123") == "ValidName123"


def test_sanitize_agent_name_replaces_invalid_chars():
    """Test _sanitize_agent_name replaces invalid characters."""
    result = _sanitize_agent_name("Agent Name!")
    # Should replace spaces and special chars with underscores
    assert " " not in result
    assert "!" not in result


# endregion


# region Test AgentProtocol.get_new_thread and deserialize_thread


@pytest.mark.asyncio
async def test_agent_get_new_thread(chat_client_base: ChatClientProtocol, tool_tool: ToolProtocol):
    """Test that get_new_thread returns a new AgentThread."""
    agent = ChatAgent(chat_client=chat_client_base, tools=[tool_tool])

    thread = agent.get_new_thread()

    assert thread is not None
    assert isinstance(thread, AgentThread)


@pytest.mark.asyncio
async def test_agent_get_new_thread_with_context_provider(
    chat_client_base: ChatClientProtocol, tool_tool: ToolProtocol
):
    """Test that get_new_thread passes context_provider to the thread."""

    class TestContextProvider(ContextProvider):
        async def invoking(self, messages, **kwargs):
            return Context()

    provider = TestContextProvider()
    agent = ChatAgent(chat_client=chat_client_base, tools=[tool_tool], context_provider=provider)

    thread = agent.get_new_thread()

    assert thread is not None
    assert thread.context_provider is provider


@pytest.mark.asyncio
async def test_agent_get_new_thread_with_service_thread_id(
    chat_client_base: ChatClientProtocol, tool_tool: ToolProtocol
):
    """Test that get_new_thread passes kwargs like service_thread_id to the thread."""
    agent = ChatAgent(chat_client=chat_client_base, tools=[tool_tool])

    thread = agent.get_new_thread(service_thread_id="test-thread-123")

    assert thread is not None
    assert thread.service_thread_id == "test-thread-123"


@pytest.mark.asyncio
async def test_agent_deserialize_thread(chat_client_base: ChatClientProtocol, tool_tool: ToolProtocol):
    """Test deserialize_thread restores a thread from serialized state."""
    agent = ChatAgent(chat_client=chat_client_base, tools=[tool_tool])

    # Create serialized thread state with messages
    serialized_state = {
        "service_thread_id": None,
        "chat_message_store_state": {
            "messages": [{"role": "user", "text": "Hello"}],
        },
    }

    thread = await agent.deserialize_thread(serialized_state)

    assert thread is not None
    assert isinstance(thread, AgentThread)
    assert thread.message_store is not None
    messages = await thread.message_store.list_messages()
    assert len(messages) == 1
    assert messages[0].text == "Hello"


# endregion


# region Test ChatAgent initialization edge cases


@pytest.mark.asyncio
async def test_chat_agent_raises_with_both_conversation_id_and_store():
    """Test ChatAgent raises error with both conversation_id and chat_message_store_factory."""
    mock_client = MagicMock()
    mock_store_factory = MagicMock()

    with pytest.raises(AgentInitializationError, match="Cannot specify both"):
        ChatAgent(
            chat_client=mock_client,
            default_options={"conversation_id": "test_id"},
            chat_message_store_factory=mock_store_factory,
        )


def test_chat_agent_calls_update_agent_name_on_client():
    """Test that ChatAgent calls _update_agent_name_and_description on client if available."""
    mock_client = MagicMock()
    mock_client._update_agent_name_and_description = MagicMock()

    ChatAgent(
        chat_client=mock_client,
        name="TestAgent",
        description="Test description",
    )

    mock_client._update_agent_name_and_description.assert_called_once_with("TestAgent", "Test description")


@pytest.mark.asyncio
async def test_chat_agent_context_provider_adds_tools_when_agent_has_none(chat_client_base: ChatClientProtocol):
    """Test that context provider tools are used when agent has no default tools."""

    @tool
    def context_tool(text: str) -> str:
        """A tool provided by context."""
        return text

    class ToolContextProvider(ContextProvider):
        async def invoking(self, messages, **kwargs):
            return Context(tools=[context_tool])

    provider = ToolContextProvider()
    agent = ChatAgent(chat_client=chat_client_base, context_provider=provider)

    # Agent starts with empty tools list
    assert agent.default_options.get("tools") == []

    # Run the agent and verify context tools are added
    _, options, _ = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=None, input_messages=[ChatMessage(role=Role.USER, text="Hello")]
    )

    # The context tools should now be in the options
    assert options.get("tools") is not None
    assert len(options["tools"]) == 1


@pytest.mark.asyncio
async def test_chat_agent_context_provider_adds_instructions_when_agent_has_none(chat_client_base: ChatClientProtocol):
    """Test that context provider instructions are used when agent has no default instructions."""

    class InstructionContextProvider(ContextProvider):
        async def invoking(self, messages, **kwargs):
            return Context(instructions="Context-provided instructions")

    provider = InstructionContextProvider()
    agent = ChatAgent(chat_client=chat_client_base, context_provider=provider)

    # Verify agent has no default instructions
    assert agent.default_options.get("instructions") is None

    # Run the agent and verify context instructions are available
    _, options, _ = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=None, input_messages=[ChatMessage(role=Role.USER, text="Hello")]
    )

    # The context instructions should now be in the options
    assert options.get("instructions") == "Context-provided instructions"


@pytest.mark.asyncio
async def test_chat_agent_raises_on_conversation_id_mismatch(chat_client_base: ChatClientProtocol):
    """Test that ChatAgent raises when thread and agent have different conversation IDs."""
    agent = ChatAgent(
        chat_client=chat_client_base,
        default_options={"conversation_id": "agent-conversation-id"},
    )

    # Create a thread with a different service_thread_id
    thread = AgentThread(service_thread_id="different-thread-id")

    with pytest.raises(AgentExecutionException, match="conversation_id set on the agent is different"):
        await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
            thread=thread, input_messages=[ChatMessage(role=Role.USER, text="Hello")]
        )


# endregion
