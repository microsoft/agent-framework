# Copyright (c) Microsoft. All rights reserved.

"""Unified state management for group chat orchestrators.

Provides OrchestrationState dataclass for standardized checkpoint serialization
across GroupChat, Handoff, and Magentic patterns.
"""

from dataclasses import dataclass, field
from typing import Any

from .._types import ChatMessage


def _new_chat_message_list() -> list[ChatMessage]:
    """Factory function for typed empty ChatMessage list.

    Satisfies the type checker.
    """
    return []


def _new_metadata_dict() -> dict[str, Any]:
    """Factory function for typed empty metadata dict.

    Satisfies the type checker.
    """
    return {}


@dataclass
class OrchestrationState:
    """Unified state container for orchestrator checkpointing.

    This dataclass standardizes checkpoint serialization across all three
    group chat patterns while allowing pattern-specific extensions via metadata.

    Common attributes cover shared orchestration concerns (task, conversation,
    round tracking). Pattern-specific state goes in the metadata dict.

    Attributes:
        conversation: Full conversation history (all messages)
        round_index: Number of coordination rounds completed (0 if not tracked)
        metadata: Extensible dict for pattern-specific state
        task: Optional primary task/question being orchestrated
    """

    conversation: list[ChatMessage] = field(default_factory=_new_chat_message_list)
    round_index: int = 0
    metadata: dict[str, Any] = field(default_factory=_new_metadata_dict)
    task: ChatMessage | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for checkpointing.

        Returns:
            Dict with encoded conversation and metadata for persistence
        """
        from ._conversation_state import encode_chat_messages

        result: dict[str, Any] = {
            "conversation": encode_chat_messages(self.conversation),
            "round_index": self.round_index,
            "metadata": dict(self.metadata),
        }
        if self.task is not None:
            result["task"] = encode_chat_messages([self.task])[0]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OrchestrationState":
        """Deserialize from checkpointed dict.

        Args:
            data: Checkpoint data with encoded conversation

        Returns:
            Restored OrchestrationState instance
        """
        from ._conversation_state import decode_chat_messages

        task = None
        if "task" in data:
            decoded_tasks = decode_chat_messages([data["task"]])
            task = decoded_tasks[0] if decoded_tasks else None

        return cls(
            conversation=decode_chat_messages(data.get("conversation", [])),
            round_index=data.get("round_index", 0),
            metadata=dict(data.get("metadata", {})),
            task=task,
        )
