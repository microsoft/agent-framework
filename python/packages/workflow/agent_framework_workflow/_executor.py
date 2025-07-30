# Copyright (c) Microsoft. All rights reserved.

import uuid
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, get_args

from ._events import ExecutorCompleteEvent, ExecutorInvokeEvent
from ._typing_utils import is_instance_of
from ._workflow_context import WorkflowContext

T = TypeVar("T")


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
    async def _execute(self, data: T, ctx: WorkflowContext) -> None:
        """Execute the task using the registered handlers.

        Args:
            data: The data of type T to be processed.
            ctx: The execution context containing additional information.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    async def execute(self, data: T, ctx: WorkflowContext) -> None:
        """Execute a task with the given data and context.

        Args:
            data: The data of type T to be processed.
            ctx: The execution context containing additional information.
        """
        await ctx.add_event(ExecutorInvokeEvent(executor_id=self._id))
        await self._execute(data, ctx)
        await ctx.add_event(ExecutorCompleteEvent(executor_id=self._id))

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
