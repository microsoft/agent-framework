# Copyright (c) Microsoft. All rights reserved.

"""Streaming utilities for converting Agent Framework responses to ChatKit events."""

import uuid
from collections.abc import AsyncIterable, AsyncIterator, Callable
from datetime import datetime

from agent_framework import AgentResponseUpdate
from chatkit.types import (
    AssistantMessageContent,
    AssistantMessageContentPartTextDelta,
    AssistantMessageItem,
    ThreadItemAddedEvent,
    ThreadItemDoneEvent,
    ThreadItemUpdated,
    ThreadStreamEvent,
)


async def stream_agent_response(
    response_stream: AsyncIterable[AgentResponseUpdate],
    thread_id: str,
    generate_id: Callable[[str], str] | None = None,
) -> AsyncIterator[ThreadStreamEvent]:
    """Convert a streamed AgentResponseUpdate from Agent Framework to ChatKit events.

    This helper function takes a stream of AgentResponseUpdate objects from
    a Microsoft Agent Framework agent and converts them to ChatKit ThreadStreamEvent
    objects that can be consumed by the ChatKit UI.

    The function supports real-time token-by-token streaming by emitting
    ThreadItemUpdated events with AssistantMessageContentPartTextDelta for each
    text chunk as it arrives from the agent.

    Args:
        response_stream: An async iterable of AgentResponseUpdate objects
                        from an Agent Framework agent.
        thread_id: The ChatKit thread ID for the conversation.
        generate_id: Optional function to generate IDs for ChatKit items.
                    If not provided, simple incremental IDs will be used.

    Yields:
        ThreadStreamEvent: ChatKit events representing the agent's response,
                          including incremental text deltas for streaming display.
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
    content_index = 0

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
                if content.type == "text" and content.text is not None:
                    # Yield incremental text delta for streaming display
                    yield ThreadItemUpdated(
                        type="thread.item.updated",
                        item_id=message_id,
                        update=AssistantMessageContentPartTextDelta(
                            content_index=content_index,
                            delta=content.text,
                        ),
                    )
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
