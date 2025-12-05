# Copyright (c) Microsoft. All rights reserved.

"""Shared test fixtures for DevUI tests.

This module provides reusable fixtures including:
- Mock chat clients that don't require API keys
- Real workflow event classes from agent_framework
- Test agents and executors for workflow testing
- Common request/response fixtures

These fixtures follow the patterns established in the core agent_framework tests,
ensuring consistency and proper testing of the full serialization pipeline.
"""

from collections.abc import AsyncIterable, MutableSequence
from typing import Any

import pytest
import pytest_asyncio
from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseAgent,
    BaseChatClient,
    ChatAgent,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
    use_chat_middleware,
)
from agent_framework._workflows._agent_executor import AgentExecutorResponse

# Import real workflow event classes - NOT mocks!
from agent_framework._workflows._events import (
    ExecutorCompletedEvent,
    ExecutorFailedEvent,
    ExecutorInvokedEvent,
)

from agent_framework_devui._discovery import EntityDiscovery
from agent_framework_devui._executor import AgentFrameworkExecutor
from agent_framework_devui._mapper import MessageMapper
from agent_framework_devui.models._openai_custom import AgentFrameworkRequest

# =============================================================================
# Mock Chat Clients (from core tests pattern)
# =============================================================================


class MockChatClient:
    """Simple mock chat client that doesn't require API keys.

    Configure responses by setting `responses` or `streaming_responses` lists.
    """

    def __init__(self) -> None:
        self.additional_properties: dict[str, Any] = {}
        self.call_count: int = 0
        self.responses: list[ChatResponse] = []
        self.streaming_responses: list[list[ChatResponseUpdate]] = []

    async def get_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        **kwargs: Any,
    ) -> ChatResponse:
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        return ChatResponse(messages=ChatMessage(role="assistant", text="test response"))

    async def get_streaming_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        self.call_count += 1
        if self.streaming_responses:
            for update in self.streaming_responses.pop(0):
                yield update
        else:
            yield ChatResponseUpdate(text=TextContent(text="test streaming response"), role="assistant")


@use_chat_middleware
class MockBaseChatClient(BaseChatClient):
    """Full BaseChatClient mock with middleware support.

    Use this when testing features that require the full BaseChatClient interface.
    This goes through all the middleware, message normalization, etc. - only the
    actual LLM call is mocked.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.run_responses: list[ChatResponse] = []
        self.streaming_responses: list[list[ChatResponseUpdate]] = []
        self.call_count: int = 0
        self.received_messages: list[list[ChatMessage]] = []

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        self.call_count += 1
        self.received_messages.append(list(messages))
        if self.run_responses:
            return self.run_responses.pop(0)
        return ChatResponse(messages=ChatMessage(role="assistant", text="Mock response from ChatAgent"))

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        self.call_count += 1
        self.received_messages.append(list(messages))
        if self.streaming_responses:
            for update in self.streaming_responses.pop(0):
                yield update
        else:
            # Simulate realistic streaming chunks
            yield ChatResponseUpdate(text=TextContent(text="Mock "), role="assistant")
            yield ChatResponseUpdate(text=TextContent(text="streaming "), role="assistant")
            yield ChatResponseUpdate(text=TextContent(text="response "), role="assistant")
            yield ChatResponseUpdate(text=TextContent(text="from ChatAgent"), role="assistant")


# =============================================================================
# Mock Agents (for workflow testing without API keys)
# =============================================================================


class MockAgent(BaseAgent):
    """Mock agent that returns configurable responses without needing a chat client."""

    def __init__(
        self,
        response_text: str = "Mock agent response",
        streaming_chunks: list[str] | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.response_text = response_text
        self.streaming_chunks = streaming_chunks or [response_text]
        self.call_count = 0

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        self.call_count += 1
        return AgentRunResponse(
            messages=[ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text=self.response_text)])]
        )

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        self.call_count += 1
        for chunk in self.streaming_chunks:
            yield AgentRunResponseUpdate(contents=[TextContent(text=chunk)], role=Role.ASSISTANT)


class MockToolCallingAgent(BaseAgent):
    """Mock agent that simulates tool calls and results in streaming mode."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.call_count = 0

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        self.call_count += 1
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="done")])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        self.call_count += 1
        # First: text
        yield AgentRunResponseUpdate(
            contents=[TextContent(text="Let me search for that...")],
            role=Role.ASSISTANT,
        )
        # Second: tool call
        yield AgentRunResponseUpdate(
            contents=[
                FunctionCallContent(
                    call_id="call_123",
                    name="search",
                    arguments={"query": "weather"},
                )
            ],
            role=Role.ASSISTANT,
        )
        # Third: tool result
        yield AgentRunResponseUpdate(
            contents=[
                FunctionResultContent(
                    call_id="call_123",
                    result={"temperature": 72, "condition": "sunny"},
                )
            ],
            role=Role.TOOL,
        )
        # Fourth: final text
        yield AgentRunResponseUpdate(
            contents=[TextContent(text="The weather is sunny, 72°F.")],
            role=Role.ASSISTANT,
        )


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture
def mapper() -> MessageMapper:
    """Create a fresh MessageMapper for each test."""
    return MessageMapper()


@pytest.fixture
def test_request() -> AgentFrameworkRequest:
    """Create a standard test request."""
    return AgentFrameworkRequest(
        metadata={"entity_id": "test_agent"},
        input="Test input",
        stream=True,
    )


@pytest.fixture
def mock_chat_client() -> MockChatClient:
    """Create a mock chat client."""
    return MockChatClient()


@pytest.fixture
def mock_base_chat_client() -> MockBaseChatClient:
    """Create a mock BaseChatClient."""
    return MockBaseChatClient()


@pytest.fixture
def mock_agent() -> MockAgent:
    """Create a mock agent."""
    return MockAgent(id="test_agent", name="TestAgent")


@pytest.fixture
def mock_tool_agent() -> MockToolCallingAgent:
    """Create a mock agent that simulates tool calls."""
    return MockToolCallingAgent(id="tool_agent", name="ToolAgent")


# =============================================================================
# Test Data Factories
# =============================================================================


def create_agent_run_response(text: str = "Test response") -> AgentRunResponse:
    """Create an AgentRunResponse with the given text."""
    return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text=text)])])


def create_agent_executor_response(
    executor_id: str = "test_executor",
    response_text: str = "Executor response",
) -> AgentExecutorResponse:
    """Create an AgentExecutorResponse - the type that's nested in ExecutorCompletedEvent.data."""
    agent_response = create_agent_run_response(response_text)
    return AgentExecutorResponse(
        executor_id=executor_id,
        agent_run_response=agent_response,
        full_conversation=[
            ChatMessage(role=Role.USER, contents=[TextContent(text="User input")]),
            ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text=response_text)]),
        ],
    )


def create_executor_completed_event(
    executor_id: str = "test_executor",
    with_agent_response: bool = True,
) -> ExecutorCompletedEvent:
    """Create an ExecutorCompletedEvent with realistic nested data.

    This creates the exact data structure that caused the serialization bug:
    ExecutorCompletedEvent.data contains AgentExecutorResponse which contains
    AgentRunResponse and ChatMessage objects (SerializationMixin, not Pydantic).
    """
    data = create_agent_executor_response(executor_id) if with_agent_response else {"simple": "dict"}
    return ExecutorCompletedEvent(executor_id=executor_id, data=data)


def create_executor_invoked_event(executor_id: str = "test_executor") -> ExecutorInvokedEvent:
    """Create an ExecutorInvokedEvent."""
    return ExecutorInvokedEvent(executor_id=executor_id)


def create_executor_failed_event(
    executor_id: str = "test_executor",
    error_message: str = "Test error",
) -> ExecutorFailedEvent:
    """Create an ExecutorFailedEvent."""
    from agent_framework._workflows._events import WorkflowErrorDetails

    details = WorkflowErrorDetails(error_type="TestError", message=error_message)
    return ExecutorFailedEvent(executor_id=executor_id, details=details)


# =============================================================================
# Executor with Real ChatAgent Fixture
# =============================================================================


@pytest_asyncio.fixture
async def executor_with_real_agent() -> tuple[AgentFrameworkExecutor, str, MockBaseChatClient]:
    """Create an executor with a REAL ChatAgent using mock chat client.

    This tests the full execution pipeline:
    - Real ChatAgent class
    - Real message handling and normalization
    - Real middleware pipeline
    - Only the LLM call is mocked

    Returns tuple of (executor, entity_id, mock_client) so tests can access all components.
    """
    mock_client = MockBaseChatClient()
    discovery = EntityDiscovery(None)
    mapper = MessageMapper()
    executor = AgentFrameworkExecutor(discovery, mapper)

    # Create a REAL ChatAgent with mock client
    agent = ChatAgent(
        id="test_chat_agent",
        name="Test Chat Agent",
        description="A real ChatAgent for testing execution flow",
        chat_client=mock_client,
        system_message="You are a helpful test assistant.",
    )

    # Register the real agent
    entity_info = await discovery.create_entity_info_from_object(agent, source="test")
    discovery.register_entity(entity_info.id, entity_info, agent)

    return executor, entity_info.id, mock_client


# =============================================================================
# Reusable Workflow Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def sequential_workflow_fixture() -> tuple[AgentFrameworkExecutor, str, MockBaseChatClient, Any]:
    """Create a realistic sequential workflow (Writer → Reviewer).

    This fixture provides a reusable multi-agent workflow that:
    - Chains 2 ChatAgents sequentially
    - Writer generates content, Reviewer provides feedback
    - Pre-configures mock responses for both agents

    Returns tuple of (executor, entity_id, mock_client, workflow) for test access.
    """
    from agent_framework import SequentialBuilder

    mock_client = MockBaseChatClient()
    mock_client.run_responses = [
        ChatResponse(messages=ChatMessage(role=Role.ASSISTANT, text="Here's the draft content about the topic.")),
        ChatResponse(messages=ChatMessage(role=Role.ASSISTANT, text="Review: Content is clear and well-structured.")),
    ]

    writer = ChatAgent(
        id="writer",
        name="Writer",
        description="Content writer agent",
        chat_client=mock_client,
        system_message="You are a content writer. Create clear, engaging content.",
    )
    reviewer = ChatAgent(
        id="reviewer",
        name="Reviewer",
        description="Content reviewer agent",
        chat_client=mock_client,
        system_message="You are a reviewer. Provide constructive feedback.",
    )

    workflow = SequentialBuilder().participants([writer, reviewer]).build()

    discovery = EntityDiscovery(None)
    mapper = MessageMapper()
    executor = AgentFrameworkExecutor(discovery, mapper)

    entity_info = await discovery.create_entity_info_from_object(workflow, entity_type="workflow", source="test")
    discovery.register_entity(entity_info.id, entity_info, workflow)

    return executor, entity_info.id, mock_client, workflow


@pytest_asyncio.fixture
async def concurrent_workflow_fixture() -> tuple[AgentFrameworkExecutor, str, MockBaseChatClient, Any]:
    """Create a realistic concurrent workflow (Researcher | Analyst | Summarizer).

    This fixture provides a reusable fan-out/fan-in workflow that:
    - Runs 3 ChatAgents in parallel
    - Each agent processes the same input independently
    - Pre-configures mock responses for all agents

    Returns tuple of (executor, entity_id, mock_client, workflow) for test access.
    """
    from agent_framework import ConcurrentBuilder

    mock_client = MockBaseChatClient()
    mock_client.run_responses = [
        ChatResponse(messages=ChatMessage(role=Role.ASSISTANT, text="Research findings: Key data points identified.")),
        ChatResponse(messages=ChatMessage(role=Role.ASSISTANT, text="Analysis: Trends indicate positive growth.")),
        ChatResponse(messages=ChatMessage(role=Role.ASSISTANT, text="Summary: Overall outlook is favorable.")),
    ]

    researcher = ChatAgent(
        id="researcher",
        name="Researcher",
        description="Research agent",
        chat_client=mock_client,
        system_message="You are a researcher. Find key data and insights.",
    )
    analyst = ChatAgent(
        id="analyst",
        name="Analyst",
        description="Analysis agent",
        chat_client=mock_client,
        system_message="You are an analyst. Identify trends and patterns.",
    )
    summarizer = ChatAgent(
        id="summarizer",
        name="Summarizer",
        description="Summary agent",
        chat_client=mock_client,
        system_message="You are a summarizer. Provide concise summaries.",
    )

    workflow = ConcurrentBuilder().participants([researcher, analyst, summarizer]).build()

    discovery = EntityDiscovery(None)
    mapper = MessageMapper()
    executor = AgentFrameworkExecutor(discovery, mapper)

    entity_info = await discovery.create_entity_info_from_object(workflow, entity_type="workflow", source="test")
    discovery.register_entity(entity_info.id, entity_info, workflow)

    return executor, entity_info.id, mock_client, workflow
