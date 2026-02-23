# Copyright (c) Microsoft. All rights reserved.

import contextlib
import functools
import inspect
import logging
import sys
import types
from builtins import type as builtin_type
from collections.abc import Awaitable, Callable
from types import UnionType
from typing import TYPE_CHECKING, Any, TypeVar, cast

from ._typing_utils import is_instance_of, is_type_compatible, normalize_type_to_list, resolve_type_annotation
from ._workflow_context import WorkflowContext, validate_workflow_context_annotation

if sys.version_info >= (3, 11):
    from typing import overload  # pragma: no cover
else:
    from typing_extensions import overload  # pragma: no cover

if TYPE_CHECKING:
    from ._executor import Executor


logger = logging.getLogger(__name__)


class RequestInfoMixin:
    """Mixin providing common functionality for request info handling."""

    def is_request_supported(self, request_type: builtin_type[Any], response_type: builtin_type[Any]) -> bool:
        """Check if the executor supports request of the given type and handling a response of the given type.

        Args:
            request_type: The type of the request message
            response_type: The type of the expected response message
        Returns:
            True if a response handler is registered for the given request and response types, False otherwise
        """
        if not hasattr(self, "_response_handlers"):
            return False

        for request_type_key, response_type_key in self._response_handlers:
            if is_type_compatible(request_type, request_type_key) and is_type_compatible(
                response_type, response_type_key
            ):
                return True

        return False

    def _find_response_handler(self, request: Any, response: Any) -> Callable[..., Awaitable[None]] | None:
        """Find a registered response handler for the given request and response types.

        Args:
            request: The original request
            response: The response message
        Returns:
            The response handler function with the request bound as the first argument, or None if not found
        """
        if not hasattr(self, "_response_handlers"):
            return None

        for (request_type, response_type), handler in self._response_handlers.items():
            if is_instance_of(request, request_type) and is_instance_of(response, response_type):
                return functools.partial(handler, request)

        return None

    def _discover_response_handlers(self) -> None:
        """Discover and register response handlers defined in the class."""
        # Initialize handler storage if not already present
        if not hasattr(self, "_response_handlers"):
            self._response_handlers: dict[
                tuple[builtin_type[Any], builtin_type[Any]],  # key
                Callable[[Any, Any, WorkflowContext[Any, Any]], Awaitable[None]],  # value
            ] = {}
        if not hasattr(self, "_response_handler_specs"):
            self._response_handler_specs: list[dict[str, Any]] = []

        for attr_name in dir(self.__class__):
            try:
                attr = getattr(self.__class__, attr_name)
                if callable(attr) and hasattr(attr, "_response_handler_spec"):
                    handler_spec = attr._response_handler_spec  # type: ignore

                    request_type = handler_spec["request_type"]
                    response_type = handler_spec["response_type"]

                    if self._response_handlers.get((request_type, response_type)):
                        raise ValueError(
                            f"Duplicate response handler for request type {request_type} "
                            f"and response type {response_type} in {self.__class__.__name__}"
                        )

                    self._response_handlers[request_type, response_type] = getattr(self, attr_name)
                    self._response_handler_specs.append({**handler_spec, "source": "class_method"})
            except AttributeError:
                continue  # Skip non-callable attributes or those without handler spec

        # A request sent via `request_info` must be handled by a response handler inside the same executor.
        # It is safe to assume that an executor is request-response capable if it has at least one response
        # handler, and that the executor could send a request.
        self.is_request_response_capable = bool(self._response_handlers)


ExecutorT = TypeVar("ExecutorT", bound="Executor")
ContextT = TypeVar("ContextT", bound="WorkflowContext[Any, Any]")

# region Handler Decorator


@overload
def response_handler(
    func: Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]],
) -> Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]]: ...


@overload
def response_handler(
    func: None = None,
    *,
    request: type | types.UnionType | str | None = None,
    response: type | types.UnionType | str | None = None,
    output: type | types.UnionType | str | None = None,
    workflow_output: type | types.UnionType | str | None = None,
) -> Callable[
    [Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]]],
    Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]],
]: ...


def response_handler(
    func: Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]] | None = None,
    *,
    request: type | types.UnionType | str | None = None,
    response: type | types.UnionType | str | None = None,
    output: type | types.UnionType | str | None = None,
    workflow_output: type | types.UnionType | str | None = None,
) -> (
    Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]]
    | Callable[
        [Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]]],
        Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]],
    ]
):
    """Decorator to register a handler to handle responses for a request.

    Type information can be provided in two mutually exclusive ways:

    1. **Introspection** (default): Types are inferred from function signature annotations.
       Use type annotations on the original_request, response parameters and WorkflowContext
       generic parameters.

    2. **Explicit parameters**: Types are specified via decorator parameters (request, response,
       output, workflow_output). When ANY explicit parameter is provided, ALL types must come
       from explicit parameters - introspection is completely disabled. The ``request`` and
       ``response`` parameters are required; ``output`` and ``workflow_output`` are optional
       (default to no outputs).

    Args:
        func: The function to decorate. Can be None when used with parameters.
        request: Explicit request type for this handler (the original_request parameter type).
            Required when using explicit mode. Supports union types and string forward references.
        response: Explicit response type for this handler (the response parameter type).
            Required when using explicit mode. Supports union types and string forward references.
        output: Explicit output type(s) that can be sent via ``ctx.send_message()``.
            Optional; defaults to no outputs if not specified.
        workflow_output: Explicit output type(s) that can be yielded via ``ctx.yield_output()``.
            Optional; defaults to no outputs if not specified.

    Returns:
        The decorated function with handler metadata.

    Example:
        .. code-block:: python

            # Mode 1: Introspection - types from annotations
            @handler
            async def run(self, message: int, context: WorkflowContext[str]) -> None:
                # Example of a handler that sends a request
                ...
                # Send a request with a `CustomRequest` payload and expect a `str` response.
                await context.request_info(CustomRequest(...), str)


            @response_handler
            async def handle_response(
                self,
                original_request: CustomRequest,
                response: str,
                context: WorkflowContext[str],
            ) -> None:
                # Example of a response handler for the above request
                ...


            # Mode 2: Explicit types - ALL types from decorator params
            # Note: No type annotations on function parameters when using explicit types
            @response_handler(request=CustomRequest, response=dict, output=int)
            async def handle_response(self, original_request, response, context):
                # Example of a response handler with explicit types
                await context.send_message(42)


            # Explicit with string forward references
            @response_handler(request="MyRequest", response="MyResponse")
            async def handle_response(self, original_request, response, context): ...
    """

    def decorator(
        func: Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]],
    ) -> Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]]:
        # Check if ANY explicit type parameter was provided - if so, use ONLY explicit params.
        # This is "all or nothing" - no mixing of explicit params with introspection.
        use_explicit_types = (
            request is not None or response is not None or output is not None or workflow_output is not None
        )

        if use_explicit_types:
            # Resolve string forward references using the function's globals
            resolved_request_type = resolve_type_annotation(request, func.__globals__) if request is not None else None
            resolved_response_type = (
                resolve_type_annotation(response, func.__globals__) if response is not None else None
            )
            resolved_output_type = resolve_type_annotation(output, func.__globals__) if output is not None else None
            resolved_workflow_output_type = (
                resolve_type_annotation(workflow_output, func.__globals__) if workflow_output is not None else None
            )

            # Validate signature structure but skip type extraction
            _validate_response_handler_signature(func, skip_annotations=True)

            # Validate required parameters
            if resolved_request_type is None:
                raise ValueError(
                    f"Response handler {func.__name__} with explicit type parameters must specify 'request' type"
                )
            if resolved_response_type is None:
                raise ValueError(
                    f"Response handler {func.__name__} with explicit type parameters must specify 'response' type"
                )

            final_request_type = resolved_request_type
            final_response_type = resolved_response_type
            final_output_types = normalize_type_to_list(resolved_output_type) if resolved_output_type else []
            final_workflow_output_types = (
                normalize_type_to_list(resolved_workflow_output_type) if resolved_workflow_output_type else []
            )
            # Get ctx_annotation for consistency
            ctx_annotation = (
                inspect.signature(func).parameters[list(inspect.signature(func).parameters.keys())[3]].annotation
            )
            if ctx_annotation == inspect.Parameter.empty:
                ctx_annotation = None
        else:
            # Use introspection - all types from annotations
            (
                inferred_request_type,
                inferred_response_type,
                ctx_annotation,
                final_output_types,
                final_workflow_output_types,
            ) = _validate_response_handler_signature(func)
            # In introspection mode, validation ensures these are not None (raises ValueError if missing)
            final_request_type = cast(type, inferred_request_type)
            final_response_type = cast(type, inferred_response_type)

        # Get signature for preservation
        sig = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(self: ExecutorT, original_request: Any, response_msg: Any, ctx: ContextT) -> Any:
            """Wrapper function to call the handler."""
            return await func(self, original_request, response_msg, ctx)

        # Preserve the original function signature for introspection during validation
        with contextlib.suppress(AttributeError, TypeError):
            wrapper.__signature__ = sig  # type: ignore[attr-defined]

        wrapper._response_handler_spec = {  # type: ignore
            "name": func.__name__,
            "request_type": final_request_type,
            "response_type": final_response_type,
            # Keep output_types and workflow_output_types in spec for validators
            "output_types": final_output_types,
            "workflow_output_types": final_workflow_output_types,
            "ctx_annotation": ctx_annotation,
        }

        return wrapper

    # If func is provided, this means @response_handler was used without parentheses
    if func is not None:
        return decorator(func)

    # Otherwise, return the wrapper for @response_handler(...) with parameters
    return decorator


# endregion: Handler Decorator

# region Response Handler Validation


def _validate_response_handler_signature(
    func: Callable[..., Any],
    *,
    skip_annotations: bool = False,
) -> tuple[type | None, type | None, Any, list[type[Any] | UnionType], list[type[Any] | UnionType]]:
    """Validate function signature for response handler functions.

    Args:
        func: The function to validate
        skip_annotations: If True, skip validation that request/response parameters have type
            annotations. Used when types are explicitly provided to the @response_handler decorator.

    Returns:
        Tuple of (request_type, response_type, ctx_annotation, output_types, workflow_output_types).
        request_type and response_type may be None if skip_annotations is True and no annotations exist.

    Raises:
        ValueError: If the function signature is invalid
    """
    signature = inspect.signature(func)
    params = list(signature.parameters.values())

    # Note that the original_request parameter must be the second parameter
    # such that we can wrap the handler with functools.partial to bind it
    # to the original request when registering the handler, while maintaining
    # the order of parameters as if the response handler is a normal handler.
    expected_counts = 4  # self, original_request, message, ctx
    param_description = "(self, original_request, response, ctx)"
    if len(params) != expected_counts:
        raise ValueError(
            f"Response handler {func.__name__} must have {param_description}. Got {len(params)} parameters."
        )

    # Check original_request parameter exists and has annotation (unless skipped)
    original_request_param = params[1]
    if not skip_annotations and original_request_param.annotation == inspect.Parameter.empty:
        raise ValueError(
            f"Response handler {func.__name__} must have a type annotation for the original_request parameter"
        )

    # Check response parameter has type annotation (unless skipped)
    response_param = params[2]
    if not skip_annotations and response_param.annotation == inspect.Parameter.empty:
        raise ValueError(f"Response handler {func.__name__} must have a type annotation for the response parameter")

    # Validate ctx parameter is WorkflowContext and extract type args (if annotated)
    ctx_param = params[3]
    if ctx_param.annotation != inspect.Parameter.empty:
        output_types, workflow_output_types = validate_workflow_context_annotation(
            ctx_param.annotation, f"parameter '{ctx_param.name}'", "Response handler"
        )
    else:
        output_types, workflow_output_types = [], []

    request_type = (
        original_request_param.annotation if original_request_param.annotation != inspect.Parameter.empty else None
    )
    response_type = response_param.annotation if response_param.annotation != inspect.Parameter.empty else None
    ctx_annotation = ctx_param.annotation if ctx_param.annotation != inspect.Parameter.empty else None

    return request_type, response_type, ctx_annotation, output_types, workflow_output_types


# endregion: Response Handler Validation
