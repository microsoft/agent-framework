# Copyright (c) Microsoft. All rights reserved.

"""Child-process runner for local CodeAct subprocess mode."""

from __future__ import annotations

import ast
import asyncio
import contextlib
import io
import json
import keyword
import sys
import traceback
from collections.abc import Mapping, Sequence
from typing import Any, TextIO, cast


class _CappedTextIO(io.TextIOBase):
    def __init__(self, limit: int) -> None:
        super().__init__()
        self._limit = max(0, limit)
        self._buffer = io.StringIO()
        self.truncated = False

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        text = str(value)
        current = self._buffer.tell()
        remaining = max(0, self._limit - current)
        if remaining:
            self._buffer.write(text[:remaining])
        if len(text) > remaining:
            self.truncated = True
        return len(text)

    def getvalue(self) -> str:
        return self._buffer.getvalue()


def _json_safe_mapping(value: Mapping[Any, Any]) -> dict[str, object]:
    return {str(key): _json_safe(item) for key, item in value.items()}


def _json_safe_sequence(value: Sequence[Any]) -> list[object]:
    return [_json_safe(item) for item in value]


def _json_safe(value: object) -> object:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        if isinstance(value, Mapping):
            return _json_safe_mapping(cast("Mapping[Any, Any]", value))  # type: ignore[redundant-cast]
        if isinstance(value, (list, tuple)):
            return _json_safe_sequence(cast("Sequence[Any]", value))
        return repr(value)
    return value


def _compile_main(code: str) -> tuple[Any, bool]:
    module = ast.parse(code, mode="exec")
    body = list(module.body)
    output_present = bool(body and isinstance(body[-1], ast.Expr))
    if output_present:
        last_expr = body[-1]
        if isinstance(last_expr, ast.Expr):
            body[-1] = ast.Return(value=last_expr.value)
    else:
        body.append(ast.Return(value=ast.Constant(value=None)))

    async_function_def = cast(Any, ast.AsyncFunctionDef)
    function = async_function_def(
        name="__local_codeact_main__",
        args=ast.arguments(
            posonlyargs=[],
            args=[],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=body,
        decorator_list=[],
        returns=None,
        type_comment=None,
    )
    wrapped = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(wrapped)
    return compile(wrapped, "<local-codeact>", "exec"), output_present


def _send(control: TextIO, payload: Mapping[str, Any]) -> None:
    control.write(json.dumps(payload, separators=(",", ":")) + "\n")
    control.flush()


async def _read_response(call_id: int) -> dict[str, Any]:
    line = await asyncio.to_thread(sys.stdin.readline)
    if not line:
        raise RuntimeError("Parent process closed the tool bridge.")
    response_value: Any = json.loads(line)
    if not isinstance(response_value, dict):
        raise RuntimeError("Received an invalid tool bridge response.")
    response = cast("dict[str, Any]", response_value)
    if response.get("call_id") != call_id:
        raise RuntimeError("Received an invalid tool bridge response.")
    if not response.get("ok"):
        exc_type = str(response.get("exc_type") or "RuntimeError")
        message = str(response.get("message") or "Tool call failed.")
        raise RuntimeError(f"{exc_type}: {message}")
    return response


def _make_tool(name: str, *, control: TextIO, bridge_lock: asyncio.Lock) -> Any:
    async def _tool(**kwargs: Any) -> Any:
        return await _call_tool(name, control=control, bridge_lock=bridge_lock, kwargs=kwargs)

    _tool.__name__ = name
    return _tool


async def _call_tool(
    name: str,
    *,
    control: TextIO,
    bridge_lock: asyncio.Lock,
    kwargs: Mapping[str, Any],
) -> Any:
    call_id = id(kwargs)
    async with bridge_lock:
        _send(
            control,
            {
                "type": "tool_call",
                "call_id": call_id,
                "name": name,
                "kwargs": _json_safe(dict(kwargs)),
            },
        )
        response = await _read_response(call_id)
    return response.get("result")


async def _execute(request: Mapping[str, Any], control: TextIO) -> dict[str, Any]:
    code = str(request.get("code") or "")
    stdout = _CappedTextIO(int(request.get("max_stdout_bytes") or 0))
    stderr = _CappedTextIO(int(request.get("max_stderr_bytes") or 0))
    tool_names_value = request.get("tool_names")
    tool_names = (
        [str(name) for name in cast("Sequence[Any]", tool_names_value)] if isinstance(tool_names_value, list) else []
    )
    bridge_lock = asyncio.Lock()

    async def call_tool(name: str, **kwargs: Any) -> Any:
        return await _call_tool(name, control=control, bridge_lock=bridge_lock, kwargs=kwargs)

    globals_dict: dict[str, Any] = {
        "__builtins__": __builtins__,
        "asyncio": asyncio,
        "call_tool": call_tool,
    }
    for tool_name in tool_names:
        if tool_name.isidentifier() and not keyword.iskeyword(tool_name):
            globals_dict[tool_name] = _make_tool(tool_name, control=control, bridge_lock=bridge_lock)

    compiled, output_present = _compile_main(code)
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exec(compiled, globals_dict, globals_dict)  # noqa: S102 - this runner exists to execute generated code.
        output = await globals_dict["__local_codeact_main__"]()

    return {
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "stdout_truncated": stdout.truncated,
        "stderr_truncated": stderr.truncated,
        "output_present": output_present,
        "output": _json_safe(output),
    }


async def _main() -> int:
    control = sys.stdout
    line = await asyncio.to_thread(sys.stdin.readline)
    if not line:
        return 1
    try:
        request_value: Any = json.loads(line)
        if not isinstance(request_value, dict):
            raise ValueError("Expected a JSON object request.")
        request = cast("dict[str, Any]", request_value)
        result = await _execute(request, control)
        _send(control, {"type": "complete", "result": result})
        return 0
    except BaseException as exc:
        _send(
            control,
            {
                "type": "error",
                "exc_type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=20),
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
