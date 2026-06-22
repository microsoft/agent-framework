# Copyright (c) Microsoft. All rights reserved.

"""Protocol definition for workflow orchestration contexts.

This module defines the ``WorkflowOrchestrationContext`` protocol that abstracts
the differences between Azure Functions' ``DurableOrchestrationContext`` and the
standalone ``durabletask.task.OrchestrationContext``.  The shared workflow
orchestrator (:func:`run_workflow_orchestrator`) programs against this protocol
so that the same orchestration logic works on any host.

Each host provides a thin adapter that maps its native context to this protocol:

- ``DurableTaskWorkflowContext`` (this package) — wraps ``OrchestrationContext``
- ``AzureFunctionsWorkflowContext`` (azurefunctions package) — wraps
  ``DurableOrchestrationContext``
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class WorkflowOrchestrationContext(Protocol):
    """Host-agnostic interface for workflow orchestration primitives.

    All methods that return yieldable tasks return ``Any`` because the concrete
    task types differ between hosting SDKs (``TaskBase`` for Azure Functions,
    ``Task[T]`` for durabletask).  The generator-based orchestrator simply
    yields these opaque objects back to the hosting framework.
    """

    @property
    def instance_id(self) -> str:
        """The unique ID of the current orchestration instance."""
        ...

    @property
    def is_replaying(self) -> bool:
        """Whether the orchestrator is replaying previously-recorded history.

        Side effects intended to be observed live exactly once (for example,
        publishing streaming status to the custom status) must be skipped while
        this is ``True`` so they are not re-emitted on replay.
        """
        ...

    @property
    def supports_event_streaming(self) -> bool:
        """Whether this host streams the workflow event timeline via custom status.

        The orchestrator accumulates the full :class:`WorkflowEvent` history and can
        publish it to the orchestration custom status so a streaming client can
        replay it (see ``DurableWorkflowClient.stream_workflow``). A host returns
        ``True`` only when both are true: it has a streaming consumer *and* its
        custom status can carry an accumulating, payload-bearing event log.

        The Azure Functions host returns ``False``: its Durable Functions custom
        status is capped at 16 KB (UTF-16) by the WebJobs extension, and its HTTP
        status endpoint exposes only ``state`` / ``pending_requests`` / ``output``,
        never the event stream. Publishing the accumulating event log there would
        overflow the cap and fail the orchestrator without serving any consumer.

        When ``False``, the orchestrator skips event accumulation and omits
        ``events`` from the custom status; ``state`` and any ``pending_requests``
        (needed for human-in-the-loop) are still published.
        """
        ...

    @property
    def current_utc_datetime(self) -> datetime:
        """The current replay-safe UTC datetime."""
        ...

    def prepare_agent_task(self, executor_id: str, message: str, orchestration_instance_id: str) -> Any:
        """Create a yieldable task that runs an agent executor.

        Args:
            executor_id: Agent name / executor ID.
            message: The text message to send to the agent.
            orchestration_instance_id: Instance ID used as the entity session key.

        Returns:
            A yieldable task whose result is an ``AgentResponse``.
        """
        ...

    def prepare_activity_task(self, activity_name: str, input_json: str) -> Any:
        """Create a yieldable task that runs an activity executor.

        Args:
            activity_name: The registered activity function name.
            input_json: JSON-serialized activity input.

        Returns:
            A yieldable task whose result is a JSON string.
        """
        ...

    def task_all(self, tasks: list[Any]) -> Any:
        """Create a yieldable composite task that completes when *all* tasks complete.

        Args:
            tasks: List of yieldable tasks.

        Returns:
            A yieldable task whose result is a list of individual results.
        """
        ...

    def task_any(self, tasks: list[Any]) -> Any:
        """Create a yieldable composite task that completes when *any* task completes.

        Args:
            tasks: List of yieldable tasks.

        Returns:
            A yieldable task whose result is the winning task.
        """
        ...

    def wait_for_external_event(self, name: str) -> Any:
        """Create a yieldable task that waits for a named external event.

        Args:
            name: Event name to wait for.

        Returns:
            A yieldable task whose result is the event payload.
        """
        ...

    def create_timer(self, fire_at: datetime) -> Any:
        """Create a yieldable timer task.

        Args:
            fire_at: UTC datetime when the timer should fire.

        Returns:
            A yieldable timer task.
        """
        ...

    def set_custom_status(self, status: Any) -> None:
        """Set the orchestration's custom status (visible to external clients).

        Args:
            status: JSON-serializable status object.
        """
        ...

    def new_uuid(self) -> str:
        """Generate a replay-safe UUID."""
        ...

    def cancel_task(self, task: Any) -> None:
        """Best-effort cancellation of a pending task.

        Args:
            task: The task to cancel.  If the underlying SDK does not support
                cancellation this is a no-op.
        """
        ...

    def get_task_result(self, task: Any) -> Any:
        """Extract the result from a completed task.

        Args:
            task: A completed task object.

        Returns:
            The result value.
        """
        ...
