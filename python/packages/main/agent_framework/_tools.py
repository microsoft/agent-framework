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
from pydantic import AnyUrl, BaseModel, Field, PrivateAttr, ValidationError, create_model, field_validator

from ._logging import get_logger
from ._pydantic import AFBaseModel
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


# region Tools
@runtime_checkable
class ToolProtocol(Protocol):
    """Represents a generic tool that can be specified to an AI service.

    Parameters:
        name: The name of the tool.
        description: A description of the tool.
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


def _default_histogram() -> Histogram:
    """Get the default histogram for function invocation duration."""
    return get_meter().create_histogram(
        name=OtelAttr.MEASUREMENT_FUNCTION_INVOCATION_DURATION,
        unit=OtelAttr.DURATION_UNIT,
        description="Measures the duration of a function's execution",
        explicit_bucket_boundaries_advisory=OPERATION_DURATION_BUCKET_BOUNDARIES,
    )


class AIFunction(BaseTool, Generic[ArgsT, ReturnT]):
    """A AITool that is callable as code.

    Args:
        name: The name of the function.
        description: A description of the function.
        additional_properties: Additional properties to set on the function.
        func: The function to wrap. If None, returns a decorator.
        input_model: The Pydantic model that defines the input parameters for the function.
    """

    func: Callable[..., Awaitable[ReturnT] | ReturnT]
    input_model: type[ArgsT]
    _invocation_duration_histogram: Histogram = PrivateAttr(default_factory=_default_histogram)

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
            otel_settings: Optional model diagnostics settings to override the default settings.
            kwargs: keyword arguments to pass to the function, will not be used if `arguments` is provided.
        """
        global OTEL_SETTINGS
        from .observability import OTEL_SETTINGS

        tool_call_id = kwargs.pop("tool_call_id", None)
        if arguments is not None:
            if not isinstance(arguments, self.input_model):
                raise TypeError(f"Expected {self.input_model.__name__}, got {type(arguments).__name__}")
            kwargs = arguments.model_dump(exclude_none=True)
        if not OTEL_SETTINGS.ENABLED:  # type: ignore[name-defined]
            logger.info(f"Function name: {self.name}")
            logger.debug(f"Function arguments: {kwargs}")
            res = self.__call__(**kwargs)
            result = await res if inspect.isawaitable(res) else res
            logger.info(f"Function {self.name} succeeded.")
            logger.debug(f"Function result: {result or 'None'}")
            return result  # type: ignore[reportReturnType]

        attributes = get_function_span_attributes(self, tool_call_id=tool_call_id)
        if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED:  # type: ignore[name-defined]
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
            if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED:  # type: ignore[name-defined]
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
                if OTEL_SETTINGS.SENSITIVE_DATA_ENABLED:  # type: ignore[name-defined]
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


# region AI Function Decorator


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

    Example:

        .. code-block:: python

            from typing import Annotated
            from pydantic import Field


            def ai_function_example(
                arg1: Annotated[str, Field(description="The first argument")],
                arg2: Annotated[int, Field(description="The second argument")],
            ) -> str:
                # An example function that takes two arguments and returns a string.
                return f"arg1: {arg1}, arg2: {arg2}"

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
    """Invoke a function call requested by the agent, applying filters that are defined in the agent."""
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
    | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]",
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
    | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]",
    middleware_pipeline: Any = None,  # Optional MiddlewarePipeline to avoid circular imports
) -> list["Contents"]:
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


def update_conversation_id(kwargs: dict[str, Any], conversation_id: str | None) -> None:
    """Update kwargs with conversation id."""
    if conversation_id is None:
        return
    if "chat_options" in kwargs:
        kwargs["chat_options"].conversation_id = conversation_id
    else:
        kwargs["conversation_id"] = conversation_id


def _handle_function_calls_response(
    func: Callable[..., Awaitable["ChatResponse"]],
    *,
    max_iterations: int = 10,
) -> Callable[..., Awaitable["ChatResponse"]]:
    """Decorate the get_response method to enable function calls.

    Args:
        func: The get_response method to decorate.
        max_iterations: The maximum number of function call iterations to perform.

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
            from ._types import ChatMessage, ChatOptions, FunctionCallContent, FunctionResultContent

            prepped_messages = prepare_messages(messages)
            response: "ChatResponse | None" = None
            fcc_messages: "list[ChatMessage]" = []
            for attempt_idx in range(max_iterations):
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
                    update_conversation_id(kwargs, response.conversation_id)
                    prepped_messages = []

                tools = kwargs.get("tools")
                if not tools and (chat_options := kwargs.get("chat_options")) and isinstance(chat_options, ChatOptions):
                    tools = chat_options.tools
                if function_calls and tools:
                    # Extract function middleware pipeline from kwargs if available
                    middleware_pipeline = kwargs.get("_function_middleware_pipeline")
                    function_results = await execute_function_calls(
                        custom_args=kwargs,
                        attempt_idx=attempt_idx,
                        function_calls=function_calls,
                        tools=tools,  # type: ignore
                        middleware_pipeline=middleware_pipeline,
                    )
                    # add a single ChatMessage to the response with the results
                    result_message = ChatMessage(role="tool", contents=function_results)  # type: ignore[call-overload]
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
    *,
    max_iterations: int = 10,
) -> Callable[..., AsyncIterable["ChatResponseUpdate"]]:
    """Decorate the get_streaming_response method to handle function calls.

    Args:
        func: The get_streaming_response method to decorate.
        max_iterations: The maximum number of function call iterations to perform.

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
            from ._types import ChatMessage, ChatOptions, ChatResponse, ChatResponseUpdate, FunctionCallContent

            prepped_messages = prepare_messages(messages)
            for attempt_idx in range(max_iterations):
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
                    update_conversation_id(kwargs, response.conversation_id)
                    prepped_messages = []

                tools = kwargs.get("tools")
                if not tools and (chat_options := kwargs.get("chat_options")) and isinstance(chat_options, ChatOptions):
                    tools = chat_options.tools

                if function_calls and tools:
                    # Extract function middleware pipeline from kwargs if available
                    middleware_pipeline = kwargs.get("_function_middleware_pipeline")
                    function_results = await execute_function_calls(
                        custom_args=kwargs,
                        attempt_idx=attempt_idx,
                        function_calls=function_calls,
                        tools=tools,  # type: ignore[reportArgumentType]
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
    """Class decorator that enables tool calling for a chat client."""
    if getattr(chat_client, FUNCTION_INVOKING_CHAT_CLIENT_MARKER, False):
        return chat_client

    max_iterations = DEFAULT_MAX_ITERATIONS

    try:
        chat_client.get_response = _handle_function_calls_response(  # type: ignore
            func=chat_client.get_response,  # type: ignore
            max_iterations=max_iterations,
        )
    except AttributeError as ex:
        raise ChatClientInitializationError(
            f"Chat client {chat_client.__name__} does not have a get_response method, cannot apply function invocation."
        ) from ex
    try:
        chat_client.get_streaming_response = _handle_function_calls_streaming_response(  # type: ignore
            func=chat_client.get_streaming_response,
            max_iterations=max_iterations,
        )
    except AttributeError as ex:
        raise ChatClientInitializationError(
            f"Chat client {chat_client.__name__} does not have a get_streaming_response method, "
            "cannot apply function invocation."
        ) from ex
    setattr(chat_client, FUNCTION_INVOKING_CHAT_CLIENT_MARKER, True)
    return chat_client
