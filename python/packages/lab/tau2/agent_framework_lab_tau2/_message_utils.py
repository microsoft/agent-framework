# Copyright (c) Microsoft. All rights reserved.

from agent_framework._types import ChatMessage, Contents, Role
from loguru import logger


def flip_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Flip message roles between assistant and user for role-playing scenarios.

    Used in agent simulations where the assistant's messages become user inputs
    and vice versa. Function calls are filtered out when flipping assistant
    messages to user messages (since users typically don't make function calls).
    """

    def filter_out_function_calls(messages: list[Contents]) -> list[Contents]:
        """Remove function call content from message contents."""
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


def log_messages(messages: list[ChatMessage]) -> None:
    """Log messages with colored output based on role and content type.

    Provides visual debugging by color-coding different message roles and
    content types. Escapes HTML-like characters to prevent log formatting issues.
    """
    _logger = logger.opt(colors=True)
    for msg in messages:
        # Handle different content types
        if hasattr(msg, "contents") and msg.contents:
            for content in msg.contents:
                if hasattr(content, "type"):
                    if content.type == "text":
                        escape_text = content.text.replace("<", r"\<")
                        if msg.role == Role.SYSTEM:
                            _logger.info(f"<cyan>[SYSTEM]</cyan> {escape_text}")
                        elif msg.role == Role.USER:
                            _logger.info(f"<green>[USER]</green> {escape_text}")
                        elif msg.role == Role.ASSISTANT:
                            _logger.info(f"<blue>[ASSISTANT]</blue> {escape_text}")
                        elif msg.role == Role.TOOL:
                            _logger.info(f"<yellow>[TOOL]</yellow> {escape_text}")
                        else:
                            _logger.info(f"<magenta>[{msg.role.value.upper()}]</magenta> {escape_text}")
                    elif content.type == "function_call":
                        function_call_text = f"{content.name}({content.arguments})"
                        function_call_text = function_call_text.replace("<", r"\<")
                        _logger.info(f"<yellow>[TOOL_CALL]</yellow> 🔧 {function_call_text}")
                    elif content.type == "function_result":
                        function_result_text = f"ID:{content.call_id} -> {content.result}"
                        function_result_text = function_result_text.replace("<", r"\<")
                        _logger.info(f"<yellow>[TOOL_RESULT]</yellow> 🔨 {function_result_text}")
                    else:
                        content_text = str(content).replace("<", r"\<")
                        _logger.info(f"<magenta>[{msg.role.value.upper()}] ({content.type})</magenta> {content_text}")
                else:
                    # Fallback for content without type
                    text_content = str(content).replace("<", r"\<")
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
            text_content = msg.text.replace("<", r"\<")
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
        else:
            # Fallback for other message formats
            text_content = str(msg).replace("<", r"\<")
            _logger.info(f"<magenta>[{msg.role.value.upper()}]</magenta> {text_content}")
