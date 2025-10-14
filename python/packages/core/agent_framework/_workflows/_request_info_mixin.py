# Copyright (c) Microsoft. All rights reserved.

import contextlib
import functools
import inspect
import logging
from builtins import type as builtin_type
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from ._workflow_context import WorkflowContext, validate_function_signature

if TYPE_CHECKING:
    from ._executor import Executor


logger = logging.getLogger(__name__)


class RequestInfoMixin:
    """Mixin providing common functionality for request info handling."""

    _PENDING_SHARED_STATE_KEY: ClassVar[str] = "_af_pending_request_info"

    def _discover_response_handlers(self) -> None:
        """Discover and register response handlers defined in the class."""
        # Initialize handler storage if not already present
        if not hasattr(self, "_response_handlers"):
            self._response_handlers: dict[
                builtin_type[Any], Callable[[Any, WorkflowContext[Any, Any]], Awaitable[None]]
            ] = {}
        if not hasattr(self, "_response_handler_specs"):
            self._response_handler_specs: list[dict[str, Any]] = []

        for attr_name in dir(self.__class__):
            try:
                attr = getattr(self.__class__, attr_name)
                if callable(attr) and hasattr(attr, "_response_handler_spec"):
                    handler_spec = attr._response_handler_spec  # type: ignore
                    message_type = handler_spec["message_type"]

                    if self._response_handlers.get(message_type):
                        raise ValueError(
                            f"Duplicate response handler for message type {message_type} in {self.__class__.__name__}"
                        )

                    self._response_handlers[message_type] = getattr(self, attr_name)
                    self._response_handler_specs.append({
                        "name": handler_spec["name"],
                        "message_type": message_type,
                        "output_types": handler_spec.get("output_types", []),
                        "workflow_output_types": handler_spec.get("workflow_output_types", []),
                        "ctx_annotation": handler_spec.get("ctx_annotation"),
                        "source": "class_method",  # Distinguish from instance handlers if needed
                    })
            except AttributeError:
                continue  # Skip non-callable attributes or those without handler spec


ExecutorT = TypeVar("ExecutorT", bound="Executor")
ContextT = TypeVar("ContextT", bound="WorkflowContext[Any, Any]")


def response_handler(
    func: Callable[[ExecutorT, Any, ContextT], Awaitable[None]],
) -> Callable[[ExecutorT, Any, ContextT], Awaitable[None]]:
    """Decorator to register a handler to handle responses for a request.

    Args:
        func: The function to decorate.

    Returns:
        The decorated function with handler metadata.

    Example:
        @response_handler
        async def handle_response(self, response: str, context: WorkflowContext[str]) -> None:
            ...

        @response_handler
        async def handle_response(self, response: dict, context: WorkflowContext[int]) -> None:
            ...
    """

    def decorator(
        func: Callable[[ExecutorT, Any, ContextT], Awaitable[None]],
    ) -> Callable[[ExecutorT, Any, ContextT], Awaitable[None]]:
        message_type, ctx_annotation, inferred_output_types, inferred_workflow_output_types = (
            validate_function_signature(func, "Handler method")
        )

        # Get signature for preservation
        sig = inspect.signature(func)

        @functools.wraps(func)
        async def wrapper(self: ExecutorT, message: Any, ctx: ContextT) -> Any:
            """Wrapper function to call the handler."""
            return await func(self, message, ctx)

        # Preserve the original function signature for introspection during validation
        with contextlib.suppress(AttributeError, TypeError):
            wrapper.__signature__ = sig  # type: ignore[attr-defined]

        wrapper._response_handler_spec = {  # type: ignore
            "name": func.__name__,
            "message_type": message_type,
            # Keep output_types and workflow_output_types in spec for validators
            "output_types": inferred_output_types,
            "workflow_output_types": inferred_workflow_output_types,
            "ctx_annotation": ctx_annotation,
        }

        return wrapper

    return decorator(func)
