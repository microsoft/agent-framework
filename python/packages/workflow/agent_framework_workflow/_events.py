# Copyright (c) Microsoft. All rights reserved.

import traceback as _traceback
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from agent_framework import AgentRunResponse, AgentRunResponseUpdate

if TYPE_CHECKING:
    from ._executor import RequestInfoMessage


class WorkflowEvent:
    """Base class for workflow events."""

    def __init__(self, data: Any | None = None):
        """Initialize the workflow event with optional data."""
        self.data = data

    def __repr__(self) -> str:
        """Return a string representation of the workflow event."""
        return f"{self.__class__.__name__}(data={self.data if self.data is not None else 'None'})"


class WorkflowStartedEvent(WorkflowEvent):
    """Event triggered when a workflow starts."""

    ...


class WorkflowCompletedEvent(WorkflowEvent):
    """Event triggered when a workflow completes.

    Backward compatible with existing usages that only pass `data`.
    Can optionally flag error completion with details when appropriate.
    """

    def __init__(
        self,
        data: Any | None = None,
        *,
        is_error: bool = False,
        error_details: "WorkflowErrorDetails | None" = None,
    ) -> None:
        super().__init__(data)
        self.is_error = is_error
        self.error_details = error_details

    def __repr__(self) -> str:  # pragma: no cover - representation only
        if self.is_error:
            return f"{self.__class__.__name__}(data={self.data!r}, is_error=True, error_details={self.error_details})"
        return f"{self.__class__.__name__}(data={self.data!r})"


class WorkflowWarningEvent(WorkflowEvent):
    """Event triggered when a warning occurs in the workflow."""

    def __init__(self, data: str):
        """Initialize the workflow warning event with optional data and warning message."""
        super().__init__(data)

    def __repr__(self) -> str:
        """Return a string representation of the workflow warning event."""
        return f"{self.__class__.__name__}(message={self.data})"


class WorkflowErrorEvent(WorkflowEvent):
    """Event triggered when an error occurs in the workflow."""

    def __init__(self, data: Exception):
        """Initialize the workflow error event with optional data and error message."""
        super().__init__(data)

    def __repr__(self) -> str:
        """Return a string representation of the workflow error event."""
        return f"{self.__class__.__name__}(exception={self.data})"


class WorkflowRunState(str, Enum):
    """Run-level state of a workflow execution."""

    STARTED = "STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowStatusEvent(WorkflowEvent):
    """Event indicating a transition in the workflow run state."""

    def __init__(self, state: WorkflowRunState, data: Any | None = None):
        super().__init__(data)
        self.state = state

    def __repr__(self) -> str:  # pragma: no cover - representation only
        return f"{self.__class__.__name__}(state={self.state}, data={self.data!r})"


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
    """Terminal failure event for a workflow run."""

    def __init__(self, details: WorkflowErrorDetails, data: Any | None = None):
        super().__init__(data)
        self.details = details

    def __repr__(self) -> str:  # pragma: no cover - representation only
        return f"{self.__class__.__name__}(details={self.details}, data={self.data!r})"


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


class ExecutorEvent(WorkflowEvent):
    """Base class for executor events."""

    def __init__(self, executor_id: str, data: Any | None = None):
        """Initialize the executor event with an executor ID and optional data."""
        super().__init__(data)
        self.executor_id = executor_id

    def __repr__(self) -> str:
        """Return a string representation of the executor event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, data={self.data})"


class ExecutorInvokeEvent(ExecutorEvent):
    """Event triggered when an executor handler is invoked."""

    def __repr__(self) -> str:
        """Return a string representation of the executor handler invoke event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id})"


class ExecutorCompletedEvent(ExecutorEvent):
    """Event triggered when an executor handler is completed."""

    def __repr__(self) -> str:
        """Return a string representation of the executor handler complete event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id})"


class ExecutorFailedEvent(ExecutorEvent):
    """Event triggered when an executor handler raises an error."""

    def __init__(self, executor_id: str, details: WorkflowErrorDetails):
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
