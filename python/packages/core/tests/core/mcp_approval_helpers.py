# Copyright (c) Microsoft. All rights reserved.

"""Helpers for the MCP approval-policy tests."""

from collections.abc import Sequence
from typing import Any

from agent_framework import (
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionTool,
    MCPStreamableHTTPTool,
    Message,
)


class ForwardingMCPTool(MCPStreamableHTTPTool):
    """Transport subclass whose constructor forwards to the transport constructor."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="docs", url="https://example.com/mcp", **kwargs)


async def run_function_call(
    client: Any,
    tools: Sequence[FunctionTool],
    function_name: str,
    *,
    streaming: bool,
) -> ChatResponse:
    """Run one scripted model turn that calls ``function_name`` through the function-invocation loop."""
    function_call = Content.from_function_call(call_id=f"call-{function_name}", name=function_name, arguments={})
    messages = [Message(role="user", contents=["run"])]
    if streaming:
        client.streaming_responses = [
            [ChatResponseUpdate(role="assistant", contents=[function_call], finish_reason="tool_calls")],
            [ChatResponseUpdate(role="assistant", contents=[Content.from_text("done")], finish_reason="stop")],
        ]
        stream = client.get_response(messages, stream=True, options={"tools": list(tools)})
        async for _ in stream:
            pass
        return await stream.get_final_response()
    client.run_responses = [
        ChatResponse(messages=Message(role="assistant", contents=[function_call])),
        ChatResponse(messages=Message(role="assistant", contents=["done"])),
    ]
    return await client.get_response(messages, options={"tools": list(tools)})


def approval_request_names(response: ChatResponse) -> list[str | None]:
    """Return the function names of the approval requests in a response."""
    return [
        content.function_call.name
        for message in response.messages
        for content in message.contents
        if content.type == "function_approval_request" and content.function_call is not None
    ]
