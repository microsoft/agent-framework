# Copyright (c) Microsoft. All rights reserved.

"""Inline (non-durable) Monty execution bridge and type-stub generation.

Adapted from https://github.com/anthonychu/maf-codeact-monty-python.
"""

from __future__ import annotations

import asyncio
import inspect
import keyword
import types
import typing
from collections.abc import Callable, Sequence
from typing import Annotated, Any, cast, get_type_hints

MAX_PRINT_OUTPUT_CHARS = 8192

# Prelude injected into all Monty code so `asyncio.gather` works for fan-out.
_CODEACT_PRELUDE = """\
import asyncio
"""


def _ensure_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("Non-finite floating point values are not JSON-safe.")
        return value
    if isinstance(value, (list, tuple)):
        items = cast("list[object] | tuple[object, ...]", value)
        return [_ensure_json_value(item) for item in items]
    if isinstance(value, dict):
        as_dict = cast("dict[object, object]", value)
        return {str(k): _ensure_json_value(v) for k, v in as_dict.items()}
    raise ValueError(f"Value of type {type(value).__name__} is not JSON-safe.")


def _external_error(exc: Exception) -> dict[str, str]:
    return {"exc_type": type(exc).__name__, "message": str(exc)}


def _parse_call_tool(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not args:
        raise ValueError("call_tool requires a tool name as the first argument.")
    name = args[0]
    if not isinstance(name, str) or not name:
        raise ValueError("Tool name must be a non-empty string.")
    if len(args) > 1:
        raise ValueError(
            "call_tool accepts only the tool name as a positional argument. Use keyword arguments for parameters."
        )
    return name, dict(kwargs)


def _build_code(code: str) -> str:
    return f"{_CODEACT_PRELUDE}\n{code}"


def _python_type_repr(annotation: Any) -> str:
    """Convert a Python type annotation to its string representation for stubs."""
    if annotation is inspect.Parameter.empty:
        return "Any"
    if annotation is type(None):
        # ``None`` in annotations represents ``NoneType``; emit it literally so
        # ``ty`` can validate ``Optional[X]`` / ``Union[..., None]`` / ``-> None``
        # signatures correctly.
        return "None"
    origin = typing.get_origin(annotation)
    if origin is Annotated:
        args = typing.get_args(annotation)
        return _python_type_repr(args[0]) if args else "Any"
    if origin is not None:
        args = typing.get_args(annotation)
        # Normalize ``typing.Union[...]`` and PEP-604 ``X | Y`` to PEP-604 syntax so
        # ``None`` is preserved across both forms.
        if origin is typing.Union or origin is types.UnionType:
            return " | ".join(_python_type_repr(a) for a in args) if args else "Any"
        origin_name = getattr(origin, "__name__", None)
        if origin_name is None:
            origin_name = str(origin)
            if origin_name.startswith("<class '"):
                origin_name = origin_name[8:-2]
        if args:
            arg_strs = ", ".join(_python_type_repr(a) for a in args)
            return f"{origin_name}[{arg_strs}]"
        return origin_name
    if hasattr(annotation, "__name__"):
        return str(annotation.__name__)
    return str(annotation)


def generate_type_stubs(tool_callables: dict[str, Callable[..., Any]]) -> str:
    """Generate Python type stub declarations for tools + DSL primitives.

    Stubs are fed to Monty's ``type_check_stubs`` so ``ty`` can validate the
    LLM-generated code against the actual tool signatures before any host
    call runs.

    Tools whose ``name`` is not a valid Python identifier are skipped because
    their name cannot be safely splatted into stub source. The model can still
    reach them via the ``call_tool("weird name", ...)`` fallback at runtime,
    but they will not get type-checked stubs.
    """
    lines: list[str] = [
        "from typing import Any",
        "",
        "# DSL primitives",
        "async def call_tool(name: str, **kwargs: Any) -> Any:",
        "    raise NotImplementedError()",
        "",
        "# Registered tools - call directly with typed arguments",
    ]

    for name, func in sorted(tool_callables.items()):
        if not name.isidentifier() or keyword.iskeyword(name):
            # A non-identifier name (or a Python keyword) would inject invalid
            # / dangerous syntax into the stub source. Skip stub generation;
            # the tool stays reachable through ``call_tool(name, ...)``.
            continue
        try:
            sig = inspect.signature(func)
            hints = get_type_hints(func, include_extras=True)
        except (ValueError, TypeError):
            lines.append(f"async def {name}(**kwargs: Any) -> Any:")
            lines.append("    raise NotImplementedError()")
            lines.append("")
            continue

        params: list[str] = []
        for param_name, param in sig.parameters.items():
            annotation = hints.get(param_name, inspect.Parameter.empty)
            type_str = _python_type_repr(annotation)
            if param.default is not inspect.Parameter.empty:
                params.append(f"{param_name}: {type_str} = ...")
            else:
                params.append(f"{param_name}: {type_str}")

        return_annotation = hints.get("return", inspect.Parameter.empty)
        return_str = _python_type_repr(return_annotation)
        param_str = ", ".join(params)
        lines.append(f"async def {name}({param_str}) -> {return_str}:")
        lines.append("    raise NotImplementedError()")
        lines.append("")

    return "\n".join(lines)


class _PrintCollector:
    """Collect Monty stdout, capped at ``MAX_PRINT_OUTPUT_CHARS``."""

    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.truncated: bool = False
        self._size: int = 0  # running character count to avoid O(n) per append

    def __call__(self, stream: str, text: str) -> None:
        if self.truncated:
            return
        remaining = MAX_PRINT_OUTPUT_CHARS - self._size
        if remaining <= 0:
            self.truncated = True
            return
        text_value = str(text)
        if len(text_value) > remaining:
            clipped = text_value[:remaining]
            self.chunks.append(clipped)
            self._size += len(clipped)
            self.truncated = True
        else:
            self.chunks.append(text_value)
            self._size += len(text_value)

    @property
    def output(self) -> str:
        return "".join(self.chunks)


def load_monty() -> Any:
    """Import ``pydantic_monty`` lazily so unit tests can run without it.

    Returns the module so callers can read ``Monty``, ``MontyComplete``,
    ``FunctionSnapshot``, ``FutureSnapshot``, ``NameLookupSnapshot`` from it.
    """
    try:
        import pydantic_monty
    except ImportError as exc:
        raise RuntimeError(
            "The `pydantic-monty` package is required to execute Monty CodeAct code. "
            "Install it with `pip install pydantic-monty`."
        ) from exc
    return pydantic_monty


class InlineCodeBridge:
    """Execute Monty code inline (non-durable).

    Supports both ``await call_tool('name', ...)`` and direct ``await name(...)``
    calls. When Monty yields a :class:`FutureSnapshot`, the bridge invokes the
    registered host tools and resumes execution with the results.
    """

    def __init__(
        self,
        tool_map: dict[str, Callable[..., Any]],
        *,
        type_stubs: str | None = None,
        mounts: Sequence[Any] | None = None,
        resource_limits: dict[str, Any] | None = None,
    ) -> None:
        self.tool_map: dict[str, Callable[..., Any]] = dict(tool_map)
        self.type_stubs: str | None = type_stubs
        self._mounts = tuple(mounts) if mounts else ()
        self._resource_limits = resource_limits
        self._pending_calls: dict[int, tuple[str, dict[str, Any]]] = {}

    async def run(self, code: str) -> dict[str, Any]:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Code must be a non-empty string.")

        monty_module = load_monty()
        Monty = monty_module.Monty
        MontyComplete = monty_module.MontyComplete
        FunctionSnapshot = monty_module.FunctionSnapshot
        FutureSnapshot = monty_module.FutureSnapshot
        NameLookupSnapshot = monty_module.NameLookupSnapshot

        printer = _PrintCollector()
        monty = Monty(
            _build_code(code),
            script_name="codeact.py",
            type_check=self.type_stubs is not None,
            type_check_stubs=self.type_stubs,
        )
        start_kwargs: dict[str, Any] = {"print_callback": printer}
        if self._mounts:
            start_kwargs["mount"] = list(self._mounts)
        if self._resource_limits:
            start_kwargs["limits"] = self._resource_limits
        progress = monty.start(**start_kwargs)

        while True:
            if isinstance(progress, MontyComplete):
                return {
                    "output": _ensure_json_value(progress.output),
                    "stdout": printer.output,
                    "truncated": printer.truncated,
                }
            if isinstance(progress, FunctionSnapshot):
                progress = self._handle_function(progress)
                continue
            if isinstance(progress, FutureSnapshot):
                progress = await self._handle_future(progress)
                continue
            if isinstance(progress, NameLookupSnapshot):
                raise RuntimeError(f"Name lookup not supported: {progress.variable_name!r}")
            raise RuntimeError(f"Unsupported Monty progress type: {type(progress).__name__}")

    def _handle_function(self, snapshot: Any) -> Any:
        if snapshot.is_os_function:
            return snapshot.resume({
                "exc_type": "PermissionError",
                "message": "OS and filesystem calls are not available.",
            })

        function_name = str(snapshot.function_name)

        if function_name in self.tool_map:
            return self._schedule_direct_tool(snapshot, function_name)
        if function_name == "call_tool":
            return self._schedule_call_tool(snapshot)

        return snapshot.resume({
            "exc_type": "NameError",
            "message": f"Function {function_name!r} is not available.",
        })

    def _schedule_direct_tool(self, snapshot: Any, name: str) -> Any:
        # Positional args are rejected up-front by ``ty`` because the generated
        # stubs declare every parameter as keyword-typed. Anything that slips
        # through (e.g. tools with no signature inspection) is forwarded to the
        # host tool as-is via kwargs only.
        self._pending_calls[int(snapshot.call_id)] = (name, dict(snapshot.kwargs))
        return snapshot.resume({"future": ...})

    def _schedule_call_tool(self, snapshot: Any) -> Any:
        try:
            name, kwargs = _parse_call_tool(snapshot.args, snapshot.kwargs)
            if name not in self.tool_map:
                allowed = ", ".join(sorted(self.tool_map.keys())) or "<none>"
                raise ValueError(f"Tool {name!r} is not registered. Available tools: {allowed}")
            self._pending_calls[int(snapshot.call_id)] = (name, kwargs)
        except Exception as exc:
            return snapshot.resume(_external_error(exc))
        return snapshot.resume({"future": ...})

    async def _handle_future(self, snapshot: Any) -> Any:
        pending_call_ids = [int(cid) for cid in snapshot.pending_call_ids]
        if not pending_call_ids:
            return snapshot.resume({})

        entries: list[tuple[int, tuple[str, dict[str, Any]]]] = []
        for cid in pending_call_ids:
            if cid not in self._pending_calls:
                raise RuntimeError(f"Unknown future call ID: {cid}")
            entries.append((cid, self._pending_calls.pop(cid)))

        tasks = [self._invoke_tool(cid, name, kwargs) for cid, (name, kwargs) in entries]
        results = await asyncio.gather(*tasks)
        resume_results: dict[int, Any] = dict(results)
        return snapshot.resume(resume_results)

    async def _invoke_tool(self, cid: int, name: str, kwargs: dict[str, Any]) -> tuple[int, Any]:
        # Every entry in ``self.tool_map`` is produced by ``_make_tool_callback``
        # as ``partial(FunctionTool.invoke, skip_parsing=True)``. ``FunctionTool.invoke``
        # is always ``async def``, so a plain ``await`` is correct for every call and
        # avoids relying on ``inspect.iscoroutinefunction(partial(...))``, which can
        # return ``False`` for some ``partial`` shapes (cpython#98590) and would route
        # the call through ``asyncio.to_thread`` with an unawaited coroutine return.
        try:
            result = await self.tool_map[name](**kwargs)
            return cid, {"return_value": _ensure_json_value(result)}
        except Exception as exc:
            return cid, _external_error(exc)
