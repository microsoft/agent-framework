# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import Sequence
from typing import Any

import tiktoken
from agent_framework._threads import ChatMessageList
from agent_framework._types import ChatMessage, Role
from loguru import logger


class SlidingWindowChatMessageList(ChatMessageList):
    """A token-aware sliding window implementation of ChatMessageList.

    Maintains two message lists: complete history and truncated window.
    Automatically removes oldest messages when token limit is exceeded.
    Also removes leading tool messages to ensure valid conversation flow.
    """

    def __init__(
        self,
        messages: Sequence[ChatMessage] | None = None,
        max_tokens: int = 3800,
        system_message: str | None = None,
        tool_definitions: Any | None = None,
    ):
        super().__init__(messages)
        self._truncated_messages = self._messages.copy()  # Separate truncated view
        self.max_tokens = max_tokens
        self.system_message = system_message  # Included in token count
        self.tool_definitions = tool_definitions
        # An estimation based on a commonly used vocab table
        self.encoding = tiktoken.get_encoding("o200k_base")

    async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
        await super().add_messages(messages)

        self._truncated_messages = self._messages.copy()
        self.truncate_messages()

    async def list_messages(self) -> list[ChatMessage]:
        """Get the current list of messages, which may be truncated."""
        return self._truncated_messages

    async def list_all_messages(self) -> list[ChatMessage]:
        """Get all messages from the store including the truncated ones."""
        return self._messages

    def truncate_messages(self) -> None:
        while len(self._truncated_messages) > 0 and self.get_token_count() > self.max_tokens:
            logger.warning("Messages exceed max tokens. Truncating oldest message.")
            self._truncated_messages.pop(0)
        # Remove leading tool messages
        while len(self._truncated_messages) > 0 and self._truncated_messages[0].role == Role.TOOL:
            logger.warning("Removing leading tool message because tool result cannot be the first message.")
            self._truncated_messages.pop(0)

    def get_token_count(self) -> int:
        """Estimate token count for a list of messages using tiktoken.
        Args:
            messages: List of ChatMessage objects
            system_message: Optional system message to include in count
        Returns:
            Estimated token count
        """
        total_tokens = 0

        # Add system message tokens if provided
        if self.system_message:
            total_tokens += len(self.encoding.encode(self.system_message))
            total_tokens += 4  # Extra tokens for system message formatting

        for msg in self._truncated_messages:
            # Add 4 tokens per message for role, formatting, etc.
            total_tokens += 4

            # Handle different content types
            if hasattr(msg, "contents") and msg.contents:
                for content in msg.contents:
                    if hasattr(content, "type"):
                        if content.type == "text":
                            total_tokens += len(self.encoding.encode(content.text))
                        elif content.type == "function_call":
                            total_tokens += 4
                            # Serialize function call and count tokens
                            func_call_data = {
                                "name": content.name,
                                "arguments": content.arguments,
                            }
                            total_tokens += self.estimate_any_object_token_count(func_call_data)
                        elif content.type == "function_result":
                            total_tokens += 4
                            # Serialize function result and count tokens
                            func_result_data = {
                                "call_id": content.call_id,
                                "result": content.result,
                            }
                            total_tokens += self.estimate_any_object_token_count(func_result_data)
                        else:
                            # For other content types, serialize the whole content
                            total_tokens += self.estimate_any_object_token_count(content)
                    else:
                        # Content without type, treat as text
                        total_tokens += self.estimate_any_object_token_count(content)
            elif hasattr(msg, "text") and msg.text:
                # Simple text message
                total_tokens += self.estimate_any_object_token_count(msg.text)
            else:
                # Skip it
                pass

        if total_tokens > self.max_tokens / 2:
            logger.opt(colors=True).warning(
                f"<yellow>Total tokens {total_tokens} is "
                f"{total_tokens / self.max_tokens * 100:.0f}% "
                f"of max tokens {self.max_tokens}</yellow>"
            )
        elif total_tokens > self.max_tokens:
            logger.opt(colors=True).warning(
                f"<red>Total tokens {total_tokens} is over max tokens {self.max_tokens}. Will truncate messages.</red>"
            )

        return total_tokens

    def estimate_any_object_token_count(self, obj: Any) -> int:
        try:
            serialized = json.dumps(obj)
        except Exception:
            serialized = str(obj)
        return len(self.encoding.encode(serialized))
