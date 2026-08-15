# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import httpx
import pytest
from agent_framework import Agent, FunctionInvocationConfiguration
from agent_framework._sessions import AgentSession
from agent_framework_openai import OpenAIChatClient
from openai import AsyncOpenAI

from agent_framework_foundry import FoundryChatClient

_MARKERS = ("first", "second")


def _response(marker: str, model: str) -> dict[str, Any]:
    return {
        "id": f"response-{marker}",
        "created_at": 0,
        "model": model,
        "object": "response",
        "output": [
            {
                "id": f"function-{marker}",
                "type": "function_call",
                "call_id": f"call-{marker}",
                "name": "remote_lookup",
                "arguments": json.dumps({"prompt": marker}),
                "status": "completed",
            },
            {
                "id": f"message-{marker}",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": f"response for {marker}",
                        "annotations": [],
                        "logprobs": [],
                    }
                ],
            },
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "status": "completed",
    }


def _stream_events(marker: str, model: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "sequence_number": 0,
            "item": {
                "id": f"function-{marker}",
                "type": "function_call",
                "call_id": f"call-{marker}",
                "name": "remote_lookup",
                "arguments": "",
                "status": "in_progress",
            },
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": f"function-{marker}",
            "output_index": 0,
            "sequence_number": 1,
            "delta": json.dumps({"prompt": marker}),
        },
        {
            "type": "response.output_text.delta",
            "content_index": 0,
            "delta": f"response for {marker}",
            "item_id": f"message-{marker}",
            "logprobs": [],
            "output_index": 1,
            "sequence_number": 2,
        },
        {
            "type": "response.completed",
            "sequence_number": 3,
            "response": _response(marker, model),
        },
    ]


class _ResponsesTransport:
    def __init__(self, model: str) -> None:
        self.model = model
        self.requests: dict[str, list[dict[str, Any]]] = {marker: [] for marker in _MARKERS}
        self.active_requests = 0
        self.max_active_requests = 0
        self._both_calls_started = asyncio.Event()

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        marker = next(marker for marker in _MARKERS if marker in body)
        self.requests[marker].append(json.loads(body))
        self.active_requests += 1
        self.max_active_requests = max(self.max_active_requests, self.active_requests)
        if self.active_requests == 2:
            self._both_calls_started.set()
        try:
            await asyncio.wait_for(self._both_calls_started.wait(), timeout=1)
            if self.requests[marker][-1].get("stream"):
                content = "".join(f"data: {json.dumps(event)}\n\n" for event in _stream_events(marker, self.model))
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=f"{content}data: [DONE]\n\n",
                )
            return httpx.Response(200, json=_response(marker, self.model))
        finally:
            self.active_requests -= 1


class _ProjectClient:
    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    def get_openai_client(self, **kwargs: Any) -> AsyncOpenAI:
        del kwargs
        return self._client


def _build_client(
    provider: str,
    model: str,
    transport: _ResponsesTransport,
) -> tuple[OpenAIChatClient[Any] | FoundryChatClient, AsyncOpenAI]:
    async_client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://example.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
    )
    function_invocation_configuration: FunctionInvocationConfiguration = {"enabled": False}
    if provider == "foundry":
        project_client = _ProjectClient(async_client)
        return (
            FoundryChatClient(
                project_client=cast(Any, project_client),
                model=model,
                function_invocation_configuration=function_invocation_configuration,
            ),
            async_client,
        )
    return (
        OpenAIChatClient(
            model=model,
            async_client=async_client,
            function_invocation_configuration=function_invocation_configuration,
        ),
        async_client,
    )


async def _run_agent(
    client: OpenAIChatClient[Any] | FoundryChatClient,
    prompt: str,
    *,
    stream: bool,
) -> tuple[str, set[str], set[str], AgentSession]:
    agent = Agent(client=client)
    session = agent.get_session(service_session_id=f"previous-{prompt}")
    if stream:
        text_parts: list[str] = []
        call_ids: set[str] = set()
        arguments: set[str] = set()
        async for update in agent.run(prompt, session=session, stream=True):
            for content in update.contents:
                if content.type == "text" and content.text is not None:
                    text_parts.append(content.text)
                elif content.type == "function_call" and content.call_id is not None:
                    call_ids.add(content.call_id)
                    arguments.add(str(content.arguments))
        return "".join(text_parts), call_ids, arguments, session

    response = await agent.run(prompt, session=session, stream=False)
    call_contents = [
        content for message in response.messages for content in message.contents if content.type == "function_call"
    ]
    return (
        response.text,
        {content.call_id for content in call_contents if content.call_id is not None},
        {str(content.arguments) for content in call_contents},
        session,
    )


@pytest.mark.parametrize("provider", ["openai", "foundry"])
@pytest.mark.parametrize(
    ("first_stream", "second_stream"),
    [(False, False), (True, True), (True, False)],
    ids=["non-streaming", "streaming", "mixed"],
)
async def test_shared_chat_client_keeps_concurrent_agent_runs_isolated(
    provider: str,
    first_stream: bool,
    second_stream: bool,
) -> None:
    model = "test-model"
    transport = _ResponsesTransport(model)
    client, async_client = _build_client(provider, model, transport)

    try:
        first, second = await asyncio.gather(
            _run_agent(client, "first", stream=first_stream),
            _run_agent(client, "second", stream=second_stream),
        )
    finally:
        await async_client.close()

    first_text, first_call_ids, first_arguments, first_session = first
    second_text, second_call_ids, second_arguments, second_session = second
    assert first_text == "response for first"
    assert second_text == "response for second"
    assert first_call_ids == {"call-first"}
    assert second_call_ids == {"call-second"}
    assert json.dumps({"prompt": "first"}) in first_arguments
    assert json.dumps({"prompt": "second"}) in second_arguments
    assert transport.requests["first"][0]["previous_response_id"] == "previous-first"
    assert transport.requests["second"][0]["previous_response_id"] == "previous-second"
    assert all("second" not in json.dumps(request) for request in transport.requests["first"])
    assert all("first" not in json.dumps(request) for request in transport.requests["second"])
    assert first_session.service_session_id == "response-first"
    assert second_session.service_session_id == "response-second"
    assert transport.max_active_requests == 2
