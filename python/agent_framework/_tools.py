# Copyright (c) Microsoft. All rights reserved.

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, create_model


@runtime_checkable
class AITool(Protocol):
    """Represents a tool that can be specified to an AI service."""

    name: str
    """The name of the tool."""
    description: str | None = None
    """A description of the tool, suitable for use in describing the purpose to a model."""
    additional_properties: dict[str, Any] | None = None
    """Additional properties associated with the tool."""

    def __str__(self) -> str:
        """Return a string representation of the tool."""
        ...


ArgsT = TypeVar("ArgsT", bound=BaseModel)
ReturnT = TypeVar("ReturnT")


class AIFunction(Generic[ArgsT, ReturnT]):
    """A tool that represents a function that can be called by an AI service."""

    def __init__(
        self,
        func: Callable[..., Awaitable[ReturnT] | ReturnT],
        name: str,
        description: str,
        input_model: type[ArgsT],
        **kwargs: Any,
    ):
        """Initialize a FunctionTool.

        Args:
            func: The function to wrap.
            name: The name of the tool.
            description: A description of the tool.
            input_model: A Pydantic model that defines the input parameters for the function.
            **kwargs: Additional properties to set on the tool.
                stored in additional_properties.
        """
        self.name = name
        self.description = description
        self.input_model = input_model
        self.additional_properties: dict[str, Any] | None = kwargs
        self._func = func

    def model_json_schema(self):
        """Return the JSON schema of the input model."""
        return self.input_model.model_json_schema()

    def __call__(self, *args: Any, **kwargs: Any) -> ReturnT | Awaitable[ReturnT]:
        """Call the wrapped function with the provided arguments."""
        if not inspect.iscoroutinefunction(self._func):
            return self._func(*args, **kwargs)

        async def _async_wrapper():
            """Wrapper to handle async function calls."""
            return await self._func(*args, **kwargs)

        return _async_wrapper()

    def __get__(self, obj: object, objtype: type | None = None):
        """Support binding the function tool to an object, allowing it to be called as a method."""
        if obj is None:
            return self

        def _bound(*args, **kwargs) -> ReturnT | Awaitable[ReturnT]:
            if inspect.iscoroutinefunction(self._func):

                async def _async_wrapper():
                    """Wrapper to handle async function calls."""
                    return await self._func(obj, *args, **kwargs)

                return _async_wrapper()
            return self._func(obj, *args, **kwargs)

        return AIFunction(
            func=_bound,
            name=self.name,
            description=self.description,
            input_model=self.input_model,
        )

    async def invoke(
        self,
        *,
        arguments: ArgsT | None = None,
        **kwargs: Any,
    ) -> ReturnT:
        """Run the AI function with the provided arguments as a Pydantic model.

        Args:
            arguments: A Pydantic model instance containing the arguments for the function.
            kwargs: keyword arguments to pass to the function, will not be used if `args` is provided.
        """
        if arguments is not None:
            if not isinstance(arguments, self.input_model):
                raise TypeError(f"Expected {self.input_model.__name__}, got {type(arguments).__name__}")
            kwargs = arguments.model_dump(exclude_none=True)
        res = self.__call__(**kwargs)
        if inspect.isawaitable(res):
            return await res
        return res


def ai_function(
    func: Callable[..., ReturnT | Awaitable[ReturnT]] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    additional_properties: dict[str, Any] | None = None,
) -> AIFunction[Any, ReturnT] | Callable[Callable[..., ReturnT | Awaitable[ReturnT]], AIFunction[Any, ReturnT]]:
    """Create a AIFunction from a function and return the callable tool object."""

    def wrapper(f: Callable[..., ReturnT | Awaitable[ReturnT]]) -> AIFunction[Any, ReturnT]:
        tool_name = name or getattr(f, "__name__", "unknown_function")
        tool_desc = description or (f.__doc__ or "")
        sig = inspect.signature(f)
        fields = {
            pname: (
                param.annotation if param.annotation is not inspect.Parameter.empty else str,
                param.default if param.default is not inspect.Parameter.empty else ...,
            )
            for pname, param in sig.parameters.items()
            if pname not in {"self", "cls"}
        }
        input_model = create_model(f"{tool_name}_input", **fields)

        return functools.update_wrapper(
            AIFunction[Any, ReturnT](
                func=f,
                name=tool_name,
                description=tool_desc,
                input_model=input_model,
                **(additional_properties if additional_properties is not None else {}),
            ),
            f,
        )

    return wrapper(func) if func else wrapper
