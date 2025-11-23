# Copyright (c) Microsoft. All rights reserved.

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState
from agent_framework import ChatMessage, DataContent, Role, TextContent, UriContent
from agent_framework.a2a import BaseA2aEventAdapter


class TestBaseA2aEventAdapter:
    """Tests for BaseA2aEventAdapter.handle_events method."""

    @pytest.fixture
    def adapter(self) -> BaseA2aEventAdapter:
        """Create a BaseA2aEventAdapter instance."""
        return BaseA2aEventAdapter()

    @pytest.fixture
    def mock_updater(self) -> TaskUpdater:
        """Create a mock execution context."""
        updater = MagicMock()
        updater.update_status = AsyncMock()
        updater.new_agent_message = MagicMock(return_value="mock_message")
        return updater

    @pytest.mark.asyncio
    async def test_ignore_user_messages(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test that messages from USER role are ignored."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="User input")],
            role=Role.USER,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignore_messages_with_no_contents(
        self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock
    ) -> None:
        """Test that messages with no contents are ignored."""
        # Arrange
        message = ChatMessage(
            contents=[],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_text_content(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test handling messages with text content."""
        # Arrange
        text = "Hello, this is a test message"
        message = ChatMessage(
            contents=[TextContent(text=text)],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_args = mock_updater.update_status.call_args
        assert call_args.kwargs["state"] == TaskState.working
        assert mock_updater.new_agent_message.called

    @pytest.mark.asyncio
    async def test_handle_multiple_text_contents(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test handling messages with multiple text contents."""
        # Arrange
        message = ChatMessage(
            contents=[
                TextContent(text="First message"),
                TextContent(text="Second message"),
            ],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        assert mock_updater.new_agent_message.called

    @pytest.mark.asyncio
    async def test_handle_data_content(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test handling messages with data content."""
        # Arrange
        data = b"test file data"
        base64_data = base64.b64encode(data).decode("utf-8")
        data_uri = f"data:application/octet-stream;base64,{base64_data}"

        message = ChatMessage(
            contents=[DataContent(uri=data_uri)],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_args = mock_updater.update_status.call_args
        assert call_args.kwargs["state"] == TaskState.working

    @pytest.mark.asyncio
    async def test_handle_uri_content(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test handling messages with URI content."""
        # Arrange
        uri = "https://example.com/file.pdf"
        message = ChatMessage(
            contents=[UriContent(uri=uri, media_type="pdf")],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_args = mock_updater.update_status.call_args
        assert call_args.kwargs["state"] == TaskState.working

    @pytest.mark.asyncio
    async def test_handle_uri_content_with_media_type(
        self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock
    ) -> None:
        """Test handling messages with URI content that includes media type."""
        # Arrange
        uri = "https://example.com/image.jpg"
        message = ChatMessage(
            contents=[UriContent(uri=uri, media_type="image/jpeg")],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_mixed_content_types(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test handling messages with mixed content types."""
        # Arrange
        data = b"file data"
        base64_data = base64.b64encode(data).decode("utf-8")
        data_uri = f"data:application/octet-stream;base64,{base64_data}"

        message = ChatMessage(
            contents=[
                TextContent(text="Processing file..."),
                DataContent(uri=data_uri),
                UriContent(uri="https://example.com/reference.pdf", media_type="pdf"),
            ],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_args = mock_updater.update_status.call_args
        assert call_args.kwargs["state"] == TaskState.working
        # Verify all parts were created
        new_agent_message_call = mock_updater.new_agent_message.call_args
        assert new_agent_message_call is not None

    @pytest.mark.asyncio
    async def test_handle_with_additional_properties(
        self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock
    ) -> None:
        """Test handling messages with additional properties metadata."""
        # Arrange
        additional_props = {"custom_field": "custom_value", "priority": "high"}
        message = ChatMessage(
            contents=[TextContent(text="Test message")],
            role=Role.ASSISTANT,
            additional_properties=additional_props,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        mock_updater.new_agent_message.assert_called_once()
        call_args = mock_updater.new_agent_message.call_args
        assert call_args.kwargs["metadata"] == additional_props

    @pytest.mark.asyncio
    async def test_handle_with_no_additional_properties(
        self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock
    ) -> None:
        """Test handling messages without additional properties."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="Test message")],
            role=Role.ASSISTANT,
            additional_properties=None,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        mock_updater.new_agent_message.assert_called_once()
        call_args = mock_updater.new_agent_message.call_args
        assert call_args.kwargs["metadata"] == {}

    @pytest.mark.asyncio
    async def test_parts_list_passed_to_new_agent_message(
        self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock
    ) -> None:
        """Test that parts list is correctly passed to new_agent_message."""
        # Arrange
        message = ChatMessage(
            contents=[
                TextContent(text="Message 1"),
                TextContent(text="Message 2"),
            ],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.new_agent_message.assert_called_once()
        call_kwargs = mock_updater.new_agent_message.call_args.kwargs
        assert "parts" in call_kwargs
        parts_list = call_kwargs["parts"]
        assert len(parts_list) == 2

    @pytest.mark.asyncio
    async def test_unsupported_content_type_skipped(
        self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock
    ) -> None:
        """Test that unsupported content types are silently skipped."""
        # Arrange
        # Create a message with a valid content and mock an unsupported one
        message = ChatMessage(
            contents=[
                TextContent(text="Valid text"),
            ],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert - should still process the valid text content
        mock_updater.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_update_status_when_no_parts_created(
        self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock
    ) -> None:
        """Test that update_status is not called when no parts are created."""
        # Arrange
        message = ChatMessage(
            contents=[],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_assistant_role(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test handling messages with ASSISTANT role."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="Assistant response")],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_system_role(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test handling messages with SYSTEM role."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="System message")],
            role=Role.SYSTEM,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_empty_text_content(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test handling messages with empty text content."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="")],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_kwargs = mock_updater.new_agent_message.call_args.kwargs
        parts_list = call_kwargs["parts"]
        assert len(parts_list) == 1

    @pytest.mark.asyncio
    async def test_task_state_always_working(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test that task state is always set to working."""
        # Arrange
        message = ChatMessage(
            contents=[TextContent(text="Any message")],
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        call_kwargs = mock_updater.update_status.call_args.kwargs
        assert call_kwargs["state"] == TaskState.working

    @pytest.mark.asyncio
    async def test_large_number_of_contents(self, adapter: BaseA2aEventAdapter, mock_updater: MagicMock) -> None:
        """Test handling messages with a large number of content items."""
        # Arrange
        contents = [TextContent(text=f"Message {i}") for i in range(100)]
        message = ChatMessage(
            contents=contents,
            role=Role.ASSISTANT,
        )

        # Act
        await adapter.handle_events(message, mock_updater)

        # Assert
        mock_updater.update_status.assert_called_once()
        call_kwargs = mock_updater.new_agent_message.call_args.kwargs
        parts_list = call_kwargs["parts"]
        assert len(parts_list) == 100
