# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, MutableSequence, Sequence
from uuid import uuid4

from pytest import raises

from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatMessageList,
    ChatResponse,
    Contents,
    HostedCodeInterpreterTool,
    Role,
    TextContent,
)
from agent_framework._memory import AggregateContextProvider, Context, ContextProvider
from agent_framework.exceptions import AgentExecutionException


def test_agent_thread_type(agent_thread: AgentThread) -> None:
    assert isinstance(agent_thread, AgentThread)


def test_agent_type(agent: AgentProtocol) -> None:
    assert isinstance(agent, AgentProtocol)


async def test_agent_run(agent: AgentProtocol) -> None:
    response = await agent.run("test")
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[0].text == "Response"


async def test_agent_run_streaming(agent: AgentProtocol) -> None:
    async def collect_updates(updates: AsyncIterable[AgentRunResponseUpdate]) -> list[AgentRunResponseUpdate]:
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
    assert agent.display_name == agent_id  # Display name defaults to id if name is None


async def test_chat_client_agent_init_with_name(chat_client: ChatClientProtocol) -> None:
    agent_id = str(uuid4())
    agent = ChatAgent(chat_client=chat_client, id=agent_id, name="Test Agent", description="Test")

    assert agent.id == agent_id
    assert agent.name == "Test Agent"
    assert agent.description == "Test"
    assert agent.display_name == "Test Agent"  # Display name is the name if present


async def test_chat_client_agent_run(chat_client: ChatClientProtocol) -> None:
    agent = ChatAgent(chat_client=chat_client)

    result = await agent.run("Hello")

    assert result.text == "test response"


async def test_chat_client_agent_run_streaming(chat_client: ChatClientProtocol) -> None:
    agent = ChatAgent(chat_client=chat_client)

    result = await AgentRunResponse.from_agent_response_generator(agent.run_stream("Hello"))

    assert result.text == "test streaming response another update"


async def test_chat_client_agent_get_new_thread(chat_client: ChatClientProtocol) -> None:
    agent = ChatAgent(chat_client=chat_client)
    thread = agent.get_new_thread()

    assert isinstance(thread, AgentThread)


async def test_chat_client_agent_prepare_thread_and_messages(chat_client: ChatClientProtocol) -> None:
    agent = ChatAgent(chat_client=chat_client)
    message = ChatMessage(role=Role.USER, text="Hello")
    thread = AgentThread(message_store=ChatMessageList(messages=[message]))

    _, result_messages = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=thread,
        context=Context(),
        input_messages=[ChatMessage(role=Role.USER, text="Test")],
    )

    assert len(result_messages) == 2
    assert result_messages[0] == message
    assert result_messages[1].text == "Test"


async def test_chat_client_agent_update_thread_id(chat_client_base: ChatClientProtocol) -> None:
    mock_response = ChatResponse(
        messages=[ChatMessage(role=Role.ASSISTANT, contents=[TextContent("test response")])],
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
        agent._update_thread_with_type_and_conversation_id(thread, None)  # type: ignore[reportPrivateUsage]


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
                ChatMessage(role=Role.ASSISTANT, contents=[TextContent("test response")], author_name="TestAuthor")
            ]
        )
    ]

    agent = ChatAgent(chat_client=chat_client_base, tools=HostedCodeInterpreterTool())

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "TestAuthor"


# Mock context provider for testing
class MockContextProvider(ContextProvider):
    context_contents: list[Contents] | None = None
    thread_created_called: bool = False
    messages_adding_called: bool = False
    model_invoking_called: bool = False
    thread_created_thread_id: str | None = None
    messages_adding_thread_id: str | None = None
    new_messages: list[ChatMessage] = []

    def __init__(self, contents: list[Contents] | None = None) -> None:
        super().__init__()
        self.context_contents = contents
        self.thread_created_called = False
        self.messages_adding_called = False
        self.model_invoking_called = False
        self.thread_created_thread_id = None
        self.messages_adding_thread_id = None
        self.new_messages = []

    async def thread_created(self, thread_id: str | None) -> None:
        self.thread_created_called = True
        self.thread_created_thread_id = thread_id

    async def messages_adding(self, thread_id: str | None, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        self.messages_adding_called = True
        self.messages_adding_thread_id = thread_id
        if isinstance(new_messages, ChatMessage):
            self.new_messages.append(new_messages)
        else:
            self.new_messages.extend(new_messages)

    async def model_invoking(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> Context:
        self.model_invoking_called = True
        return Context(contents=self.context_contents)


async def test_chat_agent_context_providers_model_invoking(chat_client: ChatClientProtocol) -> None:
    """Test that context providers' model_invoking is called during agent run."""
    mock_provider = MockContextProvider(contents=[TextContent("Test context instructions")])
    agent = ChatAgent(chat_client=chat_client, context_providers=mock_provider)

    await agent.run("Hello")

    assert mock_provider.model_invoking_called


async def test_chat_agent_context_providers_thread_created(chat_client_base: ChatClientProtocol) -> None:
    """Test that context providers' thread_created is called during agent run."""
    mock_provider = MockContextProvider()
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, contents=[TextContent("test response")])],
            conversation_id="test-thread-id",
        )
    ]

    agent = ChatAgent(chat_client=chat_client_base, context_providers=mock_provider)

    await agent.run("Hello")

    assert mock_provider.thread_created_called
    assert mock_provider.thread_created_thread_id == "test-thread-id"


async def test_chat_agent_context_providers_messages_adding(chat_client: ChatClientProtocol) -> None:
    """Test that context providers' messages_adding is called during agent run."""
    mock_provider = MockContextProvider()
    agent = ChatAgent(chat_client=chat_client, context_providers=mock_provider)

    await agent.run("Hello")

    assert mock_provider.messages_adding_called
    # Should be called with both input and response messages
    assert len(mock_provider.new_messages) >= 2


async def test_chat_agent_context_instructions_in_messages(chat_client: ChatClientProtocol) -> None:
    """Test that AI context instructions are included in messages."""
    mock_provider = MockContextProvider(contents=[TextContent("Context-specific instructions")])
    agent = ChatAgent(chat_client=chat_client, instructions="Agent instructions", context_providers=mock_provider)

    # We need to test the _prepare_thread_and_messages method directly
    context = Context(contents=[TextContent("Context-specific instructions")])
    _, messages = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=None, context=context, input_messages=[ChatMessage(role=Role.USER, text="Hello")]
    )

    # Should have agent instructions, context instructions, and user message
    assert len(messages) == 3
    assert messages[0].role == Role.SYSTEM
    assert messages[0].text == "Agent instructions"
    assert messages[1].role == Role.SYSTEM
    assert messages[1].text == "Context-specific instructions"
    assert messages[2].role == Role.USER
    assert messages[2].text == "Hello"


async def test_chat_agent_context_instructions_without_agent_instructions(chat_client: ChatClientProtocol) -> None:
    """Test that AI context instructions work when agent has no instructions."""
    agent = ChatAgent(chat_client=chat_client)  # No instructions
    context = Context(contents=[TextContent("Context-only instructions")])

    _, messages = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=None, context=context, input_messages=[ChatMessage(role=Role.USER, text="Hello")]
    )

    # Should have context instructions and user message only
    assert len(messages) == 2
    assert messages[0].role == Role.SYSTEM
    assert messages[0].text == "Context-only instructions"
    assert messages[1].role == Role.USER
    assert messages[1].text == "Hello"


async def test_chat_agent_no_context_instructions(chat_client: ChatClientProtocol) -> None:
    """Test behavior when AI context has no instructions."""
    agent = ChatAgent(chat_client=chat_client, instructions="Agent instructions")
    context = Context()  # No instructions

    _, messages = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=None, context=context, input_messages=[ChatMessage(role=Role.USER, text="Hello")]
    )

    # Should have agent instructions and user message only
    assert len(messages) == 2
    assert messages[0].role == Role.SYSTEM
    assert messages[0].text == "Agent instructions"
    assert messages[1].role == Role.USER
    assert messages[1].text == "Hello"


async def test_chat_agent_run_stream_context_providers(chat_client: ChatClientProtocol) -> None:
    """Test that context providers work with run_stream method."""
    mock_provider = MockContextProvider(contents=[TextContent("Stream context instructions")])
    agent = ChatAgent(chat_client=chat_client, context_providers=mock_provider)

    # Collect all stream updates
    updates: list[AgentRunResponseUpdate] = []
    async for update in agent.run_stream("Hello"):
        updates.append(update)

    # Verify context provider was called
    assert mock_provider.model_invoking_called
    assert mock_provider.thread_created_called
    assert mock_provider.messages_adding_called


async def test_chat_agent_multiple_context_providers(chat_client: ChatClientProtocol) -> None:
    """Test that multiple context providers work together."""
    provider1 = MockContextProvider(contents=[TextContent("First provider instructions")])
    provider2 = MockContextProvider(contents=[TextContent("Second provider instructions")])

    agent = ChatAgent(chat_client=chat_client, context_providers=[provider1, provider2])

    await agent.run("Hello")

    # Both providers should be called
    assert provider1.model_invoking_called
    assert provider1.thread_created_called
    assert provider1.messages_adding_called

    assert provider2.model_invoking_called
    assert provider2.thread_created_called
    assert provider2.messages_adding_called


async def test_chat_agent_aggregate_context_provider_combines_instructions() -> None:
    """Test that AggregateContextProvider combines instructions from multiple providers."""
    provider1 = MockContextProvider(contents=[TextContent("First instruction")])
    provider2 = MockContextProvider(contents=[TextContent("Second instruction")])

    aggregate = AggregateContextProvider()
    aggregate.providers.append(provider1)
    aggregate.providers.append(provider2)

    # Test model_invoking combines instructions
    result = await aggregate.model_invoking([ChatMessage(role=Role.USER, text="Test")])

    assert result.contents
    assert isinstance(result.contents[0], TextContent)
    assert isinstance(result.contents[1], TextContent)
    assert result.contents[0].text == "First instruction"
    assert result.contents[1].text == "Second instruction"


async def test_chat_agent_context_providers_with_thread_service_id(chat_client_base: ChatClientProtocol) -> None:
    """Test context providers with service-managed thread."""
    mock_provider = MockContextProvider()
    chat_client_base.run_responses = [
        ChatResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, contents=[TextContent("test response")])],
            conversation_id="service-thread-123",
        )
    ]

    agent = ChatAgent(chat_client=chat_client_base, context_providers=mock_provider)

    # Use existing service-managed thread
    thread = AgentThread(service_thread_id="existing-thread-id")
    await agent.run("Hello", thread=thread)

    # messages_adding should be called with the service thread ID from response
    assert mock_provider.messages_adding_called
    assert mock_provider.messages_adding_thread_id == "service-thread-123"  # Updated thread ID from response


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
    """Test that the generated AIFunction can be executed."""
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
    collected_updates: list[AgentRunResponseUpdate] = []

    def stream_callback(update: AgentRunResponseUpdate) -> None:
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
    collected_updates: list[AgentRunResponseUpdate] = []

    async def async_stream_callback(update: AgentRunResponseUpdate) -> None:
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
