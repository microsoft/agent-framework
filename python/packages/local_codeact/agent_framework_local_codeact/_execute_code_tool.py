# Copyright (c) Microsoft. All rights reserved.

"""``LocalExecuteCodeTool`` - run Python locally through a CodeAct surface."""

from __future__ import annotations

import contextlib
import json
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from agent_framework import Content, FunctionTool
from agent_framework._tools import ApprovalMode, normalize_tools

from ._bridge import SubprocessCodeBridge, UnsafeInProcessCodeBridge
from ._files import (
    WORKSPACE_MOUNT_PATH,
    capture_written_files,
    is_file_mount_pair,
    normalize_file_mount,
    normalize_mount_path,
    resolve_existing_directory,
    snapshot_writable_mounts,
)
from ._instructions import build_codeact_instructions, build_execute_code_description
from ._types import ExecutionMode, FileMount, FileMountInput, ProcessExecutionLimits
from ._validator import CodeValidationError, validate_code

EXECUTE_CODE_TOOL_NAME = "execute_code"
EXECUTE_CODE_TOOL_DESCRIPTION = "Execute Python locally in the agent environment."

EXECUTE_CODE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "title": "_ExecuteCodeInput",
    "properties": {
        "code": {
            "type": "string",
            "title": "Code",
            "description": "Python code to execute locally in the agent environment.",
        },
    },
    "required": ["code"],
}


def _collect_tools(*tool_groups: Any) -> list[FunctionTool]:
    """Merge tool groups, dropping ``execute_code`` entries and deduping by name."""
    tools_by_name: dict[str, FunctionTool] = {}
    for tool_group in tool_groups:
        normalized_group = normalize_tools(tool_group)
        for tool_obj in normalized_group:
            if not isinstance(tool_obj, FunctionTool):
                continue
            if tool_obj.name == EXECUTE_CODE_TOOL_NAME:
                continue
            tools_by_name.pop(tool_obj.name, None)
            tools_by_name[tool_obj.name] = tool_obj
    return list(tools_by_name.values())


def _resolve_execute_code_approval_mode(
    *, base_approval_mode: ApprovalMode, tools: Sequence[FunctionTool]
) -> ApprovalMode:
    if base_approval_mode == "always_require":
        return "always_require"
    if any(tool_obj.approval_mode == "always_require" for tool_obj in tools):
        return "always_require"
    return "never_require"


def _validate_code(
    code: str,
    *,
    limits: ProcessExecutionLimits,
    allowed_imports: set[str] | None = None,
    blocked_imports: set[str] | None = None,
    allowed_builtins: set[str] | None = None,
    blocked_builtins: set[str] | None = None,
    allowed_os_attrs: set[str] | None = None,
) -> None:
    if not isinstance(code, str):
        raise TypeError("code must be a string.")
    if not code.strip():
        raise ValueError("code must not be empty.")
    size = len(code.encode("utf-8"))
    if size > limits.max_code_bytes:
        raise ValueError(f"code exceeds max_code_bytes ({limits.max_code_bytes}).")
    # Validate code against AST allow-lists
    validate_code(
        code,
        allowed_imports=allowed_imports,
        blocked_imports=blocked_imports,
        allowed_builtins=allowed_builtins,
        blocked_builtins=blocked_builtins,
        allowed_os_attrs=allowed_os_attrs,
    )


def _looks_like_path(value: str) -> bool:
    return "/" in value or "\\" in value


def _normalize_python_executable(value: str | Path | None) -> str:
    if value is None:
        return sys.executable
    raw = str(value).strip()
    if not raw:
        raise ValueError("python_executable must not be empty.")
    candidate = Path(raw).expanduser()
    if candidate.is_absolute() or _looks_like_path(raw):
        absolute = candidate.absolute()
        if not absolute.exists():
            raise ValueError(f"python_executable {raw!r} must point to an existing executable.")
        if not absolute.is_file():
            raise ValueError(f"python_executable {raw!r} must point to an executable file.")
        return str(absolute)
    return raw


def _normalize_runner_script(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    try:
        resolved = Path(value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"runner_script {str(value)!r} must point to an existing Python file.") from exc
    if not resolved.is_file():
        raise ValueError(f"runner_script {str(value)!r} must point to an existing Python file.")
    return resolved


def _build_execution_contents(*, result: Mapping[str, Any]) -> list[Content]:
    stdout = str(result.get("stdout") or "").replace("\r\n", "\n")
    stderr = str(result.get("stderr") or "").replace("\r\n", "\n")
    output_present = bool(result.get("output_present"))
    output_value = result.get("output")
    stdout_truncated = bool(result.get("stdout_truncated"))
    stderr_truncated = bool(result.get("stderr_truncated"))

    outputs: list[Content] = []
    if stdout:
        text = stdout
        if stdout_truncated:
            text = f"{text}\n\n[stdout truncated]"
        outputs.append(Content.from_text(text))
    elif stdout_truncated:
        outputs.append(Content.from_text("[stdout truncated]"))

    if stderr:
        text = stderr
        if stderr_truncated:
            text = f"{text}\n\n[stderr truncated]"
        outputs.append(Content.from_text(text, additional_properties={"stream": "stderr"}))
    elif stderr_truncated:
        outputs.append(Content.from_text("[stderr truncated]", additional_properties={"stream": "stderr"}))

    if output_present:
        try:
            serialized_output = json.dumps(output_value, ensure_ascii=False)
        except (TypeError, ValueError):
            serialized_output = repr(output_value)
        outputs.append(Content.from_text(serialized_output))

    if not outputs:
        outputs.append(Content.from_text("Code executed successfully without output."))

    return outputs


class LocalExecuteCodeTool(FunctionTool):
    """Execute Python code locally, with subprocess mode as the default.

    This tool is intended for externally sandboxed environments such as Foundry
    hosted agents. Its controls are defense-in-depth only and do not make Python
    execution safe on an unsandboxed host.
    """

    def __init__(
        self,
        *,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None = None,
        approval_mode: ApprovalMode | None = None,
        workspace_root: str | Path | None = None,
        file_mounts: FileMountInput | Sequence[FileMountInput] | None = None,
        execution_limits: ProcessExecutionLimits | None = None,
        env: Mapping[str, str] | None = None,
        execution_mode: ExecutionMode = "subprocess",
        python_executable: str | Path | None = None,
        runner_script: str | Path | None = None,
        allowed_imports: set[str] | None = None,
        blocked_imports: set[str] | None = None,
        allowed_builtins: set[str] | None = None,
        blocked_builtins: set[str] | None = None,
        allowed_os_attrs: set[str] | None = None,
    ) -> None:
        """Initialize a local execute-code tool.

        Args:
            tools: Host tools available to generated code.
            approval_mode: Base approval mode (propagates ``always_require`` from tools).
            workspace_root: Read-write workspace directory (auto-mounted at /input).
            file_mounts: Additional file mount configurations.
            execution_limits: Timeout and byte limits for execution.
            env: Environment variables for subprocess mode (does not apply to unsafe mode).
            execution_mode: Either 'subprocess' (default) or 'unsafe_in_process'.
            python_executable: Python interpreter path (defaults to sys.executable).
            runner_script: Path to runner script (for hosts that bundle the runner).
            allowed_imports: Custom allowed imports (replaces defaults).
            blocked_imports: Custom blocked imports (replaces defaults).
            allowed_builtins: Custom allowed builtins (replaces defaults).
            blocked_builtins: Custom blocked builtins (replaces defaults).
            allowed_os_attrs: Custom allowed ``os`` attribute names (replaces the
                default ``{"environ", "path"}`` allow-list).
        """
        super().__init__(
            name=EXECUTE_CODE_TOOL_NAME,
            description=EXECUTE_CODE_TOOL_DESCRIPTION,
            approval_mode="never_require",
            func=self._run_code,
            input_model=EXECUTE_CODE_INPUT_SCHEMA,
        )
        self._default_approval_mode: ApprovalMode = approval_mode or "never_require"
        self._managed_tools: list[FunctionTool] = []
        self._workspace_root: Path | None = (
            resolve_existing_directory(workspace_root) if workspace_root is not None else None
        )
        self._file_mounts: dict[str, FileMount] = {}
        self._execution_limits = execution_limits or ProcessExecutionLimits()
        self._env = dict(env or {})
        if execution_mode not in {"subprocess", "unsafe_in_process"}:
            raise ValueError("execution_mode must be 'subprocess' or 'unsafe_in_process'.")
        self._execution_mode: ExecutionMode = execution_mode
        self._python_executable = _normalize_python_executable(python_executable)
        self._runner_script = _normalize_runner_script(runner_script)
        self._allowed_imports = allowed_imports
        self._blocked_imports = blocked_imports
        self._allowed_builtins = allowed_builtins
        self._blocked_builtins = blocked_builtins
        self._allowed_os_attrs = allowed_os_attrs
        if tools is not None:
            self.add_tools(tools)
        if file_mounts is not None:
            self.add_file_mounts(file_mounts)

        self._refresh_approval_mode()

    @property
    def description(self) -> str:
        if not hasattr(self, "_managed_tools"):
            return str(self.__dict__.get("description", EXECUTE_CODE_TOOL_DESCRIPTION))
        return build_execute_code_description(
            tools=self._managed_tools,
            mounts=self._effective_mounts(),
        )

    @description.setter
    def description(self, value: str) -> None:
        self.__dict__["description"] = value

    def add_tools(
        self,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]],
    ) -> None:
        """Add host tools available to generated code."""
        self._managed_tools = _collect_tools(self._managed_tools, tools)
        self._refresh_approval_mode()

    def get_tools(self) -> list[FunctionTool]:
        """Return the currently managed host tools."""
        return list(self._managed_tools)

    def remove_tool(self, name: str) -> None:
        """Remove one managed host tool by name."""
        remaining_tools = [tool_obj for tool_obj in self._managed_tools if tool_obj.name != name]
        if len(remaining_tools) == len(self._managed_tools):
            raise KeyError(f"No managed tool named {name!r} is registered.")
        self._managed_tools = remaining_tools
        self._refresh_approval_mode()

    def clear_tools(self) -> None:
        """Remove all managed host tools."""
        self._managed_tools = []
        self._refresh_approval_mode()

    def add_file_mounts(self, file_mounts: FileMountInput | Sequence[FileMountInput]) -> None:
        """Add one or more file mounts."""
        if isinstance(file_mounts, (str, FileMount)) or is_file_mount_pair(file_mounts):
            normalized = [normalize_file_mount(cast("FileMountInput", file_mounts))]
        else:
            normalized = [normalize_file_mount(item) for item in cast("Sequence[FileMountInput]", file_mounts)]

        for mount in normalized:
            self._file_mounts[mount.mount_path] = mount

    def get_file_mounts(self) -> list[FileMount]:
        """Return configured file mounts, excluding ``workspace_root``."""
        return list(self._file_mounts.values())

    def remove_file_mount(self, mount_path: str) -> None:
        """Remove one file mount by its display/capture path."""
        normalized = normalize_mount_path(mount_path)
        if normalized not in self._file_mounts:
            raise KeyError(f"No file mount exists for {mount_path!r}.")
        del self._file_mounts[normalized]

    def clear_file_mounts(self) -> None:
        """Remove all configured file mounts."""
        self._file_mounts.clear()

    @property
    def workspace_root(self) -> Path | None:
        """Return the configured workspace root, if any."""
        return self._workspace_root

    @property
    def execution_limits(self) -> ProcessExecutionLimits:
        """Return the configured process execution limits."""
        return self._execution_limits

    @property
    def execution_mode(self) -> ExecutionMode:
        """Return the configured execution mode."""
        return self._execution_mode

    @property
    def python_executable(self) -> str:
        """Return the Python executable used for subprocess execution."""
        return self._python_executable

    @property
    def runner_script(self) -> Path | None:
        """Return the custom runner script used for subprocess execution, if any."""
        return self._runner_script

    def build_instructions(self, *, tools_visible_to_model: bool) -> str:
        """Build current CodeAct instructions for this execute-code surface."""
        return build_codeact_instructions(
            tools=list(self._managed_tools),
            tools_visible_to_model=tools_visible_to_model,
            mounts=self._effective_mounts(),
        )

    def create_run_tool(self) -> LocalExecuteCodeTool:
        """Create a run-scoped snapshot of this execute-code surface."""
        return LocalExecuteCodeTool(
            tools=self.get_tools(),
            approval_mode=self._default_approval_mode,
            workspace_root=self._workspace_root,
            file_mounts=list(self._file_mounts.values()) or None,
            execution_limits=self._execution_limits,
            env=self._env,
            execution_mode=self._execution_mode,
            python_executable=self._python_executable,
            runner_script=self._runner_script,
            allowed_imports=self._allowed_imports,
            blocked_imports=self._blocked_imports,
            allowed_builtins=self._allowed_builtins,
            blocked_builtins=self._blocked_builtins,
            allowed_os_attrs=self._allowed_os_attrs,
        )

    def build_serializable_state(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the effective run state."""
        mounts = self._effective_mounts()
        approval_mode = _resolve_execute_code_approval_mode(
            base_approval_mode=self._default_approval_mode,
            tools=self._managed_tools,
        )
        return {
            "runtime": "local_codeact",
            "execution_mode": self._execution_mode,
            "python_executable": self._python_executable,
            "runner_script": str(self._runner_script) if self._runner_script is not None else None,
            "approval_mode": approval_mode,
            "tool_names": [tool_obj.name for tool_obj in self._managed_tools],
            "workspace_root": str(self._workspace_root) if self._workspace_root is not None else None,
            "file_mounts": [
                {
                    "host_path": str(mount.host_path),
                    "mount_path": mount.mount_path,
                    "mode": mount.mode,
                    "write_bytes_limit": mount.write_bytes_limit,
                }
                for mount in mounts
            ],
            "execution_limits": {
                "timeout_seconds": self._execution_limits.timeout_seconds,
                "max_code_bytes": self._execution_limits.max_code_bytes,
                "max_stdout_bytes": self._execution_limits.max_stdout_bytes,
                "max_stderr_bytes": self._execution_limits.max_stderr_bytes,
                "max_result_bytes": self._execution_limits.max_result_bytes,
                "max_captured_file_bytes": self._execution_limits.max_captured_file_bytes,
                "max_total_captured_file_bytes": self._execution_limits.max_total_captured_file_bytes,
            },
            "env_keys": sorted(self._env),
        }

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        self.__dict__["description"] = self.description
        return super().to_dict(exclude=exclude, exclude_none=exclude_none)

    def _refresh_approval_mode(self) -> None:
        self.approval_mode = _resolve_execute_code_approval_mode(
            base_approval_mode=self._default_approval_mode,
            tools=self._managed_tools,
        )

    def _effective_mounts(self) -> list[FileMount]:
        mounts: list[FileMount] = []
        if self._workspace_root is not None and WORKSPACE_MOUNT_PATH not in self._file_mounts:
            mounts.append(
                FileMount(
                    host_path=self._workspace_root,
                    mount_path=WORKSPACE_MOUNT_PATH,
                    mode="read-write",
                    write_bytes_limit=None,
                )
            )
        mounts.extend(self._file_mounts.values())
        return mounts

    async def _run_code(self, *, code: str) -> list[Content]:
        try:
            _validate_code(
                code,
                limits=self._execution_limits,
                allowed_imports=self._allowed_imports,
                blocked_imports=self._blocked_imports,
                allowed_builtins=self._allowed_builtins,
                blocked_builtins=self._blocked_builtins,
                allowed_os_attrs=self._allowed_os_attrs,
            )
        except (TypeError, ValueError, CodeValidationError) as exc:
            return [Content.from_error(message="Invalid code", error_details=str(exc))]

        tools = list(self._managed_tools)
        mounts = self._effective_mounts()
        pre_state = snapshot_writable_mounts(mounts)

        cwd: str | None = None
        temp_dir: tempfile.TemporaryDirectory[str] | None = None
        if self._workspace_root is not None:
            cwd = str(self._workspace_root)
        elif self._execution_mode == "subprocess":
            # ignore_cleanup_errors handles the Windows race where a freshly-killed
            # subprocess may still hold a file handle in the workspace; without it
            # tempfile's recursive retry can hit RecursionError on Windows.
            temp_dir = tempfile.TemporaryDirectory(prefix="local-codeact-", ignore_cleanup_errors=True)
            cwd = temp_dir.name

        try:
            bridge = (
                UnsafeInProcessCodeBridge(tools=tools, limits=self._execution_limits)
                if self._execution_mode == "unsafe_in_process"
                else SubprocessCodeBridge(
                    tools=tools,
                    limits=self._execution_limits,
                    env=self._env,
                    cwd=cwd,
                    python_executable=self._python_executable,
                    runner_script=str(self._runner_script) if self._runner_script is not None else None,
                )
            )
            result = await bridge.run(code)
        except Exception as exc:
            return [
                Content.from_error(
                    message="Execution error",
                    error_details=f"{type(exc).__name__}: {exc}",
                ),
            ]
        finally:
            if temp_dir is not None:
                # Best-effort cleanup; TemporaryDirectory(ignore_cleanup_errors=True)
                # absorbs Windows file-lock errors. Swallow anything else (e.g. the
                # RecursionError some Python versions raise inside their cleanup retry)
                # so the caller still receives the proper error Content.
                with contextlib.suppress(Exception):
                    temp_dir.cleanup()

        contents = _build_execution_contents(result=result)
        contents.extend(capture_written_files(mounts, pre_state, limits=self._execution_limits))
        return contents
