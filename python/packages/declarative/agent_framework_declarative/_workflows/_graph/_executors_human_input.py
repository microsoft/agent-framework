# Copyright (c) Microsoft. All rights reserved.

"""Human-in-loop executors for declarative workflows.

These executors handle interactions that require human input, using the
RequestInfo pattern to pause the workflow and wait for responses.
"""

from dataclasses import dataclass
from typing import Any

from agent_framework._workflows import (
    WorkflowContext,
    handler,
)

from ._base import (
    ActionComplete,
    DeclarativeActionExecutor,
)


@dataclass
class QuestionChoice:
    """A choice option for a question."""

    value: str
    label: str | None = None


@dataclass
class HumanInputRequest:
    """Request for human input (triggers workflow pause)."""

    request_type: str
    message: str
    metadata: dict[str, Any]


class QuestionExecutor(DeclarativeActionExecutor):
    """Executor that asks the user a question and waits for a response.

    This uses the workflow's request_info mechanism to pause execution until
    the user provides an answer. The response is stored in workflow state.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete, HumanInputRequest],
    ) -> None:
        """Ask the question and wait for a response."""
        state = await self._ensure_state_initialized(ctx, trigger)

        question_text = self._action_def.get("text") or self._action_def.get("question", "")
        output_property = self._action_def.get("output", {}).get("property") or self._action_def.get(
            "property", "turn.answer"
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

        # Yield the request for human input
        # The workflow runtime will pause here and return the response when provided
        await ctx.yield_output(
            HumanInputRequest(
                request_type="question",
                message=str(evaluated_question),
                metadata={
                    "output_property": output_property,
                    "choices": choices_data,
                    "allow_free_text": allow_free_text,
                    "default_value": default_value,
                },
            )
        )

        # Note: In a full implementation, the workflow would pause here
        # and resume with the response. For now, we just use default.
        answer = default_value

        # Store the answer
        if output_property:
            await state.set(output_property, answer)

        await ctx.send_message(ActionComplete())


class ConfirmationExecutor(DeclarativeActionExecutor):
    """Executor that asks for a yes/no confirmation.

    This is a specialized version of Question that returns a boolean.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete, HumanInputRequest],
    ) -> None:
        """Ask for confirmation."""
        state = await self._ensure_state_initialized(ctx, trigger)

        message = self._action_def.get("text") or self._action_def.get("message", "")
        output_property = self._action_def.get("output", {}).get("property") or self._action_def.get(
            "property", "turn.confirmed"
        )
        yes_label = self._action_def.get("yesLabel", "Yes")
        no_label = self._action_def.get("noLabel", "No")
        default_value = self._action_def.get("defaultValue", False)

        # Evaluate the message if it's an expression
        evaluated_message = await state.eval_if_expression(message)

        # Yield the request for confirmation
        await ctx.yield_output(
            HumanInputRequest(
                request_type="confirmation",
                message=str(evaluated_message),
                metadata={
                    "output_property": output_property,
                    "yes_label": yes_label,
                    "no_label": no_label,
                    "default_value": default_value,
                },
            )
        )

        # Store the default value
        if output_property:
            await state.set(output_property, default_value)

        await ctx.send_message(ActionComplete())


class WaitForInputExecutor(DeclarativeActionExecutor):
    """Executor that waits for user input during a conversation turn.

    This is used when the workflow needs to pause and wait for the next
    user message in a conversational flow.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete, HumanInputRequest | str],
    ) -> None:
        """Wait for user input."""
        state = await self._ensure_state_initialized(ctx, trigger)

        prompt = self._action_def.get("prompt")
        output_property = self._action_def.get("output", {}).get("property") or self._action_def.get(
            "property", "turn.input"
        )
        timeout_seconds = self._action_def.get("timeout")

        # Emit prompt if specified
        if prompt:
            evaluated_prompt = await state.eval_if_expression(prompt)
            await ctx.yield_output(str(evaluated_prompt))

        # Yield the request for input
        await ctx.yield_output(
            HumanInputRequest(
                request_type="user_input",
                message=str(prompt) if prompt else "Waiting for input...",
                metadata={
                    "output_property": output_property,
                    "timeout_seconds": timeout_seconds,
                },
            )
        )

        # Store empty input (will be populated when workflow resumes)
        if output_property:
            await state.set(output_property, "")

        await ctx.send_message(ActionComplete())


class RequestExternalInputExecutor(DeclarativeActionExecutor):
    """Executor that requests external input/approval.

    This is used for more complex external integrations beyond simple questions,
    such as approval workflows, document uploads, or external system integrations.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete, HumanInputRequest],
    ) -> None:
        """Request external input."""
        state = await self._ensure_state_initialized(ctx, trigger)

        request_type = self._action_def.get("requestType", "external")
        message = self._action_def.get("message", "")
        output_property = self._action_def.get("output", {}).get("property") or self._action_def.get(
            "property", "turn.externalInput"
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

        # Yield the request
        await ctx.yield_output(
            HumanInputRequest(
                request_type=request_type,
                message=str(evaluated_message),
                metadata=request_metadata,
            )
        )

        # Store None (will be populated when workflow resumes)
        if output_property:
            await state.set(output_property, None)

        await ctx.send_message(ActionComplete())


# Mapping of human input action kinds to executor classes
HUMAN_INPUT_EXECUTORS: dict[str, type[DeclarativeActionExecutor]] = {
    "Question": QuestionExecutor,
    "Confirmation": ConfirmationExecutor,
    "WaitForInput": WaitForInputExecutor,
    "RequestExternalInput": RequestExternalInputExecutor,
}
