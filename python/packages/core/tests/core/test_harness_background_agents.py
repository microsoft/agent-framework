# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any, Sequence

import pytest

from agent_framework import (
    AgentResponse,
    AgentSession,
    BackgroundAgentsProvider,
    BackgroundTaskInfo,
    BackgroundTaskStatus,
    Content,
    Message,
    ServiceSessionId,
)
from agent_framework._harness._background_agents import BackgroundTaskRuntimeStore, _run_agent_with_renewal
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
        self.name: str | None = name
        self.description = description
        self._response_text = response_text
        self._delay = delay
        self._should_fail = should_fail

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(self, service_session_id: str | ServiceSessionId, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(service_session_id=service_session_id, session_id=session_id)

    async def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: Any = None,
        **kwargs: Any,
    ) -> AgentResponse[Any]:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        if self._should_fail:
            raise RuntimeError("Agent execution failed")
        return AgentResponse(messages=[Message(role="assistant", contents=[self._response_text])])


def _make_provider(*agents: _FakeAgent, **kwargs: Any) -> BackgroundAgentsProvider:
    """Create a provider with given agents."""
    return BackgroundAgentsProvider(agents, **kwargs)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]


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
        BackgroundAgentsProvider([agent])  # type: ignore  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]


def test_constructor_rejects_duplicate_names() -> None:
    """Should reject duplicate agent names (case-insensitive)."""
    agent1 = _FakeAgent("Research")
    agent2 = _FakeAgent("research")
    with pytest.raises(ValueError, match="Duplicate background agent name"):
        BackgroundAgentsProvider([agent1, agent2])  # type: ignore  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]


def test_constructor_valid_agents() -> None:
    """Should succeed with valid unique agents."""
    provider = _make_provider(_FakeAgent("Alpha"), _FakeAgent("Beta"))  # type: ignore  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
    assert provider.source_id == "background_agents"


def test_constructor_custom_source_id() -> None:
    """Should accept custom source_id."""
    provider = _make_provider(_FakeAgent("Agent1"), source_id="custom_bg")  # type: ignore  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
    assert provider.source_id == "custom_bg"


def test_constructor_uses_default_wait_timeout() -> None:
    """Should use a bounded five-minute wait by default."""
    provider = _make_provider(_FakeAgent("Worker"))
    assert provider._wait_timeout_seconds == 300


@pytest.mark.parametrize("wait_timeout_seconds", [0, -1, True, 1.5, float("inf"), float("nan")])
def test_constructor_rejects_invalid_wait_timeout(wait_timeout_seconds: object) -> None:
    """Should reject wait timeouts that are not positive integers."""
    with pytest.raises(ValueError, match="positive integer"):
        _make_provider(
            _FakeAgent("Worker"),  # type: ignore  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
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
        tools["background_agents_start_task"], agent_name="Worker", input="do something", description="test task"
    )
    assert "task 1 started" in result.lower()
    assert "Worker" in result


async def test_start_task_unknown_agent() -> None:
    """Should return error for unknown agent name."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(
        tools["background_agents_start_task"], agent_name="NonExistent", input="do something", description="test"
    )
    assert "Error" in result
    assert "NonExistent" in result


async def test_start_task_increments_ids() -> None:
    """Task IDs should increment sequentially."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    r1 = await _invoke_tool(
        tools["background_agents_start_task"], agent_name="Worker", input="task 1", description="first"
    )
    r2 = await _invoke_tool(
        tools["background_agents_start_task"], agent_name="Worker", input="task 2", description="second"
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

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="hello", description="my task")
    result = await _invoke_tool(tools["background_agents_get_all_tasks"])
    assert "my task" in result
    assert "Worker" in result


# --- Wait for Completion Tests ---


async def test_wait_for_first_completion() -> None:
    """Should wait and return when a task completes."""
    provider = _make_provider(_FakeAgent("Fast", response_text="fast result", delay=0.01))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Fast", input="go", description="fast task")
    result = await _invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[1])
    assert "finished" in result.lower()
    assert "completed" in result.lower()


async def test_wait_empty_task_ids() -> None:
    """Should return error for empty task_ids."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[])
    assert "Error" in result


async def test_wait_no_running_tasks() -> None:
    """Should return error when no specified tasks are running."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[999])
    assert "Error" in result or "not running" in result.lower()


async def test_wait_timeout_returns_without_stopping_task() -> None:
    """Should return normally on timeout and leave the child task running."""
    provider = _make_provider(
        _FakeAgent("Slow", delay=10.0),  # type: ignore  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]
        wait_timeout_seconds=1,
    )
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Slow", input="go", description="slow task")

    try:
        result = await _invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[1])
        assert result == (
            "No background task completed within 1 seconds. "
            "The tasks are still running; call this tool again if you wish to continue waiting."
        )

        runtime = provider._get_runtime(session)
        assert not runtime.in_flight_tasks[1].done()

        task_result = await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
        assert "still running" in task_result.lower()
    finally:
        await provider.release_session(session, cancel_running=True)

    # task cancellation verified inside release_session test

    assert runtime.in_flight_tasks == {}
    assert runtime.background_sessions == {}

    assert session.session_id not in provider._runtime


# --- Get Task Results Tests ---


async def test_get_task_results_completed() -> None:
    """Should return the result text for a completed task."""
    provider = _make_provider(_FakeAgent("Worker", response_text="the answer", delay=0.01))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Worker", input="query", description="test")
    # Wait for completion.
    await _invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[1])
    result = await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
    assert result == "the answer"


async def test_get_task_results_running() -> None:
    """Should indicate task is still running."""
    provider = _make_provider(_FakeAgent("Slow", delay=10.0))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Slow", input="query", description="slow task")
    try:
        result = await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
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
        tools["background_agents_start_task"], agent_name="Broken", input="query", description="will fail"
    )
    await _invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[1])
    result = await _invoke_tool(tools["background_agents_get_task_results"], task_id=1)
    assert "failed" in result.lower()


async def test_get_task_results_not_found() -> None:
    """Should return error for non-existent task."""
    provider = _make_provider(_FakeAgent("Worker"))
    session = _make_session()
    tools = await _get_tools(provider, session)

    result = await _invoke_tool(tools["background_agents_get_task_results"], task_id=999)
    assert "Error" in result


# --- Continue Task Tests ---


async def test_continue_task_after_completion() -> None:
    """Should be able to continue a completed task."""
    provider = _make_provider(_FakeAgent("Worker", response_text="first result", delay=0.01))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"], agent_name="Worker", input="first input", description="continuable"
    )
    await _invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[1])
    result = await _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="follow up")
    assert "continued" in result.lower()


async def test_continue_task_still_running() -> None:
    """Should return error if task is still running."""
    provider = _make_provider(_FakeAgent("Slow", delay=10.0))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(tools["background_agents_start_task"], agent_name="Slow", input="input", description="running")
    try:
        result = await _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="follow up")
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

    result = await _invoke_tool(tools["background_agents_continue_task"], task_id=999, text="hello")
    assert "Error" in result


# --- Clear Task Tests ---


async def test_clear_completed_task() -> None:
    """Should clear a completed task."""
    provider = _make_provider(_FakeAgent("Worker", response_text="done", delay=0.01))
    session = _make_session()
    tools = await _get_tools(provider, session)

    await _invoke_tool(
        tools["background_agents_start_task"], agent_name="Worker", input="task", description="clearable"
    )
    await _invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[1])
    result = await _invoke_tool(tools["background_agents_clear_completed_task"], task_id=1)
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
        tools["background_agents_start_task"], agent_name="Slow", input="task", description="still going"
    )
    try:
        result = await _invoke_tool(tools["background_agents_clear_completed_task"], task_id=1)
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

    result = await _invoke_tool(tools["background_agents_clear_completed_task"], task_id=999)
    assert "Error" in result


# --- BackgroundTaskInfo Tests ---


def test_task_info_serialization() -> None:
    """BackgroundTaskInfo should round-trip through to_dict/from_dict."""
    info = BackgroundTaskInfo(
        id=1, agent_name="Worker", description="test task", status=BackgroundTaskStatus.COMPLETED, result_text="hello"
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
        tools["background_agents_start_task"], agent_name="Slow", input="task", description="long running"
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
        tools["background_agents_start_task"], agent_name="Slow", input="task", description="long running"
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

    await _invoke_tool(tools_a["background_agents_start_task"], agent_name="Worker", input="A", description="A")
    await _invoke_tool(tools_b["background_agents_start_task"], agent_name="Worker", input="B", description="B")

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
        tools["background_agents_start_task"], agent_name="Worker", input="task", description="should not start"
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

    wait_result = await _invoke_tool(tools["background_agents_wait_for_first_completion"], task_ids=[1])
    assert "being released" in wait_result

    continue_result = await _invoke_tool(tools["background_agents_continue_task"], task_id=1, text="continue")
    assert "being released" in continue_result

    clear_result = await _invoke_tool(tools["background_agents_clear_completed_task"], task_id=1)
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

    await asyncio.wait_for(provider.release_session(session, cancel_running=True, timeout=0.05), timeout=1.0)

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

    release_task = asyncio.create_task(provider.release_session(session, cancel_running=True, timeout=5.0))

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

    await provider.release_session(session, cancel_running=True, timeout=1.0)


async def test_release_session_skips_drain_when_no_pending_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
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


# --- Cross-Process / RuntimeStore Tests (Issue #8760) ---


class _TestRuntimeStore(BackgroundTaskRuntimeStore):
    """A minimal in-memory store for testing cross-process behaviour."""

    def __init__(self) -> None:
        self.leases: dict[tuple[str, int], float] = {}
        self.outcomes: dict[tuple[str, int], BackgroundTaskInfo] = {}
        self.cancel_requests: list[str] = []
        self.renew_calls: list[tuple[str, int]] = []

    async def acquire(self, qualified_session_key: str, task_id: int, *, ttl_seconds: float) -> None:
        self.leases[(qualified_session_key, task_id)] = time.time() + ttl_seconds
        self.outcomes.pop((qualified_session_key, task_id), None)

    async def renew(self, qualified_session_key: str, task_id: int, *, ttl_seconds: float) -> None:
        self.renew_calls.append((qualified_session_key, task_id))
        if (qualified_session_key, task_id) in self.leases:
            self.leases[(qualified_session_key, task_id)] = time.time() + ttl_seconds

    async def is_alive(self, qualified_session_key: str, task_id: int) -> bool:
        expiry = self.leases.get((qualified_session_key, task_id))
        if expiry is None:
            return False
        return time.time() < expiry

    async def publish_outcome(self, qualified_session_key: str, task_id: int, info: BackgroundTaskInfo) -> None:
        if (qualified_session_key, task_id) not in self.outcomes:
            self.outcomes[(qualified_session_key, task_id)] = info
        self.leases.pop((qualified_session_key, task_id), None)

    async def fetch_outcome(self, qualified_session_key: str, task_id: int) -> BackgroundTaskInfo | None:
        return self.outcomes.get((qualified_session_key, task_id))

    async def request_cancel(self, qualified_session_key: str) -> None:
        self.cancel_requests.append(qualified_session_key)

    async def is_cancel_requested(self, qualified_session_key: str) -> bool:
        if qualified_session_key in self.cancel_requests:
            self.cancel_requests.remove(qualified_session_key)
            return True
        return False


@pytest.mark.asyncio
async def test_cross_process_is_alive_prevents_lost_status() -> None:
    """A task running on process A should not be marked LOST by process B."""
    shared_store = _TestRuntimeStore()

    # Process A
    provider_a = _make_provider(_FakeAgent("worker", delay=10.0), runtime_store=shared_store)
    session = _make_session()
    tools_a = await _get_tools(provider_a, session)
    await _invoke_tool(tools_a["background_agents_start_task"], agent_name="worker", input="go", description="job")

    # Process B (shares the same session state and store)
    provider_b = _make_provider(_FakeAgent("worker", delay=10.0), runtime_store=shared_store)
    tools_b = await _get_tools(provider_b, session)

    # Process B checks tasks
    res = await _invoke_tool(tools_b["background_agents_get_task_results"], task_id=1)

    # Since store.is_alive() returns True, it should still be RUNNING, not LOST
    assert "still running" in res


@pytest.mark.asyncio
async def test_cross_process_outcome_recovery() -> None:
    """A completed task on process A should have its result delivered to process B."""
    shared_store = _TestRuntimeStore()

    # Process A
    provider_a = _make_provider(_FakeAgent("worker", delay=0.0, response_text="A result"), runtime_store=shared_store)
    session = _make_session()
    tools_a = await _get_tools(provider_a, session)
    await _invoke_tool(tools_a["background_agents_start_task"], agent_name="worker", input="go", description="job")

    # Wait for the task to finish on A so the done-callback publishes the outcome
    await asyncio.sleep(0.1)

    # Process B (starts with same session)
    provider_b = _make_provider(_FakeAgent("worker", delay=0.0), runtime_store=shared_store)
    tools_b = await _get_tools(provider_b, session)

    # Process B asks for results. It has no local asyncio.Task, but the store has the outcome.
    res = await _invoke_tool(tools_b["background_agents_get_task_results"], task_id=1)
    assert res == "A result"


@pytest.mark.asyncio
async def test_release_session_signals_cancel_to_non_owners() -> None:
    """Calling release_session on process B should signal request_cancel to the store."""
    shared_store = _TestRuntimeStore()

    provider = _make_provider(_FakeAgent("worker"), runtime_store=shared_store)
    session = AgentSession(session_id="test-session-123")

    # release_session should invoke request_cancel even without local in_flight_tasks
    await provider.release_session(session, cancel_running=True)

    assert "test-session-123" in shared_store.cancel_requests


@pytest.mark.asyncio
async def test_continue_task_on_non_owner_returns_error() -> None:
    """background_agents_continue_task should fail safely when called cross-process."""
    shared_store = _TestRuntimeStore()

    # A publishes a finished task
    session = _make_session()
    provider_a = _make_provider(_FakeAgent("worker", response_text="done"), runtime_store=shared_store)
    tools_a = await _get_tools(provider_a, session)
    await _invoke_tool(tools_a["background_agents_start_task"], agent_name="worker", input="go", description="job")
    await asyncio.sleep(0.1)  # allow completion

    # B attempts to continue it
    provider_b = _make_provider(_FakeAgent("worker", response_text="done"), runtime_store=shared_store)
    tools_b = await _get_tools(provider_b, session)

    res = await _invoke_tool(tools_b["background_agents_continue_task"], task_id=1, text="more")
    assert "was completed on another instance" in res
    assert "continue is not available cross-process" in res


@pytest.mark.asyncio
async def test_default_in_memory_store_regression() -> None:
    """Without a shared store, cross-process tasks should be marked LOST (historical behaviour)."""
    # Process A
    provider_a = _make_provider(_FakeAgent("worker", delay=10.0))  # type: ignore[list-item]
    session = _make_session()
    tools_a = await _get_tools(provider_a, session)
    await _invoke_tool(tools_a["background_agents_start_task"], agent_name="worker", input="go", description="job")

    # Process B
    provider_b = _make_provider(_FakeAgent("worker", delay=10.0))  # type: ignore[list-item]
    tools_b = await _get_tools(provider_b, session)

    res = await _invoke_tool(tools_b["background_agents_get_task_results"], task_id=1)

    # Without a shared store, Process B cannot see Process A's tasks, so it reverts to LOST
    assert "Task state was lost" in res


@pytest.mark.asyncio
async def test_cross_process_task_expires_shows_lost() -> None:
    """A task whose lease expires should be shown as LOST."""
    shared_store = _TestRuntimeStore()

    provider_a = _make_provider(_FakeAgent("worker", delay=10.0), runtime_store=shared_store)  # type: ignore[list-item]
    session = _make_session()
    tools_a = await _get_tools(provider_a, session)
    await _invoke_tool(tools_a["background_agents_start_task"], agent_name="worker", input="go", description="job")

    # Manually expire the lease
    shared_store.leases[(session.session_id, 1)] = time.time() - 10.0

    provider_b = _make_provider(_FakeAgent("worker", delay=10.0), runtime_store=shared_store)  # type: ignore[list-item]
    tools_b = await _get_tools(provider_b, session)
    res = await _invoke_tool(tools_b["background_agents_get_task_results"], task_id=1)

    assert "Task state was lost" in res
    await provider_a.release_session(session, cancel_running=True)


@pytest.mark.asyncio
async def test_cross_process_task_recovers_from_lost_when_outcome_arrives() -> None:
    """A task marked LOST should recover if its outcome eventually appears in the store."""
    shared_store = _TestRuntimeStore()
    provider_a = _make_provider(
        _FakeAgent("worker", delay=0.1, response_text="late_result"),  # type: ignore[list-item]
        runtime_store=shared_store,
    )
    session = _make_session()
    tools_a = await _get_tools(provider_a, session)
    await _invoke_tool(tools_a["background_agents_start_task"], agent_name="worker", input="go", description="job")

    # Manually expire the lease so B sees it as LOST
    shared_store.leases[(session.session_id, 1)] = time.time() - 10.0

    provider_b = _make_provider(_FakeAgent("worker"), runtime_store=shared_store)  # type: ignore[list-item]
    tools_b = await _get_tools(provider_b, session)

    # First check: B sees it as LOST because lease is expired and outcome isn't there yet
    res1 = await _invoke_tool(tools_b["background_agents_get_task_results"], task_id=1)
    assert "Task state was lost" in res1

    # Allow the task on A to actually finish and publish its outcome
    await asyncio.sleep(0.2)

    # Second check: B should recover the LOST task because the outcome is now in the store
    res2 = await _invoke_tool(tools_b["background_agents_get_task_results"], task_id=1)
    assert "late_result" in res2

    await provider_a.release_session(session, cancel_running=True)


@pytest.mark.asyncio
async def test_cross_process_wait_polls_store() -> None:
    """Wait for first completion should poll the store if no local task."""
    shared_store = _TestRuntimeStore()

    provider_a = _make_provider(
        _FakeAgent("worker", delay=0.5, response_text="A result"),  # type: ignore[list-item]
        runtime_store=shared_store,
    )
    session = _make_session()
    tools_a = await _get_tools(provider_a, session)
    await _invoke_tool(tools_a["background_agents_start_task"], agent_name="worker", input="go", description="job")

    provider_b = _make_provider(_FakeAgent("worker", delay=0.5), runtime_store=shared_store)  # type: ignore[list-item]
    # Reduce timeout for faster test
    provider_b._wait_timeout_seconds = 2
    tools_b = await _get_tools(provider_b, session)

    res = await _invoke_tool(tools_b["background_agents_wait_for_first_completion"], task_ids=[1])
    assert "Task 1 finished with status: completed" in res

    await provider_a.release_session(session, cancel_running=True)


@pytest.mark.asyncio
async def test_continue_task_new_outcome() -> None:
    """Continue task should clear the old outcome and store the new one."""
    shared_store = _TestRuntimeStore()

    provider_a = _make_provider(
        _FakeAgent("worker", delay=0.1, response_text="done 1"),  # type: ignore[list-item]
        runtime_store=shared_store,
    )
    session = _make_session()
    tools_a = await _get_tools(provider_a, session)
    await _invoke_tool(tools_a["background_agents_start_task"], agent_name="worker", input="go", description="job")

    await asyncio.sleep(0.2)  # let it finish

    # Now continue it on the same provider (owner)
    provider_a._agents["worker"] = _FakeAgent("worker", delay=0.1, response_text="done 2")  # type: ignore[assignment]
    await _invoke_tool(tools_a["background_agents_continue_task"], task_id=1, text="more")

    await asyncio.sleep(0.2)  # let it finish

    provider_b = _make_provider(_FakeAgent("worker"), runtime_store=shared_store)  # type: ignore[list-item]
    tools_b = await _get_tools(provider_b, session)
    res = await _invoke_tool(tools_b["background_agents_get_task_results"], task_id=1)

    assert res == "done 2"
    await provider_a.release_session(session, cancel_running=True)


@pytest.mark.asyncio
async def test_run_agent_with_renewal_renews_lease() -> None:
    """The renewal loop must call renew on the store."""
    shared_store = _TestRuntimeStore()

    async def slow_agent():
        await asyncio.sleep(1.5)
        return AgentResponse(messages=[Message(role="assistant", contents=["done"])])

    # ttl=1.0 means it renews every 0.5s
    await _run_agent_with_renewal(slow_agent(), shared_store, "test-key", 1, ttl_seconds=1.0)

    assert len(shared_store.renew_calls) >= 1
    assert ("test-key", 1) in shared_store.renew_calls


@pytest.mark.asyncio
async def test_run_agent_with_renewal_cancels_on_remote_signal() -> None:
    """The renewal loop must cancel the work task when is_cancel_requested returns True."""
    shared_store = _TestRuntimeStore()

    async def long_agent() -> AgentResponse[Any]:
        await asyncio.sleep(30.0)
        return AgentResponse(messages=[Message(role="assistant", contents=["never"])])

    # Pre-seed a cancel request so it fires on the first renewal tick (ttl/2 = 0.5s).
    shared_store.cancel_requests.append("test-cancel-key")

    with pytest.raises(asyncio.CancelledError):
        await _run_agent_with_renewal(long_agent(), shared_store, "test-cancel-key", 1, ttl_seconds=1.0)
