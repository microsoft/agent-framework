# Copyright (c) Microsoft. All rights reserved.

"""External input executors for declarative workflows.

These executors handle interactions that require external input (user questions,
confirmations, etc.), using the request_info pattern to pause the workflow and
wait for responses.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_framework._workflows import (
    WorkflowContext,
    handler,
    response_handler,
)

from ._declarative_base import (
    ActionComplete,
    DeclarativeActionExecutor,
)


@dataclass
class ExternalInputRequest:
    """Request for external input (triggers workflow pause).

    Aligns with .NET ExternalInputRequest pattern. Used by Question, Confirmation,
    WaitForInput, and RequestExternalInput executors to signal that user input is
    needed. The workflow will pause via request_info and wait for an ExternalInputResponse.

    Attributes:
        request_id: Unique identifier for this request.
        message: The prompt or question to display to the user.
        request_type: Type of input requested (question, confirmation, user_input, external).
        metadata: Additional context (choices, output_property, timeout, etc.).
    """

    request_id: str
    message: str
    request_type: str = "external"
    metadata: dict[str, Any] = field(default_factory=dict)  # type: ignore


@dataclass
class ExternalInputResponse:
    """Response to an ExternalInputRequest.

    Provided by the caller to resume workflow execution with user input.

    Attributes:
        user_input: The user's text response.
        value: Optional typed value (e.g., bool for confirmations, selected choice).
    """

    user_input: str
    value: Any = None


class QuestionExecutor(DeclarativeActionExecutor):
    """Executor that asks the user a question and waits for a response.

    Uses the request_info pattern to pause execution until the user provides an answer.
    The response is stored in workflow state at the configured output property.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Ask the question and wait for a response."""
        state = await self._ensure_state_initialized(ctx, trigger)

        question_text = self._action_def.get("text") or self._action_def.get("question", "")
        output_property = self._action_def.get("output", {}).get("property") or self._action_def.get(
            "property", "Local.answer"
        )
        choices = self._action_def.get("choices", [])
        default_value = self._action_def.get("defaultValue")
        allow_free_text = self._action_def.get("allowFreeText", True)

        # Evaluate the question text if it's an expression
        evaluated_question = await state.eval_if_expression(question_text)

        # Build choices metadata
        choices_data: list[dict[str, str]] | None = None
        if choices:
            choices_data = []
            for c in choices:
                if isinstance(c, dict):
                    c_dict: dict[str, Any] = dict(c)  # type: ignore[arg-type]
                    choices_data.append({
                        "value": c_dict.get("value", ""),
                        "label": c_dict.get("label") or c_dict.get("value", ""),
                    })
                else:
                    choices_data.append({"value": str(c), "label": str(c)})

        # Store output property in shared state for response handler
        await ctx.shared_state.set("_question_output_property", output_property)
        await ctx.shared_state.set("_question_default_value", default_value)

        # Request external input - workflow pauses here
        await ctx.request_info(
            ExternalInputRequest(
                request_id=str(uuid.uuid4()),
                message=str(evaluated_question),
                request_type="question",
                metadata={
                    "output_property": output_property,
                    "choices": choices_data,
                    "allow_free_text": allow_free_text,
                    "default_value": default_value,
                },
            ),
            ExternalInputResponse,
        )

    @response_handler
    async def handle_response(
        self,
        original_request: ExternalInputRequest,
        response: ExternalInputResponse,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the user's response to the question."""
        state = self._get_state(ctx.shared_state)

        output_property = original_request.metadata.get("output_property", "Local.answer")
        answer = response.value if response.value is not None else response.user_input

        if output_property:
            await state.set(output_property, answer)

        await ctx.send_message(ActionComplete())


class ConfirmationExecutor(DeclarativeActionExecutor):
    """Executor that asks for a yes/no confirmation.

    A specialized version of Question that expects a boolean response.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Ask for confirmation."""
        state = await self._ensure_state_initialized(ctx, trigger)

        message = self._action_def.get("text") or self._action_def.get("message", "")
        output_property = self._action_def.get("output", {}).get("property") or self._action_def.get(
            "property", "Local.confirmed"
        )
        yes_label = self._action_def.get("yesLabel", "Yes")
        no_label = self._action_def.get("noLabel", "No")
        default_value = self._action_def.get("defaultValue", False)

        # Evaluate the message if it's an expression
        evaluated_message = await state.eval_if_expression(message)

        # Request confirmation - workflow pauses here
        await ctx.request_info(
            ExternalInputRequest(
                request_id=str(uuid.uuid4()),
                message=str(evaluated_message),
                request_type="confirmation",
                metadata={
                    "output_property": output_property,
                    "yes_label": yes_label,
                    "no_label": no_label,
                    "default_value": default_value,
                },
            ),
            ExternalInputResponse,
        )

    @response_handler
    async def handle_response(
        self,
        original_request: ExternalInputRequest,
        response: ExternalInputResponse,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the user's confirmation response."""
        state = self._get_state(ctx.shared_state)

        output_property = original_request.metadata.get("output_property", "Local.confirmed")

        # Convert response to boolean
        if response.value is not None:
            confirmed = bool(response.value)
        else:
            # Interpret common affirmative responses
            user_input_lower = response.user_input.lower().strip()
            confirmed = user_input_lower in ("yes", "y", "true", "1", "confirm", "ok")

        if output_property:
            await state.set(output_property, confirmed)

        await ctx.send_message(ActionComplete())


class WaitForInputExecutor(DeclarativeActionExecutor):
    """Executor that waits for user input during a conversation.

    Used when the workflow needs to pause and wait for the next user message
    in a conversational flow.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete, str],
    ) -> None:
        """Wait for user input."""
        state = await self._ensure_state_initialized(ctx, trigger)

        prompt = self._action_def.get("prompt")
        output_property = self._action_def.get("output", {}).get("property") or self._action_def.get(
            "property", "Local.input"
        )
        timeout_seconds = self._action_def.get("timeout")

        # Emit prompt if specified
        if prompt:
            evaluated_prompt = await state.eval_if_expression(prompt)
            await ctx.yield_output(str(evaluated_prompt))

        # Request user input - workflow pauses here
        await ctx.request_info(
            ExternalInputRequest(
                request_id=str(uuid.uuid4()),
                message=str(prompt) if prompt else "Waiting for input...",
                request_type="user_input",
                metadata={
                    "output_property": output_property,
                    "timeout_seconds": timeout_seconds,
                },
            ),
            ExternalInputResponse,
        )

    @response_handler
    async def handle_response(
        self,
        original_request: ExternalInputRequest,
        response: ExternalInputResponse,
        ctx: WorkflowContext[ActionComplete, str],
    ) -> None:
        """Handle the user's input."""
        state = self._get_state(ctx.shared_state)

        output_property = original_request.metadata.get("output_property", "Local.input")

        if output_property:
            await state.set(output_property, response.user_input)

        await ctx.send_message(ActionComplete())


class RequestExternalInputExecutor(DeclarativeActionExecutor):
    """Executor that requests external input/approval.

    Used for complex external integrations beyond simple questions,
    such as approval workflows, document uploads, or external system integrations.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Request external input."""
        state = await self._ensure_state_initialized(ctx, trigger)

        request_type = self._action_def.get("requestType", "external")
        message = self._action_def.get("message", "")
        output_property = self._action_def.get("output", {}).get("property") or self._action_def.get(
            "property", "Local.externalInput"
        )
        timeout_seconds = self._action_def.get("timeout")
        required_fields = self._action_def.get("requiredFields", [])
        metadata = self._action_def.get("metadata", {})

        # Evaluate the message if it's an expression
        evaluated_message = await state.eval_if_expression(message)

        # Build request metadata
        request_metadata: dict[str, Any] = {
            **metadata,
            "output_property": output_property,
            "required_fields": required_fields,
        }

        if timeout_seconds:
            request_metadata["timeout_seconds"] = timeout_seconds

        # Request external input - workflow pauses here
        await ctx.request_info(
            ExternalInputRequest(
                request_id=str(uuid.uuid4()),
                message=str(evaluated_message),
                request_type=request_type,
                metadata=request_metadata,
            ),
            ExternalInputResponse,
        )

    @response_handler
    async def handle_response(
        self,
        original_request: ExternalInputRequest,
        response: ExternalInputResponse,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the external input response."""
        state = self._get_state(ctx.shared_state)

        output_property = original_request.metadata.get("output_property", "Local.externalInput")

        # Store the response value or user_input
        result = response.value if response.value is not None else response.user_input
        if output_property:
            await state.set(output_property, result)

        await ctx.send_message(ActionComplete())


# Mapping of external input action kinds to executor classes
EXTERNAL_INPUT_EXECUTORS: dict[str, type[DeclarativeActionExecutor]] = {
    "Question": QuestionExecutor,
    "Confirmation": ConfirmationExecutor,
    "WaitForInput": WaitForInputExecutor,
    "RequestExternalInput": RequestExternalInputExecutor,
}
