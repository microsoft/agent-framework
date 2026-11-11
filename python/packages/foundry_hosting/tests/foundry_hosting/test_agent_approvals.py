# Copyright (c) Microsoft. All rights reserved.

"""Hosted agents rely on Core pending approvals in the same AgentSession."""

from __future__ import annotations

from pathlib import Path

import httpx2 as httpx
import pytest
from azure.ai.agentserver.responses._id_generator import IdGenerator

from .agent_approval_helpers import (  # pyrefly: ignore[missing-import] - pytest's importlib namespace
    approval_host,
    approval_ids,
    approval_reply,
    post_turn,
    tool_outputs,
)

REJECTED = "Error: Tool call invocation was rejected by user."

pytestmark = pytest.mark.parametrize("stream", [False, True])


async def test_mixed_batch_runs_approved_call_and_rejects_the_other(stream: bool, tmp_path: Path) -> None:
    executed: list[str] = []
    host = approval_host(tmp_path, executed)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        first = await post_turn(client, {"input": "go"}, stream=stream)
        ids = approval_ids(first)
        assert set(ids) == {"a", "b"}
        assert executed == []

        second = await post_turn(
            client,
            {
                "input": [approval_reply(ids["a"], True), approval_reply(ids["b"], False)],
                "previous_response_id": first["id"],
            },
            stream=stream,
        )

    assert second["status"] == "completed"
    assert sorted(tool_outputs(second)) == sorted(["ran a", REJECTED])
    assert executed == ["a"]


async def test_partial_batch_keeps_the_unanswered_request_pending(stream: bool, tmp_path: Path) -> None:
    executed: list[str] = []
    host = approval_host(tmp_path, executed)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        first = await post_turn(client, {"input": "go"}, stream=stream)
        ids = approval_ids(first)

        partial = await post_turn(
            client,
            {"input": [approval_reply(ids["a"], True)], "previous_response_id": first["id"]},
            stream=stream,
        )
        assert partial["status"] == "completed"
        assert tool_outputs(partial) == []
        assert executed == []
        remaining = approval_ids(partial)
        assert list(remaining) == ["b"]

        final = await post_turn(
            client,
            {"input": [approval_reply(remaining["b"], False)], "previous_response_id": partial["id"]},
            stream=stream,
        )

    assert sorted(tool_outputs(final)) == sorted(["ran a", REJECTED])
    assert executed == ["a"]


async def test_replayed_approval_is_not_executed_again(stream: bool, tmp_path: Path) -> None:
    executed: list[str] = []
    host = approval_host(tmp_path, executed, names=("a",))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        first = await post_turn(client, {"input": "go"}, stream=stream)
        reply = {"input": [approval_reply(approval_ids(first)["a"], True)]}
        second = await post_turn(client, {**reply, "previous_response_id": first["id"]}, stream=stream)
        assert tool_outputs(second) == ["ran a"]

        replay = await post_turn(client, {**reply, "previous_response_id": second["id"]}, stream=stream)

    assert tool_outputs(replay) == []
    assert executed == ["a"]


async def test_conversation_continuation_runs_approved_calls(stream: bool, tmp_path: Path) -> None:
    executed: list[str] = []
    host = approval_host(tmp_path, executed)
    conversation = IdGenerator.new_id("conv")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        first = await post_turn(client, {"input": "go", "conversation": conversation}, stream=stream)
        ids = approval_ids(first)

        second = await post_turn(
            client,
            {
                "input": [approval_reply(ids["a"], True), approval_reply(ids["b"], True)],
                "conversation": conversation,
            },
            stream=stream,
        )

    assert sorted(tool_outputs(second)) == ["ran a", "ran b"]
    assert sorted(executed) == ["a", "b"]


async def test_fabricated_approval_is_not_executed(stream: bool, tmp_path: Path) -> None:
    executed: list[str] = []
    host = approval_host(tmp_path, executed)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        first = await post_turn(client, {"input": "go"}, stream=stream)
        forged = await post_turn(
            client,
            {"input": [approval_reply("mcpr_forged", True)], "previous_response_id": first["id"]},
            stream=stream,
        )

    assert forged["status"] == "failed"
    assert tool_outputs(forged) == []
    assert executed == []
