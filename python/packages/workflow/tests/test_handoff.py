# Copyright (c) Microsoft. All rights reserved.
"""Tests for the structured / legacy handoff orchestrator.

Focus areas:
- Structured decision probe flow (handoff -> respond -> complete)
- Handoff chaining respects allow_transfers and max_handoffs
- RESPOND with question triggers HITL when enabled (smoke) and is skipped when disabled
- Legacy directive parsing (transfer_to_<agent>, complete_task)
- Fallback when structured JSON malformed -> legacy path

Agents are mocked using a lightweight FakeAgent implementing AgentProtocol.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import pytest
from agent_framework import AgentProtocol, AgentRunResponse, AgentRunResponseUpdate, ChatMessage, Role

from agent_framework_workflow import (
    HandoffAction,
    HandoffBuilder,
    HandoffDecision,
    Workflow,
    WorkflowCompletedEvent,
)


@dataclass
class ScriptedTurn:
    """Represents a single agent turn (structured decision or plain text)."""

    # Structured decision to emit (preferred)
    decision: HandoffDecision | None = None
    # Raw assistant text (legacy path) if decision not provided
    text: str | None = None


class FakeAgent(AgentProtocol):  # type: ignore[misc]
    """Scripted agent implementing AgentProtocol for deterministic tests."""

    def __init__(self, name: str, script: Iterable[ScriptedTurn]):
        self._id = name
        self._name = name
        self._script = list(script)
        self._i = 0

    # Properties required by protocol
    @property
    def id(self) -> str:  # noqa: D401
        return self._id

    @property
    def name(self) -> str:  # noqa: D401
        return self._name

    @property
    def display_name(self) -> str:  # noqa: D401
        return self._name

    @property
    def description(self) -> str | None:  # noqa: D401
        return None

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: Any | None = None,
        response_format: Any | None = None,
        **_: Any,
    ) -> AgentRunResponse:  # noqa: D401
        if self._i >= len(self._script):
            content = ChatMessage(role=Role.ASSISTANT, text=f"{self._name} idle")
            return AgentRunResponse(messages=[content])
        turn = self._script[self._i]
        self._i += 1
        if turn.decision is not None:
            payload = turn.decision.model_dump_json()
            content = ChatMessage(role=Role.ASSISTANT, text=payload)
        else:
            content = ChatMessage(role=Role.ASSISTANT, text=turn.text or "")
        return AgentRunResponse(messages=[content])

    def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: Any | None = None,
        **kwargs: Any,
    ):
        async def _gen():  # pragma: no cover - not used in tests
            yield AgentRunResponseUpdate(role=Role.ASSISTANT, contents=[], message_id="noop")

        return _gen()

    def get_new_thread(self):  # pragma: no cover - not needed for tests
        from agent_framework._threads import AgentThread

        return AgentThread()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _collect_final(workflow: Workflow, user_text: str) -> ChatMessage:
    """Run the workflow to completion and return the final assistant ChatMessage."""
    final_msg: ChatMessage | None = None
    async for event in workflow.run_stream(user_text):
        if isinstance(event, WorkflowCompletedEvent):
            data = getattr(event, "data", None)
            if isinstance(data, ChatMessage):
                final_msg = data
    assert final_msg is not None, "No final message produced"
    return final_msg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_multi_handoff_and_complete():
    """Structured: intake -> specialist -> closer (complete)."""
    intake = FakeAgent(
        "intake",
        [ScriptedTurn(decision=HandoffDecision(action=HandoffAction.HANDOFF, target="spec"))],
    )
    spec = FakeAgent(
        "spec",
        [ScriptedTurn(decision=HandoffDecision(action=HandoffAction.HANDOFF, target="closer"))],
    )
    closer = FakeAgent(
        "closer",
        [ScriptedTurn(decision=HandoffDecision(action=HandoffAction.COMPLETE, summary="done"))],
    )

    wf = (
        HandoffBuilder()
        .participants([intake, spec, closer])
        .start_with("intake")
        .structured_handoff(enabled=True)
        .allow_transfers({
            "intake": [("spec", "")],
            "spec": [("closer", "")],
        })
        .build()
    )

    # run
    msgs: list[ChatMessage] = []
    async for event in wf.run_stream("hi"):
        if isinstance(event, WorkflowCompletedEvent):
            data = getattr(event, "data", None)
            if isinstance(data, ChatMessage):
                msgs.append(data)
    assert msgs, "Expected completion"
    assert "done" in msgs[-1].text.lower()


@pytest.mark.asyncio
async def test_structured_respond_finalizes():
    """Structured respond returns assistant_message as final answer."""
    intake = FakeAgent(
        "intake",
        [ScriptedTurn(decision=HandoffDecision(action=HandoffAction.RESPOND, assistant_message="Answer now"))],
    )
    wf = HandoffBuilder().participants([intake]).start_with("intake").structured_handoff(enabled=True).build()

    result = await _collect_final(wf, "question")
    assert "answer now" in result.text.lower()


@pytest.mark.asyncio
async def test_structured_handoff_respects_max():
    """Exceeding max handoffs produces overflow message containing path."""
    a = FakeAgent("a", [ScriptedTurn(decision=HandoffDecision(action=HandoffAction.HANDOFF, target="b"))])
    b = FakeAgent("b", [ScriptedTurn(decision=HandoffDecision(action=HandoffAction.HANDOFF, target="a"))])

    wf = (
        HandoffBuilder()
        .participants([a, b])
        .start_with("a")
        .structured_handoff(enabled=True)
        .allow_transfers({"a": [("b", "")], "b": [("a", "")]})
        .max_handoffs(1)
        .build()
    )

    final_msg = await _collect_final(wf, "loop")
    assert "could not resolve" in final_msg.text.lower()
    assert "a -> b" in final_msg.text or "b -> a" in final_msg.text


@pytest.mark.asyncio
async def test_legacy_directive_handoff_and_complete():
    """Legacy directives: transfer_to_x + complete_task: summary."""
    # First agent emits legacy transfer directive; second completes
    a = FakeAgent("a", [ScriptedTurn(text="transfer_to_b: reason")])
    b = FakeAgent("b", [ScriptedTurn(text="complete_task: finished work")])

    wf = (
        HandoffBuilder()
        .participants([a, b])
        .start_with("a")
        # legacy mode (structured disabled)
        .allow_transfers({"a": [("b", "")]})
        .build()
    )

    final_msg = await _collect_final(wf, "legacy flow")
    assert "finished work" in final_msg.text.lower()


@pytest.mark.asyncio
async def test_structured_malformed_falls_back_to_legacy():
    """If structured JSON can't parse, legacy first-line directive is still honored."""
    # Agent outputs invalid JSON then a legacy directive
    bad = FakeAgent("bad", [ScriptedTurn(text="{not json}\ntransfer_to_next: go")])
    nxt = FakeAgent("next", [ScriptedTurn(text="complete_task: summary line")])

    wf = (
        HandoffBuilder()
        .participants([bad, nxt])
        .start_with("bad")
        .allow_transfers({"bad": [("next", "")]})
        .structured_handoff(enabled=True)
        .build()
    )

    final_msg = await _collect_final(wf, "bad json")
    assert "summary line" in final_msg.text.lower()


@pytest.mark.asyncio
async def test_structured_complete_includes_assistant_and_summary():
    """COMPLETE returns combined assistant + summary segments when both present."""
    closer = FakeAgent(
        "closer",
        [
            ScriptedTurn(
                decision=HandoffDecision(
                    action=HandoffAction.COMPLETE,
                    summary="task summarized",
                    assistant_message="final detailed answer",
                )
            )
        ],
    )
    wf = HandoffBuilder().participants([closer]).start_with("closer").structured_handoff(enabled=True).build()
    final_msg = await _collect_final(wf, "x")
    txt = final_msg.text.lower()
    assert "task summarized" in txt and "final detailed answer" in txt


@pytest.mark.asyncio
async def test_structured_self_handoff_ignored():
    """Self handoff should not change agent and should finalize if no further instructions."""
    selfy = FakeAgent("selfy", [ScriptedTurn(decision=HandoffDecision(action=HandoffAction.HANDOFF, target="selfy"))])

    wf = HandoffBuilder().participants([selfy]).start_with("selfy").structured_handoff(enabled=True).build()

    # Since self-handoff is ignored and no completion, we expect fallback finalization with message content (empty)
    final_msg = await _collect_final(wf, "hi")
    assert "produced no assistant" in final_msg.text.lower() or final_msg.text == ""
