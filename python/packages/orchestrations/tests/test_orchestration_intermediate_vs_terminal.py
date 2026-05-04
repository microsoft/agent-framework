# Copyright (c) Microsoft. All rights reserved.

"""Tests for orchestration intermediate vs terminal output labeling.

Verifies that under the strict-output model:
  - Sequential / Concurrent / GroupChat / Magentic designate their terminator,
    aggregator, orchestrator, or manager as the sole output executor; per-step
    yields from non-designated executors emit `type='intermediate'` events.
  - Handoff designates ALL participants — every reply is `type='output'`.
  - When wrapped via `workflow.as_agent()`, intermediate events surface as
    `text_reasoning` content; terminal events as `text` content; existing
    `.text` accessors return terminal-only.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable
from typing import Any, Literal, overload

import pytest
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    BaseAgent,
    Content,
    Message,
    ResponseStream,
)
from agent_framework.orchestrations import ConcurrentBuilder, SequentialBuilder


class _EchoAgent(BaseAgent):
    """Minimal non-streaming agent that returns a single assistant message."""

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...
    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[True],
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(
                    contents=[Content.from_text(text=f"{self.name} reply")], author_name=self.name
                )

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", [f"{self.name} reply"], author_name=self.name)])

        return _run()


# ---------------------------------------------------------------------------
# Sequential
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequential_default_only_terminator_is_output() -> None:
    """Default Sequential (intermediate_outputs=False) designates only the terminator;
    earlier participants surface as type='intermediate'."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c]).build()

    output_events: list[Any] = []
    intermediate_events: list[Any] = []
    async for event in workflow.run("hello", stream=True):
        if event.type == "output":
            output_events.append(event)
        elif event.type == "intermediate":
            intermediate_events.append(event)

    # Only the terminator (C) emits type='output'.
    assert len(output_events) == 1
    assert "C" in {ev.executor_id for ev in output_events}

    # A and B emit type='intermediate'.
    intermediate_executors = {ev.executor_id for ev in intermediate_events}
    assert "A" in intermediate_executors
    assert "B" in intermediate_executors


@pytest.mark.asyncio
async def test_sequential_intermediate_outputs_true_designates_all() -> None:
    """Sequential with intermediate_outputs=True preserves the legacy contract:
    every participant's yield surfaces as type='output'."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c], intermediate_outputs=True).build()
    result = await workflow.run("hello")
    outputs = result.get_outputs()
    # All three participants' yields surface in get_outputs() under intermediate_outputs=True.
    assert len(outputs) == 3


@pytest.mark.asyncio
async def test_sequential_get_outputs_returns_terminator_only() -> None:
    """WorkflowRunResult.get_outputs() returns only the terminator's yield."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")

    workflow = SequentialBuilder(participants=[a, b]).build()
    result = await workflow.run("hi")
    outputs = result.get_outputs()
    assert len(outputs) == 1


# ---------------------------------------------------------------------------
# Concurrent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_default_only_aggregator_is_output() -> None:
    """Default Concurrent (intermediate_outputs=False): only the aggregator is
    designated; participants surface as type='intermediate'."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")

    workflow = ConcurrentBuilder(participants=[a, b]).build()

    output_events: list[Any] = []
    intermediate_events: list[Any] = []
    async for event in workflow.run("hello", stream=True):
        if event.type == "output":
            output_events.append(event)
        elif event.type == "intermediate":
            intermediate_events.append(event)

    # Aggregator is the only designated executor → only it emits type='output'.
    assert len(output_events) == 1

    # Both participants emit type='intermediate'.
    intermediate_authors = {ev.executor_id for ev in intermediate_events}
    assert "A" in intermediate_authors
    assert "B" in intermediate_authors


@pytest.mark.asyncio
async def test_concurrent_intermediate_outputs_true_designates_all() -> None:
    """Concurrent with intermediate_outputs=True designates participants alongside the
    aggregator — every participant's yield surfaces as type='output'."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")

    workflow = ConcurrentBuilder(participants=[a, b], intermediate_outputs=True).build()
    result = await workflow.run("hello")
    outputs = result.get_outputs()
    # Two participants + aggregator → three terminal outputs in get_outputs().
    assert len(outputs) == 3


# ---------------------------------------------------------------------------
# Sequential wrapped as_agent — text_reasoning mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequential_default_as_agent_intermediates_are_text_reasoning() -> None:
    """Default Sequential wrapped as_agent: per-step participant replies become
    text_reasoning content; the terminator's reply becomes text content.
    """
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c]).build()
    agent = workflow.as_agent("seq")

    response = await agent.run("hi")

    # .text returns terminal content only — only C's reply.
    assert response.text == "C reply"

    text_contents = [c for m in response.messages for c in m.contents if c.type == "text"]
    reasoning_contents = [c for m in response.messages for c in m.contents if c.type == "text_reasoning"]

    assert any("C reply" in c.text for c in text_contents)
    assert any("A reply" in c.text for c in reasoning_contents)
    assert any("B reply" in c.text for c in reasoning_contents)


@pytest.mark.asyncio
async def test_sequential_as_agent_intermediate_outputs_true_all_text() -> None:
    """Sequential with intermediate_outputs=True wrapped as_agent: every participant's
    reply is now designated terminal, so each surfaces as text content (not reasoning).
    Existing callers reading .text get all participants' replies concatenated."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c], intermediate_outputs=True).build()
    agent = workflow.as_agent("seq")

    response = await agent.run("hi")
    text_contents = [c for m in response.messages for c in m.contents if c.type == "text"]
    text = " ".join(c.text for c in text_contents)
    assert "A reply" in text
    assert "B reply" in text
    assert "C reply" in text


# ---------------------------------------------------------------------------
# Concurrent wrapped as_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_default_as_agent_participants_are_text_reasoning() -> None:
    """Default Concurrent wrapped as_agent: participant replies are text_reasoning;
    aggregator's yield is text content."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")

    workflow = ConcurrentBuilder(participants=[a, b]).build()
    agent = workflow.as_agent("concurrent")

    response = await agent.run("hi")

    text_contents = [c for m in response.messages for c in m.contents if c.type == "text"]
    reasoning_contents = [c for m in response.messages for c in m.contents if c.type == "text_reasoning"]

    # A's and B's replies are intermediate (text_reasoning).
    assert any("A reply" in c.text for c in reasoning_contents)
    assert any("B reply" in c.text for c in reasoning_contents)

    # The aggregator's default-yielded AgentResponse passes through as text content.
    assert text_contents, "expected at least one terminal text content from the aggregator"
