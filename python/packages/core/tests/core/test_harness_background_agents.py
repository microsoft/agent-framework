# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
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


async def test_reused_task_id_does_not_associate_stale_snapshot_with_continuation() -> None:
    """A stale snapshot must reconcile with its own execution, not a later continuation.

    Regression test for reused task IDs:
    If task 1 is snapshotted while RUNNING, finishes, is continued (starting a
    new execution under task ID 1), and the second execution finishes, restoring
    the original snapshot must reconcile with the first execution's result, NOT
    the continuation's result.
    """

    class _ContinuationAgent:
        def __init__(self, name: str = "Worker") -> None:
            self.name = name
            self.description = "Worker that tracks runs"
            self.call_count = 0

        def create_session(self, *, session_id: str | None = None) -> AgentSession:
            return AgentSession(session_id=session_id)

        def get_session(self, service_session_id: Any, *, session_id: str | None = None) -> AgentSession:
            return AgentSession(service_session_id=service_session_id, session_id=session_id)

        async def run(self, messages: Any = None, **kwargs: Any) -> AgentResponse[Any]:
            del messages, kwargs
            self.call_count += 1
            return AgentResponse(
                messages=[Message(role="assistant", contents=[f"result generation {self.call_count}"])]
            )

    agent = _ContinuationAgent("Worker")
    provider = _make_provider(agent)  # type: ignore[arg-type]
    session = _make_session()
    tools = await _get_tools(provider, session)

    # 1. Start task 1 on Worker (generation 1).
    await _invoke_tool(
        tools["background_agents_start_task"],
        agent_name="Worker",
        input="first run",
        description="task 1",
    )
    # Immediately capture snapshot while task 1 is RUNNING (generation 1).
    snapshot_gen1 = session.to_dict()

    runtime = provider._get_runtime(session)
    task_1 = runtime.in_flight_tasks[(1, 1)]
    await task_1

    # 2. Finalize first run via refresh.
    tools2 = await _get_tools(provider, session)
    res1 = await _invoke_tool(tools2["background_agents_get_task_results"], task_id=1)
    assert res1 == "result generation 1"

    # 3. Continue task 1 with new input (generation 2).
    continue_msg = await _invoke_tool(tools2["background_agents_continue_task"], task_id=1, text="second run")
    assert "continued" in continue_msg.lower()

    task_2 = runtime.in_flight_tasks[(1, 2)]
    await task_2

    # Finalize continuation via refresh.
    tools3 = await _get_tools(provider, session)
    res2 = await _invoke_tool(tools3["background_agents_get_task_results"], task_id=1)
    assert res2 == "result generation 2"

    # 4. Now restore the generation 1 snapshot into the same provider.
    session_restored = AgentSession.from_dict(snapshot_gen1)
    tools_restored = await _get_tools(provider, session_restored)

    # Refreshing on the restored snapshot must reconcile with generation 1 task,
    # NOT with generation 2 task.
    res_restored = await _invoke_tool(tools_restored["background_agents_get_task_results"], task_id=1)
    assert res_restored == "result generation 1", (
        f"Expected generation 1 result but got continuation result: {res_restored!r}"
    )

    await provider.release_session(session)
    await provider.release_session(session_restored)
