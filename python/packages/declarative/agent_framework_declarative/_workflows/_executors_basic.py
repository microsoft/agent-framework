# Copyright (c) Microsoft. All rights reserved.

"""Basic action executors for the graph-based declarative workflow system.

These executors handle simple actions like SetValue, SendActivity, etc.
Each action becomes a node in the workflow graph.
"""

from typing import Any

from agent_framework._workflows import (
    WorkflowContext,
    handler,
)

from ._declarative_base import (
    ActionComplete,
    DeclarativeActionExecutor,
)


def _get_variable_path(action_def: dict[str, Any], key: str = "variable") -> str | None:
    """Extract variable path from action definition.

    Supports .NET style (variable: Local.VarName) and nested object style (variable: {path: ...}).
    """
    variable = action_def.get(key)
    if isinstance(variable, str):
        return variable
    if isinstance(variable, dict):
        return variable.get("path")
    return action_def.get("path")


class SetValueExecutor(DeclarativeActionExecutor):
    """Executor for the SetValue action.

    Sets a value in the workflow state at a specified path.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the SetValue action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        path = self._action_def.get("path")
        value = self._action_def.get("value")

        if path:
            # Evaluate value if it's an expression
            evaluated_value = await state.eval_if_expression(value)
            await state.set(path, evaluated_value)

        await ctx.send_message(ActionComplete())


class SetVariableExecutor(DeclarativeActionExecutor):
    """Executor for the SetVariable action (.NET style naming)."""

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the SetVariable action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        path = _get_variable_path(self._action_def)
        value = self._action_def.get("value")

        if path:
            evaluated_value = await state.eval_if_expression(value)
            await state.set(path, evaluated_value)

        await ctx.send_message(ActionComplete())


class SetTextVariableExecutor(DeclarativeActionExecutor):
    """Executor for the SetTextVariable action."""

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the SetTextVariable action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        path = _get_variable_path(self._action_def)
        text = self._action_def.get("text", "")

        if path:
            evaluated_text = await state.eval_if_expression(text)
            await state.set(path, str(evaluated_text) if evaluated_text is not None else "")

        await ctx.send_message(ActionComplete())


class SetMultipleVariablesExecutor(DeclarativeActionExecutor):
    """Executor for the SetMultipleVariables action."""

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the SetMultipleVariables action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        assignments = self._action_def.get("assignments", [])
        for assignment in assignments:
            variable = assignment.get("variable")
            path: str | None
            if isinstance(variable, str):
                path = variable
            elif isinstance(variable, dict):
                path = variable.get("path")
            else:
                path = assignment.get("path")
            value = assignment.get("value")
            if path:
                evaluated_value = await state.eval_if_expression(value)
                await state.set(path, evaluated_value)

        await ctx.send_message(ActionComplete())


class AppendValueExecutor(DeclarativeActionExecutor):
    """Executor for the AppendValue action."""

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the AppendValue action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        path = self._action_def.get("path")
        value = self._action_def.get("value")

        if path:
            evaluated_value = await state.eval_if_expression(value)
            await state.append(path, evaluated_value)

        await ctx.send_message(ActionComplete())


class ResetVariableExecutor(DeclarativeActionExecutor):
    """Executor for the ResetVariable action."""

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the ResetVariable action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        path = _get_variable_path(self._action_def)

        if path:
            # Reset to None/empty
            await state.set(path, None)

        await ctx.send_message(ActionComplete())


class ClearAllVariablesExecutor(DeclarativeActionExecutor):
    """Executor for the ClearAllVariables action."""

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the ClearAllVariables action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        # Get state data and clear turn variables
        state_data = await state.get_state_data()
        state_data["turn"] = {}
        await state.set_state_data(state_data)

        await ctx.send_message(ActionComplete())


class SendActivityExecutor(DeclarativeActionExecutor):
    """Executor for the SendActivity action.

    Sends a text message or activity as workflow output.
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete, str],
    ) -> None:
        """Handle the SendActivity action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        activity = self._action_def.get("activity", "")

        # Activity can be a string directly or a dict with a "text" field
        text = activity.get("text", "") if isinstance(activity, dict) else activity

        if isinstance(text, str):
            # First evaluate any =expression syntax
            text = await state.eval_if_expression(text)
            # Then interpolate any {Variable.Path} template syntax
            if isinstance(text, str):
                text = await state.interpolate_string(text)

        # Yield the text as workflow output
        if text:
            await ctx.yield_output(str(text))

        await ctx.send_message(ActionComplete())


class EmitEventExecutor(DeclarativeActionExecutor):
    """Executor for the EmitEvent action.

    Emits a custom event to the workflow event stream.

    Supports two schema formats:
    1. Graph mode: eventName, eventValue
    2. Interpreter mode: event.name, event.data
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete, dict[str, Any]],
    ) -> None:
        """Handle the EmitEvent action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        # Support both schema formats:
        # - Graph mode: eventName, eventValue
        # - Interpreter mode: event.name, event.data
        event_def = self._action_def.get("event", {})
        event_name = self._action_def.get("eventName") or event_def.get("name", "")
        event_value = self._action_def.get("eventValue")
        if event_value is None:
            event_value = event_def.get("data")

        if event_name:
            evaluated_name = await state.eval_if_expression(event_name)
            evaluated_value = await state.eval_if_expression(event_value)

            event_data = {
                "eventName": evaluated_name,
                "eventValue": evaluated_value,
            }
            await ctx.yield_output(event_data)

        await ctx.send_message(ActionComplete())


# Mapping of action kinds to executor classes
BASIC_ACTION_EXECUTORS: dict[str, type[DeclarativeActionExecutor]] = {
    "SetValue": SetValueExecutor,
    "SetVariable": SetVariableExecutor,
    "SetTextVariable": SetTextVariableExecutor,
    "SetMultipleVariables": SetMultipleVariablesExecutor,
    "AppendValue": AppendValueExecutor,
    "ResetVariable": ResetVariableExecutor,
    "ClearAllVariables": ClearAllVariablesExecutor,
    "SendActivity": SendActivityExecutor,
    "EmitEvent": EmitEventExecutor,
}
