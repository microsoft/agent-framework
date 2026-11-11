# Copyright (c) Microsoft. All rights reserved.

"""Real-Agent boundaries for hosted approval round trips."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx2 as httpx
from agent_framework import (
    Agent,
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    FunctionTool,
    Message,
    ResponseStream,
    tool,
)

from agent_framework_foundry_hosting import ResponsesHostServer

from .approval_helpers import SqliteSessionStore
from .toolbox_approval_helpers import FixedSessionStoreProvider


class BatchApprovalClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """Call the protected tool for each name after user text; answer with text otherwise."""

    def __init__(self, names: Sequence[str]) -> None:
        super().__init__()
        self.names = list(names)

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        last = messages[-1]
        contents = (
            [
                Content.from_function_call(call_id=f"call-{name}", name="protected", arguments={"name": name})
                for name in self.names
            ]
            if last.role == "user" and any(content.type == "text" for content in last.contents)
            else [Content.from_text("done")]
        )

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            yield ChatResponseUpdate(role="assistant", contents=contents)

        async def complete() -> ChatResponse:
            return ChatResponse(messages=[Message("assistant", contents=contents)])

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates) if stream else complete()


def protected_tool(executed: list[str]) -> FunctionTool:
    @tool(approval_mode="always_require")
    def protected(name: str) -> str:
        """Run a protected action."""
        executed.append(name)
        return f"ran {name}"

    return protected


def approval_host(tmp_path: Path, executed: list[str], names: Sequence[str] = ("a", "b")) -> ResponsesHostServer:
    return ResponsesHostServer(
        agent=Agent(client=BatchApprovalClient(names), tools=[protected_tool(executed)]),
        agent_session_store_provider=FixedSessionStoreProvider(SqliteSessionStore(tmp_path / "sessions.db")),
    )


async def post_turn(client: httpx.AsyncClient, payload: dict[str, Any], *, stream: bool) -> dict[str, Any]:
    """Post one turn and return its terminal response body."""
    response = await client.post("/responses", json={"model": "test-model", **payload, "stream": stream})
    assert response.status_code == 200, response.text
    if not stream:
        return response.json()
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    return next(
        event["response"]
        for event in events
        if event["type"] in ("response.completed", "response.failed", "response.incomplete")
    )


def approval_ids(body: dict[str, Any]) -> dict[str, str]:
    """Map each requested tool argument name to its wire approval id."""
    return {
        json.loads(item["arguments"])["name"]: item["id"]
        for item in body["output"]
        if item["type"] == "mcp_approval_request"
    }


def approval_reply(approval_request_id: str, approve: bool) -> dict[str, Any]:
    return {"type": "mcp_approval_response", "approval_request_id": approval_request_id, "approve": approve}


def tool_outputs(body: dict[str, Any]) -> list[str]:
    return [item["output"] for item in body["output"] if item["type"] == "function_call_output"]
