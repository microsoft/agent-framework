# Copyright (c) Microsoft. All rights reserved.

"""Execution bridges for local CodeAct."""

from __future__ import annotations

import ast
import asyncio
import contextlib
import io
import json
import keyword
import os
import subprocess  # noqa: S404 - subprocess mode is the default execution strategy for this package.
import traceback
from collections.abc import Mapping, Sequence
from copy import copy
from typing import Any, cast

from agent_framework import FunctionTool

from ._types import ProcessExecutionLimits


def _json_safe_mapping(value: Mapping[Any, Any]) -> dict[str, object]:
    return {str(key): json_safe(item) for key, item in value.items()}


def _json_safe_sequence(value: Sequence[Any]) -> list[object]:
    return [json_safe(item) for item in value]


def json_safe(value: object) -> object:
    """Return a JSON-safe representation of ``value``."""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        if isinstance(value, Mapping):
            return _json_safe_mapping(cast("Mapping[Any, Any]", value))  # type: ignore[redundant-cast]
        if isinstance(value, (list, tuple)):
            return _json_safe_sequence(cast("Sequence[Any]", value))
        return repr(value)
    return value


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


def _build_child_env(env: Mapping[str, str]) -> dict[str, str]:
    child_env = {key: str(value) for key, value in env.items()}
    if os.name == "nt":
        for key in ("SYSTEMROOT", "COMSPEC", "PATHEXT"):
            if key in os.environ and key not in child_env:
                child_env[key] = os.environ[key]
    return child_env


def _check_result_size(result: Mapping[str, Any], *, limits: ProcessExecutionLimits) -> None:
    encoded = json.dumps(result, separators=(",", ":")).encode("utf-8")
    if len(encoded) > limits.max_result_bytes:
        raise RuntimeError("Generated code result exceeded max_result_bytes.")


async def _invoke_tool(tool_obj: FunctionTool, kwargs: Mapping[str, Any]) -> Any:
    return await copy(tool_obj).invoke(skip_parsing=True, **dict(kwargs))


class SubprocessCodeBridge:
    """Parent-side bridge for subprocess execution and host-tool dispatch."""

    def __init__(
        self,
        *,
        tools: Sequence[FunctionTool],
        limits: ProcessExecutionLimits,
        env: Mapping[str, str],
        cwd: str | None,
        python_executable: str,
        runner_script: str | None,
    ) -> None:
        self._tools = {tool_obj.name: tool_obj for tool_obj in tools}
        self._limits = limits
        self._env = dict(env)
        self._cwd = cwd
        self._python_executable = python_executable
        self._runner_script = runner_script

    async def run(self, code: str) -> dict[str, Any]:
        """Run generated code in a child Python process."""
        command = [self._python_executable, "-I"]
        if self._runner_script is None:
            command.extend(["-m", "agent_framework_local_codeact._runner"])
        else:
            command.append(self._runner_script)

        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self._cwd,
            env=_build_child_env(self._env),
        )
        try:
            return await asyncio.wait_for(self._communicate(process, code), timeout=self._limits.timeout_seconds)
        except TimeoutError as exc:
            await self._stop_process(process)
            raise TimeoutError(f"Generated code exceeded {self._limits.timeout_seconds} seconds.") from exc

    async def _communicate(self, process: asyncio.subprocess.Process, code: str) -> dict[str, Any]:
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("Subprocess pipes were not created.")
        request = {
            "code": code,
            "tool_names": list(self._tools),
            "max_stdout_bytes": self._limits.max_stdout_bytes,
            "max_stderr_bytes": self._limits.max_stderr_bytes,
        }
        process.stdin.write(json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n")
        await process.stdin.drain()

        while True:
            line = await process.stdout.readline()
            if not line:
                stderr = await self._read_stderr(process)
                raise RuntimeError(f"Local CodeAct subprocess exited without a result. stderr: {stderr}")
            try:
                message_value: Any = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError as exc:
                await self._stop_process(process)
                raise RuntimeError("Local CodeAct subprocess emitted invalid bridge data.") from exc
            if not isinstance(message_value, dict):
                continue
            message = cast("dict[str, Any]", message_value)
            message_type = message.get("type")
            if message_type == "tool_call":
                await self._handle_tool_call(process, message)
                continue
            if message_type == "complete":
                result = message.get("result")
                if not isinstance(result, dict):
                    raise RuntimeError("Local CodeAct subprocess returned an invalid result.")
                result_dict = cast("dict[str, Any]", result)
                _check_result_size(result_dict, limits=self._limits)
                await process.wait()
                return dict(result_dict)
            if message_type == "error":
                details = str(message.get("traceback") or message.get("message") or "Unknown execution error.")
                await self._stop_process(process)
                raise RuntimeError(details)

    async def _handle_tool_call(self, process: asyncio.subprocess.Process, message: Mapping[str, Any]) -> None:
        if process.stdin is None:
            raise RuntimeError("Subprocess stdin was not created.")
        call_id = int(message.get("call_id") or 0)
        name = str(message.get("name") or "")
        kwargs_value: Any = message.get("kwargs")
        if kwargs_value is None:
            kwargs_value = {}
        response: dict[str, Any]
        if name not in self._tools:
            response = {
                "call_id": call_id,
                "ok": False,
                "exc_type": "ValueError",
                "message": f"Tool {name!r} is not registered.",
            }
        elif not isinstance(kwargs_value, Mapping):
            response = {
                "call_id": call_id,
                "ok": False,
                "exc_type": "TypeError",
                "message": "Tool kwargs must be a JSON object.",
            }
        else:
            try:
                result = await _invoke_tool(self._tools[name], cast("Mapping[str, Any]", kwargs_value))
                response = {"call_id": call_id, "ok": True, "result": json_safe(result)}
            except Exception as exc:
                response = {
                    "call_id": call_id,
                    "ok": False,
                    "exc_type": type(exc).__name__,
                    "message": str(exc),
                }
        process.stdin.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")
        await process.stdin.drain()

    async def _read_stderr(self, process: asyncio.subprocess.Process) -> str:
        if process.stderr is None:
            return ""
        data = await process.stderr.read(self._limits.max_stderr_bytes)
        return data.decode("utf-8", errors="replace")

    async def _stop_process(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=1)
        except TimeoutError:
            process.kill()
            await process.wait()


class UnsafeInProcessCodeBridge:
    """Same-interpreter execution bridge for debugging only."""

    def __init__(self, *, tools: Sequence[FunctionTool], limits: ProcessExecutionLimits) -> None:
        self._tools = {tool_obj.name: tool_obj for tool_obj in tools}
        self._limits = limits

    async def run(self, code: str) -> dict[str, Any]:
        """Run generated code in the current interpreter."""
        return await asyncio.wait_for(self._run_without_timeout_control(code), timeout=self._limits.timeout_seconds)

    async def _run_without_timeout_control(self, code: str) -> dict[str, Any]:
        stdout = _CappedTextIO(self._limits.max_stdout_bytes)
        stderr = _CappedTextIO(self._limits.max_stderr_bytes)

        async def call_tool(name: str, **kwargs: Any) -> Any:
            if name not in self._tools:
                raise ValueError(f"Tool {name!r} is not registered.")
            return json_safe(await _invoke_tool(self._tools[name], kwargs))

        globals_dict: dict[str, Any] = {
            "__builtins__": __builtins__,
            "asyncio": asyncio,
            "call_tool": call_tool,
        }
        for tool_name in self._tools:
            if tool_name.isidentifier() and not keyword.iskeyword(tool_name):
                globals_dict[tool_name] = self._make_direct_tool(tool_name)

        compiled, output_present = self._compile_main(code)
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(compiled, globals_dict, globals_dict)  # noqa: S102 - explicit unsafe in-process mode.
                output = await globals_dict["__local_codeact_main__"]()
        except Exception:
            raise RuntimeError(traceback.format_exc(limit=20)) from None

        result = {
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "stdout_truncated": stdout.truncated,
            "stderr_truncated": stderr.truncated,
            "output_present": output_present,
            "output": json_safe(output),
        }
        _check_result_size(result, limits=self._limits)
        return result

    def _make_direct_tool(self, name: str) -> Any:
        async def _tool(**kwargs: Any) -> Any:
            if name not in self._tools:
                raise ValueError(f"Tool {name!r} is not registered.")
            return json_safe(await _invoke_tool(self._tools[name], kwargs))

        _tool.__name__ = name
        return _tool

    def _compile_main(self, code: str) -> tuple[Any, bool]:
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
