# Copyright (c) Microsoft. All rights reserved.

"""BackgroundAgentsProvider: enables an agent to delegate work to background sub-agents asynchronously.

This module provides :class:`BackgroundAgentsProvider`, a context provider that allows
a parent agent to start background tasks on child agents, wait for their completion,
and retrieve results. Each background task runs in its own session concurrently.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, MutableMapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, cast

from .._agents import SupportsAgentRun
from .._feature_stage import ExperimentalFeature, experimental
from .._serialization import SerializationMixin
from .._sessions import AgentSession, ContextProvider, SessionContext
from .._telemetry import FeatureIndex, mark_feature_used
from .._tools import tool
from .._types import AgentResponse, Message

DEFAULT_BACKGROUND_AGENTS_SOURCE_ID = "background_agents"

DEFAULT_BACKGROUND_AGENTS_INSTRUCTIONS = """\
## Background Agents

You have access to background agents that can perform work on your behalf.

- Use the `background_agents_*` tools to start tasks on background agents and check their results.
- Creating a background task does not block, and background tasks run concurrently.
- Important: Always wait for outstanding tasks to finish before you finish processing.
- Important: After retrieving results from a completed task, clear it with \
background_agents_clear_completed_task to free memory, unless you plan to continue it with \
background_agents_continue_task.

{background_agents}"""


class BackgroundTaskStatus(str, Enum):
    """Status of a background task."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    LOST = "lost"


@experimental(feature_id=ExperimentalFeature.HARNESS)
class BackgroundTaskInfo(SerializationMixin):
    """Metadata for a single background task."""

    DEFAULT_EXCLUDE: ClassVar[set[str]] = set()

    id: int
    agent_name: str
    description: str
    status: BackgroundTaskStatus
    result_text: str | None
    error_text: str | None
    __slots__ = ("agent_name", "description", "error_text", "id", "result_text", "status")

    def __init__(
        self,
        id: int,
        agent_name: str,
        description: str,
        status: BackgroundTaskStatus = BackgroundTaskStatus.RUNNING,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> None:
        """Initialize a background task info entry."""
        self.id = id
        self.agent_name = agent_name
        self.description = description
        self.status = status
        self.result_text = result_text
        self.error_text = error_text

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Serialize for session state persistence."""
        del exclude
        data: dict[str, Any] = {
            "id": self.id,
            "agent_name": self.agent_name,
            "description": self.description,
            "status": self.status.value,
        }
        if not exclude_none or self.result_text is not None:
            data["result_text"] = self.result_text
        if not exclude_none or self.error_text is not None:
            data["error_text"] = self.error_text
        return data

    @classmethod
    def from_dict(cls, data: MutableMapping[str, Any], **kwargs: Any) -> BackgroundTaskInfo:
        """Deserialize from session state."""
        return cls(
            id=data["id"],
            agent_name=data["agent_name"],
            description=data["description"],
            status=BackgroundTaskStatus(data["status"]),
            result_text=data.get("result_text"),
            error_text=data.get("error_text"),
        )


@dataclass
class _RuntimeState:
    """Non-serializable per-session runtime state for background tasks."""

    in_flight_tasks: dict[int, asyncio.Task[AgentResponse[Any]]] = field(default_factory=lambda: {})
    background_sessions: dict[int, AgentSession] = field(default_factory=lambda: {})


# ---------------------------------------------------------------------------
# Module-level helper functions (following ModeProvider pattern)
# ---------------------------------------------------------------------------


async def _run_agent(awaitable: Awaitable[AgentResponse[Any]]) -> AgentResponse[Any]:
    """Wrap an Awaitable in a proper coroutine for use with asyncio.create_task."""
    return await awaitable


def _validate_and_build_agent_dict(agents: Sequence[SupportsAgentRun]) -> dict[str, SupportsAgentRun]:
    """Validate agents and build a case-insensitive lookup dict.

    Raises:
        ValueError: If agents is empty, an agent has no name, or names are not unique.
    """
    if not agents:
        raise ValueError("At least one background agent must be provided.")

    agent_dict: dict[str, SupportsAgentRun] = {}
    for agent in agents:
        name = agent.name
        if not name or not name.strip():
            raise ValueError("All background agents must have a non-empty name.")
        key = name.lower()
        if key in agent_dict:
            raise ValueError(
                f"Duplicate background agent name: '{name}'. Agent names must be unique (case-insensitive)."
            )
        agent_dict[key] = agent
    return agent_dict


def _build_agent_list_text(agents: dict[str, SupportsAgentRun]) -> str:
    """Build text listing available background agents."""
    lines = ["Available background agents:"]
    for agent in agents.values():
        line = f"- {agent.name}"
        if agent.description:
            line += f": {agent.description}"
        lines.append(line)
    return "\n".join(lines)


def _get_provider_state(session: AgentSession, *, source_id: str) -> dict[str, Any]:
    """Load or initialize serializable provider state from session."""
    state = session.state.get(source_id)
    if state is None:
        initial: dict[str, Any] = {"next_task_id": 1, "tasks": []}
        session.state[source_id] = initial
        return initial
    return cast(dict[str, Any], state)


def _save_provider_state(session: AgentSession, state: dict[str, Any], *, source_id: str) -> None:
    """Persist serializable state to session."""
    session.state[source_id] = state


def _get_tasks(state: dict[str, Any]) -> list[BackgroundTaskInfo]:
    """Parse task list from state dict."""
    return [BackgroundTaskInfo.from_dict(t) for t in state.get("tasks", [])]


def _save_tasks(state: dict[str, Any], tasks: list[BackgroundTaskInfo]) -> None:
    """Serialize task list back to state dict."""
    state["tasks"] = [t.to_dict() for t in tasks]


def _finalize_task(
    task_info: BackgroundTaskInfo,
    completed_task: asyncio.Task[AgentResponse[Any]],
    runtime: _RuntimeState,
) -> None:
    """Extract results from a completed asyncio task and update task info."""
    if completed_task.cancelled():
        task_info.status = BackgroundTaskStatus.FAILED
        task_info.error_text = "Task was canceled."
    else:
        exception = completed_task.exception()
        if exception is not None:
            task_info.status = BackgroundTaskStatus.FAILED
            task_info.error_text = str(exception)
        else:
            task_info.status = BackgroundTaskStatus.COMPLETED
            task_info.result_text = completed_task.result().text
    runtime.in_flight_tasks.pop(task_info.id, None)


def _refresh_task_state(
    session: AgentSession, state: dict[str, Any], runtime: _RuntimeState, *, source_id: str
) -> list[BackgroundTaskInfo]:
    """Refresh status of in-flight tasks and return updated task list."""
    tasks = _get_tasks(state)
    changed = False

    for task_info in tasks:
        if task_info.status != BackgroundTaskStatus.RUNNING:
            continue

        in_flight = runtime.in_flight_tasks.get(task_info.id)
        if in_flight is None:
            task_info.status = BackgroundTaskStatus.LOST
            changed = True
            continue

        if in_flight.done():
            _finalize_task(task_info, in_flight, runtime)
            changed = True

    if changed:
        _save_tasks(state, tasks)
        _save_provider_state(session, state, source_id=source_id)

    return tasks


# ---------------------------------------------------------------------------
# Provider class
# ---------------------------------------------------------------------------


@experimental(feature_id=ExperimentalFeature.HARNESS)
class BackgroundAgentsProvider(ContextProvider):
    """Context provider that enables an agent to delegate work to background sub-agents.

    The ``BackgroundAgentsProvider`` allows a parent agent to start background tasks on child agents,
    wait for their completion, and retrieve results. Each background task runs in its own session and
    executes concurrently.

    This provider exposes the following tools to the agent:

    - ``background_agents_start_task`` — Start a background task on a named agent with text input.
    - ``background_agents_wait_for_first_completion`` — Block until the first of the specified tasks completes.
    - ``background_agents_get_task_results`` — Retrieve the text output of a completed background task.
    - ``background_agents_get_all_tasks`` — List all background tasks with their IDs, statuses, and descriptions.
    - ``background_agents_continue_task`` — Send follow-up input to a completed task's session to resume work.
    - ``background_agents_clear_completed_task`` — Remove a completed task and release its session.

    Security considerations:
        The agents passed to the constructor are delegated arbitrary work by the parent agent — the
        parent sends them text input (which may include content derived from the parent's own
        untrusted context) and receives back whatever text they produce. A compromised or malicious
        supplied agent (for example, one with a compromised system prompt, tools, or upstream model)
        could exfiltrate that input to an external system, or return adversarial output designed to
        influence the parent agent via indirect prompt injection once its result is retrieved. Only
        supply background agents you have vetted and trust with the data the parent may pass to them.
    """

    def __init__(
        self,
        agents: Sequence[SupportsAgentRun],
        *,
        source_id: str = DEFAULT_BACKGROUND_AGENTS_SOURCE_ID,
        instructions: str | None = None,
    ) -> None:
        """Initialize the background agents provider.

        Args:
            agents: Collection of background agents available for delegation.
                Each agent must have a non-empty, unique name (case-insensitive).
                **Security:** each supplied agent should be vetted and trusted, since it will receive
                text input from the parent agent and its output is fed back into the parent's
                context — see the class-level security considerations for the exfiltration and
                prompt-injection risks of untrusted agents.

        Keyword Args:
            source_id: Unique source ID for serializable task state in session.
            instructions: Optional instruction override. May include ``{background_agents}``
                placeholder which will be replaced with the agent listing.

        Raises:
            ValueError: If agents is empty, an agent has no name, or names are not unique.
        """
        super().__init__(source_id)

        self._agents = _validate_and_build_agent_dict(agents)

        # Build instructions with agent listing.
        base_instructions = instructions if instructions is not None else DEFAULT_BACKGROUND_AGENTS_INSTRUCTIONS
        agent_list_text = _build_agent_list_text(self._agents)
        self._instructions = base_instructions.replace("{background_agents}", agent_list_text)

        # Per-session runtime state (non-serializable), keyed by session_id.
        # Note: Runtime state (in-flight asyncio.Task objects, child AgentSession handles)
        # is inherently non-serializable and cannot survive process restarts. If the provider
        # instance is lost, _refresh_task_state() marks orphaned tasks as LOST.
        self._runtime: dict[str, _RuntimeState] = {}

    def _get_runtime(self, session: AgentSession) -> _RuntimeState:
        """Get or create runtime state for a session."""
        session_id = session.session_id
        if session_id not in self._runtime:
            self._runtime[session_id] = _RuntimeState()
        return self._runtime[session_id]

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject background agent tools and instructions before the model runs."""
        mark_feature_used(FeatureIndex.CORE_BACKGROUND_AGENTS_PROVIDER)
        del agent, state

        provider_state = _get_provider_state(session, source_id=self.source_id)
        runtime = self._get_runtime(session)
        source_id = self.source_id

        @tool(name="background_agents_start_task", approval_mode="never_require")
        def background_agents_start_task(agent_name: str, input: str, description: str) -> str:
            """Start a background task on a named agent. Returns a confirmation with the task ID."""
            key = agent_name.lower()
            if key not in self._agents:
                available = ", ".join(a.name or "" for a in self._agents.values())
                return f"Error: No background agent found with name '{agent_name}'. Available agents: {available}"

            bg_agent = self._agents[key]
            task_id = provider_state.get("next_task_id", 1)
            provider_state["next_task_id"] = task_id + 1

            task_info = BackgroundTaskInfo(
                id=task_id,
                agent_name=agent_name,
                description=description,
            )
            tasks = _get_tasks(provider_state)
            tasks.append(task_info)
            _save_tasks(provider_state, tasks)

            # Create a dedicated session for this background task.
            sub_session = bg_agent.create_session()

            # Start the task concurrently.
            async_task = asyncio.create_task(_run_agent(bg_agent.run(input, session=sub_session)))
            runtime.in_flight_tasks[task_id] = async_task
            runtime.background_sessions[task_id] = sub_session

            _save_provider_state(session, provider_state, source_id=source_id)
            return f"Background task {task_id} started on agent '{agent_name}'."

        background_agents_start_task._invoke_sync_on_event_loop = True  # pyright: ignore[reportPrivateUsage]

        @tool(name="background_agents_wait_for_first_completion", approval_mode="never_require")
        async def background_agents_wait_for_first_completion(task_ids: list[int]) -> str:
            """Block until the first of the specified background tasks completes. Returns the completed task's ID."""
            if not task_ids:
                return "Error: No task IDs provided."

            # Collect in-flight tasks matching the requested IDs.
            waitable: list[tuple[int, asyncio.Task[AgentResponse[Any]]]] = []
            for tid in task_ids:
                in_flight = runtime.in_flight_tasks.get(tid)
                if in_flight is not None:
                    waitable.append((tid, in_flight))

            if not waitable:
                # Refresh state to catch any that completed.
                tasks = _refresh_task_state(session, provider_state, runtime, source_id=source_id)
                already_complete = next(
                    (t for t in tasks if t.id in task_ids and t.status != BackgroundTaskStatus.RUNNING), None
                )
                if already_complete is not None:
                    return (
                        f"Task {already_complete.id} is not running; current status: {already_complete.status.value}."
                    )
                return "Error: None of the specified task IDs correspond to running tasks."

            # Wait for the first one to complete.
            done, _ = await asyncio.wait(
                [t for _, t in waitable],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Find which ID completed.
            completed_id: int | None = None
            for tid, task in waitable:
                if task in done:
                    completed_id = tid
                    break

            # Finalize the completed task.
            tasks = _get_tasks(provider_state)
            task_info = next((t for t in tasks if t.id == completed_id), None)
            if task_info is not None and completed_id is not None:
                completed_task = runtime.in_flight_tasks.get(completed_id)
                if completed_task is not None:
                    _finalize_task(task_info, completed_task, runtime)
                    _save_tasks(provider_state, tasks)
                    _save_provider_state(session, provider_state, source_id=source_id)

            status_str = task_info.status.value if task_info else "Unknown"
            return f"Task {completed_id} finished with status: {status_str}."

        @tool(name="background_agents_get_task_results", approval_mode="never_require")
        def background_agents_get_task_results(task_id: int) -> str:
            """Get the text output of a background task by its ID."""
            tasks = _refresh_task_state(session, provider_state, runtime, source_id=source_id)
            task_info = next((t for t in tasks if t.id == task_id), None)

            if task_info is None:
                return f"Error: No task found with ID {task_id}."

            if task_info.status == BackgroundTaskStatus.COMPLETED:
                return task_info.result_text or "(no output)"
            if task_info.status == BackgroundTaskStatus.FAILED:
                return f"Task failed: {task_info.error_text or 'Unknown error'}"
            if task_info.status == BackgroundTaskStatus.LOST:
                return "Task state was lost (reference unavailable)."
            if task_info.status == BackgroundTaskStatus.RUNNING:
                return f"Task {task_id} is still running."
            return f"Task {task_id} has status: {task_info.status.value}."

        @tool(name="background_agents_get_all_tasks", approval_mode="never_require")
        def background_agents_get_all_tasks() -> str:
            """List all background tasks with their IDs, statuses, agent names, and descriptions."""
            tasks = _refresh_task_state(session, provider_state, runtime, source_id=source_id)

            if not tasks:
                return "No tasks."

            lines = ["Tasks:"]
            for t in tasks:
                lines.append(f"- Task {t.id} [{t.status.value}] ({t.agent_name}): {t.description}")
            return "\n".join(lines)

        @tool(name="background_agents_continue_task", approval_mode="never_require")
        def background_agents_continue_task(task_id: int, text: str) -> str:
            """Send follow-up input to a completed or failed task to resume its work."""
            tasks = _refresh_task_state(session, provider_state, runtime, source_id=source_id)
            task_info = next((t for t in tasks if t.id == task_id), None)

            if task_info is None:
                return f"Error: No task found with ID {task_id}."

            if task_info.status == BackgroundTaskStatus.LOST:
                return (
                    f"Error: Task {task_id} cannot be continued because its session was lost. Start a new task instead."
                )

            if task_info.status == BackgroundTaskStatus.RUNNING:
                return f"Error: Task {task_id} is still running. Wait for it to complete before continuing."

            key = task_info.agent_name.lower()
            if key not in self._agents:
                return f"Error: Agent '{task_info.agent_name}' is no longer available."

            sub_session = runtime.background_sessions.get(task_id)
            if sub_session is None:
                return f"Error: Session for task {task_id} is no longer available."

            bg_agent = self._agents[key]

            # Reset task state and start a new run on the existing session.
            task_info.status = BackgroundTaskStatus.RUNNING
            task_info.result_text = None
            task_info.error_text = None
            _save_tasks(provider_state, tasks)

            async_task = asyncio.create_task(_run_agent(bg_agent.run(text, session=sub_session)))
            runtime.in_flight_tasks[task_id] = async_task

            _save_provider_state(session, provider_state, source_id=source_id)
            return f"Task {task_id} continued with new input."

        background_agents_continue_task._invoke_sync_on_event_loop = True  # pyright: ignore[reportPrivateUsage]

        @tool(name="background_agents_clear_completed_task", approval_mode="never_require")
        def background_agents_clear_completed_task(task_id: int) -> str:
            """Remove a completed or failed task and release its session to free memory."""
            tasks = _refresh_task_state(session, provider_state, runtime, source_id=source_id)
            task_info = next((t for t in tasks if t.id == task_id), None)

            if task_info is None:
                return f"Error: No task found with ID {task_id}."

            if task_info.status == BackgroundTaskStatus.RUNNING:
                return f"Error: Task {task_id} is still running. Wait for it to complete before clearing."

            # Remove the task from state.
            tasks = [t for t in tasks if t.id != task_id]
            _save_tasks(provider_state, tasks)

            # Clean up runtime references.
            runtime.in_flight_tasks.pop(task_id, None)
            runtime.background_sessions.pop(task_id, None)

            _save_provider_state(session, provider_state, source_id=source_id)
            return f"Task {task_id} cleared."

        # Inject instructions and current task status.
        context.extend_instructions(self.source_id, [self._instructions])
        context.extend_tools(
            self.source_id,
            [
                background_agents_start_task,
                background_agents_wait_for_first_completion,
                background_agents_get_task_results,
                background_agents_get_all_tasks,
                background_agents_continue_task,
                background_agents_clear_completed_task,
            ],
        )

        # Include current task status as context message if there are tasks.
        # Refresh first to get accurate statuses for any tasks that completed between turns.
        tasks = _refresh_task_state(session, provider_state, runtime, source_id=source_id)
        if tasks:
            status_lines = ["### Current background tasks"]
            for t in tasks:
                status_lines.append(f"- Task {t.id} [{t.status.value}] ({t.agent_name}): {t.description}")
            context.extend_messages(
                self.source_id,
                [Message(role="user", contents=["\n".join(status_lines)])],
            )
