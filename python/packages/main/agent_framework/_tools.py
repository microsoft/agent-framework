# Copyright (c) Microsoft. All rights reserved.

import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from time import perf_counter
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from opentelemetry import metrics, trace
from pydantic import BaseModel, create_model

from ._logging import get_logger
from .telemetry import GenAIAttributes, start_as_current_span

tracer: trace.Tracer = trace.get_tracer("agent_framework")
meter: metrics.Meter = metrics.get_meter_provider().get_meter("agent_framework")
logger = get_logger()

__all__ = ["AIFunction", "AITool", "HostedCodeInterpreterTool", "ai_function"]


@runtime_checkable
class AITool(Protocol):
    """Represents a generic tool that can be specified to an AI service.

    Attributes:
        name: The name of the tool.
        description: A description of the tool.
        additional_properties: Additional properties associated with the tool.

    Methods:
        parameters: The parameters accepted by the tool, in a json schema format.
    """

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


class AIFunction(AITool, Generic[ArgsT, ReturnT]):
    """A AITool that is callable as code."""

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
        self.invocation_duration_histogram = meter.create_histogram(
            "agent_framework.function.invocation.duration",
            unit="s",
            description="Measures the duration of a function's execution",
        )

    def parameters(self) -> dict[str, Any]:
        """Return the parameter json schemas of the input model."""
        return self.input_model.model_json_schema()

    def __call__(self, *args: Any, **kwargs: Any) -> ReturnT | Awaitable[ReturnT]:
        """Call the wrapped function with the provided arguments."""
        return self._func(*args, **kwargs)

    def __str__(self) -> str:
        return f"AIFunction(name={self.name}, description={self.description})"

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
        tool_call_id = kwargs.pop("tool_call_id", None)
        if arguments is not None:
            if not isinstance(arguments, self.input_model):
                raise TypeError(f"Expected {self.input_model.__name__}, got {type(arguments).__name__}")
            kwargs = arguments.model_dump(exclude_none=True)
        logger.info(f"Function name: {self.name}")
        logger.debug(f"Function arguments: {kwargs}")
        with start_as_current_span(
            tracer, self, metadata={"tool_call_id": tool_call_id, "kwargs": kwargs}
        ) as current_span:
            attributes: dict[str, Any] = {
                GenAIAttributes.MEASUREMENT_FUNCTION_TAG_NAME.value: self.name,
                GenAIAttributes.TOOL_CALL_ID.value: tool_call_id,
            }
            starting_time_stamp = perf_counter()
            try:
                res = self.__call__(**kwargs)
                result = await res if inspect.isawaitable(res) else res
                logger.info(f"Function {self.name} succeeded.")
                logger.debug(f"Function result: {result or 'None'}")
                return result  # type: ignore[reportReturnType]
            except Exception as exception:
                attributes[GenAIAttributes.ERROR_TYPE.value] = type(exception).__name__
                current_span.record_exception(exception)
                current_span.set_attribute(GenAIAttributes.ERROR_TYPE.value, type(exception).__name__)
                current_span.set_status(trace.StatusCode.ERROR, description=str(exception))
                logger.error(f"Function failed. Error: {exception}")
                raise
            finally:
                duration = perf_counter() - starting_time_stamp
                self.invocation_duration_histogram.record(duration, attributes=attributes)
                logger.info("Function completed. Duration: %fs", duration)


def ai_function(
    func: Callable[..., ReturnT | Awaitable[ReturnT]] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    additional_properties: dict[str, Any] | None = None,
) -> AIFunction[Any, ReturnT]:
    """Decorate a function to turn it into a AIFunction that can be passed to models and executed automatically.

    This function will create a Pydantic model from the function's signature,
    which will be used to validate the arguments passed to the function.
    And will be used to generate the JSON schema for the function's parameters.
    In order to add descriptions to parameters, in your function signature,
    use the `Annotated` type from `typing` and the `Field` class from `pydantic`:

            from typing import Annotated

            from pydantic import Field

            <field_name>: Annotated[<type>, Field(description="<description>")]

    Args:
        func: The function to wrap. If None, returns a decorator.
        name: The name of the tool. Defaults to the function's name.
        description: A description of the tool. Defaults to the function's docstring.
        additional_properties: Additional properties to set on the tool.

    """

    def decorator(func: Callable[..., ReturnT | Awaitable[ReturnT]]) -> AIFunction[Any, ReturnT]:
        @wraps(func)
        def wrapper(f: Callable[..., ReturnT | Awaitable[ReturnT]]) -> AIFunction[Any, ReturnT]:
            tool_name: str = name or getattr(f, "__name__", "unknown_function")  # type: ignore[assignment]
            tool_desc: str = description or (f.__doc__ or "")
            sig = inspect.signature(f)
            fields = {
                pname: (
                    param.annotation if param.annotation is not inspect.Parameter.empty else str,
                    param.default if param.default is not inspect.Parameter.empty else ...,
                )
                for pname, param in sig.parameters.items()
                if pname not in {"self", "cls"}
            }
            input_model: Any = create_model(f"{tool_name}_input", **fields)  # type: ignore[call-overload]
            if not issubclass(input_model, BaseModel):
                raise TypeError(f"Input model for {tool_name} must be a subclass of BaseModel, got {input_model}")

            return AIFunction[Any, ReturnT](
                func=f,
                name=tool_name,
                description=tool_desc,
                input_model=input_model,
                **(additional_properties if additional_properties is not None else {}),
            )

        return wrapper(func)

    return decorator(func) if func else decorator  # type: ignore[reportReturnType, return-value]


class HostedCodeInterpreterTool(AITool):
    """Represents a hosted tool that can be specified to an AI service to enable it to execute generated code.

    This tool does not implement code interpretation itself. It serves as a marker to inform a service
    that it is allowed to execute generated code if the service is capable of doing so.
    """

    def __init__(
        self,
        name: str = "code_interpreter",
        description: str | None = None,
        additional_properties: dict[str, Any] | None = None,
    ):
        """Initialize a HostedCodeInterpreterTool.

        Args:
            name: The name of the tool. Defaults to "code_interpreter".
            description: A description of the tool.
            additional_properties: Additional properties associated with the tool, specific to the service used.
        """
        self.name = name
        self.description = description
        self.additional_properties = additional_properties

    def __str__(self) -> str:
        """Return a string representation of the tool."""
        return f"HostedCodeInterpreterTool(name={self.name})"
