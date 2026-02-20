# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import builtins
import sys
import traceback as _traceback
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, Literal, cast

from ._typing_utils import deserialize_type, serialize_type

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore[import] # pragma: no cover

DataT = TypeVar("DataT", default=Any)


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


class WorkflowRunState(str, Enum):
    """Run-level state of a workflow execution."""

    STARTED = "STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    IN_PROGRESS_PENDING_REQUESTS = "IN_PROGRESS_PENDING_REQUESTS"
    IDLE = "IDLE"
    IDLE_WITH_PENDING_REQUESTS = "IDLE_WITH_PENDING_REQUESTS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


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
    ) -> WorkflowErrorDetails:
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


# Type discriminator for workflow events.
# Includes both framework lifecycle types and well-known orchestration types.
WorkflowEventType = Literal[
    # Lifecycle events (workflow-level)
    "started",  # Workflow run began
    "status",  # Workflow state changed (use .state)
    "failed",  # Workflow terminated with error (use .details)
    # Data events
    "output",  # Executor yielded final output (use .executor_id, .data)
    "data",  # Executor emitted data during execution (use .executor_id, .data)
    # Request events (human-in-the-loop)
    "request_info",  # Executor requests external info (use .request_id, .source_executor_id)
    # Diagnostic events (warnings/errors from user code)
    "warning",  # Warning from user code (use .data as str)
    "error",  # Error from user code, non-fatal (use .data as Exception)
    # Iteration events (supersteps)
    "superstep_started",  # Superstep began (use .iteration)
    "superstep_completed",  # Superstep ended (use .iteration)
    # Executor lifecycle events
    "executor_invoked",  # Executor handler was called (use .executor_id, .data)
    "executor_completed",  # Executor handler completed (use .executor_id, .data)
    "executor_failed",  # Executor handler raised error (use .executor_id, .details)
    # Orchestration event types (use .data for typed payload)
    "group_chat",  # Group chat orchestrator events (use .data as GroupChatRequestSentEvent | GroupChatResponseReceivedEvent)  # noqa: E501
    "handoff_sent",  # Handoff routing events (use .data as HandoffSentEvent)
    "magentic_orchestrator",  # Magentic orchestrator events (use .data as MagenticOrchestratorEvent)
]


class WorkflowEvent(Generic[DataT]):
    """Unified event for all workflow emissions.

    This single generic class handles all workflow events through a `type` discriminator,
    following the same pattern as the `Content` class.

    Use factory methods for convenient construction:

    - `WorkflowEvent.started()` - workflow run began
    - `WorkflowEvent.status(state)` - workflow state changed
    - `WorkflowEvent.failed(details)` - workflow terminated with error
    - `WorkflowEvent.warning(message)` - warning from user code
    - `WorkflowEvent.error(exception)` - error from user code
    - `WorkflowEvent.output(executor_id, data)` - executor yielded final output
    - `WorkflowEvent.data(executor_id, data)` - executor emitted data (e.g., AgentResponse)
    - `WorkflowEvent.request_info(...)` - executor requests external info
    - `WorkflowEvent.superstep_started(iteration)` - superstep began
    - `WorkflowEvent.superstep_completed(iteration)` - superstep ended
    - `WorkflowEvent.executor_invoked(executor_id)` - executor handler called
    - `WorkflowEvent.executor_completed(executor_id)` - executor handler completed
    - `WorkflowEvent.executor_failed(executor_id, details)` - executor handler failed

    The generic parameter DataT represents the type of the event's data payload:
    - Lifecycle events: `WorkflowEvent[None]` (data is None)
    - Data events: `WorkflowEvent[DataT]` where DataT is the payload type (e.g., AgentResponse)

    Examples:
        .. code-block:: python

            # Create events via factory methods
            started = WorkflowEvent.started()
            status = WorkflowEvent.status(WorkflowRunState.IN_PROGRESS)
            output = WorkflowEvent.output("agent1", result_data)

            # Emit typed data from executor
            event: WorkflowEvent[AgentResponse] = WorkflowEvent.data("agent1", response)
            data: AgentResponse = event.data  # Type-safe access

            # Check event type
            if event.type == "status":
                print(f"State: {event.state}")
            elif event.type == "output":
                print(f"Output from {event.executor_id}: {event.data}")
            elif event.type == "data":
                if isinstance(event.data, AgentResponse):
                    print(f"Agent response: {event.data.text}")
    """

    type: WorkflowEventType
    data: DataT

    def __init__(
        self,
        type: WorkflowEventType,
        data: DataT | None = None,
        *,
        # Event context fields
        origin: WorkflowEventSource | None = None,
        # STATUS event fields
        state: WorkflowRunState | None = None,
        # FAILED event fields
        details: WorkflowErrorDetails | None = None,
        # OUTPUT/DATA event fields
        executor_id: str | None = None,
        # REQUEST_INFO event fields
        request_id: str | None = None,
        source_executor_id: str | None = None,
        request_type: builtins.type[Any] | None = None,
        response_type: builtins.type[Any] | None = None,
        # SUPERSTEP event fields
        iteration: int | None = None,
    ) -> None:
        """Initialize the workflow event.

        Prefer using factory methods like `WorkflowEvent.started()` instead of __init__ directly.
        """
        self.type = type
        self.data = data  # type: ignore[assignment]
        self.origin = origin if origin is not None else _current_event_origin()

        # Event-specific fields
        self.state = state
        self.details = details
        self.executor_id = executor_id
        self._request_id = request_id
        self._source_executor_id = source_executor_id
        self._request_type = request_type
        self._response_type = response_type
        self.iteration = iteration

    def __repr__(self) -> str:
        """Return a string representation of the workflow event."""
        parts = [f"type={self.type!r}"]
        if self.state is not None:
            parts.append(f"state={self.state.value}")
        if self.executor_id is not None:
            parts.append(f"executor_id={self.executor_id!r}")
        if self.iteration is not None:
            parts.append(f"iteration={self.iteration}")
        if self._request_id is not None:
            parts.append(f"request_id={self._request_id!r}")
        if self.data is not None:
            parts.append(f"data={self.data!r}")
        return f"WorkflowEvent({', '.join(parts)})"  # pragma: no cover

    # ==========================================================================
    # Factory methods
    # ==========================================================================

    @classmethod
    def started(cls, data: DataT | None = None) -> WorkflowEvent[DataT]:
        """Create a 'started' event when a workflow run begins."""
        return cls("started", data=data)

    @classmethod
    def status(cls, state: WorkflowRunState, data: DataT | None = None) -> WorkflowEvent[DataT]:
        """Create a 'status' event for workflow state transitions."""
        return cls("status", data=data, state=state)

    @classmethod
    def failed(cls, details: WorkflowErrorDetails, data: DataT | None = None) -> WorkflowEvent[DataT]:
        """Create a 'failed' event when a workflow terminates with error."""
        return cls("failed", data=data, details=details)

    @classmethod
    def warning(cls, message: str) -> WorkflowEvent[str]:
        """Create a 'warning' event from user code."""
        return WorkflowEvent("warning", data=message)

    @classmethod
    def error(cls, exception: Exception) -> WorkflowEvent[Exception]:
        """Create an 'error' event from user code."""
        return WorkflowEvent("error", data=exception)

    @classmethod
    def output(cls, executor_id: str, data: DataT) -> WorkflowEvent[DataT]:
        """Create an 'output' event when an executor yields final output."""
        return cls("output", executor_id=executor_id, data=data)

    @classmethod
    def emit(cls, executor_id: str, data: DataT) -> WorkflowEvent[DataT]:
        """Create a 'data' event when an executor emits data during execution.

        This is the primary method for executors to emit typed data
        (e.g., AgentResponse, AgentResponseUpdate, custom data).
        """
        return cls("data", executor_id=executor_id, data=data)

    @classmethod
    def request_info(
        cls,
        request_id: str,
        source_executor_id: str,
        request_data: DataT,
        response_type: builtins.type[Any],
    ) -> WorkflowEvent[DataT]:
        """Create a 'request_info' event when an executor requests external information."""
        return cls(
            "request_info",
            data=request_data,
            request_id=request_id,
            source_executor_id=source_executor_id,
            request_type=type(request_data),
            response_type=response_type,
        )

    @classmethod
    def superstep_started(cls, iteration: int, data: DataT | None = None) -> WorkflowEvent[DataT]:
        """Create a 'superstep_started' event when a superstep begins."""
        return cls("superstep_started", iteration=iteration, data=data)

    @classmethod
    def superstep_completed(cls, iteration: int, data: DataT | None = None) -> WorkflowEvent[DataT]:
        """Create a 'superstep_completed' event when a superstep ends."""
        return cls("superstep_completed", iteration=iteration, data=data)

    @classmethod
    def executor_invoked(cls, executor_id: str, data: DataT | None = None) -> WorkflowEvent[DataT]:
        """Create an 'executor_invoked' event when an executor handler is called."""
        return cls("executor_invoked", executor_id=executor_id, data=data)

    @classmethod
    def executor_completed(cls, executor_id: str, data: DataT | None = None) -> WorkflowEvent[DataT]:
        """Create an 'executor_completed' event when an executor handler completes."""
        return cls("executor_completed", executor_id=executor_id, data=data)

    @classmethod
    def executor_failed(cls, executor_id: str, details: WorkflowErrorDetails) -> WorkflowEvent[WorkflowErrorDetails]:
        """Create an 'executor_failed' event when an executor handler raises an error."""
        return WorkflowEvent("executor_failed", executor_id=executor_id, data=details, details=details)

    # ==========================================================================
    # Property for type-safe access
    # ==========================================================================

    @property
    def request_id(self) -> str:
        """Get request_id for request_info events.

        Returns:
            The request ID as a non-None string.

        Raises:
            RuntimeError: If called on an event that is not a request_info event,
                or if the event is malformed (request_info without request_id).
        """
        if self.type != "request_info" or self._request_id is None:
            raise RuntimeError(f"request_id is only available for request_info events, got type={self.type!r}")
        return self._request_id

    @property
    def source_executor_id(self) -> str:
        """Get source_executor_id for request_info events.

        Returns:
            The source executor ID as a non-None string.

        Raises:
            RuntimeError: If called on an event that is not a request_info event,
                or if the event is malformed (request_info without source_executor_id).
        """
        if self.type != "request_info" or self._source_executor_id is None:
            raise RuntimeError(f"source_executor_id is only available for request_info events, got type={self.type!r}")
        return self._source_executor_id

    @property
    def request_type(self) -> builtins.type[Any]:
        """Get request_type for request_info events.

        Returns:
            The request data type as a non-None type object.

        Raises:
            RuntimeError: If called on an event that is not a request_info event,
                or if the event is malformed (request_info without request_type).
        """
        if self.type != "request_info" or self._request_type is None:
            raise RuntimeError(f"request_type is only available for request_info events, got type={self.type!r}")
        return self._request_type

    @property
    def response_type(self) -> builtins.type[Any]:
        """Get response_type for request_info events.

        Returns:
            The response data type as a non-None type object.

        Raises:
            RuntimeError: If called on an event that is not a request_info event,
                or if the event is malformed (request_info without response_type).
        """
        if self.type != "request_info" or self._response_type is None:
            raise RuntimeError(f"response_type is only available for request_info events, got type={self.type!r}")
        return self._response_type

    # ==========================================================================
    # Serialization methods (primarily for REQUEST_INFO events)
    # ==========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Currently only implemented for 'request_info' events for checkpoint storage.
        """
        if self.type != "request_info":
            raise ValueError(f"to_dict() only supported for 'request_info' events, got '{self.type}'")
        return {
            "type": self.type,
            "data": self.data,
            "request_id": self._request_id,
            "source_executor_id": self._source_executor_id,
            "request_type": serialize_type(self._request_type) if self._request_type else None,
            "response_type": serialize_type(self._response_type) if self._response_type else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowEvent[Any]:
        """Create a REQUEST_INFO event from a dictionary."""
        for prop in ["data", "request_id", "source_executor_id", "request_type", "response_type"]:
            if prop not in data:
                raise KeyError(f"Missing '{prop}' field in WorkflowEvent dictionary.")

        request_data = data["data"]
        request_type = deserialize_type(data["request_type"])

        if request_type is not type(request_data):
            raise TypeError(
                "Mismatch between deserialized request_data type and request_type field in WorkflowEvent dictionary."
            )

        return cls.request_info(
            request_id=data["request_id"],
            source_executor_id=data["source_executor_id"],
            request_data=cast(Any, request_data),  # type: ignore
            response_type=deserialize_type(data["response_type"]),
        )
