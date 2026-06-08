# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_framework import (
    AgentResponse,
    AgentSession,
    BackgroundAgentsProvider,
    BackgroundTaskInfo,
    BackgroundTaskStatus,
    Message,
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

    def get_session(self, service_session_id: str, *, session_id: str | None = None) -> AgentSession:
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
    return BackgroundAgentsProvider(agents)


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
        BackgroundAgentsProvider([agent])


def test_constructor_rejects_duplicate_names() -> None:
    """Should reject duplicate agent names (case-insensitive)."""
    agent1 = _FakeAgent("Research")
    agent2 = _FakeAgent("research")
    with pytest.raises(ValueError, match="Duplicate background agent name"):
        BackgroundAgentsProvider([agent1, agent2])


def test_constructor_valid_agents() -> None:
    """Should succeed with valid unique agents."""
    provider = BackgroundAgentsProvider([_FakeAgent("Alpha"), _FakeAgent("Beta")])
    assert provider.source_id == "background_agents"


def test_constructor_custom_source_id() -> None:
    """Should accept custom source_id."""
    provider = BackgroundAgentsProvider([_FakeAgent("Agent1")], source_id="custom_bg")
    assert provider.source_id == "custom_bg"


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
