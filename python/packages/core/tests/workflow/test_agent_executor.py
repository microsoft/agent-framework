# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import AsyncIterable, Awaitable
from typing import TYPE_CHECKING, Any

import pytest

from agent_framework import (
    AgentExecutor,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    Message,
    ResponseStream,
    WorkflowRunState,
)
from agent_framework._workflows._agent_executor import AgentExecutorResponse
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage
from agent_framework.orchestrations import SequentialBuilder

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture


class _CountingAgent(BaseAgent):
    """Agent that echoes messages with a counter to verify session state persistence."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.call_count = 0

    def run(
        self,
        messages: str | Message | list[str] | list[Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        self.call_count += 1
        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(
                    contents=[Content.from_text(text=f"Response #{self.call_count}: {self.name}")]
                )

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", [f"Response #{self.call_count}: {self.name}"])])

        return _run()


class _StreamingHookAgent(BaseAgent):
    """Agent that exposes whether its streaming result hook was executed."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.result_hook_called = False

    def run(
        self,
        messages: str | Message | list[str] | list[Message] | None = None,
        *,
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        if stream:

            async def _stream() -> AsyncIterable[AgentResponseUpdate]:
                yield AgentResponseUpdate(
                    contents=[Content.from_text(text="hook test")],
                    role="assistant",
                )

            async def _mark_result_hook_called(response: AgentResponse) -> AgentResponse:
                self.result_hook_called = True
                return response

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates).with_result_hook(
                _mark_result_hook_called
            )

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", ["hook test"])])

        return _run()


async def test_agent_executor_streaming_finalizes_stream_and_runs_result_hooks() -> None:
    """AgentExecutor should call get_final_response() so stream result hooks execute."""
    agent = _StreamingHookAgent(id="hook_agent", name="HookAgent")
    executor = AgentExecutor(agent, id="hook_exec")
    workflow = SequentialBuilder(participants=[executor]).build()

    output_events: list[Any] = []
    async for event in workflow.run("run hook test", stream=True):
        if event.type == "output":
            output_events.append(event)

    assert output_events
    assert agent.result_hook_called


async def test_agent_executor_checkpoint_stores_and_restores_state() -> None:
    """Test that workflow checkpoint stores AgentExecutor's cache and session states and restores them correctly."""
    storage = InMemoryCheckpointStorage()

    # Create initial agent with a custom session
    initial_agent = _CountingAgent(id="test_agent", name="TestAgent")
    initial_session = AgentSession()

    # Add some initial messages to the session state to verify session state persistence
    initial_messages = [
        Message(role="user", text="Initial message 1"),
        Message(role="assistant", text="Initial response 1"),
    ]
    initial_session.state["history"] = {"messages": initial_messages}

    # Create AgentExecutor with the session
    executor = AgentExecutor(initial_agent, session=initial_session)

    # Build workflow with checkpointing enabled
    wf = SequentialBuilder(participants=[executor], checkpoint_storage=storage).build()

    # Run the workflow with a user message
    first_run_output: AgentExecutorResponse | None = None
    async for ev in wf.run("First workflow run", stream=True):
        if ev.type == "output":
            first_run_output = ev.data  # type: ignore[assignment]
        if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
            break

    assert first_run_output is not None
    assert initial_agent.call_count == 1

    # Verify checkpoint was created
    checkpoints = await storage.list_checkpoints(workflow_name=wf.name)
    assert len(checkpoints) >= 2, (
        "Expected at least 2 checkpoints. The first one is after the start executor, "
        "and the second one is after the agent execution."
    )

    # Get the second checkpoint which should contain the state after processing
    # the first message by the start executor in the sequential workflow
    checkpoints.sort(key=lambda cp: cp.timestamp)
    restore_checkpoint = checkpoints[1]

    # Verify checkpoint contains executor state with both cache and session
    assert "_executor_state" in restore_checkpoint.state
    executor_states = restore_checkpoint.state["_executor_state"]
    assert isinstance(executor_states, dict)
    assert executor.id in executor_states

    executor_state = executor_states[executor.id]  # type: ignore[index]
    assert "cache" in executor_state, "Checkpoint should store executor cache state"
    assert "agent_session" in executor_state, "Checkpoint should store executor session state"

    # Verify session state structure
    session_state = executor_state["agent_session"]  # type: ignore[index]
    assert "session_id" in session_state, "Session state should include session_id"
    assert "state" in session_state, "Session state should include state dict"

    # Verify checkpoint contains pending requests from agents and responses to be sent
    assert "pending_agent_requests" in executor_state
    assert "pending_responses_to_agent" in executor_state

    # Create a new agent and executor for restoration
    # This simulates starting from a fresh state and restoring from checkpoint
    restored_agent = _CountingAgent(id="test_agent", name="TestAgent")
    restored_session = AgentSession()
    restored_executor = AgentExecutor(restored_agent, session=restored_session)

    # Verify the restored agent starts with a fresh state
    assert restored_agent.call_count == 0

    # Build new workflow with the restored executor
    wf_resume = SequentialBuilder(participants=[restored_executor], checkpoint_storage=storage).build()

    # Resume from checkpoint
    resumed_output: AgentExecutorResponse | None = None
    async for ev in wf_resume.run(checkpoint_id=restore_checkpoint.checkpoint_id, stream=True):
        if ev.type == "output":
            resumed_output = ev.data  # type: ignore[assignment]
        if ev.type == "status" and ev.state in (
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        ):
            break

    assert resumed_output is not None

    # Verify the restored executor's session state was restored
    restored_session_obj = restored_executor._session  # type: ignore[reportPrivateUsage]
    assert restored_session_obj is not None
    assert restored_session_obj.session_id == initial_session.session_id


async def test_agent_executor_save_and_restore_state_directly() -> None:
    """Test AgentExecutor's on_checkpoint_save and on_checkpoint_restore methods directly."""
    # Create agent with session containing state
    agent = _CountingAgent(id="direct_test_agent", name="DirectTestAgent")
    session = AgentSession()

    # Add messages to session state
    session_messages = [
        Message(role="user", text="Message in session 1"),
        Message(role="assistant", text="Session response 1"),
        Message(role="user", text="Message in session 2"),
    ]
    session.state["history"] = {"messages": session_messages}

    executor = AgentExecutor(agent, session=session)

    # Add messages to executor cache
    cache_messages = [
        Message(role="user", text="Cached user message"),
        Message(role="assistant", text="Cached assistant response"),
    ]
    executor._cache = list(cache_messages)  # type: ignore[reportPrivateUsage]

    # Snapshot the state
    state = await executor.on_checkpoint_save()

    # Verify snapshot contains both cache and session
    assert "cache" in state
    assert "agent_session" in state

    # Verify session state structure
    session_state = state["agent_session"]  # type: ignore[index]
    assert "session_id" in session_state
    assert "state" in session_state

    # Create new executor to restore into
    new_agent = _CountingAgent(id="direct_test_agent", name="DirectTestAgent")
    new_session = AgentSession()
    new_executor = AgentExecutor(new_agent, session=new_session)

    # Verify new executor starts empty
    assert len(new_executor._cache) == 0  # type: ignore[reportPrivateUsage]
    assert len(new_session.state) == 0

    # Restore state
    await new_executor.on_checkpoint_restore(state)

    # Verify cache is restored
    restored_cache = new_executor._cache  # type: ignore[reportPrivateUsage]
    assert len(restored_cache) == len(cache_messages)
    assert restored_cache[0].text == "Cached user message"
    assert restored_cache[1].text == "Cached assistant response"

    # Verify session was restored with correct session_id
    restored_session = new_executor._session  # type: ignore[reportPrivateUsage]
    assert restored_session.session_id == session.session_id


async def test_agent_executor_run_with_session_kwarg_does_not_raise() -> None:
    """Passing session= via workflow.run() should not cause a duplicate-keyword TypeError (#4295)."""
    agent = _CountingAgent(id="session_kwarg_agent", name="SessionKwargAgent")
    executor = AgentExecutor(agent, id="session_kwarg_exec")
    workflow = SequentialBuilder(participants=[executor]).build()

    # This previously raised: TypeError: run() got multiple values for keyword argument 'session'
    result = await workflow.run("hello", session="user-supplied-value")
    assert result is not None
    assert agent.call_count == 1


async def test_agent_executor_run_streaming_with_stream_kwarg_does_not_raise() -> None:
    """Passing stream= via workflow.run() kwargs should not cause a duplicate-keyword TypeError."""
    agent = _CountingAgent(id="stream_kwarg_agent", name="StreamKwargAgent")
    executor = AgentExecutor(agent, id="stream_kwarg_exec")
    workflow = SequentialBuilder(participants=[executor]).build()

    # stream=True at workflow level triggers streaming mode (returns async iterable)
    events = []
    async for event in workflow.run("hello", stream=True):
        events.append(event)
    assert len(events) > 0
    assert agent.call_count == 1


@pytest.mark.parametrize("reserved_kwarg", ["session", "stream", "messages"])
async def test_prepare_agent_run_args_strips_reserved_kwargs(
    reserved_kwarg: str, caplog: "LogCaptureFixture"
) -> None:
    """_prepare_agent_run_args must remove reserved kwargs and log a warning."""
    raw = {reserved_kwarg: "should-be-stripped", "custom_key": "keep-me"}

    with caplog.at_level(logging.WARNING):
        run_kwargs, options = AgentExecutor._prepare_agent_run_args(raw)

    assert reserved_kwarg not in run_kwargs
    assert "custom_key" in run_kwargs
    assert options is not None
    assert options["additional_function_arguments"]["custom_key"] == "keep-me"
    assert any(reserved_kwarg in record.message for record in caplog.records)


async def test_prepare_agent_run_args_preserves_non_reserved_kwargs() -> None:
    """Non-reserved workflow kwargs should pass through unchanged."""
    raw = {"custom_param": "value", "another": 42}
    run_kwargs, options = AgentExecutor._prepare_agent_run_args(raw)
    assert run_kwargs["custom_param"] == "value"
    assert run_kwargs["another"] == 42


async def test_prepare_agent_run_args_strips_all_reserved_kwargs_at_once(
    caplog: "LogCaptureFixture",
) -> None:
    """All reserved kwargs should be stripped when supplied together, each emitting a warning."""
    raw = {"session": "x", "stream": True, "messages": [], "custom": 1}

    with caplog.at_level(logging.WARNING):
        run_kwargs, options = AgentExecutor._prepare_agent_run_args(raw)

    assert "session" not in run_kwargs
    assert "stream" not in run_kwargs
    assert "messages" not in run_kwargs
    assert run_kwargs["custom"] == 1
    assert options is not None
    assert options["additional_function_arguments"]["custom"] == 1

    warned_keys = {r.message.split("'")[1] for r in caplog.records if "reserved" in r.message.lower()}
    assert warned_keys == {"session", "stream", "messages"}


async def test_agent_executor_run_with_messages_kwarg_does_not_raise() -> None:
    """Passing messages= via workflow.run() kwargs should not cause a duplicate-keyword TypeError."""
    agent = _CountingAgent(id="messages_kwarg_agent", name="MessagesKwargAgent")
    executor = AgentExecutor(agent, id="messages_kwarg_exec")
    workflow = SequentialBuilder(participants=[executor]).build()

    result = await workflow.run("hello", messages=["stale"])
    assert result is not None
    assert agent.call_count == 1
