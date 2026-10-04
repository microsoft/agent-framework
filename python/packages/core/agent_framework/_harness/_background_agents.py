# Copyright (c) Microsoft. All rights reserved.

"""BackgroundAgentsProvider: enables an agent to delegate work to background sub-agents asynchronously.

This module provides :class:`BackgroundAgentsProvider`, a context provider that allows
a parent agent to start background tasks on child agents, wait for their completion,
and retrieve results. Each background task runs in its own session concurrently.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, MutableMapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, ClassVar, Protocol, cast

from .._agents import SupportsAgentRun
from .._feature_stage import ExperimentalFeature, experimental
from .._serialization import SerializationMixin
from .._sessions import AgentSession, ContextProvider, SessionContext
from .._telemetry import FeatureIndex, mark_feature_used
from .._tools import tool
from .._types import AgentResponse, Message

logger = logging.getLogger(__name__)

DEFAULT_BACKGROUND_AGENTS_SOURCE_ID = "background_agents"
DEFAULT_BACKGROUND_AGENTS_WAIT_TIMEOUT_SECONDS = 300

# Default lease lifetime in seconds.  The renewal wrapper fires at ttl/2, so
# a task running longer than this will still renew before expiry.
DEFAULT_LEASE_TTL_SECONDS = 60.0

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


# ---------------------------------------------------------------------------
# BackgroundTaskRuntimeStore - pluggable liveness and outcome store
# ---------------------------------------------------------------------------


@experimental(feature_id=ExperimentalFeature.HARNESS)
class BackgroundTaskRuntimeStore(Protocol):
    """Protocol for a pluggable cross-process task liveness and outcome store.

    ``BackgroundAgentsProvider`` uses this store to distinguish a task that is
    running on another replica from one whose owner process has died, and to
    deliver a completed task's result to whichever process serves the next turn.

    The default implementation (:class:`_InMemoryBackgroundTaskRuntimeStore`)
    keeps all state in the current process, reproducing today's single-process
    behaviour exactly.  Multi-replica hosts should supply a distributed
    implementation (e.g. Redis-backed) via the ``runtime_store`` kwarg of
    :class:`BackgroundAgentsProvider`.

    All methods receive ``qualified_session_key`` — a caller-chosen string that
    uniquely identifies the session across processes.
    :class:`BackgroundAgentsProvider` uses ``session.session_id`` directly;
    callers that need namespace isolation can wrap or subclass the store.

    Distributed implementations should use the shared store's TTL or server
    clock for lease expiry rather than storing owner-computed ``time.time()``
    deadlines.  Client wall-clocks across hosts can be skewed, causing healthy
    tasks to be expired early or dead tasks to be kept alive.  The built-in
    :class:`_InMemoryBackgroundTaskRuntimeStore` uses ``time.time()`` safely
    because all comparisons occur within a single process.
    """

    async def acquire(self, qualified_session_key: str, task_id: int, *, ttl_seconds: float) -> None:
        """Record that this process owns ``task_id`` and write an initial lease.

        Must be called when a task is first started or continued.  Implementations
        must **atomically** replace the lease and remove any previously published
        outcome for this ``task_id`` so that a continuation can publish a fresh
        result (first-write-wins is reset on re-acquire).  The lease expires after
        ``ttl_seconds`` unless :meth:`renew` is called before then.

        Args:
            qualified_session_key: Unique session identifier.
            task_id: The task's integer ID.
            ttl_seconds: Lease lifetime in seconds.
        """
        ...

    async def renew(self, qualified_session_key: str, task_id: int, *, ttl_seconds: float) -> None:
        """Extend an existing lease so the task is not considered dead.

        Silently ignored if no active lease is found.

        Args:
            qualified_session_key: Unique session identifier.
            task_id: The task's integer ID.
            ttl_seconds: New lease lifetime from ``time.time()`` now.
        """
        ...

    async def is_alive(self, qualified_session_key: str, task_id: int) -> bool:
        """Return ``True`` if the task's lease is present and not expired.

        A ``False`` result means the owning process is gone, the lease expired,
        or the task was never acquired; consult :meth:`fetch_outcome` next.

        Args:
            qualified_session_key: Unique session identifier.
            task_id: The task's integer ID.
        """
        ...

    async def publish_outcome(
        self,
        qualified_session_key: str,
        task_id: int,
        info: BackgroundTaskInfo,
    ) -> None:
        """Persist the final outcome of a completed or failed task.

        Called from a done-callback on the underlying :class:`asyncio.Task` so
        that the result is available to any process on the next turn, even when
        the owning process never handles another turn for this session.

        Implementations must **atomically** store the first outcome and remove
        the task's active lease.  Only the first call for a given
        ``(qualified_session_key, task_id)`` pair should be stored; subsequent
        calls must be silently ignored to prevent overwriting a committed outcome.
        Removing the lease at publish time is required so that
        :meth:`_refresh_task_state` does not report the task as still alive
        while a result is already available.

        Args:
            qualified_session_key: Unique session identifier.
            task_id: The task's integer ID.
            info: The completed :class:`BackgroundTaskInfo` (COMPLETED or FAILED).
        """
        ...

    async def fetch_outcome(
        self,
        qualified_session_key: str,
        task_id: int,
    ) -> BackgroundTaskInfo | None:
        """Return the stored outcome for a task, or ``None`` if not yet available.

        Args:
            qualified_session_key: Unique session identifier.
            task_id: The task's integer ID.
        """
        ...

    async def request_cancel(self, qualified_session_key: str) -> None:
        """Signal the owning process to cancel all tasks for this session.

        Used by :meth:`BackgroundAgentsProvider.release_session` when called on
        a non-owning process so that running tasks are not left orphaned.  The
        in-memory default is a no-op; local tasks are cancelled directly.

        Args:
            qualified_session_key: Unique session identifier.
        """
        ...

    async def is_cancel_requested(self, qualified_session_key: str) -> bool:
        """Return ``True`` if :meth:`request_cancel` has been called for this session.

        Polled by :func:`_run_agent_with_renewal` on each renewal tick so that a
        cancel signal from another process causes the owning process to abort all
        tasks for this session.  Implementations **must not** clear the flag on
        read: the flag is session-scoped and sticky so that every concurrently
        polling task observes the cancellation, not just the first one to poll.

        Args:
            qualified_session_key: Unique session identifier.
        """
        ...


class _InMemoryBackgroundTaskRuntimeStore:
    """Default in-process implementation of :class:`BackgroundTaskRuntimeStore`.

    Keeps all state in plain dicts scoped to this provider instance, exactly
    reproducing today's single-process semantics:

    * Tasks ``acquire``d by *this* instance are visible here.
    * Tasks from a *different* provider instance (simulating another process
      sharing no store) are invisible, so :meth:`is_alive` returns ``False``
      and :meth:`_refresh_task_state` falls back to ``LOST`` — identical to
      the behaviour before the store was introduced.

    Hosts running multiple replicas should supply a shared distributed store.
    """

    def __init__(self) -> None:
        # (qualified_session_key, task_id) -> wall-clock expiry (time.time() + ttl)
        self._leases: dict[tuple[str, int], float] = {}
        # (qualified_session_key, task_id) -> outcome; first-write-wins
        self._outcomes: dict[tuple[str, int], BackgroundTaskInfo] = {}
        # session keys for which cancellation has been requested
        self._cancel_requests: set[str] = set()

    async def acquire(self, qualified_session_key: str, task_id: int, *, ttl_seconds: float) -> None:
        """Write an initial lease for the task."""
        self._leases[qualified_session_key, task_id] = time.time() + ttl_seconds
        self._outcomes.pop((qualified_session_key, task_id), None)

    async def renew(self, qualified_session_key: str, task_id: int, *, ttl_seconds: float) -> None:
        """Extend an existing lease; silently ignored if no lease is present."""
        key = (qualified_session_key, task_id)
        if key in self._leases:
            self._leases[key] = time.time() + ttl_seconds

    async def is_alive(self, qualified_session_key: str, task_id: int) -> bool:
        """Return ``True`` if the lease exists and has not expired."""
        key = (qualified_session_key, task_id)
        expiry = self._leases.get(key)
        return expiry is not None and time.time() < expiry

    async def publish_outcome(
        self,
        qualified_session_key: str,
        task_id: int,
        info: BackgroundTaskInfo,
    ) -> None:
        """Store the outcome (first-write-wins) and clear the lease.

        Removing the lease ensures subsequent :meth:`is_alive` calls return
        ``False``, causing :meth:`_refresh_task_state` to pick up the outcome
        via :meth:`fetch_outcome` on the next turn.
        """
        key = (qualified_session_key, task_id)
        if key not in self._outcomes:
            # First-write-wins: a late or duplicate done-callback cannot
            # overwrite an already-committed outcome.
            self._outcomes[key] = info
        self._leases.pop(key, None)

    async def fetch_outcome(
        self,
        qualified_session_key: str,
        task_id: int,
    ) -> BackgroundTaskInfo | None:
        """Return the stored outcome, or ``None`` if not yet published."""
        return self._outcomes.get((qualified_session_key, task_id))

    async def request_cancel(self, qualified_session_key: str) -> None:
        """Record a cancellation request for this session key."""
        self._cancel_requests.add(qualified_session_key)

    async def is_cancel_requested(self, qualified_session_key: str) -> bool:
        """Return ``True`` if a cancel has been requested for this session.

        The flag is sticky: it is never cleared so every concurrent task in
        the session observes the cancellation on its next poll.
        """
        return qualified_session_key in self._cancel_requests


@dataclass
class _RuntimeState:
    """Non-serializable per-session runtime state for background tasks."""

    in_flight_tasks: dict[int, asyncio.Task[AgentResponse[Any]]] = field(default_factory=lambda: {})
    background_sessions: dict[int, AgentSession] = field(default_factory=lambda: {})
    publish_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    closed: bool = False

    def track_task(self, task_id: int, task: asyncio.Task[AgentResponse[Any]]) -> None:
        """Track a background task if this runtime is still open."""
        if self.closed:
            task.cancel()
            raise RuntimeError("Session runtime is closed; cannot start background task.")

        self.in_flight_tasks[task_id] = task


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


async def _run_agent(awaitable: Awaitable[AgentResponse[Any]]) -> AgentResponse[Any]:
    """Wrap an Awaitable in a proper coroutine for use with asyncio.create_task."""
    return await awaitable


async def _run_agent_with_renewal(
    awaitable: Awaitable[AgentResponse[Any]],
    store: BackgroundTaskRuntimeStore,
    qualified_session_key: str,
    task_id: int,
    *,
    ttl_seconds: float,
) -> AgentResponse[Any]:
    """Run an agent coroutine while periodically renewing its store lease.

    The renewal fires at ``ttl_seconds / 2`` so the lease is always extended
    before it expires during a healthy run.  Because renewal is woven into
    this wrapper coroutine (not a separate :func:`asyncio.create_task`), the
    renewal lifecycle is tied to the task: when the task completes or is
    cancelled the renewal loop stops automatically.

    Args:
        awaitable: The agent-run coroutine to execute.
        store: The :class:`BackgroundTaskRuntimeStore` to renew against.
        qualified_session_key: Lease namespace key.
        task_id: The task's integer ID.
        ttl_seconds: Full lease lifetime; renewal fires at half this interval.
    """
    if ttl_seconds < 1.0:
        raise ValueError(f"ttl_seconds must be at least 1.0, got {ttl_seconds}")
    # Don't hammer the store for tiny TTLs, but never exceed ttl/2.
    renewal_interval = max(0.5, ttl_seconds / 2)
    work_task: asyncio.Task[AgentResponse[Any]] = asyncio.create_task(_run_agent(awaitable))
    try:
        while True:
            done, _ = await asyncio.wait({work_task}, timeout=renewal_interval)
            if done:
                return work_task.result()
            # Task still running - check for remote cancellation request first.
            try:
                if await store.is_cancel_requested(qualified_session_key):
                    logger.debug(
                        "Remote cancel requested for session %s; aborting task %s.",
                        qualified_session_key,
                        task_id,
                    )
                    work_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await work_task
                    raise asyncio.CancelledError
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Failed to check cancel request for session %s", qualified_session_key)
            # Then extend the lease before it can expire.
            try:
                await store.renew(qualified_session_key, task_id, ttl_seconds=ttl_seconds)
            except Exception:
                logger.debug(
                    "Failed to renew lease for task %s on session %s",
                    task_id,
                    qualified_session_key,
                )
    except BaseException:
        if not work_task.done():
            work_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await work_task
        raise


def _log_abandoned_background_task(task: asyncio.Task[Any]) -> None:
    """Retrieve exception from an abandoned task to avoid asyncio warnings."""
    if task.cancelled():
        return

    try:
        exception = task.exception()
    except asyncio.CancelledError:
        return

    if exception is not None:
        logger.debug("Abandoned background task raised: %s", exception)


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


def _finalize_task_from_info(
    task_info: BackgroundTaskInfo,
    stored: BackgroundTaskInfo,
    runtime: _RuntimeState,
) -> None:
    """Copy outcome fields from a store-fetched BackgroundTaskInfo into task_info.

    Used by :func:`_refresh_task_state` when the owning process published a
    result via a done-callback but the current process has no local
    :class:`asyncio.Task` for this task.  After this call the in-session record
    reflects the correct terminal status without marking the task ``LOST``.

    Args:
        task_info: The in-session record to update in place.
        stored: The published outcome retrieved from the runtime store.
        runtime: The process-local runtime (the task entry is popped from
            ``in_flight_tasks`` to match the behaviour of :func:`_finalize_task`).
    """
    task_info.status = stored.status
    task_info.result_text = stored.result_text
    task_info.error_text = stored.error_text
    runtime.in_flight_tasks.pop(task_info.id, None)


def _make_done_callback(
    store: BackgroundTaskRuntimeStore,
    qualified_session_key: str,
    task_id: int,
    agent_name: str,
    description: str,
    runtime: _RuntimeState,
) -> Callable[[asyncio.Task[AgentResponse[Any]]], None]:
    """Return an asyncio done-callback that publishes the task outcome to the store.

    The callback fires the instant the underlying task settles (success,
    failure, or cancellation), regardless of which turn or process is active.
    The publish is scheduled via ``loop.create_task`` so it does not block the
    event loop from inside the synchronous callback.

    Args:
        store: Destination runtime store for the published outcome.
        qualified_session_key: Lease/outcome namespace key.
        task_id: The task's integer ID.
        agent_name: Captured at task-start time for constructing the outcome.
        description: Captured at task-start time for constructing the outcome.
        runtime: The process-local runtime state.
    """

    def _callback(completed_task: asyncio.Task[AgentResponse[Any]]) -> None:
        if completed_task.cancelled():
            outcome = BackgroundTaskInfo(
                id=task_id,
                agent_name=agent_name,
                description=description,
                status=BackgroundTaskStatus.FAILED,
                error_text="Task was canceled.",
            )
        else:
            exc = completed_task.exception()
            if exc is not None:
                outcome = BackgroundTaskInfo(
                    id=task_id,
                    agent_name=agent_name,
                    description=description,
                    status=BackgroundTaskStatus.FAILED,
                    error_text=str(exc),
                )
            else:
                outcome = BackgroundTaskInfo(
                    id=task_id,
                    agent_name=agent_name,
                    description=description,
                    status=BackgroundTaskStatus.COMPLETED,
                    result_text=completed_task.result().text,
                )
        try:
            loop = asyncio.get_running_loop()
            pub_task = loop.create_task(store.publish_outcome(qualified_session_key, task_id, outcome))
            runtime.publish_tasks.add(pub_task)

            def _on_pub_done(t: asyncio.Task[None]) -> None:
                runtime.publish_tasks.discard(t)
                if not t.cancelled():
                    exc = t.exception()
                    if exc is not None:
                        logger.warning(
                            "Failed to publish outcome for task %s on session %s: %s",
                            task_id,
                            qualified_session_key,
                            exc,
                        )

            pub_task.add_done_callback(_on_pub_done)
        except RuntimeError:
            logger.debug(
                "No running event loop when publishing outcome for task %s; outcome not stored.",
                task_id,
            )

    return _callback


async def _refresh_task_state(
    session: AgentSession,
    state: dict[str, Any],
    runtime: _RuntimeState,
    store: BackgroundTaskRuntimeStore,
    qualified_session_key: str,
    *,
    source_id: str,
) -> list[BackgroundTaskInfo]:
    """Refresh status of in-flight tasks and return the updated task list.

    For each ``RUNNING`` record this function applies the following logic:

    1. **Local asyncio.Task exists and is done** — finalize immediately.
    2. **Local asyncio.Task exists and is still running** — leave ``RUNNING``.
    3. **No local asyncio.Task** — consult the store:

       a. :meth:`~BackgroundTaskRuntimeStore.is_alive` returns ``True`` —
          the task is owned by another process; leave ``RUNNING``.
       b. :meth:`~BackgroundTaskRuntimeStore.fetch_outcome` returns a result —
          finalize from the stored outcome (fixes orphaned results).
       c. Neither — mark ``LOST``, same as before.

    Store calls that raise are caught and logged; on an outage the record is
    left unchanged (``RUNNING`` or ``LOST``) so that a transient store failure
    does not permanently corrupt task state.  Only successful liveness and
    outcome queries trigger a state transition.

    Args:
        session: Current agent session (for persisting updated state).
        state: Provider-scoped state dict from ``session.state``.
        runtime: Process-local runtime state.
        store: The :class:`BackgroundTaskRuntimeStore` for liveness/outcome queries.
        qualified_session_key: Key passed to store methods.
        source_id: Provider source identifier used when saving state.
    """
    tasks = _get_tasks(state)
    changed = False

    for task_info in tasks:
        if task_info.status not in (BackgroundTaskStatus.RUNNING, BackgroundTaskStatus.LOST):
            continue

        in_flight = runtime.in_flight_tasks.get(task_info.id)

        if in_flight is not None:
            # Local task found - finalize if done, otherwise leave RUNNING (or recover from LOST).
            if in_flight.done():
                _finalize_task(task_info, in_flight, runtime)
                changed = True
            elif task_info.status == BackgroundTaskStatus.LOST:
                task_info.status = BackgroundTaskStatus.RUNNING
                changed = True
            continue

        # No local asyncio.Task on this process - ask the store.
        try:
            alive = await store.is_alive(qualified_session_key, task_info.id)
        except Exception:
            logger.debug(
                "Store is_alive check failed for task %s on session %s — leaving status unchanged.",
                task_info.id,
                qualified_session_key,
            )
            # Do not transition to LOST on a store outage; preserve current status
            # and retry on the next refresh to avoid false-LOST from a transient failure.
            continue

        if alive:
            # Task is running on another process - leave RUNNING (or recover from LOST).
            if task_info.status == BackgroundTaskStatus.LOST:
                task_info.status = BackgroundTaskStatus.RUNNING
                changed = True
            continue

        # Not alive - check for a published outcome before declaring LOST.
        try:
            stored_outcome = await store.fetch_outcome(qualified_session_key, task_info.id)
        except Exception:
            logger.debug(
                "Store fetch_outcome failed for task %s on session %s — leaving status unchanged.",
                task_info.id,
                qualified_session_key,
            )
            # Same as above: preserve current status on outage rather than writing LOST.
            continue

        if stored_outcome is not None:
            _finalize_task_from_info(task_info, stored_outcome, runtime)
            changed = True
        elif task_info.status != BackgroundTaskStatus.LOST:
            # Only write LOST on the first transition, not on every subsequent refresh.
            task_info.status = BackgroundTaskStatus.LOST
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
    - ``background_agents_wait_for_first_completion`` — Wait until the first specified task completes or the
      configured timeout expires. A timeout leaves the tasks running so the tool can be called again.
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
        wait_timeout_seconds: int = DEFAULT_BACKGROUND_AGENTS_WAIT_TIMEOUT_SECONDS,
        runtime_store: BackgroundTaskRuntimeStore | None = None,
    ) -> None:
        """Initialize the background agents provider.

        Args:
            agents: Collection of background agents available for delegation.
                Each agent must have a non-empty, unique name (case-insensitive).
                **Security:** each supplied agent should be vetted and trusted, since it will receive
                text input from the parent agent and its output is fed back into the parent's
                context - see the class-level security considerations for the exfiltration and
                prompt-injection risks of untrusted agents.

        Keyword Args:
            source_id: Unique source ID for serializable task state in session.
            instructions: Optional instruction override. May include ``{background_agents}``
                placeholder which will be replaced with the agent listing.
            wait_timeout_seconds: Maximum seconds the wait tool blocks for a task to complete.
                Must be a positive integer. Defaults to 300 seconds.
            runtime_store: Optional :class:`BackgroundTaskRuntimeStore` for cross-process task
                liveness and outcome delivery.  Defaults to
                :class:`_InMemoryBackgroundTaskRuntimeStore`, which reproduces single-process
                behaviour unchanged.  Supply a distributed implementation (e.g. Redis-backed)
                to support multi-replica deployments.

        Raises:
            ValueError: If agents is empty, an agent has no name, names are not unique, or
                wait_timeout_seconds is not a positive integer.
        """
        super().__init__(source_id)

        self._agents = _validate_and_build_agent_dict(agents)
        if (
            isinstance(wait_timeout_seconds, bool)
            or not isinstance(wait_timeout_seconds, int)
            or wait_timeout_seconds <= 0
        ):
            raise ValueError("wait_timeout_seconds must be a positive integer.")
        self._wait_timeout_seconds = wait_timeout_seconds

        # Build instructions with agent listing.
        base_instructions = instructions if instructions is not None else DEFAULT_BACKGROUND_AGENTS_INSTRUCTIONS
        agent_list_text = _build_agent_list_text(self._agents)
        self._instructions = base_instructions.replace("{background_agents}", agent_list_text)

        # Per-session runtime state (non-serializable), keyed by session_id.
        # Note: Runtime state (in-flight asyncio.Task objects, child AgentSession handles)
        # is inherently non-serializable and cannot survive process restarts. When a shared
        # runtime_store is configured, _refresh_task_state() consults it before marking
        # orphaned tasks as LOST, allowing results produced by another process to be delivered.
        self._runtime: dict[str, _RuntimeState] = {}

        # Store for cross-process task liveness and outcome delivery.
        self._runtime_store: BackgroundTaskRuntimeStore = (
            runtime_store if runtime_store is not None else _InMemoryBackgroundTaskRuntimeStore()
        )

    def _get_runtime(self, session: AgentSession) -> _RuntimeState:
        """Get or create runtime state for a session."""
        session_id = session.session_id
        runtime = self._runtime.get(session_id)

        if runtime is None or runtime.closed:
            runtime = _RuntimeState()
            self._runtime[session_id] = runtime

        return runtime

    async def release_session(
        self,
        session: AgentSession,
        *,
        cancel_running: bool = True,
        timeout: float | None = 30.0,
    ) -> None:
        """Release all runtime state for a session to prevent runtime leaks.

        Args:
            session: The agent session whose runtime state should be released.
            cancel_running: If True, cancel pending asyncio.Tasks safely.
            timeout: Maximum seconds to wait for tasks to finish cancellation.
                If None, wait indefinitely. The default is bounded so a buggy
                task cannot wedge host eviction or shutdown.
        """
        session_id = session.session_id
        qualified_session_key = session_id

        # Signal the owning process to cancel tasks.  This call is placed
        # *before* the early-return guard so that a non-owning process (which
        # has no local runtime entry) still propagates the cancel signal to
        # the process that actually owns the tasks.  Previously this function
        # silently returned early on non-owning processes (issue #8760 scenario 6).
        if cancel_running:
            try:
                await self._runtime_store.request_cancel(qualified_session_key)
            except Exception:
                logger.debug("Failed to send cancel request for session %s", session_id)

        runtime = self._runtime.get(session_id)

        if runtime is None or runtime.closed:
            return

        pending = [task for task in list(runtime.in_flight_tasks.values()) if not task.done()]

        if pending and not cancel_running:
            raise RuntimeError(f"Cannot release session {session_id}: {len(pending)} tasks still running.")

        runtime.closed = True

        try:
            if pending:
                await self._drain_runtime(
                    runtime,
                    cancel_running=cancel_running,
                    timeout=timeout,
                )
            else:
                completed = list(runtime.in_flight_tasks.values())
                if completed:
                    await asyncio.gather(*completed, return_exceptions=True)
        finally:
            runtime.in_flight_tasks.clear()
            runtime.background_sessions.clear()

            if self._runtime.get(session_id) is runtime:
                self._runtime.pop(session_id, None)

    async def _drain_runtime(
        self,
        runtime: _RuntimeState,
        *,
        cancel_running: bool,
        timeout: float | None,
    ) -> None:
        """Cancel and await tracked tasks, bounded by timeout."""
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + float(timeout)

        while True:
            tasks = list(runtime.in_flight_tasks.values())
            pending = [task for task in tasks if not task.done()]

            if not pending:
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                return

            if not cancel_running:
                raise RuntimeError(f"Cannot release session: {len(pending)} tasks still running.")

            for task in pending:
                if not task.done():
                    task.cancel()

            remaining = None
            if deadline is not None:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    logger.warning(
                        "Session release timed out before all tasks finished. Abandoning %s task(s).",
                        len(pending),
                    )
                    for task in pending:
                        if not task.done():
                            task.add_done_callback(_log_abandoned_background_task)
                    return

            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                not_done = [task for task in pending if not task.done()]
                logger.warning(
                    "Session release timed out waiting for %s task(s). They will be abandoned.",
                    len(not_done),
                )
                for task in not_done:
                    task.add_done_callback(_log_abandoned_background_task)
                return

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
        runtime_store = self._runtime_store
        qualified_session_key = session.session_id

        @tool(name="background_agents_start_task", approval_mode="never_require")
        async def background_agents_start_task(agent_name: str, input: str, description: str) -> str:
            """Start a background task on a named agent. Returns a confirmation with the task ID."""
            if runtime.closed:
                return "Error: Session is being released; cannot start a new background task."

            key = agent_name.lower()
            if key not in self._agents:
                available = ", ".join(a.name or "" for a in self._agents.values())
                return f"Error: No background agent found with name '{agent_name}'. Available agents: {available}"

            bg_agent = self._agents[key]
            task_id = provider_state.get("next_task_id", 1)

            sub_session = bg_agent.create_session()

            async_task = asyncio.create_task(
                _run_agent_with_renewal(
                    bg_agent.run(input, session=sub_session),
                    runtime_store,
                    qualified_session_key,
                    task_id,
                    ttl_seconds=DEFAULT_LEASE_TTL_SECONDS,
                )
            )
            try:
                runtime.track_task(task_id, async_task)
            except RuntimeError as exc:
                async_task.cancel()
                return f"Error: {exc}"

            # Acquire the lease before returning so other processes see the
            # task as alive as soon as this turn's session state is saved.
            try:
                await runtime_store.acquire(qualified_session_key, task_id, ttl_seconds=DEFAULT_LEASE_TTL_SECONDS)
            except Exception:
                logger.debug("Failed to acquire lease for task %s", task_id)

            # Guard against a release_session that closed the runtime while
            # the acquire awaited above.  If the session is now closed, cancel
            # the task and clean up before reporting an error.
            if runtime.closed:
                async_task.cancel()
                runtime.in_flight_tasks.pop(task_id, None)
                return "Error: Session was released while starting the background task."

            # Attach a done-callback so the outcome is published to the store
            # the instant the task settles, even between turns or on a different process.
            async_task.add_done_callback(
                _make_done_callback(runtime_store, qualified_session_key, task_id, agent_name, description, runtime)
            )

            runtime.background_sessions[task_id] = sub_session

            provider_state["next_task_id"] = task_id + 1

            task_info = BackgroundTaskInfo(
                id=task_id,
                agent_name=agent_name,
                description=description,
            )
            tasks = _get_tasks(provider_state)
            tasks.append(task_info)
            _save_tasks(provider_state, tasks)

            _save_provider_state(session, provider_state, source_id=source_id)
            return f"Background task {task_id} started on agent '{agent_name}'."

        # Note: background_agents_start_task previously required `_invoke_sync_on_event_loop = True`
        # because it was a synchronous function that spawned asyncio Tasks. Now that it is natively `async def`,
        # the tool runner inherently executes it on the event loop (confirmed redundant: see `_tools.py`
        # line 824 where `inspect.iscoroutinefunction` triggers the exact same loop branch).

        @tool(name="background_agents_wait_for_first_completion", approval_mode="never_require")
        async def background_agents_wait_for_first_completion(task_ids: list[int]) -> str:
            """Wait until the first of the specified tasks completes or the configured timeout expires.

            Returns the completed task's ID. On timeout, the tasks remain running and this tool
            can be called again to continue waiting.
            """
            if runtime.closed:
                return "Error: Session is being released; cannot wait for background tasks."

            if not task_ids:
                return "Error: No task IDs provided."

            start_time = time.time()

            while time.time() - start_time < self._wait_timeout_seconds:
                tasks = await _refresh_task_state(
                    session,
                    provider_state,
                    runtime,
                    runtime_store,
                    qualified_session_key,
                    source_id=source_id,
                )

                for tid in task_ids:
                    t_info = next((t for t in tasks if t.id == tid), None)
                    if t_info is not None and t_info.status != BackgroundTaskStatus.RUNNING:
                        return f"Task {tid} finished with status: {t_info.status.value}."

                running = [t for t in tasks if t.id in task_ids and t.status == BackgroundTaskStatus.RUNNING]
                if not running:
                    return "Error: None of the specified task IDs correspond to running tasks."

                local_waitables = [runtime.in_flight_tasks[t.id] for t in running if t.id in runtime.in_flight_tasks]

                if local_waitables:
                    await asyncio.wait(local_waitables, timeout=1.0, return_when=asyncio.FIRST_COMPLETED)
                else:
                    await asyncio.sleep(1.0)

            return (
                f"No background task completed within {self._wait_timeout_seconds} seconds. "
                "The tasks are still running; call this tool again if you wish to continue waiting."
            )

        @tool(name="background_agents_get_task_results", approval_mode="never_require")
        async def background_agents_get_task_results(task_id: int) -> str:
            """Get the text output of a background task by its ID."""
            tasks = await _refresh_task_state(
                session,
                provider_state,
                runtime,
                runtime_store,
                qualified_session_key,
                source_id=source_id,
            )
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
        async def background_agents_get_all_tasks() -> str:
            """List all background tasks with their IDs, statuses, agent names, and descriptions."""
            tasks = await _refresh_task_state(
                session,
                provider_state,
                runtime,
                runtime_store,
                qualified_session_key,
                source_id=source_id,
            )

            if not tasks:
                return "No tasks."

            lines = ["Tasks:"]
            for t in tasks:
                lines.append(f"- Task {t.id} [{t.status.value}] ({t.agent_name}): {t.description}")
            return "\n".join(lines)

        @tool(name="background_agents_continue_task", approval_mode="never_require")
        async def background_agents_continue_task(task_id: int, text: str) -> str:
            """Send follow-up input to a completed or failed task to resume its work."""
            if runtime.closed:
                return "Error: Session is being released; cannot continue a background task."

            tasks = await _refresh_task_state(
                session,
                provider_state,
                runtime,
                runtime_store,
                qualified_session_key,
                source_id=source_id,
            )
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
                return (
                    f"Error: Task {task_id} was completed on another instance; "
                    "continue is not available cross-process in this release."
                )

            bg_agent = self._agents[key]

            async_task = asyncio.create_task(
                _run_agent_with_renewal(
                    bg_agent.run(text, session=sub_session),
                    runtime_store,
                    qualified_session_key,
                    task_id,
                    ttl_seconds=DEFAULT_LEASE_TTL_SECONDS,
                )
            )
            try:
                runtime.track_task(task_id, async_task)
            except RuntimeError as exc:
                async_task.cancel()
                return f"Error: {exc}"

            try:
                await runtime_store.acquire(qualified_session_key, task_id, ttl_seconds=DEFAULT_LEASE_TTL_SECONDS)
            except Exception:
                logger.debug("Failed to acquire lease for continued task %s", task_id)

            # Guard against release_session closing the runtime during the acquire await.
            if runtime.closed:
                async_task.cancel()
                runtime.in_flight_tasks.pop(task_id, None)
                return "Error: Session was released while continuing the background task."

            async_task.add_done_callback(
                _make_done_callback(
                    runtime_store,
                    qualified_session_key,
                    task_id,
                    task_info.agent_name,
                    task_info.description,
                    runtime,
                )
            )

            task_info.status = BackgroundTaskStatus.RUNNING
            task_info.result_text = None
            task_info.error_text = None
            _save_tasks(provider_state, tasks)

            _save_provider_state(session, provider_state, source_id=source_id)
            return f"Task {task_id} continued with new input."

        @tool(name="background_agents_clear_completed_task", approval_mode="never_require")
        async def background_agents_clear_completed_task(task_id: int) -> str:
            """Remove a completed or failed task and release its session to free memory."""
            if runtime.closed:
                return "Error: Session is being released; cannot clear tasks."

            tasks = await _refresh_task_state(
                session,
                provider_state,
                runtime,
                runtime_store,
                qualified_session_key,
                source_id=source_id,
            )
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
        tasks = await _refresh_task_state(
            session,
            provider_state,
            runtime,
            runtime_store,
            qualified_session_key,
            source_id=source_id,
        )
        if tasks:
            status_lines = ["### Current background tasks"]
            for t in tasks:
                status_lines.append(f"- Task {t.id} [{t.status.value}] ({t.agent_name}): {t.description}")
            context.extend_messages(
                self.source_id,
                [Message(role="user", contents=["\n".join(status_lines)])],
            )
