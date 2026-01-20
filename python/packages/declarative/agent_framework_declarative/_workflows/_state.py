# Copyright (c) Microsoft. All rights reserved.

"""WorkflowState manages PowerFx variables during declarative workflow execution.

This module provides state management for declarative workflows, handling:
- Workflow inputs (read-only)
- Turn-scoped variables
- Workflow outputs
- Agent results and context
"""

from collections.abc import Mapping
from typing import Any, cast

from agent_framework import get_logger

try:
    from powerfx import Engine

    _powerfx_engine: Engine | None = Engine()
except (ImportError, RuntimeError):
    # ImportError: powerfx package not installed
    # RuntimeError: .NET runtime not available or misconfigured
    _powerfx_engine = None

logger = get_logger("agent_framework.declarative.workflows")


class WorkflowState:
    """Manages variables and state during declarative workflow execution.

    WorkflowState provides a unified interface for:

    - Reading workflow inputs (immutable after initialization)
    - Managing Local-scoped variables that persist across actions
    - Storing agent results and making them available to subsequent actions
    - Evaluating PowerFx expressions with the current state as context

    The state is organized into namespaces that mirror the .NET implementation:

    - Workflow.Inputs: Initial inputs to the workflow
    - Workflow.Outputs: Values to be returned from the workflow
    - Local: Variables that persist within the current workflow turn
    - System: System-level variables (ConversationId, LastMessage, etc.)
    - Agent: Results from the most recent agent invocation
    - Conversation: Conversation history and messages

    Examples:
        .. code-block:: python

            from agent_framework_declarative import WorkflowState

            # Initialize with inputs
            state = WorkflowState(inputs={"query": "Hello", "user_id": "123"})

            # Access inputs (read-only)
            query = state.get("Workflow.Inputs.query")  # "Hello"

            # Set Local-scoped variables
            state.set("Local.results", [])
            state.append("Local.results", "item1")
            state.append("Local.results", "item2")

            # Set workflow outputs
            state.set("Workflow.Outputs.response", "Completed")

        .. code-block:: python

            from agent_framework_declarative import WorkflowState

            # PowerFx expression evaluation
            state = WorkflowState(inputs={"name": "World"})
            result = state.eval("=Concat('Hello ', Workflow.Inputs.name)")
            # result: "Hello World"

            # Non-PowerFx strings are returned as-is
            plain = state.eval("Hello World")
            # plain: "Hello World"

        .. code-block:: python

            from agent_framework_declarative import WorkflowState

            # Working with agent results
            state = WorkflowState()
            state.set_agent_result(
                text="The answer is 42.",
                messages=[],
                tool_calls=[],
            )

            # Access agent result in subsequent actions
            response = state.get("Agent.text")  # "The answer is 42."
    """

    def __init__(
        self,
        inputs: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize workflow state with optional inputs.

        Args:
            inputs: Initial inputs to the workflow. These become available
                   as Workflow.Inputs.* and are immutable after initialization.
        """
        self._inputs: dict[str, Any] = dict(inputs) if inputs else {}
        self._local: dict[str, Any] = {}
        self._outputs: dict[str, Any] = {}
        self._system: dict[str, Any] = {
            "ConversationId": "default",
            "LastMessage": {"Text": "", "Id": ""},
            "LastMessageText": "",
            "LastMessageId": "",
        }
        self._agent: dict[str, Any] = {}
        self._conversation: dict[str, Any] = {
            "messages": [],
            "history": [],
        }
        self._custom: dict[str, Any] = {}

    @property
    def inputs(self) -> Mapping[str, Any]:
        """Get the workflow inputs (read-only)."""
        return self._inputs

    @property
    def outputs(self) -> dict[str, Any]:
        """Get the workflow outputs."""
        return self._outputs

    @property
    def local(self) -> dict[str, Any]:
        """Get the Local-scoped variables."""
        return self._local

    @property
    def system(self) -> dict[str, Any]:
        """Get the System-scoped variables."""
        return self._system

    @property
    def agent(self) -> dict[str, Any]:
        """Get the most recent agent result."""
        return self._agent

    @property
    def conversation(self) -> dict[str, Any]:
        """Get the conversation state."""
        return self._conversation

    def get(self, path: str, default: Any = None) -> Any:
        """Get a value from the state using a dot-notated path.

        Args:
            path: Dot-notated path like 'Local.results' or 'Workflow.Inputs.query'
            default: Default value if path doesn't exist

        Returns:
            The value at the path, or default if not found
        """
        parts = path.split(".")
        if not parts:
            return default

        namespace = parts[0]
        remaining = parts[1:]

        # Handle Workflow.Inputs and Workflow.Outputs specially
        if namespace == "Workflow" and remaining:
            sub_namespace = remaining[0]
            remaining = remaining[1:]
            if sub_namespace == "Inputs":
                obj: Any = self._inputs
            elif sub_namespace == "Outputs":
                obj = self._outputs
            else:
                return default
        elif namespace == "Local":
            obj = self._local
        elif namespace == "System":
            obj = self._system
        elif namespace == "Agent":
            obj = self._agent
        elif namespace == "Conversation":
            obj = self._conversation
        else:
            # Try custom namespace
            obj = self._custom.get(namespace, default)
            if obj is default:
                return default

        # Navigate the remaining path
        for part in remaining:
            if isinstance(obj, dict):
                obj_dict: dict[str, Any] = cast(dict[str, Any], obj)
                obj = obj_dict.get(part, default)
                if obj is default:
                    return default
            elif hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return default

        return obj

    def set(self, path: str, value: Any) -> None:
        """Set a value in the state using a dot-notated path.

        Args:
            path: Dot-notated path like 'Local.results' or 'Workflow.Outputs.response'
            value: The value to set

        Raises:
            ValueError: If attempting to set Workflow.Inputs (which is read-only)
        """
        parts = path.split(".")
        if not parts:
            return

        namespace = parts[0]
        remaining = parts[1:]

        # Handle Workflow.Inputs and Workflow.Outputs specially
        if namespace == "Workflow":
            if not remaining:
                raise ValueError("Cannot set 'Workflow' directly; use 'Workflow.Outputs.*'")
            sub_namespace = remaining[0]
            remaining = remaining[1:]
            if sub_namespace == "Inputs":
                raise ValueError("Cannot modify Workflow.Inputs - they are read-only")
            if sub_namespace == "Outputs":
                target = self._outputs
            else:
                raise ValueError(f"Unknown Workflow namespace: {sub_namespace}")
        elif namespace == "Local":
            target = self._local
        elif namespace == "System":
            target = self._system
        elif namespace == "Agent":
            target = self._agent
        elif namespace == "Conversation":
            target = self._conversation
        else:
            # Create or use custom namespace
            if namespace not in self._custom:
                self._custom[namespace] = {}
            target = self._custom[namespace]

        # Navigate to the parent and set the value
        if not remaining:
            # Setting the namespace root itself - this shouldn't happen normally
            raise ValueError(f"Cannot replace entire namespace '{namespace}'")

        # Navigate to parent, creating dicts as needed
        for part in remaining[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]

        # Set the final value
        target[remaining[-1]] = value

    def append(self, path: str, value: Any) -> None:
        """Append a value to a list at the specified path.

        If the path doesn't exist, creates a new list with the value.
        If the path exists but isn't a list, raises ValueError.

        Args:
            path: Dot-notated path to a list
            value: The value to append

        Raises:
            ValueError: If the existing value is not a list
        """
        existing = self.get(path)
        if existing is None:
            self.set(path, [value])
        elif isinstance(existing, list):
            existing.append(value)
            self.set(path, existing)
        else:
            raise ValueError(f"Cannot append to non-list at path '{path}'")

    def set_agent_result(
        self,
        text: str | None = None,
        messages: list[Any] | None = None,
        tool_calls: list[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Set the result from the most recent agent invocation.

        This updates the 'agent' namespace with the agent's response,
        making it available to subsequent actions via agent.text, agent.messages, etc.

        Args:
            text: The text content of the agent's response
            messages: The messages from the agent
            tool_calls: Any tool calls made by the agent
            **kwargs: Additional result data
        """
        self._agent = {
            "text": text,
            "messages": messages or [],
            "toolCalls": tool_calls or [],
            **kwargs,
        }

    def add_conversation_message(self, message: Any) -> None:
        """Add a message to the conversation history.

        Args:
            message: The message to add (typically a ChatMessage or similar)
        """
        self._conversation["messages"].append(message)
        self._conversation["history"].append(message)

    def to_powerfx_symbols(self) -> dict[str, Any]:
        """Convert the current state to a PowerFx symbols dictionary.

        Returns:
            A dictionary suitable for passing to PowerFx Engine.eval()
        """
        symbols = {
            "Workflow": {
                "Inputs": dict(self._inputs),
                "Outputs": dict(self._outputs),
            },
            "Local": dict(self._local),
            "System": dict(self._system),
            "Agent": dict(self._agent),
            "Conversation": dict(self._conversation),
            # Also expose inputs at top level for backward compatibility with =inputs.X syntax
            "inputs": dict(self._inputs),
            **self._custom,
        }
        # Debug log the Local symbols to help diagnose type issues
        if self._local:
            for key, value in self._local.items():
                logger.debug(
                    f"PowerFx symbol Local.{key}: type={type(value).__name__}, "
                    f"value_preview={str(value)[:100] if value else None}"
                )
        return symbols

    def eval(self, expression: str) -> Any:
        """Evaluate a PowerFx expression with the current state.

        Expressions starting with '=' are evaluated as PowerFx.
        Other strings are returned as-is (after variable interpolation if applicable).

        Args:
            expression: The expression to evaluate

        Returns:
            The evaluated result, or the original expression if not a PowerFx expression
        """
        if not expression:
            return expression

        if not expression.startswith("="):
            return expression

        # Strip the leading '=' for evaluation
        formula = expression[1:]

        if _powerfx_engine is not None:
            # Try PowerFx evaluation first
            try:
                symbols = self.to_powerfx_symbols()
                return _powerfx_engine.eval(formula, symbols=symbols)
            except Exception as exc:
                logger.warning(f"PowerFx evaluation failed for '{expression[:50]}': {exc}")
                # Fall through to simple evaluation

        # Fallback: Simple expression evaluation using custom functions
        return self._eval_simple(formula)

    def _eval_simple(self, formula: str) -> Any:
        """Simple expression evaluation when PowerFx is not available.

        Supports:
        - Variable references: Local.X, System.X, Workflow.Inputs.X
        - Simple function calls: IsBlank(x), Find(a, b), etc.
        - Simple comparisons: x < 4, x = "value"
        - Logical operators: And, Or, Not, ||, !
        - Negation: !expression

        Args:
            formula: The formula to evaluate (without leading '=')

        Returns:
            The evaluated result
        """
        from ._powerfx_functions import CUSTOM_FUNCTIONS

        formula = formula.strip()

        # Handle negation prefix
        if formula.startswith("!"):
            inner = formula[1:].strip()
            result = self._eval_simple(inner)
            return not bool(result)

        # Handle Not() function
        if formula.startswith("Not(") and formula.endswith(")"):
            inner = formula[4:-1].strip()
            result = self._eval_simple(inner)
            return not bool(result)

        # Handle function calls
        for func_name, func in CUSTOM_FUNCTIONS.items():
            if formula.startswith(f"{func_name}(") and formula.endswith(")"):
                args_str = formula[len(func_name) + 1 : -1]
                # Simple argument parsing (doesn't handle nested calls well)
                args = self._parse_function_args(args_str)
                evaluated_args = [self._eval_simple(arg) if isinstance(arg, str) else arg for arg in args]
                try:
                    return func(*evaluated_args)
                except Exception as e:
                    logger.warning(f"Function {func_name} failed: {e}")
                    return formula

        # Handle And operator
        if " And " in formula:
            parts = formula.split(" And ", 1)
            left = self._eval_simple(parts[0])
            right = self._eval_simple(parts[1])
            return bool(left) and bool(right)

        # Handle Or operator (||)
        if " || " in formula or " Or " in formula:
            parts = formula.split(" || ", 1) if " || " in formula else formula.split(" Or ", 1)
            left = self._eval_simple(parts[0])
            right = self._eval_simple(parts[1])
            return bool(left) or bool(right)

        # Handle comparison operators
        for op in [" < ", " > ", " <= ", " >= ", " <> ", " = "]:
            if op in formula:
                parts = formula.split(op, 1)
                left = self._eval_simple(parts[0].strip())
                right = self._eval_simple(parts[1].strip())
                if op == " < ":
                    return left < right
                if op == " > ":
                    return left > right
                if op == " <= ":
                    return left <= right
                if op == " >= ":
                    return left >= right
                if op == " <> ":
                    return left != right
                if op == " = ":
                    return left == right

        # Handle arithmetic operators
        if " + " in formula:
            parts = formula.split(" + ", 1)
            left = self._eval_simple(parts[0].strip())
            right = self._eval_simple(parts[1].strip())
            # Treat None as 0 for arithmetic (PowerFx behavior)
            if left is None:
                left = 0
            if right is None:
                right = 0
            # Try numeric addition first, fall back to string concat
            try:
                return float(left) + float(right)
            except (ValueError, TypeError):
                return str(left) + str(right)

        if " - " in formula:
            parts = formula.split(" - ", 1)
            left = self._eval_simple(parts[0].strip())
            right = self._eval_simple(parts[1].strip())
            # Treat None as 0 for arithmetic (PowerFx behavior)
            if left is None:
                left = 0
            if right is None:
                right = 0
            try:
                return float(left) - float(right)
            except (ValueError, TypeError):
                return formula

        # Handle multiplication
        if " * " in formula:
            parts = formula.split(" * ", 1)
            left = self._eval_simple(parts[0].strip())
            right = self._eval_simple(parts[1].strip())
            # Treat None as 0 for arithmetic (PowerFx behavior)
            if left is None:
                left = 0
            if right is None:
                right = 0
            try:
                return float(left) * float(right)
            except (ValueError, TypeError):
                return formula

        # Handle division with div-by-zero protection
        if " / " in formula:
            parts = formula.split(" / ", 1)
            left = self._eval_simple(parts[0].strip())
            right = self._eval_simple(parts[1].strip())
            # Treat None as 0 for arithmetic (PowerFx behavior)
            if left is None:
                left = 0
            if right is None:
                right = 0
            try:
                right_float = float(right)
                if right_float == 0:
                    # PowerFx returns Error for division by zero; we return None (Blank)
                    logger.warning(f"Division by zero in expression: {formula}")
                    return None
                return float(left) / right_float
            except (ValueError, TypeError):
                return formula

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
            # For known namespaces, return None if not found (PowerFx semantics)
            # rather than the formula string
            if formula.startswith(("Local.", "Workflow.", "Agent.", "Conversation.", "System.")):
                return self.get(formula)
            not_found = object()
            value = self.get(formula, default=not_found)
            if value is not not_found:
                return value

        # Return the formula as-is if we can't evaluate it
        return formula

    def _parse_function_args(self, args_str: str) -> list[str]:
        """Parse function arguments, handling nested parentheses and strings.

        Args:
            args_str: The argument string (without outer parentheses)

        Returns:
            List of argument strings
        """
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

    def eval_if_expression(self, value: Any) -> Any:
        """Evaluate a value if it's a PowerFx expression, otherwise return as-is.

        This is a convenience method that handles both expressions and literals.

        Args:
            value: A value that may or may not be a PowerFx expression

        Returns:
            The evaluated result if it's an expression, or the original value
        """
        if isinstance(value, str):
            return self.eval(value)
        if isinstance(value, dict):
            return {str(k): self.eval_if_expression(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.eval_if_expression(item) for item in value]
        return value

    def reset_local(self) -> None:
        """Reset Local-scoped variables for a new turn.

        This clears the Local namespace while preserving other state.
        """
        self._local.clear()

    def reset_agent(self) -> None:
        """Reset the agent result for a new agent invocation."""
        self._agent.clear()

    def clone(self) -> "WorkflowState":
        """Create a shallow copy of the state.

        Returns:
            A new WorkflowState with copied data
        """
        import copy

        new_state = WorkflowState()
        new_state._inputs = copy.copy(self._inputs)
        new_state._local = copy.copy(self._local)
        new_state._system = copy.copy(self._system)
        new_state._outputs = copy.copy(self._outputs)
        new_state._agent = copy.copy(self._agent)
        new_state._conversation = copy.copy(self._conversation)
        new_state._custom = copy.copy(self._custom)
        return new_state
