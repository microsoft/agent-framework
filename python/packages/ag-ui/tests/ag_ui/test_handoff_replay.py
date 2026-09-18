# Copyright (c) Microsoft. All rights reserved.

"""Acceptance tests for replayable AG-UI workflow handoffs."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, cast

import httpx
from agent_framework import Agent, ChatOptions, ChatResponseUpdate, Content, Message, Workflow
from agent_framework.orchestrations import HandoffBuilder
from conftest import StreamingChatClientStub  # pyrefly: ignore[missing-import] # pyright: ignore[reportMissingImports]
from fastapi import FastAPI

from agent_framework_ag_ui import AgentFrameworkWorkflow, AGUIChatClient, add_agent_framework_fastapi_endpoint
from agent_framework_ag_ui._workflow_run import run_workflow_stream


def _as_handoff_agent(agent: Any) -> Agent:
    return cast(Agent, agent)


def _unmatched_function_call_ids(messages: Sequence[Message]) -> set[str]:
    pending: set[str] = set()
    for message in messages:
        for content in message.contents:
            if content.type == "function_call" and content.call_id:
                pending.add(content.call_id)
            elif content.type == "function_result" and content.call_id:
                pending.discard(content.call_id)
    return pending


def _build_handoff_workflow(
    triage_requests: list[list[Message]] | None = None,
) -> Workflow:
    triage_invocation = 0
    specialist_invocation = 0

    async def triage_stream(
        messages: Sequence[Message], options: Any, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        nonlocal triage_invocation
        del options, kwargs
        unmatched_call_ids = _unmatched_function_call_ids(messages)
        if unmatched_call_ids:
            raise ValueError(f"No tool output found for function call {sorted(unmatched_call_ids)[0]}")
        if triage_requests is not None:
            triage_requests.append(list(messages))

        if triage_invocation == 0:
            yield ChatResponseUpdate(
                contents=[
                    Content.from_function_call(
                        call_id="handoff-call",
                        name="handoff_to_specialist",
                        arguments={},
                    )
                ],
                role=None,
            )
        else:
            yield ChatResponseUpdate(contents=[Content.from_text("Triage follow-up response")], role="assistant")
        triage_invocation += 1

    async def specialist_stream(
        messages: Sequence[Message], options: Any, **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        nonlocal specialist_invocation
        del options, kwargs
        unmatched_call_ids = _unmatched_function_call_ids(messages)
        if unmatched_call_ids:
            raise ValueError(f"No tool output found for function call {sorted(unmatched_call_ids)[0]}")
        specialist_invocation += 1
        yield ChatResponseUpdate(
            contents=[Content.from_text(f"Specialist response {specialist_invocation}")],
            role="assistant",
        )

    triage = Agent(
        id="triage",
        name="triage",
        client=StreamingChatClientStub(triage_stream),
        require_per_service_call_history_persistence=True,
    )
    specialist = Agent(
        id="specialist",
        name="specialist",
        client=StreamingChatClientStub(specialist_stream),
        require_per_service_call_history_persistence=True,
    )
    return (
        HandoffBuilder(
            participants=[_as_handoff_agent(triage), _as_handoff_agent(specialist)],
            termination_condition=lambda conversation: bool(
                conversation and conversation[-1].role == "assistant" and conversation[-1].text
            ),
        )
        .with_start_agent(_as_handoff_agent(triage))
        .build()
    )


async def test_real_handoff_runner_emits_replayable_tool_result() -> None:
    """A real HandoffBuilder run should expose its synthetic result under the original call ID."""
    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "Route this request"}]},
            _build_handoff_workflow(),
        )
    ]

    handoff_events = [
        event
        for event in events
        if event.type in {"TOOL_CALL_START", "TOOL_CALL_END", "TOOL_CALL_RESULT"}
        and getattr(event, "tool_call_id", None) == "handoff-call"
    ]
    assert [event.type for event in handoff_events] == [
        "TOOL_CALL_START",
        "TOOL_CALL_END",
        "TOOL_CALL_RESULT",
    ]
    assert json.loads(handoff_events[-1].content) == {"handoff_to": "specialist"}  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    assert events.index(handoff_events[-1]) < next(i for i, event in enumerate(events) if event.type == "RUN_FINISHED")


async def test_outer_agent_replays_balanced_handoff_on_second_turn() -> None:
    """An outer Agent should replay a balanced handoff transcript to the workflow on turn two."""
    triage_requests: list[list[Message]] = []
    workflow_runner = AgentFrameworkWorkflow(
        workflow_factory=lambda _thread_id: _build_handoff_workflow(triage_requests)
    )
    app = FastAPI()
    add_agent_framework_fastapi_endpoint(app, workflow_runner, path="/workflow", keepalive_seconds=None)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        agui_client = AGUIChatClient(
            endpoint="http://testserver/workflow",
            http_client=http_client,
        )
        outer_options: ChatOptions = {"metadata": {"thread_id": "handoff-thread"}}
        outer_agent = Agent(
            name="outer",
            client=cast(Any, agui_client),
            default_options=outer_options,
        )
        session = outer_agent.create_session()

        first_response = await outer_agent.run("Route this request", session=session)
        second_response = await outer_agent.run("Continue on the same thread", session=session)

    first_contents = [content for message in first_response.messages for content in message.contents]
    assert [content.call_id for content in first_contents if content.type == "function_call"] == ["handoff-call"]
    assert [content.call_id for content in first_contents if content.type == "function_result"] == ["handoff-call"]
    first_call_index = next(
        index
        for index, message in enumerate(first_response.messages)
        if any(content.type == "function_call" and content.call_id == "handoff-call" for content in message.contents)
    )
    first_result_index = next(
        index
        for index, message in enumerate(first_response.messages)
        if any(content.type == "function_result" and content.call_id == "handoff-call" for content in message.contents)
    )
    assert first_call_index < first_result_index
    assert second_response.text == "Triage follow-up response"
    assert len(triage_requests) == 2
    assert _unmatched_function_call_ids(triage_requests[1]) == set()
