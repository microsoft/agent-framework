# Copyright (c) Microsoft. All rights reserved.

"""Streaming utilities for converting Agent Framework responses to ChatKit events."""

import uuid
from collections.abc import AsyncIterable, AsyncIterator, Callable
from datetime import datetime

from agent_framework import AgentRunResponseUpdate, TextContent
from chatkit.types import (
    AssistantMessageContent,
    AssistantMessageItem,
    ThreadItemAddedEvent,
    ThreadItemDoneEvent,
    ThreadStreamEvent,
)


async def stream_agent_response(
    response_stream: AsyncIterable[AgentRunResponseUpdate],
    thread_id: str,
    generate_id: Callable[[str], str] | None = None,
) -> AsyncIterator[ThreadStreamEvent]:
    """Convert a streamed AgentRunResponseUpdate from Agent Framework to ChatKit events.

    This helper function takes a stream of AgentRunResponseUpdate objects from
    a Microsoft Agent Framework agent and converts them to ChatKit ThreadStreamEvent
    objects that can be consumed by the ChatKit UI.

    Args:
        response_stream: An async iterable of AgentRunResponseUpdate objects
                        from an Agent Framework agent.
        thread_id: The ChatKit thread ID for the conversation.
        generate_id: Optional function to generate IDs for ChatKit items.
                    If not provided, simple incremental IDs will be used.

    Yields:
        ThreadStreamEvent: ChatKit events representing the agent's response.
    """
    # Use provided ID generator or create default one
    if generate_id is None:

        def _default_id_generator(item_type: str) -> str:
            return f"{item_type}_{uuid.uuid4().hex[:8]}"

        message_id = _default_id_generator("msg")
    else:
        message_id = generate_id("msg")

    # Track if we've started the message
    message_started = False
    accumulated_text = ""

    async for update in response_stream:
        # Start the assistant message if not already started
        if not message_started:
            assistant_message = AssistantMessageItem(
                id=message_id,
                thread_id=thread_id,
                type="assistant_message",
                content=[],
                created_at=datetime.now(),
            )

            yield ThreadItemAddedEvent(type="thread.item.added", item=assistant_message)
            message_started = True

        # Process the update content
        if update.contents:
            for content in update.contents:
                # Handle text content - only TextContent has a text attribute
                if isinstance(content, TextContent) and content.text is not None:
                    accumulated_text += content.text

    # Finalize the message
    if message_started:
        final_message = AssistantMessageItem(
            id=message_id,
            thread_id=thread_id,
            type="assistant_message",
            content=[AssistantMessageContent(type="output_text", text=accumulated_text, annotations=[])]
            if accumulated_text
            else [],
            created_at=datetime.now(),
        )

        yield ThreadItemDoneEvent(type="thread.item.done", item=final_message)
