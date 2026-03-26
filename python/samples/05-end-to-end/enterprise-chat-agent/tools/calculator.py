"""
Calculator Tool

Provides safe mathematical expression evaluation with DoS protections.
"""

import ast
import operator
from typing import Union

from agent_framework import tool

# Safety limits to prevent DoS attacks
MAX_EXPRESSION_LENGTH = 200  # Maximum characters in expression
MAX_EXPONENT = 100  # Maximum allowed exponent value
MAX_RESULT_MAGNITUDE = 1e308  # Maximum result magnitude (near float max)

# Safe operators for expression evaluation
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> Union[int, float]:
    """
    Safely evaluate an AST node containing only numeric operations.
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    if isinstance(node, ast.BinOp):
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")

        # Enforce exponent limit to prevent DoS (e.g., 2 ** 1000000000)
        if op_type is ast.Pow and abs(right) > MAX_EXPONENT:
            raise ValueError(
                f"Exponent {right} exceeds maximum allowed ({MAX_EXPONENT})"
            )

        result = SAFE_OPERATORS[op_type](left, right)

        # Check result magnitude
        if abs(result) > MAX_RESULT_MAGNITUDE:
            raise ValueError("Result exceeds maximum allowed magnitude")

        return result

    if isinstance(node, ast.UnaryOp):
        operand = _safe_eval(node.operand)
        op_type = type(node.op)
        if op_type in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type.__name__}")

    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)

    raise ValueError(f"Unsupported AST node type: {type(node).__name__}")


@tool
def calculate(expression: str) -> float:
    """
    Evaluate a mathematical expression safely.

    Supports: +, -, *, /, ** (power with exponent <= 100), parentheses

    Args:
        expression: A mathematical expression string (e.g., "85 * 0.15")
                   Maximum length: 200 characters.

    Returns:
        The result of the calculation.

    Raises:
        ValueError: If the expression contains unsupported operations,
                   exceeds length limits, or has exponents > 100.
    """
    # Length limit to prevent parsing DoS
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError(
            f"Expression exceeds maximum length ({MAX_EXPRESSION_LENGTH} chars)"
        )

    try:
        # Parse the expression into an AST
        tree = ast.parse(expression, mode="eval")

        # Safely evaluate the AST
        result = _safe_eval(tree)

        return float(result)
    except (SyntaxError, ValueError) as e:
        raise ValueError(f"Invalid expression '{expression}': {e}") from e
