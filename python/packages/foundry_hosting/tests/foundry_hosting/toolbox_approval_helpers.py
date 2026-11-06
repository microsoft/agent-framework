# Copyright (c) Microsoft. All rights reserved.

"""Offline protocol boundaries for Toolbox approval regressions."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

import httpx2 as httpx
from agent_framework import (
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
)
from azure.core.credentials import AccessToken

from agent_framework_foundry_hosting import FoundryToolbox


class ToolboxCredential:
    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        return AccessToken("offline-token", 9999999999)


class ToolboxApprovalServer:
    def __init__(self) -> None:
        self.tools: list[dict[str, Any]] = []
        self.prompts: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.initializations = 0
        self.page_size: int | None = None

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(405)
        if request.method == "DELETE":
            return httpx.Response(200)
        payload = json.loads(request.content)
        method = payload.get("method")
        if "id" not in payload:
            return httpx.Response(202)
        result: dict[str, Any]
        if method == "server/discover":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "error": {"code": -32601, "message": "Method not found"},
                },
            )
        if method == "initialize":
            self.initializations += 1
            result = {
                "protocolVersion": payload["params"]["protocolVersion"],
                "capabilities": {"tools": {}, "prompts": {}},
                "serverInfo": {"name": "toolbox-approval", "version": "1"},
            }
        elif method == "tools/list":
            start = int(payload.get("params", {}).get("cursor", "0"))
            end = len(self.tools) if self.page_size is None else start + self.page_size
            result = {"tools": self.tools[start:end]}
            if end < len(self.tools):
                result["nextCursor"] = str(end)
        elif method == "tools/call":
            self.calls.append(payload["params"])
            result = {"content": [{"type": "text", "text": "search-result"}]}
        elif method == "prompts/list":
            result = {"prompts": self.prompts}
        elif method == "ping":
            result = {}
        else:
            raise AssertionError(f"Unexpected MCP method: {method}")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})


@asynccontextmanager
async def toolbox_connection(
    server: ToolboxApprovalServer, *, connect: bool = True, **kwargs: Any
) -> AsyncGenerator[FoundryToolbox]:
    toolbox = FoundryToolbox(ToolboxCredential(), url="https://toolbox.invalid/mcp", **kwargs)
    original = toolbox._httpx_client
    assert original is not None
    await original.aclose()
    toolbox._httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(server.handle))
    try:
        if connect:
            await toolbox.connect()
        yield toolbox
    finally:
        await toolbox.close()


def toolbox_tool(
    approval: Any = "always",
    *,
    name: str = "learn___microsoft_docs_search",
    read_only: bool | None = None,
) -> dict[str, Any]:
    tool: dict[str, Any] = {
        "name": name,
        "inputSchema": {"type": "object", "properties": {}},
        "_meta": {
            "tool_configuration": {
                "type": "mcp",
                "server_label": "learn",
                "server_url": "https://learn.microsoft.com/api/mcp",
                "require_approval": approval,
                "original_type": "mcp",
            }
        },
    }
    if read_only is not None:
        tool["annotations"] = {"readOnlyHint": read_only}
    return tool


class ToolboxApprovalClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    def __init__(self, tool_name: str) -> None:
        super().__init__()
        self.tool_name = tool_name
        self.calls: list[list[Message]] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        self.calls.append(list(messages))
        contents = (
            [Content.from_function_call(call_id="call-search", name=self.tool_name, arguments="{}")]
            if len(self.calls) == 1
            else [Content.from_text("done")]
        )

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=contents)

        async def complete() -> ChatResponse:
            return ChatResponse(messages=[Message("assistant", contents=contents)])

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates) if stream else complete()
