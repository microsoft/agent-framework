# Copyright (c) Microsoft. All rights reserved.

"""Tests for ChatKit to Agent Framework converter utilities."""

from unittest.mock import Mock

import pytest
from agent_framework import ChatMessage, Role, TextContent
from chatkit.types import UserMessageTextContent

from agent_framework_chatkit import ThreadItemConverter, simple_to_agent_input


class TestThreadItemConverter:
    """Tests for ThreadItemConverter class."""

    @pytest.fixture
    def converter(self):
        """Create a ThreadItemConverter instance for testing."""
        return ThreadItemConverter()

    async def test_to_agent_input_none(self, converter):
        """Test converting empty list returns empty list."""
        result = await converter.to_agent_input([])
        assert result == []

    async def test_to_agent_input_with_text(self, converter):
        """Test converting user message with text content."""
        from datetime import datetime

        from chatkit.types import UserMessageItem

        input_item = UserMessageItem(
            id="msg_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="user_message",
            content=[UserMessageTextContent(text="Hello, how can you help me?")],
            attachments=[],
            inference_options={},
        )

        result = await converter.to_agent_input(input_item)

        assert len(result) == 1
        assert isinstance(result[0], ChatMessage)
        assert result[0].role == Role.USER
        assert result[0].text == "Hello, how can you help me?"

    async def test_to_agent_input_empty_text(self, converter):
        """Test converting user message with empty or whitespace-only text."""
        from datetime import datetime

        from chatkit.types import UserMessageItem

        input_item = UserMessageItem(
            id="msg_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="user_message",
            content=[UserMessageTextContent(text="   ")],
            attachments=[],
            inference_options={},
        )

        result = await converter.to_agent_input(input_item)
        assert result == []

    async def test_to_agent_input_no_content(self, converter):
        """Test converting user message with no content."""
        from datetime import datetime

        from chatkit.types import UserMessageItem

        input_item = UserMessageItem(
            id="msg_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="user_message",
            content=[],
            attachments=[],
            inference_options={},
        )

        result = await converter.to_agent_input(input_item)
        assert result == []

    async def test_to_agent_input_multiple_content_parts(self, converter):
        """Test converting user message with multiple text content parts."""
        from datetime import datetime

        from chatkit.types import UserMessageItem

        input_item = UserMessageItem(
            id="msg_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="user_message",
            content=[
                UserMessageTextContent(text="Hello "),
                UserMessageTextContent(text="world!"),
            ],
            attachments=[],
            inference_options={},
        )

        result = await converter.to_agent_input(input_item)

        assert len(result) == 1
        assert result[0].text == "Hello world!"

    def test_hidden_context_to_input(self, converter):
        """Test converting hidden context item to ChatMessage."""
        hidden_item = Mock()
        hidden_item.content = "This is hidden context information"

        result = converter.hidden_context_to_input(hidden_item)

        assert isinstance(result, ChatMessage)
        assert result.role == Role.SYSTEM
        assert result.text == "<HIDDEN_CONTEXT>This is hidden context information</HIDDEN_CONTEXT>"

    def test_tag_to_message_content(self, converter):
        """Test converting tag to message content."""
        from chatkit.types import UserMessageTagContent

        tag = UserMessageTagContent(
            type="input_tag",
            id="tag_1",
            text="john",
            data={"name": "John Doe"},
            interactive=False,
        )

        result = converter.tag_to_message_content(tag)
        assert isinstance(result, TextContent)
        # Since data is a dict, getattr won't work, so it will fall back to text
        assert result.text == "<TAG>Name:john</TAG>"

    def test_tag_to_message_content_no_name(self, converter):
        """Test converting tag with no name to message content."""
        from chatkit.types import UserMessageTagContent

        tag = UserMessageTagContent(
            type="input_tag",
            id="tag_2",
            text="jane",
            data={},
            interactive=False,
        )

        result = converter.tag_to_message_content(tag)
        assert isinstance(result, TextContent)
        assert result.text == "<TAG>Name:jane</TAG>"

    async def test_attachment_to_message_content_file_without_fetcher(self, converter):
        """Test that FileAttachment without data fetcher returns None."""
        from chatkit.types import FileAttachment

        attachment = FileAttachment(
            id="file_123",
            name="document.pdf",
            mime_type="application/pdf",
            type="file",
        )

        result = await converter.attachment_to_message_content(attachment)
        assert result is None

    async def test_attachment_to_message_content_image_with_preview_url(self, converter):
        """Test that ImageAttachment with preview_url creates UriContent."""
        from agent_framework import UriContent
        from chatkit.types import ImageAttachment

        attachment = ImageAttachment(
            id="img_123",
            name="photo.jpg",
            mime_type="image/jpeg",
            type="image",
            preview_url="https://example.com/photo.jpg",
        )

        result = await converter.attachment_to_message_content(attachment)
        assert isinstance(result, UriContent)
        assert result.uri == "https://example.com/photo.jpg"
        assert result.media_type == "image/jpeg"

    async def test_attachment_to_message_content_with_data_fetcher(self):
        """Test attachment conversion with data fetcher."""
        from agent_framework import DataContent
        from chatkit.types import FileAttachment

        # Mock data fetcher
        async def fetch_data(attachment_id: str) -> bytes:
            return b"file content data"

        converter = ThreadItemConverter(attachment_data_fetcher=fetch_data)

        attachment = FileAttachment(
            id="file_123",
            name="document.pdf",
            mime_type="application/pdf",
            type="file",
        )

        result = await converter.attachment_to_message_content(attachment)
        assert isinstance(result, DataContent)
        assert result.media_type == "application/pdf"

    async def test_to_agent_input_with_image_attachment(self):
        """Test converting user message with text and image attachment."""
        from datetime import datetime

        from agent_framework import UriContent
        from chatkit.types import ImageAttachment, UserMessageItem

        attachment = ImageAttachment(
            id="img_123",
            name="photo.jpg",
            mime_type="image/jpeg",
            type="image",
            preview_url="https://example.com/photo.jpg",
        )

        input_item = UserMessageItem(
            id="msg_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="user_message",
            content=[UserMessageTextContent(text="Check out this photo!")],
            attachments=[attachment],
            inference_options={},
        )

        converter = ThreadItemConverter()
        result = await converter.to_agent_input(input_item)

        assert len(result) == 1
        message = result[0]
        assert message.role == Role.USER
        assert len(message.contents) == 2

        # First content should be text
        assert isinstance(message.contents[0], TextContent)
        assert message.contents[0].text == "Check out this photo!"

        # Second content should be UriContent for the image
        assert isinstance(message.contents[1], UriContent)
        assert message.contents[1].uri == "https://example.com/photo.jpg"
        assert message.contents[1].media_type == "image/jpeg"

    async def test_to_agent_input_with_file_attachment_and_fetcher(self):
        """Test converting user message with file attachment using data fetcher."""
        from datetime import datetime

        from agent_framework import DataContent
        from chatkit.types import FileAttachment, UserMessageItem

        attachment = FileAttachment(
            id="file_123",
            name="report.pdf",
            mime_type="application/pdf",
            type="file",
        )

        input_item = UserMessageItem(
            id="msg_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="user_message",
            content=[UserMessageTextContent(text="Here's the document")],
            attachments=[attachment],
            inference_options={},
        )

        # Create converter with data fetcher
        async def fetch_data(attachment_id: str) -> bytes:
            return b"PDF content data"

        converter = ThreadItemConverter(attachment_data_fetcher=fetch_data)
        result = await converter.to_agent_input(input_item)

        assert len(result) == 1
        message = result[0]
        assert len(message.contents) == 2

        # First content should be text
        assert isinstance(message.contents[0], TextContent)

        # Second content should be DataContent for the file
        assert isinstance(message.contents[1], DataContent)
        assert message.contents[1].media_type == "application/pdf"

    def test_task_to_input(self, converter):
        """Test converting TaskItem to ChatMessage."""
        from datetime import datetime

        from chatkit.types import CustomTask, TaskItem

        task_item = TaskItem(
            id="task_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="task",
            task=CustomTask(type="custom", title="Analysis", content="Analyzed the data"),
        )

        result = converter.task_to_input(task_item)
        assert isinstance(result, ChatMessage)
        assert result.role == Role.USER
        assert "Analysis: Analyzed the data" in result.text
        assert "<Task>" in result.text

    def test_task_to_input_no_custom_task(self, converter):
        """Test that non-custom tasks return None."""
        from datetime import datetime

        from chatkit.types import TaskItem, ThoughtTask

        task_item = TaskItem(
            id="task_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="task",
            task=ThoughtTask(type="thought", title="Think", content="Thinking..."),
        )

        result = converter.task_to_input(task_item)
        assert result is None

    def test_workflow_to_input(self, converter):
        """Test converting WorkflowItem to ChatMessages."""
        from datetime import datetime

        from chatkit.types import CustomTask, Workflow, WorkflowItem

        workflow_item = WorkflowItem(
            id="wf_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="workflow",
            workflow=Workflow(
                type="custom",
                tasks=[
                    CustomTask(type="custom", title="Step 1", content="First step"),
                    CustomTask(type="custom", title="Step 2", content="Second step"),
                ],
            ),
        )

        result = converter.workflow_to_input(workflow_item)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(msg, ChatMessage) for msg in result)
        assert "Step 1: First step" in result[0].text
        assert "Step 2: Second step" in result[1].text

    def test_workflow_to_input_empty(self, converter):
        """Test that workflows with no custom tasks return None."""
        from datetime import datetime

        from chatkit.types import Workflow, WorkflowItem

        workflow_item = WorkflowItem(
            id="wf_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="workflow",
            workflow=Workflow(type="custom", tasks=[]),
        )

        result = converter.workflow_to_input(workflow_item)
        assert result is None

    def test_widget_to_input(self, converter):
        """Test converting WidgetItem to ChatMessage."""
        from datetime import datetime

        from chatkit.types import WidgetItem
        from chatkit.widgets import Card, Text

        widget_item = WidgetItem(
            id="widget_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="widget",
            widget=Card(key="card1", children=[Text(value="Hello")]),
        )

        result = converter.widget_to_input(widget_item)
        assert isinstance(result, ChatMessage)
        assert result.role == Role.USER
        assert "widget_1" in result.text
        assert "graphical UI widget" in result.text


class TestSimpleToAgentInput:
    """Tests for simple_to_agent_input helper function."""

    async def test_simple_to_agent_input_empty_list(self):
        """Test simple conversion with empty list."""
        result = await simple_to_agent_input([])
        assert result == []

    async def test_simple_to_agent_input_with_text(self):
        """Test simple conversion with text content."""
        from datetime import datetime

        from chatkit.types import UserMessageItem

        input_item = UserMessageItem(
            id="msg_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="user_message",
            content=[UserMessageTextContent(text="Test message")],
            attachments=[],
            inference_options={},
        )

        result = await simple_to_agent_input(input_item)

        assert len(result) == 1
        assert isinstance(result[0], ChatMessage)
        assert result[0].role == Role.USER
        assert result[0].text == "Test message"
