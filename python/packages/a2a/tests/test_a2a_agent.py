# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterator
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from a2a.types import (
    AgentCard,
    Artifact,
    Part,
    StreamResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.types import Message as A2AMessage
from a2a.types import Role as A2ARole
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    Content,
    ContextProvider,
    Message,
    SessionContext,
)
from agent_framework.a2a import A2AAgent
from pytest import fixture, mark, raises, warns

from agent_framework_a2a import A2AAgentSession, A2AContinuationToken, A2AServiceSessionId
from agent_framework_a2a._utils import get_uri_data


class MockA2AClient:
    """Mock implementation of A2A Client for testing."""

    def __init__(self) -> None:
        self.call_count: int = 0
        self.responses: list[StreamResponse] = []
        self.subscribe_responses: list[StreamResponse] = []
        self.get_task_response: Task | None = None
        self.last_message: Any = None
        self.last_request: Any = None

    def add_message_response(self, message_id: str, text: str, role: str = "agent") -> None:
        """Add a mock Message response."""
        message = A2AMessage(
            message_id=message_id,
            role=A2ARole.ROLE_AGENT if role == "agent" else A2ARole.ROLE_USER,
            parts=[Part(text=text)],
        )
        self.responses.append(StreamResponse(message=message))

    def add_task_response(self, task_id: str, artifacts: list[dict[str, Any]]) -> None:
        """Add a mock Task response."""
        mock_artifacts = []
        for artifact_data in artifacts:
            artifact = Artifact(
                artifact_id=artifact_data.get("id", str(uuid4())),
                name=artifact_data.get("name", "test-artifact"),
                parts=[Part(text=artifact_data.get("content", "Test content"))],
            )
            mock_artifacts.append(artifact)

        status = TaskStatus(state=TaskState.TASK_STATE_COMPLETED)
        task = Task(id=task_id, context_id="test-context", status=status, artifacts=mock_artifacts)
        self.responses.append(StreamResponse(task=task))

    def add_in_progress_task_response(
        self,
        task_id: str,
        context_id: str = "test-context",
        state: TaskState = TaskState.TASK_STATE_WORKING,
        text: str | None = None,
        role: A2ARole = A2ARole.ROLE_AGENT,
    ) -> None:
        """Add a mock in-progress Task response (non-terminal)."""
        message = None
        if text is not None:
            message = A2AMessage(
                message_id=str(uuid4()),
                role=role,
                parts=[Part(text=text)],
            )
        status = TaskStatus(state=state, message=message)
        task = Task(id=task_id, context_id=context_id, status=status)
        self.responses.append(StreamResponse(task=task))

    async def send_message(self, request: Any) -> AsyncIterator[StreamResponse]:
        """Mock send_message method that yields responses."""
        self.last_request = request
        self.last_message = getattr(request, "message", request)
        self.call_count += 1

        for response in self.responses:
            yield response
        self.responses.clear()

    async def subscribe(self, request: Any) -> AsyncIterator[StreamResponse]:
        """Mock subscribe method that yields responses."""
        self.call_count += 1

        for response in self.subscribe_responses:
            yield response
        self.subscribe_responses.clear()

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
    return A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)


def test_a2a_agent_initialization_with_client(mock_a2a_client: MockA2AClient) -> None:
    """Test A2AAgent initialization with provided client."""
    # Use model_construct to bypass Pydantic validation for mock objects
    agent = A2AAgent(
        name="Test Agent",
        id="test-agent-123",
        description="A test agent",
        client=cast(Any, mock_a2a_client),
        http_client=None,
    )

    assert agent.name == "Test Agent"
    assert agent.id == "test-agent-123"
    assert agent.description == "A test agent"
    assert agent.client == mock_a2a_client


def test_a2a_agent_session_emits_deprecation_warning() -> None:
    """A2AAgentSession emits a deprecation warning on construction."""
    with warns(DeprecationWarning, match="A2AAgentSession is deprecated"):
        A2AAgentSession()


def test_a2a_agent_defaults_name_description_from_agent_card(mock_a2a_client: MockA2AClient) -> None:
    """Test A2AAgent defaults name and description from agent_card when not explicitly provided."""
    mock_card = MagicMock(spec=AgentCard)
    mock_card.name = "Card Agent Name"
    mock_card.description = "Card agent description"

    agent = A2AAgent(agent_card=mock_card, client=cast(Any, mock_a2a_client), http_client=None)

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
        client=cast(Any, mock_a2a_client),
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
        client=cast(Any, mock_a2a_client),
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
    # An empty StreamResponse has no payload set (WhichOneof returns None)
    mock_a2a_client.responses.append(StreamResponse())

    with raises(NotImplementedError, match="Unsupported StreamResponse payload"):
        await a2a_agent.run("Test message")


def test_parse_messages_from_task_empty_artifacts(a2a_agent: A2AAgent) -> None:
    """Test _parse_messages_from_task with task containing no artifacts."""
    task = Task(id="test", context_id="test", status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED))

    result = a2a_agent._parse_messages_from_task(task)

    assert len(result) == 0


def test_parse_messages_from_task_with_artifacts(a2a_agent: A2AAgent) -> None:
    """Test _parse_messages_from_task with task containing artifacts."""
    artifact1 = Artifact(artifact_id="art-1", parts=[Part(text="Content 1")])
    artifact2 = Artifact(artifact_id="art-2", parts=[Part(text="Content 2")])
    task = Task(
        id="test",
        context_id="test",
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        artifacts=[artifact1, artifact2],
    )

    result = a2a_agent._parse_messages_from_task(task)

    assert len(result) == 2
    assert result[0].text == "Content 1"
    assert result[1].text == "Content 2"
    assert all(msg.role == "assistant" for msg in result)


def test_parse_message_from_artifact(a2a_agent: A2AAgent) -> None:
    """Test _parse_message_from_artifact conversion."""
    artifact = Artifact(artifact_id="test-artifact", parts=[Part(text="Artifact content")])

    result = a2a_agent._parse_message_from_artifact(artifact)

    assert isinstance(result, Message)
    assert result.role == "assistant"
    assert result.text == "Artifact content"
    assert result.raw_representation == artifact


def test_get_uri_data_valid_uri() -> None:
    """Test get_uri_data with valid data URI."""

    uri = "data:application/json;base64,eyJ0ZXN0IjoidmFsdWUifQ=="
    result = get_uri_data(uri)
    assert result == "eyJ0ZXN0IjoidmFsdWUifQ=="


def test_get_uri_data_invalid_uri() -> None:
    """Test get_uri_data with invalid URI format."""

    with raises(ValueError, match="Invalid data URI format"):
        get_uri_data("not-a-valid-data-uri")


def test_parse_contents_from_a2a_conversion(a2a_agent: A2AAgent) -> None:
    """Test A2A parts to contents conversion."""

    agent = A2AAgent(name="Test Agent", client=cast(Any, MockA2AClient()), http_client=None)

    # Create A2A parts
    parts = [Part(text="First part"), Part(text="Second part")]

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
    assert a2a_message.parts[0].text == "Test error message"


def test_prepare_message_for_a2a_with_uri_content(a2a_agent: A2AAgent) -> None:
    """Test _prepare_message_for_a2a with UriContent."""

    # Create Message with UriContent
    uri_content = Content.from_uri(uri="http://example.com/file.pdf", media_type="application/pdf")
    message = Message(role="user", contents=[uri_content])

    # Convert to A2A message
    a2a_message = a2a_agent._prepare_message_for_a2a(message)

    # Verify conversion
    assert len(a2a_message.parts) == 1
    assert a2a_message.parts[0].url == "http://example.com/file.pdf"
    assert a2a_message.parts[0].media_type == "application/pdf"


def test_prepare_message_for_a2a_with_data_content(a2a_agent: A2AAgent) -> None:
    """Test _prepare_message_for_a2a with DataContent."""

    # Create Message with DataContent (base64 data URI)
    data_content = Content.from_uri(uri="data:text/plain;base64,SGVsbG8gV29ybGQ=", media_type="text/plain")
    message = Message(role="user", contents=[data_content])

    # Convert to A2A message
    a2a_message = a2a_agent._prepare_message_for_a2a(message)

    # Verify conversion
    assert len(a2a_message.parts) == 1
    assert a2a_message.parts[0].raw == b"Hello World"
    assert a2a_message.parts[0].media_type == "text/plain"


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
    assert updates[0].message_id == "msg-stream-123"
    assert mock_a2a_client.call_count == 1


async def test_context_manager_cleanup() -> None:
    """Test context manager cleanup of http client."""

    # Create mock http client that tracks aclose calls
    mock_http_client = AsyncMock()
    mock_a2a_client = MagicMock()

    agent = A2AAgent(client=cast(Any, mock_a2a_client))
    agent._http_client = mock_http_client

    # Test context manager cleanup
    async with agent:
        pass

    # Verify aclose was called
    mock_http_client.aclose.assert_called_once()


async def test_context_manager_no_cleanup_when_no_http_client() -> None:
    """Test context manager when _http_client is None."""

    mock_a2a_client = MagicMock()

    agent = A2AAgent(client=cast(Any, mock_a2a_client), http_client=None)

    # This should not raise any errors
    async with agent:
        pass


def test_prepare_message_for_a2a_with_multiple_contents() -> None:
    """Test conversion of Message with multiple contents."""

    agent = A2AAgent(client=MagicMock(), http_client=None)

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
    assert result.parts[0].WhichOneof("content") == "text"  # Regular text
    assert result.parts[1].WhichOneof("content") == "raw"  # Binary data
    assert result.parts[2].WhichOneof("content") == "url"  # URI content
    assert result.parts[3].WhichOneof("content") == "text"  # JSON text remains as text (no parsing)


def test_prepare_message_for_a2a_forwards_context_id() -> None:
    """Test conversion of Message uses context_id from A2AAgentSession."""

    agent = A2AAgent(client=MagicMock(), http_client=None)

    message = Message(
        role="user",
        contents=[Content.from_text(text="Continue the task")],
        additional_properties={"a2a_metadata": {"trace_id": "trace-456"}},
    )

    session = A2AAgentSession(context_id="ctx-123")
    result = agent._prepare_message_for_a2a(message, session=session)

    assert result.context_id == "ctx-123"
    assert result.metadata == {"trace_id": "trace-456"}


def test_prepare_message_for_a2a_uses_fallback_context_id() -> None:
    """Test that service_session_id from a plain session is used when message has no context_id property."""

    agent = A2AAgent(client=MagicMock(), http_client=None)

    message = Message(
        role="user",
        contents=[Content.from_text(text="Hello")],
    )

    session = AgentSession(service_session_id="session-ctx-1")
    result = agent._prepare_message_for_a2a(message, session=session)

    assert result.context_id == "session-ctx-1"


def test_prepare_message_for_a2a_a2a_session_context_id_takes_precedence() -> None:
    """Test that A2AAgentSession.context_id is used over plain session service_session_id."""

    agent = A2AAgent(client=MagicMock(), http_client=None)

    message = Message(
        role="user",
        contents=[Content.from_text(text="Hello")],
    )

    session = A2AAgentSession(context_id="a2a-ctx")
    result = agent._prepare_message_for_a2a(message, session=session)

    assert result.context_id == "a2a-ctx"


def test_parse_contents_from_a2a_with_data_part() -> None:
    """Test conversion of A2A data Part."""
    from google.protobuf.json_format import ParseDict
    from google.protobuf.struct_pb2 import Struct, Value  # ty: ignore[unresolved-import]

    agent = A2AAgent(client=MagicMock(), http_client=None)

    # Create Part with data (protobuf Value containing a struct)
    value = ParseDict({"key": "value", "number": 42}, Value())
    metadata = Struct()
    metadata.update({"source": "test"})
    data_part = Part(data=value, metadata=metadata)

    contents = agent._parse_contents_from_a2a([data_part])

    assert len(contents) == 1

    assert contents[0].type == "text"
    # MessageToJson may format slightly differently — verify the parsed structure
    import json

    assert contents[0].text is not None
    parsed = json.loads(contents[0].text)
    assert parsed["key"] == "value"
    assert parsed["number"] == 42
    assert contents[0].additional_properties == {"source": "test"}


def test_parse_contents_from_a2a_unknown_part_kind() -> None:
    """Test error handling for unknown A2A part kind."""
    agent = A2AAgent(client=MagicMock(), http_client=None)

    # Create a Part with no content field set (WhichOneof returns None)
    empty_part = Part()

    with raises(ValueError, match="Unknown Part content type"):
        agent._parse_contents_from_a2a([empty_part])


def test_prepare_message_for_a2a_with_hosted_file() -> None:
    """Test conversion of Message with HostedFileContent to A2A message."""

    agent = A2AAgent(client=MagicMock(), http_client=None)

    # Create message with hosted file content
    message = Message(
        role="user",
        contents=[Content.from_hosted_file(file_id="hosted://storage/document.pdf")],
    )

    result = agent._prepare_message_for_a2a(message)  # noqa: SLF001

    # Verify the conversion
    assert len(result.parts) == 1
    part = result.parts[0]
    assert part.WhichOneof("content") == "url"
    assert part.url == "hosted://storage/document.pdf"


def test_parse_contents_from_a2a_with_hosted_file_uri() -> None:
    """Test conversion of A2A FilePart with hosted file URI back to UriContent."""

    agent = A2AAgent(client=MagicMock(), http_client=None)

    # Create Part with hosted file URL (simulating what A2A would send back)
    file_part = Part(url="hosted://storage/document.pdf")

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
    # Create a mock agent card with supported_interfaces
    mock_agent_card = MagicMock(spec=AgentCard)
    mock_interface = MagicMock()
    mock_interface.url = "http://test-agent.example.com"
    mock_agent_card.supported_interfaces = [mock_interface]
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
    agent = A2AAgent(name="Test Agent", client=cast(Any, MockA2AClient()), http_client=None)

    custom_timeout = httpx.Timeout(connect=15.0, read=180.0, write=20.0, pool=8.0)
    timeout_config = agent._create_timeout_config(custom_timeout)

    assert timeout_config is custom_timeout  # Same object reference
    assert timeout_config.connect == 15.0
    assert timeout_config.read == 180.0
    assert timeout_config.write == 20.0
    assert timeout_config.pool == 8.0


def test_create_timeout_config_invalid_type() -> None:
    """Test _create_timeout_config with invalid type raises TypeError."""
    agent = A2AAgent(name="Test Agent", client=cast(Any, MockA2AClient()), http_client=None)

    with raises(TypeError, match="Invalid timeout type: <class 'str'>. Expected float, httpx.Timeout, or None."):
        agent._create_timeout_config(cast(Any, "invalid"))


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


def test_a2a_agent_initialization_with_supported_protocol_bindings() -> None:
    """Test A2AAgent initialization with custom supported_protocol_bindings."""
    with (
        patch("agent_framework_a2a._agent.httpx.AsyncClient") as mock_async_client,
        patch("agent_framework_a2a._agent.ClientConfig") as mock_config,
        patch("agent_framework_a2a._agent.ClientFactory") as mock_factory,
    ):
        mock_async_client.return_value = MagicMock()
        mock_client_instance = MagicMock()
        mock_factory.return_value.create.return_value = mock_client_instance

        A2AAgent(
            name="Test Agent",
            url="https://test-agent.example.com",
            supported_protocol_bindings=["GRPC", "JSONRPC"],
        )

        # Verify ClientConfig was called with our custom bindings for both streaming and non-streaming
        assert mock_config.call_count == 2
        for call in mock_config.call_args_list:
            assert call.kwargs["supported_protocol_bindings"] == ["GRPC", "JSONRPC"]


def test_a2a_agent_initialization_defaults_to_jsonrpc() -> None:
    """Test A2AAgent defaults to JSONRPC when supported_protocol_bindings is not provided."""
    with (
        patch("agent_framework_a2a._agent.httpx.AsyncClient") as mock_async_client,
        patch("agent_framework_a2a._agent.ClientConfig") as mock_config,
        patch("agent_framework_a2a._agent.ClientFactory") as mock_factory,
    ):
        mock_async_client.return_value = MagicMock()
        mock_client_instance = MagicMock()
        mock_factory.return_value.create.return_value = mock_client_instance

        A2AAgent(name="Test Agent", url="https://test-agent.example.com")

        # Verify ClientConfig was called with default JSONRPC bindings
        assert mock_config.call_count == 2
        for call in mock_config.call_args_list:
            assert call.kwargs["supported_protocol_bindings"] == ["JSONRPC"]


def test_a2a_agent_initialization_empty_list_preserved() -> None:
    """Test that an explicit empty list is preserved and not replaced with defaults."""
    with (
        patch("agent_framework_a2a._agent.httpx.AsyncClient") as mock_async_client,
        patch("agent_framework_a2a._agent.ClientConfig") as mock_config,
        patch("agent_framework_a2a._agent.ClientFactory") as mock_factory,
    ):
        mock_async_client.return_value = MagicMock()
        mock_client_instance = MagicMock()
        mock_factory.return_value.create.return_value = mock_client_instance

        A2AAgent(
            name="Test Agent",
            url="https://test-agent.example.com",
            supported_protocol_bindings=[],
        )

        # Verify ClientConfig was called with the explicit empty list, not the default
        assert mock_config.call_count == 2
        for call in mock_config.call_args_list:
            assert call.kwargs["supported_protocol_bindings"] == []


def test_a2a_agent_fallback_uses_custom_bindings() -> None:
    """Test that transport fallback path uses custom bindings."""
    mock_agent_card = MagicMock()
    mock_agent_card.supported_interfaces = [MagicMock(url="https://fallback.example.com")]

    mock_factory = MagicMock()
    # First create() call fails (primary streaming), then fallback calls succeed
    primary_error = Exception("no compatible transports found")
    mock_factory.create.side_effect = [primary_error, MagicMock(), MagicMock()]

    with (
        patch("agent_framework_a2a._agent.ClientFactory", return_value=mock_factory),
        patch("agent_framework_a2a._agent.minimal_agent_card") as mock_minimal_card,
        patch("agent_framework_a2a._agent.httpx.AsyncClient"),
    ):
        A2AAgent(
            name="test-agent",
            agent_card=mock_agent_card,
            supported_protocol_bindings=["GRPC", "HTTP+JSON"],
        )

        # Verify minimal_agent_card was called with the custom bindings
        mock_minimal_card.assert_called_once_with("https://fallback.example.com", ["GRPC", "HTTP+JSON"])


async def test_working_task_emits_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that a working (non-terminal) task yields an update with a continuation token when background=True."""
    mock_a2a_client.add_in_progress_task_response("task-wip", context_id="ctx-1", state=TaskState.TASK_STATE_WORKING)

    response = await a2a_agent.run("Start long task", background=True)

    assert isinstance(response, AgentResponse)
    assert response.continuation_token is not None
    token = cast(dict[str, Any], response.continuation_token)
    assert token["task_id"] == "task-wip"
    assert token["context_id"] == "ctx-1"


async def test_submitted_task_emits_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that a submitted task yields a continuation token when background=True."""
    mock_a2a_client.add_in_progress_task_response("task-sub", state=TaskState.TASK_STATE_SUBMITTED)

    response = await a2a_agent.run("Submit task", background=True)

    assert response.continuation_token is not None
    token = cast(dict[str, Any], response.continuation_token)
    assert token["task_id"] == "task-sub"


async def test_input_required_task_emits_continuation_token(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that an input_required task yields a continuation token when background=True."""
    mock_a2a_client.add_in_progress_task_response("task-input", state=TaskState.TASK_STATE_INPUT_REQUIRED)

    response = await a2a_agent.run("Need input", background=True)

    assert response.continuation_token is not None
    token = cast(dict[str, Any], response.continuation_token)
    assert token["task_id"] == "task-input"


async def test_working_task_no_token_without_background(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that background=False (default) does not emit continuation tokens for in-progress tasks."""
    mock_a2a_client.add_in_progress_task_response("task-fg", context_id="ctx-fg", state=TaskState.TASK_STATE_WORKING)

    response = await a2a_agent.run("Foreground task")

    assert response.continuation_token is None


async def test_background_sets_return_immediately_on_request(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that background=True sets return_immediately=True on SendMessageRequest configuration."""
    mock_a2a_client.add_in_progress_task_response("task-bg", state=TaskState.TASK_STATE_WORKING)

    await a2a_agent.run("Background task", background=True)

    assert mock_a2a_client.last_request.configuration.return_immediately is True


async def test_foreground_does_not_set_return_immediately(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that background=False (default) does not set configuration on SendMessageRequest."""
    mock_a2a_client.add_task_response("task-fg2", [{"id": "art-1", "content": "Done"}])

    await a2a_agent.run("Foreground task")

    assert mock_a2a_client.last_request.HasField("configuration") is False


async def test_streaming_background_does_not_set_return_immediately(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that background=True with stream=True does not set return_immediately.

    Per A2A spec, return_immediately only applies to non-streaming (message/send).
    """
    mock_a2a_client.add_task_response("task-sb", [{"id": "art-1", "content": "Streaming bg"}])

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Stream background", stream=True, background=True):
        updates.append(update)

    assert mock_a2a_client.last_request.HasField("configuration") is False


async def test_non_streaming_run_uses_non_streaming_client() -> None:
    """Test that stream=False uses the non-streaming client when available."""
    streaming_client = MockA2AClient()
    non_streaming_client = MockA2AClient()
    non_streaming_client.add_task_response("task-ns", [{"id": "art-1", "content": "Non-streaming result"}])

    agent = A2AAgent(name="Test Agent", id="test-ns", client=cast(Any, streaming_client), http_client=None)
    agent._non_streaming_client = cast(Any, non_streaming_client)  # type: ignore[assignment]

    response = await agent.run("Hello")

    # Non-streaming client should have been called
    assert non_streaming_client.call_count == 1
    assert streaming_client.call_count == 0
    assert response.messages[0].text == "Non-streaming result"
    assert non_streaming_client.last_request.HasField("configuration") is False


async def test_streaming_run_uses_streaming_client() -> None:
    """Test that stream=True always uses the streaming client."""
    streaming_client = MockA2AClient()
    non_streaming_client = MockA2AClient()
    streaming_client.add_task_response("task-s", [{"id": "art-1", "content": "Streaming result"}])

    agent = A2AAgent(name="Test Agent", id="test-s", client=cast(Any, streaming_client), http_client=None)
    agent._non_streaming_client = cast(Any, non_streaming_client)  # type: ignore[assignment]

    updates: list[AgentResponseUpdate] = []
    async for update in agent.run("Hello", stream=True):
        updates.append(update)

    # Streaming client should have been called
    assert streaming_client.call_count == 1
    assert non_streaming_client.call_count == 0
    assert updates[0].contents[0].text == "Streaming result"


async def test_non_streaming_client_fallback_when_not_available(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that stream=False falls back to streaming client when non-streaming client is unavailable."""
    mock_a2a_client.add_task_response("task-fb", [{"id": "art-1", "content": "Fallback result"}])

    # a2a_agent is created with client= param so _non_streaming_client is None
    assert a2a_agent._non_streaming_client is None

    response = await a2a_agent.run("Hello")

    assert mock_a2a_client.call_count == 1
    assert response.messages[0].text == "Fallback result"


async def test_completed_task_has_no_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that a completed task does not set a continuation token."""
    mock_a2a_client.add_task_response("task-done", [{"id": "art-1", "content": "Result"}])

    response = await a2a_agent.run("Quick task")

    assert response.continuation_token is None
    assert len(response.messages) == 1
    assert response.messages[0].text == "Result"


async def test_streaming_emits_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that streaming with background=True yields updates with continuation tokens."""
    mock_a2a_client.add_in_progress_task_response("task-stream", context_id="ctx-s", state=TaskState.TASK_STATE_WORKING)

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Stream task", stream=True, background=True):
        updates.append(update)

    assert len(updates) == 1
    assert updates[0].continuation_token is not None
    token = cast(dict[str, Any], updates[0].continuation_token)
    assert token["task_id"] == "task-stream"
    assert token["context_id"] == "ctx-s"


async def test_resume_via_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that run() with continuation_token uses resubscribe instead of send_message."""
    # Set up the resubscribe response (completed task)
    status = TaskStatus(state=TaskState.TASK_STATE_COMPLETED, message=None)
    artifact = Artifact(
        artifact_id="art-resume",
        name="result",
        parts=[Part(text="Resumed result")],
    )
    task = Task(id="task-resume", context_id="ctx-r", status=status, artifacts=[artifact])
    mock_a2a_client.subscribe_responses.append(StreamResponse(task=task))

    token = A2AContinuationToken(task_id="task-resume", context_id="ctx-r")
    response = await a2a_agent.run(continuation_token=token)

    assert isinstance(response, AgentResponse)
    assert len(response.messages) == 1
    assert response.messages[0].text == "Resumed result"
    assert response.continuation_token is None


async def test_resume_streaming_via_continuation_token(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that streaming run() with continuation_token and background=True uses resubscribe."""
    # Still working
    status_wip = TaskStatus(state=TaskState.TASK_STATE_WORKING, message=None)
    task_wip = Task(id="task-rs", context_id="ctx-rs", status=status_wip)
    # Then completed
    status_done = TaskStatus(state=TaskState.TASK_STATE_COMPLETED, message=None)
    artifact = Artifact(
        artifact_id="art-rs",
        name="result",
        parts=[Part(text="Stream resumed")],
    )
    task_done = Task(id="task-rs", context_id="ctx-rs", status=status_done, artifacts=[artifact])
    mock_a2a_client.subscribe_responses.extend([StreamResponse(task=task_wip), StreamResponse(task=task_done)])

    token = A2AContinuationToken(task_id="task-rs", context_id="ctx-rs")
    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run(stream=True, continuation_token=token, background=True):
        updates.append(update)

    # First update: in-progress with token, second: completed with content
    assert len(updates) == 2
    assert updates[0].continuation_token is not None
    continuation_payload = cast(dict[str, Any], updates[0].continuation_token)
    assert continuation_payload["task_id"] == "task-rs"
    assert updates[1].continuation_token is None
    assert updates[1].contents[0].text == "Stream resumed"


async def test_poll_task_in_progress(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test poll_task returns continuation token when task is still in progress."""
    status = TaskStatus(state=TaskState.TASK_STATE_WORKING, message=None)
    mock_a2a_client.get_task_response = Task(id="task-poll", context_id="ctx-p", status=status)

    token = A2AContinuationToken(task_id="task-poll", context_id="ctx-p")
    response = await a2a_agent.poll_task(token)

    assert response.continuation_token is not None
    response_token = cast(dict[str, Any], response.continuation_token)
    assert response_token["task_id"] == "task-poll"


async def test_poll_task_completed(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test poll_task returns result with no continuation token when task is complete."""
    status = TaskStatus(state=TaskState.TASK_STATE_COMPLETED, message=None)
    artifact = Artifact(
        artifact_id="art-poll",
        name="result",
        parts=[Part(text="Poll result")],
    )
    mock_a2a_client.get_task_response = Task(
        id="task-poll-done", context_id="ctx-pd", status=status, artifacts=[artifact]
    )

    token = A2AContinuationToken(task_id="task-poll-done", context_id="ctx-pd")
    response = await a2a_agent.poll_task(token)

    assert response.continuation_token is None
    assert len(response.messages) == 1
    assert response.messages[0].text == "Poll result"


# endregion


# region Session context_id Integration Tests


@mark.asyncio
async def test_run_passes_session_service_session_id_as_context_id(mock_a2a_client: MockA2AClient) -> None:
    """Test that run() wires session.service_session_id to the A2A message context_id."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)
    mock_a2a_client.add_message_response("msg-ctx", "reply")

    session = AgentSession(service_session_id="svc-session-42")
    await agent.run("Hello", session=session)

    assert mock_a2a_client.last_message is not None
    assert mock_a2a_client.last_message.context_id == "svc-session-42"


@mark.asyncio
async def test_run_a2a_session_context_id_used_over_service_session_id(mock_a2a_client: MockA2AClient) -> None:
    """Test that A2AAgentSession.context_id is used for outbound messages."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)
    mock_a2a_client.add_message_response("msg-ctx2", "reply")

    session = A2AAgentSession(context_id="a2a-ctx-99")
    await agent.run("Hello", session=session)

    assert mock_a2a_client.last_message is not None
    assert mock_a2a_client.last_message.context_id == "a2a-ctx-99"


# endregion


# region Context Provider Tests


class TrackingContextProvider(ContextProvider):
    """A context provider that records when before_run and after_run are called."""

    def __init__(self) -> None:
        super().__init__(source_id="tracking-provider")
        self.before_run_called = False
        self.after_run_called = False
        self.before_run_context: SessionContext | None = None
        self.after_run_context: SessionContext | None = None

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        self.before_run_called = True
        self.before_run_context = context

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        self.after_run_called = True
        self.after_run_context = context


async def test_run_invokes_context_providers(mock_a2a_client: MockA2AClient) -> None:
    """Test that context providers are invoked during non-streaming run."""
    provider = TrackingContextProvider()
    agent = A2AAgent(
        name="Test Agent",
        client=cast(Any, mock_a2a_client),
        context_providers=[provider],
        http_client=None,
    )
    mock_a2a_client.add_message_response("msg-1", "Hello from A2A")
    session = agent.create_session()

    response = await agent.run("Hello", session=session)

    assert provider.before_run_called
    assert provider.after_run_called
    assert response.text == "Hello from A2A"


async def test_run_streaming_invokes_context_providers(mock_a2a_client: MockA2AClient) -> None:
    """Test that context providers are invoked during streaming run."""
    provider = TrackingContextProvider()
    agent = A2AAgent(
        name="Test Agent",
        client=cast(Any, mock_a2a_client),
        context_providers=[provider],
        http_client=None,
    )
    mock_a2a_client.add_message_response("msg-1", "Streamed response")
    session = agent.create_session()

    stream = agent.run("Hello", stream=True, session=session)
    updates = []
    async for update in stream:
        updates.append(update)

    assert provider.before_run_called
    assert provider.after_run_called
    assert len(updates) == 1
    assert updates[0].text == "Streamed response"


async def test_context_providers_receive_response(mock_a2a_client: MockA2AClient) -> None:
    """Test that after_run providers can access the response via session context."""
    provider = TrackingContextProvider()
    agent = A2AAgent(
        name="Test Agent",
        client=cast(Any, mock_a2a_client),
        context_providers=[provider],
        http_client=None,
    )
    mock_a2a_client.add_message_response("msg-1", "Response text")
    session = agent.create_session()

    await agent.run("Hello", session=session)

    assert provider.after_run_context is not None
    assert provider.after_run_context.response is not None
    assert provider.after_run_context.response.text == "Response text"


async def test_context_providers_receive_input_messages(mock_a2a_client: MockA2AClient) -> None:
    """Test that before_run providers can access input messages via session context."""
    provider = TrackingContextProvider()
    agent = A2AAgent(
        name="Test Agent",
        client=cast(Any, mock_a2a_client),
        context_providers=[provider],
        http_client=None,
    )
    mock_a2a_client.add_message_response("msg-1", "Reply")
    session = agent.create_session()

    await agent.run("Hello world", session=session)

    assert provider.before_run_context is not None
    assert len(provider.before_run_context.input_messages) > 0
    assert provider.before_run_context.input_messages[-1].text == "Hello world"


async def test_run_without_context_providers(mock_a2a_client: MockA2AClient) -> None:
    """Test that run works normally when no context providers are configured."""
    agent = A2AAgent(
        name="Test Agent",
        client=cast(Any, mock_a2a_client),
        http_client=None,
    )
    mock_a2a_client.add_message_response("msg-1", "Hello")

    response = await agent.run("Hello")

    assert response.text == "Hello"


async def test_run_creates_session_for_providers_when_none_provided(mock_a2a_client: MockA2AClient) -> None:
    """Test that a session is auto-created when context providers are configured but no session is passed."""
    provider = TrackingContextProvider()
    agent = A2AAgent(
        name="Test Agent",
        client=cast(Any, mock_a2a_client),
        context_providers=[provider],
        http_client=None,
    )
    mock_a2a_client.add_message_response("msg-1", "Hello")

    await agent.run("Hello")

    assert provider.before_run_called
    assert provider.after_run_called


@mark.parametrize("messages", [None, []])
async def test_run_raises_when_no_messages_and_no_continuation_token(
    mock_a2a_client: MockA2AClient, messages: list[str] | None
) -> None:
    """Test that run() raises ValueError when messages is None/empty and no continuation_token is provided."""
    agent = A2AAgent(
        name="Test Agent",
        client=cast(Any, mock_a2a_client),
        http_client=None,
    )

    with raises(ValueError, match="At least one message is required"):
        await agent.run(messages)


async def test_run_with_continuation_token_does_not_require_messages(mock_a2a_client: MockA2AClient) -> None:
    """Test that run() does not raise when messages is None but a continuation_token is provided."""
    task = Task(
        id="task-cont",
        context_id="ctx-cont",
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED, message=None),
    )
    mock_a2a_client.subscribe_responses.append(StreamResponse(task=task))

    agent = A2AAgent(
        name="Test Agent",
        client=cast(Any, mock_a2a_client),
        http_client=None,
    )

    token = A2AContinuationToken(task_id="task-cont", context_id="ctx-cont")
    response = await agent.run(None, continuation_token=token)
    assert response is not None


# endregion

# region Streaming with in-progress message content


async def test_streaming_working_updates_yield_message_content(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that streaming working updates with status.message yield content."""
    mock_a2a_client.add_in_progress_task_response("task-w", context_id="ctx-w", text="Processing step 1...")
    mock_a2a_client.add_in_progress_task_response("task-w", context_id="ctx-w", text="Processing step 2...")
    mock_a2a_client.add_task_response("task-w", [{"id": "art-w", "content": "Final result"}])

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 3
    assert updates[0].contents[0].text == "Processing step 1..."
    assert updates[1].contents[0].text == "Processing step 2..."
    assert updates[2].contents[0].text == "Final result"


async def test_streaming_single_working_update_with_message(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that a single working update with message content is not dropped."""
    mock_a2a_client.add_in_progress_task_response("task-s", context_id="ctx-s", text="Thinking...")
    mock_a2a_client.add_task_response("task-s", [{"id": "art-s", "content": "Done"}])

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 2
    assert updates[0].contents[0].text == "Thinking..."
    assert updates[0].role == "assistant"
    assert updates[1].contents[0].text == "Done"


async def test_streaming_working_update_without_message_is_skipped(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that working updates without status.message are still silently skipped."""
    mock_a2a_client.add_in_progress_task_response("task-n", context_id="ctx-n")
    mock_a2a_client.add_task_response("task-n", [{"id": "art-n", "content": "Result"}])

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 1
    assert updates[0].contents[0].text == "Result"


async def test_streaming_working_update_user_role_mapping(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that A2ARole.ROLE_USER in status message maps to role='user'."""
    mock_a2a_client.add_in_progress_task_response(
        "task-u", context_id="ctx-u", text="User echo", role=A2ARole.ROLE_USER
    )
    mock_a2a_client.add_task_response("task-u", [{"id": "art-u", "content": "Done"}])

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 2
    assert updates[0].contents[0].text == "User echo"
    assert updates[0].role == "user"


async def test_background_with_status_message_yields_continuation_token(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that background=True takes precedence over status message content."""
    mock_a2a_client.add_in_progress_task_response("task-bg", context_id="ctx-bg", text="Should be ignored")

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True, background=True):
        updates.append(update)

    assert len(updates) == 1
    assert updates[0].continuation_token is not None
    token = cast(dict[str, Any], updates[0].continuation_token)
    assert token["task_id"] == "task-bg"
    assert updates[0].contents == []


async def test_non_streaming_does_not_surface_intermediate_messages(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that run(stream=False) does not include intermediate status messages."""
    mock_a2a_client.add_in_progress_task_response("task-ns", context_id="ctx-ns", text="Intermediate")
    mock_a2a_client.add_task_response("task-ns", [{"id": "art-ns", "content": "Final"}])

    response = await a2a_agent.run("Hello")

    assert len(response.messages) == 1
    assert response.messages[0].text == "Final"


async def test_terminal_no_artifacts_after_working_with_content(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that a terminal task with no artifacts after working-state messages does not re-emit the working content."""
    mock_a2a_client.add_in_progress_task_response("task-t", context_id="ctx-t", text="Working on it...")
    # Terminal task with no artifacts and no history
    status = TaskStatus(state=TaskState.TASK_STATE_COMPLETED, message=None)
    task = Task(id="task-t", context_id="ctx-t", status=status)
    mock_a2a_client.responses.append(StreamResponse(task=task))

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 2
    assert updates[0].contents[0].text == "Working on it..."
    # Terminal task with no artifacts yields an empty-contents update
    assert updates[1].contents == []


async def test_streaming_working_update_with_empty_parts_is_skipped(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that a working update with status.message but empty parts list is skipped."""
    # Construct a message with an empty parts list (distinct from message=None)
    message = A2AMessage(
        message_id=str(uuid4()),
        role=A2ARole.ROLE_AGENT,
        parts=[],
    )
    status = TaskStatus(state=TaskState.TASK_STATE_WORKING, message=message)
    task = Task(id="task-ep", context_id="ctx-ep", status=status)
    mock_a2a_client.responses.append(StreamResponse(task=task))
    mock_a2a_client.add_task_response("task-ep", [{"id": "art-ep", "content": "Result"}])

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 1
    assert updates[0].contents[0].text == "Result"


async def test_streaming_artifact_update_event_yields_content(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that streaming artifact update events yield incremental content."""
    artifact = Artifact(
        artifact_id="artifact-1",
        parts=[Part(text="Hello")],
    )
    update_event = TaskArtifactUpdateEvent(task_id="task-art", context_id="ctx-art", artifact=artifact, append=False)
    mock_a2a_client.responses.append(StreamResponse(artifact_update=update_event))

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 1
    assert updates[0].text == "Hello"
    assert updates[0].message_id == "artifact-1"
    assert updates[0].raw_representation == update_event


async def test_streaming_status_update_event_yields_content(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that streaming status update events surface content for terminal/input-required states only."""
    # COMPLETED state should yield content (terminal)
    update_event = TaskStatusUpdateEvent(
        task_id="task-status",
        context_id="ctx-status",
        status=TaskStatus(
            state=TaskState.TASK_STATE_COMPLETED,
            message=A2AMessage(
                message_id="msg-status-done",
                role=A2ARole.ROLE_AGENT,
                parts=[Part(text="Done")],
            ),
        ),
    )
    mock_a2a_client.responses.append(StreamResponse(status_update=update_event))

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 1
    assert updates[0].text == "Done"
    assert updates[0].role == "assistant"
    assert updates[0].message_id == "msg-status-done"
    assert updates[0].raw_representation == update_event


@mark.asyncio
async def test_streaming_input_required_emits_content(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that input-required status updates emit content (gated states that pass through)."""
    update_event = TaskStatusUpdateEvent(
        task_id="task-status",
        context_id="ctx-status",
        status=TaskStatus(
            state=TaskState.TASK_STATE_INPUT_REQUIRED,
            message=A2AMessage(
                message_id="msg-input-req",
                role=A2ARole.ROLE_AGENT,
                parts=[Part(text="What is your name?")],
            ),
        ),
    )
    mock_a2a_client.responses.append(StreamResponse(status_update=update_event))

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 1
    assert updates[0].text == "What is your name?"
    assert updates[0].message_id == "msg-input-req"


@mark.asyncio
async def test_streaming_working_status_gates_content(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test that intermediate WORKING status updates do NOT emit content (gated like .NET)."""
    update_event = TaskStatusUpdateEvent(
        task_id="task-status",
        context_id="ctx-status",
        status=TaskStatus(
            state=TaskState.TASK_STATE_WORKING,
            message=A2AMessage(
                message_id=str(uuid4()),
                role=A2ARole.ROLE_AGENT,
                parts=[Part(text="Processing...")],
            ),
        ),
    )
    mock_a2a_client.responses.append(StreamResponse(status_update=update_event))

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 0


async def test_streaming_artifact_update_event_does_not_duplicate_terminal_task_artifacts(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that streamed artifact chunks are not re-emitted from the final terminal task."""
    first_chunk = TaskArtifactUpdateEvent(
        task_id="task-art-dup",
        context_id="ctx-art-dup",
        artifact=Artifact(
            artifact_id="artifact-dup",
            parts=[Part(text="Hello ")],
        ),
        append=False,
    )
    second_chunk = TaskArtifactUpdateEvent(
        task_id="task-art-dup",
        context_id="ctx-art-dup",
        artifact=Artifact(
            artifact_id="artifact-dup",
            parts=[Part(text="world")],
        ),
        append=True,
    )
    terminal_task = Task(
        id="task-art-dup",
        context_id="ctx-art-dup",
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        artifacts=[
            Artifact(
                artifact_id="artifact-dup",
                parts=[Part(text="Hello world")],
            )
        ],
    )

    mock_a2a_client.responses.extend([
        StreamResponse(artifact_update=first_chunk),
        StreamResponse(artifact_update=second_chunk),
        StreamResponse(task=terminal_task),
    ])

    stream = a2a_agent.run("Hello", stream=True)
    updates: list[AgentResponseUpdate] = []
    async for update in stream:
        updates.append(update)
    response = await stream.get_final_response()

    assert [update.text for update in updates] == ["Hello ", "world"]
    assert response.text == "Hello world"
    assert len(response.messages) == 1


async def test_streaming_terminal_task_artifacts_are_emitted_when_terminal_event_has_no_content(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that terminal task artifacts are still emitted when the final status event has no message."""
    terminal_task = Task(
        id="task-art-final",
        context_id="ctx-art-final",
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        artifacts=[
            Artifact(
                artifact_id="artifact-final",
                parts=[Part(text="Final artifact")],
            )
        ],
    )
    mock_a2a_client.responses.append(StreamResponse(task=terminal_task))

    updates: list[AgentResponseUpdate] = []
    async for update in a2a_agent.run("Hello", stream=True):
        updates.append(update)

    assert len(updates) == 1
    assert updates[0].text == "Final artifact"
    assert updates[0].message_id == "artifact-final"


async def test_streaming_terminal_task_only_emits_unstreamed_artifacts(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Test that the terminal task only emits artifacts that were not already streamed incrementally."""
    streamed_chunk = TaskArtifactUpdateEvent(
        task_id="task-art-mixed",
        context_id="ctx-art-mixed",
        artifact=Artifact(
            artifact_id="artifact-streamed",
            parts=[Part(text="Hello")],
        ),
        append=False,
    )
    terminal_task = Task(
        id="task-art-mixed",
        context_id="ctx-art-mixed",
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        artifacts=[
            Artifact(
                artifact_id="artifact-streamed",
                parts=[Part(text="Hello")],
            ),
            Artifact(
                artifact_id="artifact-final",
                parts=[Part(text="Goodbye")],
            ),
        ],
    )

    mock_a2a_client.responses.extend([
        StreamResponse(artifact_update=streamed_chunk),
        StreamResponse(task=terminal_task),
    ])

    stream = a2a_agent.run("Hello", stream=True)
    updates: list[AgentResponseUpdate] = []
    async for update in stream:
        updates.append(update)
    response = await stream.get_final_response()

    assert [update.text for update in updates] == ["Hello", "Goodbye"]
    assert [message.text for message in response.messages] == ["Hello", "Goodbye"]


# endregion

# region Metadata propagation tests


async def test_message_metadata_propagated(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """A2AMessage.metadata should appear on response.additional_properties."""
    msg = A2AMessage(
        message_id="msg-meta",
        role=A2ARole.ROLE_AGENT,
        parts=[Part(text="hi")],
        metadata={"source": "server", "trace_id": "abc"},
    )
    mock_a2a_client.responses.append(StreamResponse(message=msg))

    response = await a2a_agent.run("hello")
    assert response.additional_properties["a2a_metadata"]["source"] == "server"
    assert response.additional_properties["a2a_metadata"]["trace_id"] == "abc"


async def test_artifact_metadata_propagated(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Artifact.metadata should appear on response.additional_properties."""
    task = Task(
        id="task-art-meta",
        context_id="ctx",
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        artifacts=[
            Artifact(
                artifact_id="a1",
                parts=[Part(text="result")],
                metadata={"artifact_key": "artifact_value"},
            ),
        ],
    )
    mock_a2a_client.responses.append(StreamResponse(task=task))

    response = await a2a_agent.run("go")
    assert response.additional_properties["a2a_metadata"]["artifact_key"] == "artifact_value"


async def test_task_metadata_propagated_to_response(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Task.metadata should appear on response.additional_properties for terminal tasks."""
    task = Task(
        id="task-meta",
        context_id="ctx",
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        artifacts=[
            Artifact(artifact_id="a1", parts=[Part(text="done")]),
        ],
        metadata={"task_key": "task_value"},
    )
    mock_a2a_client.responses.append(StreamResponse(task=task))

    response = await a2a_agent.run("go")
    assert response.additional_properties["a2a_metadata"]["task_key"] == "task_value"


async def test_task_artifact_update_event_metadata_merged(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """TaskArtifactUpdateEvent and Artifact metadata should both appear on the streaming update."""
    artifact_event = TaskArtifactUpdateEvent(
        task_id="task-ae",
        context_id="ctx",
        artifact=Artifact(
            artifact_id="a1",
            parts=[Part(text="chunk")],
            metadata={"from_artifact": True},
        ),
        metadata={"from_event": True},
    )
    terminal_task = Task(
        id="task-ae",
        context_id="ctx",
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        artifacts=[
            Artifact(artifact_id="a1", parts=[Part(text="chunk")]),
        ],
    )
    mock_a2a_client.responses.extend([
        StreamResponse(artifact_update=artifact_event),
        StreamResponse(task=terminal_task),
    ])

    stream = a2a_agent.run("hello", stream=True)
    updates: list[AgentResponseUpdate] = []
    async for update in stream:
        updates.append(update)

    artifact_update = updates[0]
    assert artifact_update.additional_properties is not None
    metadata = artifact_update.additional_properties["a2a_metadata"]
    assert metadata["from_artifact"] is True
    assert metadata["from_event"] is True


async def test_task_status_update_event_metadata_merged(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """TaskStatusUpdateEvent and its message metadata should both appear on the streaming update."""
    status_event = TaskStatusUpdateEvent(
        task_id="task-se",
        context_id="ctx",
        status=TaskStatus(
            state=TaskState.TASK_STATE_INPUT_REQUIRED,
            message=A2AMessage(
                message_id="m1",
                role=A2ARole.ROLE_AGENT,
                parts=[Part(text="need input")],
                metadata={"msg_key": "msg_val"},
            ),
        ),
        metadata={"event_key": "event_val"},
    )
    mock_a2a_client.responses.append(StreamResponse(status_update=status_event))

    stream = a2a_agent.run("hello", stream=True)
    updates: list[AgentResponseUpdate] = []
    async for update in stream:
        updates.append(update)

    status_update = updates[0]
    assert status_update.additional_properties is not None
    metadata = status_update.additional_properties["a2a_metadata"]
    assert metadata["msg_key"] == "msg_val"
    assert metadata["event_key"] == "event_val"


async def test_history_message_metadata_propagated(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Metadata on a history Message should appear on response.additional_properties."""
    task = Task(
        id="task-hist",
        context_id="ctx",
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        history=[
            A2AMessage(
                message_id="h1",
                role=A2ARole.ROLE_AGENT,
                parts=[Part(text="reply")],
                metadata={"history_key": "history_value"},
            ),
        ],
    )
    mock_a2a_client.responses.append(StreamResponse(task=task))

    response = await a2a_agent.run("go")
    assert response.additional_properties["a2a_metadata"]["history_key"] == "history_value"


async def test_continuation_token_update_carries_task_metadata(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """In-progress tasks with background=True should propagate task metadata."""
    task = Task(
        id="task-cont",
        context_id="ctx",
        status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
        metadata={"bg_key": "bg_value"},
    )
    mock_a2a_client.responses.append(StreamResponse(task=task))

    response = await a2a_agent.run("go", background=True)
    assert response.continuation_token is not None
    assert response.additional_properties["a2a_metadata"]["bg_key"] == "bg_value"


async def test_none_metadata_leaves_additional_properties_empty(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """When A2A types have no metadata, additional_properties should remain empty/default."""
    msg = A2AMessage(
        message_id="msg-none",
        role=A2ARole.ROLE_AGENT,
        parts=[Part(text="no meta")],
    )
    mock_a2a_client.responses.append(StreamResponse(message=msg))

    response = await a2a_agent.run("hello")
    assert not response.additional_properties


async def test_non_streaming_terminal_status_update_surfaces_content(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Non-streaming run() should surface content from terminal status_update events."""
    completed_msg = A2AMessage(
        message_id="msg-complete",
        role=A2ARole.ROLE_AGENT,
        parts=[Part(text="Done! Here is your answer.")],
    )
    status = TaskStatus(state=TaskState.TASK_STATE_COMPLETED, message=completed_msg)
    event = TaskStatusUpdateEvent(task_id="task-ts", context_id="ctx-ts", status=status)
    mock_a2a_client.responses.append(StreamResponse(status_update=event))

    response = await a2a_agent.run("Hello")

    assert len(response.messages) == 1
    assert response.messages[0].text == "Done! Here is your answer."


async def test_non_streaming_working_content_gated(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Non-streaming: WORKING status content is gated and not surfaced to callers."""
    # Intermediate WORKING event with content — should be gated
    working_msg = A2AMessage(
        message_id="msg-working",
        role=A2ARole.ROLE_AGENT,
        parts=[Part(text="Here is your answer from working state.")],
    )
    working_status = TaskStatus(state=TaskState.TASK_STATE_WORKING, message=working_msg)
    working_event = TaskStatusUpdateEvent(task_id="task-acc", context_id="ctx-acc", status=working_status)
    mock_a2a_client.responses.append(StreamResponse(status_update=working_event))

    # Terminal COMPLETED event with NO content
    completed_status = TaskStatus(state=TaskState.TASK_STATE_COMPLETED)
    completed_event = TaskStatusUpdateEvent(task_id="task-acc", context_id="ctx-acc", status=completed_status)
    mock_a2a_client.responses.append(StreamResponse(status_update=completed_event))

    response = await a2a_agent.run("Hello")

    # WORKING content is gated — nothing to accumulate or flush
    assert len(response.messages) == 0


async def test_non_streaming_intermediate_discarded_when_terminal_has_content(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Non-streaming: if terminal event has content, intermediate content is discarded."""
    # Intermediate WORKING event
    working_msg = A2AMessage(
        message_id="msg-working",
        role=A2ARole.ROLE_AGENT,
        parts=[Part(text="Still thinking...")],
    )
    working_status = TaskStatus(state=TaskState.TASK_STATE_WORKING, message=working_msg)
    working_event = TaskStatusUpdateEvent(task_id="task-wi", context_id="ctx-wi", status=working_status)
    mock_a2a_client.responses.append(StreamResponse(status_update=working_event))

    # Terminal COMPLETED event WITH content
    completed_msg = A2AMessage(
        message_id="msg-final",
        role=A2ARole.ROLE_AGENT,
        parts=[Part(text="Final answer")],
    )
    completed_status = TaskStatus(state=TaskState.TASK_STATE_COMPLETED, message=completed_msg)
    completed_event = TaskStatusUpdateEvent(task_id="task-wi", context_id="ctx-wi", status=completed_status)
    mock_a2a_client.responses.append(StreamResponse(status_update=completed_event))

    response = await a2a_agent.run("Hello")

    # Terminal content supersedes accumulated intermediates
    assert len(response.messages) == 1
    assert response.messages[0].text == "Final answer"


async def test_non_streaming_artifact_update_surfaces_content(
    a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient
) -> None:
    """Non-streaming run() should surface content from artifact_update events."""
    artifact = Artifact(
        artifact_id="art-ns",
        parts=[Part(text="Artifact content")],
    )
    event = TaskArtifactUpdateEvent(task_id="task-anu", context_id="ctx-anu", artifact=artifact, append=False)
    mock_a2a_client.responses.append(StreamResponse(artifact_update=event))

    # Terminal task with the same artifact ID — should be deduped
    mock_a2a_client.add_task_response("task-anu", [{"id": "art-ns", "content": "Artifact content"}])

    response = await a2a_agent.run("Hello")

    # Artifact update + terminal task with same artifact ID = content emitted once from
    # the artifact_update, then the duplicate from the task is filtered by streamed_artifact_ids
    assert len(response.messages) == 1
    assert response.messages[0].text == "Artifact content"


# endregion


# region Reference Task IDs Tests


@mark.asyncio
async def test_first_message_has_no_reference_task_ids(mock_a2a_client: MockA2AClient) -> None:
    """Test that the first message sent has no reference_task_ids."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)
    mock_a2a_client.add_task_response("task-first", [{"content": "Hello back"}])

    session = A2AAgentSession()
    await agent.run("Hello", session=session)

    assert mock_a2a_client.last_message is not None
    assert list(mock_a2a_client.last_message.reference_task_ids) == []


@mark.asyncio
async def test_follow_up_message_includes_reference_task_ids(mock_a2a_client: MockA2AClient) -> None:
    """Test that a follow-up message references the previous task_id."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)
    mock_a2a_client.add_task_response("task-abc-123", [{"content": "First reply"}])

    session = A2AAgentSession()
    await agent.run("Hello", session=session)

    # Verify task_id was persisted on session
    assert session.task_id == "task-abc-123"

    # Send a follow-up message
    mock_a2a_client.add_task_response("task-def-456", [{"content": "Second reply"}])
    await agent.run("Follow up", session=session)

    assert mock_a2a_client.last_message is not None
    assert list(mock_a2a_client.last_message.reference_task_ids) == ["task-abc-123"]


@mark.asyncio
async def test_reference_task_ids_updated_after_each_interaction(mock_a2a_client: MockA2AClient) -> None:
    """Test that reference_task_ids always points to the most recent task."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)

    session = A2AAgentSession()

    # First interaction
    mock_a2a_client.add_task_response("task-1", [{"content": "Reply 1"}])
    await agent.run("Message 1", session=session)
    assert session.task_id == "task-1"

    # Second interaction
    mock_a2a_client.add_task_response("task-2", [{"content": "Reply 2"}])
    await agent.run("Message 2", session=session)
    assert mock_a2a_client.last_message.reference_task_ids == ["task-1"]
    assert session.task_id == "task-2"

    # Third interaction references the second task
    mock_a2a_client.add_task_response("task-3", [{"content": "Reply 3"}])
    await agent.run("Message 3", session=session)
    assert mock_a2a_client.last_message.reference_task_ids == ["task-2"]
    assert session.task_id == "task-3"


@mark.asyncio
async def test_task_id_tracked_from_status_update_events(mock_a2a_client: MockA2AClient) -> None:
    """Test that task_id is tracked even when response only contains status update events."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)

    # Simulate a stream that only has status_update events (no full task payload)
    status_event = TaskStatusUpdateEvent(
        task_id="task-from-status",
        context_id="ctx-1",
        status=TaskStatus(
            state=TaskState.TASK_STATE_COMPLETED,
            message=A2AMessage(
                message_id="msg-status",
                role=A2ARole.ROLE_AGENT,
                parts=[Part(text="Done")],
            ),
        ),
    )
    mock_a2a_client.responses.append(StreamResponse(status_update=status_event))

    session = A2AAgentSession()
    await agent.run("Hello", session=session)

    assert session.task_id == "task-from-status"
    assert session.task_state == TaskState.TASK_STATE_COMPLETED


@mark.asyncio
async def test_no_session_does_not_crash_reference_task_ids(mock_a2a_client: MockA2AClient) -> None:
    """Test that running without a session (no reference tracking) works fine."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)
    mock_a2a_client.add_task_response("task-no-session", [{"content": "Reply"}])

    # Should not raise — no session means no reference_task_ids
    response = await agent.run("Hello")
    assert response is not None
    assert mock_a2a_client.last_message.reference_task_ids == []


@mark.asyncio
async def test_task_id_not_tracked_from_message_payload(mock_a2a_client: MockA2AClient) -> None:
    """Test that task_id is NOT tracked from message payloads (simple interactions without task tracking)."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)

    # Simulate a response that is a message with task_id set (no task/status_update events).
    # Per A2A spec, a Message response indicates simple interaction — task_id should not be persisted.
    message_with_task = A2AMessage(
        message_id="msg-with-task",
        role=A2ARole.ROLE_AGENT,
        parts=[Part(text="Response")],
        task_id="task-from-message",
    )
    mock_a2a_client.responses.append(StreamResponse(message=message_with_task))

    session = A2AAgentSession()
    await agent.run("Hello", session=session)

    assert session.task_id is None


@mark.asyncio
async def test_context_id_assigned_from_response(mock_a2a_client: MockA2AClient) -> None:
    """Test that context_id is assigned from the response when not set on session."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)
    mock_a2a_client.add_task_response("task-ctx", [{"content": "Reply"}])

    session = A2AAgentSession()
    assert session.context_id is None

    await agent.run("Hello", session=session)

    # context_id from the task response should be assigned
    assert session.context_id == "test-context"
    assert session.service_session_id == A2AServiceSessionId(
        context_id="test-context",
        task_id="task-ctx",
        task_state=TaskState.TASK_STATE_COMPLETED,
    )


@mark.asyncio
async def test_context_id_tracked_from_message_payload(mock_a2a_client: MockA2AClient) -> None:
    """Test that context_id is captured from message-only responses (no task payload)."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)

    # Simulate a response with only a message that has context_id but no task_id
    message_with_context = A2AMessage(
        message_id="msg-ctx-only",
        role=A2ARole.ROLE_AGENT,
        parts=[Part(text="Hello!")],
        context_id="server-ctx-123",
    )
    mock_a2a_client.responses.append(StreamResponse(message=message_with_context))

    session = A2AAgentSession()
    await agent.run("Hi", session=session)

    # context_id should be captured even without a task_id
    assert session.context_id == "server-ctx-123"
    assert session.service_session_id == A2AServiceSessionId(
        context_id="server-ctx-123",
        task_id=None,
        task_state=None,
    )
    assert session.task_id is None


@mark.asyncio
async def test_context_id_mismatch_raises_error(mock_a2a_client: MockA2AClient) -> None:
    """Test that a context_id mismatch between session and response raises an error."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)

    # Task response has context_id="test-context" (from add_task_response helper)
    mock_a2a_client.add_task_response("task-mismatch", [{"content": "Reply"}])

    # Session already has a different context_id
    session = A2AAgentSession(context_id="different-context")

    with raises(RuntimeError, match="differs from the session's context_id"):
        await agent.run("Hello", session=session)


@mark.asyncio
async def test_task_state_tracked_on_session(mock_a2a_client: MockA2AClient) -> None:
    """Test that task_state is tracked on A2AAgentSession."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)

    # Add a task that ends in INPUT_REQUIRED
    mock_a2a_client.add_in_progress_task_response(
        "task-input",
        context_id="ctx-input",
        state=TaskState.TASK_STATE_INPUT_REQUIRED,
        text="What is your name?",
    )

    session = A2AAgentSession()
    await agent.run("Start", session=session)

    assert session.task_id == "task-input"
    assert session.task_state == TaskState.TASK_STATE_INPUT_REQUIRED


@mark.asyncio
async def test_plain_agent_session_tracks_structured_service_session_id(mock_a2a_client: MockA2AClient) -> None:
    """Plain AgentSession should persist A2A continuation state in structured service_session_id."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)
    mock_a2a_client.add_task_response("task-plain", [{"content": "Reply"}])

    session = AgentSession()
    await agent.run("Hello", session=session)

    assert session.service_session_id == A2AServiceSessionId(
        context_id="test-context",
        task_id="task-plain",
        task_state=TaskState.TASK_STATE_COMPLETED,
    )

    # Follow-up should use the tracked task_id in reference_task_ids
    mock_a2a_client.add_task_response("task-plain-2", [{"content": "Reply 2"}])
    await agent.run("Follow up", session=session)
    assert list(mock_a2a_client.last_message.reference_task_ids) == ["task-plain"]


@mark.asyncio
async def test_a2a_agent_session_serialization() -> None:
    """Test A2AAgentSession serialization and deserialization."""
    session = A2AAgentSession(
        context_id="ctx-456",
        task_id="task-789",
        task_state=TaskState.TASK_STATE_COMPLETED,
    )

    data = session.to_dict()
    restored = A2AAgentSession.from_dict(data)

    assert restored.session_id == session.session_id
    assert restored.context_id == "ctx-456"
    assert restored.task_id == "task-789"
    assert restored.task_state == TaskState.TASK_STATE_COMPLETED
    assert restored.service_session_id == A2AServiceSessionId(
        context_id="ctx-456",
        task_id="task-789",
        task_state=TaskState.TASK_STATE_COMPLETED,
    )


@mark.asyncio
async def test_plain_agent_session_structured_service_session_id_for_input_required(
    mock_a2a_client: MockA2AClient,
) -> None:
    """Structured service_session_id should drive INPUT_REQUIRED follow-up task_id behavior."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)
    session = AgentSession(
        service_session_id=A2AServiceSessionId(
            context_id="ctx-ir",
            task_id="task-ir-123",
            task_state=TaskState.TASK_STATE_INPUT_REQUIRED,
        )
    )

    mock_a2a_client.add_in_progress_task_response(
        "task-ir-456",
        context_id="ctx-ir",
        state=TaskState.TASK_STATE_COMPLETED,
        text="Thanks!",
    )
    await agent.run("My name is Alice", session=session)

    last_msg = mock_a2a_client.last_message
    assert last_msg.task_id == "task-ir-123"
    assert list(last_msg.reference_task_ids) == []


def test_a2a_agent_otel_conversation_id_uses_context_id() -> None:
    """Telemetry conversation id should map to context_id for structured A2A sessions."""
    agent = A2AAgent(client=MagicMock(), http_client=None)
    session = AgentSession(
        service_session_id=A2AServiceSessionId(
            context_id="ctx-otel",
            task_id="task-otel",
            task_state=TaskState.TASK_STATE_WORKING,
        )
    )

    assert agent._get_otel_conversation_id(session) == "ctx-otel"


@mark.asyncio
async def test_input_required_sets_task_id_instead_of_reference(mock_a2a_client: MockA2AClient) -> None:
    """Test that when task_state is INPUT_REQUIRED, follow-up sets task_id (not reference_task_ids)."""
    agent = A2AAgent(name="Test Agent", id="test-agent", client=cast(Any, mock_a2a_client), http_client=None)

    # First turn: task ends in INPUT_REQUIRED
    mock_a2a_client.add_in_progress_task_response(
        "task-ir",
        context_id="ctx-ir",
        state=TaskState.TASK_STATE_INPUT_REQUIRED,
        text="What is your name?",
    )

    session = A2AAgentSession()
    await agent.run("Start", session=session)

    assert session.task_state == TaskState.TASK_STATE_INPUT_REQUIRED
    assert session.task_id == "task-ir"

    # Second turn: follow-up should set task_id (not reference_task_ids)
    mock_a2a_client.add_in_progress_task_response(
        "task-ir-2", context_id="ctx-ir", state=TaskState.TASK_STATE_COMPLETED, text="Thanks!"
    )
    await agent.run("My name is Alice", session=session)

    # The outbound message should have task_id set, not reference_task_ids
    last_msg = mock_a2a_client.last_message
    assert last_msg.task_id == "task-ir"
    assert list(last_msg.reference_task_ids) == []


# endregion
