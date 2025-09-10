# Copyright (c) Microsoft. All rights reserved.
import inspect
import sys
from collections.abc import Awaitable, Callable, Collection
from functools import wraps
from time import perf_counter
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Generic,
    Literal,
    Protocol,
    TypeVar,
    get_args,
    get_origin,
    runtime_checkable,
)

from opentelemetry import metrics, trace
from pydantic import AnyUrl, BaseModel, Field, PrivateAttr, ValidationError, create_model, field_validator

from ._logging import get_logger
from ._pydantic import AFBaseModel
from .exceptions import ToolException
from .telemetry import GenAIAttributes, start_as_current_span

if TYPE_CHECKING:
    from ._types import Contents

if sys.version_info >= (3, 12):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # pragma: no cover

tracer: trace.Tracer = trace.get_tracer("agent_framework")
meter: metrics.Meter = metrics.get_meter_provider().get_meter("agent_framework")
logger = get_logger()

__all__ = [
    "AIFunction",
    "HostedCodeInterpreterTool",
    "HostedFileSearchTool",
    "HostedMCPSpecificApproval",
    "HostedMCPTool",
    "HostedWebSearchTool",
    "ToolProtocol",
    "ai_function",
]


def _parse_inputs(
    inputs: "Contents | dict[str, Any] | str | list[Contents | dict[str, Any] | str] | None",
) -> list["Contents"]:
    """Parse the inputs for a tool, ensuring they are of type Contents."""
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


@runtime_checkable
class ToolProtocol(Protocol):
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
    description: str
    """A description of the tool, suitable for use in describing the purpose to a model."""
    additional_properties: dict[str, Any] | None
    """Additional properties associated with the tool."""

    def __str__(self) -> str:
        """Return a string representation of the tool."""
        ...


ArgsT = TypeVar("ArgsT", bound=BaseModel)
ReturnT = TypeVar("ReturnT")


class BaseTool(AFBaseModel):
    """Base class for AI tools, providing common attributes and methods.

    Args:
        name: The name of the tool.
        description: A description of the tool.
        additional_properties: Additional properties associated with the tool.
    """

    name: str = Field(..., kw_only=False)
    description: str = ""
    additional_properties: dict[str, Any] | None = None

    def __str__(self) -> str:
        """Return a string representation of the tool."""
        if self.description:
            return f"{self.__class__.__name__}(name={self.name}, description={self.description})"
        return f"{self.__class__.__name__}(name={self.name})"


class HostedCodeInterpreterTool(BaseTool):
    """Represents a hosted tool that can be specified to an AI service to enable it to execute generated code.

    This tool does not implement code interpretation itself. It serves as a marker to inform a service
    that it is allowed to execute generated code if the service is capable of doing so.
    """

    inputs: list[Any] = Field(default_factory=list)

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
        args: dict[str, Any] = {
            "name": "code_interpreter",
        }
        if inputs:
            args["inputs"] = _parse_inputs(inputs)
        if description is not None:
            args["description"] = description
        if additional_properties is not None:
            args["additional_properties"] = additional_properties
        if "name" in kwargs:
            raise ValueError("The 'name' argument is reserved for the HostedCodeInterpreterTool and cannot be set.")
        super().__init__(**args, **kwargs)


class HostedWebSearchTool(BaseTool):
    """Represents a web search tool that can be specified to an AI service to enable it to perform web searches."""

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
        """
        args: dict[str, Any] = {
            "name": "web_search",
        }
        super().__init__(**args, **kwargs)


class HostedMCPSpecificApproval(TypedDict, total=False):
    """Represents the `specific` mode for a hosted tool.

    When using this mode, the user must specify which tools always or never require approval.
    This is represented as a dictionary with two optional keys:
    - `always_require_approval`: A sequence of tool names that always require approval.
    - `never_require_approval`: A sequence of tool names that never require approval.

    """

    always_require_approval: Collection[str] | None
    never_require_approval: Collection[str] | None


class HostedMCPTool(BaseTool):
    """Represents a MCP tool that is managed and executed by the service."""

    url: AnyUrl
    approval_mode: Literal["always_require", "never_require"] | HostedMCPSpecificApproval | None = None
    allowed_tools: set[str] | None = None
    headers: dict[str, str] | None = None

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
        args: dict[str, Any] = {
            "name": name,
            "url": url,
        }
        if allowed_tools is not None:
            args["allowed_tools"] = allowed_tools
        if approval_mode is not None:
            args["approval_mode"] = approval_mode
        if headers is not None:
            args["headers"] = headers
        if description is not None:
            args["description"] = description
        if additional_properties is not None:
            args["additional_properties"] = additional_properties
        try:
            super().__init__(**args, **kwargs)
        except ValidationError as err:
            raise ToolException(f"Error initializing HostedMCPTool: {err}", inner_exception=err) from err

    @field_validator("approval_mode")
    def validate_approval_mode(cls, approval_mode: str | dict[str, Any] | None) -> str | dict[str, Any] | None:
        """Validate the approval_mode field to ensure it is one of the accepted values."""
        if approval_mode is None or not isinstance(approval_mode, dict):
            return approval_mode
        # Validate that the dict has sets
        for key, value in approval_mode.items():
            if not isinstance(value, set):
                approval_mode[key] = set(value)  # Convert to set if it's a list or other collection
        return approval_mode


class HostedFileSearchTool(BaseTool):
    """Represents a file search tool that can be specified to an AI service to enable it to perform file searches."""

    inputs: list[Any] | None = None
    max_results: int | None = None

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
        args: dict[str, Any] = {
            "name": "file_search",
        }
        if inputs:
            args["inputs"] = _parse_inputs(inputs)
        if max_results:
            args["max_results"] = max_results
        if description is not None:
            args["description"] = description
        if additional_properties is not None:
            args["additional_properties"] = additional_properties
        if "name" in kwargs:
            raise ValueError("The 'name' argument is reserved for the HostedFileSearchTool and cannot be set.")
        super().__init__(**args, **kwargs)


class AIFunction(BaseTool, Generic[ArgsT, ReturnT]):
    """A ToolProtocol that is callable as code.

    Args:
        name: The name of the function.
        description: A description of the function.
        additional_properties: Additional properties to set on the function.
        func: The function to wrap. If None, returns a decorator.
        input_model: The Pydantic model that defines the input parameters for the function.
    """

    func: Callable[..., Awaitable[ReturnT] | ReturnT]
    input_model: type[ArgsT]
    _invocation_duration_histogram: metrics.Histogram = PrivateAttr(
        default_factory=lambda: meter.create_histogram(
            GenAIAttributes.MEASUREMENT_FUNCTION_INVOCATION_DURATION.value,
            unit="s",
            description="Measures the duration of a function's execution",
        )
    )

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
                self._invocation_duration_histogram.record(duration, attributes=attributes)
                logger.info("Function completed. Duration: %fs", duration)

    def parameters(self) -> dict[str, Any]:
        """Create the json schema of the parameters."""
        return self.input_model.model_json_schema()

    def to_json_schema_spec(self) -> dict[str, Any]:
        """Convert a AIFunction to the JSON Schema function specification format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters(),
            },
        }


def _parse_annotation(annotation: Any) -> Any:
    """Parse a type annotation and return the corresponding type.

    If the second annotation (after the type) is a string, then we convert that to a pydantic Field description.
    The rest are returned as-is, allowing for multiple annotations.
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
