# Copyright (c) Microsoft. All rights reserved.

"""Offline protocol boundaries for invocation-time Foundry Toolbox OAuth consent tests."""

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

CONSENT_LINK = "https://consent.example.com/authorize?state=abc"


class ConsentCredential:
    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        return AccessToken("offline-token", 9999999999)


class ToolboxConsentServer:
    """Offline MCP server whose listed tools succeed unless configured to return a ``-32006`` consent error."""

    def __init__(self, tool_names: Sequence[str]) -> None:
        self.tool_names = list(tool_names)
        self.consent_errors: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []

    def require_consent(
        self,
        tool_name: str,
        *,
        message: str = f"Request failed (remote): {CONSENT_LINK}",
        data: Any = None,
    ) -> None:
        error: dict[str, Any] = {"code": -32006, "message": message}
        if data is not None:
            error["data"] = data
        self.consent_errors[tool_name] = error

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
                json={"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -32601, "message": "Method not found"}},
            )
        if method == "initialize":
            result = {
                "protocolVersion": payload["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "toolbox-consent", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {"name": name, "inputSchema": {"type": "object", "properties": {}}} for name in self.tool_names
                ]
            }
        elif method == "tools/call":
            name = payload["params"]["name"]
            self.calls.append(name)
            if (error := self.consent_errors.get(name)) is not None:
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "error": error})
            result = {"content": [{"type": "text", "text": f"{name}-result"}]}
        elif method == "ping":
            result = {}
        else:
            raise AssertionError(f"Unexpected MCP method: {method}")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})


@asynccontextmanager
async def consent_toolbox(server: ToolboxConsentServer, **kwargs: Any) -> AsyncGenerator[FoundryToolbox]:
    toolbox = FoundryToolbox(ConsentCredential(), url="https://toolbox.invalid/toolboxes/secure/mcp", **kwargs)
    original = toolbox._httpx_client
    assert original is not None
    await original.aclose()
    toolbox._httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(server.handle))
    try:
        await toolbox.connect()
        yield toolbox
    finally:
        await toolbox.close()


class BatchToolCallClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """Requests one batch of function calls on its first turn, then answers with text."""

    def __init__(self, tool_names: Sequence[str]) -> None:
        super().__init__()
        self.tool_names = list(tool_names)
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
            [
                Content.from_function_call(call_id=f"call-{index}", name=name, arguments="{}")
                for index, name in enumerate(self.tool_names)
            ]
            if len(self.calls) == 1
            else [Content.from_text("done")]
        )

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=contents)

        async def complete() -> ChatResponse:
            return ChatResponse(messages=[Message("assistant", contents=contents)])

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates) if stream else complete()
