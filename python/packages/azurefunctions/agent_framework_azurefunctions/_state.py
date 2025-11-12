# Copyright (c) Microsoft. All rights reserved.

"""Agent State Management.

This module defines the AgentState class for managing conversation state and
serializing agent framework responses.
"""

from collections.abc import MutableMapping
from datetime import datetime, timezone
from typing import Any, cast

from agent_framework import AgentRunResponse, ChatMessage, Role, get_logger

logger = get_logger("agent_framework.azurefunctions.state")


class AgentState:
    """Manages agent conversation state using agent_framework types (ChatMessage, AgentRunResponse).

    This class handles:
    - Conversation history tracking using ChatMessage objects
    - Agent response storage using AgentRunResponse objects with correlation IDs
    - State persistence and restoration
    - Message counting
    """

    def __init__(self) -> None:
        """Initialize empty agent state."""
        self.conversation_history: list[ChatMessage] = []
        self.last_response: str | None = None
        self.message_count: int = 0

    def _current_timestamp(self) -> str:
        """Return an ISO 8601 UTC timestamp."""
        return datetime.now(timezone.utc).isoformat()

    def add_user_message(
        self,
        content: str,
        role: Role = Role.USER,
        correlation_id: str | None = None,
    ) -> None:
        """Add a user message to the conversation history as a ChatMessage object.

        Args:
            content: The message content
            role: The message role (user, system, etc.)
            correlation_id: Optional correlation identifier associated with the user message
        """
        self.message_count += 1
        timestamp = self._current_timestamp()
        additional_props: MutableMapping[str, Any] = {"timestamp": timestamp}
        if correlation_id is not None:
            additional_props["correlation_id"] = correlation_id
        chat_message = ChatMessage(role=role, text=content, additional_properties=additional_props)
        self.conversation_history.append(chat_message)
        logger.debug(f"Added {role} ChatMessage to history (message #{self.message_count})")

    def add_assistant_message(
        self, content: str, agent_response: AgentRunResponse, correlation_id: str | None = None
    ) -> None:
        """Add an assistant message to the conversation history with full agent response.

        Args:
            content: The text content of the response
            agent_response: The AgentRunResponse object from the agent framework
            correlation_id: Optional correlation ID for tracking this response
        """
        self.last_response = content
        timestamp = self._current_timestamp()
        serialized_response = self.serialize_response(agent_response)

        # Create a ChatMessage for the assistant response
        # The agent_response already contains messages, but we store it as a custom ChatMessage
        # with the agent_response stored in additional_properties for full metadata preservation
        additional_props: dict[str, Any] = {
            "agent_response": serialized_response,
            "correlation_id": correlation_id,
            "timestamp": timestamp,
            "message_count": self.message_count,
        }
        chat_message = ChatMessage(role="assistant", text=content, additional_properties=additional_props)

        self.conversation_history.append(chat_message)

        logger.debug(
            f"Added assistant ChatMessage to history with AgentRunResponse metadata (correlation_id: {correlation_id})"
        )

    def get_chat_messages(self) -> list[ChatMessage]:
        """Return a copy of the full conversation history."""
        return list(self.conversation_history)

    def try_get_agent_response(self, correlation_id: str) -> dict[str, Any] | None:
        """Get an agent response by correlation ID.

        Args:
            correlation_id: The correlation ID to look up

        Returns:
            The agent response data if found, None otherwise
        """
        for message in reversed(self.conversation_history):
            metadata = getattr(message, "additional_properties", {}) or {}
            if metadata.get("correlation_id") == correlation_id:
                return self._build_agent_response_payload(message, metadata)

        return None

    def serialize_response(self, response: AgentRunResponse) -> dict[str, Any]:
        """Serialize an ``AgentRunResponse`` to a dictionary.

        Args:
            response: The agent framework response object

        Returns:
            Dictionary containing all response fields
        """
        try:
            return response.to_dict()
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning(f"Error serializing response: {exc}")
            return {"response": str(response), "serialization_error": str(exc)}

    def to_dict(self) -> dict[str, Any]:
        """Get the current state as a dictionary for persistence.

        Returns:
            Dictionary containing conversation_history (as serialized ChatMessages),
            last_response, and message_count
        """
        return {
            "conversation_history": [msg.to_dict() for msg in self.conversation_history],
            "last_response": self.last_response,
            "message_count": self.message_count,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore state from a dictionary, reconstructing ChatMessage objects.

        Args:
            state: Dictionary containing conversation_history, last_response, and message_count
        """
        # Restore conversation history as ChatMessage objects
        history_data = state.get("conversation_history", [])
        restored_history: list[ChatMessage] = []
        for raw_message in history_data:
            if isinstance(raw_message, dict):
                restored_history.append(ChatMessage.from_dict(cast(dict[str, Any], raw_message)))
            else:
                restored_history.append(cast(ChatMessage, raw_message))

        self.conversation_history = restored_history

        self.last_response = state.get("last_response")
        self.message_count = state.get("message_count", 0)
        logger.debug("Restored state: %s ChatMessages in history", len(self.conversation_history))

    def reset(self) -> None:
        """Reset the state to empty."""
        self.conversation_history = []
        self.last_response = None
        self.message_count = 0
        logger.debug("State reset to empty")

    def __repr__(self) -> str:
        """String representation of the state."""
        return f"AgentState(messages={self.message_count}, history_length={len(self.conversation_history)})"

    def _build_agent_response_payload(self, message: ChatMessage, metadata: dict[str, Any]) -> dict[str, Any]:
        """Construct the agent response payload returned to callers."""
        return {
            "content": message.text,
            "agent_response": metadata.get("agent_response"),
            "message_count": metadata.get("message_count", self.message_count),
            "timestamp": metadata.get("timestamp"),
            "correlation_id": metadata.get("correlation_id"),
        }
