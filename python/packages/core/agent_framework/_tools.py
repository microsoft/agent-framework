# Copyright (c) Microsoft. All rights reserved.

import asyncio
import inspect
import json
import sys
from collections.abc import AsyncIterable, Awaitable, Callable, Collection, MutableMapping, Sequence
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
    get_args,
    get_origin,
    runtime_checkable,
)

from opentelemetry.metrics import Histogram
from pydantic import AnyUrl, BaseModel, Field, ValidationError, create_model

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
        FunctionCallContent,
    )

if sys.version_info >= (3, 12):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # pragma: no cover

logger = get_logger()

__all__ = [
    "FUNCTION_INVOKING_CHAT_CLIENT_MARKER",
    "AIFunction",
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
DEFAULT_MAX_ITERATIONS: Final[int] = 10
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
    """Represents a generic tool that can be specified to an AI service.

    This protocol defines the interface that all tools must implement to be compatible
    with the agent framework.

    Attributes:
        name: The name of the tool.
        description: A description of the tool, suitable for use in describing the purpose to a model.
        additional_properties: Additional properties associated with the tool.

    Examples:
        .. code-block:: python

            from agent_framework import ToolProtocol


            class CustomTool:
                def __init__(self, name: str, description: str) -> None:
                    self.name = name
                    self.description = description
                    self.additional_properties = None

                def __str__(self) -> str:
                    return f"CustomTool(name={self.name})"


            # Tool now implements ToolProtocol
            tool: ToolProtocol = CustomTool("my_tool", "Does something useful")
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

    This class provides the foundation for creating custom tools with serialization support.

    Args:
        name: The name of the tool.
        description: A description of the tool.
        additional_properties: Additional properties associated with the tool.

    Examples:
        .. code-block:: python

            from agent_framework import BaseTool


            class MyCustomTool(BaseTool):
                def __init__(self, name: str, custom_param: str) -> None:
                    super().__init__(name=name, description="My custom tool")
                    self.custom_param = custom_param


            tool = MyCustomTool(name="custom", custom_param="value")
            print(tool)  # MyCustomTool(name=custom, description=My custom tool)
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

        Args:
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

        Args:
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

        Args:
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

        Args:
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
        inputs: "Contents | dict[str, Any] | str | list[Contents | dict[str, Any] | str] | None" = None,
        max_results: int | None = None,
        description: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """Initialize a FileSearchTool.

        Args:
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


class AIFunction(BaseTool, Generic[ArgsT, ReturnT]):
    """A AITool that is callable as code.

    This class wraps a Python function to make it callable by AI models with automatic
    parameter validation and JSON schema generation.

    Args:
        name: The name of the function.
        description: A description of the function.
        additional_properties: Additional properties to set on the function.
        func: The function to wrap.
        input_model: The Pydantic model that defines the input parameters for the function.

    Examples:
        .. code-block:: python

            from typing import Annotated
            from pydantic import BaseModel
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
        additional_properties: dict[str, Any] | None = None,
        func: Callable[..., Awaitable[ReturnT] | ReturnT],
        input_model: type[ArgsT],
        **kwargs: Any,
    ) -> None:
        """Initialize the AIFunction.

        Args:
            name: The name of the function.
            description: A description of the function.
            additional_properties: Additional properties to set on the function.
            func: The function to wrap.
            input_model: The Pydantic model that defines the input parameters for the function.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(
            name=name,
            description=description,
            additional_properties=additional_properties,
            **kwargs,
        )
        self.func = func
        self.input_model = input_model
        self._invocation_duration_histogram = _default_histogram()

    def __call__(self, *args: Any, **kwargs: Any) -> ReturnT | Awaitable[ReturnT]:
        """Call the wrapped function with the provided arguments."""
        return self.func(*args, **kwargs)

    async def invoke(
        self,
        *,
        arguments: ArgsT | None = None,
        **kwargs: Any,
    ) -> ReturnT:
        """Run the AI function with the provided arguments as a Pydantic model.

        Args:
            arguments: A Pydantic model instance containing the arguments for the function.
            kwargs: Keyword arguments to pass to the function, will not be used if ``arguments`` is provided.

        Returns:
            The result of the function execution.

        Raises:
            TypeError: If arguments is not an instance of the expected input model.
        """
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


def ai_function(
    func: Callable[..., ReturnT | Awaitable[ReturnT]] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    additional_properties: dict[str, Any] | None = None,
) -> AIFunction[Any, ReturnT]:
    """Decorate a function to turn it into a AIFunction that can be passed to models and executed automatically.

    This decorator creates a Pydantic model from the function's signature,
    which will be used to validate the arguments passed to the function
    and to generate the JSON schema for the function's parameters.

    To add descriptions to parameters, use the ``Annotated`` type from ``typing``
    with a string description as the second argument. You can also use Pydantic's
    ``Field`` class for more advanced configuration.

    Args:
        func: The function to wrap. If None, returns a decorator.
        name: The name of the tool. Defaults to the function's name.
        description: A description of the tool. Defaults to the function's docstring.
        additional_properties: Additional properties to set on the tool.

    Returns:
        An AIFunction instance that wraps the decorated function.

    Examples:
        .. code-block:: python

            from typing import Annotated
            from agent_framework import ai_function


            # Using string annotations (recommended)
            @ai_function
            def get_weather(
                location: Annotated[str, "The city name"],
                unit: Annotated[str, "Temperature unit"] = "celsius",
            ) -> str:
                '''Get the weather for a location.'''
                return f"Weather in {location}: 22°{unit[0].upper()}"


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
            sig = inspect.signature(f)
            fields = {
                pname: (
                    _parse_annotation(param.annotation) if param.annotation is not inspect.Parameter.empty else str,
                    param.default if param.default is not inspect.Parameter.empty else ...,
                )
                for pname, param in sig.parameters.items()
                if pname not in {"self", "cls"}
            }
            input_model: Any = create_model(f"{tool_name}_input", **fields)  # type: ignore[call-overload]
            if not issubclass(input_model, BaseModel):
                raise TypeError(f"Input model for {tool_name} must be a subclass of BaseModel, got {input_model}")

            return AIFunction[Any, ReturnT](
                name=tool_name,
                description=tool_desc,
                additional_properties=additional_properties or {},
                func=f,
                input_model=input_model,
            )

        return wrapper(func)

    return decorator(func) if func else decorator  # type: ignore[reportReturnType, return-value]


# region Function Invoking Chat Client


async def _auto_invoke_function(
    function_call_content: "FunctionCallContent",
    custom_args: dict[str, Any] | None = None,
    *,
    tool_map: dict[str, AIFunction[BaseModel, Any]],
    sequence_index: int | None = None,
    request_index: int | None = None,
    middleware_pipeline: Any = None,  # Optional MiddlewarePipeline
) -> "Contents":
    """Invoke a function call requested by the agent, applying middleware that is defined.

    Args:
        function_call_content: The function call content from the model.
        custom_args: Additional custom arguments to merge with parsed arguments.
        tool_map: A mapping of tool names to AIFunction instances.
        sequence_index: The index of the function call in the sequence.
        request_index: The index of the request iteration.
        middleware_pipeline: Optional middleware pipeline to apply during execution.

    Returns:
        A FunctionResultContent containing the result or exception.

    Raises:
        KeyError: If the requested function is not found in the tool map.
    """
    from ._types import FunctionResultContent

    tool: AIFunction[BaseModel, Any] | None = tool_map.get(function_call_content.name)
    if tool is None:
        raise KeyError(f"No tool or function named '{function_call_content.name}'")

    parsed_args: dict[str, Any] = dict(function_call_content.parse_arguments() or {})

    # Merge with user-supplied args; right-hand side dominates, so parsed args win on conflicts.
    merged_args: dict[str, Any] = (custom_args or {}) | parsed_args
    args = tool.input_model.model_validate(merged_args)
    exception = None

    # Execute through middleware pipeline if available
    if middleware_pipeline and hasattr(middleware_pipeline, "has_middlewares") and middleware_pipeline.has_middlewares:
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
        except Exception as ex:
            exception = ex
            function_result = None
    else:
        # No middleware - execute directly
        try:
            function_result = await tool.invoke(
                arguments=args,
                tool_call_id=function_call_content.call_id,
            )  # type: ignore[arg-type]
        except Exception as ex:
            exception = ex
            function_result = None

    return FunctionResultContent(
        call_id=function_call_content.call_id,
        exception=exception,
        result=function_result,
    )


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


async def execute_function_calls(
    custom_args: dict[str, Any],
    attempt_idx: int,
    function_calls: Sequence["FunctionCallContent"],
    tools: "ToolProtocol \
    | Callable[..., Any] \
    | MutableMapping[str, Any] \
    | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]",
    middleware_pipeline: Any = None,  # Optional MiddlewarePipeline to avoid circular imports
) -> list["Contents"]:
    """Execute multiple function calls concurrently.

    Args:
        custom_args: Custom arguments to pass to each function.
        attempt_idx: The index of the current attempt iteration.
        function_calls: A sequence of FunctionCallContent to execute.
        tools: The tools available for execution.
        middleware_pipeline: Optional middleware pipeline to apply during execution.

    Returns:
        A list of Contents containing the results of each function call.
    """
    tool_map = _get_tool_map(tools)
    # Run all function calls concurrently
    return await asyncio.gather(*[
        _auto_invoke_function(
            function_call_content=function_call,
            custom_args=custom_args,
            tool_map=tool_map,
            sequence_index=seq_idx,
            request_index=attempt_idx,
            middleware_pipeline=middleware_pipeline,
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
            from ._clients import prepare_messages
            from ._middleware import extract_and_merge_function_middleware
            from ._types import ChatMessage, ChatOptions, FunctionCallContent, FunctionResultContent

            # Extract and merge function middleware from chat client with kwargs pipeline
            extract_and_merge_function_middleware(self, kwargs)

            # Extract the middleware pipeline before calling the underlying function
            # because the underlying function may not preserve it in kwargs
            stored_middleware_pipeline = kwargs.get("_function_middleware_pipeline")

            # Get max_iterations from instance additional_properties or class attribute
            instance_max_iterations: int = DEFAULT_MAX_ITERATIONS
            if hasattr(self, "additional_properties") and self.additional_properties:
                instance_max_iterations = self.additional_properties.get("max_iterations", DEFAULT_MAX_ITERATIONS)
            elif hasattr(self.__class__, "MAX_ITERATIONS"):
                instance_max_iterations = getattr(self.__class__, "MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS)

            prepped_messages = prepare_messages(messages)
            response: "ChatResponse | None" = None
            fcc_messages: "list[ChatMessage]" = []
            for attempt_idx in range(instance_max_iterations):
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

                tools = kwargs.get("tools")
                if not tools and (chat_options := kwargs.get("chat_options")) and isinstance(chat_options, ChatOptions):
                    tools = chat_options.tools
                if function_calls and tools:
                    # Use the stored middleware pipeline instead of extracting from kwargs
                    # because kwargs may have been modified by the underlying function
                    middleware_pipeline = stored_middleware_pipeline
                    function_call_results: list[Contents] = await execute_function_calls(
                        custom_args=kwargs,
                        attempt_idx=attempt_idx,
                        function_calls=function_calls,
                        tools=tools,  # type: ignore
                        middleware_pipeline=middleware_pipeline,
                    )
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
                    # and add them as additional context to the messages
                    if getattr(kwargs.get("chat_options"), "store", False):
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
            from ._clients import prepare_messages
            from ._middleware import extract_and_merge_function_middleware
            from ._types import ChatMessage, ChatOptions, ChatResponse, ChatResponseUpdate, FunctionCallContent

            # Extract and merge function middleware from chat client with kwargs pipeline
            extract_and_merge_function_middleware(self, kwargs)

            # Extract the middleware pipeline before calling the underlying function
            # because the underlying function may not preserve it in kwargs
            stored_middleware_pipeline = kwargs.get("_function_middleware_pipeline")

            # Get max_iterations from instance additional_properties or class attribute
            instance_max_iterations: int = DEFAULT_MAX_ITERATIONS
            if hasattr(self, "additional_properties") and self.additional_properties:
                instance_max_iterations = self.additional_properties.get("max_iterations", DEFAULT_MAX_ITERATIONS)
            elif hasattr(self.__class__, "MAX_ITERATIONS"):
                instance_max_iterations = getattr(self.__class__, "MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS)

            prepped_messages = prepare_messages(messages)
            for attempt_idx in range(instance_max_iterations):
                all_updates: list["ChatResponseUpdate"] = []
                async for update in func(self, messages=prepped_messages, **kwargs):
                    all_updates.append(update)
                    yield update

                # efficient check for FunctionCallContent in the updates
                # if there is at least one, this stops and continuous
                # if there are no FCC's then it returns
                if not any(isinstance(item, FunctionCallContent) for upd in all_updates for item in upd.contents):
                    return

                # Now combining the updates to create the full response.
                # Depending on the prompt, the message may contain both function call
                # content and others

                response: "ChatResponse" = ChatResponse.from_chat_response_updates(all_updates)
                # add the response message to the previous messages
                prepped_messages.append(response.messages[0])
                # get the fccs
                function_calls = [
                    item for item in response.messages[0].contents if isinstance(item, FunctionCallContent)
                ]

                # When conversation id is present, it means that messages are hosted on the server.
                # In this case, we need to update kwargs with conversation id and also clear messages
                if response.conversation_id is not None:
                    _update_conversation_id(kwargs, response.conversation_id)
                    prepped_messages = []

                tools: Sequence[ToolProtocol | MutableMapping[str, Any]] | None = kwargs.get("tools")
                if not tools and (chat_options := kwargs.get("chat_options")) and isinstance(chat_options, ChatOptions):
                    tools = chat_options.tools

                if function_calls and tools:
                    # Use the stored middleware pipeline instead of extracting from kwargs
                    # because kwargs may have been modified by the underlying function
                    middleware_pipeline = stored_middleware_pipeline
                    function_results = await execute_function_calls(
                        custom_args=kwargs,
                        attempt_idx=attempt_idx,
                        function_calls=function_calls,
                        tools=tools,
                        middleware_pipeline=middleware_pipeline,
                    )
                    function_result_msg = ChatMessage(role="tool", contents=function_results)
                    yield ChatResponseUpdate(contents=function_results, role="tool")
                    response.messages.append(function_result_msg)
                    prepped_messages.append(function_result_msg)
                    continue

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

    # Set MAX_ITERATIONS as a class variable if not already set
    if not hasattr(chat_client, "MAX_ITERATIONS"):
        chat_client.MAX_ITERATIONS = DEFAULT_MAX_ITERATIONS  # type: ignore

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
