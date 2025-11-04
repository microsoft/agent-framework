# Copyright (c) Microsoft. All rights reserved.

"""Shared orchestrator utilities for group chat patterns.

This module provides simple, reusable functions for common orchestration tasks.
No inheritance required - just import and call.
"""

import logging
from typing import TYPE_CHECKING, Any

from .._types import ChatMessage, Role

if TYPE_CHECKING:
    from ._group_chat import _GroupChatRequestMessage  # type: ignore[reportPrivateUsage]

logger = logging.getLogger(__name__)


def clean_conversation_for_handoff(conversation: list[ChatMessage]) -> list[ChatMessage]:
    """Remove tool-related content from conversation for clean handoffs.

    During handoffs, tool calls can cause API errors because:
    1. Assistant messages with tool_calls must be followed by tool responses
    2. Tool response messages must follow an assistant message with tool_calls

    This creates a cleaned copy removing ALL tool-related content.

    Removes:
    - FunctionApprovalRequestContent and FunctionCallContent from assistant messages
    - Tool response messages (Role.TOOL)
    - Messages with only tool calls and no text

    Preserves:
    - User messages
    - Assistant messages with text content

    Args:
        conversation: Original conversation with potential tool content

    Returns:
        Cleaned conversation safe for handoff routing
    """
    from agent_framework import FunctionApprovalRequestContent, FunctionCallContent

    cleaned: list[ChatMessage] = []
    for msg in conversation:
        # Skip tool response messages entirely
        if msg.role == Role.TOOL:
            continue

        # Check for tool-related content
        has_tool_content = False
        if msg.contents:
            has_tool_content = any(
                isinstance(content, (FunctionApprovalRequestContent, FunctionCallContent)) for content in msg.contents
            )

        # If no tool content, keep original
        if not has_tool_content:
            cleaned.append(msg)
            continue

        # Has tool content - only keep if it also has text
        if msg.text and msg.text.strip():
            # Create fresh text-only message while preserving additional_properties
            msg_copy = ChatMessage(
                role=msg.role,
                text=msg.text,
                author_name=msg.author_name,
                additional_properties=dict(msg.additional_properties) if msg.additional_properties else None,
            )
            cleaned.append(msg_copy)

    return cleaned


def create_completion_message(
    *,
    text: str | None = None,
    author_name: str,
    reason: str = "completed",
) -> ChatMessage:
    """Create a standardized completion message.

    Simple helper to avoid duplicating completion message creation.

    Args:
        text: Message text, or None to generate default
        author_name: Author/orchestrator name
        reason: Reason for completion (for default text generation)

    Returns:
        ChatMessage with ASSISTANT role
    """
    message_text = text or f"Conversation {reason}."
    return ChatMessage(
        role=Role.ASSISTANT,
        text=message_text,
        author_name=author_name,
    )


def prepare_participant_request(
    *,
    participant_name: str,
    conversation: list[ChatMessage],
    instruction: str | None = None,
    task: ChatMessage | None = None,
    metadata: dict[str, Any] | None = None,
) -> "_GroupChatRequestMessage":
    """Create a standardized participant request message.

    Simple helper to avoid duplicating request construction.

    Args:
        participant_name: Name of the target participant
        conversation: Conversation history to send
        instruction: Optional instruction from manager/orchestrator
        task: Optional task context
        metadata: Optional metadata dict

    Returns:
        GroupChatRequestMessage ready to send
    """
    # Import here to avoid circular dependency
    from ._group_chat import _GroupChatRequestMessage  # type: ignore[reportPrivateUsage]

    return _GroupChatRequestMessage(
        agent_name=participant_name,
        conversation=list(conversation),
        instruction=instruction or "",
        task=task,
        metadata=metadata,
    )


class ParticipantRegistry:
    """Simple registry for tracking participant executor IDs and routing info.

    Provides a clean interface for the common pattern of mapping participant names
    to executor IDs and tracking which are agents vs custom executors.
    """

    def __init__(self) -> None:
        self._participant_entry_ids: dict[str, str] = {}
        self._agent_executor_ids: dict[str, str] = {}
        self._executor_id_to_participant: dict[str, str] = {}
        self._non_agent_participants: set[str] = set()

    def register(
        self,
        name: str,
        *,
        entry_id: str,
        is_agent: bool,
    ) -> None:
        """Register a participant's routing information.

        Args:
            name: Participant name
            entry_id: Executor ID for this participant's entry point
            is_agent: Whether this is an AgentExecutor (True) or custom Executor (False)
        """
        self._participant_entry_ids[name] = entry_id

        if is_agent:
            self._agent_executor_ids[name] = entry_id
            self._executor_id_to_participant[entry_id] = name
        else:
            self._non_agent_participants.add(name)

    def get_entry_id(self, name: str) -> str | None:
        """Get the entry executor ID for a participant name."""
        return self._participant_entry_ids.get(name)

    def get_participant_name(self, executor_id: str) -> str | None:
        """Get the participant name for an executor ID (agents only)."""
        return self._executor_id_to_participant.get(executor_id)

    def is_agent(self, name: str) -> bool:
        """Check if a participant is an agent (vs custom executor)."""
        return name in self._agent_executor_ids

    def is_registered(self, name: str) -> bool:
        """Check if a participant is registered."""
        return name in self._participant_entry_ids

    def all_participants(self) -> set[str]:
        """Get all registered participant names."""
        return set(self._participant_entry_ids.keys())
