# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from a2a.types import (
    AgentCard,
    Artifact,
    DataPart,
    FilePart,
    FileWithUri,
    Part,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from a2a.types import Message as A2AMessage
from a2a.types import Role as A2ARole
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseContextProvider,
    BaseHistoryProvider,
    Content,
    Message,
)
from agent_framework.a2a import A2AAgent
from pytest import fixture, raises

from agent_framework_a2a import A2AContinuationToken
from agent_framework_a2a._agent import _get_uri_data  # type: ignore


class MockA2AClient:
    """Mock implementation of A2A Client for testing."""

    def __init__(self) -> None:
        self.call_count: int = 0
        self.responses: list[Any] = []
        self.resubscribe_responses: list[Any] = []
        self.get_task_response: Task | None = None

    def add_message_response(self, message_id: str, text: str, role: str = "agent") -> None:
        """Add a mock Message response."""

        # Create actual TextPart instance and wrap it in Part
        text_part = Part(root=TextPart(text=text))

        # Create actual Message instance
        message = A2AMessage(
            message_id=message_id, role=A2ARole.agent if role == "agent" else A2ARole.user, parts=[text_part]
        )
        self.responses.append(message)

    def add_task_response(self, task_id: str, artifacts: list[dict[str, Any]]) -> None:
        """Add a mock Task response."""
        # Create mock artifacts
        mock_artifacts = []
        for artifact_data in artifacts:
            # Create actual TextPart instance and wrap it in Part
            text_part = Part(root=TextPart(text=artifact_data.get("content", "Test content")))

            artifact = Artifact(
                artifact_id=artifact_data.get("id", str(uuid4())),
                name=artifact_data.get("name", "test-artifact"),
                description=artifact_data.get("description", "Test artifact"),
                parts=[text_part],
            )
            mock_artifacts.append(artifact)

        # Create task status
        status = TaskStatus(state=TaskState.completed, message=None)

        # Create actual Task instance
        task = Task(
            id=task_id, context_id="test-context", status=status, artifacts=mock_artifacts if mock_artifacts else None
        )

        # Mock the ClientEvent tuple format
        update_event = None  # No specific update event for completed tasks
        client_event = (task, update_event)
        self.responses.append(client_event)

    def add_in_progress_task_response(
        self,
        task_id: str,
        context_id: str = "test-context",
        state: TaskState = TaskState.working,
    ) -> None:
        """Add a mock in-progress Task response (non-terminal)."""
        status = TaskStatus(state=state, message=None)
        task = Task(id=task_id, context_id=context_id, status=status)
        client_event = (task, None)
        self.responses.append(client_event)

    async def send_message(self, message: Any) -> AsyncIterator[Any]:
        """Mock send_message method that yields responses."""
        self.call_count += 1

        if self.responses:
            response = self.responses.pop(0)
            yield response

    async def resubscribe(self, request: Any) -> AsyncIterator[Any]:
        """Mock resubscribe method that yields responses."""
        self.call_count += 1

        for response in self.resubscribe_responses:
            yield response
        self.resubscribe_responses.clear()

    async def get_task(self, request: Any) -> Task:
        """Mock get_task method that returns a task."""
        self.call_count += 1
        if self.get_task_response is not None:
            return self.get_task_response
        msg = "No get_task response configured"
        raise ValueError(msg)


@fixture
def mock_a2a_client() -> MockA2AClient:
    """Fixture that provides a mock A2A client."""
    return MockA2AClient()


@fixture
def a2a_agent(mock_a2a_client: MockA2AClient) -> A2AAgent:
    """Fixture that provides an A2AAgent with a mock client."""
    return A2AAgent(name="Test Agent", id="test-agent", client=mock_a2a_client, http_client=None)


def test_a2a_agent_initialization_with_client(mock_a2a_client: MockA2AClient) -> None:
    """Test A2AAgent initialization with provided client."""
    # Use model_construct to bypass Pydantic validation for mock objects
    agent = A2AAgent(
        name="Test Agent", id="test-agent-123", description="A test agent", client=mock_a2a_client, http_client=None
    )

    assert agent.name == "Test Agent"
    assert agent.id == "test-agent-123"
    assert agent.description == "A test agent"
    assert agent.client == mock_a2a_client


def test_a2a_agent_defaults_name_description_from_agent_card(mock_a2a_client: MockA2AClient) -> None:
    """Test A2AAgent defaults name and description from agent_card when not explicitly provided."""
    mock_card = MagicMock(spec=AgentCard)
    mock_card.name = "Card Agent Name"
    mock_card.description = "Card agent description"

    agent = A2AAgent(agent_card=mock_card, client=mock_a2a_client, http_client=None)

    assert agent.name == "Card Agent Name"
    assert agent.description == "Card agent description"


def test_a2a_agent_explicit_name_description_overrides_agent_card(mock_a2a_client: MockA2AClient) -> None:
    """Test that explicit name/description take precedence over agent_card values."""
    mock_card = MagicMock(spec=AgentCard)
    mock_card.name = "Card Agent Name"
    mock_card.description = "Card agent description"

    agent = A2AAgent(
        name="Explicit Name",
        description="Explicit description",
        agent_card=mock_card,
        client=mock_a2a_client,
        http_client=None,
    )

    assert agent.name == "Explicit Name"
    assert agent.description == "Explicit description"


def test_a2a_agent_empty_string_name_description_not_overridden(mock_a2a_client: MockA2AClient) -> None:
    """Test that explicitly provided empty strings are not overridden by agent_card values."""
    mock_card = MagicMock(spec=AgentCard)
    mock_card.name = "Card Agent Name"
    mock_card.description = "Card agent description"

    agent = A2AAgent(
        name="",
        description="",
        agent_card=mock_card,
        client=mock_a2a_client,
        http_client=None,
    )

    assert agent.name == ""
    assert agent.description == ""


def test_a2a_agent_initialization_without_client_raises_error() -> None:
    """Test A2AAgent initialization without client or URL raises ValueError."""
    with raises(ValueError, match="Either agent_card or url must be provided"):
        A2AAgent(name="Test Agent")


async def test_run_with_message_response(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test run() method with immediate Message response."""
    mock_a2a_client.add_message_response("msg-123", "Hello from agent!", "agent")

    response = await a2a_agent.run("Hello agent")

    assert isinstance(response, AgentResponse)
    assert len(response.messages) == 1
    assert response.messages[0].role == "assistant"
    assert response.messages[0].text == "Hello from agent!"
    assert response.response_id == "msg-123"
    assert mock_a2a_client.call_count == 1


async def test_run_with_task_response_single_artifact(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test run() method with Task response containing single artifact."""
    artifacts = [{"id": "art-1", "content": "Generated report content"}]
    mock_a2a_client.add_task_response("task-456", artifacts)

    response = await a2a_agent.run("Generate a report")

    assert isinstance(response, AgentResponse)
    assert len(response.messages) == 1
    assert response.messages[0].role == "assistant"
    assert response.messages[0].text == "Generated report content"
    assert response.response_id == "task-456"
    assert mock_a2a_client.call_count == 1


async def test_run_with_task_response_multiple_artifacts(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test run() method with Task response containing multiple artifacts."""
    artifacts = [
        {"id": "art-1", "content": "First artifact content"},
        {"id": "art-2", "content": "Second artifact content"},
        {"id": "art-3", "content": "Third artifact content"},
    ]
    mock_a2a_client.add_task_response("task-789", artifacts)

    response = await a2a_agent.run("Generate multiple outputs")

    assert isinstance(response, AgentResponse)
    assert len(response.messages) == 3

    assert response.messages[0].text == "First artifact content"
    assert response.messages[1].text == "Second artifact content"
    assert response.messages[2].text == "Third artifact content"

    # All should be assistant messages
    for message in response.messages:
        assert message.role == "assistant"

    assert response.response_id == "task-789"


async def test_run_with_task_response_no_artifacts(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test run() method with Task response containing no artifacts."""
    mock_a2a_client.add_task_response("task-empty", [])

    response = await a2a_agent.run("Do something with no output")

    assert isinstance(response, AgentResponse)
    assert response.response_id == "task-empty"


async def test_run_with_unknown_response_type_raises_error(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test run() method with unknown response type raises NotImplementedError."""
    mock_a2a_client.responses.append("invalid_response")

    with raises(NotImplementedError, match="Only Message and Task responses are supported"):
        await a2a_agent.run("Test message")


def test_parse_messages_from_task_empty_artifacts(a2a_agent: A2AAgent) -> None:
    """Test _parse_messages_from_task with task containing no artifacts."""
    task = MagicMock()
    task.artifacts = None

    result = a2a_agent._parse_messages_from_task(task)

    assert len(result) == 0


def test_parse_messages_from_task_with_artifacts(a2a_agent: A2AAgent) -> None:
    """Test _parse_messages_from_task with task containing artifacts."""
    task = MagicMock()

    # Create mock artifacts
    artifact1 = MagicMock()
    artifact1.artifact_id = "art-1"
    text_part1 = MagicMock()
    text_part1.root = MagicMock()
    text_part1.root.kind = "text"
    text_part1.root.text = "Content 1"
    text_part1.root.metadata = None
    artifact1.parts = [text_part1]

    artifact2 = MagicMock()
    artifact2.artifact_id = "art-2"
    text_part2 = MagicMock()
    text_part2.root = MagicMock()
    text_part2.root.kind = "text"
    text_part2.root.text = "Content 2"
    text_part2.root.metadata = None
    artifact2.parts = [text_part2]

    task.artifacts = [artifact1, artifact2]

    result = a2a_agent._parse_messages_from_task(task)

    assert len(result) == 2
    assert result[0].text == "Content 1"
    assert result[1].text == "Content 2"
    assert all(msg.role == "assistant" for msg in result)


def test_parse_message_from_artifact(a2a_agent: A2AAgent) -> None:
    """Test _parse_message_from_artifact conversion."""
    artifact = MagicMock()
    artifact.artifact_id = "test-artifact"

    text_part = MagicMock()
    text_part.root = MagicMock()
    text_part.root.kind = "text"
    text_part.root.text = "Artifact content"
    text_part.root.metadata = None

    artifact.parts = [text_part]

    result = a2a_agent._parse_message_from_artifact(artifact)

    assert isinstance(result, Message)
    assert result.role == "assistant"
    assert result.text == "Artifact content"
    assert result.raw_representation == artifact


def test_get_uri_data_valid_uri() -> None:
    """Test _get_uri_data with valid data URI."""

    uri = "data:application/json;base64,eyJ0ZXN0IjoidmFsdWUifQ=="
    result = _get_uri_data(uri)
    assert result == "eyJ0ZXN0IjoidmFsdWUifQ=="


def test_get_uri_data_invalid_uri() -> None:
    """Test _get_uri_data with invalid URI format."""

    with raises(ValueError, match="Invalid data URI format"):
        _get_uri_data("not-a-valid-data-uri")


def test_parse_contents_from_a2a_conversion(a2a_agent: A2AAgent) -> None:
    """Test A2A parts to contents conversion."""

    agent = A2AAgent(name="Test Agent", client=MockA2AClient(), _http_client=None)

    # Create A2A parts
    parts = [Part(root=TextPart(text="First part")), Part(root=TextPart(text="Second part"))]

    # Convert to contents
    contents = agent._parse_contents_from_a2a(parts)

    # Verify conversion
    assert len(contents) == 2
    assert contents[0].type == "text"
    assert contents[1].type == "text"
    assert contents[0].text == "First part"
    assert contents[1].text == "Second part"


def test_prepare_message_for_a2a_with_error_content(a2a_agent: A2AAgent) -> None:
    """Test _prepare_message_for_a2a with ErrorContent."""

    # Create Message with ErrorContent
    error_content = Content.from_error(message="Test error message")
    message = Message(role="user", contents=[error_content])

    # Convert to A2A message
    a2a_message = a2a_agent._prepare_message_for_a2a(message)

    # Verify conversion
    assert len(a2a_message.parts) == 1
    assert a2a_message.parts[0].root.text == "Test error message"


def test_prepare_message_for_a2a_with_uri_content(a2a_agent: A2AAgent) -> None:
    """Test _prepare_message_for_a2a with UriContent."""

    # Create Message with UriContent
    uri_content = Content.from_uri(uri="http://example.com/file.pdf", media_type="application/pdf")
    message = Message(role="user", contents=[uri_content])

    # Convert to A2A message
    a2a_message = a2a_agent._prepare_message_for_a2a(message)

    # Verify conversion
    assert len(a2a_message.parts) == 1
    assert a2a_message.parts[0].root.file.uri == "http://example.com/file.pdf"
    assert a2a_message.parts[0].root.file.mime_type == "application/pdf"


def test_prepare_message_for_a2a_with_data_content(a2a_agent: A2AAgent) -> None:
    """Test _prepare_message_for_a2a with DataContent."""

    # Create Message with DataContent (base64 data URI)
    data_content = Content.from_uri(uri="data:text/plain;base64,SGVsbG8gV29ybGQ=", media_type="text/plain")
    message = Message(role="user", contents=[data_content])

    # Convert to A2A message
    a2a_message = a2a_agent._prepare_message_for_a2a(message)

    # Verify conversion
    assert len(a2a_message.parts) == 1
    assert a2a_message.parts[0].root.file.bytes == "SGVsbG8gV29ybGQ="
    assert a2a_message.parts[0].root.file.mime_type == "text/plain"


def test_prepare_message_for_a2a_empty_contents_raises_error(a2a_agent: A2AAgent) -> None:
    """Test _prepare_message_for_a2a with empty contents raises ValueError."""
    # Create Message with no contents
    message = Message(role="user", contents=[])

    # Should raise ValueError for empty contents
    with raises(ValueError, match="Message.contents is empty"):
        a2a_agent._prepare_message_for_a2a(message)


async def test_run_streaming_with_message_response(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test run(stream=True) method with immediate Message response."""
    mock_a2a_client.add_message_response("msg-stream-123", "Streaming response from agent!", "agent")

    # Collect streaming updates
    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello agent", stream=True):
        updates.append(update)

    # Verify streaming response
    assert len(updates) == 1
    assert isinstance(updates[0], AgentResponseUpdate)
    assert updates[0].role == "assistant"
    assert len(updates[0].contents) == 1

    content = updates[0].contents[0]
    assert content.type == "text"
    assert content.text == "Streaming response from agent!"

    assert updates[0].response_id == "msg-stream-123"
    assert mock_a2a_client.call_count == 1


async def test_context_manager_cleanup() -> None:
    """Test context manager cleanup of http client."""

    # Create mock http client that tracks aclose calls
    mock_http_client = AsyncMock()
    mock_a2a_client = MagicMock()

    agent = A2AAgent(client=mock_a2a_client)
    agent._http_client = mock_http_client

    # Test context manager cleanup
    async with agent:
        pass

    # Verify aclose was called
    mock_http_client.aclose.assert_called_once()


async def test_context_manager_no_cleanup_when_no_http_client() -> None:
    """Test context manager when _http_client is None."""

    mock_a2a_client = MagicMock()

    agent = A2AAgent(client=mock_a2a_client, _http_client=None)

    # This should not raise any errors
    async with agent:
        pass


def test_prepare_message_for_a2a_with_multiple_contents() -> None:
    """Test conversion of Message with multiple contents."""

    agent = A2AAgent(client=MagicMock(), _http_client=None)

    # Create message with multiple content types
    message = Message(
        role="user",
        contents=[
            Content.from_text(text="Here's the analysis:"),
            Content.from_data(data=b"binary data", media_type="application/octet-stream"),
            Content.from_uri(uri="https://example.com/image.png", media_type="image/png"),
            Content.from_text(text='{"structured": "data"}'),
        ],
    )

    result = agent._prepare_message_for_a2a(message)

    # Should have converted all 4 contents to parts
    assert len(result.parts) == 4

    # Check each part type
    assert result.parts[0].root.kind == "text"  # Regular text
    assert result.parts[1].root.kind == "file"  # Binary data
    assert result.parts[2].root.kind == "file"  # URI content
    assert result.parts[3].root.kind == "text"  # JSON text remains as text (no parsing)


def test_prepare_message_for_a2a_forwards_context_id() -> None:
    """Test conversion of Message preserves context_id without duplicating it in metadata."""

    agent = A2AAgent(client=MagicMock(), _http_client=None)

    message = Message(
        role="user",
        contents=[Content.from_text(text="Continue the task")],
        additional_properties={"context_id": "ctx-123", "trace_id": "trace-456"},
    )

    result = agent._prepare_message_for_a2a(message)

    assert result.context_id == "ctx-123"
    assert result.metadata == {"trace_id": "trace-456"}


def test_parse_contents_from_a2a_with_data_part() -> None:
    """Test conversion of A2A DataPart."""

    agent = A2AAgent(client=MagicMock(), _http_client=None)

    # Create DataPart
    data_part = Part(root=DataPart(data={"key": "value", "number": 42}, metadata={"source": "test"}))

    contents = agent._parse_contents_from_a2a([data_part])

    assert len(contents) == 1

    assert contents[0].type == "text"
    assert contents[0].text == '{"key": "value", "number": 42}'
    assert contents[0].additional_properties == {"source": "test"}


def test_parse_contents_from_a2a_unknown_part_kind() -> None:
    """Test error handling for unknown A2A part kind."""
    agent = A2AAgent(client=MagicMock(), _http_client=None)

    # Create a mock part with unknown kind
    mock_part = MagicMock()
    mock_part.root.kind = "unknown_kind"

    with raises(ValueError, match="Unknown Part kind: unknown_kind"):
        agent._parse_contents_from_a2a([mock_part])


def test_prepare_message_for_a2a_with_hosted_file() -> None:
    """Test conversion of Message with HostedFileContent to A2A message."""

    agent = A2AAgent(client=MagicMock(), _http_client=None)

    # Create message with hosted file content
    message = Message(
        role="user",
        contents=[Content.from_hosted_file(file_id="hosted://storage/document.pdf")],
    )

    result = agent._prepare_message_for_a2a(message)  # noqa: SLF001

    # Verify the conversion
    assert len(result.parts) == 1
    part = result.parts[0]
    assert part.root.kind == "file"

    # Verify it's a FilePart with FileWithUri

    assert isinstance(part.root, FilePart)
    assert isinstance(part.root.file, FileWithUri)
    assert part.root.file.uri == "hosted://storage/document.pdf"
    assert part.root.file.mime_type is None  # HostedFileContent doesn't specify media_type


def test_parse_contents_from_a2a_with_hosted_file_uri() -> None:
    """Test conversion of A2A FilePart with hosted file URI back to UriContent."""

    agent = A2AAgent(client=MagicMock(), _http_client=None)

    # Create FilePart with hosted file URI (simulating what A2A would send back)
    file_part = Part(
        root=FilePart(
            file=FileWithUri(
                uri="hosted://storage/document.pdf",
                mime_type=None,
            )
        )
    )

    contents = agent._parse_contents_from_a2a([file_part])  # noqa: SLF001

    assert len(contents) == 1

    assert contents[0].type == "uri"
    assert contents[0].uri == "hosted://storage/document.pdf"
    assert contents[0].media_type == ""  # Converted None to empty string


def test_auth_interceptor_parameter() -> None:
    """Test that auth_interceptor parameter is accepted without errors."""
    # Create a mock auth interceptor
    mock_auth_interceptor = MagicMock()

    # Test that A2AAgent can be created with auth_interceptor parameter
    # Using url parameter for simplicity
    agent = A2AAgent(
        name="test-agent",
        url="https://test-agent.example.com",
        auth_interceptor=mock_auth_interceptor,
    )

    # Verify the agent was created successfully
    assert agent.name == "test-agent"
    assert agent.client is not None


def test_transport_negotiation_both_fail() -> None:
    """Test that RuntimeError is raised when both primary and fallback transport negotiation fail."""
    # Create a mock agent card
    mock_agent_card = MagicMock(spec=AgentCard)
    mock_agent_card.url = "http://test-agent.example.com"
    mock_agent_card.name = "Test Agent"
    mock_agent_card.description = "A test agent"

    # Mock the factory to simulate both primary and fallback failures
    mock_factory = MagicMock()

    # Both calls to factory.create() fail
    primary_error = Exception("no compatible transports found")
    fallback_error = Exception("fallback also failed")
    mock_factory.create.side_effect = [primary_error, fallback_error]

    with (
        patch("agent_framework_a2a._agent.ClientFactory", return_value=mock_factory),
        patch("agent_framework_a2a._agent.minimal_agent_card"),
        patch("agent_framework_a2a._agent.httpx.AsyncClient"),
        raises(RuntimeError, match="A2A transport negotiation failed"),
    ):
        # Attempt to create A2AAgent - should raise RuntimeError
        A2AAgent(
            name="test-agent",
            agent_card=mock_agent_card,
        )


def test_create_timeout_config_httpx_timeout() -> None:
    """Test _create_timeout_config with httpx.Timeout object returns it unchanged."""
    agent = A2AAgent(name="Test Agent", client=MockA2AClient(), http_client=None)

    custom_timeout = httpx.Timeout(connect=15.0, read=180.0, write=20.0, pool=8.0)
    timeout_config = agent._create_timeout_config(custom_timeout)

    assert timeout_config is custom_timeout  # Same object reference
    assert timeout_config.connect == 15.0
    assert timeout_config.read == 180.0
    assert timeout_config.write == 20.0
    assert timeout_config.pool == 8.0


def test_create_timeout_config_invalid_type() -> None:
    """Test _create_timeout_config with invalid type raises TypeError."""
    agent = A2AAgent(name="Test Agent", client=MockA2AClient(), http_client=None)

    with raises(TypeError, match="Invalid timeout type: <class 'str'>. Expected float, httpx.Timeout, or None."):
        agent._create_timeout_config("invalid")


def test_a2a_agent_initialization_with_timeout_parameter() -> None:
    """Test A2AAgent initialization with timeout parameter."""
    # Test with URL to trigger httpx client creation
    with (
        patch("agent_framework_a2a._agent.httpx.AsyncClient") as mock_async_client,
        patch("agent_framework_a2a._agent.ClientFactory") as mock_factory,
    ):
        # Mock the factory and client creation
        mock_client_instance = MagicMock()
        mock_factory.return_value.create.return_value = mock_client_instance

        # Create agent with custom timeout
        A2AAgent(name="Test Agent", url="https://test-agent.example.com", timeout=120.0)

        # Verify httpx.AsyncClient was called with the configured timeout
        mock_async_client.assert_called_once()
        call_args = mock_async_client.call_args

        # Check that timeout parameter was passed
        assert "timeout" in call_args.kwargs
        timeout_arg = call_args.kwargs["timeout"]

        # Verify it's an httpx.Timeout object with our custom timeout applied to all components
        assert isinstance(timeout_arg, httpx.Timeout)


# region Continuation Token Tests


async def test_working_task_emits_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that a working (non-terminal) task yields an update with a continuation token when background=True."""
    mock_a2a_client.add_in_progress_task_response("task-wip", context_id="ctx-1", state=TaskState.working)

    response = await a2a_agent.run("Start long task", background=True)

    assert isinstance(response, AgentResponse)
    assert response.continuation_token is not None
    assert response.continuation_token["task_id"] == "task-wip"
    assert response.continuation_token["context_id"] == "ctx-1"


async def test_submitted_task_emits_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that a submitted task yields a continuation token when background=True."""
    mock_a2a_client.add_in_progress_task_response("task-sub", state=TaskState.submitted)

    response = await a2a_agent.run("Submit task", background=True)

    assert response.continuation_token is not None
    assert response.continuation_token["task_id"] == "task-sub"


async def test_input_required_task_emits_continuation_token(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that an input_required task yields a continuation token when background=True."""
    mock_a2a_client.add_in_progress_task_response("task-input", state=TaskState.input_required)

    response = await a2a_agent.run("Need input", background=True)

    assert response.continuation_token is not None
    assert response.continuation_token["task_id"] == "task-input"


async def test_working_task_no_token_without_background(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that background=False (default) does not emit continuation tokens for in-progress tasks."""
    mock_a2a_client.add_in_progress_task_response("task-fg", context_id="ctx-fg", state=TaskState.working)

    response = await a2a_agent.run("Foreground task")

    assert response.continuation_token is None


async def test_completed_task_has_no_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that a completed task does not set a continuation token."""
    mock_a2a_client.add_task_response("task-done", [{"id": "art-1", "content": "Result"}])

    response = await a2a_agent.run("Quick task")

    assert response.continuation_token is None
    assert len(response.messages) == 1
    assert response.messages[0].text == "Result"


async def test_streaming_emits_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that streaming with background=True yields updates with continuation tokens."""
    mock_a2a_client.add_in_progress_task_response("task-stream", context_id="ctx-s", state=TaskState.working)

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Stream task", stream=True, background=True):
        updates.append(update)

    assert len(updates) == 1
    assert updates[0].continuation_token is not None
    assert updates[0].continuation_token["task_id"] == "task-stream"
    assert updates[0].continuation_token["context_id"] == "ctx-s"


async def test_resume_via_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that run() with continuation_token uses resubscribe instead of send_message."""
    # Set up the resubscribe response (completed task)
    status = TaskStatus(state=TaskState.completed, message=None)
    artifact = Artifact(
        artifact_id="art-resume",
        name="result",
        parts=[Part(root=TextPart(text="Resumed result"))],
    )
    task = Task(id="task-resume", context_id="ctx-r", status=status, artifacts=[artifact])
    mock_a2a_client.resubscribe_responses.append((task, None))

    token = A2AContinuationToken(task_id="task-resume", context_id="ctx-r")
    response = await a2a_agent.run(continuation_token=token)

    assert isinstance(response, AgentResponse)
    assert len(response.messages) == 1
    assert response.messages[0].text == "Resumed result"
    assert response.continuation_token is None


async def test_resume_streaming_via_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that streaming run() with continuation_token and background=True uses resubscribe."""
    # Still working
    status_wip = TaskStatus(state=TaskState.working, message=None)
    task_wip = Task(id="task-rs", context_id="ctx-rs", status=status_wip)
    # Then completed
    status_done = TaskStatus(state=TaskState.completed, message=None)
    artifact = Artifact(
        artifact_id="art-rs",
        name="result",
        parts=[Part(root=TextPart(text="Stream resumed"))],
    )
    task_done = Task(id="task-rs", context_id="ctx-rs", status=status_done, artifacts=[artifact])
    mock_a2a_client.resubscribe_responses.extend([(task_wip, None), (task_done, None)])

    token = A2AContinuationToken(task_id="task-rs", context_id="ctx-rs")
    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run(stream=True, continuation_token=token, background=True):
        updates.append(update)

    # First update: in-progress with token, second: completed with content
    assert len(updates) == 2
    assert updates[0].continuation_token is not None
    assert updates[0].continuation_token["task_id"] == "task-rs"
    assert updates[1].continuation_token is None
    assert updates[1].contents[0].text == "Stream resumed"


async def test_poll_task_in_progress(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test poll_task returns continuation token when task is still in progress."""
    status = TaskStatus(state=TaskState.working, message=None)
    mock_a2a_client.get_task_response = Task(id="task-poll", context_id="ctx-p", status=status)

    token = A2AContinuationToken(task_id="task-poll", context_id="ctx-p")
    response = await a2a_agent.poll_task(token)

    assert response.continuation_token is not None
    assert response.continuation_token["task_id"] == "task-poll"


async def test_poll_task_completed(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test poll_task returns result with no continuation token when task is complete."""
    status = TaskStatus(state=TaskState.completed, message=None)
    artifact = Artifact(
        artifact_id="art-poll",
        name="result",
        parts=[Part(root=TextPart(text="Poll result"))],
    )
    mock_a2a_client.get_task_response = Task(
        id="task-poll-done", context_id="ctx-pd", status=status, artifacts=[artifact]
    )

    token = A2AContinuationToken(task_id="task-poll-done", context_id="ctx-pd")
    response = await a2a_agent.poll_task(token)

    assert response.continuation_token is None
    assert len(response.messages) == 1
    assert response.messages[0].text == "Poll result"


# region context_providers


class TrackingContextProvider(BaseContextProvider):
    """Context provider that tracks before_run/after_run calls."""

    def __init__(self, source_id: str = "tracking") -> None:
        super().__init__(source_id=source_id)
        self.before_run_called = False
        self.after_run_called = False
        self.before_run_session: AgentSession | None = None
        self.after_run_session: AgentSession | None = None
        self.after_run_response: AgentResponse | None = None

    async def before_run(self, *, agent, session, context, state) -> None:
        self.before_run_called = True
        self.before_run_session = session

    async def after_run(self, *, agent, session, context, state) -> None:
        self.after_run_called = True
        self.after_run_session = session
        self.after_run_response = context.response


async def test_run_invokes_context_providers(mock_a2a_client: MockA2AClient) -> None:
    """Test that run() calls before_run and after_run on context providers."""
    provider = TrackingContextProvider()
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None, context_providers=[provider])

    mock_a2a_client.add_message_response("msg-ctx", "Hello!", "agent")

    response = await agent.run("Hi")

    assert provider.before_run_called
    assert provider.after_run_called
    assert provider.after_run_response is not None
    assert isinstance(response, AgentResponse)
    assert response.messages[0].text == "Hello!"


async def test_run_invokes_context_providers_with_session(mock_a2a_client: MockA2AClient) -> None:
    """Test that context providers receive the provided session."""
    provider = TrackingContextProvider()
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None, context_providers=[provider])
    session = AgentSession(session_id="test-session")

    mock_a2a_client.add_message_response("msg-sess", "With session", "agent")

    await agent.run("Hi", session=session)

    assert provider.before_run_session is session
    assert provider.after_run_session is session


async def test_run_creates_session_for_providers_when_none(mock_a2a_client: MockA2AClient) -> None:
    """Test that a session is auto-created when context_providers are set but no session is passed."""
    provider = TrackingContextProvider()
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None, context_providers=[provider])

    mock_a2a_client.add_message_response("msg-auto", "Auto session", "agent")

    await agent.run("Hi")

    assert provider.before_run_session is not None
    assert provider.after_run_session is not None


async def test_streaming_invokes_context_providers(mock_a2a_client: MockA2AClient) -> None:
    """Test that streaming run() calls before_run and after_run on context providers."""
    provider = TrackingContextProvider()
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None, context_providers=[provider])

    mock_a2a_client.add_message_response("msg-stream-ctx", "Streamed!", "agent")

    response = await agent.run("Hi", stream=True).get_final_response()

    assert provider.before_run_called
    assert provider.after_run_called
    assert provider.after_run_response is not None
    assert response.messages[0].text == "Streamed!"


async def test_run_without_providers_still_works(mock_a2a_client: MockA2AClient) -> None:
    """Test that run() without context_providers still works correctly."""
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None)

    mock_a2a_client.add_message_response("msg-no-ctx", "No providers", "agent")

    response = await agent.run("Hi")

    assert isinstance(response, AgentResponse)
    assert response.messages[0].text == "No providers"


async def test_multiple_providers_invoked_in_order(mock_a2a_client: MockA2AClient) -> None:
    """Test that multiple context providers are called in forward/reverse order."""
    call_order: list[str] = []

    class OrderTrackingProvider(BaseContextProvider):
        async def before_run(self, *, agent, session, context, state) -> None:
            call_order.append(f"before:{self.source_id}")

        async def after_run(self, *, agent, session, context, state) -> None:
            call_order.append(f"after:{self.source_id}")

    provider_a = OrderTrackingProvider(source_id="a")
    provider_b = OrderTrackingProvider(source_id="b")
    agent = A2AAgent(
        name="Test Agent", client=mock_a2a_client, http_client=None, context_providers=[provider_a, provider_b]
    )

    mock_a2a_client.add_message_response("msg-order", "Ordered", "agent")

    await agent.run("Hi")

    assert call_order == ["before:a", "before:b", "after:b", "after:a"]


class TrackingHistoryProvider(BaseHistoryProvider):
    """History provider that tracks before_run/after_run calls."""

    def __init__(self, source_id: str = "history", *, load_messages: bool = True) -> None:
        super().__init__(source_id=source_id, load_messages=load_messages)
        self.before_run_called = False
        self.after_run_called = False

    async def before_run(self, *, agent, session, context, state) -> None:
        self.before_run_called = True

    async def after_run(self, *, agent, session, context, state) -> None:
        self.after_run_called = True

    async def get_messages(self, session_id, **kwargs) -> list[Message]:
        return []

    async def save_messages(self, session_id, messages, **kwargs) -> None:
        pass


async def test_history_provider_load_messages_false_skips_before_run(mock_a2a_client: MockA2AClient) -> None:
    """Test that BaseHistoryProvider with load_messages=False has before_run skipped."""
    provider = TrackingHistoryProvider(load_messages=False)
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None, context_providers=[provider])

    mock_a2a_client.add_message_response("msg-hist", "Hello!", "agent")

    await agent.run("Hi")

    assert not provider.before_run_called
    assert provider.after_run_called


async def test_history_provider_load_messages_false_raises_if_before_run_called(
    mock_a2a_client: MockA2AClient,
) -> None:
    """Test with a stub whose before_run raises, proving it is never invoked."""

    class FailingHistoryProvider(BaseHistoryProvider):
        def __init__(self) -> None:
            super().__init__(source_id="fail-hist", load_messages=False)
            self.after_run_called = False

        async def before_run(self, *, agent, session, context, state) -> None:
            raise AssertionError("before_run should not be called when load_messages=False")

        async def after_run(self, *, agent, session, context, state) -> None:
            self.after_run_called = True

        async def get_messages(self, session_id, **kwargs) -> list[Message]:
            return []

        async def save_messages(self, session_id, messages, **kwargs) -> None:
            pass

    provider = FailingHistoryProvider()
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None, context_providers=[provider])

    mock_a2a_client.add_message_response("msg-fail", "OK", "agent")

    # Should not raise — before_run is skipped
    await agent.run("Hi")
    assert provider.after_run_called


async def test_history_provider_load_messages_true_calls_before_run(mock_a2a_client: MockA2AClient) -> None:
    """Test that BaseHistoryProvider with load_messages=True (default) has before_run called."""
    provider = TrackingHistoryProvider(load_messages=True)
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None, context_providers=[provider])

    mock_a2a_client.add_message_response("msg-hist-true", "Hello!", "agent")

    await agent.run("Hi")

    assert provider.before_run_called
    assert provider.after_run_called


async def test_history_provider_load_messages_false_streaming(mock_a2a_client: MockA2AClient) -> None:
    """Test that streaming skips before_run for BaseHistoryProvider with load_messages=False."""
    provider = TrackingHistoryProvider(load_messages=False)
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None, context_providers=[provider])

    mock_a2a_client.add_message_response("msg-hist-stream", "Streamed!", "agent")

    await agent.run("Hi", stream=True).get_final_response()

    assert not provider.before_run_called
    assert provider.after_run_called


async def test_mixed_providers_with_history_load_messages_false(mock_a2a_client: MockA2AClient) -> None:
    """Test that a regular provider's before_run is called while history provider's is skipped."""
    context_provider = TrackingContextProvider(source_id="ctx")
    history_provider = TrackingHistoryProvider(source_id="hist", load_messages=False)
    agent = A2AAgent(
        name="Test Agent",
        client=mock_a2a_client,
        http_client=None,
        context_providers=[context_provider, history_provider],
    )

    mock_a2a_client.add_message_response("msg-mixed", "Mixed!", "agent")

    await agent.run("Hi")

    assert context_provider.before_run_called
    assert not history_provider.before_run_called
    assert context_provider.after_run_called
    assert history_provider.after_run_called


async def test_resume_via_continuation_token_with_context_providers(mock_a2a_client: MockA2AClient) -> None:
    """Test that non-streaming run() with continuation_token correctly invokes context providers."""
    provider = TrackingContextProvider()
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None, context_providers=[provider])

    status = TaskStatus(state=TaskState.completed, message=None)
    artifact = Artifact(
        artifact_id="art-ctx-resume",
        name="result",
        parts=[Part(root=TextPart(text="Resumed with providers"))],
    )
    task = Task(id="task-ctx-resume", context_id="ctx-cr", status=status, artifacts=[artifact])
    mock_a2a_client.resubscribe_responses.append((task, None))

    token = A2AContinuationToken(task_id="task-ctx-resume", context_id="ctx-cr")
    response = await agent.run(continuation_token=token)

    assert isinstance(response, AgentResponse)
    assert response.messages[0].text == "Resumed with providers"
    assert provider.before_run_called
    assert provider.after_run_called
    assert provider.after_run_response is not None


async def test_resume_via_continuation_token_no_context_providers(mock_a2a_client: MockA2AClient) -> None:
    """Test that run() with continuation_token and no context_providers works without crash."""
    agent = A2AAgent(name="Test Agent", client=mock_a2a_client, http_client=None)

    status = TaskStatus(state=TaskState.completed, message=None)
    artifact = Artifact(
        artifact_id="art-no-ctx",
        name="result",
        parts=[Part(root=TextPart(text="Resumed no providers"))],
    )
    task = Task(id="task-no-ctx", context_id="ctx-nc", status=status, artifacts=[artifact])
    mock_a2a_client.resubscribe_responses.append((task, None))

    token = A2AContinuationToken(task_id="task-no-ctx", context_id="ctx-nc")
    response = await agent.run(continuation_token=token)

    assert isinstance(response, AgentResponse)
    assert response.messages[0].text == "Resumed no providers"
    assert response.continuation_token is None


# endregion
