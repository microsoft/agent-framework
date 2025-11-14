# Copyright (c) Microsoft. All rights reserved.

import contextlib
import functools
import inspect
import logging
from builtins import type as builtin_type
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from ._typing_utils import is_instance_of, is_type_compatible
from ._workflow_context import WorkflowContext, validate_workflow_context_annotation

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
                    self._response_handler_specs.append({
                        "name": handler_spec["name"],
                        "request_type": request_type,
                        "response_type": response_type,
                        "output_types": handler_spec.get("output_types", []),
                        "workflow_output_types": handler_spec.get("workflow_output_types", []),
                        "ctx_annotation": handler_spec.get("ctx_annotation"),
                        "source": "class_method",  # Distinguish from instance handlers if needed
                    })
            except AttributeError:
                continue  # Skip non-callable attributes or those without handler spec

        # A request sent via `request_info` must be handled by a response handler inside the same executor.
        # It is safe to assume that an executor is request-response capable if it has at least one response
        # handler, and that the executor could send a request.
        self.is_request_response_capable = bool(self._response_handlers)


ExecutorT = TypeVar("ExecutorT", bound="Executor")
ContextT = TypeVar("ContextT", bound="WorkflowContext[Any, Any]")

# region Handler Decorator


def response_handler(
    func: Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]],
) -> Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]]:
    """Decorator to register a handler to handle responses for a request.

    Args:
        func: The function to decorate.

    Returns:
        The decorated function with handler metadata.

    Example:
        .. code-block:: python

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


            @response_handler
            async def handle_response(
                self,
                original_request: CustomRequest,
                response: dict,
                context: WorkflowContext[int],
            ) -> None:
                # Example of a response handler for a request expecting a dict response
                ...
    """

    def decorator(
        func: Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]],
    ) -> Callable[[ExecutorT, Any, Any, ContextT], Awaitable[None]]:
        request_type, response_type, ctx_annotation, inferred_output_types, inferred_workflow_output_types = (
            _validate_response_handler_signature(func)
        )

        # Get signature for preservation
        sig = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(self: ExecutorT, original_request: Any, response: Any, ctx: ContextT) -> Any:
            """Wrapper function to call the handler."""
            return await func(self, original_request, response, ctx)

        # Preserve the original function signature for introspection during validation
        with contextlib.suppress(AttributeError, TypeError):
            wrapper.__signature__ = sig  # type: ignore[attr-defined]

        wrapper._response_handler_spec = {  # type: ignore
            "name": func.__name__,
            "request_type": request_type,
            "response_type": response_type,
            # Keep output_types and workflow_output_types in spec for validators
            "output_types": inferred_output_types,
            "workflow_output_types": inferred_workflow_output_types,
            "ctx_annotation": ctx_annotation,
        }

        return wrapper

    return decorator(func)


# endregion: Handler Decorator

# region Response Handler Validation


def _validate_response_handler_signature(
    func: Callable[..., Any],
) -> tuple[type, type, Any, list[type[Any]], list[type[Any]]]:
    """Validate function signature for executor functions.

    Args:
        func: The function to validate

    Returns:
        Tuple of (request_type, response_type, ctx_annotation, output_types, workflow_output_types)

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
    param_description = "(self, original_request: TRequest, message: TResponse, ctx: WorkflowContext[U, V])"
    if len(params) != expected_counts:
        raise ValueError(
            f"Response handler {func.__name__} must have {param_description}. Got {len(params)} parameters."
        )

    # Check original_request parameter exists
    original_request_param = params[1]
    if original_request_param.annotation == inspect.Parameter.empty:
        raise ValueError(
            f"Response handler {func.__name__} must have a type annotation for the original_request parameter"
        )

    # Check response parameter has type annotation
    response_param = params[2]
    if response_param.annotation == inspect.Parameter.empty:
        raise ValueError(f"Response handler {func.__name__} must have a type annotation for the message parameter")

    # Validate ctx parameter is WorkflowContext and extract type args
    ctx_param = params[3]
    output_types, workflow_output_types = validate_workflow_context_annotation(
        ctx_param.annotation, f"parameter '{ctx_param.name}'", "Response handler"
    )

    request_type = original_request_param.annotation
    response_type = response_param.annotation
    ctx_annotation = ctx_param.annotation

    return request_type, response_type, ctx_annotation, output_types, workflow_output_types


# endregion: Response Handler Validation
