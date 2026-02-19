# Copyright (c) Microsoft. All rights reserved.

import json
from typing import Any

import tiktoken
from agent_framework import InMemoryHistoryProvider, Message
from loguru import logger


class SlidingWindowHistoryProvider(InMemoryHistoryProvider):
    """A token-aware sliding window implementation of InMemoryHistoryProvider.

    Stores all messages in session state but returns a truncated window from
    ``get_messages`` that fits within ``max_tokens``. Automatically removes
    oldest messages and leading tool messages to ensure valid conversation flow.
    """

    def __init__(
        self,
        source_id: str = InMemoryHistoryProvider.DEFAULT_SOURCE_ID,
        *,
        max_tokens: int = 3800,
        system_message: str | None = None,
        tool_definitions: Any | None = None,
    ):
        super().__init__(source_id)
        self.max_tokens = max_tokens
        self.system_message = system_message  # Included in token count
        self.tool_definitions = tool_definitions
        # An estimation based on a commonly used vocab table
        self.encoding = tiktoken.get_encoding("o200k_base")

    async def get_messages(
        self, session_id: str | None, *, state: dict[str, Any] | None = None, **kwargs: Any
    ) -> list[Message]:
        """Retrieve messages from session state, truncated to fit within max_tokens."""
        all_messages = await super().get_messages(session_id, state=state, **kwargs)
        return self._truncate(list(all_messages))

    def _truncate(self, messages: list[Message]) -> list[Message]:
        """Truncate messages to fit within max_tokens and remove leading tool messages."""
        while len(messages) > 0 and self._get_token_count(messages) > self.max_tokens:
            logger.warning("Messages exceed max tokens. Truncating oldest message.")
            messages.pop(0)
        # Remove leading tool messages
        while len(messages) > 0:
            if messages[0].role != "tool":
                break
            logger.warning("Removing leading tool message because tool result cannot be the first message.")
            messages.pop(0)
        return messages

    def _get_token_count(self, messages: list[Message]) -> int:
        """Estimate token count for a list of messages using tiktoken.

        Returns:
            Estimated token count
        """
        total_tokens = 0

        # Add system message tokens if provided
        if self.system_message:
            total_tokens += len(self.encoding.encode(self.system_message))
            total_tokens += 4  # Extra tokens for system message formatting

        for msg in messages:
            # Add 4 tokens per message for role, formatting, etc.
            total_tokens += 4

            # Handle different content types
            if hasattr(msg, "contents") and msg.contents:
                for content in msg.contents:
                    if hasattr(content, "type"):
                        if content.type == "text":
                            total_tokens += len(self.encoding.encode(content.text))  # type: ignore[arg-type]
                        elif content.type == "function_call":
                            total_tokens += 4
                            # Serialize function call and count tokens
                            func_call_data = {
                                "name": content.name,
                                "arguments": content.arguments,
                            }
                            total_tokens += self._estimate_any_object_token_count(func_call_data)
                        elif content.type == "function_result":
                            total_tokens += 4
                            # Serialize function result and count tokens
                            func_result_data = {
                                "call_id": content.call_id,
                                "result": content.result,
                            }
                            total_tokens += self._estimate_any_object_token_count(func_result_data)
                        else:
                            # For other content types, serialize the whole content
                            total_tokens += self._estimate_any_object_token_count(content)
                    else:
                        # Content without type, treat as text
                        total_tokens += self._estimate_any_object_token_count(content)
            elif hasattr(msg, "text") and msg.text:
                # Simple text message
                total_tokens += self._estimate_any_object_token_count(msg.text)

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

    def _estimate_any_object_token_count(self, obj: Any) -> int:
        try:
            serialized = json.dumps(obj)
        except Exception:
            serialized = str(obj)
        return len(self.encoding.encode(serialized))
