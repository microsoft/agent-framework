# Copyright (c) Microsoft. All rights reserved.

import uuid
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, get_args

from ._shared_state import SharedState
from ._typing_utils import is_instance_of
from .events import ExecutorCompleteEvent, ExecutorInvokeEvent, WorkflowEvent
from .workflow_context import NoopWorkflowContext, WorkflowContext

T = TypeVar("T")


class ExecutorContext:
    """Context for executing an executor.

    This class is used to provide a way for executors to interact with the workflow
    context and shared state, while preventing direct access to the workflow context.
    """

    def __init__(self, executor_id: str, shared_state: SharedState, workflow_context: WorkflowContext):
        """Initialize the executor context with the given workflow context."""
        self._workflow_context = workflow_context
        self._executor_id = executor_id
        self._shared_state = shared_state

    async def send_message(self, message: Any) -> None:
        """Send a message to the workflow context."""
        await self._workflow_context.send_message(self._executor_id, message)

    async def add_event(self, event: WorkflowEvent) -> None:
        """Add an event to the workflow context."""
        await self._workflow_context.add_event(event)

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


class NoopExecutorContext(ExecutorContext):
    """A no-operation executor context that does nothing."""

    def __init__(self):
        """Initialize the noop executor context."""
        super().__init__(executor_id="", shared_state=SharedState(), workflow_context=NoopWorkflowContext())


class Executor(Generic[T], ABC):
    """An abstract base class for executing tasks in a workflow.

    Args:
        T: The type of the task to be executed.
    """

    def __init__(self, id: str | None = None):
        """Initialize the executor with a unique identifier."""
        self._id = id or str(uuid.uuid4())

        args = get_args(self.__orig_bases__[0])  # type: ignore
        if len(args) != 1:
            raise ValueError(f"Executor must be parameterized with a single type, got {args}")
        self._input_type = args[0]

    @abstractmethod
    async def _execute(self, data: T, ctx: ExecutorContext) -> Any:
        """Execute the task using the registered handlers.

        Args:
            data: The data of type T to be processed.
            ctx: The execution context containing additional information.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    async def execute(self, data: T, ctx: ExecutorContext | None = None) -> Any:
        """Execute a task with the given data and context.

        Args:
            data: The data of type T to be processed.
            ctx: The execution context containing additional information.
        """
        if ctx is None:
            ctx = NoopExecutorContext()

        await ctx.add_event(ExecutorInvokeEvent(executor_id=self._id, data=data))
        result = await self._execute(data, ctx)
        await ctx.add_event(ExecutorCompleteEvent(executor_id=self._id, data=result))

        return result

    @property
    def id(self) -> str:
        """Get the unique identifier of the executor."""
        return self._id

    def can_handle(self, data: Any) -> bool:
        """Determine if the executor can handle the given data.

        Args:
            data: The data to check.

        Returns:
            bool: True if the executor can handle the data, False otherwise.
        """
        return is_instance_of(data, self._input_type)


TExecutor = TypeVar("TExecutor", bound=Executor[Any])


def output_message_types(*output_types: type):
    """Decorator to specify the output types of an executor."""

    def decorator(cls: type[TExecutor]) -> type[TExecutor]:
        cls._declare_output_types = output_types  # type: ignore
        return cls

    return decorator
