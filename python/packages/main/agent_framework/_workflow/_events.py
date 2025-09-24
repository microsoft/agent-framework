# Copyright (c) Microsoft. All rights reserved.

import traceback as _traceback
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeAlias

from agent_framework import AgentRunResponse, AgentRunResponseUpdate

if TYPE_CHECKING:
    from ._executor import RequestInfoMessage


class WorkflowEventSource(str, Enum):
    """Identifies whether a workflow event came from the framework or an executor.

    Use `FRAMEWORK` for events emitted by built-in orchestration paths—even when the
    code that raises them lives in runner-related modules—and `EXECUTOR` for events
    surfaced by developer-provided executor implementations.
    """

    FRAMEWORK = "FRAMEWORK"  # Framework-owned orchestration, regardless of module location
    EXECUTOR = "EXECUTOR"  # User-supplied executor code and callbacks


_event_origin_context: ContextVar[WorkflowEventSource] = ContextVar(
    "workflow_event_origin", default=WorkflowEventSource.EXECUTOR
)


def _current_event_origin() -> WorkflowEventSource:
    """Return the origin to associate with newly created workflow events."""
    return _event_origin_context.get()


@contextmanager
def _framework_event_origin() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Temporarily mark subsequently created events as originating from the framework (internal)."""
    token = _event_origin_context.set(WorkflowEventSource.FRAMEWORK)
    try:
        yield
    finally:
        _event_origin_context.reset(token)


class WorkflowEvent:
    """Base class for workflow events."""

    def __init__(self, data: Any | None = None):
        """Initialize the workflow event with optional data."""
        self.data = data
        self.origin = _current_event_origin()

    def __repr__(self) -> str:
        """Return a string representation of the workflow event."""
        data_repr = self.data if self.data is not None else "None"
        return f"{self.__class__.__name__}(origin={self.origin}, data={data_repr})"


class WorkflowStartedEvent(WorkflowEvent):
    """Built-in lifecycle event emitted when a workflow run begins."""

    ...


class WorkflowWarningEvent(WorkflowEvent):
    """Executor-origin event signaling a warning surfaced by user code."""

    def __init__(self, data: str):
        """Initialize the workflow warning event with optional data and warning message."""
        super().__init__(data)

    def __repr__(self) -> str:
        """Return a string representation of the workflow warning event."""
        return f"{self.__class__.__name__}(message={self.data}, origin={self.origin})"


class WorkflowErrorEvent(WorkflowEvent):
    """Executor-origin event signaling an error surfaced by user code."""

    def __init__(self, data: Exception):
        """Initialize the workflow error event with optional data and error message."""
        super().__init__(data)

    def __repr__(self) -> str:
        """Return a string representation of the workflow error event."""
        return f"{self.__class__.__name__}(exception={self.data}, origin={self.origin})"


class WorkflowRunState(str, Enum):
    """Run-level state of a workflow execution.

    Semantics:
      - STARTED: Run has been initiated and the workflow context has been created.
        This is an initial state before any meaningful work is performed. In this
        codebase we emit a dedicated `WorkflowStartedEvent` for telemetry, and
        typically advance the status directly to `IN_PROGRESS`. Consumers may
        still rely on `STARTED` for state machines that need an explicit pre-work
        phase.

      - IN_PROGRESS: The workflow is actively executing (e.g., the initial
        message has been delivered to the start executor or a superstep is
        running). This status is emitted at the beginning of a run and can be
        followed by other statuses as the run progresses.

      - IN_PROGRESS_PENDING_REQUESTS: Active execution while one or more
        request-for-information operations are outstanding. New work may still
        be scheduled while requests are in flight.

      - IDLE: The workflow is quiescent with no outstanding requests and no more
        work to do. This is the normal terminal state for workflows that have
        finished executing, potentially having produced outputs along the way.

      - IDLE_WITH_PENDING_REQUESTS: The workflow is paused awaiting external
        input (e.g., emitted a `RequestInfoEvent`). This is a non-terminal
        state; the workflow can resume when responses are supplied.

      - FAILED: Terminal state indicating an error surfaced. Accompanied by a
        `WorkflowFailedEvent` with structured error details.

      - CANCELLED: Terminal state indicating the run was cancelled by a caller
        or orchestrator. Not currently emitted by default runner paths but
        included for integrators/orchestrators that support cancellation.
    """

    STARTED = "STARTED"  # Explicit pre-work phase (rarely emitted as status; see note above)
    IN_PROGRESS = "IN_PROGRESS"  # Active execution is underway
    IN_PROGRESS_PENDING_REQUESTS = "IN_PROGRESS_PENDING_REQUESTS"  # Active execution with outstanding requests
    IDLE = "IDLE"  # No active work and no outstanding requests
    IDLE_WITH_PENDING_REQUESTS = "IDLE_WITH_PENDING_REQUESTS"  # Paused awaiting external responses
    FAILED = "FAILED"  # Finished with an error
    CANCELLED = "CANCELLED"  # Finished due to cancellation


class WorkflowStatusEvent(WorkflowEvent):
    """Built-in lifecycle event emitted for workflow run state transitions."""

    def __init__(
        self,
        state: WorkflowRunState,
        data: Any | None = None,
    ):
        """Initialize the workflow status event with a new state and optional data.

        Args:
            state: The new state of the workflow run.
            data: Optional additional data associated with the state change.
        """
        super().__init__(data)
        self.state = state

    def __repr__(self) -> str:  # pragma: no cover - representation only
        return f"{self.__class__.__name__}(state={self.state}, data={self.data!r}, origin={self.origin})"


@dataclass
class WorkflowErrorDetails:
    """Structured error information to surface in error events/results."""

    error_type: str
    message: str
    traceback: str | None = None
    executor_id: str | None = None
    extra: dict[str, Any] | None = None

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        *,
        executor_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> "WorkflowErrorDetails":
        tb = None
        try:
            tb = "".join(_traceback.format_exception(type(exc), exc, exc.__traceback__))
        except Exception:
            tb = None
        return cls(
            error_type=exc.__class__.__name__,
            message=str(exc),
            traceback=tb,
            executor_id=executor_id,
            extra=extra,
        )


class WorkflowFailedEvent(WorkflowEvent):
    """Built-in lifecycle event emitted when a workflow run terminates with an error."""

    def __init__(
        self,
        details: WorkflowErrorDetails,
        data: Any | None = None,
    ):
        super().__init__(data)
        self.details = details

    def __repr__(self) -> str:  # pragma: no cover - representation only
        return f"{self.__class__.__name__}(details={self.details}, data={self.data!r}, origin={self.origin})"


class RequestInfoEvent(WorkflowEvent):
    """Event triggered when a workflow executor requests external information."""

    def __init__(
        self,
        request_id: str,
        source_executor_id: str,
        request_type: type,
        request_data: "RequestInfoMessage",
    ):
        """Initialize the request info event.

        Args:
            request_id: Unique identifier for the request.
            source_executor_id: ID of the executor that made the request.
            request_type: Type of the request (e.g., a specific data type).
            request_data: The data associated with the request.
        """
        super().__init__(request_data)
        self.request_id = request_id
        self.source_executor_id = source_executor_id
        self.request_type = request_type

    def __repr__(self) -> str:
        """Return a string representation of the request info event."""
        return (
            f"{self.__class__.__name__}("
            f"request_id={self.request_id}, "
            f"source_executor_id={self.source_executor_id}, "
            f"request_type={self.request_type.__name__}, "
            f"data={self.data})"
        )


class WorkflowOutputEvent(WorkflowEvent):
    """Event triggered when a workflow executor yields output."""

    def __init__(
        self,
        data: Any,
        source_executor_id: str,
    ):
        """Initialize the workflow output event.

        Args:
            data: The output yielded by the executor.
            source_executor_id: ID of the executor that yielded the output.
        """
        super().__init__(data)
        self.source_executor_id = source_executor_id

    def __repr__(self) -> str:
        """Return a string representation of the workflow output event."""
        return f"{self.__class__.__name__}(data={self.data}, source_executor_id={self.source_executor_id})"


class ExecutorEvent(WorkflowEvent):
    """Base class for executor events."""

    def __init__(self, executor_id: str, data: Any | None = None):
        """Initialize the executor event with an executor ID and optional data."""
        super().__init__(data)
        self.executor_id = executor_id

    def __repr__(self) -> str:
        """Return a string representation of the executor event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, data={self.data})"


class ExecutorInvokedEvent(ExecutorEvent):
    """Event triggered when an executor handler is invoked."""

    def __repr__(self) -> str:
        """Return a string representation of the executor handler invoke event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, data={self.data})"


class ExecutorCompletedEvent(ExecutorEvent):
    """Event triggered when an executor handler is completed."""

    def __repr__(self) -> str:
        """Return a string representation of the executor handler complete event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, data={self.data})"


class ExecutorFailedEvent(ExecutorEvent):
    """Event triggered when an executor handler raises an error."""

    def __init__(
        self,
        executor_id: str,
        details: WorkflowErrorDetails,
    ):
        super().__init__(executor_id, details)
        self.details = details

    def __repr__(self) -> str:  # pragma: no cover - representation only
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, details={self.details})"


class AgentRunUpdateEvent(ExecutorEvent):
    """Event triggered when an agent is streaming messages."""

    def __init__(self, executor_id: str, data: AgentRunResponseUpdate | None = None):
        """Initialize the agent streaming event."""
        super().__init__(executor_id, data)

    def __repr__(self) -> str:
        """Return a string representation of the agent streaming event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, messages={self.data})"


class AgentRunEvent(ExecutorEvent):
    """Event triggered when an agent run is completed."""

    def __init__(self, executor_id: str, data: AgentRunResponse | None = None):
        """Initialize the agent run event."""
        super().__init__(executor_id, data)

    def __repr__(self) -> str:
        """Return a string representation of the agent run event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, data={self.data})"


WorkflowLifecycleEvent: TypeAlias = WorkflowStartedEvent | WorkflowStatusEvent | WorkflowFailedEvent
