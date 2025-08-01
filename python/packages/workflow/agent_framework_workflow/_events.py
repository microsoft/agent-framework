# Copyright (c) Microsoft. All rights reserved.

from typing import Any

from agent_framework import AgentRunResponse, AgentRunResponseUpdate


class WorkflowEvent:
    """Base class for workflow events."""

    def __init__(self, data: Any | None = None):
        """Initialize the workflow event with optional data."""
        self.data = data

    def __repr__(self):
        """Return a string representation of the workflow event."""
        return f"{self.__class__.__name__}(data={self.data if self.data is not None else 'None'})"


class WorkflowStartedEvent(WorkflowEvent):
    """Event triggered when a workflow starts."""

    ...


class WorkflowCompletedEvent(WorkflowEvent):
    """Event triggered when a workflow completes."""

    ...


class WorkflowWarningEvent(WorkflowEvent):
    """Event triggered when a warning occurs in the workflow."""

    def __init__(self, data: str):
        """Initialize the workflow warning event with optional data and warning message."""
        super().__init__(data)

    def __repr__(self):
        """Return a string representation of the workflow warning event."""
        return f"{self.__class__.__name__}(message={self.data})"


class WorkflowErrorEvent(WorkflowEvent):
    """Event triggered when an error occurs in the workflow."""

    def __init__(self, data: Exception):
        """Initialize the workflow error event with optional data and error message."""
        super().__init__(data)

    def __repr__(self):
        """Return a string representation of the workflow error event."""
        return f"{self.__class__.__name__}(exception={self.data})"


class ExecutorEvent(WorkflowEvent):
    """Base class for executor events."""

    def __init__(self, executor_id: str, data: Any | None = None):
        """Initialize the executor event with an executor ID and optional data."""
        super().__init__(data)
        self.executor_id = executor_id

    def __repr__(self):
        """Return a string representation of the executor event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, data={self.data})"


class HumanInTheLoopEvent(ExecutorEvent):
    """Event triggered when human intervention is required in the workflow."""

    def __init__(self, executor_id: str, data: Any | None = None, **kwargs: Any):
        """Initialize the human-in-the-loop event with optional data."""
        super().__init__(executor_id, data)
        self.kwargs = kwargs

    def __repr__(self):
        """Return a string representation of the human-in-the-loop event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, data={self.data}, kwargs={self.kwargs})"


class ExecutorInvokeEvent(ExecutorEvent):
    """Event triggered when an executor handler is invoked."""

    def __repr__(self):
        """Return a string representation of the executor handler invoke event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id})"


class ExecutorCompleteEvent(ExecutorEvent):
    """Event triggered when an executor handler is completed."""

    def __repr__(self):
        """Return a string representation of the executor handler complete event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id})"


class AgentRunStreamingEvent(ExecutorEvent):
    """Event triggered when an agent is streaming messages."""

    def __init__(self, executor_id: str, data: AgentRunResponseUpdate | None = None):
        """Initialize the agent streaming event."""
        super().__init__(executor_id, data)

    def __repr__(self):
        """Return a string representation of the agent streaming event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, messages={self.data})"


class AgentRunEvent(ExecutorEvent):
    """Event triggered when an agent run is completed."""

    def __init__(self, executor_id: str, data: AgentRunResponse | None = None):
        """Initialize the agent run event."""
        super().__init__(executor_id, data)

    def __repr__(self):
        """Return a string representation of the agent run event."""
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, data={self.data})"
