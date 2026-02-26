# Copyright (c) Microsoft. All rights reserved.

import contextlib
from collections.abc import AsyncIterable, MutableSequence
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pytest import raises

from agent_framework import (
    Agent,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseContextProvider,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionTool,
    Message,
    SupportsAgentRun,
    SupportsChatGetResponse,
    tool,
)
from agent_framework._agents import _merge_options, _sanitize_agent_name
from agent_framework._mcp import MCPTool


def test_agent_session_type(agent_session: AgentSession) -> None:
    assert isinstance(agent_session, AgentSession)


def test_agent_type(agent: SupportsAgentRun) -> None:
    assert isinstance(agent, SupportsAgentRun)


async def test_agent_run(agent: SupportsAgentRun) -> None:
    response = await agent.run("test")
    assert response.messages[0].role == "assistant"
    assert response.messages[0].text == "Response"


async def test_agent_run_with_content(agent: SupportsAgentRun) -> None:
    response = await agent.run(Content.from_text("test"))
    assert response.messages[0].role == "assistant"
    assert response.messages[0].text == "Response"


async def test_agent_run_streaming(agent: SupportsAgentRun) -> None:
    async def collect_updates(updates: AsyncIterable[AgentResponseUpdate]) -> list[AgentResponseUpdate]:
        return [u async for u in updates]

    updates = await collect_updates(agent.run("test", stream=True))
    assert len(updates) == 1
    assert updates[0].text == "Response"


def test_chat_client_agent_type(client: SupportsChatGetResponse) -> None:
    chat_client_agent = Agent(client=client)
    assert isinstance(chat_client_agent, SupportsAgentRun)


async def test_chat_client_agent_init(client: SupportsChatGetResponse) -> None:
    agent_id = str(uuid4())
    agent = Agent(client=client, id=agent_id, description="Test")

    assert agent.id == agent_id
    assert agent.name is None
    assert agent.description == "Test"


async def test_chat_client_agent_init_with_name(client: SupportsChatGetResponse) -> None:
    agent_id = str(uuid4())
    agent = Agent(client=client, id=agent_id, name="Test Agent", description="Test")

    assert agent.id == agent_id
    assert agent.name == "Test Agent"
    assert agent.description == "Test"


async def test_chat_client_agent_run(client: SupportsChatGetResponse) -> None:
    agent = Agent(client=client)

    result = await agent.run("Hello")

    assert result.text == "test response"


async def test_chat_client_agent_run_streaming(client: SupportsChatGetResponse) -> None:
    agent = Agent(client=client)

    result = await AgentResponse.from_update_generator(agent.run("Hello", stream=True))

    assert result.text == "test streaming response another update"


async def test_chat_client_agent_streaming_response_format_from_default_options(
    client: SupportsChatGetResponse,
) -> None:
    """AgentResponse.value must be parsed when response_format is set in default_options and streaming."""
    from pydantic import BaseModel

    class Greeting(BaseModel):
        greeting: str

    json_text = '{"greeting": "Hello"}'
    client.streaming_responses.append(  # type: ignore[attr-defined]
        [ChatResponseUpdate(contents=[Content.from_text(json_text)], role="assistant", finish_reason="stop")]
    )

    agent = Agent(client=client, default_options={"response_format": Greeting})
    stream = agent.run("Hello", stream=True)
    async for _ in stream:
        pass
    result = await stream.get_final_response()

    assert result.text == json_text
    assert result.value is not None
    assert isinstance(result.value, Greeting)
    assert result.value.greeting == "Hello"


async def test_chat_client_agent_streaming_response_format_from_run_options(
    client: SupportsChatGetResponse,
) -> None:
    """AgentResponse.value must be parsed when response_format is passed via run() options kwarg."""
    from pydantic import BaseModel

    class Greeting(BaseModel):
        greeting: str

    json_text = '{"greeting": "Hi"}'
    client.streaming_responses.append(  # type: ignore[attr-defined]
        [ChatResponseUpdate(contents=[Content.from_text(json_text)], role="assistant", finish_reason="stop")]
    )

    agent = Agent(client=client)
    stream = agent.run("Hello", stream=True, options={"response_format": Greeting})
    async for _ in stream:
        pass
    result = await stream.get_final_response()

    assert result.text == json_text
    assert result.value is not None
    assert isinstance(result.value, Greeting)
    assert result.value.greeting == "Hi"


async def test_chat_client_agent_create_session(client: SupportsChatGetResponse) -> None:
    agent = Agent(client=client)
    session = agent.create_session()

    assert isinstance(session, AgentSession)


async def test_chat_client_agent_prepare_session_and_messages(client: SupportsChatGetResponse) -> None:
    from agent_framework._sessions import InMemoryHistoryProvider

    agent = Agent(client=client, context_providers=[InMemoryHistoryProvider()])
    message = Message(role="user", text="Hello")
    session = AgentSession()
    session.state[InMemoryHistoryProvider.DEFAULT_SOURCE_ID] = {"messages": [message]}

    session_context, _ = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", text="Test")],
    )
    result_messages = session_context.get_messages(include_input=True)

    assert len(result_messages) == 2
    assert result_messages[0].text == "Hello"
    assert result_messages[1].text == "Test"


async def test_prepare_session_does_not_mutate_agent_chat_options(client: SupportsChatGetResponse) -> None:
    tool = {"type": "code_interpreter"}
    agent = Agent(client=client, tools=[tool])

    assert agent.default_options.get("tools") is not None
    base_tools = agent.default_options["tools"]
    session = agent.create_session()

    _, prepared_chat_options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", text="Test")],
    )

    assert prepared_chat_options.get("tools") is not None
    assert base_tools is not prepared_chat_options["tools"]

    prepared_chat_options["tools"].append({"type": "code_interpreter"})  # type: ignore[arg-type]
    assert len(agent.default_options["tools"]) == 1


async def test_chat_client_agent_run_with_session(chat_client_base: SupportsChatGetResponse) -> None:
    mock_response = ChatResponse(
        messages=[Message(role="assistant", contents=[Content.from_text("test response")])],
        conversation_id="123",
    )
    chat_client_base.run_responses = [mock_response]
    agent = Agent(
        client=chat_client_base,
        tools={"type": "code_interpreter"},
    )
    session = agent.get_session(service_session_id="123")

    result = await agent.run("Hello", session=session)
    assert result.text == "test response"

    assert session.service_session_id == "123"


async def test_chat_client_agent_updates_existing_session_id_non_streaming(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[Message(role="assistant", contents=[Content.from_text("test response")])],
            conversation_id="resp_new_123",
        )
    ]

    agent = Agent(client=chat_client_base)
    session = agent.get_session(service_session_id="resp_old_123")

    await agent.run("Hello", session=session)
    assert session.service_session_id == "resp_new_123"


async def test_chat_client_agent_update_session_id_streaming_uses_conversation_id(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_text("stream part 1")],
                role="assistant",
                response_id="resp_stream_123",
                conversation_id="conv_stream_456",
            ),
            ChatResponseUpdate(
                contents=[Content.from_text(" stream part 2")],
                role="assistant",
                response_id="resp_stream_123",
                conversation_id="conv_stream_456",
                finish_reason="stop",
            ),
        ]
    ]

    agent = Agent(client=chat_client_base)
    session = agent.create_session()

    stream = agent.run("Hello", session=session, stream=True)
    async for _ in stream:
        pass
    result = await stream.get_final_response()
    assert result.text == "stream part 1 stream part 2"
    assert session.service_session_id == "conv_stream_456"


async def test_chat_client_agent_updates_existing_session_id_streaming(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_text("stream part 1")],
                role="assistant",
                response_id="resp_stream_123",
                conversation_id="resp_new_456",
            ),
            ChatResponseUpdate(
                contents=[Content.from_text(" stream part 2")],
                role="assistant",
                response_id="resp_stream_123",
                conversation_id="resp_new_456",
                finish_reason="stop",
            ),
        ]
    ]

    agent = Agent(client=chat_client_base)
    session = agent.get_session(service_session_id="resp_old_456")

    stream = agent.run("Hello", session=session, stream=True)
    async for _ in stream:
        pass
    await stream.get_final_response()
    assert session.service_session_id == "resp_new_456"


async def test_chat_client_agent_update_session_id_streaming_does_not_use_response_id(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_text("stream response without conversation id")],
                role="assistant",
                response_id="resp_only_123",
                finish_reason="stop",
            ),
        ]
    ]

    agent = Agent(client=chat_client_base)
    session = agent.create_session()

    stream = agent.run("Hello", session=session, stream=True)
    async for _ in stream:
        pass
    result = await stream.get_final_response()
    assert result.text == "stream response without conversation id"
    assert session.service_session_id is None


async def test_chat_client_agent_streaming_session_id_set_without_get_final_response(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Test that session.service_session_id is set during streaming iteration.

    This verifies the eager propagation of conversation_id via transform hook,
    which is needed for multi-turn flows (e.g. hosted MCP approval) where the
    user iterates the stream and then makes a follow-up call without calling
    get_final_response().
    """
    chat_client_base.streaming_responses = [
        [
            ChatResponseUpdate(
                contents=[Content.from_text("part 1")],
                role="assistant",
                response_id="resp_123",
                conversation_id="resp_123",
            ),
            ChatResponseUpdate(
                contents=[Content.from_text(" part 2")],
                role="assistant",
                response_id="resp_123",
                conversation_id="resp_123",
                finish_reason="stop",
            ),
        ]
    ]

    agent = Agent(client=chat_client_base)
    session = agent.create_session()
    assert session.service_session_id is None

    # Only iterate — do NOT call get_final_response()
    async for _ in agent.run("Hello", session=session, stream=True):
        pass

    assert session.service_session_id == "resp_123"


async def test_chat_client_agent_update_session_messages(client: SupportsChatGetResponse) -> None:
    from agent_framework._sessions import InMemoryHistoryProvider

    agent = Agent(client=client)
    session = agent.create_session()

    result = await agent.run("Hello", session=session)
    assert result.text == "test response"

    assert session.service_session_id is None

    chat_messages: list[Message] = session.state.get(InMemoryHistoryProvider.DEFAULT_SOURCE_ID, {}).get("messages", [])

    assert chat_messages is not None
    assert len(chat_messages) == 2
    assert chat_messages[0].text == "Hello"
    assert chat_messages[1].text == "test response"


async def test_chat_client_agent_update_session_conversation_id_missing(client: SupportsChatGetResponse) -> None:
    agent = Agent(client=client)
    session = agent.get_session(service_session_id="123")

    # With the session-based API, service_session_id is managed directly on the session
    assert session.service_session_id == "123"


async def test_chat_client_agent_default_author_name(client: SupportsChatGetResponse) -> None:
    # Name is not specified here, so default name should be used
    agent = Agent(client=client)

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "UnnamedAgent"


async def test_chat_client_agent_author_name_as_agent_name(client: SupportsChatGetResponse) -> None:
    # Name is specified here, so it should be used as author name
    agent = Agent(client=client, name="TestAgent")

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "TestAgent"


async def test_chat_client_agent_author_name_is_used_from_response(chat_client_base: SupportsChatGetResponse) -> None:
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[
                Message(role="assistant", contents=[Content.from_text("test response")], author_name="TestAuthor")
            ]
        )
    ]

    agent = Agent(client=chat_client_base, tools={"type": "code_interpreter"})

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "TestAuthor"


# Mock context provider for testing
class MockContextProvider(BaseContextProvider):
    def __init__(self, messages: list[Message] | None = None) -> None:
        super().__init__(source_id="mock")
        self.context_messages = messages
        self.before_run_called = False
        self.after_run_called = False
        self.new_messages: list[Message] = []
        self.last_service_session_id: str | None = None

    async def before_run(self, *, agent: Any, session: Any, context: Any, state: Any) -> None:
        self.before_run_called = True
        if self.context_messages:
            context.extend_messages(self, self.context_messages)

    async def after_run(self, *, agent: Any, session: Any, context: Any, state: Any) -> None:
        self.after_run_called = True
        if session:
            self.last_service_session_id = session.service_session_id
        if context.response:
            self.new_messages.extend(context.input_messages)
            self.new_messages.extend(context.response.messages)


async def test_chat_agent_context_providers_model_before_run(client: SupportsChatGetResponse) -> None:
    """Test that context providers' before_run is called during agent run."""
    mock_provider = MockContextProvider(messages=[Message(role="system", text="Test context instructions")])
    agent = Agent(client=client, context_providers=[mock_provider])

    await agent.run("Hello")

    assert mock_provider.before_run_called


async def test_chat_agent_context_providers_after_run(chat_client_base: SupportsChatGetResponse) -> None:
    """Test that context providers' after_run is called during agent run."""
    mock_provider = MockContextProvider()
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[Message(role="assistant", contents=[Content.from_text("test response")])],
            conversation_id="test-thread-id",
        )
    ]

    agent = Agent(client=chat_client_base, context_providers=[mock_provider])

    session = agent.get_session(service_session_id="test-thread-id")
    await agent.run("Hello", session=session)

    assert mock_provider.after_run_called
    assert mock_provider.last_service_session_id == "test-thread-id"


async def test_chat_agent_context_providers_messages_adding(client: SupportsChatGetResponse) -> None:
    """Test that context providers' after_run is called during agent run."""
    mock_provider = MockContextProvider()
    agent = Agent(client=client, context_providers=[mock_provider])

    await agent.run("Hello")

    assert mock_provider.after_run_called
    # Should be called with both input and response messages
    assert len(mock_provider.new_messages) >= 2


async def test_chat_agent_context_instructions_in_messages(client: SupportsChatGetResponse) -> None:
    """Test that AI context instructions are included in messages."""
    mock_provider = MockContextProvider(messages=[Message(role="system", text="Context-specific instructions")])
    agent = Agent(client=client, instructions="Agent instructions", context_providers=[mock_provider])

    # We need to test the _prepare_session_and_messages method directly
    session_context, _ = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=None, input_messages=[Message(role="user", text="Hello")]
    )
    messages = session_context.get_messages(include_input=True)

    # Should have context instructions, and user message
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[0].text == "Context-specific instructions"
    assert messages[1].role == "user"
    assert messages[1].text == "Hello"
    # instructions system message is added by a client


async def test_chat_agent_no_context_instructions(client: SupportsChatGetResponse) -> None:
    """Test behavior when AI context has no instructions."""
    mock_provider = MockContextProvider()
    agent = Agent(client=client, instructions="Agent instructions", context_providers=[mock_provider])

    session_context, _ = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=None, input_messages=[Message(role="user", text="Hello")]
    )
    messages = session_context.get_messages(include_input=True)

    # Should have agent instructions and user message only
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].text == "Hello"


async def test_chat_agent_run_stream_context_providers(client: SupportsChatGetResponse) -> None:
    """Test that context providers work with run method."""
    mock_provider = MockContextProvider(messages=[Message(role="system", text="Stream context instructions")])
    agent = Agent(client=client, context_providers=[mock_provider])

    # Collect all stream updates and get final response
    stream = agent.run("Hello", stream=True)
    updates: list[AgentResponseUpdate] = []
    async for update in stream:
        updates.append(update)
    # Get final response to trigger post-processing hooks (including context provider notification)
    await stream.get_final_response()

    # Verify context provider was called
    assert mock_provider.before_run_called
    assert mock_provider.after_run_called


async def test_chat_agent_context_providers_with_service_session_id(chat_client_base: SupportsChatGetResponse) -> None:
    """Test context providers with service-managed session."""
    mock_provider = MockContextProvider()
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[Message(role="assistant", contents=[Content.from_text("test response")])],
            conversation_id="service-thread-123",
        )
    ]

    agent = Agent(client=chat_client_base, context_providers=[mock_provider])

    # Use existing service-managed session
    session = agent.get_session(service_session_id="existing-thread-id")
    await agent.run("Hello", session=session)

    # after_run should be called
    assert mock_provider.after_run_called


# Tests for as_tool method
async def test_chat_agent_as_tool_basic(client: SupportsChatGetResponse) -> None:
    """Test basic as_tool functionality."""
    agent = Agent(client=client, name="TestAgent", description="Test agent for as_tool")

    tool = agent.as_tool()

    assert tool.name == "TestAgent"
    assert tool.description == "Test agent for as_tool"
    assert hasattr(tool, "func")
    assert hasattr(tool, "input_model")


async def test_chat_agent_as_tool_custom_parameters(client: SupportsChatGetResponse) -> None:
    """Test as_tool with custom parameters."""
    agent = Agent(client=client, name="TestAgent", description="Original description")

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


async def test_chat_agent_as_tool_defaults(client: SupportsChatGetResponse) -> None:
    """Test as_tool with default parameters."""
    agent = Agent(
        client=client,
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


async def test_chat_agent_as_tool_no_name(client: SupportsChatGetResponse) -> None:
    """Test as_tool when agent has no name (should raise ValueError)."""
    agent = Agent(client=client)  # No name provided

    # Should raise ValueError since agent has no name
    with raises(ValueError, match="Agent tool name cannot be None"):
        agent.as_tool()


async def test_chat_agent_as_tool_function_execution(client: SupportsChatGetResponse) -> None:
    """Test that the generated FunctionTool can be executed."""
    agent = Agent(client=client, name="TestAgent", description="Test agent")

    tool = agent.as_tool()

    # Test function execution
    result = await tool.invoke(arguments=tool.input_model(task="Hello"))

    # Should return the agent's response text
    assert isinstance(result, str)
    assert result == "test response"  # From mock chat client


async def test_chat_agent_as_tool_with_stream_callback(client: SupportsChatGetResponse) -> None:
    """Test as_tool with stream callback functionality."""
    agent = Agent(client=client, name="StreamingAgent")

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


async def test_chat_agent_as_tool_with_custom_arg_name(client: SupportsChatGetResponse) -> None:
    """Test as_tool with custom argument name."""
    agent = Agent(client=client, name="CustomArgAgent")

    tool = agent.as_tool(arg_name="prompt", arg_description="Custom prompt input")

    # Test that the custom argument name works
    result = await tool.invoke(arguments=tool.input_model(prompt="Test prompt"))
    assert result == "test response"


async def test_chat_agent_as_tool_with_async_stream_callback(client: SupportsChatGetResponse) -> None:
    """Test as_tool with async stream callback functionality."""
    agent = Agent(client=client, name="AsyncStreamingAgent")

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


async def test_chat_agent_as_tool_name_sanitization(client: SupportsChatGetResponse) -> None:
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
        agent = Agent(client=client, name=agent_name, description="Test agent")
        tool = agent.as_tool()
        assert tool.name == expected_tool_name, f"Expected {expected_tool_name}, got {tool.name} for input {agent_name}"


async def test_chat_agent_as_mcp_server_basic(client: SupportsChatGetResponse) -> None:
    """Test basic as_mcp_server functionality."""
    agent = Agent(client=client, name="TestAgent", description="Test agent for MCP")

    # Create MCP server with default parameters
    server = agent.as_mcp_server()

    # Verify server is created
    assert server is not None
    assert hasattr(server, "name")
    assert hasattr(server, "version")


async def test_chat_agent_run_with_mcp_tools(client: SupportsChatGetResponse) -> None:
    """Test run method with MCP tools to cover MCP tool handling code."""
    agent = Agent(client=client, name="TestAgent", description="Test agent")

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


async def test_chat_agent_with_local_mcp_tools(client: SupportsChatGetResponse) -> None:
    """Test agent initialization with local MCP tools."""
    # Create a mock MCP tool
    mock_mcp_tool = MagicMock(spec=MCPTool)
    mock_mcp_tool.is_connected = False
    mock_mcp_tool.__aenter__ = AsyncMock(return_value=mock_mcp_tool)
    mock_mcp_tool.__aexit__ = AsyncMock(return_value=None)

    # Test agent with MCP tools in constructor
    with contextlib.suppress(Exception):
        agent = Agent(client=client, name="TestAgent", description="Test agent", tools=[mock_mcp_tool])
        # Test async context manager with MCP tools
        async with agent:
            pass


async def test_agent_tool_receives_session_in_kwargs(chat_client_base: Any) -> None:
    """Verify tool execution receives 'session' inside **kwargs when function is called by client."""

    captured: dict[str, Any] = {}

    @tool(name="echo_session_info", approval_mode="never_require")
    def echo_session_info(text: str, **kwargs: Any) -> str:  # type: ignore[reportUnknownParameterType]
        session = kwargs.get("session")
        captured["has_session"] = session is not None
        captured["has_state"] = session.state is not None if isinstance(session, AgentSession) else False
        return f"echo: {text}"

    # Make the base client emit a function call for our tool
    chat_client_base.run_responses = [
        ChatResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_function_call(call_id="1", name="echo_session_info", arguments='{"text": "hello"}')
                ],
            )
        ),
        ChatResponse(messages=Message(role="assistant", text="done")),
    ]

    agent = Agent(client=chat_client_base, tools=[echo_session_info])
    session = agent.create_session()

    result = await agent.run("hello", session=session, options={"additional_function_arguments": {"session": session}})

    assert result.text == "done"
    assert captured.get("has_session") is True
    assert captured.get("has_state") is True


async def test_chat_agent_tool_choice_run_level_overrides_agent_level(chat_client_base: Any, tool_tool: Any) -> None:
    """Verify that tool_choice passed to run() overrides agent-level tool_choice."""

    captured_options: list[dict[str, Any]] = []

    # Store the original inner method
    original_inner = chat_client_base._inner_get_response

    async def capturing_inner(
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(options)
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    # Create agent with agent-level tool_choice="auto" and a tool (tools required for tool_choice to be meaningful)
    agent = Agent(
        client=chat_client_base,
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
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(options)
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    # Create agent with agent-level tool_choice="required" and a tool
    agent = Agent(
        client=chat_client_base,
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
        *, messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> ChatResponse:
        captured_options.append(options)
        return await original_inner(messages=messages, options=options, **kwargs)

    chat_client_base._inner_get_response = capturing_inner

    # Create agent with agent-level tool_choice="auto" and a tool
    agent = Agent(
        client=chat_client_base,
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


# region Test SupportsAgentRun.create_session


@pytest.mark.asyncio
async def test_agent_create_session(chat_client_base: SupportsChatGetResponse, tool_tool: FunctionTool):
    """Test that create_session returns a new AgentSession."""
    agent = Agent(client=chat_client_base, tools=[tool_tool])

    session = agent.create_session()

    assert session is not None
    assert isinstance(session, AgentSession)


@pytest.mark.asyncio
async def test_agent_create_session_with_context_providers(
    chat_client_base: SupportsChatGetResponse, tool_tool: FunctionTool
):
    """Test that create_session works when context_providers are set on the agent."""

    class TestContextProvider(BaseContextProvider):
        def __init__(self):
            super().__init__(source_id="test")

    provider = TestContextProvider()
    agent = Agent(client=chat_client_base, tools=[tool_tool], context_providers=[provider])

    session = agent.create_session()

    assert session is not None
    assert agent.context_providers[0] is provider


@pytest.mark.asyncio
async def test_agent_get_session_with_service_session_id(
    chat_client_base: SupportsChatGetResponse, tool_tool: FunctionTool
):
    """Test that get_session creates a session with service_session_id."""
    agent = Agent(client=chat_client_base, tools=[tool_tool])

    session = agent.get_session(service_session_id="test-thread-123")

    assert session is not None
    assert session.service_session_id == "test-thread-123"


def test_agent_session_from_dict(chat_client_base: SupportsChatGetResponse, tool_tool: FunctionTool):
    """Test AgentSession.from_dict restores a session from serialized state."""
    # Create serialized session state
    serialized_state = {
        "type": "session",
        "session_id": "test-session",
        "service_session_id": None,
        "state": {},
    }

    session = AgentSession.from_dict(serialized_state)

    assert session is not None
    assert isinstance(session, AgentSession)
    assert session.session_id == "test-session"


# endregion


# region Test Agent initialization edge cases


def test_chat_agent_calls_update_agent_name_on_client():
    """Test that Agent calls _update_agent_name_and_description on client if available."""
    mock_client = MagicMock()
    mock_client._update_agent_name_and_description = MagicMock()

    Agent(
        client=mock_client,
        name="TestAgent",
        description="Test description",
    )

    assert mock_client._update_agent_name_and_description.call_count == 1
    mock_client._update_agent_name_and_description.assert_called_with("TestAgent", "Test description")


@pytest.mark.asyncio
async def test_chat_agent_context_provider_adds_tools_when_agent_has_none(chat_client_base: SupportsChatGetResponse):
    """Test that context provider tools are used when agent has no default tools."""

    @tool
    def context_tool(text: str) -> str:
        """A tool provided by context."""
        return text

    class ToolContextProvider(BaseContextProvider):
        def __init__(self):
            super().__init__(source_id="tool-context")

        async def before_run(self, *, agent, session, context, state):
            context.extend_tools("tool-context", [context_tool])

    provider = ToolContextProvider()
    agent = Agent(client=chat_client_base, context_providers=[provider])

    # Agent starts with empty tools list
    assert agent.default_options.get("tools") == []

    # Run the agent and verify context tools are added
    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=None, input_messages=[Message(role="user", text="Hello")]
    )

    # The context tools should now be in the options
    assert options.get("tools") is not None
    assert len(options["tools"]) == 1


@pytest.mark.asyncio
async def test_chat_agent_context_provider_adds_instructions_when_agent_has_none(
    chat_client_base: SupportsChatGetResponse,
):
    """Test that context provider instructions are used when agent has no default instructions."""

    class InstructionContextProvider(BaseContextProvider):
        def __init__(self):
            super().__init__(source_id="instruction-context")

        async def before_run(self, *, agent, session, context, state):
            context.extend_instructions("instruction-context", "Context-provided instructions")

    provider = InstructionContextProvider()
    agent = Agent(client=chat_client_base, context_providers=[provider])

    # Verify agent has no default instructions
    assert agent.default_options.get("instructions") is None

    # Run the agent and verify context instructions are available
    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=None, input_messages=[Message(role="user", text="Hello")]
    )

    # The context instructions should now be in the options
    assert options.get("instructions") == "Context-provided instructions"


# region STORES_BY_DEFAULT tests


async def test_stores_by_default_skips_inmemory_injection(client: SupportsChatGetResponse) -> None:
    """Client with STORES_BY_DEFAULT=True should not auto-inject InMemoryHistoryProvider."""
    from agent_framework._sessions import InMemoryHistoryProvider

    # Simulate a client that stores by default
    client.STORES_BY_DEFAULT = True  # type: ignore[attr-defined]

    agent = Agent(client=client)
    session = agent.create_session()

    await agent.run("Hello", session=session)

    # No InMemoryHistoryProvider should have been injected
    assert not any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)


async def test_stores_by_default_false_injects_inmemory(client: SupportsChatGetResponse) -> None:
    """Client with STORES_BY_DEFAULT=False (default) should auto-inject InMemoryHistoryProvider."""
    from agent_framework._sessions import InMemoryHistoryProvider

    agent = Agent(client=client)
    session = agent.create_session()

    await agent.run("Hello", session=session)

    # InMemoryHistoryProvider should have been injected
    assert any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)


async def test_stores_by_default_with_store_false_injects_inmemory(client: SupportsChatGetResponse) -> None:
    """Client with STORES_BY_DEFAULT=True but store=False should still inject InMemoryHistoryProvider."""
    from agent_framework._sessions import InMemoryHistoryProvider

    client.STORES_BY_DEFAULT = True  # type: ignore[attr-defined]

    agent = Agent(client=client)
    session = agent.create_session()

    await agent.run("Hello", session=session, options={"store": False})

    # User explicitly disabled server storage, so InMemoryHistoryProvider should be injected
    assert any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)


# endregion


# endregion
