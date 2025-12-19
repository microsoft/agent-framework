# Copyright (c) Microsoft. All rights reserved.

"""Human-in-the-loop action handlers for declarative workflows.

This module implements handlers for human input patterns:
- Question: Request human input with validation
- RequestExternalInput: Request input from external system
- ExternalLoop processing: Loop while waiting for external input
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from agent_framework import get_logger

from ._handlers import (
    ActionContext,
    WorkflowEvent,
    action_handler,
)

if TYPE_CHECKING:
    from ._state import WorkflowState

logger = get_logger("agent_framework.declarative.workflows.human_input")


@dataclass
class QuestionRequest(WorkflowEvent):
    """Event emitted when the workflow needs user input via Question action.

    When this event is yielded, the workflow execution should pause
    and wait for user input to be provided via workflow.send_response().

    This is used by the Question, RequestExternalInput, and WaitForInput
    action handlers in the non-graph workflow path.
    """

    request_id: str
    """Unique identifier for this request."""

    prompt: str | None
    """The prompt/question to display to the user."""

    variable: str
    """The variable where the response should be stored."""

    validation: dict[str, Any] | None = None
    """Optional validation rules for the input."""

    choices: list[str] | None = None
    """Optional list of valid choices."""

    default_value: Any = None
    """Default value if no input is provided."""


@dataclass
class ExternalLoopEvent(WorkflowEvent):
    """Event emitted when entering an external input loop.

    This event signals that the action is waiting for external input
    in a loop pattern (e.g., input.externalLoop.when condition).
    """

    action_id: str
    """The ID of the action that requires external input."""

    iteration: int
    """The current iteration number (0-based)."""

    condition_expression: str
    """The PowerFx condition that must become false to exit the loop."""


@action_handler("Question")
async def handle_question(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Handle Question action - request human input with optional validation.

    Action schema:
        kind: Question
        id: ask_name
        variable: Local.userName
        prompt: What is your name?
        validation:
          required: true
          minLength: 1
          maxLength: 100
        choices:        # optional - present as multiple choice
          - Option A
          - Option B
        default: Option A  # optional default value

    The handler emits a QuestionRequest and expects the workflow runner
    to capture and provide the response before continuing.
    """
    question_id = ctx.action.get("id", "question")
    variable = ctx.action.get("variable")
    prompt = ctx.action.get("prompt")
    question: dict[str, Any] | Any = ctx.action.get("question", {})
    validation = ctx.action.get("validation", {})
    choices = ctx.action.get("choices")
    default_value = ctx.action.get("default")

    if not variable:
        logger.warning("Question action missing 'variable' property")
        return

    # Evaluate prompt if it's an expression (support both 'prompt' and 'question.text')
    prompt_text: Any | None = None
    if isinstance(question, dict):
        question_dict: dict[str, Any] = cast(dict[str, Any], question)
        prompt_text = prompt or question_dict.get("text")
    else:
        prompt_text = prompt
    evaluated_prompt = ctx.state.eval_if_expression(prompt_text) if prompt_text else None

    # Evaluate choices if they're expressions
    evaluated_choices = None
    if choices:
        evaluated_choices = [ctx.state.eval_if_expression(c) if isinstance(c, str) else c for c in choices]

    logger.debug(f"Question: requesting input for {variable}")

    # Emit the request event
    yield QuestionRequest(
        request_id=question_id,
        prompt=str(evaluated_prompt) if evaluated_prompt else None,
        variable=variable,
        validation=validation,
        choices=evaluated_choices,
        default_value=default_value,
    )

    # Apply default value if specified (for non-interactive scenarios)
    if default_value is not None:
        evaluated_default = ctx.state.eval_if_expression(default_value)
        ctx.state.set(variable, evaluated_default)


@action_handler("RequestExternalInput")
async def handle_request_external_input(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Handle RequestExternalInput action - request input from external system.

    Action schema:
        kind: RequestExternalInput
        id: get_approval
        variable: Local.approval
        prompt: Please approve or reject the request
        timeout: 300  # seconds
        default: "No feedback provided"  # optional default value
        output:
          response: Local.approvalResponse
          timestamp: Local.approvalTime

    Similar to Question but designed for external system integration
    rather than direct human input.
    """
    request_id = ctx.action.get("id", "external_input")
    variable = ctx.action.get("variable")
    prompt = ctx.action.get("prompt")
    timeout = ctx.action.get("timeout")  # seconds
    default_value = ctx.action.get("default")
    _output = ctx.action.get("output", {})  # Reserved for future use

    if not variable:
        logger.warning("RequestExternalInput action missing 'variable' property")
        return

    # Extract prompt text (support both 'prompt' string and 'prompt.text' object)
    prompt_text: Any | None = None
    if isinstance(prompt, dict):
        prompt_dict: dict[str, Any] = cast(dict[str, Any], prompt)
        prompt_text = prompt_dict.get("text")
    else:
        prompt_text = prompt

    # Evaluate prompt if it's an expression
    evaluated_prompt = ctx.state.eval_if_expression(prompt_text) if prompt_text else None

    logger.debug(f"RequestExternalInput: requesting input for {variable}")

    # Emit the request event
    yield QuestionRequest(
        request_id=request_id,
        prompt=str(evaluated_prompt) if evaluated_prompt else None,
        variable=variable,
        validation={"timeout": timeout} if timeout else None,
        default_value=default_value,
    )

    # Apply default value if specified (for non-interactive scenarios)
    if default_value is not None:
        evaluated_default = ctx.state.eval_if_expression(default_value)
        ctx.state.set(variable, evaluated_default)


@action_handler("WaitForInput")
async def handle_wait_for_input(ctx: ActionContext) -> AsyncGenerator[WorkflowEvent, None]:  # noqa: RUF029
    """Handle WaitForInput action - pause and wait for external input.

    Action schema:
        kind: WaitForInput
        id: wait_for_response
        variable: Local.response
        message: Waiting for user response...

    This is a simpler form of RequestExternalInput that just pauses
    execution until input is provided.
    """
    wait_id = ctx.action.get("id", "wait")
    variable = ctx.action.get("variable")
    message = ctx.action.get("message")

    if not variable:
        logger.warning("WaitForInput action missing 'variable' property")
        return

    # Evaluate message if it's an expression
    evaluated_message = ctx.state.eval_if_expression(message) if message else None

    logger.debug(f"WaitForInput: waiting for {variable}")

    yield QuestionRequest(
        request_id=wait_id,
        prompt=str(evaluated_message) if evaluated_message else None,
        variable=variable,
    )


def process_external_loop(
    input_config: dict[str, Any],
    state: "WorkflowState",
) -> tuple[bool, str | None]:
    """Process the externalLoop.when pattern from action input.

    This function evaluates the externalLoop.when condition to determine
    if the action should continue looping for external input.

    Args:
        input_config: The input configuration containing externalLoop
        state: The workflow state for expression evaluation

    Returns:
        Tuple of (should_continue_loop, condition_expression)
        - should_continue_loop: True if the loop should continue
        - condition_expression: The original condition expression for diagnostics
    """
    external_loop = input_config.get("externalLoop", {})
    when_condition = external_loop.get("when")

    if not when_condition:
        return (False, None)

    # Evaluate the condition
    result = state.eval(when_condition)

    # The loop continues while the condition is True
    should_continue = bool(result) if result is not None else False

    logger.debug(f"ExternalLoop condition '{when_condition[:50]}' evaluated to {should_continue}")

    return (should_continue, when_condition)


def validate_input_response(
    value: Any,
    validation: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Validate input response against validation rules.

    Args:
        value: The input value to validate
        validation: Validation rules from the Question action

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not validation:
        return (True, None)

    # Check required
    if validation.get("required") and (value is None or value == ""):
        return (False, "This field is required")

    if value is None:
        return (True, None)

    # Check string length
    if isinstance(value, str):
        min_length = validation.get("minLength")
        max_length = validation.get("maxLength")

        if min_length is not None and len(value) < min_length:
            return (False, f"Minimum length is {min_length}")

        if max_length is not None and len(value) > max_length:
            return (False, f"Maximum length is {max_length}")

    # Check numeric range
    if isinstance(value, (int, float)):
        min_value = validation.get("min")
        max_value = validation.get("max")

        if min_value is not None and value < min_value:
            return (False, f"Minimum value is {min_value}")

        if max_value is not None and value > max_value:
            return (False, f"Maximum value is {max_value}")

    # Check pattern (regex)
    pattern = validation.get("pattern")
    if pattern and isinstance(value, str):
        import re

        if not re.match(pattern, value):
            return (False, f"Value does not match pattern: {pattern}")

    return (True, None)
