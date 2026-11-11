# Copyright (c) Microsoft. All rights reserved.

"""Invocation-time Foundry Toolbox OAuth consent and its Responses translation."""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Mapping
from typing import Any

import pytest
from agent_framework import Agent, ChatOptions, Content, Message, UserInputRequiredException
from agent_framework.exceptions import ToolExecutionException
from azure.ai.agentserver.responses.aio import ResponseEventStream
from mcp import MCPError

from agent_framework_foundry_hosting._responses_shared import (
    OAUTH_CONSENT_NOT_EXECUTED_RESULT,
    OAUTH_CONSENT_REQUIRED_RESULT,
    _activate_toolbox_consent_scope,
    _current_toolbox_consent_scope,
    _normalize_allowed_oauth_consent_origins,
    _OutputItemTracker,
    tool_call_consent_url_from_error,
)

from .toolbox_consent_helpers import (
    CONSENT_LINK,
    BatchToolCallClient,
    ToolboxConsentServer,
    consent_toolbox,
)

# region Error parsing


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MCPError(-32006, "Request failed (remote): https://c.example.com/x"), "https://c.example.com/x"),
        (MCPError(-32006, "ignored", {"detail": " https://d.example.com/y "}), "https://d.example.com/y"),
        (MCPError(-32006, "Request failed (remote): https://c.example.com/x", {"detail": 7}), ""),
        (
            MCPError(
                -32006,
                'tools/list failed {"errors": [{"name": "s", "type": "mcp", "error": '
                '{"code": "CONSENT_REQUIRED", "message": "https://j.example.com/z"}}]}',
            ),
            "https://j.example.com/z",
        ),
        (MCPError(-32000, "Request failed (remote): https://c.example.com/x"), None),
    ],
)
def test_tool_call_consent_url_from_error_parses_gateway_shapes(error: MCPError, expected: str | None) -> None:
    assert tool_call_consent_url_from_error(error) == expected
    assert tool_call_consent_url_from_error(ToolExecutionException("call failed", error)) == expected


def test_tool_call_consent_url_from_error_ignores_unrelated_exceptions() -> None:
    assert tool_call_consent_url_from_error(ToolExecutionException("boom")) is None
    assert tool_call_consent_url_from_error(ValueError("https://c.example.com")) is None


# endregion

# region Scope


async def test_consent_scope_is_shared_with_copied_task_contexts() -> None:
    async def run() -> None:
        scope = _activate_toolbox_consent_scope()

        def mark() -> None:
            current = _current_toolbox_consent_scope()
            assert current is not None
            assert current is scope
            current.consent_rejected = True

        contextvars.copy_context().run(mark)
        await asyncio.create_task(asyncio.sleep(0))
        assert scope.blocks_toolbox_calls

    await asyncio.create_task(run())
    assert _current_toolbox_consent_scope() is None


# endregion

# region Toolbox call_tool


async def _in_scope(coroutine_factory: Any, *, allowed_origins: frozenset[str] | None = None) -> Any:
    async def run() -> Any:
        scope = _activate_toolbox_consent_scope(allowed_origins=allowed_origins)
        try:
            return scope, await coroutine_factory()
        except BaseException as exc:  # noqa: BLE001 - returned for assertions
            return scope, exc

    return await asyncio.create_task(run())


async def test_call_tool_translates_allowed_consent_to_structured_user_input() -> None:
    server = ToolboxConsentServer(["secure"])
    server.require_consent("secure")
    async with consent_toolbox(server) as toolbox:
        scope, result = await _in_scope(lambda: toolbox.call_tool("secure"))

    assert isinstance(result, UserInputRequiredException)
    function_result, consent = result.contents
    assert function_result.type == "function_result"
    assert function_result.result == OAUTH_CONSENT_REQUIRED_RESULT
    assert consent.type == "oauth_consent_request"
    assert consent.consent_link == CONSENT_LINK
    assert consent.user_input_request is True
    assert scope.consent_required and scope.blocks_toolbox_calls
    assert [(c.name, c.consent_url) for c in scope.consents] == [(toolbox.name, CONSENT_LINK)]


async def test_call_tool_uses_structured_detail_for_consent_link() -> None:
    server = ToolboxConsentServer(["secure"])
    server.require_consent("secure", message="consent required", data={"detail": CONSENT_LINK})
    async with consent_toolbox(server) as toolbox:
        _, result = await _in_scope(lambda: toolbox.call_tool("secure"))

    assert isinstance(result, UserInputRequiredException)
    assert result.contents[1].consent_link == CONSENT_LINK


@pytest.mark.parametrize(
    ("message", "allowed"),
    [
        ("Request failed (remote): http://consent.example.com/authorize", None),
        ("Request failed (remote): https://user:pw@consent.example.com/authorize", None),
        (f"Request failed (remote): {CONSENT_LINK}", ["https://other.example.com"]),
        ("Request failed (remote): ", None),
    ],
)
async def test_call_tool_rejects_unsafe_or_disallowed_consent_links(message: str, allowed: list[str] | None) -> None:
    server = ToolboxConsentServer(["secure"])
    server.require_consent("secure", message=message)
    async with consent_toolbox(server) as toolbox:
        scope, result = await _in_scope(
            lambda: toolbox.call_tool("secure"),
            allowed_origins=_normalize_allowed_oauth_consent_origins(allowed),
        )

    assert isinstance(result, ToolExecutionException)
    assert not isinstance(result, UserInputRequiredException)
    assert "consent.example.com" not in str(result)
    assert result.__cause__ is None
    assert scope.consent_rejected and not scope.consent_required and scope.blocks_toolbox_calls


async def test_call_tool_accepts_consent_link_from_allowed_origin() -> None:
    server = ToolboxConsentServer(["secure"])
    server.require_consent("secure")
    async with consent_toolbox(server) as toolbox:
        _, result = await _in_scope(
            lambda: toolbox.call_tool("secure"),
            allowed_origins=_normalize_allowed_oauth_consent_origins(["https://consent.example.com"]),
        )

    assert isinstance(result, UserInputRequiredException)


async def test_call_tool_blocks_later_toolbox_calls_without_contacting_gateway() -> None:
    server = ToolboxConsentServer(["secure", "open"])
    server.require_consent("secure")
    async with consent_toolbox(server) as toolbox:

        async def both() -> Any:
            with pytest.raises(UserInputRequiredException):
                await toolbox.call_tool("secure")
            return await toolbox.call_tool("open")

        _, result = await _in_scope(both)

    assert result == OAUTH_CONSENT_NOT_EXECUTED_RESULT
    assert server.calls == ["secure"]


async def test_call_tool_without_scope_propagates_original_error() -> None:
    server = ToolboxConsentServer(["secure"])
    server.require_consent("secure")
    async with consent_toolbox(server) as toolbox:
        with pytest.raises(ToolExecutionException) as error:
            await toolbox.call_tool("secure")

    assert not isinstance(error.value, UserInputRequiredException)
    assert tool_call_consent_url_from_error(error.value) == CONSENT_LINK


async def test_call_tool_in_scope_propagates_non_consent_errors() -> None:
    server = ToolboxConsentServer(["secure"])
    server.consent_errors["secure"] = {"code": -32000, "message": "boom"}
    async with consent_toolbox(server) as toolbox:
        scope, result = await _in_scope(lambda: toolbox.call_tool("secure"))

    assert isinstance(result, ToolExecutionException)
    assert not scope.blocks_toolbox_calls


# endregion

# region Function loop


def _function_results(messages: list[Message]) -> dict[str, list[Content]]:
    results: dict[str, list[Content]] = {}
    for message in messages:
        for content in message.contents:
            if content.type == "function_result" and content.call_id is not None:
                results.setdefault(content.call_id, []).append(content)
    return results


def _all_contents(messages: list[Message]) -> list[Content]:
    return [content for message in messages for content in message.contents]


@pytest.mark.parametrize("stream", [False, True])
async def test_sequential_function_loop_returns_consent_and_blocks_later_calls(stream: bool) -> None:
    server = ToolboxConsentServer(["before", "secure", "after"])
    server.require_consent("secure")
    async with consent_toolbox(server) as toolbox:
        client = BatchToolCallClient([function.name for function in toolbox.functions])
        agent = Agent(client=client, tools=toolbox, default_options=ChatOptions(allow_multiple_tool_calls=True))

        async def run() -> list[Message]:
            client.function_invocation_configuration["allow_concurrent_invocation"] = False  # type: ignore[index]
            if stream:
                response_stream = agent.run("go", stream=True)
                async for _ in response_stream:
                    pass
                return list((await response_stream.get_final_response()).messages)
            return list((await agent.run("go")).messages)

        scope, messages = await _in_scope(run)

    assert not isinstance(messages, BaseException), messages
    assert server.calls == ["before", "secure"]
    assert len(client.calls) == 1
    results = _function_results(messages)
    assert all(len(items) == 1 for items in results.values())
    assert set(results) == {"call-0", "call-1", "call-2"}
    assert results["call-1"][0].result == OAUTH_CONSENT_REQUIRED_RESULT
    assert results["call-2"][0].result == OAUTH_CONSENT_NOT_EXECUTED_RESULT
    assert "before-result" in str(results["call-0"][0].result)
    consents = [c for c in _all_contents(messages) if c.type == "oauth_consent_request"]
    assert [c.consent_link for c in consents] == [CONSENT_LINK]
    assert scope.consent_required


@pytest.mark.parametrize("stream", [False, True])
async def test_parallel_function_loop_preserves_completed_siblings(stream: bool) -> None:
    server = ToolboxConsentServer(["secure", "open"])
    server.require_consent("secure")
    async with consent_toolbox(server) as toolbox:
        client = BatchToolCallClient([function.name for function in toolbox.functions])
        agent = Agent(client=client, tools=toolbox, default_options=ChatOptions(allow_multiple_tool_calls=True))

        async def run() -> list[Message]:
            if stream:
                response_stream = agent.run("go", stream=True)
                async for _ in response_stream:
                    pass
                return list((await response_stream.get_final_response()).messages)
            return list((await agent.run("go")).messages)

        _, messages = await _in_scope(run)

    assert not isinstance(messages, BaseException), messages
    assert len(client.calls) == 1
    results = _function_results(messages)
    assert set(results) == {"call-0", "call-1"}
    assert all(len(items) == 1 for items in results.values())
    assert results["call-0"][0].result == OAUTH_CONSENT_REQUIRED_RESULT
    # Concurrent siblings may already have started; their completed or not-executed result is preserved.
    assert results["call-1"][0].result == OAUTH_CONSENT_NOT_EXECUTED_RESULT or "open-result" in str(
        results["call-1"][0].result
    )


# endregion

# region Responses translation


async def test_tracker_emits_terminal_output_then_consent_and_marks_response_incomplete() -> None:
    stream = ResponseEventStream(response_id="resp_consent")
    stream.emit_created()
    stream.emit_in_progress()
    tracker = _OutputItemTracker(
        stream, allowed_oauth_consent_origins=_normalize_allowed_oauth_consent_origins(["https://consent.example.com"])
    )
    contents = [
        Content.from_function_call(call_id="call-1", name="secure", arguments="{}"),
        Content.from_function_result(call_id="call-1", result=OAUTH_CONSENT_REQUIRED_RESULT),
        Content.from_oauth_consent_request(CONSENT_LINK, additional_properties={"server_label": "secure-box"}),
        Content.from_function_call(call_id="call-2", name="other", arguments="{}"),
        Content.from_function_result(call_id="call-2", result=OAUTH_CONSENT_NOT_EXECUTED_RESULT),
    ]
    events: list[Any] = []
    for content in contents:
        async for event in tracker.handle(content):
            events.append(event)
    events.extend(tracker.close())

    done_items = [
        dict(e["item"]) if isinstance(e, Mapping) else e.item.as_dict()
        for e in events
        if (e.get("type") if isinstance(e, Mapping) else e.type) == "response.output_item.done"
    ]
    assert [item["type"] for item in done_items] == [
        "function_call",
        "function_call_output",
        "oauth_consent_request",
        "function_call",
        "function_call_output",
    ]
    outputs = {item["call_id"]: item["output"] for item in done_items if item["type"] == "function_call_output"}
    assert outputs == {"call-1": OAUTH_CONSENT_REQUIRED_RESULT, "call-2": OAUTH_CONSENT_NOT_EXECUTED_RESULT}
    consent = next(item for item in done_items if item["type"] == "oauth_consent_request")
    assert consent["consent_link"] == CONSENT_LINK
    assert consent["server_label"] == "secure-box"
    assert tracker.oauth_consent_requested


async def test_tracker_rejects_consent_from_disallowed_origin() -> None:
    stream = ResponseEventStream(response_id="resp_consent_rejected")
    stream.emit_created()
    tracker = _OutputItemTracker(
        stream, allowed_oauth_consent_origins=_normalize_allowed_oauth_consent_origins(["https://other.example.com"])
    )
    with pytest.raises(ValueError, match="allowed safe HTTPS"):
        async for _ in tracker.handle(Content.from_oauth_consent_request(CONSENT_LINK)):
            pass


# endregion
