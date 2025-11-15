# Copyright (c) Microsoft. All rights reserved.

import asyncio
import inspect
import json
import sys
from collections.abc import AsyncIterable, Awaitable, Callable, Collection, Mapping, MutableMapping, Sequence
from functools import wraps
from time import perf_counter, time_ns
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Final,
    Generic,
    Literal,
    Protocol,
    TypeVar,
    cast,
    get_args,
    get_origin,
    runtime_checkable,
)

from opentelemetry.metrics import Histogram
from pydantic import AnyUrl, BaseModel, Field, ValidationError, create_model
from pydantic.fields import FieldInfo

from ._logging import get_logger
from ._serialization import SerializationMixin
from .exceptions import ChatClientInitializationError, ToolException
from .observability import (
    OPERATION_DURATION_BUCKET_BOUNDARIES,
    OtelAttr,
    capture_exception,  # type: ignore
    get_function_span,
    get_function_span_attributes,
    get_meter,
)

if TYPE_CHECKING:
    from ._clients import ChatClientProtocol
    from ._types import (
        ChatMessage,
        ChatResponse,
        ChatResponseUpdate,
        Contents,
        FunctionApprovalResponseContent,
        FunctionCallContent,
    )

if sys.version_info >= (3, 12):
    from typing import (
        TypedDict,  # pragma: no cover
        override,  # type: ignore # pragma: no cover
    )
else:
    from typing_extensions import (
        TypedDict,  # pragma: no cover
        override,  # type: ignore[import] # pragma: no cover
    )

if sys.version_info >= (3, 11):
    from typing import overload  # pragma: no cover
else:
    from typing_extensions import overload  # pragma: no cover

logger = get_logger()

__all__ = [
    "FUNCTION_INVOKING_CHAT_CLIENT_MARKER",
    "AIFunction",
    "FunctionInvocationConfiguration",
    "HostedCodeInterpreterTool",
    "HostedFileSearchTool",
    "HostedMCPSpecificApproval",
    "HostedMCPTool",
    "HostedWebSearchTool",
    "ToolProtocol",
    "ai_function",
    "use_function_invocation",
]


logger = get_logger()
FUNCTION_INVOKING_CHAT_CLIENT_MARKER: Final[str] = "__function_invoking_chat_client__"
DEFAULT_MAX_ITERATIONS: Final[int] = 40
DEFAULT_MAX_CONSECUTIVE_ERRORS_PER_REQUEST: Final[int] = 3
TChatClient = TypeVar("TChatClient", bound="ChatClientProtocol")
# region Helpers

ArgsT = TypeVar("ArgsT", bound=BaseModel)
ReturnT = TypeVar("ReturnT")


class _NoOpHistogram:
    def record(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - trivial
        return None


_NOOP_HISTOGRAM = _NoOpHistogram()


def _parse_inputs(
    inputs: "Contents | dict[str, Any] | str | list[Contents | dict[str, Any] | str] | None",
) -> list["Contents"]:
    """Parse the inputs for a tool, ensuring they are of type Contents.

    Args:
        inputs: The inputs to parse. Can be a single item or list of Contents, dicts, or strings.

    Returns:
        A list of Contents objects.

    Raises:
        ValueError: If an unsupported input type is encountered.
        TypeError: If the input type is not supported.
    """
    if inputs is None:
        return []

    from ._types import BaseContent, DataContent, HostedFileContent, HostedVectorStoreContent, UriContent

    parsed_inputs: list["Contents"] = []
    if not isinstance(inputs, list):
        inputs = [inputs]
    for input_item in inputs:
        if isinstance(input_item, str):
            # If it's a string, we assume it's a URI or similar identifier.
            # Convert it to a UriContent or similar type as needed.
            parsed_inputs.append(UriContent(uri=input_item, media_type="text/plain"))
        elif isinstance(input_item, dict):
            # If it's a dict, we assume it contains properties for a specific content type.
            # we check if the required keys are present to determine the type.
            # for instance, if it has "uri" and "media_type", we treat it as UriContent.
            # if is only has uri, then we treat it as DataContent.
            # etc.
            if "uri" in input_item:
                parsed_inputs.append(
                    UriContent(**input_item) if "media_type" in input_item else DataContent(**input_item)
                )
            elif "file_id" in input_item:
                parsed_inputs.append(HostedFileContent(**input_item))
            elif "vector_store_id" in input_item:
                parsed_inputs.append(HostedVectorStoreContent(**input_item))
            elif "data" in input_item:
                parsed_inputs.append(DataContent(**input_item))
            else:
                raise ValueError(f"Unsupported input type: {input_item}")
        elif isinstance(input_item, BaseContent):
            parsed_inputs.append(input_item)
        else:
            raise TypeError(f"Unsupported input type: {type(input_item).__name__}. Expected Contents or dict.")
    return parsed_inputs


# region Tools
@runtime_checkable
class ToolProtocol(Protocol):
    """Represents a generic tool.

    This protocol defines the interface that all tools must implement to be compatible
    with the agent framework. It is implemented by various tool classes such as HostedMCPTool,
    HostedWebSearchTool, and AIFunction's. A AIFunction is usually created by the `ai_function` decorator.

    Since each connector needs to parse tools differently, users can pass a dict to
    specify a service-specific tool when no abstraction is available.

    Attributes:
        name: The name of the tool.
        description: A description of the tool, suitable for use in describing the purpose to a model.
        additional_properties: Additional properties associated with the tool.
    """

    name: str
    """The name of the tool."""
    description: str
    """A description of the tool, suitable for use in describing the purpose to a model."""
    additional_properties: dict[str, Any] | None
    """Additional properties associated with the tool."""

    def __str__(self) -> str:
        """Return a string representation of the tool."""
        ...


class BaseTool(SerializationMixin):
    """Base class for AI tools, providing common attributes and methods.

    Used as the base class for the various tools in the agent framework, such as HostedMCPTool,
    HostedWebSearchTool, and AIFunction.

    Since each connector needs to parse tools differently, this class is not exposed directly to end users.
    In most cases, users can pass a dict to specify a service-specific tool when no abstraction is available.
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"additional_properties"}

    def __init__(
        self,
        *,
        name: str,
        description: str = "",
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the BaseTool.

        Keyword Args:
            name: The name of the tool.
            description: A description of the tool.
            additional_properties: Additional properties associated with the tool.
            **kwargs: Additional keyword arguments.
        """
        self.name = name
        self.description = description
        self.additional_properties = additional_properties
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self) -> str:
        """Return a string representation of the tool."""
        if self.description:
            return f"{self.__class__.__name__}(name={self.name}, description={self.description})"
        return f"{self.__class__.__name__}(name={self.name})"


class HostedCodeInterpreterTool(BaseTool):
    """Represents a hosted tool that can be specified to an AI service to enable it to execute generated code.

    This tool does not implement code interpretation itself. It serves as a marker to inform a service
    that it is allowed to execute generated code if the service is capable of doing so.

    Examples:
        .. code-block:: python

            from agent_framework import HostedCodeInterpreterTool

            # Create a code interpreter tool
            code_tool = HostedCodeInterpreterTool()

            # With file inputs
            code_tool_with_files = HostedCodeInterpreterTool(inputs=[{"file_id": "file-123"}, {"file_id": "file-456"}])
    """

    def __init__(
        self,
        *,
        inputs: "Contents | dict[str, Any] | str | list[Contents | dict[str, Any] | str] | None" = None,
        description: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the HostedCodeInterpreterTool.

        Keyword Args:
            inputs: A list of contents that the tool can accept as input. Defaults to None.
                This should mostly be HostedFileContent or HostedVectorStoreContent.
                Can also be DataContent, depending on the service used.
                When supplying a list, it can contain:
                - Contents instances
                - dicts with properties for Contents (e.g., {"uri": "http://example.com", "media_type": "text/html"})
                - strings (which will be converted to UriContent with media_type "text/plain").
                If None, defaults to an empty list.
            description: A description of the tool.
            additional_properties: Additional properties associated with the tool.
            **kwargs: Additional keyword arguments to pass to the base class.
        """
        if "name" in kwargs:
            raise ValueError("The 'name' argument is reserved for the HostedCodeInterpreterTool and cannot be set.")

        self.inputs = _parse_inputs(inputs) if inputs else []

        super().__init__(
            name="code_interpreter",
            description=description or "",
            additional_properties=additional_properties,
            **kwargs,
        )


class HostedWebSearchTool(BaseTool):
    """Represents a web search tool that can be specified to an AI service to enable it to perform web searches.

    Examples:
        .. code-block:: python

            from agent_framework import HostedWebSearchTool

            # Create a basic web search tool
            search_tool = HostedWebSearchTool()

            # With location context
            search_tool_with_location = HostedWebSearchTool(
                description="Search the web for information",
                additional_properties={"user_location": {"city": "Seattle", "country": "US"}},
            )
    """

    def __init__(
        self,
        description: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """Initialize a HostedWebSearchTool.

        Keyword Args:
            description: A description of the tool.
            additional_properties: Additional properties associated with the tool
                (e.g., {"user_location": {"city": "Seattle", "country": "US"}}).
            **kwargs: Additional keyword arguments to pass to the base class.
                if additional_properties is not provided, any kwargs will be added to additional_properties.
        """
        args: dict[str, Any] = {
            "name": "web_search",
        }
        if additional_properties is not None:
            args["additional_properties"] = additional_properties
        elif kwargs:
            args["additional_properties"] = kwargs
        if description is not None:
            args["description"] = description
        super().__init__(**args)


class HostedMCPSpecificApproval(TypedDict, total=False):
    """Represents the specific mode for a hosted tool.

    When using this mode, the user must specify which tools always or never require approval.
    This is represented as a dictionary with two optional keys:

    Attributes:
        always_require_approval: A sequence of tool names that always require approval.
        never_require_approval: A sequence of tool names that never require approval.
    """

    always_require_approval: Collection[str] | None
    never_require_approval: Collection[str] | None


class HostedMCPTool(BaseTool):
    """Represents a MCP tool that is managed and executed by the service.

    Examples:
        .. code-block:: python

            from agent_framework import HostedMCPTool

            # Create a basic MCP tool
            mcp_tool = HostedMCPTool(
                name="my_mcp_tool",
                url="https://example.com/mcp",
            )

            # With approval mode and allowed tools
            mcp_tool_with_approval = HostedMCPTool(
                name="my_mcp_tool",
                description="My MCP tool",
                url="https://example.com/mcp",
                approval_mode="always_require",
                allowed_tools=["tool1", "tool2"],
                headers={"Authorization": "Bearer token"},
            )

            # With specific approval mode
            mcp_tool_specific = HostedMCPTool(
                name="my_mcp_tool",
                url="https://example.com/mcp",
                approval_mode={
                    "always_require_approval": ["dangerous_tool"],
                    "never_require_approval": ["safe_tool"],
                },
            )
    """

    def __init__(
        self,
        *,
        name: str,
        description: str | None = None,
        url: AnyUrl | str,
        approval_mode: Literal["always_require", "never_require"] | HostedMCPSpecificApproval | None = None,
        allowed_tools: Collection[str] | None = None,
        headers: dict[str, str] | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create a hosted MCP tool.

        Keyword Args:
            name: The name of the tool.
            description: A description of the tool.
            url: The URL of the tool.
            approval_mode: The approval mode for the tool. This can be:
                - "always_require": The tool always requires approval before use.
                - "never_require": The tool never requires approval before use.
                - A dict with keys `always_require_approval` or `never_require_approval`,
                  followed by a sequence of strings with the names of the relevant tools.
            allowed_tools: A list of tools that are allowed to use this tool.
            headers: Headers to include in requests to the tool.
            additional_properties: Additional properties to include in the tool definition.
            **kwargs: Additional keyword arguments to pass to the base class.
        """
        try:
            # Validate approval_mode
            if approval_mode is not None:
                if isinstance(approval_mode, str):
                    if approval_mode not in ("always_require", "never_require"):
                        raise ValueError(
                            f"Invalid approval_mode: {approval_mode}. "
                            "Must be 'always_require', 'never_require', or a dict with 'always_require_approval' "
                            "or 'never_require_approval' keys."
                        )
                elif isinstance(approval_mode, dict):
                    # Validate that the dict has sets
                    for key, value in approval_mode.items():
                        if not isinstance(value, set):
                            approval_mode[key] = set(value)  # type: ignore

            # Validate allowed_tools
            if allowed_tools is not None and isinstance(allowed_tools, dict):
                raise TypeError(
                    f"allowed_tools must be a sequence of strings, not a dict. Got: {type(allowed_tools).__name__}"
                )

            super().__init__(
                name=name,
                description=description or "",
                additional_properties=additional_properties,
                **kwargs,
            )
            self.url = url if isinstance(url, AnyUrl) else AnyUrl(url)
            self.approval_mode = approval_mode
            self.allowed_tools = set(allowed_tools) if allowed_tools else None
            self.headers = headers
        except (ValidationError, ValueError, TypeError) as err:
            raise ToolException(f"Error initializing HostedMCPTool: {err}", inner_exception=err) from err


class HostedFileSearchTool(BaseTool):
    """Represents a file search tool that can be specified to an AI service to enable it to perform file searches.

    Examples:
        .. code-block:: python

            from agent_framework import HostedFileSearchTool

            # Create a basic file search tool
            file_search = HostedFileSearchTool()

            # With vector store inputs and max results
            file_search_with_inputs = HostedFileSearchTool(
                inputs=[{"vector_store_id": "vs_123"}],
                max_results=10,
                description="Search files in vector store",
            )
    """

    def __init__(
        self,
        *,
        inputs: "Contents | dict[str, Any] | str | list[Contents | dict[str, Any] | str] | None" = None,
        max_results: int | None = None,
        description: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """Initialize a FileSearchTool.

        Keyword Args:
            inputs: A list of contents that the tool can accept as input. Defaults to None.
                This should be one or more HostedVectorStoreContents.
                When supplying a list, it can contain:
                - Contents instances
                - dicts with properties for Contents (e.g., {"uri": "http://example.com", "media_type": "text/html"})
                - strings (which will be converted to UriContent with media_type "text/plain").
                If None, defaults to an empty list.
            max_results: The maximum number of results to return from the file search.
                If None, max limit is applied.
            description: A description of the tool.
            additional_properties: Additional properties associated with the tool.
            **kwargs: Additional keyword arguments to pass to the base class.
        """
        if "name" in kwargs:
            raise ValueError("The 'name' argument is reserved for the HostedFileSearchTool and cannot be set.")

        self.inputs = _parse_inputs(inputs) if inputs else None
        self.max_results = max_results

        super().__init__(
            name="file_search",
            description=description or "",
            additional_properties=additional_properties,
            **kwargs,
        )


def _default_histogram() -> Histogram:
    """Get the default histogram for function invocation duration.

    Returns:
        A Histogram instance for recording function invocation duration,
        or a no-op histogram if observability is disabled.
    """
    from .observability import OBSERVABILITY_SETTINGS  # local import to avoid circulars

    if not OBSERVABILITY_SETTINGS.ENABLED:  # type: ignore[name-defined]
        return _NOOP_HISTOGRAM  # type: ignore[return-value]
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


TClass = TypeVar("TClass", bound="SerializationMixin")


class EmptyInputModel(BaseModel):
    """An empty input model for functions with no parameters."""


class AIFunction(BaseTool, Generic[ArgsT, ReturnT]):
    """A tool that wraps a Python function to make it callable by AI models.

    This class wraps a Python function to make it callable by AI models with automatic
    parameter validation and JSON schema generation.

    Examples:
        .. code-block:: python

            from typing import Annotated
            from pydantic import BaseModel, Field
            from agent_framework import AIFunction, ai_function


            # Using the decorator with string annotations
            @ai_function
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


            weather_func = AIFunction(
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
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"input_model", "_invocation_duration_histogram"}

    def __init__(
        self,
        *,
        name: str,
        description: str = "",
        approval_mode: Literal["always_require", "never_require"] | None = None,
        max_invocations: int | None = None,
        max_invocation_exceptions: int | None = None,
        additional_properties: dict[str, Any] | None = None,
        func: Callable[..., Awaitable[ReturnT] | ReturnT] | None = None,
        input_model: type[ArgsT] | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the AIFunction.

        Keyword Args:
            name: The name of the function.
            description: A description of the function.
            approval_mode: Whether or not approval is required to run this tool.
                Default is that approval is not needed.
            max_invocations: The maximum number of times this function can be invoked.
                If None, there is no limit. Should be at least 1.
            max_invocation_exceptions: The maximum number of exceptions allowed during invocations.
                If None, there is no limit. Should be at least 1.
            additional_properties: Additional properties to set on the function.
            func: The function to wrap.
            input_model: The Pydantic model that defines the input parameters for the function.
                This can also be a JSON schema dictionary.
                If not provided, it will be inferred from the function signature.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(
            name=name,
            description=description,
            additional_properties=additional_properties,
            **kwargs,
        )
        self.func = func
        self.input_model = self._resolve_input_model(input_model)
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
        self.type: Literal["ai_function"] = "ai_function"

    @property
    def declaration_only(self) -> bool:
        """Indicate whether the function is declaration only (i.e., has no implementation)."""
        return self.func is None

    def _resolve_input_model(self, input_model: type[ArgsT] | Mapping[str, Any] | None) -> type[ArgsT]:
        """Resolve the input model for the function."""
        if input_model is None:
            if self.func is None:
                return cast(type[ArgsT], EmptyInputModel)
            return cast(type[ArgsT], _create_input_model_from_func(func=self.func, name=self.name))
        if inspect.isclass(input_model) and issubclass(input_model, BaseModel):
            return input_model
        if isinstance(input_model, Mapping):
            return cast(type[ArgsT], _create_model_from_json_schema(self.name, input_model))
        raise TypeError("input_model must be a Pydantic BaseModel subclass or a JSON schema dict.")

    def __call__(self, *args: Any, **kwargs: Any) -> ReturnT | Awaitable[ReturnT]:
        """Call the wrapped function with the provided arguments."""
        if self.func is None:
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
            return self.func(*args, **kwargs)
        except Exception:
            self.invocation_exception_count += 1
            raise

    async def invoke(
        self,
        *,
        arguments: ArgsT | None = None,
        **kwargs: Any,
    ) -> ReturnT:
        """Run the AI function with the provided arguments as a Pydantic model.

        Keyword Args:
            arguments: A Pydantic model instance containing the arguments for the function.
            kwargs: Keyword arguments to pass to the function, will not be used if ``arguments`` is provided.

        Returns:
            The result of the function execution.

        Raises:
            TypeError: If arguments is not an instance of the expected input model.
        """
        if self.declaration_only:
            raise ToolException(f"Function '{self.name}' is declaration only and cannot be invoked.")
        global OBSERVABILITY_SETTINGS
        from .observability import OBSERVABILITY_SETTINGS

        tool_call_id = kwargs.pop("tool_call_id", None)
        if arguments is not None:
            if not isinstance(arguments, self.input_model):
                raise TypeError(f"Expected {self.input_model.__name__}, got {type(arguments).__name__}")
            kwargs = arguments.model_dump(exclude_none=True)
        if not OBSERVABILITY_SETTINGS.ENABLED:  # type: ignore[name-defined]
            logger.info(f"Function name: {self.name}")
            logger.debug(f"Function arguments: {kwargs}")
            res = self.__call__(**kwargs)
            result = await res if inspect.isawaitable(res) else res
            logger.info(f"Function {self.name} succeeded.")
            logger.debug(f"Function result: {result or 'None'}")
            return result  # type: ignore[reportReturnType]

        attributes = get_function_span_attributes(self, tool_call_id=tool_call_id)
        if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:  # type: ignore[name-defined]
            attributes.update({
                OtelAttr.TOOL_ARGUMENTS: arguments.model_dump_json()
                if arguments
                else json.dumps(kwargs)
                if kwargs
                else "None"
            })
        with get_function_span(attributes=attributes) as span:
            attributes[OtelAttr.MEASUREMENT_FUNCTION_TAG_NAME] = self.name
            logger.info(f"Function name: {self.name}")
            if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:  # type: ignore[name-defined]
                logger.debug(f"Function arguments: {kwargs}")
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
                logger.info(f"Function {self.name} succeeded.")
                if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:  # type: ignore[name-defined]
                    try:
                        json_result = json.dumps(result)
                    except (TypeError, OverflowError):
                        span.set_attribute(OtelAttr.TOOL_RESULT, "<non-serializable result>")
                        logger.debug("Function result: <non-serializable result>")
                    else:
                        span.set_attribute(OtelAttr.TOOL_RESULT, json_result)
                        logger.debug(f"Function result: {json_result}")
                return result  # type: ignore[reportReturnType]
            finally:
                duration = (end_time_stamp or perf_counter()) - start_time_stamp
                span.set_attribute(OtelAttr.MEASUREMENT_FUNCTION_INVOCATION_DURATION, duration)
                self._invocation_duration_histogram.record(duration, attributes=attributes)
                logger.info("Function duration: %fs", duration)

    def parameters(self) -> dict[str, Any]:
        """Create the JSON schema of the parameters.

        Returns:
            A dictionary containing the JSON schema for the function's parameters.
        """
        return self.input_model.model_json_schema()

    def to_json_schema_spec(self) -> dict[str, Any]:
        """Convert a AIFunction to the JSON Schema function specification format.

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
        as_dict["input_model"] = self.input_model.model_json_schema()
        return as_dict


def _tools_to_dict(
    tools: (
        ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None
    ),
) -> list[str | dict[str, Any]] | None:
    """Parse the tools to a dict.

    Args:
        tools: The tools to parse. Can be a single tool or a sequence of tools.

    Returns:
        A list of tool specifications as dictionaries, or None if no tools provided.
    """
    if not tools:
        return None
    if not isinstance(tools, list):
        if isinstance(tools, AIFunction):
            return [tools.to_json_schema_spec()]
        if isinstance(tools, SerializationMixin):
            return [tools.to_dict()]
        if isinstance(tools, dict):
            return [tools]
        if callable(tools):
            return [ai_function(tools).to_json_schema_spec()]
        logger.warning("Can't parse tool.")
        return None
    results: list[str | dict[str, Any]] = []
    for tool in tools:
        if isinstance(tool, AIFunction):
            results.append(tool.to_json_schema_spec())
            continue
        if isinstance(tool, SerializationMixin):
            results.append(tool.to_dict())
            continue
        if isinstance(tool, dict):
            results.append(tool)
            continue
        if callable(tool):
            results.append(ai_function(tool).to_json_schema_spec())
            continue
        logger.warning("Can't parse tool.")
    return results


# region AI Function Decorator


def _parse_annotation(annotation: Any) -> Any:
    """Parse a type annotation and return the corresponding type.

    If the second annotation (after the type) is a string, then we convert that to a Pydantic Field description.
    The rest are returned as-is, allowing for multiple annotations.

    Args:
        annotation: The type annotation to parse.

    Returns:
        The parsed annotation, potentially wrapped in Annotated with a Field.
    """
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        # For other generics, return the origin type (e.g., list for List[int])
        if len(args) > 1 and isinstance(args[1], str):
            # Create a new Annotated type with the updated Field
            args_list = list(args)
            if len(args_list) == 2:
                return Annotated[args_list[0], Field(description=args_list[1])]
            return Annotated[args_list[0], Field(description=args_list[1]), tuple(args_list[2:])]
    return annotation


def _create_input_model_from_func(func: Callable[..., Any], name: str) -> type[BaseModel]:
    """Create a Pydantic model from a function's signature."""
    sig = inspect.signature(func)
    fields = {
        pname: (
            _parse_annotation(param.annotation) if param.annotation is not inspect.Parameter.empty else str,
            param.default if param.default is not inspect.Parameter.empty else ...,
        )
        for pname, param in sig.parameters.items()
        if pname not in {"self", "cls"}
    }
    return create_model(f"{name}_input", **fields)  # type: ignore[call-overload, no-any-return]


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
    # Extract field definitions with type annotations
    field_definitions: dict[str, tuple[type, FieldInfo]] = {}
    for field_name, field_schema in schema_json["properties"].items():
        field_args: dict[str, Any] = {}
        if (field_description := field_schema.get("description", None)) is not None:
            field_args["description"] = field_description
        if (field_default := field_schema.get("default", None)) is not None:
            field_args["default"] = field_default
        field_type = field_schema.get("type", None)
        if field_type is None:
            raise ValueError(
                f"Missing 'type' for field '{field_name}' in JSON schema. "
                f"Got: {field_schema}, Supported types: {list(TYPE_MAPPING.keys())}"
            )
        python_type = TYPE_MAPPING.get(field_type)
        if python_type is None:
            raise ValueError(
                f"Unsupported type '{field_type}' for field '{field_name}' in JSON schema. "
                f"Got: {field_schema}, Supported types: {list(TYPE_MAPPING.keys())}"
            )
        field_definitions[field_name] = (python_type, Field(**field_args))

    return create_model(f"{tool_name}_input", **field_definitions)  # type: ignore[call-overload, no-any-return]


@overload
def ai_function(
    func: Callable[..., ReturnT | Awaitable[ReturnT]],
    *,
    name: str | None = None,
    description: str | None = None,
    approval_mode: Literal["always_require", "never_require"] | None = None,
    max_invocations: int | None = None,
    max_invocation_exceptions: int | None = None,
    additional_properties: dict[str, Any] | None = None,
) -> AIFunction[Any, ReturnT]: ...


@overload
def ai_function(
    func: None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    approval_mode: Literal["always_require", "never_require"] | None = None,
    max_invocations: int | None = None,
    max_invocation_exceptions: int | None = None,
    additional_properties: dict[str, Any] | None = None,
) -> Callable[[Callable[..., ReturnT | Awaitable[ReturnT]]], AIFunction[Any, ReturnT]]: ...


def ai_function(
    func: Callable[..., ReturnT | Awaitable[ReturnT]] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    approval_mode: Literal["always_require", "never_require"] | None = None,
    max_invocations: int | None = None,
    max_invocation_exceptions: int | None = None,
    additional_properties: dict[str, Any] | None = None,
) -> AIFunction[Any, ReturnT] | Callable[[Callable[..., ReturnT | Awaitable[ReturnT]]], AIFunction[Any, ReturnT]]:
    """Decorate a function to turn it into a AIFunction that can be passed to models and executed automatically.

    This decorator creates a Pydantic model from the function's signature,
    which will be used to validate the arguments passed to the function
    and to generate the JSON schema for the function's parameters.

    To add descriptions to parameters, use the ``Annotated`` type from ``typing``
    with a string description as the second argument. You can also use Pydantic's
    ``Field`` class for more advanced configuration.

    Args:
        func: The function to decorate.

    Keyword Args:
        name: The name of the function. If not provided, the function's ``__name__``
            attribute will be used.
        description: A description of the function. If not provided, the function's
            docstring will be used.
        approval_mode: Whether or not approval is required to run this tool.
            Default is that approval is not needed.
        max_invocations: The maximum number of times this function can be invoked.
            If None, there is no limit, should be at least 1.
        max_invocation_exceptions: The maximum number of exceptions allowed during invocations.
            If None, there is no limit, should be at least 1.
        additional_properties: Additional properties to set on the function.

    Note:
        When approval_mode is set to "always_require", the function will not be executed
        until explicit approval is given, this only applies to the auto-invocation flow.
        It is also important to note that if the model returns multiple function calls, some that require approval
        and others that do not, it will ask approval for all of them.

    Example:

        .. code-block:: python

            from agent_framework import ai_function
            from typing import Annotated


            @ai_function
            def ai_function_example(
                arg1: Annotated[str, "The first argument"],
                arg2: Annotated[int, "The second argument"],
            ) -> str:
                # An example function that takes two arguments and returns a string.
                return f"arg1: {arg1}, arg2: {arg2}"


            # the same function but with approval required to run
            @ai_function(approval_mode="always_require")
            def ai_function_example(
                arg1: Annotated[str, "The first argument"],
                arg2: Annotated[int, "The second argument"],
            ) -> str:
                # An example function that takes two arguments and returns a string.
                return f"arg1: {arg1}, arg2: {arg2}"


            # With custom name and description
            @ai_function(name="custom_weather", description="Custom weather function")
            def another_weather_func(location: str) -> str:
                return f"Weather in {location}"


            # Async functions are also supported
            @ai_function
            async def async_get_weather(location: str) -> str:
                '''Get weather asynchronously.'''
                # Simulate async operation
                return f"Weather in {location}"

    """

    def decorator(func: Callable[..., ReturnT | Awaitable[ReturnT]]) -> AIFunction[Any, ReturnT]:
        @wraps(func)
        def wrapper(f: Callable[..., ReturnT | Awaitable[ReturnT]]) -> AIFunction[Any, ReturnT]:
            tool_name: str = name or getattr(f, "__name__", "unknown_function")  # type: ignore[assignment]
            tool_desc: str = description or (f.__doc__ or "")
            return AIFunction[Any, ReturnT](
                name=tool_name,
                description=tool_desc,
                approval_mode=approval_mode,
                max_invocations=max_invocations,
                max_invocation_exceptions=max_invocation_exceptions,
                additional_properties=additional_properties or {},
                func=f,
            )

        return wrapper(func)

    return decorator(func) if func else decorator


# region Function Invoking Chat Client


class FunctionInvocationConfiguration(SerializationMixin):
    """Configuration for function invocation in chat clients.

    This class is created automatically on every chat client that supports function invocation.
    This means that for most cases you can just alter the attributes on the instance, rather then creating a new one.

    Example:
        .. code-block:: python
            from agent_framework.openai import OpenAIChatClient

            # Create an OpenAI chat client
            client = OpenAIChatClient(api_key="your_api_key")

            # Disable function invocation
            client.function_invocation_config.enabled = False

            # Set maximum iterations to 10
            client.function_invocation_config.max_iterations = 10

            # Enable termination on unknown function calls
            client.function_invocation_config.terminate_on_unknown_calls = True

            # Add additional tools for function execution
            client.function_invocation_config.additional_tools = [my_custom_tool]

            # Enable detailed error information in function results
            client.function_invocation_config.include_detailed_errors = True

            # You can also create a new configuration instance if needed
            new_config = FunctionInvocationConfiguration(
                enabled=True,
                max_iterations=20,
                terminate_on_unknown_calls=False,
                additional_tools=[another_tool],
                include_detailed_errors=False,
            )

            # and then assign it to the client
            client.function_invocation_config = new_config


    Attributes:
        enabled: Whether function invocation is enabled.
            When this is set to False, the client will not attempt to invoke any functions,
            because the tool mode will be set to None.
        max_iterations: Maximum number of function invocation iterations.
            Each request to this client might end up making multiple requests to the model. Each time the model responds
            with a function call request, this client might perform that invocation and send the results back to the
            model in a new request. This property limits the number of times such a roundtrip is performed. The value
            must be at least one, as it includes the initial request.
            If you want to fully disable function invocation, use the ``enabled`` property.
            The default is 40.
        max_consecutive_errors_per_request: Maximum consecutive errors allowed per request.
            The maximum number of consecutive function call errors allowed before stopping
            further function calls for the request.
            The default is 3.
        terminate_on_unknown_calls: Whether to terminate on unknown function calls.
            When False, call requests to any tools that aren't available to the client
            will result in a response message automatically being created and returned to the inner client stating that
            the tool couldn't be found. This behavior can help in cases where a model hallucinates a function, but it's
            problematic if the model has been made aware of the existence of tools outside of the normal mechanisms, and
            requests one of those. ``additional_tools`` can be used to help with that. But if instead the consumer wants
            to know about all function call requests that the client can't handle, this can be set to True. Upon
            receiving a request to call a function that the client doesn't know about, it will terminate the function
            calling loop and return the response, leaving the handling of the function call requests to the consumer of
            the client.
        additional_tools: Additional tools to include for function execution.
            These will not impact the requests sent by the client, which will pass through the
            ``tools`` unmodified. However, if the inner client requests the invocation of a tool
            that was not in ``ChatOptions.tools``, this ``additional_tools`` collection will also be consulted to look
            for a corresponding tool. This is useful when the service might have been pre-configured to be aware of
            certain tools that aren't also sent on each individual request. These tools are treated the same as
            ``declaration_only`` tools and will be returned to the user.
        include_detailed_errors: Whether to include detailed error information in function results.
            When set to True, detailed error information such as exception type and message
            will be included in the function result content when a function invocation fails.
            When False, only a generic error message will be included.


    """

    def __init__(
        self,
        enabled: bool = True,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_consecutive_errors_per_request: int = DEFAULT_MAX_CONSECUTIVE_ERRORS_PER_REQUEST,
        terminate_on_unknown_calls: bool = False,
        additional_tools: Sequence[ToolProtocol] | None = None,
        include_detailed_errors: bool = False,
    ) -> None:
        """Initialize FunctionInvocationConfiguration.

        Args:
            enabled: Whether function invocation is enabled.
            max_iterations: Maximum number of function invocation iterations.
            max_consecutive_errors_per_request: Maximum consecutive errors allowed per request.
            terminate_on_unknown_calls: Whether to terminate on unknown function calls.
            additional_tools: Additional tools to include for function execution.
            include_detailed_errors: Whether to include detailed error information in function results.
        """
        self.enabled = enabled
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")
        self.max_iterations = max_iterations
        if max_consecutive_errors_per_request < 0:
            raise ValueError("max_consecutive_errors_per_request must be 0 or more.")
        self.max_consecutive_errors_per_request = max_consecutive_errors_per_request
        self.terminate_on_unknown_calls = terminate_on_unknown_calls
        self.additional_tools = additional_tools or []
        self.include_detailed_errors = include_detailed_errors


async def _auto_invoke_function(
    function_call_content: "FunctionCallContent | FunctionApprovalResponseContent",
    custom_args: dict[str, Any] | None = None,
    *,
    config: FunctionInvocationConfiguration,
    tool_map: dict[str, AIFunction[BaseModel, Any]],
    sequence_index: int | None = None,
    request_index: int | None = None,
    middleware_pipeline: Any = None,  # Optional MiddlewarePipeline
) -> "Contents":
    """Invoke a function call requested by the agent, applying middleware that is defined.

    Args:
        function_call_content: The function call content from the model.
        custom_args: Additional custom arguments to merge with parsed arguments.

    Keyword Args:
        config: The function invocation configuration.
        tool_map: A mapping of tool names to AIFunction instances.
        sequence_index: The index of the function call in the sequence.
        request_index: The index of the request iteration.
        middleware_pipeline: Optional middleware pipeline to apply during execution.

    Returns:
        A FunctionResultContent containing the result or exception.

    Raises:
        KeyError: If the requested function is not found in the tool map.
    """
    from ._types import (
        FunctionResultContent,
    )

    # Note: The scenarios for approval_mode="always_require", declaration_only, and
    # terminate_on_unknown_calls are all handled in _try_execute_function_calls before
    # this function is called. This function only handles the actual execution of approved,
    # non-declaration-only functions.

    tool: AIFunction[BaseModel, Any] | None = None
    if function_call_content.type == "function_call":
        tool = tool_map.get(function_call_content.name)
        # Tool should exist because _try_execute_function_calls validates this
        if tool is None:
            exc = KeyError(f'Function "{function_call_content.name}" not found.')
            return FunctionResultContent(
                call_id=function_call_content.call_id,
                result=f'Error: Requested function "{function_call_content.name}" not found.',
                exception=exc,
            )
    else:
        # Note: Unapproved tools (approved=False) are handled in _replace_approval_contents_with_results
        # and never reach this function, so we only handle approved=True cases here.
        tool = tool_map.get(function_call_content.function_call.name)
        if tool is None:
            # we assume it is a hosted tool
            return function_call_content
        function_call_content = function_call_content.function_call

    parsed_args: dict[str, Any] = dict(function_call_content.parse_arguments() or {})

    # Merge with user-supplied args; right-hand side dominates, so parsed args win on conflicts.
    merged_args: dict[str, Any] = (custom_args or {}) | parsed_args
    try:
        args = tool.input_model.model_validate(merged_args)
    except ValidationError as exc:
        message = "Error: Argument parsing failed."
        if config.include_detailed_errors:
            message = f"{message} Exception: {exc}"
        return FunctionResultContent(call_id=function_call_content.call_id, result=message, exception=exc)
    if not middleware_pipeline or (
        not hasattr(middleware_pipeline, "has_middlewares") and not middleware_pipeline.has_middlewares
    ):
        # No middleware - execute directly
        try:
            function_result = await tool.invoke(
                arguments=args,
                tool_call_id=function_call_content.call_id,
            )  # type: ignore[arg-type]
            return FunctionResultContent(
                call_id=function_call_content.call_id,
                result=function_result,
            )
        except Exception as exc:
            message = "Error: Function failed."
            if config.include_detailed_errors:
                message = f"{message} Exception: {exc}"
            return FunctionResultContent(call_id=function_call_content.call_id, result=message, exception=exc)
    # Execute through middleware pipeline if available
    from ._middleware import FunctionInvocationContext

    middleware_context = FunctionInvocationContext(
        function=tool,
        arguments=args,
        kwargs=custom_args or {},
    )

    async def final_function_handler(context_obj: Any) -> Any:
        return await tool.invoke(
            arguments=context_obj.arguments,
            tool_call_id=function_call_content.call_id,
        )

    try:
        function_result = await middleware_pipeline.execute(
            function=tool,
            arguments=args,
            context=middleware_context,
            final_handler=final_function_handler,
        )
        return FunctionResultContent(
            call_id=function_call_content.call_id,
            result=function_result,
        )
    except Exception as exc:
        message = "Error: Function failed."
        if config.include_detailed_errors:
            message = f"{message} Exception: {exc}"
        return FunctionResultContent(call_id=function_call_content.call_id, result=message, exception=exc)


def _get_tool_map(
    tools: "ToolProtocol \
    | Callable[..., Any] \
    | MutableMapping[str, Any] \
    | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]",
) -> dict[str, AIFunction[Any, Any]]:
    ai_function_list: dict[str, AIFunction[Any, Any]] = {}
    for tool in tools if isinstance(tools, list) else [tools]:
        if isinstance(tool, AIFunction):
            ai_function_list[tool.name] = tool
            continue
        if callable(tool):
            # Convert to AITool if it's a function or callable
            ai_tool = ai_function(tool)
            ai_function_list[ai_tool.name] = ai_tool
    return ai_function_list


async def _try_execute_function_calls(
    custom_args: dict[str, Any],
    attempt_idx: int,
    function_calls: Sequence["FunctionCallContent"] | Sequence["FunctionApprovalResponseContent"],
    tools: "ToolProtocol \
    | Callable[..., Any] \
    | MutableMapping[str, Any] \
    | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]",
    config: FunctionInvocationConfiguration,
    middleware_pipeline: Any = None,  # Optional MiddlewarePipeline to avoid circular imports
) -> Sequence["Contents"]:
    """Execute multiple function calls concurrently.

    Args:
        custom_args: Custom arguments to pass to each function.
        attempt_idx: The index of the current attempt iteration.
        function_calls: A sequence of FunctionCallContent to execute.
        tools: The tools available for execution.
        config: Configuration for function invocation.
        middleware_pipeline: Optional middleware pipeline to apply during execution.

    Returns:
        A list of Contents containing the results of each function call,
        or the approval requests if any function requires approval,
        or the original function calls if any are declaration only.
    """
    from ._types import FunctionApprovalRequestContent, FunctionCallContent

    tool_map = _get_tool_map(tools)
    approval_tools = [tool_name for tool_name, tool in tool_map.items() if tool.approval_mode == "always_require"]
    declaration_only = [tool_name for tool_name, tool in tool_map.items() if tool.declaration_only]
    additional_tool_names = [tool.name for tool in config.additional_tools] if config.additional_tools else []
    # check if any are calling functions that need approval
    # if so, we return approval request for all
    approval_needed = False
    declaration_only_flag = False
    for fcc in function_calls:
        if isinstance(fcc, FunctionCallContent) and fcc.name in approval_tools:
            approval_needed = True
            break
        if isinstance(fcc, FunctionCallContent) and (fcc.name in declaration_only or fcc.name in additional_tool_names):
            declaration_only_flag = True
            break
        if config.terminate_on_unknown_calls and isinstance(fcc, FunctionCallContent) and fcc.name not in tool_map:
            raise KeyError(f'Error: Requested function "{fcc.name}" not found.')
    if approval_needed:
        # approval can only be needed for Function Call Contents, not Approval Responses.
        return [
            FunctionApprovalRequestContent(id=fcc.call_id, function_call=fcc)
            for fcc in function_calls
            if isinstance(fcc, FunctionCallContent)
        ]
    if declaration_only_flag:
        # return the declaration only tools to the user, since we cannot execute them.
        return [fcc for fcc in function_calls if isinstance(fcc, FunctionCallContent)]

    # Run all function calls concurrently
    return await asyncio.gather(*[
        _auto_invoke_function(
            function_call_content=function_call,  # type: ignore[arg-type]
            custom_args=custom_args,
            tool_map=tool_map,
            sequence_index=seq_idx,
            request_index=attempt_idx,
            middleware_pipeline=middleware_pipeline,
            config=config,
        )
        for seq_idx, function_call in enumerate(function_calls)
    ])


def _update_conversation_id(kwargs: dict[str, Any], conversation_id: str | None) -> None:
    """Update kwargs with conversation id.

    Args:
        kwargs: The keyword arguments dictionary to update.
        conversation_id: The conversation ID to set, or None to skip.
    """
    if conversation_id is None:
        return
    if "chat_options" in kwargs:
        kwargs["chat_options"].conversation_id = conversation_id
    else:
        kwargs["conversation_id"] = conversation_id


def _extract_tools(kwargs: dict[str, Any]) -> Any:
    """Extract tools from kwargs or chat_options.

    Returns:
        ToolProtocol | Callable[..., Any] | MutableMapping[str, Any] |
        Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]] | None
    """
    from ._types import ChatOptions

    tools = kwargs.get("tools")
    if not tools and (chat_options := kwargs.get("chat_options")) and isinstance(chat_options, ChatOptions):
        tools = chat_options.tools
    return tools


def _collect_approval_responses(
    messages: "list[ChatMessage]",
) -> dict[str, "FunctionApprovalResponseContent"]:
    """Collect approval responses (both approved and rejected) from messages."""
    from ._types import ChatMessage, FunctionApprovalResponseContent

    fcc_todo: dict[str, FunctionApprovalResponseContent] = {}
    for msg in messages:
        for content in msg.contents if isinstance(msg, ChatMessage) else []:
            # Collect BOTH approved and rejected responses
            if isinstance(content, FunctionApprovalResponseContent):
                fcc_todo[content.id] = content
    return fcc_todo


def _replace_approval_contents_with_results(
    messages: "list[ChatMessage]",
    fcc_todo: dict[str, "FunctionApprovalResponseContent"],
    approved_function_results: "list[Contents]",
) -> None:
    """Replace approval request/response contents with function call/result contents in-place."""
    from ._types import (
        FunctionApprovalRequestContent,
        FunctionApprovalResponseContent,
        FunctionCallContent,
        FunctionResultContent,
        Role,
    )

    result_idx = 0
    for msg in messages:
        # First pass - collect existing function call IDs to avoid duplicates
        existing_call_ids = {
            content.call_id for content in msg.contents if isinstance(content, FunctionCallContent) and content.call_id
        }

        # Track approval requests that should be removed (duplicates)
        contents_to_remove = []

        for content_idx, content in enumerate(msg.contents):
            if isinstance(content, FunctionApprovalRequestContent):
                # Don't add the function call if it already exists (would create duplicate)
                if content.function_call.call_id in existing_call_ids:
                    # Just mark for removal - the function call already exists
                    contents_to_remove.append(content_idx)
                else:
                    # Put back the function call content only if it doesn't exist
                    msg.contents[content_idx] = content.function_call
            elif isinstance(content, FunctionApprovalResponseContent):
                if content.approved and content.id in fcc_todo:
                    # Replace with the corresponding result
                    if result_idx < len(approved_function_results):
                        msg.contents[content_idx] = approved_function_results[result_idx]
                        result_idx += 1
                        msg.role = Role.TOOL
                else:
                    # Create a "not approved" result for rejected calls
                    # Use function_call.call_id (the function's ID), not content.id (approval's ID)
                    msg.contents[content_idx] = FunctionResultContent(
                        call_id=content.function_call.call_id,
                        result="Error: Tool call invocation was rejected by user.",
                    )
                    msg.role = Role.TOOL

        # Remove approval requests that were duplicates (in reverse order to preserve indices)
        for idx in reversed(contents_to_remove):
            msg.contents.pop(idx)


def _handle_function_calls_response(
    func: Callable[..., Awaitable["ChatResponse"]],
) -> Callable[..., Awaitable["ChatResponse"]]:
    """Decorate the get_response method to enable function calls.

    Args:
        func: The get_response method to decorate.

    Returns:
        A decorated function that handles function calls automatically.
    """

    def decorator(
        func: Callable[..., Awaitable["ChatResponse"]],
    ) -> Callable[..., Awaitable["ChatResponse"]]:
        """Inner decorator."""

        @wraps(func)
        async def function_invocation_wrapper(
            self: "ChatClientProtocol",
            messages: "str | ChatMessage | list[str] | list[ChatMessage]",
            **kwargs: Any,
        ) -> "ChatResponse":
            from ._middleware import extract_and_merge_function_middleware
            from ._types import (
                ChatMessage,
                FunctionApprovalRequestContent,
                FunctionCallContent,
                FunctionResultContent,
                prepare_messages,
            )

            # Extract and merge function middleware from chat client with kwargs pipeline
            extract_and_merge_function_middleware(self, **kwargs)

            # Extract the middleware pipeline before calling the underlying function
            # because the underlying function may not preserve it in kwargs
            stored_middleware_pipeline = kwargs.get("_function_middleware_pipeline")

            # Get the config for function invocation (not part of ChatClientProtocol, hence getattr)
            config: FunctionInvocationConfiguration | None = getattr(self, "function_invocation_configuration", None)
            if not config:
                # Default config if not set
                config = FunctionInvocationConfiguration()

            errors_in_a_row: int = 0
            prepped_messages = prepare_messages(messages)
            response: "ChatResponse | None" = None
            fcc_messages: "list[ChatMessage]" = []

            # If tools are provided but tool_choice is not set, default to "auto" for function invocation
            tools = _extract_tools(kwargs)
            if tools and kwargs.get("tool_choice") is None:
                kwargs["tool_choice"] = "auto"

            for attempt_idx in range(config.max_iterations if config.enabled else 0):
                fcc_todo = _collect_approval_responses(prepped_messages)
                if fcc_todo:
                    tools = _extract_tools(kwargs)
                    # Only execute APPROVED function calls, not rejected ones
                    approved_responses = [resp for resp in fcc_todo.values() if resp.approved]
                    approved_function_results: list[Contents] = []
                    if approved_responses:
                        approved_function_results = await _try_execute_function_calls(
                            custom_args=kwargs,
                            attempt_idx=attempt_idx,
                            function_calls=approved_responses,
                            tools=tools,  # type: ignore
                            middleware_pipeline=stored_middleware_pipeline,
                            config=config,
                        )
                        if any(
                            fcr.exception is not None
                            for fcr in approved_function_results
                            if isinstance(fcr, FunctionResultContent)
                        ):
                            errors_in_a_row += 1
                            # no need to reset the counter here, since this is the start of a new attempt.
                        if errors_in_a_row >= config.max_consecutive_errors_per_request:
                            logger.warning(
                                "Maximum consecutive function call errors reached (%d). "
                                "Stopping further function calls for this request.",
                                config.max_consecutive_errors_per_request,
                            )
                            # break out of the loop and do the fallback response
                            break
                    _replace_approval_contents_with_results(prepped_messages, fcc_todo, approved_function_results)

                response = await func(self, messages=prepped_messages, **kwargs)
                # if there are function calls, we will handle them first
                function_results = {
                    it.call_id for it in response.messages[0].contents if isinstance(it, FunctionResultContent)
                }
                function_calls = [
                    it
                    for it in response.messages[0].contents
                    if isinstance(it, FunctionCallContent) and it.call_id not in function_results
                ]

                if response.conversation_id is not None:
                    _update_conversation_id(kwargs, response.conversation_id)
                    prepped_messages = []

                # we load the tools here, since middleware might have changed them compared to before calling func.
                tools = _extract_tools(kwargs)
                if function_calls and tools:
                    # Use the stored middleware pipeline instead of extracting from kwargs
                    # because kwargs may have been modified by the underlying function
                    function_call_results: list[Contents] = await _try_execute_function_calls(
                        custom_args=kwargs,
                        attempt_idx=attempt_idx,
                        function_calls=function_calls,
                        tools=tools,  # type: ignore
                        middleware_pipeline=stored_middleware_pipeline,
                        config=config,
                    )
                    # Check if we have approval requests or function calls (not results) in the results
                    if any(isinstance(fccr, FunctionApprovalRequestContent) for fccr in function_call_results):
                        # Add approval requests to the existing assistant message (with tool_calls)
                        # instead of creating a separate tool message
                        from ._types import Role

                        if response.messages and response.messages[0].role == Role.ASSISTANT:
                            response.messages[0].contents.extend(function_call_results)
                        else:
                            # Fallback: create new assistant message (shouldn't normally happen)
                            result_message = ChatMessage(role="assistant", contents=function_call_results)
                            response.messages.append(result_message)
                        return response
                    if any(isinstance(fccr, FunctionCallContent) for fccr in function_call_results):
                        # the function calls are already in the response, so we just continue
                        return response

                    if any(
                        fcr.exception is not None
                        for fcr in function_call_results
                        if isinstance(fcr, FunctionResultContent)
                    ):
                        errors_in_a_row += 1
                        if errors_in_a_row >= config.max_consecutive_errors_per_request:
                            logger.warning(
                                "Maximum consecutive function call errors reached (%d). "
                                "Stopping further function calls for this request.",
                                config.max_consecutive_errors_per_request,
                            )
                            # break out of the loop and do the fallback response
                            break
                    else:
                        errors_in_a_row = 0

                    # add a single ChatMessage to the response with the results
                    result_message = ChatMessage(role="tool", contents=function_call_results)
                    response.messages.append(result_message)
                    # response should contain 2 messages after this,
                    # one with function call contents
                    # and one with function result contents
                    # the amount and call_id's should match
                    # this runs in every but the first run
                    # we need to keep track of all function call messages
                    fcc_messages.extend(response.messages)
                    if response.conversation_id is not None:
                        prepped_messages.clear()
                        prepped_messages.append(result_message)
                    else:
                        prepped_messages.extend(response.messages)
                    continue
                # If we reach this point, it means there were no function calls to handle,
                # we'll add the previous function call and responses
                # to the front of the list, so that the final response is the last one
                # TODO (eavanvalkenburg): control this behavior?
                if fcc_messages:
                    for msg in reversed(fcc_messages):
                        response.messages.insert(0, msg)
                return response

            # Failsafe: give up on tools, ask model for plain answer
            kwargs["tool_choice"] = "none"
            response = await func(self, messages=prepped_messages, **kwargs)
            if fcc_messages:
                for msg in reversed(fcc_messages):
                    response.messages.insert(0, msg)
            return response

        return function_invocation_wrapper  # type: ignore

    return decorator(func)


def _handle_function_calls_streaming_response(
    func: Callable[..., AsyncIterable["ChatResponseUpdate"]],
) -> Callable[..., AsyncIterable["ChatResponseUpdate"]]:
    """Decorate the get_streaming_response method to handle function calls.

    Args:
        func: The get_streaming_response method to decorate.

    Returns:
        A decorated function that handles function calls in streaming mode.
    """

    def decorator(
        func: Callable[..., AsyncIterable["ChatResponseUpdate"]],
    ) -> Callable[..., AsyncIterable["ChatResponseUpdate"]]:
        """Inner decorator."""

        @wraps(func)
        async def streaming_function_invocation_wrapper(
            self: "ChatClientProtocol",
            messages: "str | ChatMessage | list[str] | list[ChatMessage]",
            **kwargs: Any,
        ) -> AsyncIterable["ChatResponseUpdate"]:
            """Wrap the inner get streaming response method to handle tool calls."""
            from ._middleware import extract_and_merge_function_middleware
            from ._types import (
                ChatMessage,
                ChatResponse,
                ChatResponseUpdate,
                FunctionCallContent,
                FunctionResultContent,
                prepare_messages,
            )

            # Extract and merge function middleware from chat client with kwargs pipeline
            extract_and_merge_function_middleware(self, **kwargs)

            # Extract the middleware pipeline before calling the underlying function
            # because the underlying function may not preserve it in kwargs
            stored_middleware_pipeline = kwargs.get("_function_middleware_pipeline")

            # Get the config for function invocation (not part of ChatClientProtocol, hence getattr)
            config: FunctionInvocationConfiguration | None = getattr(self, "function_invocation_configuration", None)
            if not config:
                # Default config if not set
                config = FunctionInvocationConfiguration()

            errors_in_a_row: int = 0
            prepped_messages = prepare_messages(messages)
            fcc_messages: "list[ChatMessage]" = []
            for attempt_idx in range(config.max_iterations if config.enabled else 0):
                fcc_todo = _collect_approval_responses(prepped_messages)
                if fcc_todo:
                    tools = _extract_tools(kwargs)
                    # Only execute APPROVED function calls, not rejected ones
                    approved_responses = [resp for resp in fcc_todo.values() if resp.approved]
                    approved_function_results: list[Contents] = []
                    if approved_responses:
                        approved_function_results = await _try_execute_function_calls(
                            custom_args=kwargs,
                            attempt_idx=attempt_idx,
                            function_calls=approved_responses,
                            tools=tools,  # type: ignore
                            middleware_pipeline=stored_middleware_pipeline,
                            config=config,
                        )
                        if any(
                            fcr.exception is not None
                            for fcr in approved_function_results
                            if isinstance(fcr, FunctionResultContent)
                        ):
                            errors_in_a_row += 1
                            # no need to reset the counter here, since this is the start of a new attempt.
                    _replace_approval_contents_with_results(prepped_messages, fcc_todo, approved_function_results)

                all_updates: list["ChatResponseUpdate"] = []
                async for update in func(self, messages=prepped_messages, **kwargs):
                    all_updates.append(update)
                    yield update

                # efficient check for FunctionCallContent in the updates
                # if there is at least one, this stops and continuous
                # if there are no FCC's then it returns
                from ._types import FunctionApprovalRequestContent

                if not any(
                    isinstance(item, (FunctionCallContent, FunctionApprovalRequestContent))
                    for upd in all_updates
                    for item in upd.contents
                ):
                    return

                # Now combining the updates to create the full response.
                # Depending on the prompt, the message may contain both function call
                # content and others

                response: "ChatResponse" = ChatResponse.from_chat_response_updates(all_updates)
                # get the function calls (excluding ones that already have results)
                function_results = {
                    it.call_id for it in response.messages[0].contents if isinstance(it, FunctionResultContent)
                }
                function_calls = [
                    it
                    for it in response.messages[0].contents
                    if isinstance(it, FunctionCallContent) and it.call_id not in function_results
                ]

                # When conversation id is present, it means that messages are hosted on the server.
                # In this case, we need to update kwargs with conversation id and also clear messages
                if response.conversation_id is not None:
                    _update_conversation_id(kwargs, response.conversation_id)
                    prepped_messages = []

                # we load the tools here, since middleware might have changed them compared to before calling func.
                tools = _extract_tools(kwargs)
                if function_calls and tools:
                    # Use the stored middleware pipeline instead of extracting from kwargs
                    # because kwargs may have been modified by the underlying function
                    function_call_results: list[Contents] = await _try_execute_function_calls(
                        custom_args=kwargs,
                        attempt_idx=attempt_idx,
                        function_calls=function_calls,
                        tools=tools,  # type: ignore
                        middleware_pipeline=stored_middleware_pipeline,
                        config=config,
                    )

                    # Check if we have approval requests or function calls (not results) in the results
                    if any(isinstance(fccr, FunctionApprovalRequestContent) for fccr in function_call_results):
                        # Add approval requests to the existing assistant message (with tool_calls)
                        # instead of creating a separate tool message
                        from ._types import Role

                        if response.messages and response.messages[0].role == Role.ASSISTANT:
                            response.messages[0].contents.extend(function_call_results)
                            # Yield the approval requests as part of the assistant message
                            yield ChatResponseUpdate(contents=function_call_results, role="assistant")
                        else:
                            # Fallback: create new assistant message (shouldn't normally happen)
                            result_message = ChatMessage(role="assistant", contents=function_call_results)
                            yield ChatResponseUpdate(contents=function_call_results, role="assistant")
                            response.messages.append(result_message)
                        return
                    if any(isinstance(fccr, FunctionCallContent) for fccr in function_call_results):
                        # the function calls were already yielded.
                        return

                    if any(
                        fcr.exception is not None
                        for fcr in function_call_results
                        if isinstance(fcr, FunctionResultContent)
                    ):
                        errors_in_a_row += 1
                        if errors_in_a_row >= config.max_consecutive_errors_per_request:
                            logger.warning(
                                "Maximum consecutive function call errors reached (%d). "
                                "Stopping further function calls for this request.",
                                config.max_consecutive_errors_per_request,
                            )
                            # break out of the loop and do the fallback response
                            break
                    else:
                        errors_in_a_row = 0

                    # add a single ChatMessage to the response with the results
                    result_message = ChatMessage(role="tool", contents=function_call_results)
                    yield ChatResponseUpdate(contents=function_call_results, role="tool")
                    response.messages.append(result_message)
                    # response should contain 2 messages after this,
                    # one with function call contents
                    # and one with function result contents
                    # the amount and call_id's should match
                    # this runs in every but the first run
                    # we need to keep track of all function call messages
                    fcc_messages.extend(response.messages)
                    if response.conversation_id is not None:
                        prepped_messages.clear()
                        prepped_messages.append(result_message)
                    else:
                        prepped_messages.extend(response.messages)
                    continue
                # If we reach this point, it means there were no function calls to handle,
                # so we're done
                return

            # Failsafe: give up on tools, ask model for plain answer
            kwargs["tool_choice"] = "none"
            async for update in func(self, messages=prepped_messages, **kwargs):
                yield update

        return streaming_function_invocation_wrapper

    return decorator(func)


def use_function_invocation(
    chat_client: type[TChatClient],
) -> type[TChatClient]:
    """Class decorator that enables tool calling for a chat client.

    This decorator wraps the ``get_response`` and ``get_streaming_response`` methods
    to automatically handle function calls from the model, execute them, and return
    the results back to the model for further processing.

    Args:
        chat_client: The chat client class to decorate.

    Returns:
        The decorated chat client class with function invocation enabled.

    Raises:
        ChatClientInitializationError: If the chat client does not have the required methods.

    Examples:
        .. code-block:: python

            from agent_framework import use_function_invocation, BaseChatClient


            @use_function_invocation
            class MyCustomClient(BaseChatClient):
                async def get_response(self, messages, **kwargs):
                    # Implementation here
                    pass

                async def get_streaming_response(self, messages, **kwargs):
                    # Implementation here
                    pass


            # The client now automatically handles function calls
            client = MyCustomClient()
    """
    if getattr(chat_client, FUNCTION_INVOKING_CHAT_CLIENT_MARKER, False):
        return chat_client

    try:
        chat_client.get_response = _handle_function_calls_response(  # type: ignore
            func=chat_client.get_response,  # type: ignore
        )
    except AttributeError as ex:
        raise ChatClientInitializationError(
            f"Chat client {chat_client.__name__} does not have a get_response method, cannot apply function invocation."
        ) from ex
    try:
        chat_client.get_streaming_response = _handle_function_calls_streaming_response(  # type: ignore
            func=chat_client.get_streaming_response,
        )
    except AttributeError as ex:
        raise ChatClientInitializationError(
            f"Chat client {chat_client.__name__} does not have a get_streaming_response method, "
            "cannot apply function invocation."
        ) from ex
    setattr(chat_client, FUNCTION_INVOKING_CHAT_CLIENT_MARKER, True)
    return chat_client
