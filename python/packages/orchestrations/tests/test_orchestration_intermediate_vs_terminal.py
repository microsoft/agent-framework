# Copyright (c) Microsoft. All rights reserved.

"""Tests for orchestration intermediate vs terminal output labeling.

Verifies that under the strict-output model:
  - Sequential / Concurrent / GroupChat / Magentic designate their terminator,
    aggregator, orchestrator, or manager as the sole output executor; per-step
    yields from non-designated executors emit `type='intermediate'` events.
  - Handoff designates ALL participants — every reply is `type='output'`.
  - When wrapped via `workflow.as_agent()`, caller-facing workflow events surface
    with their original content types.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Callable
from typing import Any, ClassVar, Literal, overload

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
from agent_framework.orchestrations import (
    ConcurrentBuilder,
    GroupChatBuilder,
    GroupChatState,
    HandoffBuilder,
    MagenticBuilder,
    MagenticContext,
    MagenticManagerBase,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
    SequentialBuilder,
)


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
    """Default Sequential designates only the terminator; earlier participants are hidden."""
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

    assert not intermediate_events


@pytest.mark.asyncio
async def test_sequential_output_from_designates_workflow_output_participants() -> None:
    """Sequential output_from controls which participant yields surface as workflow output."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c], output_from=["A", "B", "C"]).build()
    result = await workflow.run("hello")
    outputs = result.get_outputs()
    assert len(outputs) == 3


@pytest.mark.asyncio
async def test_sequential_intermediate_output_from_surface_as_intermediate() -> None:
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c], intermediate_output_from=[a, "B"]).build()

    output_executors: set[str] = set()
    intermediate_executors: set[str] = set()
    async for event in workflow.run("hello", stream=True):
        if event.type == "output" and event.executor_id is not None:
            output_executors.add(event.executor_id)
        elif event.type == "intermediate" and event.executor_id is not None:
            intermediate_executors.add(event.executor_id)

    assert output_executors == {"C"}
    assert intermediate_executors == {"A", "B"}


@pytest.mark.asyncio
async def test_sequential_intermediate_can_demote_default_terminator() -> None:
    """Regression: marking the default output terminator as intermediate must not raise an overlap error.

    Sequential's default output list is `[participants[-1]]`. Before the fix, designating that
    same participant via `intermediate_output_from` triggered the
    "Participants cannot be both output and intermediate designated" overlap rejection in
    `_participant_output_config`, contradicting the public contract that
    `intermediate_output_from` can be used independently of `output_from`.
    """
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c], intermediate_output_from=["C"]).build()

    output_executors: set[str] = set()
    intermediate_executors: set[str] = set()
    async for event in workflow.run("hello", stream=True):
        if event.type == "output" and event.executor_id is not None:
            output_executors.add(event.executor_id)
        elif event.type == "intermediate" and event.executor_id is not None:
            intermediate_executors.add(event.executor_id)

    # The default-final list ([C]) is implicitly narrowed by the intermediate designation,
    # so no participant surfaces as terminal output and C surfaces as intermediate.
    assert output_executors == set()
    assert intermediate_executors == {"C"}


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
    """Default Concurrent designates only the aggregator; participants are hidden."""
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

    assert not intermediate_events


@pytest.mark.asyncio
async def test_concurrent_output_from_designates_workflow_output_participants() -> None:
    """Concurrent output_from designates participant outputs alongside the aggregator."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")

    workflow = ConcurrentBuilder(participants=[a, b], output_from=[a, "B"]).build()
    result = await workflow.run("hello")
    outputs = result.get_outputs()
    assert len(outputs) == 3


@pytest.mark.asyncio
async def test_concurrent_intermediate_output_from_surface_as_intermediate() -> None:
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")

    workflow = ConcurrentBuilder(participants=[a, b], intermediate_output_from=["A", b]).build()

    output_executors: set[str] = set()
    intermediate_executors: set[str] = set()
    async for event in workflow.run("hello", stream=True):
        if event.type == "output" and event.executor_id is not None:
            output_executors.add(event.executor_id)
        elif event.type == "intermediate" and event.executor_id is not None:
            intermediate_executors.add(event.executor_id)

    assert "aggregator" in output_executors
    assert intermediate_executors == {"A", "B"}


# ---------------------------------------------------------------------------
# Sequential wrapped as_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequential_default_as_agent_forwards_original_content_types() -> None:
    """Default Sequential wrapped as_agent forwards original content types."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c]).build()
    agent = workflow.as_agent("seq")

    response = await agent.run("hi")

    text_contents = [c for m in response.messages for c in m.contents if c.type == "text"]
    reasoning_contents = [c for m in response.messages for c in m.contents if c.type == "text_reasoning"]

    assert any("C reply" in c.text for c in text_contents)
    assert not reasoning_contents


@pytest.mark.asyncio
async def test_sequential_as_agent_output_from_all_text() -> None:
    """output_from makes designated participant replies normal response text content."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c], output_from=["A", "B", "C"]).build()
    agent = workflow.as_agent("seq")

    response = await agent.run("hi")
    text_contents = [c for m in response.messages for c in m.contents if c.type == "text"]
    text = " ".join(c.text for c in text_contents)
    assert "A reply" in text
    assert "B reply" in text
    assert "C reply" in text


@pytest.mark.asyncio
async def test_sequential_as_agent_intermediate_output_from_keeps_text_content() -> None:
    """intermediate_output_from keeps selected participant replies as their original content type."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c], intermediate_output_from=["A", "B"]).build()
    agent = workflow.as_agent("seq")

    response = await agent.run("hi")

    text_contents = [c for m in response.messages for c in m.contents if c.type == "text"]
    reasoning_contents = [c for m in response.messages for c in m.contents if c.type == "text_reasoning"]
    assert any("C reply" in c.text for c in text_contents)
    assert any("A reply" in c.text for c in text_contents)
    assert any("B reply" in c.text for c in text_contents)
    assert not reasoning_contents


# ---------------------------------------------------------------------------
# Concurrent wrapped as_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_default_as_agent_participants_keep_text_content() -> None:
    """Default Concurrent wrapped as_agent keeps original participant content types."""
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")

    workflow = ConcurrentBuilder(participants=[a, b]).build()
    agent = workflow.as_agent("concurrent")

    response = await agent.run("hi")

    text_contents = [c for m in response.messages for c in m.contents if c.type == "text"]
    reasoning_contents = [c for m in response.messages for c in m.contents if c.type == "text_reasoning"]

    assert not any("A reply" in c.text for c in reasoning_contents)
    assert not any("B reply" in c.text for c in reasoning_contents)

    # The aggregator's default-yielded AgentResponse passes through as text content.
    assert text_contents, "expected at least one terminal text content from the aggregator"


# ---------------------------------------------------------------------------
# GroupChat
# ---------------------------------------------------------------------------


def _two_step_selector() -> Callable[[GroupChatState], str]:
    """Selector that picks each participant once, then keeps the first to keep tests bounded."""
    counter = {"n": 0}

    def _select(state: GroupChatState) -> str:
        participants = list(state.participants.keys())
        step = counter["n"]
        counter["n"] = step + 1
        if step == 0:
            return participants[0]
        if step == 1 and len(participants) > 1:
            return participants[1]
        return participants[0]

    return _select


@pytest.mark.asyncio
async def test_group_chat_default_only_orchestrator_is_output() -> None:
    """Default GroupChat designates only the orchestrator; participant replies are hidden."""
    alpha = _EchoAgent(name="alpha")
    beta = _EchoAgent(name="beta")

    workflow = GroupChatBuilder(
        participants=[alpha, beta],
        max_rounds=2,
        selection_func=_two_step_selector(),
    ).build()

    output_executors: set[str] = set()
    intermediate_executors: set[str] = set()
    async for event in workflow.run("kickoff", stream=True):
        if event.type == "output" and event.executor_id is not None:
            output_executors.add(event.executor_id)
        elif event.type == "intermediate" and event.executor_id is not None:
            intermediate_executors.add(event.executor_id)

    assert "group_chat_orchestrator" in output_executors
    assert "alpha" not in intermediate_executors
    assert "beta" not in intermediate_executors
    # Participants must NOT appear among designated outputs in the default contract.
    assert "alpha" not in output_executors
    assert "beta" not in output_executors


@pytest.mark.asyncio
async def test_group_chat_output_from_designates_workflow_output_participants() -> None:
    """GroupChat output_from designates participants alongside the orchestrator."""
    alpha = _EchoAgent(name="alpha")
    beta = _EchoAgent(name="beta")

    workflow = GroupChatBuilder(
        participants=[alpha, beta],
        max_rounds=2,
        selection_func=_two_step_selector(),
        output_from=[alpha, "beta"],
    ).build()

    output_executors: set[str] = set()
    async for event in workflow.run("kickoff", stream=True):
        if event.type == "output" and event.executor_id is not None:
            output_executors.add(event.executor_id)

    assert {"group_chat_orchestrator", "alpha", "beta"}.issubset(output_executors)


@pytest.mark.asyncio
async def test_group_chat_intermediate_output_from_surface_as_intermediate() -> None:
    alpha = _EchoAgent(name="alpha")
    beta = _EchoAgent(name="beta")

    workflow = GroupChatBuilder(
        participants=[alpha, beta],
        max_rounds=2,
        selection_func=_two_step_selector(),
        intermediate_output_from=["alpha", beta],
    ).build()

    output_executors: set[str] = set()
    intermediate_executors: set[str] = set()
    async for event in workflow.run("kickoff", stream=True):
        if event.type == "output" and event.executor_id is not None:
            output_executors.add(event.executor_id)
        elif event.type == "intermediate" and event.executor_id is not None:
            intermediate_executors.add(event.executor_id)

    assert "group_chat_orchestrator" in output_executors
    assert intermediate_executors == {"alpha", "beta"}


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------


def test_handoff_builder_designates_every_participant_as_output() -> None:
    """Handoff has no intermediate channel — every participant's reply is a primary
    output. The builder must designate all participants in the workflow's
    output designation so each per-agent yield surfaces as type='output'.

    Structural assertion (vs end-to-end) because Handoff agents require a full
    chat-client/middleware stack that we don't want to reproduce in this contract test.
    """
    from agent_framework import Agent
    from agent_framework._clients import BaseChatClient
    from agent_framework._middleware import ChatMiddlewareLayer
    from agent_framework._tools import FunctionInvocationLayer

    class _StubClient(FunctionInvocationLayer[Any], ChatMiddlewareLayer[Any], BaseChatClient[Any]):
        def __init__(self) -> None:
            ChatMiddlewareLayer.__init__(self)
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)

        def _inner_get_response(self, **kwargs: Any) -> Any:  # pragma: no cover - never called
            raise NotImplementedError

    alpha = Agent(
        name="alpha",
        id="alpha",
        client=_StubClient(),
        require_per_service_call_history_persistence=True,
    )
    beta = Agent(
        name="beta",
        id="beta",
        client=_StubClient(),
        require_per_service_call_history_persistence=True,
    )

    workflow = HandoffBuilder(participants=[alpha, beta]).with_start_agent(alpha).build()

    designated = {ex.id for ex in workflow.get_output_executors()}
    assert "alpha" in designated, f"alpha must be designated; got {designated}"
    assert "beta" in designated, f"beta must be designated; got {designated}"


def test_handoff_builder_output_from_can_select_workflow_output_participants() -> None:
    from agent_framework import Agent
    from agent_framework._clients import BaseChatClient
    from agent_framework._middleware import ChatMiddlewareLayer
    from agent_framework._tools import FunctionInvocationLayer

    class _StubClient(FunctionInvocationLayer[Any], ChatMiddlewareLayer[Any], BaseChatClient[Any]):
        def __init__(self) -> None:
            ChatMiddlewareLayer.__init__(self)
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)

        def _inner_get_response(self, **kwargs: Any) -> Any:  # pragma: no cover - never called
            raise NotImplementedError

    alpha = Agent(
        name="alpha",
        id="alpha",
        client=_StubClient(),
        require_per_service_call_history_persistence=True,
    )
    beta = Agent(
        name="beta",
        id="beta",
        client=_StubClient(),
        require_per_service_call_history_persistence=True,
    )

    workflow = HandoffBuilder(participants=[alpha, beta], output_from=["alpha"]).with_start_agent(alpha).build()

    assert {ex.id for ex in workflow.get_output_executors()} == {"alpha"}


def test_handoff_builder_intermediate_output_from_demotes_from_default_output() -> None:
    """Regression: `intermediate_output_from` alone must not collide with the default output list.

    Handoff defaults workflow output to every participant. Before the fix, supplying
    `intermediate_output_from=["alpha"]` without restating `output_from` triggered
    "Participants cannot be both output and intermediate designated: ['alpha']" because
    alpha was simultaneously in the default output list and the explicit intermediate list.
    The contract documented at `_handoff.py:619-622` promises `intermediate_output_from` is
    usable on its own.
    """
    from agent_framework import Agent
    from agent_framework._clients import BaseChatClient
    from agent_framework._middleware import ChatMiddlewareLayer
    from agent_framework._tools import FunctionInvocationLayer

    class _StubClient(FunctionInvocationLayer[Any], ChatMiddlewareLayer[Any], BaseChatClient[Any]):
        def __init__(self) -> None:
            ChatMiddlewareLayer.__init__(self)
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)

        def _inner_get_response(self, **kwargs: Any) -> Any:  # pragma: no cover - never called
            raise NotImplementedError

    alpha = Agent(name="alpha", id="alpha", client=_StubClient(), require_per_service_call_history_persistence=True)
    beta = Agent(name="beta", id="beta", client=_StubClient(), require_per_service_call_history_persistence=True)

    workflow = (
        HandoffBuilder(participants=[alpha, beta], intermediate_output_from=["alpha"]).with_start_agent(alpha).build()
    )

    # alpha is implicitly removed from the default-final set; beta remains final.
    assert {ex.id for ex in workflow.get_output_executors()} == {"beta"}
    assert {ex.id for ex in workflow.get_intermediate_executors()} == {"alpha"}


# ---------------------------------------------------------------------------
# Magentic
# ---------------------------------------------------------------------------


class _StubMagenticManager(MagenticManagerBase):
    """Deterministic manager that finishes after one round with a fixed final answer."""

    FINAL_ANSWER: ClassVar[str] = "MAGENTIC_FINAL"

    def __init__(self) -> None:
        super().__init__(max_stall_count=3)
        self.name = "magentic_manager"
        self.next_speaker_name = "alpha"

    async def plan(self, magentic_context: MagenticContext) -> Message:
        return Message("assistant", ["Plan: do the thing."], author_name=self.name)

    async def replan(self, magentic_context: MagenticContext) -> Message:
        return Message("assistant", ["Replan."], author_name=self.name)

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
        is_satisfied = len(magentic_context.chat_history) > 1
        return MagenticProgressLedger(
            is_request_satisfied=MagenticProgressLedgerItem(reason="t", answer=is_satisfied),
            is_in_loop=MagenticProgressLedgerItem(reason="t", answer=False),
            is_progress_being_made=MagenticProgressLedgerItem(reason="t", answer=True),
            next_speaker=MagenticProgressLedgerItem(reason="t", answer=self.next_speaker_name),
            instruction_or_question=MagenticProgressLedgerItem(reason="t", answer="Go."),
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> Message:
        return Message("assistant", [self.FINAL_ANSWER], author_name=self.name)


def test_magentic_builder_default_only_manager_designated() -> None:
    """Default Magentic: only the orchestrator (manager) is designated for terminal output;
    participant replies surface as type='intermediate'.

    Structural assertion on the workflow's output designation because exercising a Magentic
    plan/replan loop end-to-end is heavy and orthogonal to this contract.
    """
    manager = _StubMagenticManager()
    alpha = _EchoAgent(name="alpha")

    workflow = MagenticBuilder(participants=[alpha], manager=manager).build()

    designated = {ex.id for ex in workflow.get_output_executors()}
    assert "magentic_orchestrator" in designated, f"manager must be designated; got {designated}"
    assert "alpha" not in designated, f"participant must not be designated by default; got {designated}"


def test_magentic_builder_output_from_designates_workflow_output_participants() -> None:
    """Magentic output_from designates workers alongside the orchestrator."""
    manager = _StubMagenticManager()
    alpha = _EchoAgent(name="alpha")

    workflow = MagenticBuilder(participants=[alpha], manager=manager, output_from=["alpha"]).build()

    designated = {ex.id for ex in workflow.get_output_executors()}
    assert {"magentic_orchestrator", "alpha"}.issubset(designated)


def test_magentic_builder_intermediate_output_from_designates_intermediate_workers() -> None:
    manager = _StubMagenticManager()
    alpha = _EchoAgent(name="alpha")

    workflow = MagenticBuilder(participants=[alpha], manager=manager, intermediate_output_from=[alpha]).build()

    assert {ex.id for ex in workflow.get_output_executors()} == {"magentic_orchestrator"}
    assert {ex.id for ex in workflow.get_intermediate_executors()} == {"alpha"}


def test_sequential_output_from_all_selects_all_participants() -> None:
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(participants=[a, b, c], output_from="all").build()

    assert {ex.id for ex in workflow.get_output_executors()} == {"A", "B", "C"}


def test_sequential_intermediate_output_from_all_other_selects_non_outputs() -> None:
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")
    c = _EchoAgent(name="C")

    workflow = SequentialBuilder(
        participants=[a, b, c], output_from=["C"], intermediate_output_from="all_other"
    ).build()

    assert {ex.id for ex in workflow.get_output_executors()} == {"C"}
    assert {ex.id for ex in workflow.get_intermediate_executors()} == {"A", "B"}


def test_sequential_all_other_with_omitted_output_from_selects_all_intermediate() -> None:
    a = _EchoAgent(name="A")
    b = _EchoAgent(name="B")

    workflow = SequentialBuilder(participants=[a, b], intermediate_output_from="all_other").build()

    assert {ex.id for ex in workflow.get_output_executors()} == set()
    assert {ex.id for ex in workflow.get_intermediate_executors()} == {"A", "B"}


# ---------------------------------------------------------------------------
# Participant designation validation
# ---------------------------------------------------------------------------


def _build_sequential_with_designation(**kwargs: Any) -> None:
    SequentialBuilder(participants=[_EchoAgent(name="alpha"), _EchoAgent(name="beta")], **kwargs).build()


def _build_concurrent_with_designation(**kwargs: Any) -> None:
    ConcurrentBuilder(participants=[_EchoAgent(name="alpha"), _EchoAgent(name="beta")], **kwargs).build()


def _build_group_chat_with_designation(**kwargs: Any) -> None:
    GroupChatBuilder(
        participants=[_EchoAgent(name="alpha"), _EchoAgent(name="beta")],
        max_rounds=1,
        selection_func=_two_step_selector(),
        **kwargs,
    ).build()


def _build_magentic_with_designation(**kwargs: Any) -> None:
    MagenticBuilder(participants=[_EchoAgent(name="alpha")], manager=_StubMagenticManager(), **kwargs).build()


def _build_handoff_with_designation(**kwargs: Any) -> None:
    from agent_framework import Agent
    from agent_framework._clients import BaseChatClient
    from agent_framework._middleware import ChatMiddlewareLayer
    from agent_framework._tools import FunctionInvocationLayer

    class _StubClient(FunctionInvocationLayer[Any], ChatMiddlewareLayer[Any], BaseChatClient[Any]):
        def __init__(self) -> None:
            ChatMiddlewareLayer.__init__(self)
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)

        def _inner_get_response(self, **kwargs: Any) -> Any:  # pragma: no cover - never called
            raise NotImplementedError

    alpha = Agent(
        name="alpha",
        id="alpha",
        client=_StubClient(),
        require_per_service_call_history_persistence=True,
    )
    beta = Agent(
        name="beta",
        id="beta",
        client=_StubClient(),
        require_per_service_call_history_persistence=True,
    )
    HandoffBuilder(participants=[alpha, beta], **kwargs).with_start_agent(alpha).build()


@pytest.mark.parametrize(
    "build",
    [
        _build_sequential_with_designation,
        _build_concurrent_with_designation,
        _build_group_chat_with_designation,
        _build_magentic_with_designation,
        _build_handoff_with_designation,
    ],
)
@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"output_from": [], "intermediate_output_from": []}, "cannot both be empty"),
        ({"output_from": ["alpha", "alpha"]}, "Duplicate output participant"),
        ({"output_from": ["alpha"], "intermediate_output_from": ["alpha"]}, "cannot be both output"),
        ({"output_from": ["missing"]}, "Unknown output participant"),
        ({"output_from": "all_other"}, "output_from='all_other'"),
    ],
)
def test_participant_output_config_validation(build: Callable[..., None], kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        build(**kwargs)


@pytest.mark.parametrize(
    "build",
    [
        _build_sequential_with_designation,
        _build_concurrent_with_designation,
        _build_group_chat_with_designation,
        _build_magentic_with_designation,
        _build_handoff_with_designation,
    ],
)
def test_participant_output_config_rejects_final_output_from_parameter(build: Callable[..., None]) -> None:
    with pytest.raises(TypeError, match="final_output_from"):
        build(final_output_from=["beta"])
