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
    "os",  # Limited to explicit os.environ and lexical os.path chains
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

# Allowed top-level `os` attribute names. Descendants are validated separately
# against complete-chain allow-lists.
ALLOWED_OS_ATTRS: set[str] = {"environ", "path"}

# Lexical path helpers that do not query or mutate the filesystem.
ALLOWED_OS_PATH_ATTRS: set[str] = {
    "abspath",
    "basename",
    "commonpath",
    "commonprefix",
    "dirname",
    "expandvars",
    "isabs",
    "join",
    "normcase",
    "normpath",
    "relpath",
    "split",
    "splitdrive",
    "splitext",
    "splitroot",
}

# Read-only mapping helpers for the scrubbed child-process environment.
ALLOWED_OS_ENVIRON_ATTRS: set[str] = {
    "copy",
    "get",
}

# Builtins that consume an OS-derived value without retaining it.
_OS_VALUE_CONSUMER_BUILTINS: frozenset[str] = frozenset({"bool", "len", "print", "repr", "str"})

# Collection operations are safe only for os.environ, whose values are strings.
_OS_ENVIRON_COPY_BUILTINS: frozenset[str] = frozenset(
    {"dict", "enumerate", "frozenset", "iter", "list", "reversed", "set", "sorted", "tuple"}
)

_OS_VALUE_BUILTINS: frozenset[str] = _OS_VALUE_CONSUMER_BUILTINS | _OS_ENVIRON_COPY_BUILTINS

_SAFE_DUNDER_ATTRS: frozenset[str] = frozenset(
    {
        "__aenter__",
        "__aexit__",
        "__doc__",
        "__enter__",
        "__eq__",
        "__exit__",
        "__file__",
        "__hash__",
        "__init__",
        "__iter__",
        "__len__",
        "__module__",
        "__name__",
        "__next__",
        "__repr__",
        "__str__",
    }
)

_BLOCKED_CAPABILITY_ATTRS: frozenset[str] = frozenset(
    {
        "__builtins__",
        "_sys",
        "builtins",
        "connect_accepted_socket",
        "create_connection",
        "create_server",
        "create_subprocess_exec",
        "create_subprocess_shell",
        "create_unix_connection",
        "create_unix_server",
        "getaddrinfo",
        "getnameinfo",
        "importlib",
        "open_connection",
        "open_unix_connection",
        "socket",
        "sock_accept",
        "sock_connect",
        "sock_recv",
        "sock_recv_into",
        "sock_recvfrom",
        "sock_recvfrom_into",
        "sock_sendall",
        "sock_sendfile",
        "sock_sendto",
        "start_server",
        "start_unix_server",
        "subprocess",
        "subprocess_exec",
        "subprocess_shell",
        "sys",
    }
)

_OS_ROOT_CHAIN: tuple[str, ...] = ("os",)
_OS_PATH_CHAIN: tuple[str, ...] = ("os", "path")
_OS_ENVIRON_CHAIN: tuple[str, ...] = ("os", "environ")

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
    "__builtins__",
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
        self._os_aliases: dict[str, set[tuple[str, ...]]] = {"os": {_OS_ROOT_CHAIN}}
        self._os_containers: dict[str, set[tuple[str, ...]]] = {}
        self._shadowed_os_value_builtins: set[str] = set()

    def validate(self, code: str) -> None:
        """Validate code and raise CodeValidationError if it violates policy."""
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as exc:
            raise CodeValidationError(f"Syntax error in generated code: {exc}") from exc

        self._errors = []
        self._os_aliases = {"os": {_OS_ROOT_CHAIN}}
        self._os_containers = {}
        self._shadowed_os_value_builtins = self._find_shadowed_os_value_builtins(tree)
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

            if alias_node.name == "os":
                self._remember_os_alias(alias_node.asname or "os", _OS_ROOT_CHAIN)
            elif alias_node.name.startswith("os."):
                chain = tuple(alias_node.name.split("."))
                if chain != _OS_PATH_CHAIN:
                    self._errors.append(f"Import of '{alias_node.name}' is not allowed")
                elif alias_node.asname is not None:
                    self._remember_os_alias(alias_node.asname, chain)
                else:
                    self._remember_os_alias("os", _OS_ROOT_CHAIN)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Validate from-import statements."""
        if node.module is None:
            self._errors.append("Relative imports are not allowed")
            return

        if any(alias_node.name == "*" for alias_node in node.names):
            self._errors.append(f"Wildcard import from '{node.module}' is not allowed")

        module_name = node.module.split(".")[0]
        if module_name in self._blocked_imports:
            self._errors.append(f"Import from '{node.module}' is not allowed (blocked: {module_name})")
        elif module_name not in self._allowed_imports:
            self._errors.append(f"Import from '{node.module}' is not allowed (not in allow-list)")
        elif module_name == "os":
            for alias_node in node.names:
                chain = (*tuple(node.module.split(".")), alias_node.name)
                if node.module != "os" or alias_node.name not in self._allowed_os_attrs:
                    self._errors.append(f"Import from 'os' of '{alias_node.name}' is not allowed")
                else:
                    self._remember_os_alias(alias_node.asname or alias_node.name, chain)
        else:
            for alias_node in node.names:
                if alias_node.name.startswith("__") and alias_node.name.endswith("__"):
                    self._errors.append(
                        f"Import from '{node.module}' of reflective attribute '{alias_node.name}' is not allowed"
                    )
                elif alias_node.name in {"os", "_os"}:
                    self._remember_os_alias(alias_node.asname or alias_node.name, _OS_ROOT_CHAIN)
                elif alias_node.name in _BLOCKED_CAPABILITY_ATTRS:
                    self._errors.append(
                        f"Import from '{node.module}' of capability '{alias_node.name}' is not allowed"
                    )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """Reject access to blocked builtin objects before they can be aliased."""
        if isinstance(node.ctx, ast.Load) and node.id in self._blocked_builtins:
            self._errors.append(f"Access to builtin '{node.id}' is not allowed")

    def visit_Assign(self, node: ast.Assign) -> None:
        """Track assignments of OS-derived values."""
        for target in node.targets:
            self._track_os_provenance(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Track annotated assignments of OS-derived values."""
        if node.value is not None:
            self._track_os_provenance(node.target, node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Reject mutation of an OS-derived value."""
        target_direct, target_contained = self._get_os_provenance(node.target)
        value_direct, value_contained = self._get_os_provenance(node.value)
        if target_direct or target_contained or value_direct or value_contained:
            self._errors.append("Mutation of an OS-derived value is not allowed")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        """Track values extracted from containers during iteration."""
        self._track_os_iteration_target(node.target, node.iter)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        """Track values extracted from containers during async iteration."""
        self._track_os_iteration_target(node.target, node.iter)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        """Reject comprehensions that could extract an OS-derived object."""
        direct, contained = self._get_os_provenance(node.iter)
        if contained or any(chain != _OS_ENVIRON_CHAIN for chain in direct):
            self._errors.append("Comprehension over an OS-derived value is not allowed")
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        """Reject list comprehensions that retain OS-derived objects."""
        self._reject_os_derived_result(node.elt, "List comprehension")
        self.generic_visit(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        """Reject set comprehensions that retain OS-derived objects."""
        self._reject_os_derived_result(node.elt, "Set comprehension")
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        """Reject dictionary comprehensions that retain OS-derived objects."""
        self._reject_os_derived_result(node.key, "Dictionary comprehension")
        self._reject_os_derived_result(node.value, "Dictionary comprehension")
        self.generic_visit(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        """Reject generator expressions that retain OS-derived objects."""
        self._reject_os_derived_result(node.elt, "Generator expression")
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        """Reject pattern matching that could bind an OS-derived object."""
        direct, contained = self._get_os_provenance(node.subject)
        if direct or contained:
            self._errors.append("Pattern matching on an OS-derived value is not allowed")
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        """Reject returning OS-derived objects from local helpers."""
        if node.value is not None:
            direct, contained = self._get_os_provenance(node.value)
            if direct or contained:
                self._errors.append("Returning an OS-derived value is not allowed")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Reject OS-derived function defaults."""
        self._validate_function_defaults(node.args)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Reject OS-derived async-function defaults."""
        self._validate_function_defaults(node.args)
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        """Reject lambdas that capture or return OS-derived objects."""
        self._validate_function_defaults(node.args)
        direct, contained = self._get_os_provenance(node.body)
        if direct or contained:
            self._errors.append("Returning an OS-derived value is not allowed")
        self.generic_visit(node)

    def _remember_os_alias(self, name: str, chain: tuple[str, ...]) -> None:
        self._os_aliases.setdefault(name, set()).add(chain)

    def _remember_os_chains(
        self,
        target: ast.AST,
        direct: set[tuple[str, ...]],
        contained: set[tuple[str, ...]],
    ) -> None:
        if isinstance(target, ast.Starred):
            target = target.value

        if isinstance(target, ast.Name):
            if direct:
                self._os_aliases.setdefault(target.id, set()).update(direct)
            if contained:
                self._os_containers.setdefault(target.id, set()).update(contained)
        elif isinstance(target, (ast.Tuple, ast.List)):
            possible = direct | contained
            for target_item in target.elts:
                self._remember_os_chains(target_item, possible, set())
        elif direct or contained:
            self._errors.append("Storing an OS-derived value on an object is not allowed")

    def _track_os_provenance(self, target: ast.AST, value: ast.AST) -> None:
        if isinstance(target, ast.Starred):
            target = target.value

        if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
            starred_index = next(
                (index for index, target_item in enumerate(target.elts) if isinstance(target_item, ast.Starred)),
                None,
            )
            if starred_index is None:
                for target_item, value_item in zip(target.elts, value.elts):
                    self._track_os_provenance(target_item, value_item)
                return

            trailing_count = len(target.elts) - starred_index - 1
            for target_item, value_item in zip(target.elts[:starred_index], value.elts[:starred_index]):
                self._track_os_provenance(target_item, value_item)
            if trailing_count:
                for target_item, value_item in zip(target.elts[-trailing_count:], value.elts[-trailing_count:]):
                    self._track_os_provenance(target_item, value_item)

            star_contained: set[tuple[str, ...]] = set()
            middle_end = len(value.elts) - trailing_count if trailing_count else len(value.elts)
            for value_item in value.elts[starred_index:middle_end]:
                item_direct, item_contained = self._get_os_provenance(value_item)
                star_contained.update(item_direct)
                star_contained.update(item_contained)
            self._remember_os_chains(target.elts[starred_index], set(), star_contained)
            return

        direct, contained = self._get_os_provenance(value)
        self._remember_os_chains(target, direct, contained)

    def _track_os_iteration_target(self, target: ast.AST, iterator: ast.AST) -> None:
        direct, contained = self._get_os_provenance(iterator)
        extracted = set(contained)
        extracted.update(chain for chain in direct if chain != _OS_ENVIRON_CHAIN)
        if extracted:
            self._remember_os_chains(target, extracted, set())

    def _validate_function_defaults(self, arguments: ast.arguments) -> None:
        defaults = [*arguments.defaults, *(default for default in arguments.kw_defaults if default is not None)]
        for default in defaults:
            direct, contained = self._get_os_provenance(default)
            if direct or contained:
                self._errors.append("Using an OS-derived value as a function default is not allowed")

    def _reject_os_derived_result(self, node: ast.AST, expression_name: str) -> None:
        direct, contained = self._get_os_provenance(node)
        if direct or contained:
            self._errors.append(f"{expression_name} retaining an OS-derived value is not allowed")

    def _get_os_provenance(
        self,
        node: ast.AST,
    ) -> tuple[set[tuple[str, ...]], set[tuple[str, ...]]]:
        if isinstance(node, ast.Starred):
            return self._get_os_provenance(node.value)

        if isinstance(node, ast.Name):
            return (
                set(self._os_aliases.get(node.id, set())),
                set(self._os_containers.get(node.id, set())),
            )

        if isinstance(node, ast.Attribute):
            direct, _ = self._get_os_provenance(node.value)
            if not direct and node.attr in {"os", "_os"}:
                return ({_OS_ROOT_CHAIN}, set())
            return ({(*chain, node.attr) for chain in direct}, set())

        if isinstance(node, ast.Subscript):
            direct, contained = self._get_os_provenance(node.value)
            extracted = set(contained)
            extracted.update(chain for chain in direct if chain != _OS_ENVIRON_CHAIN)
            return extracted, set()

        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            contained: set[tuple[str, ...]] = set()
            for item in node.elts:
                item_direct, item_contained = self._get_os_provenance(item)
                contained.update(item_direct)
                contained.update(item_contained)
            return set(), contained

        if isinstance(node, ast.Dict):
            contained = set()
            for item in [*node.keys, *node.values]:
                if item is None:
                    continue
                item_direct, item_contained = self._get_os_provenance(item)
                contained.update(item_direct)
                contained.update(item_contained)
            return set(), contained

        if isinstance(node, ast.IfExp):
            body_direct, body_contained = self._get_os_provenance(node.body)
            else_direct, else_contained = self._get_os_provenance(node.orelse)
            return body_direct | else_direct, body_contained | else_contained

        if isinstance(node, ast.BoolOp):
            direct: set[tuple[str, ...]] = set()
            contained: set[tuple[str, ...]] = set()
            for value in node.values:
                value_direct, value_contained = self._get_os_provenance(value)
                direct.update(value_direct)
                contained.update(value_contained)
            return direct, contained

        if isinstance(node, ast.BinOp):
            left_direct, left_contained = self._get_os_provenance(node.left)
            right_direct, right_contained = self._get_os_provenance(node.right)
            return left_direct | right_direct, left_contained | right_contained

        return set(), set()

    def _is_allowed_os_chain(self, chain: tuple[str, ...]) -> bool:
        if chain == _OS_ROOT_CHAIN:
            return True
        if len(chain) == 2:
            return chain[0] == "os" and chain[1] in self._allowed_os_attrs
        if len(chain) != 3:
            return False
        if chain[:2] == _OS_PATH_CHAIN and "path" in self._allowed_os_attrs:
            return chain[2] in ALLOWED_OS_PATH_ATTRS
        if chain[:2] == _OS_ENVIRON_CHAIN and "environ" in self._allowed_os_attrs:
            return chain[2] in ALLOWED_OS_ENVIRON_ATTRS
        return False

    @staticmethod
    def _format_os_chains(chains: set[tuple[str, ...]]) -> str:
        return ", ".join(".".join(chain) for chain in sorted(chains))

    @staticmethod
    def _find_shadowed_os_value_builtins(tree: ast.AST) -> set[str]:
        bound_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound_names.add(node.id)
            elif isinstance(node, ast.arg):
                bound_names.add(node.arg)
            elif isinstance(node, ast.alias):
                bound_names.add(node.asname or node.name.split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                bound_names.add(node.name)
            elif isinstance(node, ast.ExceptHandler) and node.name is not None:
                bound_names.add(node.name)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name is not None:
                bound_names.add(node.name)
            elif isinstance(node, ast.MatchMapping) and node.rest is not None:
                bound_names.add(node.rest)
        return bound_names & _OS_VALUE_BUILTINS

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

        func_direct, func_contained = self._get_os_provenance(node.func)
        for chain in func_direct:
            if not self._is_allowed_os_chain(chain):
                self._errors.append(f"Call to OS-derived function '{'.'.join(chain)}' is not allowed")
        if func_contained:
            chains = self._format_os_chains(func_contained)
            self._errors.append(f"Calling a value containing OS-derived objects ({chains}) is not allowed")

        consumer_name = node.func.id if isinstance(node.func, ast.Name) else None
        is_unshadowed_builtin = (
            consumer_name is not None
            and consumer_name in _PYTHON_BUILTIN_NAMES
            and consumer_name not in self._shadowed_os_value_builtins
        )
        for argument in [*node.args, *(keyword_node.value for keyword_node in node.keywords)]:
            direct, contained = self._get_os_provenance(argument)
            consumes_value = is_unshadowed_builtin and consumer_name in _OS_VALUE_CONSUMER_BUILTINS
            copies_environment = (
                is_unshadowed_builtin
                and consumer_name in _OS_ENVIRON_COPY_BUILTINS
                and not contained
                and bool(direct)
                and all(chain == _OS_ENVIRON_CHAIN for chain in direct)
            )
            if (direct or contained) and not consumes_value and not copies_environment:
                chains = self._format_os_chains(direct | contained)
                self._errors.append(f"Passing an OS-derived value ({chains}) to a call is not allowed")

        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if (
                attr_name.startswith("__")
                and attr_name.endswith("__")
                and attr_name not in {"__init__", "__str__", "__repr__", "__eq__", "__hash__"}
            ):
                self._errors.append(f"Call to dunder method '{attr_name}' is not allowed")

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Validate attribute access."""
        if node.attr in _BLOCKED_CAPABILITY_ATTRS:
            self._errors.append(f"Access to capability attribute '{node.attr}' is not allowed")

        direct, _ = self._get_os_provenance(node)
        _, base_contained = self._get_os_provenance(node.value)
        for chain in direct:
            if not self._is_allowed_os_chain(chain):
                self._errors.append(f"Access to {'.'.join(chain)} is not allowed")
            elif not isinstance(node.ctx, ast.Load):
                self._errors.append(f"Mutation of {'.'.join(chain)} is not allowed")
        if base_contained:
            chains = self._format_os_chains(base_contained)
            self._errors.append(f"Attribute access on a value containing OS-derived objects ({chains}) is not allowed")

        if (
            node.attr.startswith("__")
            and node.attr.endswith("__")
            and node.attr not in _SAFE_DUNDER_ATTRS
        ):
            self._errors.append(f"Access to attribute '{node.attr}' is not allowed")

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Permit only read access to the scrubbed environment mapping."""
        direct, contained = self._get_os_provenance(node.value)
        if contained:
            chains = self._format_os_chains(contained)
            self._errors.append(f"Subscript access to a value containing OS-derived objects ({chains}) is not allowed")
        for chain in direct:
            if chain != _OS_ENVIRON_CHAIN or "environ" not in self._allowed_os_attrs:
                self._errors.append(f"Subscript access to {'.'.join(chain)} is not allowed")
            elif not isinstance(node.ctx, ast.Load):
                self._errors.append("Mutation of os.environ is not allowed")
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
        allowed_os_attrs: Custom set of allowed top-level ``os`` attribute names
            (replaces the default ``{"environ", "path"}`` allow-list). Nested
            ``os.path`` and ``os.environ`` access remains constrained by the
            built-in complete-chain policy.

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


def _main() -> int:
    """Script entrypoint: read a JSON request from stdin and validate it.

    Request shape:
        {
            "code": "...",
            "allowed_imports": [...]?,
            "blocked_imports": [...]?,
            "allowed_builtins": [...]?,
            "blocked_builtins": [...]?,
            "allowed_os_attrs": [...]?
        }

    On success: exit code 0, no output required.
    On validation failure: exit code 1, JSON {"errors": ["..."]} on stdout.
    On request error: exit code 2, JSON {"message": "..."} on stdout.
    """
    import json
    import sys

    raw = sys.stdin.read()
    try:
        request = json.loads(raw) if raw.strip() else {}
        if not isinstance(request, dict):
            raise ValueError("Validator request must be a JSON object.")
        code = request.get("code")
        if not isinstance(code, str):
            raise ValueError("Validator request must include a 'code' string field.")
    except Exception as exc:  # noqa: BLE001 - report any parse error to caller
        json.dump({"message": f"Invalid validator request: {exc}"}, sys.stdout)
        return 2

    def _as_set(value: Any) -> set[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("Validator allow/block lists must be arrays of strings.")
        return {str(item) for item in value}

    try:
        validate_code(
            code,
            allowed_imports=_as_set(request.get("allowed_imports")),
            blocked_imports=_as_set(request.get("blocked_imports")),
            allowed_builtins=_as_set(request.get("allowed_builtins")),
            blocked_builtins=_as_set(request.get("blocked_builtins")),
            allowed_os_attrs=_as_set(request.get("allowed_os_attrs")),
        )
    except CodeValidationError as exc:
        message = str(exc)
        lines = [line.lstrip("- ").rstrip() for line in message.splitlines() if line.strip()]
        if lines and lines[0].startswith("Generated code violates"):
            lines = lines[1:]
        if not lines:
            lines = [message]
        json.dump({"errors": lines}, sys.stdout)
        return 1
    except Exception as exc:  # noqa: BLE001 - convert unexpected errors to a structured response
        json.dump({"errors": [f"{type(exc).__name__}: {exc}"]}, sys.stdout)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
