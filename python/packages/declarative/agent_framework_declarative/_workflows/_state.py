# Copyright (c) Microsoft. All rights reserved.

"""WorkflowState manages PowerFx variables during declarative workflow execution.

This module provides state management for declarative workflows, handling:
- Workflow inputs (read-only)
- Turn-scoped variables
- Workflow outputs
- Agent results and context
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from typing import Any, cast

from ._powerfx_limits import _PowerFxStateLimitError, _validate_powerfx_state  # pyright: ignore[reportPrivateUsage]
from ._state_path import _is_safe_path_segment  # pyright: ignore[reportPrivateUsage]

try:
    from powerfx import Engine

    _powerfx_engine: Engine | None = Engine()
except (ImportError, RuntimeError):
    # ImportError: powerfx package not installed
    # RuntimeError: .NET runtime not available or misconfigured
    _powerfx_engine = None

logger = logging.getLogger("agent_framework.declarative")


class _UnsupportedExpressionError(ValueError):
    """A formula uses syntax outside the simple fallback evaluator's subset.

    Raised by :meth:`WorkflowState._eval_simple` instead of silently returning
    an unevaluated formula, so callers can distinguish "evaluated" from
    "not supported".
    """


def _skip_quoted_token(formula: str, start: int) -> int:
    """Return the index after the quoted token starting at ``start``.

    Handles Power Fx escaped quotes (a doubled quote inside the literal).
    Returns ``len(formula)`` for an unterminated literal.
    """
    quote = formula[start]
    pos = start + 1
    while pos < len(formula):
        if formula[pos] == quote:
            if pos + 1 < len(formula) and formula[pos + 1] == quote:
                pos += 2
                continue
            return pos + 1
        pos += 1
    return len(formula)


def _skip_comment(formula: str, start: int) -> int:
    """Return the index after the ``//`` or ``/* */`` comment at ``start``, or ``start``."""
    if formula.startswith("//", start):
        pos = formula.find("\n", start)
        return len(formula) if pos == -1 else pos + 1
    if formula.startswith("/*", start):
        pos = formula.find("*/", start + 2)
        return len(formula) if pos == -1 else pos + 2
    return start


def _tokenize_formula(formula: str) -> list[tuple[str, Any]]:
    """Split a formula into ``(kind, value)`` tokens.

    Operator text is only recognized outside string literals and comments, so
    ``"a And b"`` tokenizes as one string literal. Comments are skipped as
    trivia, matching ``whole_call_args``.

    Returns:
        Tokens ending with a final ``("EOF", None)`` marker.

    Raises:
        _UnsupportedExpressionError: If the formula contains characters or
            literals outside the supported subset.
    """
    tokens: list[tuple[str, Any]] = []
    i = 0
    length = len(formula)
    while i < length:
        char = formula[i]
        if char.isspace():
            i += 1
            continue
        if char in ('"', "'"):
            end = _skip_quoted_token(formula, i)
            if end == length and formula[end - 1] != char:
                raise _UnsupportedExpressionError(f"unterminated string literal at position {i}")
            tokens.append(("STR", formula[i + 1 : end - 1].replace(char + char, char)))
            i = end
            continue
        comment_end = _skip_comment(formula, i)
        if comment_end != i:
            i = comment_end
            continue
        if char.isdigit():
            j = i
            while j < length and (formula[j].isdigit() or formula[j] == "."):
                j += 1
            text = formula[i:j]
            try:
                value: Any = float(text) if "." in text else int(text)
            except ValueError:
                raise _UnsupportedExpressionError(f"invalid numeric literal {text!r}") from None
            tokens.append(("NUM", value))
            i = j
            continue
        if char.isalpha() or char == "_":
            j = i
            while j < length and (formula[j].isalnum() or formula[j] in "_."):
                j += 1
            tokens.append(("IDENT", formula[i:j]))
            i = j
            continue
        two = formula[i : i + 2]
        if two in ("<>", "<=", ">=", "||"):
            tokens.append(("OP", two))
            i += 2
            continue
        if char in "()<>=+-*/,!":
            tokens.append(("OP", char))
            i += 1
            continue
        raise _UnsupportedExpressionError(
            f"unsupported syntax: character {char!r} at position {i} is outside the fallback subset"
        )
    tokens.append(("EOF", None))
    return tokens


_COMPARISON_OPS = ("=", "<>", "<", "<=", ">", ">=")


class _SimpleFormulaEvaluator:
    """Precedence-climbing evaluator for the fallback's supported subset.

    Operator precedence (tightest binding last)::

        Or / ||  <  And  <  = <> < > <= >=  <  + -  <  * /  <  ! / Not() / unary -

    Operators at the same level are left-associative; ``( ... )`` groups.
    """

    def __init__(self, formula: str, state: WorkflowState) -> None:
        from ._powerfx_functions import CUSTOM_FUNCTIONS

        self._formula = formula
        self._state = state
        self._custom_functions = CUSTOM_FUNCTIONS
        self._tokens = _tokenize_formula(formula)
        self._pos = 0

    def evaluate(self) -> Any:
        """Evaluate the token stream and reject unconsumed trailing input."""
        result = self._parse_or()
        kind, value = self._peek()
        if kind != "EOF":
            raise _UnsupportedExpressionError(
                f"unsupported syntax: unexpected {value!r} after a complete expression is outside the fallback subset"
            )
        return result

    def _peek(self) -> tuple[str, Any]:
        return self._tokens[self._pos]

    def _advance(self) -> tuple[str, Any]:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _match_op(self, *ops: str) -> str | None:
        kind, value = self._peek()
        if kind in ("OP", "IDENT") and value in ops:
            self._pos += 1
            return str(value)
        return None

    def _parse_or(self) -> Any:
        left = self._parse_and()
        while self._match_op("||", "Or") is not None:
            right = self._parse_and()
            left = bool(left) or bool(right)
        return left

    def _parse_and(self) -> Any:
        left = self._parse_comparison()
        while self._match_op("And") is not None:
            right = self._parse_comparison()
            left = bool(left) and bool(right)
        return left

    def _parse_comparison(self) -> Any:
        left = self._parse_additive()
        while (op := self._match_op(*_COMPARISON_OPS)) is not None:
            right = self._parse_additive()
            if op == "=":
                left = left == right
            elif op == "<>":
                left = left != right
            elif op == "<":
                left = left < right
            elif op == "<=":
                left = left <= right
            elif op == ">":
                left = left > right
            else:
                left = left >= right
        return left

    def _parse_additive(self) -> Any:
        left = self._parse_multiplicative()
        while (op := self._match_op("+", "-")) is not None:
            right = self._parse_multiplicative()
            left_num = left if left is not None else 0
            right_num = right if right is not None else 0
            if op == "+":
                try:
                    left = float(left_num) + float(right_num)
                except (ValueError, TypeError):
                    left = str(left) + str(right)
            else:
                try:
                    left = float(left_num) - float(right_num)
                except (ValueError, TypeError):
                    return self._formula
        return left

    def _parse_multiplicative(self) -> Any:
        left = self._parse_unary()
        while (op := self._match_op("*", "/")) is not None:
            right = self._parse_unary()
            try:
                if op == "*":
                    left = float(left if left is not None else 0) * float(right if right is not None else 0)
                else:
                    right_float = float(right if right is not None else 0)
                    if right_float == 0:
                        logger.warning(f"Division by zero in expression: {self._formula}")
                        return None
                    left = float(left if left is not None else 0) / right_float
            except (ValueError, TypeError):
                return self._formula
        return left

    def _parse_unary(self) -> Any:
        kind, value = self._peek()
        if kind == "OP" and value == "!":
            self._advance()
            return not bool(self._parse_unary())
        if kind == "OP" and value == "-":
            self._advance()
            operand = self._parse_unary()
            if isinstance(operand, (int, float)) and not isinstance(operand, bool):
                return -operand
            try:
                return -float(operand if operand is not None else 0)
            except (ValueError, TypeError):
                return self._formula
        return self._parse_primary()

    def _parse_primary(self) -> Any:
        kind, value = self._advance()
        if kind in ("NUM", "STR"):
            return value
        if kind == "OP" and value == "(":
            inner = self._parse_or()
            kind_close, value_close = self._advance()
            if not (kind_close == "OP" and value_close == ")"):
                raise _UnsupportedExpressionError("unbalanced parentheses in formula")
            return inner
        if kind == "IDENT" and isinstance(value, str) and value:
            if value.lower() in ("true", "false"):
                return value.lower() == "true"
            if self._peek() == ("OP", "("):
                return self._parse_call(value)
            return self._resolve_identifier(value)
        raise _UnsupportedExpressionError(f"unsupported syntax near {value!r}: outside the fallback subset")

    def _parse_call(self, name: str) -> Any:
        self._advance()
        args: list[Any] = []
        if self._peek() == ("OP", ")"):
            self._advance()
        else:
            while True:
                args.append(self._parse_or())
                kind, value = self._advance()
                if kind == "OP" and value == ",":
                    continue
                if kind == "OP" and value == ")":
                    break
                raise _UnsupportedExpressionError(f"malformed argument list in call to {name}()")
        if name == "Not":
            return not bool(args[0]) if args else True
        func = self._custom_functions.get(name)
        if func is None:
            raise _UnsupportedExpressionError(
                f"function {name}() is not supported by the fallback; install/enable PowerFx for full Power Fx support"
            )
        try:
            return func(*args)
        except Exception as e:
            logger.warning(f"Function {name} failed: {e}")
            return self._formula

    def _resolve_identifier(self, path: str) -> Any:
        if path.startswith(("Local.", "Workflow.", "Agent.", "Conversation.", "System.")):
            return self._state.get(path)
        not_found = object()
        value = self._state.get(path, default=not_found)
        if value is not not_found:
            return value
        return path


class WorkflowState:
    """Manages standalone workflow state and expression evaluation.

    Workflows created by ``WorkflowFactory`` use a separate, checkpoint-backed
    ``DeclarativeWorkflowState`` implementation.

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
        _validate_powerfx_state(inputs)
        self._inputs: dict[str, Any] = dict(inputs) if inputs else {}
        self._local: dict[str, Any] = {}
        self._outputs: dict[str, Any] = {}
        conversation_id = str(uuid.uuid4())
        self._system: dict[str, Any] = {
            "ConversationId": conversation_id,
            "LastMessage": {"Text": "", "Id": ""},
            "LastMessageText": "",
            "LastMessageId": "",
            "conversations": {
                conversation_id: {"id": conversation_id, "messages": []},
            },
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

        Dict-keyed segments may use arbitrary string keys. Segments resolved
        through object-attribute access must match ``[A-Za-z][A-Za-z0-9_]*``;
        other shapes return ``default`` without accessing the attribute.

        Args:
            path: Dot-notated path like 'Local.results' or 'Workflow.Inputs.query'
            default: Default value if path doesn't exist

        Returns:
            The value at the path, or default if not found or unreachable
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
            else:
                if not _is_safe_path_segment(part):
                    logger.warning(
                        "WorkflowState.get: rejecting attribute segment %r in path %r",
                        part,
                        path,
                    )
                    return default
                if hasattr(obj, part):
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
            existing_list = cast(list[Any], existing)
            existing_list.append(value)
            self.set(path, existing_list)
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
            message: The message to add (typically a Message or similar)
        """
        self._conversation["messages"].append(message)
        self._conversation["history"].append(message)

    def to_powerfx_symbols(self) -> dict[str, Any]:
        """Convert the current state to a PowerFx symbols dictionary.

        Returns:
            A dictionary suitable for passing to PowerFx Engine.eval()

        Raises:
            ValueError: If the state or projected symbols exceed the PowerFx state budget.
        """
        _validate_powerfx_state({
            "Inputs": self._inputs,
            "Outputs": self._outputs,
            "Local": self._local,
            "System": self._system,
            "Agent": self._agent,
            "Conversation": self._conversation,
            "Custom": self._custom,
        })
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
            for value in self._local.values():
                logger.debug(
                    "PowerFx Local symbol type=%s",
                    type(value).__name__,
                )
        _validate_powerfx_state(symbols)
        return symbols

    def eval(self, expression: str) -> Any:
        """Evaluate a PowerFx expression with the current state.

        Expressions starting with '=' are evaluated as PowerFx.
        Other strings are returned as-is. If PowerFx is unavailable or raises
        an ordinary evaluation error, the simple evaluator is used instead.
        Its state references follow :meth:`get`'s object-member rules.
        State-budget errors propagate without falling back.

        The simple evaluator supports a documented subset of Power Fx (see
        :meth:`_eval_simple`) and raises ``_UnsupportedExpressionError`` (a
        ``ValueError``) for formulas outside that subset.

        Args:
            expression: The expression to evaluate

        Returns:
            The evaluated result, or the original expression if not a PowerFx expression

        Raises:
            ValueError: If symbol construction exceeds the PowerFx state budget,
                or the formula is outside the simple evaluator's subset.
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
            except _PowerFxStateLimitError:
                raise
            except Exception as exc:
                logger.warning(f"PowerFx evaluation failed for '{expression[:50]}': {exc}")
                # Fall through to simple evaluation

        # Fallback: Simple expression evaluation using custom functions
        return self._eval_simple(formula)

    def _eval_simple(self, formula: str) -> Any:
        """Simple expression evaluation when PowerFx is not available.

        Evaluates a documented subset of Power Fx; results are best-effort and
        may differ from full Power Fx semantics. Supported:

        - Variable references: Local.X, System.X, Workflow.Inputs.X, Agent.X,
          Conversation.X, and custom namespaces (resolved through :meth:`get`)
        - Literals: "text" / 'text' (doubled-quote escapes), numbers,
          true / false (case-insensitive)
        - Operators, tightest binding last: ``Or`` / ``||``, ``And``,
          comparisons ``= <> < > <= >=``, ``+ -``, ``* /``, and
          ``!`` / ``Not()`` / unary ``-``, with left-to-right associativity
          and ``( ... )`` grouping
        - Custom function calls: If, IsBlank, Concat, Upper, Lower, ...
          (dispatched through CUSTOM_FUNCTIONS)
        - Trivia: whitespace and ``//`` / ``/* */`` comments

        Unresolved references are returned as-is. ``None`` (Blank) is treated
        as ``0`` in arithmetic, ``+`` falls back to string concatenation, and
        division by zero returns ``None``.

        Args:
            formula: The formula to evaluate (without leading '=')

        Returns:
            The evaluated result

        Raises:
            _UnsupportedExpressionError: If the formula uses syntax outside
                the supported subset, such as unknown operators (``&``),
                unknown function calls, or malformed expressions.
        """
        formula = formula.strip()
        return _SimpleFormulaEvaluator(formula, self).evaluate()

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
            return {str(k): self.eval_if_expression(v) for k, v in value.items()}  # type: ignore[reportUnknownVariableType]
        if isinstance(value, list):
            return [self.eval_if_expression(item) for item in value]  # type: ignore[reportUnknownVariableType]
        return value

    def reset_local(self) -> None:
        """Reset Local-scoped variables for a new turn.

        This clears the Local namespace while preserving other state.
        """
        self._local.clear()

    def reset_agent(self) -> None:
        """Reset the agent result for a new agent invocation."""
        self._agent.clear()

    def clone(self) -> WorkflowState:
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
