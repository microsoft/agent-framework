# Copyright (c) Microsoft. All rights reserved.

"""Offline protocol boundaries for Toolbox approval and OAuth consent regressions."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any, Literal

import httpx as host_httpx
import httpx2 as httpx
from agent_framework import (
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationContext,
    FunctionInvocationLayer,
    FunctionMiddleware,
    FunctionTool,
    Message,
    ResponseStream,
    SessionStore,
)
from agent_framework.exceptions import UserInputRequiredException
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.core.credentials import AccessToken
from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from pydantic import BaseModel

from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
from agent_framework_foundry_hosting._shared import StoreProvider

TOOL_NAMES = ("learn___completed", "learn___protected", "learn___later")
CONSENT_LINK = "https://consent.example.com/authorize"


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


class ToolboxConsentServer(ToolboxApprovalServer):
    def __init__(self) -> None:
        super().__init__()
        self.tools = [toolbox_tool("never", name=name) for name in TOOL_NAMES]
        self.authorized = False
        self.before_consent: Callable[[], Awaitable[object]] | None = None
        self.error: dict[str, Any] = {
            "code": -32006,
            "message": "tools/call failed "
            + json.dumps({
                "errors": [
                    {
                        "name": "learn",
                        "type": "mcp",
                        "error": {"code": "CONSENT_REQUIRED", "message": CONSENT_LINK},
                    }
                ]
            }),
        }

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payload = json.loads(request.content)
            if (
                payload.get("method") == "tools/call"
                and payload["params"]["name"] == "learn___protected"
                and not self.authorized
            ):
                self.calls.append(payload["params"])
                if self.before_consent is not None:
                    await self.before_consent()
                return httpx.Response(
                    200,
                    json={"jsonrpc": "2.0", "id": payload["id"], "error": self.error},
                )
        return await super().handle(request)


class ConsentModelServer:
    def __init__(self, tool_names: Sequence[str] = TOOL_NAMES) -> None:
        self.tool_names = tuple(tool_names)
        self.requests: list[dict[str, Any]] = []
        self.chains: dict[str, list[dict[str, Any]]] = {}
        self.history_errors: list[str] = []
        self.fail_settlement = False
        self.unexpected_settlement_call = False
        self.sdk_httpx: Any = import_module(DefaultAsyncHttpxClient.__mro__[1].__module__.partition(".")[0])

    async def handle(self, request: Any) -> Any:
        payload = json.loads(request.content)
        self.requests.append(payload)
        previous = payload.get("previous_response_id")
        history = copy.deepcopy(self.chains[previous]) if previous is not None else []
        inputs = payload["input"]
        history.extend(inputs if isinstance(inputs, list) else [{"type": "message", "content": inputs}])
        pending: set[str] = set()
        for item in history:
            if item.get("type") == "function_call":
                pending.add(item["call_id"])
            elif item.get("type") == "function_call_output":
                if item["call_id"] not in pending:
                    self.history_errors.append(f"Unexpected tool result for {item['call_id']}")
                pending.discard(item["call_id"])
        if pending or self.history_errors:
            self.history_errors.extend(f"No tool output found for {call_id}" for call_id in sorted(pending))
            return self.sdk_httpx.Response(
                400,
                json={"error": {"message": self.history_errors[-1], "type": "invalid_request_error"}},
            )
        settling = payload.get("tool_choice") == "none"
        if settling and self.fail_settlement:
            return self.sdk_httpx.Response(
                500, json={"error": {"message": "settlement refused", "type": "server_error"}}
            )
        index = len(self.requests)
        names = self.tool_names if index == 1 else ()
        authorized_retry = any(item.get("role") == "user" and "I have signed in" in json.dumps(item) for item in inputs)
        if (
            not settling
            and authorized_retry
            and not any(
                item.get("type") == "function_call_output" and item["call_id"].startswith("call_retry_")
                for item in inputs
            )
        ):
            names = ("learn___protected",)
        if settling and self.unexpected_settlement_call:
            names = ("learn___later",)
        output: list[dict[str, Any]] = [
            {
                "type": "function_call",
                "id": f"fc_{index}_{position}",
                "call_id": f"call_{'initial' if index == 1 else 'retry'}_{position}",
                "name": name,
                "arguments": "{}",
                "status": "completed",
            }
            for position, name in enumerate(names)
        ]
        if not output:
            output = [
                {
                    "type": "message",
                    "id": f"msg_{index}",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "hidden settlement reply" if settling else "done",
                            "annotations": [],
                            "logprobs": [],
                        }
                    ],
                }
            ]
        response: dict[str, Any] = {
            "id": f"resp_model_{index}",
            "object": "response",
            "created_at": 1_700_000_000,
            "model": "test-model",
            "status": "completed",
            "output": output,
            "error": None,
            "incomplete_details": None,
            "instructions": None,
            "metadata": {},
            "parallel_tool_calls": True,
            "temperature": 1.0,
            "tool_choice": payload.get("tool_choice", "auto"),
            "tools": [],
            "top_p": 1.0,
            "usage": {
                "input_tokens": 5,
                "output_tokens": 2,
                "total_tokens": 7,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
            "store": payload.get("store", True),
            "background": False,
            "conversation": None,
        }
        if response["store"]:
            self.chains[response["id"]] = history + copy.deepcopy(output)
        if not payload.get("stream"):
            return self.sdk_httpx.Response(200, json=response)
        events: list[dict[str, Any]] = [
            {
                "type": "response.created",
                "response": {**response, "status": "in_progress", "output": [], "usage": None},
            }
        ]
        for position, item in enumerate(output):
            events.append({
                "type": "response.output_item.added",
                "output_index": position,
                "item": {**item, "arguments": ""} if item["type"] == "function_call" else {**item, "content": []},
            })
            if item["type"] == "function_call":
                events.append({
                    "type": "response.function_call_arguments.delta",
                    "item_id": item["id"],
                    "output_index": position,
                    "delta": item["arguments"],
                })
            else:
                events.append({
                    "type": "response.output_text.delta",
                    "item_id": item["id"],
                    "output_index": position,
                    "content_index": 0,
                    "delta": item["content"][0]["text"],
                    "logprobs": [],
                })
            events.append({"type": "response.output_item.done", "output_index": position, "item": item})
        events.append({"type": "response.completed", "response": response})
        for sequence_number, event in enumerate(events):
            event["sequence_number"] = sequence_number
        text = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events)
        return self.sdk_httpx.Response(
            200, headers={"content-type": "text/event-stream"}, text=text + "data: [DONE]\n\n"
        )


@asynccontextmanager
async def consent_model_client(
    server: ConsentModelServer, *, concurrent: bool = False
) -> AsyncGenerator[OpenAIChatClient[OpenAIChatOptions]]:
    async with AsyncOpenAI(
        api_key="offline-key",
        base_url="https://model.invalid/v1",
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(transport=server.sdk_httpx.MockTransport(server.handle)),
    ) as api_client:
        yield OpenAIChatClient[OpenAIChatOptions](
            model="test-model",
            async_client=api_client,
            function_invocation_configuration={"allow_concurrent_invocation": concurrent},
        )


class ConsentSessionStoreProvider(StoreProvider[SessionStore]):
    def __init__(self) -> None:
        self.store = SessionStore()

    def get_store(self, *, config: AgentConfig, platform_context: FoundryAgentRequestContext) -> SessionStore:
        return self.store


class ConsentPendingInput(FunctionMiddleware):
    def __init__(self, kind: Literal["input", "approval"], *, require_approval: bool = False) -> None:
        self.kind = kind
        self.executions = 0
        self.function = FunctionTool(
            name="awaiting_input",
            func=self.invoke,
            approval_mode="always_require" if require_approval else "never_require",
        )

    async def invoke(self) -> str:
        self.executions += 1
        if self.kind == "input":
            raise UserInputRequiredException([
                Content("text", text="Please supply the missing input.", user_input_request=True),
                Content("text", text="Return the input as this call's result.", user_input_request=True),
            ])
        return "pending-result"

    async def process(self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        if context.function.name == self.function.name and self.kind == "approval":
            approval = context.metadata.get("approval_response")
            approved_call = approval.function_call if isinstance(approval, Content) else None
            if approved_call is None or not approved_call.additional_properties.get("test_runtime_approval"):
                occurrence_id = context.metadata["function_call_occurrence_id"]
                context.result = Content.from_function_approval_request(
                    id=f"runtime-{occurrence_id}",
                    function_call=Content.from_function_call(
                        call_id=context.metadata["call_id"],
                        name=context.function.name,
                        arguments=(
                            context.arguments.model_dump()
                            if isinstance(context.arguments, BaseModel)
                            else context.arguments
                        ),
                        id=occurrence_id,
                        additional_properties={"test_runtime_approval": True},
                    ),
                    additional_properties={"_replacement_approval_request": True},
                )
                return
        await call_next()


async def post_consent_response(
    host: ResponsesHostServer, payload: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    async with host_httpx.AsyncClient(transport=host_httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post("/responses", json={"model": "test-model", **payload})
        if payload.get("background"):
            assert response.status_code == 200, response.text
            body = response.json()
            async with asyncio.timeout(5):
                while body["status"] in ("queued", "in_progress"):
                    await asyncio.sleep(0.01)
                    response = await client.get(f"/responses/{body['id']}")
                    assert response.status_code == 200, response.text
                    body = response.json()
            return body, []
    assert response.status_code == 200, response.text
    if not payload.get("stream"):
        return response.json(), []
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]
    terminal = [
        event["response"]
        for event in events
        if event["type"] in ("response.completed", "response.incomplete", "response.failed")
    ]
    assert len(terminal) == 1, events
    return terminal[0], events


class ConsentCallerHeaders(FunctionMiddleware):
    def __init__(self) -> None:
        self.later_queued = asyncio.Event()

    async def process(self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        context.kwargs["caller"] = "later" if context.function.name.endswith("later") else "first"
        await call_next()

    def headers(self, kwargs: dict[str, Any]) -> dict[str, str]:
        caller = kwargs["caller"]
        if caller == "later":
            self.later_queued.set()
        return {"x-test-caller": caller}
