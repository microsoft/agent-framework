# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

from pytest import fixture, raises

from agent_framework import AgentRunResponse, ChatMessage, Role
from agent_framework._a2a import A2AAgent


class MockA2AClient:
    """Mock implementation of A2A Client for testing."""

    def __init__(self) -> None:
        self.call_count: int = 0
        self.responses: list[Any] = []

    def add_message_response(self, message_id: str, text: str, role: str = "agent") -> None:
        """Add a mock Message response."""
        from a2a.types import Message, Part, TextPart
        from a2a.types import Role as A2ARole

        # Create actual TextPart instance and wrap it in Part
        text_part = Part(root=TextPart(text=text))

        # Create actual Message instance
        message = Message(
            message_id=message_id, role=A2ARole.agent if role == "agent" else A2ARole.user, parts=[text_part]
        )
        self.responses.append(message)

    def add_task_response(self, task_id: str, artifacts: list[dict[str, Any]]) -> None:
        """Add a mock Task response."""
        from a2a.types import Artifact, Task, TaskState, TaskStatus

        # Create mock artifacts
        mock_artifacts = []
        for artifact_data in artifacts:
            # Create actual TextPart instance and wrap it in Part
            from a2a.types import Part, TextPart

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

    async def send_message(self, message: Any) -> AsyncIterator[Any]:
        """Mock send_message method that yields responses."""
        self.call_count += 1

        if self.responses:
            response = self.responses.pop(0)
            yield response


@fixture
def mock_a2a_client() -> MockA2AClient:
    """Fixture that provides a mock A2A client."""
    return MockA2AClient()


@fixture
def a2a_agent(mock_a2a_client: MockA2AClient) -> A2AAgent:
    """Fixture that provides an A2AAgent with a mock client."""
    return A2AAgent(name="Test Agent", id="test-agent", client=mock_a2a_client)


def test_a2a_agent_initialization_with_client(mock_a2a_client: MockA2AClient) -> None:
    """Test A2AAgent initialization with provided client."""
    agent = A2AAgent(name="Test Agent", id="test-agent-123", description="A test agent", client=mock_a2a_client)

    assert agent.name == "Test Agent"
    assert agent.id == "test-agent-123"
    assert agent.description == "A test agent"
    assert agent._client == mock_a2a_client


def test_a2a_agent_initialization_without_client_raises_error() -> None:
    """Test A2AAgent initialization without client or URL raises ValueError."""
    with raises(ValueError, match="Either agent_card or url must be provided"):
        A2AAgent(name="Test Agent")


async def test_run_with_message_response(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test run() method with immediate Message response."""
    mock_a2a_client.add_message_response("msg-123", "Hello from agent!", "agent")

    response = await a2a_agent.run("Hello agent")

    assert isinstance(response, AgentRunResponse)
    assert len(response.messages) == 1
    assert response.messages[0].role == Role.ASSISTANT
    assert response.messages[0].text == "Hello from agent!"
    assert response.response_id == "msg-123"
    assert mock_a2a_client.call_count == 1


async def test_run_with_task_response_single_artifact(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test run() method with Task response containing single artifact."""
    artifacts = [{"id": "art-1", "content": "Generated report content"}]
    mock_a2a_client.add_task_response("task-456", artifacts)

    response = await a2a_agent.run("Generate a report")

    assert isinstance(response, AgentRunResponse)
    assert len(response.messages) == 1
    assert response.messages[0].role == Role.ASSISTANT
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

    assert isinstance(response, AgentRunResponse)
    assert len(response.messages) == 3

    assert response.messages[0].text == "First artifact content"
    assert response.messages[1].text == "Second artifact content"
    assert response.messages[2].text == "Third artifact content"

    # All should be assistant messages
    for message in response.messages:
        assert message.role == Role.ASSISTANT

    assert response.response_id == "task-789"


async def test_run_with_task_response_no_artifacts(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test run() method with Task response containing no artifacts."""
    mock_a2a_client.add_task_response("task-empty", [])

    response = await a2a_agent.run("Do something with no output")

    assert isinstance(response, AgentRunResponse)
    assert len(response.messages) == 0  # No artifacts = no messages (matching .NET behavior)
    assert response.response_id == "task-empty"


async def test_run_with_unknown_response_type_raises_error(a2a_agent: A2AAgent, mock_a2a_client: MockA2AClient) -> None:
    """Test run() method with unknown response type raises NotImplementedError."""
    mock_a2a_client.responses.append("invalid_response")

    with raises(NotImplementedError, match="Only Message and Task responses are supported"):
        await a2a_agent.run("Test message")


async def test_normalize_messages_string_input(a2a_agent: A2AAgent) -> None:
    """Test _normalize_messages with string input."""
    result = a2a_agent._normalize_messages("Hello")

    assert len(result) == 1
    assert result[0].role == Role.USER
    assert result[0].text == "Hello"


async def test_normalize_messages_chat_message_input(a2a_agent: A2AAgent) -> None:
    """Test _normalize_messages with ChatMessage input."""
    message = ChatMessage(role=Role.USER, text="Test message")
    result = a2a_agent._normalize_messages(message)

    assert len(result) == 1
    assert result[0] == message


async def test_normalize_messages_list_input(a2a_agent: A2AAgent) -> None:
    """Test _normalize_messages with list input."""
    messages = ["First message", ChatMessage(role=Role.USER, text="Second message")]
    result = a2a_agent._normalize_messages(messages)

    assert len(result) == 2
    assert result[0].text == "First message"
    assert result[0].role == Role.USER
    assert result[1].text == "Second message"
    assert result[1].role == Role.USER


async def test_normalize_messages_none_input(a2a_agent: A2AAgent) -> None:
    """Test _normalize_messages with None input."""
    result = a2a_agent._normalize_messages(None)

    assert len(result) == 0


def test_task_to_chat_messages_empty_artifacts(a2a_agent: A2AAgent) -> None:
    """Test _task_to_chat_messages with task containing no artifacts."""
    task = MagicMock()
    task.artifacts = None

    result = a2a_agent._task_to_chat_messages(task)

    assert len(result) == 0


def test_task_to_chat_messages_with_artifacts(a2a_agent: A2AAgent) -> None:
    """Test _task_to_chat_messages with task containing artifacts."""
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

    result = a2a_agent._task_to_chat_messages(task)

    assert len(result) == 2
    assert result[0].text == "Content 1"
    assert result[1].text == "Content 2"
    assert all(msg.role == Role.ASSISTANT for msg in result)


def test_artifact_to_chat_message(a2a_agent: A2AAgent) -> None:
    """Test _artifact_to_chat_message conversion."""
    artifact = MagicMock()
    artifact.artifact_id = "test-artifact"

    text_part = MagicMock()
    text_part.root = MagicMock()
    text_part.root.kind = "text"
    text_part.root.text = "Artifact content"
    text_part.root.metadata = None

    artifact.parts = [text_part]

    result = a2a_agent._artifact_to_chat_message(artifact)

    assert isinstance(result, ChatMessage)
    assert result.role == Role.ASSISTANT
    assert result.text == "Artifact content"
    assert result.raw_representation == artifact


def test_get_uri_data_valid_uri() -> None:
    """Test _get_uri_data with valid data URI."""
    from agent_framework._a2a import _get_uri_data

    uri = "data:application/json;base64,eyJ0ZXN0IjoidmFsdWUifQ=="
    result = _get_uri_data(uri)
    assert result == "eyJ0ZXN0IjoidmFsdWUifQ=="


def test_get_uri_data_invalid_uri() -> None:
    """Test _get_uri_data with invalid URI format."""
    from agent_framework._a2a import _get_uri_data

    with raises(ValueError, match="Invalid data URI format"):
        _get_uri_data("not-a-valid-data-uri")


def test_normalize_messages_empty_list(a2a_agent: A2AAgent) -> None:
    """Test _normalize_messages with empty list."""
    result = a2a_agent._normalize_messages([])
    assert len(result) == 0


def test_a2a_parts_to_contents_conversion(a2a_agent: A2AAgent) -> None:
    """Test A2A parts to contents conversion."""
    from a2a.types import Part, TextPart

    from agent_framework import TextContent

    agent = A2AAgent(name="Test Agent", client=MockA2AClient())

    # Create A2A parts
    parts = [Part(root=TextPart(text="First part")), Part(root=TextPart(text="Second part"))]

    # Convert to contents
    contents = agent._a2a_parts_to_contents(parts)

    # Verify conversion
    assert len(contents) == 2
    assert isinstance(contents[0], TextContent)
    assert isinstance(contents[1], TextContent)
    assert contents[0].text == "First part"
    assert contents[1].text == "Second part"


def test_chat_message_to_a2a_message_with_error_content(a2a_agent: A2AAgent) -> None:
    """Test _chat_message_to_a2a_message with ErrorContent."""
    from agent_framework import ErrorContent

    # Create ChatMessage with ErrorContent
    error_content = ErrorContent(message="Test error message")
    message = ChatMessage(role=Role.USER, contents=[error_content])

    # Convert to A2A message
    a2a_message = a2a_agent._chat_message_to_a2a_message(message)

    # Verify conversion
    assert len(a2a_message.parts) == 1
    assert a2a_message.parts[0].root.text == "Test error message"


def test_chat_message_to_a2a_message_with_uri_content(a2a_agent: A2AAgent) -> None:
    """Test _chat_message_to_a2a_message with UriContent."""
    from agent_framework import UriContent

    # Create ChatMessage with UriContent
    uri_content = UriContent(uri="http://example.com/file.pdf", media_type="application/pdf")
    message = ChatMessage(role=Role.USER, contents=[uri_content])

    # Convert to A2A message
    a2a_message = a2a_agent._chat_message_to_a2a_message(message)

    # Verify conversion
    assert len(a2a_message.parts) == 1
    assert a2a_message.parts[0].root.file.uri == "http://example.com/file.pdf"
    assert a2a_message.parts[0].root.file.mime_type == "application/pdf"


def test_chat_message_to_a2a_message_with_data_content(a2a_agent: A2AAgent) -> None:
    """Test _chat_message_to_a2a_message with DataContent."""
    from agent_framework import DataContent

    # Create ChatMessage with DataContent (base64 data URI)
    data_content = DataContent(uri="data:text/plain;base64,SGVsbG8gV29ybGQ=", media_type="text/plain")
    message = ChatMessage(role=Role.USER, contents=[data_content])

    # Convert to A2A message
    a2a_message = a2a_agent._chat_message_to_a2a_message(message)

    # Verify conversion
    assert len(a2a_message.parts) == 1
    assert a2a_message.parts[0].root.file.bytes == "SGVsbG8gV29ybGQ="
    assert a2a_message.parts[0].root.file.mime_type == "text/plain"


def test_chat_message_to_a2a_message_empty_contents_raises_error(a2a_agent: A2AAgent) -> None:
    """Test _chat_message_to_a2a_message with empty contents raises ValueError."""
    # Create ChatMessage with no contents
    message = ChatMessage(role=Role.USER, contents=[])

    # Should raise ValueError for empty contents
    with raises(ValueError, match="ChatMessage.contents is empty"):
        a2a_agent._chat_message_to_a2a_message(message)
