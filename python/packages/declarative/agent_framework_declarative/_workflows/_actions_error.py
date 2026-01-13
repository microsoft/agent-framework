# Copyright (c) Microsoft. All rights reserved.

"""Error handling action handlers for declarative workflows.

This module implements handlers for:
- ThrowException: Raise an error that can be caught by TryCatch
- TryCatch: Try-catch-finally error handling
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from agent_framework import get_logger

from ._handlers import (
    ActionContext,
    WorkflowEvent,
    action_handler,
)

logger = get_logger("agent_framework.declarative.workflows.actions")


class WorkflowActionError(Exception):
    """Exception raised by ThrowException action."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


@dataclass
class ErrorEvent(WorkflowEvent):
    """Event emitted when an error occurs."""

    message: str
    """The error message."""

    code: str | None = None
    """Optional error code."""

    source_action: str | None = None
    """The action that caused the error."""


@action_handler("ThrowException")
async def handle_throw_exception(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Raise an exception that can be caught by TryCatch.

    Action schema:
        kind: ThrowException
        message: =expression or literal error message
        code: ERROR_CODE  # optional error code
    """
    message_expr = ctx.action.get("message", "An error occurred")
    code = ctx.action.get("code")

    # Evaluate the message if it's an expression
    message = ctx.state.eval_if_expression(message_expr)

    logger.debug(f"ThrowException: {message} (code={code})")

    raise WorkflowActionError(str(message), code)

    # This yield is never reached but makes it a generator
    yield ErrorEvent(message=str(message), code=code)  # type: ignore[unreachable]


@action_handler("TryCatch")
async def handle_try_catch(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:
    """Try-catch-finally error handling.

    Action schema:
        kind: TryCatch
        try:
          - kind: ...  # actions to try
        catch:
          - kind: ...  # actions to execute on error (optional)
        finally:
          - kind: ...  # actions to always execute (optional)

    In the catch block, the following variables are available:
        Local.error.message: The error message
        Local.error.code: The error code (if provided)
        Local.error.type: The error type name
    """
    try_actions = ctx.action.get("try", [])
    catch_actions = ctx.action.get("catch", [])
    finally_actions = ctx.action.get("finally", [])

    error_occurred = False
    error_info = None

    # Execute try block
    try:
        async for event in ctx.execute_actions(try_actions, ctx.state):
            yield event
    except WorkflowActionError as e:
        error_occurred = True
        error_info = {
            "message": str(e),
            "code": e.code,
            "type": "WorkflowActionError",
        }
        logger.debug(f"TryCatch: caught WorkflowActionError: {e}")
    except Exception as e:
        error_occurred = True
        error_info = {
            "message": str(e),
            "code": None,
            "type": type(e).__name__,
        }
        logger.debug(f"TryCatch: caught {type(e).__name__}: {e}")

    # Execute catch block if error occurred
    if error_occurred and catch_actions:
        # Set error info in Local scope
        ctx.state.set("Local.error", error_info)

        try:
            async for event in ctx.execute_actions(catch_actions, ctx.state):
                yield event
        finally:
            # Clean up error info (but don't interfere with finally block)
            pass

    # Execute finally block
    if finally_actions:
        async for event in ctx.execute_actions(finally_actions, ctx.state):
            yield event
