# Copyright (c) Microsoft. All rights reserved.

"""Converter utilities for converting ChatKit thread items to Agent Framework messages."""

from typing import Any

from agent_framework import ChatMessage, Role
from chatkit.types import UserMessageItem


class ThreadItemConverter:
    """Helper class to convert ChatKit thread items to Agent Framework ChatMessage objects.

    This class provides a base implementation for converting ChatKit thread items
    to Agent Framework messages. It can be extended to handle attachments,
    @-mentions, hidden context items, and custom thread item formats.
    """

    async def to_agent_input(self, input_item: UserMessageItem | None) -> list[ChatMessage]:
        """Convert a ChatKit UserMessageItem to a list of Agent Framework ChatMessage objects.

        Args:
            input_item: The ChatKit user message item to convert.

        Returns:
            A list of ChatMessage objects that can be consumed by an Agent Framework agent.
        """
        if input_item is None:
            return []

        # Extract text content from the user message
        text_content = ""
        if input_item.content:
            for content_part in input_item.content:
                if hasattr(content_part, "text"):
                    text_content += content_part.text

        if not text_content.strip():
            return []

        return [ChatMessage(role=Role.USER, text=text_content.strip())]

    async def attachment_to_message_content(self, attachment: Any) -> Any:
        """Convert a ChatKit attachment to Agent Framework message content.

        This is a placeholder method that should be overridden in subclasses
        to handle specific attachment types and storage implementations.

        Args:
            attachment: The ChatKit attachment to convert.

        Returns:
            Agent Framework message content representing the attachment.
        """
        raise NotImplementedError("Subclasses should implement attachment handling")

    def hidden_context_to_input(self, item: Any) -> ChatMessage:
        """Convert a ChatKit HiddenContextItem to an Agent Framework ChatMessage.

        Args:
            item: The ChatKit hidden context item to convert.

        Returns:
            A ChatMessage with system role containing the hidden context.
        """
        return ChatMessage(role=Role.SYSTEM, text=f"<HIDDEN_CONTEXT>{item.content}</HIDDEN_CONTEXT>")

    def tag_to_message_content(self, tag: Any) -> str:
        """Convert a ChatKit tag (@-mention) to message content.

        Args:
            tag: The ChatKit tag to convert.

        Returns:
            String representation of the tag for inclusion in message content.
        """
        return f"<TAG>Name:{getattr(tag.data, 'name', 'unknown')}</TAG>"


async def simple_to_agent_input(input_item: UserMessageItem | None) -> list[ChatMessage]:
    """Helper function that uses the default ThreadItemConverter.

    This function provides a quick way to get started with ChatKit integration
    without needing to create a custom ThreadItemConverter instance.

    Args:
        input_item: The ChatKit user message item to convert.

    Returns:
        A list of ChatMessage objects that can be consumed by an Agent Framework agent.
    """
    # Use the default converter
    converter = ThreadItemConverter()
    return await converter.to_agent_input(input_item)
