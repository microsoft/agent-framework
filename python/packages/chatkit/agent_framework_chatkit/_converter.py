# Copyright (c) Microsoft. All rights reserved.

"""Converter utilities for converting ChatKit thread items to Agent Framework messages."""

import logging
import sys
from collections.abc import Awaitable, Callable, Sequence

from agent_framework import (
    ChatMessage,
    Content,
    Role,
)
from chatkit.types import (
    AssistantMessageItem,
    Attachment,
    ClientToolCallItem,
    EndOfTurnItem,
    GeneratedImageItem,
    HiddenContextItem,
    ImageAttachment,
    SDKHiddenContextItem,
    TaskItem,
    ThreadItem,
    UserMessageItem,
    UserMessageTagContent,
    UserMessageTextContent,
    WidgetItem,
    WorkflowItem,
)

if sys.version_info >= (3, 11):
    from typing import assert_never  # type:ignore # pragma: no cover
else:
    from typing_extensions import assert_never  # type:ignore # pragma: no cover

logger = logging.getLogger(__name__)


class ThreadItemConverter:
    """Helper class to convert ChatKit thread items to Agent Framework ChatMessage objects.

    This class provides a base implementation for converting ChatKit thread items
    to Agent Framework messages. It can be extended to handle attachments,
    @-mentions, hidden context items, and custom thread item formats.

    Args:
        attachment_data_fetcher: Optional async function to fetch attachment binary data.
            If provided, it should take an attachment ID and return the binary data as bytes.
            If not provided, attachments will be converted to UriContent using available URLs.
    """

    def __init__(
        self,
        attachment_data_fetcher: Callable[[str], Awaitable[bytes]] | None = None,
    ) -> None:
        """Initialize the converter.

        Args:
            attachment_data_fetcher: Optional async function to fetch attachment data by ID.
        """
        self.attachment_data_fetcher = attachment_data_fetcher

    async def user_message_to_input(
        self, item: UserMessageItem, is_last_message: bool = True
    ) -> ChatMessage | list[ChatMessage] | None:
        """Convert a ChatKit UserMessageItem to Agent Framework ChatMessage(s).

        This method is called internally by `to_agent_input()`. Override this method
        to customize how user messages are converted.

        Args:
            item: The ChatKit user message item to convert.
            is_last_message: Whether this is the last message in the thread (used for quoted_text handling).

        Returns:
            A ChatMessage, list of messages, or None to skip.

        Note:
            Instead of calling this method directly, use `to_agent_input()` which handles
            all ThreadItem types and provides proper message ordering.
        """
        # Extract text content from the user message
        text_content = ""
        if item.content:
            for content_part in item.content:
                if isinstance(content_part, UserMessageTextContent):
                    text_content += content_part.text

        # Convert attachments to Content
        data_contents: list[Content] = []
        if item.attachments:
            for attachment in item.attachments:
                content = await self.attachment_to_message_content(attachment)
                if content is not None:
                    data_contents.append(content)

        # Create the message with text and attachments
        if not text_content.strip() and not data_contents:
            return None

        # If only text and no attachments, use text parameter for simplicity
        if text_content.strip() and not data_contents:
            user_message = ChatMessage(role=Role.USER, text=text_content.strip())
        else:
            # Build contents list with both text and attachments
            contents: list[Content] = []
            if text_content.strip():
                contents.append(Content.from_text(text=text_content.strip()))
            contents.extend(data_contents)
            user_message = ChatMessage(role=Role.USER, contents=contents)

        # Handle quoted text if this is the last message
        messages = [user_message]
        if item.quoted_text and is_last_message:
            quoted_context = ChatMessage(
                role=Role.USER,
                text=f"The user is referring to this in particular:\n{item.quoted_text}",
            )
            # Prepend quoted context before the main message
            messages.insert(0, quoted_context)

        return messages

    async def attachment_to_message_content(self, attachment: Attachment) -> Content | None:
        """Convert a ChatKit attachment to Agent Framework content.

        This method is called internally by `user_message_to_input()` to handle attachments.
        Override this method to customize attachment handling for your storage backend.

        The default implementation provides two strategies:
        1. If an attachment_data_fetcher was provided, it fetches the binary data
           and creates a DataContent object
        2. Otherwise, for ImageAttachment with preview_url, it creates a UriContent object

        For FileAttachment without a data fetcher, returns None (attachment is skipped).

        Args:
            attachment: The ChatKit attachment to convert (FileAttachment or ImageAttachment).

        Returns:
            DataContent if binary data is available, UriContent if only URL is available,
            or None if the attachment cannot be converted.

        Note:
            Instead of calling this method directly, use `to_agent_input()` which handles
            all ThreadItem types including attachments within user messages.

        Examples:
            .. code-block:: python

                # With data fetcher
                async def fetch_data(attachment_id: str) -> bytes:
                    return await my_storage.get_file(attachment_id)


                converter = ThreadItemConverter(attachment_data_fetcher=fetch_data)
                messages = await converter.to_agent_input(thread_items)

                # Without data fetcher (uses URLs for images)
                converter = ThreadItemConverter()
                messages = await converter.to_agent_input(thread_items)
        """
        # If we have a data fetcher, use it to get binary data
        if self.attachment_data_fetcher is not None:
            try:
                data = await self.attachment_data_fetcher(attachment.id)
                return Content.from_data(data=data, media_type=attachment.mime_type)
            except Exception as e:
                # If fetch fails, fall through to URL-based approach
                logger.debug(f"Failed to fetch attachment data for {attachment.id}: {e}")

        # For ImageAttachment, try to use preview_url
        if isinstance(attachment, ImageAttachment) and attachment.preview_url:
            return Content.from_uri(uri=str(attachment.preview_url), media_type=attachment.mime_type)

        # For FileAttachment without data fetcher, skip the attachment
        # Subclasses can override this method to provide custom handling
        return None

    def hidden_context_to_input(
        self, item: HiddenContextItem | SDKHiddenContextItem
    ) -> ChatMessage | list[ChatMessage] | None:
        """Convert a ChatKit HiddenContextItem or SDKHiddenContextItem to Agent Framework ChatMessage(s).

        This method is called internally by `to_agent_input()`. Override this method
        to customize how hidden context is converted.

        The default implementation wraps the hidden context in XML tags and returns
        a system message. This allows the model to distinguish hidden context from
        regular conversation.

        Args:
            item: The ChatKit hidden context item to convert.

        Returns:
            A ChatMessage with system role, a list of messages, or None to skip.

        Note:
            Instead of calling this method directly, use `to_agent_input()` which handles
            all ThreadItem types and provides proper message ordering.

        Examples:
            .. code-block:: python

                # Default behavior
                converter = ThreadItemConverter()
                hidden_item = HiddenContextItem(
                    id="ctx_1",
                    thread_id="thread_1",
                    created_at=datetime.now(),
                    content="User's email: user@example.com",
                )
                message = converter.hidden_context_to_input(hidden_item)
                # Returns: ChatMessage(role=SYSTEM, text="<HIDDEN_CONTEXT>User's email: ...</HIDDEN_CONTEXT>")
        """
        return ChatMessage(role=Role.SYSTEM, text=f"<HIDDEN_CONTEXT>{item.content}</HIDDEN_CONTEXT>")

    def tag_to_message_content(self, tag: UserMessageTagContent) -> Content:
        """Convert a ChatKit tag (@-mention) to Agent Framework content.

        This method is called internally by `user_message_to_input()` to handle tags.
        Override this method to customize tag conversion for your application.

        The default implementation extracts the tag's display name and wraps it in
        XML tags to provide context to the model about the @-mention.

        Args:
            tag: The ChatKit tag content to convert.

        Returns:
            TextContent with the tag information.

        Note:
            Instead of calling this method directly, use `to_agent_input()` which handles
            all ThreadItem types including tags within user messages.

        Examples:
            .. code-block:: python

                # Default behavior
                converter = ThreadItemConverter()
                tag = UserMessageTagContent(
                    type="input_tag", id="tag_1", text="john", data={"name": "John Doe"}, interactive=False
                )
                content = converter.tag_to_message_content(tag)
                # Returns: Content.from_text(text="<TAG>Name:John Doe</TAG>")
        """
        name = getattr(tag.data, "name", tag.text if hasattr(tag, "text") else "unknown")
        return Content.from_text(text=f"<TAG>Name:{name}</TAG>")

    def task_to_input(self, item: TaskItem) -> ChatMessage | list[ChatMessage] | None:
        """Convert a ChatKit TaskItem to Agent Framework ChatMessage(s).

        This method is called internally by `to_agent_input()`. Override this method
        to customize how tasks are converted.

        The default implementation converts custom tasks with title/content into
        a user message explaining what task was displayed to the user.

        Args:
            item: The ChatKit task item to convert.

        Returns:
            A ChatMessage, a list of messages, or None to skip the task.

        Note:
            Instead of calling this method directly, use `to_agent_input()` which handles
            all ThreadItem types and provides proper message ordering.

        Examples:
            .. code-block:: python

                # Task with both title and content
                from chatkit.types import Task

                task_item = TaskItem(
                    id="task_1",
                    thread_id="thread_1",
                    created_at=datetime.now(),
                    task=Task(type="custom", title="Data Analysis", content="Analyzed sales data"),
                )
                message = converter.task_to_input(task_item)
                # Returns message explaining the task was performed
        """
        if item.task.type != "custom" or (not item.task.title and not item.task.content):
            return None

        title = item.task.title or ""
        content = item.task.content or ""
        task_text = f"{title}: {content}" if title and content else title or content
        text = (
            f"A message was displayed to the user that the following task was performed:\n<Task>\n{task_text}\n</Task>"
        )

        return ChatMessage(role=Role.USER, text=text)

    def workflow_to_input(self, item: WorkflowItem) -> ChatMessage | list[ChatMessage] | None:
        """Convert a ChatKit WorkflowItem to Agent Framework ChatMessage(s).

        This method is called internally by `to_agent_input()`. Override this method
        to customize how workflows are converted.

        The default implementation converts each custom task in the workflow into
        a separate user message explaining what tasks were performed.

        Args:
            item: The ChatKit workflow item to convert.

        Returns:
            A list of ChatMessages (one per task), a single message, or None to skip.

        Note:
            Instead of calling this method directly, use `to_agent_input()` which handles
            all ThreadItem types and provides proper message ordering.

        Examples:
            .. code-block:: python

                # Workflow with multiple tasks
                from chatkit.types import Workflow, Task

                workflow_item = WorkflowItem(
                    id="wf_1",
                    thread_id="thread_1",
                    created_at=datetime.now(),
                    workflow=Workflow(
                        type="custom",
                        tasks=[
                            Task(type="custom", title="Step 1", content="Gathered data"),
                            Task(type="custom", title="Step 2", content="Analyzed results"),
                        ],
                    ),
                )
                messages = converter.workflow_to_input(workflow_item)
                # Returns list of messages for each task
        """
        messages: list[ChatMessage] = []
        for task in item.workflow.tasks:
            if task.type != "custom" or (not task.title and not task.content):
                continue

            title = task.title or ""
            content = task.content or ""
            task_text = f"{title}: {content}" if title and content else title or content
            text = (
                "A message was displayed to the user that the following task was performed:\n"
                f"<Task>\n{task_text}\n</Task>"
            )

            messages.append(ChatMessage(role=Role.USER, text=text))

        return messages if messages else None

    def widget_to_input(self, item: WidgetItem) -> ChatMessage | list[ChatMessage] | None:
        """Convert a ChatKit WidgetItem to Agent Framework ChatMessage(s).

        This method is called internally by `to_agent_input()`. Override this method
        to customize how widgets are converted.

        The default implementation converts the widget to a JSON representation
        and includes it in a user message, allowing the model to understand what
        UI element was displayed to the user.

        Args:
            item: The ChatKit widget item to convert.

        Returns:
            A ChatMessage describing the widget, or None to skip.

        Note:
            Instead of calling this method directly, use `to_agent_input()` which handles
            all ThreadItem types and provides proper message ordering.

        Examples:
            .. code-block:: python

                # Widget item
                from chatkit.widgets import Card, Text

                widget_item = WidgetItem(
                    id="widget_1",
                    thread_id="thread_1",
                    created_at=datetime.now(),
                    widget=Card(children=[Text(value="Hello")]),
                )
                message = converter.widget_to_input(widget_item)
                # Returns message with JSON representation of the widget
        """
        try:
            widget_json = item.widget.model_dump_json(exclude_unset=True, exclude_none=True)
            text = f"The following graphical UI widget (id: {item.id}) was displayed to the user:{widget_json}"
            return ChatMessage(role=Role.USER, text=text)
        except Exception:
            # If JSON serialization fails, skip the widget
            return None

    async def assistant_message_to_input(self, item: AssistantMessageItem) -> ChatMessage | list[ChatMessage] | None:
        """Convert a ChatKit AssistantMessageItem to Agent Framework ChatMessage(s).

        The default implementation extracts text from all content parts and creates
        an assistant message.

        Args:
            item: The ChatKit assistant message item to convert.

        Returns:
            A ChatMessage with assistant role, or None to skip.

        Note:
            Instead of calling this method directly, use `to_agent_input()` which handles
            all ThreadItem types and provides proper message ordering.
        """
        # Extract text from all content parts
        text_parts = [content.text for content in item.content]
        if not text_parts:
            return None

        return ChatMessage(role=Role.ASSISTANT, text="".join(text_parts))

    async def client_tool_call_to_input(self, item: ClientToolCallItem) -> ChatMessage | list[ChatMessage] | None:
        """Convert a ChatKit ClientToolCallItem to Agent Framework ChatMessage(s).

        The default implementation converts completed tool calls into function call
        and result content.

        Args:
            item: The ChatKit client tool call item to convert.

        Returns:
            A list containing function call and result messages, or None for pending calls.

        Note:
            Instead of calling this method directly, use `to_agent_input()` which handles
            all ThreadItem types and provides proper message ordering.
        """
        if item.status == "pending":
            # Skip pending tool calls - they cannot be sent to the model
            return None

        import json

        # Create function call message
        function_call_msg = ChatMessage(
            role=Role.ASSISTANT,
            contents=[
                Content.from_function_call(
                    call_id=item.call_id,
                    name=item.name,
                    arguments=json.dumps(item.arguments),
                )
            ],
        )

        # Create function result message
        function_result_msg = ChatMessage(
            role=Role.TOOL,
            contents=[
                Content.from_function_result(
                    call_id=item.call_id,
                    result=json.dumps(item.output) if item.output is not None else "",
                )
            ],
        )

        return [function_call_msg, function_result_msg]

    async def end_of_turn_to_input(self, item: EndOfTurnItem) -> ChatMessage | list[ChatMessage] | None:
        """Convert a ChatKit EndOfTurnItem to Agent Framework ChatMessage(s).

        The default implementation skips end-of-turn markers as they are only UI hints.

        Args:
            item: The ChatKit end-of-turn item to convert.

        Returns:
            None (end-of-turn items are not converted).

        Note:
            Instead of calling this method directly, use `to_agent_input()` which handles
            all ThreadItem types and provides proper message ordering.
        """
        # End-of-turn is only used for UI hints - skip it
        return None

    async def _thread_item_to_input_item(
        self,
        item: ThreadItem,
        is_last_message: bool = True,
    ) -> list[ChatMessage]:
        """Internal method to convert a single ThreadItem to ChatMessage(s).

        Args:
            item: The thread item to convert.
            is_last_message: Whether this is the last item in the thread.

        Returns:
            A list of ChatMessage objects (may be empty).
        """
        match item:
            case UserMessageItem():
                out = await self.user_message_to_input(item, is_last_message) or []
                return out if isinstance(out, list) else [out]
            case AssistantMessageItem():
                out = await self.assistant_message_to_input(item) or []
                return out if isinstance(out, list) else [out]
            case ClientToolCallItem():
                out = await self.client_tool_call_to_input(item) or []
                return out if isinstance(out, list) else [out]
            case EndOfTurnItem():
                out = await self.end_of_turn_to_input(item) or []
                return out if isinstance(out, list) else [out]
            case WidgetItem():
                out = self.widget_to_input(item) or []
                return out if isinstance(out, list) else [out]
            case WorkflowItem():
                out = self.workflow_to_input(item) or []
                return out if isinstance(out, list) else [out]
            case TaskItem():
                out = self.task_to_input(item) or []
                return out if isinstance(out, list) else [out]
            case HiddenContextItem():
                out = self.hidden_context_to_input(item) or []
                return out if isinstance(out, list) else [out]
            case SDKHiddenContextItem():
                out = self.hidden_context_to_input(item) or []
                return out if isinstance(out, list) else [out]
            case GeneratedImageItem():
                # TODO(evmattso): Implement generated image handling in a future PR
                return []
            case _:
                assert_never(item)

    async def to_agent_input(
        self,
        thread_items: Sequence[ThreadItem] | ThreadItem,
    ) -> list[ChatMessage]:
        """Convert ChatKit thread items to Agent Framework ChatMessages.

        This is the main entry point for converting ChatKit thread items. It handles
        all ThreadItem types (UserMessageItem, AssistantMessageItem, TaskItem, etc.)
        and calls the appropriate conversion method for each.

        Args:
            thread_items: A single ThreadItem or a sequence of ThreadItems to convert.

        Returns:
            A list of ChatMessage objects that can be sent to an Agent Framework agent.

        Examples:
            .. code-block:: python

                from agent_framework_chatkit import ThreadItemConverter

                converter = ThreadItemConverter()

                # Convert a single thread item
                messages = await converter.to_agent_input(user_message_item)

                # Convert multiple thread items
                messages = await converter.to_agent_input([user_message_item, assistant_message_item, task_item])

                # Use with agent
                from agent_framework import ChatAgent

                agent = ChatAgent(...)
                response = await agent.run_stream(messages)
        """
        thread_items = list(thread_items) if isinstance(thread_items, Sequence) else [thread_items]

        output: list[ChatMessage] = []
        for item in thread_items:
            output.extend(
                await self._thread_item_to_input_item(
                    item,
                    is_last_message=item is thread_items[-1],
                )
            )
        return output


# Default converter instance
_DEFAULT_CONVERTER = ThreadItemConverter()


async def simple_to_agent_input(thread_items: Sequence[ThreadItem] | ThreadItem) -> list[ChatMessage]:
    """Helper function that uses the default ThreadItemConverter.

    This function provides a quick way to get started with ChatKit integration
    without needing to create a custom ThreadItemConverter instance.

    Args:
        thread_items: A single ThreadItem or a sequence of ThreadItems to convert.

    Returns:
        A list of ChatMessage objects that can be sent to an Agent Framework agent.

    Examples:
        .. code-block:: python

            from agent_framework_chatkit import simple_to_agent_input

            # Convert a single item
            messages = await simple_to_agent_input(user_message_item)

            # Convert multiple items
            messages = await simple_to_agent_input([user_message_item, assistant_message_item, task_item])
    """
    return await _DEFAULT_CONVERTER.to_agent_input(thread_items)
