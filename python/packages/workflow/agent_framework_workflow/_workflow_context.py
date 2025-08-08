# Copyright (c) Microsoft. All rights reserved.

from typing import Any

from ._events import WorkflowEvent
from ._runner_context import Message, RunnerContext
from ._shared_state import SharedState


class WorkflowContext:
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
    ):
        """Initialize the executor context with the given workflow context.

        Args:
            executor_id: The unique identifier of the executor that this context belongs to.
            source_executor_ids: The IDs of the source executors that sent messages to this executor.
                This is a list to support fan_in scenarios where multiple sources send aggregated
                messages to the same executor.
            shared_state: The shared state for the workflow.
            runner_context: The runner context that provides methods to send messages and events.
        """
        self._executor_id = executor_id
        self._source_executor_ids = source_executor_ids
        self._runner_context = runner_context
        self._shared_state = shared_state

        if not self._source_executor_ids:
            raise ValueError("source_executor_ids cannot be empty. At least one source executor ID is required.")

    async def send_message(self, message: Any, target_id: str | None = None) -> None:
        """Send a message to the workflow context.

        Args:
            message: The message to send. This can be any data type that the target executor can handle.
            target_id: The ID of the target executor to send the message to.
                       If None, the message will be sent to all target executors.
        """
        await self._runner_context.send_message(
            Message(
                data=message,
                source_id=self._executor_id,
                target_id=target_id,
            )
        )

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
