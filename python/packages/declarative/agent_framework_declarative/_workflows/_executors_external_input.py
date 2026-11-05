# Copyright (c) Microsoft. All rights reserved.

"""External input executors for declarative workflows.

These executors handle interactions that require external input (user questions
and external integrations), using the request_info pattern to pause the workflow
and wait for responses.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, cast

from agent_framework import (
    WorkflowContext,
    handler,
    response_handler,
)

from ._declarative_base import (
    ActionComplete,
    DeclarativeActionExecutor,
)


def _get_prompt_text(action_def: dict[str, Any], primary_key: str, fallback_key: str) -> Any:
    """Return the prompt text from an action definition.

    Accepts a nested ``{primary_key: {"text": ...}}`` mapping, a bare
    string under ``primary_key``, or a top-level ``fallback_key`` value.
    """
    match action_def.get(primary_key):
        case {"text": text}:
            return text
        case str() as text:
            return text
        case _:
            return action_def.get(fallback_key, "")


def _get_output_path(action_def: dict[str, Any], default: str) -> str:
    """Return the state path where the action result should be written.

    Looks at ``variable``, then ``output.property``, then top-level
    ``property``, falling back to ``default``.
    """
    output = action_def.get("output")
    nested = cast(dict[str, Any], output).get("property") if isinstance(output, dict) else None
    return action_def.get("variable") or nested or action_def.get("property") or default


@dataclass
class ExternalInputRequest:
    """Request for external input (triggers workflow pause).

    Aligns with .NET ExternalInputRequest pattern. Used by Question and
    RequestExternalInput executors to signal that user input is needed.
    The workflow will pause via request_info and wait for an ExternalInputResponse.

    Attributes:
        request_id: Unique identifier for this request.
        message: The prompt or question to display to the user.
        request_type: A free-form discriminator describing the kind of input
            being requested. ``QuestionExecutor`` emits ``"question"`` and
            ``RequestExternalInputExecutor`` defaults to ``"external"``; callers
            may supply any other string via the ``requestType`` field on a
            ``RequestExternalInput`` action (e.g. ``"approval"``) and it is
            propagated unchanged.
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

        question_text = _get_prompt_text(self._action_def, primary_key="question", fallback_key="text")
        output_property = _get_output_path(self._action_def, default="Local.answer")
        default_value = self._action_def.get("default", self._action_def.get("defaultValue"))
        choices = self._action_def.get("choices", [])
        allow_free_text = self._action_def.get("allowFreeText", True)

        evaluated_question = state.eval_if_expression(question_text)

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
        ctx.state.set("_question_output_property", output_property)
        ctx.state.set("_question_default_value", default_value)

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
        state = self._get_state(ctx.state)

        output_property = original_request.metadata.get("output_property", "Local.answer")
        answer = response.value if response.value is not None else response.user_input

        if output_property:
            state.set(output_property, answer)

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

        message = _get_prompt_text(self._action_def, primary_key="prompt", fallback_key="message")
        output_property = _get_output_path(self._action_def, default="Local.externalInput")
        default_value = self._action_def.get("default")

        request_type = self._action_def.get("requestType", "external")
        timeout_seconds = self._action_def.get("timeout")
        required_fields = self._action_def.get("requiredFields", [])
        metadata = self._action_def.get("metadata", {})

        evaluated_message = state.eval_if_expression(message)

        # Build request metadata
        request_metadata: dict[str, Any] = {
            **metadata,
            "output_property": output_property,
            "required_fields": required_fields,
            "default_value": default_value,
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
        state = self._get_state(ctx.state)

        output_property = original_request.metadata.get("output_property", "Local.externalInput")

        # Store the response value or user_input
        result = response.value if response.value is not None else response.user_input
        if output_property:
            state.set(output_property, result)

        await ctx.send_message(ActionComplete())


# Mapping of external input action kinds to executor classes
EXTERNAL_INPUT_EXECUTORS: dict[str, type[DeclarativeActionExecutor]] = {
    "Question": QuestionExecutor,
    "RequestExternalInput": RequestExternalInputExecutor,
}
