# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import gc
import logging
import threading
import weakref
from contextlib import suppress
from typing import Any

import pytest

from agent_framework import (
    AgentResponse,
    AgentSession,
    BackgroundAgentsProvider,
    BackgroundTaskInfo,
    BackgroundTaskStatus,
    Message,
    ServiceSessionId,
)
from agent_framework._harness import _background_agents
from agent_framework._sessions import SessionContext

# Suppress "coroutine was never awaited" warnings from task cancellation in tests.
# This occurs when cancelling tasks that wrap coroutines through _run_agent().
pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning:asyncio")

# --- Test Helpers ---


class _FakeAgent:
    """Minimal agent stub for testing background agent delegation."""

    def __init__(
        self,
        name: str,
        description: str | None = None,
        *,
        response_text: str = "done",
        delay: float = 0.0,
        should_fail: bool = False,
    ):
        self.id = f"agent-{name}"
        self.name = name
        self.description = description
        self._response_text = response_text
        self._delay = delay
        self._should_fail = should_fail

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(
        self,
        service_session_id: str | ServiceSessionId,
        *,
        session_id: str | None = None,
    ) -> AgentSession:
        return AgentSession(service_session_id=service_session_id, session_id=session_id)

    async def run(
        self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any
    ) -> AgentResponse[Any]:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        if self._should_fail:
            raise RuntimeError("Agent execution failed")
        return AgentResponse(messages=[Message(role="assistant", contents=[self._response_text])])


def _make_provider(*agents: _FakeAgent) -> BackgroundAgentsProvider:
    """Create a provider with given agents."""
    return BackgroundAgentsProvider(agents)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]


def _make_session() -> AgentSession:
    """Create a session for testing."""
    return AgentSession()


async def _get_tools(provider: BackgroundAgentsProvider, session: AgentSession) -> dict[str, Any]:
    """Run before_run and return tools by name."""
    context = SessionContext(input_messages=[])
    await provider.before_run(agent=None, session=session, context=context, state={})
    tools_by_name: dict[str, Any] = {}
    for t in context.tools:
        tools_by_name[t.name if hasattr(t, "name") else str(t)] = t
    return tools_by_name


async def _invoke_tool(tool_obj: Any, **kwargs: Any) -> str:
    """Invoke a FunctionTool and return the raw result string."""
    return await tool_obj.invoke(arguments=kwargs, skip_parsing=True)


# --- Constructor Tests ---


def test_constructor_requires_at_least_one_agent() -> None:
    """Should reject empty agent list."""
    with pytest.raises(ValueError, match="At least one background agent"):
        BackgroundAgentsProvider([])


def test_constructor_requires_agent_names() -> None:
    """Should reject agents with no name."""
    agent = _FakeAgent("")
    with pytest.raises(ValueError, match="non-empty name"):
        BackgroundAgentsProvider([agent])  # type: ignore[list-item]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]


def test_constructor_rejects_duplicate_names() -> None:
    """Should reject duplicate agent names (case-insensitive)."""
    agent1 = _FakeAgent("Research")
    agent2 = _FakeAgent("research")
    with pytest.raises(ValueError, match="Duplicate background agent name"):
        BackgroundAgentsProvider([agent1, agent2])  # type: ignore[list-item]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]


def test_constructor_valid_agents() -> None:
    """Should succeed with valid unique agents."""
    provider = BackgroundAgentsProvider([_FakeAgent("Alpha"), _FakeAgent("Beta")])  # type: ignore[list-item]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
    assert provider.source_id == "background_agents"


def test_constructor_custom_source_id() -> None:
    """Should accept custom source_id."""
    provider = BackgroundAgentsProvider([_FakeAgent("Agent1")], source_id="custom_bg")  # type: ignore[list-item]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
    assert provider.source_id == "custom_bg"


def test_constructor_uses_default_wait_timeout() -> None:
    """Should use a bounded five-minute wait by default."""
    provider = _make_provider(_FakeAgent("Worker"))
    assert provider._wait_timeout_seconds == 300


@pytest.mark.parametrize("wait_timeout_seconds", [0, -1, True, 1.5, float("inf"), float("nan")])
def test_constructor_rejects_invalid_wait_timeout(wait_timeout_seconds: object) -> None:
    """Should reject wait timeouts that are not positive integers."""
    with pytest.raises(ValueError, match="positive integer"):
        BackgroundAgentsProvider(
            [_FakeAgent("Worker")],  # type: ignore[list-item]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
            wait_timeout_seconds=wait_timeout_seconds,  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        )


# --- Tool Injection Tests ---


async def test_before_run_injects_six_tools() -> None:
    """before_run should inject exactly 6 tools."""
    provider = _make_provider(_FakeAgent("Worker"))
    tools = await _get_tools(provider, _make_session())
    assert len(tools) == 6
    expected_names = {
        "background_agents_start_task",
        "background_agents_wait_for_first_completion",
        "background_agents_get_task_results",
        "background_agents_get_all_tasks",
        "background_agents_continue_task",
        "background_agents_clear_completed_task",
    }
    assert set(tools.keys()) == expected_names


async def test_wait_timeout_is_not_model_settable() -> None:
    """The model-facing wait tool should only accept task IDs."""
    provider = _make_provider(_FakeAgent("Worker"))
    tools = await _get_tools(provider, _make_session())
    wait_tool = tools["background_agents_wait_for_first_completion"]
    wait_parameters = wait_tool.parameters()
    assert set(wait_parameters["properties"]) == {"task_ids"}
    assert "configured timeout expires" in wait_tool.description
    assert "tasks remain running" in wait_tool.description
    assert "called again" in wait_tool.description


async def test_before_run_injects_instructions() -> None:
    """before_run should inject instructions mentioning agent names."""
    provider = _make_provider(_FakeAgent("ResearchBot", "Does research"))
    context = SessionContext(input_messages=[])
    session = _make_session()
    await provider.before_run(agent=None, session=session, context=context, state={})
    all_instructions = " ".join(context.instructions)
    assert "ResearchBot" in all_instructions
    assert "Does research" in all_instructions


# --- Start Task Tests ---


async def test_start_task_success() -> None:
    """Should start a task and return confirmation."""
    provider = _make_provider(_FakeAgent("Worker", response_text="result"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="do something",
        description="test task",
    )
    assert "task 1 started" in result.lower()
    assert "Worker" in result


async def test_start_task_unknown_agent() -> None:
    """Should return error for unknown agent name."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="NonExistent",
        input="do something",
        description="test",
    )
    assert "Error" in result
    assert "NonExistent" in result


async def test_start_task_increments_ids() -> None:
    """Task IDs should increment sequentially."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    r1 = await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="task 1",
        description="first",
    )
    r2 = await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="task 2",
        description="second",
    )
    assert "task 1 started" in r1.lower()
    assert "task 2 started" in r2.lower()


# --- Get All Tasks Tests ---


async def test_get_all_tasks_empty() -> None:
    """Should return 'No tasks.' when no tasks exist."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(tools["background_agents_get_all_tasks"])
    assert "No tasks" in result


async def test_get_all_tasks_shows_tasks() -> None:
    """Should list all tasks with status and description."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="hello",
        description="my task",
    )
    result = await _invoke_tool(tools["background_agents_get_all_tasks"])
    assert "my task" in result
    assert "Worker" in result


# --- Wait for Completion Tests ---


@pytest.mark.parametrize("continuation_state", ["running", "completed", "finalized", "failed"])
@pytest.mark.parametrize("first_outcome", ["completed", "failed", "cancelled"])
async def test_wait_does_not_finalize_a_continued_task(
    monkeypatch: pytest.MonkeyPatch, continuation_state: str, first_outcome: str
) -> None:
    """A waiter for an earlier execution must not consume a continuation's task."""
    first_release = asyncio.Event()
    second_started = asyncio.Event()
    second_release = asyncio.Event()
    wait_started = asyncio.Event()
    wait_completed = asyncio.Event()
    release_waiter = asyncio.Event()

    class ContinuingAgent(_FakeAgent):
        async def run(self, messages: Any = None, **kwargs: Any) -> AgentResponse[Any]:
            if messages == "first":
                await first_release.wait()
                if first_outcome == "failed":
                    raise RuntimeError("first failed")
                if first_outcome == "cancelled":
                    raise asyncio.CancelledError
                return AgentResponse(messages=[Message(role="assistant", contents=["first result"])])
            second_started.set()
            await second_release.wait()
            if continuation_state == "failed":
                raise RuntimeError("continuation failed")
            return AgentResponse(messages=[Message(role="assistant", contents=["second result"])])

    real_wait = asyncio.wait

    async def paused_wait(*args: Any, **kwargs: Any) -> Any:
        wait_started.set()
        result = await real_wait(*args, **kwargs)
        wait_completed.set()
        await release_waiter.wait()
        return result

    monkeypatch.setattr(asyncio, "wait", paused_wait)
    provider = _make_provider(ContinuingAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)
    await _invoke_tool(
        tools["background_agents_start_task"], agent_name="Worker", input="first", description="first execution"
    )
    waiter = asyncio.create_task(_invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[1]))
    try:
        await wait_started.wait()
        first_release.set()
        await wait_completed.wait()
        first_result = {
            "completed": "first result",
            "failed": "Task failed: first failed",
            "cancelled": "Task failed: Task was canceled.",
        }[first_outcome]
        assert await _invoke_tool(tools["background_agents_get_task_results"], task_id=1) == first_result
        assert "continued" in await _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="second")
        await second_started.wait()
        continuation = provider._runtime[session.session_id].in_flight_tasks[1]
        if continuation_state != "running":
            second_release.set()
            await asyncio.gather(continuation, return_exceptions=True)
        if continuation_state == "finalized":
            assert await _invoke_tool(tools["background_agents_get_task_results"], task_id=1) == "second result"
        expected_state = session.to_dict()
        release_waiter.set()
        expected_status = "completed" if first_outcome == "completed" else "failed"
        assert await waiter == f"Task 1 finished with status: {expected_status}."
        assert session.to_dict() == expected_state
        if continuation_state != "finalized":
            assert provider._runtime[session.session_id].in_flight_tasks[1] is continuation
        second_release.set()
        await asyncio.gather(continuation, return_exceptions=True)
        expected_result = "Task failed: continuation failed" if continuation_state == "failed" else "second result"
        assert await _invoke_tool(tools["background_agents_get_task_results"], task_id=1) == expected_result
    finally:
        first_release.set()
        second_release.set()
        release_waiter.set()
        await asyncio.gather(waiter, return_exceptions=True)
        await provider.release_session(session)


async def test_concurrent_waiters_report_the_same_completed_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both waiters must report completion even when one has already finalized it."""
    agent_release = asyncio.Event()
    both_waiting = asyncio.Event()
    wait_count = 0
    real_wait = asyncio.wait

    class WaitingAgent(_FakeAgent):
        async def run(self, messages: Any = None, **kwargs: Any) -> AgentResponse[Any]:
            await agent_release.wait()
            return AgentResponse(messages=[Message(role="assistant", contents=["shared result"])])

    async def counted_wait(*args: Any, **kwargs: Any) -> Any:
        nonlocal wait_count
        wait_count += 1
        if wait_count == 2:
            both_waiting.set()
        return await real_wait(*args, **kwargs)

    monkeypatch.setattr(asyncio, "wait", counted_wait)
    provider = _make_provider(WaitingAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)
    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="start", description="shared")
    waiters = [
        asyncio.create_task(_invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[1]))
        for _ in range(2)
    ]
    try:
        await both_waiting.wait()
        agent_release.set()
        assert await asyncio.gather(*waiters) == ["Task 1 finished with status: completed."] * 2
        assert await _invoke_tool(tools["background_agents_get_task_results"], task_id=1) == "shared result"
        # Finished executions are retained until cleared or released.
        runtime = provider._runtime[session.session_id]
        assert runtime.in_flight_tasks[1].done()
        assert await _invoke_tool(tools["background_agents_clear_completed_task"], task_id=1) == "Task 1 cleared."
        assert not runtime.in_flight_tasks
    finally:
        agent_release.set()
        await asyncio.gather(*waiters, return_exceptions=True)
        await provider.release_session(session)


async def test_wait_for_first_completion() -> None:
    """Should wait and return when a task completes."""
    provider = _make_provider(_FakeAgent("Fast", response_text="fast result", delay=0.01))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Fast",
        input="go",
        description="fast task",
    )
    result = await _invoke_tool(
        tools["background_agents_wait_for_first_completion"],
        task_ids=[1],
    )
    assert "finished" in result.lower()
    assert "completed" in result.lower()


async def test_wait_empty_task_ids() -> None:
    """Should return error for empty task_ids."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(
        tools["background_agents_wait_for_first_completion"],
        task_ids=[],
    )
    assert "Error" in result


async def test_wait_no_running_tasks() -> None:
    """Should return error when no specified tasks are running."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(
        tools["background_agents_wait_for_first_completion"],
        task_ids=[999],
    )
    assert "Error" in result or "not running" in result.lower()


async def test_wait_timeout_returns_without_stopping_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should return normally on timeout and leave the child task running."""
    observed_timeout: float | None = None

    async def _return_timeout(
        tasks: Any,
        *,
        timeout: float | None = None,
        return_when: Any = asyncio.ALL_COMPLETED,
    ) -> tuple[set[Any], set[Any]]:
        nonlocal observed_timeout
        observed_timeout = timeout
        return set(), set(tasks)

    monkeypatch.setattr(asyncio, "wait", _return_timeout)
    provider = BackgroundAgentsProvider(
        [_FakeAgent("Slow", delay=10.0)],  # type: ignore[list-item]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        wait_timeout_seconds=7,
    )
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Slow",
        input="go",
        description="slow task",
    )

    try:
        result = await _invoke_tool(
            tools["background_agents_wait_for_first_completion"],
            task_ids=[1],
        )
        assert result == (
            "No background task completed within 7 seconds. "
            "The tasks are still running; call this tool again if you wish to continue waiting."
        )
        assert observed_timeout == 7

        runtime = provider._get_runtime(session)
        assert not runtime.in_flight_tasks[1].done()

        task_result = await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
        assert "still running" in task_result.lower()
    finally:
        await provider.release_session(session)


# --- Get Task Results Tests ---


async def test_get_task_results_completed() -> None:
    """Should return result text for completed task."""
    provider = _make_provider(_FakeAgent("Worker", response_text="the answer", delay=0.01))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="query",
        description="test",
    )
    # Wait for completion.
    await _invoke_tool(
        tools["background_agents_wait_for_first_completion"],
        task_ids=[1],
    )
    result = await _invoke_tool(
        tools["background_agents_get_task_results"],
        task_id=1,
    )
    assert result == "the answer"


async def test_get_task_results_running() -> None:
    """Should indicate task is still running."""
    provider = _make_provider(_FakeAgent("Slow", delay=10.0))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Slow",
        input="query",
        description="slow task",
    )
    try:
        result = await _invoke_tool(
            tools["background_agents_get_task_results"],
            task_id=1,
        )
        assert "still running" in result.lower()
    finally:
        runtime = provider._get_runtime(session)
        for task in list(runtime.in_flight_tasks.values()):
            task.cancel()
        await asyncio.gather(*runtime.in_flight_tasks.values(), return_exceptions=True)


async def test_get_task_results_failed() -> None:
    """Should return error text for failed task."""
    provider = _make_provider(_FakeAgent("Broken", should_fail=True, delay=0.01))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Broken",
        input="query",
        description="will fail",
    )
    await _invoke_tool(
        tools["background_agents_wait_for_first_completion"],
        task_ids=[1],
    )
    result = await _invoke_tool(
        tools["background_agents_get_task_results"],
        task_id=1,
    )
    assert "failed" in result.lower()


async def test_get_task_results_not_found() -> None:
    """Should return error for non-existent task."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(
        tools["background_agents_get_task_results"],
        task_id=999,
    )
    assert "Error" in result


# --- Continue Task Tests ---


async def test_continue_task_after_completion() -> None:
    """Should be able to continue a completed task."""
    provider = _make_provider(_FakeAgent("Worker", response_text="first result", delay=0.01))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="first input",
        description="continuable",
    )
    await _invoke_tool(
        tools["background_agents_wait_for_first_completion"],
        task_ids=[1],
    )
    result = await _invoke_tool(
        tools["background_agents_continue_task"],
        task_id=1,
        text="follow up",
    )
    assert "continued" in result.lower()


async def test_continue_task_still_running() -> None:
    """Should return error if task is still running."""
    provider = _make_provider(_FakeAgent("Slow", delay=10.0))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Slow",
        input="input",
        description="running",
    )
    try:
        result = await _invoke_tool(
            tools["background_agents_continue_task"],
            task_id=1,
            text="follow up",
        )
        assert "still running" in result.lower()
    finally:
        runtime = provider._get_runtime(session)
        for task in list(runtime.in_flight_tasks.values()):
            task.cancel()
        await asyncio.gather(*runtime.in_flight_tasks.values(), return_exceptions=True)


async def test_continue_task_not_found() -> None:
    """Should return error for non-existent task."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(
        tools["background_agents_continue_task"],
        task_id=999,
        text="hello",
    )
    assert "Error" in result


# --- Clear Task Tests ---


async def test_clear_completed_task() -> None:
    """Should clear a completed task."""
    provider = _make_provider(_FakeAgent("Worker", response_text="done", delay=0.01))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="task",
        description="clearable",
    )
    await _invoke_tool(
        tools["background_agents_wait_for_first_completion"],
        task_ids=[1],
    )
    result = await _invoke_tool(
        tools["background_agents_clear_completed_task"],
        task_id=1,
    )
    assert "cleared" in result.lower()

    # Verify task is gone.
    all_tasks = await _invoke_tool(tools["background_agents_get_all_tasks"])
    assert "No tasks" in all_tasks


async def test_clear_running_task_error() -> None:
    """Should return error when clearing a running task."""
    provider = _make_provider(_FakeAgent("Slow", delay=10.0))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Slow",
        input="task",
        description="still going",
    )
    try:
        result = await _invoke_tool(
            tools["background_agents_clear_completed_task"],
            task_id=1,
        )
        assert "still running" in result.lower()
    finally:
        runtime = provider._get_runtime(session)
        for task in list(runtime.in_flight_tasks.values()):
            task.cancel()
        await asyncio.gather(*runtime.in_flight_tasks.values(), return_exceptions=True)


async def test_clear_not_found() -> None:
    """Should return error for non-existent task."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(
        tools["background_agents_clear_completed_task"],
        task_id=999,
    )
    assert "Error" in result


# --- BackgroundTaskInfo Tests ---


def test_task_info_serialization() -> None:
    """BackgroundTaskInfo should round-trip through to_dict/from_dict."""
    info = BackgroundTaskInfo(
        id=1,
        agent_name="Worker",
        description="test task",
        status=BackgroundTaskStatus.COMPLETED,
        result_text="hello",
    )
    data = info.to_dict()
    restored = BackgroundTaskInfo.from_dict(data)
    assert restored.id == 1
    assert restored.agent_name == "Worker"
    assert restored.status == BackgroundTaskStatus.COMPLETED
    assert restored.result_text == "hello"
    assert restored.error_text is None


def test_task_status_enum_values() -> None:
    """BackgroundTaskStatus should have expected values."""
    assert BackgroundTaskStatus.RUNNING == "running"
    assert BackgroundTaskStatus.COMPLETED == "completed"
    assert BackgroundTaskStatus.FAILED == "failed"
    assert BackgroundTaskStatus.LOST == "lost"


async def test_release_session_cancels_and_clears() -> None:
    """Should cancel pending tasks and clear runtime state."""
    provider = _make_provider(_FakeAgent("Slow", delay=10.0))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Slow",
        input="task",
        description="long running",
    )

    runtime = provider._runtime.get(session.session_id)
    assert runtime is not None
    assert len(runtime.in_flight_tasks) == 1

    task = next(iter(runtime.in_flight_tasks.values()))

    await provider.release_session(session, cancel_running=True)

    assert task.done()
    assert task.cancelled()
    assert runtime.in_flight_tasks == {}
    assert runtime.background_sessions == {}

    assert session.session_id not in provider._runtime


async def test_release_session_raises_if_cancel_running_false() -> None:
    """Should raise RuntimeError if cancel_running=False and tasks are pending."""
    provider = _make_provider(_FakeAgent("Slow", delay=10.0))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Slow",
        input="task",
        description="long running",
    )

    with pytest.raises(RuntimeError, match="tasks still running"):
        await provider.release_session(session, cancel_running=False)

    assert session.session_id in provider._runtime
    await provider.release_session(session, cancel_running=True)


async def test_release_session_idempotent() -> None:
    """Should not raise when releasing an unknown or already released session."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()

    await provider.release_session(AgentSession(session_id="non_existent_session"))

    await provider.release_session(session)
    await provider.release_session(session)


async def test_release_session_isolation() -> None:
    """Releasing one session should not affect another."""
    provider = _make_provider(_FakeAgent("Worker", delay=10.0))
    session_a = AgentSession(session_id="session_a")
    session_b = AgentSession(session_id="session_b")

    tools_a = await _get_tools(provider, session_a)
    tools_b = await _get_tools(provider, session_b)

    await _invoke_tool(
        tools_a["background_agents_start_task"],
        agent_name="Worker",
        input="A",
        description="A",
    )
    await _invoke_tool(
        tools_b["background_agents_start_task"],
        agent_name="Worker",
        input="B",
        description="B",
    )

    await provider.release_session(session_a, cancel_running=True)

    assert "session_a" not in provider._runtime
    assert "session_b" in provider._runtime

    await provider.release_session(session_b, cancel_running=True)


async def test_get_runtime_replaces_closed_runtime() -> None:
    """A closed runtime should be replaced by a new runtime instance."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()

    old_runtime = provider._get_runtime(session)
    old_runtime.closed = True

    new_runtime = provider._get_runtime(session)

    assert new_runtime is not old_runtime
    assert provider._runtime.get(session.session_id) is new_runtime


async def test_track_task_rejects_when_runtime_closed() -> None:
    """Closed runtime should not accept new background tasks."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()

    runtime = provider._get_runtime(session)
    runtime.closed = True

    async def _dummy() -> Any:
        await asyncio.sleep(0)

    task = asyncio.create_task(_dummy())

    with pytest.raises(RuntimeError, match="closed"):
        runtime.track_task(1, task)

    with suppress(asyncio.CancelledError):
        await task

    assert task.cancelled()


async def test_start_task_returns_error_when_runtime_closed() -> None:
    """background_agents_start_task should refuse to run on a closed runtime."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()

    tools = await _get_tools(provider, session)

    runtime = provider._get_runtime(session)
    runtime.closed = True

    result = await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="task",
        description="should not start",
    )

    assert "being released" in result
    assert runtime.in_flight_tasks == {}


async def test_tools_return_error_when_runtime_closed() -> None:
    """Mutating/background tools should refuse to run on a closed runtime."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()

    tools = await _get_tools(provider, session)

    runtime = provider._get_runtime(session)
    runtime.closed = True

    wait_result = await _invoke_tool(
        tools["background_agents_wait_for_first_completion"],
        task_ids=[1],
    )
    assert "being released" in wait_result

    continue_result = await _invoke_tool(
        tools["background_agents_continue_task"],
        task_id=1,
        text="continue",
    )
    assert "being released" in continue_result

    clear_result = await _invoke_tool(
        tools["background_agents_clear_completed_task"],
        task_id=1,
    )
    assert "being released" in clear_result


async def test_release_session_times_out_if_task_ignores_cancellation() -> None:
    """release_session should return within bounded time even if task ignores cancel."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()

    runtime = provider._get_runtime(session)
    unblock = asyncio.Event()

    async def _ignore_cancel() -> Any:
        try:
            await unblock.wait()
        except asyncio.CancelledError:
            await unblock.wait()
            raise

    task = asyncio.create_task(_ignore_cancel())
    runtime.in_flight_tasks[1] = task

    start = asyncio.get_running_loop().time()

    await asyncio.wait_for(
        provider.release_session(
            session,
            cancel_running=True,
            timeout=0.05,
        ),
        timeout=1.0,
    )

    elapsed = asyncio.get_running_loop().time() - start

    assert elapsed < 1.0
    assert session.session_id not in provider._runtime

    unblock.set()
    with suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)


async def test_release_session_times_out_if_task_repeatedly_suppresses_cancellation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """release_session must honour its timeout even if a task suppresses every cancellation."""
    caplog.set_level(logging.DEBUG, logger=_background_agents.__name__)
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    runtime = provider._get_runtime(session)
    exit_gate = asyncio.Event()
    cancellations = 0

    async def _suppress_every_cancellation() -> Any:
        nonlocal cancellations
        while True:
            try:
                await exit_gate.wait()
            except asyncio.CancelledError:
                cancellations += 1
                continue
            raise RuntimeError("failed after release")

    task = asyncio.create_task(_suppress_every_cancellation())
    runtime.in_flight_tasks[1] = task
    await asyncio.sleep(0)  # let the task start waiting on its gate

    # Observe the release with asyncio.wait so an unbounded release fails the test instead of hanging it.
    release = asyncio.create_task(provider.release_session(session, cancel_running=True, timeout=0.05))
    try:
        done, _ = await asyncio.wait({release}, timeout=2.0)
        assert release in done, "release_session did not return within its timeout"
        await release
        assert cancellations >= 1
        assert not task.done()
        assert session.session_id not in provider._runtime
        assert not runtime.in_flight_tasks
    finally:
        exit_gate.set()
        await asyncio.wait({task, release}, timeout=2.0)

    # The abandoned task's eventual exception is retrieved instead of going unobserved.
    await asyncio.sleep(0)
    assert isinstance(task.exception(), RuntimeError)
    assert "Abandoned background task raised: failed after release" in caplog.text


async def test_release_session_timeout_retrieves_exceptions_of_finished_tasks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A timed-out release must still observe failures of tasks that finished, not only abandon the rest."""
    caplog.set_level(logging.DEBUG, logger=_background_agents.__name__)
    loop = asyncio.get_running_loop()
    unobserved: list[dict[str, Any]] = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: unobserved.append(context))

    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    runtime = provider._get_runtime(session)
    exit_gate = asyncio.Event()

    async def _fail_before_release() -> Any:
        raise RuntimeError("failed before release")

    async def _fail_when_cancelled() -> Any:
        try:
            await exit_gate.wait()
        except asyncio.CancelledError:
            raise RuntimeError("failed during cancellation") from None

    async def _suppress_every_cancellation() -> Any:
        while True:
            with suppress(asyncio.CancelledError):
                await exit_gate.wait()
                return

    runtime.in_flight_tasks[1] = asyncio.create_task(_fail_before_release())
    runtime.in_flight_tasks[2] = asyncio.create_task(_fail_when_cancelled())
    stubborn = asyncio.create_task(_suppress_every_cancellation())
    runtime.in_flight_tasks[3] = stubborn
    failed_task_refs = [weakref.ref(runtime.in_flight_tasks[1]), weakref.ref(runtime.in_flight_tasks[2])]
    await asyncio.sleep(0)  # task 1 fails; tasks 2 and 3 start waiting on the gate

    release = asyncio.create_task(provider.release_session(session, cancel_running=True, timeout=0.05))
    try:
        done, _ = await asyncio.wait({release}, timeout=2.0)
        assert release in done, "release_session did not return within its timeout"
        await release
        assert not stubborn.done()
        assert not runtime.in_flight_tasks
    finally:
        exit_gate.set()
        await asyncio.wait({stubborn, release}, timeout=2.0)
        # Unretrieved task exceptions are reported when the task is garbage collected.
        gc.collect()
        loop.set_exception_handler(previous_handler)

    assert not [context["message"] for context in unobserved if "never retrieved" in context.get("message", "")]
    assert all(ref() is None for ref in failed_task_refs)  # the failed tasks were really collected
    assert "Abandoned background task raised: failed before release" in caplog.text
    assert "Abandoned background task raised: failed during cancellation" in caplog.text


async def test_cancelled_release_session_still_retrieves_task_exceptions(caplog: pytest.LogCaptureFixture) -> None:
    """If the release itself is cancelled while waiting, tasks it stops tracking are still observed."""
    caplog.set_level(logging.DEBUG, logger=_background_agents.__name__)
    loop = asyncio.get_running_loop()
    unobserved: list[dict[str, Any]] = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: unobserved.append(context))

    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    runtime = provider._get_runtime(session)
    exit_gate = asyncio.Event()

    async def _fail_after_gate() -> Any:
        while True:
            try:
                await exit_gate.wait()
            except asyncio.CancelledError:
                continue
            raise RuntimeError("failed after release was cancelled")

    runtime.in_flight_tasks[1] = asyncio.create_task(_fail_after_gate())
    failed_task_ref = weakref.ref(runtime.in_flight_tasks[1])
    await asyncio.sleep(0)

    release = asyncio.create_task(provider.release_session(session, cancel_running=True, timeout=None))
    try:
        for _ in range(100):
            if runtime.closed:
                break
            await asyncio.sleep(0)
        await asyncio.sleep(0)  # let the release start waiting on the task
        release.cancel()
        with suppress(asyncio.CancelledError):
            await release
        assert release.cancelled()
        assert not runtime.in_flight_tasks
    finally:
        exit_gate.set()
        for _ in range(10):
            await asyncio.sleep(0)  # let the abandoned task fail and its callbacks run
        # On Python 3.10 a cancelled task keeps its CancelledError traceback, whose frames reference the tasks.
        del release
        gc.collect()
        loop.set_exception_handler(previous_handler)

    assert not [context["message"] for context in unobserved if "never retrieved" in context.get("message", "")]
    assert failed_task_ref() is None
    assert "Abandoned background task raised: failed after release was cancelled" in caplog.text


async def test_release_session_timeout_keeps_abandoned_tasks_alive() -> None:
    """An abandoned task must not be garbage collected while still pending."""
    loop = asyncio.get_running_loop()
    unobserved: list[dict[str, Any]] = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: unobserved.append(context))

    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    runtime = provider._get_runtime(session)
    keep_running = True

    async def _wait_on_unreferenced_future() -> Any:
        while True:
            try:
                await asyncio.get_running_loop().create_future()
            except asyncio.CancelledError:
                if not keep_running:
                    raise

    runtime.in_flight_tasks[1] = asyncio.create_task(_wait_on_unreferenced_future())
    task_ref = weakref.ref(runtime.in_flight_tasks[1])
    await asyncio.sleep(0)

    try:
        await asyncio.wait_for(provider.release_session(session, cancel_running=True, timeout=0.05), timeout=2.0)
        gc.collect()  # nothing outside the provider references the abandoned task any more
        abandoned = task_ref()
        assert abandoned is not None, "abandoned task was garbage collected while pending"
        assert not abandoned.done()
        assert abandoned in _background_agents._abandoned_background_tasks
    finally:
        keep_running = False
        abandoned = task_ref()
        if abandoned is not None:
            abandoned.cancel()
            with suppress(asyncio.CancelledError):
                await abandoned
        loop.set_exception_handler(previous_handler)

    assert task_ref() is None or task_ref() not in _background_agents._abandoned_background_tasks
    assert not [context["message"] for context in unobserved if "pending" in context.get("message", "")]


async def test_release_session_does_not_pop_replacement_runtime() -> None:
    """A release of an old runtime should not remove a replacement runtime."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()

    old_runtime = provider._get_runtime(session)
    unblock = asyncio.Event()

    async def _blocked_task() -> Any:
        try:
            await unblock.wait()
        except asyncio.CancelledError:
            await unblock.wait()
            raise

    task = asyncio.create_task(_blocked_task())
    old_runtime.in_flight_tasks[1] = task

    release_task = asyncio.create_task(
        provider.release_session(
            session,
            cancel_running=True,
            timeout=5.0,
        )
    )

    for _ in range(100):
        if old_runtime.closed:
            break
        await asyncio.sleep(0)

    assert old_runtime.closed

    new_runtime = provider._get_runtime(session)
    assert new_runtime is not old_runtime

    unblock.set()

    await asyncio.wait_for(release_task, timeout=1.0)

    assert provider._runtime.get(session.session_id) is new_runtime

    with suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)

    await provider.release_session(
        session,
        cancel_running=True,
        timeout=1.0,
    )


async def test_release_session_skips_drain_when_no_pending_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Should not invoke the drain path when there are no pending tasks."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    runtime = provider._get_runtime(session)

    async def completed_task() -> Any:
        return None

    task = asyncio.create_task(completed_task())
    await task

    runtime.in_flight_tasks[1] = task

    drain_called = False
    original_drain = provider._drain_runtime

    async def fake_drain(*args: Any, **kwargs: Any) -> None:
        nonlocal drain_called
        drain_called = True
        await original_drain(*args, **kwargs)

    monkeypatch.setattr(provider, "_drain_runtime", fake_drain)

    await provider.release_session(session)

    assert drain_called is False
    assert session.session_id not in provider._runtime


# ---------------------------------------------------------------------------
# Regression tests: finished tasks must survive until cleared or released
# (Part of #8760 - single-process snapshot/state desync fix)
# ---------------------------------------------------------------------------


async def test_snapshot_restore_returns_real_result_not_lost() -> None:
    """A session snapshot taken while a task is RUNNING must still return the
    real result after the task finishes and the snapshot is restored.

    Repro for the single-process gap: _finalize_task previously removed the
    finished asyncio.Task from in_flight_tasks.  If the host persists session
    state only after the run completes and a failure (or snapshot restoration)
    occurs before that, the next refresh would find no local task and mark it
    LOST, silently discarding the result.
    """
    provider = _make_provider(_FakeAgent("Worker", response_text="hello from worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    # Start a task and immediately snapshot the session state (task is RUNNING).
    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="do work",
        description="regression task",
    )
    snapshot = session.to_dict()  # captured while task is still RUNNING

    # Let the task complete deterministically (no sleep).
    runtime = provider._get_runtime(session)
    task = runtime.in_flight_tasks[1]
    await task  # wait for the asyncio.Task to finish

    # Finalize by refreshing (simulates what before_run / get_task_results does).
    tools2 = await _get_tools(provider, session)
    result_before_restore = await _invoke_tool(tools2["background_agents_get_task_results"], task_id=1)
    assert result_before_restore == "hello from worker"

    # Now restore the pre-finalization snapshot into the same provider.
    # This simulates the host restoring an older session state (e.g. after a
    # failed persist or a multi-turn rollback).
    session2 = AgentSession.from_dict(snapshot)
    tools3 = await _get_tools(provider, session2)

    # The task is still in in_flight_tasks (finished but not yet cleared).
    # get_task_results must return the real result, not "Task state was lost".
    result_after_restore = await _invoke_tool(tools3["background_agents_get_task_results"], task_id=1)
    assert result_after_restore == "hello from worker", f"Expected real result but got: {result_after_restore!r}"

    await provider.release_session(session)
    await provider.release_session(session2)


async def test_snapshot_restore_preserves_error_text_for_failed_task() -> None:
    """Same as above but for a task that raises; error_text must survive restore."""
    provider = _make_provider(_FakeAgent("Failer", should_fail=True))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Failer",
        input="trigger failure",
        description="failure regression",
    )
    snapshot = session.to_dict()

    runtime = provider._get_runtime(session)
    task = runtime.in_flight_tasks[1]
    with suppress(Exception):
        await task

    # Finalize via a refresh so task_info gets FAILED status.
    tools2 = await _get_tools(provider, session)
    await _invoke_tool(tools2["background_agents_get_task_results"], task_id=1)

    # Restore snapshot and confirm the failure is still readable.
    session2 = AgentSession.from_dict(snapshot)
    tools3 = await _get_tools(provider, session2)
    result = await _invoke_tool(tools3["background_agents_get_task_results"], task_id=1)
    assert "Agent execution failed" in result, f"Unexpected result: {result!r}"

    await provider.release_session(session)
    await provider.release_session(session2)


async def test_snapshot_restore_preserves_error_text_for_cancelled_task() -> None:
    """Cancelled task error_text must survive snapshot restoration."""
    provider = _make_provider(_FakeAgent("Slow", delay=60.0))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Slow",
        input="start slow task",
        description="cancellation regression",
    )
    snapshot = session.to_dict()

    runtime = provider._get_runtime(session)
    task = runtime.in_flight_tasks[1]
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    # Finalize via a refresh.
    tools2 = await _get_tools(provider, session)
    await _invoke_tool(tools2["background_agents_get_task_results"], task_id=1)

    # Restore snapshot and confirm cancellation error survives.
    session2 = AgentSession.from_dict(snapshot)
    tools3 = await _get_tools(provider, session2)
    result = await _invoke_tool(tools3["background_agents_get_task_results"], task_id=1)
    assert "canceled" in result.lower(), f"Unexpected result: {result!r}"

    await provider.release_session(session)
    await provider.release_session(session2)


async def test_clear_completed_task_removes_entry_from_in_flight_tasks() -> None:
    """clear_completed_task must remove the finished task from in_flight_tasks."""
    provider = _make_provider(_FakeAgent("Worker", response_text="done"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="work",
        description="clear test",
    )

    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]

    # Finalize and then clear.
    tools2 = await _get_tools(provider, session)
    await _invoke_tool(tools2["background_agents_get_task_results"], task_id=1)
    clear_result = await _invoke_tool(tools2["background_agents_clear_completed_task"], task_id=1)

    assert clear_result == "Task 1 cleared."
    assert 1 not in runtime.in_flight_tasks, "Task should be removed by clear_completed_task"

    await provider.release_session(session)


async def test_release_session_clears_in_flight_tasks() -> None:
    """release_session must clear all in_flight_tasks including finished ones."""
    provider = _make_provider(_FakeAgent("Worker", response_text="done"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="work",
        description="release test",
    )

    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]

    # Finalize (task is now finished but still in in_flight_tasks).
    tools2 = await _get_tools(provider, session)
    await _invoke_tool(tools2["background_agents_get_task_results"], task_id=1)

    assert 1 in runtime.in_flight_tasks, "Finished task should still be present before release"

    await provider.release_session(session)

    assert session.session_id not in provider._runtime
    assert not runtime.in_flight_tasks


async def test_wait_blocks_for_running_task_and_ignores_finished() -> None:
    """wait_for_first_completion ignores finished retained tasks and waits for running ones."""
    provider = _make_provider(
        _FakeAgent("Fast", response_text="fast done"),
        _FakeAgent("Slow", response_text="slow done", delay=0.02),
    )
    session = _make_session()
    tools = await _get_tools(provider, session)

    # 1. Start and finish task 1.
    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Fast",
        input="work",
        description="task 1",
    )
    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]

    # Finalize task 1 so its status is COMPLETED and its task is retained.
    tools2 = await _get_tools(provider, session)
    await _invoke_tool(tools2["background_agents_get_task_results"], task_id=1)

    # 2. Start task 2 which takes longer.
    await _invoke_tool(
        tools2["background_agents_start_task"],
        agent_name="Slow",
        input="slow work",
        description="task 2",
    )

    # 3. wait([1, 2]) must block for running task 2 and NOT return finished task 1.
    wait_result = await _invoke_tool(
        tools2["background_agents_wait_for_first_completion"],
        task_ids=[1, 2],
    )
    assert "Task 2 finished with status: completed." in wait_result
    assert "Task 1" not in wait_result

    # 4. wait([1]) on finished task returns "not running; current status" text.
    finished_wait_result = await _invoke_tool(
        tools2["background_agents_wait_for_first_completion"],
        task_ids=[1],
    )
    assert "Task 1 is not running; current status: completed." in finished_wait_result

    await provider.release_session(session)


async def test_clear_completed_task_does_not_clear_in_flight_continuation() -> None:
    """Restoring an older completed snapshot and clearing task 1 must not clear a running continuation."""

    class _ContinuationAgent(_FakeAgent):
        def __init__(self, name: str = "Worker") -> None:
            super().__init__(name, response_text="done")
            self.release = asyncio.Event()
            self._runs = 0

        async def run(
            self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any
        ) -> AgentResponse[Any]:
            self._runs += 1
            if self._runs > 1:
                await self.release.wait()
            return await super().run(messages, stream=stream, session=session, **kwargs)

    agent = _ContinuationAgent("Worker")
    provider = _make_provider(agent)
    session = _make_session()
    tools = await _get_tools(provider, session)

    # 1. Start task 1 and let it complete.
    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="first run",
        description="task 1",
    )
    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]

    # Finalize task 1 so its status is COMPLETED.
    tools2 = await _get_tools(provider, session)
    await _invoke_tool(tools2["background_agents_get_task_results"], task_id=1)

    # 2. Snapshot the completed state.
    snapshot = session.to_dict()

    # 3. continue_task with slow agent.
    continue_msg = await _invoke_tool(tools2["background_agents_continue_task"], task_id=1, text="second run")
    assert "continued" in continue_msg.lower()

    continuation_task = runtime.in_flight_tasks[1]
    assert not continuation_task.done()

    # 4. Restore snapshot into a new AgentSession.
    session2 = AgentSession.from_dict(snapshot)
    tools3 = await _get_tools(provider, session2)

    # 5. Call clear_completed_task(1) on restored session.
    clear_msg = await _invoke_tool(tools3["background_agents_clear_completed_task"], task_id=1)
    assert clear_msg == "Task 1 cleared."

    # 6. Continuation is still in in_flight_tasks.
    assert 1 in runtime.in_flight_tasks
    assert runtime.in_flight_tasks[1] is continuation_task
    assert not continuation_task.done()

    # 7. release_session(cancel_running=True) cancels it.
    await provider.release_session(session, cancel_running=True)
    assert continuation_task.cancelled()
    assert not runtime.in_flight_tasks


# ---------------------------------------------------------------------------
# Regression tests: execution identity for reused task IDs
# ---------------------------------------------------------------------------


class _ScriptedAgent(_FakeAgent):
    """Agent whose N-th run returns ``responses[N]`` and optionally waits on a gate or fails."""

    def __init__(self, name: str, responses: list[str], *, fail_runs: set[int] | None = None) -> None:
        super().__init__(name)
        self.responses = responses
        self.fail_runs = fail_runs or set()
        self.gates: dict[int, asyncio.Event] = {}
        self.runs = 0

    async def run(
        self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any
    ) -> AgentResponse[Any]:
        index = self.runs
        self.runs += 1
        gate = self.gates.get(index)
        if gate is not None:
            await gate.wait()
        if index in self.fail_runs:
            raise RuntimeError(f"run {index} failed")
        return AgentResponse(messages=[Message(role="assistant", contents=[self.responses[index]])])


def _task_record(session: AgentSession, task_id: int) -> dict[str, Any]:
    return next(t for t in session.state["background_agents"]["tasks"] if t["id"] == task_id)


def test_task_info_execution_id_round_trip_and_legacy_state() -> None:
    """execution_id is persisted, and state written before it existed loads without one."""
    info = BackgroundTaskInfo(id=1, agent_name="A", description="d", execution_id="abc")
    assert BackgroundTaskInfo.from_dict(info.to_dict()).execution_id == "abc"

    legacy = {"id": 1, "agent_name": "A", "description": "d", "status": "running"}
    assert BackgroundTaskInfo.from_dict(legacy).execution_id is None


async def test_every_execution_gets_a_distinct_execution_id() -> None:
    """Starts and continuations each record a new execution ID on the task."""
    agent = _ScriptedAgent("Worker", ["first result", "second result"])
    provider = _make_provider(agent)
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="t")
    runtime = provider._get_runtime(session)
    first_execution_id = _task_record(session, 1)["execution_id"]
    assert runtime.execution_ids[1] == first_execution_id
    await runtime.in_flight_tasks[1]
    await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)

    await _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="again")
    second_execution_id = _task_record(session, 1)["execution_id"]
    assert second_execution_id != first_execution_id
    assert runtime.execution_ids[1] == second_execution_id

    await provider.release_session(session)


@pytest.mark.parametrize("continuation_fails", [False, True])
async def test_restored_running_snapshot_does_not_receive_continuation_outcome(continuation_fails: bool) -> None:
    """A stale RUNNING snapshot must not be finalized with a later continuation's result or error."""
    agent = _ScriptedAgent("Worker", ["first result", "second result"], fail_runs={1} if continuation_fails else None)
    provider = _make_provider(agent)
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="t")
    stale_snapshot = session.to_dict()  # first execution, RUNNING
    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]

    # The live session retrieves the first execution and continues the task.
    assert await _invoke_tool(tools["background_agents_get_task_results"], task_id=1) == "first result"
    await _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="again")
    continuation = runtime.in_flight_tasks[1]
    with suppress(Exception):
        await continuation

    # The host restores the snapshot taken while the first execution was running.
    restored = AgentSession.from_dict(stale_snapshot)
    restored_tools = await _get_tools(provider, restored)
    stale_result = await _invoke_tool(restored_tools["background_agents_get_task_results"], task_id=1)
    assert stale_result == "Task state was lost (reference unavailable)."

    # The live session still sees its own continuation outcome, and it is still tracked.
    live_result = await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
    assert live_result == ("Task failed: run 1 failed" if continuation_fails else "second result")
    assert runtime.in_flight_tasks[1] is continuation

    await provider.release_session(session)


async def test_restored_running_snapshot_does_not_wait_on_continuation() -> None:
    """Waiting from a stale snapshot must not block on (or finalize) a newer running continuation."""
    agent = _ScriptedAgent("Worker", ["first result", "second result"])
    agent.gates[1] = asyncio.Event()
    provider = _make_provider(agent)
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="t")
    stale_snapshot = session.to_dict()
    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]
    await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
    await _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="again")
    continuation = runtime.in_flight_tasks[1]

    restored = AgentSession.from_dict(stale_snapshot)
    restored_tools = await _get_tools(provider, restored)
    wait_result = await _invoke_tool(restored_tools["background_agents_wait_for_first_completion"], task_ids=[1])
    assert wait_result == "Task 1 is not running; current status: lost."
    assert runtime.in_flight_tasks[1] is continuation
    assert not continuation.done()

    agent.gates[1].set()
    wait_result = await _invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[1])
    assert wait_result == "Task 1 finished with status: completed."
    assert await _invoke_tool(tools["background_agents_get_task_results"], task_id=1) == "second result"

    await provider.release_session(session)


@pytest.mark.parametrize("other_execution_state", ["running", "completed"])
async def test_continue_from_stale_snapshot_is_rejected(other_execution_state: str) -> None:
    """A task continued from one copy of the session cannot be continued again from an older copy."""
    agent = _ScriptedAgent("Worker", ["first result", "second result", "third result"])
    agent.gates[1] = asyncio.Event()
    provider = _make_provider(agent)
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="t")
    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]
    await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
    completed_snapshot = session.to_dict()  # first execution, COMPLETED
    await _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="again")
    continuation = runtime.in_flight_tasks[1]
    continuation_execution_id = runtime.execution_ids[1]
    if other_execution_state == "completed":
        agent.gates[1].set()
        await continuation

    restored = AgentSession.from_dict(completed_snapshot)
    restored_tools = await _get_tools(provider, restored)
    result = await _invoke_tool(restored_tools["background_agents_continue_task"], task_id=1, text="stale")
    assert result.startswith("Error: Task 1 was continued from another copy of this session")
    assert runtime.in_flight_tasks[1] is continuation
    assert runtime.execution_ids[1] == continuation_execution_id

    # The other copy's continuation, including an unread result, is untouched.
    agent.gates[1].set()
    await continuation
    assert await _invoke_tool(tools["background_agents_get_task_results"], task_id=1) == "second result"

    await provider.release_session(session)


async def test_clear_from_stale_snapshot_keeps_other_execution() -> None:
    """Clearing an older copy's record keeps a finished execution that another copy still owns."""
    agent = _ScriptedAgent("Worker", ["first result", "second result"])
    provider = _make_provider(agent)
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="t")
    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]
    await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
    completed_snapshot = session.to_dict()
    await _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="again")
    continuation = runtime.in_flight_tasks[1]
    await continuation

    restored = AgentSession.from_dict(completed_snapshot)
    restored_tools = await _get_tools(provider, restored)
    assert await _invoke_tool(restored_tools["background_agents_clear_completed_task"], task_id=1) == "Task 1 cleared."
    assert runtime.in_flight_tasks[1] is continuation
    assert 1 in runtime.background_sessions

    # The owning copy can still read and then clear it, which releases the runtime references.
    assert await _invoke_tool(tools["background_agents_get_task_results"], task_id=1) == "second result"
    assert await _invoke_tool(tools["background_agents_clear_completed_task"], task_id=1) == "Task 1 cleared."
    assert 1 not in runtime.in_flight_tasks
    assert 1 not in runtime.execution_ids
    assert 1 not in runtime.background_sessions

    await provider.release_session(session)


async def test_start_after_rollback_does_not_reuse_tracked_task_id() -> None:
    """Restoring a snapshot from before a task started must not let a new task take over its ID."""
    agent = _ScriptedAgent("Worker", ["original result", "replacement result"])
    agent.gates[0] = asyncio.Event()
    provider = _make_provider(agent)
    session = _make_session()
    tools = await _get_tools(provider, session)
    before_start = session.to_dict()  # next_task_id == 1

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="original")
    after_start = session.to_dict()  # original task RUNNING
    runtime = provider._get_runtime(session)
    original = runtime.in_flight_tasks[1]

    # Roll back to before the original task started and start a different task.
    rolled_back = AgentSession.from_dict(before_start)
    rolled_back_tools = await _get_tools(provider, rolled_back)
    result = await _invoke_tool(
        rolled_back_tools["background_agents_start_task"], agent_name="Worker", input="go", description="replacement"
    )
    assert result == "Background task 2 started on agent 'Worker'."
    assert runtime.in_flight_tasks[1] is original
    await runtime.in_flight_tasks[2]

    # Restoring the original task's RUNNING snapshot must not accept the replacement's result.
    restored = AgentSession.from_dict(after_start)
    restored_tools = await _get_tools(provider, restored)
    assert (
        await _invoke_tool(restored_tools["background_agents_get_task_results"], task_id=1)
        == "Task 1 is still running."
    )
    agent.gates[0].set()
    await original
    assert await _invoke_tool(restored_tools["background_agents_get_task_results"], task_id=1) == "original result"

    await provider.release_session(session)


async def test_start_after_rollback_and_clear_does_not_reuse_task_id() -> None:
    """A task ID stays reserved for the runtime's lifetime, even after its task was cleared."""
    provider = _make_provider(_ScriptedAgent("Worker", ["first result", "second result"]))
    session = _make_session()
    tools = await _get_tools(provider, session)
    before_start = session.to_dict()

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="t1")
    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]
    await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
    assert await _invoke_tool(tools["background_agents_clear_completed_task"], task_id=1) == "Task 1 cleared."

    rolled_back = AgentSession.from_dict(before_start)
    rolled_back_tools = await _get_tools(provider, rolled_back)
    result = await _invoke_tool(
        rolled_back_tools["background_agents_start_task"], agent_name="Worker", input="go", description="t2"
    )
    assert result == "Background task 2 started on agent 'Worker'."

    await provider.release_session(session)


async def test_snapshot_from_released_runtime_never_matches_a_new_execution() -> None:
    """Execution IDs are globally unique, so a new runtime's execution never matches an old record."""
    agent = _ScriptedAgent("Worker", ["original result", "replacement result"])
    agent.gates[0] = asyncio.Event()
    provider = _make_provider(agent)
    session = _make_session()
    tools = await _get_tools(provider, session)
    before_start = session.to_dict()

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="original")
    after_start = session.to_dict()
    await asyncio.sleep(0)  # let the original execution start (it then blocks on its gate)
    assert agent.runs == 1
    await provider.release_session(session, cancel_running=True)

    # A fresh runtime hands out task ID 1 again for a different task.
    rolled_back = AgentSession.from_dict(before_start)
    rolled_back_tools = await _get_tools(provider, rolled_back)
    result = await _invoke_tool(
        rolled_back_tools["background_agents_start_task"], agent_name="Worker", input="go", description="replacement"
    )
    assert result == "Background task 1 started on agent 'Worker'."
    await provider._get_runtime(rolled_back).in_flight_tasks[1]

    restored = AgentSession.from_dict(after_start)
    restored_tools = await _get_tools(provider, restored)
    stale_result = await _invoke_tool(restored_tools["background_agents_get_task_results"], task_id=1)
    assert stale_result == "Task state was lost (reference unavailable)."

    await provider.release_session(rolled_back)


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("background_agents_start_task", {"agent_name": "Worker", "input": "go", "description": "t2"}),
        ("background_agents_wait_for_first_completion", {"task_ids": [1]}),
        ("background_agents_get_task_results", {"task_id": 1}),
        ("background_agents_get_all_tasks", {}),
        ("background_agents_continue_task", {"task_id": 1, "text": "again"}),
        ("background_agents_clear_completed_task", {"task_id": 1}),
    ],
)
async def test_background_tools_run_on_the_event_loop_thread(
    monkeypatch: pytest.MonkeyPatch, tool_name: str, arguments: dict[str, Any]
) -> None:
    """Every tool touches runtime state on the event loop, never from a worker thread.

    Continuation registration runs on the event loop; running the other tools there too makes each
    tool's check-and-update atomic with respect to it.
    """
    provider = _make_provider(_ScriptedAgent("Worker", ["first result", "second result", "third result"]))
    session = _make_session()
    tools = await _get_tools(provider, session)
    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="t1")
    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]
    if tool_name != "background_agents_wait_for_first_completion":
        await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)

    loop_thread = threading.get_ident()
    seen_threads: set[int] = set()
    real_get_tasks = _background_agents._get_tasks

    def recording_get_tasks(state: dict[str, Any]) -> list[BackgroundTaskInfo]:
        seen_threads.add(threading.get_ident())
        return real_get_tasks(state)

    monkeypatch.setattr(_background_agents, "_get_tasks", recording_get_tasks)
    await _invoke_tool(tools[tool_name], **arguments)

    assert seen_threads == {loop_thread}
    await provider.release_session(session)


@pytest.mark.parametrize("continue_first", [True, False])
async def test_concurrent_stale_clear_and_continuation_keep_continuation_tracked(continue_first: bool) -> None:
    """A stale clear racing a continuation must never strand the continuation untracked."""
    agent = _ScriptedAgent("Worker", ["first result", "second result"])
    agent.gates[1] = asyncio.Event()
    provider = _make_provider(agent)
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="t")
    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]
    await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
    restored = AgentSession.from_dict(session.to_dict())  # another copy of the same COMPLETED execution
    restored_tools = await _get_tools(provider, restored)

    continue_call = _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="again")
    clear_call = _invoke_tool(restored_tools["background_agents_clear_completed_task"], task_id=1)
    calls = [continue_call, clear_call] if continue_first else [clear_call, continue_call]
    results = await asyncio.gather(*calls)
    continue_result = results[0] if continue_first else results[1]

    if continue_result == "Task 1 continued with new input.":
        # The continuation must still be tracked so release can cancel it.
        continuation = runtime.in_flight_tasks[1]
        assert not continuation.done()
        await provider.release_session(session, cancel_running=True)
        assert continuation.cancelled()
    else:
        # The clear won; the continuation was refused instead of starting untracked.
        assert continue_result == "Error: Session for task 1 is no longer available."
        assert 1 not in runtime.in_flight_tasks
        assert agent.runs == 1
        await provider.release_session(session)


@pytest.mark.parametrize("read_first", [True, False])
async def test_concurrent_stale_result_read_and_continuation_never_crosses_executions(read_first: bool) -> None:
    """A stale reader racing a continuation must never accept the continuation's result as its own."""
    agent = _ScriptedAgent("Worker", ["first result", "second result"])
    provider = _make_provider(agent)
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="go", description="t")
    stale_snapshot = session.to_dict()  # first execution, RUNNING
    runtime = provider._get_runtime(session)
    await runtime.in_flight_tasks[1]
    await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
    restored = AgentSession.from_dict(stale_snapshot)
    restored_tools = await _get_tools(provider, restored)

    read_call = _invoke_tool(restored_tools["background_agents_get_task_results"], task_id=1)
    continue_call = _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="again")
    calls = [read_call, continue_call] if read_first else [continue_call, read_call]
    results = await asyncio.gather(*calls)
    stale_result = results[0] if read_first else results[1]
    assert stale_result in {"first result", "Task state was lost (reference unavailable)."}

    # Let the continuation finish; the stale record still never reports it.
    await runtime.in_flight_tasks[1]
    assert await _invoke_tool(restored_tools["background_agents_get_task_results"], task_id=1) == stale_result
    assert await _invoke_tool(tools["background_agents_get_task_results"], task_id=1) == "second result"

    await provider.release_session(session)
