# Copyright (c) Microsoft. All rights reserved.

"""Tests for ChatKit to Agent Framework converter utilities."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agent_framework import Message
from chatkit.types import InferenceOptions, UserMessageTextContent
from pydantic import AnyUrl

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
            inference_options=InferenceOptions(),
        )

        result = await converter.to_agent_input(input_item)

        assert len(result) == 1
        assert isinstance(result[0], Message)
        assert result[0].role == "user"
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
            inference_options=InferenceOptions(),
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
            inference_options=InferenceOptions(),
        )

        result = await converter.to_agent_input(input_item)
        assert result == []

    async def test_to_agent_input_multiple_content_parts(self, converter):
        """Test converting user message with multiple text content parts."""
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
            inference_options=InferenceOptions(),
        )

        result = await converter.to_agent_input(input_item)

        assert len(result) == 1
        assert result[0].text == "Hello world!"

    async def test_to_agent_input_with_quoted_text_for_last_message(self, converter):
        """Test quoted text is prepended as context for the last user message."""
        from chatkit.types import UserMessageItem

        input_item = UserMessageItem(
            id="msg_quoted",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="user_message",
            content=[UserMessageTextContent(text="Please summarize this")],
            attachments=[],
            quoted_text="Important excerpt",
            inference_options=InferenceOptions(),
        )

        result = await converter.to_agent_input(input_item)

        assert [message.role for message in result] == ["user", "user"]
        assert result[0].text == "The user is referring to this in particular:\nImportant excerpt"
        assert result[1].text == "Please summarize this"

    def test_hidden_context_to_input(self, converter):
        """Test converting hidden context item to Message."""
        hidden_item = Mock()
        hidden_item.content = "This is hidden context information"

        result = converter.hidden_context_to_input(hidden_item)

        assert isinstance(result, Message)
        assert result.role == "system"
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
        assert result.type == "text"
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
        assert result.type == "text"
        assert result.text == "<TAG>Name:jane</TAG>"

    def test_tag_to_message_content_prefers_name_attribute(self, converter):
        """Test converting tag content when the backing object exposes a name attribute."""
        tag = Mock()
        tag.data = SimpleNamespace(name="Jane Doe")
        tag.text = "fallback"

        result = converter.tag_to_message_content(tag)

        assert result.text == "<TAG>Name:Jane Doe</TAG>"

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
        from chatkit.types import ImageAttachment

        attachment = ImageAttachment(
            id="img_123",
            name="photo.jpg",
            mime_type="image/jpeg",
            type="image",
            preview_url=AnyUrl("https://example.com/photo.jpg"),
        )

        result = await converter.attachment_to_message_content(attachment)
        assert result.type == "uri"
        assert result.uri == "https://example.com/photo.jpg"
        assert result.media_type == "image/jpeg"

    async def test_attachment_to_message_content_with_data_fetcher(self):
        """Test attachment conversion with data fetcher."""
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
        assert result is not None
        assert result.type == "data"
        assert result.media_type == "application/pdf"

    async def test_attachment_to_message_content_fetcher_failure_falls_back_to_preview_url(self) -> None:
        """Test failed attachment fetch falls back to image preview URLs."""
        from chatkit.types import ImageAttachment

        async def fetch_data(_: str) -> bytes:
            raise RuntimeError("storage unavailable")

        converter = ThreadItemConverter(attachment_data_fetcher=fetch_data)
        attachment = ImageAttachment(
            id="img_fallback",
            name="photo.jpg",
            mime_type="image/jpeg",
            type="image",
            preview_url=AnyUrl("https://example.com/fallback.jpg"),
        )

        result = await converter.attachment_to_message_content(attachment)

        assert result is not None
        assert result.type == "uri"
        assert result.uri == "https://example.com/fallback.jpg"

    async def test_to_agent_input_with_image_attachment(self):
        """Test converting user message with text and image attachment."""
        from chatkit.types import ImageAttachment, UserMessageItem

        attachment = ImageAttachment(
            id="img_123",
            name="photo.jpg",
            mime_type="image/jpeg",
            type="image",
            preview_url=AnyUrl("https://example.com/photo.jpg"),
        )

        input_item = UserMessageItem(
            id="msg_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="user_message",
            content=[UserMessageTextContent(text="Check out this photo!")],
            attachments=[attachment],
            inference_options=InferenceOptions(),
        )

        converter = ThreadItemConverter()
        result = await converter.to_agent_input(input_item)

        assert len(result) == 1
        message = result[0]
        assert message.role == "user"
        assert len(message.contents) == 2

        # First content should be text
        assert message.contents[0].type == "text"
        assert message.contents[0].text == "Check out this photo!"

        # Second content should be UriContent for the image
        assert message.contents[1].type == "uri"
        assert message.contents[1].uri == "https://example.com/photo.jpg"
        assert message.contents[1].media_type == "image/jpeg"

    async def test_to_agent_input_with_file_attachment_and_fetcher(self):
        """Test converting user message with file attachment using data fetcher."""
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
            inference_options=InferenceOptions(),
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
        assert message.contents[0].type == "text"

        # Second content should be DataContent for the file
        assert message.contents[1].type == "data"
        assert message.contents[1].media_type == "application/pdf"

    def test_task_to_input(self, converter):
        """Test converting TaskItem to Message."""
        from chatkit.types import CustomTask, TaskItem

        task_item = TaskItem(
            id="task_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="task",
            task=CustomTask(type="custom", title="Analysis", content="Analyzed the data"),
        )

        result = converter.task_to_input(task_item)
        assert isinstance(result, Message)
        assert result.role == "user"
        assert "Analysis: Analyzed the data" in result.text
        assert "<Task>" in result.text

    def test_task_to_input_no_custom_task(self, converter):
        """Test that non-custom tasks return None."""
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
        assert all(isinstance(msg, Message) for msg in result)
        assert "Step 1: First step" in result[0].text
        assert "Step 2: Second step" in result[1].text

    def test_workflow_to_input_skips_non_custom_tasks(self, converter):
        """Test workflows ignore unsupported or empty tasks but keep valid custom tasks."""
        from chatkit.types import CustomTask, ThoughtTask, Workflow, WorkflowItem

        workflow_item = WorkflowItem(
            id="wf_skip",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="workflow",
            workflow=Workflow(
                type="custom",
                tasks=[
                    ThoughtTask(type="thought", title="Thinking", content="Working"),
                    CustomTask(type="custom"),
                    CustomTask(type="custom", title="Step", content="Done"),
                ],
            ),
        )

        result = converter.workflow_to_input(workflow_item)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].text is not None
        assert "Step: Done" in result[0].text

    def test_workflow_to_input_empty(self, converter):
        """Test that workflows with no custom tasks return None."""
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
        """Test converting WidgetItem to Message."""
        from chatkit.types import WidgetItem
        from chatkit.widgets import Card, Text  # ty: ignore[deprecated]

        widget_item = WidgetItem(
            id="widget_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="widget",
            widget=Card(key="card1", children=[Text(value="Hello")]),  # ty: ignore[deprecated]
        )

        result = converter.widget_to_input(widget_item)
        assert isinstance(result, Message)
        assert result.role == "user"
        assert "widget_1" in result.text
        assert "graphical UI widget" in result.text

    def test_widget_to_input_serialization_failure_returns_none(self, converter):
        """Test widget conversion skips widgets that cannot be serialized."""
        widget_item = Mock()
        widget_item.id = "widget_broken"
        widget_item.widget = Mock()
        widget_item.widget.model_dump_json.side_effect = RuntimeError("boom")

        assert converter.widget_to_input(widget_item) is None

    async def test_assistant_message_to_input_handles_empty_and_text_content(self, converter):
        """Test assistant messages convert text content and skip empty messages."""
        from chatkit.types import AssistantMessageContent, AssistantMessageItem

        assistant_item = AssistantMessageItem(
            id="assistant_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="assistant_message",
            content=[
                AssistantMessageContent(type="output_text", text="Hello", annotations=[]),
                AssistantMessageContent(type="output_text", text=" world", annotations=[]),
            ],
        )
        empty_item = AssistantMessageItem(
            id="assistant_2",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="assistant_message",
            content=[],
        )

        result = await converter.assistant_message_to_input(assistant_item)

        assert isinstance(result, Message)
        assert result.role == "assistant"
        assert result.text == "Hello world"
        assert await converter.assistant_message_to_input(empty_item) is None

    async def test_client_tool_call_to_input_handles_pending_and_completed(self, converter):
        """Test client tool call conversion only emits completed tool calls."""
        import json

        from chatkit.types import ClientToolCallItem

        pending_item = ClientToolCallItem(
            id="tool_pending",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="client_tool_call",
            status="pending",
            call_id="call_pending",
            name="get_weather",
            arguments={"location": "SEA"},
        )
        completed_item = ClientToolCallItem(
            id="tool_done",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="client_tool_call",
            status="completed",
            call_id="call_done",
            name="get_weather",
            arguments={"location": "SEA"},
            output={"temperature": 72},
        )

        assert await converter.client_tool_call_to_input(pending_item) is None

        result = await converter.client_tool_call_to_input(completed_item)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0].role == "assistant"
        assert result[0].contents[0].parse_arguments() == {"location": "SEA"}
        assert result[1].role == "tool"
        assert json.loads(result[1].contents[0].result) == {"temperature": 72}

    async def test_end_of_turn_to_input_returns_none(self, converter):
        """Test end-of-turn markers are skipped."""
        from chatkit.types import EndOfTurnItem

        end_item = EndOfTurnItem(
            id="end_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="end_of_turn",
        )

        assert await converter.end_of_turn_to_input(end_item) is None

    async def test_to_agent_input_dispatches_supported_variants(self, converter):
        """Test thread item dispatch converts supported items and skips unsupported variants."""
        from chatkit.types import (
            AssistantMessageContent,
            AssistantMessageItem,
            ClientToolCallItem,
            CustomTask,
            EndOfTurnItem,
            GeneratedImageItem,
            HiddenContextItem,
            SDKHiddenContextItem,
            StructuredInputItem,
            TaskItem,
            WidgetItem,
            Workflow,
            WorkflowItem,
        )
        from chatkit.widgets import Card, Text  # ty: ignore[deprecated]

        thread_items = [
            AssistantMessageItem(
                id="assistant_dispatch",
                thread_id="thread_1",
                created_at=datetime.now(),
                type="assistant_message",
                content=[AssistantMessageContent(type="output_text", text="Assistant", annotations=[])],
            ),
            ClientToolCallItem(
                id="tool_dispatch",
                thread_id="thread_1",
                created_at=datetime.now(),
                type="client_tool_call",
                status="completed",
                call_id="dispatch_call",
                name="search",
                arguments={"query": "docs"},
                output={"result": "ok"},
            ),
            EndOfTurnItem(id="end_dispatch", thread_id="thread_1", created_at=datetime.now(), type="end_of_turn"),
            WidgetItem(
                id="widget_dispatch",
                thread_id="thread_1",
                created_at=datetime.now(),
                type="widget",
                widget=Card(key="card_dispatch", children=[Text(value="Dispatch")]),  # ty: ignore[deprecated]
            ),
            WorkflowItem(
                id="workflow_dispatch",
                thread_id="thread_1",
                created_at=datetime.now(),
                type="workflow",
                workflow=Workflow(type="custom", tasks=[CustomTask(type="custom", title="Step", content="Done")]),
            ),
            TaskItem(
                id="task_dispatch",
                thread_id="thread_1",
                created_at=datetime.now(),
                type="task",
                task=CustomTask(type="custom", title="Analysis", content="Completed"),
            ),
            HiddenContextItem(
                id="hidden_dispatch",
                thread_id="thread_1",
                created_at=datetime.now(),
                type="hidden_context_item",
                content="secret",
            ),
            SDKHiddenContextItem(
                id="sdk_hidden_dispatch",
                thread_id="thread_1",
                created_at=datetime.now(),
                type="sdk_hidden_context",
                content="sdk secret",
            ),
            GeneratedImageItem(id="generated_dispatch", thread_id="thread_1", created_at=datetime.now()),
            StructuredInputItem(
                id="structured_dispatch",
                thread_id="thread_1",
                created_at=datetime.now(),
                type="structured_input",
                inputs=[],
            ),
            object(),
        ]

        result = await converter.to_agent_input(thread_items)

        assert [message.role for message in result] == [
            "assistant",
            "assistant",
            "tool",
            "user",
            "user",
            "user",
            "system",
            "system",
        ]
        assert result[0].text == "Assistant"
        assert result[2].contents[0].result is not None
        assert "widget_dispatch" in result[3].text
        assert "Step: Done" in result[4].text
        assert "Analysis: Completed" in result[5].text
        assert result[6].text == "<HIDDEN_CONTEXT>secret</HIDDEN_CONTEXT>"
        assert result[7].text == "<HIDDEN_CONTEXT>sdk secret</HIDDEN_CONTEXT>"


class TestSimpleToAgentInput:
    """Tests for simple_to_agent_input helper function."""

    async def test_simple_to_agent_input_empty_list(self):
        """Test simple conversion with empty list."""
        result = await simple_to_agent_input([])
        assert result == []

    async def test_simple_to_agent_input_with_text(self):
        """Test simple conversion with text content."""
        from chatkit.types import UserMessageItem

        input_item = UserMessageItem(
            id="msg_1",
            thread_id="thread_1",
            created_at=datetime.now(),
            type="user_message",
            content=[UserMessageTextContent(text="Test message")],
            attachments=[],
            inference_options=InferenceOptions(),
        )

        result = await simple_to_agent_input(input_item)

        assert len(result) == 1
        assert isinstance(result[0], Message)
        assert result[0].role == "user"
        assert result[0].text == "Test message"
