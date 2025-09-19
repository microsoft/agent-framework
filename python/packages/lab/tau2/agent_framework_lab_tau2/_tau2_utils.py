# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

import numpy as np
from agent_framework._tools import AIFunction
from agent_framework._types import ChatMessage
from loguru import logger
from pydantic import BaseModel
from tau2.data_model.message import (  # type: ignore[import-untyped]
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau2.data_model.tasks import EnvFunctionCall, InitializationData  # type: ignore[import-untyped]
from tau2.environment.environment import Environment  # type: ignore[import-untyped]
from tau2.environment.tool import Tool  # type: ignore[import-untyped]

_original_set_state = Environment.set_state


def convert_tau2_tool_to_ai_function(tau2_tool: Tool) -> AIFunction[Any, Any]:
    """Convert a tau2 Tool to an AIFunction for agent framework compatibility.

    Creates a wrapper that preserves the tool's interface while ensuring
    results are deep-copied to prevent unintended mutations.
    """

    def wrapped_func(**kwargs: Any) -> Any:
        result = tau2_tool(**kwargs)
        # Deep copy to prevent mutations of returned data
        if isinstance(result, BaseModel):
            result = result.model_copy(deep=True)
        else:
            result = deepcopy(result)
        return result

    return AIFunction(
        name=tau2_tool.name,
        description=tau2_tool._get_description(),
        func=wrapped_func,
        input_model=tau2_tool.params,
    )


def convert_agent_framework_messages_to_tau2_messages(messages: list[ChatMessage]) -> list[Message]:
    """Convert agent framework ChatMessages to tau2 Message objects.

    Handles role mapping, text extraction, function calls, and function results.
    Function results are converted to separate ToolMessage instances.
    """

    tau2_messages = []

    for msg in messages:
        role_str = str(msg.role)

        # Extract text content from all text-type contents
        text_content = None
        text_contents = [c for c in msg.contents if hasattr(c, "text") and hasattr(c, "type") and c.type == "text"]
        if text_contents:
            text_content = " ".join(c.text for c in text_contents)

        # Extract function calls and convert to ToolCall objects
        function_calls = [c for c in msg.contents if hasattr(c, "type") and c.type == "function_call"]
        tool_calls = None
        if function_calls:
            tool_calls = []
            for fc in function_calls:
                arguments = fc.parse_arguments() or {}
                tool_call = ToolCall(
                    id=fc.call_id,
                    name=fc.name,
                    arguments=arguments,
                    requestor="assistant" if role_str == "assistant" else "user",
                )
                tool_calls.append(tool_call)

        # Extract function results for separate ToolMessage creation
        function_results = [c for c in msg.contents if hasattr(c, "type") and c.type == "function_result"]

        # Create main message based on role
        if role_str == "system":
            tau2_messages.append(SystemMessage(role="system", content=text_content))
        elif role_str == "user":
            tau2_messages.append(UserMessage(role="user", content=text_content, tool_calls=tool_calls))
        elif role_str == "assistant":
            tau2_messages.append(AssistantMessage(role="assistant", content=text_content, tool_calls=tool_calls))
        elif role_str == "tool":
            # Tool messages are handled as function results below
            pass

        # Convert function results to separate ToolMessage instances
        for fr in function_results:
            dumpable_content = _dump_function_result(fr.result)
            content = dumpable_content if isinstance(dumpable_content, str) else json.dumps(dumpable_content)
            tool_msg = ToolMessage(
                id=fr.call_id,
                role="tool",
                content=content,
                requestor="assistant",  # Most tool calls originate from assistant
                error=fr.exception is not None,
            )
            tau2_messages.append(tool_msg)

    return tau2_messages


def patch_env_set_state() -> None:
    """Patch Environment.set_state to allow inconsistent tool call results.

    Modifies the original method to log warnings instead of raising errors
    when actual tool results differ from expected results, enabling more
    flexible testing and development workflows.
    """

    def set_state(
        self: Any,
        initialization_data: InitializationData | None,
        initialization_actions: list[EnvFunctionCall] | None,
        message_history: list[Message],
    ) -> None:
        if self.solo_mode:
            if any(isinstance(message, UserMessage) for message in message_history):
                raise ValueError("User messages are not allowed in solo mode")

        def get_actions_from_messages(
            messages: list[Message],
        ) -> list[tuple[ToolCall, ToolMessage]]:
            """
            Get the actions from the messages.
            """
            messages = deepcopy(messages)[::-1]
            actions = []
            while messages:
                message = messages.pop()
                if isinstance(message, ToolMessage):
                    raise ValueError("Tool message not expected. Tool messages should always follow a tool call.")
                if isinstance(message, (AssistantMessage, UserMessage)) and message.is_tool_call():
                    tool_calls = message.tool_calls
                    if tool_calls is None:
                        raise ValueError("Tool message expected. Got None.")
                    for tc in tool_calls:
                        if len(messages) == 0:
                            raise ValueError("Tool message expected. Got None.")
                        tm = messages.pop()
                        if not isinstance(tm, ToolMessage):
                            raise ValueError(f"Tool message expected. Got {type(tm)}")
                        if tc.id != tm.id:
                            raise ValueError(f"Tool call id mismatch. Got {tc.id} and {tm.id}")
                        actions.append((tc, tm))

            return actions

        if initialization_data is not None:
            if initialization_data.agent_data is not None:
                self.tools.update_db(initialization_data.agent_data)
            if initialization_data.user_data is not None:
                self.user_tools.update_db(initialization_data.user_data)

        if initialization_actions is not None:
            for action in initialization_actions:
                self.run_env_function_call(action)

        action_responses = get_actions_from_messages(message_history)
        for tool_call, expected_response in action_responses:
            response = self.get_response(tool_call)
            content = _recursive_json_deserialize(response.content)
            expected_content = _recursive_json_deserialize(expected_response.content)
            if content != expected_content:
                diff = f"Tool call:\n{tool_call}\n\nReturned:\n{response}\n\nExpected:\n{expected_response}"
                if isinstance(content, str) and content.startswith("Error:"):
                    # If the tool call resulted in an error, the difference can be ignored
                    logger.warning(f"Tool call resulted in an error. Ignoring the difference.\n{diff}")
                else:
                    raise ValueError(
                        f"Tool call:\n{tool_call}\n\nReturned:\n{response}\n\nExpected:\n{expected_response}"
                    )
        self.sync_tools()

    Environment.set_state = set_state


def unpatch_env_set_state() -> None:
    Environment.set_state = _original_set_state


def _dump_function_result(result: Any) -> Any:
    if isinstance(result, BaseModel):
        return result.model_dump_json()
    elif isinstance(result, list):
        return [_dump_function_result(item) for item in result]
    elif isinstance(result, dict):
        return {k: _dump_function_result(v) for k, v in result.items()}
    elif result is None:
        return None
    else:
        return result


def _to_native(obj: Any) -> Any:
    """Convert data retrieved from Panquet to data usable in AGL server."""
    # 1) Arrays -> list (then recurse)
    if isinstance(obj, np.ndarray):
        return _to_native(obj.tolist())

    # 2) NumPy scalar types -> Python scalars
    if isinstance(obj, np.generic):
        return _to_native(obj.item())

    # 3) Dict-like -> dict
    if isinstance(obj, Mapping):
        return {_to_native(k): _to_native(v) for k, v in obj.items()}

    # 4) Lists/Tuples/Sets -> list
    if isinstance(obj, (list, tuple, set)):
        return [_to_native(x) for x in obj]

    # 5) Anything else: leave as-is
    return obj


def _recursive_json_deserialize(obj: Any) -> Any:
    """
    Recursively deserialize a JSON object.
    """
    if isinstance(obj, str):
        try:
            deserialized = json.loads(obj)
            return _recursive_json_deserialize(deserialized)
        except (json.JSONDecodeError, TypeError):
            return obj
    elif isinstance(obj, list):
        return [_recursive_json_deserialize(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _recursive_json_deserialize(v) for k, v in obj.items()}
    else:
        return obj
