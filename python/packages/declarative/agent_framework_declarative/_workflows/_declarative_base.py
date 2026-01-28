# Copyright (c) Microsoft. All rights reserved.

"""Base classes for graph-based declarative workflow executors.

This module provides:
- DeclarativeWorkflowState: Manages workflow variables via SharedState
- DeclarativeActionExecutor: Base class for action executors
- Message types for inter-executor communication

PowerFx Expression Evaluation
-----------------------------
The .NET version uses RecalcEngine with:
1. Pre-registered custom functions (UserMessage, AgentMessage, MessageText)
2. Typed schemas for variables defined at compile time
3. UpdateVariable() to register mutable state with proper types

The Python `powerfx` library only exposes eval() with runtime symbols, not
the full RecalcEngine API. We work around this by:
1. Pre-processing custom functions (UserMessage, MessageText) before PowerFx
2. Gracefully handling undefined variable errors (returning None)
3. Converting non-serializable objects to PowerFx-safe types at runtime

See: dotnet/src/Microsoft.Agents.AI.Workflows.Declarative/PowerFx/
"""

import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal as _Decimal
from typing import Any, Literal, cast

from agent_framework._workflows import (
    Executor,
    SharedState,
    WorkflowContext,
)
from powerfx import Engine

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover


logger = logging.getLogger(__name__)


class ConversationData(TypedDict):
    """Structure for conversation-related state data.

    Attributes:
        messages: Active conversation messages for the current agent interaction.
            This is the primary storage used by InvokeAgent actions.
        history: Deprecated. Previously used as a separate history buffer, but
            messages and history are now kept in sync. Use messages instead.
    """

    messages: list[Any]
    history: list[Any]  # Deprecated: use messages instead


class DeclarativeStateData(TypedDict, total=False):
    """Structure for the declarative workflow state stored in SharedState.

    This TypedDict defines the schema for workflow variables stored
    under the DECLARATIVE_STATE_KEY in SharedState.

    Variable Scopes (matching .NET naming conventions):
        Inputs: Initial workflow inputs (read-only after initialization).
        Outputs: Values to return from the workflow.
        Local: Variables persisting within the current workflow turn.
        System: System-level variables (ConversationId, LastMessage, etc.).
        Agent: Results from the most recent agent invocation.
        Conversation: Conversation history and messages.
        Custom: User-defined custom variables.
        _declarative_loop_state: Internal loop iteration state (managed by ForeachExecutors).
    """

    Inputs: dict[str, Any]
    Outputs: dict[str, Any]
    Local: dict[str, Any]
    System: dict[str, Any]
    Agent: dict[str, Any]
    Conversation: ConversationData
    Custom: dict[str, Any]
    _declarative_loop_state: dict[str, Any]


# Key used in SharedState to store declarative workflow variables
DECLARATIVE_STATE_KEY = "_declarative_workflow_state"


# Types that PowerFx can serialize directly
# Note: Decimal is included because PowerFx returns Decimal for numeric values
_POWERFX_SAFE_TYPES = (str, int, float, bool, type(None), _Decimal)


def _make_powerfx_safe(value: Any) -> Any:
    """Convert a value to a PowerFx-serializable form.

    PowerFx can only serialize primitive types, dicts, and lists.
    Custom objects (like ChatMessage) must be converted to dicts or excluded.

    Args:
        value: Any Python value

    Returns:
        A PowerFx-safe representation of the value
    """
    if value is None or isinstance(value, _POWERFX_SAFE_TYPES):
        return value

    if isinstance(value, dict):
        return {k: _make_powerfx_safe(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_make_powerfx_safe(item) for item in value]

    # Try to convert objects with __dict__ or dataclass-style attributes
    if hasattr(value, "__dict__"):
        return _make_powerfx_safe(vars(value))

    # For other objects, try to convert to string representation
    return str(value)


class DeclarativeWorkflowState:
    """Manages workflow variables stored in SharedState.

    This class provides the same interface as the interpreter-based WorkflowState
    but stores all data in SharedState for checkpointing support.

    The state is organized into namespaces (matching .NET naming conventions):
    - Workflow.Inputs: Initial inputs (read-only)
    - Workflow.Outputs: Values to return from workflow
    - Local: Variables persisting within the workflow turn
    - System: System-level variables (ConversationId, LastMessage, etc.)
    - Agent: Results from most recent agent invocation
    - Conversation: Conversation history
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
            inputs: Initial workflow inputs (become Workflow.Inputs.*)
        """
        state_data: DeclarativeStateData = {
            "Inputs": dict(inputs) if inputs else {},
            "Outputs": {},
            "Local": {},
            "System": {
                "ConversationId": "default",
                "LastMessage": {"Text": "", "Id": ""},
                "LastMessageText": "",
                "LastMessageId": "",
            },
            "Agent": {},
            "Conversation": {"messages": [], "history": []},
            "Custom": {},
        }
        await self._shared_state.set(DECLARATIVE_STATE_KEY, state_data)

    async def get_state_data(self) -> DeclarativeStateData:
        """Get the full state data dict from shared state."""
        try:
            result: DeclarativeStateData = await self._shared_state.get(DECLARATIVE_STATE_KEY)
            return result
        except KeyError:
            # Initialize if not present
            await self.initialize()
            return cast(DeclarativeStateData, await self._shared_state.get(DECLARATIVE_STATE_KEY))

    async def set_state_data(self, data: DeclarativeStateData) -> None:
        """Set the full state data dict in shared state."""
        await self._shared_state.set(DECLARATIVE_STATE_KEY, data)

    async def get(self, path: str, default: Any = None) -> Any:
        """Get a value from the state using a dot-notated path.

        Args:
            path: Dot-notated path like 'Local.results' or 'Workflow.Inputs.query'
            default: Default value if path doesn't exist

        Returns:
            The value at the path, or default if not found
        """
        state_data = await self.get_state_data()
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
                obj: Any = state_data.get("Inputs", {})
            elif sub_namespace == "Outputs":
                obj = state_data.get("Outputs", {})
            else:
                return default
        elif namespace == "Local":
            obj = state_data.get("Local", {})
        elif namespace == "System":
            obj = state_data.get("System", {})
        elif namespace == "Agent":
            obj = state_data.get("Agent", {})
        elif namespace == "Conversation":
            obj = state_data.get("Conversation", {})
        else:
            # Try custom namespace
            custom_data: dict[str, Any] = state_data.get("Custom", {})
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
            path: Dot-notated path like 'Local.results' or 'Workflow.Outputs.response'
            value: The value to set

        Raises:
            ValueError: If attempting to set Workflow.Inputs (which is read-only)
        """
        state_data = await self.get_state_data()
        parts = path.split(".")
        if not parts:
            return

        namespace = parts[0]
        remaining = parts[1:]

        # Determine target dict
        if namespace == "Workflow":
            if not remaining:
                raise ValueError("Cannot set 'Workflow' directly; use 'Workflow.Outputs.*'")
            sub_namespace = remaining[0]
            remaining = remaining[1:]
            if sub_namespace == "Inputs":
                raise ValueError("Cannot modify Workflow.Inputs - they are read-only")
            if sub_namespace == "Outputs":
                target = state_data.setdefault("Outputs", {})
            else:
                raise ValueError(f"Unknown Workflow namespace: {sub_namespace}")
        elif namespace == "Local":
            target = state_data.setdefault("Local", {})
        elif namespace == "System":
            target = state_data.setdefault("System", {})
        elif namespace == "Agent":
            target = state_data.setdefault("Agent", {})
        elif namespace == "Conversation":
            target = cast(dict[str, Any], state_data).setdefault("Conversation", {})
        else:
            # Create or use custom namespace
            custom = state_data.setdefault("Custom", {})
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

    async def eval(self, expression: str) -> Any:
        """Evaluate a PowerFx expression with the current state.

        Expressions starting with '=' are evaluated as PowerFx.
        Other strings are returned as-is.

        Handles special custom functions not supported by PowerFx:
        - UserMessage(text): Creates a user message dict from text
        - MessageText(messages): Extracts text from the last message

        Args:
            expression: The expression to evaluate

        Returns:
            The evaluated result. Returns None if the expression references
            undefined variables (matching legacy fallback parser behavior).

        Raises:
            ImportError: If the powerfx package is not installed.
        """
        if not expression:
            return expression

        if not isinstance(expression, str):
            return expression

        if not expression.startswith("="):
            return expression

        # Strip the leading '=' for evaluation
        formula = expression[1:]

        # Handle custom functions not supported by PowerFx
        # First check if the entire formula is a custom function
        result = await self._eval_custom_function(formula)
        if result is not None:
            return result

        # Pre-process nested custom functions (e.g., Upper(MessageText(...)))
        # Replace them with their evaluated results before sending to PowerFx
        formula = await self._preprocess_custom_functions(formula)

        engine = Engine()
        symbols = await self._to_powerfx_symbols()
        try:
            return engine.eval(formula, symbols=symbols)
        except ValueError as e:
            error_msg = str(e)
            # Handle undefined variable errors gracefully by returning None
            # This matches the behavior of the legacy fallback parser
            if "isn't recognized" in error_msg or "Name isn't valid" in error_msg:
                logger.debug(f"PowerFx: undefined variable in expression '{formula}', returning None")
                return None
            raise

    async def _eval_custom_function(self, formula: str) -> Any | None:
        """Handle custom functions not supported by the Python PowerFx library.

        The standard PowerFx library supports these functions but the Python wrapper
        may have limitations. We also handle Copilot Studio-specific dialects.

        Returns None if the formula is not a custom function call.
        """
        import re

        # Concat/Concatenate - string concatenation
        # In standard PowerFx, Concatenate is for strings, Concat is for tables.
        # Copilot Studio uses Concat for strings, so we support both.
        match = re.match(r"(?:Concat|Concatenate)\((.+)\)$", formula.strip())
        if match:
            args_str = match.group(1)
            # Parse comma-separated arguments (handling nested parentheses)
            args = self._parse_function_args(args_str)
            evaluated_args = []
            for arg in args:
                arg = arg.strip()
                if arg.startswith('"') and arg.endswith('"'):
                    # String literal
                    evaluated_args.append(arg[1:-1])
                elif arg.startswith("'") and arg.endswith("'"):
                    # Single-quoted string literal
                    evaluated_args.append(arg[1:-1])
                else:
                    # Variable reference - evaluate it
                    result = await self.eval(f"={arg}")
                    evaluated_args.append(str(result) if result is not None else "")
            return "".join(evaluated_args)

        # UserMessage(expr) - creates a user message dict
        match = re.match(r"UserMessage\((.+)\)$", formula.strip())
        if match:
            inner_expr = match.group(1).strip()
            # Evaluate the inner expression
            text = await self.eval(f"={inner_expr}")
            return {"role": "user", "text": str(text) if text else ""}

        # AgentMessage(expr) - creates an assistant message dict
        match = re.match(r"AgentMessage\((.+)\)$", formula.strip())
        if match:
            inner_expr = match.group(1).strip()
            text = await self.eval(f"={inner_expr}")
            return {"role": "assistant", "text": str(text) if text else ""}

        # MessageText(expr) - extracts text from the last message
        match = re.match(r"MessageText\((.+)\)$", formula.strip())
        if match:
            inner_expr = match.group(1).strip()
            # Reuse the helper method for consistent text extraction
            return await self._eval_and_replace_message_text(inner_expr)

        return None

    async def _preprocess_custom_functions(self, formula: str) -> str:
        """Pre-process custom functions nested inside other PowerFx functions.

        Custom functions like MessageText() are not supported by the PowerFx engine.
        When they appear nested inside other functions (e.g., Upper(MessageText(...))),
        we need to evaluate them first and replace with the result.

        For long strings (>500 chars), the result is stored in a temporary state variable
        to avoid exceeding PowerFx's 1000 character expression limit. This is a limitation
        of the Python PowerFx wrapper (powerfx package), which doesn't expose the
        MaximumExpressionLength configuration that the .NET PowerFxConfig provides.
        The .NET implementation defaults to 10,000 characters, while Python defaults to 1,000.

        Args:
            formula: The PowerFx formula to pre-process

        Returns:
            The formula with custom function calls replaced by their evaluated results
        """
        import re

        # Threshold for storing in state vs embedding as literal.
        # The Python PowerFx wrapper defaults to a 1000 char expression limit (vs 10,000 in .NET).
        # We use 500 to leave room for the rest of the expression around the replaced value.
        MAX_INLINE_LENGTH = 500

        # Counter for generating unique temp variable names
        temp_var_counter = 0

        # Custom functions that need pre-processing: (regex pattern, handler)
        custom_functions = [
            (r"MessageText\(", self._eval_and_replace_message_text),
        ]

        for pattern, handler in custom_functions:
            # Find all occurrences of the custom function
            while True:
                match = re.search(pattern, formula)
                if not match:
                    break

                # Find the matching closing parenthesis
                start = match.start()
                paren_start = match.end() - 1  # Position of opening (
                depth = 1
                pos = paren_start + 1
                in_string = False
                escape_next = False

                while pos < len(formula) and depth > 0:
                    char = formula[pos]
                    if escape_next:
                        escape_next = False
                        pos += 1
                        continue
                    if char == "\\":
                        escape_next = True
                        pos += 1
                        continue
                    if char == '"' and not escape_next:
                        in_string = not in_string
                    elif not in_string:
                        if char == "(":
                            depth += 1
                        elif char == ")":
                            depth -= 1
                    pos += 1

                if depth != 0:
                    # Malformed expression, skip
                    break

                # Extract the inner expression (between parentheses)
                end = pos
                inner_expr = formula[paren_start + 1 : end - 1]

                # Evaluate and get replacement
                replacement = await handler(inner_expr)

                # Replace in formula
                if isinstance(replacement, str):
                    if len(replacement) > MAX_INLINE_LENGTH:
                        # Store long strings in a temp variable to avoid PowerFx expression limit
                        temp_var_name = f"_TempMessageText{temp_var_counter}"
                        temp_var_counter += 1
                        await self.set(f"Local.{temp_var_name}", replacement)
                        replacement_str = f"Local.{temp_var_name}"
                        logger.debug(
                            f"Stored long MessageText result ({len(replacement)} chars) "
                            f"in temp variable {temp_var_name}"
                        )
                    else:
                        # Short strings can be embedded directly
                        escaped = replacement.replace('"', '""')
                        replacement_str = f'"{escaped}"'
                else:
                    replacement_str = str(replacement) if replacement is not None else '""'

                formula = formula[:start] + replacement_str + formula[end:]

        return formula

    async def _eval_and_replace_message_text(self, inner_expr: str) -> str:
        """Evaluate MessageText() and return the text result.

        Args:
            inner_expr: The expression inside MessageText()

        Returns:
            The extracted text from the messages
        """
        messages: Any = await self.eval(f"={inner_expr}")
        if isinstance(messages, list) and messages:
            last_msg: Any = messages[-1]
            if isinstance(last_msg, dict):
                # Try "text" key first (simple dict format)
                if "text" in last_msg:
                    return str(last_msg["text"])
                # Try extracting from "contents" (ChatMessage dict format)
                # ChatMessage.text concatenates text from all TextContent items
                contents = last_msg.get("contents", [])
                if isinstance(contents, list):
                    text_parts = []
                    for content in contents:
                        if isinstance(content, dict):
                            # TextContent has a "text" key
                            if content.get("type") == "text" or "text" in content:
                                text_parts.append(str(content.get("text", "")))
                        elif hasattr(content, "text"):
                            text_parts.append(str(getattr(content, "text", "")))
                    if text_parts:
                        return " ".join(text_parts)
                return ""
            if hasattr(last_msg, "text"):
                return str(getattr(last_msg, "text", ""))
        return ""

    def _parse_function_args(self, args_str: str) -> list[str]:
        """Parse comma-separated function arguments, handling nested parentheses and strings."""
        args = []
        current = []
        depth = 0
        in_string = False
        string_char = None

        for char in args_str:
            if char in ('"', "'") and not in_string:
                in_string = True
                string_char = char
                current.append(char)
            elif char == string_char and in_string:
                in_string = False
                string_char = None
                current.append(char)
            elif char == "(" and not in_string:
                depth += 1
                current.append(char)
            elif char == ")" and not in_string:
                depth -= 1
                current.append(char)
            elif char == "," and depth == 0 and not in_string:
                args.append("".join(current).strip())
                current = []
            else:
                current.append(char)

        if current:
            args.append("".join(current).strip())

        return args

    async def _to_powerfx_symbols(self) -> dict[str, Any]:
        """Convert the current state to a PowerFx symbols dictionary.

        Uses .NET-style PascalCase names (System, Local, Workflow) matching
        the .NET declarative workflow implementation.
        """
        state_data = await self.get_state_data()
        local_data = state_data.get("Local", {})
        agent_data = state_data.get("Agent", {})
        conversation_data = state_data.get("Conversation", {})
        system_data = state_data.get("System", {})
        inputs_data = state_data.get("Inputs", {})
        outputs_data = state_data.get("Outputs", {})

        symbols: dict[str, Any] = {
            # .NET-style PascalCase names (matching .NET implementation)
            "Workflow": {
                "Inputs": inputs_data,
                "Outputs": outputs_data,
            },
            "Local": local_data,
            "Agent": agent_data,
            "Conversation": conversation_data,
            "System": system_data,
            # Also expose inputs at top level for backward compatibility with =inputs.X syntax
            "inputs": inputs_data,
            # Custom namespaces
            **state_data.get("Custom", {}),
        }
        # Debug log the Local symbols to help diagnose type issues
        if local_data:
            for key, value in local_data.items():
                logger.debug(
                    f"PowerFx symbol Local.{key}: type={type(value).__name__}, "
                    f"value_preview={str(value)[:100] if value else None}"
                )
        result = _make_powerfx_safe(symbols)
        return cast(dict[str, Any], result)

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
            value = await self.get(var_path)
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

    action: Literal["break", "continue"]


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
        ctx: "WorkflowContext[Any, Any]",
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
