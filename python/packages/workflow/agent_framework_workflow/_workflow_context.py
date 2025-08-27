# Copyright (c) Microsoft. All rights reserved.

from typing import Any, Generic, TypeVar

from opentelemetry.propagate import inject

from ._events import WorkflowEvent
from ._runner_context import Message, RunnerContext
from ._shared_state import SharedState
from ._telemetry import workflow_tracer

T_Out = TypeVar("T_Out")


class WorkflowContext(Generic[T_Out]):
    """Context for executors in a workflow.

    This class is used to provide a way for executors to interact with the workflow
    context and shared state, while preventing direct access to the runtime context.
    """

    def __init__(
        self,
        executor_id: str,
        source_executor_ids: list[str],
        shared_state: SharedState,
        runner_context: RunnerContext,
        trace_contexts: list[dict[str, str]] | None = None,
        source_span_ids: list[str] | None = None,
    ):
        """Initialize the executor context with the given workflow context.

        Args:
            executor_id: The unique identifier of the executor that this context belongs to.
            source_executor_ids: The IDs of the source executors that sent messages to this executor.
                This is a list to support fan_in scenarios where multiple sources send aggregated
                messages to the same executor.
            shared_state: The shared state for the workflow.
            runner_context: The runner context that provides methods to send messages and events.
            trace_contexts: Optional trace contexts from multiple sources for OpenTelemetry propagation.
            source_span_ids: Optional source span IDs from multiple sources for linking (not for nesting).
        """
        self._executor_id = executor_id
        self._source_executor_ids = source_executor_ids
        self._runner_context = runner_context
        self._shared_state = shared_state

        # Store trace contexts and source span IDs for linking (supporting multiple sources)
        self._trace_contexts = trace_contexts or []
        self._source_span_ids = source_span_ids or []

        if not self._source_executor_ids:
            raise ValueError("source_executor_ids cannot be empty. At least one source executor ID is required.")

    async def send_message(self, message: T_Out, target_id: str | None = None) -> None:
        """Send a message to the workflow context.

        Args:
            message: The message to send. This must conform to the output type(s) declared on this context.
            target_id: The ID of the target executor to send the message to.
                       If None, the message will be sent to all target executors.
        """
        # Create publishing span (inherits current trace context automatically)
        with workflow_tracer.create_sending_span(type(message).__name__, target_id) as span:
            # Create Message wrapper
            msg = Message(data=message, source_id=self._executor_id, target_id=target_id)

            # Inject current trace context if tracing enabled
            if workflow_tracer.enabled and span and span.is_recording():
                trace_context: dict[str, str] = {}
                inject(trace_context)  # Inject current trace context for message propagation

                msg.trace_contexts = [trace_context]
                msg.source_span_ids = [format(span.get_span_context().span_id, "016x")]

            await self._runner_context.send_message(msg)

    async def add_event(self, event: WorkflowEvent) -> None:
        """Add an event to the workflow context."""
        await self._runner_context.add_event(event)

    async def get_shared_state(self, key: str) -> Any:
        """Get a value from the shared state."""
        return await self._shared_state.get(key)

    async def set_shared_state(self, key: str, value: Any) -> None:
        """Set a value in the shared state."""
        await self._shared_state.set(key, value)

    def get_source_executor_id(self) -> str:
        """Get the ID of the source executor that sent the message to this executor.

        Raises:
            RuntimeError: If there are multiple source executors, this method raises an error.
        """
        if len(self._source_executor_ids) > 1:
            raise RuntimeError(
                "Cannot get source executor ID when there are multiple source executors. "
                "Access the full list via the source_executor_ids property instead."
            )
        return self._source_executor_ids[0]

    @property
    def source_executor_ids(self) -> list[str]:
        """Get the IDs of the source executors that sent messages to this executor."""
        return self._source_executor_ids

    @property
    def shared_state(self) -> SharedState:
        """Get the shared state."""
        return self._shared_state

    async def set_state(self, state: dict[str, Any]) -> None:
        """Persist this executor's state into the checkpointable context.

        Executors call this with a JSON-serializable dict capturing the minimal
        state needed to resume. It replaces any previously stored state.
        """
        if hasattr(self._runner_context, "set_state"):
            await self._runner_context.set_state(self._executor_id, state)  # type: ignore[arg-type]

    async def get_state(self) -> dict[str, Any] | None:
        """Retrieve previously persisted state for this executor, if any."""
        if hasattr(self._runner_context, "get_state"):
            return await self._runner_context.get_state(self._executor_id)  # type: ignore[return-value]
        return None
