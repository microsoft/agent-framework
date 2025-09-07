# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, MutableSequence
from typing import Any
from uuid import uuid4

from pytest import fixture, raises

from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseChatClient,
    ChatAgent,
    ChatClientProtocol,
    ChatMessage,
    ChatMessageList,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Role,
    TextContent,
)
from agent_framework.exceptions import AgentExecutionException


# Mock AgentThread implementation for testing
class MockAgentThread(AgentThread):
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
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, contents=[TextContent("Response")])])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        yield AgentRunResponseUpdate(contents=[TextContent("Response")])

    def get_new_thread(self) -> AgentThread:
        return MockAgentThread()


# Mock ChatClientProtocol implementation for testing
class MockChatClient(BaseChatClient):
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
            else ChatResponse(messages=ChatMessage(role=Role.ASSISTANT, text="test response"))
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        yield ChatResponseUpdate(role=Role.ASSISTANT, text=TextContent(text="test streaming response"))


@fixture
def agent_thread() -> AgentThread:
    return MockAgentThread()


@fixture
def agent() -> AgentProtocol:
    return MockAgent()


@fixture
def chat_client() -> BaseChatClient:
    return MockChatClient()


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

    assert result.text == "test streaming response"


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
        input_messages=[ChatMessage(role=Role.USER, text="Test")],
    )

    assert len(result_messages) == 2
    assert result_messages[0] == message
    assert result_messages[1].text == "Test"


async def test_chat_client_agent_update_thread_id() -> None:
    chat_client = MockChatClient(
        mock_response=ChatResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, contents=[TextContent("test response")])],
            conversation_id="123",
        )
    )
    agent = ChatAgent(chat_client=chat_client)
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


async def test_chat_client_agent_author_name_is_used_from_response() -> None:
    chat_client = MockChatClient(
        mock_response=ChatResponse(
            messages=[
                ChatMessage(role=Role.ASSISTANT, contents=[TextContent("test response")], author_name="TestAuthor")
            ]
        )
    )
    agent = ChatAgent(chat_client=chat_client)

    result = await agent.run("Hello")
    assert result.text == "test response"
    assert result.messages[0].author_name == "TestAuthor"
