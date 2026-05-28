# Copyright (c) Microsoft. All rights reserved.

"""``LocalCodeActProvider`` - context provider injecting local CodeAct."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_framework import AgentSession, ContextProvider, FunctionTool, SessionContext
from agent_framework._tools import ApprovalMode

from ._execute_code_tool import LocalExecuteCodeTool
from ._types import ExecutionMode, FileMount, FileMountInput, ProcessExecutionLimits


class LocalCodeActProvider(ContextProvider):
    """Inject a local CodeAct surface using provider-owned host tools."""

    DEFAULT_SOURCE_ID = "local_codeact"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
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
        """Initialize a local CodeAct context provider.

        Args:
            source_id: Provider source identifier.
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
        super().__init__(source_id)
        self._execute_code_tool = LocalExecuteCodeTool(
            tools=tools,
            approval_mode=approval_mode,
            workspace_root=workspace_root,
            file_mounts=file_mounts,
            execution_limits=execution_limits,
            env=env,
            execution_mode=execution_mode,
            python_executable=python_executable,
            runner_script=runner_script,
            allowed_imports=allowed_imports,
            blocked_imports=blocked_imports,
            allowed_builtins=allowed_builtins,
            blocked_builtins=blocked_builtins,
            allowed_os_attrs=allowed_os_attrs,
        )

    def add_tools(
        self,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]],
    ) -> None:
        """Add provider-owned host tools."""
        self._execute_code_tool.add_tools(tools)

    def get_tools(self) -> list[FunctionTool]:
        """Return provider-owned host tools."""
        return self._execute_code_tool.get_tools()

    def remove_tool(self, name: str) -> None:
        """Remove one provider-owned host tool by name."""
        self._execute_code_tool.remove_tool(name)

    def clear_tools(self) -> None:
        """Remove all provider-owned host tools."""
        self._execute_code_tool.clear_tools()

    def add_file_mounts(self, file_mounts: FileMountInput | Sequence[FileMountInput]) -> None:
        """Add provider-managed file mounts."""
        self._execute_code_tool.add_file_mounts(file_mounts)

    def get_file_mounts(self) -> list[FileMount]:
        """Return provider-managed file mounts, excluding ``workspace_root``."""
        return self._execute_code_tool.get_file_mounts()

    def remove_file_mount(self, mount_path: str) -> None:
        """Remove one provider-managed file mount by its display/capture path."""
        self._execute_code_tool.remove_file_mount(mount_path)

    def clear_file_mounts(self) -> None:
        """Remove all provider-managed file mounts."""
        self._execute_code_tool.clear_file_mounts()

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject CodeAct instructions and a run-scoped execute-code tool."""
        run_tool = self._execute_code_tool.create_run_tool()
        state[self.source_id] = run_tool.build_serializable_state()
        context.extend_instructions(self.source_id, run_tool.build_instructions(tools_visible_to_model=False))
        context.extend_tools(self.source_id, [run_tool])
