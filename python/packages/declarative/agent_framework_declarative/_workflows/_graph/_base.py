# Copyright (c) Microsoft. All rights reserved.

"""Base classes for graph-based declarative workflow executors.

This module provides:
- DeclarativeWorkflowState: Manages workflow variables via SharedState
- DeclarativeActionExecutor: Base class for action executors
- Message types for inter-executor communication
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from agent_framework._workflows import (
    Executor,
    SharedState,
    WorkflowContext,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Mapping

# Key used in SharedState to store declarative workflow variables
DECLARATIVE_STATE_KEY = "_declarative_workflow_state"


class DeclarativeWorkflowState:
    """Manages workflow variables stored in SharedState.

    This class provides the same interface as the interpreter-based WorkflowState
    but stores all data in SharedState for checkpointing support.

    The state is organized into namespaces:
    - workflow.inputs: Initial inputs (read-only)
    - workflow.outputs: Values to return from workflow
    - turn: Variables persisting within the workflow turn
    - agent: Results from most recent agent invocation
    - conversation: Conversation history
    """

    def __init__(self, shared_state: SharedState):
        """Initialize with a SharedState instance.

        Args:
            shared_state: The workflow's shared state for persistence
        """
        self._shared_state = shared_state

    async def initialize(self, inputs: "Mapping[str, Any] | None" = None) -> None:
        """Initialize the declarative state with inputs.

        Args:
            inputs: Initial workflow inputs (become workflow.inputs.*)
        """
        state_data: dict[str, Any] = {
            "inputs": dict(inputs) if inputs else {},
            "outputs": {},
            "turn": {},
            "agent": {},
            "conversation": {"messages": [], "history": []},
            "custom": {},
        }
        await self._shared_state.set(DECLARATIVE_STATE_KEY, state_data)

    async def get_state_data(self) -> dict[str, Any]:
        """Get the full state data dict from shared state."""
        try:
            result: dict[str, Any] = await self._shared_state.get(DECLARATIVE_STATE_KEY)
            return result
        except KeyError:
            # Initialize if not present
            await self.initialize()
            return cast(dict[str, Any], await self._shared_state.get(DECLARATIVE_STATE_KEY))

    async def set_state_data(self, data: dict[str, Any]) -> None:
        """Set the full state data dict in shared state."""
        await self._shared_state.set(DECLARATIVE_STATE_KEY, data)

    async def get(self, path: str, default: Any = None) -> Any:
        """Get a value from the state using a dot-notated path.

        Args:
            path: Dot-notated path like 'turn.results' or 'workflow.inputs.query'
            default: Default value if path doesn't exist

        Returns:
            The value at the path, or default if not found
        """
        # Map .NET style namespaces to Python style
        if path.startswith("Local."):
            path = "turn." + path[6:]
        elif path.startswith("System."):
            path = "system." + path[7:]
        elif path.startswith("Workflow."):
            path = "workflow." + path[9:]
        elif path.startswith("inputs."):
            path = "workflow.inputs." + path[7:]

        state_data = await self.get_state_data()
        parts = path.split(".")
        if not parts:
            return default

        namespace = parts[0]
        remaining = parts[1:]

        # Handle workflow.inputs and workflow.outputs specially
        if namespace == "workflow" and remaining:
            sub_namespace = remaining[0]
            remaining = remaining[1:]
            if sub_namespace == "inputs":
                obj: Any = state_data.get("inputs", {})
            elif sub_namespace == "outputs":
                obj = state_data.get("outputs", {})
            else:
                return default
        elif namespace == "turn":
            obj = state_data.get("turn", {})
        elif namespace == "system":
            obj = state_data.get("system", {})
        elif namespace == "agent":
            obj = state_data.get("agent", {})
        elif namespace == "conversation":
            obj = state_data.get("conversation", {})
        else:
            # Try custom namespace
            custom_data: dict[str, Any] = state_data.get("custom", {})
            obj = custom_data.get(namespace, default)
            if obj is default:
                return default

        # Navigate the remaining path
        for part in remaining:
            if isinstance(obj, dict):
                obj = obj.get(part, default)  # type: ignore[union-attr]
                if obj is default:
                    return default
            elif hasattr(obj, part):  # type: ignore[arg-type]
                obj = getattr(obj, part)  # type: ignore[arg-type]
            else:
                return default

        return obj  # type: ignore[return-value]

    async def set(self, path: str, value: Any) -> None:
        """Set a value in the state using a dot-notated path.

        Args:
            path: Dot-notated path like 'turn.results' or 'workflow.outputs.response'
            value: The value to set

        Raises:
            ValueError: If attempting to set workflow.inputs (which is read-only)
        """
        # Map .NET style namespaces to Python style
        if path.startswith("Local."):
            path = "turn." + path[6:]
        elif path.startswith("System."):
            path = "system." + path[7:]
        elif path.startswith("Workflow."):
            path = "workflow." + path[9:]
        elif path.startswith("inputs."):
            path = "workflow.inputs." + path[7:]

        state_data = await self.get_state_data()
        parts = path.split(".")
        if not parts:
            return

        namespace = parts[0]
        remaining = parts[1:]

        # Determine target dict
        if namespace == "workflow":
            if not remaining:
                raise ValueError("Cannot set 'workflow' directly; use 'workflow.outputs.*'")
            sub_namespace = remaining[0]
            remaining = remaining[1:]
            if sub_namespace == "inputs":
                raise ValueError("Cannot modify workflow.inputs - they are read-only")
            if sub_namespace == "outputs":
                target = state_data.setdefault("outputs", {})
            else:
                raise ValueError(f"Unknown workflow namespace: {sub_namespace}")
        elif namespace == "turn":
            target = state_data.setdefault("turn", {})
        elif namespace == "system":
            target = state_data.setdefault("system", {})
        elif namespace == "agent":
            target = state_data.setdefault("agent", {})
        elif namespace == "conversation":
            target = state_data.setdefault("conversation", {})
        else:
            # Create or use custom namespace
            custom = state_data.setdefault("custom", {})
            if namespace not in custom:
                custom[namespace] = {}
            target = custom[namespace]

        if not remaining:
            raise ValueError(f"Cannot replace entire namespace '{namespace}'")

        # Navigate to parent, creating dicts as needed
        for part in remaining[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]

        # Set the final value
        target[remaining[-1]] = value
        await self.set_state_data(state_data)

    async def append(self, path: str, value: Any) -> None:
        """Append a value to a list at the specified path.

        If the path doesn't exist, creates a new list with the value.

        Note: This operation is not atomic. In concurrent scenarios, use explicit
        locking or consider using atomic operations at the storage layer.

        Args:
            path: Dot-notated path to a list
            value: The value to append
        """
        existing = await self.get(path)
        if existing is None:
            await self.set(path, [value])
        elif isinstance(existing, list):
            existing_list: list[Any] = list(existing)  # type: ignore[arg-type]
            existing_list.append(value)
            await self.set(path, existing_list)
        else:
            raise ValueError(f"Cannot append to non-list at path '{path}'")

    async def get_inputs(self) -> dict[str, Any]:
        """Get the workflow inputs."""
        state_data = await self.get_state_data()
        inputs: dict[str, Any] = state_data.get("inputs", {})
        return inputs

    async def get_outputs(self) -> dict[str, Any]:
        """Get the workflow outputs."""
        state_data = await self.get_state_data()
        outputs: dict[str, Any] = state_data.get("outputs", {})
        return outputs

    async def eval(self, expression: str) -> Any:
        """Evaluate a PowerFx expression with the current state.

        Expressions starting with '=' are evaluated as PowerFx.
        Other strings are returned as-is.

        Args:
            expression: The expression to evaluate

        Returns:
            The evaluated result
        """
        if not expression:
            return expression

        if not isinstance(expression, str):
            return expression

        if not expression.startswith("="):
            return expression

        # Strip the leading '=' for evaluation
        formula = expression[1:]

        # Try PowerFx evaluation if available
        try:
            from powerfx import Engine

            engine = Engine()
            symbols = await self._to_powerfx_symbols()
            return engine.eval(formula, symbols=symbols)
        except ImportError:
            # powerfx package not installed - use simple fallback
            logger.debug(f"PowerFx package not installed, using simple evaluation for: {formula}")
        except Exception:
            # PowerFx evaluation failed (syntax error, unsupported function, etc.)
            # Fall back to simple evaluation which handles basic cases
            logger.debug(f"PowerFx evaluation failed for '{formula}', falling back to simple evaluation")

        # Fallback to simple evaluation
        return await self._eval_simple(formula)

    async def _to_powerfx_symbols(self) -> dict[str, Any]:
        """Convert the current state to a PowerFx symbols dictionary."""
        state_data = await self.get_state_data()
        return {
            "workflow": {
                "inputs": state_data.get("inputs", {}),
                "outputs": state_data.get("outputs", {}),
            },
            "turn": state_data.get("turn", {}),
            "agent": state_data.get("agent", {}),
            "conversation": state_data.get("conversation", {}),
            **state_data.get("custom", {}),
        }

    async def _eval_simple(self, formula: str) -> Any:
        """Simple expression evaluation fallback."""
        from .._powerfx_functions import CUSTOM_FUNCTIONS

        formula = formula.strip()

        # Handle logical operators first (lowest precedence)
        # Note: " And " and " Or " are case-sensitive in PowerFx
        # We also handle common variations with newlines
        for and_op in [" And ", "\n And ", " And\n", "\nAnd\n", "\nAnd ", " And\r\n", "\r\nAnd "]:
            if and_op in formula:
                # Split on first occurrence
                idx = formula.find(and_op)
                left_str = formula[:idx].strip()
                right_str = formula[idx + len(and_op) :].strip()
                left = await self._eval_simple(left_str)
                right = await self._eval_simple(right_str)
                return bool(left) and bool(right)

        for or_op in [" Or ", "\n Or ", " Or\n", "\nOr\n", "\nOr ", " Or\r\n", "\r\nOr "]:
            if or_op in formula:
                idx = formula.find(or_op)
                left_str = formula[:idx].strip()
                right_str = formula[idx + len(or_op) :].strip()
                left = await self._eval_simple(left_str)
                right = await self._eval_simple(right_str)
                return bool(left) or bool(right)

        # Handle negation
        if formula.startswith("!"):
            inner = formula[1:].strip()
            result = await self._eval_simple(inner)
            return not bool(result)

        # Handle Not() function
        if formula.startswith("Not(") and formula.endswith(")"):
            inner = formula[4:-1].strip()
            result = await self._eval_simple(inner)
            return not bool(result)

        # Handle function calls
        for func_name, func in CUSTOM_FUNCTIONS.items():
            if formula.startswith(f"{func_name}(") and formula.endswith(")"):
                args_str = formula[len(func_name) + 1 : -1]
                args = self._parse_function_args(args_str)
                evaluated_args: list[Any] = []
                for arg in args:
                    if isinstance(arg, str):
                        evaluated_args.append(await self._eval_simple(arg))
                    else:
                        evaluated_args.append(arg)
                try:
                    return func(*evaluated_args)
                except Exception:
                    return formula

        # Handle comparison operators
        # Support both PowerFx style (=) and Python style (==) for equality
        for op in [" < ", " > ", " <= ", " >= ", " <> ", " != ", " == ", " = "]:
            if op in formula:
                parts = formula.split(op, 1)
                left = await self._eval_simple(parts[0].strip())
                right = await self._eval_simple(parts[1].strip())
                if op == " < ":
                    return left < right
                if op == " > ":
                    return left > right
                if op == " <= ":
                    return left <= right
                if op == " >= ":
                    return left >= right
                if op == " <> " or op == " != ":
                    return left != right
                if op == " = " or op == " == ":
                    return left == right

        # Handle arithmetic operators (lower precedence than comparison)
        for op in [" + ", " - ", " * ", " / "]:
            if op in formula:
                parts = formula.split(op, 1)
                left = await self._eval_simple(parts[0].strip())
                right = await self._eval_simple(parts[1].strip())
                # Treat None as 0 for arithmetic (PowerFx behavior)
                if left is None:
                    left = 0
                if right is None:
                    right = 0
                # Coerce Decimal to float for arithmetic
                if hasattr(left, "__float__"):
                    left = float(left)
                if hasattr(right, "__float__"):
                    right = float(right)
                if op == " + ":
                    return left + right
                if op == " - ":
                    return left - right
                if op == " * ":
                    return left * right
                if op == " / ":
                    # Division by zero protection - return None (Blank in PowerFx)
                    if right == 0:
                        from agent_framework import get_logger

                        logger = get_logger("agent_framework.declarative.workflows")
                        logger.warning(f"Division by zero in expression: {formula}")
                        return None
                    return left / right

        # Handle string literals
        if (formula.startswith('"') and formula.endswith('"')) or (formula.startswith("'") and formula.endswith("'")):
            return formula[1:-1]

        # Handle numeric literals
        try:
            if "." in formula:
                return float(formula)
            return int(formula)
        except ValueError:
            pass

        # Handle boolean literals
        if formula.lower() == "true":
            return True
        if formula.lower() == "false":
            return False

        # Handle variable references
        if "." in formula:
            path = formula
            if formula.startswith("Local."):
                path = "turn." + formula[6:]
            elif formula.startswith("System."):
                path = "system." + formula[7:]
            elif formula.startswith("Workflow."):
                path = "workflow." + formula[9:]
            elif formula.startswith("inputs."):
                path = "workflow.inputs." + formula[7:]
            return await self.get(path)

        return formula

    def _parse_function_args(self, args_str: str) -> list[str]:
        """Parse function arguments, handling nested parentheses."""
        args: list[str] = []
        current = ""
        depth = 0
        in_string = False
        string_char = None

        for char in args_str:
            if char in ('"', "'") and not in_string:
                in_string = True
                string_char = char
                current += char
            elif char == string_char and in_string:
                in_string = False
                string_char = None
                current += char
            elif char == "(" and not in_string:
                depth += 1
                current += char
            elif char == ")" and not in_string:
                depth -= 1
                current += char
            elif char == "," and depth == 0 and not in_string:
                args.append(current.strip())
                current = ""
            else:
                current += char

        if current.strip():
            args.append(current.strip())

        return args

    async def eval_if_expression(self, value: Any) -> Any:
        """Evaluate a value if it's a PowerFx expression, otherwise return as-is."""
        if isinstance(value, str):
            return await self.eval(value)
        if isinstance(value, dict):
            value_dict: dict[str, Any] = dict(value)  # type: ignore[arg-type]
            return {k: await self.eval_if_expression(v) for k, v in value_dict.items()}
        if isinstance(value, list):
            value_list: list[Any] = list(value)  # type: ignore[arg-type]
            return [await self.eval_if_expression(item) for item in value_list]
        return value

    async def interpolate_string(self, text: str) -> str:
        """Interpolate {Variable.Path} references in a string.

        This handles template-style variable substitution like:
        - "Created ticket #{Local.TicketParameters.TicketId}"
        - "Routing to {Local.RoutingParameters.TeamName}"

        Args:
            text: Text that may contain {Variable.Path} references

        Returns:
            Text with variables interpolated
        """
        import re

        async def replace_var(match: re.Match[str]) -> str:
            var_path: str = match.group(1)
            # Map .NET style to Python style (Local.X -> turn.X)
            path = var_path
            if var_path.startswith("Local."):
                path = "turn." + var_path[6:]
            elif var_path.startswith("System."):
                path = "system." + var_path[7:]
            value = await self.get(path)
            return str(value) if value is not None else ""

        # Match {Variable.Path} patterns
        pattern = r"\{([A-Za-z][A-Za-z0-9_.]*)\}"

        # re.sub doesn't support async, so we need to do it manually
        result = text
        for match in re.finditer(pattern, text):
            replacement = await replace_var(match)
            result = result.replace(match.group(0), replacement, 1)

        return result


# Message types for inter-executor communication
# These are defined before DeclarativeActionExecutor since it references them


class ActionTrigger:
    """Message that triggers a declarative action executor.

    This is sent between executors in the graph to pass control
    and any action-specific data.
    """

    def __init__(self, data: Any = None):
        """Initialize the action trigger.

        Args:
            data: Optional data to pass to the action
        """
        self.data = data


class ActionComplete:
    """Message sent when a declarative action completes.

    This is sent to downstream executors to continue the workflow.
    """

    def __init__(self, result: Any = None):
        """Initialize the completion message.

        Args:
            result: Optional result from the action
        """
        self.result = result


@dataclass
class ConditionResult:
    """Result of evaluating a condition (If/Switch).

    This message is output by ConditionEvaluatorExecutor and SwitchEvaluatorExecutor
    to indicate which branch should be taken.
    """

    matched: bool
    branch_index: int  # Which branch matched (0 = first, -1 = else/default)
    value: Any = None  # The evaluated condition value


@dataclass
class LoopIterationResult:
    """Result of a loop iteration step.

    This message is output by ForeachInitExecutor and ForeachNextExecutor
    to indicate whether the loop should continue.
    """

    has_next: bool
    current_item: Any = None
    current_index: int = 0


@dataclass
class LoopControl:
    """Signal for loop control (break/continue).

    This message is output by BreakLoopExecutor and ContinueLoopExecutor.
    """

    action: str  # "break" or "continue"


# Union type for any declarative action message - allows executors to accept
# messages from triggers, completions, and control flow results
DeclarativeMessage = ActionTrigger | ActionComplete | ConditionResult | LoopIterationResult | LoopControl


class DeclarativeActionExecutor(Executor):
    """Base class for declarative action executors.

    Each declarative action (SetValue, SendActivity, etc.) is implemented
    as a subclass of this executor. The executor receives an ActionInput
    message containing the action definition and state reference.
    """

    def __init__(
        self,
        action_def: dict[str, Any],
        *,
        id: str | None = None,
    ):
        """Initialize the declarative action executor.

        Args:
            action_def: The action definition from YAML
            id: Optional executor ID (defaults to action id or generated)
        """
        action_id = id or action_def.get("id") or f"{action_def.get('kind', 'action')}_{hash(str(action_def)) % 10000}"
        super().__init__(id=action_id, defer_discovery=True)
        self._action_def = action_def

        # Manually register handlers after initialization
        self._handlers = {}
        self._handler_specs = []
        self._discover_handlers()
        self._discover_response_handlers()

    @property
    def action_def(self) -> dict[str, Any]:
        """Get the action definition."""
        return self._action_def

    @property
    def display_name(self) -> str | None:
        """Get the display name for logging."""
        return self._action_def.get("displayName")

    def _get_state(self, shared_state: SharedState) -> DeclarativeWorkflowState:
        """Get the declarative workflow state wrapper."""
        return DeclarativeWorkflowState(shared_state)

    async def _ensure_state_initialized(
        self,
        ctx: WorkflowContext[Any, Any],
        trigger: Any,
    ) -> DeclarativeWorkflowState:
        """Ensure declarative state is initialized.

        Follows .NET's DefaultTransform pattern - accepts any input type:
        - dict/Mapping: Used directly as workflow.inputs
        - str: Converted to {"input": value}
        - DeclarativeMessage: Internal message, no initialization needed
        - Any other type: Converted via str() to {"input": str(value)}

        Args:
            ctx: The workflow context
            trigger: The trigger message - can be any type

        Returns:
            The initialized DeclarativeWorkflowState
        """
        state = self._get_state(ctx.shared_state)

        if isinstance(trigger, dict):
            # Structured inputs - use directly
            await state.initialize(trigger)  # type: ignore
        elif isinstance(trigger, str):
            # String input - wrap in dict
            await state.initialize({"input": trigger})
        elif not isinstance(
            trigger, (ActionTrigger, ActionComplete, ConditionResult, LoopIterationResult, LoopControl)
        ):
            # Any other type - convert to string like .NET's DefaultTransform
            await state.initialize({"input": str(trigger)})

        return state
