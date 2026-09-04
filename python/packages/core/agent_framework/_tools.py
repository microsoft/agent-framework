# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import contextvars
import copy
import inspect
import json
import logging
import sys
import typing
import warnings
from collections import deque
from collections.abc import (
    AsyncIterable,
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    Sequence,
)
from contextlib import suppress
from dataclasses import dataclass
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
    cast,
    get_args,
    get_origin,
    overload,
)
from uuid import uuid4

from opentelemetry.metrics import Histogram, NoOpHistogram
from pydantic import BaseModel, Field, ValidationError, create_model

from ._serialization import SerializationMixin
from .exceptions import ToolException, UserInputRequiredException
from .observability import (
    OPERATION_DURATION_BUCKET_BOUNDARIES,
    OtelAttr,
    capture_exception,
    get_function_span,
    get_function_span_attributes,
    get_meter,
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover


if TYPE_CHECKING:
    from ._clients import SupportsChatGetResponse
    from ._compaction import CompactionStrategy, TokenizerProtocol
    from ._mcp import MCPTool
    from ._middleware import (
        ChatAndFunctionMiddlewareTypes,
        FunctionInvocationContext,
        FunctionMiddlewarePipeline,
        FunctionMiddlewareTypes,
        MiddlewareTypes,
    )
    from ._sessions import AgentSession
    from ._types import (
        ChatOptions,
        ChatResponse,
        ChatResponseUpdate,
        Content,
        Message,
        ResponseStream,
        UsageDetails,
    )

else:
    MCPTool = Any  # type: ignore[assignment,misc]


logger = logging.getLogger("agent_framework")


def _generate_function_call_occurrence_id() -> str:
    """Generate an Agent Framework identity for one function-call occurrence."""
    return f"af-call-{uuid4().hex}"


DEFAULT_MAX_ITERATIONS: Final[int] = 40
DEFAULT_MAX_CONSECUTIVE_ERRORS_PER_REQUEST: Final[int] = 3
SHELL_TOOL_KIND_VALUE: Final[str] = "shell"
_TOOL_APPROVAL_STATE_KEY: Final[str] = "tool_approval"
_ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY: Final[str] = "already_approved_approval_request_groups"
_PENDING_APPROVAL_REQUESTS_KEY: Final[str] = "pending_approval_requests"
_FUNCTION_INVOCATION_BUDGET_STATE_KEY: Final[str] = "_function_invocation_budget_state"
_FUNCTION_INVOCATION_LIMIT_FALLBACK_TEXT: Final[str] = (
    "Function invocation limit reached before a final answer could be produced."
)
_USER_VISIBLE_CONTENT_TYPES: Final[set[str]] = {"data", "uri", "error", "hosted_file", "hosted_vector_store"}
ApprovalMode: TypeAlias = Literal["always_require", "never_require"]
ChatClientT = TypeVar("ChatClientT", bound="SupportsChatGetResponse[Any]")
ResponseModelBoundT = TypeVar("ResponseModelBoundT", bound=BaseModel)


class _SkipParsingSentinel:
    """Sentinel signaling that :meth:`FunctionTool.invoke` should return the raw value.

    When passed as ``result_parser`` to :class:`FunctionTool` (or the ``@tool`` decorator),
    the default :meth:`FunctionTool.parse_result` is bypassed and the wrapped function's
    return value is returned unchanged from :meth:`FunctionTool.invoke`. Callers may also
    request the raw value on a per-call basis by passing ``skip_parsing=True`` to
    :meth:`FunctionTool.invoke`.

    Use the module-level ``SKIP_PARSING`` singleton — do not instantiate this class.
    """

    _instance: ClassVar[_SkipParsingSentinel | None] = None

    def __new__(cls) -> _SkipParsingSentinel:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "SKIP_PARSING"


SKIP_PARSING: Final[_SkipParsingSentinel] = _SkipParsingSentinel()
"""Sentinel for ``FunctionTool(result_parser=...)`` meaning "do not parse the result"."""

# region Helpers


def _get_tool_name(tool: Any) -> str | None:
    """Extract a tool name from a tool object or dict tool definition."""
    if isinstance(tool, Mapping):
        func = tool.get("function", None)  # type: ignore
        if func and isinstance(func, Mapping):
            name = func.get("name")  # type: ignore
            return name if isinstance(name, str) else None
        return None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None


def _parse_inputs(  # pyright: ignore[reportUnusedFunction]
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

    if not OBSERVABILITY_SETTINGS.ENABLED:
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


def _annotation_includes_function_invocation_context(annotation: Any) -> bool:
    """Check whether an annotation resolves to FunctionInvocationContext."""
    from ._middleware import FunctionInvocationContext

    candidates = get_args(annotation) or (annotation,)
    return any(
        candidate is FunctionInvocationContext or candidate == "FunctionInvocationContext" for candidate in candidates
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
        "_invoke_sync_on_event_loop",
    }

    def __init__(
        self,
        *,
        name: str,
        description: str = "",
        approval_mode: ApprovalMode | None = None,
        kind: str | None = None,
        max_invocations: int | None = None,
        max_invocation_exceptions: int | None = None,
        additional_properties: dict[str, Any] | None = None,
        func: Callable[..., Any] | None = None,
        input_model: type[BaseModel] | Mapping[str, Any] | None = None,
        result_parser: Callable[[Any], str | list[Content]] | _SkipParsingSentinel | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the FunctionTool.

        Keyword Args:
            name: The name of the function.
            description: A description of the function.
            approval_mode: Whether or not approval is required to run this tool.
                Default is that approval is NOT required (``"never_require"``).
            kind: Optional provider-agnostic tool classification
                (for example ``"shell"``).
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
                built-in :meth:`parse_result` logic. Pass the :data:`SKIP_PARSING` sentinel
                instead of a callable to opt out of parsing entirely; in that case
                :meth:`invoke` returns the wrapped function's raw return value. Depending
                on your function, it may be easiest to just do the serialization directly
                in the function body rather than providing a custom ``result_parser``.
            **kwargs: Additional keyword arguments.
        """
        # Core attributes (formerly from BaseTool)
        self.name = name
        self.description = description
        self.kind = kind
        self.additional_properties = additional_properties
        self._invoke_sync_on_event_loop = False
        for key, value in kwargs.items():
            setattr(self, key, value)

        # FunctionTool-specific attributes
        self.func = func
        self._instance = None  # Store the instance for bound methods
        self._context_parameter_name: str | None = None
        self._input_model_explicitly_provided = input_model is not None
        if self.func:
            self._discover_injected_parameters()

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

    def _discover_injected_parameters(self) -> None:
        """Inspect the wrapped function for runtime injection parameters."""
        func = self.func.func if isinstance(self.func, FunctionTool) else self.func
        if func is None:
            return

        signature = inspect.signature(func)
        try:
            type_hints = typing.get_type_hints(func)
        except Exception:
            type_hints = {name: param.annotation for name, param in signature.parameters.items()}

        for name, param in signature.parameters.items():
            if name in {"self", "cls"}:
                continue
            annotation = type_hints.get(name, param.annotation)
            if self._is_context_parameter(name, annotation):
                if self._context_parameter_name is not None:
                    raise ValueError(f"Function '{self.name}' defines multiple FunctionInvocationContext parameters.")
                self._context_parameter_name = name

    def _is_context_parameter(self, name: str, annotation: Any) -> bool:
        """Check whether a callable parameter should receive FunctionInvocationContext injection."""
        if _annotation_includes_function_invocation_context(annotation):
            return True
        return self._input_model_explicitly_provided and name == "ctx" and annotation is inspect.Parameter.empty

    def __str__(self) -> str:
        """Return a string representation of the tool."""
        if self.description:
            return f"{self.__class__.__name__}(name={self.name}, description={self.description})"
        return f"{self.__class__.__name__}(name={self.name})"

    @property
    def declaration_only(self) -> bool:
        """Indicate whether the function is declaration only (i.e., has no implementation)."""
        # Check for explicit _declaration_only attribute first (used in tests)
        declaration_flag = getattr(self, "_declaration_only", False)
        if isinstance(declaration_flag, bool) and declaration_flag:
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
        try:
            type_hints = typing.get_type_hints(func, include_extras=True)
        except Exception:
            type_hints = {}
        fields: dict[str, Any] = {
            pname: (
                _parse_annotation(type_hints.get(pname, param.annotation))
                if type_hints.get(pname, param.annotation) is not inspect.Parameter.empty
                else str,
                param.default if param.default is not inspect.Parameter.empty else ...,
            )
            for pname, param in sig.parameters.items()
            if pname not in {"self", "cls"}
            and pname != self._context_parameter_name
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
            func = self.func
            if func is None:
                raise ToolException(f"Function '{self.name}' has no implementation.")
            # If we have a bound instance, call the function with self
            if self._instance is not None:
                return func(self._instance, *args, **kwargs)
            return func(*args, **kwargs)
        except Exception:
            self.invocation_exception_count += 1
            raise

    async def _invoke_function(self, call_kwargs: Mapping[str, Any]) -> Any:
        """Run sync tools off the event loop during async invocation."""
        func = self.func.func if isinstance(self.func, FunctionTool) else self.func
        if inspect.iscoroutinefunction(func) or getattr(self, "_invoke_sync_on_event_loop", False):
            res = self.__call__(**call_kwargs)
            return await res if inspect.isawaitable(res) else res

        res = await asyncio.to_thread(self.__call__, **call_kwargs)
        return await res if inspect.isawaitable(res) else res

    @overload
    async def invoke(
        self,
        *,
        arguments: BaseModel | Mapping[str, Any] | None = None,
        context: FunctionInvocationContext | None = None,
        tool_call_id: str | None = None,
        skip_parsing: Literal[True],
        **kwargs: Any,
    ) -> Any: ...

    @overload
    async def invoke(
        self,
        *,
        arguments: BaseModel | Mapping[str, Any] | None = None,
        context: FunctionInvocationContext | None = None,
        tool_call_id: str | None = None,
        skip_parsing: Literal[False] = False,
        **kwargs: Any,
    ) -> list[Content]: ...

    async def invoke(
        self,
        *,
        arguments: BaseModel | Mapping[str, Any] | None = None,
        context: FunctionInvocationContext | None = None,
        tool_call_id: str | None = None,
        skip_parsing: bool = False,
        **kwargs: Any,
    ) -> list[Content] | Any:
        """Run the AI function with the provided arguments as a Pydantic model.

        The raw return value of the wrapped function is automatically parsed into a
        ``list[Content]`` using :meth:`parse_result` or the custom ``result_parser``
        configured on the tool. Every result — text, rich media, or serialized
        objects — is represented uniformly as Content items.

        Parsing can be skipped in two ways: configure the tool with
        ``result_parser=SKIP_PARSING`` to always skip parsing, or pass
        ``skip_parsing=True`` per call. Either way the wrapped function's raw value
        is returned. This is intended for callers (e.g. sandboxed runtimes) that
        consume the value from Python directly and would otherwise undo the
        ``Content`` wrapping.

        Keyword Args:
            arguments: A mapping or model instance containing the arguments for the function.
            context: Explicit function invocation context carrying runtime kwargs.
            tool_call_id: Optional tool call identifier used for telemetry and tracing.
            skip_parsing: When ``True``, bypass parsing and return the wrapped function's
                raw value instead of a ``list[Content]``. Defaults to ``False``.
            kwargs: Direct function argument values. When provided, every keyword
                must match a declared tool parameter. Runtime data must be passed
                via ``context``.

        Returns:
            ``list[Content]`` by default. The raw function return value (``Any``) when
            ``skip_parsing=True`` (or the tool was constructed with
            ``result_parser=SKIP_PARSING``).

        Raises:
            TypeError: If arguments is not mapping-like or fails schema checks.
        """
        if self.declaration_only:
            raise ToolException(f"Function '{self.name}' is declaration only and cannot be invoked.")
        global OBSERVABILITY_SETTINGS
        from ._middleware import FunctionInvocationContext
        from ._types import Content
        from .observability import OBSERVABILITY_SETTINGS

        configured_parser = self.result_parser
        skip_parsing = skip_parsing or configured_parser is SKIP_PARSING
        parser = configured_parser if callable(configured_parser) else FunctionTool.parse_result

        parameter_names = set(self.parameters().get("properties", {}).keys())
        direct_argument_kwargs = (
            {key: value for key, value in kwargs.items() if key in parameter_names} if arguments is None else {}
        )
        runtime_kwargs = dict(context.kwargs) if context is not None else {}
        unexpected_kwargs = {key: value for key, value in kwargs.items() if key not in direct_argument_kwargs}
        if unexpected_kwargs:
            unexpected_names = ", ".join(sorted(unexpected_kwargs))
            raise TypeError(
                f"Unexpected keyword argument(s) for tool '{self.name}': {unexpected_names}. "
                "Pass runtime data via FunctionInvocationContext instead."
            )
        if arguments is None and direct_argument_kwargs:
            arguments = direct_argument_kwargs
        if arguments is None and context is not None:
            arguments = context.arguments

        if arguments is None:
            validated_arguments: dict[str, Any] = {}
        else:
            try:
                if isinstance(arguments, Mapping):
                    parsed_arguments = dict(arguments)
                    if self.input_model is not None and not self._schema_supplied:
                        # exclude_unset (not exclude_none): keep arguments the model
                        # explicitly provided even when their value is null, and drop
                        # only the ones it left out, so the function's own defaults
                        # apply. Excluding null instead would strip a required nullable
                        # parameter the model deliberately set to null, failing the
                        # invocation on the missing argument (#5934).
                        parsed_arguments = self.input_model.model_validate(parsed_arguments).model_dump(
                            exclude_unset=True
                        )
                elif isinstance(arguments, BaseModel):
                    if (
                        self.input_model is not None
                        and not self._schema_supplied
                        and not isinstance(arguments, self.input_model)
                    ):
                        raise TypeError(f"Expected {self.input_model.__name__}, got {type(arguments).__name__}")
                    parsed_arguments = arguments.model_dump(exclude_unset=True)
                else:
                    raise TypeError(
                        f"Expected mapping-like arguments for tool '{self.name}', got {type(arguments).__name__}"
                    )
            except ValidationError as exc:
                raise TypeError(f"Invalid arguments for '{self.name}': {exc}") from exc

            validated_arguments = _validate_arguments_against_schema(
                arguments=parsed_arguments,
                schema=self.parameters(),
                tool_name=self.name,
            )

        effective_context = context
        if effective_context is None and self._context_parameter_name is not None:
            effective_context = FunctionInvocationContext(
                function=self,
                arguments=validated_arguments,
                kwargs=runtime_kwargs,
            )
        if effective_context is not None:
            effective_context.function = self
            effective_context.arguments = validated_arguments
            effective_context.kwargs = dict(runtime_kwargs)

        call_kwargs = dict(validated_arguments)
        observable_kwargs = dict(validated_arguments)
        if self._context_parameter_name is not None and effective_context is not None:
            call_kwargs[self._context_parameter_name] = effective_context

        if not OBSERVABILITY_SETTINGS.ENABLED:
            logger.info(f"Function name: {self.name}")
            logger.debug(f"Function arguments: {observable_kwargs}")
            result = await self._invoke_function(call_kwargs)
            if skip_parsing:
                logger.info(f"Function {self.name} succeeded.")
                logger.debug(f"Function result: {type(result).__name__}")
                return result
            try:
                parsed = parser(result)
            except Exception:
                logger.warning(f"Function {self.name}: result parser failed, falling back to str().")
                parsed = [Content.from_text(str(result))]
            if isinstance(parsed, str):
                parsed = [Content.from_text(parsed)]
            logger.info(f"Function {self.name} succeeded.")
            if parsed:
                types = [item.type for item in parsed]
                logger.debug(f"Function result: {len(parsed)} item(s) ({', '.join(types)})")
            else:
                logger.debug("Function result: None")
            return parsed

        attributes = get_function_span_attributes(self, tool_call_id=tool_call_id)
        # Filter out framework kwargs that are not JSON serializable.
        serializable_kwargs = {
            k: v
            for k, v in observable_kwargs.items()
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
        # gen_ai.tool.call.arguments/result were introduced above v1.36.0; only emit them
        # as span attributes when that semconv version is active.
        emit_tool_call_attrs = OBSERVABILITY_SETTINGS.emit_tool_call_attributes
        if emit_tool_call_attrs:
            attributes.update({
                OtelAttr.TOOL_ARGUMENTS: (
                    json.dumps(serializable_kwargs, default=str, ensure_ascii=False) if serializable_kwargs else "None"
                )
            })
        with get_function_span(attributes=attributes) as span:
            attributes[OtelAttr.MEASUREMENT_FUNCTION_TAG_NAME] = self.name
            logger.info(f"Function name: {self.name}")
            if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:
                logger.debug(f"Function arguments: {serializable_kwargs}")
            start_time_stamp = perf_counter()
            end_time_stamp: float | None = None
            try:
                result = await self._invoke_function(call_kwargs)
                end_time_stamp = perf_counter()
            except Exception as exception:
                end_time_stamp = perf_counter()
                attributes[OtelAttr.ERROR_TYPE] = type(exception).__name__
                capture_exception(span=span, exception=exception, timestamp=time_ns())
                logger.error(f"Function failed. Error: {exception}")
                raise
            else:
                if skip_parsing:
                    logger.info(f"Function {self.name} succeeded.")
                    if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:
                        result_str = str(result)
                        logger.debug(f"Function result: {result_str}")
                        if emit_tool_call_attrs:
                            span.set_attribute(OtelAttr.TOOL_RESULT, result_str)
                    return result
                try:
                    parsed = parser(result)
                except Exception:
                    logger.warning(f"Function {self.name}: result parser failed, falling back to str().")
                    parsed = [Content.from_text(str(result))]
                if isinstance(parsed, str):
                    parsed = [Content.from_text(parsed)]
                logger.info(f"Function {self.name} succeeded.")
                if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:
                    result_str = "\n".join(c.text or "" for c in parsed if c.type == "text") or str(parsed)
                    logger.debug(f"Function result: {result_str}")
                    if emit_tool_call_attrs:
                        span.set_attribute(OtelAttr.TOOL_RESULT, result_str)
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
            list_value = cast(list[object], value)
            return [FunctionTool._make_dumpable(item) for item in list_value]
        if isinstance(value, dict):
            dict_value = cast(dict[object, object], value)
            return {key: FunctionTool._make_dumpable(item) for key, item in dict_value.items()}
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
    def parse_result(result: Any) -> list[Content]:
        """Convert a raw function return value to a list of Content items.

        Every tool result is represented as a uniform ``list[Content]``.  Text
        results become ``Content(type="text")``, rich media (images, audio,
        files) are preserved as-is, and arbitrary objects are serialized to JSON
        text.

        This is called automatically by :meth:`invoke` before returning the result,
        ensuring that the result stored in ``Content.from_function_result`` is
        already in a form that can be passed directly to LLM APIs.

        Args:
            result: The raw return value from the wrapped function.

        Returns:
            A list of Content items representing the tool output.
        """
        from ._types import Content

        if result is None:
            return [Content.from_text("")]
        if isinstance(result, str):
            return [Content.from_text(result)]
        if isinstance(result, Content):
            return [result]
        if isinstance(result, list) and any(isinstance(item, Content) for item in result):  # type: ignore[reportUnknownVariableType]
            parsed_items: list[Content] = []
            for item in result:  # type: ignore[reportUnknownVariableType]
                if isinstance(item, Content):
                    parsed_items.append(item)
                else:
                    dumpable = FunctionTool._make_dumpable(item)
                    text = dumpable if isinstance(dumpable, str) else json.dumps(dumpable, default=str)
                    parsed_items.append(Content.from_text(text))
            return parsed_items
        dumpable = FunctionTool._make_dumpable(result)
        if isinstance(dumpable, str):
            return [Content.from_text(dumpable)]
        return [Content.from_text(json.dumps(dumpable, default=str))]

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


ToolTypes: TypeAlias = FunctionTool | MCPTool | Mapping[str, Any] | object


def _raise_duplicate_tool_name(tool_name: str, duplicate_error_message: str | None = None) -> None:
    message = duplicate_error_message or "Tool names must be unique."
    raise ValueError(f"Duplicate tool name '{tool_name}'. {message}")


def _append_unique_tools(
    existing_tools: list[ToolTypes],
    new_tools: Sequence[ToolTypes],
    *,
    duplicate_error_message: str | None = None,
) -> list[ToolTypes]:
    seen_by_name: dict[str, ToolTypes] = {}
    for tool_item in existing_tools:
        if tool_name := _get_tool_name(tool_item):
            seen_by_name[tool_name] = tool_item

    for tool_item in new_tools:
        tool_name = _get_tool_name(tool_item)
        if tool_name is None:
            existing_tools.append(tool_item)
            continue

        existing_tool = seen_by_name.get(tool_name)
        if existing_tool is None:
            seen_by_name[tool_name] = tool_item
            existing_tools.append(tool_item)
            continue

        if existing_tool is tool_item:
            continue

        _raise_duplicate_tool_name(tool_name, duplicate_error_message)

    return existing_tools


def _ensure_unique_tool_names(
    tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]],
    *,
    duplicate_error_message: str | None = None,
) -> list[ToolTypes]:
    normalized_tools = normalize_tools(tools)
    return _append_unique_tools([], normalized_tools, duplicate_error_message=duplicate_error_message)


def normalize_tools(
    tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None,
) -> list[ToolTypes]:
    """Normalize tool inputs while preserving non-callable tool objects.

    Args:
        tools: A single tool or sequence of tools.

    Returns:
        A normalized list where callable inputs are converted to ``FunctionTool``
        using :func:`tool`, and existing tool objects are passed through unchanged.

    Tool-collection wrappers are flattened in two forms:

    - non-tool, non-callable iterables
    - mapping-like objects that expose a ``.tools`` collection (for example
      ``ToolboxVersionObject`` from azure-ai-projects)

    This lets callers write ``tools=[toolbox, my_func]`` and have the
    toolbox's contents spread in alongside individual tools.
    """
    if not tools:
        return []

    if isinstance(tools, (str, bytes, bytearray, Mapping)) or not isinstance(tools, Sequence):
        tools = cast(list[ToolTypes | Callable[..., Any]], [tools])

    from ._mcp import MCPTool

    normalized: list[ToolTypes] = []
    for tool_item in tools:  # type: ignore[reportUnknownVariableType]
        # check known types, these are also callable, so we need to do that first
        if isinstance(tool_item, FunctionTool):
            normalized.append(tool_item)
            continue
        if isinstance(tool_item, dict):
            normalized.append(tool_item)  # type: ignore[reportUnknownArgumentType]
            continue
        if isinstance(tool_item, MCPTool):
            normalized.append(tool_item)
            continue
        if callable(tool_item):  # type: ignore[reportUnknownArgumentType]
            normalized.append(tool(tool_item))
            continue
        # Mapping-like tool collections (for example ToolboxVersionObject) are
        # not flattened by the generic Iterable branch below because they are
        # also Mapping instances. If they expose a ``tools`` collection, spread
        # that collection into the normalized list.
        collection_tools = getattr(tool_item, "tools", None)  # type: ignore[reportUnknownArgumentType]
        if isinstance(collection_tools, Iterable) and not isinstance(
            collection_tools, (str, bytes, bytearray, Mapping)
        ):
            normalized.extend(normalize_tools(list(collection_tools)))  # type: ignore[reportUnknownArgumentType]
            continue
        # Tool-collection wrapper (e.g. FoundryToolbox): a non-tool, non-callable
        # iterable. Flatten its contents so ``tools=[toolbox, my_func]`` works.
        # Strings, mappings, and Pydantic BaseModel are excluded — BaseModel
        # instances iterate over (field, value) tuples, not tools, so they
        # should pass through as leaf tool specs (handled below).
        if isinstance(tool_item, Iterable) and not isinstance(tool_item, (str, bytes, bytearray, Mapping, BaseModel)):
            normalized.extend(normalize_tools(list(tool_item)))  # type: ignore[reportUnknownArgumentType]
            continue
        normalized.append(tool_item)  # type: ignore[reportUnknownArgumentType]
    return normalized


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

    required_fields = [field for field in schema.get("required", []) if isinstance(field, str)]
    missing_fields = [field for field in required_fields if field not in parsed_arguments]
    if missing_fields:
        raise TypeError(f"Missing required argument(s) for '{tool_name}': {', '.join(sorted(missing_fields))}")

    properties: Mapping[str, Any] = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        unexpected_fields = sorted(field for field in parsed_arguments if field not in properties)
        if unexpected_fields:
            raise TypeError(f"Unexpected argument(s) for '{tool_name}': {', '.join(unexpected_fields)}")

    for field_name, field_value in parsed_arguments.items():
        if not isinstance(properties.get(field_name), dict):
            continue

        enum_values = properties.get(field_name, {}).get("enum")
        if isinstance(enum_values, list) and enum_values and field_value not in enum_values:
            raise TypeError(
                f"Invalid value for '{field_name}' in '{tool_name}': {field_value!r} is not in {enum_values!r}"
            )

        schema_type = properties.get(field_name, {}).get("type")
        if isinstance(schema_type, str):
            if not _matches_json_schema_type(field_value, schema_type):
                raise TypeError(
                    f"Invalid type for '{field_name}' in '{tool_name}': "
                    f"expected {schema_type}, got {type(field_value).__name__}"
                )
            continue

        if isinstance(schema_type, list):
            allowed_types: list[str] = [item for item in schema_type if isinstance(item, str)]  # type: ignore[reportUnknownVariableType]
            if allowed_types and not any(_matches_json_schema_type(field_value, item) for item in allowed_types):
                raise TypeError(
                    f"Invalid type for '{field_name}' in '{tool_name}': expected one of "
                    f"{allowed_types}, got {type(field_value).__name__}"
                )

    return parsed_arguments


@overload
def tool(
    func: Callable[..., Any],
    *,
    name: str | None = None,
    description: str | None = None,
    schema: type[BaseModel] | Mapping[str, Any] | None = None,
    approval_mode: ApprovalMode | None = None,
    kind: str | None = None,
    max_invocations: int | None = None,
    max_invocation_exceptions: int | None = None,
    additional_properties: dict[str, Any] | None = None,
    result_parser: Callable[[Any], str | list[Content]] | _SkipParsingSentinel | None = None,
) -> FunctionTool: ...


@overload
def tool(
    func: None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    schema: type[BaseModel] | Mapping[str, Any] | None = None,
    approval_mode: ApprovalMode | None = None,
    kind: str | None = None,
    max_invocations: int | None = None,
    max_invocation_exceptions: int | None = None,
    additional_properties: dict[str, Any] | None = None,
    result_parser: Callable[[Any], str | list[Content]] | _SkipParsingSentinel | None = None,
) -> Callable[[Callable[..., Any]], FunctionTool]: ...


def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    schema: type[BaseModel] | Mapping[str, Any] | None = None,
    approval_mode: ApprovalMode | None = None,
    kind: str | None = None,
    max_invocations: int | None = None,
    max_invocation_exceptions: int | None = None,
    additional_properties: dict[str, Any] | None = None,
    result_parser: Callable[[Any], str | list[Content]] | _SkipParsingSentinel | None = None,
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
        kind: Optional provider-agnostic tool classification.
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
            tool_name: str = name or getattr(f, "__name__", "unknown_function")
            tool_desc: str = description or (f.__doc__ or "")
            return FunctionTool(
                name=tool_name,
                description=tool_desc,
                approval_mode=approval_mode,
                kind=kind,
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
    return normalized


def _function_execution_error_result(
    function_call: Content,
    tool_name: str,
    exception: Exception,
    config: FunctionInvocationConfiguration,
) -> Content:
    from ._types import Content

    logger.warning(
        "Function '%s' raised an exception; returning an error result to the model. "
        "Set include_detailed_errors=True for the full detail. Exception: %r",
        tool_name,
        exception,
    )
    message = "Error: Function failed."
    if config.get("include_detailed_errors", False):
        message = f"{message} Exception: {exception}"
    return Content.from_function_result(
        call_id=function_call.call_id,  # type: ignore[arg-type]
        result=message,
        exception=str(exception),
        additional_properties=function_call.additional_properties,
    )


async def _auto_invoke_function(
    function_call_content: Content,
    custom_args: dict[str, Any] | None = None,
    *,
    config: FunctionInvocationConfiguration,
    tool_map: dict[str, FunctionTool],
    invocation_session: AgentSession | None = None,
    middleware_pipeline: FunctionMiddlewarePipeline | None = None,
    live_tools: list[ToolTypes] | None = None,
) -> Content:
    """Invoke a function call requested by the agent, applying middleware that is defined.

    Args:
        function_call_content: The function call content from the model.
        custom_args: Additional custom arguments to merge with parsed arguments.

    Keyword Args:
        config: The function invocation configuration.
        tool_map: A mapping of tool names to FunctionTool instances.
        invocation_session: The agent session for this invocation, if any.
        middleware_pipeline: Optional middleware pipeline to apply during execution.
        live_tools: The live, mutable tools list for the current agent run, exposed on
            the FunctionInvocationContext so tools can add/remove tools at runtime.

    Returns:
        The function result content.

    Raises:
        KeyError: If the requested function is not found in the tool map.
        MiddlewareTermination: If middleware requests loop termination.
        MiddlewareFailure: If middleware (or the tool) aborts the run fail-closed.
            Unlike ordinary exceptions, which are converted into tool-error results,
            this explicit signal is re-raised so it propagates to the run's caller.
        UserInputRequiredException: If the tool requires user input to proceed.
    """
    from ._types import Content

    # Note: The scenarios for approval_mode="always_require", declaration_only, and
    # terminate_on_unknown_calls are all handled in _try_execute_function_calls before
    # this function is called. This function only handles the actual execution of approved,
    # non-declaration-only functions.

    approval_response: Content | None = None

    if function_call_content.type == "function_call":
        tool = tool_map.get(function_call_content.name)  # type: ignore[arg-type]
        # Tool should exist because _try_execute_function_calls validates this
        if tool is None:
            exc = KeyError(f'Function "{function_call_content.name}" not found.')
            return Content.from_function_result(
                call_id=function_call_content.call_id,  # type: ignore[arg-type]
                result=f'Error: Requested function "{function_call_content.name}" not found.',
                exception=str(exc),
                additional_properties=function_call_content.additional_properties,
            )
    else:
        # Note: Unapproved tools (approved=False) are handled in _replace_approval_contents_with_results
        # and never reach this function, so we only handle approved=True cases here.
        approved_function_call = function_call_content.function_call
        if (
            approved_function_call is None
            or approved_function_call.type != "function_call"
            or approved_function_call.name is None
        ):
            return function_call_content
        tool = tool_map.get(approved_function_call.name)
        if tool is None:
            # we assume it is a hosted tool
            return function_call_content

        approval_response = function_call_content
        function_call_content = approved_function_call

    parsed_args: dict[str, Any] = dict(function_call_content.parse_arguments() or {})

    # Filter out internal framework kwargs before passing to tools.
    # conversation_id is an internal tracking ID that should not be forwarded to tools.
    runtime_kwargs: dict[str, Any] = {
        key: value
        for key, value in (custom_args or {}).items()
        if key not in {"_function_middleware_pipeline", "middleware", "conversation_id"}
    }
    if invocation_session is not None:
        runtime_kwargs["session"] = invocation_session
    try:
        if not cast(bool, getattr(tool, "_schema_supplied", False)) and tool.input_model is not None:
            # exclude_unset (not exclude_none) so an argument the model explicitly set
            # to null still reaches the function; see FunctionTool.invoke for the full
            # rationale. This is the auto-calling path #5934 actually hits.
            args = tool.input_model.model_validate(parsed_args).model_dump(exclude_unset=True)
        else:
            args = dict(parsed_args)
        args = _validate_arguments_against_schema(
            arguments=args,
            schema=tool.parameters(),
            tool_name=tool.name,
        )
    except (TypeError, ValidationError) as exc:
        message = "Error: Argument parsing failed."
        if config.get("include_detailed_errors", False):
            message = f"{message} Exception: {exc}"
        return Content.from_function_result(
            call_id=function_call_content.call_id,  # type: ignore[arg-type]
            result=message,
            exception=str(exc),
            additional_properties=function_call_content.additional_properties,
        )

    from ._middleware import FunctionInvocationContext, MiddlewareFailure

    if middleware_pipeline is None or not middleware_pipeline.has_middlewares:
        # No middleware - execute directly
        try:
            direct_context = None
            if getattr(tool, "_context_parameter_name", None):
                direct_context = FunctionInvocationContext(
                    function=tool,
                    arguments=args,
                    session=invocation_session,
                    kwargs=runtime_kwargs.copy(),
                    tools=live_tools,
                )
            function_result = await tool.invoke(
                arguments=args,
                context=direct_context,
                tool_call_id=function_call_content.call_id,
            )
            return Content.from_function_result(
                call_id=function_call_content.call_id,  # type: ignore[arg-type]
                result=function_result,
                additional_properties=function_call_content.additional_properties,
            )
        except (MiddlewareFailure, UserInputRequiredException):
            # Explicit control-flow signals escape the loop; only ordinary exceptions
            # are absorbed into tool-error results below.
            raise
        except Exception as exc:
            return _function_execution_error_result(function_call_content, tool.name, exc, config)
    # Execute through middleware pipeline if available
    middleware_context = FunctionInvocationContext(
        function=tool,
        arguments=args,
        session=invocation_session,
        kwargs=runtime_kwargs.copy(),
        tools=live_tools,
    )

    call_id = function_call_content.call_id
    if call_id is None:
        raise KeyError(f'Function "{function_call_content.name}" is missing call_id.')

    # Pass both provider correlation and framework occurrence identity to middleware.
    middleware_context.metadata["call_id"] = call_id
    if function_call_content.id is not None:
        middleware_context.metadata["function_call_occurrence_id"] = function_call_content.id

    # Pass through the original approval response so middleware can decide whether
    # this replay corresponds to a middleware-specific approval flow.
    if approval_response is not None:
        middleware_context.metadata["approval_response"] = approval_response

    async def final_function_handler(context_obj: Any) -> Any:
        return await tool.invoke(
            arguments=context_obj.arguments,
            context=context_obj,
            tool_call_id=call_id,
        )

    from ._middleware import MiddlewareTermination

    # MiddlewareTermination bubbles up to signal loop termination
    try:
        function_result = await middleware_pipeline.execute(
            context=middleware_context,
            final_handler=final_function_handler,
        )

        # Pass through function_approval_request directly (e.g., from security middleware)
        if isinstance(function_result, Content) and function_result.type == "function_approval_request":
            return function_result

        return Content.from_function_result(call_id=call_id, result=function_result)
    except MiddlewareTermination as term_exc:
        # Re-raise to signal loop termination, but first capture any result set by middleware
        if middleware_context.result is not None:
            # Pass through function_approval_request directly (e.g., from security policy middleware)
            # so the approval flow in _handle_function_call_results activates correctly.
            if (
                isinstance(middleware_context.result, Content)
                and middleware_context.result.type == "function_approval_request"
            ):
                term_exc.result = middleware_context.result
            else:
                # Store result in exception for caller to extract
                term_exc.result = Content.from_function_result(
                    call_id=call_id,
                    result=middleware_context.result,
                    additional_properties=function_call_content.additional_properties,
                )
        raise
    except (MiddlewareFailure, UserInputRequiredException):
        # MiddlewareFailure is the loop's explicit fail-closed escape: middleware that
        # must abort the run (enforcement layers, guardrails) raises it instead of
        # relying on the tool-error conversion below, and it propagates to the caller.
        raise
    except Exception as exc:
        return _function_execution_error_result(function_call_content, tool.name, exc, config)


def _get_tool_map(
    tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]],
) -> dict[str, FunctionTool]:
    return {
        tool_item.name: tool_item
        for tool_item in _ensure_unique_tool_names(tools)
        if isinstance(tool_item, FunctionTool)
    }


def _is_actionable_function_call(content: Content) -> bool:
    return content.type == "function_call" and not content.informational_only


def _underlying_function_call(content: Content) -> Content:
    if content.type == "function_approval_response" and content.function_call is not None:
        return content.function_call
    return content


async def _execute_single_function_call(
    function_call: Content,
    *,
    custom_args: dict[str, Any],
    config: FunctionInvocationConfiguration,
    tool_map: dict[str, FunctionTool],
    invocation_session: AgentSession | None,
    middleware_pipeline: FunctionMiddlewarePipeline | None,
    live_tools: list[ToolTypes] | None,
) -> tuple[list[Content], bool]:
    from ._middleware import MiddlewareTermination
    from ._sessions import _suspend_run_persistence_gate  # pyright: ignore[reportPrivateUsage]
    from ._types import Content

    try:
        # A run-persistence gate defers only the gated run's own persistence; nested
        # agent runs persist inline at their own boundaries. Run-identity ownership
        # (see _sessions._RunPersistenceGate.accepts) enforces that for every run that
        # stamps an identity; suspending the gate around the tool invocation (the most
        # common nesting seam) additionally covers nested agents with fully custom run
        # loops, which never stamp one and would otherwise inherit the outer identity.
        with _suspend_run_persistence_gate():
            result = await _auto_invoke_function(
                function_call_content=function_call,
                custom_args=custom_args,
                tool_map=tool_map,
                invocation_session=invocation_session,
                middleware_pipeline=middleware_pipeline,
                config=config,
                live_tools=live_tools,
            )
        return [result], False
    except MiddlewareTermination as exc:
        if isinstance(exc.result, Content):
            return [exc.result], True
        source_function_call = _underlying_function_call(function_call)
        return [
            Content.from_function_result(
                call_id=source_function_call.call_id,  # type: ignore[arg-type]
                result=exc.result,
            )
        ], True
    except UserInputRequiredException as exc:
        source_function_call = _underlying_function_call(function_call)
        call_id = source_function_call.call_id
        propagated_contents = [item for item in exc.contents if isinstance(item, Content)] if exc.contents else []
        for item in propagated_contents:
            item.call_id = call_id
            if not item.id:
                item.id = call_id
        if propagated_contents:
            return propagated_contents, False
        return [
            Content.from_function_result(
                call_id=call_id,  # type: ignore[arg-type]
                result="Tool requires user input but no request details were provided.",
                exception="UserInputRequiredException",
            )
        ], False


async def _try_execute_function_call_groups(
    custom_args: dict[str, Any],
    function_calls: Sequence[Content],
    tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]],
    config: FunctionInvocationConfiguration,
    invocation_session: AgentSession | None = None,
    middleware_pipeline: FunctionMiddlewarePipeline | None = None,
) -> tuple[list[list[Content]], bool]:
    """Execute multiple function calls concurrently while preserving per-call result groups.

    Args:
        custom_args: Custom arguments to pass to each function.
        function_calls: A sequence of FunctionCallContent to execute.
        tools: The tools available for execution.
        config: Configuration for function invocation.
        invocation_session: The agent session for this invocation, if any.
        middleware_pipeline: Optional middleware pipeline to apply during execution.

    Returns:
        A tuple of:
        - One ordered content group per function call.
        - True when function middleware requested loop termination.
    """
    from ._types import Content

    # Normalize the batch to calls owned by this layer before making any control-flow decision.
    function_calls = [
        function_call
        for function_call in function_calls
        if function_call.type == "function_approval_response" or _is_actionable_function_call(function_call)
    ]
    if not function_calls:
        return [], False

    tool_map = _get_tool_map(tools)
    # The live tools list (when tools is the run-local list) is exposed on the
    # FunctionInvocationContext so tools can add/remove tools during the run.
    live_tools: list[ToolTypes] | None = cast("list[ToolTypes]", tools) if isinstance(tools, list) else None
    approval_tool_names = {tool_name for tool_name, tool in tool_map.items() if tool.approval_mode == "always_require"}
    logger.debug(
        "_try_execute_function_calls: tool_map keys=%s, approval_tools=%s",
        list(tool_map.keys()),
        approval_tool_names,
    )
    declaration_only_tool_names = {tool_name for tool_name, tool in tool_map.items() if tool.declaration_only}
    additional_tool_names = {tool.name for tool in config.get("additional_tools") or []}
    actionable_calls = [
        function_call for function_call in function_calls if _is_actionable_function_call(function_call)
    ]

    # Classify the entire batch first: any required user interaction pauses the batch before execution.
    requires_approval = False
    has_declaration_only_call = False
    # A user-input pause takes precedence over unknown-call termination in mixed batches.
    for function_call in actionable_calls:
        function_name = function_call.name
        logger.debug(
            "Checking function call: type=%s, name=%s, in approval_tools=%s",
            function_call.type,
            function_name,
            function_name in approval_tool_names,
        )
        if function_name in approval_tool_names:
            logger.debug("Approval needed for function: %s", function_name)
            requires_approval = True
            break
        if function_name in declaration_only_tool_names or function_name in additional_tool_names:
            has_declaration_only_call = True
            break
        if config.get("terminate_on_unknown_calls", False) and function_name not in tool_map:
            raise KeyError(f'Error: Requested function "{function_name}" not found.')
    if requires_approval:
        # Surface only the approvals the host must decide; session-backed safe siblings wait for that resume.
        # approval can only be needed for Function Call Content, not Approval Responses.
        logger.debug("Returning visible function_approval_request contents and storing already-approved requests")
        visible_requests: list[Content] = []
        already_approved_requests: list[Content] = []
        for function_call in function_calls:
            if function_call.type != "function_call":
                continue
            approval_request = Content.from_function_approval_request(
                id=function_call.id or function_call.call_id,  # type: ignore[arg-type]
                function_call=function_call,
            )
            tool_name = function_call.name
            if tool_name is None:
                visible_requests.append(approval_request)
                continue
            tool = tool_map.get(tool_name)
            if (
                tool_name in approval_tool_names
                or tool is None
                or tool_name in declaration_only_tool_names
                or tool_name in additional_tool_names
            ):
                visible_requests.append(approval_request)
                continue
            if invocation_session is None:
                visible_requests.append(approval_request)
                continue
            already_approved_requests.append(approval_request)
        _store_already_approved_approval_requests(
            invocation_session,
            visible_requests,
            already_approved_requests,
        )
        _store_pending_approval_requests(invocation_session, visible_requests)
        return [[request] for request in visible_requests], False
    if has_declaration_only_call:
        # Declaration-only calls are returned as user input rather than executed locally.
        # return the declaration only tools to the user, since we cannot execute them.
        # Mark as user_input_request so AgentExecutor emits request_info events and pauses the workflow.
        declaration_only_calls: list[Content] = []
        for function_call in function_calls:
            if function_call.type == "function_call":
                function_call.user_input_request = True
                if function_call.id is None:
                    function_call.id = function_call.call_id
                declaration_only_calls.append(function_call)
        return [[function_call] for function_call in declaration_only_calls], False

    # Only a fully executable batch reaches this point; run calls concurrently but retain per-call result groups.
    # Create each task inside a copied context so the active agent span is
    # preserved for every parallel tool invocation.
    execution_tasks = [
        contextvars.copy_context().run(
            asyncio.create_task,
            _execute_single_function_call(
                function_call,
                custom_args=custom_args,
                config=config,
                tool_map=tool_map,
                invocation_session=invocation_session,
                middleware_pipeline=middleware_pipeline,
                live_tools=live_tools,
            ),
        )
        for function_call in function_calls
    ]
    try:
        execution_results = await asyncio.gather(*execution_tasks)
    except BaseException:
        # A loud escape from one call (e.g. MiddlewareFailure aborting the run
        # fail-closed) fails the whole batch: cancel in-flight siblings and wait for
        # them so no new tool work starts after the loop is abandoned. Cancellation
        # is cooperative — a synchronous tool body already running in a worker thread
        # (asyncio.to_thread) cannot be interrupted and may complete its side effects,
        # but its result is discarded with the batch and never reaches the transcript,
        # the model, or history.
        for task in execution_tasks:
            task.cancel()
        await asyncio.gather(*execution_tasks, return_exceptions=True)
        raise

    should_terminate = any(terminate for _, terminate in execution_results)
    return [result_contents for result_contents, _ in execution_results], should_terminate


@dataclass
class _FunctionExecutionBatch:
    """Results from one ordered batch of function-call executions."""

    result_groups: list[list[Content]]
    should_terminate: bool = False

    @property
    def contents(self) -> list[Content]:
        """Flatten the ordered result groups for ordinary response processing."""
        return [content for result_group in self.result_groups for content in result_group]

    @property
    def had_errors(self) -> bool:
        """Whether any execution produced an error result."""
        return any(
            content.exception is not None
            for result_group in self.result_groups
            for content in result_group
            if content.type == "function_result"
        )


async def _execute_function_calls(
    *,
    custom_args: dict[str, Any],
    function_calls: list[Content],
    options: dict[str, Any] | None,
    config: FunctionInvocationConfiguration,
    invocation_session: AgentSession | None = None,
    middleware_pipeline: FunctionMiddlewarePipeline | None = None,
) -> _FunctionExecutionBatch:
    tools = _extract_tools(options)
    if not tools:
        return _FunctionExecutionBatch(result_groups=[])
    result_groups, should_terminate = await _try_execute_function_call_groups(
        custom_args=custom_args,
        function_calls=function_calls,
        tools=tools,
        invocation_session=invocation_session,
        middleware_pipeline=middleware_pipeline,
        config=config,
    )
    return _FunctionExecutionBatch(
        result_groups=result_groups,
        should_terminate=should_terminate,
    )


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
        kwargs["chat_options"]["conversation_id"] = conversation_id
    else:
        kwargs["conversation_id"] = conversation_id

    # Also update options since some clients (e.g., AssistantsClient) read conversation_id from options
    if options is not None:
        options["conversation_id"] = conversation_id


def _clear_internal_conversation_id(response: ChatResponse[Any]) -> ChatResponse[Any]:
    if response.has_internal_conversation_id():
        response.conversation_id = None
        response.clear_internal_conversation_id()
    return response


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


def _is_approval_granted(value: Any) -> bool:
    """Return whether an approval decision is the strict boolean ``True``."""
    return value is True


def _is_unexecutable_local_tool_content(content: Content) -> bool:
    if _is_actionable_function_call(content):
        return True
    return content.type == "function_approval_request" and not _is_hosted_tool_approval(content)


def _response_has_visible_content(response: ChatResponse[Any]) -> bool:
    for message in response.messages:
        for content in message.contents:
            if content.type == "text":
                if content.text and content.text.strip():
                    return True
            elif content.type in _USER_VISIBLE_CONTENT_TYPES:
                return True
    return False


def _response_has_hosted_tool_approval(response: ChatResponse[Any]) -> bool:
    return any(
        content.type == "function_approval_request" and _is_hosted_tool_approval(content)
        for message in response.messages
        for content in message.contents
    )


def _drop_unexecutable_tool_contents_from_response(response: ChatResponse[Any]) -> None:
    for message in response.messages:
        if any(_is_unexecutable_local_tool_content(content) for content in message.contents):
            message.contents = [
                content for content in message.contents if not _is_unexecutable_local_tool_content(content)
            ]


def _ensure_function_invocation_limit_fallback_response(response: ChatResponse[Any]) -> bool:
    _drop_unexecutable_tool_contents_from_response(response)
    if _response_has_visible_content(response) or _response_has_hosted_tool_approval(response):
        return False

    from ._types import Content, Message

    fallback_content = Content.from_text(_FUNCTION_INVOCATION_LIMIT_FALLBACK_TEXT)
    if response.messages and not response.messages[-1].contents:
        response.messages[-1].role = "assistant"
        response.messages[-1].contents = [fallback_content]
    else:
        response.messages.append(Message(role="assistant", contents=[fallback_content]))
    return True


def _function_invocation_limit_fallback_update() -> ChatResponseUpdate:
    from ._types import ChatResponseUpdate, Content

    return ChatResponseUpdate(
        contents=[Content.from_text(_FUNCTION_INVOCATION_LIMIT_FALLBACK_TEXT)],
        role="assistant",
        finish_reason="stop",
    )


def _update_has_meaningful_metadata(update: ChatResponseUpdate) -> bool:
    return any((
        update.author_name is not None,
        update.response_id is not None,
        update.message_id is not None,
        update.conversation_id is not None,
        update.model is not None,
        update.created_at is not None,
        update.finish_reason is not None,
        update.continuation_token is not None,
        bool(update.additional_properties),
        update.raw_representation is not None,
    ))


def _drop_unexecutable_tool_contents_from_update(update: ChatResponseUpdate) -> ChatResponseUpdate | None:
    if not any(_is_unexecutable_local_tool_content(content) for content in update.contents):
        return update
    update.contents = [content for content in update.contents if not _is_unexecutable_local_tool_content(content)]
    return update if update.contents or _update_has_meaningful_metadata(update) else None


def _extract_tools(
    options: dict[str, Any] | None,
) -> ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None:
    """Extract tools from options dict.

    Args:
        options: The options dict containing chat options.

    Returns:
        ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None
    """
    return options.get("tools") if options else None


def _get_tool_approval_state(invocation_session: AgentSession | None) -> dict[str, Any] | None:
    """Return the shared tool-approval state bag for the invocation session."""
    if invocation_session is None:
        return None
    raw_state = invocation_session.state.get(_TOOL_APPROVAL_STATE_KEY)
    if isinstance(raw_state, dict):
        return cast(dict[str, Any], raw_state)
    from ._harness._tool_approval import ToolApprovalState

    if isinstance(raw_state, ToolApprovalState):
        serialized_state = raw_state.to_dict(exclude={"type"})
        invocation_session.state[_TOOL_APPROVAL_STATE_KEY] = serialized_state
        return serialized_state
    if raw_state is not None:
        raise TypeError(
            f"Session state for {_TOOL_APPROVAL_STATE_KEY!r} must be a dict or ToolApprovalState, "
            f"got {type(raw_state).__name__}."
        )
    new_state: dict[str, Any] = {}
    invocation_session.state[_TOOL_APPROVAL_STATE_KEY] = new_state
    return new_state


def _content_from_state(value: Any) -> Content | None:
    """Restore a Content item stored in session state."""
    from ._types import Content

    if isinstance(value, Content):
        return value
    if isinstance(value, Mapping):
        return Content.from_dict(cast(Mapping[str, Any], value))
    return None


def _load_pending_approval_requests(invocation_session: AgentSession | None) -> dict[str, Content]:
    """Load immutable approval-request snapshots keyed by request ID."""
    state = _get_tool_approval_state(invocation_session)
    if state is None:
        return {}
    raw_requests = state.get(_PENDING_APPROVAL_REQUESTS_KEY, [])
    if not isinstance(raw_requests, list):
        return {}
    pending: dict[str, Content] = {}
    for raw_request in cast(list[Any], raw_requests):
        request = _content_from_state(raw_request)
        if request is not None and request.type == "function_approval_request" and request.id is not None:
            if request.id in pending:
                raise ValueError(f"Duplicate pending approval request id {request.id!r}.")
            pending[request.id] = request
    return pending


def _save_pending_approval_requests(
    invocation_session: AgentSession | None,
    pending_requests: Mapping[str, Content],
) -> None:
    """Persist the active approval-request batch."""
    state = _get_tool_approval_state(invocation_session)
    if state is None:
        return
    if pending_requests:
        state[_PENDING_APPROVAL_REQUESTS_KEY] = [request.to_dict() for request in pending_requests.values()]
    else:
        state.pop(_PENDING_APPROVAL_REQUESTS_KEY, None)


def _store_pending_approval_requests(
    invocation_session: AgentSession | None,
    approval_requests: Sequence[Content],
) -> None:
    """Replace the active batch with immutable snapshots of surfaced approval requests."""
    if invocation_session is None:
        return
    pending: dict[str, Content] = {}
    for request in approval_requests:
        if request.type != "function_approval_request" or request.id is None:
            continue
        if request.id in pending:
            raise ValueError(f"Duplicate approval request id {request.id!r} in the active batch.")
        snapshot = _content_from_state(request.to_dict())
        if snapshot is not None:
            pending[request.id] = snapshot
    _save_pending_approval_requests(invocation_session, pending)
    state = _get_tool_approval_state(invocation_session)
    if state is None:
        return
    raw_groups = state.get(_ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY)
    if not isinstance(raw_groups, list):
        return
    active_ids = set(pending)
    active_groups: list[Any] = []
    for raw_group in cast(list[Any], raw_groups):
        if not isinstance(raw_group, Mapping):
            continue
        group = cast(Mapping[str, Any], raw_group)
        raw_ids = group.get("approval_request_ids")
        if not isinstance(raw_ids, list):
            continue
        group_ids = {str(item) for item in cast(list[Any], raw_ids)}
        if group_ids.issubset(active_ids):
            active_groups.append(raw_group)
    if active_groups:
        state[_ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY] = active_groups
    else:
        state.pop(_ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY, None)


def _bind_approval_response_to_pending_request(
    response: Content,
    invocation_session: AgentSession | None,
    *,
    consume: bool,
) -> Content | None:
    """Bind one approval response to a session-recorded request."""
    from ._types import Content

    if invocation_session is None:
        return response
    pending = _load_pending_approval_requests(invocation_session)
    request_key = response.id
    request = pending.get(request_key) if request_key is not None else None

    # During the staged migration, accept the occurrence id even if an intermediate
    # producer still stored the provider call_id as the request id. This is not a
    # call_id alias: the lookup uses the stored function_call.id only.
    if request is None and response.id is not None:
        matching_occurrences = [
            (pending_id, candidate)
            for pending_id, candidate in pending.items()
            if not _is_hosted_tool_approval(candidate)
            and candidate.function_call is not None
            and candidate.function_call.id == response.id
        ]
        if len(matching_occurrences) == 1:
            request_key, request = matching_occurrences[0]

    if request is None or request.function_call is None or request_key is None:
        return None

    stored_call = request.function_call
    is_hosted = _is_hosted_tool_approval(request)
    occurrence_id = stored_call.id
    if not is_hosted and occurrence_id is not None:
        embedded_call = response.function_call
        uses_occurrence_id = response.id == occurrence_id
        uses_legacy_request_id = response.id == request.id
        if not uses_occurrence_id:
            if not (uses_legacy_request_id and embedded_call is not None and embedded_call.id == occurrence_id):
                return None
            warnings.warn(
                "An occurrence-aware approval used the legacy provider call_id request binding. "
                "Return function_call.id as the approval response id; legacy request-id binding will be removed "
                "in a future release.",
                FutureWarning,
                stacklevel=3,
            )
        elif embedded_call is not None and embedded_call.id != occurrence_id:
            return None
    elif not is_hosted:
        warnings.warn(
            "Resuming a legacy stored approval whose function_call has no Content.id. This exact request-id "
            "compatibility path is deprecated; complete the pending approval and store occurrence-aware snapshots "
            "before support is removed in a future release.",
            FutureWarning,
            stacklevel=3,
        )

    rebound_call = _content_from_state(stored_call.to_dict())
    if rebound_call is None:
        return None
    rebound_id = occurrence_id if not is_hosted and occurrence_id is not None else response.id
    rebound = Content.from_function_approval_response(
        approved=_is_approval_granted(response.approved),
        id=rebound_id,  # type: ignore[arg-type]
        function_call=rebound_call,
        annotations=response.annotations,
        additional_properties=copy.deepcopy(response.additional_properties),
        raw_representation=response.raw_representation,
    )
    if consume:
        pending.pop(request_key, None)
        _save_pending_approval_requests(invocation_session, pending)
    return rebound


def _bind_approval_responses_to_pending_requests(
    messages: list[Message],
    invocation_session: AgentSession | None,
) -> None:
    """Rebind approval responses and remove unissued or duplicate responses."""
    if invocation_session is None:
        return

    filtered_messages: list[Message] = []
    for message in messages:
        filtered_contents: list[Content] = []
        for content in message.contents:
            if content.type != "function_approval_response":
                filtered_contents.append(content)
                continue
            rebound = _bind_approval_response_to_pending_request(
                content,
                invocation_session,
                consume=True,
            )
            if rebound is None:
                logger.warning(
                    "Ignored an approval response with id %r because it did not match the active approval "
                    "occurrence identity; the pending request was retained for retry.",
                    content.id,
                )
                continue
            filtered_contents.append(rebound)
        if filtered_contents:
            message.contents = filtered_contents
            filtered_messages.append(message)
    messages[:] = filtered_messages


def _store_already_approved_approval_requests(
    invocation_session: AgentSession | None,
    visible_approval_requests: Sequence[Content],
    already_approved_requests: Sequence[Content],
) -> None:
    """Store hidden already-approved requests keyed by the visible approvals that resume the batch."""
    if not already_approved_requests:
        return
    state = _get_tool_approval_state(invocation_session)
    if state is None:
        return
    visible_ids = [request.id for request in visible_approval_requests if request.id]
    if not visible_ids:
        return

    existing_groups = state.get(_ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY)
    pending_groups = list(cast(list[Any], existing_groups)) if isinstance(existing_groups, list) else []
    pending_groups.append({
        "approval_request_ids": visible_ids,
        "approval_requests": [request.to_dict() for request in already_approved_requests],
    })
    state[_ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY] = pending_groups


def _pop_already_approved_approval_responses(
    invocation_session: AgentSession | None,
    approval_response_ids: set[str],
) -> list[Content]:
    """Pop already-approved requests for the visible approval ids being answered."""
    if not approval_response_ids:
        return []
    state = _get_tool_approval_state(invocation_session)
    if state is None:
        return []
    raw_groups = state.get(_ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY, [])
    if not isinstance(raw_groups, list):
        return []
    typed_groups = cast(list[Any], raw_groups)

    responses: list[Content] = []
    remaining_groups: list[Any] = []
    for raw_group in typed_groups:
        if not isinstance(raw_group, Mapping):
            continue
        group = cast(Mapping[str, Any], raw_group)
        raw_ids = group.get("approval_request_ids")
        group_ids: set[str] = {str(item) for item in cast(list[Any], raw_ids)} if isinstance(raw_ids, list) else set()
        if group_ids.isdisjoint(approval_response_ids):
            remaining_groups.append(raw_group)
            continue
        raw_requests = group.get("approval_requests")
        if not isinstance(raw_requests, list):
            continue
        for raw_request in cast(list[Any], raw_requests):
            request = _content_from_state(raw_request)
            if request is None or request.type != "function_approval_request":
                continue
            responses.append(request.to_function_approval_response(approved=True))
    if remaining_groups:
        state[_ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY] = remaining_groups
    else:
        state.pop(_ALREADY_APPROVED_APPROVAL_REQUEST_GROUPS_KEY, None)
    return responses


def _collect_approval_responses(
    messages: list[Message],
) -> dict[str, Content]:
    """Collect approval responses (both approved and rejected) from messages.

    Hosted tool approvals (e.g. MCP) are excluded because they must be
    forwarded to the API as-is rather than processed locally.
    """
    approval_responses: list[Content] = []
    pending_by_call_id: dict[str, deque[Content]] = {}
    resolved_response_ids: set[int] = set()
    for message in messages:
        for content in message.contents:
            if content.type == "function_approval_response" and not _is_hosted_tool_approval(content):
                function_call = content.function_call
                if function_call is None or function_call.call_id is None:
                    continue
                approval_responses.append(content)
                pending_by_call_id.setdefault(function_call.call_id, deque()).append(content)
                continue
            if content.call_id is None:
                continue
            is_terminal_result = content.type == "function_result" and not _is_approval_placeholder_result(content)
            is_follow_up_request = content.user_input_request and content.type not in {
                "function_approval_request",
                "function_approval_response",
            }
            if not (is_terminal_result or is_follow_up_request):
                continue
            pending_responses = pending_by_call_id.get(content.call_id)
            if pending_responses:
                resolved_response_ids.add(id(pending_responses.popleft()))

    return {
        content.id: content
        for content in approval_responses
        if id(content) not in resolved_response_ids and content.id is not None
    }


def _collect_unanswered_approval_requests(messages: Sequence[Message]) -> list[Content]:
    approval_requests_by_id: dict[str, Content] = {}
    pending_request_ids_by_call_id: dict[str, deque[str]] = {}
    answered_approval_ids: set[str] = set()

    for message in messages:
        for content in message.contents:
            if content.type == "function_approval_request":
                function_call = content.function_call
                if content.id is None or function_call is None or function_call.call_id is None:
                    continue
                if content.id not in approval_requests_by_id:
                    approval_requests_by_id[content.id] = content
                    pending_request_ids_by_call_id.setdefault(function_call.call_id, deque()).append(content.id)
                continue
            if content.type == "function_approval_response":
                if content.id is not None:
                    answered_approval_ids.add(content.id)
                continue
            if content.call_id is None:
                continue
            is_terminal_result = content.type == "function_result" and not _is_approval_placeholder_result(content)
            is_follow_up_request = content.user_input_request and content.type not in {
                "function_approval_request",
                "function_approval_response",
            }
            if not (is_terminal_result or is_follow_up_request):
                continue
            if request_ids := pending_request_ids_by_call_id.get(content.call_id):
                answered_approval_ids.add(request_ids.popleft())

    return [
        request for approval_id, request in approval_requests_by_id.items() if approval_id not in answered_approval_ids
    ]


def _remove_unanswered_approval_batches_from_model_input(messages: list[Message]) -> None:
    pending_requests = _collect_unanswered_approval_requests(messages)
    if not pending_requests:
        return

    pending_approval_ids = {request.id for request in pending_requests if request.id is not None}
    pending_call_ids = {
        request.function_call.call_id
        for request in pending_requests
        if request.function_call is not None and request.function_call.call_id is not None
    }
    open_calls_by_id: dict[str, deque[tuple[Content, int]]] = {}
    bound_call_content_ids: set[int] = set()
    call_batch_message_indices: set[int] = set()
    bound_approval_ids: set[str] = set()

    for message_index, message in enumerate(messages):
        for content in message.contents:
            if content.type == "function_call" and content.call_id:
                open_calls_by_id.setdefault(content.call_id, deque()).append((content, message_index))
                continue
            if content.type == "function_result" and content.call_id:
                if open_calls := open_calls_by_id.get(content.call_id):
                    resolved_call, _ = open_calls.popleft()
                    bound_call_content_ids.discard(id(resolved_call))
                continue
            if (
                content.type != "function_approval_request"
                or content.id is None
                or content.id not in pending_approval_ids
                or content.id in bound_approval_ids
                or content.function_call is None
                or content.function_call.call_id is None
            ):
                continue
            bound_approval_ids.add(content.id)
            open_calls = open_calls_by_id.get(content.function_call.call_id)
            bound_call = next(
                (call for call in open_calls or () if id(call[0]) not in bound_call_content_ids),
                None,
            )
            if bound_call is None:
                call_batch_message_indices.add(message_index)
            else:
                bound_call_content_ids.add(id(bound_call[0]))
                call_batch_message_indices.add(bound_call[1])

    unanswered_call_content_ids = {
        id(function_call) for open_calls in open_calls_by_id.values() for function_call, _ in open_calls
    }
    fully_pending_call_message_indices: set[int] = set()
    for message_index in call_batch_message_indices:
        call_contents = [
            content
            for content in messages[message_index].contents
            if content.type in {"function_call", "mcp_server_tool_call"}
        ]
        if call_contents and all(
            id(content) in unanswered_call_content_ids or content.call_id in pending_call_ids
            for content in call_contents
        ):
            fully_pending_call_message_indices.add(message_index)

    for call_message_index in tuple(fully_pending_call_message_indices):
        reasoning_index = call_message_index - 1
        while (
            reasoning_index >= 0
            and messages[reasoning_index].role == "assistant"
            and messages[reasoning_index].contents
            and all(content.type == "text_reasoning" for content in messages[reasoning_index].contents)
        ):
            fully_pending_call_message_indices.add(reasoning_index)
            reasoning_index -= 1

    filtered_messages: list[Message] = []
    for message_index, message in enumerate(messages):
        filtered_contents = [
            content
            for content in message.contents
            if not (
                (content.type == "function_approval_request" and content.id in pending_approval_ids)
                or (
                    message_index in call_batch_message_indices
                    and (
                        (content.type == "function_call" and id(content) in unanswered_call_content_ids)
                        or (content.type == "mcp_server_tool_call" and content.call_id in pending_call_ids)
                    )
                )
                or (message_index in fully_pending_call_message_indices and content.type == "text_reasoning")
            )
        ]
        if not filtered_contents:
            continue
        message.contents = filtered_contents
        filtered_messages.append(message)
    messages[:] = filtered_messages


def _is_approval_placeholder_result(content: Content) -> bool:
    """Whether a function_result is the stand-in emitted while approval is pending."""
    result = getattr(content, "result", None)
    return isinstance(result, str) and "[APPROVAL_PENDING]" in result


@dataclass
class _ApprovalCallOccurrence:
    function_call: Content
    approval_id: str | None = None
    placeholder_message: Message | None = None
    placeholder_content: Content | None = None
    closed: bool = False


def _replace_approval_contents_with_results(
    messages: list[Message],
    pending_approval_responses: dict[str, Content],
    approved_function_result_groups: list[list[Content]],
) -> list[Content]:
    """Replace approval request/response contents with function call/result contents in-place.

    Also replaces placeholder tool results (marked with [APPROVAL_PENDING]) with actual results.

    Returns:
        The terminal contents produced while resolving the approval responses, in response order.
    """
    from ._types import (
        Content,
    )

    result_groups_by_call_id: dict[str, deque[list[Content]]] = {}
    for result_group in approved_function_result_groups:
        call_id = next((result.call_id for result in result_group if result.call_id is not None), None)
        if call_id is not None:
            result_groups_by_call_id.setdefault(call_id, deque()).append(result_group)

    occurrences_by_call_id: dict[str, list[_ApprovalCallOccurrence]] = {}
    occurrences_by_approval_id: dict[str, list[_ApprovalCallOccurrence]] = {}
    seen_approval_requests: set[tuple[str, str, str | None, str]] = set()
    placeholder_replacements: list[tuple[Message, Content, list[Content]]] = []
    resolved_contents: list[Content] = []

    def find_open_occurrence(call_id: str, *, require_unbound: bool = False) -> _ApprovalCallOccurrence | None:
        for occurrence in occurrences_by_call_id.get(call_id, []):
            if occurrence.closed:
                continue
            if require_unbound and occurrence.approval_id is not None:
                continue
            return occurrence
        return None

    def find_approval_occurrence(approval_id: str) -> _ApprovalCallOccurrence | None:
        for occurrence in occurrences_by_approval_id.get(approval_id, []):
            if not occurrence.closed:
                return occurrence
        return None

    for msg in messages:
        contents_to_remove: list[int] = []
        replacement_groups_by_index: dict[int, list[Content]] = {}

        for content_idx, content in enumerate(msg.contents):
            if content.type == "function_call" and content.call_id:
                occurrences_by_call_id.setdefault(content.call_id, []).append(
                    _ApprovalCallOccurrence(function_call=content)
                )
            elif content.type == "function_approval_request":
                if _is_hosted_tool_approval(content):
                    continue
                if content.function_call is None or content.function_call.call_id is None or content.id is None:
                    continue
                call_id = content.function_call.call_id
                occurrence = find_open_occurrence(call_id, require_unbound=True)
                request_identity = (
                    content.id,
                    call_id,
                    content.function_call.name,
                    str(content.function_call.arguments),
                )
                if occurrence is None and request_identity in seen_approval_requests:
                    contents_to_remove.append(content_idx)
                    continue
                seen_approval_requests.add(request_identity)
                if occurrence is None:
                    occurrence = _ApprovalCallOccurrence(
                        function_call=content.function_call,
                        approval_id=content.id,
                    )
                    occurrences_by_call_id.setdefault(call_id, []).append(occurrence)
                    msg.contents[content_idx] = content.function_call
                else:
                    occurrence.approval_id = content.id
                    contents_to_remove.append(content_idx)
                occurrences_by_approval_id.setdefault(content.id, []).append(occurrence)
            elif content.type == "function_approval_response":
                if _is_hosted_tool_approval(content):
                    continue
                if content.function_call is None or content.function_call.call_id is None or content.id is None:
                    continue
                if content.id not in pending_approval_responses:
                    contents_to_remove.append(content_idx)
                    continue
                call_id = content.function_call.call_id
                occurrence = find_approval_occurrence(content.id)
                if occurrence is None:
                    occurrence = find_open_occurrence(call_id)
                replacements: list[Content] | None
                if _is_approval_granted(content.approved):
                    call_result_groups = result_groups_by_call_id.get(call_id)
                    replacements = call_result_groups.popleft() if call_result_groups else None
                else:
                    replacements = [
                        Content.from_function_result(
                            call_id=call_id,
                            result="Error: Tool call invocation was rejected by user.",
                            additional_properties=content.function_call.additional_properties,
                        )
                    ]
                if not replacements:
                    continue
                if (
                    occurrence is not None
                    and occurrence.placeholder_message is not None
                    and occurrence.placeholder_content is not None
                ):
                    placeholder_replacements.append((
                        occurrence.placeholder_message,
                        occurrence.placeholder_content,
                        replacements,
                    ))
                    contents_to_remove.append(content_idx)
                else:
                    replacement_groups_by_index[content_idx] = replacements
                if occurrence is not None:
                    occurrence.closed = True
                resolved_contents.extend(replacements)
            elif content.type == "function_result":
                if content.call_id is None:
                    continue
                occurrence = find_open_occurrence(content.call_id)
                if occurrence is None:
                    continue
                if _is_approval_placeholder_result(content):
                    occurrence.placeholder_message = msg
                    occurrence.placeholder_content = content
                else:
                    occurrence.closed = True

        if replacement_groups_by_index:
            msg.role = (
                "assistant"
                if any(
                    replacement.user_input_request
                    for replacements in replacement_groups_by_index.values()
                    for replacement in replacements
                )
                else "tool"
            )
        if contents_to_remove or replacement_groups_by_index:
            removed_indexes = set(contents_to_remove)
            updated_contents: list[Content] = []
            for idx, existing in enumerate(msg.contents):
                if idx in removed_indexes:
                    continue
                replacements = replacement_groups_by_index.get(idx)
                if replacements is not None:
                    updated_contents.extend(replacements)
                else:
                    updated_contents.append(existing)
            msg.contents = updated_contents

    for placeholder_message, placeholder_content, replacements in placeholder_replacements:
        for idx, existing in enumerate(placeholder_message.contents):
            if existing is placeholder_content:
                placeholder_message.contents[idx : idx + 1] = replacements
                break

    messages_to_remove: list[int] = []
    for msg_idx, msg in enumerate(messages):
        if not msg.contents:
            messages_to_remove.append(msg_idx)
    for msg_idx in reversed(messages_to_remove):
        messages.pop(msg_idx)
    return resolved_contents


def _extract_function_calls(response: ChatResponse) -> list[Content]:
    completed_occurrence_ids: set[str] = set()
    open_occurrence_ids_by_call_id: dict[str, deque[str]] = {}
    seen_occurrence_ids: set[str] = set()
    candidate_calls: list[Content] = []
    for message in response.messages:
        for item in message.contents:
            if item.type == "function_result" and item.call_id:
                if open_occurrence_ids := open_occurrence_ids_by_call_id.get(item.call_id):
                    completed_occurrence_ids.add(open_occurrence_ids.popleft())
                continue
            if not _is_actionable_function_call(item):
                continue
            if item.id is None:
                item.id = _generate_function_call_occurrence_id()
            if not item.call_id:
                item.call_id = item.id
                warnings.warn(
                    "An actionable function_call had an empty call_id. Agent Framework used its generated "
                    "Content.id for local correlation. Providers should supply and preserve their service call_id; "
                    "this fallback will be removed in a future release.",
                    FutureWarning,
                    stacklevel=3,
                )
            if item.id in seen_occurrence_ids:
                continue
            seen_occurrence_ids.add(item.id)
            candidate_calls.append(item)
            open_occurrence_ids_by_call_id.setdefault(item.call_id, deque()).append(item.id)
    return [function_call for function_call in candidate_calls if function_call.id not in completed_occurrence_ids]


def _prepend_function_call_messages(response: ChatResponse, function_call_messages: list[Message]) -> None:
    response.messages[:0] = function_call_messages


def _copy_messages_for_function_invocation(messages: Any) -> list[Message]:
    from ._types import normalize_messages

    copied_messages: list[Message] = []
    for message in normalize_messages(messages):
        copied_message = copy.copy(message)
        copied_message.contents = list(message.contents)
        copied_message.additional_properties = dict(message.additional_properties)
        copied_messages.append(copied_message)
    return copied_messages


def _function_call_limit_reached(total_function_calls: int, max_function_calls: int | None) -> bool:
    return max_function_calls is not None and total_function_calls >= max_function_calls


def _update_consecutive_error_count(
    errors_in_a_row: int,
    *,
    had_errors: bool,
    max_errors: int,
) -> tuple[int, bool]:
    if not had_errors:
        return 0, False
    errors_in_a_row += 1
    reached_error_limit = errors_in_a_row >= max_errors
    if reached_error_limit:
        logger.warning(
            "Maximum consecutive function call errors reached (%d). Stopping further function calls for this request.",
            max_errors,
        )
    return errors_in_a_row, reached_error_limit


def _disable_tools_at_function_call_limit(
    options: dict[str, Any],
    total_function_calls: int,
    max_function_calls: int | None,
) -> None:
    if not _function_call_limit_reached(total_function_calls, max_function_calls):
        return
    logger.info(
        "Maximum function calls reached (%d/%d). Stopping further function calls for this request.",
        total_function_calls,
        max_function_calls,
    )
    options["tool_choice"] = "none"


def _record_function_calls(
    budget_state: dict[str, Any],
    total_function_calls: int,
    function_call_count: int,
) -> int:
    total_function_calls += function_call_count
    budget_state["total_function_calls"] = total_function_calls
    return total_function_calls


def _reset_required_tool_choice(options: dict[str, Any]) -> None:
    tool_choice = options.get("tool_choice")
    required_mode = isinstance(tool_choice, Mapping) and cast(Mapping[str, Any], tool_choice).get("mode") == "required"
    if tool_choice == "required" or required_mode:
        options["tool_choice"] = None


def _prepare_messages_for_next_iteration(prepared_messages: list[Message], response: ChatResponse[Any]) -> None:
    if response.conversation_id is None:
        prepared_messages.extend(response.messages)
        return
    prepared_messages[:] = response.messages[-1:]


@dataclass
class _FunctionProcessingResult:
    """Control data produced while resolving or executing function calls."""

    errors_in_a_row: int
    action: Literal["return", "continue", "stop"] = "continue"
    function_call_count: int = 0
    response_messages: tuple[Message, ...] = ()
    streaming_updates: tuple[ChatResponseUpdate, ...] = ()


_FunctionCallExecutor: TypeAlias = Callable[..., Awaitable[_FunctionExecutionBatch]]


def _messages_and_updates_for_terminal_contents(
    contents: Sequence[Content],
) -> tuple[tuple[Message, ...], tuple[ChatResponseUpdate, ...]]:
    from ._types import ChatResponseUpdate, Message

    messages: list[Message] = []
    updates: list[ChatResponseUpdate] = []
    current_role: Literal["assistant", "tool"] | None = None
    current_contents: list[Content] = []

    for content in contents:
        role: Literal["assistant", "tool"] = (
            "assistant" if content.type == "function_call" or content.user_input_request else "tool"
        )
        if current_role is not None and role != current_role:
            messages.append(Message(role=current_role, contents=current_contents))
            updates.append(ChatResponseUpdate(role=current_role, contents=current_contents))
            current_contents = []
        current_role = role
        current_contents.append(content)

    if current_role is not None:
        messages.append(Message(role=current_role, contents=current_contents))
        updates.append(ChatResponseUpdate(role=current_role, contents=current_contents))
    return tuple(messages), tuple(updates)


def _handle_function_call_results(
    *,
    response: ChatResponse,
    execution_results: list[Content],
    function_call_count: int,
    function_call_messages: list[Message] | None,
    errors_in_a_row: int,
    had_errors: bool,
    max_errors: int,
) -> _FunctionProcessingResult:
    """Append execution results to the response and determine the next loop action."""
    from ._types import ChatResponseUpdate, Message

    if any(
        result.type in {"function_approval_request", "function_call"} or result.user_input_request
        for result in execution_results
    ):
        # Only add items that aren't already in the message (e.g. function_approval_request wrappers).
        # Declaration-only function_call items are already present from the LLM response.
        new_items = [result for result in execution_results if result.type != "function_call"]
        if new_items:
            if response.messages and response.messages[0].role == "assistant":
                response.messages[0].contents.extend(new_items)
            else:
                response.messages.append(Message(role="assistant", contents=new_items))
        streaming_items: list[Content] = []
        for result in execution_results:
            if result.type == "function_call":
                metadata_only_result = copy.copy(result)
                metadata_only_result.arguments = None
                streaming_items.append(metadata_only_result)
            else:
                streaming_items.append(result)
        return _FunctionProcessingResult(
            errors_in_a_row=errors_in_a_row,
            action="return",
            function_call_count=function_call_count,
            streaming_updates=(ChatResponseUpdate(contents=streaming_items, role="assistant"),),
        )

    errors_in_a_row, reached_error_limit = _update_consecutive_error_count(
        errors_in_a_row,
        had_errors=had_errors,
        max_errors=max_errors,
    )

    response.messages.append(Message(role="tool", contents=execution_results))
    if function_call_messages is not None:
        function_call_messages.extend(response.messages)
    return _FunctionProcessingResult(
        errors_in_a_row=errors_in_a_row,
        action="stop" if reached_error_limit else "continue",
        function_call_count=function_call_count,
        streaming_updates=(ChatResponseUpdate(contents=execution_results, role="tool"),),
    )


async def _resolve_approval_responses(
    *,
    prepared_messages: list[Message],
    options: dict[str, Any] | None,
    errors_in_a_row: int,
    max_errors: int,
    execute_function_calls: _FunctionCallExecutor,
    invocation_session: AgentSession | None = None,
    settle_dangling_calls: Callable[[Sequence[Content]], Awaitable[None]] | None = None,
) -> _FunctionProcessingResult:
    """Resolve inbound approval responses before the next model call.

    ``settle_dangling_calls``, when provided, is invoked with the approved batch if
    executing it aborts with ``MiddlewareFailure``, so a service-managed conversation
    can be settled before the abort propagates (the replay's original calls belong to
    an earlier, already-persisted model turn).
    """
    from ._middleware import MiddlewareFailure
    from ._types import Message

    _bind_approval_responses_to_pending_requests(prepared_messages, invocation_session)

    # 1. Restore safe siblings hidden with a prior mixed approval batch when its visible decision arrives.
    explicit_approval_response_ids = {
        content.id
        for message in prepared_messages
        for content in message.contents
        if content.type == "function_approval_response" and content.id
    }

    if already_approved_responses := _pop_already_approved_approval_responses(
        invocation_session,
        explicit_approval_response_ids,
    ):
        prepared_messages.append(Message(role="user", contents=already_approved_responses))

    # 2. With no new decision, hide any still-pending batch from model input while keeping it resumable in history.
    if not (pending_approval_responses := _collect_approval_responses(prepared_messages)):
        _remove_unanswered_approval_batches_from_model_input(prepared_messages)
        return _FunctionProcessingResult(errors_in_a_row=errors_in_a_row)

    # 3. Execute approved decisions once. Rejected decisions are converted to results during normalization below.
    responses_to_execute = [
        response for response in pending_approval_responses.values() if _is_approval_granted(response.approved)
    ]
    execution_result_groups: list[list[Content]] = []
    should_terminate = False
    reached_error_limit = False
    if responses_to_execute:
        try:
            execution = await execute_function_calls(
                function_calls=responses_to_execute,
                options=options,
            )
        except MiddlewareFailure:
            # Fail-closed abort during an approved replay: the original calls belong
            # to an already-persisted model turn, so settle them on a service-managed
            # conversation before propagating (best-effort inside the callback).
            if settle_dangling_calls is not None:
                await settle_dangling_calls(responses_to_execute)
            raise
        execution_result_groups = execution.result_groups
        should_terminate = execution.should_terminate
        errors_in_a_row, reached_error_limit = _update_consecutive_error_count(
            errors_in_a_row,
            had_errors=execution.had_errors,
            max_errors=max_errors,
        )

    # 4. Replace approval controls/placeholders with terminal contents, correlated by logical call occurrence.
    terminal_contents = _replace_approval_contents_with_results(
        prepared_messages,
        pending_approval_responses,
        execution_result_groups,
    )
    if pending_requests := _collect_unanswered_approval_requests(prepared_messages):
        terminal_contents.extend(pending_requests)

    # 5. Return role-correct output and tell the outer loop whether to return, stop tools, or call the model.
    executed_function_count = len(execution_result_groups)
    requires_user_input = any(
        result.type == "function_call" or result.user_input_request for result in terminal_contents
    )
    response_messages, streaming_updates = _messages_and_updates_for_terminal_contents(terminal_contents)
    action: Literal["return", "continue", "stop"] = "continue"
    if should_terminate or requires_user_input:
        action = "return"
    elif reached_error_limit:
        action = "stop"
    return _FunctionProcessingResult(
        errors_in_a_row=errors_in_a_row,
        action=action,
        function_call_count=executed_function_count,
        response_messages=response_messages,
        streaming_updates=streaming_updates,
    )


async def _process_model_function_calls(
    *,
    response: ChatResponse,
    options: dict[str, Any] | None,
    function_call_messages: list[Message] | None,
    errors_in_a_row: int,
    max_errors: int,
    execute_function_calls: _FunctionCallExecutor,
    invocation_session: AgentSession | None = None,
) -> _FunctionProcessingResult:
    """Execute function calls from a newly completed model response."""
    approval_requests = [
        content
        for message in response.messages
        for content in message.contents
        if content.type == "function_approval_request"
    ]
    # 1. Extract only actionable, unanswered calls from this model turn.
    tools = _extract_tools(options)
    function_calls = _extract_function_calls(response)
    if not (function_calls and tools):
        if function_call_messages is not None:
            _prepend_function_call_messages(response, function_call_messages)
        if approval_requests:
            _store_pending_approval_requests(invocation_session, approval_requests)
        return _FunctionProcessingResult(errors_in_a_row=errors_in_a_row, action="return")

    # 2. Execute the batch once while preserving each call's result group.
    execution = await execute_function_calls(
        function_calls=function_calls,
        options=options,
    )

    # 3. Fold results into the response and translate errors or middleware termination into the next loop action.
    processing_result = _handle_function_call_results(
        response=response,
        execution_results=execution.contents,
        function_call_count=len(execution.result_groups),
        function_call_messages=function_call_messages,
        errors_in_a_row=errors_in_a_row,
        had_errors=execution.had_errors,
        max_errors=max_errors,
    )
    if execution.should_terminate:
        processing_result.action = "return"
    if processing_result.action == "return":
        returned_approval_requests = [
            content
            for message in response.messages
            for content in message.contents
            if content.type == "function_approval_request"
        ]
        if returned_approval_requests:
            _store_pending_approval_requests(invocation_session, returned_approval_requests)
    return processing_result


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
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        **kwargs: Any,
    ) -> None:
        from ._middleware import categorize_middleware

        # Chat clients install only chat and function middleware. Agent middleware in
        # a bundle raises (a bundle must never be partially installed); bare agent
        # middleware is warned about and skipped inside categorize_middleware.
        categorized_middleware = categorize_middleware(middleware, supported_categories=("chat", "function"))
        self.function_middleware: list[FunctionMiddlewareTypes] = list(categorized_middleware["function"])
        self._cached_function_middleware_pipeline: FunctionMiddlewarePipeline | None = None
        self.function_invocation_configuration = normalize_function_invocation_configuration(
            function_invocation_configuration
        )
        if (chat_middleware := (categorized_middleware["chat"] or None)) is not None:
            kwargs["middleware"] = chat_middleware
        super().__init__(**kwargs)

    def _update_function_invocation_continuation_state(
        self,
        kwargs: dict[str, Any],
        response: ChatResponse[Any],
        *,
        session: AgentSession | None,
        options: dict[str, Any] | None = None,
    ) -> None:
        """Update continuation state after a function-loop service call."""
        conversation_id = response.conversation_id
        if conversation_id is None:
            return

        _update_conversation_id(kwargs, conversation_id, options)
        if (
            session is not None
            and not response.has_internal_conversation_id()
            and session.service_session_id != conversation_id
        ):
            session.service_session_id = conversation_id

    async def _settle_dangling_service_function_calls(
        self,
        *,
        super_get_response: Callable[..., Any],
        function_calls: Sequence[Content],
        options: dict[str, Any],
        request_kwargs: dict[str, Any],
        compaction_strategy: CompactionStrategy | None,
        tokenizer: TokenizerProtocol | None,
        invocation_session: AgentSession | None,
        response_conversation_id: str | None = None,
    ) -> None:
        """Resolve an aborted batch's function calls on a service-managed conversation.

        When ``MiddlewareFailure`` aborts a tool batch, the local run raises before
        any result exists — but on a service-managed conversation the continuation
        state (``session.service_session_id``) was already persisted, so the hosted
        thread ends with unresolved ``function_call`` items and OpenAI-style
        continuations reject the session's next request (missing tool output). Settle
        the thread by submitting one error ``function_result`` per dangling call
        (approval-response wrappers are unwrapped to their underlying calls;
        hosted-tool approvals are left to their own provider protocol) with
        ``tool_choice="none"`` so no new calls are requested, then advance the
        persisted continuation to the settlement response: for response-ID
        continuations the settlement response is the first endpoint whose chain
        includes the synthetic outputs, so the next run must start from it (for
        conversation-object ids the advance is a no-op). The settlement response is
        otherwise discarded and the run still fails with the original
        ``MiddlewareFailure``. Everything here is best-effort — a settlement failure
        is logged and never masks the abort. Costs one extra request, only on the
        failure path and only when a service-managed conversation is in play.
        """
        from ._types import ChatResponse, Content, Message

        if response_conversation_id is None and not options.get("conversation_id"):
            return
        try:
            error_results: list[Content] = []
            for function_call in function_calls:
                if _is_hosted_tool_approval(function_call):
                    continue
                underlying_call = _underlying_function_call(function_call)
                if underlying_call.type != "function_call" or underlying_call.call_id is None:
                    continue
                error_results.append(
                    Content.from_function_result(
                        call_id=underlying_call.call_id,
                        result="Error: Tool execution was aborted by middleware before a result was produced.",
                        exception="MiddlewareFailure",
                        additional_properties=underlying_call.additional_properties,
                    )
                )
            if not error_results:
                return
            options["tool_choice"] = "none"
            settlement_response = await super_get_response(
                messages=[Message(role="tool", contents=error_results)],
                stream=False,
                options=options,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                client_kwargs=request_kwargs,
            )
            if isinstance(settlement_response, ChatResponse):
                self._update_function_invocation_continuation_state(
                    request_kwargs,
                    cast("ChatResponse[Any]", settlement_response),
                    session=invocation_session,
                    options=options,
                )
        except Exception:
            logger.warning(
                "Failed to settle dangling function calls on the service-managed conversation; "
                "the next request over this conversation may be rejected by the service.",
                exc_info=True,
            )

    def _get_function_middleware_pipeline(
        self,
        runtime_middleware: Sequence[FunctionMiddlewareTypes],
    ) -> FunctionMiddlewarePipeline:
        from ._middleware import FunctionMiddlewarePipeline

        effective_middleware = [*self.function_middleware, *runtime_middleware]
        if self._cached_function_middleware_pipeline is not None and self._cached_function_middleware_pipeline.matches(
            effective_middleware
        ):
            return self._cached_function_middleware_pipeline

        self._cached_function_middleware_pipeline = FunctionMiddlewarePipeline(*effective_middleware)
        return self._cached_function_middleware_pipeline

    async def _get_response_with_function_invocation(
        self,
        *,
        super_get_response: Callable[..., Any],
        messages: Sequence[Message],
        options: dict[str, Any],
        request_kwargs: dict[str, Any],
        compaction_strategy: CompactionStrategy | None,
        tokenizer: TokenizerProtocol | None,
        execute_function_calls: _FunctionCallExecutor,
        invocation_session: AgentSession | None,
        budget_state: dict[str, Any],
        max_errors: int,
    ) -> ChatResponse[Any]:
        """Run the non-streaming function invocation loop."""
        from ._middleware import MiddlewareFailure
        from ._types import ChatResponse, add_usage_details

        errors_in_a_row = 0
        total_function_calls = int(budget_state.get("total_function_calls", 0) or 0)
        max_function_calls = self.function_invocation_configuration.get("max_function_calls")
        prepared_messages = _copy_messages_for_function_invocation(messages)
        function_call_messages: list[Message] = []
        response: ChatResponse[Any] | None = None
        aggregated_usage: UsageDetails | None = None
        max_iterations = self.function_invocation_configuration.get("max_iterations", DEFAULT_MAX_ITERATIONS)
        attempt_start = int(budget_state.get("attempt_count", 0) or 0)

        async def settle_approval_replay_calls(function_calls: Sequence[Content]) -> None:
            await self._settle_dangling_service_function_calls(
                super_get_response=super_get_response,
                function_calls=function_calls,
                options=options,
                request_kwargs=request_kwargs,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                invocation_session=invocation_session,
            )

        # Phase 1: resolve inbound approvals before consuming another model iteration.
        approval_processing = await _resolve_approval_responses(
            prepared_messages=prepared_messages,
            options=options,
            errors_in_a_row=errors_in_a_row,
            max_errors=max_errors,
            execute_function_calls=execute_function_calls,
            invocation_session=invocation_session,
            settle_dangling_calls=settle_approval_replay_calls,
        )
        function_call_messages.extend(approval_processing.response_messages)
        errors_in_a_row = approval_processing.errors_in_a_row
        total_function_calls = _record_function_calls(
            budget_state,
            total_function_calls,
            approval_processing.function_call_count,
        )
        if approval_processing.action == "return":
            response = ChatResponse(messages=list(function_call_messages))
            response.usage_details = aggregated_usage
            return _clear_internal_conversation_id(response)
        if approval_processing.action == "stop":
            options["tool_choice"] = "none"
        else:
            _disable_tools_at_function_call_limit(options, total_function_calls, max_function_calls)

        # Phase 2: alternate model turns and local execution until a terminal response or safety limit is reached.
        for attempt_idx in range(attempt_start, max_iterations):
            budget_state["attempt_count"] = attempt_idx + 1
            response = cast(
                ChatResponse[Any],
                await super_get_response(
                    messages=prepared_messages,
                    stream=False,
                    options=options,
                    compaction_strategy=compaction_strategy,
                    tokenizer=tokenizer,
                    client_kwargs=request_kwargs,
                ),
            )
            if options.get("tool_choice") == "none" and _function_call_limit_reached(
                total_function_calls, max_function_calls
            ):
                _ensure_function_invocation_limit_fallback_response(response)
            aggregated_usage = add_usage_details(aggregated_usage, response.usage_details)
            self._update_function_invocation_continuation_state(
                request_kwargs,
                response,
                session=invocation_session,
                options=options,
            )

            try:
                function_processing = await _process_model_function_calls(
                    response=response,
                    options=options,
                    function_call_messages=function_call_messages,
                    errors_in_a_row=errors_in_a_row,
                    max_errors=max_errors,
                    execute_function_calls=execute_function_calls,
                    invocation_session=invocation_session,
                )
            except MiddlewareFailure:
                # Fail-closed abort: before propagating, settle the batch's calls on a
                # service-managed conversation and advance the persisted continuation
                # to the settled endpoint (best-effort — a settlement failure never
                # masks the abort).
                await self._settle_dangling_service_function_calls(
                    super_get_response=super_get_response,
                    function_calls=_extract_function_calls(response),
                    options=options,
                    request_kwargs=request_kwargs,
                    compaction_strategy=compaction_strategy,
                    tokenizer=tokenizer,
                    invocation_session=invocation_session,
                    response_conversation_id=response.conversation_id,
                )
                raise
            total_function_calls = _record_function_calls(
                budget_state,
                total_function_calls,
                function_processing.function_call_count,
            )
            if function_processing.action == "return":
                response.usage_details = aggregated_usage
                return _clear_internal_conversation_id(response)
            if function_processing.action == "stop":
                options["tool_choice"] = "none"
            else:
                _disable_tools_at_function_call_limit(options, total_function_calls, max_function_calls)
            errors_in_a_row = function_processing.errors_in_a_row
            _reset_required_tool_choice(options)
            _prepare_messages_for_next_iteration(prepared_messages, response)

        # Phase 3: the iteration budget is exhausted, so request one final response with tools disabled.
        if response is not None:
            logger.info(
                "Maximum iterations reached (%d). Requesting final response without tools.",
                max_iterations,
            )
        options["tool_choice"] = "none"
        response = cast(
            ChatResponse[Any],
            await super_get_response(
                messages=prepared_messages,
                stream=False,
                options=options,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                client_kwargs=request_kwargs,
            ),
        )
        _ensure_function_invocation_limit_fallback_response(response)
        aggregated_usage = add_usage_details(aggregated_usage, response.usage_details)
        self._update_function_invocation_continuation_state(
            request_kwargs,
            response,
            session=invocation_session,
            options=options,
        )
        response.usage_details = aggregated_usage
        _prepend_function_call_messages(response, function_call_messages)
        return _clear_internal_conversation_id(response)

    async def _stream_response_with_function_invocation(
        self,
        *,
        super_get_response: Callable[..., Any],
        messages: Sequence[Message],
        options: dict[str, Any],
        request_kwargs: dict[str, Any],
        compaction_strategy: CompactionStrategy | None,
        tokenizer: TokenizerProtocol | None,
        execute_function_calls: _FunctionCallExecutor,
        invocation_session: AgentSession | None,
        budget_state: dict[str, Any],
        max_errors: int,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Run the streaming function invocation loop."""
        from ._middleware import MiddlewareFailure

        errors_in_a_row = 0
        total_function_calls = int(budget_state.get("total_function_calls", 0) or 0)
        max_function_calls = self.function_invocation_configuration.get("max_function_calls")
        prepared_messages = _copy_messages_for_function_invocation(messages)
        response: ChatResponse[Any] | None = None
        max_iterations = self.function_invocation_configuration.get("max_iterations", DEFAULT_MAX_ITERATIONS)
        attempt_start = int(budget_state.get("attempt_count", 0) or 0)

        async def settle_approval_replay_calls(function_calls: Sequence[Content]) -> None:
            await self._settle_dangling_service_function_calls(
                super_get_response=super_get_response,
                function_calls=function_calls,
                options=options,
                request_kwargs=request_kwargs,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                invocation_session=invocation_session,
            )

        # Phase 1: resolve and emit inbound approval outcomes before opening another provider stream.
        approval_processing = await _resolve_approval_responses(
            prepared_messages=prepared_messages,
            options=options,
            errors_in_a_row=errors_in_a_row,
            max_errors=max_errors,
            execute_function_calls=execute_function_calls,
            invocation_session=invocation_session,
            settle_dangling_calls=settle_approval_replay_calls,
        )
        errors_in_a_row = approval_processing.errors_in_a_row
        total_function_calls = _record_function_calls(
            budget_state,
            total_function_calls,
            approval_processing.function_call_count,
        )
        for update in approval_processing.streaming_updates:
            yield update
        if approval_processing.action == "return":
            return
        if approval_processing.action == "stop":
            options["tool_choice"] = "none"
        else:
            _disable_tools_at_function_call_limit(options, total_function_calls, max_function_calls)

        # Phase 2: stream each model turn, finalize it, execute its calls, then advance the transcript.
        for attempt_idx in range(attempt_start, max_iterations):
            budget_state["attempt_count"] = attempt_idx + 1
            inner_stream = cast(
                "ResponseStream[ChatResponseUpdate, ChatResponse[Any]]",
                super_get_response(
                    messages=prepared_messages,
                    stream=True,
                    options=options,
                    compaction_strategy=compaction_strategy,
                    tokenizer=tokenizer,
                    client_kwargs=request_kwargs,
                ),
            )
            await inner_stream
            drop_unexecutable_calls = options.get("tool_choice") == "none" and _function_call_limit_reached(
                total_function_calls,
                max_function_calls,
            )
            streamed_identities_by_call_id: dict[str, tuple[str, str]] = {}
            streamed_names_by_call_id: dict[str, str] = {}
            last_streamed_identity: tuple[str, str] | None = None
            warned_empty_call_ids: set[str] = set()
            async for update in inner_stream:
                for content in update.contents:
                    if content.type != "function_call":
                        continue
                    if not _is_actionable_function_call(content):
                        continue
                    had_occurrence_id = content.id is not None
                    provider_call_id = content.call_id
                    identity = streamed_identities_by_call_id.get(provider_call_id) if provider_call_id else None
                    if (
                        identity is not None
                        and provider_call_id is not None
                        and content.id is None
                        and content.name
                        and (
                            streamed_names_by_call_id.get(provider_call_id) != content.name
                            or isinstance(content.arguments, Mapping)
                        )
                    ):
                        identity = None
                    if identity is None and not provider_call_id and not content.name:
                        identity = last_streamed_identity

                    if identity is None:
                        occurrence_id = content.id or _generate_function_call_occurrence_id()
                        effective_call_id = provider_call_id or ("" if had_occurrence_id else occurrence_id)
                    else:
                        occurrence_id, effective_call_id = identity
                    if content.id is not None:
                        occurrence_id = content.id
                    if provider_call_id:
                        effective_call_id = provider_call_id

                    content.id = occurrence_id
                    if not content.call_id and not had_occurrence_id:
                        content.call_id = effective_call_id
                        if identity is None and occurrence_id not in warned_empty_call_ids:
                            warnings.warn(
                                "An actionable function_call had an empty call_id. Agent Framework used its generated "
                                "Content.id for local correlation. Providers should supply and preserve their service "
                                "call_id; this fallback will be removed in a future release.",
                                FutureWarning,
                                stacklevel=3,
                            )
                            warned_empty_call_ids.add(occurrence_id)
                    identity = (occurrence_id, effective_call_id)
                    if effective_call_id:
                        streamed_identities_by_call_id[effective_call_id] = identity
                        if content.name:
                            streamed_names_by_call_id[effective_call_id] = content.name
                    last_streamed_identity = identity
                if drop_unexecutable_calls:
                    update = _drop_unexecutable_tool_contents_from_update(update)
                    if update is None:
                        continue
                yield update

            response = await inner_stream.get_final_response()
            function_call_limit_reached = options.get("tool_choice") == "none" and _function_call_limit_reached(
                total_function_calls, max_function_calls
            )
            fallback_added = False
            if function_call_limit_reached:
                fallback_added = _ensure_function_invocation_limit_fallback_response(response)
            self._update_function_invocation_continuation_state(
                request_kwargs,
                response,
                session=invocation_session,
                options=options,
            )

            if not any(
                item.type == "function_approval_request" or _is_actionable_function_call(item)
                for message in response.messages
                for item in message.contents
            ):
                if fallback_added:
                    yield _function_invocation_limit_fallback_update()
                return

            try:
                function_processing = await _process_model_function_calls(
                    response=response,
                    options=options,
                    function_call_messages=None,
                    errors_in_a_row=errors_in_a_row,
                    max_errors=max_errors,
                    execute_function_calls=execute_function_calls,
                    invocation_session=invocation_session,
                )
            except MiddlewareFailure:
                # See the non-streaming loop: settle a service-managed conversation's
                # dangling calls and advance the persisted continuation before
                # propagating the fail-closed abort (best-effort).
                await self._settle_dangling_service_function_calls(
                    super_get_response=super_get_response,
                    function_calls=_extract_function_calls(response),
                    options=options,
                    request_kwargs=request_kwargs,
                    compaction_strategy=compaction_strategy,
                    tokenizer=tokenizer,
                    invocation_session=invocation_session,
                    response_conversation_id=response.conversation_id,
                )
                raise
            errors_in_a_row = function_processing.errors_in_a_row
            total_function_calls = _record_function_calls(
                budget_state,
                total_function_calls,
                function_processing.function_call_count,
            )
            for update in function_processing.streaming_updates:
                yield update
            if function_processing.action == "stop":
                options["tool_choice"] = "none"
            elif function_processing.action != "continue":
                return
            else:
                _disable_tools_at_function_call_limit(options, total_function_calls, max_function_calls)
            _reset_required_tool_choice(options)
            _prepare_messages_for_next_iteration(prepared_messages, response)

        # Phase 3: the iteration budget is exhausted, so stream one final response with tools disabled.
        if response is not None:
            logger.info(
                "Maximum iterations reached (%d). Requesting final response without tools.",
                max_iterations,
            )
        options["tool_choice"] = "none"
        final_inner_stream = cast(
            "ResponseStream[ChatResponseUpdate, ChatResponse[Any]]",
            super_get_response(
                messages=prepared_messages,
                stream=True,
                options=options,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                client_kwargs=request_kwargs,
            ),
        )
        await final_inner_stream
        async for update in final_inner_stream:
            update = _drop_unexecutable_tool_contents_from_update(update)
            if update is None:
                continue
            yield update
        final_response = await final_inner_stream.get_final_response()
        fallback_added = _ensure_function_invocation_limit_fallback_response(final_response)
        self._update_function_invocation_continuation_state(
            request_kwargs,
            final_response,
            session=invocation_session,
            options=options,
        )
        if fallback_added:
            yield _function_invocation_limit_fallback_update()

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[ResponseModelBoundT],
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[ResponseModelBoundT]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: OptionsCoT | ChatOptions[None] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: OptionsCoT | ChatOptions[Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: OptionsCoT | ChatOptions[Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        from ._middleware import _as_middleware_list, categorize_middleware  # pyright: ignore[reportPrivateUsage]
        from ._types import (
            ChatResponse,
            ResponseStream,
        )

        super_get_response = cast(
            Callable[..., Any],
            super().get_response,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        )

        # Build the run-local middleware pipeline and recover shared budget/session state for approval re-entry.
        request_kwargs = dict(client_kwargs) if client_kwargs is not None else {}
        if middleware is not None:
            request_kwargs["middleware"] = [
                *_as_middleware_list(
                    cast("MiddlewareTypes | Sequence[MiddlewareTypes] | None", request_kwargs.get("middleware"))
                ),
                *middleware,
            ]
        # Same contract as the constructor: this seam installs chat and function
        # middleware only; a bundle carrying an agent member fails loudly instead of
        # silently losing that member.
        categorized_runtime_middleware = categorize_middleware(
            request_kwargs.pop("middleware", []), supported_categories=("chat", "function")
        )

        function_middleware_pipeline = self._get_function_middleware_pipeline(
            categorized_runtime_middleware["function"]
        )
        if categorized_runtime_middleware["chat"]:
            request_kwargs["middleware"] = categorized_runtime_middleware["chat"]
        raw_budget_state = request_kwargs.pop(_FUNCTION_INVOCATION_BUDGET_STATE_KEY, None)
        budget_state: dict[str, Any] = (
            cast(dict[str, Any], raw_budget_state) if isinstance(raw_budget_state, dict) else {}
        )
        max_errors = self.function_invocation_configuration.get(
            "max_consecutive_errors_per_request", DEFAULT_MAX_CONSECUTIVE_ERRORS_PER_REQUEST
        )
        additional_function_arguments = (
            dict(function_invocation_kwargs) if function_invocation_kwargs is not None else {}
        )
        if options and (additional_opts := options.get("additional_function_arguments")):
            additional_function_arguments.update(cast(Mapping[str, Any], additional_opts))
        from ._sessions import AgentSession as _AgentSession

        raw_session = request_kwargs.get("session")
        invocation_session = raw_session if isinstance(raw_session, _AgentSession) else None

        # Bind one executor with the run's custom arguments, middleware, configuration, and session.
        execute_function_calls = partial(
            _execute_function_calls,
            custom_args=additional_function_arguments,
            config=self.function_invocation_configuration,
            invocation_session=invocation_session,
            middleware_pipeline=function_middleware_pipeline,
        )

        # Give the loop private mutable options and one shared run-local tool list for progressive tool changes.
        # Make options mutable so we can update conversation_id during function invocation loop
        mutable_options: dict[str, Any] = dict(options) if options else {}
        # Remove additional_function_arguments from options passed to underlying chat client
        # It's for tool invocation only and not recognized by chat service APIs
        mutable_options.pop("additional_function_arguments", None)
        if not self.function_invocation_configuration.get("enabled", True):
            return super_get_response(
                messages=messages,
                stream=stream,
                options=mutable_options,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                function_invocation_kwargs=function_invocation_kwargs,
                client_kwargs=request_kwargs,
            )
        # Establish a single, run-local mutable tools list so that tools can add or remove
        # tools during the run (progressive tool exposure). A fresh list is created via
        # normalize_tools so the caller's original tools container is never mutated, while
        # the same list object is shared with the model (options["tools"]) and the tool map
        # rebuilt on every loop iteration.
        if mutable_options.get("tools"):
            mutable_options["tools"] = normalize_tools(mutable_options["tools"])

        # Dispatch to the shape-specific loop; both loops follow the same approval -> model -> execution phases.
        if not stream:
            return self._get_response_with_function_invocation(
                super_get_response=super_get_response,
                messages=messages,
                options=mutable_options,
                request_kwargs=request_kwargs,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                execute_function_calls=execute_function_calls,
                invocation_session=invocation_session,
                budget_state=budget_state,
                max_errors=max_errors,
            )

        response_format = mutable_options.get("response_format")
        return ResponseStream(
            self._stream_response_with_function_invocation(
                super_get_response=super_get_response,
                messages=messages,
                options=mutable_options,
                request_kwargs=request_kwargs,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                execute_function_calls=execute_function_calls,
                invocation_session=invocation_session,
                budget_state=budget_state,
                max_errors=max_errors,
            ),
            finalizer=partial(ChatResponse.from_updates, output_format_type=response_format),
        )


# Alias for the @tool decorator, used by security tools and samples
ai_function = tool
