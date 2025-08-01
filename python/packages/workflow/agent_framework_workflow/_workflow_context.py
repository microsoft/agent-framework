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
        shared_state: SharedState,
        runner_context: RunnerContext,
    ):
        """Initialize the executor context with the given workflow context.

        Args:
            executor_id: The unique identifier of the executor that this context belongs to.
            source_executor_id: The unique identifier of the source executor that generated this context.
            shared_state: The shared state for the workflow.
            runner_context: The runner context that provides methods to send messages and events.
        """
        self._executor_id = executor_id
        self._runner_context = runner_context
        self._shared_state = shared_state

    async def send_message(self, message: Any, target_id: str | None = None) -> None:
        """Send a message to the workflow context."""
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

    @property
    def shared_state(self) -> SharedState:
        """Get the shared state."""
        return self._shared_state
