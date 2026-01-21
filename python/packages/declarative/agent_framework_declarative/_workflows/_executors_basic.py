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

        # Get state data and clear Local variables
        state_data = await state.get_state_data()
        state_data["Local"] = {}
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


class EditTableExecutor(DeclarativeActionExecutor):
    """Executor for the EditTable action.

    Performs operations on a table (list) variable such as add, remove, or clear.
    This is equivalent to the .NET EditTable action.

    YAML example:
        - kind: EditTable
          table: Local.Items
          operation: add  # add, remove, clear
          value: =Local.NewItem
          index: 0  # optional, for insert at position
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the EditTable action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        table_path = self._action_def.get("table") or _get_variable_path(self._action_def, "variable")
        operation = self._action_def.get("operation", "add").lower()
        value = self._action_def.get("value")
        index = self._action_def.get("index")

        if table_path:
            # Get current table value
            current_table = await state.get(table_path)
            if current_table is None:
                current_table = []
            elif not isinstance(current_table, list):
                current_table = [current_table]

            if operation == "add" or operation == "insert":
                evaluated_value = await state.eval_if_expression(value)
                if index is not None:
                    evaluated_index = await state.eval_if_expression(index)
                    idx = int(evaluated_index) if evaluated_index is not None else len(current_table)
                    current_table.insert(idx, evaluated_value)
                else:
                    current_table.append(evaluated_value)

            elif operation == "remove":
                if value is not None:
                    # Remove by value
                    evaluated_value = await state.eval_if_expression(value)
                    if evaluated_value in current_table:
                        current_table.remove(evaluated_value)
                elif index is not None:
                    # Remove by index
                    evaluated_index = await state.eval_if_expression(index)
                    idx = int(evaluated_index) if evaluated_index is not None else -1
                    if 0 <= idx < len(current_table):
                        current_table.pop(idx)

            elif operation == "clear":
                current_table = []

            elif operation == "set" or operation == "update":
                # Update item at index
                if index is not None:
                    evaluated_value = await state.eval_if_expression(value)
                    evaluated_index = await state.eval_if_expression(index)
                    idx = int(evaluated_index) if evaluated_index is not None else 0
                    if 0 <= idx < len(current_table):
                        current_table[idx] = evaluated_value

            await state.set(table_path, current_table)

        await ctx.send_message(ActionComplete())


class EditTableV2Executor(DeclarativeActionExecutor):
    """Executor for the EditTableV2 action.

    Enhanced table editing with more operations and better record support.
    This is equivalent to the .NET EditTableV2 action.

    YAML example:
        - kind: EditTableV2
          table: Local.Records
          operation: addOrUpdate  # add, remove, clear, addOrUpdate, filter
          item: =Local.NewRecord
          key: id  # for addOrUpdate, the field to match on
          condition: =item.status = "active"  # for filter operation
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the EditTableV2 action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        table_path = self._action_def.get("table") or _get_variable_path(self._action_def, "variable")
        operation = self._action_def.get("operation", "add").lower()
        item = self._action_def.get("item") or self._action_def.get("value")
        key_field = self._action_def.get("key")
        index = self._action_def.get("index")

        if table_path:
            # Get current table value
            current_table = await state.get(table_path)
            if current_table is None:
                current_table = []
            elif not isinstance(current_table, list):
                current_table = [current_table]

            if operation == "add":
                evaluated_item = await state.eval_if_expression(item)
                if index is not None:
                    evaluated_index = await state.eval_if_expression(index)
                    idx = int(evaluated_index) if evaluated_index is not None else len(current_table)
                    current_table.insert(idx, evaluated_item)
                else:
                    current_table.append(evaluated_item)

            elif operation == "remove":
                if item is not None:
                    evaluated_item = await state.eval_if_expression(item)
                    if key_field and isinstance(evaluated_item, dict):
                        # Remove by key match
                        key_value = evaluated_item.get(key_field)
                        current_table = [
                            r for r in current_table if not (isinstance(r, dict) and r.get(key_field) == key_value)
                        ]
                    elif evaluated_item in current_table:
                        current_table.remove(evaluated_item)
                elif index is not None:
                    evaluated_index = await state.eval_if_expression(index)
                    idx = int(evaluated_index) if evaluated_index is not None else -1
                    if 0 <= idx < len(current_table):
                        current_table.pop(idx)

            elif operation == "clear":
                current_table = []

            elif operation == "addorupdate":
                evaluated_item = await state.eval_if_expression(item)
                if key_field and isinstance(evaluated_item, dict):
                    key_value = evaluated_item.get(key_field)
                    # Find existing item with same key
                    found_idx = -1
                    for i, r in enumerate(current_table):
                        if isinstance(r, dict) and r.get(key_field) == key_value:
                            found_idx = i
                            break
                    if found_idx >= 0:
                        # Update existing
                        current_table[found_idx] = evaluated_item
                    else:
                        # Add new
                        current_table.append(evaluated_item)
                else:
                    # No key field - just add
                    current_table.append(evaluated_item)

            elif operation == "update":
                evaluated_item = await state.eval_if_expression(item)
                if index is not None:
                    evaluated_index = await state.eval_if_expression(index)
                    idx = int(evaluated_index) if evaluated_index is not None else 0
                    if 0 <= idx < len(current_table):
                        current_table[idx] = evaluated_item
                elif key_field and isinstance(evaluated_item, dict):
                    key_value = evaluated_item.get(key_field)
                    for i, r in enumerate(current_table):
                        if isinstance(r, dict) and r.get(key_field) == key_value:
                            current_table[i] = evaluated_item
                            break

            await state.set(table_path, current_table)

        await ctx.send_message(ActionComplete())


class ParseValueExecutor(DeclarativeActionExecutor):
    """Executor for the ParseValue action.

    Parses a value expression and optionally converts it to a target type.
    This is equivalent to the .NET ParseValue action.

    YAML example:
        - kind: ParseValue
          variable: Local.ParsedData
          value: =System.LastMessage.Text
          valueType: object  # optional: string, number, boolean, object, array
    """

    @handler
    async def handle_action(
        self,
        trigger: Any,
        ctx: WorkflowContext[ActionComplete],
    ) -> None:
        """Handle the ParseValue action."""
        state = await self._ensure_state_initialized(ctx, trigger)

        path = _get_variable_path(self._action_def)
        value = self._action_def.get("value")
        value_type = self._action_def.get("valueType")

        if path and value is not None:
            # Evaluate the value expression
            evaluated_value = await state.eval_if_expression(value)

            # Convert to target type if specified
            if value_type:
                evaluated_value = self._convert_to_type(evaluated_value, value_type)

            await state.set(path, evaluated_value)

        await ctx.send_message(ActionComplete())

    def _convert_to_type(self, value: Any, target_type: str) -> Any:
        """Convert a value to the specified target type.

        Args:
            value: The value to convert
            target_type: Target type (string, number, boolean, object, array)

        Returns:
            The converted value
        """
        import json

        target_type = target_type.lower()

        if target_type == "string":
            if value is None:
                return ""
            return str(value)

        if target_type in ("number", "int", "integer", "float", "decimal"):
            if value is None:
                return 0
            if isinstance(value, str):
                # Try to parse as number
                try:
                    if "." in value:
                        return float(value)
                    return int(value)
                except ValueError:
                    return 0
            return float(value) if isinstance(value, (int, float)) else 0

        if target_type in ("boolean", "bool"):
            if value is None:
                return False
            if isinstance(value, str):
                return value.lower() in ("true", "yes", "1", "on")
            return bool(value)

        if target_type in ("object", "record"):
            if value is None:
                return {}
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    return parsed if isinstance(parsed, dict) else {"value": parsed}
                except json.JSONDecodeError:
                    return {"value": value}
            return {"value": value}

        if target_type in ("array", "table", "list"):
            if value is None:
                return []
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    return parsed if isinstance(parsed, list) else [parsed]
                except json.JSONDecodeError:
                    return [value]
            return [value]

        # Unknown type - return as-is
        return value


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
    "ParseValue": ParseValueExecutor,
    "EditTable": EditTableExecutor,
    "EditTableV2": EditTableV2Executor,
}
