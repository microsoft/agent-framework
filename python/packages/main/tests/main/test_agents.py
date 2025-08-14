# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, MutableSequence, Sequence
from typing import Any
from uuid import uuid4

from pytest import fixture, raises

from agent_framework import (
    Agent,
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    AgentThreadType,
    ChatClient,
    ChatClientBase,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    TextContent,
)
from agent_framework.exceptions import AgentExecutionException


# Mock AgentThread implementation for testing
class MockAgentThread(AgentThread):
    async def _on_new_messages(self, new_messages: ChatMessage | Sequence[ChatMessage]) -> None:
        pass


# Mock Agent implementation for testing
class MockAgent(AgentProtocol):
    @property
    def id(self) -> str:
        return str(uuid4())

    @property
    def name(self) -> str | None:
        """Returns the name of the agent."""
        return "Name"

    @property
    def display_name(self) -> str:
        """Returns the name of the agent."""
        return "Display Name"

    @property
    def description(self) -> str | None:
        return "Description"

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        return AgentRunResponse(messages=[ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent("Response")])])

    async def run_streaming(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        yield AgentRunResponseUpdate(contents=[TextContent("Response")])

    def get_new_thread(self) -> AgentThread:
        return MockAgentThread()


# Mock ChatClient implementation for testing
class MockChatClient(ChatClientBase):
    _mock_response: ChatResponse | None = None

    def __init__(self, mock_response: ChatResponse | None = None) -> None:
        self._mock_response = mock_response

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        return (
            self._mock_response
            if self._mock_response
            else ChatResponse(messages=ChatMessage(role=ChatRole.ASSISTANT, text="test response"))
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(role=ChatRole.ASSISTANT, text=TextContent(text="test streaming response"))


@fixture
def agent_thread() -> AgentThread:
    return MockAgentThread()


@fixture
def agent() -> AgentProtocol:
    return MockAgent()


@fixture
def chat_client() -> ChatClientBase:
    return MockChatClient()


def test_agent_thread_type(agent_thread: AgentThread) -> None:
    assert isinstance(agent_thread, AgentThread)


def test_agent_type(agent: AgentProtocol) -> None:
    assert isinstance(agent, AgentProtocol)


async def test_agent_run(agent: AgentProtocol) -> None:
    response = await agent.run("test")
    assert response.messages[0].role == ChatRole.ASSISTANT
    assert response.messages[0].text == "Response"


async def test_agent_run_streaming(agent: AgentProtocol) -> None:
    async def collect_updates(updates: AsyncIterable[AgentRunResponseUpdate]) -> list[AgentRunResponseUpdate]:
        return [u async for u in updates]

    updates = await collect_updates(agent.run_streaming(messages="test"))
    assert len(updates) == 1
    assert updates[0].text == "Response"


async def test_chat_client_agent_thread_init_in_memory() -> None:
    messages = [ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])]
    thread = AgentThread(messages=messages)

    assert thread.storage_location == AgentThreadType.IN_MEMORY_MESSAGES
    assert thread.id is None
    assert thread.chat_messages == messages


async def test_chat_client_agent_thread_empty() -> None:
    thread = AgentThread()

    assert thread.storage_location is None
    assert thread.id is None
    assert thread.chat_messages is None


async def test_chat_client_agent_thread_init_invalid() -> None:
    with raises(ValueError, match="Cannot specify both id and messages"):
        AgentThread(id="123", messages=[ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])])

    with raises(ValueError, match="ID cannot be empty or whitespace"):
        AgentThread(id=" ")


async def test_chat_client_agent_thread_init_conversation_id() -> None:
    thread_id = str(uuid4())
    thread = AgentThread(id=thread_id)

    assert thread.storage_location == AgentThreadType.CONVERSATION_ID
    assert thread.id == thread_id
    assert thread.chat_messages is None


async def test_chat_client_agent_thread_get_messages() -> None:
    messages = [ChatMessage(role=ChatRole.USER, contents=[TextContent("Hello")])]
    thread = AgentThread(messages=messages)

    result = [msg async for msg in thread.get_messages()]
    assert result == messages


async def test_chat_client_agent_thread_on_new_messages_in_memory() -> None:
    initial_message = ChatMessage(role=ChatRole.USER, contents=[TextContent("Initial message")])
    new_message = ChatMessage(role=ChatRole.USER, contents=[TextContent("New message")])

    thread = AgentThread(messages=[initial_message])

    await thread._on_new_messages(new_message)  # type: ignore[reportPrivateUsage]
    assert thread.chat_messages == [initial_message, new_message]


def test_chat_client_agent_type(chat_client: ChatClient) -> None:
    chat_client_agent = Agent(chat_client=chat_client)
    assert isinstance(chat_client_agent, AgentProtocol)


async def test_chat_client_agent_init(chat_client: ChatClient) -> None:
    agent_id = str(uuid4())
    agent = Agent(chat_client=chat_client, id=agent_id, description="Test")

    assert agent.id == agent_id
    assert agent.name is None
    assert agent.description == "Test"
    assert agent.display_name == agent_id  # Display name defaults to id if name is None


async def test_chat_client_agent_init_with_name(chat_client: ChatClient) -> None:
    agent_id = str(uuid4())
    agent = Agent(chat_client=chat_client, id=agent_id, name="Test Agent", description="Test")

    assert agent.id == agent_id
    assert agent.name == "Test Agent"
    assert agent.description == "Test"
    assert agent.display_name == "Test Agent"  # Display name is the name if present


async def test_chat_client_agent_run(chat_client: ChatClient) -> None:
    agent = Agent(chat_client=chat_client)

    result = await agent.run("Hello")

    assert result.text == "test response"


async def test_chat_client_agent_run_streaming(chat_client: ChatClient) -> None:
    agent = Agent(chat_client=chat_client)

    result = await AgentRunResponse.from_agent_response_generator(agent.run_streaming("Hello"))

    assert result.text == "test streaming response"


async def test_chat_client_agent_get_new_thread(chat_client: ChatClient) -> None:
    agent = Agent(chat_client=chat_client)
    thread = agent.get_new_thread()

    assert isinstance(thread, AgentThread)
    assert thread.storage_location is None


async def test_chat_client_agent_prepare_thread_and_messages(chat_client: ChatClient) -> None:
    agent = Agent(chat_client=chat_client)
    message = ChatMessage(role=ChatRole.USER, text="Hello")
    thread = AgentThread(messages=[message])

    result_thread = agent._validate_or_create_thread_type(  # type: ignore[reportPrivateUsage]
        thread, lambda: AgentThread(), expected_type=AgentThread
    )  # type: ignore[reportPrivateUsage]

    assert result_thread == thread
    assert isinstance(result_thread, AgentThread)

    _, result_messages = await agent._prepare_thread_and_messages(  # type: ignore[reportPrivateUsage]
        thread=result_thread,
        input_messages=[ChatMessage(role=ChatRole.USER, text="Test")],
    )

    assert len(result_messages) == 2
    assert result_messages[0] == message
    assert result_messages[1].text == "Test"


async def test_chat_client_agent_validate_or_create_thread(chat_client: ChatClient) -> None:
    agent = Agent(chat_client=chat_client)
    thread = None

    result_thread = agent._validate_or_create_thread_type(  # type: ignore[reportPrivateUsage]
        thread, lambda: AgentThread(), expected_type=AgentThread
    )  # type: ignore[reportPrivateUsage]

    assert result_thread != thread
    assert isinstance(result_thread, AgentThread)


async def test_chat_client_agent_update_thread_id() -> None:
    chat_client = MockChatClient(
        mock_response=ChatResponse(
            messages=[ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent("test response")])],
            conversation_id="123",
        )
    )
    agent = Agent(chat_client=chat_client)
    thread = agent.get_new_thread()

    result = await agent.run("Hello", thread=thread)
    assert result.text == "test response"

    assert thread.id == "123"
    assert isinstance(thread, AgentThread)
    assert thread.storage_location == AgentThreadType.CONVERSATION_ID


async def test_chat_client_agent_update_thread_messages(chat_client: ChatClient) -> None:
    agent = Agent(chat_client=chat_client)
    thread = agent.get_new_thread()

    result = await agent.run("Hello", thread=thread)
    assert result.text == "test response"

    assert thread.id is None
    assert isinstance(thread, AgentThread)
    assert thread.storage_location == AgentThreadType.IN_MEMORY_MESSAGES

    assert thread.chat_messages is not None
    assert len(thread.chat_messages) == 2
    assert thread.chat_messages[0].text == "Hello"
    assert thread.chat_messages[1].text == "test response"


async def test_chat_client_agent_update_thread_conversation_id_missing(chat_client: ChatClient) -> None:
    agent = Agent(chat_client=chat_client)
    thread = AgentThread(id="123")

    with raises(AgentExecutionException, match="Service did not return a valid conversation id"):
        agent._update_thread_with_type_and_conversation_id(thread, None)  # type: ignore[reportPrivateUsage]


async def test_chat_client_agent_default_author_name(chat_client: ChatClient) -> None:
    # Name is not specified here, so default name should be used
    agent = Agent(chat_client=chat_client)

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "UnnamedAgent"


async def test_chat_client_agent_author_name_as_agent_name(chat_client: ChatClient) -> None:
    # Name is specified here, so it should be used as author name
    agent = Agent(chat_client=chat_client, name="TestAgent")

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "TestAgent"


async def test_chat_client_agent_author_name_is_used_from_response() -> None:
    chat_client = MockChatClient(
        mock_response=ChatResponse(
            messages=[
                ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent("test response")], author_name="TestAuthor")
            ]
        )
    )
    agent = Agent(chat_client=chat_client)

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "TestAuthor"
