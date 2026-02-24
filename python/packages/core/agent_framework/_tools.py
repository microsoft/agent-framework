# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sys
from collections.abc import (
    AsyncIterable,
    Awaitable,
    Callable,
    Mapping,
    Sequence,
)
from contextlib import suppress
from functools import partial, wraps
from time import perf_counter, time_ns
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Final,
    Generic,
    Literal,
    TypeAlias,
    TypedDict,
    Union,
    get_args,
    get_origin,
    overload,
)

from opentelemetry.metrics import Histogram, NoOpHistogram
from pydantic import BaseModel, Field, ValidationError, create_model

from ._serialization import SerializationMixin
from .exceptions import ToolException
from .observability import (
    OPERATION_DURATION_BUCKET_BOUNDARIES,
    OtelAttr,
    capture_exception,
    get_function_span,
    get_function_span_attributes,
    get_meter,
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore[import] # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover


if TYPE_CHECKING:
    from ._clients import SupportsChatGetResponse
    from ._mcp import MCPTool
    from ._middleware import FunctionMiddlewarePipeline, FunctionMiddlewareTypes
    from ._types import (
        ChatOptions,
        ChatResponse,
        ChatResponseUpdate,
        Content,
        Message,
        ResponseStream,
    )

    ResponseModelBoundT = TypeVar("ResponseModelBoundT", bound=BaseModel)
else:
    MCPTool = Any  # type: ignore[assignment,misc]


logger = logging.getLogger("agent_framework")

DEFAULT_MAX_ITERATIONS: Final[int] = 40
DEFAULT_MAX_CONSECUTIVE_ERRORS_PER_REQUEST: Final[int] = 3
ChatClientT = TypeVar("ChatClientT", bound="SupportsChatGetResponse[Any]")
# region Helpers


def _parse_inputs(
    inputs: Content | dict[str, Any] | str | list[Content | dict[str, Any] | str] | None,
) -> list[Content]:
    """Parse the inputs for a tool, ensuring they are of type Content.

    Args:
        inputs: The inputs to parse. Can be a single item or list of Content, dicts, or strings.

    Returns:
        A list of Content objects.

    Raises:
        ValueError: If an unsupported input type is encountered.
        TypeError: If the input type is not supported.
    """
    if inputs is None:
        return []

    from ._types import (
        Content,
    )

    parsed_inputs: list[Content] = []
    if not isinstance(inputs, list):
        inputs = [inputs]
    for input_item in inputs:
        if isinstance(input_item, str):
            # If it's a string, we assume it's a URI or similar identifier.
            # Convert it to a UriContent or similar type as needed.
            parsed_inputs.append(Content.from_uri(uri=input_item, media_type="text/plain"))
        elif isinstance(input_item, dict):
            # If it's a dict, we assume it contains properties for a specific content type.
            # we check if the required keys are present to determine the type.
            # for instance, if it has "uri" and "media_type", we treat it as UriContent.
            # if it only has uri and media_type without a specific type indicator, we treat it as DataContent.
            # etc.
            if "uri" in input_item:
                # Use Content.from_uri for proper URI content, DataContent for backwards compatibility
                parsed_inputs.append(Content.from_uri(**input_item))
            elif "file_id" in input_item:
                parsed_inputs.append(Content.from_hosted_file(**input_item))
            elif "vector_store_id" in input_item:
                parsed_inputs.append(Content.from_hosted_vector_store(**input_item))
            elif "data" in input_item:
                # DataContent helper handles both uri and data parameters
                parsed_inputs.append(Content.from_data(**input_item))
            else:
                raise ValueError(f"Unsupported input type: {input_item}")
        elif isinstance(input_item, Content):
            parsed_inputs.append(input_item)
        else:
            raise TypeError(f"Unsupported input type: {type(input_item).__name__}. Expected Content or dict.")
    return parsed_inputs


# region Tools


def _default_histogram() -> Histogram:
    """Get the default histogram for function invocation duration.

    Returns:
        A Histogram instance for recording function invocation duration,
        or a no-op histogram if observability is disabled.
    """
    from .observability import OBSERVABILITY_SETTINGS  # local import to avoid circulars

    if not OBSERVABILITY_SETTINGS.ENABLED:  # type: ignore[name-defined]
        return NoOpHistogram(
            name=OtelAttr.MEASUREMENT_FUNCTION_INVOCATION_DURATION,
            unit=OtelAttr.DURATION_UNIT,
        )
    meter = get_meter()
    try:
        return meter.create_histogram(
            name=OtelAttr.MEASUREMENT_FUNCTION_INVOCATION_DURATION,
            unit=OtelAttr.DURATION_UNIT,
            description="Measures the duration of a function's execution",
            explicit_bucket_boundaries_advisory=OPERATION_DURATION_BUCKET_BOUNDARIES,
        )
    except TypeError:
        return meter.create_histogram(
            name=OtelAttr.MEASUREMENT_FUNCTION_INVOCATION_DURATION,
            unit=OtelAttr.DURATION_UNIT,
            description="Measures the duration of a function's execution",
        )


ClassT = TypeVar("ClassT", bound="SerializationMixin")


class FunctionTool(SerializationMixin):
    """A tool that wraps a Python function to make it callable by AI models.

    This class wraps a Python function to make it callable by AI models with automatic
    parameter validation and JSON schema generation.

    Attributes:
        name: The name of the tool.
        description: A description of the tool, suitable for use in describing the purpose to a model.
        additional_properties: Additional properties associated with the tool.

    Examples:
        .. code-block:: python

            from typing import Annotated
            from pydantic import BaseModel, Field
            from agent_framework import FunctionTool, tool


            # Using the decorator with string annotations
            @tool(approval_mode="never_require")
            def get_weather(
                location: Annotated[str, "The city name"],
                unit: Annotated[str, "Temperature unit"] = "celsius",
            ) -> str:
                '''Get the weather for a location.'''
                return f"Weather in {location}: 22°{unit[0].upper()}"


            # Using direct instantiation with Field
            class WeatherArgs(BaseModel):
                location: Annotated[str, Field(description="The city name")]
                unit: Annotated[str, Field(description="Temperature unit")] = "celsius"


            weather_func = FunctionTool(
                name="get_weather",
                description="Get the weather for a location",
                func=lambda location, unit="celsius": f"Weather in {location}: 22°{unit[0].upper()}",
                approval_mode="never_require",
                input_model=WeatherArgs,
            )

            # Invoke the function
            result = await weather_func.invoke(arguments=WeatherArgs(location="Seattle"))
    """

    INJECTABLE: ClassVar[set[str]] = {"func"}
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {
        "additional_properties",
        "input_model",
        "_invocation_duration_histogram",
        "_cached_parameters",
        "_input_schema",
        "_schema_supplied",
    }

    def __init__(
        self,
        *,
        name: str,
        description: str = "",
        approval_mode: Literal["always_require", "never_require"] | None = None,
        max_invocations: int | None = None,
        max_invocation_exceptions: int | None = None,
        additional_properties: dict[str, Any] | None = None,
        func: Callable[..., Any] | None = None,
        input_model: type[BaseModel] | Mapping[str, Any] | None = None,
        result_parser: Callable[[Any], str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the FunctionTool.

        Keyword Args:
            name: The name of the function.
            description: A description of the function.
            approval_mode: Whether or not approval is required to run this tool.
                Default is that approval is NOT required (``"never_require"``).
            max_invocations: The maximum number of times this function can be invoked
                across the **lifetime of this tool instance**. If None (default),
                there is no limit. Should be at least 1. If the tool is called multiple
                times in one iteration, those will execute, after that it will stop working. For example,
                if max_invocations is 3 and the tool is called 5 times in a single iteration,
                these will complete, but any subsequent calls to the tool (in the same or future iterations)
                will raise a ToolException.

                .. note::
                    This counter lives on the tool instance and is never automatically
                    reset. For module-level or singleton tools in long-running
                    applications, the counter accumulates across all requests. Use
                    :attr:`invocation_count` to inspect or reset the counter manually,
                    or consider using
                    ``FunctionInvocationConfiguration["max_function_calls"]``
                    for per-request limits instead.

            max_invocation_exceptions: The maximum number of exceptions allowed during invocations.
                If None, there is no limit. Should be at least 1.
            additional_properties: Additional properties to set on the function.
            func: The function to wrap. When ``None``, creates a declaration-only tool
                that has no implementation. Declaration-only tools are useful when you want
                the agent to reason about tool usage without executing them, or when the
                actual implementation exists elsewhere (e.g., client-side rendering).
            input_model: The Pydantic model that defines the input parameters for the function.
                This can also be a JSON schema dictionary.
                If not provided and ``func`` is not ``None``, it will be inferred from
                the function signature. When ``func`` is ``None`` and ``input_model`` is
                not provided, the tool will use an empty input model (no parameters) in
                its JSON schema. For declaration-only tools that should declare
                parameters, explicitly provide ``input_model`` (either a Pydantic
                ``BaseModel`` or a JSON schema dictionary) so the model can reason about
                the expected arguments.
            result_parser: An optional callable with signature ``Callable[[Any], str]`` that
                overrides the default result parsing behavior. When provided, this callable
                is used to convert the raw function return value to a string instead of the
                built-in :meth:`parse_result` logic. Depending on your function, it may be
                easiest to just do the serialization directly in the function body rather
                than providing a custom ``result_parser``.
            **kwargs: Additional keyword arguments.
        """
        # Core attributes (formerly from BaseTool)
        self.name = name
        self.description = description
        self.additional_properties = additional_properties
        for key, value in kwargs.items():
            setattr(self, key, value)

        # FunctionTool-specific attributes
        self.func = func
        self._instance = None  # Store the instance for bound methods

        # Initialize schema cache (will be lazily populated)
        self._input_schema_cached: dict[str, Any] | None = None

        # Track if schema was supplied as JSON dict (for optimization)
        if isinstance(input_model, Mapping):
            self._schema_supplied = True
            self._input_schema_cached = dict(input_model)
            self.input_model: type[BaseModel] | None = None
        else:
            self._schema_supplied = False
            self.input_model = self._resolve_input_model(input_model)
            # Defer schema generation to avoid issues with forward references
        self._cached_parameters: dict[str, Any] | None = None
        self.approval_mode = approval_mode or "never_require"
        if max_invocations is not None and max_invocations < 1:
            raise ValueError("max_invocations must be at least 1 or None.")
        if max_invocation_exceptions is not None and max_invocation_exceptions < 1:
            raise ValueError("max_invocation_exceptions must be at least 1 or None.")
        self.max_invocations = max_invocations
        self.invocation_count = 0
        self.max_invocation_exceptions = max_invocation_exceptions
        self.invocation_exception_count = 0
        self._invocation_duration_histogram = _default_histogram()
        self.type: Literal["function_tool"] = "function_tool"
        self.result_parser = result_parser
        self._forward_runtime_kwargs: bool = False
        if self.func:
            sig = inspect.signature(self.func)
            for param in sig.parameters.values():
                if param.kind == inspect.Parameter.VAR_KEYWORD:
                    self._forward_runtime_kwargs = True
                    break

    def __str__(self) -> str:
        """Return a string representation of the tool."""
        if self.description:
            return f"{self.__class__.__name__}(name={self.name}, description={self.description})"
        return f"{self.__class__.__name__}(name={self.name})"

    @property
    def declaration_only(self) -> bool:
        """Indicate whether the function is declaration only (i.e., has no implementation)."""
        # Check for explicit _declaration_only attribute first (used in tests)
        if hasattr(self, "_declaration_only") and self._declaration_only:
            return True
        return self.func is None

    def __get__(self, obj: Any, objtype: type | None = None) -> FunctionTool:
        """Implement the descriptor protocol to support bound methods.

        When a FunctionTool is accessed as an attribute of a class instance,
        this method is called to bind the instance to the function.

        Args:
            obj: The instance that owns the descriptor, or None for class access.
            objtype: The type that owns the descriptor.

        Returns:
            A new FunctionTool with the instance bound to the wrapped function.
        """
        if obj is None:
            # Accessed from the class, not an instance
            return self

        # Check if the wrapped function is a method (has 'self' parameter)
        if self.func is not None:
            sig = inspect.signature(self.func)
            params = list(sig.parameters.keys())
            if params and params[0] in {"self", "cls"}:
                # Create a new FunctionTool with the bound method
                import copy

                bound_func = copy.copy(self)
                bound_func._instance = obj
                return bound_func

        return self

    def _resolve_input_model(self, input_model: type[BaseModel] | None) -> type[BaseModel]:
        """Resolve the input model for the function."""
        if input_model is not None:
            if inspect.isclass(input_model) and issubclass(input_model, BaseModel):
                return input_model
            raise TypeError("input_model must be a Pydantic BaseModel subclass or a JSON schema dict.")

        if self.func is None:
            return create_model(f"{self.name}_input")

        func = self.func.func if isinstance(self.func, FunctionTool) else self.func
        if func is None:
            return create_model(f"{self.name}_input")
        sig = inspect.signature(func)
        fields: dict[str, Any] = {
            pname: (
                _parse_annotation(param.annotation) if param.annotation is not inspect.Parameter.empty else str,
                param.default if param.default is not inspect.Parameter.empty else ...,
            )
            for pname, param in sig.parameters.items()
            if pname not in {"self", "cls"}
            and param.kind not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        }
        return create_model(f"{self.name}_input", **fields)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the wrapped function with the provided arguments."""
        if self.declaration_only:
            raise ToolException(f"Function '{self.name}' is declaration only and cannot be invoked.")
        if self.max_invocations is not None and self.invocation_count >= self.max_invocations:
            raise ToolException(
                f"Function '{self.name}' has reached its maximum invocation limit, you can no longer use this tool."
            )
        if (
            self.max_invocation_exceptions is not None
            and self.invocation_exception_count >= self.max_invocation_exceptions
        ):
            raise ToolException(
                f"Function '{self.name}' has reached its maximum exception limit, "
                f"you tried to use this tool too many times and it kept failing."
            )
        self.invocation_count += 1
        try:
            # If we have a bound instance, call the function with self
            if self._instance is not None:
                return self.func(self._instance, *args, **kwargs)
            return self.func(*args, **kwargs)  # type:ignore[misc]
        except Exception:
            self.invocation_exception_count += 1
            raise

    async def invoke(
        self,
        *,
        arguments: BaseModel | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Run the AI function with the provided arguments as a Pydantic model.

        The raw return value of the wrapped function is automatically parsed into a ``str``
        (either plain text or serialized JSON) using :meth:`parse_result` or the custom
        ``result_parser`` if one was provided.

        Keyword Args:
            arguments: A mapping or model instance containing the arguments for the function.
            kwargs: Keyword arguments to pass to the function, will not be used if ``arguments`` is provided.

        Returns:
            The parsed result as a string — either plain text or serialized JSON.

        Raises:
            TypeError: If arguments is not mapping-like or fails schema checks.
        """
        if self.declaration_only:
            raise ToolException(f"Function '{self.name}' is declaration only and cannot be invoked.")
        global OBSERVABILITY_SETTINGS
        from .observability import OBSERVABILITY_SETTINGS

        parser = self.result_parser or FunctionTool.parse_result

        original_kwargs = dict(kwargs)
        tool_call_id = original_kwargs.pop("tool_call_id", None)
        if arguments is not None:
            try:
                if isinstance(arguments, Mapping):
                    parsed_arguments = dict(arguments)
                    if self.input_model is not None and not self._schema_supplied:
                        parsed_arguments = self.input_model.model_validate(parsed_arguments).model_dump(
                            exclude_none=True
                        )
                elif isinstance(arguments, BaseModel):
                    if (
                        self.input_model is not None
                        and not self._schema_supplied
                        and not isinstance(arguments, self.input_model)
                    ):
                        raise TypeError(f"Expected {self.input_model.__name__}, got {type(arguments).__name__}")
                    parsed_arguments = arguments.model_dump(exclude_none=True)
                else:
                    raise TypeError(
                        f"Expected mapping-like arguments for tool '{self.name}', got {type(arguments).__name__}"
                    )
            except ValidationError as exc:
                raise TypeError(f"Invalid arguments for '{self.name}': {exc}") from exc
            kwargs = _validate_arguments_against_schema(
                arguments=parsed_arguments,
                schema=self.parameters(),
                tool_name=self.name,
            )
            if getattr(self, "_forward_runtime_kwargs", False) and original_kwargs:
                kwargs.update(original_kwargs)
        else:
            kwargs = original_kwargs
        if not OBSERVABILITY_SETTINGS.ENABLED:  # type: ignore[name-defined]
            logger.info(f"Function name: {self.name}")
            logger.debug(f"Function arguments: {kwargs}")
            res = self.__call__(**kwargs)
            result = await res if inspect.isawaitable(res) else res
            try:
                parsed = parser(result)
            except Exception:
                logger.warning(f"Function {self.name}: result parser failed, falling back to str().")
                parsed = str(result)
            logger.info(f"Function {self.name} succeeded.")
            logger.debug(f"Function result: {parsed or 'None'}")
            return parsed

        attributes = get_function_span_attributes(self, tool_call_id=tool_call_id)
        # Filter out framework kwargs that are not JSON serializable.
        serializable_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k
            not in {
                "chat_options",
                "tools",
                "tool_choice",
                "session",
                "conversation_id",
                "options",
                "response_format",
            }
        }
        if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:  # type: ignore[name-defined]
            attributes.update({
                OtelAttr.TOOL_ARGUMENTS: (
                    json.dumps(serializable_kwargs, default=str, ensure_ascii=False) if serializable_kwargs else "None"
                )
            })
        with get_function_span(attributes=attributes) as span:
            attributes[OtelAttr.MEASUREMENT_FUNCTION_TAG_NAME] = self.name
            logger.info(f"Function name: {self.name}")
            if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:  # type: ignore[name-defined]
                logger.debug(f"Function arguments: {serializable_kwargs}")
            start_time_stamp = perf_counter()
            end_time_stamp: float | None = None
            try:
                res = self.__call__(**kwargs)
                result = await res if inspect.isawaitable(res) else res
                end_time_stamp = perf_counter()
            except Exception as exception:
                end_time_stamp = perf_counter()
                attributes[OtelAttr.ERROR_TYPE] = type(exception).__name__
                capture_exception(span=span, exception=exception, timestamp=time_ns())
                logger.error(f"Function failed. Error: {exception}")
                raise
            else:
                try:
                    parsed = parser(result)
                except Exception:
                    logger.warning(f"Function {self.name}: result parser failed, falling back to str().")
                    parsed = str(result)
                logger.info(f"Function {self.name} succeeded.")
                if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:  # type: ignore[name-defined]
                    span.set_attribute(OtelAttr.TOOL_RESULT, parsed)
                    logger.debug(f"Function result: {parsed}")
                return parsed
            finally:
                duration = (end_time_stamp or perf_counter()) - start_time_stamp
                span.set_attribute(OtelAttr.MEASUREMENT_FUNCTION_INVOCATION_DURATION, duration)
                self._invocation_duration_histogram.record(duration, attributes=attributes)
                logger.info("Function duration: %fs", duration)

    @property
    def _input_schema(self) -> dict[str, Any]:
        """Get the input schema, generating it lazily if needed."""
        if self._input_schema_cached is None:
            if self.input_model is not None:
                # Try to rebuild the model in case it has forward references
                with suppress(Exception):
                    self.input_model.model_rebuild(force=True, raise_errors=False)
                self._input_schema_cached = self.input_model.model_json_schema()
            else:
                self._input_schema_cached = {}
        return self._input_schema_cached

    def parameters(self) -> dict[str, Any]:
        """Create the JSON schema of the parameters.

        Returns:
            A dictionary containing the JSON schema for the function's parameters.
            The result is cached after the first call for performance.
        """
        if self._cached_parameters is None:
            self._cached_parameters = self._input_schema
        return self._cached_parameters

    @staticmethod
    def _make_dumpable(value: Any) -> Any:
        """Recursively convert a value to a JSON-dumpable form."""
        from ._types import Content

        if isinstance(value, list):
            return [FunctionTool._make_dumpable(item) for item in value]
        if isinstance(value, dict):
            return {k: FunctionTool._make_dumpable(v) for k, v in value.items()}
        if isinstance(value, Content):
            return value.to_dict(exclude={"raw_representation", "additional_properties"})
        if isinstance(value, BaseModel):
            return value.model_dump()
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if hasattr(value, "text") and isinstance(value.text, str):
            return value.text
        return value

    @staticmethod
    def parse_result(result: Any) -> str:
        """Convert a raw function return value to a string representation.

        The return value is always a ``str`` — either plain text or serialized JSON.
        This is called automatically by :meth:`invoke` before returning the result,
        ensuring that the result stored in ``Content.from_function_result`` is
        already in a form that can be passed directly to LLM APIs.

        Args:
            result: The raw return value from the wrapped function.

        Returns:
            A string representation of the result, either plain text or serialized JSON.
        """
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        dumpable = FunctionTool._make_dumpable(result)
        if isinstance(dumpable, str):
            return dumpable
        return json.dumps(dumpable, default=str)

    def to_json_schema_spec(self) -> dict[str, Any]:
        """Convert a FunctionTool to the JSON Schema function specification format.

        Returns:
            A dictionary containing the function specification in JSON Schema format.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters(),
            },
        }

    @override
    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        as_dict = super().to_dict(exclude=exclude, exclude_none=exclude_none)
        if (exclude and "input_model" in exclude) or not self.input_model:
            return as_dict
        as_dict["input_model"] = self.parameters()  # Use cached parameters()
        return as_dict


ToolTypes: TypeAlias = FunctionTool | MCPTool | Mapping[str, Any] | Any


def normalize_tools(
    tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None,
) -> list[ToolTypes]:
    """Normalize tool inputs while preserving non-callable tool objects.

    Args:
        tools: A single tool or sequence of tools.

    Returns:
        A normalized list where callable inputs are converted to ``FunctionTool``
        using :func:`tool`, and existing tool objects are passed through unchanged.
    """
    if not tools:
        return []

    tool_items = (
        list(tools)
        if isinstance(tools, Sequence) and not isinstance(tools, (str, bytes, bytearray, Mapping))
        else [tools]
    )
    from ._mcp import MCPTool

    normalized: list[ToolTypes] = []
    for tool_item in tool_items:
        # check known types, these are also callable, so we need to do that first
        if isinstance(tool_item, (FunctionTool, Mapping, MCPTool)):
            normalized.append(tool_item)
            continue
        if callable(tool_item):
            normalized.append(tool(tool_item))
            continue
        normalized.append(tool_item)
    return normalized


def _tools_to_dict(
    tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None,
) -> list[str | dict[str, Any]] | None:
    """Parse the tools to a dict.

    Args:
        tools: The tools to parse. Can be a single tool or a sequence of tools.

    Returns:
        A list of tool specifications as dictionaries, or None if no tools provided.
    """
    normalized_tools = normalize_tools(tools)
    if not normalized_tools:
        return None

    results: list[str | dict[str, Any]] = []
    for tool_item in normalized_tools:
        if isinstance(tool_item, FunctionTool):
            results.append(tool_item.to_json_schema_spec())
            continue
        if isinstance(tool_item, SerializationMixin):
            results.append(tool_item.to_dict())
            continue
        if isinstance(tool_item, Mapping):
            results.append(dict(tool_item))
            continue
        logger.warning("Can't parse tool.")
    return results


# region AI Function Decorator


def _parse_annotation(annotation: Any) -> Any:
    """Parse a type annotation and return the corresponding type.

    If the second annotation (after the type) is a string, then we convert that to a Pydantic Field description.
    The rest are returned as-is, allowing for multiple annotations.

    Literal types are returned as-is to preserve their enum-like values.

    Args:
        annotation: The type annotation to parse.

    Returns:
        The parsed annotation, potentially wrapped in Annotated with a Field.
    """
    origin = get_origin(annotation)
    if origin is not None:
        # Literal types should be returned as-is - their args are the allowed values,
        # not type annotations to be parsed. For example, Literal["Data", "Security"]
        # has args ("Data", "Security") which are the valid string values.
        if origin is Literal:
            return annotation

        args = get_args(annotation)
        # For other generics, return the origin type (e.g., list for List[int])
        if len(args) > 1 and isinstance(args[1], str):
            # Create a new Annotated type with the updated Field
            args_list = list(args)
            if len(args_list) == 2:
                return Annotated[args_list[0], Field(description=args_list[1])]
            return Annotated[args_list[0], Field(description=args_list[1]), tuple(args_list[2:])]
    return annotation


def _matches_json_schema_type(value: Any, schema_type: str) -> bool:
    """Check a value against a simple JSON schema primitive type."""
    match schema_type:
        case "string":
            return isinstance(value, str)
        case "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        case "number":
            return (isinstance(value, int | float)) and not isinstance(value, bool)
        case "boolean":
            return isinstance(value, bool)
        case "array":
            return isinstance(value, list)
        case "object":
            return isinstance(value, dict)
        case "null":
            return value is None
        case _:
            return True


def _validate_arguments_against_schema(
    *,
    arguments: Mapping[str, Any],
    schema: Mapping[str, Any],
    tool_name: str,
) -> dict[str, Any]:
    """Run lightweight argument checks for schema-supplied tools."""
    parsed_arguments = dict(arguments)

    required_raw = schema.get("required", [])
    required_fields = [field for field in required_raw if isinstance(field, str)]
    missing_fields = [field for field in required_fields if field not in parsed_arguments]
    if missing_fields:
        raise TypeError(f"Missing required argument(s) for '{tool_name}': {', '.join(sorted(missing_fields))}")

    properties_raw = schema.get("properties")
    properties = properties_raw if isinstance(properties_raw, Mapping) else {}

    if schema.get("additionalProperties") is False:
        unexpected_fields = sorted(field for field in parsed_arguments if field not in properties)
        if unexpected_fields:
            raise TypeError(f"Unexpected argument(s) for '{tool_name}': {', '.join(unexpected_fields)}")

    for field_name, field_value in parsed_arguments.items():
        field_schema = properties.get(field_name)
        if not isinstance(field_schema, Mapping):
            continue

        enum_values = field_schema.get("enum")
        if isinstance(enum_values, list) and enum_values and field_value not in enum_values:
            raise TypeError(
                f"Invalid value for '{field_name}' in '{tool_name}': {field_value!r} is not in {enum_values!r}"
            )

        schema_type = field_schema.get("type")
        if isinstance(schema_type, str):
            if not _matches_json_schema_type(field_value, schema_type):
                raise TypeError(
                    f"Invalid type for '{field_name}' in '{tool_name}': "
                    f"expected {schema_type}, got {type(field_value).__name__}"
                )
            continue

        if isinstance(schema_type, list):
            allowed_types = [item for item in schema_type if isinstance(item, str)]
            if allowed_types and not any(_matches_json_schema_type(field_value, item) for item in allowed_types):
                raise TypeError(
                    f"Invalid type for '{field_name}' in '{tool_name}': expected one of "
                    f"{allowed_types}, got {type(field_value).__name__}"
                )

    return parsed_arguments


# Map JSON Schema types to Pydantic types
TYPE_MAPPING = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _build_pydantic_model_from_json_schema(
    model_name: str,
    schema: Mapping[str, Any],
) -> type[BaseModel]:
    """Creates a Pydantic model from JSON Schema with support for $refs, nested objects, and typed arrays.

    Args:
        model_name: The name of the model to be created.
        schema: The JSON Schema definition (should contain 'properties', 'required', '$defs', etc.).

    Returns:
        The dynamically created Pydantic model class.
    """
    properties = schema.get("properties")
    required = schema.get("required", [])
    definitions = schema.get("$defs", {})

    # Check if 'properties' is missing or not a dictionary
    if not properties:
        return create_model(f"{model_name}_input")

    def _resolve_literal_type(prop_details: dict[str, Any]) -> type | None:
        """Check if property should be a Literal type (const or enum).

        Args:
            prop_details: The JSON Schema property details

        Returns:
            Literal type if const or enum is present, None otherwise
        """
        # const → Literal["value"]
        if "const" in prop_details:
            return Literal[prop_details["const"]]  # type: ignore

        # enum → Literal["a", "b", ...]
        if "enum" in prop_details and isinstance(prop_details["enum"], list):
            enum_values = prop_details["enum"]
            if enum_values:
                return Literal[tuple(enum_values)]  # type: ignore

        return None

    def _resolve_type(prop_details: dict[str, Any], parent_name: str = "") -> type:
        """Resolve JSON Schema type to Python type, handling $ref, nested objects, and typed arrays.

        Args:
            prop_details: The JSON Schema property details
            parent_name: Name to use for creating nested models (for uniqueness)

        Returns:
            Python type annotation (could be int, str, list[str], or a nested Pydantic model)
        """
        # Handle oneOf + discriminator (polymorphic objects)
        if "oneOf" in prop_details and "discriminator" in prop_details:
            discriminator = prop_details["discriminator"]
            disc_field = discriminator.get("propertyName")

            variants = []
            for variant in prop_details["oneOf"]:
                if "$ref" in variant:
                    ref = variant["$ref"]
                    if ref.startswith("#/$defs/"):
                        def_name = ref.split("/")[-1]
                        resolved = definitions.get(def_name)
                        if resolved:
                            variant_model = _resolve_type(
                                resolved,
                                parent_name=f"{parent_name}_{def_name}",
                            )
                            variants.append(variant_model)

            if variants and disc_field:
                return Annotated[
                    Union[tuple(variants)],  # type: ignore
                    Field(discriminator=disc_field),
                ]

        # Handle $ref by resolving the reference
        if "$ref" in prop_details:
            ref = prop_details["$ref"]
            # Extract the reference path (e.g., "#/$defs/CustomerIdParam" -> "CustomerIdParam")
            if ref.startswith("#/$defs/"):
                def_name = ref.split("/")[-1]
                if def_name in definitions:
                    # Resolve the reference and use its type
                    resolved = definitions[def_name]
                    return _resolve_type(resolved, def_name)
            # If we can't resolve the ref, default to dict for safety
            return dict

        # Map JSON Schema types to Python types
        json_type = prop_details.get("type", "string")
        match json_type:
            case "integer":
                return int
            case "number":
                return float
            case "boolean":
                return bool
            case "array":
                # Handle typed arrays
                items_schema = prop_details.get("items")
                if items_schema and isinstance(items_schema, dict):
                    # Recursively resolve the item type
                    item_type = _resolve_type(items_schema, f"{parent_name}_item")
                    # Return list[ItemType] instead of bare list
                    return list[item_type]  # type: ignore
                # If no items schema or invalid, return bare list
                return list
            case "object":
                # Handle nested objects by creating a nested Pydantic model
                nested_properties = prop_details.get("properties")
                nested_required = prop_details.get("required", [])

                if nested_properties and isinstance(nested_properties, dict):
                    # Create the name for the nested model
                    nested_model_name = f"{parent_name}_nested" if parent_name else "NestedModel"

                    # Recursively build field definitions for the nested model
                    nested_field_definitions: dict[str, Any] = {}
                    for nested_prop_name, nested_prop_details in nested_properties.items():
                        nested_prop_details = (
                            json.loads(nested_prop_details)
                            if isinstance(nested_prop_details, str)
                            else nested_prop_details
                        )

                        # Check for Literal types first (const/enum)
                        literal_type = _resolve_literal_type(nested_prop_details)
                        if literal_type is not None:
                            nested_python_type = literal_type
                        else:
                            nested_python_type = _resolve_type(
                                nested_prop_details,
                                f"{nested_model_name}_{nested_prop_name}",
                            )
                        nested_description = nested_prop_details.get("description", "")

                        # Build field kwargs for nested property
                        nested_field_kwargs: dict[str, Any] = {}
                        if nested_description:
                            nested_field_kwargs["description"] = nested_description

                        # Create field definition
                        if nested_prop_name in nested_required:
                            nested_field_definitions[nested_prop_name] = (
                                (
                                    nested_python_type,
                                    Field(**nested_field_kwargs),
                                )
                                if nested_field_kwargs
                                else (nested_python_type, ...)
                            )
                        else:
                            nested_field_kwargs["default"] = nested_prop_details.get("default", None)
                            nested_field_definitions[nested_prop_name] = (
                                nested_python_type,
                                Field(**nested_field_kwargs),
                            )

                    # Create and return the nested Pydantic model
                    return create_model(nested_model_name, **nested_field_definitions)  # type: ignore

                # If no properties defined, return bare dict
                return dict
            case _:
                return str  # default

    field_definitions: dict[str, Any] = {}
    for prop_name, prop_details in properties.items():
        prop_details = json.loads(prop_details) if isinstance(prop_details, str) else prop_details

        # Check for Literal types first (const/enum)
        literal_type = _resolve_literal_type(prop_details)
        if literal_type is not None:
            python_type = literal_type
        else:
            python_type = _resolve_type(prop_details, f"{model_name}_{prop_name}")
        description = prop_details.get("description", "")

        # Build field kwargs (description, etc.)
        field_kwargs: dict[str, Any] = {}
        if description:
            field_kwargs["description"] = description

        # Create field definition for create_model
        if prop_name in required:
            if field_kwargs:
                field_definitions[prop_name] = (python_type, Field(**field_kwargs))
            else:
                field_definitions[prop_name] = (python_type, ...)
        else:
            default_value = prop_details.get("default", None)
            field_kwargs["default"] = default_value
            if field_kwargs and any(k != "default" for k in field_kwargs):
                field_definitions[prop_name] = (python_type, Field(**field_kwargs))
            else:
                field_definitions[prop_name] = (python_type, default_value)

    return create_model(f"{model_name}_input", **field_definitions)


def _create_model_from_json_schema(tool_name: str, schema_json: Mapping[str, Any]) -> type[BaseModel]:
    """Creates a Pydantic model from a given JSON Schema.

    Args:
      tool_name: The name of the model to be created.
      schema_json: The JSON Schema definition.

    Returns:
      The dynamically created Pydantic model class.
    """
    # Validate that 'properties' exists and is a dict
    if "properties" not in schema_json or not isinstance(schema_json["properties"], dict):
        raise ValueError(
            f"JSON schema for tool '{tool_name}' must contain a 'properties' key of type dict. "
            f"Got: {schema_json.get('properties', None)}"
        )

    return _build_pydantic_model_from_json_schema(tool_name, schema_json)


@overload
def tool(
    func: Callable[..., Any],
    *,
    name: str | None = None,
    description: str | None = None,
    schema: type[BaseModel] | Mapping[str, Any] | None = None,
    approval_mode: Literal["always_require", "never_require"] | None = None,
    max_invocations: int | None = None,
    max_invocation_exceptions: int | None = None,
    additional_properties: dict[str, Any] | None = None,
    result_parser: Callable[[Any], str] | None = None,
) -> FunctionTool: ...


@overload
def tool(
    func: None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    schema: type[BaseModel] | Mapping[str, Any] | None = None,
    approval_mode: Literal["always_require", "never_require"] | None = None,
    max_invocations: int | None = None,
    max_invocation_exceptions: int | None = None,
    additional_properties: dict[str, Any] | None = None,
    result_parser: Callable[[Any], str] | None = None,
) -> Callable[[Callable[..., Any]], FunctionTool]: ...


def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    schema: type[BaseModel] | Mapping[str, Any] | None = None,
    approval_mode: Literal["always_require", "never_require"] | None = None,
    max_invocations: int | None = None,
    max_invocation_exceptions: int | None = None,
    additional_properties: dict[str, Any] | None = None,
    result_parser: Callable[[Any], str] | None = None,
) -> FunctionTool | Callable[[Callable[..., Any]], FunctionTool]:
    """Decorate a function to turn it into a FunctionTool that can be passed to models and executed automatically.

    This decorator creates a Pydantic model from the function's signature,
    which will be used to validate the arguments passed to the function
    and to generate the JSON schema for the function's parameters.

    To add descriptions to parameters, use the ``Annotated`` type from ``typing``
    with a string description as the second argument. You can also use Pydantic's
    ``Field`` class for more advanced configuration.

    Alternatively, you can provide an explicit schema via the ``schema`` parameter
    to bypass automatic inference from the function signature.

    Args:
        func: The function to decorate. This parameter enables the decorator to be used
            both with and without parentheses: ``@tool`` directly decorates the function,
            while ``@tool()`` or ``@tool(name="custom")`` returns a decorator. For
            declaration-only tools (no implementation), use :class:`FunctionTool` directly
            with ``func=None``—see the example below.

    Keyword Args:
        name: The name of the function. If not provided, the function's ``__name__``
            attribute will be used.
        description: A description of the function. If not provided, the function's
            docstring will be used.
        schema: An explicit input schema for the function. This can be a Pydantic
            ``BaseModel`` subclass or a JSON schema dictionary (``Mapping[str, Any]``).
            When a dictionary is provided, it must be a flat object schema with a
            ``properties`` key (complex JSON Schema features such as ``oneOf``,
            ``$ref``, or nested compositions are not supported).
            When provided, the schema is used instead of inferring one from the
            function's signature. Defaults to ``None`` (infer from signature).
        approval_mode: Whether or not approval is required to run this tool.
            Default is that approval is NOT required (``"never_require"``).
        max_invocations: The maximum number of times this function can be invoked
            across the **lifetime of this tool instance**. If None (default), there is
            no limit. Should be at least 1. For per-request limits, use
            ``FunctionInvocationConfiguration["max_function_calls"]`` instead.
        max_invocation_exceptions: The maximum number of exceptions allowed during invocations.
            If None, there is no limit, should be at least 1.
        additional_properties: Additional properties to set on the function.
        result_parser: An optional callable with signature ``Callable[[Any], str]`` that
            overrides the default result parsing. When provided, this callable converts the
            raw function return value to a string instead of using the built-in
            :meth:`FunctionTool.parse_result`. Depending on your function, it may be
            easiest to just do the serialization directly in the function body rather
            than providing a custom ``result_parser``.

    Note:
        When approval_mode is set to "always_require", the function will not be executed
        until explicit approval is given, this only applies to the auto-invocation flow.
        It is also important to note that if the model returns multiple function calls, some that require approval
        and others that do not, it will ask approval for all of them.

    Example:

        .. code-block:: python

            from agent_framework import tool
            from typing import Annotated


            @tool(approval_mode="never_require")
            def tool_example(
                arg1: Annotated[str, "The first argument"],
                arg2: Annotated[int, "The second argument"],
            ) -> str:
                # An example function that takes two arguments and returns a string.
                return f"arg1: {arg1}, arg2: {arg2}"


            # the same function but with approval required to run
            @tool(approval_mode="always_require")
            def tool_example(
                arg1: Annotated[str, "The first argument"],
                arg2: Annotated[int, "The second argument"],
            ) -> str:
                # An example function that takes two arguments and returns a string.
                return f"arg1: {arg1}, arg2: {arg2}"


            # With custom name and description
            @tool(name="custom_weather", description="Custom weather function")
            def another_weather_func(location: str) -> str:
                return f"Weather in {location}"


            # Async functions are also supported
            @tool(approval_mode="never_require")
            async def async_get_weather(location: str) -> str:
                '''Get weather asynchronously.'''
                # Simulate async operation
                return f"Weather in {location}"


            # With an explicit Pydantic model schema
            from pydantic import BaseModel, Field


            class WeatherInput(BaseModel):
                location: Annotated[str, Field(description="City name")]
                unit: str = "celsius"


            @tool(schema=WeatherInput)
            def get_weather(location: str, unit: str = "celsius") -> str:
                '''Get weather for a location.'''
                return f"Weather in {location}: 22 {unit}"


            # Declaration-only tool (no implementation)
            # Use FunctionTool directly when you need a tool declaration without
            # an executable function. The agent can request this tool, but it won't
            # be executed automatically. Useful for testing agent reasoning or when
            # the implementation is handled externally (e.g., client-side rendering).
            from agent_framework import FunctionTool

            declaration_only_tool = FunctionTool(
                name="get_current_time",
                description="Get the current time in ISO 8601 format.",
                func=None,  # Explicitly no implementation - makes declaration_only=True
            )

    """

    def decorator(func: Callable[..., Any]) -> FunctionTool:
        @wraps(func)
        def wrapper(f: Callable[..., Any]) -> FunctionTool:
            tool_name: str = name or getattr(f, "__name__", "unknown_function")  # type: ignore[assignment]
            tool_desc: str = description or (f.__doc__ or "")
            return FunctionTool(
                name=tool_name,
                description=tool_desc,
                approval_mode=approval_mode,
                max_invocations=max_invocations,
                max_invocation_exceptions=max_invocation_exceptions,
                additional_properties=additional_properties or {},
                func=f,
                input_model=schema,
                result_parser=result_parser,
            )

        return wrapper(func)

    return decorator(func) if func else decorator


# region Function Invoking Chat Client


class FunctionInvocationConfiguration(TypedDict, total=False):
    """Configuration for function invocation in chat clients.

    The configuration controls the tool execution loop that runs when the model
    requests function calls. Key settings:

    - ``enabled``: Master switch for the function invocation loop.
    - ``max_iterations``: Limits the number of **LLM roundtrips** (iterations).
      Each iteration may execute one or more function calls in parallel, so
      this does *not* directly limit the total number of function executions.
    - ``max_function_calls``: Limits the **total number of individual function
      invocations** across all iterations within a single request. This is the
      primary knob for controlling cost and preventing runaway tool usage. When
      the limit is reached, the loop stops invoking tools and forces the model
      to produce a text response. Default is ``None`` (unlimited).

      This is a **best-effort** limit: it is checked *after* each batch of
      parallel tool calls completes, not before. If the model requests 20
      parallel calls in a single iteration and the limit is 10, all 20 will
      execute before the loop stops.
    - ``max_consecutive_errors_per_request``: How many consecutive errors
      before abandoning the tool loop for this request.
    - ``terminate_on_unknown_calls``: Whether to raise an error when the model
      requests a function that is not in the tool map.
    - ``additional_tools``: Extra tools available during execution but not
      advertised to the model in the tool list.
    - ``include_detailed_errors``: Whether to include exception details in the
      function result returned to the model.

    Note:
        ``max_iterations`` and ``max_function_calls`` serve complementary purposes.
        ``max_iterations`` caps the number of model round-trips regardless of how
        many tools are called per trip. ``max_function_calls`` caps the cumulative
        number of individual tool executions regardless of how they are distributed
        across iterations.

    Example:
        .. code-block:: python

            from agent_framework.openai import OpenAIChatClient

            client = OpenAIChatClient(api_key="your_api_key")

            # Limit to 5 LLM roundtrips and 20 total function executions
            client.function_invocation_configuration["max_iterations"] = 5
            client.function_invocation_configuration["max_function_calls"] = 20
    """

    enabled: bool
    max_iterations: int
    max_function_calls: int | None
    max_consecutive_errors_per_request: int
    terminate_on_unknown_calls: bool
    additional_tools: Sequence[FunctionTool]
    include_detailed_errors: bool


def normalize_function_invocation_configuration(
    config: FunctionInvocationConfiguration | None,
) -> FunctionInvocationConfiguration:
    normalized: FunctionInvocationConfiguration = {
        "enabled": True,
        "max_iterations": DEFAULT_MAX_ITERATIONS,
        "max_function_calls": None,
        "max_consecutive_errors_per_request": DEFAULT_MAX_CONSECUTIVE_ERRORS_PER_REQUEST,
        "terminate_on_unknown_calls": False,
        "additional_tools": [],
        "include_detailed_errors": False,
    }
    if config:
        normalized.update(config)
    if normalized["max_iterations"] < 1:
        raise ValueError("max_iterations must be at least 1.")
    if normalized["max_function_calls"] is not None and normalized["max_function_calls"] < 1:
        raise ValueError("max_function_calls must be at least 1 or None.")
    if normalized["max_consecutive_errors_per_request"] < 0:
        raise ValueError("max_consecutive_errors_per_request must be 0 or more.")
    if normalized["additional_tools"] is None:
        normalized["additional_tools"] = []
    return normalized


async def _auto_invoke_function(
    function_call_content: Content,
    custom_args: dict[str, Any] | None = None,
    *,
    config: FunctionInvocationConfiguration,
    tool_map: dict[str, FunctionTool],
    sequence_index: int | None = None,
    request_index: int | None = None,
    middleware_pipeline: FunctionMiddlewarePipeline | None = None,  # Optional MiddlewarePipeline
) -> Content:
    """Invoke a function call requested by the agent, applying middleware that is defined.

    Args:
        function_call_content: The function call content from the model.
        custom_args: Additional custom arguments to merge with parsed arguments.

    Keyword Args:
        config: The function invocation configuration.
        tool_map: A mapping of tool names to FunctionTool instances.
        sequence_index: The index of the function call in the sequence.
        request_index: The index of the request iteration.
        middleware_pipeline: Optional middleware pipeline to apply during execution.

    Returns:
        The function result content.

    Raises:
        KeyError: If the requested function is not found in the tool map.
        MiddlewareTermination: If middleware requests loop termination.
    """
    from ._types import Content

    # Note: The scenarios for approval_mode="always_require", declaration_only, and
    # terminate_on_unknown_calls are all handled in _try_execute_function_calls before
    # this function is called. This function only handles the actual execution of approved,
    # non-declaration-only functions.

    tool: FunctionTool | None = None
    if function_call_content.type == "function_call":
        tool = tool_map.get(function_call_content.name)  # type: ignore[arg-type]
        # Tool should exist because _try_execute_function_calls validates this
        if tool is None:
            exc = KeyError(f'Function "{function_call_content.name}" not found.')
            return Content.from_function_result(
                call_id=function_call_content.call_id,  # type: ignore[arg-type]
                result=f'Error: Requested function "{function_call_content.name}" not found.',
                exception=str(exc),  # type: ignore[arg-type]
            )
    else:
        # Note: Unapproved tools (approved=False) are handled in _replace_approval_contents_with_results
        # and never reach this function, so we only handle approved=True cases here.
        inner_call = function_call_content.function_call  # type: ignore[attr-defined]
        if inner_call.type != "function_call":  # type: ignore[union-attr]
            return function_call_content
        tool = tool_map.get(inner_call.name)  # type: ignore[attr-defined, union-attr, arg-type]
        if tool is None:
            # we assume it is a hosted tool
            return function_call_content
        function_call_content = inner_call  # type: ignore[assignment]

    parsed_args: dict[str, Any] = dict(function_call_content.parse_arguments() or {})

    # Filter out internal framework kwargs before passing to tools.
    # conversation_id is an internal tracking ID that should not be forwarded to tools.
    runtime_kwargs: dict[str, Any] = {
        key: value
        for key, value in (custom_args or {}).items()
        if key not in {"_function_middleware_pipeline", "middleware", "conversation_id"}
    }
    try:
        if not tool._schema_supplied and tool.input_model is not None:
            args = tool.input_model.model_validate(parsed_args).model_dump(exclude_none=True)
        else:
            args = dict(parsed_args)
        args = _validate_arguments_against_schema(
            arguments=args,
            schema=tool.parameters(),
            tool_name=tool.name,
        )
    except (TypeError, ValidationError) as exc:
        message = "Error: Argument parsing failed."
        if config["include_detailed_errors"]:
            message = f"{message} Exception: {exc}"
        return Content.from_function_result(
            call_id=function_call_content.call_id,  # type: ignore[arg-type]
            result=message,
            exception=str(exc),  # type: ignore[arg-type]
        )

    if middleware_pipeline is None or not middleware_pipeline.has_middlewares:
        # No middleware - execute directly
        try:
            function_result = await tool.invoke(
                arguments=args,
                tool_call_id=function_call_content.call_id,
                **runtime_kwargs if getattr(tool, "_forward_runtime_kwargs", False) else {},
            )
            return Content.from_function_result(
                call_id=function_call_content.call_id,  # type: ignore[arg-type]
                result=function_result,
            )
        except Exception as exc:
            message = "Error: Function failed."
            if config["include_detailed_errors"]:
                message = f"{message} Exception: {exc}"
            return Content.from_function_result(
                call_id=function_call_content.call_id,  # type: ignore[arg-type]
                result=message,
                exception=str(exc),
            )
    # Execute through middleware pipeline if available
    from ._middleware import FunctionInvocationContext

    middleware_context = FunctionInvocationContext(
        function=tool,
        arguments=args,
        kwargs=runtime_kwargs.copy(),
    )

    async def final_function_handler(context_obj: Any) -> Any:
        return await tool.invoke(
            arguments=context_obj.arguments,
            tool_call_id=function_call_content.call_id,
            **context_obj.kwargs if getattr(tool, "_forward_runtime_kwargs", False) else {},
        )

    from ._middleware import MiddlewareTermination

    # MiddlewareTermination bubbles up to signal loop termination
    try:
        function_result = await middleware_pipeline.execute(middleware_context, final_function_handler)
        return Content.from_function_result(
            call_id=function_call_content.call_id,  # type: ignore[arg-type]
            result=function_result,
        )
    except MiddlewareTermination as term_exc:
        # Re-raise to signal loop termination, but first capture any result set by middleware
        if middleware_context.result is not None:
            # Store result in exception for caller to extract
            term_exc.result = Content.from_function_result(
                call_id=function_call_content.call_id,  # type: ignore[arg-type]
                result=middleware_context.result,
            )
        raise
    except Exception as exc:
        message = "Error: Function failed."
        if config["include_detailed_errors"]:
            message = f"{message} Exception: {exc}"
        return Content.from_function_result(
            call_id=function_call_content.call_id,  # type: ignore[arg-type]
            result=message,
            exception=str(exc),  # type: ignore[arg-type]
        )


def _get_tool_map(
    tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]],
) -> dict[str, FunctionTool]:
    tool_list: dict[str, FunctionTool] = {}
    for tool_item in normalize_tools(tools):
        if isinstance(tool_item, FunctionTool):
            tool_list[tool_item.name] = tool_item
    return tool_list


async def _try_execute_function_calls(
    custom_args: dict[str, Any],
    attempt_idx: int,
    function_calls: Sequence[Content],
    tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]],
    config: FunctionInvocationConfiguration,
    middleware_pipeline: Any = None,  # Optional MiddlewarePipeline to avoid circular imports
) -> tuple[Sequence[Content], bool]:
    """Execute multiple function calls concurrently.

    Args:
        custom_args: Custom arguments to pass to each function.
        attempt_idx: The index of the current attempt iteration.
        function_calls: A sequence of FunctionCallContent to execute.
        tools: The tools available for execution.
        config: Configuration for function invocation.
        middleware_pipeline: Optional middleware pipeline to apply during execution.

    Returns:
        A tuple of:
        - A list of Content containing the results of each function call,
          or the approval requests if any function requires approval,
          or the original function calls if any are declaration only.
        - Always False; termination via middleware is no longer supported.
    """
    from ._types import Content

    tool_map = _get_tool_map(tools)
    approval_tools = [tool_name for tool_name, tool in tool_map.items() if tool.approval_mode == "always_require"]
    logger.debug(
        "_try_execute_function_calls: tool_map keys=%s, approval_tools=%s",
        list(tool_map.keys()),
        approval_tools,
    )
    declaration_only = [tool_name for tool_name, tool in tool_map.items() if tool.declaration_only]
    additional_tool_names = [tool.name for tool in config["additional_tools"]] if config["additional_tools"] else []
    # check if any are calling functions that need approval
    # if so, we return approval request for all
    approval_needed = False
    declaration_only_flag = False
    for fcc in function_calls:
        fcc_name = getattr(fcc, "name", None)
        logger.debug(
            "Checking function call: type=%s, name=%s, in approval_tools=%s",
            fcc.type,
            fcc_name,
            fcc_name in approval_tools,
        )
        if fcc.type == "function_call" and fcc.name in approval_tools:  # type: ignore[attr-defined]
            logger.debug("Approval needed for function: %s", fcc.name)
            approval_needed = True
            break
        if fcc.type == "function_call" and (fcc.name in declaration_only or fcc.name in additional_tool_names):  # type: ignore[attr-defined]
            declaration_only_flag = True
            break
        if (
            config["terminate_on_unknown_calls"] and fcc.type == "function_call" and fcc.name not in tool_map  # type: ignore[attr-defined]
        ):
            raise KeyError(f'Error: Requested function "{fcc.name}" not found.')  # type: ignore[attr-defined]
    if approval_needed:
        # approval can only be needed for Function Call Content, not Approval Responses.
        logger.debug("Returning function_approval_request contents")
        return (
            [
                Content.from_function_approval_request(id=fcc.call_id, function_call=fcc)  # type: ignore[attr-defined, arg-type]
                for fcc in function_calls
                if fcc.type == "function_call"
            ],
            False,
        )
    if declaration_only_flag:
        # return the declaration only tools to the user, since we cannot execute them.
        # Mark as user_input_request so AgentExecutor emits request_info events and pauses the workflow.
        declaration_only_calls = []
        for fcc in function_calls:
            if fcc.type == "function_call":
                fcc.user_input_request = True
                fcc.id = fcc.call_id
                declaration_only_calls.append(fcc)
        return (declaration_only_calls, False)

    # Run all function calls concurrently, handling MiddlewareTermination
    from ._middleware import MiddlewareTermination

    async def invoke_with_termination_handling(
        function_call: Content,
        seq_idx: int,
    ) -> tuple[Content, bool]:
        """Invoke function and catch MiddlewareTermination, returning (result, should_terminate)."""
        try:
            result = await _auto_invoke_function(
                function_call_content=function_call,  # type: ignore[arg-type]
                custom_args=custom_args,
                tool_map=tool_map,
                sequence_index=seq_idx,
                request_index=attempt_idx,
                middleware_pipeline=middleware_pipeline,
                config=config,
            )
            return (result, False)
        except MiddlewareTermination as exc:
            # Middleware requested termination - return result as Content
            # exc.result may already be a Content (set by _auto_invoke_function) or raw value
            if isinstance(exc.result, Content):
                return (exc.result, True)
            result_content = Content.from_function_result(
                call_id=function_call.call_id,  # type: ignore[arg-type]
                result=exc.result,
            )
            return (result_content, True)

    execution_results = await asyncio.gather(*[
        invoke_with_termination_handling(function_call, seq_idx) for seq_idx, function_call in enumerate(function_calls)
    ])

    # Unpack results - each is (Content, terminate_flag)
    contents: list[Content] = [result[0] for result in execution_results]
    # If any function requested termination, terminate the loop
    should_terminate = any(result[1] for result in execution_results)
    return (contents, should_terminate)


async def _execute_function_calls(
    *,
    custom_args: dict[str, Any],
    attempt_idx: int,
    function_calls: list[Content],
    tool_options: dict[str, Any] | None,
    config: FunctionInvocationConfiguration,
    middleware_pipeline: Any = None,
) -> tuple[list[Content], bool, bool]:
    tools = _extract_tools(tool_options)
    if not tools:
        return [], False, False
    results, should_terminate = await _try_execute_function_calls(
        custom_args=custom_args,
        attempt_idx=attempt_idx,
        function_calls=function_calls,
        tools=tools,  # type: ignore
        middleware_pipeline=middleware_pipeline,
        config=config,
    )
    had_errors = any(fcr.exception is not None for fcr in results if fcr.type == "function_result")
    return list(results), should_terminate, had_errors


def _update_conversation_id(
    kwargs: dict[str, Any],
    conversation_id: str | None,
    options: dict[str, Any] | None = None,
) -> None:
    """Update kwargs and options with conversation id.

    Args:
        kwargs: The keyword arguments dictionary to update.
        conversation_id: The conversation ID to set, or None to skip.
        options: Optional options dictionary to also update with conversation_id.
    """
    if conversation_id is None:
        return
    if "chat_options" in kwargs:
        kwargs["chat_options"].conversation_id = conversation_id
    else:
        kwargs["conversation_id"] = conversation_id

    # Also update options since some clients (e.g., AssistantsClient) read conversation_id from options
    if options is not None:
        options["conversation_id"] = conversation_id


async def _ensure_response_stream(
    stream_like: ResponseStream[Any, Any] | Awaitable[ResponseStream[Any, Any]],
) -> ResponseStream[Any, Any]:
    from ._types import ResponseStream

    stream = await stream_like if isinstance(stream_like, Awaitable) else stream_like
    if not isinstance(stream, ResponseStream):
        raise ValueError("Streaming function invocation requires a ResponseStream result.")
    if getattr(stream, "_stream", None) is None:
        await stream
    return stream


def _extract_tools(
    options: dict[str, Any] | None,
) -> ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None:
    """Extract tools from options dict.

    Args:
        options: The options dict containing chat options.

    Returns:
        ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None
    """
    if options and isinstance(options, dict):
        return options.get("tools")
    return None


def _is_hosted_tool_approval(content: Any) -> bool:
    """Check if a function_approval_request/response is for a hosted tool (e.g. MCP).

    Hosted tool approvals have a server_label in function_call.additional_properties
    and should be passed through to the API untouched rather than processed locally.
    """
    fc = getattr(content, "function_call", None)
    if fc is None:
        return False
    ap = getattr(fc, "additional_properties", None)
    return bool(ap and ap.get("server_label"))


def _collect_approval_responses(
    messages: list[Message],
) -> dict[str, Content]:
    """Collect approval responses (both approved and rejected) from messages.

    Hosted tool approvals (e.g. MCP) are excluded because they must be
    forwarded to the API as-is rather than processed locally.
    """
    from ._types import Message

    fcc_todo: dict[str, Content] = {}
    for msg in messages:
        for content in msg.contents if isinstance(msg, Message) else []:
            # Collect BOTH approved and rejected responses, but skip hosted tool approvals
            if content.type == "function_approval_response" and not _is_hosted_tool_approval(content):
                fcc_todo[content.id] = content  # type: ignore[attr-defined, index]
    return fcc_todo


def _replace_approval_contents_with_results(
    messages: list[Message],
    fcc_todo: dict[str, Content],
    approved_function_results: list[Content],
) -> None:
    """Replace approval request/response contents with function call/result contents in-place."""
    from ._types import (
        Content,
    )

    result_idx = 0
    for msg in messages:
        # First pass - collect existing function call IDs to avoid duplicates
        existing_call_ids = {
            content.call_id  # type: ignore[union-attr, operator]
            for content in msg.contents
            if content.type == "function_call" and content.call_id  # type: ignore[attr-defined]
        }

        # Track approval requests that should be removed (duplicates)
        contents_to_remove = []

        for content_idx, content in enumerate(msg.contents):
            if content.type == "function_approval_request":
                # Skip hosted tool approvals — they must pass through to the API unchanged
                if _is_hosted_tool_approval(content):
                    continue
                # Don't add the function call if it already exists (would create duplicate)
                if content.function_call.call_id in existing_call_ids:  # type: ignore[attr-defined, union-attr, operator]
                    # Just mark for removal - the function call already exists
                    contents_to_remove.append(content_idx)
                else:
                    # Put back the function call content only if it doesn't exist
                    msg.contents[content_idx] = content.function_call  # type: ignore[attr-defined, assignment]
            elif content.type == "function_approval_response":
                # Skip hosted tool approvals — they must pass through to the API unchanged
                if _is_hosted_tool_approval(content):
                    continue
                if content.approved and content.id in fcc_todo:  # type: ignore[attr-defined]
                    # Replace with the corresponding result
                    if result_idx < len(approved_function_results):
                        msg.contents[content_idx] = approved_function_results[result_idx]
                        result_idx += 1
                        msg.role = "tool"
                else:
                    # Create a "not approved" result for rejected calls
                    # Use function_call.call_id (the function's ID), not content.id (approval's ID)
                    msg.contents[content_idx] = Content.from_function_result(
                        call_id=content.function_call.call_id,  # type: ignore[union-attr, arg-type]
                        result="Error: Tool call invocation was rejected by user.",
                    )
                    msg.role = "tool"

        # Remove approval requests that were duplicates (in reverse order to preserve indices)
        for idx in reversed(contents_to_remove):
            msg.contents.pop(idx)


def _get_result_hooks_from_stream(stream: Any) -> list[Callable[[Any], Any]]:
    inner_stream = getattr(stream, "_inner_stream", None)
    if inner_stream is None:
        inner_source = getattr(stream, "_inner_stream_source", None)
        if inner_source is not None:
            inner_stream = inner_source
    if inner_stream is None:
        inner_stream = stream
    return list(getattr(inner_stream, "_result_hooks", []))


def _extract_function_calls(response: ChatResponse) -> list[Content]:
    function_results = {
        item.call_id
        for message in response.messages
        for item in message.contents
        if item.type == "function_result" and item.call_id
    }
    seen_call_ids: set[str] = set()
    function_calls: list[Content] = []
    for message in response.messages:
        for item in message.contents:
            if item.type != "function_call":
                continue
            if item.call_id and item.call_id in function_results:
                continue
            if item.call_id and item.call_id in seen_call_ids:
                continue
            if item.call_id:
                seen_call_ids.add(item.call_id)
            function_calls.append(item)
    return function_calls


def _prepend_fcc_messages(response: ChatResponse, fcc_messages: list[Message]) -> None:
    if not fcc_messages:
        return
    for msg in reversed(fcc_messages):
        response.messages.insert(0, msg)


class FunctionRequestResult(TypedDict, total=False):
    """Result of processing function requests.

    Attributes:
        action: The action to take ("return", "continue", or "stop").
        errors_in_a_row: The number of consecutive errors encountered.
        result_message: The message containing function call results, if any.
        update_role: The role to update for the next message, if any.
        function_call_results: The list of function call results, if any.
        function_call_count: The number of function calls executed in this processing step.
    """

    action: Literal["return", "continue", "stop"]
    errors_in_a_row: int
    result_message: Message | None
    update_role: Literal["assistant", "tool"] | None
    function_call_results: list[Content] | None
    function_call_count: int


def _handle_function_call_results(
    *,
    response: ChatResponse,
    function_call_results: list[Content],
    fcc_messages: list[Message],
    errors_in_a_row: int,
    had_errors: bool,
    max_errors: int,
) -> FunctionRequestResult:
    from ._types import Message

    if any(fccr.type in {"function_approval_request", "function_call"} for fccr in function_call_results):
        # Only add items that aren't already in the message (e.g. function_approval_request wrappers).
        # Declaration-only function_call items are already present from the LLM response.
        new_items = [fccr for fccr in function_call_results if fccr.type != "function_call"]
        if new_items:
            if response.messages and response.messages[0].role == "assistant":
                response.messages[0].contents.extend(new_items)
            else:
                response.messages.append(Message(role="assistant", contents=new_items))
        return {
            "action": "return",
            "errors_in_a_row": errors_in_a_row,
            "result_message": None,
            "update_role": "assistant",
            "function_call_results": None,
        }

    if had_errors:
        errors_in_a_row += 1
        reached_error_limit = errors_in_a_row >= max_errors
        if reached_error_limit:
            logger.warning(
                "Maximum consecutive function call errors reached (%d). "
                "Stopping further function calls for this request.",
                max_errors,
            )
    else:
        errors_in_a_row = 0
        reached_error_limit = False

    result_message = Message(role="tool", contents=function_call_results)
    response.messages.append(result_message)
    fcc_messages.extend(response.messages)
    return {
        "action": "stop" if reached_error_limit else "continue",
        "errors_in_a_row": errors_in_a_row,
        "result_message": result_message,
        "update_role": "tool",
        "function_call_results": None,
    }


async def _process_function_requests(
    *,
    response: ChatResponse | None,
    prepped_messages: list[Message] | None,
    tool_options: dict[str, Any] | None,
    attempt_idx: int,
    fcc_messages: list[Message] | None,
    errors_in_a_row: int,
    max_errors: int,
    execute_function_calls: Callable[..., Awaitable[tuple[list[Content], bool, bool]]],
) -> FunctionRequestResult:
    if prepped_messages is not None:
        fcc_todo = _collect_approval_responses(prepped_messages)
        if not fcc_todo:
            fcc_todo = {}
        if fcc_todo:
            approved_responses = [resp for resp in fcc_todo.values() if resp.approved]
            approved_function_results: list[Content] = []
            should_terminate = False
            if approved_responses:
                results, should_terminate, had_errors = await execute_function_calls(
                    attempt_idx=attempt_idx,
                    function_calls=approved_responses,
                    tool_options=tool_options,
                )
                approved_function_results = list(results)
                if had_errors:
                    errors_in_a_row += 1
                    if errors_in_a_row >= max_errors:
                        logger.warning(
                            "Maximum consecutive function call errors reached (%d). "
                            "Stopping further function calls for this request.",
                            max_errors,
                        )
            _replace_approval_contents_with_results(prepped_messages, fcc_todo, approved_function_results)
            executed_count = sum(1 for r in approved_function_results if r.type == "function_result")
            # Continue to call chat client with updated messages (containing function results)
            # so it can generate the final response
            return {
                "action": "return" if should_terminate else "continue",
                "errors_in_a_row": errors_in_a_row,
                "result_message": None,
                "update_role": None,
                "function_call_results": None,
                "function_call_count": executed_count,
            }

    if response is None or fcc_messages is None:
        return {
            "action": "continue",
            "errors_in_a_row": errors_in_a_row,
            "result_message": None,
            "update_role": None,
            "function_call_results": None,
            "function_call_count": 0,
        }

    tools = _extract_tools(tool_options)
    function_calls = _extract_function_calls(response)
    if not (function_calls and tools):
        _prepend_fcc_messages(response, fcc_messages)
        return {
            "action": "return",
            "errors_in_a_row": errors_in_a_row,
            "result_message": None,
            "update_role": None,
            "function_call_results": None,
            "function_call_count": 0,
        }

    function_call_results, should_terminate, had_errors = await execute_function_calls(
        attempt_idx=attempt_idx,
        function_calls=function_calls,
        tool_options=tool_options,
    )
    result = _handle_function_call_results(
        response=response,
        function_call_results=function_call_results,
        fcc_messages=fcc_messages,
        errors_in_a_row=errors_in_a_row,
        had_errors=had_errors,
        max_errors=max_errors,
    )
    result["function_call_results"] = list(function_call_results)
    result["function_call_count"] = sum(1 for r in function_call_results if r.type == "function_result")
    # If middleware requested termination, change action to return
    if should_terminate:
        result["action"] = "return"
    return result


OptionsCoT = TypeVar(
    "OptionsCoT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="ChatOptions[None]",
    covariant=True,
)


class FunctionInvocationLayer(Generic[OptionsCoT]):
    """Layer for chat clients to apply function invocation around get_response."""

    def __init__(
        self,
        *,
        function_middleware: Sequence[FunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        **kwargs: Any,
    ) -> None:
        self.function_middleware: list[FunctionMiddlewareTypes] = (
            list(function_middleware) if function_middleware else []
        )
        self.function_invocation_configuration = normalize_function_invocation_configuration(
            function_invocation_configuration
        )
        super().__init__(**kwargs)

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[ResponseModelBoundT],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[ResponseModelBoundT]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: OptionsCoT | ChatOptions[None] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: OptionsCoT | ChatOptions[Any] | None = None,
        **kwargs: Any,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        function_middleware: Sequence[FunctionMiddlewareTypes] | None = None,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        from ._middleware import FunctionMiddlewarePipeline
        from ._types import (
            ChatResponse,
            ChatResponseUpdate,
            ResponseStream,
        )

        super_get_response = super().get_response  # type: ignore[misc]

        # ChatMiddleware adds this kwarg
        function_middleware_pipeline = FunctionMiddlewarePipeline(
            *(self.function_middleware), *(function_middleware or [])
        )
        max_errors: int = self.function_invocation_configuration["max_consecutive_errors_per_request"]  # type: ignore[assignment]
        additional_function_arguments: dict[str, Any] = {}
        if options and (additional_opts := options.get("additional_function_arguments")):  # type: ignore[attr-defined]
            additional_function_arguments = additional_opts  # type: ignore
        execute_function_calls = partial(
            _execute_function_calls,
            custom_args=additional_function_arguments,
            config=self.function_invocation_configuration,
            middleware_pipeline=function_middleware_pipeline,
        )
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != "session"}

        # Make options mutable so we can update conversation_id during function invocation loop
        mutable_options: dict[str, Any] = dict(options) if options else {}
        # Remove additional_function_arguments from options passed to underlying chat client
        # It's for tool invocation only and not recognized by chat service APIs
        mutable_options.pop("additional_function_arguments", None)
        # Support tools passed via kwargs in direct client.get_response(...) calls.
        if "tools" in filtered_kwargs:
            if mutable_options.get("tools") is None:
                mutable_options["tools"] = filtered_kwargs["tools"]
            filtered_kwargs.pop("tools", None)

        if not stream:

            async def _get_response() -> ChatResponse:
                nonlocal mutable_options
                nonlocal filtered_kwargs
                errors_in_a_row: int = 0
                total_function_calls: int = 0
                max_function_calls: int | None = self.function_invocation_configuration.get("max_function_calls")
                prepped_messages = list(messages)
                fcc_messages: list[Message] = []
                response: ChatResponse | None = None

                for attempt_idx in range(
                    self.function_invocation_configuration["max_iterations"]
                    if self.function_invocation_configuration["enabled"]
                    else 0
                ):
                    approval_result = await _process_function_requests(
                        response=None,
                        prepped_messages=prepped_messages,
                        tool_options=mutable_options,  # type: ignore[arg-type]
                        attempt_idx=attempt_idx,
                        fcc_messages=None,
                        errors_in_a_row=errors_in_a_row,
                        max_errors=max_errors,
                        execute_function_calls=execute_function_calls,
                    )
                    if approval_result["action"] == "stop":
                        response = ChatResponse(messages=prepped_messages)
                        break
                    errors_in_a_row = approval_result["errors_in_a_row"]
                    total_function_calls += approval_result.get("function_call_count", 0)

                    response = await super_get_response(
                        messages=prepped_messages,
                        stream=False,
                        options=mutable_options,
                        **filtered_kwargs,
                    )

                    if response.conversation_id is not None:
                        _update_conversation_id(kwargs, response.conversation_id, mutable_options)
                        prepped_messages = []

                    result = await _process_function_requests(
                        response=response,
                        prepped_messages=None,
                        tool_options=mutable_options,  # type: ignore[arg-type]
                        attempt_idx=attempt_idx,
                        fcc_messages=fcc_messages,
                        errors_in_a_row=errors_in_a_row,
                        max_errors=max_errors,
                        execute_function_calls=execute_function_calls,
                    )
                    if result["action"] == "return":
                        return response
                    total_function_calls += result.get("function_call_count", 0)
                    if result["action"] == "stop":
                        # Error threshold reached: force a final non-tool turn so
                        # function_call_output items are submitted before exit.
                        mutable_options["tool_choice"] = "none"
                    elif (
                        max_function_calls is not None
                        and total_function_calls >= max_function_calls
                    ):
                        # Best-effort limit: checked after each batch of parallel calls completes,
                        # so the current batch always runs to completion even if it overshoots.
                        logger.info(
                            "Maximum function calls reached (%d/%d). "
                            "Stopping further function calls for this request.",
                            total_function_calls,
                            max_function_calls,
                        )
                        mutable_options["tool_choice"] = "none"
                    errors_in_a_row = result["errors_in_a_row"]

                    # When tool_choice is 'required', reset tool_choice after one iteration to avoid infinite loops
                    if mutable_options.get("tool_choice") == "required" or (
                        isinstance(mutable_options.get("tool_choice"), dict)
                        and mutable_options.get("tool_choice", {}).get("mode") == "required"
                    ):
                        mutable_options["tool_choice"] = None  # reset to default for next iteration

                    if response.conversation_id is not None:
                        # For conversation-based APIs, the server already has the function call message.
                        # Only send the new function result message (added by _handle_function_call_results).
                        prepped_messages.clear()
                        if response.messages:
                            prepped_messages.append(response.messages[-1])
                    else:
                        prepped_messages.extend(response.messages)
                    continue

                if response is not None:
                    return response

                mutable_options["tool_choice"] = "none"
                response = await super_get_response(
                    messages=prepped_messages,
                    stream=False,
                    options=mutable_options,
                    **filtered_kwargs,
                )
                if fcc_messages:
                    for msg in reversed(fcc_messages):
                        response.messages.insert(0, msg)
                return response

            return _get_response()

        response_format = mutable_options.get("response_format") if mutable_options else None
        output_format_type = response_format if isinstance(response_format, type) else None
        stream_result_hooks: list[Callable[[ChatResponse], Any]] = []

        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            nonlocal filtered_kwargs
            nonlocal mutable_options
            nonlocal stream_result_hooks
            errors_in_a_row: int = 0
            total_function_calls: int = 0
            max_function_calls: int | None = self.function_invocation_configuration.get("max_function_calls")
            prepped_messages = list(messages)
            fcc_messages: list[Message] = []
            response: ChatResponse | None = None

            for attempt_idx in range(
                self.function_invocation_configuration["max_iterations"]
                if self.function_invocation_configuration["enabled"]
                else 0
            ):
                approval_result = await _process_function_requests(
                    response=None,
                    prepped_messages=prepped_messages,
                    tool_options=mutable_options,  # type: ignore[arg-type]
                    attempt_idx=attempt_idx,
                    fcc_messages=None,
                    errors_in_a_row=errors_in_a_row,
                    max_errors=max_errors,
                    execute_function_calls=execute_function_calls,
                )
                errors_in_a_row = approval_result["errors_in_a_row"]
                total_function_calls += approval_result.get("function_call_count", 0)
                if approval_result["action"] == "stop":
                    mutable_options["tool_choice"] = "none"
                    return

                inner_stream = await _ensure_response_stream(
                    super_get_response(
                        messages=prepped_messages,
                        stream=True,
                        options=mutable_options,
                        **filtered_kwargs,
                    )
                )
                # Collect result hooks from the inner stream to run later
                stream_result_hooks[:] = _get_result_hooks_from_stream(inner_stream)

                # Yield updates from the inner stream, letting it collect them
                async for update in inner_stream:
                    yield update

                # Get the finalized response from the inner stream
                # This triggers the inner stream's finalizer and result hooks
                response = await inner_stream.get_final_response()

                if not any(
                    item.type in ("function_call", "function_approval_request")
                    for msg in response.messages
                    for item in msg.contents
                ):
                    return

                if response.conversation_id is not None:
                    _update_conversation_id(kwargs, response.conversation_id, mutable_options)
                    prepped_messages = []

                result = await _process_function_requests(
                    response=response,
                    prepped_messages=None,
                    tool_options=mutable_options,  # type: ignore[arg-type]
                    attempt_idx=attempt_idx,
                    fcc_messages=fcc_messages,
                    errors_in_a_row=errors_in_a_row,
                    max_errors=max_errors,
                    execute_function_calls=execute_function_calls,
                )
                errors_in_a_row = result["errors_in_a_row"]
                total_function_calls += result.get("function_call_count", 0)
                if role := result["update_role"]:
                    yield ChatResponseUpdate(
                        contents=result["function_call_results"] or [],
                        role=role,
                    )
                if result["action"] == "stop":
                    # Error threshold reached: submit collected function_call_output
                    # items once more with tools disabled.
                    mutable_options["tool_choice"] = "none"
                elif result["action"] != "continue":
                    return
                elif (
                    max_function_calls is not None
                    and total_function_calls >= max_function_calls
                ):
                    # Best-effort limit: checked after each batch of parallel calls completes,
                    # so the current batch always runs to completion even if it overshoots.
                    logger.info(
                        "Maximum function calls reached (%d/%d). "
                        "Stopping further function calls for this request.",
                        total_function_calls,
                        max_function_calls,
                    )
                    mutable_options["tool_choice"] = "none"

                # When tool_choice is 'required', reset the tool_choice after one iteration to avoid infinite loops
                if mutable_options.get("tool_choice") == "required" or (
                    isinstance(mutable_options.get("tool_choice"), dict)
                    and mutable_options.get("tool_choice", {}).get("mode") == "required"
                ):
                    mutable_options["tool_choice"] = None  # reset to default for next iteration

                if response.conversation_id is not None:
                    # For conversation-based APIs, the server already has the function call message.
                    # Only send the new function result message (the last one added by _handle_function_call_results).
                    prepped_messages.clear()
                    if response.messages:
                        prepped_messages.append(response.messages[-1])
                else:
                    prepped_messages.extend(response.messages)
                continue

            if response is not None:
                return

            mutable_options["tool_choice"] = "none"
            inner_stream = await _ensure_response_stream(
                super_get_response(
                    messages=prepped_messages,
                    stream=True,
                    options=mutable_options,
                    **filtered_kwargs,
                )
            )
            async for update in inner_stream:
                yield update
            # Finalize the inner stream to trigger its hooks
            await inner_stream.get_final_response()

        def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            # Note: stream_result_hooks are already run via inner stream's get_final_response()
            # We don't need to run them again here
            return ChatResponse.from_updates(updates, output_format_type=output_format_type)

        return ResponseStream(_stream(), finalizer=_finalize)
