# type: ignore

import json
from typing import Any
from collections.abc import Sequence

import tiktoken
from loguru import logger
from agent_framework import ChatMessage, Contents, Role
from agent_framework._threads import ChatMessageList


def _flip_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Flip the messages from assistant to user and vice versa."""

    def filter_out_function_calls(messages: list[Contents]) -> list[Contents]:
        return [content for content in messages if content.type != "function_call"]

    flipped_messages = []
    for msg in messages:
        if msg.role == Role.ASSISTANT:
            # Flip assistant to user
            contents = filter_out_function_calls(msg.contents)
            if contents:
                flipped_msg = ChatMessage(
                    role=Role.USER,
                    # The function calls will cause 400 when role is user
                    contents=contents,
                    author_name=msg.author_name,
                    message_id=msg.message_id,
                )
                flipped_messages.append(flipped_msg)
        elif msg.role == Role.USER:
            # Flip user to assistant
            flipped_msg = ChatMessage(
                role=Role.ASSISTANT, contents=msg.contents, author_name=msg.author_name, message_id=msg.message_id
            )
            flipped_messages.append(flipped_msg)
        elif msg.role == Role.TOOL:
            # Skip tool messages
            pass
        else:
            # Keep other roles as-is (system, tool, etc.)
            flipped_messages.append(msg)
    return flipped_messages


def _log_messages(messages: list[ChatMessage]) -> None:
    """Log messages with colored output based on role and content type."""
    _logger = logger.opt(colors=True)
    for msg in messages:
        # Handle different content types
        if hasattr(msg, "contents") and msg.contents:
            for content in msg.contents:
                if hasattr(content, "type"):
                    if content.type == "text":
                        if msg.role == Role.SYSTEM:
                            _logger.info(f"<cyan>[SYSTEM]</cyan> {content.text}")
                        elif msg.role == Role.USER:
                            _logger.info(f"<green>[USER]</green> {content.text}")
                        elif msg.role == Role.ASSISTANT:
                            _logger.info(f"<blue>[ASSISTANT]</blue> {content.text}")
                        elif msg.role == Role.TOOL:
                            _logger.info(f"<yellow>[TOOL]</yellow> {content.text}")
                        else:
                            _logger.info(f"<magenta>[{msg.role.value.upper()}]</magenta> {content.text}")
                    elif content.type == "function_call":
                        _logger.info(f"<yellow>[TOOL_CALL]</yellow> 🔧 {content.name}({content.arguments})")
                    elif content.type == "function_result":
                        _logger.info(f"<yellow>[TOOL_RESULT]</yellow> 🔨 ID:{content.call_id} -> {content.result}")
                    else:
                        _logger.info(f"<magenta>[{msg.role.value.upper()}] ({content.type})</magenta> {str(content)}")
                else:
                    # Fallback for content without type
                    text_content = str(content)
                    if msg.role == Role.SYSTEM:
                        _logger.info(f"<cyan>[SYSTEM]</cyan> {text_content}")
                    elif msg.role == Role.USER:
                        _logger.info(f"<green>[USER]</green> {text_content}")
                    elif msg.role == Role.ASSISTANT:
                        _logger.info(f"<blue>[ASSISTANT]</blue> {text_content}")
                    elif msg.role == Role.TOOL:
                        _logger.info(f"<yellow>[TOOL]</yellow> {text_content}")
                    else:
                        _logger.info(f"<magenta>[{msg.role.value.upper()}]</magenta> {text_content}")
        elif hasattr(msg, "text") and msg.text:
            # Handle simple text messages
            if msg.role == Role.SYSTEM:
                _logger.info(f"<cyan>[SYSTEM]</cyan> {msg.text}")
            elif msg.role == Role.USER:
                _logger.info(f"<green>[USER]</green> {msg.text}")
            elif msg.role == Role.ASSISTANT:
                _logger.info(f"<blue>[ASSISTANT]</blue> {msg.text}")
            elif msg.role == Role.TOOL:
                _logger.info(f"<yellow>[TOOL]</yellow> {msg.text}")
            else:
                _logger.info(f"<magenta>[{msg.role.value.upper()}]</magenta> {msg.text}")
        else:
            # Fallback for other message formats
            _logger.info(f"<magenta>[{msg.role.value.upper()}]</magenta> {str(msg)}")


class SlidingWindowChatMessageList(ChatMessageList):
    """A sliding window implementation of ChatMessageList."""

    def __init__(
        self,
        messages: Sequence[ChatMessage] | None = None,
        max_tokens: int = 3800,
        system_message: str | None = None,
        tool_definitions: Any | None = None,
    ):
        super().__init__(messages)
        self.max_tokens = max_tokens
        self.system_message = system_message
        self.tool_definitions = tool_definitions
        self.encoding = tiktoken.get_encoding("o200k_base")  # An estimation

    async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
        await super().add_messages(messages)
        self.truncate_messages()

    def truncate_messages(self) -> None:
        while self.get_token_count() > self.max_tokens:
            self.pop(0)

    def get_token_count(self) -> int:
        """Estimate token count for a list of messages using tiktoken.

        Args:
            messages: List of ChatMessage objects
            system_message: Optional system message to include in count

        Returns:
            Estimated token count
        """
        # Use cl100k_base encoding (GPT-4, GPT-3.5-turbo)

        total_tokens = 0

        # Add system message tokens if provided
        if self.system_message:
            total_tokens += len(self.encoding.encode(self.system_message))
            total_tokens += 4  # Extra tokens for system message formatting

        for msg in self._messages:
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
                return self.estimate_any_object_token_count(msg.text)
            else:
                # Skip it
                pass

        if total_tokens > self.max_tokens / 2:
            logger.opt(colors=True).warning(
                f"<yellow>Total tokens {total_tokens} is {total_tokens / self.max_tokens * 100:.0f}% of max tokens {self.max_tokens}</yellow>"
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
