# Copyright (c) Microsoft. All rights reserved.

import uuid
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, get_args

from ._shared_state import SharedState
from ._typing_utils import is_instance_of
from .events import ExecutorCompleteEvent, ExecutorInvokeEvent, WorkflowEvent
from .execution_context import ExecutionContext, NoopExecutionContext

T = TypeVar("T")


class ExecutorContext:
    """Context for executing an executor.

    This class provides a way to execute an executor with a specific context.
    It is used to manage the execution of tasks in a workflow.
    """

    def __init__(self, executor_id: str, shared_state: SharedState, execution_context: ExecutionContext):
        """Initialize the executor context with the given execution context."""
        self._execution_context = execution_context
        self._executor_id = executor_id
        self._shared_state = shared_state

    async def send_message(self, message: Any) -> None:
        """Send a message to the execution context."""
        await self._execution_context.send_message(self._executor_id, message)

    async def add_event(self, event: WorkflowEvent) -> None:
        """Add an event to the execution context."""
        await self._execution_context.add_event(event)

    async def get_shared_state(self, key: str) -> Any:
        """Get a value from the shared state."""
        return await self._shared_state.get(key)

    async def set_shared_state(self, key: str, value: Any) -> None:
        """Set a value in the shared state."""
        await self._shared_state.set(key, value)


class NoopExecutorContext(ExecutorContext):
    """A no-operation executor context that does nothing."""

    def __init__(self):
        """Initialize the noop executor context."""
        super().__init__(executor_id="", shared_state=SharedState(), execution_context=NoopExecutionContext())


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
