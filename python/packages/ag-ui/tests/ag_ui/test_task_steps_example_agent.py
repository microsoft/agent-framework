# Copyright (c) Microsoft. All rights reserved.

"""Tests for the task steps example agent used by Dojo."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, MutableSequence
from types import SimpleNamespace
from typing import Any

import pytest
from ag_ui.core import MessagesSnapshotEvent, StateDeltaEvent, StateSnapshotEvent, TextMessageContentEvent
from agent_framework import ChatResponseUpdate, Content, Message

from agent_framework_ag_ui._utils import _AGUI_PROTOCOL_VERSION
from agent_framework_ag_ui_examples.agents import task_steps_agent as task_steps_module

_STEPS = [{"description": "Digging hole", "status": "pending"}, {"description": "Planting tree", "status": "pending"}]


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
def task_steps_agent(streaming_chat_client_stub: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The demo agent over a scripted client: plan the steps, confirm, then summarize."""
    monkeypatch.setattr(task_steps_module, "asyncio", SimpleNamespace(sleep=_no_sleep))

    async def stream_fn(
        messages: MutableSequence[Message], options: dict[str, Any], **kwargs: Any
    ) -> AsyncIterator[ChatResponseUpdate]:
        del options, kwargs
        last = messages[-1]
        if "successfully executed" in (last.text or ""):
            yield ChatResponseUpdate(contents=[Content.from_text(text="Both steps are done.")])
        elif any(content.type == "function_result" for content in last.contents):
            yield ChatResponseUpdate(contents=[Content.from_text(text="I created the plan.")])
        else:
            yield ChatResponseUpdate(
                contents=[
                    Content.from_function_call(
                        name="generate_task_steps", call_id="call-steps", arguments=json.dumps({"steps": _STEPS})
                    )
                ]
            )

    return task_steps_module.task_steps_agent_wrapped(streaming_chat_client_stub(stream_fn))


async def test_predictive_steps_delta_drives_step_execution(task_steps_agent: Any) -> None:
    """The predictive /steps delta is read whichever way ag-ui-protocol models patch operations."""
    events = [
        event
        async for event in task_steps_agent.run(
            {"thread_id": "t1", "run_id": "r1", "messages": [{"id": "u1", "role": "user", "content": "Plant a tree"}]}
        )
    ]

    steps_deltas = [
        event
        for event in events
        if isinstance(event, StateDeltaEvent) and event.model_dump()["delta"][0]["path"] == "/steps"
    ]
    assert steps_deltas
    final_states = [event.snapshot for event in events if isinstance(event, StateSnapshotEvent)]
    assert final_states[-1] == {"steps": [{**step, "status": "completed"} for step in _STEPS]}


async def test_final_snapshot_accepts_history_with_legacy_binary_attachment(task_steps_agent: Any) -> None:
    """The summary MESSAGES_SNAPSHOT replays a legacy binary attachment from the request history."""
    history = [
        {
            "id": "u1",
            "role": "user",
            "content": [
                {"type": "text", "text": "Plan around this photo"},
                {"type": "binary", "mimeType": "image/png", "url": "https://example.com/garden.png"},
            ],
        }
    ]

    events = [event async for event in task_steps_agent.run({"thread_id": "t1", "run_id": "r1", "messages": history})]

    summary_text = "".join(event.delta for event in events if isinstance(event, TextMessageContentEvent))
    assert "Summary generation error" not in summary_text
    final_snapshot = [event for event in events if isinstance(event, MessagesSnapshotEvent)][-1]
    dumped = final_snapshot.model_dump(by_alias=True, exclude_none=True)["messages"]
    assert dumped[-1]["content"] == "Both steps are done."
    attachment = dumped[0]["content"][1]
    if _AGUI_PROTOCOL_VERSION is None:  # ag-ui-protocol < 1.0 still models the binary part
        assert attachment["type"] == "binary"
    else:
        assert attachment == {
            "type": "image",
            "source": {"type": "url", "value": "https://example.com/garden.png", "mimeType": "image/png"},
        }
