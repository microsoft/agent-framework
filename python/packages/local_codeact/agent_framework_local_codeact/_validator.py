# Copyright (c) Microsoft. All rights reserved.

"""AST validation for generated Python code."""

from __future__ import annotations

import ast
import builtins as _builtins
from typing import Any

_PYTHON_BUILTIN_NAMES: frozenset[str] = frozenset(dir(_builtins))

# Allowed imports that generated code may use.
ALLOWED_IMPORTS: set[str] = {
    "asyncio",
    "pathlib",
    "json",
    "math",
    "datetime",
    "time",
    "itertools",
    "functools",
    "collections",
    "typing",
    "dataclasses",
    "decimal",
    "fractions",
    "re",
    "base64",
    "hashlib",
    "uuid",
    "random",
    "os",  # Limited to os.environ, os.path - validated via attribute access
}

# Blocked imports that expose dangerous capabilities.
BLOCKED_IMPORTS: set[str] = {
    "sys",
    "subprocess",
    "socket",
    "urllib",
    "requests",
    "http",
    "ftplib",
    "smtplib",
    "telnetlib",
    "multiprocessing",
    "threading",
    "ctypes",
    "shutil",
    "tempfile",
    "importlib",
    "builtins",
    "__builtin__",
}

# Allowed `os` attribute names. Generated code may only touch `os.environ` and
# `os.path`; everything else (file I/O, process control, mutating helpers, etc.)
# is rejected by default. Users may pass a custom allow-list via
# ``allowed_os_attrs`` on the validator entry points.
ALLOWED_OS_ATTRS: set[str] = {"environ", "path"}

# Allowed builtin function names that generated code may call.
# Note: getattr/setattr/hasattr/delattr are NOT included because they can bypass
# AST attribute restrictions (e.g., getattr(os, 'system')('...') avoids os.system check).
# User-defined functions and registered tools are allowed at runtime.
ALLOWED_BUILTINS: set[str] = {
    "print",
    "len",
    "str",
    "int",
    "float",
    "bool",
    "list",
    "dict",
    "tuple",
    "set",
    "frozenset",
    "range",
    "enumerate",
    "zip",
    "map",
    "filter",
    "sorted",
    "reversed",
    "sum",
    "min",
    "max",
    "abs",
    "round",
    "pow",
    "divmod",
    "all",
    "any",
    "chr",
    "ord",
    "hex",
    "oct",
    "bin",
    "format",
    "repr",
    "ascii",
    "bytes",
    "bytearray",
    "memoryview",
    "isinstance",
    "issubclass",
    "callable",
    "type",
    "id",
    "hash",
    "next",
    "iter",
    "slice",
}

# Blocked builtin function names that expose dangerous capabilities.
BLOCKED_BUILTINS: set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "globals",
    "locals",
    "vars",
    "dir",
    "open",  # File I/O must go through pathlib with explicit mounts
    "input",
    "help",
    "breakpoint",
    "exit",
    "quit",
    "copyright",
    "credits",
    "license",
    "delattr",
    "getattr",  # Can bypass AST attribute checks: getattr(os, 'system')
    "setattr",  # Can bypass AST attribute checks
    "hasattr",  # Can probe for dangerous attributes
}

# Allowed AST node types for code structure and operations.
ALLOWED_AST_NODES: set[type[ast.AST]] = {
    ast.Module,
    ast.Expr,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.If,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.ExceptHandler,
    ast.Pass,
    ast.Break,
    ast.Continue,
    ast.Return,
    ast.Await,
    # Comparisons and boolean operations
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
    ast.UAdd,
    ast.USub,
    ast.Invert,
    # Data access
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Del,
    ast.Attribute,
    ast.Subscript,
    ast.Slice,
    # Literals
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Dict,
    # Arithmetic and bitwise operations
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.FloorDiv,
    ast.Pow,
    ast.LShift,
    ast.RShift,
    ast.BitOr,
    ast.BitXor,
    ast.BitAnd,
    # Function calls and comprehensions
    ast.Call,
    ast.keyword,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.comprehension,
    # Control flow helpers
    ast.IfExp,
    ast.JoinedStr,
    ast.FormattedValue,
    # Imports (validated separately)
    ast.Import,
    ast.ImportFrom,
    ast.alias,
    # Function definitions (for local helpers)
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.arguments,
    ast.arg,
    # Lambda expressions
    ast.Lambda,
    # Match statements (Python 3.10+)
    ast.Match,
    ast.match_case,
    ast.MatchValue,
    ast.MatchSingleton,
    ast.MatchSequence,
    ast.MatchMapping,
    ast.MatchClass,
    ast.MatchStar,
    ast.MatchAs,
    ast.MatchOr,
    # Starred expressions
    ast.Starred,
}


class CodeValidationError(ValueError):
    """Raised when generated code violates the allow-list policy."""

    pass


class _CodeValidator(ast.NodeVisitor):
    """AST visitor that validates generated code against allow-lists."""

    def __init__(
        self,
        *,
        allowed_imports: set[str] | None = None,
        blocked_imports: set[str] | None = None,
        allowed_builtins: set[str] | None = None,
        blocked_builtins: set[str] | None = None,
        allowed_os_attrs: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._errors: list[str] = []
        self._allowed_imports = allowed_imports if allowed_imports is not None else ALLOWED_IMPORTS
        self._blocked_imports = blocked_imports if blocked_imports is not None else BLOCKED_IMPORTS
        self._allowed_builtins = allowed_builtins if allowed_builtins is not None else ALLOWED_BUILTINS
        self._blocked_builtins = blocked_builtins if blocked_builtins is not None else BLOCKED_BUILTINS
        self._allowed_os_attrs = allowed_os_attrs if allowed_os_attrs is not None else ALLOWED_OS_ATTRS

    def validate(self, code: str) -> None:
        """Validate code and raise CodeValidationError if it violates policy."""
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as exc:
            raise CodeValidationError(f"Syntax error in generated code: {exc}") from exc

        self._errors = []
        self.visit(tree)

        if self._errors:
            raise CodeValidationError(
                "Generated code violates allow-list policy:\n" + "\n".join(f"- {err}" for err in self._errors)
            )

    def visit(self, node: ast.AST) -> Any:
        """Visit a node and check if its type is allowed."""
        node_type = type(node)
        if node_type not in ALLOWED_AST_NODES:
            self._errors.append(f"AST node type '{node_type.__name__}' is not allowed")
            return None
        return super().visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Validate import statements."""
        for alias_node in node.names:
            module_name = alias_node.name.split(".")[0]
            if module_name in self._blocked_imports:
                self._errors.append(f"Import of '{alias_node.name}' is not allowed (blocked: {module_name})")
            elif module_name not in self._allowed_imports:
                self._errors.append(f"Import of '{alias_node.name}' is not allowed (not in allow-list)")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Validate from-import statements."""
        if node.module is None:
            self._errors.append("Relative imports are not allowed")
            return

        module_name = node.module.split(".")[0]
        if module_name in self._blocked_imports:
            self._errors.append(f"Import from '{node.module}' is not allowed (blocked: {module_name})")
        elif module_name not in self._allowed_imports:
            self._errors.append(f"Import from '{node.module}' is not allowed (not in allow-list)")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Validate function calls.

        For names that match a real Python builtin we enforce both the block-list
        and the allow-list. Names that are not builtins are treated as user-defined
        functions or registered tools and are allowed (validated at runtime).
        """
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in self._blocked_builtins:
                self._errors.append(f"Call to builtin '{func_name}' is not allowed")
            elif func_name in _PYTHON_BUILTIN_NAMES and func_name not in self._allowed_builtins:
                # Real builtin that wasn't explicitly allowed — reject so the allow-list is meaningful.
                self._errors.append(f"Call to builtin '{func_name}' is not in the allowed builtins list")

        # Check for attribute access to dangerous methods
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            # Block common dangerous attribute methods
            if (
                attr_name.startswith("__")
                and attr_name.endswith("__")
                and attr_name not in {"__init__", "__str__", "__repr__", "__eq__", "__hash__"}
            ):
                self._errors.append(f"Call to dunder method '{attr_name}' is not allowed")

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Validate attribute access."""
        # Enforce the `os` attribute allow-list. Anything outside `ALLOWED_OS_ATTRS`
        # (file I/O, process control, mutating helpers, etc.) is rejected so the
        # validator matches the documented `os.environ` / `os.path`-only contract.
        if isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr not in self._allowed_os_attrs:
            self._errors.append(f"Access to os.{node.attr} is not allowed")

        # Block access to certain dangerous attributes
        if (
            node.attr.startswith("__")
            and node.attr.endswith("__")
            and node.attr
            not in {
                "__name__",
                "__doc__",
                "__dict__",
                "__class__",
                "__module__",
                "__file__",
                "__init__",
                "__str__",
                "__repr__",
                "__eq__",
                "__hash__",
                "__len__",
                "__iter__",
                "__next__",
                "__enter__",
                "__exit__",
                "__aenter__",
                "__aexit__",
            }
        ):
            self._errors.append(f"Access to attribute '{node.attr}' is not allowed")

        self.generic_visit(node)


def validate_code(
    code: str,
    *,
    allowed_imports: set[str] | None = None,
    blocked_imports: set[str] | None = None,
    allowed_builtins: set[str] | None = None,
    blocked_builtins: set[str] | None = None,
    allowed_os_attrs: set[str] | None = None,
) -> None:
    """Validate generated code against AST allow-lists.

    Args:
        code: Python source code to validate.
        allowed_imports: Custom set of allowed module names (replaces defaults).
        blocked_imports: Custom set of blocked module names (replaces defaults).
        allowed_builtins: Custom set of allowed builtin names (replaces defaults).
        blocked_builtins: Custom set of blocked builtin names (replaces defaults).
        allowed_os_attrs: Custom set of allowed ``os`` attribute names
            (replaces the default ``{"environ", "path"}`` allow-list).

    Raises:
        CodeValidationError: If the code violates the allow-list policy.
    """
    validator = _CodeValidator(
        allowed_imports=allowed_imports,
        blocked_imports=blocked_imports,
        allowed_builtins=allowed_builtins,
        blocked_builtins=blocked_builtins,
        allowed_os_attrs=allowed_os_attrs,
    )
    validator.validate(code)
