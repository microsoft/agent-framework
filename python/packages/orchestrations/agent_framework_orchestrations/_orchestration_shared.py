# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_framework._types import Message


@dataclass
class OrchestrationOutput:
    """Standardized output format for orchestrations.

    Attributes:
        messages: List of messages representing the full conversation of the orchestration, including all agent turns.
    """

    messages: list[Message]


def _new_chat_message_list() -> list[Message]:
    """Factory function for typed empty Message list.

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

    conversation: list[Message] = field(default_factory=_new_chat_message_list)
    round_index: int = 0
    orchestrator_name: str = ""
    metadata: dict[str, Any] = field(default_factory=_new_metadata_dict)
    task: Message | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for checkpointing.

        Returns:
            Dict with encoded conversation and metadata for persistence
        """
        result: dict[str, Any] = {
            "conversation": self.conversation,
            "round_index": self.round_index,
            "orchestrator_name": self.orchestrator_name,
            "metadata": dict(self.metadata),
        }
        if self.task is not None:
            result["task"] = self.task
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestrationState:
        """Deserialize from checkpointed dict.

        Args:
            data: Checkpoint data with encoded conversation

        Returns:
            Restored OrchestrationState instance
        """
        task = None
        if "task" in data:
            decoded_tasks = [data["task"]]
            task = decoded_tasks[0] if decoded_tasks else None

        return cls(
            conversation=data.get("conversation", []),
            round_index=data.get("round_index", 0),
            orchestrator_name=data.get("orchestrator_name", ""),
            metadata=dict(data.get("metadata", {})),
            task=task,
        )


def filter_tool_contents(conversation: list[Message]) -> list[Message]:
    """Keep only plain text chat history for handoff routing.

    Handoff executors must not replay prior tool-control artifacts (function calls,
    tool outputs, approval payloads) into future model turns, or providers may reject
    the next request due to unmatched tool-call state.

    This helper builds a text-only copy of the conversation:
    - Drops all non-text content from every message.
    - Drops messages with no remaining text content.
    - Preserves original roles and author names for retained text messages.
    """
    cleaned: list[Message] = []
    for msg in conversation:
        # Keep only plain text history for handoff routing. Tool-control content
        # (function_call/function_result/approval payloads) is runtime-only and
        # must not be replayed in future model turns.
        text_parts = [content.text for content in msg.contents if content.type == "text" and content.text]
        if not text_parts:
            continue

        msg_copy = Message(
            role=msg.role,
            text=" ".join(text_parts),
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
) -> Message:
    """Create a standardized completion message.

    Simple helper to avoid duplicating completion message creation.

    Args:
        text: Message text, or None to generate default
        author_name: Author/orchestrator name
        reason: Reason for completion (for default text generation)

    Returns:
        Message with assistant role
    """
    message_text = text or f"Conversation {reason}."
    return Message(
        role="assistant",
        text=message_text,
        author_name=author_name,
    )
